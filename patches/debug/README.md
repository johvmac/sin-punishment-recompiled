# Debug patches

Diagnostic instrumentation, kept out of the build by default and stored here as
re-appliable patches. Nothing in this directory is a fix — these probes exist to
answer questions, and every one of them is `getenv()`-gated so an applied patch
still runs at full speed until you ask for it.

Unlike `patches/upstream/`, **`scripts/bootstrap.sh` does not apply these.**
Apply one by hand when you need it, and revert it before committing.

## `N64ModernRuntime-snp-probes.patch`

The `SNP_*` instrumentation for the attract-mode freeze investigation. Applies
on top of `patches/upstream/N64ModernRuntime-vi-null-mode-fix.patch` (i.e. the
state `bootstrap.sh` leaves the submodule in).

```bash
git -C lib/N64ModernRuntime apply patches/debug/N64ModernRuntime-snp-probes.patch
cmake --build build          # runtime-only: no recompile needed
```

Revert with `git -C lib/N64ModernRuntime checkout ultramodern/src/`, then
re-apply the VI null-mode patch (that one is a real fix and must stay).

| switch | what it does |
|---|---|
| `SNP_HEARTBEAT=1` | gfx + non-gfx RSP task counts per second — the trustworthy liveness signal. Also drives the once-per-second reporting for `SNP_WATCH`, `SNP_WALK` and `SNP_VI_PROBE`, so **those need it too**. |
| `SNP_CENSUS=1` | per-second send/recv/block rates for every queue, keyed by thread |
| `SNP_WATCH=0xA[,0xB][,0xA+0xLEN]` | sample game memory once per second; the `BASE+LEN` form watches a word range and reports only what changed |
| `SNP_WALK=1` | per-thread scene-walk depth, stack low-water mark, dispatched node types, recursion levels, and cycle detection (a node that is its own ancestor), with the offending edge captured. **Needs the toml hook below.** |
| `SNP_WALK_FRAMED=1` | **Use this with `SNP_WALK`, or the depth is wrong.** Clears the shadow stack whenever the frame proxy ticks, so `levels` is a strictly WITHIN-FRAME depth. Without it the walker's entry `sp` falls `0x18` per frame, the previous frame's entries can never be popped, and one stale level plus one phantom "cycle" accumulate **per frame** — which reads exactly like runaway recursion. That artifact produced `levels=1345 cycles=8044`; framed, the same run reads `levels=9 cycles=9` (ledger A77/A78). Also reports `root=` / `roots=` / `rootchg=`: the walk's top-level node, how many top-level descents happened, and how often the root changed., plus `fmax=`/`fmin=`/`fdepth=` — the **per-frame** sp extremes and the walk's per-frame footprint. Use those, not `low_sp`/`high_sp`/`depth`, which are cumulative over the whole run and are what made a constant-size walk look like runaway depth. |
| `SNP_STACKS=1` | every thread's stack top, priority and entry point, logged at `osCreateThread` |
| `SNP_STACK_RELOC=<id>[,<id>]` | hands the named threads a 256KB stack in unused high RDRAM instead of the game's. **Hides a defect rather than fixing it** — see below. |
| `SNP_TASK_BT=1` | one resolvable backtrace per distinct sender to a queue (resolve with `scripts/resolve_bt.sh`) |
| `SNP_VI_PROBE=1` | per-queue send/recv/wake/full counters; `=0xADDR` targets another queue |
| `SNP_TRACE=1` | verbose per-event queue tracing. Loud enough to perturb timing — prefer `SNP_CENSUS`. |
| `SNP_SCHED_PROBE=1` | counts scheduler handoffs declined on priority |
| `SNP_STUB_PROBE=1` | first-call report per silently-stubbed function; paired with `scripts/probe_stubs.py` |
| `SNP_OVL=1` | logs every `load_overlays()` call with its ROM range and how many sections matched. **A load into `0x800E4780` with 0 matches means that code overlay is not recompiled at all** — its functions never enter `func_map` and indirect calls into the window resolve to a stale overlay instead of failing loudly |
| `SNP_PHASE=1` | frame-phase tallies (DRIVER/REWIND/APPEND/PASS/CALLBACK) per thread, reported at thread 3's rewinds. Needs the toml hooks in the journal |
| `SNP_SORT=1` | draw-list sort diagnostics: the three bucket (pointer, count) pairs at `obj+0xF8/+0x100/+0x108`, and the pivot's three slots when any is NULL. **Needs the two toml hooks below.** |

### `SNP_WALK` also needs a recompile hook

`recomp_walk_probe()` is called from the game side, so `SNP_WALK` does nothing
until this goes between the scratch-hook markers in `sinpunishment.toml` — and
that costs a `scripts/recompile.sh`, not just a rebuild.

```toml
[[patches.hook]]
func = "boot_func_80033758"
before_vram = 0x80033758
text = "{ extern void recomp_walk_probe(unsigned char*, unsigned int, unsigned int); recomp_walk_probe(rdram, (unsigned int)ctx->r29, (unsigned int)ctx->r4); }"
```

`boot_func_80033758` is the recursive scene-graph walker. Hooked at entry, so
`ctx->r29` is still the *caller's* stack pointer; its minimum over time is the
stack low-water mark.

Put it **inside** the `BEGIN/END SCRATCH DEBUG HOOKS` markers.
`scripts/strip_scratch_hooks.sh` only removes what is between them, and a hook
placed after `END` survives into a commit — which is exactly what happened on
2026-08-17.

### `SNP_SORT` also needs recompile hooks

```toml
[[patches.hook]]
func = "boot_func_8002AA3C"
before_vram = 0x8002AA3C
text = "{ extern void recomp_buckets_probe(unsigned char*, unsigned int); recomp_buckets_probe(rdram, (unsigned int)ctx->r4); }"

[[patches.hook]]
func = "boot_func_8003860C"
before_vram = 0x8003860C
text = "{ extern void recomp_sort_probe(unsigned char*, unsigned int, unsigned int, unsigned int); recomp_sort_probe(rdram, (unsigned int)ctx->r4, (unsigned int)ctx->r5, (unsigned int)ctx->r6); }"
```

`boot_func_8002AA3C` sorts three parallel draw lists; `boot_func_8003860C` is
the median-of-three pivot that dereferences three slots as float keys with no
null check. Reproduce the fault with START at t=20s (`SP_INPUT_SCRIPT`), which
needs no stack relocation and so runs in 25s.

### `SNP_STACK_RELOC` is a diagnostic, not a fix

It answers "is this really a stack overflow?" by moving the stack somewhere the
overflow cannot hurt anything. The walk still descends exactly as far — it just
lands in dead memory. **Do not leave it on to make something work.**

Measured 2026-08-18, `SNP_STACK_RELOC=4`:

| | baseline | thread 4 relocated |
|---|---|---|
| gfx tasks at t=42s | 1240, then +0 forever | 1240, +30 and climbing |
| gfx tasks at t=89s | 1240 (47s stalled) | 2650, still +30/sec |

The arena is `0x80700000` upward, 256KB per relocated thread. That region was
chosen by measurement, not assumption: RDRAM is 8MB here, the highest stack the
game allocates itself was observed at `0x80376160`, and a 55s run watching
`0x80400000` / `0x80600000` / `0x80700000` / `0x807F0000` recorded no changes in
any of them. **Re-run that survey before trusting a result from this switch in a
later game state** — a level load may well reach higher than the attract loop.

### Reading `SNP_WALK`'s cycle output

`levels` is the recursion depth from an explicit shadow stack; `cycles` counts
descents in which a node turned up as its own ancestor. Run it **with**
`SNP_STACK_RELOC=4` — on the game's own 8KB stack the walk is truncated by the
crash it causes, so the depth it actually wants is invisible.

Sanity-check any run against its own free positive control: the attract loop is
healthy until t≈40s and must read `levels=9 cycles=0` there, matching the
independent `depth=640` from the sp low-water mark. A first version of the
detector reported 37 levels and 23 cycles in that window — the probe records the
*caller's* sp, so siblings share a value and a strict `<` pop never retired
them. If the healthy window looks unhealthy, the instrument is broken.

### A retired counter, and why it is called out here

`SNP_WALK` used to report `longest_list` / `bad`, walking a `0xFF`-terminated
byte list at `node+8`. **That structure does not exist in this game.** The
children are a counted array reached through the walker's third argument
(`(a2)+0` -> object, `+0` = entry array, `+4` = count, `0x10`-byte entries,
dispatched via a vtable at `0x80059748` indexed by the type halfword at
entry+0). The counter was reading unrelated memory and reporting healthy-looking
values, and a handoff used those values to rule out malformed child lists.

Kept in this README rather than quietly deleted, because the failure mode is the
point: **a probe that reads the wrong structure does not look broken.** It looks
like evidence. Before trusting a counter that reads game memory, check its
offsets against the generated source in `RecompiledFuncs/` — that read is free.

## Probe discipline

Learned the hard way; the long form is in the diagnostic playbook.

- **A probe heavy enough to change timing measures itself.** `backtrace()` in
  `do_send` killed the game at t=8s with `No threads left to run!` — a failure
  that never occurs without the probe. That is why the census keys on thread id
  (already in hand, free) rather than a backtrace, and why `SNP_TASK_BT` fires
  once per distinct sender.
- **Report from a sampling thread, not the hot path.** The interesting event is
  usually something *stopping*, which by definition cannot print from inside the
  function that stopped being called.
- **Validate an instrument with a positive control before trusting a negative.**
  A probe that never fires and a probe that was never reached look identical.
- **Measure rates, not samples.** A thread that wakes 30x/sec is "blocked" in
  almost every backtrace.

### Hook statics are SHARED BETWEEN THREADS — use `_Thread_local`

A `[[patches.hook]]` body is an ordinary function body, so a `static` inside it
is one variable for the whole process. Several threads call the same game
function (both thread 3 and thread 4 walk the scene graph), so any per-thread
tally, shadow stack or low-water mark silently mixes them.

This has now caused **three** of the seven instrument defects on this project
(I4, I5, I8). It is the single most common probe bug here.

The fix is free — the generated functions are built as C17:

```c
static _Thread_local unsigned depth = 0;   /* per thread, as intended */
```

Two related traps from the same session:

* **Don't key per-thread state on `OSThread->id`.** Two different threads report
  **id 3** on this game (entries `0x80025E44` and `0x80052064`, different
  priorities and stacks). `_Thread_local` keys on the real thread.
* **Byte access to RDRAM needs `^3`**; word access does not. A probe that read
  `rdram[addr]` directly printed every 4-byte group reversed, which read as a
  child index of `0` — the exact bug being hunted. Caught only by cross-checking
  against another probe that had printed the same address.
