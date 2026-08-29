# Diagnostic playbook — Sin & Punishment recomp

> [!IMPORTANT]
> **READ `docs/findings-ledger.md` FIRST — in full, before any investigation.**
> It is ~178 entries and it is the **visited set**: every established fact,
> ruled-out hypothesis, *withdrawn* belief and dead tool, one line each.
>
> *If that count has grown much past 178, or entries have stopped being one
> line each, read **T55** before anything else. The ledger is the INDEX layer
> of this playbook. When it stops being scannable the fix is to move detail
> back down here and leave one line — not to build a second index.*
>
> This file and the journal are 1,700 and 5,000+ lines. Searching them to ask
> "do we already know X?" costs more than re-deriving X, so without the ledger
> the cheap move becomes re-deriving — and the same ground gets covered twice.
> That has happened: the ares comparison and the stub sweep were both re-run
> needlessly. **Skipping the ledger does not save time, it spends it twice.**


**Living document.** This is the decision tree for diagnosing anything wrong
with this build. It is meant to be *followed in order* and *edited as we go*.
See "Update protocol" at the bottom for how it stays current — that part is
not optional, it's the reason this file is worth having.

Companion documents:
- `docs/boot-debugging-2026-08-13.md` — the running session log (what we found,
  pass by pass). **Findings go there. Method goes here.**
- `~/.claude/projects/.../memory/sin_punishment_recomp_status.md` — cross-session
  memory: environment, tool locations, current status.

Both this file and the session log are gitignored (`.gitignore`: `*.md` with
`!README.md` — "development Markdown stays local"). Keep it that way unless we
decide to publish it deliberately.

---

## WHAT IS INSTALLED ON THIS MACHINE — check here before asking or assuming

**WHY THIS SECTION EXISTS (user-reported, 2026-08-22):** more than one session
has burned time working out whether the reference recompilations were even
present. Everything below WAS already mentioned somewhere in this file — the
problem was that finding it required already knowing it existed. **This is the
one place. All paths verified 2026-08-22.**

### Reference recompilations — BOTH ARE CHECKED OUT LOCALLY

| what | where | state |
|---|---|---|
| **Zelda64Recomp** (Majora's Mask) | `/home/joh/Documents/reference-recomps/Zelda64Recomp` | 1.9 GB, git `1a9c266` |
| **BanjoRecomp** (Banjo-Kazooie) | `/home/joh/Documents/reference-recomps/BanjoRecomp` | 1.5 GB, git `ec85963`, includes `BanjoRecompSyms` and a decompressed ROM |

These are **working recompilations of other N64 games built on the same stack**,
so they answer "is this our bug or the framework's?" without any theorising —
G5 is the gate for that. `Zelda64Recomp` also ships
`config_example.cheats.json`, which is directly relevant to the memory-poke work
(T145).

**NOT checked out:** `trouble-makers-pc-recomp` (Mischief Makers). T143 surveyed
it **through its README over the web**, not its source — every claim in T143
about their implementation is theirs-as-described. Its ROM *is* on disk.

> **DO NOT CLONE IT HOPING FOR A CUSTOM-MICROCODE COMPARATOR (T176).** Its RSP
> config says outright: *"The game ships the standard Nintendo `aspMain` audio
> RSP ucode"* — `output_function_name = "aspMain"`, `text_offset = 0xBCAB0`,
> `text_size = 0xE20`, `text_address = 0x04001080`. **It is STOCK, like Majora's
> Mask and Banjo-Kazooie. Sin & Punishment is the only one of the four with a
> custom audio microcode, and that holds even against its own developer's
> earlier game.** Two web fetches established this; 1.5 GB would have bought
> nothing.
>
> **Two things it DID give us free:** its range `0x1080..0x1EA0` contains our DP
> sites and its build ships, so stock `aspMain` there writes no DP registers —
> a second stock arm where Banjo's range could not reach. And it states
> `text_address` must be `0x04001080` **not** `0x04001000`, which is exactly
> A179's correction for our own config, asserted by a project that has never
> heard of us.

**AND READ PAST THE TABLE.** T176 is the entry for scoping comparators by what
was checked out rather than by what could discriminate — I read the two-row
table above and stopped, one line short of the game by the same developer.

### Emulators — THERE ARE NOW TWO, AND THEY DO DIFFERENT JOBS

**1. `ares` is a FLATPAK.** `command -v ares` returns NOTHING and the app is
installed. Run it as `flatpak run dev.ares.ares`, which is what
`scripts/ares_capture.sh` does. Do not conclude from a bare `command -v` that
the reference emulator is missing. **This is the REFERENCE VIDEO source** —
A222/A229/A267/A372/A384 all rest on its captures.

> **Its gdb DebugServer DOES NOT WORK for us and the cheap fixes are spent
> (A403/A405).** It serves FROZEN memory with `$pc=0xffffffff` while the game
> visibly runs at 60 VPS. Not a missing setting, not `HomebrewMode`, not
> headlessness, not `gdb-multiarch`. `Boot/Debugger=true` halts it at boot and
> blocks `continue`. **The interrupt-based rewrite is DROPPED — use ares-64.**

**2. `ares-64` is BUILT FROM SOURCE at
`~/Documents/sin_and_punishment/tools/ares-64` (A407/A408, 2026-08-25).**
HailToDodongo's debugging fork. Binary: `build/desktop-ui/ares`. Rebuild with
`ninja -C build desktop-ui` **(`cmake --build build` is refused by
`guard_bash.py`, which matches the string with no directory scoping — a false
positive on third-party trees, not a real protection here).**

**What it gives us that nothing else does — the RDP COMMAND LOG:**

```sh
./build/desktop-ui/ares --dump-log rdp:120:1 --system "Nintendo 64" <rom>
```

`spec = <rsp|rdp|rsp+rdp>:<after-frames>[:<frame-count>]`. **Frame-indexed**,
decoded to named commands with parameters AND raw hex, then quits. Measured on
our ROM: frame 120 gave 192 RDP commands, F3DEX2 detected and dispatch hooked.

* **`0 RSP` commands is EXPECTED, not a fault** — RSPQ/F3DEX2 capture needs a
  libdragon ELF and ours is a commercial ROM. That half stays closed this way.

**THE THREE THINGS THAT WILL BITE YOU. All three cost a mistake already.**

**1. `<after-frames>` COUNTS PRESENTED FRAMES, NOT VI TICKS — so ~30/s, NOT 60
(A410).** The capture commits on a framebuffer swap, "not on every VI"
(`desktop-ui/program/program.cpp` ~line 132). **`frame N ≈ N/30 seconds.`**
A409 assumed 60 and aimed a control at 8–16 s believing it was 4–8 s.

**2. COORDINATES ARE 10.2 FIXED POINT — DIVIDE BY 4 (A408).** The tool prints
the raw value as a float. `lr=(1232.0, 924.0)` is really `(308, 231)`; the
scissor `ul=(48,32) lr=(1232,924)` is a 296×223 area in a 320×240 frame — i.e.
ordinary hardware. Nothing is upscaled and nothing is wrong.

**3. THE COMMAND NAMES CONTAIN SPACES. ENUMERATE THEM BEFORE COUNTING (A409).**
Grepping `Texture|LoadBlock|SetTile` returned **zero on every frame** and read
exactly like "the real game submits no textures". The real vocabulary:

> `Sync Pipe` · `Set Tile` · `Tex Image` · `Sync Load` · `Tile Size` ·
> `Load Block` · `Tex-Rect` · `Sync Tile` · `Load Tex LUT` · `Other Modes` ·
> `Color Combiner` · `Triangle (Shade Tex Z)` · `Triangle (Tex Z)` ·
> `Triangle (Shade Z)` · `Prim Color` · `Scissor` · `Fill-Rect` · `Env Color` ·
> `Color Image` · `Fill Color` · `Sync Full` · `Fog Color` · `Depth Image`

Get the list from the data, never from memory:
`awk -F'\t' 'NR>1 && NF>=5 {print $5}' dump.txt | sort | uniq -c | sort -rn`

**HOW IT WAS VALIDATED — three controls, all passed (A409/A410).** Do not
re-derive these; do re-run control 3 if the ares-64 build is ever updated.

| control | result |
|---|---|
| **Renderer invariance** — same frame under `parallel` and `angrylion` | **byte-identical**, md5 `3bb990a1fcb770c2`, `diff` empty. **This is what licenses comparing the stream against our RT64 census: the commands are the GAME's, not the renderer's.** |
| **Frame-index discrimination** | 72 / 871 / 1563 / 2133 commands at frames 60/240/360/480 — `--after-frames` really selects |
| **Known positive** (A224's logo window, measured from VIDEO) | frames 120 & 150 (4.0 s, 5.0 s): 18 `Tex-Rect`, 20 `Tex Image`, **0 triangles** — flat blits, no geometry. Frame 60 near-blank; frames 200/250 carry ~130 triangles as the 3D attract starts |

Select the renderer with `--setting Video/Renderer=angrylion` (or `parallel`,
`none`); the banner line confirms which was used, so check it rather than
assuming the flag took.

* Headless JS runner (`README_JS.md`, `cmake --preset linux-headless`, target
  `ares-test`) needs no window, GPU or audio, uses EMULATED time so runs are
  reproducible, and exposes `setRenderer("angrylion")`. **Not yet built.**
* **No wrapper script yet, deliberately** — every invocation so far has been
  hand-typed, and the first real query (A396's scene boundary) is what should
  decide the script's shape. A wrapper written before that is a guess, and it
  would owe T71's gates itself.

### ELAN annotation — the loop is closed in both directions now

* **`scripts/eaf_read.py`** reads the user's annotations back as data. It
  REFUSES a file with no annotations rather than reporting an empty read as an
  empty file — so a `rc=2` on a freshly built file is correct, not a fault.
* **`scripts/eaf_make.py`** (added 2026-08-25, A413/U16) writes the file they
  annotate INTO. `--dry-run` prints tiers and media and exits; `--self-check`
  is **11/11** with three arms **verified to discriminate** (was 6/6 — see
  T205, and note the suite was passing at 9/9 while the tool mis-paired media).

  ```sh
  scripts/eaf_make.py CLIP.mp4 -o OUT.eaf --tier a --tier b --question "..."
  ```

  **IT LINKS BOTH MEDIA, AND IT REFUSES IF IT CANNOT (T205).** Our `.mp4` has
  **no audio track** — the sound finalises to a `.flac` beside it (T160) — so a
  project linking only the video is a **silent film**, which is precisely what
  T150 predicted would leave A97 where it is. The `.flac` is found by **nearest
  timestamp within 120 s**, never by sort order: the first version paired the
  11:40 video with the 08:50 sound, and **a cross-run pair is worse than no
  audio — it plays, the timestamps look plausible, and every annotation made
  against it is silently wrong.** No sound beside the video ⇒ `rc=2`; pass
  `--audio <file>`, or `--no-audio` to say you meant it.

  **IT PRE-FILLS NOTHING, AND THAT IS THE POINT, NOT AN OMISSION.** Tiers arrive
  empty and named after the question. A383 found the user's labels disagreed
  with unanimous machine consensus on 3 of 5 entries — an annotation file
  carrying my marker saying "the interesting moment is here" spends exactly the
  independent reading it was built to collect. Same rule as the status page's
  "NO answer key reaches the page" control.
* Media is linked **absolutely and relatively**, because the archive drive's
  mount point has changed before.
* The question is written INTO the file as a PROPERTY — A266's `.eaf` outlived
  the conversation that produced it by days.

### Decompilation and analysis tooling — `/home/joh/Documents/sin_and_punishment/tools/`

* **Ghidra 12.1.2** (`ghidra_12.1.2_PUBLIC`), with `ghidra-projects/` and
  `ghidra-in/` alongside it.
* **m2c** plus its virtualenv (`m2c`, `m2c-venv`) — the decompiler behind
  `scripts/decomp.sh`, which is the free "read the real C" step in G2.

### Sibling repositories

* **`splat-project/`** — 228 MB, git `d6bcdde`. The splat configuration, the
  base ROM, `symbol_addrs.txt` and the disassembly. **It is NOT in this repo**
  (T19) and edits to the splat config belong there.

### Command-line tools present

`rclone` `ffmpeg` `ffprobe` `gdb` `rr` `ninja` `cmake` `nm` `objdump` `python3`

**ABSENT:** `vulkaninfo` — so GPU identity comes from RT64's own startup lines
in the run log, not from that tool (T144).

### Sub-agents — a reading amplifier, with measured limits (T157)

**`docs/agent-brief.md` is the single source. Part 1 decides whether to spawn
one; Part 2 is pasted into the prompt verbatim.** Do not restate its rules here
— a second copy is a copy that goes stale (the whole reason `CLAUDE.md` says so).

**T71's three gates are cleared and the trial is T157**, not an argument:

* **Dry run / gate first.** `guard_bash.py` **does** fire for sub-agent tool
  calls — verified with one agent attempting a bare `echo` of the binary path,
  refused with identical text. A cold agent cannot launch the game. **Nothing
  else was allowed to run until that passed.**
* **A control that failed.** Two models on ONE prompt returned **opposite
  verdicts on the same line** — Sonnet 5 `UNGUARDED` with a correct
  cross-object trace, Haiku 4.5 `GUARDED`, signing off "no unguarded container
  accesses found in scope" on the exact path that had SIGSEGVed the game twice
  that morning. **The repeatability control failed and that is the result, not
  a disappointment**: a single agent run is a SAMPLE, not a survey.
* **The incident that motivated it.** The user proposed it 2026-08-22; it was
  designed as T153 before anything ran, precisely so the criteria could not be
  invented after seeing the output.

**The economics, measured once:** 9 records returned, **6 targeted reads to
verify, against 41,030 lines not read.** Strongly favourable — but only for the
capable model, and only because the output was `file:line` rather than prose.
**A narrative costs the same to check as to derive, which cancels the benefit.**

**What it bought that is NOT token economy:** the agent had not read A310, so it
had none of my priors and **found an error in it that I would very likely have
re-confirmed**, having already written it down. That failure — reading past
one's own recorded conclusion — has a history here (T135, A305). **An
independent reader is worth most exactly where I already believe something.**

### Other applications

* **ELAN 7.1** — `/home/joh/opt/ELAN_7.1/bin/ELAN_7.1`. Annotate recordings with
  time-aligned notes; needs VLC installed, which it is. This is how user
  observations come back with exact start/end times.
* **Google Drive backup** — `rclone` remote named **`google`** (NOT `gdrive`).
  `scripts/backup_drive.sh` auto-detects a sole remote. Runs from cron at 18:45.

---

## The map

```mermaid
flowchart TD
    S["Symptom observed"] --> G0["G0: State it falsifiably<br/>exact numbers, N-of-M repro"]
    G0 --> G1{"G1: Which layer?"}
    G1 -->|"A: recompiler output"| G2
    G1 -->|"B: runtime layer"| G2
    G1 -->|"C: game logic"| G2
    G1 -->|"D: host/env"| G2
    G2{"G2: Known bug class?<br/>(catalogue below)"} -->|yes| FIX["Apply known fix pattern<br/>→ verify → record instance"]
    G2 -->|no| DEC["scripts/decomp.sh &lt;func&gt;<br/>free: read the real C"]
    DEC --> G3{"G3: Automated tooling<br/>can answer it?"}
    G3 -->|yes| EV
    G3 -->|no| G4{"G4: Docs / existing<br/>resources answer it?"}
    G4 -->|yes| EV
    G4 -->|no| G5{"G5: Class B?<br/>→ compare MM / BK"}
    G5 -->|yes| EV
    G5 -->|no| G6{"G6: Class A or C?<br/>→ compare ares"}
    G6 -->|yes| EV
    G6 -->|"no / G6 UNUSABLE 2026-08-18"| G7["G7: Live gdb<br/>(most expensive, last)"]
    G7 --> EV
    EV{"EV: Evidence gate<br/>do I actually know this?"} -->|"solid"| FIX
    EV -->|"inferred / ambiguous"| ASK["Get a cleaner test,<br/>or ask the user"]
    ASK --> G3
    FIX --> UP["Update protocol:<br/>local finding → session log<br/>generalisable → this file"]
```

**Free nodes come before every gate.** `scripts/decomp.sh <func>` (real C for
any ROM function) and reading a capture cost nothing and no run — expand them
before anything that starts a process. A free node left unexpanded while
90-second experiments run is the most common way this ordering gets violated in
practice; it happened on 2026-08-18 and the free read, once taken, immediately
overturned the working theory. **G6 is currently unusable** — see its section.

Ordering principle: **cheapest and least human-attention-consuming first.**
G2 (known bug class) is at the front because empirically it has the highest hit
rate in this project by a wide margin — six of the bugs fixed so far were the
same class, and the sixth took a full live-gdb session that a catalogue lookup
would have short-circuited.

Note this reorders the intuitive list slightly: "is the screenshot definitely
what I want to see?" is **not** a step, it's the evidence gate (EV) that applies
to *every* observation at *every* stage. It was the failure mode twice in one
session, both times at the point of interpreting a result, not at the point of
choosing a tool.

---

## G0 — State the symptom falsifiably

Before touching a tool, write down:

- **Exact observable** — the literal error string, the exit code, the task
  count, the `boot_screen_check.sh` verdict numbers. Not "it's broken".
- **Reproducibility** — N of M runs, and whether the failure point is
  *identical* each time (e.g. "stalls at exactly 123 gfx tasks, 3/3 runs").
  A stable number is itself a strong diagnostic signal; a varying one means
  a race and routes to class B.
- **Last known good** — which commit / which build / before which change.
- **What would falsify my current guess.** Write this before running anything.

If you can't fill these in, you don't have a bug report, you have an
impression. Go get the numbers first — usually `scripts/boot_screen_check.sh`
or a task-count print is enough.

> **From our history:** "the screen changed after I pressed Start" was reported
> as progress. It wasn't — it was the attract-mode demo continuing on its own
> schedule. There was no baseline for "what does the screen do if I press
> *nothing* for the same duration," so the observation had no discriminating
> power. **A change you can't compare against a do-nothing control is not
> evidence.**

---

## G1 — Routing: which layer is this?

The single most decisive question, because it determines which of the two
cross-comparisons downstream is *valid* — using the wrong one wastes a lot of
time and can produce confidently wrong answers.

| Class | What it is | Signature | Useful gates |
|---|---|---|---|
| **A** | **Recompiler output** — N64Recomp mis-translated the MIPS | Build-time errors; `Unhandled branch in static_NN_ADDR`; dangling gotos; a function that's a no-op when the ROM's disassembly says otherwise; control flow that doesn't match the ROM | G2, G4, **G6 (ares)**, G7 |
| **B** | **Runtime layer** — `ultramodern`/`librecomp`/RT64 differs from real hardware | Races; timing-dependent; "worked in ares"; uninitialized-looking reads; scheduler/deadlock; input/VI/DMA behaviour | G2, G4, **G5 (MM/BK)**, G7 |
| **C** | **Game logic / progression** — the N64 code runs correctly but doesn't do what we expect | No crash, no error, just doesn't advance; a branch not taken; a state machine parked | G4, **G6 (ares)**, G7 |
| **D** | **Host / environment** | Fails before the ROM matters; machine-specific; Vulkan/SDL/X11/permissions/packaging | G3, G4 |

**The routing rule that matters most:**
- Reference recomps (MM/BK) share our *exact runtime source*. They are ground
  truth for **class B** and worthless for class C.
- ares shares the *real hardware behaviour of the game*. It is ground truth for
  **class A and C** and worthless for class B (it doesn't run our runtime at
  all).

Getting this backwards is how you end up "proving" something with a comparison
that structurally cannot speak to the question.

If you genuinely can't route it yet, that's fine — say so explicitly, and use
G3 to gather enough to route it. Don't guess a class and then pick a comparison
that confirms it.

---

## G2 — Is this a known bug class?

Check here **first**, every time. Cheap, and historically the highest-yield gate
in this project.

### BC-1 — Populated metadata, unpopulated pointer *(6 instances — our signature bug)*

**Class:** B (runtime layer).

**Mechanism:** `ultramodern` performs PI DMA **synchronously**; real N64
hardware is **asynchronous**. Real game code is written assuming a window in
which a struct's count/metadata field is set but its pointer field isn't yet
(or vice versa) — hardware's interrupt-driven timing closes that window before
anything reads it. Ours doesn't, so a read lands on an uninitialized slot.

**Signature:**
- `SIGSEGV` on a dereference, or `Failed to find function at 0x<garbage>`.
- The bad value is *not* a slightly-corrupted pointer — it's arbitrary
  (`0x3DC7CA55`), i.e. uninitialized stack/heap, not arithmetic gone wrong.
- The surrounding code often *already* guards against the value being exactly
  `0` ("not registered yet") but not against nonzero-garbage. **That existing
  zero-check is the tell**, and it also hands you the fix's control flow for
  free.

**Fix pattern:** validate against valid N64 RAM range before use, and on
failure jump to wherever the existing "not ready" path already goes:

```toml
[[patches.hook]]
func = "boot_func_XXXXXXXX"
before_vram = 0xXXXXXXXX
text = "if ((unsigned int)ctx->rN < 0x80000000u || (unsigned int)ctx->rN >= 0x80800000u) { goto L_<existing_fallback>; }"
```

The bound `0x80000000`–`0x80800000` is the same one `scripts/auto_stub_pass.py`
uses. Reuse it; don't invent a new one.

**Known instances:** `boot_func_80026A54`, `boot_func_800395C8`,
`boot_func_80030448`, `boot_func_800303D4`, `boot_func_8004E640`,
`boot_func_8004DD0C` (×2 sites — function pointer rather than data pointer,
same class).

**Fast confirmation:** get the bad value. If it's arbitrary rather than
near-valid, and there's a nearby `== 0` guard, it's this — apply the fix and
verify rather than root-causing the DMA timing again. We have root-caused this
class six times; the mechanism is settled.

**Standing question (not yet answered):** whether to keep patching per-site or
fix it once centrally in `ultramodern`. Six instances is enough that the
central fix probably now costs less than the next three site fixes. Worth
deciding deliberately rather than by default. See the session log's
"Open strategic question" note.

---

### BC-2 — Symbol-boundary mis-split *(3 instances)*

**Class:** A (recompiler output).

> **Instance 3, and the most damaging so far (2026-08-18): a function declared
> TOO SHORT, which fails completely silently.** `ovlfile02_func_800E4F34` was
> declared `size = 0x14`; the real function runs `0x8C` to the next symbol. The
> generated C simply **stopped after the first call** — no error, no warning, no
> stub, and it compiles and runs. The seven statements that were dropped included
> the call registering the renderer's per-frame reset, so pressing START loaded a
> scene that registered nothing, left stale list counts, and segfaulted one frame
> later in a sort. Fix was one number in `symbols/sinpunishment.syms.toml`.
>
> **Detection, and why it is cheap:** decompile the address with
> `scripts/decomp.sh` and compare against the generated C. A short function whose
> generated body ends mid-logic — especially right after a `jal` — is this bug.
> A sweep for `vram + size < next_vram` across the symbol file finds every
> candidate at once (296 exist; most are genuine data, so triage, don't mass-fix).
>
> **Why it evaded every earlier gate:** the symptom appeared four scene loads
> downstream, in unrelated resident code, as a NULL dereference. Nothing pointed
> at a symbol table. Reaching it took a hardware watchpoint on the affected
> global to name the writer, then a `[reg]` probe to show the registration never
> happened. **Truncated symbols present as missing behaviour, never as an error.**

**Mechanism:** a function branches into the **middle** of a neighbouring,
already-declared function — the shared-tail / switch-statement pattern real
compilers emit. N64Recomp can't express this; it tries to synthesize a
standalone function for the mid-function target and fails on nested or chained
cases.

**Signature:** `Unhandled branch in static_NN_ADDR` at build time, **or**
(nastier, and how it bit us) a silently-generated function that is a **true
no-op** — declares locals, returns immediately — where the ROM's disassembly
clearly has real work. Silent version produces a hang/stall, not an error.

**Fix pattern:** in `symbols/sinpunishment.syms.toml`, merge the two symbols
into one — extend the *earlier* function's declared `size` to cover both, and
delete the now-redundant second declaration.

**Known instances:** `ovlfile22_func_800E4780` (`0x40` → `0x20C`, removed
`ovlfile22_func_800E47C0`); `ovlfile01_func_800E4780` (`0x40` → `0xF8`, removed
`ovlfile01_func_800E47C0`, kept `ovlfile01_func_800E4878`).

**Fast confirmation:** disassemble the address range in ares (or against the
ROM directly) and compare against the generated C. A generated function whose
body doesn't match the ROM's instruction count is this.

---

### BC-3 — Call-free spin-wait deadlock *(2 instances)*

**Class:** B.

**Mechanism:** `while (*addr == 0);` with **zero OS calls in the loop body**.
Real hardware preempts via interrupt. `ultramodern` only delivers messages and
reschedules from inside a game thread's own OS calls
(`osSendMesg`/`osRecvMesg`/`osSetThreadPri`/…), so a call-free spin can never
be broken out of.

**Signature:** hang at 100% CPU on one core, no crash, no progress.

**Fix pattern:** `[[patches.hook]]` in the loop body calling
`ultramodern::yield_self_1ms()` (already in the runtime for exactly this).

**Known instances:** `boot_func_80025CA4`, `boot_func_8004D7B0`.

**Scope note:** a codebase-wide scan for this shape (whole function body is a
single backward-branching `MEM_*` poll, no calls) found exactly these two. A
third would most likely show up in gameplay code — same fix.

---

### BC-4 — Unsymbolized Yay0 overlay *(0 confirmed, 1 predicted)*

**Class:** A.

**Mechanism:** a third overlay system distinct from the 27 known `ovlfileNN`
files — 73 boundary markers (72 files) starting at ROM `0x7C8680`, Yay0-
compressed, **zero symbol coverage**.

**Signature:** `Failed to find function` at an address that traces back to one
of those compressed loads (and *not* to the `0x800E4780` shared window, which
is already handled).

**Fix:** not a quick patch — needs a Yay0 decoder plus fresh boundary analysis
on the decompressed output. Comparable in scope to the original 27-file
archaeology. **Do it deliberately as a project, not as a fix in the middle of
another investigation.**

---

## G3 — Can automated tooling answer this?

Check what already exists before writing anything new. **Do not add fresh
instrumentation until you've confirmed an existing hook doesn't cover it** —
several already do.

### G3.0 — First, check you can READ the whole call chain (T43)

Before investigating any backtrace or call chain, run `decomp.sh` over **every
frame at once**:

```bash
scripts/decomp.sh boot_func_80033758 boot_func_80033A40 main_func_800B09EC ...
```

It ends with `coverage: N readable, M NOT FOUND`. **An unreadable frame is the
first finding, not an obstacle to hand-read around.** It means splat has no
segment covering that address (L6); fix the config in the **sibling** repo
`splat-project` (T19), re-run, and verify per T42.

This exists because on 2026-08-19 an A99 investigation hand-read the
transliterated C in `RecompiledFuncs/`, stopped at "the node is arg0", and never
asked whether the *caller* was readable. It was not — and the fix was already
sitting in the schedule labelled as tooling rather than as a dependency of the
frontier. One run of the command above would have said so in seconds.

**Reading generated C by hand is the last resort, not the first move.** That is
what `decomp.sh` is for; a hand-read of `boot_func_8002AA90` on 2026-08-18
truncated and missed an entire list that m2c emitted in six lines.

### G3.1 — Overlay data: ALWAYS list every copy before quoting a value (added 2026-08-19)

**One command, before you quote any value at a `0x802C`–`0x802E` address:**

```bash
grep -l '802CE128' /home/joh/Documents/sin_and_punishment/splat-project/asm/*.s
```

If more than one file defines it, **the value is overlay-dependent** and a
single reading of it means nothing on its own. Quote all of them, or say which
overlay you read.

**Why this is here rather than in anyone's memory.** This is A85's trap and it
has now caught us twice. On 2026-08-19 (A110) the check was run on
`D_802E1680`, came back with a single definition, and was reported clear. One
dereference later (A114) the same reasoning quoted a buffer as
"`.word 0x00000000` in the ROM image, verified by direct lookup" — and that
address is defined in **three** overlays, `0x00000000` in one and real float
data in the other two (A119). The lookup was correct. The scope was not.

**Having cleared the trap once is exactly what makes the second instance
likely** — the check felt spent. It costs one command; run it every time.

### G3.2 — Read the ROM directly with the MIPS toolchain (added 2026-08-19)

`binutils-mips-linux-gnu` is installed. Use it whenever you would otherwise
compute a ROM offset by hand, and to check splat rather than trusting it.

```bash
mips-linux-gnu-objdump -D -b binary -m mips:4300 -EB \
  --adjust-vma=0x80024C00 --start-address=0x800339C8 --stop-address=0x800339F4 \
  /home/joh/Documents/sin_and_punishment/splat-project/baserom.z64
```

* `--adjust-vma` is the vram→ROM delta **as an explicit argument**. That is the
  point: T49 derived a delta from one misread anchor and produced a clean,
  plausible, entirely wrong dispatch table. Here a wrong delta shows up
  immediately as instructions that do not match a known symbol.
* **The delta is per segment, not global.** `0x80024C00` is right for the boot
  segment (`asm/1050.s`); overlays have their own. Get it from the `[[section]]`
  `rom`/`vram` pair in `symbols/sinpunishment.syms.toml`, and T49's two-anchor
  rule still applies to choosing it.
* Validated on adoption (T61): the command above reproduces splat's
  `asm/1050.s` instruction-for-instruction with identical encodings. **Re-run
  that comparison if you ever doubt the invocation** — it is a positive control
  on tool, arguments and splat together.
* `mips-linux-gnu-nm` is also available for the ELF side.

### Environment hooks already built into the build

| Hook | What it does |
|---|---|
| `SP_AUTOSTART=1` | Skip the launcher, boot straight into the ROM |
| `SNP_TRACE=1` | Enables diagnostic prints already scattered through the codebase (input via `maybe_log_input`, audio via `queue_samples`, …) |
| `SP_INPUT_SCRIPT=<file>` | Timed synthetic input: `t=<sec> keydown\|keyup <BUTTON>`, or `stick <x> <y>`. Feeds the same path real input takes |
| `SNP_AUDIO_DUMP=<file>` | Audio capture |

### Scripts

| Script | Question it answers |
|---|---|
| `scripts/boot_screen_check.sh <sec> <out.png>` | "Is the screen black?" — launches, screenshots the *game window* (`xwininfo`+`xwd`+`ffmpeg`), gives a numeric dark-fraction verdict. Window-selection fixed 2026-08-14 to require WM_CLASS `SinPunishmentRecompiled` and exclude `mutter` — it used to match the WM's own decoration/frame window too (same title text) and could silently capture that instead. Check the printed image `size=`: `(1280, 720)` is the real content window; anything else means the wrong window was captured. **A "BLACK" result is no longer trustworthy on its own — see the standing rule below.** |
| `scripts/gdb_watch.sh <vram> [arm] [deadline] [log] [bin] [cond]` | Hardware watchpoint on an N64 address — breaks at `recomp_entrypoint`, captures rdram base, computes the host address. **`[cond]` is appended to the `watch` (e.g. `"== 0x02000000"`) — use it or a hot word floods the watchpoint.** Its arm-time print of the current value is the positive control: if the value is already what you are hunting, you armed too late and a null result would be meaningless |
| `scripts/gdb_fault.sh [deadline] [log] [bin]` | Catches the SIGSEGV and dumps the game-side register file, the per-level `$s0` descent off the game stack, and (with `SNP_RDRAM_DUMP`) an 8MB snapshot — see G7.2. **Two built-in controls:** it names the faulting function and flags a MISMATCH if it is not A99's, and it reports how many recursion levels are stride-consistent (0 means the stack walk is misaligned — do not read the values as a descent). **Run it against `build-debug/` — `ctx` needs debug info; against `build/` you get frame names only.** **`--self-check` (4 controls, added 2026-08-20 as A191): until then this script had NO static controls at all, despite being the tool that produced A99's identification. The defect it was added for: the register labels (`<-- the garbage pointer that was dereferenced`) are read off A99's faulting instruction and were printed UNCONDITIONALLY — three lines after the script's own control reported `This is NOT A99's crash`. On the post-A99 fault that mislabelled a caller-saved return value as a dereferenced pointer. **A control whose result gates nothing downstream is decoration.** The labels are now gated on the frame matching; otherwise the values print bare with the reason. The self-check greps the EXECUTABLE REGION ONLY, and control 1 is verified to FAIL (3/4) when the guard is removed.** There is no core file to inspect instead: `ulimit -c` is 0 and apport owns `core_pattern`, so bash's "(core dumped)" is the signal disposition, not a file |
| `scripts/display_isolate.sh` | Sourced by the three launchers, never run directly. `xvfb` (default, truly headless) / `SNP_ISO=xephyr` (nested — input isolated but **a window IS shown**) / `SNP_VISIBLE=1` (real display, your typing reaches the game — T23). One copy on purpose: three divergent copies is what let the gdb wrappers run unisolated (T59) |
| `scripts/xtest_key.py <win_hex> <keysym>…` | Real synthetic keyboard input to an SDL/X11 window. Clicks into the window first (WM click-to-focus) then `xtest.fake_input`. Works against our build *and* the reference recomps |
| `scripts/xclick.py <win_hex> <x> <y>` | Real synthetic click at a specific point in an X11 window. Reliable against top-level SDL/game-render windows (ours, BanjoRecomp, ares' main window); **not** reliable against native Qt dropdown menus — ask the user to drive those directly instead |
| `scripts/strip_scratch_hooks.sh` | Removes the scratch-debug-hook block from `sinpunishment.toml` between its BEGIN/END markers — **run before committing** |
| `scripts/run_game.sh <sec> <log> [ENV=v…]` | **The only correct way to run the game from tooling.** Kills by PID with SIGKILL and reports `leftover=N`. Plain `timeout` does *not* work (SDL2 catches SIGTERM) and `pkill -f` kills its own shell — see the two rules under G3 |
| `scripts/auto_stub_pass.py`, `auto_label_fix.py`, `fix_dangling_gotos.py`, `fix_zero_writes.py`, `patch_si_stubs.py` | Bulk recompiler-output repairs (class A) |
| `scripts/rom_info.py` | ROM identification / conversion |
| `scripts/rom_disasm.py <vram> [end\ **`--section <name>` (A197) and, since A198, AN AMBIGUOUS ADDRESS IS A REFUSAL WITH EMPTY STDOUT — not a warning.** A warning only works if it is read; a refusal works even when it is not, because there is nothing to misread. Main-segment addresses match one section and are unaffected. **PICK THE OVERLAY EXPLICITLY.** Fifteen sections contain an address like `0x800F9448` — that is what an overlay IS. The tool names all of them on **stderr** and shows the first; **if you pipe it through `2>&1 | tail` you will drop that warning and read the wrong overlay's bytes as though they were your function's** (A196, and it is T76/T84 — check what a pipe drops). The two `--section` controls are in `--self-check`; the discriminating one asserts the flag CHANGES THE BYTES, because a flag that parses and then silently uses the default is exactly the T49 failure and an exit-code check passes on it. |+len]` | Disassemble the ROM at a VRAM address. **Looks the vram->ROM delta up from the `[[section]]` blocks rather than taking it as an argument** — deriving it by hand is what produced T49's confident wrong table. REFUSES if no section contains the address, and warns when several do (overlays share vram — A85/G3.1). `--self-check` compares against splat's committed asm: a positive control on tool, invocation and delta at once |
| `scripts/audit_l2.py` / `scripts/audit_l3.py` | **L2 (daily) and L3 (weekly) of the audit ladder.** L2 groups L1's findings by class and asks whether a fix held; L3 asks whether the rate is falling and which classes recur despite tooling. **Each reads ONLY the level below's output — `--self-check` enforces that by parsing the file's AST, and fails if it constructs a path to any raw-data file.** L3 refuses to claim a direction from fewer than 2 digests (its first block claimed FALLING from one). `--dry-run` on both; `check_ledger` nags when due and its hook exits 2 on an overdue level |
| `scripts/build_staleness.sh` (sourced) | **Warns when a binary is older than the sources it was built from.** `build.sh --no-recomp` builds the RELEASE tree only, so the debug binary both debuggers default to can silently be last week's code — that cost an afternoon's confusion on 2026-08-20 (T125). **Not a build-both rule**: the debug binary is ~247 MB and paying that on every build is a tax that gets worked around. **Not a compare-the-pair rule** either — how much drift is acceptable is a judgement; older-than-its-own-sources is a fact, and it catches the mirror case too. **Warns, never refuses**, because deliberately running an older binary is what every A/B against a snapshot does; `SNP_STALE=0` silences it. Wired into all three runners, with a control asserting so. 8 controls in `test_staleness.sh`; the discriminating pair is fires-on-stale AND silent-on-fresh |
| `scripts/ares_capture.sh [secs] [label]` | **Capture a REFERENCE run in ares to compare against our build.** Output goes to `ares-refs/`, **never `scene-refs/`** — that tree feeds the perceptual matcher with frames from OUR build, and ares renders at a different resolution with the console's video filtering emulated, so mixing them poisons the matcher and invites the pixel comparison T88 forbids. Authoritative for SEQUENCE and IDENTITY only. Runs under `xephyr` so you can watch without keystrokes reaching it. Inherits two hard-won mechanics from `ares_watch.sh`: **absolute ROM path** (relative fails silently inside the flatpak sandbox) and **verify the live cmdline**. 8 controls. **It FAILS when no video was produced** — the first smoke test lost its recording to a mangled filename and still exited 0, because `snp_start_recording` takes a LABEL plus `SNP_REC_DIR`, not a path. Note the automatic crop REFUSES on ares footage: the crop rect is tuned to our binary's window, so every pixel is kept. Crop deliberately to roughly `710x535+265+75` for the game area |
| `scripts/test_supersede.py` | **Controls for the two noise fixes of T123.** `audit.py`'s single-run check now consults `check_ledger.superseded_by_later()` — ONE shared correction-word vocabulary, because two definitions let an entry be live for one checker and dead for the other — and it honours the write-time `ONE RUN IS ENOUGH` waiver it used to ignore. **Every suppression is PRINTED**, since a rule that hides its own work is indistinguishable from a broken check. `route.py` warns when the frontier cannot support exploration at all, or when an EXPLORE draw had a single candidate at p=1.00. **The discriminating control is that a BARE citation must NOT suppress** — otherwise the rule hides every entry anyone mentions again, which is worse than the noise. Verified to FAIL at 6/7. Measured effect on audit #10: 8 findings -> 6, four suppressions all named |
| `scripts/session.py start 25m [task]` / `status` / `shelve` / `block` / `end` | **A timed working session: a deadline, a shelf, and a summary that is required.** Built after the same shape was asked for three times in one day and three things went wrong by hand, none of them judgement calls: **the CLOCK** (elapsed time estimated from how much work had happened, wrong by up to eleven minutes in both directions), **the SHELF** ("shelve it and move on" existed only in my head, so a shelved item could be silently dropped), and **the SUMMARY** (the part with no mechanical check, and the part that got skipped). `end` REFUSES without a plain sentence and applies the ledger's own plain-language test. It also reports **rolls consumed against entries added, naming any entry that cites neither a roll nor user direction** — the drift a human caught by hand. **It cannot decide HARD vs SOFT blocks; that is the one judgement left, and both take a mandatory reason so skipping it is costly.** `--dry-run`, `--self-check` (14 controls; the discriminating two are that the clock actually MOVES and that drift is detected — a status printing a constant would look perfectly healthy). Protocol lives in `.claude/skills/timed-session/` |
| `scripts/gdb_trace.sh <file:line> <cond> <printf-args> [arm] [deadline] [log] [bin]` | **Log a function's ENTRY ARGUMENTS at runtime, conditioned so it fires only on the case of interest.** This is how call chains get established now — a stack image cannot do it (T69). **Controls:** a REACH COUNTER breakpoint that never stops but counts every hit, so 0 conditional hits is only meaningful against a non-zero reach count (T56); refusal if any `__PLACEHOLDER__` survives substitution; `SNP_TRACE_DRYRUN=1` to print the generated gdb script without launching. Logs generic `HIT %08X x4` under a `FIELDS:` header naming the expressions — the labels were once hardcoded `a0/a1/a2/sp` and the second trace logged different registers under them, which is evidence that reads as something else. **Refuses unless exactly 4 comma-separated expressions are given**, since a mismatch makes gdb error at every hit and log nothing. **Use build-debug or `ctx` will not resolve (A122). Mask every register with `& 0xFFFFFFFF` — `ctx->rN` is sign-extended (I17), and an unmasked compare is always false and looks exactly like 'never happened'** |
| `scripts/ledger.py --index \| --show \| --grep \| --open \| --cited-by` | **How the findings ledger is read now** (T67/T68). `--index` renders every entry for ~8.5k tokens and replaces reading the 83k-token file end to end; `--show` expands verbatim. **The index says WHETHER something was checked, never WHAT it established — expand before relying on anything.** `--cited-by <ID>` is the one to run before trusting an old entry: if it is withdrawn, everything listed needs re-checking. **Run `--self-check` first, every time** — 5 controls, and they fail on a body-dumping index (3/5), a tag-dropping one (4/5) and a parser that silently loses odd-shaped rows (4/5, the bug the first version actually had: 33 of 198 rows) |
| `scripts/user_queue.py [--check]` | **The batched list of work only the user can do, and the alarm that stops it rotting** (T131). Several open items need a real display and a person: F1 opens the RT64 inspector and does **nothing** under Xvfb or Xephyr (A245), and naming what a texture IS is recognition work (A227's split). Each needs a launch, a screen and the user present, so run singly they pay that setup over and over; batched, one sitting clears several. **The list is the easy half — the alarm is the load-bearing half**, because T122 is what a queue becomes without one (two confirmed problems written up as findings, never marked open, the router offering one candidate for five straight rolls). **Three counts, none needing a judgement: DEPTH, AGE, BLOCKED.** BLOCKED is the mechanised form of "the last few checkpoints all pointed at F1" — it counts distinct entries the live items CITE, so an entry is in it only because an item names it. **Counted that way on purpose:** deciding whether a checkpoint "pointed at" the inspector is exactly the threshold-judgement T118 measured at a 6-of-7 noise rate and T122 recorded as debt rather than mechanise badly. **It is a REMINDER, NEVER A GATE (T127)** — I cannot clear any item myself and a block only the user can lift would halt work while they are away. **It does not forget (T120):** no high-water mark, so it fires every run until the queue is swept. **An item is SWEPT only when an entry records the result**, not when the observation is made — otherwise it becomes A227, data gathered and nothing resolved. `--dry-run`; **12 controls**, and the discriminating ones are that a dangling `SERVES` is REPORTED, that a SWEPT item naming no result entry is REPORTED, that a small fresh queue raises NO alarm (one that always fires is not an alarm), and that the scope rule still bites inside items — **that last is restored coverage, not new: excluding this section from ledger parsing also removed it from the prose checks, which had already flagged two of these very items.** Its first real run fired immediately on 9 blocked entries, which is what T100 asks of a new checker |
| `docs/agent-brief.md` + `docs/agent-trial-2-scoring.md` | **The sub-agent contract and the trial that priced it** (T157/T158). Brief Part 1 = when to spawn; Part 2 = pasted into the prompt verbatim. **Not a script, so `lint_tools.py`'s documentation rule does not cover it** — instead it has a dedicated content control there, verified to FAIL at 10/11 against a gutted brief, because a file that exists and has been emptied looks identical to a healthy one and would vouch for nothing. The scoring key was **committed before the run** (`ea1a444`) so the criteria could not be invented after seeing the output, the same reason `route.py` carries a witness. **Its ground truth is a crash measured twice and a finding I verified myself** — trial 1's control was VOID because I seeded it from my own unchecked source reading, one instance of which was a local variable sharing a name |
| `/home/joh/opt/ELAN_7.1/bin/ELAN_7.1` | **Time-aligned video annotation — how the user returns observations now (2026-08-21).** Not ours and not in `scripts/`: ELAN 7.1, installed from the MPI tarball into `~/opt` (bundled Java 26, **no sudo, nothing touching system packages**; the `.deb` would have needed it). Scrub, pause, mark a **point or a span**, type a note, across multiple tiers. **THE OUTPUT IS THE WHOLE POINT — and it is the `.eaf` THE USER GETS BY HITTING SAVE, not an export.** ~~`File → Export As → Tab-delimited Text`~~ — **CORRECTED BY THE USER 2026-08-22, see T150**: the format settled on is whatever ELAN writes on save, and that file already carries everything needed. `evidence/2026-08-21/run_game-135748.eaf` is the worked example: `TIME_ORDER` holds every start/end in milliseconds and each `ALIGNABLE_ANNOTATION` names its two slots, so "the background is missing here" becomes a timestamp range I can pull exact frames from, with no export step and nothing for the user to remember. A247, the biggest finding of 2026-08-21, came from the user saying *which frames to look at*; this makes that the normal case. **Suggested tiers: one for faults, one for SCENE IDENTITY** — the second earns its place because scene identity has been wrong twice from my sampling (A93, A161), the observation right and the quantifier wrong, and a user-stamped tier removes that failure mode entirely. **IT RUNS ON THE REAL DISPLAY (`:0`) AND THAT IS NOT AN ISOLATION BREACH:** T59/T23 govern *the game*, whose input must never be contaminated. This is a viewer reading files off the archive drive with no game running. **IT DOES NOT CLEAR THE OBSERVED-RUN GATE (T101)** — annotating old footage is not watching the build behave, and the gate is about a run happening. Our recordings are H.264 / yuv420p / 640x480 / 30 fps, which it plays natively; if video loads but will not play, that is ELAN's media backend preference, not the file |
| `scripts/rdram_peek.py <snap> <vram> [n]` | Read game memory out of an RDRAM snapshot — no gdb, no game run. `--stride N` for record arrays, `--regs` for the register file at the fault. **Run `--self-check` first, every time**: it asserts values measured by other means and catches the silent endianness/offset errors that produce plausible byte-reversed output (T64, and I7 for the same fact about byte access) |
| `scripts/rr_record.sh` | **Refuses by default — `rr` cannot record this target (G7.1/T62).** Kept for a future `rr` version; `SNP_RR_FORCE=1` overrides |

### Standard loop

```bash
./scripts/build.sh          # NOT recompile.sh + cmake directly:
                            # build.sh lints the probes first and snapshots the
                            # binary it is about to overwrite (T25/T26)
./scripts/boot_screen_check.sh 60 /tmp/check.png
```

### `scripts/yaz0_extract.py` — reading the SIBLING PORT's ROM (added 2026-08-28, A658)

**WHAT IT IS FOR.** T197 wants to borrow function names from the Majora's Mask
decomp. A642 verified our MM ROM is the correct revision — its md5 matches
zeldaret/mm's published `checksum-compressed.md5` **exactly** — and then found
the blocker: **2,033 Yaz0 blocks starting at 0x956780, 70.8% of the image.**
Skeleton matching needs function BYTES, and you cannot read bytes out of a
compressed ROM by address.

**THE BORROW ARM WAS CLOSED FIRST.** A650 fired A642's own falsifier across four
independent channels — repo + submodule source, the toolchain directory,
importable Python modules, `PATH` — and found nothing. Only then was writing one
the right move.

**DO NOT CONFUSE IT WITH `yay0_extract.py`.** *Our* game uses **Yay0** (28 blocks,
0 Yaz0); *MM* uses **Yaz0** (2,033 blocks, 0 Yay0). Two formats, near-identical
names, different layouts — Yay0 stores its three streams separately, Yaz0
interleaves a flag byte with the data. The existing tool does not help here and
reaching for it will silently produce nonsense.

**THE THREE GATES, all met in the checkpoint that added it (T71):**
* **Dry run** — `--dry-run <rom>` reports block count, first/last offset and
  total declared size, then exits without decoding or writing.
* **A control that CAN fail** — `--self-check <rom>` runs **both arms**:
  15 real blocks sampled from the start, middle and end must each decode to
  **exactly the length their own header declares**; then three deliberate
  corruptions must each be **REJECTED** — a bad size field, a truncated image,
  and a wrong offset. **5/5 at time of writing.** A control that only checks the
  passing case is what let T226 survive.
* **This write-up**, same checkpoint.

**THE ONE IMPLEMENTATION TRAP.** Back-references may **overlap themselves** —
that is how runs are encoded — so the copy must be **byte at a time**. A slice
copy passes casual testing and gives wrong output on exactly the cases the
format exists to compress.

```bash
scripts/yaz0_extract.py --dry-run "rom/Legend of Zelda, The - Majora's Mask (USA).z64"
scripts/yaz0_extract.py --self-check "rom/Legend of Zelda, The - Majora's Mask (USA).z64"
scripts/yaz0_extract.py --list <rom>                # every block + declared size
scripts/yaz0_extract.py <rom> 0x956780 out.bin      # decode one block
```

**MEASURED:** block 0 at 0x956780 is 41,746 compressed → 84,720 bytes; the whole
ROM declares 36,872,880 bytes uncompressed across its 2,033 blocks.

#### `build.sh` used to exit 0 on a build that failed — fixed 2026-08-28 (T226)

**THE INCIDENT (A631).** A compile error appeared in the build output, the
executable was never relinked, and `build.sh` printed `==> built <time>` and
returned **rc=0**. It was caught only because someone happened to grep the
output for `error:`.

**THE CAUSE, and it threw the status away twice.** The build line read
`if ! timeout 1800 cmake --build build … | grep -E "…"; then : ; fi`. The
pipeline reported **grep's** status rather than cmake's, and the
`if ! …; then :; fi` swallowed even that. Control then fell to the
`[[ -x "$BIN" ]]` test, which **passed on the STALE binary from the previous
build** — still present, still executable.

**WHY IT MATTERED HERE MORE THAN ELSEWHERE.** Every measurement on this project
runs `build/SinPunishmentRecompiled`. A silent build failure means the next run
measures the *previous* binary while the log says the change was applied — the
one tool standing between every code change and every number we take, producing
a confidently wrong answer.

**THE FIX.** cmake's output goes to a **file** rather than a pipe, its real exit
status is captured into `BUILD_RC`, and a non-zero status prints the error,
says the on-disk binary is stale and must not be measured, **keeps the whole
log** and exits 1. Writing to a file rather than a pipe is deliberate (T163):
the `grep` filter still keeps normal output short, but it can no longer *drop*
anything, because the full log survives and its path is printed.

**THE CONTROL, RUN IN BOTH DIRECTIONS — a one-direction control is what let this
survive.** Verified 2026-08-28, ~90 s total, using `--no-recomp`:

* **Must FAIL:** append a bad token to `src/main/register_overlays.cpp` (22
  lines, git-clean, compiles in seconds) → **rc=1**, the error printed, the
  stale-binary warning printed, log kept.
* **Must PASS:** restore and re-run → **rc=0**, `Linking CXX executable`,
  `==> built`.
* **And the tree is left where it started:** back the file up by **copy and
  restore by sha256**, never `git checkout` — this tree carries uncommitted
  probe content and a stray checkout would destroy it. The binary was confirmed
  byte-identical (`a0db62c2…`) before and after.

**KNOWN ROUGHNESS, not fixed:** on failure the `tail -30` is often dominated by
one enormous compiler command line. The concise `error:` lines are already
printed above it by the filter, and the full log path is given, so nothing is
lost — but do not expect the tail alone to be readable.

### Wayland/xwd capture unreliability — root-caused and fixed, 2026-08-14

**`xwd`-based capture could *intermittently* report solid black for a window
that was genuinely rendering correctly** — not consistently broken, which is
what made it dangerous. This machine's desktop session is Wayland
(`$XDG_SESSION_TYPE=wayland`); `xwd`'s traditional X11 `XGetImage` capture
reads a window's legacy X11 backing store, and this game's Vulkan swapchain
presentation (`SDL_WINDOW_VULKAN` + RT64) doesn't reliably keep that backing
store updated under XWayland. Caught by contradiction: `nvidia-smi` showed
the game actively rendering (GPU memory + compute in use) while every
capture insisted the screen was black; resolved by asking the user to look
directly, which showed it was fine the whole time.

**Actually fixed, not just worked around**: `SDL_VIDEODRIVER=x11` forces a
native X11 window instead of a Wayland-native one, which sidesteps the whole
XWayland/Vulkan interaction. Verified with three consecutive captures in a
row, all correct — this was the intermittent failure's real cause, not a
coincidence of timing. `scripts/boot_screen_check.sh` now sets this by
default. **This specific tool no longer needs the black-result caution below
applied to it** — but the underlying mechanism (Wayland + Vulkan + `xwd` is
an unreliable combination) is still true for *any other* ad hoc capture on
this machine that doesn't force the same driver, so the general rule stays.

**A second, related fix while making the game run out of the user's way**:
the user asked whether test runs could avoid depending on their own screen
at all — not just capture-reliably, but not visibly interrupt them either.
True headless rendering isn't available here (Xvfb + software Vulkan aren't
installed, need `apt`+sudo). What worked instead: standard ICCCM iconify
(`WM_CHANGE_STATE` → `IconicState` via a `ClientMessage`, not a plain move —
GNOME/mutter clamps windows back on-screen if you try `configure(x=-3000,
...)`, and ignores `_NET_WM_DESKTOP` requests for workspaces that don't
exist under its dynamic-workspace model). New script:
`scripts/minimize_window.py`. The game keeps rendering and stays fully
capturable via `xwd` while minimized — confirmed with a capture taken 45s in,
well after the window had left the user's view, showing the attract-mode
subtitle text had genuinely advanced between runs (a live, progressing
capture, not a stale one).

**One real pitfall integrating the two, worth remembering for any
similar window-automation task**: minimizing a window *immediately* at
creation — before its first successful frame present — can leave it stuck
never rendering for the rest of the run. Confirmed reproducible twice.
Minimizing only works reliably once the window has actually presented a real
frame. `boot_screen_check.sh` handles this by polling with quick throwaway
`xwd` captures (every 0.25s) until the first non-black one shows up, then
minimizes immediately — self-calibrating to the real first-present timing
rather than guessing a fixed delay, which would otherwise be either too
conservative (window stays visible longer than it needs to) or too tight and
flaky under system load. A fixed 8s delay was tried first and worked, but
the user reasonably wanted the window visible for less time than that when
it isn't necessary — the polling version minimizes as soon as it's safe,
observed at roughly 1-3s in practice, without needing to know or tune that
number.

`boot_screen_check.sh` minimizes by default now; set `KEEP_VISIBLE=1` to skip
it when a human actually needs to look at the live window.

### Liveness is measured with `SNP_HEARTBEAT=1`, never by diffing screenshots

**Do not judge "is the game still running?" from frame-to-frame screenshot
differences.** `boot_screen_check.sh` and `freeze_check.sh` both *minimize* the
window before capturing, and `xwd` on a minimized window does not reliably
reflect what is being drawn. Differences between consecutive captures there are
capture noise, not animation.

This produced confident wrong answers in **both** directions on 2026-08-15/17 —
"still animating at 100s" and "freezes at 40-55s" — and a 5-run survey reporting
`ANIMATING 5/5` for a build the user was watching sit frozen. The user caught it
every time; the tooling never did.

**Use the heartbeat instead:**

```bash
SP_AUTOSTART=1 SNP_HEARTBEAT=1 ./build/SinPunishmentRecompiled
```

It counts display lists the *game* submits (`submit_rsp_task`, `M_GFXTASK`) and
reports once a second from a sampling thread — so it still prints when
submissions stop, which is the interesting event:

```
[heartbeat] t=42s gfx_tasks=1240  +29
[heartbeat] t=43s gfx_tasks=1240  +0  <<< NO GFX TASKS (1s stalled)
```

Produced by game logic, independent of any window, compositor or capture path.
It agreed with direct human observation immediately where screenshot diffing had
failed repeatedly. Screenshots remain fine for *what* is on screen; they are not
evidence of *whether the game is running*.

**Corollary — never compare readings across separate runs.** Each
`boot_screen_check.sh` invocation launches a fresh process. Comparing its output
at 50s, 70s and 100s compares three independent runs, which measures run-to-run
variation, not whether one run is progressing. This game's boot is genuinely
nondeterministic (freeze / run-long / silent exit / never-render all occur from
one binary), so **any claim from a single run is unfounded by construction** —
use `scripts/freeze_survey.sh` for outcome rates.

### General rule: a "BLACK" verdict from an unfamiliar capture method is not trustworthy on its own

The specific tool above is fixed, but the underlying lesson generalizes to
*any* future screen-capture need on this machine that isn't already going
through the fixed path: before concluding a build is broken from a black
screenshot, get at least one independent, non-visual signal first. In order
of preference:
1. **Ask the user to look directly at their screen.** Fastest, most reliable,
   zero setup. Use this first, not last, when a screenshot alone is the only
   evidence of a problem.
2. **A stderr trace/probe signal** (`SNP_TRACE=1`, or a temporary probe like
   the gfx-task-submission counter used this session) — proves real
   game-logic/renderer activity independent of any capture method.
3. **A live gdb thread-state check (G7)** — proves threads are or aren't
   actually stuck, independent of any capture method.

A black `xwd` capture is only usable as *corroborating* evidence once one of
these confirms the same conclusion, never as the sole basis for "this build
regressed." This upgrades — doesn't replace — the three-band ambiguous
threshold from `EV` rule 1: that handles genuinely borderline pixel
statistics; this handles the capture method being *confidently wrong*.

### Never put `pkill -f <binary>` in the same command line as the run

`pkill -f` matches against **full command lines** — including the command line
of the shell that is running the `pkill`. So this self-destructs:

```bash
pkill -f SinPunishmentRecompiled; sleep 1; timeout 10 ./build/SinPunishmentRecompiled   # kills its own shell
```

It fails **silently and misleadingly**: the run returns `Exit code 144` with
*zero* output — no game output, and not even output from `echo` statements
earlier in the same line. On 2026-08-15 this was misread as "the game hangs
before initialisation" across an entire debugging stretch, while the game was
in fact segfaulting in ~1s. It simultaneously produced a "can't close the game
window" symptom, because the pkill never reached the real process.

**The `[R]` bracket trick is NOT a sufficient fix.** It stops the *pattern*
from matching its own argv, but the same command line usually also contains
the binary path in plain form (`./build/SinPunishmentRecompiled` on the
`timeout` line) — and `pkill -f` matches *that*, killing the shell anyway.
Recorded because it was tried as the fix in this session and failed exactly
this way, producing another round of silent no-output runs.

**Use `scripts/run_game.sh`.** It kills **by PID**, never by name pattern,
which is the only form that cannot self-match:

```bash
scripts/run_game.sh 20 /tmp/run.log SNP_TRACE=1
```

It prints `leftover=N` so a failure to die is visible rather than silent.

Generalised rule: **a test command that returns no output at all has not
proved anything about the program.** Before concluding "it hangs", confirm the
harness itself survived — put an `echo` at the end of the line and check that
it printed. This is the `EV`-gate discipline applied to the harness rather
than to the program.

### `timeout N` does not kill this game — SDL2 eats the SIGTERM (root-caused)

This was previously recorded under G7 as observed-but-not-root-caused ("two
`timeout 20` runs were both still alive ~1h45m later"). The cause:

**SDL2 installs its own `SIGINT`/`SIGTERM` handlers by default** and converts
them into an `SDL_QUIT` *event* rather than terminating. `SDL_HINT_NO_SIGNAL_HANDLERS`
is not set in `src/main/main.cpp`. So `timeout N` politely *asks* the game to
quit — and while debugging, the game thread is usually blocked and never
processes the event. The process survives indefinitely, the window stays up,
and the WM eventually shows the user a **"application is not responding /
force quit"** dialog. That dialog is a symptom of this bug, not of the game.

Measured this session, same binary, same build:

| kill method | result |
|---|---|
| `timeout 12` (SIGTERM) | **still alive at 120s** |
| `kill -9` by PID (`scripts/run_game.sh 12`) | dead at 12s, `leftover=0` |

**Never use plain `timeout` on the game.** Use `scripts/run_game.sh`, or
`timeout -s KILL` if invoking directly. SIGKILL cannot be caught by SDL or
anything else.

### Never "fix" a bug by editing `RecompiledFuncs/`

`RecompiledFuncs/` is **gitignored, untracked, and regenerated from scratch by
every `recompile.sh` run.** An edit there is invisible to `git status`, cannot
be reviewed or committed, and evaporates on the next recompile — so a "fix"
that lives there will appear to work and then silently vanish, and any later
session will be unable to see why behaviour changed.

Worse, the generated C is a faithful transcription of the ROM. If it does
`sw $zero, ...` then the ROM zeroes that word, and overwriting that with a
hand-picked value is **fabricating behaviour the game does not have** — it
does not fix the reason the real writer never ran. On 2026-08-15 a callback
slot was force-populated this way; it made the callback fire, and the
resulting segfault was then chased as if it were a separate bug.

Probes and `#include <stdio.h>` in generated files are fine (they're
observational, and reapplied per the note below). *Semantic* changes are not:
they belong in `sinpunishment.toml` patches, the symbol map, or the runtime.
If a function never runs, find its real caller — see **G4**'s "Tracing
indirect calls (function-pointer tables in ROM data)".

### A note on scratch hooks

Temporary `[[patches.hook]]` entries go between the BEGIN/END markers in
`sinpunishment.toml` and get stripped by `strip_scratch_hooks.sh`. Instrument
freely, but **revert instrumentation in submodules by hand**
(`git checkout -- <path>`) — the strip script doesn't touch those, and a stray
`printf` in `lib/N64ModernRuntime` will silently ride along into a commit.

**A `fprintf`/`stderr` scratch hook needs `#include <stdio.h>` added by hand.**
The generated `RecompiledFuncs/funcs_N.c` files don't include it by default,
so a hook text using `fprintf(stderr, ...)` fails to compile
(`'stderr' undeclared`) the first time. `scripts/ensure_stdio.py` already
exists for this but only fires on files containing the literal string
`"[flag]"` (an older, different debug-print convention) — it won't catch a
differently-tagged probe. Either match that exact tag, or just manually
prepend the include to the affected generated file(s) after `recompile.sh`
and before `cmake --build` (fine for a one-off — `RecompiledFuncs/` is
gitignored and regenerated every time anyway).

### A probe set ships with its controls, or it costs a second build (added 2026-08-18)

`recompile.sh` + `cmake --build` is ~3 minutes, and a probe run that must reach
frame 992 is another **5 minutes**. So a probe that has to be revised because it
lacked a control costs roughly one working cycle, every time.

On 2026-08-18 three cycles were spent on one question and **one was pure
waste**: the first probe set had ARM lines but no *heartbeat*, so a 60s run came
back completely silent. That silence was unreadable — a true negative and a
probe that never reached its frame gate look identical (T16, and defect class
I1). The second cycle added four characters' worth of heartbeat and nothing
else.

**Before building, every probe set gets all four:**

1. **ARM line** — one print on first execution. Proves the probe is live.
2. **Heartbeat** — a periodic print of the gating variable (frame counter),
   from at least one probe. Proves the gate was *reached*, which is a different
   claim from "the probe ran".
3. **`static _Thread_local`** on all probe state (I4/I5/I8 — three defects of
   this one class).
4. **A run length that reaches the gate.** ~300s to pass frame 1024 here. The
   habitual 20-45s run does not get there, and its silence means nothing.

Batch every probe you can foresee needing into **one** hook set. Hooks are
cheap per-probe and expensive per-build: 14 probes cost the same as 1.

### The audit ladder (added 2026-08-18)

26 of 170 ledger entries were withdrawn in one session, and in-the-moment
discipline caught almost none of them. What caught them: the user spotting two,
random EXPLORE rolls landing on stale items, and one audit. So review is the
mechanism that works here — but only if it is cheap enough to actually happen.

**The rule that keeps it cheap: each level reads the level below's OUTPUT, never
the raw data.** Nothing ever trawls the journal.

| level | when | reads | output |
|---|---|---|---|
| L0 | every checkpoint | — | `check_ledger.py` hook + `route.py` roll |
| **L1** | every ~10 rolls | ledger table, `run-log.tsv`, `route-log.md`, git | `scripts/audit.py` -> `docs/audit-log.md`, <=15 lines |
| **L2** | daily | **only the L1 blocks** in `audit-log.md` | group defects by class; did the fix for class X hold?; list the day's load-bearing claims + falsifiers for the user to scan |
| L3 | weekly | **only the L2 blocks** | which classes recur despite tooling? — plus a defect-count direction that is **CONFOUNDED and labelled as such** (T100): a falling count cannot be told apart from having stopped noticing, and better discipline raises it first |

`audit.py` checks **leading indicators**, never findings themselves —
re-verifying a claim costs what producing it cost, and an audit that expensive
gets skipped. Each check maps to a failure that really happened: single-run
claims (T22), probes with no control (I1, I13), entries created and withdrawn
in one window (I14), explore ratio below eps (T14), missing evidence (the
A24/B35 dangling-citation class), contaminated runs (T23).

**Kill criterion, so this cannot become theatre:** three consecutive quiet
audits -> halve the frequency. Two quiet L2s -> drop to weekly. An audit that
never fires is a cost, not a control. `audit.py` tracks the quiet streak itself.

> **A NO-OP IS NOT A QUIET DAY (fixed 2026-08-20).** The kill criterion above
> nearly disabled the ladder using the ladder's own inactivity as the evidence.
> Both `audit_l2.py` and `audit_l3.py` computed
> `quiet = not new or <no defects found>` — which scores **"the level below has
> not run"** identically to **"I read its output and it was clean."** Those are
> opposite situations. And because each level reads the level below, it
> compounds: one skipped L1 makes L2 quiet, which would make L3 quiet, so
> **skipped work propagates upward as apparent health.**
>
> It was one step from firing. On 2026-08-20 an L2 ran with no new L1 blocks,
> scored itself quiet, and took the streak to 1; a second would have dropped L2
> to weekly — while the un-audited window contained T89, T90 and T91, the worst
> defects of the session.
>
> Now a no-op **HOLDS** the streak: it cannot advance it (nothing was examined)
> and must not reset it (nothing was refuted). The digest says so out loud
> rather than printing a number — *"n/a — NOTHING WAS DIGESTED, so this is not
> evidence of calm"* — and names the level that is behind. Both `--self-check`s
> gained a control over the three cases, **verified to fail** by reinstating the
> old expression (it reported `no-op holds: got 2 want 1`).
>
> The general shape, worth carrying: **any metric that treats "no input" as
> "good input" will eventually be satisfied by doing nothing.**

**L2 and L3 were BUILT on 2026-08-19 (T78), 1 day after being specified.** Until
then they existed only as the table above — no script, no trigger, no run — and
the user had been doing L2's job by hand, catching four claim-broader-than-
evidence defects in one session that no mechanical check could see.

```bash
scripts/audit_l2.py --self-check   # 4/4; layering by AST + the no-op control
scripts/audit_l2.py --dry-run      # digest, record nothing
scripts/audit_l2.py                # record an L2 block
scripts/audit_l3.py --self-check   # 6/6; layering + no-op + confound-note controls
scripts/audit_l3.py                # same shape, reads only the L2 blocks
```

**The layering is enforced, not promised.** Each level's `--self-check` parses
its own AST and fails if the file constructs a path to any lower-level or raw
data file. That control was wrong twice before it worked: the first version
searched for the bare filenames and matched *its own list of them*; the second
searched for the `DOCS / "name"` idiom and matched *the comment explaining the
idiom*. A control that fires on its own text is as useless as one that cannot
fire (T65).

**`check_ledger.py` nags for both** — daily for L2, weekly for L3 — because L1
had a nag and still went 13 rolls unread (T76), so a level with no nag was never
going to run at all.

**L3 refuses a trend below 2 digests.** Its first recorded block claimed
"defects per digest: 118.0 -> 0.0 — FALLING" from a *single* digest: the window
was halved regardless of size and the empty half scored 0. That is a direction
asserted from n=1 — T72's error, printed by the tool meant to catch it. The
block is annotated VOID in `audit-l3-log.md` rather than deleted.

**Known limit.** Mechanical checks catch structure, not "this claim is broader
than its evidence" unless it leaves a trace — and both errors the user caught
were of exactly that kind. L2's real product is therefore a digest short enough
for the user to scan in 30 seconds, not a verdict from the same judgement that
made the error.

### Reverting a multi-file change: revert every piece together, not one at a time

**A real bug, caught by the user watching directly, not by any tooling**:
reverted `sinpunishment.toml` back to committed state but forgot
`scripts/patch_si_stubs.py` and the `cont.cpp` submodule change, which were
still holding the *other*, SI-fix version. The result wasn't "old state" or
"new state" — it was a **third, untested, broken combination**
(`sinpunishment.toml` said two functions should be empty stubs;
`patch_si_stubs.py` no longer knew to inject a return value into them, since
its list had also changed). Produced a real black screen that looked exactly
like a genuine regression.

**When a fix spans multiple files that depend on each other's exact content
(here: a TOML stub list + a Python post-processor that reads the same
function names + a C++ source addition), revert all of them in the same
step, then verify each one individually — not just the one that comes to
mind first.** `diff`/`git diff` every file that was part of the original
change, not just the most obviously-changed one. A partial revert can be
harder to diagnose than either full state, because it doesn't match either
of the two things you've already characterized.

### Where captures live (added 2026-08-18)

Screenshots do **not** stay in the scratchpad. One ares session at 2s sampling
produced 106 PNGs plus 14MB of `.xwd` intermediates, on a root filesystem at 92%.

- **Keep** the handful of frames that are *reference behaviour* — what the real
  game does — in `/media/joh/extra/sin-punishment-archive/reference-captures/`,
  with a README naming each. That set is 308KB and re-deriving it costs a whole
  ares session.
- **Delete** every `.xwd` intermediate (~700KB each, regenerable in one command)
  and every frame that only re-confirms what a kept frame already shows.
- **Never** leave a copied binary in the scratchpad. `build.sh` snapshots builds
  to the archive drive, so a stray `cur.bin` is 23MB of pure duplication.

### Caching a known-good build for fast comparison

**Snapshot on every state you might want to A/B later, not only on milestones
(added 2026-08-18).** The rule above says "milestone", and following it that
literally cost a control: on 2026-08-18 several builds ran healthy for 90s at
`+30/s`, later builds stalled at t~20s (A86), and by then **every healthy binary
had been overwritten by the next `cmake --build`** — so "is it the build or the
environment?" became unanswerable. An older cached binary was no substitute: it
predated the heartbeat probe, so it had no comparable liveness signal at all.

Cheap rule: before a build that changes anything you might want to compare
against, copy `build/SinPunishmentRecompiled`, `sinpunishment.toml` **and**
`symbols/sinpunishment.syms.toml` into `known_good_builds/` with a dated name.
~24MB each, the directory is gitignored, and a snapshot is far cheaper than
re-deriving a lost baseline. Name non-milestones `DIAGNOSTIC` so the label never
implies a verified state — a milestone still requires the user confirming on
screen.

**A cached binary is only a control if it carries the same instruments.**
Snapshot the probe set with it, or the comparison it was kept for cannot be
made.

`known_good_builds/` (gitignored) holds verified-working binaries + their
matching `sinpunishment.toml`, so comparing current behavior against a known
baseline doesn't require a full `recompile.sh` + `cmake --build` cycle each
time — copy the cached binary into `build/` directly. Worth refreshing
whenever a new, verified-stable milestone is reached (e.g. after confirming
via `boot_screen_check.sh` + direct viewing that a build is genuinely
healthy) — cheap to do at that point, saves a full rebuild later whenever
that baseline is needed again for an A/B comparison (e.g. "does the known-good
build's thread state look the same as the one I'm debugging").

---

## G4 — Can documentation or an existing resource answer this?

Cheaper than any experiment. Check in this order:

0. **`scripts/decomp.sh <func>` — decompile the ROM function and read it.**
   Added 2026-08-18 and now the FIRST thing to try for any "what does this
   function actually do?" question. It runs m2c over splat's per-function
   assembly and emits real C. `boot_func_8002AA90` came out as six lines:

   ```c
   void func_8002AA90(void) {
       D_80067D98 -= D_80067D9C * 4;
       D_80067DA0 -= D_80067DA4 * 4;
       D_80067DA8 -= D_80067DAC * 4;
       func_8002AA3C(&D_80067CA0);
       D_80067DB4 -= D_80067DB8 * 0x10;
   }
   ```

   The same function took a hand-read of ~60 lines of `ctx->r2 = SUB32(...)` in
   `RecompiledFuncs/` to reach the same conclusion — and that hand-read stopped
   early and **missed the fourth list entirely**. Needs no MIPS toolchain (there
   is none installed, and none is required) and no ROM access.

1. **`docs/boot-debugging-2026-08-13.md`** — 25+ passes of findings, including
   several explicitly-recorded dead ends. Re-reading this has repeatedly been
   cheaper than re-deriving.
2. **Our own runtime source** — `lib/N64ModernRuntime` (`ultramodern`,
   `librecomp`), `external/N64Recomp`, RecompFrontend (`recompui`,
   `recompinput`). For class B questions the answer is usually *readable* and
   doesn't need an experiment at all.
3. **`n64decomp/libreultra`** — full libultra decomp. Ground truth for what an
   `os*` call is actually supposed to do.
4. **n64brew.dev wiki** — hardware behaviour (PI/SI/VI/DP timing, memory map).
5. **Upstream repo** — `maximilianoide/sin-punishment-recompiled`: commits and
   open issues. (As of last check: no issues, no commits past `8c31a07`.)
6. **The reference projects' repos** — Zelda64Recomp and BanjoRecomp have both
   solved problems we haven't. Their commit history is searchable prior art.

7. **GameShark cheat codes** (libretro-database has a `(J)` set for this ROM).
   An underrated symbol source: N64 cheat addresses are **KSEG0 virtual
   addresses**, the same `0x80xxxxxx` space `SNP_WATCH` takes, so they are
   usable verbatim with no translation. Confirmed useful:

   | address | meaning |
   |---|---|
   | `0x80075DD6` / `DD8` / `DDC` | unlocked levels / option-menu items / credits — i.e. the **save+options block**, which also contains the `0x80075DCC` gate byte we had already probed anonymously |
   | `0x800D5A9B` / `0x800D5A97` | energy / time, fixed across all levels — a ready-made "are we actually in a level yet?" signal |
   | per-level player struct | varies wildly by level (`0x8010BB2B` in 0-0, `0x801657FB` in 1-1), so the player object is heap-allocated after level load |

   Also tells us a **level "0-0" exists before 1-1** (the tutorial), so the
   transition START triggers is attract → 0-0.

> **Standing principle** (see the `check_for_existing_resources_first` memory):
> search for an existing decomp/doc/tool before deep manual reverse-engineering.
> This project's symbol map exists because someone else did that work already.

> **Negative result, recorded so it is not re-searched** (2026-08-18): there is
> **no public Sin & Punishment decompilation or symbol map**. Nothing on GitHub
> or under `n64decomp` — only translation patches and cheat files. The manual RE
> here is not duplicating anyone's work. Translation patches are *not* worth
> mining: they produce a modified ROM with a different checksum (so our symbol
> map would not apply), and what they reverse-engineer is text pointer tables
> and font routines, nothing on the render or scheduling paths.

### Tracing indirect calls (function-pointer tables in ROM data)

If a function has no caller anywhere in the generated C (checked via grep,
including split `lui`/`addiu` forms for the address), it's likely invoked
indirectly through a function-pointer table sitting in ROM *data*, which
N64Recomp has no way to know is code-shaped and so never disassembles or
cross-references. Confirmed working recipe: search the raw ROM bytes
directly for the target address(es) as big-endian 4-byte words —

```python
rom = open("rom/sinpunishment.z64", "rb").read()
rom.find(bytes.fromhex("8004C680"))  # -> ROM offset, if present
```

A real hit is usually part of a small contiguous array (one entry per
item — e.g. one per controller port); dump a few words either side to find
the table's actual boundaries.

**Converting the ROM offset to a VRAM address: use the segment table's own
documented mapping, never back-compute it from matching a short instruction
sequence.** `symbols/sinpunishment.syms.toml`'s header comment gives the real
mapping per segment (e.g. `.boot`: ROM `0x1000` → RAM `0x80025C00`) — add the
same delta to your ROM offset. **Do not** calibrate the delta by finding a
known function's own opcode bytes in the ROM and computing
`vram - found_offset`, unless you've first confirmed that byte sequence is
unique across the whole ROM. A 3-instruction function prologue
(`addiu sp,sp,-N; sw ra,...; sw s0,...`) is common enough to occur hundreds
of times — the naive version of this silently picked a wrong occurrence and
produced a confidently wrong address. Caught only by checking the match count
before trusting it (which the segment-table approach makes unnecessary in the
first place).

**Static tracing has a hard ceiling at a `LOOKUP_FUNC(ctx->rN)(rdram, ctx)`
call site: the actual target is only known at runtime.** Grepping every
static reference to a data table (as above) finds what a dispatcher *can*
call, not what it *does* call on a given run — a live gdb backtrace through
an active `LOOKUP_FUNC` call shows the real target directly in the frame
(`#N boot_func_XXXXXXXX ()` right below the `LOOKUP_FUNC` frame). This is
exactly the kind of thing that's cheap to verify with G7 and expensive to
fully rule out with G4 alone: a whole indirect-call chain
(`boot_func_8004EAD0` → `boot_func_8004D428` → `boot_func_8003D750` →
`boot_func_8003D5B0`) was completely invisible to every static search this
project ran, because the dispatcher's only static reference to any of it was
the generic `LOOKUP_FUNC(ctx->r2)(...)` pattern — the real target only showed
up once something was actually running under gdb.

---

## G5 — Cross-compare with a reference recomp (MM / BK)

**Valid for class B only.** These share our *exact* runtime source
(`lib/N64ModernRuntime`, RT64, RecompFrontend), so "does this happen there
too?" cleanly separates "our game's bug" from "how this runtime works."

**Invalid for class C.** They tell you nothing about what Sin & Punishment's own
code should do.

**Locations:** `/home/joh/Documents/reference-recomps/BanjoRecomp` and
`/home/joh/Documents/reference-recomps/Zelda64Recomp`,
both built (`build-cmake/BanjoRecompiled`, `build-cmake/Zelda64Recompiled`).
Setup details, ROM hashes, and decompression steps are in the
`sin_punishment_recomp_status` memory.

**Procedure:**
1. Make the identical change/instrumentation in the reference project's copy of
   the shared file (e.g. `lib/N64ModernRuntime/librecomp/src/cont.cpp`).
2. Reach a state in the reference game that is **unambiguously** the state you
   need — see the trap below.
3. Compare. Then **revert the instrumentation** (`git checkout --`).

**The trap, and it caught us:** both reference games open with long
non-interactive intros/attract sequences that *look exactly like gameplay* in a
screenshot. Clock Town and a Mumbo Jumbo conversation both read as "the game is
being played" and neither was. **A screenshot cannot distinguish autoplay from
interactive control.** To establish that a reference build is genuinely taking
input, you need an input→specific-response test: send a key with
`scripts/xtest_key.py`, at a screen where the expected response is unique and
gameplay-only (BK's save-file-select "PRESS A TO PLAY THE GAME" was the one
that worked — selecting an empty slot is unambiguously game logic, not a
`recompui` overlay action). Enter/Start is a **bad** choice: `GameInput::START`
and `GameInput::ACCEPT_MENU` share a default binding, so a response is
ambiguous between the game and the frontend.

---

## G6 — Cross-compare with ares

> [!CAUTION]
> **G6 IS CURRENTLY UNUSABLE — 2026-08-18.** ares stops executing as soon as gdb
> attaches, and keeps reporting readable RDRAM, so a poll returns a full,
> plausible, completely static set of samples. Measured: 43 polls over 86s, a
> 64-word block of thread 3's *active stack* unchanged in every one, `$pc` =
> `0xffffffff` throughout, and a `0xDEADBEEF` canary planted into a live
> function pointer surviving the whole run. **Every prior ares result is void**,
> including the one that attributed the attract-mode stack overflow to us rather
> than to the game. `scripts/ares_watch.sh` now prints an explicit
> `CONTROL FAILED` verdict instead of a clean-looking table. Fix the resume path
> before using this gate again — see `docs/boot-debugging-2026-08-13.md`,
> 2026-08-18.

**Valid for class A and C** — ares is hardware-accurate, so it's ground truth
for *what the real game does*. Use it to answer "what is supposed to happen
here?" and "does the real code path look like our generated code?"

**Invalid for class B** — ares doesn't run our runtime, so it cannot speak to
runtime-layer differences.

Installed user-level via Flatpak (`dev.ares.ares`). With a real GDB remote
serial protocol debug server:

```bash
flatpak run dev.ares.ares --setting DebugServer/Enabled=true \
    --setting DebugServer/Port=9123 --setting DebugServer/UseIPv4=true \
    --system "Nintendo 64" "rom/Tsumi to Batsu - Hoshi no Keishousha (Japan).z64"
```

Then `target remote localhost:9123`. gdb warns about the `mips:4000`
architecture string.

> **Correction (2026-08-14):** the memory note calling this warning
> "cosmetic" was wrong, or at least incomplete — it was true for whatever the
> prior session did (a raw register dump), but **breaks outright** for
> anything requiring gdb to decode the register set, including the very first
> `target remote` handshake in some cases: `Remote 'g' packet reply is too
> long (expected 312 bytes, got 568 bytes)`. Root cause: this machine's gdb
> (Ubuntu 15.1, x86_64 build) has **no MIPS architecture support compiled in
> at all** — `set architecture mips` and `set architecture mips:4000` both
> fail with `Undefined item`, not just "ignored." A gdb built without a MIPS
> target cannot reliably drive ares's remote-serial debug server for anything
> beyond what happens to work with the wrong register layout. Setting
> breakpoints, single-stepping, or reading registers is not safe to rely on
> until a MIPS-capable gdb (`gdb-multiarch`, or a cross-built gdb) is
> confirmed to be installed. **Don't sink time re-attempting this without
> that** — check `gdb -batch -ex "set architecture mips"` first; if it says
> `Undefined item`, this whole approach is blocked, not just noisy.
>
> **What still works without it:** ares's debug server accepts the connection
> and raw memory can likely still be read/written via `x`/`monitor` commands
> that don't require full register-set decoding (not yet confirmed — untested
> this pass, the failure happened at the initial handshake before reaching
> that). **What doesn't:** breakpoints, `bt`, single-step, anything needing
> live register state.
>
> **Cheaper substitute for a class-C "does real hardware respond to input at
> this point" question, no gdb needed:** launch ares normally (no debug
> server), let it reach the state in question, then send real input directly
> — a real keypress, or `scripts/xtest_key.py` for a scripted one — and
> compare screenshots before/after, the same recipe already validated against
> BanjoRecomp in G5. This answers the input-timing question directly without
> needing to see *which* function fired, just *whether* the game responded.
> Slightly weaker evidence (behavioural, not call-level) but immediately
> available. **Validated 2026-08-14** against ares directly: reset via
> `Nintendo 64 > Reset`, pressed Start seconds later (nowhere near a natural
> attract-loop cycle boundary, to avoid the exact confound `EV` warns about),
> got an unambiguous real-hardware answer — see the session log's "does Start
> work at all" entry.
>
> **One sub-pitfall found doing this:** `xtest.fake_input` clicks land
> reliably on the main game-render window but **not** on ares's native Qt
> dropdown menus (`Settings`, `Nintendo 64`, …) — a computed-correct click on
> "Input..." only produced a hover-highlight on the wrong item, never opened
> it. Likely an override-redirect/popup reparenting difference from the
> top-level window. Don't burn time iterating on menu coordinates — ask the
> user to drive that one interaction directly (this is exactly the
> "physical interaction we can't reliably automate" case in `EV`'s ask-the-
> user list) and resume once done. `scripts/xtest_key.py`/`xclick.py`-style
> direct key/click against the *game window itself* remains reliable.

**What it's good for, concretely:**
- Confirming the target state is real and reachable (it boots to attract mode
  in seconds — that's how we know "reach the title screen" isn't a slow edge
  case).
- Instruction traces (we captured an 8M-instruction trace this way) to see
  which path the real game takes through a function.
- Confirming a generated function's body against real execution — the
  detection method for BC-2.
- Visual ground truth for "is this graphical glitch ours or the game's?"

No rebuild cycle and no `ptrace_scope` problems. Underused relative to how
useful it is.

---

## G7 — Live debugging (gdb on our build)

> **BEFORE WRITING ANY CONDITION, READ `docs/instrument-semantics.md` (T108).**
> It is the premise list this gate's failures came from: `ctx` is one struct per
> THREAD (not per frame), a breakpoint fires BEFORE its line, reach counts scale
> with the arm window and must never be compared across windows, and a zero is
> meaningless without a healthy reach counter. Two multi-roll dead ends (A166's
> sp-pairing, A157's two-writer premise) die at birth against that table.

Most expensive gate. Real time cost, and it distorts the thing you're
measuring. Everything above should be exhausted first.

**Concrete escalation threshold, not just "exhausted":** if a live regression
(hang or crash, not a build error) survives **two** static-hypothesis-then-
rebuild-and-test cycles with no crash signature to chase, stop generating a
third hypothesis and come here instead. Two real attempts at the SI-manager
dispatch-thread investigation each looked well-evidenced from static reading
alone (one byte-verified against raw ROM data) and both produced a silent
hang with nothing in the log to narrow it further — static tracing had run
out of leverage on its own; a `thread apply all bt` would answer in minutes
what a third round of reading would have kept guessing at. **A silent hang
with no error text is the specific signature that should trigger this** —
static analysis is strong at explaining *why* code takes a path, but has
nothing to say about *where two threads are stuck relative to each other*
once neither is producing output.

**Pitfalls, all hit for real:**

- **`ptrace_scope=1` blocks attaching** to a running process. Launch the target
  as gdb's own child: `gdb -batch -ex run --args ./build/SinPunishmentRecompiled`.
- **gdb slows wall-clock 10–20×.** A bug that reproduces in ~20s bare can take
  minutes. Budget for it, or capture differently.
- **`pkill` returning 1 aborts chained commands** in this shell. Check with
  `ps`/`pgrep` and kill by explicit PID.
- **Name collisions with typedefs**: `break get_function` resolved to a *type*
  ("Attempt to use a type name as an expression"). Work around with a raw
  address: `nm` static offset + the ASLR slide (gdb disables ASLR for its own
  children, so compute the slide from a known runtime address like `main`),
  then `break *0x<runtime_addr>`.
- **Missing debug info for a TU**: `break overlays.cpp:367` → "No source file
  named overlays.cpp". Same raw-address workaround.
- **Breaking at a function's first instruction is pre-prologue** — parameters
  aren't spilled yet, so `p addr` fails. Read the calling-convention register
  directly (`$edi` = first `int` arg, SysV ABI).
- **STL evaluation in breakpoint conditions is unreliable** (`func_map.find(...)`
  errors or needs symbols not yet loaded). Condition on plain register
  comparisons instead: `$edi == 0x3dc7ca55`.
- **`MEM_W(offset, reg)` needs a sign-extended 64-bit address**, not a plain
  literal: `0xFFFFFFFF80068A9C`, not `0x80068A9C`. Passing the short form
  lands ~4GB off. This cost a full investigation pass.
- **A `fprintf`/`stderr` scratch hook needs `#include <stdio.h>` prepended to
  the generated `funcs_N.c` file(s) it lands in, and this does not survive**
  `recompile.sh` **-- it regenerates `RecompiledFuncs/` from scratch every
  time.** Reapply after every recompile, before `cmake --build`:
  `grep -rl '\[probe\]' RecompiledFuncs/*.c | xargs -I{} sed -i '1i #include <stdio.h>' {}`
  (adjust the grep marker to whatever tag the scratch hooks use). Hit twice
  in one session from forgetting this after a toml-triggered regenerate.
- **RecompFrontend's quit-confirmation modal** eats `SIGTERM` — `timeout` won't
  kill a running build cleanly, it just blocks on a dialog. Kill by PID.
- **Kill leftover processes when done.** Check:
  `ps aux | grep -iE "sinpunishmentrecompiled|zelda64recompiled|banjorecompiled|ares|gdb" | grep -v grep`
- **External `kill -INT <gdb-pid>` to stop a long `run` doesn't reliably work
  when gdb was launched non-interactively/backgrounded** (no controlling tty —
  e.g. launched via this tool's background-execution support rather than a
  real terminal). Confirmed twice: the signal either killed gdb outright or
  was silently swallowed, with no `thread apply all bt` output either way.
  **Fix: self-interrupt from inside the gdb script**, so no external signal
  timing/tty dependency exists at all — spawn a real OS thread that sleeps in
  wall-clock time, then posts a gdb event:
  ```
  python
  import threading, gdb, time
  def interrupter():
      time.sleep(70)
      gdb.post_event(lambda: gdb.execute("interrupt"))
  threading.Thread(target=interrupter, daemon=True).start()
  end
  run
  thread apply all bt 8
  quit
  ```
  This worked cleanly on the first try once switched to. `gdb.execute("interrupt")`
  behaves exactly like the old working `kill -INT` did in earlier sessions
  (same underlying mechanism, just triggered from inside gdb's own event loop
  instead of an external signal), so this should be the default approach going
  forward rather than something to fall back to after `kill -INT` fails.
- **`timeout N ./build/...` is not guaranteed to actually kill the process
  after N seconds** when launched through this tool's backgrounded execution
  -- confirmed twice: two `timeout 20` runs were both still alive (~1h45m
  elapsed) when checked much later, needing an explicit `kill -9`. Not
  root-caused (possibly SIGTERM being swallowed with no controlling
  terminal). Treat `timeout` as advisory here, not a guarantee -- always
  `pgrep`/kill explicitly before ending a session rather than trusting it
  alone.
- **This tool's background-execution (`run_in_background: true`) does not
  persist `cd`** — each backgrounded command starts back at the default
  working directory, even though foreground commands in the same session do
  chain a persisted cwd. `cd` explicitly (or use absolute paths) at the start
  of every backgrounded command that touches this repo; a bare `./build/...`
  path silently resolved against the wrong directory and produced a confusing
  "No such file or directory" from gdb itself, not from the shell.
- **`boot_screen_check.sh`'s minimize step is inside that script** — a manual
  `gdb --args ./build/SinPunishmentRecompiled` launch (for a thread-state
  check, not a screenshot check) does not get the auto-minimize behavior for
  free. If isolation from the user's desktop still matters for this run, call
  `scripts/minimize_window.py` manually (via the `decomp-venv` Python, passing
  the real content window's hex ID from `xwininfo`, not the class name) after
  waiting for the first real frame — same sequencing rule as the script's own
  8s delay. Caught live by the user noticing the window hadn't minimized.

---

### G7.1 — `rr`: TRIED, DOES NOT WORK ON THIS TARGET (2026-08-19)

**Do not spend time on this.** `rr` was installed, the sysctl was set, a wrapper
was written, and it was measured. It cannot record this program. Recorded here
so the idea is not re-proposed — it is an attractive one.

**Blocker 1 — rr aborts on ioctls it does not model.** The first was SDL's HID
gamepad probe (`HIDIOCGVERSION`, type `'H'` nr 1), which *is* disableable with
`SDL_JOYSTICK_HIDAPI=0`. Past that it hits
**`DMA_BUF_IOCTL_EXPORT_SYNC_FILE`** (`0xc0086202`, type `'b'` nr 2) from the
Vulkan/RT64 path, which is not disableable without giving up the renderer.

**Blocker 2, and it is independent — the timing dies anyway.** `rr` serialises
threads onto one core. Measured gfx rate under recording: **`+0`/`+1`** against
a normal **`+30`** (T60). The 158s crash is timing-anchored, so even a working
recording could not reach it.

**Each attempt also raises an Ubuntu apport crash dialog on the user's desktop.**
`scripts/rr_record.sh` therefore **refuses by default** and prints why;
`SNP_RR_FORCE=1` overrides, which is worth doing after an `rr` upgrade and not
otherwise.

**What to use instead:** `scripts/gdb_watch.sh` with a value condition. It found
A99's writer in one run — see the Scripts table for the arming control, which is
the part people get wrong.

**Note `rr check` is not a subcommand** in rr 5.7 (`rr help` lists the real
ones); it fails with `execve failed: 'check'`. The prerequisite it would have
reported is `kernel.perf_event_paranoid <= 1`, which is now set on this machine.


### G7.2 — Snapshot RDRAM at the fault, then ask questions offline (added 2026-08-19)

**Take a snapshot on every fault run. It costs 8 MB and it makes the crash
re-interrogable.** The reason to bother: a run to the A99 fault costs ~158s and
yields one fixed set of values, so every new question is another run. On
2026-08-19 `gdb_fault.sh` was run twice against the same crash purely because
the first pass used the release binary and `ctx` would not resolve (A122).

```bash
SNP_RDRAM_DUMP=/media/joh/extra/sin-punishment-archive/evidence/<date>/<name>.rdram \
  scripts/gdb_fault.sh 320 /tmp/fault.log build-debug/SinPunishmentRecompiled

scripts/rdram_peek.py <snap> 0x8013C278           # one word
scripts/rdram_peek.py <snap> 0x802E1680 20        # 20 words
scripts/rdram_peek.py <snap> --stride 0x14 0x802E1680 8
scripts/rdram_peek.py <snap> --regs               # register file at the fault
scripts/rdram_peek.py --self-check                # ALWAYS, before believing output
```

**NOT a core file.** `SNP_CORE` exists but a core of this process is **11.8 GB**
— librecomp reserves 4 GB and commits 512 MB (`addresses.hpp`) — and enabling
system-wide cores would fill the root filesystem in about three crashes (T63).
The snapshot is 8.4 MB because every address this project has ever examined
lives in the first few MB of RDRAM. Keep as many as you like.

**RUN `--self-check` BEFORE TRUSTING ANY READ.** This is not ceremony. The first
version of `rdram_peek.py` read words big-endian and printed clean, plausible,
**byte-reversed** values — `0x8013C278` as `0x00000002`, A110's child pointers as
`34162E80` instead of `802E1634` (T64). RDRAM is stored in HOST word order,
which is the same fact that makes byte access need `^3` (I7). Endianness is not
eyeballable here: most of these words look like plausible data either way round.
The self-check asserts values measured by other means, and it discriminates —
4/4 pass when correct, **0/4 pass under the original bug**.

**What it is good for, with a worked example.** Diffing a snapshot against the
ROM image found **A126** — every typed scene node is rebased `+0x1B` at load,
while `0xFFFF` sentinels are untouched — which corrected A111's type analysis.
Nobody had asked that question; asking it cost nothing because the crash state
was already on disk. **Static data and runtime data are different things, and a
snapshot is how you tell them apart** (G3.1 is the overlay-copy version of the
same trap).

**WHAT A SNAPSHOT CANNOT DO: reconstruct a call chain (T69).** Memory above the
outermost live frame holds whatever an earlier, deeper call left there, and
leftovers of a recursive function are indistinguishable from live frames of it —
same layout, same plausible pointers, same arithmetic relationships. This stack
produced **four** self-consistent, mutually incompatible readings (A125, A128,
A130, A132); three are withdrawn.

**So: use a stack image to generate candidates and to REFUTE** — a value outside
an arithmetic bound is a genuine refutation, which is how A125 fell — **never to
establish a chain. Establish chains by logging entry arguments at runtime**,
where each record is one real invocation and a leftover cannot appear.

**Preserve snapshots to the archive drive, not `/tmp`** — evidence cited from
session-scoped paths does not survive (T47).


## THE IMPOSSIBLE-RESULT RULE — a contradiction is a premise audit, not a new experiment (added 2026-08-20, T107)

**The single most expensive failure this project has recorded.** A99's third
circle cost roughly **15 rolls**, and every experiment inside it was
well-controlled: positive controls on conditions, exact-value pairing,
whole-run arming, thread logging. The discipline was flawless and it was
pointed at the wrong thing.

At roll #84, A157 concluded *"these three measurements cannot all be right."*
That was the correct instinct attached to the wrong object: it went on to
dismiss a **measurement** (A141) while leaving its own **premise** — "the
walker writes `$s0` in exactly two places" — unexamined. Six further
experiments then ran *under* that premise, each honestly excluding another
possibility *within* it. The premise was finally checked at roll #103 and fell
in two greps: the count had been taken inside ONE function, while `ctx` is one
struct per THREAD and **9,199 write sites exist**.

> **THE RULE. When a checkpoint concludes that measurements are mutually
> impossible — or uses the words paradox, contradiction, cannot all be right —
> the NEXT checkpoint on that item MUST enumerate the premises under the
> contradiction and attack the LEAST-VERIFIED one. It may not run another
> experiment under them.**

Enumerating premises is cheap and static almost every time. The two greps that
broke circle 3 cost seconds; the six experiments that preceded them cost rolls
and runs each.

**How to enumerate.** Write the contradiction as *"A and B and C cannot all
hold."* Then list, for each term, what makes it true — including the things so
obvious they were never written down. Those are the candidates. In circle 3 the
unwritten one was *"`$s0` belongs to this function"*, which is false for a
shared per-thread context.

**Smell tests that this rule is being violated:**

* the word "paradox" appears and the next action is a trace
* an experiment is designed to distinguish two options *inside* a frame that
  has never itself been tested
* a **measured** result is being explained away rather than a premise being
  checked (see the dismissal bar below)
* the excluded-possibilities list is growing while the question is unchanged

**Its own falsifier:** a recorded case where running one more experiment under
the premise was cheaper than enumerating the premises. None exists yet.

---

### The dismissal bar — overturning a measurement needs a measurement (added 2026-08-20, T107)

**A141 was dismissed twice on plausibility arguments and vindicated twice by
measurement.** A157 called its reach count "impossible" by comparing it against
a count taken over a **different arm window** (A173 later showed the error), and
the second dismissal rested on the same premise circle 3 was built on. At
209,649 reaches, A180 confirmed A141's original negative exactly.

> **A MEASURED entry may be FLAGGED by an argument, but may only be
> OVERTURNED by evidence at the same standard — same-run or same-window
> measurement, or a static proof.** A plausibility argument raises a question;
> it does not answer one.

The asymmetry to watch for: making a claim here requires controls, repeats and
a stated scope. Dismissing one has historically required only a confident
sentence. **That gap is the defect** — it lets the cheapest possible evidence
overturn the most expensive.

---

## EV — The evidence gate (applies to every observation, at every gate)

This is the generalised form of "is this screenshot definitely what I want to
see?" — and it's the gate that has failed most often. Both failures were at the
*interpretation* step, not the tool-choice step, which is exactly why it's a
gate that runs continuously rather than a step in the sequence.

Before recording any conclusion, answer all five:

1. **Is this observation or inference?** Did I *see* the thing, or did I see
   something consistent with it? "The screen shows Clock Town" is an
   observation. "The game is being played" is an inference.

   > **A scalar verdict from a script is an inference, not an observation —
   > even when the script sounds authoritative** (`RESULT: NOT BLACK`).
   > `boot_screen_check.sh` once returned `dark_fraction=0.954` for a frame
   > that was, on actual inspection, **completely black** — the 0.98 cutoff
   > called it "not black" and that verdict was accepted without opening the
   > PNG, reasoning the borderline number away instead. This rule already
   > existed when that happened; it didn't fire, because "the script's
   > verdict" didn't *feel* like an inference in the moment. **The concrete
   > fix**: any tool that reduces a visual/state check to a single number
   > needs three bands, not two — confidently-one-way, confidently-the-
   > other-way, and an explicit **ambiguous middle band that refuses to
   > render a verdict** and instead says "go look directly." Don't rely on
   > remembering to be suspicious of a borderline number; make the tool
   > incapable of quietly picking a side near its own threshold.
   > `boot_screen_check.sh` now does this (`>0.995` black, `<0.85` not-black,
   > `0.85–0.995` forces a direct look) — apply the same three-band pattern
   > to any future automated pass/fail check in this project.
2. **What's the control?** What does the same observation look like when the
   thing I'm testing *doesn't* happen? Without a do-nothing baseline, a change
   over time proves nothing — attract-mode footage changes on its own.

   > **The inverse trap is just as real: *no* change across different
   > durations is itself a signal, not a null result.** Three
   > `boot_screen_check.sh` runs at 20s/30s/40s once returned the identical
   > `dark_fraction` to many decimal places — a live, healthy attract loop
   > should never produce byte-identical frames across different wait times.
   > That exact repetition was the tell that something other than the game
   > state was being measured (it turned out to be a tooling bug capturing
   > the wrong window every time, not a frozen game). If repeated
   > measurements of something that should be *varying* come back identical,
   > suspect the measurement, not the game.
   >
   > **Also check you captured the thing you meant to, not just that you
   > looked at it.** Viewing a screenshot satisfies rule 1 (observation over
   > inference) but not this rule if the screenshot itself is of the wrong
   > object — `boot_screen_check.sh`'s window-selection matched both the
   > actual game window and the WM's own decoration frame (identical title
   > text on both), and silently picked whichever `xwininfo` listed first.
   > Cheap sanity check: does the captured image's reported size match the
   > expected content resolution? A frame capture came back a different
   > size than the real content window every time — that would have caught
   > it immediately if checked.
   >
   > **A stopped machine answers every question with "no."** The ares
   > comparison ran 43 polls over 86s and reported the watched word unchanged
   > at every one — a clean, plausible, entirely static table produced by an
   > emulator that gdb had halted on attach. It read memory happily the whole
   > time, which is exactly what made it convincing. The conclusion drawn from
   > it ("hardware never writes this address, so the overflow is ours")
   > survived into a handoff as established fact. **The control costs one
   > extra read per poll**: sample something that MUST change if the system is
   > alive — an active thread stack, a frame counter — and let the tool refuse
   > to report at all when it doesn't. `ares_watch.sh` now does this and
   > prints `CONTROL FAILED — this run proves NOTHING`. Note this rule already
   > existed, and the run that voided §11 of the drain-gap doc for exactly
   > this reason was itself uncontrolled. **Writing the rule down is not
   > applying it**; the durable fix is putting the control inside the tool, so
   > it cannot be skipped in the moment.
3. **Is there a second explanation that fits equally well?** If yes, the test
   is ambiguous and needs redesigning, not interpreting harder. (Enter
   advancing a cutscene: real N64 input, *or* a frontend menu-layer intercept.
   Both fit. Bad test.)
4. **Am I about to use the words "conclusive", "confirms", or "clearly"?** If
   so, re-check 1–3. Both overclaims this project has produced used exactly
   that framing.
5. **Would the user, looking at this, see what I claim to see?** If there's any
   chance they'd say "that's not what that is" — **show them and ask.** They
   have game-specific knowledge that isn't in any file here.
6. **Re-derive, don't restate.** Before building anything on a claim — your
   own or one already written in these docs — go back to the *raw* evidence
   and derive it again from scratch. Restating a prior conclusion is not
   evidence for it, no matter how many times it has been repeated or how
   confidently it was written down.

   > This is the gate that catches compounding errors, which are the
   > expensive kind. On 2026-08-15 a session read `beq $s0, $zero, L_8004C59C`
   > as "zero skips the input path" (it means the opposite), changed
   > `osContStartReadData` to match, and when that crashed, explained the
   > crash with a *new* theory instead of re-reading the branch. Three
   > further entries were written on top of the inverted premise. One
   > re-derivation at any point would have ended it.
   >
   > **The mechanism matters: ask the question in a form that cannot be
   > answered from memory.** Not "is the branch inverted?" (answerable by
   > restating), but "paste the branch instruction and say what zero vs.
   > nonzero each do." Not "is the callback slot ever written?" but "show
   > every encoding that can address it, and every store found." Force the
   > answer to come from a fresh tool call against the artifact — the
   > disassembly, the ROM bytes, a live run — not from the conversation.
   >
   > **This applies hardest to your own claims from earlier in the same
   > session**, where there's no "someone else wrote this" cue to prompt
   > suspicion. Same session, an hour after the above was diagnosed: the
   > reviewing model asserted that `0x800657B0` was "a local in
   > `boot_func_80025CA4`'s stack frame" from a plausible-sounding reading of
   > `osCreateThread`'s stack-pointer argument. Re-deriving with arithmetic
   > (frame = `0x80065790..0x800657AF`, slot = `0x800657B0`) showed it lands
   > one word *past* the frame — a global adjacent to the stack array, not a
   > local. The correct earlier conclusion had nearly been discarded on the
   > strength of a confident retelling. **Cheap, decisive habit: make the
   > machine do the arithmetic and print the comparison, rather than
   > eyeballing whether two hex numbers "look like" they overlap.**

7. **Measure rates, not samples — a backtrace cannot tell you whether a thread
   is stuck.** A thread that blocks and wakes 30 times a second is *blocked*
   in almost every sample you take of it. "Blocked in a thread dump" and "stuck"
   are different claims and only a counter over time separates them.

   > On 2026-08-17 this cost four consecutive fix designs. A gdb dump showed
   > two threads blocked on message queues, which was written down as a
   > deadlock; an entire design document
   > (`docs/design-drain-gap-fix.md`, now obsolete) was built on it. A
   > per-queue rate counter showed both threads cycling at a clean 30Hz
   > straight through the "freeze", with zero messages dropped — and audio RSP
   > tasks continuing at +30/sec indefinitely. The game was never stuck. It was
   > running at full speed and rendering nothing.
   >
   > Corollary, equally expensive: **a negative-path probe proves nothing about
   > the positive path.** The same investigation observed that its
   > declined-handoff probe never named thread 19 and concluded thread 19 was
   > never scheduled. Absence from a *decline* list meant its handoffs were
   > being *accepted*. Before reading meaning into what a probe doesn't show,
   > state explicitly what the probe would print in each case.
   >
   > **Default instrument for "is X still happening?" is a counter incremented
   > at X and printed once per second by an independent thread.** It costs
   > almost nothing, it keeps reporting after the subsystem under test goes
   > quiet, and it answers stuck-vs-slow-vs-idle in one run. `SNP_HEARTBEAT`
   > and `SNP_VI_PROBE` are the working examples.

### When to ask the user rather than push on

- **Any judgement about whether on-screen behaviour is correct for this game.**
  They know what Sin & Punishment is supposed to do; the repo doesn't.
- Distinguishing a graphical glitch from intended art.
- Whether a state transition was real progression or scripted/demo behaviour.
- Anything requiring physical interaction we can't reliably automate (though
  `scripts/xtest_key.py` now covers most of this).
- Before any commit/push — the standing constraint is **nothing proprietary**:
  no ROM data, no binaries, no copyrighted game content. Original code and
  factual metadata (addresses, sizes, short technical descriptions) only.
  Review the actual diff every time, not just the file list.

### Recording a corrected claim

When a conclusion turns out wrong, **don't quietly overwrite it.** Record the
original claim, the correction, and *why the original evidence was
insufficient* — in the session log, and if the reason generalises, as a new
item in this gate. The corrections are more valuable than the conclusions;
they're what stops the same mistake recurring under a different topic.

---

## Fix protocol

1. **Apply** — prefer a `[[patches.hook]]` in `sinpunishment.toml` (or a symbol
   fix in `symbols/sinpunishment.syms.toml`) over touching submodules. If a
   submodule change is genuinely needed, it must become a tracked patch file
   under `patches/upstream/` or it will be silently lost on a fresh clone.
2. **Match the existing control flow** — when skipping a bad value, jump where
   the code's own "not ready" path already goes. Don't invent new behaviour.
   **When the fix substitutes one `ultramodern` scheduling primitive for
   another (e.g. a yield, a wait, a hand-off), read both primitives' actual
   implementations first — don't assume from name similarity.** Two
   primitives that sound interchangeable can have meaningfully different
   guarantees: `yield_self_1ms()`'s `check_running_queue()` only hands off to
   a *higher-priority* thread, while the real blocking `osRecvMesg` path's
   `run_next_thread_and_wait()` hands off *unconditionally*. A fix that
   swapped the former in for the latter (2026-08-15, the gfx-task-stall
   investigation) produced a real, confirmed regression — zero progress
   instead of partial progress — because it silently changed a guaranteed
   hand-off into a priority-gated one. Cross-referencing a cooperative
   scheduler's threading primitives against each other's real implementation
   before composing a fix from them is exactly as necessary as any other
   "read before assuming" gate in this document.
   **Before scoping a fix to one call site, confirm that call site is
   actually reached at the failure point — don't infer it from the symptom's
   shape.** A fix at `run_next_thread`'s empty-queue branch (2026-08-15, a
   later pass of the same gfx-task-stall investigation) built clean and ran
   with no crash or regression, but a counter added to the new code path
   never fired once, including at confirmed full quiescence — the branch
   was dead code for this deadlock the whole time, because a *different*,
   equally common parking path (`resume_thread_and_wait` via
   `swap_to_thread`'s priority-preemption branch) reaches
   `wait_for_resumed()` directly, bypassing the patched function entirely.
   A cooperative scheduler with several distinct hand-off primitives can
   have several distinct parking paths that all *look* like the same
   symptom from the outside; find the one true shared choke point (here,
   `wait_for_resumed()` itself, not `run_next_thread()`) before scoping a
   fix, ideally by instrumenting the fix's own entry point and confirming
   it fires, not by reasoning alone.
   **Relatedly: an unsynchronized cooperative scheduler's "only one thread
   is ever actively executing" invariant is itself an implicit lock.** Any
   fix that lets a *parked* thread act (e.g. a timed wait with a fallback
   drain) without being explicitly resumed breaks that invariant on
   purpose, and needs an explicit replacement (real mutual exclusion) if
   more than one parked thread could plausibly do this at once — otherwise
   it reintroduces the same class of race that crashed the very first
   scoped-fix attempt at this bug (draining directly from the VI thread).
   Recognizing "this invariant is standing in for a lock" before writing
   the fix is cheaper than discovering it via a fresh crash.
3. **Verify against the original repro numbers** — same command, same duration,
   compare against the exact figures from G0.
4. **Check for regression** — `SP_AUTOSTART=1` + `boot_screen_check.sh`, still
   clearing the previously-established stability checkpoint.
5. **Strip scratch hooks** — `scripts/strip_scratch_hooks.sh`, and revert
   submodule instrumentation by hand.
6. **Record** — session log entry, and a new instance under the relevant bug
   class in G2. If the class is new, write the class.

---

## Update protocol

This file only stays useful if it's maintained during work, not after it.

**Trigger points — update at the moment these happen, not at session end:**

- A bug is root-caused → add the instance to its G2 class, or write a new class.
- A tool is built or a hook discovered → add it to G3.
- A gdb/environment pitfall is hit → add it to G7.
- A conclusion is corrected → add to EV if the *reason* generalises.
- A comparison target proves valid/invalid for a class of question → fix the
  routing table in G1.

**The promotion rule** — the thing that decides where a finding goes:

> If knowing it earlier would have changed **which gate you went to**, it
> belongs in **this file**. If it only changes **what you found there**, it
> belongs in the **session log**.

Examples: "the bad pointer was `0x3DC7CA55`" → session log. "Arbitrary values
next to an existing `== 0` guard mean BC-1, skip root-causing" → this file, it
changes the route. "MM/BK can't answer game-logic questions" → this file, G1.

**Where in this file it goes** — depends on the *nature* of the finding, and
one of the three cases lands in two places at once:

| Nature | Goes in the gate | Goes in the changelog | Why |
|---|---|---|---|
| **Instance** — another example of something already catalogued (a 7th BC-1 site, another gdb pitfall of a known kind) | **yes** — append to that gate's list | no | The map is already right; it just needs the example. A changelog entry per instance is churn that buries the entries that matter. |
| **Extension** — a genuinely new class, tool, gate, or pitfall | **yes** — write it where it belongs | **yes**, one line | The map gains a region. The changelog records when we learned it existed. |
| **Correction** — an existing gate is *wrong* or actively misleading | **yes** — amend in place, so the map reads true | **yes**, with the old rule quoted and the evidence that overturned it | **Both, always.** This is the case the file would otherwise lose. |

**Corrections are the case that justifies having a bottom section at all.**
Amending a gate in place is necessary — a map with two contradictory regions is
worse than one with a gap, and anyone following the tree must hit the corrected
rule, not the old one. But in-place amendment *destroys the evidence that the
rule was ever wrong*, which is precisely what `EV` says not to do. The changelog
is where that survives: what the gate used to say, what observation broke it,
and therefore what class of reasoning to distrust next time. Without it this
file silently converges on looking like it was always right, which is the exact
failure mode it exists to prevent.

If the old rule was one we actively acted on for a while, also leave a one-line
`superseded:` note at the gate itself — someone may have internalised it and
needs to see it was withdrawn, not just quietly differ from what they remember.

**Cross-gate propagation:** a correction rarely touches one gate. A pitfall
added to G7 that also invalidates a G5 procedure needs fixing in both, with one
changelog entry covering the pair.

**Cross-file:** anything that should survive into a *fresh session with no
context* (tool paths, environment setup, current status, standing constraints)
also goes in the `sin_punishment_recomp_status` memory. This file assumes the
repo is in front of you; the memory doesn't.

---

## Changelog

Entry format: **extensions** get one line. **Corrections** quote the rule they
replace and name the evidence that overturned it — that's the part with lasting
value, and it's the reason this section isn't just a version number.

- **2026-08-14** — *Extension.* Added a rule for reverting multi-file changes:
  revert and verify every file together, not one at a time — a partial revert
  (toml reverted, Python post-processor and C++ addition left on the new
  version) produced a third, untested, broken combination that looked exactly
  like a real regression. Caught by the user watching directly, not by tooling.
- **2026-08-14** — *Extension.* Added `known_good_builds/` (gitignored cached
  binaries + matching toml) for fast before/after comparison without a full
  rebuild cycle each time.

- **2026-08-14** — *Correction, effectively to G3's entire screenshot-based
  verification approach.* Implicitly treated "the correct window, captured
  via `xwd`, shows black" as reliable evidence of a broken build. It isn't,
  on this Wayland machine: `xwd` can report solid black for a window that's
  genuinely rendering (Vulkan swapchain presentation doesn't reliably update
  the legacy X11 backing store `xwd` reads under XWayland). Overturned when
  `nvidia-smi` showed the process actively rendering while every screenshot
  said black, and the user's direct look at their screen confirmed it was
  fine. New standing rule added after the tooling table: get a non-visual
  signal (ask the user, a stderr probe, or G7) before trusting a black
  screenshot as evidence of anything.

- **2026-08-14** — *Correction, to G3's `boot_screen_check.sh` entry.* The
  window-selection matched both the real game window and the WM's own
  decoration frame (same title text on both) and silently picked whichever
  `xwininfo` listed first — not always the content window. Overturned by
  three suspiciously identical readings across different wait durations,
  traced to the script capturing the frame instead of the game. Fixed to
  require WM_CLASS `SinPunishmentRecompiled` and exclude `mutter`; the
  result's `size=` field is now a cheap sanity check (`(1280, 720)` = real
  content, anything else = wrong window).
- **2026-08-14** — *Extension, to EV rule 2.* Identical readings across
  different wait durations is itself a signal to distrust the measurement,
  not evidence of a stable state — the exact case that surfaced the
  `boot_screen_check.sh` bug above. Also added: check the captured
  artifact's basic metadata (image size, etc.) matches what's expected,
  since "I looked at the screenshot" doesn't help if the screenshot itself
  is of the wrong thing.
- **2026-08-14** — *Extension, to G4's indirect-calls recipe.* Static
  tracing cannot resolve a `LOOKUP_FUNC(ctx->rN)(...)` call's actual target
  — a whole call chain was invisible to every grep-based search this project
  ran and only appeared in a live gdb backtrace. Noted as a hard ceiling on
  G4, not just a gap to search harder for.

- **2026-08-14** — *Extension.* Added a concrete escalation threshold to G7:
  two static-hypothesis-then-rebuild cycles producing a silent hang with no
  crash signature is the trigger to stop guessing and go to live gdb, rather
  than "everything above exhausted" staying a vague judgment call. Based on
  the SI-manager dispatch-thread investigation, where two well-evidenced
  fixes (one byte-verified) both produced an unexplained hang.

- **2026-08-14** — *Correction, to EV rule 1.* The rule ("is this observation
  or inference") already existed and still didn't prevent accepting
  `boot_screen_check.sh`'s `dark_fraction=0.954` → "NOT BLACK" verdict at
  face value for a frame that was actually completely black — a real
  regression from un-stubbing `boot_func_8004EAD0`/`8004EA68`. The user
  caught it, not the gate. The rule wasn't wrong, but it was too abstract to
  fire under time pressure: "a script's verdict is an inference" doesn't
  *feel* like the same category of risk as "I'm inferring from a
  screenshot." Added a concrete, mechanical fix instead of relying on
  remembering to be suspicious: any scalar pass/fail tool needs a middle
  band that refuses to render a verdict and forces direct inspection.
  `boot_screen_check.sh` updated accordingly (`>0.995`/`<0.85`/ambiguous
  band in between). Apply the same three-band pattern to any future
  automated check in this project — this generalises past this one script.

- **2026-08-14** — *Extension.* Added a "tracing indirect calls" recipe to
  G4: search raw ROM bytes for a function-pointer table when a function has
  no C-level caller, then convert ROM offset to VRAM using the segment
  table's documented mapping (not by back-computing from a matched
  instruction sequence — a first attempt at the latter picked a non-unique
  3-instruction prologue and silently produced a wrong address). Found while
  localizing why our build's controller-poll functions are never invoked.
- **2026-08-14** — *Extension.* Added a stdio-include gotcha to the scratch-
  hooks note in G3: `fprintf`/`stderr` scratch hooks need `#include <stdio.h>`
  added by hand to the affected generated file, since `ensure_stdio.py` only
  auto-adds it for files tagged with the older `"[flag]"` convention.

- **2026-08-14** — *Extension.* Added `scripts/xclick.py` (arbitrary-point
  X11 click via XTEST) to G3's tooling table, plus a G6 sub-pitfall: it's
  reliable against top-level SDL/game-render windows but not against native
  Qt dropdown menus, which silently produce hover-only misses instead of
  errors. Found while trying to click into ares' Settings menu; resolved by
  asking the user to drive that one interaction directly.
- **2026-08-14** — *Correction, to G6.* Previously implied the `mips:4000`
  gdb-remote warning against ares is cosmetic. It isn't: this machine's gdb
  has no MIPS architecture support compiled in at all (`set architecture mips`
  → `Undefined item`, not a warning), which broke the `target remote` register
  handshake outright before any breakpoint could be set. Overturned by
  actually trying to set a breakpoint on `osContGetReadData` during the
  attract-mode-input investigation, rather than trusting the earlier session's
  "raw protocol still works" note, which was true only for what that session
  happened to do with it. Corrected in place at G6 with a substitute
  (real/scripted input against a normally-launched ares, no debug server) that
  doesn't need a MIPS-capable gdb.

- **2026-08-14** — *Correction, to the update protocol itself.* It previously
  read: *"when something generalises, don't only append it at the bottom — go
  back and amend the gates it affects."* That framing treated the changelog as
  the lesser destination and in-place amendment as the real work — which
  directly contradicts `EV`'s "don't quietly overwrite a wrong conclusion,"
  since amending a gate in place erases the fact that it was ever wrong.
  Overturned by the user pointing out that findings should land top *and*
  bottom depending on their nature. Replaced with the three-way
  instance/extension/correction table: only corrections are dual-homed, and
  they are dual-homed *always*. Generalises beyond this file — an
  append-only rationale trail is what stops any accumulating document from
  converging on looking like it was always right.
- **2026-08-14** — Created. Seeded from 25 passes of the boot-debugging session
  log: four bug classes (BC-1…BC-4), the class-routing table, the G5/G6 validity
  split, the gdb pitfall list, and the evidence gate (written directly from the
  two overclaim corrections that occurred in that session). Persisted
  `scripts/xtest_key.py` out of session scratch so G3/G5 can rely on it.
- **2026-08-14** — *Extension, to G7's pitfall list.* Three new gotchas from a
  fresh-session gdb thread-state check: external `kill -INT` to a
  non-interactively-launched gdb doesn't reliably stop `run` (use a
  self-interrupting Python thread inside the gdb script instead — worked
  first try); this tool's `run_in_background` doesn't persist `cd` the way
  foreground commands in the same session do; and a manual gdb launch skips
  `boot_screen_check.sh`'s auto-minimize, so isolation has to be called
  explicitly if it still matters (caught live by the user noticing the window
  hadn't minimized).
- **2026-08-15** — *Extension, to the Fix protocol.* A scoped fix for the
  gfx-task-submission stall substituted `yield_self_1ms()` for the real
  blocking recv's `run_next_thread_and_wait()` and produced a confirmed
  regression (zero progress instead of partial) — the two primitives sound
  interchangeable but have different thread-hand-off guarantees (priority-
  gated vs. unconditional). Added a rule to the Fix protocol: read a
  cooperative scheduler's actual primitive implementations before composing
  a fix from them, not just their names. Also worth recording here since it
  isn't a gate extension on its own: two independent scoped-fix attempts at
  this same stall (this one, and an earlier direct-drain-from-the-VI-thread
  attempt that segfaulted) both failed for reasons specific to
  `ultramodern`'s cooperative-scheduler internals, not the game code —
  suggesting the eventual real fix belongs at the runtime-synchronization
  level rather than as a single game-specific hook, at least for this
  particular class of gap (see `docs/boot-debugging-2026-08-13.md`'s
  2026-08-15 entries for the full root-cause chain and both failed
  attempts).
- **2026-08-15** — *Extension, to the Fix protocol (a later pass, same
  investigation).* A third scoped-fix attempt at the gfx-task-submission
  stall — patching `run_next_thread`'s empty-queue branch instead of
  substituting primitives — built and ran with no crash or regression, but a
  counter proved its own new code path never actually fires, even at
  confirmed full quiescence: a different, equally common parking path
  (`resume_thread_and_wait` via `swap_to_thread`) reaches `wait_for_resumed()`
  directly, bypassing the patched function. Added two rules to the Fix
  protocol: (1) confirm a scoped fix's call site is actually reached at the
  failure point (instrument and check, don't infer from the symptom), and
  (2) an unsynchronized cooperative scheduler's "only one thread executes at
  a time" invariant is an implicit lock — a fix that lets a parked thread
  act without being resumed breaks it and needs a real replacement (mutual
  exclusion) if more than one parked thread could plausibly do the same
  thing at once, or it reintroduces the class of race that crashed the
  earlier VI-thread-direct-drain attempt. Full evidence (the message-flow
  probe pattern, the `wait_for_resumed()` finding, and why the "real" fix
  needs actual locking, not just a bigger patch) is in
  `docs/boot-debugging-2026-08-13.md`'s matching 2026-08-15 entry.
- **2026-08-18** — *Correction.* G6 (cross-compare with ares) was
  "hardware-accurate ground truth"; it is now **unusable**. gdb's attach halts
  ares while memory stays readable, so a poll returns a full, plausible,
  entirely static table. Measured: 43 polls / 86s, a 64-word block of *active
  thread stack* unchanged in every one, `$pc` = `0xffffffff` throughout, and a
  `0xDEADBEEF` canary planted into a live function pointer surviving the whole
  run. **Every prior ares result is void**, including the one that attributed
  the attract-mode stack overflow to us rather than the game.
- **2026-08-18** — *Correction.* EV rule 2 gains the sharpest instance yet: **a
  stopped machine answers every question with "no."** The rule already required
  a control and still did not fire, so the durable fix was putting the control
  *inside the tool* — `ares_watch.sh` now samples a must-change block every poll
  and prints `CONTROL FAILED — this run proves NOTHING`. Writing a rule down is
  not applying it.
- **2026-08-18** — *Correction.* `SNP_WALK`'s `longest_list`/`bad` counters read
  a `0xFF`-terminated byte list at `node+8`. **No such structure exists** — the
  children are a counted array reached via the third argument. The counters were
  reading unrelated memory and reporting healthy values, and a handoff cited
  those values to rule out malformed child lists. That rule-out is **withdrawn**.
  A probe that reads the wrong structure does not look broken; it looks like
  evidence. Check probe offsets against the generated source first — that read
  is free.
- **2026-08-18** — *Correction.* G4 previously sent you to hand-read
  `RecompiledFuncs/`. `scripts/decomp.sh` (m2c over splat's assembly) is now
  step 0: it emitted in six lines what a 60-line hand-read reached — and the
  hand-read had truncated early and missed a whole fourth list. Read the
  transliteration only to see what the *recompiler* emitted, never to learn what
  the game code means.
- **2026-08-18** — *Extension.* Route selection: expand the cheapest frontier
  node and re-cost after every result, weighing cost *per answer* rather than
  wall-clock.
- **2026-08-18** — *Extension.* Size a file before reading it; `RecompiledFuncs/`
  is 1.5M lines and reading blind evicts the context that motivated the question.
- **2026-08-18** — *Extension.* Tool inventory section; plus GameShark cheat
  addresses as a symbol source (KSEG0, usable verbatim with `SNP_WATCH`) and the
  recorded negative that no public S&P decomp exists.
- **2026-08-18** — *Extension.* Look at captures rather than trusting a scalar;
  `scripts/shrink_shot.py` downscales to the console's native ~320x240 first.
- **2026-08-18** — *Extension, user-directed.* **EV-2, claim strength.** The
  recurring failure is claims broader than their evidence, not missing evidence:
  4 universal-negatives-from-a-bounded-search, 3 measurement misinterpretations,
  3 causal compositions — while interventions and direct measurements have never
  been wrong. Adds the test-that-could-have-failed rule, an evidence-strength
  ordering, a mandatory scope on every negative, and a written falsifier for
  load-bearing claims. Ledger gains matching tags plus a Load-bearing section.
- **2026-08-18** — *Correction.* G3's xref recipe claimed `grep` over
  `../splat-project/asm/` was "a complete ROM-wide xref". **It is not.** splat
  covers `0x80020000-0x8005FFFF` and `0x800E0000+`; the `0x80060000-0x800DFFFF`
  main segment (620 functions, 5,853 `glabel`s vs 6,827 recompiled) is absent.
  An empty result means "outside splat's coverage", not "not in the ROM" — it
  produced a false "dead code" verdict on `func_8002A720`, refuted by a hardware
  watchpoint catching it execute. Use `RecompiledFuncs/` for completeness claims.
- **2026-08-18** — *Extension, user-directed.* **Count before you read, always** —
  generalises the file-sizing rule to every output-producing command (`grep -c`
  before `grep`, redirect-and-`wc -l` before reading a dump). Prompted by a
  ROM-wide `jal` xref that printed several hundred call sites when the question
  had a one-number answer. The old "size a file" rule is now its special case.

---

## Route selection: expand the cheapest frontier (added 2026-08-18)

**When two or more ways forward present themselves, take the cheapest one
first, and re-cost the alternatives after every result.** Treat the open
questions as a frontier and expand the nearest node, Dijkstra-style, rather
than picking the one that feels most central and committing to it.

Two properties make this more than "do the easy thing first":

- **Costs are not known up front; they are discovered.** A path that looked
  cheap can turn out to be a swamp, and the correct response is to drop it and
  expand elsewhere — not to sink more in because of what has already been
  spent. Re-costing after each measurement is the whole mechanism.
- **Cheap steps still pay into the map.** Every result narrows the space for
  the expensive questions later, so the cheap-first order tends to make the
  expensive path shorter by the time it is reached — or delete it entirely.

**Cost means cost-per-answer, not wall-clock.** A 10-second test that cannot
distinguish between the live hypotheses is not cheap, it is free and worthless;
weigh each candidate by what it would rule out. A step that can only confirm
what you already believe has no place on the frontier at all. The two gates
that guard this are G0 (state the symptom falsifiably) and EV rule 3 (is there
a second explanation that fits equally well?).

**Worked example, 2026-08-18.** After the ares gate collapsed, two paths were
open: chase why ares halts on gdb attach, or run the thread-4 stack-relocation
diagnostic.

| path | cost | outcome if it works |
|---|---|---|
| ares resume | open-ended emulator-stub debugging, 3 untested hypotheses, ~100s per attempt | restores a comparison gate |
| stack relocation | runtime-only: 13s build + one 90s run | confirms or kills the whole causal chain |

Relocation was expanded first purely on cost. It confirmed the chain end-to-end
and took the game from a hard freeze at gfx task 1240 to 2650 and still
climbing — the furthest it has ever run. The ares question is still open, but it
is now worth **less**: the thing it was going to be used to decide has been
decided another way. Expanding the cheap node re-costed the expensive one to
near zero. That is the pattern to look for.

---

## Cost function: tokens first, CPU is free (added 2026-08-18)

**Rank options by CONTEXT consumed, not wall-clock.** Machine time is nearly
free; context is the scarce resource, and spending it is what makes later
decisions worse.

1. **A long-running job is free if there is other work meanwhile.** Start the
   build, the 90s run, the Ghidra analysis in the background and keep going.
   Cost is what it puts in context when it finishes, not how long it took.
2. **Reduce output before it reaches context.** `grep -c`, `sort -u`, `head`,
   `awk` summaries, `tail -3`. A check that dumps 169 near-identical lines cost
   more than the run that produced them — that happened on 2026-08-18 with
   `SNP_PHASE`, where `sort -u` would have been free and lost nothing.
3. **Design probes to report a verdict, not a transcript.** One line saying
   "zero appends on the fatal frame, previous eight were 87" beats 200 lines to
   scroll. Probes are read by something with a context limit; write them for it.
4. **Prefer a targeted extract over a read.** `awk` a function out of a
   30,000-line file rather than paging it.
5. **Re-deriving a known fact is the most expensive thing here** — it burns
   context *and* run time, and produces nothing. Hence the ledger below.

## The visited set (added 2026-08-18) — REQUIRED for the routing to work

`docs/findings-ledger.md` is the **visited set**: one line per established fact,
ruled-out hypothesis, withdrawn belief and dead tool. **Read it before expanding
any node, and add to it the moment a finding lands.**

> **HOW to read it changed on 2026-08-19 — see "Reading the ledger: two tiers"
> immediately below. `scripts/ledger.py --index`, not the raw file.**

A shortest-path search with no visited set is not a shortest-path search — it is
a walk that revisits. The journal (`boot-debugging-2026-08-13.md`) cannot serve
this role: at 5,000+ lines, answering "do we already know X?" from it costs more
than re-deriving X, so the cheap move becomes re-deriving, and the same ground
gets covered twice. That is not a discipline failure, it is a missing index.

Three failure modes the ledger exists to prevent, all observed:

- **Re-running a settled experiment** — the ares comparison and the stub sweep
  were both re-run this session.
- **Acting on an overturned belief** — hence the `WD` status. A withdrawn
  finding is never deleted; the discarded belief is exactly what gets
  re-derived otherwise.
- **Missing a connection already in hand** — `0x80075DCC` had been probed days
  before its meaning surfaced from a cheat-code list. Facts that never sit in
  one readable place never meet each other.

---

## Reading the ledger: two tiers (added 2026-08-19, T67/T68)

**Read `scripts/ledger.py --index`. Expand with `--show` before relying on
anything.** Never read the raw file end to end — it costs 83k tokens and it will
keep growing.

```bash
scripts/ledger.py --self-check          # ALWAYS FIRST — 5/5, and it discriminates
scripts/ledger.py --index               # every entry, ~8.5k tokens. Replaces the full read.
scripts/ledger.py --show A99 A122       # verbatim entries, for the handful you need
scripts/ledger.py --grep overlay        # full entries matching a term
scripts/ledger.py --open                # the frontier
scripts/ledger.py --cited-by A54        # what rests on A54 — run this before trusting A54
```

### Follow the citations — the index does not carry them

`--index` gives you the claim, not what the entry rests on. That is a real cost
of the two-tier design and it bit immediately: rolls #62 and #65 re-derived most
of A104 while working A97, **whose own body says "See A104, which answered it"**
(T70).

So `--show` prints a **CITES footer** naming every ledger ID the shown entries
reference, plus the command to expand them. Read them before deriving anything.
`--self-check` asserts the footer fires and names a known citation — and it
discriminates: 5/6 with the footer disabled, and 5/6 with a footer that prints
but omits the IDs.

### The rule that makes two tiers safe

**The index tells you WHETHER something was checked. It never tells you WHAT it
established.** Every index line is a lossy paraphrase generated by a script.
Citing one instead of the entry would reintroduce the
claim-broader-than-the-evidence failure that broke about a dozen entries in a
single session — all of which cited real evidence, correctly gathered.

So: the index is for *routing attention*. `--show` is for *believing things*.

### Why not the alternatives

The tempting fixes were measured and rejected (T67):

* **Compress harder** — spent. Body text is **76.8%** of the file, the median
  entry is already at the 124-word target, and the last compression pass
  (33,646 → 27,308 words) was undone by one session of work. Compression fights
  the growth rate; it does not change it.
* **Split by topic** — actively harmful. It recreates the journal problem the
  ledger exists to solve: one file answers "has this been checked?" *precisely
  because* you ask that question when you do not know where to look. It also
  breaks citation locality (A99 cites A122, A54, A56, T57 across every topic
  boundary) and makes "which file does this go in?" a judgement call at write
  time, which is where the errors already concentrate.
* **Retrieval only, no full read** — insufficient on its own. You cannot grep
  for what you have not thought of. A127 came from noticing an overlay's address
  range while looking at something else entirely. The index preserves that
  end-to-end pass at a tenth of the cost; `--grep` complements it, never
  replaces it.

**What was NOT done, deliberately: the ledger file itself did not change.** This
is a view. If it turns out to be wrong, delete the script and nothing is lost —
no migration, no broken citations, no re-numbered entries. Rules 5 (never delete
a withdrawn entry) and 10 (merged stubs must still resolve) are untouched.

### Keeping the index honest

An index that rots is worse than none, because it fails silently — the entry is
still there, still correct, and simply says nothing. Two controls:

1. **`--self-check`, every time, before trusting output.** Five controls, and
   they discriminate: a version that dumps whole bodies scores 3/5, one that
   drops the status tag 4/5, one whose parser silently loses odd-shaped rows
   4/5. That last is not hypothetical — the first parser written for this
   dropped **33 of 198 rows** because bodies contain `|` characters.
2. **`check_ledger.py` flags any entry that indexes to a heading**, at write
   time. If it fires, put the claim in the status column or add a `**CLAIM:**`
   marker to the body. Do not "fix" it by editing the index — there is no index
   to edit, which is the point.

**Growth:** the index costs ~12 words per entry against ~400 for the file, so it
is roughly flat as the ledger keeps growing. That is the property being bought —
not a one-off saving, which is what every previous attempt bought (T54).

---

## Reporting to the user: plain English first (added 2026-08-18)

**The user is a CS student, not a console-RE specialist. Write checkpoint
summaries so they are understood by someone who knows programming but not this
domain.** Requested directly on 2026-08-18, after a run of summaries that opened
with things like "`0x800E4780` is a compressed staging buffer, not the execution
address" — true, and nearly opaque unless you already hold the whole model.

The rules:

1. **Lead with what it MEANS, then the evidence.** "The game stores this code
   squashed to save space, and unpacks it somewhere else at runtime — so the
   address we were registering was the wrong one" *before* any hex.
2. **Expand jargon on first use, once, briefly.** Overlay = a chunk of code
   swapped in and out of the same memory region. DMA = a hardware copy. Bump
   allocator = a pointer that walks along handing out memory. Staging buffer =
   scratch space data passes through on its way somewhere else.
3. **Addresses and function names are supporting detail, not the sentence.**
   `func_8002AA90` means nothing to a reader; "the function that rewinds the
   list" does. Name it once, then use the description.
4. **Say plainly what changed and what is next.** Especially when a previous
   conclusion was wrong — that is the part most worth understanding, and the
   part most easily buried under detail.
5. **Keep the precision in the docs.** The ledger and journal stay terse and
   exact; that is what they are for. Plainness is for the reply, not the record.

This is not "dumb it down" — it is putting the conclusion where it can be read,
and letting the reader ask for depth rather than mining for it.

---

## Free checks — run these before ANY experiment (added 2026-08-18)

Zero cost, no build, no run, no game launch. Every one of these has produced a
real finding, and several overturned a theory that a 90-second experiment was
about to be spent on. **A free check left unexpanded while runs are queued is
the most common way the cost ordering gets violated.**

| question | free check |
|---|---|
| what does this function actually do? | `scripts/decomp.sh <func>` |
| who touches this global, ROM-wide? | `grep -rn D_<ADDR> ../splat-project/asm/` — **but see the coverage warning below; this is NOT whole-ROM** |
| who touches this struct field (via a pointer)? | `grep -rnE "sw +\$[a-z0-9]+, 0x<OFF>\(" ../splat-project/asm/` (same warning) |
| who calls / references this, **completely**? | xref `RecompiledFuncs/` — the only complete index |

> **⚠ splat's asm is not the whole ROM (corrected 2026-08-18).** It covers
> `0x80020000-0x8005FFFF` and `0x800E0000+` only. The entire
> **`0x80060000-0x800DFFFF` "main" segment — 620 functions — is missing**:
> 5,853 `glabel`s in splat versus **6,827** functions the recompiler emits.
>
> A grep over `asm/` that comes back empty therefore means *"absent from splat's
> coverage"*, *not* "absent from the ROM". On 2026-08-18 that difference produced
> a confident, wrong "this function is dead code" conclusion about
> `func_8002A720` — which a hardware watchpoint then caught executing. Its caller
> lives in the main segment.
>
> **Before concluding a negative from an `asm/` grep, confirm the address is in
> splat's covered range.** For any completeness claim, xref `RecompiledFuncs/`
> instead (match `RECOMP_FUNC void <name>` to attribute a line to its function).
> Corollary: `scripts/decomp.sh` cannot decompile a main-segment function at all
> — read the generated C, or extend `tsumitobatsu.yaml` and re-run splat.
| which function owns this asm line? | `awk -v n=<LINE> 'NR<=n && /^glabel /{f=$2} NR==n{print f}' <file.s>` |
| which overlay/segment owns this asm file? | `grep -B6 "start: 0x<ROMOFF>" ../splat-project/tsumitobatsu.yaml` |
| is this function stubbed in our build? | `grep '"[a-z0-9]*_func_<ADDR>"' sinpunishment.toml` |
| is this global named by anyone? | GameShark cheat list (G4) — addresses are KSEG0, usable verbatim |
| what is actually on screen? | `scripts/shrink_shot.py <png>` then read the image |
| should I open this file at all? | `wc -l` first — see the sizing rule |

**Why the global xref usually looks empty and isn't.** A global reached through
a struct pointer (`obj+0xFC`) produces **no** absolute reference, so
`grep D_80067D9C` finds only the handful of absolute users and looks like a dead
end. The three draw-list counts appeared "never written anywhere in the ROM" on
that search. Search the *offset* through a pointer instead — that is what found
the per-frame reset.

**Caution: overlays share VRAM.** The same `func_800E9D8C` exists in several
overlay files with different code. Always resolve which segment an address came
from before reasoning about it; an xref hit in `file22` says nothing about what
runs when `file04` is resident.

---

## New tools: three gates before you trust one (added 2026-08-19, T71)

**Requested directly by the user on 2026-08-19, after `gdb_trace.sh` burned a
300-second run on a `sed` quoting bug that a dry run would have shown in
milliseconds.** Every new tool clears all three before its output is evidence.

### 1. DRY RUN FIRST — always, no exceptions

If the tool generates a script, a command line or a config, it must be able to
**print what it would do and exit without doing it**, and you must look at that
output before the first real invocation.

`gdb_trace.sh` substituted its values with `sed`. In a `sed` replacement `&`
means "the whole match", so the condition

    ((ctx->r6 & 0xFFFFFFFF) >= 0x8013A000 && ...)

became

    ((ctx->r6 __COND__ 0xFFFFFFFF) >= 0x8013A000 __COND____COND__ ...)

gdb rejected it, the trace never armed, and it cost a full deadline to find out.
**Any C condition worth tracing contains `&`.** The script now substitutes
literally in Python, **refuses to launch if any `__PLACEHOLDER__` survives**, and
supports `SNP_TRACE_DRYRUN=1`.

Cost asymmetry is the whole argument: a dry run is free, and a run against this
target is 3–5 minutes plus the risk of drawing a conclusion from a broken
instrument.

### 2. DISCIPLINE-COMPLIANT — carry a control that can fail

A tool that cannot report its own failure will eventually report a confident
wrong answer; four already have here (T61, T64, T66, and `gdb_trace.sh` itself).
Minimum bar:

* **A positive control, and it must discriminate.** `gdb_trace.sh` carries a
  *reach counter* — a second breakpoint at the same line with a huge `ignore`
  count that never stops but counts every hit. **Zero conditional hits means
  nothing unless the reach count is non-zero**; if both are zero the instrument
  never armed (T56). Its first real run reported 15 reaches / 2 hits, which is
  what makes those 2 hits evidence.
* **`--self-check` where the tool is a library or a reader**, asserting values
  measured by other means, and **verified to FAIL when the tool is broken** —
  not merely to pass when it works (T65). Check the discrimination by
  deliberately breaking the tool and re-running.
* **Refuse rather than guess.** `rom_disasm.py` looks the vram→ROM delta up;
  `rr_record.sh` refuses by default; `gdb_trace.sh` refuses on a leftover
  placeholder.
* **Sourced isolation** (`display_isolate.sh`) and a **hard deadline** for
  anything that launches the game.

**Calibration for `gdb_trace.sh`: traps are free.** 183,194 breakpoint traps
with zero stops perturbed nothing and A99 reproduced normally (A138's surviving
half).

**The second half of that calibration was WRONG and is corrected here.** It used
to read "93 stops changed which bug the run hit — the run took a crash in
`osSpTaskYield` instead, because each stop halts every thread and resumes them
in a new order." **T72 withdrew that causal claim** (the yield crash also occurs
with ZERO stops, so it was causation inferred from n=1 vs n=1), and **A159
confirms the withdrawal directly: three runs with ZERO conditional stops all
three took the yield crash**, at a point clustered within 0.65%.

So do NOT reason "few stops, therefore the run is undisturbed" — the yield crash
is not evidence that your trace perturbed anything, and on the current build it
is what a run does anyway. **Keep stops in the low tens for the DEADLINE's sake**
— a `printf` stop at a line hit 79,000 times is a run that never finishes — and
establish perturbation, if you need to claim it, against a no-probe control.

### 3. WRITTEN UP HERE — in the same checkpoint

A tool that only exists in a shell history is a tool the next session rebuilds.
The write-up names **what it is for, its controls, and the incident that
motivated it** — the incident is what stops it being deleted as ceremony later.
> **A NEW CHECKER'S FIRST RUN SHOULD SURPRISE YOU (T100).** If it comes back
> clean, the null hypothesis is that the checker is broken — not that the
> codebase is. On 2026-08-20 `lint_tools.py` immediately found a real `--help`
> defect, then flagged ITSELF, then its `/tmp` sweep found nine offenders where
> one had been claimed. That is what working looks like on day one.
>
> **AND MOST OF OUR GROUND TRUTH IS INTERNAL (T100).** `rom_disasm.py`'s
> self-check is the one control validated against something outside this
> project (splat's committed asm); ares gives external truth for *sequence and
> identity* only (T88). Everything else checks our instruments against our own
> expectations. That is the weakest flank in the whole method — prefer a
> control with an outside referent whenever one is available.

Add it to the **Tool inventory** table below in the same checkpoint that creates
it, not "later".

---

## Disassembling something `rom_disasm.py` cannot reach (added 2026-08-19, A155)

`scripts/rom_disasm.py` resolves a VRAM address through the `[[section]]` blocks
in the symbol file and **refuses** when no section contains it. That is correct
and it must not be loosened. But the **RSP microcode is not in those sections**
— it lives at a raw ROM offset (`rsp/audio.toml`: `text_offset = 0x32280`) and
is addressed as IMEM `0x04001000`. So the ucode needs a raw slice, which puts
you back in the position T49 came out of: **an offset chosen by hand, producing
a disassembly that looks entirely plausible and is entirely wrong.**

**The rule: an offset is not usable until a documented, unique word at a known
position decodes correctly at it.** For the audio ucode those words are already
recorded in `rsp/audio.toml`'s header comment — IMEM `0x000` = `0x09000419`
(`j 0x1064`) and IMEM `0x004` = `0x20010FC0`, described there as the only
occurrences of either value in the whole ROM. Check both *before* reading a
single instruction, and print the check rather than eyeballing it:

```bash
python3 -c "
import struct; rom=open('rom/sinpunishment.z64','rb').read(); b=0x32280
w=lambda o: struct.unpack('>I', rom[b+o:b+o+4])[0]
print('%08X %s' % (w(0), 'OK' if w(0)==0x09000419 else 'FAIL'))
print('%08X %s' % (w(4), 'OK' if w(4)==0x20010FC0 else 'FAIL'))"
```

Then slice and disassemble with the IMEM base as the vma, so the addresses in
the output match the `L_xxxx` labels in the generated C and can be compared
line for line:

```bash
mips-linux-gnu-objdump -D -b binary -m mips -EB --adjust-vma=0x1000 ucode.bin
```

**This is a control, not ceremony — it can fail.** A wrong `text_offset` fails
both words. And the comparison it enables is the point: A155 exists because the
generated C and the ROM were checked against each other instruction for
instruction, which is what made it safe to reason about the boot path at all.

**Two standing caveats.**

* **Scalar decode only.** `objdump -m mips` decodes the RSP's vector ops as
  COP2 garbage. Trust it for loads, stores, branches, `jr`/`jal`, `mtc0`/`mfc0`
  and arithmetic; do not quote it for anything vector.
* **RSP `mtc0` register numbers are NOT MIPS CP0 names.** objdump prints
  `mtc0 a3,$0` — `$0` is **SP_MEM_ADDR**, `$1` SP_DRAM_ADDR, `$2` SP_RD_LEN,
  `$4` SP_STATUS, `$5` SP_DMA_FULL, `$6` SP_DMA_BUSY, `$7` SP_SEMAPHORE,
  `$11` DPC_STATUS. The generated C names them properly in its comments; use
  that side for the names and the ROM side for the bytes.

**And the trap A155 actually turned on: `SP_MEM_ADDR` bit 12 is the IMEM/DMEM
select.** A value of `0x1080` is *IMEM offset `0x080`*, not DMEM `0x1080`.
librecomp's `DO_DMA_READ` ignores it entirely (`rsp.hpp:94`, unconditionally
`dma_rdram_to_dmem`), so any ucode that overlays its own IMEM is mis-emulated —
and **a ucode that does that also invalidates static reading of its text past
the overlay point**, because the bytes at a given IMEM address at runtime are
not the bytes RSPRecomp compiled there. Check for an IMEM-targeted DMA *before*
trusting any whole-file static scan of a ucode.

---

## Two trace sites in ONE run (added 2026-08-19, roll #86, T81)

`gdb_trace.sh` takes an optional SECOND location through the environment:

```bash
SNP_TRACE_LOC2='funcs_4.c:661' \
SNP_TRACE_COND2='((ctx->r16 & 0xFFFFFFFF) >= 0x8013A000 && (ctx->r16 & 0xFFFFFFFF) <= 0x8013D000)' \
SNP_TRACE_ARGS2='ctx->r16, ctx->r3, ctx->r6, ctx->r29' \
scripts/gdb_trace.sh 'funcs_4.c:228' '<cond1>' '<args1>' 20 280 <log>
```

All three or none — a partial set **refuses**, because silently tracing one site
would produce a log that reads exactly like the two-site run you asked for.
Hits are prefixed `HIT1` and `HIT2`, and each site gets its own reach counter.

**Why it exists.** A99's central contradiction survived six rolls only because
its three measurements were three separate runs (A157). Comparing sites ACROSS
runs cannot separate "the instrument is wrong" from "the two runs differed" —
and on this target the runs genuinely do differ, which is the whole point of
T72. Within one run, that ambiguity is gone.

**The failure mode it is built against, because it has no symptom.** gdb numbers
breakpoints in creation order, so the second site's are 3 and 4. Aim `ignore` or
`commands` at the wrong number and nothing complains:

* `ignore` on a *conditional* breakpoint — it stops the inferior on every hit
  instead of counting silently. At a line reached ~79,000 times per run, that is
  a run that never finishes. (Do NOT justify this with A138's "stops change
  which bug you hit" — T72 withdrew that causal claim. The deadline argument is
  enough and it stands on its own.)
* `commands` on the *reach counter* — the printf never fires, and an empty log
  reads exactly like "the condition was never true".

Both cost a full deadline to discover and both produce evidence that looks fine.
So `scripts/test_gdb_trace.py` (`gdb_trace.sh --self-check`, 14 controls)
**parses the generated script**, numbers the `break` statements in source order
as gdb would, and asserts every `ignore` targets a reach breakpoint and every
`commands` targets a conditional one. Asserting against the literals 3 and 4
would merely restate the bug if it were present. Verified to FAIL: swapping the
second site's numbers scores 13/14 and names both halves; pointing `commands` at
the reach counter scores 12/14.

**Always dry-run first** (`SNP_TRACE_DRYRUN=1`) — it prints the generated script
and exits without launching. A gdb syntax error otherwise costs one full
deadline to discover.

---

## Scene identity: RECORD, never sample (added 2026-08-19, T83)

**Every isolated run is now recorded to video, automatically.** `display_isolate.sh`
starts `ffmpeg -f x11grab` as soon as the isolated display is up and stops it in
`snp_display_cleanup`, so all five runners — `run_game.sh`, `gdb_fault.sh`,
`gdb_watch.sh`, `gdb_trace.sh`, `boot_screen_check.sh` — inherit it with no
per-caller change. Output goes to that day's archive evidence directory (T47).

```
SNP_REC=0        disable
SNP_REC_DIR=...  output directory
SNP_REC_FPS=N    default 30
SNP_REC_MAX=N    hard cap in seconds, default 400
```

**Recordings are CROPPED to the game window automatically**, in
`snp_display_cleanup`, via `scripts/crop_recording.py --replace`. The recorded
screen is 1280x720 and the game is a 640x480 window centred in it (Xvfb has no
window manager), so most of every frame is black padding. Measured effect:
**recordings land at 27-40% of their uncropped size** — the day's four files went
46 MB -> 14 MB. `SNP_REC_CROP=0` disables it.

**Finalize cost, measured (not extrapolated):** 2.4 s for a 30 s run (83 MB
master), **6.5 s for a 165 s run (454 MB master)** — sub-linear, it parallelises
to ~660% CPU. The old lossy-source crop took 4.9 s on a comparable run, so
lossless capture costs about **1.5 s** despite a 20x larger source. The master is
transient: ~2.7 MB/s, deleted as soon as the final file exists.

**The masters carry NO stream duration** (matroska written by a SIGINT-stopped
ffmpeg). `crop_recording.py` falls back to format duration, then frames/rate, and
**REFUSES if all three fail** — because sampling only the opening seconds while
reporting "across the whole file" is precisely the failure the check exists to
prevent, and it did exactly that until 2026-08-19 (T89).

**Cost, measured on real runs, and the first estimate was LOW.** Uncropped, a
20 s run gave 1.2 MB (~60 KB/s) but a 160 s gdb run gave **20 MB** — about
125 KB/s, roughly double, because a longer run shows more varied content and
h264 spends bits on change. **Cropped, budget ~6 MB for a long run.** Note the
short-run extrapolation understated the real rate by half; measure the case you
care about.

### Why the crop is not `cropdetect`, and why it can refuse

`cropdetect` finds the bounding box of non-black **content**, which is the wrong
box: the game's own image has black borders inside its 640x480, so a title-screen
frame measures 591x425 at 344,136. Cropping to that silently slices off real game
pixels and the result looks fine. **We want the WINDOW rect — a geometry fact,
not a content fact.**

An assumed geometry that is wrong destroys evidence and looks fine afterwards, so
the crop is never applied on the assumption alone:

> **every pixel outside the proposed rect, across frames sampled through the
> whole file, must be black — otherwise REFUSE and keep the full recording.**

Sampled across the whole file deliberately: sampling only the start would not
notice a window that moved, which is the same scope lesson as A93/A161. Verified
to refuse — a rect shifted 40 px reports `brightest pixel OUTSIDE = 151 at
x=344 y=142 t=41.3s` and declines. If the window ever moves, runs keep their full
recording and the refusal says why. Note the game window is 640x480 inside a 1280x720 screen, so
most of each frame is black padding; that is why the files are so small.

### Why this exists — three wrong answers from sampled stills

Scene identity was read off sampled frames three times and was wrong three times:

* **A93** — 10 s sampling interval skipped both the white fade and the title
  screen, and concluded the destination was the gameplay demo. The user caught it.
* **A161** — "our build never reaches the title screen", from TWO frames. The
  user caught it. Withdrawn the same day.
* the **"title scene"** label on A99, inherited and cited by A120, which nobody
  had ever measured at all.

The title screen is up for only a few seconds. **Any sampler can miss it, and no
sample can ever support "X never happened."**

### What each channel can and cannot support

| channel | resolution | can it support an ABSENCE claim? |
|---|---|---|
| still captures (`boot_screen_check.sh`) | whenever you fire them | **no** |
| `SNP_WATCH` scene byte | **1 s poll** — see `events.cpp`, it samples | **no** |
| the recording | every frame, ~33 ms | **yes**, down to one frame |
| `gdb_watch.sh` hardware watchpoint | every write | **yes** |

**`SNP_WATCH` is itself a 1 Hz sampler.** It was very nearly recommended as the
cure for a sampling error. A92's "`0x02` at t=145" therefore means "by t=145
+/-1 s", and any state shorter than a second can pass through it unseen. Check
the sampling rate of the instrument you are proposing as the fix.

### The rule

**Presence may come from a sample. ABSENCE requires a continuous channel.** This
is the ledger's existing scope rule applied to time: a negative from sampled
frames has scope "at these N instants", never "ever". Say which.

When you make a scene-identity claim, **cite the recording and a timestamp in
it**, not a still. Extract the frame if you want one in the ledger:

```bash
ffmpeg -ss 147 -i <run>.mp4 -frames:v 1 frame.png
```

### Classifying a recording automatically (T88)

```bash
scripts/classify_recording.py <run>.mp4 --fps 4      # timeline of matched scenes
scripts/classify_recording.py <run>.mp4 --fps 0      # EVERY frame -- needed for absence
scripts/classify_recording.py --self-check           # discrimination control
```

Perceptual hash (dHash) against labelled frames in
`<archive>/scene-refs/<label>.png`. It prints a timeline plus the per-frame best
distance, so a near miss is visible rather than swallowed by the threshold.

**`--fps 0` is what makes an absence claim possible.** A coarse `--fps` plus the
word "never" is A93/A161 with extra steps.

**Two scope limits that are easy to forget:**

* **Build references from OUR OWN build, never from the ares captures.** ares
  renders at roughly 240p and emulates the N64's video-interface filtering/AA;
  RT64 does not match it pixel-for-pixel. **The ares set is authoritative for
  SEQUENCE and scene IDENTITY — it is how we know the title screen is the green
  logo card — and is useless for pixel matching.**
* **References are tied to the renderer settings and window size.** Change
  resolution or filtering and they must be rebuilt. `--self-check`'s
  discrimination distances are the canary: title-vs-attract measures 21 today,
  against a threshold of 12.

A moving cinematic needs many references or it reads as `(unmatched)`. Attract
currently matches only sporadically, and the tool says so rather than guessing.

### Still open: the scene byte has never been calibrated

A92 measured `0x80068A94` going `0x01` -> `0x14` (t=7) -> `0x02` (t=145) and
said plainly what was NOT established: **that `0x02` is the menu. No byte value
has ever been tied to a named scene.** Until that table exists, scene identity
stays a judgement about artwork rather than a lookup. Building it is one
instrumented run cross-referencing the recording against the byte transitions —
and it is much cheaper now that a START press reaches the title screen in ~40 s
(A162).

---

## `SNP_DL_CENSUS` — how much is actually in the display list (added 2026-08-20, A234)

**The question it exists for.** The tutorial draws a character and two pylons
against black where the reference (A222) shows a city. Four explanations were
open and nothing separated them: the geometry is never SUBMITTED, is submitted
and SKIPPED, is drawn OFF-SCREEN, or is drawn BLACK. The first is upstream of
the renderer and the rest are inside it, so the cheapest cut is to ask how much
arrives at the renderer's door.

**Where it measures, and why there.** At `on_displaylist_submitted` in
`gfx_thread_func`, with the list pointer in hand at the moment it is handed
over. RT64's parse callback is not wired (there is a standing TODO at
`on_displaylist_parsed`), so the count has to come from walking it ourselves —
and a live walk, because a snapshot cannot tell a live frame from a leftover.

### Three design choices, each paid for by a specific failure mode

**The opcode table is DETECTED, never assumed.** F3D and F3DEX2 disagree about
the two opcodes the walk depends on (`G_DL`/`G_ENDDL` = `0xDE`/`0xDF` versus
`0x06`/`0xB8`). The walk runs under both and a table counts only if the list
TERMINATES CLEANLY under it. Guessing would have produced a confident wrong
number, which is this project's single most repeated failure.

**The histogram needs no table at all.** Counting commands per opcode byte is
interpretation-free; only the WALK needs an opcode table. So the payload
survives even if the naming of any individual opcode turns out wrong, and two
scenes can be compared without deciding in advance which byte means "triangle".

**An unresolvable branch is REJECTED, never defaulted.** Segment 0 is physical
by convention and is pre-set; every other segment must be seen in a
`G_MOVEWORD` before a branch through it is followed. Defaulting an unset
segment to base 0 would turn every unresolvable branch into a plausible address
and walk garbage confidently — the exact failure the probe was built to avoid.

### The instrument's own gap was nearly reported as a fault in the GAME

The first version had no segment resolution. It reported **0 % clean walks
across the whole tutorial window against 58 % in the window just before** — a
sharp transition exactly at the scene boundary, which reads irresistibly like a
finding. It was not. Every one of those walks had stopped at a branch to
`0x08000000` or `0x00040600`: ordinary segmented addresses that the walker
refused to follow. **The stop-REASON field is what made that legible;** a bare
`ok`/`not ok` cannot tell "the list is malformed" from "my walker is
incomplete", and those are opposite conclusions about the game. With resolution
added, **5,374 of 5,374 tasks terminate cleanly.**

### The controls, and which of them can fail

`SNP_DL_CENSUS=selftest` runs 13 controls at gfx-thread start over synthetic
lists, needing no game state (8 originally; A297 added three — see below).
Three of the original eight discriminate:

* an **unterminated** list must be REJECTED;
* an **F3D** list must be rejected by the F3DEX2 table and accepted by the F3D one;
* a branch into an **unset segment** must be rejected, not guessed.

**Verified to fail, not merely to pass** (T65): the walker was sabotaged to
return `ok` unconditionally, rebuilt and re-run — it scored **4/6**, and exactly
the two discriminating controls of that version failed while the other four
passed on a knowingly broken walker.

**Twice the controls caught a bad FIXTURE rather than a bad parser** — a
segment base that collided with the test's own base address, and a
hand-assembled `G_MOVEWORD` with the index byte one position out. Both would
have been invisible in a probe that only printed. Build fixture constants from
named parts, not hex literals.

### OPERANDS: RECTANGLES, COLOURS, SCISSORS, AND WHERE THEY SIT IN THE STREAM

Counts cannot tell a rectangle that PAINTS from one that WIPES (A256), so the
walker records operands for the commands that decide it. Added in two passes:

* **A257** — `G_FILLRECT` rectangles and `G_SETCIMG` target addresses.
* **A297** — the **fill colour** in effect at each rect, `G_SETSCISSOR`
  rectangles, and a **command sequence index** on every rect and scissor plus
  the first/last triangle index. Three gaps named in three separate entries,
  all closed by one edit sharing one rebuild and one run.

**Controls now 13, and the three added by A297 were verified to fail** — each
broken a *different* way in a single build, because four controls of the same
shape are one control (A261). Forcing `rect_color_set` true, recording the rect
INDEX instead of the command index, and decoding scissors with `G_FILLRECT`'s
packing scored **10/13**: exactly those three, the other ten unaffected.

**THE PACKING IS INVERTED BETWEEN THE TWO RECTANGLE COMMANDS, and getting it
wrong produces a finding rather than an error.** `G_SETSCISSOR` puts upper-left
in `w0` and lower-right in `w1`; `G_FILLRECT` is the other way round. Decode a
scissor with the fillrect packing and you get a valid-looking INVERTED
rectangle — which reads as "the scissor is clipping the scene away", a story
that was already live and that the counts did not support. The control names
the wrong answer as well as the right one so it cannot pass by coincidence.

**Two traps this pass walked into and out of.** Fill colour is RUNNING STATE,
not a per-rect operand — `G_FILLRECT` carries no colour, it uses whatever
`G_SETFILLCOLOR` last set — so it is tracked and *sampled* at each rect, and a
separate flag distinguishes "filled with black" from "no colour was ever set",
which are opposite meanings behind the same zero. And rect order was recorded
among RECTS only: "drawn, then overwritten by the large fill" and "filled
first, geometry never arrived" are the same rect list in a different order, and
only an index against the geometry separates them.

**STILL MISSING, and it is one line:** `G_SETCIMG` has no sequence index, so
which render target a given rect writes to cannot be read off the log. A297 is
one operand short of deciding whether the frame's large fill clears colour or
depth.

### A SATURATING COUNTER LOOKS EXACTLY LIKE THE ANSWER YOU ARE LOOKING FOR

The per-child counter first stored at most 48 children and reported `nchild`
from the same variable. Across the whole tutorial it read a flat **48** — and
the question being asked was *"has the count stopped growing?"*. The array
bound was answering the question.

**Count and storage are now separate fields**, the overflow is printed, and a
control asserts the count keeps counting past the store limit. Whenever a
measurement has a buffer behind it, ask what the buffer would report if it
overflowed, and make sure that is distinguishable from the result you expect.

### THE SAMPLE INTERVAL MUST FIT THE WINDOW YOU ARE ASKING ABOUT

The histogram printed every 300 tasks — once per ~10 s, i.e. 18 samples over a
180 s run. The opening-logo window is **4.5 seconds long** and fell entirely
between two of them, so the richest part of the instrument had nothing to say
about the question it was pointed at. `SNP_DL_CENSUS=<N>` now sets the interval:
`=15` for a dense look at a short opening, the default `300` for a long run.

Before running, ask how long the window of interest is and divide. This is the
same sparse-sampling failure as A223 wearing different clothes — there the
samples existed and went unread, here the samples were never taken.

#### THE SAMPLE PERIOD MUST NOT SHARE A FACTOR WITH THE PHENOMENON (added 2026-08-23, A367)

**The game triple-buffers.** Three colour images — `0x8038F800`, `0x803B5000`,
`0x803DA800` — exactly `0x25800` apart (320×240×2), rotating **one per frame**
in strict order. A247 inferred this from pixel retention; A367 read it straight
off the display list, 384/382/379 occurrences across 616 dense samples.

**The census default was 300, and 300 is divisible by 3.** So every 300-spaced
census this project has ever taken sampled **the same buffer every time** — one
screen in three. A237's opening census used 15: same defect. The dense captures
use ~10, which is the only reason the rotation was ever visible.

That is not a small print issue. A356 called `0x803DA800` "**the** framebuffer"
because all eighteen of its sampled tasks are ≡ 0 mod 3.

**What survives such a sample, and what does not** — the arithmetic matters more
than the caution:

* A **contrast between two bands sampled at the same period** is safe. Every arm
  sits in the same phase, so a phase-dependent effect appears in both or
  neither and cannot manufacture a difference. A356's attract-versus-tutorial
  finding survives on exactly this ground.
* A **universal** does not. "Every frame", "all 18 sampled tasks" mean *one
  buffer in three* and must be re-scoped.

**The default is now 301** — coprime to 2, 3, 4 and 5, so short cycles walk
through phases instead of hiding — and the probe **warns** when an explicitly
passed interval is divisible by 2 or 3. Rebuilt and re-controlled at 18/18 in
the same checkpoint.

**The general rule, which is why this sits in the playbook and not just in an
entry:** an instrument whose sampling period shares a factor with the period of
what it measures cannot see it, and the output looks perfectly clean. Before
trusting a periodic sample, ask what periods it is blind to.

---

## DO NOT COMPARE LIST ENTRIES BY INDEX ACROSS FRAMES

Comparing child `k` at two times showed swings of +57 and −66 commands, which
reads as violent growth and shrinkage. It is neither: the list is rebuilt every
frame and entries shift position, so index `k` is a **different object** at two
different times. Only the aggregate is comparable across frames. An index-wise
reading of the same log would have supported almost any story you wanted.

---

## Tool inventory (added 2026-08-18) — check here before building anything

Half of one session's friction was not knowing what already existed. Everything
below is installed and verified working.

| tool | where | use it for |
|---|---|---|
| **m2c** | `../tools/m2c` + `../tools/m2c-venv`, wrapped by `scripts/decomp.sh` | decompiling a ROM function to real C. **First choice** for "what does this do" |
| **splat output** | `../splat-project/asm/*.s` (30 files, whole ROM) | m2c's input; also grep-able MIPS |
| **Ghidra 12.1.2** | `../tools/ghidra_12.1.2_PUBLIC`, `support/analyzeHeadless` | cross-references ("what else writes X?") — the one thing m2c can't do |
| Ghidra projects | `../tools/ghidra-projects` | **`ovl1` only**, 0-byte `.gpr` (killed, not closed). Boot-segment work needs a fresh import |
| **gdb / gdb-multiarch** | system | `scripts/gdb_watch.sh`, `gdb_threads.sh` |
| **python-xlib** | system python3 (0.33) | window minimizing; no longer venv-only |
| **ffmpeg / ffprobe** | system, `x11grab` device present | run recording (T83), cropping, frame extraction |
| `scripts/crop_recording.py` | repo | crop + compress a lossless run master in ONE pass. **REFUSES unless everything outside the crop is black** — `--check` to verify only, `--finalize` for the capture pipeline |
| `scripts/classify_recording.py` | repo | "which scenes did this run reach, and when" — dHash vs `<archive>/scene-refs/*.png`. `--fps 0` for absence claims. `--self-check` asserts discrimination |
| `scripts/rad_hist.py` | repo | **aggregates the A668 `[rad]` per-task radius lines into scene bands.** Purpose: the draw gate reads exactly ONE field of each object (A662) — the radius it hands the frustum cull — so counting arrivals at that call site and banding them by size answers both "how many objects reach the cull" and "how big are they". Controls: `--self-check` is 14 assertions **verified to FAIL in both directions** (upper-tail sum changed b5-7→b6-7; band-vs-n consistency check disabled) — a control that only passes is not a control (T65); and it REFUSES an empty parse with a message naming the probe-absence case instead of printing an empty table. Motivated by T209's three instances — T207, A455, A461 — where an ad-hoc analysis script produced a confident wrong number because its instrument could not have shown a different answer. **Ad-hoc analysis scripts are TOOLS and T71's gates apply to them; that is the hole all three fell through.** |
| **the A668 radius probe** | runtime tree + **generated tree** (never committed) | **`snp_radius_seen(ctx->f12.u32l)` at the draw gate's single cull call site**, `RecompiledFuncs/funcs_3.c:7729`, printing a per-task exponent-band histogram. **IT LIVES IN A GENERATED FILE AND THAT IS THE WHOLE TRAP:** the read-watch tap filters on address range `0x60000-0x80000` and the object pool is outside it, so the tap CANNOT see this load and the call site must be instrumented instead — but `recompile.sh` regenerates `RecompiledFuncs/` and would delete the probe, leaving a binary that reports nothing while looking identical. **"No large objects found" and "no probe" are the same picture.** So: build **`--no-recomp`**, and the probe prints an unconditional `[rad] FIRST OBSERVATION` line on the first radius it ever sees, independent of `SNP_READWATCH` and `SNP_DL_CENSUS` — its absence makes a run VOID rather than negative. A missing per-task line WITH the first-observation line present is the other signature: that is A659 run 1's failure, `SNP_DL_CENSUS` omitted. **Restore the generated file by sha256 afterwards and rebuild**, so source and binary cannot disagree (T226). It takes `ctx->f12.u32l` — the word `MEM_W` already decoded — rather than reading RDRAM, so it cannot repeat the byte-order defect of A635/A647/A659 |
| **the A669 branch-counter probe, and THE IDENTITY CONTROL** | runtime tree + **generated tree** (never committed) | **`snp_gate_seen(n)` at all six decision points of `boot_func_80032AA0`** — entry, the 512-cap RET 0, the flag-bit path that skips the cull, the cull call, the discard RET 0, the emit RET 1. **THE REUSABLE PART IS THE CONTROL, NOT THE PROBE.** When counters are placed on every branch of a function, they must balance: here `entry == cap + skip + cull` and `ok + disc == skip + cull`. **That turns "I read all 163 instructions and found every exit" from an assertion into something that FAILS OUT LOUD if the reading was wrong** — a missed exit breaks the arithmetic, per task, in the log. Use this shape whenever instrumenting control flow; it is far stronger than a plausibility check, because it does not depend on knowing what the right answer looks like. **EXPECT +/-1 FAILURES AT TASK BOUNDARIES** and do not treat them as defects without measuring: a call in flight when the per-task counters reset puts its entry in task N and its exit in task N+1. A669 saw 421 such tasks (6.8%), **all exactly +/-1, 17 entries out of 287,866 (0.0059%)**, and confirmed the explanation by its own prediction — a `-1` in task N should be paired with a `+1` in task N+1, observed at **75.7% against a 3.2% null rate**. A *structural* error looks different: consistent, same-signed, and large. **A669 also shows the failure mode to avoid in the PRE-REGISTRATION itself** — it said in capitals "if either identity fails the run is VOID", then two paragraphs later gave the discriminator that says otherwise. The blanket rule was sloppy drafting; write the discriminator, not the absolute |
| `scripts/xref_addr.py` | repo | **"which recompiled functions touch this RDRAM address range?"** — a lui-paired scan over the recompiler's own disassembly comments, tracking registers through `lui`/`addiu`/`ori` and resolving every load/store to an effective address. **Reports TWO kinds of hit and the second is the point:** `ACCESS` (a load/store landing in the range) and `POINTER FORMED` (a base register built into the range with no direct access) — **a scan reporting only ACCESS is blind to exactly the case a descriptor table presents**, which A620 recorded as the known limit of the earlier ad-hoc scans. **Its positive control is the strong kind: it re-derives A653's independently-established 12 functions / 10 read / 4 write / 2 RMW at `0x8006826C`, a result produced before this tool existed, so the control can fail** — and it did, catching that A653 says ten functions *read* it, not ten are *read-only*. Also verified FAILING on two deliberate breaks. **SCOPE, and cite it whenever quoting a negative from this tool: it CANNOT see a base loaded from memory rather than built with `lui`, and it invalidates registers at every label (conservative — false negatives only). A negative here means "not named with lui in the tree", never "not read"** |
| **THE SCENE TABLE — canonical, use these names (A686)** | repo | **scene 1** = tasks 1-166, black then the intro's alarm-clock shot; also the window where the missing opening logos belong (A225/A651). **scene 20 = THE ATTRACT** = tasks 167-4313, the ~2.3-minute interruptible story sequence — **the user's decision 2026-08-29, on the reasoning that PRESS START is up over it, so it functions as an arcade attract reel even though it is cinematic**. **scene 2 = THE TITLE CARD** = tasks 4314-4663 (A685) — it submits no geometry because it is 2D, which is correct. **scene 19 = THE TUTORIAL** = tasks 4664-6168. **THE DUMP FILENAMES LIE AND ARE NOT BEING RENAMED:** `a594-logo.rdram` is the ATTRACT, `a604-logowindow.rdram` is scene 1, and the real logo card is scene 2 which nothing is named for — they were named after the INVESTIGATION, not the scene. `a590-tutorial.rdram` is correct. **State the scene NUMBER when citing any dump**; `scene_id.py` answers it in one command |
| `scripts/scene_id.py` | repo | **"which SCENE is this snapshot in?" — read out of memory, never sampled from video.** The current scene is a **byte at `0x80068A94`** (the one `boot_func_800263CC` re-reads at 0x80026420 and copies to `0x80068A93`, the previous scene); the *requested*-scene byte one along at `0x80068A95` is ZERO in every dump we hold and reading it instead is the mistake this tool was written after. **Why it exists: scene identity has been read off sampled frames three times here and been WRONG twice (A93, A161) and nearly a third time (A608) — T101 exists because of it.** THE CONTROL IS INDEPENDENT AND CAN FAIL: `overlay_map.py` computes each scene's final allocation-cursor value **from the ROM alone, never looking at a dump**, so the cursor at `0x800744D8` is a signature to check the byte against. Scenes sharing a cursor (5 and 19 load identical data, differing only in init function) are NARROWED not identified — but scenes 1 and 20 are unique, so a misread byte is caught. A second free control: the cursor BASE `0x800744D4` must read `0x802A0370`, the map's ROM-derived value; it does in all four dumps, which is the first validation of that map against live memory. **Byte at KSEG0 address A lives at RDRAM index `A^3`** — self-check verified FAILING when that swap is dropped, the exact A635/A647/A659 defect. If `overlay_map.py` cannot run it reports the control ABSENT rather than passing silently |
| `scripts/test_display_isolate.py` | repo | 6 controls over isolation + recording, incl. the **never-film-the-user's-desktop** guard |
| `scripts/observed_run.sh` | repo | **a run the USER watches and listens to.** Prints `observation-checklist.md` BEFORE launching, runs via `run_game.sh` in `xephyr` (visible, input isolated — never `real`, T59), then records their answers to `docs/observed-runs.md`. `--checklist` / `--dry-run` / `--self-check` (**8 controls** (was 5; the row went stale, found by T150 and corrected by T160)) |
| `scripts/gdb_trace.sh --watch` | repo | **the only instrument here that needs no LIST.** Anchors on a line to resolve `ctx`, then installs a location watchpoint — catches ANY writer without anyone enumerating them. **Arm LATE; it stops on every write.** 4 controls, verified to fail (T109) |
| `scripts/ledger.py --chain` | repo | **the correction chain, chronological** — makes a circle visible while it is happening. Reports the correction rate lifetime AND over the last 15; warns at 1/3 recent. Skeleton only, never says what was established (T110) |
| `scripts/regenerate.sh` | repo | **the ONLY correct way to regenerate.** Snapshot -> N64Recomp -> 3 repairs (one SILENT) -> build both -> SMOKE TEST on `gfx_tasks`. 'It links' was the check that passed on an inert binary (T116) |
| `scripts/snapshot_build.sh` | repo | **build state that outlives the session.** The untracked generated tree + its inputs + both binaries + a MANIFEST. Reason mandatory; refuses without the archive (T115) |
| **`docs/instrument-semantics.md`** | repo | **what a reading MEANS** — `ctx` is per-THREAD, breakpoints fire BEFORE their line, reach counts scale with the arm window, RDRAM snapshots are host-endian. **Read before designing any condition.** Every row names the incident that paid for it (T108) |
| `scripts/audio_capture.sh` | repo | **game-ONLY audio capture, routed BEFORE launch** via `PULSE_SINK` so nothing is missed at startup (T104). One LOSSLESS FLAC pass, master removed. **Isolation asserted behaviourally by a two-tone control.** `prepare`/`finish`/`attach`, `--self-check` (4), `--dry-run`, `--cleanup` |
| `scripts/ablate.py` + `SNP_ABLATE` | repo + runtime tree (hook NOT committed) | **ablation screen: run the game with ONE function stubbed to `jr ra`, per run, and diff the signature.** Full section below. `--dry-run`, `--self-check` (6, breaks 3/3 verified to FAIL), resumable TSV. **Screen rows are TRIAGE, never claims (T22)** |
| `docs/observation-checklist.md` | repo | what the user should look for, versioned. ⚑ marks the items **I cannot check at all** |
| `scripts/lint_tools.py` | repo | three enforcement checks nothing else made: is a NEW script documented (T71 gate 3), does anything taking arguments have a help path (T37), and does any script DEFAULT an evidence path to `/tmp` (T47). Baseline-bounded so it reports what you just built, not the backlog. `--dry-run`, `--strict`, `--self-check` (9 controls) |
| `scripts/test_gdb_trace.py` | repo | 14 controls over `gdb_trace.sh`; run it as `gdb_trace.sh --self-check` |
| **scene reference frames** | `<archive>/scene-refs/*.png` | labelled 640x480 frames from OUR build. **Never build these from the ares captures** — different renderer, ~240p + VI filtering (T88) |
| **PIL, numpy** | system python3 | `scripts/shrink_shot.py`, capture analysis |
| **RT64 debugger inspector** | already in `lib/rt64`; `developer_mode: true` in `~/.config/sinpunishment/graphics.json`, then **F1** | **"View Draw Call" TRUNCATES rendering to the first N calls — the frame builds up one draw at a time (A243), not a highlight. Also a "Start dumping textures" button that writes every unique loaded texture to disk keyed by hash. Plus FREE CAMERA, depth-buffer view, per-frame triangle/draw-call counts.** Free camera separates *drawn off-screen* from *not drawn*; depth view separates *drawn black* from *not drawn*. **USER-DRIVEN — it is an ImGui panel and I cannot click it.** Needs `SNP_ISO=xephyr`. Shows RT64's *interpretation*: good for presence and identity, never for pixel claims (T88). **No wireframe mode exists.** Verified not to perturb the census over 400 tasks (A239) |
| **`scripts/yay0_extract.py`** | repo | **decompress the ROM's 28 Yay0 archives and lay each out as a contact sheet** of 64x64 CI4 tiles in ROM order, for a HUMAN to recognise (A227's split: decoding is the machine's job, recognition is the person's). `--dry-run`, `--self-check` (3 controls, 2 discriminating: a corrupted archive must be REJECTED and an overrunning size must not report success). The format's declared length is the field control — 28/28 decode to it exactly. **Says nothing about whether an asset is ever LOADED; that is RT64's texture dump (A243), the complementary question** |
| **`scripts/send_key.py`** | repo | **one XTEST keypress to an isolated display**, so an interactive instrument can be tested without the user retrying blind. `--display :7 --key F1`, `--dry-run`, `--self-check` (4 controls; 2 discriminating — a nonsense key must not resolve, a dead display must FAIL). **Any run using it is CONTAMINATED BY DESIGN** — tool verification only, never evidence (A244). Note `run_game.sh`'s `input_events` counts CONTROLLER events only, so a zero there does NOT mean nothing was typed |
| **`SNP_POKE=0xADDR:0xVALUE[:size][,...]`** | runtime env var, `ultramodern/src/events.cpp` | **WRITES to RDRAM every VI (~60 Hz), the missing half of `SNP_WATCH`.** Motivated by T145: we had cheat codes — `0x80075DD6` (unlock levels), KSEG0 and usable verbatim per T5 — and *no way to write*, so a grep for a poke returned nothing and every path needing a scene we cannot reach by playing was blocked behind it. Sizes 1/2/4; the swizzle matches `recomp.h` (words native, halfwords `^2`, bytes `^3`) and **the odd-address byte case is the one that matters**, since `0x80075DD6` is odd. **Controls (A327):** `SNP_POKE_DRY=1` prints the decoded list and writes nothing — that is the T71 gate-1 analogue for an in-process facility, *not* a literal print-and-exit, and it is stated as a deviation rather than claimed as a match; the discriminating control is **poke-then-read-back through `SNP_WATCH` on the containing word**, which was pre-registered to distinguish a *correct* `^3` (byte lands in lane 1 → `0x0100`**`5A`**`00`) from an un-swizzled write (lane 2 → `0x5A000100`), so it confirms the swizzle and not merely that *a* write happened; and malformed tokens are **reported and dropped**, never silently ignored — four rejection paths (out-of-range, bad size, unparseable, misaligned) all fire on one dry run. **EVERY VI, NOT ONCE — and this is measured, not assumed:** the first ON run logged the game clobbering the byte three times during startup (`0x00`, `0x00`, then `0x01`) before our value stuck, so a one-shot startup write would have been overwritten and would have read exactly like a poke that never worked. **CONTAMINATED BY DESIGN, like `send_key.py`** — a run using it is evidence of *reaching* a scene and must never be cited as evidence of normal behaviour; the run says so itself on stderr. Bounded to the poke: input scripting is the NEXT scheduled item, not this one |
| **`scripts/guard_bash.py`** | PreToolUse hook, always on | **refuses shell commands that bypass a mechanised discipline** — launching the binary directly instead of via `run_game.sh`, and merging a project script's stderr into a pipe that truncates by position (A196). It fires often and it is not advisory; rephrase rather than retry. `test_guard.py` 30/30 |
| **`scripts/lint_hooks.py`** | pre-flight lint | scratch debug hooks left in `sinpunishment.toml`. Part of the session-start block; `daily_push.sh` refuses to push while any remain. `test_lint_hooks.py` 10/10 |
| **`scripts/resolve_bt.sh`** | post-processor | turns the raw addresses in `[taskbt]` lines into game function names via `nm`. `SNP_TASK_BT` prints addresses only, because the binary is linked without `-rdynamic` |
| **`scripts/symbol_gaps.py`** | static | classifies the unclaimed gaps between consecutive function symbols. **The named first step of the T11 triage** (see `SCHEDULE.md`). `--skip ovlfile12` withholds the section T11 closed; the withheld COUNT still prints (T76) |
| **`scripts/truncation_sweep.py`** | static | sweeps every generated function for A85's truncation signature (class BC-2) — the defect behind A96 |
| **`scripts/gap_classify.py`** | static, ROM only | **T11 step 2.** Decodes each gap's actual ROM bytes and sorts it into PADDING / SEPARATE / CONTINUATION / RETURNS-BOTH / NO-CODE / UNCLEAR. Generalises A292's hand-read; the one route to this that does not go through splat. `--self-check` 7/7, verified to FAIL on 3 deliberate breaks (A419) |
| **`scripts/overlay_map.py`** | static, ROM only | computes where every compressed code overlay unpacks to, from the ROM alone |
| **`scripts/probe_stubs.py`** | codegen | injects a first-call probe into every silently-stubbed recompiled function, so a stub that is actually reached announces itself |
| **`scripts/inject_flag_trace.py`** | codegen | injects `SNP` flag-protocol tracing into the generated pump/dispatcher code |
| **`scripts/bootstrap.sh`** | setup | bootstraps the toolchain (macOS/Linux). Already run on this machine |
| **`scripts/snp-shader-tool.sh`** | wrapper | `dxc`/`spirv-cross` shader wrapper **for macOS arm64** — not used on this Linux machine |
| **`scripts/backup_drive.sh`** | shell, needs `rclone` + a `gdrive` remote | **backs up what git cannot or must not hold.** `daily_push.sh` covers the repo; this covers the gap — `probe-patches/` (**ungittable by T36/T38**), gitignored handoffs, `ares-refs/`, and the ROMs + `.eeprom` save. **DRY RUN IS THE DEFAULT**; `--go` transfers, `--all` adds 755 MB of largely re-creatable logs and video. **Excludes `rom/*.log` — 1.24 GB of 2026-08-13 ares instruction traces that are not ROM data and predate T47.** `--self-check` runs **6 controls, verified to fail**; the exclusion and the refusal are both BEHAVIOURAL, not source-greps (T146) |
| **`SNP_DL_CENSUS`** | runtime probe, `ultramodern/src/events.cpp` | **how much is in the display list the renderer is handed, per frame.** Walks it at the submission point — not from a snapshot (T69). Detects the microcode table instead of assuming it, resolves segmented branches from `G_MOVEWORD`, and prints an opcode histogram every 300 tasks. **Also records operands: fill rectangles + their colour, scissor rectangles, render targets (and the target IN FORCE at each rect), a command sequence index against the geometry, the VIEWPORT — followed through its segmented pointer, with an unresolvable one COUNTED rather than invented — the CYCLE TYPE in force at each rect, because `G_FILLRECT` only clears in FILL mode, and `G_MTX` PARAMETER BYTES raw** (A257, A297, A300, A302, A304, A307). **Operand fields store raw bytes wherever a packing is involved — three hand-derived packings went wrong in one day, and a raw histogram lets the decode be disputed separately from the counts.** `SNP_DL_CENSUS=selftest` runs **13 controls, 6 of them verified to fail** (A234, A297) |

**No MIPS toolchain is installed, and none is needed.** m2c parses assembly as
text; splat has already produced it. Don't go looking for `mips-linux-gnu-*`.

**Ghidra's remaining niche is cross-references.** Since m2c arrived it is no
longer the way to read a function. But "who else writes `obj+0xFC`?" is a static
query, and answering that class of question with instrumented 25s runs is the
expensive habit worth replacing. Its analysis is pure CPU — no token cost — so
it can run in the background while other work continues. Budget for a one-time
import: Ghidra has no native N64 loader, so it means raw-binary MIPS big-endian
at the right base, or a loader extension.

**Never install a tool into a session scratchpad.** Ghidra was found in a
`/tmp/claude-*/…/scratchpad/` directory from six days earlier, 1.5GB of it,
surviving only because the machine had not rebooted. Scratchpads are disposable
by design. Anything meant to outlive the session goes somewhere durable.

**Look at captures; do not trust the scalar.** The Read tool renders images.
`scripts/shrink_shot.py <png>` first — the N64 rendered ~320x240 while the window
is 640x480, so halving discards upscaling, not detail (verified: fully legible at
a quarter of the pixels). A `dark_fraction` number once said "not black" for a
frame that was solid black.

---

## `dl_render.py` — draw the frame from the game's own list, with no game (added 2026-08-25, the user's question)

**Purpose.** Replay the ordered trace `SNP_DL_GEOM` emits — matrix loads, pops,
vertex loads, triangles, **in list order** — maintain the matrix stack and the
32-entry vertex cache as the RSP would, transform, project, write a PNG.
**An independent path from the display list to a picture**, owing nothing to
RT64. Every geometry claim on this project has come through RT64 or through
counts; A421's value came precisely from an instrument that agreed from the
other side.

**Arming the dump:** `SNP_DL_GEOM=2400,5400` — named tasks only. 1,136
triangles is nothing; 6,169 frames of them is 135 MB, and
`rdp-boundary-4600-4899.txt` is the standing reminder of what that costs.
The trace is emitted for the **F3DEX2 walk only** — both tables are tried on
every task, and a doubled trace replays as a doubled vertex cache, which looks
like geometry rather than like a bug.

**NO TEXTURES, AND THAT IS AN IMPROVEMENT HERE.** Triangles are coloured **by
sub-list**. A422 found 739 depth-writing triangles in a tutorial frame with no
sub-list larger than 36 — is that a character and three enemies, or ninety
fragments of something else? Real colours would hide exactly that.

**RUN THE ATTRACT FIRST. THIS IS NOT OPTIONAL.** Reconstruct a scene that
demonstrably renders and compare it against the recording of the same run. If
the pipeline reproduces a working scene it can be trusted on a broken one.
Pointing it at the tutorial first means believing whatever comes out — and
matrix-stack emulation fails *silently and plausibly*, which is this project's
signature failure.

**Four controls, all verified to FAIL** (`--self-check` 6/6, breaks 4/4):

| break | what it would do to a picture |
|---|---|
| fixed-point read as interleaved pairs | plausible frame, every transform wrong |
| unloaded vertex slot filled with `(0,0,0)` | a spike to the origin that reads as geometry |
| PUSH bit read non-inverted | stack never grows; every child inherits its sibling's transform |
| behind-eye geometry divided anyway | geometry mirrored into frame as convincing shapes |

**The F3DEX2 trap worth knowing:** `gsSPMatrix` **XORs the param with
`G_MTX_PUSH`**, so in the raw byte **0 means PUSH**. Read it the `gbi.h` way
and the stack never grows. The probe emits the byte **raw** and decodes it in
one place only — inverting it at both ends is how one end ends up wrong.

**And the Mtx layout:** the 16 **integer** halves come first in 32 bytes, then
the 16 **fractional** halves — they are *not* interleaved per element.

**SCOPE.** This shows what was **submitted**. No clipping, no z-buffer, no
combiner — it cannot show what the RDP then did with it. For "is the geometry
there at all" (A422's live question) that is exactly right. For "why does this
pixel look wrong", it is the wrong instrument.

---

## `ultralib_oracle.py` — the SDK named by compiling it ourselves (added 2026-08-25, A444)

**Purpose.** Build ultralib (the public libultra reconstruction) at several SDK
versions, extract every named function from the objects, and match against our
ROM with `symbol_transplant`'s skeleton and matcher UNCHANGED — one definition
of "matches". Relocation holes in unlinked objects are the same fields the mask
zeroes, which is why object-vs-ROM comparison works at all. The era is decided
by VOTE — whichever version recovers the most of our 57 already-named functions
— never by assumption.

**The finding it encodes (A444): S&P's libultra is the GCC build, not IDO.**
The IDO oracle diverged at word 0–2 in every C function while all assembly
matched; the fingerprint is `lui+ori` address construction and `v0` scratch
(GCC) versus `%lo`-folded loads and `t6/t7` (IDO). `TARGET=libgultra_rom` is
the one that matches — 178 exact-unique at 2.0K against 20 for the best IDO
build. **Run the GCC target first for anything Treasure.**

**Controls — and the FIRST set was worthless, which is the part to remember.**
Three deliberate breaks (regex loosened, extraction shifted 4 bytes, masking
skipped in `oracle_side`) ALL PASSED the original self-check: one break was
masked by the size gate, one kept every masked JAL valid, and one broke a
function no control exercised. T100's rule — a checker that finds nothing on
day one is suspect — applied to the controls themselves. The rebuilt set: C2
feeds the regex a crafted `*UND*` row with a NONZERO size; C3 pins the RAW
prologue/epilogue words of a known function, which catches a shift of any
size; C4 compares `oracle_side`'s hash to an independently computed one, so
the production path is exercised end to end. All three breaks now caught.

    make -C ~/Documents/reference-recomps/ultralib VERSION=K TARGET=libgultra_rom COMPARE=0
    scripts/ultralib_oracle.py --versions I J K L --target libgultra_rom
    scripts/ultralib_oracle.py --self-check

---

## `symbol_transplant.py` — borrow the Mischief Makers port's function names (added 2026-08-25, A440/A441)

**Purpose.** T197 phases 0–1: verify our MM ROM against the other port's
documented SHA-256 (it REFUSES on mismatch — their addresses are
revision-specific), skeleton-hash every named MM function and every function of
ours, and accept only matches that are exact on masked words, same length, and
**unique in both directions**. `--emit` writes the inferred-name view
`symbols/inferred-names.toml`; **RecompiledFuncs is never touched.**

**What its first run established (A440).** Exact instruction-level matching
across the two games is dead: MM ships a different build kind of libultra —
its C functions run 1.4–4× longer for the same routine — so only hand-written
assembly survives. Yield: 3 new CP0 accessor names, plus a three-way mislabel
in OUR map caught by the blind holdout (A441). **Do not re-run phase 1
expecting more; phase 2 (call-graph shape) is the only surviving route and
needs the still-owed negative control first.**

**The mask, so a match means what it claims:** J/JAL targets and the imm16 of
LUI/ADDI/ADDIU/ORI and all loads/stores are zeroed; registers, branch offsets
and ANDI/XORI/SLTI immediates are kept. The self-collision census prints for
both sides every run — small functions collide heavily (530 shared hashes on
our side) and the both-ways uniqueness rule is what absorbs that.

**The drift yardstick (A441), worth reusing:** a TRUE assembly pair across
these two SDK releases differs by exactly one word — the `or`-vs-`addu`
encoding of `move` — measured on the known-correct `osInvalICache` pair.
Anything at or below that drift is the same function; C-compiled code sits
nowhere near it.

**Controls — 5, each break caught by a different one.** C1 the mask hits
exactly the claimed fields; C2 an address-half difference must collapse; C3 a
register difference must survive; C4 a duplicate-source match must come back
ambiguous, never accepted; C5 two sections at one vram must extract from their
own ROM bases. **C5 caught its own fixture first** — `bytes(range(256))*64` is
periodic and the two ROM bases were congruent mod 256, so both sections read
identical bytes. Third fixture bug in three days (dup_draws C4, gap_classify
C5): a control is only a control if the fixture means what it claims.

    scripts/symbol_transplant.py --dry-run
    scripts/symbol_transplant.py --emit symbols/inferred-names.toml
    scripts/symbol_transplant.py --self-check

---

## `ledger_graph.py` — the ledger as a graph, and its cycles (added 2026-08-25, A439)

**Purpose.** Read `docs/findings-ledger.md` as a directed graph — an edge from A
to B when B's ID appears in A's row — and find the cycles. **User-requested.**
`--cycles` expands them, `--json` / `--layout-json` feed a viewer, `--dot` emits
graphviz, `--layout-png` renders the layout so it can be looked at.

**What it is for.** Entries are written in order, so the graph should be a DAG,
and it is: **back edges alone produce zero cycles across all 648 entries.** Every
loop comes from a retroactive edit or from a cross-series reference. The
back-edges-only run is the standing control — if it ever stops being a DAG,
entry numbering has stopped meaning what every tool here assumes.

**It uses `ledger.py`'s parser and asserts its edge rule matches `ledger.py`'s
CITES footer** (control C6, on a real entry). A second definition of "cites"
would let an entry be linked for one reader and not the other — T185, T187 and
T193 are three instances of state living in two places with nothing checking
they agree, and this would have been a fourth.

**IT IS A MENTION GRAPH, NOT A DEPENDENCY GRAPH.** An edge means one row
contains another's ID, which includes "do not confuse this with A161" and bare
withdrawal notices. The CITES footer has always had this property; this
inherits it whole and must not be described as anything stronger.

**The layout is computed in Python, not in the browser, and that is a
correctness decision.** The first build simulated in the page — and the preview
pane does not composite, so `requestAnimationFrame` never fired and **the layout
could not be inspected before publishing**. `--layout-png` renders it so a
person can look. Deterministic: no clock, no RNG, phyllotaxis seed.
**For a picture, the control is a picture.**

**Controls — 6, varying the failure mode.** C1 must find a 3-cycle exactly, C2
must not invent one in a DAG, C3 must keep two disjoint cycles apart, C4 must
not call a self-reference a cycle, C5 must classify a cross-series edge as
`cross` rather than retroactive, C6 must agree with `ledger.py`. Four deliberate
breaks — reporting singleton components, merging all components, treating cross
as forward, truncating the text scanned — each caught by a different control.

    scripts/ledger_graph.py --cycles
    scripts/ledger_graph.py --layout-png /tmp/g.png --view small
    scripts/ledger_graph.py --self-check

---

## `dup_draws.py` — is the game asking for the same thing twice? (added 2026-08-25, A437/A438)

**Purpose.** Count duplicate draws *inside one submitted frame*, offline, from
`dl_render.py --json-all` output. Two definitions, deliberately: **EXACT** (same
geometry in the same place) and **SHAPE/SIZE** (same geometry somewhere else).
They mean opposite things — an exact overlap is invisible, a displaced copy is
the visible clutter A219 is about.

**The incident that motivated it.** Queue row U2 asked the user to truncate a
tutorial frame with RT64's `View Draw Call` and report whether duplicate overlay
copies appear one-per-index. It sat SHELVED from 2026-08-22 because A316 found
every slider setting produced no visible change. **The offline replay is a
strictly better instrument for that question and the reason is structural: it
draws into an EMPTY image, so a duplicate seen there cannot be residue.** The
slider truncates into the game's own never-cleared buffer (A304) and could never
separate the two. A queue item can outlive the instrument it names.

**Read the RECTANGLES, not only the triangles.** The first version counted
triangle sub-lists only and reported the tutorial essentially clean. Overlay
elements on this hardware are usually `G_TEXRECT`, and there are 56–93 rectangles
per tutorial frame. **Every non-null result in A437 and the whole of A438 come
from the half that was nearly omitted** — a scoped negative one step from being
published as a general one.

**Controls — 8, varying the failure MODE per A261.** C1 exact copy must fire,
C2 a clean frame must stay silent, C3 a translated copy must classify as
shape-not-exact, C4 a same-count different-proportion sub-list must stay silent;
C5–C8 repeat those on the rectangle path and add kind-sensitivity (a fill and a
texrect of the same box are different commands). **Six deliberate breaks, each
caught by a different control** — exact signature losing position, shape
signature folding to a count, grouping by index, rect signature losing position,
rect signature losing kind, and rects skipped entirely.

**C4 caught its own fixture first.** The injected sub-list was a same-size
triangle at a different position, which *is* a shape duplicate, so the detector
was right and the control read as a detector failure. **A control is only a
control if its fixture means what it claims** — the same trap as C5 in
`gap_classify.py` below, two days running.

**SCOPE, inherited whole from `dl_render.py`.** This is what was *submitted*. A
duplicate submitted and then z-rejected is still counted here.

    scripts/dl_render.py <log> --json-all frames.json
    scripts/dup_draws.py frames.json --task 5400 --verbose
    scripts/dup_draws.py --self-check

### `make_dl_viewer.py` — the same frames, stepped by hand

**Not a measuring instrument and it must not be cited as one.** It builds a
self-contained HTML page from the same `--json-all` export: pick a frame, drag a
slider, watch the draws stack up one at a time with a software z-buffer, toggle
scene / screen-pinned / other geometry and rectangle outlines. **Its output is
the USER'S reading, which is why it exists** — A428, A429 and A430 are all
things the user saw in it, and two of them corrected me. **Caught by
`lint_tools.py` as undocumented on 2026-08-25, one checkpoint after it was
written: T71 gate 3 says the write-up happens in the SAME checkpoint, and it
did not.**

---

## `gap_classify.py` — where a symbol really ends, read off the ROM (added 2026-08-25, A419)

**Purpose.** T11 step 2: decide, for each unclaimed gap between two function
symbols, whether the earlier symbol is TRUNCATED or the gap is something else.
It reads the gap's bytes out of the ROM and counts exits, which is what A292
did by hand for one function. **It is the only route to this question that does
not pass through splat**, and A259/A281 established splat is guessing here.

**The incident that motivated it (A261).** Two structural rules were built for
this and both were killed:

* **Rule 1**, first `jr $ra` scanning forward, ran past the next symbol and
  **borrowed a neighbour's return** — 172 of 251 flagged, not credible.
* **Rule 2**, "returns inside its declared size", assumed every function ends in
  `jr $ra`; `ovlfile07_func_800E4780` does not.

**Both passed all four of A261's controls, because all four were the same
shape** — a truncation, flagged or not. *Four controls that vary only in the
answer are one control.*

**So the controls here vary the failure MODE, in both directions:**

| | must | why it discriminates |
|---|---|---|
| C1 L1 `ovlfile02_func_800E4F34` @ old `0x14` | FLAG | recorded truncation, the START crash |
| C2 L7 `ovlfile20_func_800E5634` @ old `0x54` | FLAG | recorded truncation, the attract freeze |
| C3 A292's `ovlfile07_func_800E4780` @ `0x40` | FLAG | proven by hand, splat-independent |
| C4 a real all-zero gap | **NOT flag** | over-flagging mode |
| C5 a real successor fed in as a gap | **NOT flag** | over-flagging mode — kills rule 1 |
| C6 both predicates vs `objdump` | agree | the decoder is hand-rolled (T60/T62/T63) |

**C5 HAS A TRAP AND I FELL IN IT FIRST TIME.** The predecessor in the fixture
must be one that **NEVER RETURNS**. With a returning predecessor, a
forward-scanning rule declines to flag anyway, so the ordering bug hides and
the control passes for the wrong reason — it went green against a deliberately
broken build. T44 measured 138 legitimately non-returning functions, so the
right fixture is easy to find. **The fixture search uses literal encodings, not
the module's own predicates**: a search built on the thing under test reports
"no fixture found" when the predicate breaks, hiding a wrong verdict behind a
missing case.

**Verified to FAIL, not merely to pass** (T71 gate 2): three deliberate breaks
— dead return predicate, dead prologue predicate, and CONTINUATION tested
before SEPARATE (rule 1's exact defect) — **3/3 caught**.

**Read the scope line it prints, and mean it.** A CONTINUATION says the sole
exit sits at the next symbol. **It does not prove the extent.** Exactly one of
the 92 current hits is proven (A292, by hand). Before editing any `size` in
`symbols/sinpunishment.syms.toml`, do the per-function read — the gap says
bytes are unclaimed, not that they belong to this function.

**Known hole, stated because it is the composing step:** `j`, `jal` and
`jr $ra` are counted; **`jr` on a register other than `$ra` is not.** A region
whose functions all exit that way would read as one long function.

---

## User-observed runs — the two things I cannot check myself (added 2026-08-20, T101)

**Standing policy, user-set:** a run the user watches **daily on any day work happened**, and
**immediately whenever anything observable changes.**

### The two gaps, and they are different

1. **I CANNOT PERCEIVE AUDIO AT ALL.** The capture pipeline's ffmpeg invocation has no
   audio input — **every recording this project has ever made is silent by
   construction.** A97's current state is *"audio silence only"*, and every claim
   in it comes from reading source. Ten seconds of listening outranks all of it.
2. **Scene identity has been wrong twice** (A93, A161), both times with the
   observation right and the **quantifier** wrong — sampled instants silently
   became "never". Sampling cannot support a claim about the moments it did not
   sample; continuous watching can.

### Why xephyr and not real

`xephyr` shows a real window but keeps **input isolated**. `real` has no isolation,
and on 2026-08-19 four debugger runs put a live game window on the user's desktop
with the keyboard attached (T59). **An observed run must be SEEN, not unprotected.**
A control asserts the default and fails if it is changed to `real`.

### The progress trigger is MECHANICAL, deliberately

"Seeming progress" judged by the party whose claims are being checked is worth
nothing. It is computed from `run-log.tsv`: a run that asked for more than the
known crash time and did **not** return 139 either survived the crash point or
broke — **both need a human.** A normal crash and a short run stay quiet, and a
control asserts all three directions.

### The daily trigger is gated on work

A calendar nag on a day with no work is ceremony — T100 records that exact defect
in L2's trigger. It is worse here because **this one spends the USER's time**, and
a policy that wastes it gets abandoned (T29).

### Audio IS recorded now, and only the game's (T102)

Recording the default sink would pick up whatever else the machine is playing —
the same class of problem as filming the user's desktop (T83). **A capture that
can pick up the user's audio is not acceptable even once.**

**Two designs were tried and MEASURED to fail before the third worked** — `pw-record --target` against the app's stream node, and against a null sink's
monitor, both captured **silence (peak 0)**. The working shape: load a dedicated
null sink, **move ONLY the game's sink-input into it**, loopback its monitor to
the real output so the run stays audible, and `parec` that monitor. The move is
what makes it private — **the monitor can only contain what was moved in.**

**The control discriminates:** two tones, one moved in, one left out. Moved-in
**1.000**, left-out **0.0000**; and routing the second app in as well takes the
left-out reading to **0.9181** and fails the control. A capture that grabbed the
whole machine would pass a naive "did we get audio" test and fail this one.

**A waveform still cannot tell me whether something sounds WRONG.** The capture
makes the answer outlive the run; it does not replace the user's ears.

### The old note, kept because the reasoning still applies elsewhere

Capturing system audio would record whatever else the machine is playing — the
same class of problem as filming the user's desktop, guarded since T83.
Per-application capture is the safe form and is **not built**. Until it is, the
user's ears are the only instrument, so the answer must be written down.

```bash
scripts/observed_run.sh --self-check   # 8/8
scripts/audio_capture.sh --self-check  # 4/4 (isolation + finalize)
scripts/observed_run.sh --checklist    # print the list, run nothing
scripts/observed_run.sh 180            # the real thing
```

---

## `status_page.py` — the user-facing status page (added 2026-08-24, T183)

**Purpose.** External visibility, so knowing where the project stands does not
depend on reading back through a chat. The user's framing set the design: make it
useful *for making them useful to the project*.

**So it is sorted by ACTIONABILITY, not by category.** Top of the page is what they
can do right now; the bottom is trend data.

**The split that earns its place is SETUP COST, not count.** The user-queue alarm
counts items, and items are not comparable — some need a real display, a launch and
three minutes of watching; others are ten minutes at a desk with nothing running.
**That distinction decides whether they can act right now and it appears nowhere
else.** It is the first thing on the page.

**Generated, never hand-edited.** Every figure is read from a live file at
generation time and the page stamps when it was made, so a stale one is obvious
rather than quietly wrong. A hand-maintained second copy of project state is
exactly the kind of duplicate this project already has a standing rule against.

**8 controls**, including two that matter beyond correctness: the page must contain
no external references (the artifact CSP blocks them, and a silent fallback would
be worse than a visible failure), and ledger text must be **escaped** before it
reaches the page — entry bodies are full of markup and angle brackets.

**Republish to update:** the URL is stable as long as the same file path is
republished from a conversation that has the URL.

```bash
scripts/status_page.py --dry-run
scripts/status_page.py /tmp/status.html    # then publish that file
scripts/status_page.py --self-check        # 8/8
```

---

## `ideas.py` — ideas raised and not acted on (added 2026-08-23, T182)

**The failure it closes.** Three things from one week reached no file at all: a
reading list the user asked for, the calibration idea, and two sub-agent sweeps
already scoped and cleared. The pattern was exact — **everything unrecorded was
something I SAID, not something a tool produced.** Tool output reaches the ledger
because the workflow puts it there. A remark in conversation has no such path.

**The standing permission (user, 2026-08-23):** any idea raised gets written here
**immediately, without asking**. Recording is cheap and reversible. *Acting* still
goes through the roll for project work, or an explicit ask for anything expensive
or irreversible — and keeping that distinction safe is exactly what this file is
for.

**Not the backlog.** `backlog.py` holds small **owed** jobs and refuses anything
that cannot say why it is owed, deliberately, so it cannot become a wish-list. An
idea is not owed. Putting ideas there destroys the one property that makes the
backlog usable.

**Why it is NOT daily**, and this was the user's objection when it was proposed:
this project already carries enough recurring work and another daily item would
add to the mass. So it fires on a **threshold (6 open) and goes quiet once swept**
until 4 more accumulate — the shape `calib.py --due` uses. T118 measured a 6-of-7
noise rate on a nag that fired regardless of having anything to say.

**Both fields are mandatory and both refusals matter.** `add` refuses an idea
that does not say *why it was not acted on* — an idea with no stated reason is one
that was simply forgotten, which is the failure this exists for. `close` refuses
without saying what was **decided**; dropping an idea is a fine outcome and still
needs a reason, because an idea closed silently cannot be told from one never
considered.

9 controls, including the threshold in four directions: silent below, fires at
threshold, silent once swept, fires again after real growth.

```bash
scripts/ideas.py                      # open ideas
scripts/ideas.py add "<idea>" "<why not acted on>"
scripts/ideas.py close IDEA3 "<what was decided>"
scripts/ideas.py --due / --mark-read
scripts/ideas.py --self-check         # 9/9
```

---

## `calib.py` — confidence, recorded and then SCORED (added 2026-08-23, T179)

**The gap.** Every load-bearing entry carries a falsifier — what would prove it
wrong. That says how to *check* a claim. Nothing said how *sure* I was, and
nothing scored that against what held. So a confidently wrong claim survived
until a roll happened to revisit it, which is luck. Five instances in one
session; **three were surfaced by the user asking a question, not by any check.**

**Calibration is not accuracy.** Saying 70% and being right 70% of the time is
perfect calibration with a mediocre hit rate. The forecasting result that makes
it worth building is that calibration improves with scoring and drifts silently
without it — and expertise tends to make it *worse*, because confidence rises
faster than accuracy.

**The field**, in any entry making a checkable claim:

    CONFIDENCE: 0.8 — that the census interval is the only cause

**Three honesty properties, each with a control verified to fail:**

1. **Forward only, never retrofit.** Assigning a confidence to an entry whose
   outcome is already known is hindsight and would manufacture perfect
   calibration from nothing. The table starts empty and says so plainly rather
   than showing an empty result that looks like a finding.
2. **The unscored count is reported as loudly as the scores.** Most entries here
   are never revisited, so the scored set is biased toward claims that turned out
   interesting or wrong — the wrong sample. A calibration figure without its
   denominator is worse than none.
3. **A number, not a word.** "Likely" cannot be scored; the parser refuses it.

**`--base-rate` reports two numbers and tells you which to use.** 32.5% of
entries are revisited with a correction-flavoured word; **12.6% have a status
that says they went wrong.** The first is an over-count — the shared
supersession test matches "closed by" and "vindicat", so an entry that was
*answered* counts the same as one that was *refuted*. Reporting it as an error
rate would be the exact failure this tool exists to prevent.

**It asks to be read, and then goes quiet.** `--due` fires only when there are
**20 scored claims across at least 2 confidence bands** — the second condition
is the one that matters, because calibration is a comparison *between* bands and
a pile of claims all at 0.9 says nothing at all. 20 is measured rather than
chosen: 33 entries/day at a 44% settle rate is ~14 scored per day, so 20 is
about a day of ordinary work. `--mark-read` silences it until it grows by
another 20. Four controls: silent below threshold, silent when all one band,
fires at threshold across two, silent again once read — and verified to fail on
the middle two.

**`check_ledger.py` asks at write time**, on entries that already carry a
falsifier — inheriting this ledger's own marker for "checkable claim" rather
than inventing a second one. A note, never a gate.

```bash
scripts/calib.py                # the table + the unscored count
scripts/calib.py --base-rate    # the prior, with the over-count named
scripts/calib.py --unscored
scripts/calib.py --self-check   # 8/8
```

---

## `qty.py` — measure the quantity, do not recall it (added 2026-08-23, T177)

**The failure.** I described something **four days old** as "months of
checkpoints ago", twice, unhedged, on a project **ten days old**. The user caught
it. Nothing in the apparatus could have: every entry carries a falsifier, which
says what would prove a claim wrong, and a claim about elapsed time is not what
falsifiers are aimed at.

**The cause was not ignorance.** 554 entries, 230 rolls, 515 commits and ~12,000
lines of tooling *feel* like months. I substituted the felt duration for the
measured one — the same substitution as quoting "GAME 9 / STACK 5" from memory
when recomputing gives 7:5 with two entries contested.

**The rule, deliberately smaller than the calibration ledger it replaces:**
> **A claim about a quantity gets the quantity MEASURED at the moment it is
> stated** — not recalled from an earlier entry, not estimated from a sense of
> how much has happened.

**Both halves are wired, because a rule with no checker is a preference:**

* **`qty.py` removes the excuse.** `age`, `since <ID>`, `between <A> <B>`,
  `counts`. Every number one command away. 5 controls, including one asserting
  the real ledger spans under 60 days — the exact claim that was got wrong,
  checked against live data.
* **`check_ledger.py` catches the lapse.** Flags vague duration language *about
  our own history* and points here. Narrow on purpose, and tested in four
  directions: fires on an assertion, **silent when the phrase is quoted** (T177
  records the failure by naming it), **silent about the game's own development**
  ("months in 1999" is legitimate), fires on other units.

**It found three more instances on its first run** — beyond the one the user
caught — in A360, A372 and A242. All three were corrected with measured figures:
four days, three days, and "earlier in the same week". **A checker that finds
nothing on day one is the suspect kind (T100); this one surprised us
immediately.**

**One imprecision, labelled rather than hidden:** `since <ID>` reports the first
roll number in the row, and a correction prefix can put a *later* entry's roll
first. The output says so. The day count is exact and is what the rule needs.

```bash
scripts/qty.py                  # age + counts
scripts/qty.py since A179       # 4 days ago, roll #102 of 230
scripts/qty.py between A92 A365
scripts/qty.py --self-check     # 5/5
```

---

## Parking an item is a ONE-WAY DOOR unless something watches it (added 2026-08-23, T175)

**`AWAITING THE USER` takes an item off the frontier** so the router stops
selecting work nobody can do. It is the right mechanism and it was used twice.

**Nothing watched either of them.** A grep for `AWAITING` across every script in
`scripts/` returned **zero hits**. Both parked items depended on someone
remembering to bring them back — and T28 is the standing finding that every
discipline left to memory on this project has been forgotten. T122 is the same
shape: *a queue nothing forces you to empty is a way of feeling like you dealt
with something.*

**What the check found the moment it existed:**

* Neither parked item **named the queue item it waits on**. One said in prose
  "re-opens the moment they name tiles" — and the queue item that means was
  sitting right there, unnamed and unreadable by any tool.
* One was **not awaiting anything at all**. The user had *decided* it (hold the
  screenshots) and the status cell still read `AWAITING`, so a closed decision
  was parked as pending work.

**So the rule is: parking requires a named way back.** `check_ledger.py` now
flags a parked item that names no queue item, and flags one whose queue items
are all `SWEPT`/`DROPPED` — that is the moment to reopen it.

**The test asserts three directions, and the first version did not.** It began
as a check that the right *strings existed in the source*, which passed happily
with the logic disabled. Rewritten to run the checker against synthetic ledgers:
fires with no blocker, **silent with a live blocker**, fires when the blocker is
finished. Verified to FAIL when the check is disabled — the break was applied to
the real file and the tree restored byte-identical, confirmed with `cmp`.

**A presence check is not a behaviour check.** That is the third time in three
days something has passed by matching text where the subject was meant.

---

## `scene_timeline.py` — what happens WHEN, without comparing pictures (added 2026-08-24, A380)

**PURPOSE.** Turn a recording into a list of scene segments, so our run and the
reference can be compared as SEQUENCES rather than as images. A379 established
why that matters: cross-emulator frame matching works only for still,
distinctive screens, because two runs are at different MOMENTS of the same
motion. A boundary is an event inside ONE recording, so the renderer difference
never enters.

**THE OBVIOUS SIGNAL WAS TRIED AND FAILED — MEASURED, NOT ASSUMED.** Distance
between consecutive frames is the natural cut detector. On the reference its
histogram over 601 frames runs **smoothly from 0 to 43 with no valley**: the game
is always moving, so there is no quiet baseline. Any threshold off that
distribution is the operator choosing the answer. `--dry-run` still prints it so
the absence of a valley is visible.

**WHAT WORKS IS FADES TO BLACK**, which A164 had already measured at the
title-to-tutorial transition. Six well-separated black runs against a brightness
range of 0-244. **A black frame is black — there is no parameter to tune.**

**THE BLACK IS A BOUNDARY, NOT A SCENE.** A four-second fade is not four seconds
of content, so segments are the LIT stretches between runs.

**CONTROLS (`--self-check`, 7).** A synthetic three-scene video with 1-second
fades, so the answer is known independently. Two are controls in the strict
sense: one asserts the DISTANCE method finds every transition on that easy
fixture — which is what makes "it failed on the reference" a claim about the
CONTENT rather than about a broken implementation — and one asserts a badly
chosen threshold gives a WRONG answer, so the fixture is known to discriminate.

**KNOWN LIMITATION, PRINTED ON STDERR RATHER THAN BURIED.** `--compare` aligns
index against index. **If one run is missing a segment, everything after it
shifts and every later row reads as a mismatch that is not one** — which is
exactly what happened on its first real use. It says so loudly when the segment
counts differ. An insert/delete-aware diff is not implemented.

**WHAT A BOUNDARY IS NOT.** A fade is where the game pauses, not necessarily
where a scene ends — a death, a wipe or a loading pause look identical. A
transition with no fade is invisible to this entirely.

---

## `ares_register.py` — find the game inside an ares capture (added 2026-08-24, A377/A378)

**PURPOSE.** An ares recording made by `ares_capture.sh` contains the whole
isolated display — **menu bar, viewport, status bar**. Anything that measures
"the content area" of such a frame measures the WINDOW. This finds the viewport
and emits a crop that registers it to our 640x480.

**THE INCIDENT THAT MOTIVATED IT (A376).** I measured the content region of an
ares frame, got 768x622 at aspect 1.2347, could not explain why it was not 4:3,
and **asked the user to re-capture with different settings.** The answer was
that I had measured the window. **Two statistical passes ran before I looked at
the image, and the image explained it in one second.** Look at the frame first.

**THE METHOD.** The viewport is what MOVES between frames; chrome is static. It
takes the **largest CONTIGUOUS band** of motion — not the outer bounds — because
the status bar carries a live VPS counter that moves too. That one distinction
is the whole tool.

**THE GEOMETRY IS MEASURED, NEVER HARD-CODED, AND THIS IS NOT FUSSINESS.**
A377 derived `crop=711:535:264:76` for one recording. It depends on ares' output
mode, window size and Overscan setting — the user changed two of those the same
day. A tool carrying that constant would keep running and register the wrong
region in silence.

**CONTROLS (`--self-check`, 4).** Synthetic frames with a KNOWN viewport, so the
answer does not come from the code agreeing with itself. One is a control
**verified to fail**: it runs the naive "any row that moved" rule on the same
fixture and asserts that it really does swallow the status bar. If that ever
passes, the fixture has stopped proving anything. A fifth check on real data:
run `--dry-run` on the 2026-08-20 reference and it must return x=264 y=76
711x535, which was derived independently by hand.

**A DRY RUN THAT TOUCHES NOTHING** — `--dry-run <video>` measures and prints,
and **warns on stderr if the band it found is not within 5% of 4:3**, because a
non-4:3 answer means it has found something that is not the game and the crop
must not be trusted.

**WHAT IT DOES NOT DO.** Registration makes the two images the same SHAPE, not
the same PICTURE. A377's floor stands: two genuinely different scenes from our
own build are 14 bits apart under dHash, so any cross-emulator distance at or
above that is noise. A378 names four ares settings that add deliberate
differences and can be switched off; the incidental ones cannot.

---

## `audit_misses.py` — did the audit catch the things that went wrong? (added 2026-08-23, T172)

**Purpose.** `audit.py` has no `--self-check` (T171). Writing it one is the
obvious fix and it is **the trap**: a control written in the same sitting, from
the same reading of the same source, by the same reader, inherits whatever that
reader misunderstood. That is why T153's control was VOID and why the agent
brief says to seed a control from ground truth, never from one's own prior
source reading.

**So this invents nothing.** The ledger already holds the experiments: entries
that were later withdrawn, corrected, refuted or scope-flagged. Each is a fault
that really happened, in a real window. The only question per entry is whether
an audit flagged it.

**Three verdicts, and the middle one matters:**

| verdict | meaning |
|---|---|
| `CAUGHT` | flagged, and the flag names the thing it was wrong about |
| `CAUGHT-OTHER` | flagged for a *different* reason — right by accident, not a catch |
| `MISSED` | no audit ever flagged it |

**What it deliberately refuses to decide:** whether a `MISSED` entry was
*catchable*. That turns on whether the fault was visible at the time or only
became visible when a later measurement contradicted it — and it is exactly the
call the author of both the mistake and the checker must not make alone. It is
`--sitting` output, for a human.

**Two defects were found by reading its own output rather than its code**, and
both are recorded because both are instructive:

* **It matched vocabulary, not subject.** The first version swept in 30 entries
  that were *doing* the correcting — A156 corrects A154, A177 refutes A176's
  suspect, T57 is a method entry about withdrawals — plus A97, whose cell merely
  says "Superseded costing follows". **A358's failure exactly.** Population fell
  81 → 51 once the marker had to *govern* the cell.
* **A control that could not fail.** Deleting the VOID-audit exclusion left the
  suite passing 9/9, because both real VOID blocks carry zero flag lines, so no
  control over the real file could ever discriminate. Closed by **injection** — a
  synthetic log whose VOID block does carry a flag. Found by running the break,
  not by reading the code (T65/T71 gate 2).

**11 controls, verified to FAIL:**

| break | controls that fired |
|---|---|
| count VOID audits as real | 1 — the injected case |
| drop flag reasons, keep ids | 3 — reason kept, known catch, all-three-verdicts |
| loosen the subject test to a word-search | 1 — the named negative control |

The named negative control replaced a "<25% of the file" size check that the
loosened matcher passed anyway — **a threshold is not a control if the failure
it is meant to catch slips under it.**

```bash
scripts/audit_misses.py             # the table
scripts/audit_misses.py --sitting   # only rows needing a human call
scripts/audit_misses.py --dry-run
scripts/audit_misses.py --self-check   # 11/11
```

---

## `eaf_read.py` — the user's annotations, readable by a tool (added 2026-08-22, T150)

**Purpose.** T101 settled time-aligned annotation as the return path for the two
things I cannot check: I cannot hear audio at all, and scene identity has been
wrong twice from my own sampling. The user marks spans on a recording in ELAN.

**The incident.** A266's `.eaf` has sat on the archive since 2026-08-21 and
**nothing could read it.** Its content survived only because I transcribed it by
hand into A266 at the time. T160 did the slice that made a reader possible — the
observed run now records *which* video and *which* audio file — and named this
as the remainder: "the recording is not served up for annotation, no `.eaf` is
read back".

**The control is the real tool's real output.** `--self-check` runs against
`evidence/2026-08-21/run_game-135748.eaf`, a file ELAN itself wrote on this
machine — **not a fixture written by whoever wrote the parser.** That matters
because a fixture can be wrong in the same direction as the author's reading of
the format, which is T100's standing complaint about controls that cannot
discriminate. Expected content is asserted **by value**: 8 time slots, 4
annotations at 140-6980, 6980-7230, 21000-32400 and 155600-182367 ms. A parser
returning plausible nonsense passes a shape check and fails this.

**Second, independent check:** the reader's output matches A266's hand
transcription word for word. Tool and human agree on the same file.

**10 controls, verified to FAIL:**

| break | controls that fired |
|---|---|
| transpose `TIME_SLOT_REF1`/`REF2` | 2 — exact spans, and every span running forwards |
| stop disclosing declared-but-empty tiers | 1 — the disclosure control |

**Two refusals rather than empty returns.** A document with no annotations, and
an annotation referencing a time slot that does not exist, both **raise**. A
reader that returns `[]` on a malformed file is indistinguishable from one
reading a file the user deliberately left blank, and those mean opposite things.
Unresolvable references are reported, never defaulted — the same rule the census
walker follows for segments.

**An empty tier is NAMED, never omitted**, and this is the control worth keeping:
`audio` is the return path for the one thing I cannot check at all, so a silently
absent tier and a tier the user left blank would look identical in the output.
Same rule as T76 — hide content, never existence. **Building this is how A362
found that `scene` and `audio` have never carried a single annotation.**

**Times come out in seconds as well as milliseconds**, because every other
instrument here speaks in seconds and an annotation that cannot be lined up
against a run log by eye is still write-only in practice.

```bash
scripts/eaf_read.py <file.eaf>              # annotations, time-ordered
scripts/eaf_read.py <file.eaf> --tier audio
scripts/eaf_read.py <file.eaf> --dry-run    # print, read nothing
scripts/eaf_read.py --self-check            # 10/10
```

---

## `away.py` — hold the eyes-needed flags, with a mandatory expiry (added 2026-08-22)

**Purpose.** Two checks here spend the USER'S time, not mine: the observed-run
gate (T101), which `route.py` cannot clear without them, and the user-queue
reminder (T131), which nags until the queue is swept. Both are worth having.
Neither is worth anything while the user is not at the machine.

**The incident.** 2026-08-22, the user's own words: away from the PC until
Monday, cut the flags until then. At that moment the queue alarm had been firing
for two days with four items and six entries waiting on it, and the observed-run
gate would have demanded a `--defer` reason at every roll across the weekend.

**How it works, and the one design decision that matters.** It does **not cut a
hole in the gate.** The gate has always accepted a recorded deferral, because
the rule is *"the run was not SILENTLY skipped"*, never *"the run happened"*. So
`away.py` supplies the deferral REASON automatically: every skipped day still
gets a dated, reasoned line in `observed-runs.md`, **written on the day**. The
audit trail is unchanged; only the asking stops. Monday still owes exactly ONE
run, not three — T151, the user's rule, and this does not touch it.

**Three properties it is built around, all previously paid for:**

* **The expiry is mandatory.** `set` refuses without a return date. A silencing
  with no end is a deleted safeguard with extra steps, discovered months later
  by its absence.
* **It hides content, never existence (T76).** Both channels still print one
  line naming what is held and when it returns.
* **Every failure means NOT AWAY.** Missing file, corrupt JSON, unparseable
  date, empty reason — all read as *flags fire*. A bug here must fail towards
  nagging, because silence is invisible and nagging is not.

**The controls, and which of them can fail.** 16/16, and **verified to FAIL
when broken**, not merely to pass when working:

| break | controls that fired |
|---|---|
| expiry never triggers (`if False`) | 3 — away on the return date, away after it, banner still printing |
| corrupt/missing read as AWAY | 3 — the two fail-safe controls plus the banner |

The discriminating triple is *away before the date / not away ON it / not away
after*: a stub returning always-True passes the first and fails both others, and
always-False does the reverse. Neither can pass all three.

`test_route.py` carries four more, asserting the WIRING rather than the module:
the away branch must write `## DEFERRED`, must hand back to the same gate rather
than jump past it, must fail towards asking, and must leave exactly one refusal
in the file. Those four are what a "simplify it to `if away: skip`" rewrite
would quietly drop.

```bash
scripts/away.py                                    # status
scripts/away.py --dry-run set 2026-08-24 "reason"  # print, write nothing
scripts/away.py set 2026-08-24 "away from PC"
scripts/away.py clear
scripts/away.py --self-check                       # 16/16
```

---

## `backlog.py` — somewhere for leftover time to GO (added 2026-08-22, T161/T162)

**Purpose.** Three timed sessions on 2026-08-22 closed early — 21m36s, 21m22s
and 17m27s of 30m — and **the user caught it, not a control.** The reasoning
error each time was asking *"does the BIGGEST pending item fit?"* and stopping
when it did not. `session.py status` catches the stop; this gives the stop
somewhere to go.

**The risk, which the user raised themselves** ("or would that be
counterintuitive"): a backlog of tidy jobs is an excellent way to LOOK BUSY
while avoiding the expensive question. So the discipline is in code, not in
prose:

* **Frontier first.** `next` REFUSES to hand out a job while a full checkpoint
  (3 min, measured over six consecutive zero-run rolls) still fits. It is not a
  menu; it is what is left when rolling is not an option.
* **Owed, never invented.** `add` REFUSES an item that does not state why it is
  already owed — a count that drifted, a check not re-run since its script
  changed, a flag left unanswered.
* **Drainable.** An item that cannot be shown done or not done does not belong.

**The control that discriminates.** A backlog that never empties and one that is
never consulted are BOTH failures, and neither is visible by reading the file.
`--check` reports added against closed and the age of the oldest open item:
growth with no closures is a wish-list, no closures at all means the mechanism
is decoration. 11/11 controls, and the pair that matters is *`next` refuses at
10 minutes left / serves at 1* — an implementation that always served would pass
half of it.

```bash
scripts/backlog.py                      # open items
scripts/backlog.py next <minutes-left>  # a job, IF a checkpoint no longer fits
scripts/backlog.py add "<job>" "<why it is owed>"
scripts/backlog.py --check              # the added-vs-closed control
scripts/backlog.py --self-check         # 11/11
```

---

## `single-run` is asked at WRITE time now, not at audit time (added 2026-08-20, T99)

`single-run` is the defect class that will not die: **21 instances, and L2 #5 still
reports it recurring after every fix aimed at it.** A class that recurs after a fix
means the fix addressed an instance.

**The problem was never detection — `audit.py` has caught these all along.** It is
TIMING. The audit asks *"repeat it or say why one is enough"* days later, when
repeating a run is inconvenient and writing a justification is easy. So the same
question now fires from `check_ledger.py` at the moment the entry is written, while
answering it honestly is still cheap.

**Three ways to satisfy it**, and the message names all three:

* repeat the run and cite a second `.log`,
* say `2 runs` / `two runs` / `both runs` in the entry, or
* write **`ONE RUN IS ENOUGH: <reason>`** — a deliberate, greppable commitment.

**The predicate is `audit.py`'s, copied deliberately rather than reinvented:**
MEASURED/INTERVENED status, exactly one distinct `.log`, no plural-runs phrasing.
Two definitions of "single-run" would be worse than one, because an entry could
pass one checker and fail the other.

**Bounded by a high-water mark**, in `docs/.check-ledger-state.json`. Unbounded it
flags all 21 historical instances every run, and 21 permanent warnings bury the two
real ones (T29). **The first run on a fresh clone SEEDS the mark and deliberately
flags nothing** — which is why its control runs the checker twice; a one-shot test
would see "does not fire" and read it as a passing negative.

Controls verified to fail in both directions: exemption widened to always-exempt →
`fires=False`; plural exemption removed → fires on a legitimate 2-run entry.

---

## Regeneration: snapshot first, and never trust a successful link (added 2026-08-20, T115/T116)

**Two failures in one afternoon, both now mechanised away.**

`RecompiledFuncs/` is **untracked** — 137 generated files that are the product of
a generator *plus* repair passes. Regenerating destroys the previous tree with no
git baseline, and the binaries are overwritten in place. On 2026-08-20 that made
"is A99 fixed or masked?" **unanswerable**: there was nothing to A/B against.
`snapshot_build.sh` captures the tree, the inputs that produced it, both
binaries and a MANIFEST — ~94 MB, and the tree compresses 9x.

**Then: five repair passes exist and only two announce themselves.**
`fix_zero_writes` and `fix_dangling_gotos` fail as compile errors. `patch_si_stubs`
fails **silently** — without it the game never clears controller detection. The
binary linked, ran a full 180 s, and rendered **nothing** (`gfx_tasks=1`).

> **A pipeline where some steps fail loudly and others fail silently will always
> be run partially.** So it is one script, and it ends in a smoke test —
> because *"it links"* was exactly the check that passed on an inert binary.

```bash
scripts/regenerate.sh "why you are regenerating"   # snapshot -> regen -> repairs -> build -> smoke
scripts/snapshot_build.sh "reason"                 # standalone, before anything risky
scripts/snapshot_build.sh --list
```

**AND REGENERATION SHIFTS LINE NUMBERS.** After the 2026-08-20 regeneration,
`funcs_4.c:661` pointed at a different statement; the traced expression had moved
to `:659`. **A trace against a stale line number returns a meaningless zero that
looks exactly like a fix** — and this was nearly used to declare A99 fixed. Verify
every `file:line` by CONTENT and `info line` after any regeneration.

---

## Two rules that stopped being prose (added 2026-08-20, T111/T112)

**`SNP_HEARTBEAT` now defaults ON (T111).** It is the liveness signal the run
verdict is computed from, and **10 of 93 logged runs were recorded `UNKNOWN`
purely because nobody passed it** — a wasted verdict on a run already paid for
in wall-clock. It is **opt-out**: an explicit `SNP_HEARTBEAT=` still wins,
because `env` takes the last assignment of a name. The operator advice on an
`UNKNOWN` verdict changed accordingly — it now says this is a **real anomaly**
(missing hook, or the run died before emitting one), not a forgotten flag.

**T57's composing-step rule now has a checker (T112).** It was the project's
most-violated prose rule — written, cited in `CLAUDE.md`, violated at least
twice afterwards, most expensively in **A179**, where an address measured in one
run was matched against contents from a snapshot of another.

The heuristic is narrow: a `MEASURED`/`READ` entry whose **evidence cell names
artifacts from two or more distinct dates** is stitching across runs. That is
not automatically wrong — it is exactly the moment T57 says to name the stitch.

**Noise was measured before shipping (T29): across 296 entries it fires ONCE**,
on A161 — a withdrawn, user-caught entry of precisely this class. Withdrawn
entries are skipped, so it starts at zero standing noise.

Its control asserts four directions, and **one of them was vacuous on the first
attempt**: a bare `WD` test row never reaches the withdrawn check because the
`MEASURED|READ` filter skips it first, so removing the withdrawn-skip did *not*
break the test. The case now carries `WD as to cause — was MEASURED`, matching
what real withdrawn entries look like. **A control that passes for the wrong
reason is the fifth instance of that pattern here** — see T100.

---

## `ledger.py --chain <id>` — see the circle while it is happening (added 2026-08-20, T110)

Reconstructing A99's shape by hand took hours in the retrospective, and by then
the ~15 rolls were already spent. **This derives the skeleton in a second.**

It prints every entry in the target's chain, ordered by roll, marking those
carrying a correction verb — then reports the correction rate **twice**:

* **lifetime**, over the whole chain, and
* **over the last 15**, which is the one that triggers the warning.

**A lifetime average hides a circle.** A99's full chain averages 26%
corrections; its recent window ran 40%. Circles are *local* — averaging over
three days dilutes exactly the signal that matters. *"Am I circling?"* is a
question about now.

At ≥1/3 corrections in the recent window it prints the **impossible-result
rule** verbatim, because that is the moment the rule applies.

**Two design decisions, both paid for on the first run:**

* **It traverses the CORRECTION graph, not the citation graph.** The first
  version followed citations transitively and returned **267 of 296 entries**
  for A99 — true and useless. An edge now requires a correction verb within
  120 characters of the citation (same windowing principle as T48).
* **It is SEEDED with depth-1 citations of the target.** Correction edges alone
  stopped at roll #87 and missed A99's entire 2026-08-20 cluster, which
  investigates it without correcting it — the part a live reader most needs.

**It is a skeleton, never a narrative.** It says who corrected whom and when; it
never says what was established. Same rule as `--index`: read the entries.

**A third defect, and the most instructive: its verdict depended on `PYTHONHASHSEED`.** 271 of 302 entries shared a `(roll, date)` sort key, so ties resolved in set-iteration order, the last-15 window changed between processes, and the circle warning fired or not by chance. It surfaced as an **intermittent** self-check — 9/10 one run, 10/10 the next. **Any ordering that feeds a threshold needs a TOTAL key.**

Controls (11 total, 6 -> **11**), verified to fail: the **bound** (reverting to
citation traversal → `267 of 296`, FAIL), recency, warning **discrimination**
(forced always-on → fires on both → FAIL), and unknown-ID refusal.

```bash
scripts/ledger.py --chain A99
```

---

## `gdb_trace.sh --watch` — the instrument that needs no list (added 2026-08-20, T109)

**Every other mode here needs an enumeration** — of sites, of callees, of
writers — and A99's third circle is what enumeration failure costs. "`$s0` has
exactly two writers" was counted inside ONE function while `ctx` is per-THREAD:
**9,199 write sites exist, so the list was 0.02% complete**, and six
well-controlled experiments ran on top of it. A watchpoint catches a writer
**without anyone naming it first.**

**Why it needs an anchor.** `ctx` is a function parameter, so it is only in
scope inside a recompiled function; the address cannot be resolved cold. The
sequence is: arm late → break once at an anchor line → resolve `ctx` there →
`watch -l` (address fixed at that moment) → **delete the anchor** → continue.
Skipping the delete leaves the anchor stopping the inferior on every entry and
the run never reaches the fault.

**ARM LATE — this is the cost, and it is real.** gdb stops on *every* write to
that address to evaluate the condition. At arm=155 s the walker is entered ~15
times; at arm=1 s it is ~210,000. **This mode is for the last seconds of a run.**

**Its control is weaker than the other modes' and you must compensate.** A
conditional watchpoint's hit count only counts stops where the condition held,
so there is no free reach counter. Two substitutes, both printed:

* `info watchpoints` **immediately after creation** — an uninstalled watchpoint
  is the silent failure, producing a clean, empty, confident log;
* **run a POSITIVE CONTROL first** — watch for a value you already know occurs.
  A zero from an unvalidated watch condition means nothing (I1/I13).

Controls (in `test_gdb_trace.py`, 15 -> **19**), each verified to fail: script
generation; watch-after-anchor ordering (reordered → FAIL); anchor deletion
(removed → FAIL); the installation print; and the T47 log path.

```bash
scripts/gdb_trace.sh --watch funcs_4.c:228 'ctx->r16' \
  '((ctx->r16 & 0xFFFFFFFF) == 0x8013C270)' \
  'ctx->r16, ctx->r29, $_thread, ctx->r31' 155 360
```

---

## `lint_tools.py` — the inventory rule, checked instead of written down (added 2026-08-20)

**The incident.** T71 gate 3 says a new tool is not evidence until it has a
playbook write-up and a Tool inventory row. On 2026-08-19/20 **four tools were
built and none of them got either** (T89/T90), and separately two
state-mutating scripts had no `--help` (T37's exact failure). Both rules were
real, written down, and unenforced. Prose describing a discipline is not the
discipline.

Unlike the failure that dominates this project — a claim broader than its
evidence — both of these leave a machine-readable trace. That is the whole
argument for automating them: they are the cheap half, and the cheap half was
still being missed.

**What it checks.**

1. **A NEW script is named somewhere in the playbook** — anywhere, not only the
   inventory table, because several tools are best explained in the gate that
   uses them.
2. **A script that reads arguments has a help path**, checked *statically*.

**Why static, and this is the load-bearing design decision:** it must never
test `--help` by running it. A script that does not handle the flag would fall
through and **do its job** — for `route.py` that means consuming a routing
roll, for `run_game.sh` it means launching the game. A checker for "does this
mishandle arguments" that mishandles arguments is worse than none.

**The baseline is what makes it survivable.** Only 7 of 55 scripts appear in the
inventory table. Flagging all 48 would produce an alarm that always fires,
which is an alarm nobody reads by its second run. So it is bounded by a
baseline, the same trick `audit.py` uses: it reports what appeared *since the
last run*. The pre-existing backlog is **printed every run as context and
explicitly not counted as findings** — reporting a narrow set while implying a
broad one is the T90 defect, so the narrowing is stated rather than silent.

**Its exemptions are derived, never allowlisted:**

* **no shebang → sourced, not executed.** `display_isolate.sh` is a library;
  there is nothing to pass `--help` to.
* **reads no arguments → nothing to document.** The `test_*.py` runners.

A name-based allowlist would need maintaining, and the first tool someone forgot
to add to it would be exempted *silently* — recreating the failure this exists
to catch.

**Controls (`--self-check`, 6, each able to fail).** A synthetic tree containing
one of each shape asserts that only the genuinely-bad tool is flagged and that
both exemptions discriminate; a `.log` file written to *look* like code asserts
the suffix filter still works; the new/backlog split is driven twice over
identical input with only the baseline changed; and the tool is required to
**pass its own rule and be documented in this playbook** — control 6 failed on
first run, correctly, because this section did not yet exist.

**It found a real one immediately.** `test_display_isolate.py` documented a
`[--dry-run]` flag, read `sys.argv`, and handled no `--help` — so
`--help` fell through and **started X servers and recorded video.** Fixed in
the same checkpoint.

**T47, added the same day (T95).** The `/tmp` check exists because the sweep that found one offender found ten: `display_isolate.sh` was the ONLY script obeying T47, and nine defaulted evidence to `/tmp` including the run log, the fault identifier and the screenshot tool. **The rule was real, written down, and unenforced for a day — the identical shape to T89/T90.** The nine are recorded as named debt rather than findings, because nine permanent findings make `--strict` useless; a script that acquires a `/tmp` default *later* is a regression and is counted.

**Its fixtures are ASSEMBLED, not written literally, and that is load-bearing.** The first version spelled them out and the linter flagged ITSELF at the line holding its own test data. The fix is to keep the pattern out of the source — **never to exempt the file**, which would be a self-exemption and precisely the hole a checker must not have. `audit_l2.py` records two earlier controls that failed this same way (T65).

**Both T47 controls were verified to fail in BOTH directions:** with the regex made inert they reported `flagged []`, and with the comment/scratch exemptions removed they caught the prose false-positive (`talks_about_tmp.sh`). A detector can be wrong by missing real cases or by flagging compliant ones, and only a two-sided control sees both.

```bash
scripts/lint_tools.py --self-check   # 9/9
scripts/lint_tools.py --dry-run      # report, do not touch the baseline
scripts/lint_tools.py --strict       # exit 1 on findings
```

---

## A trace condition is scoped to the SITE it was written for (added 2026-08-19, A163)

`:300` and `:436` are both `LOOKUP_FUNC` dispatches inside the same function.
Reusing `:300`'s condition at `:436` — "the pointer is outside
`0x80033100`-`0x80033800`, the range containing all 18 handlers" — produced
**77,058 hits out of 77,058 reaches.** Every dispatch. It looked like a
spectacular overrun and it meant nothing: `:436` dispatches through a *different
table*, so that range was never the right one for it.

**The count is not the giveaway. The SHAPE of the targets is.** 17 distinct
values, 12 of them inside a 0xCFC window and 5 in overlay space, none below
`0x80060000` — a bounded family of plausible handlers, i.e. a healthy dispatch.

So:

* **Derive the expected range from the site's OWN targets** before treating
  "outside range" as a defect. Trace unconditionally-but-cheaply first (reach
  counter plus a wide condition) and look at the distribution.
* **Judge a dispatch by whether its targets form a bounded family of plausible
  code addresses**, not by a range borrowed from a neighbour.
* A condition that fires on 100% of reaches is almost always a wrong condition,
  not a spectacular finding. Check that before writing it up.

`:598` is still untested and will need its own range on the same basis.

---

## Falsifiers: RUN the cheap ones, do not merely write them (added 2026-08-19, T86)

Every ledger entry carries a falsifier. That requirement trains you to **write**
one. It does not train you to **run** one, and those are not the same discipline.

**A161 stated the falsifier that would have killed it, and it was never run.**
Verbatim: *"a capture between 152 s and 158 s showing the green logo card."* One
capture, about two minutes, and it was written down **before** the claim was
asserted. The claim was withdrawn the same day when the user pointed at exactly
that gap.

**The rule: if a falsifier is cheap enough to run now, run it before asserting
the claim.** Then record the result, not the intention.

**For a cheap falsifier, stating it and not running it is WORSE than omitting
it** — it manufactures the appearance of rigour. A reader (including a later
session, including you) sees a falsifier and reads the entry as tested.

Ask the question in this order:

1. What would make this false?
2. **What would it cost to check that right now?**
3. If the answer to 2 is minutes, it is not a falsifier — it is the next command.

### Why this is NOT mechanised (cf. T29)

A falsifier's usual purpose *is* to be run later — that is what makes it useful
to write down for a future session. So flagging every untested falsifier would
fire on almost all of them and train you to ignore the channel, which is the
failure T29 warns about. The judgement is about **cost**, and no check can see
what a given test would cost. It stays a rule.

What the tooling does cover: `audit.py` flags entries created and withdrawn
inside one window (`churn`), which is where this failure shows up after the
fact. That caught A161 — one audit window late.

---

## EV-2 — Claim strength: match the claim to the evidence (added 2026-08-18)

**The recurring failure on this project is not missing evidence. It is claims
that are broader than the evidence supporting them.** Roughly a dozen ledger
entries were wrong in a single session; every one cited real evidence, correctly
gathered. Sorted by how they failed:

| failure mode | count | example |
|---|---|---|
| **Universal negative from a bounded search** | 4 | "nothing calls `func_8002A8E0`" — true of splat's asm, false of the ROM. A watchpoint then caught it executing |
| **Interpreting a measurement** | 3 | "CALLBACK=0" (true) became "the list was empty" (false); `0xC` (a byte size) became "12 frames" |
| **Composing facts into a causal story** | 3 | Three true findings assembled into a root cause that was wrong |

By contrast, **interventions and direct measurements have never been wrong**.
The failures live entirely in what gets inferred *around* the numbers.

**The rule.** A claim is established only if **a test ran that could have
contradicted it and didn't**. Ask that before writing any conclusion:

- A grep that returned nothing usually *could not* have contradicted the claim —
  it can't distinguish "absent" from "outside what I searched".
- A watchpoint held across the whole failure window *could* — but only with a
  **positive control** proving the same tool fires elsewhere. A non-firing
  instrument with no control is not a negative result, it is no result.

**Evidence strength, strongest first** — reach down this list only as needed:

1. **Intervention** — change one input, watch the symptom move. Settled that the
   two freezes are one bug (relocate the stack, freeze disappears).
2. **Direct observation at the moment of failure** — a watchpoint naming the
   writer, a dump of actual values on the fatal frame.
3. **Reading code** — trustworthy for "what does this do", untrustworthy for
   "what happens at runtime".
4. **Search** — good for finding, near-worthless for proving absence.
5. **Composition** — never proof, however tidy the story.

**Two hard rules, both cheap:**

- **Every negative names its scope inside the claim.** Not "nothing calls this"
  but "nothing *in splat's asm* calls this". This alone would have prevented a
  third of the errors, including a day spent believing a working probe was broken.
- **Before writing a load-bearing conclusion, write its falsifier** — what would
  have to be true for this to be wrong — and check it. Every failure above had a
  falsifier that cost one command: *"a caller outside splat's coverage"* (one
  grep), *"`0xC` is a size"* (one decompile), *"the reset is resident"* (which is
  what it turned out to be).

**Cost control:** full treatment applies only to **load-bearing** claims — ones a
fix or a routing decision will rest on. A thread map needs no falsifier; "this is
the root cause" does. See `docs/findings-ledger.md`'s Load-bearing section for
the Observed / Falsifier / Checked format.

**Enforcement — `scripts/check_ledger.py`.** Runs automatically on every edit to
the ledger via a `PostToolUse` hook in `.claude/settings.json`; also runnable by
hand, and with `--strict` in CI-ish contexts. It checks the four **structural**
failures, none of which need judgement:

1. a negative with no stated scope;
2. a load-bearing claim missing Observed / Falsifier / Checked;
3. **an entry resting on a WITHDRAWN entry** — the highest-value check, and the
   one that is not about discipline: B46 rested on B41, B41 was withdrawn, and
   B46 stood as fact until someone happened to notice. Entries that *are* the
   replacement are exempted by wording ("supersedes", "corrects", "retract");
4. duplicate IDs (six appeared in one session of incremental edits).

**Citing a withdrawn entry AS AN EXAMPLE is allowed, with a named waiver (T126).**
`CITED AS PRECEDENT: <ID>` waives exactly that one citation. A withdrawn
entry is the best example of its own error class, and six findings in one day
were all that shape. **The ID must follow the marker DIRECTLY** — the first
version allowed it anywhere within 200 characters, and its own control caught
a marker naming one entry silencing a citation of another. That would have
been a blanket off-switch on the highest-value check here.

**5. A MISSING OR JARGON-LADEN `SO WHAT:` LINE (T120).** Every entry written
after the 2026-08-20 mark must carry one plain sentence saying what the work
achieved — the checkpoint-closing sentence, moved out of chat and into the
record. **Why it moved: it was the only part of a checkpoint with no mechanical
check, and it is the part that got skipped** — on the same checkpoint that
drifted into unrolled work. `route.py` printed the requirement and
`test_route.py` asserted it was printed; nothing ever asserted anyone met it.

Two things are checked, and **the second is what makes it discriminate**:

* the line is present;
* the sentence is **plain** — an address, an entry ID, a filename or a register
  fails it. Presence alone is satisfied by pasting the entry's own jargon after
  the label, which is exactly the sentence the rule exists to prevent.

Unlike the single-run high-water mark beside it, **this mark does not advance
past an unfixed gap**: a missing sentence is reported every run until written,
because a finding reported once and then forgotten is the failure this whole
change is about. Its first run found 15 — every entry written that day.

Findings are **warnings, not gates** — it directs attention, it does not judge.
It cannot check the thing that actually goes wrong: a required field forces
presence, never truth, and `falsifier: none obvious` passes any validator.

On first run it flagged four real problems, including a compressed table row
that had silently lost its evidence.

**What this does not fix:** the conclusion gets written in the same breath as the
evidence, while the story still feels complete — and every wrong entry felt
proven when written (one literally said "ANSWERED", another "ROOT CAUSE"). A
self-assessed "am I sure?" box is worthless at exactly that moment. The falsifier
question works because it is answerable *without* knowing whether you are right.

---

## Count before you read — ALWAYS (added 2026-08-18)

**Never pull output into context without first knowing how much output there is.
Run the count unless the count is already known.** This is not a guideline to
apply when something looks big; it is unconditional, because the cases that hurt
are exactly the ones that did not look big.

It applies to *everything that produces output*, not just files:

| about to… | count first with |
|---|---|
| read a file | `wc -l` |
| `grep` across a tree | `grep -c` / `grep -rc`, or `grep -rl` for just the filenames |
| xref a symbol ROM-wide | count per file, then read only the file you need |
| list matches | `\| wc -l` before dropping the `\| wc -l` |
| run a decomp / dump / probe | write to a file, `wc -l` it, then read a range |

The pattern to internalise: **redirect, count, then read a slice.** Writing to
the scratchpad and sizing it costs one cheap call and converts an unbounded read
into a bounded one.

> **Caught on 2026-08-18.** A ROM-wide `jal` cross-reference of four functions
> printed every call site — several hundred lines — when the question was only
> *"does anything call `func_8002A8E0`?"*, whose answer is a single number (zero).
> The same session had already been told tokens are the scarce resource. A
> `grep -c` first would have answered it outright, and the later greps in that
> same session were tightened to counts and filenames only.

The failure is asymmetric, which is why the rule is unconditional: a needless
count wastes one trivial call, while a needless read costs context that the next
twenty decisions have to be made without. **Cheap insurance against an expensive
mistake is always worth buying.** See also *Cost function: tokens first, CPU is
free*.

### The special case: sizing a file

**Check how big a file is before opening it, and let the answer choose the
access method.** `wc -l` costs nothing and decides whether you read, seek, or
route around.

This project makes the failure mode acute: `RecompiledFuncs/` is **1,529,331
lines** of generated C across ~120 files, the largest single file is 28,495
lines, and the three files holding the functions of interest this session were
10,427 / 12,529 / 13,665 lines. Reading any of them whole is not "slow" — it is
impossible in a useful sense, and it evicts the context that made the question
worth asking.

Rules of thumb:

| size | approach |
|---|---|
| < ~500 lines | read it |
| 500-2,000 | read the region you need (`sed -n 'A,Bp'`) |
| > 2,000 | never open blind: locate first, then extract a range |
| generated / minified / vendored | always treat as > 2,000 regardless of size |

Locating in the generated tree, cheapest first:

```bash
grep -ln "void boot_func_8002AA90(" RecompiledFuncs/*.c   # which file
grep -n  "boot_func_8002AA90" RecompiledFuncs/funcs_2.c   # which line
awk '/^RECOMP_FUNC void boot_func_8002AA90\(/,0' f.c | sed -n '1,60p'
```

The `awk` range form is the workhorse: it extracts one function from a
30,000-line file. **Do not trust its line COUNT** as a measure of a function's
size — the range runs to the next `^}`, and a mis-split or nested brace makes it
swallow neighbours. It once reported "4,218 translated instructions" for a
function that plainly has far fewer. Use it to read, not to measure.

**Since 2026-08-18, prefer `scripts/decomp.sh <func>` over any of this when the
question is "what does this function DO".** The locate-and-extract recipe above
is now for the cases m2c cannot serve: checking what the *recompiler* emitted
(a stub, a mis-split boundary, an injected hook) rather than what the original
game code means. Those are genuinely different questions — the transliteration
is the right source for the former and the wrong one for the latter.

**The wider point:** a free read that answers the question outranks any run, so
reading generated source early is usually right — but only when it is *targeted*.
The cost of an untargeted read is not the seconds, it is that the next twenty
decisions get made with less context. Size first, then choose.

---

## Iteration economy (added 2026-08-17)

Debugging cost here is dominated by a few avoidable habits. None of these trade
away rigour; they remove waste.

1. **Only run `recompile.sh` when `sinpunishment.toml` or the symbol map
   changed.** Changes to `lib/N64ModernRuntime` / `lib/RecompFrontend` need
   `cmake --build build` alone. `recompile.sh` regenerates all of
   `RecompiledFuncs/` and is the single slowest step in the loop.
2. **Never let large probe output reach the reader.** `SNP_TRACE=1` emits ~37k
   lines per run. Always redirect to a file and `grep`/`awk` the answer out.
   Same for gdb dumps — extract the handful of frames that matter.
3. **Prefer `SNP_HEARTBEAT=1` over screenshots for anything time-based.** A
   screenshot costs a capture, a PNG decode, a per-pixel scan and (if inspected)
   an image read; the heartbeat is a few lines of text and is strictly more
   trustworthy for liveness. Reserve screenshots for "what is on screen".
4. **Match run length to the event.** The freeze lands at t≈42s, so a 50s run
   answers it; 70-115s runs add nothing. Surveys of N runs are for *rates*, not
   for facts a single well-chosen run establishes.
5. **Grep the docs; don't re-read them.** These files are thousands of lines.
   `grep -n <address|symbol> docs/` finds prior art in one call — and prior art
   exists far more often than expected (see the G4 note about an entire
   investigation being repeated 2,000 lines after it was solved).
6. **Batch independent shell work into one call.** Status checks, greps and
   file inspections that don't depend on each other should not be serialised.
7. **Test a trigger condition before building on it.** Four scheduler fixes have
   now failed because the condition they keyed on never occurs. A single
   rate-limited probe costs one build; a fix built on an unverified assumption
   costs a build, a run, a wrong conclusion, and the retraction.

### Probes that change the outcome, and runs that never end (added 2026-08-17)

Three tooling lessons from tracing the attract-mode graphics stall. All three
cost real time and one of them cost the user's screen twice.

1. **A probe heavy enough to alter timing is measuring itself.** The first
   global message census called `backtrace()` inside `do_send`, which runs
   thousands of times a second. Under it the game died at t=8s with
   `No threads left to run!` — a failure that never occurs without the probe.
   Re-keying the census on the thread id (already in hand, free) reproduced the
   normal freeze exactly. **In a cooperative scheduler, assume any per-call work
   in a hot runtime path is enough to change behaviour**; aggregate cheaply and
   reserve expensive capture (backtraces) for one filtered site, once per second
   or once per distinct value.

2. **`gdb` does NOT slow a freely-running program.** The G7 note that "gdb slows
   execution 10-20x" is true for *software* watchpoints and single-stepping, and
   was wrongly generalised to `run`. Acting on it, a watchpoint was armed 60s in
   to catch an event at t=42s — after the event had already happened, so it could
   never have fired. The user, watching the window, reported the game running at
   normal speed, which is what caught it. x86 *hardware* watchpoints (≤8 bytes)
   also run at full speed. **Arm before the event in real seconds.**

3. **Every automated run needs a hard upper bound, enforced inside the tool.**
   `gdb_watch.sh` armed a watchpoint and then `continue`d. When the watchpoint
   doesn't fire — wrong address, event already past, arming failed — `continue`
   blocks forever and the game window sits open on the user's screen. That
   happened twice before it was fixed with a deadline thread that `SIGKILL`s the
   process group regardless of state (and `setsid`, so the kill cannot reach the
   caller). `scripts/run_game.sh` already had this property; anything that opens
   a window must. **A debugging tool whose worst case is "hangs indefinitely in
   front of the user" is not finished.**

Corollary to all three: **say up front how long a run will occupy the screen.**
The user should never have to ask whether something is still supposed to be
running.

### A killed process loses its buffered output (added 2026-08-17)

`gdb_watch.sh`'s deadline `SIGKILL`s the process group. That discards anything
gdb had written but not flushed, so a run that hits the deadline comes back with
an almost-empty log — which reads exactly like "the watchpoint never fired."

A conclusion was drawn from that empty log ("the matrix stack pointer never goes
high, so the write must be via the thread stack"), and it happened to be right,
but it was not evidence. **A truncated log and a negative result are
indistinguishable unless you check.** Fixed by running gdb under
`stdbuf -oL -eL`; do the same for anything whose output you may kill.

The general rule, which cost time twice today: **before believing a negative
from an instrument, make the instrument produce a positive.** The conditional
watchpoint was validated by watching the same address with a condition that must
always hold (`> 0x80068200`, when the value rests at `0x80068284`); it fired
immediately, which is what made the real negative trustworthy. The stub probe
was validated the same way, by injecting it into a known-live function first.
Both controls cost one short run each and turned "probably nothing there" into
"nothing there."

### G6 status update (2026-08-17): ares debug server still blocked

`scripts/ares_peek.py` (new) is a standalone GDB-RSP client. **Rationale, still
valid:** this machine's gdb has no MIPS target, but the RSP memory-read packet
(`m<addr>,<len>`) is architecture-agnostic, so memory can be read without gdb
understanding MIPS at all.

**Current state: connects, then ares closes the session on the first packet** --
including a correctly-framed `$?#3f`. Ruled out: no unsolicited greeting packet
awaiting an ack; checksums correct; IPv4 confirmed (`ss` shows `0.0.0.0:9123`);
and the ROM genuinely loaded (see the trap below).

> **Trap that cost two rounds here:** pass an **absolute** ROM path. A relative
> path does not resolve inside the flatpak sandbox, so ares starts, opens the
> debug port, and sits at its menu with nothing running -- the port listens and
> the connection still dies at the first packet, i.e. *the same symptom for a
> completely different reason*. Worse, a failed background relaunch left the
> earlier relative-path instance running, so the "retry" silently re-tested the
> broken one. **Check the live process's cmdline (`pgrep -af`), not the command
> you believe you ran.**

Untried, cheapest first: `apt install gdb-multiarch` (makes the question moot);
confirm whether this ares version's DebugServer is stock RSP at all; send a bare
`+` before the first packet in case the stub expects a client ack.

**Recommended instead for the current question.** All we need is whether
hardware-accurate emulation corrupts `0x8007AF0C` the way we do. That is
answerable behaviourally: run ares to the same attract point and see whether it
continues past where our build stops -- seconds to judge by eye. Do not sink
more time into the debug server for this.

## `ablate.py` + `SNP_ABLATE` — break one function per run, on purpose (added 2026-08-26, user-directed)

**Purpose.** Attribution by subtraction: stub ONE function to an immediate
return, run headless, and read what changed off the per-run signature. Built
for A218-shaped questions ("which function feeds the geometry that appears?")
and usable as a confirmation probe for A211-shaped ones ("does stubbing the
candidate machinery move the stall?"). **The motivating incident is the
technique survey of 2026-08-26** — the user asked whether systematic
function-breaking could be automated; it can, because the runtime already
dispatches through per-section function tables with native pointers.

**Mechanism.** `SNP_ABLATE=<vram>[,<vram>...]` in the runtime
(`lib/N64ModernRuntime/librecomp/src/overlays.cpp`, `snp_ablate_init()`, runs
at the end of `init_overlays()` before any game code). Each vram is resolved
against EVERY code section; every match gets its native first byte overwritten
with x86-64 `RET` (0xC3) under a brief `mprotect` window — the function becomes
`jr ra; nop`, registers untouched. **This catches direct calls too**:
`RECOMP_FUNC` is `noipa` under gcc, so no caller has inlined a body. The hook
is in the NEVER-COMMITTED runtime tree, like every probe.

* `SNP_ABLATE_DRYRUN=1` — resolve, report, exit before launch (T71 gate 1).
* A vram that starts no function is a **hard error, exit 2** — a typo must not
  silently ablate nothing (T65). Proven the honest way: a hex-conversion
  mistake during the control runs hit exactly this path and halted the run.
* Shared-window vram (A261) patches EVERY match and logs each; qualify your
  candidate list against loaded overlays before reading an ovlfile result.

**Controls, all run 2026-08-26 before the first screen row existed:**

| control | expectation | result |
|---|---|---|
| positive (mechanism): stub `boot_gameEntry` 0x80025C40 | run visibly breaks | **0 frames, DEGRADED** vs 1297 CLEAN baseline |
| negative: stub 0x800E47F0 (ovlfile05, never loaded in the 250 s attract log) | signature identical | **1298 CLEAN, aud 86.9%, RMS −15.25 — identical** |
| refuse: bogus vram | halt at init | **REFUSING + exit, no run** |

**>>> THE alAudioFrame TRAP, and it is a finding: stubbing 0x80042B2C (the
ultralib oracle's `alAudioFrame`, A444) changed NOTHING — audio 86.9% non-zero
either way. The SDK audio driver is IN the ROM and is NOT the runtime audio
path; Treasure's own driver is. So audio amplitude does NOT discriminate for
SDK-audio targets, and any A444 name is evidence of static presence, never of
runtime use. <<<**

**The harness** (`scripts/ablate.py`): one TSV row per run — verdict / wall /
gfx totals off `run-log.tsv`'s own row, `patched_n` (0 ⇒ `INVALID-NO-PATCH`:
the run measured the ordinary game), audio %/RMS from a per-run
`SNP_AUDIO_DUMP` (raw deleted after stats unless `--keep-audio`), and a
geometry digest per armed task (v/t/r counts + hash of the ordered t/r lines).
Resumable: targets already in the TSV are skipped.

* **`SNP_DL_GEOM` is silently inert without `SNP_DL_CENSUS=1`** — it lives
  inside the census block. The harness arms both; measured on its own first
  smoke test (geom=NA on every row).
* Baseline digests are deterministic in practice (identical hashes across
  runs, consistent with A449) — but **T22 stands: a screen row that differs
  from baseline is a CANDIDATE for a 3-run confirmation, never a claim.**
* A 45 s run reaches the attract only. **The tutorial needs ≥170 s** — a
  tutorial-window screen is a different, longer night.

**Invocation used for the first screen (2026-08-26, main segment, 620
functions + baseline):**

    scripts/ablate.py --targets <archive>/evidence/2026-08-26/ablate-targets-main.txt \
        --outdir <archive>/evidence/2026-08-26/ablate-screen --secs 45 --geom 900,1100

## `ARES_WATCH` — ask the real game which instruction writes a byte (added 2026-08-26, T211/A470)

**Purpose.** The write-watch oracle: a local patch to our ares-64 checkout
(`ares/n64/cpu/memory.cpp`, `CPU::write` — the SINGLE choke point for CPU
stores; the cached/uncached split is after it). `ARES_WATCH="80068A88,..."`
(hex, ≤16 bytes, KSEG0-virtual or physical) logs
`[watch] pc=... paddr=... size=... data=...` to stderr on every CPU store
touching a watched byte. Replaces the DEAD gdb route (A405) with something
narrower. **Motivating incident: A211 needs to know what normally ENDS a
tutorial pause, and only the working game can say.**

* **Scope: CPU stores only.** DMA writes bypass the choke point — deliberate:
  the question is which CODE writes scene state, not which DMA loads over it.
* ~~**COVERAGE IS PARTIAL — the dynarec DOES bypass the hook once blocks are
  warm (A477).** An absence in a watch log means NOTHING. For complete
  coverage, force ares's CPU interpreter (unexplored) before trusting any
  negative.~~ **SUPERSEDED 2026-08-27: the interpreter IS forced now**
  (`ares/n64/accuracy.hpp`, `Accuracy::CPU::Interpreter` hard-set to 1 with the
  original expression kept in a comment), so every CPU access goes through the
  hook and **an absence is now meaningful.** This section contradicted itself
  for a day — the bullet above said absences mean nothing while the EPOCH
  bullet below said "the CPU is also interpreter-forced (A505)". Struck rather
  than deleted, because the strike is the thing worth seeing: **check
  `accuracy.hpp` rather than this file before trusting either statement.**
* **Controls (A470, run before first use):** positive — the display-list
  append pointer, written every frame: 754 hits with PCs. negative — a
  top-of-RAM word: exactly one boot-time zeroing write (data 0, boot-library
  pc), then silence.
* Launch headless by sourcing `scripts/display_isolate.sh`
  (`snp_isolate_display`), then `timeout N ./build/desktop-ui/ares --system
  "Nintendo 64" <ABSOLUTE rom path>` with the env set. The isolation wrapper
  auto-records — expect a ~2 MB/s .mkv rider beside the log.
* **THAT RIDER STOPS AT 400 SECONDS AND THE RUN DOES NOT (A536, 2026-08-27).**
  `display_isolate.sh` records with `-t ${SNP_REC_MAX:-400}`, a deliberate
  anti-runaway cap. A 701-second watch run therefore leaves a 400-second
  recording, and **sampling the video past 400 s returns NOTHING, which was
  read as the emulation freezing (A514) and reported to the user as such
  (A517).** Five archived captures sit at exactly 400.000 s for this reason.
  **SET `SNP_REC_MAX` EXPLICITLY for any run meant to exceed 400 s**, and treat
  a duration of exactly 400.000 as truncated until checked. The check is two
  timestamps: start time from the filename, last write from `stat`.
* **THE CAPTURES CARRY ARES'S OWN UI, AND `cropdetect` FINDS THE WRONG BOX
  (user-caught, 2026-08-27): the game renders inside a floating "Output"
  panel, so black-border detection returns the panel surround (1024x720),
  not the picture. Measure the game rectangle from PIXEL CONTENT per capture
  and verify one cropped frame by eye before using it — for the current
  window layout it measured `crop=564:424:225:74` (565x425, 4:3 to three
  decimals), but the panel can move, so the offset must not be reused
  blindly across runs.**
* **EPOCH BOUNDARY 2026-08-27 (A515): the checkout's VI output filtering is
  HARD-FORCED OFF at the register write** (AA mode 2, divot/dither/gamma-dither
  cleared) — every capture from this date is sharp-epoch and NOT
  pixel-comparable to real-console output or to earlier captures. The CPU is
  also interpreter-forced (A505). Both diffs live in `probe-patches/`.
* Rebuild after touching the patch: `ninja -C build desktop-ui` (NOT
  `cmake --build` — guard false positive, known).
* **The attract needs NO input** (A436) — the tutorial arrives by itself at
  ~200 s emulated, so pause-machinery questions need a ≥215 s run.

### `ARES_WATCH_READ` — the same watch, on LOADS (added 2026-08-28, A630)

**Purpose, and the mistake that motivated it.** `ARES_WATCH` sees CPU **stores**
only. A pointer table is written once at scene set-up and **read every frame**,
so a store-only watch reports it as silent exactly when it is busiest. Our own
recomp-side tap (`SNP_READWATCH`) taps `MEM_W`, which serves **both loads and
stores**. Comparing that tap's counts against a store-only watch is not a
comparison — and A627 did it, aimed at an address our own build barely uses, and
read the result as agreement. **`ARES_WATCH_READ` exists so the two sides
measure the same thing.**

* Same file (`ares/n64/cpu/memory.cpp`), same parser, same ≤16 byte addresses,
  hooked into `CPU::read` — the choke point for loads, mirroring `CPU::write`.
  Emits `[watch] R pc=... paddr=... size=...`.
* **`ARES_WATCH` keeps its exact old meaning and its exact old line format.**
  Two independent sets, two env vars. An existing watch log therefore still
  parses and still means what it meant.
* **A TIME AXIS, because A627's numbers were read off a truncated log with no
  way to tell where in the run a line fell.** Every 4096 hits the watch prints
  `[watch] T=<seconds> hits=<n>`, wall seconds since the FIRST hit. The counter
  is shared across all watched addresses, which is the point: hot control
  addresses keep the clock running so a *silent* address can still be placed in
  time.
* **A fast reject (min/max span) precedes the loop** on both hooks, so the cost
  on the hot load path is two comparisons.
* **Do not arm both on a hot address for a long run.** The write watch on the
  matrix-stack top emitted **124,793 lines in 25 s** — ~2 M over 420 s on
  unbuffered stderr, enough to slow the emulator out of the scene you wanted.
* **Controls (`a630_analyse.py --self-check`, 4 controls, 2 falsifications):**
  C1 time markers exist and advance — **falsified** by feeding a clockless log,
  which must FAIL; C2 every armed address printed *including zeros*, so "never
  fired" cannot look like "never watched"; C3 per-address totals sum to parsed
  lines; C4 a synthetic log where one address fires **only in the first half**,
  which fails if the binner reports it active late.
* **The in-scene control is the one that matters** and it is not in the script:
  watch known-hot addresses (ranges A and C) alongside the question (range B).
  If A and C are silent too, the addresses simply are not used by the reference
  and the range-B zero means nothing. **That branch must be reported, not
  explained away.**
* Scope, unchanged: **CPU accesses only.** DMA does not pass through
  `CPU::read`/`CPU::write`. A silence cannot exclude DMA traffic.

## `unsquash.py` — de-smoosh a field capture for human eyes (added 2026-08-26, user request)

Reference frames captured as one interlaced field come out **640x240** and look
vertically squashed. `scripts/unsquash.py <in.png>` doubles pixels VERTICALLY
(restoring aspect) then integer-scales by **NEAREST NEIGHBOUR** (default x2 →
1280x960) — no resampling at any step, so no blur and no invented pixels.
Controls: self-check 3/3 asserts the output colour set is EXACTLY the input's
(a resampler fails this — verified by breaking a copy to BILINEAR, 1/3);
`--dry-run` prints the transform. Skips non-squashed inputs unless `--force`.
**Viewing aid, not a measuring instrument** — measure on the original.
**Run it on anything squashed before handing the user a frame to judge.**

## `[dlgeom]` samplers: `arena` and `listN` lines (added 2026-08-26, A481/A484/A485)

The armed-task geometry trace now also emits, at each `task=N BEGIN`:
* `arena` — five sampled words from the background-texture band (the region the
  real game's tutorial backdrop strips read from). Populated-vs-zero split
  load/fill faults from submission faults in one run (A481).
* `listN` — a walk of scheduler list N printing `node:handler` pairs, node
  layout (countdown +0, HANDLER +4, next +C, payload +10) read from the
  six-list walker's own code. Bounded 24 nodes, address-sanity guarded.
  **First outputs self-validated: every printed handler resolves to a real
  function in the generated tree.** Traps: the NODE POOL ADDRESS MOVES between
  scenes (attract vs tutorial pools differ — never assume it); `x` lines are
  raw SETTIMG operands (w0 w1).

Both live in the runtime tree (uncommitted, as all probes). An absence from a
list read is trustworthy exactly when the same line shows other entities —
the instrument proves it can see in the same breath (T209 by construction).

## `av_drift.py` — audio-vs-picture drift by anchor CHANGE (added 2026-08-26, T217)

Measures drift as the **change** in offset between an early and a late anchor
pair, so the unknown constant gap between "music starts" and "screen brightens"
cancels. Replaces A462's ad-hoc script, which did not survive.

**Read this before using it: it produced a confidently wrong +139 s on its
first real run**, pairing an audio silence at t=180 with a video fade at t=38.
The correspondence check added after that failure compares FULL ordered
transition lists and returns **NA when the counts disagree** — which is what
the known-drifting pair now returns (video 16 transitions, audio 2).

**THE CONTENT PROBLEM THIS EXPOSED, and it is the real finding:** our attract's
music plays CONTINUOUSLY across scene cuts, so silence-vs-fade anchoring cannot
work on this game at all. A drift measurement needs either music-CHANGE
detection (spectral novelty) or a marker stamped into both streams at source.
**Prefer the marker.** Controls: `--self-check` 5/5, breaks 3 and 4 verified to
FAIL (a constant offset must read ZERO drift; silence must yield NO anchor).

## `a491-texrect-scan.py` — is a display list DATA or is it BUILT? (added 2026-08-26, A491)

Lives with its evidence at `<archive>/evidence/2026-08-26/`, not in `scripts/` —
it answers one question and is kept because that question recurs, not because it
is general.

**The question it exists for:** we know from a reference dump exactly which
commands the real game emits for some frame. Are those commands **static data**
sitting in the ROM or an overlay, merely pointed at — or are they **generated by
code**? The answer decides whether a deadness result about builder functions
bears on the missing draw at all.

**It scans a binary for plausible F3DEX2 `G_TEXRECT` pairs** and, separately,
for the *exact* words of a known list. Two halves, deliberately: the exact search
answers "is this specific list here", the plausible search answers **"can this
instrument see such a list at all"** — without which the negative is worthless.
Pair it with a `lui`-materialisation census of the generated C, which covers the
code route the byte-scan cannot.

**USE IT WITH BOTH HALVES OR NOT AT ALL.** The ROM is mostly Yay0-compressed, so
"not in the plain ROM" alone proves nothing. The finding is only meaningful when
the same scan is shown to FIND real lists nearby — it found 18 in the 8 MB RAM
dump, three of them the canonical whole-texture-at-origin form at exact spacing.
**And a RAM dump is a MOMENT**: a list absent from the fault-moment dump may
simply not have been resident. Decompress the archive you actually care about.

**THE CONTROL STORY, which is why this is written up at all:** the first three
deliberate breaks ALL PASSED. Two were no-ops (conditions subsumed by a later
test) and the third exposed a **vacuous filter** — a coordinate ceiling of
`0x1000` against TWELVE-BIT fields, which could never once have rejected a word.
The noise control was underpowered too: 229 candidates gave a rate identical to
three significant figures across four different mutations, and *that identity was
the tell*. Rebuilt at 4 MB / 4,040 candidates the working filter rejects **all**
of them, so the threshold is **zero** — and at zero all three breaks fail. A 2%
threshold had passed two of three.

**The transferable lesson: when a deliberate break changes nothing, do not
conclude the tool is robust.** Either the condition is redundant or it never
fired. Both were true here, and only counting the candidates told them apart.

## `morning.sh` — the day's machine-side prep, on cron (added 2026-08-27, user request)

**Purpose.** The morning chores were being done at the keyboard while the user
waited. Their words: *"I'd rather not have to wait around for it to get sorted
out every day."* This does the part a machine can do alone, at 06:03 daily.

```bash
scripts/morning.sh --dry-run      # say what it would do, change nothing
scripts/morning.sh --self-check   # 5 controls
```

Crontab line (installed 2026-08-27; **06:03, not 06:00** — an off-minute, so it
does not land with every other cron on the planet):

```
3 6 * * * cd <repo> && ./scripts/morning.sh >> <repo>/scripts/morning.log 2>&1
```

**What it does:** the L2 audit, today's evidence directory, and a status-page
HTML rebuild. Then it writes `docs/MORNING.md` (readable) and
`docs/.morning-state.json` (the detector).

### TWO THINGS IT DELIBERATELY DOES NOT DO, and both are load-bearing

**It never republishes the status page.** That needs the claude.ai artifact
capability, which is documented as absent from headless/cron runs. A job that
"publishes" and silently fails every morning is **exactly T194** — the nightly
push that died for three days and 182 commits into a log nobody read. The
regenerate it *can* do takes under a second, so the session loses nothing.

**It never runs the game and never clears the observed-run gate.** That gate
exists for the two things nobody here can check alone — audio, and scene
identity (T101). A cron that cleared it would destroy the only property it has.
It reports whether one is owed; it cannot satisfy it.

### HOW IT OBEYS T151 WITHOUT BEING NEUTERED

T151 (the user's rule): *nothing recurring on this project may accumulate; a day
with no work owes nothing.* This job is **calendar-gated** — it fires at 6am
whether or not anyone works — which is normally the forbidden shape.

It is allowed because **it bills nobody**: no notification, no nag, no debt. Its
output is a file read only if someone comes to work. **The split that makes this
legal is that the JOB is calendar-gated while its DETECTOR is activity-gated** —
`check_ledger.py` reads the state file, and `check_ledger` only runs when work is
happening. An idle fortnight produces silence. **If this ever grows a
notification it breaks the rule**, and a control asserts it has none.

### THE DETECTOR, AND WHY IT IS NOT A LOG FILE

BL17 exists because every scheduled job here reported into a log nobody read.
So the detector lives in `check_ledger.py`: it reads `.morning-state.json` and
speaks if the job **reported failures** or **has not run today**. There is
deliberately **no `else` branch** for a missing file — that means the cron was
never installed on this machine, which is not a fault to nag about.

**It earned itself on the first real run.** The job wrote malformed JSON —
`grep -c` prints its zero *and* exits 1, so `|| echo 0` appended a second line
and `observed_today` came out as `"0\n0"` — and the detector said **"morning
state unreadable"** rather than the bug sitting unnoticed in a log until an
audit happened to print the last line. That is the entire argument for the
detector not being a log file, demonstrated within a minute of shipping it.
**The correct idiom is `|| true`**: it swallows the exit status and keeps the
printed zero.

### CONTROLS — 5, with two breaks verified to fail

1. never launches the game or the observed run
2. does not attempt the publish it cannot do headless
3. **the state file records FAILURE, not only that it ran** — an always-ok
   detector detects nothing
4. sends no notification (T151)
5. `--dry-run` writes nothing (asserted by running it and comparing mtimes)

Breaks verified: adding a notification fails 4; making it launch the game
fails 1.

### THE INCIDENT THAT MOTIVATED THE CONTROL STYLE — the fifth self-referential check

**Control 4 initially failed on a fully compliant script.** It grepped for
`notify-send|mail |curl -X POST` written literally — so the pattern **matched
its own line**. This is the fifth self-referential control in this codebase
(`audit_l2` records two, `lint_tools` and `audit_l3` one each, plus
`observed_run.sh` control 6, which produced a false *pass* and is the worse
shape). It was caught here one line after a comment in *this same file*
explaining the fix for control 2.

**Writing the rule down is not the same as applying it.** Assemble the needle
from parts by default:

```bash
_n1="noti""fy-send"; _n2="cu""rl -X POST"
! grep -qE "($_n1|$_n2)" "$0"
```

## Cross-build PIXEL comparisons are contaminated by A218 — check saturation first (added 2026-08-27, A562)

**Do not compare lit-pixel counts between our build and the ares reference without
first computing how much dark area each side had to fill.** A562 built exactly that
comparison to give A247's "the overlay region is never cleared" the negative control
it never had, and the comparison does not work.

The raw numbers looked decisive: our overlay strip grows 2.10x over 40 s, the
reference's 1.23x. **The saturation correction destroys it.** Growth is bounded by
the dark area available, and the two sides start nothing like each other:

| source | strip lit at start (thr>80) | ceiling | measured | headroom used |
|---|---|---|---|---|
| ours-161403 | 14.3% | 7.01x | 2.10x | **18.3%** |
| ours-102150 | 17.5% | 5.70x | 1.81x | **17.2%** |
| reference   | 38.6% | 2.59x | 1.23x | **14.5%** |

18.3% against 14.5% is not a discrimination. **At a lower threshold it is actively
misleading:** the reference's strip is 86.4% lit, its ceiling is 1.16x, and its
measured 1.11x is pinned against that ceiling — a column that reads as a crisp
confirmation and means nothing.

**THE CAUSE IS STRUCTURAL AND WILL NOT GO AWAY.** The reference's overlay strip is
far more lit because it contains the backdrop A561 established is *missing* from
ours. **A218's fault lives inside the region A219's metric counts.** No threshold
escapes it: a high one trades the ceiling problem for a small-sample one.

This retro-justifies a scoping decision A247 made without giving this reason — it
compared frame N against frame N+3 *within* one recording. That was not caution;
within-run was the only comparison available.

**WHAT TO DO INSTEAD:** stay within one recording, or find a region where the two
builds have comparable baseline lit area (A562's falsifier — nobody has looked).
**AND ALWAYS PRINT THE CEILING NEXT TO THE MEASUREMENT.** A562's C1 and C2 both
passed and would have shipped a confident wrong conclusion on their own; only the
ceiling column caught it.

**Controls worth copying for any lit-area metric:**
* **C1 FLAT** — feed N identical frames; growth must be exactly 1.000 each time.
  Catches counting code that carries state between samples, which would manufacture
  an accumulation result out of nothing.
* **C2 DECREASING** — feed a genuinely shrinking lit set (same frame at rising
  thresholds); growth must fall below 1. **This is the one that proves the metric
  can read removal at all**, which is precisely what an "added and never removed"
  claim needs and what A247 never had.
* **C3 SATURATION** — the ceiling table above. The only one that failed.

## `gdb_hangdump.sh` + `SNP_RDRAM_DUMP` — game memory at a HANG (added 2026-08-27, A580)

**Purpose.** A211's freeze is a hang, and until now nothing captured RDRAM at
one: `gdb_fault.sh` dumps memory but needs a crash signal; the hang script
caught the freeze but recorded thread backtraces only (A577 named the gap).
Now `SNP_RDRAM_DUMP=<path> scripts/gdb_hangdump.sh <settle_s> <out.txt>` also
snapshots the first `SNP_RDRAM_MB` (default 8) MB at the interrupt, readable
with `scripts/rdram_peek.py`.

**Mechanism, and why it transfers.** The fault script's snapshot is pure gdb —
`dump binary memory` off the global `g_rdram_base` — not a fault handler, so
it fires at ANY stop, including the hang script's SIGINT. Transplanted
verbatim with **one deliberate difference**: the `.ctx` register file is
guarded separately, because at an arbitrary interrupt the stopped frame is
usually not recompiled code and `ctx` does not resolve (A122's trap). A
missing `.ctx` prints its reason and does NOT discredit the memory dump.

**Controls (T71), run 2026-08-27 on the healthy debug binary, 25 s settle:**
* dump exists at exactly 8,388,608 B; the thread dump still produced 57
  sections, so the addition broke nothing it sits beside;
* `.ctx` correctly absent with the guard's message ("No symbol ctx in current
  context"), which is the A122 case firing as designed, not a failure;
* content read back sanely: the matrix-stack top (`0x80068A84`) read
  `0x80068284` — its own base, which held the identity matrix. That is also an
  independent confirmation of A572's hand-derived base on a fresh run.
* without `SNP_RDRAM_DUMP` the block prints "RDRAM skipped", so silence is
  distinguishable (T65).

**The measurement it exists for:** run with settle ≈ 215 s to land past the
212.87 s freeze (A452), then read `0x80068A84` from the snapshot. Far above
`0x80068284` revives the runaway-stack story for t=207 (A566); at/near base
kills it everywhere and sends A211 after a different writer. Two-sided either
way (A573/A577).

**Incident that motivated it:** A573 could refute the runaway story only at
the A99 crash, because that was the sole moment with a snapshot; the t=207
hang had none.

## Overlay RESIDENCY must be checked before reading any overlay global (added 2026-08-28, A604, after A594)

**The trap.** Overlays share the window at `0x800E4780`, so an address there names
a LOCATION, not a function. A594 read four words believing they were
`ovlfile23`'s state; they were another overlay's INSTRUCTIONS — one of them
decoded as `jal 0x8002AD54`. It was one plausible-looking integer away from a
false finding, and what caught it was decoding the words as MIPS, not judging
whether they looked reasonable.

**The check.** `ovl_resident.py <snapshot> <function>` takes the overlay's first
four instructions from the generated C — ground truth for what that overlay
contains — encodes them, and compares against the snapshot at the same vram.

**Four words, not two, and this is measured.** `addiu $sp,$sp,-N; sw $ra,0x10($sp)`
is the prologue of nearly every function. At t=12 s A594's snapshot holds exactly
that pair at `0x800E6B58` — one word offset, then a *different* `lui` immediate.
**A two-word fingerprint would have false-positived there.** Four words including
a distinctive store discriminates.

**Controls (A604):**
* **POSITIVE** — a function OUTSIDE the overlay window is always mapped and must
  read resident. `boot_func_800271F8` reads True in all three snapshots tested.
  **Use one whose first four instructions are `addiu`/`sw`/`lui` only:** the
  encoder handles that subset and REFUSES (returns `None`) on anything else. A
  first attempt used `boot_func_80029070`, whose prologue contains `sdc1`/`mov.s`,
  and the control returned `None` — *a control that did not run is not a control*,
  and the refusal is only correct because it is loud.
* The encoder never guesses: an unencodable instruction returns `None` and the
  verdict is withheld, rather than comparing a partial fingerprint.

**Result it enabled:** `ovlfile23` IS resident at t=6 s, inside A225's 4.0–8.5 s
logo window, and is NOT at t=12 s, t=190 s or t=215 s. So the logo overlay loads;
its globals are legitimately readable at t=6 s and nowhere else tested.

## `ares --dump-log` — the reference's draw commands, headless, one command (added 2026-08-28, A607, user's question)

**It already exists and has already been used.** A454 joined the real game's
logo frame to ours using dumps produced this way; they are on the archive from
2026-08-25 (`rdp-f60/f120/f150/f200/f240/f250/f360/f480.txt`).

```
ares --system "Nintendo 64" <rom> --dump-log <rsp|rdp|rsp+rdp>:<after-frames>[:<count>]
```

Dumps to **stdout after N presented frames, then quits** — no GUI, no debugger
panel, works under `display_isolate.sh` like any other run. Verified 2026-08-28:
`--dump-log rdp:120:1` returned 192 RDP commands and **reproduced A454's
eighteen-Tex-Rect logo grid exactly** (6 wide x 3 tall, x from 64, y 80/112/144
after the /4 conversion).

**FORMAT:** `RDP <index> <CommandName> <decoded operands> <raw hex>`, grouped by
`=== frame N (R RSP + D RDP commands) ===`. Coordinates are **raw 10.2 fixed
point — divide by 4** (A454 confirmed this against four border fills on eight
distinct coordinates, so it is data-confirmed, not documentation-assumed).

**IT IS NOT THE SAME LEVEL AS OUR `[dlgeom]` PROBE, AND THE DIFFERENCE MATTERS:**

| | our recomp probe | `ares --dump-log rdp` |
|---|---|---|
| level | F3DEX2 **display list** — what the game submits | **RDP command stream** — what the RSP emits |
| geometry | `G_VTX`/`G_TRI`, object space, pre-cull | screen-space triangles, **post-transform, post-cull** |
| rects | `G_TEXRECT`/fills | `Tex-Rect`/`Fill-Rect`, near 1:1 with the above |

* **Rectangles join almost directly** — that is why A454 worked.
* **Geometry does not join directly**, and that is a *feature*: the RDP stream is
  downstream of the RSP's clipping and culling, so geometry present in a display
  list but absent from the RDP stream was **culled**, which our DL census
  structurally cannot see.
* **CAVEAT: our build has no RDP stream at all.** RT64 interprets the display
  list; the F3DEX2 microcode never runs. So this gives the REFERENCE side only,
  and cross-build comparison is DL-vs-RDP unless the rect subset is used.

**The `rsp` half is unavailable for our ROM:** that capture is libdragon RSPQ
(needs an ELF with `rspq_overlay_ucodes` plus `rspq-libdragon.json`) and reports
`RSPQ/F3DEX2 command capture disabled` on every retail run. Do not expect a
display-list-level dump from ares by that route.

**WHY THIS MATTERS:** the "reference tutorial draw-command dump" named as the
decisive next step by A551, A552 and A600 — the answer to far-vs-late (A598),
centre-vs-composition (A600) and the A218/A219 merge (A512) — is this command
with a bigger frame number.

## `rdp_to_stepper.py` — reference draw commands INTO the stepper (added 2026-08-28, A610, user request)

`--dump-log` (A607) gives the reference's RDP stream. Until 2026-08-28 that
stream was **unusable for geometry**: ares's capture stored word 0 and nothing
else, so a triangle could report `y:[592,585,530]` and never say where on the
scanline it was. Rectangles survived intact (which is why A454's logo join and
A607's verification both worked) because a rect fits in one word.

**The ares patch** (`<archive>/evidence/2026-08-28/a610-ares-capture.patch`).
`RDPCapture::Command` now holds `u64 words[22]` + a retained `wordCount`,
mirroring `RSPCapture`'s existing idiom. **Four push sites**, not one:
`rdp/render.cpp`, `vulkan/vulkan.cpp`, and TWO in `angrylion/angrylion.cpp`.
**Which one runs is not obvious and it matters:** `RDP::render()` returns early
whenever a backend renderer is enabled, and our runs print
`angrylion-rdp-plus enabled (CPU renderer)` — so `angrylion.cpp`'s
`captureCommands` is the site that actually feeds our dumps. Patching only the
one named in a grep would have changed nothing observable.

**`rdpCommandWordCounts` in `render.cpp` was WRONG** (`4,9,6,11,8,13,10,15`, and
only 56 of 64 initialisers, so everything past index 24 was shifted). It never
corrupted evidence because its one consumer stored the value in a field neither
the dump nor either viewer printed — but the moment the capture used it to
decide how many words to read, it would have become silently wrong DATA. Correct
values, corroborated three ways (the decoder's own `fetch()` counts, and the
independent copies in `vulkan.cpp` and `angrylion.cpp`): `4,6,12,14,12,14,20,22`.

**The reconstruction.** An RDP triangle is three EDGES. Word 0 has YH/YM/YL in
11.2; words 1/2/3 are the LOW, HIGH and MID edges as signed 16.16 x + dx/dy —
that order, which is `fetchEdge`'s, not alphabetical.

    v1 = (XH, YH)                     v2 = (XL, YM)
    v3 = (XH + DxHDy*(YL-YH), YL)

**CONTROLS, and one of them had to be corrected:**
* **C1** our YL/YM/YH vs the triple ares itself prints (`decode.cpp`, an
  independent decoder). **11848/11848.** This is what makes word 0 trustworthy.
* **C2** XH == XM (major and mid edge share the top vertex; DIFFERENT WORDS, so
  a wrong order breaks it). **It first read 41% failure and that number was an
  artefact of my own check:** 45% of this game's triangles have YM==YH or
  YM==YL, which makes an edge zero-height and XM unconstrained. Excluding those,
  79.4% agree within 1px; the rest miss by a median 2.26px — sub-scanline
  snapping. The WRONG premise (XL on the major edge) holds on 15%, so the check
  still discriminates. **It is a threshold, not an equality.**
* **C2b THE DECISIVE CONTROL IS VISUAL, because C2 is an argument and an
  argument may flag a measurement without settling it (T107).** Rasterise it:
  the correct mapping draws the tutorial corridor with a figure standing in it;
  permuting words 1-3 draws sliver hash. Both panels are in
  `a610-raster.png`, side by side, so "it looks like a picture" ships with its
  own counterexample.
* **`--self-check`** does the same falsification on a synthetic triangle whose
  answer is known, and **asserts the permuted version FAILS** (T65).
* **A control with nothing to test does NOT pass.** Run against a pre-patch
  dump, C2's first version reported PASS on zero reconstructable triangles.
  It now reports `FAIL (nothing to test)`.

**The two sources are NOT the same quantity and the page says so.** Ours is the
display list replayed offline — object space, PRE-cull, grouped by matrix
set-up. The reference is the RDP stream — screen space, POST-transform,
POST-cull, and **its draw groups are CONSTRUCTED by this script** as runs of
primitives between state changes; the RDP stream has no draw boundaries.

**Emit at 320x240, not 640x480.** Our frames are 320x240 and RDP screen space
already is; scaling up would have drawn the reference at twice our scale in the
same canvas and made comparison silently meaningless.

    scripts/rdp_to_stepper.py --self-check
    scripts/rdp_to_stepper.py <dump.txt> --dry-run
    scripts/rdp_to_stepper.py <dump.txt> --frames 2 -o reference.json
    scripts/make_dl_viewer.py ours.json reference.json -o stepper.html

**A filter that hides most of a frame looks exactly like the bug we are
chasing.** The reference draws 942 of 1481 triangles with no depth involvement
at all, and the viewer hides that class by default — a third of the frame, and
it would read as missing geometry. The page now states the hidden count aloud.

## `[dlgeom] s` — the segment table, without which texture bindings are unreadable (added 2026-08-28, A616)

`SNP_DL_GEOM` has emitted `[dlgeom] x <w0> <w1>` for every G_SETTIMG since
2026-08-26 (A480). **Do not "add texture emission" to the probe — read
`events.cpp:797` first.** A613 recommended exactly that and was wrong, because
`dl_render.py`'s "NO TEXTURES, DELIBERATELY" is about the offline RENDERER not
drawing them, not about the probe not emitting them.

**The operands are RAW, and most are SEGMENTED** — 1,013 of 1,209 bindings in a
tutorial frame use segments 6 and 7. The reference's RDP stream reports PHYSICAL
addresses, so without the segment table the two cannot be compared at all. The
walker always tracked the bases; it just never said so. It now prints
`[dlgeom] s <seg> <base>` at each G_MW_SEGMENT, **in list order**, because a
segment can be re-based mid-list and a single end-of-frame table would resolve
earlier bindings with a later base.

    scripts/run_game.sh 210 <log> SNP_DL_CENSUS=1 SNP_DL_GEOM=4800,5100,5400,6000

**SNP_DL_GEOM is inert without SNP_DL_CENSUS** (it lives inside the census
block; measured 2026-08-26). Resolve by replaying `s` and `x` lines in order,
per task — segment state must be reset at each task boundary.

**THE CONTROL THAT MAKES A RESOLUTION BELIEVABLE, and it is not optional:** a
wrong mask or shift produces plausible addresses that match nothing, which reads
exactly like a real deficit. Predict before running that resolved addresses must
land inside the reference's observed range AND that a substantial fraction must
match reference addresses EXACTLY. A616 got **97/97 in range, 97/97 exact** —
our bindings are a perfect subset of the reference's, which is far stronger
evidence than a partial overlap would have been.

**AND WHEN ASKING "IS THIS ASSET IN MEMORY", THE CONTROL IS NOT AN ARBITRARY
ADDRESS.** A614 compared the missing textures against random addresses in the
same region and got 86.3% vs 67.4% — too close to call, because that region is
densely populated. The right control is **the textures the build demonstrably
DOES bind**: same region, same kind of data, guaranteed live. Against that the
answer was immediate — 86.1% vs 86.5%, indistinguishable, so the data is there.

## An ACCESS tap on game globals — BUILT AND RUN (added 2026-08-28, A620's shelf, executed as A622)

**BUILT THE SAME DAY, and the shelf note below was WRONG about the price.** It said "do not
start this with less than an hour" because `recomp.h` is included by all 140 generated files.
**A full rebuild after touching it is 43 SECONDS**, and the instrumented build still reaches
the tutorial in a 200 s run. The estimate was the expensive part, not the work. **Measure a
rebuild before pricing a change on it.**

Result (A622): all three of A619's tables are touched from task 65 onward and keep climbing.
Enable with `SNP_READWATCH=1`; it is inert otherwise. **Totals print on a control-count
boundary, which is too coarse to read tutorial-specific rates — make it per-task if that is
the question.**

### The original design note, kept because its three gotchas all held

## A read-watch on game globals — the design (2026-08-28, A620's shelf)

**The question it answers:** A619 found three tables in the game's globals
(0x8006C044, 0x80070700, 0x800712C4) fully populated with pointers into the
missing texture bank by tutorial time. **Are they ever consulted?** Nothing we
have can say. `SNP_WATCH` is a 1 Hz sampler reporting CHANGES; `ARES_WATCH` logs
STORES and is reference-side; A620's static scan cannot see computed addressing.

**Why it was shelved rather than attempted on 2026-08-28:** `recomp.h` is
included by all 140 `RecompiledFuncs/*.c`, so any change is a full rebuild, and
the tap fires on EVERY memory access in the game. **Both the build time and the
instrumented run's speed are unknown**, and a run too slow to reach the tutorial
(~168 s native) produces nothing. Do not start this with less than an hour.

**The design, so the next attempt is short.** The macros are plain lvalue
expressions (`recomp.h:95`):

    #define MEM_W(offset, reg) \
        (*(int32_t*)(rdram + ((((reg) + (offset))) - 0xFFFFFFFF80000000)))

so a tap goes on the computed OFFSET without disturbing lvalue-ness:

    (*(int32_t*)(rdram + SNP_TAP((((reg) + (offset))) - 0xFFFFFFFF80000000)))

with `SNP_TAP` a no-op unless a build flag is set, and the range test INLINE so
the common path is a predictable branch and never a call.

**THREE THINGS THAT WILL BITE:**
* **Reads and writes are indistinguishable here.** `MEM_W(reg, offset)` (read)
  and `MEM_W(offset, reg)` (write) both reach the same macro and addition is
  symmetric. **That is fine for the actual question** — "is this table touched
  at all after it is filled" — but do not report it as a read-watch.
* **`recomp.h` is included from `.c` files**, so the hook must be C-compatible;
  declare the callback `extern "C"` on the runtime side.
* **Only instrument MEM_W.** The tables are word arrays; tapping every width
  multiplies the cost for nothing.

**The control:** watch a known-hot global as well — the matrix-stack top
0x80068A84, which A566/A620 put at 733 access sites in 293 functions. If that
reports zero the tap is not wired in, and the tables' silence means nothing.

## `check_ledger.py` check 4l — the MERGE gate on threaded work (added 2026-08-29, T231)

**PURPOSE.** Refuse a ledger entry that describes a multi-thread sub-agent run
without recording what the merge found. It exists because of **A713's F3**: two
read-only agents on related targets returned individually CORRECT reports whose
composition was WRONG — an exclusion resting on a register operand the hardware
never reads. That was caught only because the merge question sat in a
pre-registration and was asked deliberately, which left the sole safeguard
against threaded work's main hazard standing on memory. T28 records what happens
to disciplines left there.

**HOW IT TRIGGERS — two signals, both required.**

* Signal 1: two distinct thread labels (`THREAD 1`, `Thread B`), **or** the bare
  plural `threads`.
* Signal 2: a sub-agent marker — `sub-agent`, `agent`, `Fable`, `Opus`,
  `agent-brief`.

**Signal 2 is not optional and is the whole reason this is usable.** This project
writes about the GAME's threads constantly (B59's thread 4 / thread 17, I5's two
threads both reporting id 3). Triggering on the word alone would fire on every
runtime entry, and T118 measured a 6-of-7 noise rate on a nag that fired
regardless of whether it had anything to say.

**WHAT SATISFIES IT.** A `MERGE:` line of 20+ characters saying whether any
thread's claim needs something another thread denies. **"No collision, and here
is what I compared" is a complete answer.** Silence is not.

**CONTROLS — `scripts/test_check_ledger.py`, control `merge_case`, 5 directions:**
fires when missing; SILENT when answered; **SILENT on the GAME's threads**; fires
on a stub answer; catches the plural-only shape. Intact **38/38**. With the
sub-agent guard replaced by a regex matching anything, **37/38 with only
`game-threads` flipping** — verified, not assumed.

**TWO CONTROLS THAT LOOKED GREEN AND TESTED NOTHING. Read this before writing
another one.**

1. The first deliberate break was a **syntax error**. Every case went False and
   the suite "failed" — but it was measuring *the script crashed*, not *the guard
   is broken*. **A crash-detector does not discriminate.** Make the break
   semantically valid and confirm the file still parses.
2. The second break was valid and **the control passed anyway**. The
   game-thread fixture said `THREAD 4 ... THREAD 17`, and `17` never matched the
   single-character label pattern — so signal 1 never fired and signal 2 was
   never exercised. **The case was silent for the wrong reason.** T65 exactly,
   and it would have shipped as a green tick. A negative control must be
   constructed so that ONLY the thing under test can keep it quiet.

**A THIRD BUG, CAUGHT BY READING THE OUTPUT (T71 gate 1).** The first message
said *"describes 0 threads"* — it printed the label count, which stops being the
trigger once the plural signal exists. A checker stating a confidently wrong
number is the failure this file exists to catch.

**OPERATIONAL WARNING.** The break/restore cycle **timed out mid-run once and
left `check_ledger.py` broken on disk.** Take a `sha256sum` before breaking
anything and verify after restoring; without it, every later run that session is
silently unguarded.

**KNOWN LIMITS, stated rather than patched.**

* It cannot tell an entry that **is** a threaded run from one that **discusses**
  one (T121's mention-vs-use, third instance on this project). T231 trips its own
  check. Answering costs one sentence, so the conservative direction is right —
  but do not let that breed `MERGE:` lines that say nothing.
* **It sees whether a merge was RECORDED, never whether one was PERFORMED.** A
  dishonest line satisfies it exactly as a real one does. This is a floor, not a
  guarantee.
* Baseline `{"A": 709, "T": 229}` — no historical entry is examined.
