#!/usr/bin/env python3
"""Generate the status page — what the USER should do, not what happened.

WHY THIS EXISTS (T183)
----------------------
The user asked for external visibility so that being aware of the project does
not depend on reading back through a chat. Their framing was the useful one:
make it useful **for making them useful to the project**.

So the page is sorted by ACTIONABILITY, not by category. The top of it is what
they can do right now; the bottom is trend data that answers a question we
cannot answer from inside.

TWO RULES IT IS BUILT AROUND
----------------------------
1. **GENERATED, NEVER HAND-EDITED.** A second hand-maintained copy of project
   state is a copy that goes stale, and this project has a standing rule about
   exactly that. Every number comes from a live file at generation time, and the
   page stamps when it was made so a stale one is obvious rather than misleading.

2. **THE SPLIT THAT MATTERS IS SETUP COST, NOT COUNT.** The user queue's alarm
   counts items, and items are not comparable: some need a real display, a
   launch and three minutes of watching; others are ten minutes at a desk with
   nothing running. **That distinction decides whether they can act right now**
   and it appears nowhere else. It is the first thing on the page.

Usage:
    scripts/status_page.py --dry-run          # say what it would read
    scripts/status_page.py <out.html>
    scripts/status_page.py --self-check
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# ONE PARSER, TWO CALLERS (T192). The ledger reader sections entries too; a
# second copy here would drift and the two views would disagree about what an
# entry says.
from sections import sections as _sections, roundtrip as _sections_roundtrip

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LEDGER = DOCS / "findings-ledger.md"

ROW = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]*)\|\s*(.*)$")
# An item the user can do at a desk: no run, no display, no launch.
DESK = re.compile(r"NO GAME RUN|no display|AT A DESK|no run, no display", re.I)


def _git(*a):
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def _load(name, default=None):
    try:
        return json.loads((DOCS / name).read_text())
    except Exception:
        return default if default is not None else {}


def ledger_rows(text=None):
    """(entries, queue) — queue rows kept separate, as every other tool does."""
    t = text if text is not None else LEDGER.read_text()
    entries, queue, in_queue = {}, {}, False
    for line in t.split("\n"):
        if line.startswith("## "):
            in_queue = "USER QUEUE" in line.upper()
            continue
        m = ROW.match(line)
        if not m or m.group(1) in ("id", "#"):
            continue
        (queue if in_queue else entries).setdefault(m.group(1), (m.group(2).strip(), line))
    return entries, queue


ARCHIVE = Path(os.environ.get("SNP_ARCHIVE", "/media/joh/extra/sin-punishment-archive"))
LABEL_LIST = ARCHIVE / "evidence" / "2026-08-23" / "label-these-16.txt"
USER_LABELS = ARCHIVE / "evidence" / "2026-08-24" / "user_labels.json"


def _given_labels():
    """Labels the USER has already given, so regenerating cannot discard them.

    THE DEFECT THIS FIXES, FOUND THE HARD WAY (T193). The page saves a label by
    republishing itself. The generator builds the page from PROJECT FILES, which
    know nothing about a click. So any regeneration silently produced a page with
    every label blank, and publishing it would have destroyed them.

    **It was caught by a publish CONFLICT, which is luck rather than a check** --
    the conflict only fires when their save is newer than my last read. Had I
    regenerated a minute earlier the label would have gone without a trace.

    So the loop is closed the other way: their clicks are read back off the
    published page and written HERE, into the project record, and the generator
    reads this file. The archive file is the source of truth; the page is an
    input device. Nothing is lost by regenerating, and the labels survive the
    page being deleted entirely.
    """
    try:
        return json.loads(USER_LABELS.read_text()).get("labels", {})
    except Exception:
        return {}

def _labels(entries, text=None):
    """The U10 labelling task, as data the page can render as buttons.

    WHY THE LIST IS READ AND NOT HARD-CODED: `label-these-16.txt` is the single
    source -- it names the sixteen and states the categories. A copy here would
    be a second copy of an evidence file, and this project has watched those go
    stale. The generator REFUSES rather than emitting an empty section if the
    file is unreachable (see main): a page that silently drops the task looks
    exactly like a page where the task is finished.

    WHAT IS DELIBERATELY NOT SENT TO THE PAGE: my labels, and the two sub-agent
    runs. **The whole value of U10 is a key that is not mine** (A371), and a page
    that showed my answer beside the question would collect agreement rather than
    a judgement. `hand_labels.json` is never opened here.
    """
    given = {} if text is not None else _given_labels()
    if text is not None:                      # self-check fixture path
        ids = [k for k in entries if k in ("A1", "A4")]
    else:
        if not LABEL_LIST.exists():
            return None
        ids = re.findall(r"\bA\d+\b", LABEL_LIST.read_text().split("Label each one:")[0])
    out = []
    for i in ids:
        row = entries.get(i)
        if not row:
            continue
        full = _gist(row[1])
        secs = _sections(full)
        # The collapsed line is the entry's OPENING, not a summary. Summarising
        # would put my compression between the reader and the evidence, which is
        # the one thing this task cannot afford.
        row_out = {"id": i, "claim": full[:190] + ("…" if len(full) > 190 else ""),
                   "secs": secs if len(full) > 190 else []}
        if given.get(i):
            row_out["label"] = given[i]
        out.append(row_out)
    return out


def collect(text=None):
    entries, queue = ledger_rows(text)

    live = [(k, v) for k, v in queue.items() if v[0].upper().startswith("LIVE")]
    desk = [(k, v[1]) for k, v in live if DESK.search(v[1])]
    machine = [(k, v[1]) for k, v in live if not DESK.search(v[1])]

    open_items = [(k, v[1]) for k, v in entries.items()
                  if re.match(r"\s*\**OPEN\b", v[0], re.I)]
    parked = [(k, v[0]) for k, v in entries.items()
              if re.match(r"\s*\**\s*(AWAITING|HELD)\b", v[0], re.I)]

    fams = Counter(re.match(r"[A-Z]+", k).group(0) for k in entries)
    wd = sum(1 for k, v in entries.items() if re.match(r"\s*\**WD\b", v[0], re.I))

    away = _load(".away.json", {})
    st = _load(".route-state.json", {})

    obs = (DOCS / "observed-runs.md").read_text() if (DOCS / "observed-runs.md").exists() else ""
    today = date.today().isoformat()
    obs_today = bool(re.search(rf"^## {re.escape(today)}T", obs, re.M)
                     or re.search(rf"^## DEFERRED {re.escape(today)}\b", obs, re.M))

    dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", text or LEDGER.read_text())))
    span = 1
    if dates:
        span = max(1, (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days)

    ideas = []
    f = DOCS / "IDEAS.md"
    if f.exists():
        for line in f.read_text().split("\n"):
            m = re.match(r"^\|\s*(IDEA\d+)\s*\|\s*([\d-]+)\s*\|\s*(\S[^|]*?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
            if m and m.group(1) != "id" and m.group(3).strip().upper().startswith("OPEN"):
                ideas.append({"id": m.group(1), "raised": m.group(2),
                              "idea": m.group(4), "why": m.group(5)})

    def _count(p, pat):
        f = DOCS / p
        return len(re.findall(pat, f.read_text(), re.M)) if f.exists() else 0

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "desk": desk, "machine": machine,
        "open": open_items, "parked": parked,
        "entries": len(entries), "fams": dict(fams), "withdrawn": wd,
        "roll": st.get("roll", 0),
        "away": away, "obs_today": obs_today,
        "span_days": span, "per_day": len(entries) / span,
        "commits": _git("rev-list", "--count", "HEAD"),
        "labels": _labels(entries, text),
        "backlog_open": _count("BACKLOG.md", r"^\|\s*BL\d+\s*\|[^|]*\|\s*OPEN"),
        "ideas_open": _count("IDEAS.md", r"^\|\s*IDEA\d+\s*\|[^|]*\|\s*OPEN"),
        "l1_audits": _count("audit-log.md", r"^## Audit #\d+ — since"),
        "method_pct": 100.0 * fams.get("T", 0) / max(1, len(entries)),
        "ideas": ideas,
    }


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _gist(line):
    """The human-readable text of a ledger row, without the markup."""
    body = line.split("|")
    txt = body[3] if len(body) > 3 else line
    return re.sub(r"\*\*|`|~~", "", txt).strip()


def _summarise(line, n=190):
    """Backwards-compatible one-line gist. Kept for callers that want no toggle."""
    txt = _gist(line)
    return _esc(txt[:n] + ("…" if len(txt) > n else ""))


def _body(line, n=190, pre=""):
    """The row body: a clipped gist, the WHOLE text, and a toggle between them.

    WHY THE FULL TEXT IS EMBEDDED RATHER THAN FETCHED (user's request, 2026-08-24)
    -----------------------------------------------------------------------------
    "it gets cut off and trails with ... - is it possible I could have a button
    which would expand/collapse the full context". Measured before building: all
    14 rows together are 15,350 characters, so carrying every one in full costs
    ~15 KB in the page and ~15 KB again in the frozen shell. That is nothing, and
    it means expansion works with **no network access at all** -- which is not a
    nicety here, because the artifact CSP blocks external requests outright and a
    blocked fetch fails silently.

    NO BUTTON WHEN THERE IS NOTHING BEHIND IT. A control that expands to the same
    text it was already showing teaches the reader that the control is decorative,
    and then they stop pressing it on the rows where it matters.
    """
    txt = _gist(line)
    if len(txt) <= n:
        return f'<span class="body">{pre}{_esc(txt)}</span>'
    return (f'<span class="body">{pre}'
            f'<span class="t">{_esc(txt[:n])}&hellip;</span>'
            f'<span class="f">{_esc(txt)}</span>'
            f'<button class="more" type="button" aria-expanded="false">more</button>'
            f'</span>')


def _status_cell(line):
    """Field 2 of a ledger row. Badges read THIS, never the whole line.

    An entry body can quote `[cost=2]` while discussing the router -- several
    do -- and a whole-line regex would read the quotation as the row's own
    price. Same class of mistake as matching text where structure was meant.
    """
    parts = line.split("|")
    return parts[2] if len(parts) > 2 else ""


def _cost_chip(line):
    status = _status_cell(line)
    """The `[cost=N]` route.py ranks the frontier by, shown to the user.

    THE SCALE IS RELATIVE AND SAYS SO. route.py's own words: "a rough relative
    price (build cycles, run minutes, tokens; the scale only has to be
    consistent)". Printing a bare number invites reading it as hours, so the
    page labels it and the section lede states what it is.

    UNPRICED IS SHOWN, NOT HIDDEN. Rows without a cost sort LAST in the router,
    which means an unpriced item can sit at the back of the frontier
    indefinitely without anyone deciding it should. A blank cell would look like
    a formatting gap; `?` looks like the omission it is.
    """
    m = re.search(r"\[cost=(\d+)\]", status or "")
    if m:
        return f'<span class="cost" title="relative price — see the note above">{m.group(1)}</span>'
    return '<span class="cost none" title="unpriced — sorts last in the router">?</span>'


def _mins_chip(line):
    """`[mins=N]` off a user-queue row -- MY ESTIMATE, and marked as one.

    THE HONEST DIFFERENCE FROM COST, WHICH THE PAGE STATES RATHER THAN BURIES:
    `[cost=N]` already exists in the ledger because the router needs it to rank
    the frontier. **Nothing anywhere estimates how long a user task takes.** So
    these were written by hand, and only where there were grounds -- a row that
    already said "~10 minutes", or a task whose whole content is one keypress.
    Where there were no grounds the chip says `?` instead of a number I made up.

    The user asked for "a task time estimate" and inventing five plausible
    numbers would have answered the request while making the page worse: an
    estimate with no basis is indistinguishable on the page from one with a
    basis, and this project has already been caught stating quantities from
    memory (T178).
    """
    m = re.search(r"\[mins=(\d+)\]", _status_cell(line))
    if m:
        return (f'<span class="cost mins" title="my estimate of your time, '
                f'in minutes">{m.group(1)}m</span>')
    return '<span class="cost none" title="not estimated — I had no grounds">?</span>'


def _fallback_labels(labels):
    """Server-rendered labelling rows, replaced by the runtime once it draws.

    Same reason as the ideas fallback: with no runtime the section must still
    READ, because an empty one looks like a finished task rather than a broken
    page. Without the runtime there are no buttons and the answer goes in chat.
    """
    if not labels:
        return '<p class="empty">Nothing to label.</p>'
    return "".join(
        f'<div class="idea"><div class="head"><span class="rid">{_esc(x["id"])}</span>'
        f'<span class="what">{_esc(x["claim"])}</span></div></div>' for x in labels)


def _fallback(ideas):
    """Server-rendered ideas, replaced by the runtime once it draws.

    If the runtime never runs, the section still READS -- it simply has no
    buttons. An empty section would look like "nothing awaits you", which is a
    silent lie rather than a degraded page.
    """
    if not ideas:
        return '<p class="empty">Nothing awaiting your call.</p>'
    return "".join(
        f'<div class="idea"><div class="head"><span class="rid">{_esc(i["id"])}</span>'
        f'<span class="what">{_esc(i["idea"])}</span></div>'
        f'<p class="why"><b>Not acted on because:</b> {_esc(i["why"])}</p></div>'
        for i in ideas)


def _json(o):
    """JSON safe to embed in a <script> tag."""
    return json.dumps(o).replace("<", "\\u003c").replace("&", "\\u0026")


def _render_raw(d):
    """The ledger ROW is the visual unit -- hairline rules, no cards.

    Grounded in the subject: this project's whole record is dated rows with a
    status column, so the page reads as one. Rounded cards with an accent rail
    are the generic dashboard look and say nothing about what this is.
    """
    def rows(items, empty, tag, tone="", chip=None):
        """chip: a callable turning the row's source text into a leading badge.

        Passed in rather than switched on inside, because the two badges read
        DIFFERENT fields for different reasons -- cost comes off the entry's
        status cell where the router put it, minutes come off a queue row where
        I put it by hand. Conflating them would hide that one is data and the
        other is my estimate.
        """
        if not items:
            return f'<p class="empty">{empty}</p>'
        return "".join(
            f'<div class="row {tone}"><span class="tag">{tag}</span>'
            f'<span class="rid">{_esc(k)}</span>'
            f'{_body(v, pre=chip(v) if chip else "")}</div>' for k, v in items)

    away = d["away"]
    away_html = ""
    if away.get("until"):
        away_html = (f'<p class="note">Prompts that need your eyes are held until '
                     f'<b>{_esc(away["until"])}</b> &mdash; {_esc(away.get("reason", ""))}. '
                     f'They expire by themselves; nothing accumulates.</p>')

    obs = ("recorded" if d["obs_today"] else "not yet")
    obs_tone = "" if d["obs_today"] else "warn"

    return f"""<title>Sin &amp; Punishment &mdash; where things stand</title>
<style>
:root {{
  --ink:#12151a; --paper:#f7f8f7; --dim:#5c6570; --rule:#dfe3e2; --faint:#eef1f0;
  --need:#a8641b; --needfill:#fbf3e8; --ok:#1d6b63; --panel:#ffffff;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --ink:#e8eaea; --paper:#101316; --dim:#8b959e; --rule:#252b30; --faint:#171b1f;
    --need:#d9a05b; --needfill:#20180e; --ok:#5fbfae; --panel:#151a1e;
  }}
}}
:root[data-theme="dark"] {{
  --ink:#e8eaea; --paper:#101316; --dim:#8b959e; --rule:#252b30; --faint:#171b1f;
  --need:#d9a05b; --needfill:#20180e; --ok:#5fbfae; --panel:#151a1e;
}}
:root[data-theme="light"] {{
  --ink:#12151a; --paper:#f7f8f7; --dim:#5c6570; --rule:#dfe3e2; --faint:#eef1f0;
  --need:#a8641b; --needfill:#fbf3e8; --ok:#1d6b63; --panel:#ffffff;
}}
*, *::before, *::after {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--paper); color:var(--ink);
  font:400 16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;
  -webkit-font-smoothing:antialiased;
}}
.sheet {{ max-width:47rem; margin:0 auto; padding:2.6rem 1.15rem 5rem; }}

.masthead {{ border-bottom:2px solid var(--ink); padding-bottom:.7rem; }}
h1 {{
  font:600 1.55rem/1.2 Georgia,"Iowan Old Style","Times New Roman",serif;
  margin:0; letter-spacing:-.012em; text-wrap:balance;
}}
.stamp {{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.72rem; color:var(--dim); margin:.5rem 0 0;
  font-variant-numeric:tabular-nums; letter-spacing:.01em;
}}

h2 {{
  font:600 .82rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;
  text-transform:uppercase; letter-spacing:.11em; color:var(--dim);
  margin:2.7rem 0 .1rem; padding-bottom:.4rem; border-bottom:1px solid var(--rule);
}}
h2.pull {{ color:var(--need); border-bottom-color:var(--need); }}
.lede {{ font-size:.9rem; color:var(--dim); margin:.75rem 0 1rem; max-width:36rem; }}

.row {{
  display:grid; grid-template-columns:4.4rem 3rem 1fr; gap:.75rem; align-items:baseline;
  padding:.72rem 0; border-bottom:1px solid var(--faint);
}}
.row.need {{ background:var(--needfill); padding-left:.6rem; padding-right:.6rem;
  border-bottom-color:var(--rule); }}
.tag {{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.63rem;
  text-transform:uppercase; letter-spacing:.09em; color:var(--dim); padding-top:.22rem;
}}
.row.need .tag {{ color:var(--need); font-weight:600; }}
.rid {{
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.78rem;
  color:var(--ink); font-variant-numeric:tabular-nums;
}}
.body {{ font-size:.9rem; }}
.empty {{
  font-size:.88rem; color:var(--dim); padding:.9rem 0; margin:0;
  border-bottom:1px solid var(--faint);
}}
.note {{
  font-size:.85rem; color:var(--dim); background:var(--faint);
  border-left:2px solid var(--rule); padding:.6rem .8rem; margin:1rem 0 0;
}}

.figures {{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(7rem,1fr));
  gap:0; margin-top:1rem; border-top:1px solid var(--rule);
}}
.fig {{ padding:.85rem .2rem .85rem 0; border-bottom:1px solid var(--faint); }}
.fig .v {{
  font:600 1.5rem/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums; letter-spacing:-.03em;
}}
.fig .l {{
  font-size:.68rem; text-transform:uppercase; letter-spacing:.09em;
  color:var(--dim); margin-top:.35rem;
}}
.fig.mark .v {{ color:var(--ok); }}

.reading {{ font-size:.88rem; color:var(--dim); margin:1.3rem 0 0; max-width:38rem; }}
.reading b {{ color:var(--ink); font-weight:600; }}
footer {{
  margin-top:3.4rem; padding-top:.9rem; border-top:1px solid var(--rule);
  font-size:.76rem; color:var(--dim);
}}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em; }}
.idea {{ padding:.85rem 0; border-bottom:1px solid var(--faint); }}
.idea .head {{ display:flex; gap:.7rem; align-items:baseline; flex-wrap:wrap; }}
.idea .rid {{ flex:0 0 auto; }}
.idea .what {{ font-size:.92rem; flex:1 1 18rem; }}
.idea .why {{ font-size:.83rem; color:var(--dim); margin:.35rem 0 0; }}
.idea .why b {{ color:var(--ink); font-weight:600; }}
.acts {{ display:flex; gap:.4rem; margin-top:.6rem; flex-wrap:wrap; }}
button {{
  font:600 .74rem/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  text-transform:uppercase; letter-spacing:.07em;
  padding:.44rem .7rem; border:1px solid var(--rule); background:transparent;
  color:var(--dim); border-radius:2px; cursor:pointer;
}}
button:hover {{ border-color:var(--ink); color:var(--ink); }}
button:focus-visible {{ outline:2px solid var(--need); outline-offset:2px; }}
button[aria-pressed="true"] {{ border-color:var(--need); color:var(--need); background:var(--needfill); }}
.verdict {{
  font:600 .7rem/1 ui-monospace,monospace; text-transform:uppercase;
  letter-spacing:.08em; color:var(--ok); padding-top:.2rem;
}}
.verdict.no {{ color:var(--dim); }}
.saving {{ font-size:.76rem; color:var(--dim); margin-top:.5rem; min-height:1.1em; }}

/* EXPAND / COLLAPSE. The full text is always in the document; only its
   visibility changes, so nothing is fetched and nothing can fail to load. */
.f {{ display:none; }}
.row.open .t, .idea.open .t {{ display:none; }}
.row.open .f, .idea.open .f {{ display:block; }}
.idea.open .f {{ margin-top:.3rem; }}

/* SECTIONS. The wall-of-text fix: the structure is already in the entry as
   all-caps lead-ins, and this renders it instead of running it together. */
.sec {{ display:block; margin:.7rem 0 0; font-size:.88rem; }}
.sec:first-child {{ margin-top:.2rem; }}
.sh {{
  display:block; margin-bottom:.15rem;
  font:600 .64rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  text-transform:uppercase; letter-spacing:.09em; color:var(--need);
}}
button.more {{
  display:inline-block; margin-left:.4rem; padding:.12rem .38rem;
  font:600 .62rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  vertical-align:baseline;
}}
.row.open button.more {{ margin-left:0; margin-top:.5rem; display:block; }}

/* The badges. `.cost` is data off the ledger; `.mins` is my estimate, so it
   is deliberately styled DIFFERENTLY rather than matching -- a reader should
   not have to remember which column is which. */
.cost {{
  display:inline-block; min-width:1.6rem; margin-right:.5rem; padding:.1rem .3rem;
  font:600 .66rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  text-align:center; border:1px solid var(--rule); border-radius:2px;
  color:var(--dim); font-variant-numeric:tabular-nums;
}}
.cost.mins {{ border-style:dashed; }}
.cost.none {{ opacity:.55; }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}

@media (max-width:34rem) {{
  .row {{ grid-template-columns:4.4rem 1fr; }}
  .rid {{ grid-column:2; }}
  .body {{ grid-column:1 / -1; }}
}}
</style>

<div class="sheet">

<header class="masthead">
  <h1>Sin &amp; Punishment &mdash; where things stand</h1>
  <p class="stamp">generated {d['generated']} &nbsp;&middot;&nbsp; roll {d['roll']}
     &nbsp;&middot;&nbsp; {d['entries']} entries &nbsp;&middot;&nbsp; read from the
     project&rsquo;s own files, never hand-maintained</p>
</header>

<h2 class="pull">Needs you &mdash; at a desk</h2>
<p class="lede">No launch, no display, nothing running. The dashed badge is
<b>my estimate of your time, in minutes</b> &mdash; a guess, not a measurement,
and <code>?</code> means I had no grounds to guess rather than that it is quick.</p>
{rows(d['desk'], 'Nothing needs you at a desk.', 'desk', 'need', _mins_chip)}
{away_html}

<h2 class="pull">Needs you &mdash; at the machine</h2>
<p class="lede">A real display and a launch. The setup cost is the whole reason these
are batched: one sitting clears several, one at a time pays it over and over &mdash;
so <b>these minutes do not add up to the sitting</b>. They are time at the keyboard
once the game is already at the right place, and getting there is the shared cost
they all sit behind.</p>
{rows(d['machine'], 'Nothing needs the machine.', 'setup', 'need', _mins_chip)}

<h2>Waiting on nobody</h2>
<p class="lede">Open questions being worked without you. A long list here means
progress is not blocked on your time. The solid badge is the entry&rsquo;s
<b><code>cost</code></b> &mdash; this is real data off the ledger, the number the
router ranks the frontier by. It is a <em>relative</em> price (build cycles, run
minutes, tokens), consistent only against itself, and <code>?</code> means unpriced,
which sends a question to the back of the queue without anyone deciding it should.</p>
{rows(d['open'], 'Nothing open &mdash; which would be unusual.', 'open', '', _cost_chip)}

<h2>Parked</h2>
<p class="lede">Off the rotation deliberately. Each names what would bring it back,
and a check refuses to let one sit unwatched.</p>
{rows(d['parked'], 'Nothing parked.', 'held')}

<h2>Routine</h2>
<p class="lede">Nearly every check fires only when something is genuinely wrong,
so quiet is meaningful rather than ambiguous.</p>
<div class="row {obs_tone}"><span class="tag">watch</span><span class="rid">run</span>
<span class="body">Watched run today: <b>{obs}</b>. It never accumulates &mdash; idle
days owe nothing and a working day owes exactly one.</span></div>
<div class="row"><span class="tag">audit</span><span class="rid">L1</span>
<span class="body">{d['l1_audits']} run, gated on rolls rather than days. The daily
digest above it now waits for new material instead of for midnight.</span></div>

<h2 class="pull">Your call &mdash; not yet decided</h2>
<p class="lede">Ideas I raised and you have not answered. Deciding one here is
recorded on the page itself, so I pick it up next session without you repeating
it. <b>Declining is a real answer</b> &mdash; it closes the item rather than
leaving it to rot.</p>
<!--IB--><div id="ideas">{_fallback(d['ideas'])}</div><!--IA-->
<p class="saving" id="saving"></p>

<h2 class="pull">Label these &mdash; the one thing only you can do</h2>
<p class="lede">Each of these is a finding from the ledger. The question is whether
it is a fact about <b>the game</b> &mdash; Sin &amp; Punishment&rsquo;s own code,
data or behaviour &mdash; or not. That is your own question: is this game
unusually awkward, or are we just being slow.</p>
<p class="lede"><b>&ldquo;Not the game&rdquo; is a complete answer</b>, not a
shrug. The two faint buttons after it &mdash; stack, method &mdash; are optional
detail if you happen to know which; the tools that run it, or the way this
project works. <b>They are genuinely hard to separate and you should not force
it:</b> when I configure a tool, the tool&rsquo;s capability is stack and my
choice of setting is method, and they arrive as one fact in one sentence.</p>
<p class="lede"><b>Why it has to be you.</b> I already have an answer key, but it
is my reading. Two independent runs scored 88% and 100% against it, which measures
<em>agreement with me</em>, not correctness. Yours is the first that would be a
real key. <b>A99 is the one that matters</b> &mdash; it is the crash that dominated
this project, and it is the entry no two readers have labelled the same way.
Partial is genuinely fine; one label is worth more than none.</p>
<p class="lede">My labels are deliberately <b>not shown</b>, and neither are the
two machine runs &mdash; a page that showed you my answer would collect agreement
rather than a judgement. Go with your gut; there is no penalty for a wrong one,
and a disagreement is a more useful result than a match.</p>
<!--LB--><div id="labels">{_fallback_labels(d['labels'])}</div><!--LA-->
<p class="saving" id="lsaving"></p>

<h2>The shape of the work</h2>
<div class="figures">
  <div class="fig"><div class="v">{d['entries']}</div><div class="l">entries</div></div>
  <div class="fig"><div class="v">{d['per_day']:.0f}</div><div class="l">per day</div></div>
  <div class="fig mark"><div class="v">{d['method_pct']:.0f}%</div><div class="l">about method</div></div>
  <div class="fig"><div class="v">{d['withdrawn']}</div><div class="l">withdrawn</div></div>
  <div class="fig"><div class="v">{d['roll']}</div><div class="l">rolls</div></div>
  <div class="fig"><div class="v">{d['commits']}</div><div class="l">commits</div></div>
  <div class="fig"><div class="v">{d['backlog_open']}</div><div class="l">backlog</div></div>
  <div class="fig"><div class="v">{d['ideas_open']}</div><div class="l">ideas unswept</div></div>
</div>
<p class="reading"><b>&ldquo;About method&rdquo; is the figure worth watching.</b>
It is the share of entries about how the work is done rather than about the game.
Whether that means the machinery is load-bearing or that the project has started
substituting method for progress is a live question neither of us can answer from
inside &mdash; which is exactly why a trend may settle it where a single number
cannot.</p>

<footer>
Generated by <code>scripts/status_page.py</code> from the ledger, route log, backlog,
ideas list, audit log and observed-run record. If the timestamp is old, so is the
page &mdash; it cannot refresh itself.
</footer>

</div>

<script id="state" type="application/json">{_json(dict(ideas=d['ideas'], labels=d['labels'] or [], before="%%B%%", mid="%%M%%", after="%%A%%", title="%%T%%", css="%%C%%"))}</script>
<script id="boot">
// State lives in its own JSON tag so republishing never rewrites code, and the
// page is rebuilt from DATA rather than by serialising the live DOM.
(function () {{
  var S = JSON.parse(document.getElementById("state").textContent);
  // NO DOM FALLBACK FOR title/css, AND THAT IS THE WHOLE FIX (2026-08-24).
  // This used to select the first stylesheet element out of the document when
  // the state lacked css -- and the state ALWAYS lacked css, so the "fallback"
  // was the only path. That selection returns the FIRST such element, and the
  // artifact runtime injects its own reset into the head ahead of ours. So a
  // single click froze the PLATFORM'S reset into state as if it were the page's
  // stylesheet, republished an unstyled document, and -- because S.css was then
  // set -- would have kept doing so for every save thereafter.
  //
  // `doc()` below was already rebuilt-from-data and had a control on it. The DOM
  // read had simply moved one line UP, into the bootstrap, where nothing looked.
  // The generator now embeds both, so if either is missing something is wrong
  // with the page itself and the honest move is to refuse rather than to guess.
  var READY = typeof S.css === "string" && S.css.length > 0
           && typeof S.title === "string" && S.title.length > 0;
  var box = document.getElementById("ideas");
  var say = document.getElementById("saving");

  // EXPAND / COLLAPSE (user's request, 2026-08-24). Delegated from the document
  // so it keeps working across a republish: the rows live in the FROZEN SHELL,
  // which this script does not regenerate, and this script is re-embedded from
  // its own text. Nothing here touches state -- which row you have open is a
  // view preference, not a decision, and publishing it would impose your
  // reading position on every other viewer and grow the document for nobody.
  document.addEventListener("click", function (e) {{
    var b = e.target.closest("button.more");
    if (!b) return;
    var row = b.closest(".row") || b.closest(".idea");
    if (!row) return;
    var open = row.classList.toggle("open");
    b.setAttribute("aria-expanded", open ? "true" : "false");
    b.textContent = open ? "less" : "more";
    // Remembered for THIS TAB only, so approving an idea -- which reloads the
    // page from the published copy -- does not silently collapse everything
    // you had opened. sessionStorage can throw in a sandboxed frame; a lost
    // reading position is not worth a broken handler.
    try {{
      var open_ids = [];
      document.querySelectorAll(".row.open .rid").forEach(function (r) {{
        open_ids.push(r.textContent);
      }});
      sessionStorage.setItem("snp_open", JSON.stringify(open_ids));
    }} catch (_) {{}}
  }});

  try {{
    JSON.parse(sessionStorage.getItem("snp_open") || "[]").forEach(function (id) {{
      document.querySelectorAll(".row").forEach(function (row) {{
        var rid = row.querySelector(".rid"), b = row.querySelector("button.more");
        if (rid && b && rid.textContent === id) {{
          row.classList.add("open");
          b.setAttribute("aria-expanded", "true");
          b.textContent = "less";
        }}
      }});
    }});
  }} catch (_) {{}}
  var VERBS = [["yes", "Approve"], ["no", "Decline"], ["ask", "Explain first"]];

  function esc(t) {{
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }}

  function ideasHTML() {{
    if (!S.ideas.length) return '<p class="empty">Nothing awaiting your call.</p>';
    return S.ideas.map(function (it) {{
      var v = it.decision || "";
      var label = v === "yes" ? "approved" : v === "no" ? "declined"
                : v === "ask" ? "explain first" : "";
      return '<div class="idea"><div class="head">'
        + '<span class="rid">' + esc(it.id) + '</span>'
        + '<span class="what">' + esc(it.idea) + '</span>'
        + (label ? '<span class="verdict' + (v === "no" ? " no" : "") + '">' + label + '</span>' : '')
        + '</div><p class="why"><b>Not acted on because:</b> ' + esc(it.why) + '</p>'
        + '<div class="acts">' + VERBS.map(function (p) {{
            return '<button data-id="' + esc(it.id) + '" data-v="' + p[0] + '" aria-pressed="'
              + (v === p[0]) + '">' + p[1] + '</button>';
          }}).join("") + '</div></div>';
    }}).join("");
  }}

  function draw() {{ box.innerHTML = ideasHTML(); }}

  // ---- THE U10 LABELLING TASK -------------------------------------------
  var lbox = document.getElementById("labels");
  var lsay = document.getElementById("lsaving");
  // FOUR OPTIONS, NOT THREE, AND THE COARSE ONE IS NOT A COP-OUT (user, 2026-08-24).
  // T165 -- the item this task serves -- asks its question in BINARY terms: its own
  // text says classify the entries into about-the-game versus about-the-toolchain-or-
  // renderer. The three-way split was added afterwards, by me, and the extra
  // distinction is the one costing the labeller time. "not the game" is a COMPLETE
  // answer to the question actually being asked; stack and method are optional detail.
  //
  // NOT per-entry options, which was the other thing considered: choosing which
  // entries get which buttons would mean deciding in advance where each one sits,
  // and that is the labelling, done by me, in the UI.
  var CATS = [["GAME", "the game"], ["NOT-GAME", "not the game"],
              ["STACK", "· stack"], ["METHOD", "· method"]];

  function labelsHTML() {{
    if (!S.labels || !S.labels.length) return '<p class="empty">Nothing to label.</p>';
    var done = S.labels.filter(function (x) {{ return x.label; }}).length;
    // PROGRESS IS STATED, because "partial is fine" is only credible if the
    // page shows partial as a real state rather than an unfinished one.
    var head = '<p class="lede"><b>' + done + " of " + S.labels.length
      + " labelled.</b> " + (done ? "Saved as you go; stop whenever you like."
                                  : "Nothing yet &mdash; A99 is the one to do first.") + "</p>";
    return head + S.labels.map(function (it) {{
      var v = it.label || "";
      return '<div class="idea"><div class="head">'
        + '<span class="rid">' + esc(it.id) + '</span>'
        + '<span class="what">'
        + (it.secs && it.secs.length
             ? '<span class="t">' + esc(it.claim) + '</span>'
               + '<span class="f">' + it.secs.map(function (s) {{
                   return '<span class="sec">'
                     + (s.h ? '<b class="sh">' + esc(s.h) + '</b>' : '')
                     + esc(s.t) + '</span>';
                 }}).join("") + '</span>'
               + '<button class="more" type="button" aria-expanded="false">more</button>'
             : esc(it.claim))
        + '</span>'
        + (v ? '<span class="verdict">' + esc(v.toLowerCase()) + '</span>' : '')
        + '</div><div class="acts">' + CATS.map(function (p) {{
            return '<button data-id="' + esc(it.id) + '" data-v="' + p[0] + '" aria-pressed="'
              + (v === p[0]) + '">' + p[1] + '</button>';
          }}).join("") + '</div></div>';
    }}).join("");
  }}

  function ldraw() {{ lbox.innerHTML = labelsHTML(); }}

  function doc() {{
    // REBUILT FROM DATA, NEVER FROM THE DOM. A first version took
    // `.sheet.outerHTML`, which the capability contract forbids and which had a
    // concrete bug: "Saving..." is set before publish, so it would have been
    // baked permanently into the published page. The shell either side of the
    // ideas is frozen in state; only the ideas are regenerated.
    var head = '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      + "<title>" + S.title + "<" + "/title>"
      + "<style>" + S.css + "<" + "/style>";
    var body = '<div class="sheet">' + S.before + ideasHTML() + S.mid + labelsHTML()
      + S.after + "</div>"
      + '<script id="state" type="application/json">' + JSON.stringify(S) + "<" + "/script>"
      + '<script id="boot">' + document.getElementById("boot").textContent + "<" + "/script>";
    return "<!doctype html><html><head>" + head + "</head><body>" + body + "</body></html>";
  }}

  box.addEventListener("click", async function (e) {{
    var b = e.target.closest("button");
    if (!b) return;
    var it = S.ideas.filter(function (x) {{ return x.id === b.dataset.id; }})[0];
    if (!it) return;
    if (!READY) {{
      say.textContent = "This page is missing its own stylesheet in state, so "
        + "saving would publish an unstyled copy. Regenerate it; nothing was changed.";
      return;
    }}
    var was = it.decision;
    it.decision = (was === b.dataset.v) ? null : b.dataset.v;   // click again to undo
    draw();
    var api = await claude.use("artifact");
    if (!api) {{
      it.decision = was; draw();
      say.textContent = "This view can show decisions but not save them.";
      return;
    }}
    say.textContent = "Saving\u2026";
    try {{
      await api.publish(doc());
      say.textContent = "Saved. I will pick this up next session.";
    }} catch (err) {{
      var code = err && err.code;
      if (code === "conflict") return;            // another view won; this one reloads
      it.decision = was; draw();
      say.textContent = code === "not_writer" || code === "not_granted"
        ? "Read-only view \u2014 decisions cannot be saved from here."
        : "Could not save (" + (code || "unknown") + "). Nothing was changed.";
    }}
  }});

  lbox.addEventListener("click", async function (e) {{
    var b = e.target.closest("button[data-v]");   // NOT the expand button
    if (!b) return;
    var it = S.labels.filter(function (x) {{ return x.id === b.dataset.id; }})[0];
    if (!it) return;
    if (!READY) {{
      lsay.textContent = "This page is missing its own stylesheet in state, so "
        + "saving would publish an unstyled copy. Regenerate it; nothing was changed.";
      return;
    }}
    // WHICH ROWS ARE OPEN IS REBUILT AWAY BY ldraw(), so it is captured and
    // restored. Losing your place mid-task every time you press a button is the
    // kind of friction that turns "partial is fine" into "I'll do it later".
    var open_now = [];
    lbox.querySelectorAll(".idea.open .rid").forEach(function (r) {{
      open_now.push(r.textContent);
    }});
    var was = it.label;
    it.label = (was === b.dataset.v) ? null : b.dataset.v;      // click again to undo
    ldraw(); reopen(open_now);
    var api = await claude.use("artifact");
    if (!api) {{
      it.label = was; ldraw(); reopen(open_now);
      lsay.textContent = "This view can show labels but not save them.";
      return;
    }}
    lsay.textContent = "Saving…";
    try {{
      await api.publish(doc());
      lsay.textContent = "Saved. Stop whenever you like — partial is fine.";
    }} catch (err) {{
      var code = err && err.code;
      if (code === "conflict") return;            // another view won; this one reloads
      it.label = was; ldraw(); reopen(open_now);
      lsay.textContent = code === "not_writer" || code === "not_granted"
        ? "Read-only view — labels cannot be saved from here."
        : "Could not save (" + (code || "unknown") + "). Nothing was changed.";
    }}
  }});

  function reopen(ids) {{
    lbox.querySelectorAll(".idea").forEach(function (row) {{
      var rid = row.querySelector(".rid"), mb = row.querySelector("button.more");
      if (rid && mb && ids.indexOf(rid.textContent) >= 0) {{
        row.classList.add("open");
        mb.setAttribute("aria-expanded", "true");
        mb.textContent = "less";
      }}
    }});
  }}

  draw();
  ldraw();
}})();
</script>"""


def render(d):
    """Render, then freeze the shell either side of the ideas into the state.

    TWO PASSES, ONE TEMPLATE. The runtime needs the surrounding page as DATA so
    it can rebuild the document without touching the DOM -- but that shell is
    produced by the template itself. Rendering once and splitting on sentinels
    keeps a single source; writing the shell out twice would let the served page
    and the republished one drift apart silently.
    """
    html = _render_raw(d)
    # THREE FROZEN SLICES NOW, NOT TWO. There are two regenerated regions -- the
    # ideas and the labelling rows -- so the shell is before / MID / after, where
    # `mid` is everything between them. Adding the second region as a suffix of
    # `after` would have worked until the first save, which would then have
    # rebuilt the labels from data and pasted the stale copy back underneath.
    head, rest = html.split("<!--IB-->", 1)
    _ideas, rest = rest.split("<!--IA-->", 1)
    between, rest = rest.split("<!--LB-->", 1)
    _labs, tail = rest.split("<!--LA-->", 1)

    sheet_open = '<div class="sheet">'
    before = head.split(sheet_open, 1)[1] + '<div id="ideas">'
    mid = "</div>" + between + '<div id="labels">'
    # THE SHELL MUST STOP AT THE SHEET. `after` originally ran to the end of the
    # document, which swallowed the state script -- so the frozen shell contained
    # the very placeholders being written into it and they replaced themselves.
    body_tail = tail.split('<script id="state"', 1)[0]
    after = "</div>" + body_tail.rstrip().rsplit("</div>", 1)[0]

    # TITLE AND STYLESHEET ARE FROZEN HERE TOO, and they are taken from `head` --
    # the slice BEFORE the ideas sentinel -- not from the whole document. That
    # matters: the boot script further down contains the string literals
    # "<title>" and "<style>", and a regex over the whole page would happily
    # match one of those instead of a real tag. Same trap as T185; the fix is to
    # search a region that provably contains no script, not a cleverer pattern.
    title = re.search(r"<title>(.*?)</title>", head, re.S).group(1)
    css = re.search(r"<style>(.*?)</style>", head, re.S).group(1)

    def enc(x):
        return json.dumps(x)[1:-1].replace("<", "\\u003c").replace("&", "\\u0026")

    for s in ("<!--IB-->", "<!--IA-->", "<!--LB-->", "<!--LA-->"):
        html = html.replace(s, "")
    return (html.replace("%%B%%", enc(before)).replace("%%M%%", enc(mid))
                .replace("%%A%%", enc(after))
                .replace("%%T%%", enc(title)).replace("%%C%%", enc(css)))


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    syn = ("| # | s | f | e |\n|---|---|---|---|\n"
           # A1's body is deliberately LONGER than the clip, so the expand
           # control has something to expand. TAIL is a needle that exists ONLY
           # past the cut -- if the page ever clips instead of hiding, the
           # control below stops finding it.
           "| A1 | OPEN [cost=2] | an open question " + ("padding " * 40)
           + "TAIL-ONLY-PAST-THE-CUT | 2026-01-01 |\n"
           # A4 is SHORT and unpriced: it must get a `?` badge and NO button.
           "| A4 | OPEN | a short open question | 2026-01-03 |\n"
           "| A2 | MEASURED | a settled thing | 2026-01-02 |\n"
           "| A3 | AWAITING THE USER — waits on U7 | parked | 2026-01-02 |\n"
           "| T1 | INTERVENED | method work | 2026-01-02 |\n"
           "## THE USER QUEUE\n"
           "| U1 | LIVE 2026-01-01 [mins=7] | NO GAME RUN, NO DISPLAY — label some entries |\n"
           "| U2 | LIVE 2026-01-01 | Open the inspector and read the panel |\n")
    d = collect(syn)
    chk("splits the queue by SETUP COST", [k for k, _ in d["desk"]] == ["U1"]
        and [k for k, _ in d["machine"]] == ["U2"],
        f"desk={[k for k,_ in d['desk']]} machine={[k for k,_ in d['machine']]}")
    chk("queue rows are NOT counted as entries", d["entries"] == 5, f"got {d['entries']}")
    chk("finds the open item", [k for k, _ in d["open"]] == ["A1", "A4"], f"{d['open']}")
    chk("finds the parked item", [k for k, _ in d["parked"]] == ["A3"], f"{d['parked']}")
    chk("computes the method share", abs(d["method_pct"] - 20.0) < 0.01, f"{d['method_pct']}")

    html = render(d)
    # NOTHING LOADS FROM THE NETWORK. The first version of this asserted "no
    # <script at all", which was the right INTENT expressed as the wrong test --
    # it fired the moment the page grew a deliberate inline runtime. What
    # actually matters is that no request leaves the page: the artifact CSP
    # blocks them, and a blocked font or script fails silently.
    chk("nothing loads from the network",
        "http://" not in html and "https://" not in html
        and not re.search(r"<(script|link|img|iframe)[^>]*\s(src|href)=", html, re.I),
        "an external reference would be blocked, silently")
    chk("the runtime is INLINE and self-reproducing",
        '<script id="boot">' in html and '<script id="state"' in html
        and "claude.use" in html,
        "the decision runtime is missing or would not survive a republish")
    chk("the ideas section READS without the runtime",
        'id="ideas"' in html and "Not acted on because" in html.split('id="ideas"')[1][:4000],
        "an empty section would look like 'nothing awaits you' — a silent lie")
    # THE DEFECT THIS CONTROL EXISTS FOR, and it shipped once: doc() took
    # `.sheet.outerHTML`, which the capability contract forbids AND which had a
    # concrete bug -- "Saving..." is written before publish, so it would have
    # been baked permanently into the page.
    chk("the republished document is rebuilt from DATA, not the DOM",
        not re.search(r"querySelector\([^)]*\)\.outerHTML", html)
        and "S.before" in html and "S.after" in html,
        "serialising the live DOM bakes in transient UI and is forbidden by the contract")
    # THE DEFECT THAT ACTUALLY REACHED THE USER (2026-08-24). The control above
    # guarded doc(); the DOM read had moved one line up into the BOOTSTRAP, where
    # `if (!S.css) S.css = document.querySelector("style").textContent` ran on
    # every load because the state never carried css. querySelector returns the
    # document's FIRST <style>, and the artifact runtime injects its own reset
    # into <head> ahead of ours -- so one click froze the platform's reset into
    # state and republished an unstyled page.
    #
    # ASSERTING THE ABSENCE OF THE READ IS NOT ENOUGH: that is a text test, and
    # the recurring failure on this project is testing the text where the SUBJECT
    # was meant (T185). So this asserts the POSITIVE -- that what lands in state
    # is OUR stylesheet -- by looking for a selector only our sheet defines, and
    # separately that it is not the platform reset it was replaced by.
    state = json.loads(re.search(
        r'<script id="state" type="application/json">(.*?)</script>', html, re.S).group(1))
    chk("the state carries the PAGE'S OWN stylesheet",
        "--needfill" in state.get("css", "") and ".masthead" in state.get("css", ""),
        "css missing or not ours — a republish would ship an unstyled page")
    chk("the frozen stylesheet is NOT the platform's injected reset",
        "color-scheme:light}body{margin:0;padding:0" not in state.get("css", ""),
        "this exact string is what got captured on 2026-08-24")
    chk("the state carries the title, so nothing sniffs it either",
        "where things stand" in state.get("title", ""), f"{state.get('title')!r}")
    chk("the runtime NEVER reads a stylesheet off the DOM",
        not re.search(r'querySelector\(\s*["\']style["\']\s*\)', html),
        "the read that caused it; absence is necessary but not sufficient — see above")
    chk("a page missing its stylesheet REFUSES to republish",
        "READY" in html and "would publish an unstyled copy" in html,
        "silently shipping an unstyled page is how this went unnoticed for a save")
    # EXPAND/COLLAPSE AND THE BADGES (user's requests, 2026-08-24).
    # The first control asserts the WHOLE text is present, not that a button
    # exists: a toggle over text that was already clipped away would look
    # identical on the page and expand to nothing.
    chk("the full text is IN the page, past the clip",
        "TAIL-ONLY-PAST-THE-CUT" in html,
        "expansion would reveal nothing — the text never reached the document")
    chk("a clipped row offers a way to see the rest",
        re.search(r'class="f">[^<]*TAIL-ONLY-PAST-THE-CUT', html)
        and 'button class="more"' in html,
        "the text is there but nothing reveals it")
    # A button that expands to what you can already read teaches the reader that
    # the control is decorative, and then it gets ignored where it matters.
    # ISOLATE A4'S ROW AND ASK WHETHER IT HAS A BUTTON. The first version of
    # this control asserted that the bare text appeared in the page -- and it
    # PASSED against a deliberate break that put a button on every row, because
    # the full-text span holds that same string whether the row is clipped or
    # not. It matched text that exists either way, which is no test at all.
    # BOUNDED AT THE ROW'S OWN CLOSING TAG. Splitting on the opening tag left the
    # LAST slice running to end of document, so it swallowed the labelling
    # section -- which also names A4 -- and the control reported two rows. A row
    # contains spans but never a nested div, so a non-greedy match is exact.
    a4 = [r for r in re.findall(r'<div class="row[^>]*>(.*?)</div>', html, re.S)
          if ">A4<" in r]
    chk("a SHORT row gets no expand button",
        len(a4) == 1 and "more" not in a4[0] and 'class="f"' not in a4[0],
        f"A4 fits in the clip and must render bare; found {len(a4)} matching rows")
    chk("expansion survives a republish",
        "TAIL-ONLY-PAST-THE-CUT" in json.loads(re.search(
            r'<script id="state" type="application/json">(.*?)</script>',
            html, re.S).group(1)).get("before", ""),
        "the frozen shell must carry the full text or a save collapses it forever")
    chk("open rows show the ledger's own cost, and mark the unpriced",
        '<span class="cost" title="relative price' in html
        and '>2</span>' in html and 'class="cost none"' in html,
        "A1 is cost=2 and A4 is unpriced; both must be visible")
    chk("user tasks show MY estimate, visibly distinct from cost",
        'class="cost mins"' in html and ">7m<" in html,
        "an estimate that looks like data is worse than no estimate")
    # THE READ THAT WOULD MAKE BOTH BADGES WRONG. An entry body can quote
    # `[cost=2]` while discussing the router; the badge must read the STATUS
    # CELL, not the line. A2 is not open so it cannot be seen on the page --
    # this tests the parser directly.
    chk("a cost quoted in an entry's BODY is not read as its price",
        _cost_chip("| A9 | OPEN | we set [cost=2] on that one | x |") == _cost_chip("| A9 | OPEN | x | y |"),
        "matching the line instead of the field would price it from prose")
    # ---- THE U10 LABELLING SECTION (user's request, 2026-08-24) -------------
    st = json.loads(re.search(
        r'<script id="state" type="application/json">(.*?)</script>', html, re.S).group(1))
    chk("the labelling task reaches the page as DATA",
        [x["id"] for x in st.get("labels", [])] == ["A1", "A4"],
        f"got {[x.get('id') for x in st.get('labels', [])]}")
    # THE BUTTONS ARE GENERATED AT RUNTIME from an options table, so `data-v="..."`
    # never appears literally in the shipped page -- a first version of these three
    # asserted exactly that and failed against working code. The table IS the
    # contract; it is extracted and read rather than string-matched.
    cats = re.search(r"var CATS = (\[.*?\]);", html, re.S).group(1)
    cats = re.findall(r'\["([A-Z-]+)",\s*"([^"]+)"\]', cats)
    vals = [c[0] for c in cats]
    chk("the labelling row leads with the BINARY question",
        vals[:2] == ["GAME", "NOT-GAME"] and 'id="labels"' in html,
        f"T165 asks about-the-game vs not; got {vals}")
    chk("the optional refinements are still offered, after it",
        vals[2:] == ["STACK", "METHOD"],
        f"a labeller who DOES know which should not have to discard it; got {vals}")
    chk("the coarse answer is its own option, not implied by the other two",
        dict(cats).get("NOT-GAME", "").strip().lower() == "not the game",
        f"{dict(cats).get('NOT-GAME')!r}")
    # THE CONTROL THIS SECTION EXISTS FOR. U10's entire value is a key that is
    # NOT mine (A371) -- so if my label, or either sub-agent's, ever reached the
    # page it would collect agreement instead of a judgement and the item would
    # be worth nothing while still looking done.
    chk("NO answer key reaches the page",
        "hand_labels" not in html
        and not any(k in st for k in ("key", "answers", "hand_labels"))
        and not any(k in x for x in st.get("labels", []) for k in ("answer", "mine", "key")),
        "showing my answer beside the question destroys the only thing U10 buys")
    chk("labels are UNSET until the user sets one",
        all(not x.get("label") for x in st.get("labels", [])),
        "a pre-filled label is an answer key by another name (fixture has no given file)")
    # THE DEFECT T193 RECORDS: regenerating used to blank every label the user had
    # given, because the generator reads project files and a click lives on the
    # page. Their labels are now written back to the archive and read from there.
    # Asserted on the LOADER, since the fixture path deliberately supplies none.
    import tempfile as _tf
    global USER_LABELS
    _u = USER_LABELS
    try:
        with _tf.TemporaryDirectory() as _td:
            USER_LABELS = Path(_td) / "user_labels.json"
            chk("a missing given-labels file is survivable, not fatal",
                _given_labels() == {}, "must degrade to empty, never raise")
            USER_LABELS.write_text('{"labels": {"A9": "GAME"}}')
            chk("labels the user already gave are read back from the project record",
                _given_labels() == {"A9": "GAME"},
                "without this, every regeneration silently discards their work")
    finally:
        USER_LABELS = _u
    # SECOND REGENERATED REGION, SAME TRAP AS THE FIRST. If `mid` were folded
    # into `after`, the first save would rebuild the labels from data and then
    # paste the frozen copy underneath them.
    # ASSERT WHAT `mid` CONTAINS, NOT THAT THE KEY EXISTS. The first version of
    # this asked `"mid" in st`, which stays true when mid is emptied -- and it
    # PASSED against a break that set it to "". Presence is not content; ninth
    # instance of that mistake on this project.
    chk("the shell between the two live regions is frozen separately",
        'id="labels"' in st.get("mid", "") and "Label these" in st.get("mid", ""),
        "one save would rebuild the labels and paste a stale copy under them")
    # ---- SECTIONING (user: "they're kind of just walls of text") -----------
    # THE CONTROL THAT MATTERS IS LOSSLESSNESS. A splitter that silently drops a
    # clause is worse than the wall it replaces, because the reader cannot see
    # the gap. Run over EVERY entry in the real ledger, not the fixture -- the
    # fixture cannot contain the shapes that break it.
    # An EMBEDDED corpus carries the shapes that break it, so this control works
    # wherever the script is run from. The real ledger is added when reachable --
    # but relying on it alone made the control fail for the WRONG reason in every
    # break run from a scratch directory, which is BL14's defect reproduced.
    PROBES = [
        "Roll #1. WHY THIS: because. SO WHAT: it reads. Falsifier: it does not.",
        "NO GAME RUN, NO DISPLAY — the only item needing neither. THE RECOUNT: of sixteen.",
        "no headings here at all, just a plain sentence with nothing shouted",
        "TRAILING HEADING WITH NOTHING AFTER IT:",
        "of sixteen, fourteen agree — 7 GAME, 5 STACK, 2 METHOD at both scopes (A358, A369).",
    ]
    real = ([l for l in LEDGER.read_text().split("\n")
             if re.match(r"^\|\s*[A-Z]+\d+\s*\|", l)] if LEDGER.exists() else [])
    corpus = PROBES + [_gist(l) for l in real]
    lost = [c[:40] for c in corpus
            if _sections_roundtrip(c) != "".join(c.split())]
    chk(f"sectioning loses NO text ({len(corpus)} bodies, {len(real)} from the ledger)",
        not lost, f"{len(lost)} lose text: {lost[:3]}")
    # The project's own closing vocabulary is the part a reader most needs to
    # find, and every one of them is missed by the generic caps pattern.
    probe = ("Roll #1. WHY THIS AND NOT SOMETHING ELSE: because. "
             "NOT ESTABLISHED, and unchanged: the other thing. "
             "ONE RUN IS ENOUGH: there is no run. SO WHAT: it reads better. "
             "Falsifier: it does not.")
    heads = [s["h"] for s in _sections(probe)]
    chk("the standing section names are found, not just shouty ones",
        all(h in heads for h in ("SO WHAT", "Falsifier", "NOT ESTABLISHED",
                                 "ONE RUN IS ENOUGH")), f"{heads}")
    # THE LOOSE VERSION OF THIS SPLIT SHIPPED FIRST AND WAS WRONG TWICE: a bare
    # comma terminator made "7 GAME, 5 STACK" a heading, and a mid-sentence start
    # made the citation "(A358, A369)" one. Both are asserted directly.
    noise = _sections("of sixteen, fourteen agree — 7 GAME, 5 STACK, 2 METHOD "
                      "at both scopes (A358, A369), and reading works.")
    chk("mid-sentence capitals are NOT mistaken for headings",
        [s["h"] for s in noise] == [""], f"{[s['h'] for s in noise]}")
    # A HEADING MAY CONTAIN A COMMA, and allowing one to TERMINATE the heading
    # cuts real ones in half. Measured on the live ledger before this control was
    # written: the loose form changes 318 of 579 entries, turning "NO GAME RUN,
    # NO DISPLAY — ..." into a heading that stops at "NO GAME RUN". The earlier
    # probe missed this entirely and a break of exactly that shape went unnoticed.
    comma = _sections("NO GAME RUN, NO DISPLAY — the only item needing neither.")
    chk("a heading is not cut at its own internal comma",
        [s["h"] for s in comma] == ["NO GAME RUN, NO DISPLAY"],
        f"{[s['h'] for s in comma]}")
    # A HEADING MUST START A SENTENCE. Measured on the live ledger: dropping that
    # requirement changes 137 of 579 entries and promotes mid-clause emphasis to
    # headings -- "ONCE UNCONDITIONALLY", "DRAIN-WAIT". The probe below is that
    # exact shape, because the first two probes did not contain it and a break of
    # precisely this went unnoticed.
    mid = _sections("The name of 0x02 IS RECALLED, NOT CITED: the count is the finding.")
    chk("emphasis mid-sentence is not promoted to a heading",
        [s["h"] for s in mid] == [""], f"{[s['h'] for s in mid]}")
    chk("the labelling rows carry sections, not one blob",
        all("secs" in x for x in st.get("labels", [])),
        "the wall-of-text fix did not reach the data")
    chk("the labelling section READS without the runtime",
        'id="labels"' in html and ">A1<" in html.split('id="labels"')[1][:2000],
        "an empty section would look like a finished task")
    chk("the frozen shell round-trips into the state",
        '"before": "' in html and '"after": "' in html
        and "%%B%%" not in html and "%%A%%" not in html,
        "the shell placeholders were not filled — a republish would lose the page")
    chk("state is embedded as DATA, not read back off the DOM",
        'type="application/json"' in html and "JSON.parse" in html,
        "republishing from serialised DOM is what the capability docs forbid")
    # --- THE STALENESS MARKER (T195) ----------------------------------------
    # The nag had been permanently on because NOTHING wrote the marker — it was
    # a remembered hand-edit. These assert the two properties that matter, and
    # the second is the one that makes it safe: the count is read from the PAGE,
    # so publishing a stale file records the stale count instead of laundering it.
    import tempfile as _tf2
    with _tf2.TemporaryDirectory() as _td2:
        _pg = Path(_td2) / "p.html"
        _pg.write_text(html)
        _m = re.search(r"&nbsp;&middot;&nbsp;\s*(\d+)\s+entries", html)
        chk("the generated page states its own entry count, machine-readably",
            _m is not None and int(_m.group(1)) == d["entries"],
            "without this the marker cannot be derived from the page at all")
        # A page from a DIFFERENT (older) state must mark at ITS count, not today's.
        _stale = html.replace(f"{d['entries']} entries", "3 entries", 1)
        _sm = re.search(r"&nbsp;&middot;&nbsp;\s*(\d+)\s+entries", _stale)
        chk("marking reads the PAGE's count, so a stale publish stays stale",
            _sm is not None and int(_sm.group(1)) == 3,
            "if this read the ledger instead, marking would hide a stale page")
    chk("stamps when it was generated", d["generated"][:4] == str(date.today().year),
        "a page with no timestamp cannot be told from a fresh one")
    chk("escapes markup from the ledger",
        "&lt;" in render(collect(syn.replace("an open question", "a <script> thing"))),
        "ledger text injected raw into the page")
    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    if "--dry-run" in a:
        print(f"would read: {LEDGER.name}, route state, BACKLOG.md, IDEAS.md, "
              f"observed-runs.md, audit-log.md, .away.json, and `git rev-list`")
        print("would write a self-contained HTML page. Reads only; no project state changes.")
        return 0
    if not a:
        print("[status] need an output path, or --dry-run / --self-check", file=sys.stderr)
        return 2
    # --- mark a PUBLISHED page, deriving the count from the PAGE ------------
    #
    # WHY THIS IS NOT DONE AT GENERATION TIME, WHICH WAS THE OBVIOUS FIX (T195).
    # The marker exists so check_ledger can say "the user is reading a page that
    # no longer describes the project". That is about the PUBLISHED page, and
    # this script does not publish. Writing the marker when the file is WRITTEN
    # would go quiet on a page that was generated and never sent — silence in
    # the dangerous direction, which is worse than the false alarm it replaces.
    #
    # THE COUNT COMES OUT OF THE PAGE, NOT THE LEDGER. If a stale file is
    # published, the marker records the STALE count and the nag stays on, which
    # is correct. Reading the live ledger here would let marking launder a stale
    # publish into a clean bill of health.
    if "--mark-published" in a:
        i = a.index("--mark-published")
        if len(a) < i + 2:
            print("[status] --mark-published needs the file that was published",
                  file=sys.stderr)
            return 2
        pub = Path(a[i + 1])
        if not pub.exists():
            print(f"[status] no such file: {pub}", file=sys.stderr)
            return 2
        m = re.search(r"&nbsp;&middot;&nbsp;\s*(\d+)\s+entries", pub.read_text())
        if not m:
            print(f"[status] REFUSING: cannot find the entry count in {pub}. "
                  f"Marking a page whose contents I cannot read would assert "
                  f"freshness I have not checked.", file=sys.stderr)
            return 2
        mark = DOCS / ".status-page.json"
        old = _load(".status-page.json", {})
        old["entries"] = int(m.group(1))
        mark.write_text(json.dumps(old, indent=1) + "\n")
        print(f"[status] marked published at {m.group(1)} entries "
              f"(read from the page, not the ledger)")
        return 0

    out = Path(a[0])
    d = collect()
    # REFUSE RATHER THAN SHIP A PAGE WITH THE TASK MISSING. If the archive drive
    # is not mounted the label list cannot be read, and an empty section on the
    # page is indistinguishable from a finished one. Worse, publishing it would
    # overwrite whatever labels the user had already saved there.
    if d["labels"] is None:
        print(f"[status] REFUSING: the U10 label list is unreachable at\n"
              f"  {LABEL_LIST}\n"
              f"Mount the archive drive, or set SNP_ARCHIVE. Publishing without it "
              f"would show an empty labelling section — which looks like a finished "
              f"task — and a save would discard any labels already recorded.",
              file=sys.stderr)
        return 2
    out.write_text(render(d))
    print(f"[status] wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
