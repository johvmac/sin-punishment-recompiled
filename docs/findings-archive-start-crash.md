# Archive — START crash (SOLVED) : the working-out

Moved out of `docs/findings-ledger.md` on 2026-08-19 under T32's rules, by
DEPENDENCY rather than by age (T46).

**This is not deleted history and not a lesser tier.** The START crash was
root-caused and fixed — `ovlfile02_func_800E4F34` declared `size = 0x14`
against a real `0x8C`, truncating the generated C before the call that
registers the renderer's per-frame reset — and confirmed by the user over
2h36m with no crash (**L1**). What is here is how that was reached.

**`scripts/check_ledger.py` reads this file**, so citations of these IDs from
the live ledger still resolve and do NOT count as dangling (T21). Cite them
freely.

**What deliberately did NOT move**, per T32 and verified mechanically rather
than by eye:

* every **WITHDRAWN** row — B3, B12, B21, B22, B41, B42, B43, B46, B47, B64.
  The retracted beliefs are the highest value-per-byte content in the file.
* every **I-series** and **T-series** row — I5, T11.
* every **OPEN** row — T11, B36.
* every row still cited by something that stays, computed to a fixed point
  rather than assumed: B6, B20, B31, B37, B38, B49, B50, B53, B56, B59, B65.
  For example B53 is held by B12, B21 and T11; B65 by B64.

**26 rows, 1,037 words.** That the return is this small is itself a finding —
see T50.

| # | status | finding | evidence |
|---|---|---|---|
| B4 | EST | Group descriptor: 3 lists at `+0xF8/+0x100/+0x108` with counts at `+0xFC/+0x104/+0x10C`, plus a 4th pair at `+0x114/+0x118` (stride `0x10`). Rewound in `func_8002AA90`, sorted via `func_8002AA3C` -> `func_800387A0` (runs only at `count >= 2`) | 2026-08-18; m2c |
| B5 | EST | Append direction is mode-dependent on `D_80068180` (the *selected* group, set by `func_8002AD54`): `0x80067CA0` up, `0x800677C0` down. The asymmetric rewind is **correct by design** | 2026-08-18; m2c |
| B9 | EST | Gate `D_80068A97`: `!=1` -> reset + 5 populate passes + driver; `==1` -> a path with **no** driver | 2026-08-18; m2c |
| B10 | MEASURED | **Answered by one 30s run — the explore jab paid off.** `D_80068180` held `0x80067CA0` on **all 29 samples** of a full attract run and never took the other group's value (`0x800677C0`), so there is nothing for two threads to disagree about. **Stated limit:** `SNP_WATCH` samples at 1Hz, so a sub-second toggle would be invisible — this is "constant at 1Hz across 30s", not "provably never changes". Also **I5**: two threads report id 3, so "thread 3 vs thread 4" was partly ill-posed | 2026-08-18; `SNP_WATCH=0x80068180` |
| B14 | EST | Populate is a **registered-callback walk**: `func_80026A54(n)` walks list `n` of 5 at `D_80068A9C`, calling each entry's fn ptr (`+4`) with `entry+0x10`. A nonzero countdown byte (`+0`) skips, decrements, removes at 0 — real, but never starts nonzero (B50) | 2026-08-18; m2c |
| B15 | EST | Callback lists are managed by **resident** code (`func_80026900/60/A4/AF4/BDC/C34`); overlays register into them | 2026-08-18; asm xref |
| B16 | EST | `func_800263CC` (scene loader) empties all 6 lists via `func_80026900` **and** sets gate `D_80068A97 = 0`. `func_80026900` also resets the allocator arena wholesale — nothing leaks | 2026-08-18; m2c |
| B17 | EST | The game has its own transition guard (`func_800260DC`: 0 normal, 2 triggered, 1 loading) but it **never engages** — `D_80068A97 = 0` at all four thread-3 rewinds | 2026-08-18; `SNP_PHASE` |
| B19 | EST | `D_800681BE` = `D_800681B8 + 6`, the button word written through the pointer by `func_8004C2F8` | 2026-08-18; m2c |
| B24 | OUT | The defensive list-truncation hook fires **0 times** in a START run |
| B25 | EST | In `func_800263CC` the clear-all runs at the **END**, after overlay loading; the only step before the driver is the input poll `func_80026024` | 2026-08-18; m2c |
| B27 | EST | **Scene init is an indirect call through a table** at `D_800591A0` (23 entries, `0xFFFFFFFF`-terminated, ROM `0x345A0`) | 2026-08-18; m2c + ROM read |
| B32 | EST | `D_800599F0` is a **73-entry table covering only the compressed region** (`0x7C8680`-`0xA8CA40`): 28 Yay0 + 44 data, zero raw MIPS. Uncompressed overlays load via `func_8003A1D0` | 2026-08-18; ROM read |
| B34 | EST | **`0x800E4780` doubles as the compressed STAGING buffer.** `func_8003A290` DMAs there then decompresses to a **downward** allocator (`D_800744D8` from `D_800744D4`) | 2026-08-18; m2c |
| B39 | EST | **Scene N ⇔ splat `fileN`, a clean bijection** — all 23 init addresses sit in the `overlay_0` window (`0x800E4780`) and each resolves to a function boundary in exactly one `.s`, files 1-23 in ROM order. Confirmed independently by the recompiler's `ovlfileNN_` prefixes | 2026-08-18 |
| B40 | EST | START is detected in attract's chained callback `func_800E6D4C` as `D_800681BE & 0x1000`; it sets `D_8012E4B8 = 3`, and the next frame sets `D_80068A95 = 1` | 2026-08-18; m2c |
| B45 | EST | **Crash mechanism, measured.** Healthy frame b1 `ptr=0x802BA6A0 n=83`, b2 `ptr=0x802B9EA0 n=7`; fatal frame same counts, `ptr=0x802BA554` / `0x802B9E84` — each down by exactly `count*4`, unrestored. Append raises the pointer, the rewind lowers it; they balance **only while appends happen** | 2026-08-18; `SNP_SORT=1` |
| B52 | OUT | Allocator failure — heap handle valid at every registration; `func_80026900` resets the arena wholesale |
| B55 | EST | **Scene sequence on START = 23 (attract) -> 1 -> 20 -> 2.** The crash was always the *fourth* load | 2026-08-18; scene-number probe |
| B57 | EST | **USER-CONFIRMED, clean build.** START at t≈12s: no crash; ran 2h36m with non-gfx threads at +30/s throughout | 2026-08-18; user + 9,400s heartbeat |
| B58 | EST | **Visual proof the fix landed.** Screen fades to **white** on START — scene 2's init ends `func_80038214(-0x100 x4)`, a white fade and statement **8 of 9** (every other scene passes `0xFF x4`). Pre-fix it stopped at statement 1 | 2026-08-18; m2c + user |
| B60 | EST | Scene 2's overlay has **no other truncated symbol**. Its two remaining size gaps (`func_800E47B4` declared `0x128`, `func_800E4E64` declared `0x30`) are **correct** — splat's own `endlabel` agrees with the symbol file and the recompiler emitted every instruction (81 and 12, spanning exactly to the declared end). The `.main` section has **zero** gaps. The gaps are unlabelled data, not defects | 2026-08-18; splat endlabel + generated-C address span |
| B61 | EST | **Thread map** (`SNP_STACKS=1`): t1 pri10 `0x80025CA4`; **t3 pri10 `0x80025E44` = the scene loop**; t3(!) pri70 `0x80052064`; **t4 pri50 `0x8004DD0C`**; t5 pri60 `0x8004D7C8`; t6 pri115 `0x8004EAD0`; t17 pri100 `0x8004E640`; t18 pri110 `0x8004E4A0`; t19 pri120 `0x8004E154` | 2026-08-18 |
| B62 | EST | **Thread 4's loop is a two-slot dispatcher.** `func_8004DD0C` blocks on queue `D_8007D0E8`, then: msg **1** -> call `D_8007AF0C(D_8007AB94)`; msg **2** -> call `D_8007AF10()`. **Both slots are plain function pointers, and a NULL slot means the message is consumed and nothing happens.** Set by `func_8004D500(fn)` -> `D_8007AF0C` and `func_8004D54C(fn)` -> `D_8007AF10` | 2026-08-18; m2c |
| B63 | EST | **CAUSE OF B56 LOCATED.** `SNP_WATCH` on both slots across the transition: `D_8007AF0C = 0x800261FC` and `D_8007AF10 = 0x80026598` for 12 samples, then **both `0x00000000` for every sample to end of run**. They are cleared exactly at the stall and **never restored**, so thread 4 keeps consuming its 30/s messages and dispatches nothing. This is precisely B59's "producer stop" | 2026-08-18; `SNP_WATCH=0x8007AF0C,0x8007AF10` |
| B66 | EST | **Behavioural confirmation:** with `SNP_STACK_RELOC=4` and scripted START at t=12s, graphics run **straight through the transition** to 848 tasks at t=29s, +30/s, **zero stalls** — where the same run without it stalls at 354-370. The one workaround kills both symptoms | 2026-08-18 |
