---
name: timed-session
description: |
  Run a bounded, timed working session: a deadline, an optional opening task, then checkpoints until the timer ends or something blocks, finishing with a plain-language summary. Use whenever the user asks to "set a timer for N minutes and work through checkpoints", "run for half an hour then summarise", or any request combining a time box with autonomous progress. Triggers on mentions of a timer plus checkpoints, working until time runs out, or shelving blockers and moving on.
---

# Timed session

The user asks for this shape often enough that it is mechanised:

> "Set a timer for N minutes, start with X, then roll through checkpoints until
> either the timer ends or you hit something that needs me. If one thing blocks,
> shelve it and work elsewhere. Finish with a plain-language summary."

`scripts/session.py` owns the parts that are mechanical. **You own exactly one
judgement: whether a blocker is HARD or SOFT.** Everything else is measured.

## Open the session

```bash
scripts/session.py start 25m "the opening task, if the user gave one"
```

It refuses a second session while one is open, and prints a background command
that fires a notification at the deadline. Run that in the background too — but
**it is a backstop, not the clock.**

Announce to the user: the duration, the opening task, and the roll/ledger
baseline it printed.

## The loop

If the user named an opening task, do that first — it does not need a roll, and
its ledger entry says `user-directed`. Otherwise start with a roll.

Then, repeatedly, an ordinary checkpoint (`CLAUDE.md` is the authority):

1. `scripts/check_ledger.py`
2. `scripts/route.py` — **announce the roll by transcribing it, before the work**
3. the bounded work the roll selected
4. a ledger entry recording the outcome either way, **including its `SO WHAT:`
   line**, then commit, then close with the plain sentence to the user

Between checkpoints:

```bash
scripts/session.py status
```

**NEVER ESTIMATE THE CLOCK.** On 2026-08-20 I judged elapsed time from how much
work had happened and was wrong by up to eleven minutes in both directions —
once almost stopping a session at its halfway point. `status` costs nothing.

## When something blocks

This is the judgement. Ask: **can any other useful work proceed right now?**

**SOFT — yes, something else can proceed.** Record it and move on:

```bash
scripts/session.py shelve "what is blocked" "why work can continue elsewhere"
```

**HARD — no, nothing can proceed until the user answers.** Record it and *stop*:

```bash
scripts/session.py block "what is blocked" "why NOTHING else can proceed"
```

Both take a mandatory reason, and both are reported at the end. A hard block
makes `status` say STOP. **Be honest about which one it is** — "I would rather
ask" is not a hard block, and neither is "this is the most interesting thread".
A hard block means the alternative is fabricating an answer or doing something
irreversible on a guess.

Genuinely hard: a destructive or outward-facing action; a decision only the user
can make; something needing the user's eyes or ears (they can hear audio and I
cannot). Not hard: a missing tool, an unmeasured premise, an expensive run —
those are shelved, and the shelf is where the next session starts.

## Close it

When `status` shows the time is up, **finish the checkpoint you are in** — the
ledger entry and the commit — so nothing is left mid-flight. Then:

```bash
scripts/session.py end "one plain sentence about what happened"
```

It refuses an empty summary, and refuses a jargon one using the same
plain-language test the ledger applies (no addresses, entry IDs, filenames or
registers). It then reports, measured rather than remembered:

* how long it actually ran against how long was planned;
* rolls consumed against entries added;
* **any entry citing neither a roll nor user direction** — work no roll selected,
  which is the drift the user caught by hand on 2026-08-20 (T119);
* everything still shelved, and any hard block.

Finally write the user the **full** plain-language summary — several
paragraphs, no hex, no entry IDs, no tool names. Say what moved, what did not,
and what is waiting on them. `end`'s one-liner goes in the log; the user gets
the readable version.

## What this does not do

It cannot interrupt you, and it cannot decide hard-versus-soft. It makes the
deadline measurable, the shelf durable, the summary required, and drift visible
— the four things that went wrong when this was run by hand.
