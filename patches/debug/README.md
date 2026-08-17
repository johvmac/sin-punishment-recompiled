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
| `SNP_WALK=1` | per-thread scene-walk depth, stack low-water mark, child-list length. **Needs the toml hook below.** |
| `SNP_STACKS=1` | every thread's stack top, priority and entry point, logged at `osCreateThread` |
| `SNP_TASK_BT=1` | one resolvable backtrace per distinct sender to a queue (resolve with `scripts/resolve_bt.sh`) |
| `SNP_VI_PROBE=1` | per-queue send/recv/wake/full counters; `=0xADDR` targets another queue |
| `SNP_TRACE=1` | verbose per-event queue tracing. Loud enough to perturb timing — prefer `SNP_CENSUS`. |
| `SNP_SCHED_PROBE=1` | counts scheduler handoffs declined on priority |
| `SNP_STUB_PROBE=1` | first-call report per silently-stubbed function; paired with `scripts/probe_stubs.py` |

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
