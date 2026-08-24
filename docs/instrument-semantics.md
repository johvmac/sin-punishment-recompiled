# Instrument semantics — what a reading actually MEANS

**Read this before designing any gdb condition, probe, or trace.** Added
2026-08-20 (T108).

Every line here is a fact that has already cost this project at least one
entry, and several cost multi-roll dead ends. **The rule for adding a row: it
must name the incident that paid for it.** No speculative entries — a reference
of things that *might* be true is a reference nobody trusts.

The retrospective's finding is that our controls police *measurements* well and
*premises* not at all. This file is where the premises live, so they can be
checked in seconds instead of assumed for fifteen rolls.

---

## The recompiled execution model

| fact | consequence | paid for by |
|---|---|---|
| **`ctx` is ONE `recomp_context` PER THREAD, not per frame.** | `ctx->rN` is a *shared global for that thread*. Every recompiled function on the call path writes it. "Function F writes `$s0` in exactly two places" says **nothing** about what `$s0` contains at a moment. | **A183** — the count was taken inside one function; **9,199** `ctx->r16` write sites exist across 133 files. Cost ~15 rolls (A157→A183). |
| **A callee that saves a register at entry and restores it at exit protects its caller regardless of what IT calls.** | Only a **non-restoring** callee can leak. That cuts 9,199 sites to **194**. | A184 |
| **`ctx->rN` is SIGN-EXTENDED.** A KSEG0 address arrives as `0xFFFFFFFF8xxxxxxx`. | Mask with `& 0xFFFFFFFF` in **every** condition and printf. An unmasked compare is always false and looks exactly like "the case never happened". | I17 |
| **`$sp` (`ctx->r29`) is emulated state, not the host stack.** | A frame's `$sp` is constant between its prologue decrement and its epilogue restore — but it is *not* a reliable frame identifier across sites (see below). | A157, A173 |
| **RDRAM in a snapshot is stored HOST-endian.** | A naive big-endian read is byte-reversed. Use `rdram_peek.py`, or swap. | I7; caught again live in **A179** — a raw read gave `00580540` where the tool gave `40055800`. |

## Reading values at a breakpoint

| fact | consequence | paid for by |
|---|---|---|
| **A gdb line breakpoint fires BEFORE that line executes.** | At `funcs_4.c:228` (`ctx->r16 = ADD32(ctx->r6, 0)`), `ctx->r16` still holds the **caller's** value — which is how the parent→child handover was read directly. To see a value *after* an assignment, break on the **next** line. | A172 (used deliberately), A180 |
| **A value read at site X is not automatically attributable to "the frame at site X".** | `ctx->r29` at `:661` matched no invocation's entry `$sp` at all. Pair invocations by something **unambiguously per-invocation** (an argument value), never by `$sp`. | **A173**, which corrected A166/A168/A172 |
| **`$_thread` is available in conditions and printfs.** | Thread-blind traces are fine only if you have *checked* they are single-threaded. Log it when two threads run the same code. | A178 (walker heap activity confirmed single-threaded, thread `0x3F`) |
| **Line-table attribution is worth checking before blaming it.** | `info line <file:line>` gives real address ranges; if they are contiguous and monotonic, the breakpoint is where the source says. Rule this out cheaply instead of suspecting it late. | A177 |
| **A conditional breakpoint's REACH COUNTER is what makes a zero meaningful.** | 0 hits with 0 reaches = the instrument never armed. 0 hits with a healthy reach count = a real negative. Always read `info breakpoints`. | T56, and every trace since |
| **A deadline that SIGKILLs the process destroys the final `info breakpoints`.** | If the run is killed rather than faulting, the reach counters are **absent** — so a NEGATIVE from that run is worthless. Positive hits still count. | A167 |

## Runs and evidence

| fact | consequence | paid for by |
|---|---|---|
| **A snapshot cannot distinguish a live frame from a leftover.** | Memory above the outermost live frame holds whatever an earlier deeper call left. Establish call chains by logging **entry arguments** — one record = one real invocation. | T69; four incompatible readings (A125/A128/A130/A132) |
| **A negative from a run that did not reproduce the event is not a negative about it.** | Confirm the SIGSEGV is in the log before believing any absence. | T72 |
| **Reach counts scale with the ARM WINDOW, not with the program.** | `:228` gave 15 reaches at arm=150 s and 25,422 at arm=120 s — same binary, same condition. **Never compare counts across arm windows.** | **A166/A173** — this is exactly how A141 was wrongly dismissed. |
| **A trace condition is scoped to the SITE it was designed for.** | Borrowing a neighbour's range gave 77,058 confident hits that meant nothing. Derive the expected range from the site's **own** targets. | A163 |
| **A condition firing on 100% of reaches is a wrong condition, not a finding.** | Check the shape of the values before believing the count. | A163 |
| **Presence may come from a sample; ABSENCE needs a continuous channel.** | `SNP_WATCH` is a 1 Hz sampler and cannot support "never happened". Two sampled stills cannot bound what happened between them. | T83; A93 and A161, both user-caught |
| **`gdb_fault.sh` and `gdb_trace.sh` must run against `build-debug`.** | Against the release build `ctx` does not resolve, every condition silently errors, and you get an identification with **no registers** while a signature control still prints `ok`. | T85, A122 |
| **An audio capture that starts after the game does can miss the only event.** | Capture is now routed pre-launch via `PULSE_SINK`. A 6-second gap once produced a confident silent artefact against a real, heard blip. | A170/T104 |

## Static reading

| fact | consequence | paid for by |
|---|---|---|
| **ROM offset ≠ IMEM offset for a self-loading ucode.** | The audio stub DMAs its body from RDRAM to IMEM `0x080`, but that body lives at ROM `+0xD0`. Assuming the offsets match produced a plausible-looking wrong entry point. | A158 (the wrong assumption), A179 (the measurement) |
| **A DMA target that equals a jump target means the ROM bytes there NEVER execute.** | Disassembling them tells you nothing about runtime behaviour. | A174 |
| **Node types are REBASED at load time (+0x1B here).** | Every static reading of them was of unrelocated data until this was found. | A126 |
| **A grep-based sweep is only as good as its list.** | A sweep excludes what it enumerated, nothing more. When the list cannot be trusted, use an instrument that needs no list (a watchpoint). | A152 → A180/A184 |

---

## How to use this

Before writing a condition, ask the three questions this file exists to answer:

1. **What does this value belong to?** (thread? frame? invocation?)
2. **When is it read relative to the code that sets it?**
3. **What would make a ZERO here meaningless?** (reach counter, arm window,
   run that did not reproduce, sampled channel)

If a contradiction appears later, come back here **first** — the impossible-result
rule says the premises get audited before another experiment runs, and this is
the premise list.

**For the display-list census specifically, `display-list-primer.md` is the
ground-up version** — written for the user under U11, so it assumes no prior
knowledge. It carries the one semantic trap in that instrument that is easiest
to fall into: **on a `[dlrect]` line, `color=` is meaningless unless `cycle=`
says `FILL`** (A356, and A342 doubted a correct finding on exactly this). It
also states, claim by claim, which parts of a census reading are measured and
which are convention I am quoting.
