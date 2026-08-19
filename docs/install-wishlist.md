# Install wishlist — things that would have saved real time

Requested by the user 2026-08-19. **Every entry names the specific incident that
motivated it.** Nothing speculative: if it is here, it cost us something
measurable, and the cost is stated. Nothing is installed without the user
saying so — these all need `sudo`, which is theirs, not mine.

**Convention:** when a new one comes up, I mention it at the end of a checkpoint
and add a row here. I do not interrupt work for it.

---

## 1. `rr` — INSTALLED 2026-08-19, then MEASURED AS UNUSABLE. Do not retry casually.

**The wishlist's own worked example of why "install it and see" needs a
measurement step.** It was the biggest predicted win here; it does not work on
this target, and that took one wrapper and two runs to establish rather than a
week of intermittent frustration.

* `rr` aborts on ioctls it does not model. SDL's HID probe was disableable
  (`SDL_JOYSTICK_HIDAPI=0`); `DMA_BUF_IOCTL_EXPORT_SYNC_FILE` from the
  Vulkan/RT64 path is not.
* Independently, the gfx rate collapsed to `+0`/`+1` versus a normal `+30`, so
  the timing-anchored 158s repro is unreachable under recording regardless.
* Every attempt raises an apport crash dialog. `scripts/rr_record.sh` refuses by
  default; `SNP_RR_FORCE=1` to retry — **worth doing after an rr upgrade**,
  since the ioctl gap is the kind of thing upstream fixes.
* The sysctl it needed (`kernel.perf_event_paranoid=1`) is set and harmless to
  leave.

## 2. A MIPS binutils  ·  INSTALLED 2026-08-19, validated (T61)

> Working invocation, cross-checked against splat instruction-for-instruction:
> ```bash
> mips-linux-gnu-objdump -D -b binary -m mips:4300 -EB \
>   --adjust-vma=0x80024C00 --start-address=0x800339C8 --stop-address=0x800339F4 baserom.z64
> ```

`decomp.sh` says outright that there is no MIPS toolchain here, so we read the
ROM by hand.

* **What that cost:** T49. I derived a vram→ROM delta from a single anchor,
  misread the anchor by `0x3C`, and produced a clean, plausible, entirely wrong
  dispatch table — caught only because A54 had independently recorded two of its
  values. `mips-linux-gnu-objdump -D -b binary -m mips:4300 --adjust-vma=...`
  disassembles the ROM directly with correct addresses and no hand arithmetic.
* Also lets us verify splat's output rather than trusting it.

## 3. Core dumps — MEASURED AND REJECTED 2026-08-19. Do NOT enable.

**This entry previously recommended enabling system-wide core dumps. That was
wrong and it is corrected here rather than quietly removed.**

* **A core of this process is 11.8 GB** (`generate-core-file` at the A99 fault,
  measured). RDRAM is 8 MB; the recompiler maps a very large writable region and
  gdb dumps all of it.
* Root is at 78% with 40 GB free, and this project crashes the game deliberately
  several times a session. **System-wide cores would have filled the root
  filesystem in about three crashes.**
* The original entry reasoned from the 250 MB binary and attached a disk
  *caution*. A caution is not a measurement — see T63.
* **What to do instead:** `SNP_CORE=<path> scripts/gdb_fault.sh …` writes one on
  demand, no sudo and no system setting touched. For this target the answer is
  still almost always "don't" — re-running `gdb_fault.sh` costs 158 seconds,
  which is cheaper than 12 GB.

## 4. `xdotool` and `wmctrl`  ·  `sudo apt install xdotool wmctrl`

Low value **now that Xvfb is installed** — headless means no window to manage.
Listed because `scripts/minimize_window.py` exists only as a workaround for
their absence, and `boot_screen_check.sh` / `freeze_check.sh` still carry a
python-xlib probe that could be deleted if these were present.

**Recommendation: skip.** Xvfb solved the underlying problem; this would only
tidy up two scripts.

## 5. `valgrind`  ·  `sudo apt install valgrind`

**Probably not worth it, recorded so it is not re-proposed.** The bugs here are
recompilation-semantics bugs in generated C operating on an emulated 8MB RDRAM
block — from the host's point of view every access is a legal write inside one
big `malloc`, so memcheck sees nothing wrong. It would catch host-side bugs in
`N64ModernRuntime`, which is not where our defects have been.

---

## Already present, for the record

`gdb`, `ffmpeg`, `xwd`, `xwininfo`, `ripgrep`, system `python3` **with
python-xlib**, `mesa-vulkan-drivers` including lavapipe (`lvp_icd.json`), and as
of 2026-08-19 `Xvfb`.

**`Xvfb` is the worked example of how this list should be used:** requested,
installed, wired in behind the existing switch, and then **A/B'd before being
trusted** — 60s headless vs 60s nested Xephyr, gfx rate `57x +30` in both, so it
does not perturb the measurement it exists to protect.
