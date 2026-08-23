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
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

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
        "backlog_open": _count("BACKLOG.md", r"^\|\s*BL\d+\s*\|[^|]*\|\s*OPEN"),
        "ideas_open": _count("IDEAS.md", r"^\|\s*IDEA\d+\s*\|[^|]*\|\s*OPEN"),
        "l1_audits": _count("audit-log.md", r"^## Audit #\d+ — since"),
        "method_pct": 100.0 * fams.get("T", 0) / max(1, len(entries)),
    }


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _summarise(line, n=190):
    """The human-readable gist of a ledger row, without the markup."""
    body = line.split("|")
    txt = body[3] if len(body) > 3 else line
    txt = re.sub(r"\*\*|`|~~", "", txt).strip()
    return _esc(txt[:n] + ("…" if len(txt) > n else ""))


def render(d):
    """The ledger ROW is the visual unit -- hairline rules, no cards.

    Grounded in the subject: this project's whole record is dated rows with a
    status column, so the page reads as one. Rounded cards with an accent rail
    are the generic dashboard look and say nothing about what this is.
    """
    def rows(items, empty, tag, tone=""):
        if not items:
            return f'<p class="empty">{empty}</p>'
        return "".join(
            f'<div class="row {tone}"><span class="tag">{tag}</span>'
            f'<span class="rid">{_esc(k)}</span>'
            f'<span class="body">{_summarise(v)}</span></div>' for k, v in items)

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
<p class="lede">No launch, no display, nothing running. Ten minutes and the ledger.</p>
{rows(d['desk'], 'Nothing needs you at a desk.', 'desk', 'need')}
{away_html}

<h2 class="pull">Needs you &mdash; at the machine</h2>
<p class="lede">A real display and a launch. The setup cost is the whole reason these
are batched: one sitting clears several, one at a time pays it over and over.</p>
{rows(d['machine'], 'Nothing needs the machine.', 'setup', 'need')}

<h2>Waiting on nobody</h2>
<p class="lede">Open questions being worked without you. A long list here means
progress is not blocked on your time.</p>
{rows(d['open'], 'Nothing open &mdash; which would be unusual.', 'open')}

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

</div>"""


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    syn = ("| # | s | f | e |\n|---|---|---|---|\n"
           "| A1 | OPEN [cost=2] | an open question | 2026-01-01 |\n"
           "| A2 | MEASURED | a settled thing | 2026-01-02 |\n"
           "| A3 | AWAITING THE USER — waits on U7 | parked | 2026-01-02 |\n"
           "| T1 | INTERVENED | method work | 2026-01-02 |\n"
           "## THE USER QUEUE\n"
           "| U1 | LIVE 2026-01-01 | NO GAME RUN, NO DISPLAY — label some entries |\n"
           "| U2 | LIVE 2026-01-01 | Open the inspector and read the panel |\n")
    d = collect(syn)
    chk("splits the queue by SETUP COST", [k for k, _ in d["desk"]] == ["U1"]
        and [k for k, _ in d["machine"]] == ["U2"],
        f"desk={[k for k,_ in d['desk']]} machine={[k for k,_ in d['machine']]}")
    chk("queue rows are NOT counted as entries", d["entries"] == 4, f"got {d['entries']}")
    chk("finds the open item", [k for k, _ in d["open"]] == ["A1"], f"{d['open']}")
    chk("finds the parked item", [k for k, _ in d["parked"]] == ["A3"], f"{d['parked']}")
    chk("computes the method share", abs(d["method_pct"] - 25.0) < 0.01, f"{d['method_pct']}")

    html = render(d)
    chk("renders a self-contained page with no external requests",
        "http://" not in html and "https://" not in html and "<script" not in html.lower(),
        "an external reference would be blocked and would leak a request")
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
    out = Path(a[0])
    out.write_text(render(collect()))
    print(f"[status] wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
