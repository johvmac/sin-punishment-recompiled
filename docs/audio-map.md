# The audio engine, mapped by name — 2026-08-25 (A446)

**Written the evening A444 named 138 functions**, because every fact below was
unaskable while the library was `boot_func_XXXXXXXX`. Sources: JAL/data/
materialisation censuses over the whole ROM, the A99 RDRAM snapshot for
runtime-installed pointers, two `gdb_trace` runs with a positive control, and
the Yamanaka interview (A445) as the lead that started it.

**Confidence key**: MEASURED = a census or trace in the evidence chain.
READ = disassembly interpreted. INFERRED = named by position/analogy only.

## The architecture in one paragraph

Treasure did **not** use libultra's audio client layer. The sequenced-music
players (`alSeqp*`, `alSndp*`) are absent from the ROM; the stock top layer
that IS linked (`alInit`, `alClose`, `alSynNew`, `alAudioFrame`,
`osCreateScheduler`) is **dead code** — zero JAL callers, zero data references,
zero materialised addresses, dragged in by `.o` granularity (MEASURED, three
scans). In its place sits a **house engine in `.boot` 0x8004D9xx–0x800564xx**
that drives the synthesizer's internals directly: it allocates from the audio
heap (`alHeapDBAlloc` — 46 call sites, half from Treasure code), links its own
players/filters with `alLink`, installs **its own pull handlers**, and submits
RSP tasks through its own launchers, bypassing the stock scheduler entirely.
This is consistent with the composer's account (A445): a Treasure programmer
built a custom streaming layer; the interview's "streamed PCM" is that layer.
**The same engine is in Bangai-O byte-for-byte** — most of these functions are
on A443's 185-shared list.

## The cast, bottom-up

### The audio thread and its pump — MEASURED

| what | where | evidence |
|---|---|---|
| audio init | `boot_func_80051EF0` | sole caller of `osAiSetFrequency`; creates the audio thread (site 0x80052030) |
| **audio thread entry / AI pump** | `boot_func_80052064` (94w) | its address is materialised only inside 80051EF0, as the `osCreateThread` entry |
| audio heap init | `boot_func_80052A04` → `alHeapInit` | |
| master audio init | `boot_func_80053710` | calls 80051EF0 + 80052A04 |
| init chain above it | `boot_gameEntry` → `boot_func_80025E44` → `boot_func_8003A9CC` → `boot_func_8004EC90` → 80053710 | JAL census |

The pump's body (READ, disassembly at 0x80052064): stores **`0x80056F50` — the
audio ucode address A167/A174 established** — into a task template on its
stack; loops calling two functions through a **runtime vtable `*(0x800622C0)`**;
then spins on `osAiGetStatus`/`osAiGetLength` until the AI has room.

### The runtime vtable — MEASURED (A99 RDRAM snapshot)

`*(0x800622C0) = 0x80062000`, whose slots are:

| slot | function | what it does (READ) |
|---|---|---|
| +0 | `boot_func_8004ED68` | creates two message queues, calls 8004E290 — one-time init |
|  | *(pump-entry breakpoint scored 0 hits — an entry line fires once, before the 5 s arm; uninformative about the loop, and noted so the zero is not read as "thread dead")* | |
| +4 | `boot_func_8004EDD4` | `osRecvMesg` then **`jalr`** — wait-and-dispatch |
| +8 | `boot_func_8004EE70` | `osSendMesg`/`osRecvMesg` pair — post-and-wait |

So each pump iteration is *dispatch pending audio work, then feed the DAC*.
The actual frame-builder sits behind the `jalr` in slot +4 (not yet named).

### The RSP task launchers — MEASURED

`boot_func_8004E4A0` and `boot_func_8004E640` are the only non-dead callers of
`osSpTaskLoad` + `osSpTaskStartGo`. Their addresses are materialised only
inside `boot_func_8004DE74`, which creates **three threads** (sites 0x8004E08C,
0x8004E0D4, 0x8004E11C) and is called from `boot_func_80025CA4` — the second
thread started by `boot_gameEntry`. The stock scheduler's `__scExec` also
calls the pair but is unreachable (`osCreateScheduler` dead).

### The custom pull chain — MEASURED, and this is the load-bearing part

Treasure's client-init functions (`boot_func_80051990`, `boot_func_80056078`)
install **their own handlers**: `boot_func_80050950` (196w) and
`boot_func_8004F030`. `boot_func_80056434` installs `0x80041DF8` — an
unmatched function inside stock `fx.o`, positionally the fx param handler
(INFERRED, not in the view). The stock loader path is never used:

* **`alLoadParam`'s two install branches — `alAdpcmPull` at 0x80040594,
  `alRaw16Pull` at 0x80040648 — fired ZERO times in 150 s** through boot and
  attract (`pull-install-trace.log`), with the instrument positive-controlled
  the same evening at **1,647 hits/60 s** on a known-hot site
  (`pull-install-positive-control.log`). This retires A445's runtime question:
  the answer is *neither*, because the stock loader is dead code too.
* **`boot_func_80050950` — the custom handler — fired 21,755 times in the
  same window (~145/s)** with live buffer pointers in its arguments
  (`custom-audio-chain-trace.log`). **The producer runs, constantly.**

### What is still stock and alive — MEASURED

The synthesizer's *internals* under the custom top: `alHeapDBAlloc`, `alLink`/
`alUnlink`, `alFxNew` and the whole fx/envmixer/resampler chain
(`_pullSubFrame`, `alEnvmixerPull`, `_loadOutputBuffer`, …), called intra-
library exactly as libgultra 2.0K wires them. The Ai osAi* group is alive via
the pump. Everything above `alSynNew` in the stock stack is dead.

## What this does to A97

A97's measured state: audio RSP tasks flow at +30/s, the device opens, buffers
cycle at volume, **every output sample is zero**. Its lead suspect since A104:
the SIG0 hack drives the audio ucode down its ABORT path on every task.

**A445 added a rival — a starved producer — and today's traces retire it.**
The custom chain executes at full rate with real buffers; frame-building work
happens continuously. A producer that never ran, or a stream that was never
set up, would not call its pull handler 145 times a second. What today does
NOT establish is the *content* of those buffers — "the handler runs" is not
"the handler's input data is non-zero" — but the structural half of the
starved-producer story is gone.

**The fault therefore sits between the built command list and the samples: the
RSP execution of ucode 0x80056F50 — which is exactly where A104 measured the
abort.** The producer is exonerated; A104's suspect stands alone again, now
with the other branch measured away rather than assumed away.

## Open ends, priced

* Name the frame-builder behind slot +4's `jalr` (one trace with `ctx->r2`
  logged at the jalr, or one RDRAM peek at the queue's message targets).
* Read `boot_func_80050950` against `alAdpcmPull`/`alRaw16Pull` to say whether
  Treasure's decoder is an ADPCM variant or raw streaming — this is the
  remaining half of the interview's PCM claim.
* The `0x80041DF8` = fx-param-handler guess needs one disassembly comparison
  before it may enter the view.
