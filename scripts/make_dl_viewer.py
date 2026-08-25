#!/usr/bin/env python3
"""Build the draw-call stepper: pick a frame, then scrub through its draws.

THE USER'S REQUEST (2026-08-25): "a tool from which I could select a frame, and
then a slider which lets me scroll through each of the draws as they're laid on
top of one another."

WHY IT IS WORTH BUILDING RATHER THAN USING RT64's
-------------------------------------------------
RT64's inspector HAS a "View Draw Call" slider and A243 established it
TRUNCATES rather than highlights -- exactly this idea. It did not work: A316
tried it at the tutorial and every setting produced no visible change, and
A332 (the user, at the panel) confirmed the picture kept animating throughout.
A304 explains why -- **the tutorial never clears the colour buffer**, so
truncating this frame's draws leaves the previous frame's picture on screen and
nothing appears to change.

Offline we own the rasteriser and the buffer starts empty every time, so an
incremental draw really is incremental. **This is the control RT64 could not
give us**, on the same data.

INPUT is `dl_render.py --json-all`, which is the ordered replay -- so the
stepper reveals draws in the order the RSP would have executed them, not in
some order convenient for drawing.

    scripts/dl_render.py <log> --json-all frames.json --width 640 --height 480
    scripts/make_dl_viewer.py frames.json -o viewer.html

The page is SELF-CONTAINED: data is embedded, no network, no fonts fetched.
"""
import argparse
import json
import sys
from pathlib import Path

# Attract vs tutorial is the real division in this data (the tutorial is the
# broken scene), so frames are LABELLED by it rather than numbered decoratively.
# ~30 tasks/s, tutorial begins ~155 s -> ~task 4650. Measured, not guessed:
# heartbeats put t=80s at task 2378 and t=160s at task 4775.
TUTORIAL_FROM = 4650


def phase(task):
    return "tutorial" if task >= TUTORIAL_FROM else "attract"


PAGE = """<title>Draw-call stepper — Sin &amp; Punishment display lists</title>
<style>
  :root {
    --ground:#0B0F14; --panel:#131A22; --line:#223140;
    --ink:#C6D3DE; --muted:#6E8092; --trace:#57E0B0; --amber:#E0A64A;
    --well:#05080B;
    --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
    --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  @media (prefers-color-scheme: light) {
    :root { --ground:#EEF2F0; --panel:#FFFFFF; --line:#D2DBD6; --ink:#12191F;
            --muted:#5C6B78; --trace:#0B8F69; --amber:#8A5D10; --well:#E2E8E4; }
  }
  :root[data-theme="dark"] {
    --ground:#0B0F14; --panel:#131A22; --line:#223140; --ink:#C6D3DE;
    --muted:#6E8092; --trace:#57E0B0; --amber:#E0A64A; --well:#05080B;
  }
  :root[data-theme="light"] {
    --ground:#EEF2F0; --panel:#FFFFFF; --line:#D2DBD6; --ink:#12191F;
    --muted:#5C6B78; --trace:#0B8F69; --amber:#8A5D10; --well:#E2E8E4;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--ground); color:var(--ink);
         font-family:var(--sans); line-height:1.5;
         font-variant-numeric: tabular-nums; }
  .wrap { max-width: 1040px; margin: 0 auto; padding: 32px 20px 64px;
          display: flex; flex-direction: column; gap: 24px; }
  header { display:flex; flex-direction:column; gap:6px; }
  h1 { font-size: 1.5rem; margin:0; letter-spacing:-0.02em; text-wrap:balance;
       font-weight:650; }
  .sub { color:var(--muted); font-size:0.9rem; max-width:62ch; margin:0; }
  .eyebrow { font-family:var(--mono); font-size:0.7rem; letter-spacing:0.14em;
             text-transform:uppercase; color:var(--trace); }

  .chips { display:flex; flex-wrap:wrap; gap:8px; }
  .chip { font-family:var(--mono); font-size:0.78rem; padding:7px 11px;
          background:var(--panel); border:1px solid var(--line); color:var(--ink);
          border-radius:2px; cursor:pointer; display:flex; gap:8px;
          align-items:baseline; }
  .chip:hover { border-color:var(--muted); }
  .chip[aria-pressed="true"] { border-color:var(--trace); color:var(--trace); }
  .chip .ph { color:var(--muted); font-size:0.68rem; text-transform:uppercase;
              letter-spacing:0.08em; }
  .chip[aria-pressed="true"] .ph { color:var(--trace); }
  .chip:focus-visible, .btn:focus-visible, input:focus-visible {
    outline:2px solid var(--trace); outline-offset:2px; }

  .main { display:grid; grid-template-columns:minmax(0,1fr) 236px; gap:16px;
          align-items:start; }
  @media (max-width: 820px) { .main { grid-template-columns:minmax(0,1fr); } }
  .stage { background:var(--well); border:1px solid var(--line); padding:14px;
           display:flex; justify-content:center; }
  canvas { width:100%; max-width:640px; height:auto; display:block;
           image-rendering: pixelated; }

  /* The list is the slider's legend: without it a position is just a number. */
  .list { background:var(--panel); border:1px solid var(--line);
          display:flex; flex-direction:column; min-height:0; }
  .list h2 { margin:0; font-family:var(--mono); font-size:0.66rem;
             letter-spacing:0.1em; text-transform:uppercase; color:var(--muted);
             padding:11px 12px; border-bottom:1px solid var(--line); font-weight:500; }
  .rows { overflow-y:auto; max-height:452px; }
  .row { display:flex; align-items:center; gap:9px; padding:5px 12px;
         font-family:var(--mono); font-size:0.75rem; cursor:pointer;
         border:0; background:none; color:var(--ink); width:100%;
         text-align:left; border-left:2px solid transparent; }
  .row:hover { background:color-mix(in srgb, var(--ink) 7%, transparent); }
  .row .sw { width:10px; height:10px; flex:none; border-radius:1px; }
  .row .n { color:var(--muted); min-width:2.4em; }
  .row .t { margin-left:auto; color:var(--muted); }
  .row.pending { opacity:0.32; }
  .row.active { border-left-color:var(--trace); color:var(--trace);
                background:color-mix(in srgb, var(--trace) 12%, transparent); }
  .row.active .n, .row.active .t { color:var(--trace); }
  .row:focus-visible { outline:2px solid var(--trace); outline-offset:-2px; }

  .scrub { background:var(--panel); border:1px solid var(--line);
           padding:18px 20px; display:flex; flex-direction:column; gap:14px; }
  .scrubtop { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  .count { font-family:var(--mono); font-size:2rem; font-weight:600;
           color:var(--trace); letter-spacing:-0.02em; }
  .of { font-family:var(--mono); color:var(--muted); font-size:0.85rem; }
  .spacer { flex:1; }
  input[type=range] { width:100%; accent-color:var(--trace); height:26px; }
  .btns { display:flex; gap:8px; flex-wrap:wrap; }
  .btn { font-family:var(--mono); font-size:0.78rem; padding:7px 12px;
         background:transparent; border:1px solid var(--line); color:var(--ink);
         cursor:pointer; border-radius:2px; }
  .btn:hover { border-color:var(--muted); }
  .btn[aria-pressed="true"] { border-color:var(--trace); color:var(--trace); }

  .readout { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
             gap:1px; background:var(--line); border:1px solid var(--line); }
  .cell { background:var(--panel); padding:12px 14px; display:flex;
          flex-direction:column; gap:3px; }
  .cell .k { font-family:var(--mono); font-size:0.66rem; letter-spacing:0.1em;
             text-transform:uppercase; color:var(--muted); }
  .cell .v { font-family:var(--mono); font-size:1.15rem; }
  .cell.warn .v { color:var(--amber); }
  .note { color:var(--muted); font-size:0.82rem; max-width:70ch; margin:0; }
  .note b { color:var(--ink); font-weight:600; }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style>

<div class="wrap">
  <header>
    <span class="eyebrow">Display-list stepper</span>
    <h1>Every draw in the frame, laid down one at a time</h1>
    <p class="sub">Rebuilt from the game's own display list — no emulator, no
    renderer. Pick a frame, then scrub. Each step adds the next sub-list in the
    order the RSP would have run it; the newest one lands in mint before settling
    to its own colour.</p>
  </header>

  <div class="chips" id="chips" role="group" aria-label="Frame"></div>

  <div class="main">
    <div class="stage"><canvas id="cv" width="640" height="480"></canvas></div>
    <div class="list">
      <h2>Draws, in list order</h2>
      <div class="rows" id="rows"></div>
    </div>
  </div>

  <div class="scrub">
    <div class="scrubtop">
      <span class="count" id="cnt">0</span>
      <span class="of" id="of"></span>
      <span class="spacer"></span>
      <div class="btns">
        <button class="btn" id="first" type="button">&#124;&#9664; First</button>
        <button class="btn" id="prev" type="button">&#9664; Step</button>
        <button class="btn" id="play" type="button" aria-pressed="false">Play</button>
        <button class="btn" id="next" type="button">Step &#9654;</button>
        <button class="btn" id="last" type="button">All &#9654;&#124;</button>
      </div>
    </div>
    <input type="range" id="slider" min="0" value="0" step="1"
           aria-label="Draws revealed">
    <div class="btns">
      <button class="btn" id="gran" type="button" aria-pressed="false">Step by triangle</button>
      <button class="btn" id="wire" type="button" aria-pressed="false">Wireframe</button>
    </div>
  </div>

  <div class="readout">
    <div class="cell"><span class="k">Draws shown</span><span class="v" id="r1">0</span></div>
    <div class="cell"><span class="k">Triangles shown</span><span class="v" id="r2">0</span></div>
    <div class="cell"><span class="k">Sub-lists in frame</span><span class="v" id="r3">0</span></div>
    <div class="cell warn"><span class="k">Dropped behind eye</span><span class="v" id="r4">0</span></div>
  </div>

  <p class="note" id="foot"></p>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var frames = DATA.frames, fi = 0, pos = 0, byTri = false, wire = false;
  var playing = null, lastAdded = -1, addedAt = 0;

  var cv = document.getElementById("cv"), ctx = cv.getContext("2d");
  var slider = document.getElementById("slider");
  var chips = document.getElementById("chips");
  var rowsEl = document.getElementById("rows");

  function frame() { return frames[fi]; }
  // Draws = sub-lists, in first-appearance order. That is what "each of the
  // draws" means: one matrix set-up and the triangles that follow it.
  function groups(f) {
    if (f._g) return f._g;
    var order = [], seen = {}, idx = {};
    f.tris.forEach(function (t) {
      if (!(t.c in seen)) { seen[t.c] = true; idx[t.c] = order.length; order.push(t.c); }
    });
    f._g = { order: order, idx: idx };
    return f._g;
  }
  function maxPos() {
    var f = frame();
    return byTri ? f.tris.length : groups(f).order.length;
  }
  function shown() {
    var f = frame();
    if (byTri) return f.tris.slice(0, pos);
    var g = groups(f), lim = pos;
    return f.tris.filter(function (t) { return g.idx[t.c] < lim; });
  }
  function colour(c, fresh) {
    if (fresh) return getComputedStyle(document.documentElement)
                     .getPropertyValue("--trace").trim() || "#57E0B0";
    var r = (c * 97) % 200 + 55, g = (c * 57) % 200 + 55, b = (c * 151) % 200 + 55;
    return "rgb(" + r + "," + g + "," + b + ")";
  }
  // Which sub-list is "current": the one just revealed when stepping by draw,
  // or the one owning the current triangle when stepping by triangle -- so the
  // highlight means the same thing in both modes.
  function activeSub() {
    var f = frame(), g = groups(f);
    if (pos <= 0) return -1;
    if (!byTri) return g.order[pos - 1];
    return f.tris[Math.min(pos, f.tris.length) - 1].c;
  }
  function buildRows() {
    var f = frame(), g = groups(f), counts = {};
    f.tris.forEach(function (t) { counts[t.c] = (counts[t.c] || 0) + 1; });
    rowsEl.innerHTML = "";
    g.order.forEach(function (c, i) {
      var b = document.createElement("button");
      b.className = "row"; b.type = "button"; b.dataset.i = i;
      b.innerHTML = "<span class='sw' style='background:" + colour(c, false) +
                    "'></span><span class='n'>" + (i + 1) +
                    "</span><span class='t'>" + counts[c] + " tri</span>";
      b.addEventListener("click", function () {
        if (byTri) { var n = 0, k = 0;
          for (k = 0; k < f.tris.length; k++) { n++; if (g.idx[f.tris[k].c] === i) break; }
          setPos(n, true);
        } else setPos(i + 1, true);
      });
      rowsEl.appendChild(b);
    });
  }
  function syncRows() {
    var g = groups(frame()), act = activeSub(), lim = byTri ? -1 : pos;
    [].forEach.call(rowsEl.children, function (el, i) {
      var c = g.order[i];
      el.classList.toggle("active", c === act);
      el.classList.toggle("pending", byTri ? false : i >= lim);
      if (c === act && el.scrollIntoView) {
        var r = el.getBoundingClientRect(), p = rowsEl.getBoundingClientRect();
        if (r.top < p.top || r.bottom > p.bottom) {
          el.scrollIntoView({ block: "nearest" });
        }
      }
    });
  }
  function draw() {
    var f = frame(), g = groups(f);
    cv.width = f.w; cv.height = f.h;
    ctx.clearRect(0, 0, f.w, f.h);
    var freshC = (!byTri && pos > 0) ? g.order[pos - 1] : -1;
    var age = (performance.now() - addedAt) / 400;
    var list = shown();
    list.forEach(function (t) {
      var fresh = (t.c === freshC && age < 1 && freshC === lastAdded);
      ctx.beginPath();
      ctx.moveTo(t.p[0][0], t.p[0][1]);
      ctx.lineTo(t.p[1][0], t.p[1][1]);
      ctx.lineTo(t.p[2][0], t.p[2][1]);
      ctx.closePath();
      if (wire) { ctx.strokeStyle = colour(t.c, fresh); ctx.lineWidth = 1; ctx.stroke(); }
      else { ctx.fillStyle = colour(t.c, fresh); ctx.fill(); }
    });
    document.getElementById("cnt").textContent = pos;
    document.getElementById("of").textContent =
      "of " + maxPos() + (byTri ? " triangles" : " draws");
    document.getElementById("r1").textContent =
      byTri ? "\\u2014" : pos + " / " + g.order.length;
    document.getElementById("r2").textContent = list.length + " / " + f.tris.length;
    document.getElementById("r3").textContent = g.order.length;
    document.getElementById("r4").textContent = f.behind;
    document.getElementById("foot").textContent =
      "Task " + f.task + " \\u00b7 " + f.matrices + " matrix set-ups \\u00b7 " +
      f.built + " triangles built, " + f.behind +
      " dropped behind the eye. Dropped geometry is counted, never mirrored into frame.";
    syncRows();
    if (age < 1 && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      requestAnimationFrame(draw);
    }
  }
  function setPos(p, mark) {
    var m = maxPos();
    pos = Math.max(0, Math.min(m, p));
    slider.max = m; slider.value = pos;
    if (mark && !byTri && pos > 0) {
      var g = groups(frame());
      if (g.order[pos - 1] !== lastAdded) { lastAdded = g.order[pos - 1]; addedAt = performance.now(); }
    }
    draw();
  }
  function pickFrame(i) {
    fi = i;
    [].forEach.call(chips.children, function (c, n) {
      c.setAttribute("aria-pressed", n === i ? "true" : "false");
    });
    lastAdded = -1;
    buildRows();
    setPos(maxPos(), false);
  }

  frames.forEach(function (f, i) {
    var b = document.createElement("button");
    b.className = "chip"; b.type = "button"; b.setAttribute("aria-pressed", "false");
    b.innerHTML = "<span>task " + f.task + "</span><span class='ph'>" + f.phase + "</span>";
    b.addEventListener("click", function () { pickFrame(i); });
    chips.appendChild(b);
  });

  slider.addEventListener("input", function () { setPos(+slider.value, true); });
  document.getElementById("next").addEventListener("click", function () { setPos(pos + 1, true); });
  document.getElementById("prev").addEventListener("click", function () { setPos(pos - 1, true); });
  document.getElementById("first").addEventListener("click", function () { setPos(0, false); });
  document.getElementById("last").addEventListener("click", function () { setPos(maxPos(), false); });
  document.getElementById("gran").addEventListener("click", function () {
    byTri = !byTri;
    this.setAttribute("aria-pressed", byTri ? "true" : "false");
    this.textContent = byTri ? "Step by draw" : "Step by triangle";
    setPos(maxPos(), false);
  });
  document.getElementById("wire").addEventListener("click", function () {
    wire = !wire;
    this.setAttribute("aria-pressed", wire ? "true" : "false");
    draw();
  });
  document.getElementById("play").addEventListener("click", function () {
    var btn = this;
    if (playing) { clearInterval(playing); playing = null; btn.setAttribute("aria-pressed","false"); btn.textContent = "Play"; return; }
    if (pos >= maxPos()) setPos(0, false);
    btn.setAttribute("aria-pressed","true"); btn.textContent = "Pause";
    playing = setInterval(function () {
      if (pos >= maxPos()) { clearInterval(playing); playing = null;
        btn.setAttribute("aria-pressed","false"); btn.textContent = "Play"; return; }
      setPos(pos + 1, true);
    }, 90);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight") { setPos(pos + 1, true); e.preventDefault(); }
    if (e.key === "ArrowLeft") { setPos(pos - 1, true); e.preventDefault(); }
  });

  pickFrame(0);
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("json", nargs="?")
    ap.add_argument("-o", "--out", default="dl_viewer.html")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help or not a.json:
        print(__doc__)
        return 0 if a.help else 2
    data = json.loads(Path(a.json).read_text())
    if not data.get("frames"):
        print("[viewer] no frames in that json", file=sys.stderr)
        return 1
    for f in data["frames"]:
        f["phase"] = phase(f["task"])
        f.pop("_g", None)
    # </script> inside embedded JSON would close the tag early. Escaped, not
    # hoped about -- a page that silently truncates its own data renders an
    # empty frame and looks like a geometry finding.
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    Path(a.out).write_text(PAGE.replace("__DATA__", blob))
    n = sum(len(f["tris"]) for f in data["frames"])
    print(f"[viewer] {len(data['frames'])} frame(s), {n} triangles -> {a.out} "
          f"({Path(a.out).stat().st_size // 1024} KB)")
    for f in data["frames"]:
        print(f"  task {f['task']:<6} {f['phase']:<9} {len(f['tris']):>5} tris")
    return 0


if __name__ == "__main__":
    sys.exit(main())
