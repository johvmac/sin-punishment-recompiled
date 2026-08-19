# VI thread dereferences a null `ViState::mode` when a game is started before the first `update_vi()`

## Symptom

SIGSEGV in the VI thread within ~3s of launch, before the game produces any
output:

```
Thread 54 "VI Thread" received signal SIGSEGV, Segmentation fault.
0x0000555555c42f7b in vi_thread_func() ()
```

It shows up when the game is started immediately at launch — i.e. a path that
calls `recomp::start_game()` without waiting on the UI. Starting through the
menu normally gives the VI thread enough iterations to get past it, so it is
easy to miss.

## Root cause

`ViState::mode` (`ultramodern/src/events.cpp`) has no default initializer,
while its sibling does:

```cpp
struct ViState {
    const OSViMode* mode;          // no initializer
    ...
    int retrace_count = 1;         // has one
};
```

`events_context` has static storage duration, so `mode` is a deterministic
`nullptr` at startup rather than indeterminate garbage.

Before the game calls `osViSetMode()`, the only thing that populates `mode` is
`set_dummy_vi()` in `vi_thread_func()` — and that is inside the not-started
branch, while `update_vi()` a few lines later dereferences unconditionally:

```cpp
if (!ultramodern::is_game_started()) {
    set_dummy_vi(odd);             // the only pre-osViSetMode writer of mode
    ...
}
...
events_context.vi.update_vi();     // dereferences mode unconditionally
```

`is_game_started()` is `game_status.load() != GameStatus::None`, and
`recomp::start_game()` stores `GameStatus::Running` directly. Nothing on that
path waits for the recompiled game code to reach `osViSetMode()`. So the flag
can already be true on the VI thread's **first** iteration — `set_dummy_vi()`
never runs, and `update_vi()` dereferences null.

It is specifically a first-iteration race. `update_vi()` ends with

```cpp
cur_state ^= 1;
*get_next_state() = *get_cur_state();
```

so one pre-start `set_dummy_vi()` propagates a non-null `mode` into both slots
permanently. The window is only ever that first iteration, which is why it
looks intermittent and why an autostart path makes it near-deterministic.

## Evidence

From the unfixed build:

```
si_addr = 0x1c
=> 0x555555c42f7b <vi_thread_func+779>:  mov  0x1c(%r15),%edx     # %r15 = 0
```

`0x1c` is `OSViMode::comRegs.hStart` (3 bytes padding + `type`, then `ctrl` at
offset 4). Note the two preceding `&`-expressions, `&next_mode->comRegs` and
`&next_mode->fldRegs[field]`, are only address arithmetic and do not fault; the
first real load through `next_mode` is what dies.

Measured on a recompilation of *Sin and Punishment*, 3 isolated runs per arm,
with the two binaries built from the same tree and differing only in whether
this path is guarded (build is bit-reproducible, so each arm was confirmed by
SHA-256):

| arm | runs | time to SIGSEGV | faulting thread | game output first |
|---|---|---|---|---|
| unguarded | 3 | 2s, 2s, 3s | `vi_thread_func()` | none — log ends at font/asset init |
| guarded | 3 | never faults | — | 30 display lists/s, sustained 156s+ |

A fourth unguarded run with all optional debug instrumentation disabled also
died at 3s, so this is not an artifact of local probes.

Worth flagging for anyone reproducing: our guarded build eventually hits a
separate, pre-existing crash in the recompiled game's own code at ~158s. So the
discriminator is **time and faulting thread**, not crash/no-crash — a plain
"does it still crash?" comparison would wrongly conclude nothing changed.

## Environment

- `N64ModernRuntime` at `589bbf0`
- Linux, x86-64, Release build

## Note on how this was found

This investigation was AI-assisted, which I'm flagging up front given
`CONTRIBUTING.md`. I'm therefore filing it as a bug report only, with no patch
attached — the analysis and fix decision are yours. The run data above was
gathered on real builds on my machine rather than asserted.
