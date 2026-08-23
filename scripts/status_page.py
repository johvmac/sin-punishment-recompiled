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
        "backlog_open": _count("BACKLOG.md", r"^\|\s*BL\d+\s*\|[^|]*\|\s*OPEN"),
        "ideas_open": _count("IDEAS.md", r"^\|\s*IDEA\d+\s*\|[^|]*\|\s*OPEN"),
        "l1_audits": _count("audit-log.md", r"^## Audit #\d+ — since"),
        "method_pct": 100.0 * fams.get("T", 0) / max(1, len(entries)),
        "ideas": ideas,
    }


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _summarise(line, n=190):
    """The human-readable gist of a ledger row, without the markup."""
    body = line.split("|")
    txt = body[3] if len(body) > 3 else line
    txt = re.sub(r"\*\*|`|~~", "", txt).strip()
    return _esc(txt[:n] + ("…" if len(txt) > n else ""))


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

<h2 class="pull">Your call &mdash; not yet decided</h2>
<p class="lede">Ideas I raised and you have not answered. Deciding one here is
recorded on the page itself, so I pick it up next session without you repeating
it. <b>Declining is a real answer</b> &mdash; it closes the item rather than
leaving it to rot.</p>
<!--IB--><div id="ideas">{_fallback(d['ideas'])}</div><!--IA-->
<p class="saving" id="saving"></p>

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

<script id="state" type="application/json">{_json(dict(ideas=d['ideas'], before="%%B%%", after="%%A%%"))}</script>
<script id="boot">
// State lives in its own JSON tag so republishing never rewrites code, and the
// page is rebuilt from DATA rather than by serialising the live DOM.
(function () {{
  var S = JSON.parse(document.getElementById("state").textContent);
  if (!S.title) {{ S.title = document.querySelector("title").textContent; }}
  if (!S.css) {{ S.css = document.querySelector("style").textContent; }}
  var box = document.getElementById("ideas");
  var say = document.getElementById("saving");
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

  function doc() {{
    // REBUILT FROM DATA, NEVER FROM THE DOM. A first version took
    // `.sheet.outerHTML`, which the capability contract forbids and which had a
    // concrete bug: "Saving..." is set before publish, so it would have been
    // baked permanently into the published page. The shell either side of the
    // ideas is frozen in state; only the ideas are regenerated.
    var head = '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      + "<title>" + S.title + "<" + "/title>"
      + "<style>" + S.css + "<" + "/style>";
    var body = '<div class="sheet">' + S.before + ideasHTML() + S.after + "</div>"
      + '<script id="state" type="application/json">' + JSON.stringify(S) + "<" + "/script>"
      + '<script id="boot">' + document.getElementById("boot").textContent + "<" + "/script>";
    return "<!doctype html><html><head>" + head + "</head><body>" + body + "</body></html>";
  }}

  box.addEventListener("click", async function (e) {{
    var b = e.target.closest("button");
    if (!b) return;
    var it = S.ideas.filter(function (x) {{ return x.id === b.dataset.id; }})[0];
    if (!it) return;
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

  draw();
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
    head, rest = html.split("<!--IB-->", 1)
    mid, tail = rest.split("<!--IA-->", 1)

    sheet_open = '<div class="sheet">'
    before = head.split(sheet_open, 1)[1] + '<div id="ideas">'
    # THE SHELL MUST STOP AT THE SHEET. `after` originally ran to the end of the
    # document, which swallowed the state script -- so the frozen shell contained
    # the very placeholders being written into it and they replaced themselves.
    body_tail = tail.split('<script id="state"', 1)[0]
    after = "</div>" + body_tail.rstrip().rsplit("</div>", 1)[0]

    def enc(x):
        return json.dumps(x)[1:-1].replace("<", "\\u003c").replace("&", "\\u0026")

    return (html.replace("<!--IB-->", "").replace("<!--IA-->", "")
                .replace("%%B%%", enc(before)).replace("%%A%%", enc(after)))


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
    chk("the frozen shell round-trips into the state",
        '"before": "' in html and '"after": "' in html
        and "%%B%%" not in html and "%%A%%" not in html,
        "the shell placeholders were not filled — a republish would lose the page")
    chk("state is embedded as DATA, not read back off the DOM",
        'type="application/json"' in html and "JSON.parse" in html,
        "republishing from serialised DOM is what the capability docs forbid")
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
