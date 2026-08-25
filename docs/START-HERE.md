# START HERE — the message that opens a post-clear session

**Paste the block below as the first message of a fresh chat.** It exists
because a `/clear` leaves nothing, so the first turn has no idea what happened
(P7 in `protocols-draft.md`).

**It is a POINTER, not a summary.** Everything it names lives in a file that is
kept current. If you find yourself adding facts here, they belong in the
handoff instead — a second copy is a copy that goes stale, and this is the one
file whose reader is least able to notice it has.

**Keep it under a screen.** Update the two bracketed bits when they change:
the handoff's date, and the one-line blocker.

---

```
Sin & Punishment recomp session. Start by reading HANDOFF-2026-08-25.md in
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

Where we left off: the real game's tutorial frame is captured at
<archive>/evidence/2026-08-25/REFERENCE-tutorial-real-game.png and shows the
walkway, buildings and sky that our build leaves black. The next checkpoint is
one blocker wide — see T201.

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
