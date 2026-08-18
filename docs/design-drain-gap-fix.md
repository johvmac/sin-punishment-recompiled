# Design: fixing the external-message drain gap (attract-mode freeze)

Status: **proposal, not implemented.** Written 2026-08-17 after three failed
opportunistic attempts. Read this before touching the scheduler again.

## 1. The bug, in one paragraph

`ultramodern` stages hardware events (VI retrace, SP, DP, SI, AI, PI) into a
lock-free `external_messages` queue from native threads. They only become
*receivable* when some **game thread** calls a drain-triggering primitive
(`osSendMesg`/`osRecvMesg`/`wait_for_external_message*`). Sin & Punishment's
thread 3 does most of that draining in practice. When thread 3 parks inside
`boot_func_8004EDD4`'s wait-for-completion loop, nothing drains; VI retrace stops
reaching `0x800A326C`; the game's display scheduler (thread 19,
`boot_func_8004E154`) never wakes; it never sends the type-1 completion thread 3
is waiting for; every other thread parks behind them. Total quiescence at
**exactly 1240 gfx tasks** every run, in every config.

Evidence: `docs/boot-debugging-2026-08-13.md`, 2026-08-17 entries.

## 2. Why the existing "pre-drain" fix doesn't work

`threads.cpp:wait_for_resumed()` currently does:

```cpp
ultramodern::wait_for_external_message_timed(PASS_RDRAM 0);  // attempt drain
thread_context->running.wait();
```

Three independent reasons this cannot close the gap:

1. **It drains at most one message.** `wait_for_external_message_timed` dequeues
   a single `QueuedMessage`, not a loop.
2. **It drains before parking, so it loses the race.** The retrace that matters
   arrives ~16ms *after* the last thread parks. Nothing looks again.
3. **`running.wait()` is unbounded.** Once entered, only another game thread's
   `signal()` can end it — and by hypothesis there is no other runnable thread.

It is not harmful, but it is not a fix. Do not count it as one.

## 3. Constraints the design must respect (verified in code, not assumed)

- **`schedule_running_thread()` (`scheduling.cpp`) only inserts into
  `running_queue`. It does not signal.** So `do_send()` waking a waiter merely
  makes it *queued*, not *running*.
- **The only places that actually start a thread are `resume_thread()` (via
  `run_next_thread()`) and `resume_thread_and_wait()`** — both called by the one
  currently-active game thread. Handoff is explicit and single-threaded.
- **Therefore the true invariant is: at most one game thread is unparked at a
  time**, and *that* is what protects the unsynchronized scheduler state
  (`thread_queue_insert/pop`, `running_queue`, per-thread `state`).
- **Re-entrancy is real**: `do_send`/`do_recv` can reach `check_running_queue()`
  -> `swap_to_thread()` -> `resume_thread_and_wait()` -> `wait_for_resumed()`.
  Any lock held across a park would deadlock.
- `pause_self`/`yield_self`/`yield_self_1ms` already drain then
  `check_running_queue()`; `check_running_queue()` only yields to a *higher
  priority* thread (this is what made the earlier `yield_self_1ms` substitution
  starve the scheduler).

## 4. What has already been tried and why each failed

| attempt | result | cause |
|---|---|---|
| VI thread calls `dequeue_external_messages()` directly | SIGSEGV | `do_send` mutates scheduler state concurrently with an active game thread |
| Guard `boot_func_8004E154`'s `osRecvMesg` with `yield_self_1ms()` | worse (0 gfx tasks) | `check_running_queue()` only hands off to higher priority; real path hands off unconditionally |
| Drain in `run_next_thread()`'s empty-queue branch | dead code | `wait_for_resumed()` parks without ever calling `run_next_thread()` |

## 5. Option A — full mutex + condition-variable scheduler (correct, invasive)

Replace each thread's counting semaphore with one global `scheduler_mutex` plus a
per-thread `condition_variable`, and take the mutex around *all* scheduler-state
mutation (`do_send`, `do_recv`, queue ops, `run_next_thread`).

Parking becomes:

```cpp
std::unique_lock lk{scheduler_mutex};
while (!self->runnable) {
    if (self->cv.wait_for(lk, 2ms) == std::cv_status::timeout) {
        dequeue_external_messages_locked(PASS_RDRAM1);   // safe: we hold it
        dispatch_one_runnable_locked(PASS_RDRAM1);
    }
}
self->runnable = false;
```

This solves re-entrancy for free: `cv.wait_for` **atomically releases** the mutex
while parked, so a thread that parks from inside `do_send` does not hold it.

- **Pros:** fixes the whole class at once (VI/SP/DP/SI/AI/PI), removes the
  fragile implicit invariant, correct by construction.
- **Cons:** touches the core of `ultramodern`, which is **shared upstream code**
  also used by Zelda64Recomp/BanjoRecomp. Every `RDRAM_ARG` scheduler path needs
  auditing for lock discipline. High blast radius; hard to A/B in small steps.

## 6. Option B — quiescence watchdog (additive, low risk) — **RECOMMENDED**

**Key observation:** the reason the VI-thread drain segfaulted is that a game
thread may be actively mutating scheduler state. But **when every game thread is
parked, no game thread can be mutating anything** — by definition they are all
blocked in `running.wait()`. In that state a native thread may safely touch
scheduler state, with no lock at all.

So: detect true quiescence, and only then act.

```cpp
// incremented when a game thread resumes, decremented immediately before it parks
std::atomic<int> active_game_threads{0};

// watchdog thread, started next to the VI thread
while (running) {
    sleep_for(4ms);
    if (active_game_threads.load(std::memory_order_acquire) != 0) continue;
    if (external_messages_empty()) continue;

    // No game thread is unparked: safe to deliver and dispatch.
    dequeue_external_messages(PASS_RDRAM1);   // may queue threads runnable
    if (!thread_queue_empty(PASS_RDRAM running_queue)) {
        run_next_thread(PASS_RDRAM1);         // signal exactly one
    }
}
```

with `wait_for_resumed()` becoming:

```cpp
active_game_threads.fetch_sub(1, std::memory_order_release);
thread_context->running.wait();
active_game_threads.fetch_add(1, std::memory_order_acquire);
```

**Why this is safe:** a thread only becomes unparked by being signalled, and the
only signaller while the count is zero is the watchdog, which signals exactly one
thread and then immediately sees a non-zero count on its next pass. Normal
operation is completely untouched — the fast path adds only two relaxed atomic
ops and the watchdog does nothing whenever any thread is running.

**Races to verify before trusting it** (do not skip):
1. **Decrement-then-block window.** Between `fetch_sub` and `running.wait()` the
   thread is counted as parked but has not blocked. It touches no scheduler state
   in that window (verify by reading `wait_for_resumed` after any future edit).
   If the watchdog signals it there, the counting semaphore remembers the signal
   and `wait()` returns immediately — correct, not lost.
2. **Stale signal.** `LightweightSemaphore` is counting, so a thread signalled
   before parking wakes at once and re-increments without watchdog involvement.
   Benign, but it means the count can go 0 -> 1 spontaneously; the watchdog must
   re-check the count *after* deciding to act, and abort if non-zero.
3. **`run_next_thread()`'s throw.** The watchdog must not call it on an empty
   queue (guarded above), or it will convert a freeze into a crash.
4. **Shutdown.** Watchdog must exit cleanly and not touch RDRAM after teardown.

- **Pros:** additive; zero change to the hot path; no lock, so no re-entrancy
  problem; small enough to A/B honestly; easy to disable behind an env var for
  comparison.
- **Cons:** a watchdog is a heuristic layer over an invariant that is still
  implicit — it makes the symptom go away without making the model correct.
  Option A remains the right long-term answer.

## 7. Option C — per-queue timed wait in the game's scheduler (rejected)

Patch `boot_func_8004E154`'s `osRecvMesg` to a timed wait so it self-drains.
Rejected: it fixes one thread's instance of a general problem, it was already
tried in a related form and regressed, and it puts game-specific scheduling
policy into a `sinpunishment.toml` patch where the next affected queue will need
its own copy.

## 8. Test plan (any attempt must clear all of these)

1. **`SNP_HEARTBEAT=1` must pass 1240 gfx tasks and keep incrementing.** This is
   the pass/fail signal — not screenshots (see the playbook's liveness rule).
2. **`scripts/freeze_survey.sh 5`** on the fixed build vs.
   `known_good_builds/…-2026-08-14-title-screen`; report outcome *rates*, never a
   single run.
3. **No new boot-reliability regression** — the SI work currently costs ~2/5
   boots; the fix must not add to that.
4. **`scripts/gdb_threads.sh`** at t≈60s: no thread parked on `0x800A66D0` or
   `0x800A326C` indefinitely.
5. **User confirmation on screen before anything is called a new baseline**
   (standing rule — the attract loop must visibly continue past the brick/water
   scene).

## 9. Recommendation

Implement **Option B** behind an env flag (`SNP_DRAIN_WATCHDOG=1`) so it can be
A/B'd against the identical binary, verify races 1-4 by reading the code paths
rather than assuming, then run the full test plan. If it holds, propose Option A
upstream separately as the principled fix — it benefits every project on this
runtime, not just this one.

---

## 10. UPDATE 2026-08-17: Option B is INVALID — measured before implementing

Option B triggers on "all game threads parked" (`active_game_threads == 0`).
**That state never occurs at the freeze.** Verified with a rate-limited probe on
`check_running_queue`'s declined-handoff branch (`SNP_SCHED_PROBE=1`):

```
[heartbeat] t=42s gfx_tasks=1240  +28
[heartbeat] t=43s gfx_tasks=1240  +0   <<< frozen
[sched]     t=43s declines=71471  runnable thread 1 (pri 0) <= self 3 (pri 10)
[sched]     t=49s declines=79957  runnable thread 1 (pri 0) <= self 3 (pri 10)
```

Declines continue at **~1,420/second straight through the freeze**. So at the
frozen state:

- **thread 3 is actively running** (it is the one calling `check_running_queue`),
  spinning in `boot_func_80025E44`'s `yield_self_1ms` idle loop;
- **thread 1 (priority 0) is runnable and permanently starved**, because
  `check_running_queue()` only hands off when `next->priority > self->priority`,
  and `0 > 10` is false.

The watchdog would have been dead code — the same failure mode as the earlier
`run_next_thread`-empty-branch attempt. **Four designs, four different reasons
the trigger never fires.** The lesson is consistent: verify the trigger
condition actually occurs *before* building anything on it.

### What this changes about the diagnosis

`yield_self_1ms()` *does* drain (`wait_for_external_message_timed(1)`), and
thread 3 calls it ~1,420 times/second, so **external messages are being drained
continuously at the freeze.** The earlier "nothing drains once thread 3 parks"
framing (section 1) is therefore **not** what happens in the silent-freeze shape.
It may still describe the `No threads left to run!` shape seen under
`SNP_TRACE=1`, which is a different path — do not merge the two without evidence.

### The open question, restated precisely

Thread 19 (display scheduler, priority 120) is blocked on `0x800A326C` awaiting
VI retrace (`0x29A`). Thread 3 is draining external messages constantly. If a
retrace were being delivered, `do_send` would queue thread 19, and
`check_running_queue` **would** hand off to it (120 > 10). The declines name
only thread 1, never thread 19 — so **thread 19 is not being made runnable**,
meaning retrace messages are not reaching `0x800A326C`.

Next diagnostic (cheap, do this before any more design): a probe on
`do_send`/`enqueue_external_message_src` filtered to `0x800A326C` and to the VI
source, rate-limited by time, to determine which is true:
1. the VI thread stops enqueueing retrace messages, or
2. they are enqueued but delivered somewhere else / dropped, or
3. they are delivered to `0x800A326C` but thread 19 is not actually blocked on it
   at that point (i.e. it is elsewhere and the earlier read of its state is stale).

Only after that is known should a fix be designed. Sections 5-7 above remain
valid as *option shapes*, but their trigger conditions must be re-derived
against whichever of (1)-(3) is true.

---

## 11. UPDATE 2026-08-17 (late): THE WHOLE DOCUMENT IS OBSOLETE

**There is no drain gap. There is no deadlock. Sections 1-10 describe a bug that
does not exist.** Do not implement Option A, B, or C. Do not use this document
as a starting point; keep it only as a record of how the misdiagnosis happened.

Measured with `SNP_VI_PROBE` (per-queue send/recv/wake counters, reported once
per second by the heartbeat thread). Full data in
`docs/boot-debugging-2026-08-13.md`, 2026-08-17 (late) entry. Summary:

| claim in this document | measured reality at the freeze |
|---|---|
| VI retrace stops reaching `0x800A326C` | 30/sec delivered, 0 dropped |
| thread 19 never wakes | woken 30/sec, receives, re-blocks |
| thread 3 is parked in a wait loop | cycling 30/sec on `0x800A66D0` |
| nothing drains once thread 3 parks | drains continuously |
| the game is deadlocked | audio RSP tasks continue at +30/sec forever |

The game is **running normally at full frame rate and has stopped submitting
display lists**. That is a game-state problem, not a runtime scheduling problem.

### The methodological failure, recorded so it isn't repeated

Every wrong step here shares one shape: **a static observation of a dynamic
system, treated as a steady state.**

- A backtrace showed thread 19 blocked on a queue. It blocks and wakes 30 times
  a second, so *of course* a sample catches it blocked. "Blocked in a backtrace"
  and "stuck" are different claims, and only a rate counter distinguishes them.
- A negative-path probe (declined handoffs) never named thread 19, which was
  read as "thread 19 never becomes runnable". It actually meant the opposite:
  handoffs to it were *accepted*, so it never appeared in the decline list.
- Each new design was built on the previous design's unverified premise rather
  than on a fresh measurement, so one bad reading survived four iterations.

**Rule, now in the playbook:** before designing anything, measure the trigger
condition *and* measure that the failing subsystem is actually failing — with a
rate, over time, not a single sample. A counter that keeps incrementing is proof
of life that no backtrace can give you.
