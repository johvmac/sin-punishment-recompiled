# START HERE — the message that opens a post-clear session

**Paste the block below as the first message of a fresh chat.** It exists
because a `/clear` leaves nothing, so the first turn has no idea what happened
(P7 in `protocols-draft.md`).

**It is a POINTER, not a summary.** Everything it names lives in a file that is
kept current. If you find yourself adding facts here, they belong in the
handoff instead — a second copy is a copy that goes stale, and this is the one
file whose reader is least able to notice it has.

**Keep it under a screen.** Exactly two things go stale, and both are marked
with **`«…»`** so they can be found and checked: **the handoff filename** and
**the one-line blocker**. The guillemets stay in THIS FILE; only what is *inside* them is replaced, and P7 step 5 refreshes both at clear time. **They are STRIPPED when the block is pasted into chat** — a maintenance mark for this file, not part of the message. Stripping is a deterministic transform, not a second copy.

> **Why they are marked at all.** This file used to say "update the two
> bracketed bits" with nothing bracketed — so there was no way to locate them
> and no way to check them. On 2026-08-26 the handoff was renamed
> `HANDOFF-2026-08-25.md` → `HANDOFF-2026-08-26.md` and **this file went on
> naming a file that no longer existed**: a first message pointing at nothing,
> handed to the one session least able to work out why. The marks exist so a
> checker can read the filename out and `stat` it.

---

```
Sin & Punishment recomp session. Start by reading «HANDOFF-2026-08-26.md» in
the repo root — it is gitignored so it will not appear in any repo listing;
open it by path. Run its [ONCE] steps in order before anything else, and do
not skip them because you think you know the state:

  0a. WebFetch the status page and merge BOTH kinds of click into the
      archive file BEFORE any regenerate or publish.
  0.  Settle the observed-run gate — ask me to watch one, or I'll give you
      a deferral reason.
  0b. Any user-directed work greps the visited set first
      (scripts/ledger.py --grep '<topic>').

Then read docs/protocols-draft.md — it is how we run recurring work, it is a
draft, and it has a deviations log you should add to rather than work around.

Where we left off: «the sound works and is the right music, but it slides ~23
seconds behind the picture over three minutes — measured, and neither slow
playback nor dropouts. That is A463, open at cost 2, and its cheapest next
step needs no knowledge of our audio code: run a DIFFERENT recompiled N64 game
through the same capture and measure ITS drift. Drifts too, the fault is ours
generally; doesn't, it is this build.»

Report the state in a few plain sentences and stop there; I'll say when to
take the first roll.
```

---

## Why each line is there

* **"open it by path"** — the handoff is gitignored; a session that lists the
  repo concludes it does not exist and re-derives the state from scratch.
* **"do not skip them because you think you know the state"** — after a COMPACT
  (not a clear) a summary may assert the gates were done. They were done for
  the *previous* session.
* **the observed-run line** — that gate needs the user's eyes and `route.py`
  refuses to roll without it. The seed asks rather than assumes.
* **the protocols pointer** — otherwise the next session re-improvises P1–P7,
  which is the thing the draft exists to stop.
* **one blocker, named by entry** — not a topic. "Continue the clears work"
  gets nowhere; a blocker with an entry ID gets read.
* **"stop there"** — the user opens the rotation. Every session so far has
  started with them deciding what it is for.
* **the `«…»` marks** — they are not decoration and they are not for the reader
  of the pasted message, who never sees this file. They exist so that the two
  things which go stale can be *found* and *machine-checked*. A file that says
  "update the bits that change" without saying which bits is a file that will
  be pasted stale, and after a clear there is nobody left who knows.

## What this file is NOT

**It is not a state summary and must never become one.** The handoff is the
state; this is the pointer to it. Every fact added here is a second copy with a
reader uniquely unable to notice it has gone stale — which is `CLAUDE.md`'s
standing rule, aimed at its worst case.

**It is not a shortcut past the `[ONCE]` gates.** A seed reading "carry on with
the audio work" invites skipping the observed-run gate and the visited-set
check. **Its job is to get those run, not to get past them.**
