# Session log

Append-only. Written by `scripts/session.py end`.

| started | ran / planned | rolls | entries | shelved | blocked | unaccounted | what happened |
|---|---|---|---|---|---|---|---|
| 2026-08-20 17:17 | 24m23s / 30m00s | 5 | 5 | 1 | 0 | 0 | the game now plays past the title screen into the tutorial for the first time, and the user confirmed there is still no sound |
| 2026-08-20 17:59 | 22m01s / 30m00s | 9 | 12 | 0 | 0 | 2 | the game now plays into the tutorial, we measured how the picture degrades, and found that it never actually freezes -- it just stops drawing |
| 2026-08-21 10:01 | 25m51s / 30m00s | 9 | 10 | 1 | 0 | 0 | Found that the on-screen clutter is old drawing that never gets wiped away, opened up every packed picture in the cartridge for the user to look through, and narrowed the silent-audio problem to two specific instructions. |
| 2026-08-21 14:22 | 24m11s / 30m00s | 5 | 6 | 1 | 0 | 0 | Proved the audio recording actually works, then found that another team's fix for a message-delivery bug matches the place our game sits waiting forever, and that our copy still has the broken code. |
| 2026-08-21 14:56 | 25m01s / 30m00s | 9 | 10 | 0 | 0 | 0 | Killed my own best theory about why the game stops drawing -- it goes quiet rather than spinning, which rules that explanation out and leaves the other one standing. |
| 2026-08-21 16:21 | 20m04s / 30m00s | 6 | 6 | 0 | 0 | 0 | Found that when the picture stops the game simply stops asking for frames, which killed both explanations I had borrowed from another project, and proved from the game's own bytes that a function we had recorded as tiny is really twenty times longer. |
