# Session log

Append-only. Written by `scripts/session.py end`.

| started | ran / planned | rolls | entries | shelved | blocked | unaccounted | what happened |
|---|---|---|---|---|---|---|---|
| 2026-08-20 17:17 | 24m23s / 30m00s | 5 | 5 | 1 | 0 | 0 | the game now plays past the title screen into the tutorial for the first time, and the user confirmed there is still no sound |
| 2026-08-20 17:59 | 22m01s / 30m00s | 9 | 12 | 0 | 0 | 2 | the game now plays into the tutorial, we measured how the picture degrades, and found that it never actually freezes -- it just stops drawing |
| 2026-08-21 10:01 | 25m51s / 30m00s | 9 | 10 | 1 | 0 | 0 | Found that the on-screen clutter is old drawing that never gets wiped away, opened up every packed picture in the cartridge for the user to look through, and narrowed the silent-audio problem to two specific instructions. |
