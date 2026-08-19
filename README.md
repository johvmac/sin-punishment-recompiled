<p align="center">
  <img src="assets/repository-banner.svg" alt="Sin &amp; Punishment: Recompiled project banner">
</p>

<p align="center">
  <a href="#project-status"><img src="https://img.shields.io/badge/status-work%20in%20progress-f04b3e?style=flat-square" alt="Status: work in progress"></a>
  <a href="#progress"><img src="https://img.shields.io/badge/phase-3%20in%20progress-f8b84e?style=flat-square" alt="Phase 3 in progress"></a>
  <img src="https://img.shields.io/badge/C%2B%2B-20-72d8ff?style=flat-square" alt="C++20">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-8b93a7?style=flat-square" alt="Platforms: macOS, Linux, Windows">
</p>

# Sin &amp; Punishment: Recompiled

An experimental native PC port of Treasure's **Sin &amp; Punishment: Hoshi no Keishousha**
(Nintendo 64, Japanese release, 2000), built with static recompilation rather than a
traditional decompilation.

The project combines [N64Recomp](https://github.com/N64Recomp/N64Recomp),
[N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime),
[RT64](https://github.com/rt64/rt64), and
[RecompFrontend](https://github.com/N64Recomp/RecompFrontend) to turn a ROM analysis
and symbol map into a native C++ executable.

## Project status

> [!WARNING]
> This is an active reverse-engineering repository, not a finished release. It does
> not ship a ROM, game assets, or a redistributable playable build. The build reaches
> a live, correctly-rendering title screen (see the 2026-08-13 update below), but
> whether controller/keyboard input actually reaches the game from there is not yet
> verified. Full gameplay, menus, two-player support, enhancement features, and
> release QA are all still ahead.

### At a glance

| Area | Current state |
| --- | --- |
| Toolchain | N64Recomp and RSPRecomp build locally; CMake/Ninja tree is wired |
| Reverse engineering | Symbol sections and custom audio microcode have been mapped |
| Runtime | Native window, RT64 presentation, audio callbacks, input callbacks, and overlays are integrated |
| Visual milestone | Reached: a live, correctly-rendering title screen, reproduced on the current build (2026-08-13) |
| Playability | Phase 3 validation is in progress; input handling past the title screen not yet verified |
| Release | No packaged build, ROM distribution, or final QA pass |

## Progress

| Phase | Status | Milestone |
| --- | --- | --- |
| 0 — Toolchain | Complete | Recompiler tools, submodules, scripts, and the CMake tree |
| 1 — Symbols and memory map | Complete | Ghidra-derived symbol data, overlays, and RSP findings |
| 2 — Boot and title screen | Reached | Native executable boots and reaches a live, correctly-rendering title screen (see 2026-08-13 update below) |
| 3 — Runtime completion | In progress | Menus, input, audio, configuration, and two-player verification |
| 4 — Enhancements | Planned | Widescreen, higher internal resolution, high framerate, and modern aiming |
| 5 — QA and release | Planned | Full playthrough, platform matrix, packaging, and troubleshooting documentation |

### Update — 2026-08-13 (evening)

The build now reaches a live, correctly-rendering title screen, reproduced
directly on this build (not just claimed from an earlier checkpoint). Two
more real bugs were found and fixed on top of the boot-blocking fixes from
earlier the same day:

- Two symbol-boundary issues where N64Recomp couldn't resolve a branch that
  jumped into the middle of a neighboring function (a shared-tail/switch-
  statement pattern), and had silently stubbed the affected function to a
  no-op rather than raising a build error. Both functions turned out to be
  on the game's live per-frame path — one was permanently starving a
  scheduler thread, the other was reachable but never taking effect. Fixed
  by correcting the function boundaries in the symbol map so N64Recomp
  compiles the real logic instead of stubbing it.
- A fifth instance of the same struct-validation bug class from earlier the
  same day (a per-client message-queue pointer read from a struct field
  that hadn't been populated yet — see the architecture notes on
  `ultramodern`'s synchronous vs. real hardware's asynchronous PI DMA).

With both fixed, the build passed well over 1,000 rendered graphics tasks
(previously capped at 123, permanently) and shows the actual attract-mode
title sequence, matching a real-hardware reference emulator run frame for
frame. **Not yet verified:** whether a Start button press is recognized by
the game's own input handling — a scripted press was sent and the on-screen
content changed, but it's very likely that was just the attract-mode demo
continuing on its own schedule rather than a real state transition, per
direct comparison against the reference emulator (which also plays a full
demo scene under the "press start" prompt). Input handling is Phase 3 scope
and hasn't been investigated yet.

The checkpoint below, from 2026-08-09, describes an earlier state and is
kept for history; it does not describe the current build.

### Checkpoint — 2026-08-09 (superseded, see above)

- Phases 0–2 were reported complete as of this checkpoint.
- The executable reached the title screen through the native RT64 path.
- The documented stability run reached **4,577 graphics tasks (about 76 seconds) without a crash**.
- The display pipeline was repaired: the title is presented, `osViBlack(0)` occurs once at boot, and the render loop keeps producing graphics work.
- The custom audio ucode is located and recompiles through RSPRecomp; SDL audio callbacks and tracing are wired.
- The Phase 3 foundation is present: recompinput profiles, controller polling, a mouse-to-stick path, a recompui launcher, graphics/input/audio/mod configuration tabs, and a scripted-input test hook.
- The remaining Phase 3 work is validation and correction, not an empty scaffold: navigate title → mode selection → level 1, verify full audio, persist settings, exercise two controllers, and complete the robustness pass.

The title screen milestone above is reproduced on the current build (see the
2026-08-13 update), not carried over from this superseded checkpoint. The
project will not call itself playable until the Phase 3 acceptance criteria
are evidenced.

The public repository intentionally omits internal reverse-engineering notebooks and
session handoffs. The status above is the concise, publishable checkpoint.

## Architecture

```text
Japanese N64 ROM + symbols
             │
             ├── N64Recomp ────────▶ generated game functions
             ├── RSPRecomp ────────▶ generated custom audio ucode
             └── native display lists ─▶ RT64 graphics backend
                                         │
              N64ModernRuntime + RecompFrontend
                                         │
                         SinPunishmentRecompiled
```

The graphics microcode is handled by RT64's native GBI path in the current runtime;
the generated RSP source is used for the custom audio task. This distinction matters
when reading the generated-output rules below.

## Build the developer tree

The repository contains source, configs, symbol data, scripts, and submodule pins.
ROMs and generated output are intentionally ignored.

### Requirements

- macOS with full Xcode installed (RT64 compiles Metal shaders; Command Line Tools alone are not enough)
- Linux with a Debian-compatible package manager, or Windows with Visual Studio 2022/clang and CMake
- Python 3
- A legally obtained Japanese ROM dump matching the project metadata

### Bootstrap and compile

```bash
git submodule update --init --recursive

# macOS/Linux: installs dependencies and builds N64Recomp + RSPRecomp.
./scripts/bootstrap.sh

# Convert a local V64 dump to the big-endian Z64 form used by the project.
mkdir -p rom
python3 scripts/rom_info.py convert \
  "/path/to/your/japanese-dump.n64" \
  rom/sinpunishment.z64
python3 scripts/rom_info.py info rom/sinpunishment.z64

# Generate the C/C++ recompilation output once the local development working image
# expected by sinpunishment.toml is available.
./scripts/recompile.sh

# Configure and build the native executable.
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

The clean `rom/sinpunishment.z64` is the runtime ROM identity. The active
reverse-engineering config currently points N64Recomp at
`rom/sinpunishment_patched.z64`, a development working image that is not distributed
by this repository. The patch inventory and the clean/stored ROM distinction stay
outside the public tree. Until that working-image pipeline is published, a clean
clone is an engineering checkout, not a one-command release build.

### Run the current executable

```bash
# Opens the normal recomp frontend launcher.
./build/SinPunishmentRecompiled

# Developer shortcut: skips the launcher and starts the registered game.
SP_AUTOSTART=1 ./build/SinPunishmentRecompiled
```

Useful development instrumentation:

| Variable | Purpose |
| --- | --- |
| `SNP_TRACE=1` | Logs runtime, audio, and input activity |
| `SNP_AUDIO_DUMP=/tmp/snp_audio.raw` | Dumps queued stereo samples for offline inspection |
| `SP_INPUT_SCRIPT=/path/to/script` | Feeds timed synthetic controller, stick, or mouse-delta input |
| `SP_WINDOW_SIZE=WxH` | Window size; defaults to 640x480, the N64's own hi-res output |

These hooks are for development and validation; they are not release UX.

### Debugging harness

`scripts/decomp.sh <func>` decompiles a ROM function to readable C via
[m2c](https://github.com/matt-kempster/m2c), reading splat's per-function
assembly — no MIPS toolchain or ROM access needed. Prefer it over reading
`RecompiledFuncs/`, which is a literal instruction-by-instruction
transliteration. Point it at your own checkouts with `SNP_SPLAT_DIR`,
`SNP_M2C_DIR` and `SNP_M2C_PYTHON`.

`scripts/shrink_shot.py <png>` downscales a capture to the N64's own ~320x240
before viewing.

`scripts/` also carries the tooling built while chasing boot and attract-mode
defects: `run_game.sh` (the supported way to launch a run with instrumentation),
`freeze_check.sh` and `boot_screen_check.sh` (scripted capture and
black-frame checks), `gdb_watch.sh` and `gdb_threads.sh` (watchpoints and
thread state on the native build), `ares_watch.sh` (compare against
hardware-accurate ares), `resolve_bt.sh` and `probe_stubs.py`.

Deeper runtime instrumentation — per-queue message census, RSP-task heartbeat,
memory watches, scene-walk depth, thread stack layout — lives in
`patches/debug/` rather than in the build, and is applied by hand when needed.
See `patches/debug/README.md` for the switches and for the probe discipline
these scripts assume.

> [!NOTE]
> Any measurement taken through one of these tools needs a positive control
> before a negative result means anything. A probe that never fires and a probe
> that was never reached look identical, and an emulator that has silently
> halted produces the same "nothing ever changed" reading as a running one that
> genuinely never writes.

## Repository map

```text
sinpunishment.toml       N64Recomp configuration and patch/stub list
symbols/                  Ghidra-derived function and data symbols
scripts/                  Bootstrap, recompilation, ROM inspection, and post-processing
src/main/                 Native launcher, runtime callbacks, and overlay registration
src/game/                 Game-specific integration (currently being expanded)
rsp/                      RSPRecomp configs; generated .cpp files are ignored
include/                  Port-facing headers and generated interfaces
patches/                  Port patch helpers and UI integration headers
patches/upstream/         Fixes to pinned submodules, applied by bootstrap.sh
patches/debug/            Opt-in diagnostic instrumentation; NOT applied by bootstrap
lib/                      Pinned RT64, runtime, and frontend submodules
external/N64Recomp/       Pinned N64Recomp toolchain submodule
README.md                 Public project status, build notes, and contribution rules
```

## Roadmap

The next meaningful milestone is not a graphics feature. It is a trustworthy
Phase 3 playthrough:

1. Navigate the title screen and mode selection with keyboard and controller.
2. Reach level 1 and verify the complete input path, including aiming.
3. Check title and level audio for continuity, latency, and synchronization.
4. Confirm settings persist across launches and survive runtime option changes.
5. Exercise two-player assignment and a long session before calling the phase done.
6. Implement mouse input (`InputType::Mouse`), currently an unimplemented
   `// TODO mouse support` in `recompinput`'s `input_state.cpp` — the enum value
   and binding plumbing exist, but both `get_input_digital` and
   `get_input_analog` return "not pressed" for it, so mouse buttons cannot be
   bound at all today. Two things depend on this: left-click for Z (shot/sword),
   and mouse-driven aiming. Aiming matters most — the keyboard defaults bind the
   3D stick (照準の移動, reticle movement) to the arrow keys, which is
   full-deflection-or-nothing and unsuited to a rail shooter whose entire game is
   the reticle. `main.cpp` already has a mouse-delta-to-virtual-stick scaffold to
   build on.
7. Only then move to widescreen, resolution, framerate, and release QA.

The roadmap above is the public summary; detailed acceptance evidence stays in the
development workspace rather than this repository.

## Research and contribution rules

This project has no public decompilation to build on, so reverse-engineering evidence
is part of the implementation. When working here:

- Keep reverse-engineering findings in private notes or issue/PR discussions, with reproducible evidence.
- Keep commits focused and do not commit ROMs, generated recompilation output, build directories, or local runtime state.
- Treat the pinned submodules as upstream dependencies; changes to them need an explicit reason and a reproducible checkpoint.
- Do not describe the project as playable until the acceptance criteria are met.

### Provenance — clean room from the retail ROM

Everything this project knows about the game is derived from static and dynamic
analysis of a **retail ROM that the user supplies locally**. No leaked, stolen, or
otherwise unauthorised source material, internal documentation, or development
artifact has been used.

Concretely, and verifiably from this repository:

- The recompiled C (`RecompiledFuncs/`) and the RSP microcode translations
  (`rsp/*.cpp`) are **machine-generated** on the user's own machine by
  [N64Recomp](https://github.com/N64Recomp/N64Recomp) and RSPRecomp from that ROM.
  Both are `.gitignore`d and **no file from either is tracked in git** — the only
  tracked file under `rsp/` is `audio.toml`, a configuration.
- No ROM is included or tracked; `*.z64` and `rom/` are ignored.
- Symbol names, sizes and addresses in `symbols/` are the project's own hypotheses,
  arrived at from disassembly, [splat](https://github.com/ethteck/splat) output, m2c
  decompilation and runtime measurement. Where a symbol is wrong, the ledger records
  how it was found to be wrong — which is the record of a reverse-engineering process,
  not of a copy.

**Contributors** must not use leaked or unauthorised material, and should not
contribute here if they have consulted such material for this title.

**On AI assistance.** This project uses AI tools (see Credits). Their training data
cannot be independently audited, which is worth stating plainly rather than glossing.
Two things limit the exposure. First, no source code for this title is known to have
been publicly leaked — it is not among the titles reported in the 2020 Nintendo
"Gigaleak" or the iQue leak, and the game was developed by Treasure rather than
Nintendo internally. Second, and more importantly, **the process does not rely on a
model knowing anything about the game**: every game-specific claim in this repository
originates from a tool run locally against the ROM, is recorded with its evidence in
`docs/findings-ledger.md`, and is reproducible without any AI in the loop. AI
assistance is applied to the harness, the analysis method and the write-ups — not as
a source of facts about the game.

## Credits and licensing

This port's original code follows the project's GPL-3.0 licensing intent. The
third-party submodules retain their upstream licenses:

- [N64Recomp — MIT](https://github.com/N64Recomp/N64Recomp)
- [N64ModernRuntime — GPL-3.0](https://github.com/N64Recomp/N64ModernRuntime)
- [RT64 — MIT](https://github.com/rt64/rt64)
- [RecompFrontend — GPL-3.0](https://github.com/N64Recomp/RecompFrontend)
- AI assistance: **DeepSeek Flash** and **Claude** — development and research support.

No ROM or proprietary game asset is included. Use only materials you are legally
entitled to use locally; do not open issues or pull requests containing copyrighted
game data.
