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

TWO SOURCES, AND THEY ARE NOT THE SAME QUANTITY (2026-08-28, the user's ask:
"hook the dump up ... so that I can step through it similarly"). Several JSON
files may be given; their frames are concatenated and each keeps its own `src`.
`rdp_to_stepper.py` emits `src="reference"` frames read from the REAL emulator's
RDP command stream -- screen space, post-transform, POST-CULL, with draw
groupings this project constructed rather than read. Ours are the F3DEX2 display
list replayed offline -- object space, PRE-cull, grouped by matrix set-up. The
page labels every chip with its source and says this in the open, because A608
already had to caveat exactly this comparison for counting.

    scripts/rdp_to_stepper.py <ares-dump.txt> -o reference.json
    scripts/make_dl_viewer.py frames.json reference.json -o viewer.html

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
  .sub b { color:var(--ink); font-weight:600; }
  .sub b.oursk { color:var(--trace); }
  .sub b.refk { color:var(--amber); }
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
  /* Reference frames come from a different instrument measuring a different
     quantity, so they are not allowed to look like ours. */
  .chip.ref[aria-pressed="true"] { border-color:var(--amber); color:var(--amber); }
  .chip.ref[aria-pressed="true"] .ph { color:var(--amber); }
  .srcbar { display:flex; gap:10px; align-items:baseline; flex-wrap:wrap;
            font-family:var(--mono); font-size:0.7rem; color:var(--muted);
            letter-spacing:0.08em; text-transform:uppercase; }
  .srcbar .k { display:inline-flex; align-items:center; gap:5px; }
  .srcbar .sw { width:9px; height:9px; display:inline-block; }
  .chip:focus-visible, .btn:focus-visible, input:focus-visible {
    outline:2px solid var(--trace); outline-offset:2px; }

  .stage { background:var(--well); border:1px solid var(--line); padding:14px;
           display:flex; justify-content:center; }
  canvas { width:100%; max-width:640px; height:auto; display:block;
           image-rendering: pixelated; }

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
  /* A filter hiding most of a frame looks exactly like missing geometry, which
     is the bug this whole project is chasing. Never let it be silent. */
  .hidden { margin:0; font-family:var(--mono); font-size:0.74rem;
            color:var(--amber); min-height:1em; }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style>

<div class="wrap">
  <header>
    <span class="eyebrow">Display-list stepper</span>
    <h1>Every draw in the frame, laid down one at a time</h1>
    <p class="sub">Pick a frame, then scrub. Each step adds the next draw in the
    order it was issued; the newest one lands in mint before settling to its own
    colour. <b>Arrow keys step</b> — hold Shift for ten at a time, Home and End
    for either end. Geometry splits three ways: what writes depth, scenery that
    does not (the pylons live here), and screen-pinned overlay. Dashed boxes are
    rectangle commands — mint for textured, amber for fills — drawn as outlines
    because we have no textures to put in them.</p>
    <p class="sub"><b>Two sources, and they do not measure the same thing.</b>
    <b class="oursk">Ours</b> is our display list replayed offline: object space,
    <b>before</b> culling, grouped by matrix set-up. <b class="refk">Reference</b>
    is the real emulator's RDP command stream: screen space, <b>after</b>
    transform and culling, with draw boundaries this project constructed rather
    than read from the data. Compare <b>what is on screen and where</b>. Do not
    read the two triangle counts as the same quantity.</p>
  </header>

  <div class="srcbar">
    <span class="k"><span class="sw" style="background:var(--trace)"></span>ours — display list, pre-cull</span>
    <span class="k"><span class="sw" style="background:var(--amber)"></span>reference — ares RDP, post-cull</span>
  </div>

  <div class="chips" id="chips" role="group" aria-label="Frame"></div>

  <div class="stage"><canvas id="cv" width="640" height="480"></canvas></div>

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
      <button class="btn" id="kd" type="button" aria-pressed="true">Depth-writing</button>
      <button class="btn" id="ks" type="button" aria-pressed="true">Scene, no depth</button>
      <button class="btn" id="ko" type="button" aria-pressed="false">Screen overlay</button>
      <button class="btn" id="kr" type="button" aria-pressed="true">Rects</button>
    </div>
    <p class="hidden" id="hid"></p>
  </div>

  <div class="readout">
    <div class="cell"><span class="k">Draws shown</span><span class="v" id="r1">0</span></div>
    <div class="cell"><span class="k">Triangles shown</span><span class="v" id="r2">0</span></div>
    <div class="cell"><span class="k">Sub-lists in frame</span><span class="v" id="r3">0</span></div>
    <div class="cell warn"><span class="k">Clipped / dropped</span><span class="v" id="r4">0</span></div>
    <div class="cell"><span class="k">Depth / scene / screen</span><span class="v" id="r5">0</span></div>
    <div class="cell"><span class="k">Rect commands</span><span class="v" id="r6">0</span></div>
  </div>

  <p class="note" id="foot"></p>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var frames = DATA.frames, fi = 0, pos = 0, byTri = false, wire = false;
  var playing = null, lastAdded = -1, addedAt = 0;
  // A428: three populations, not two. 'Scene, no depth' is where the pylons
  // live -- calling them overlay hid them for a day.
  var show = { d: true, s: true, o: false };
  var showRects = true;

  var cv = document.getElementById("cv"), ctx = cv.getContext("2d");
  var slider = document.getElementById("slider");
  var chips = document.getElementById("chips");

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
  // The 2D overlay is EXCLUDED BY DEFAULT and this is not cosmetic. A422
  // measured which triangles carry Z_UPD; the ones that do not are screen-space
  // overlay, drawn on hardware with depth-write off and a mostly transparent
  // texture. Offline they are opaque, and task 2400 draw 114 is two of them
  // covering the whole frame at z = -0.996 -- nearest possible, so they win
  // every depth test and paint the scene out. Hiding them shows the 3D scene;
  // showing them shows what the frame also contains.
  function keep(t) { return show[t.k || (t.z ? "d" : "o")]; }
  function shown() {
    var f = frame();
    if (byTri) return f.tris.slice(0, pos).filter(keep);
    var g = groups(f), lim = pos;
    return f.tris.filter(function (t) { return g.idx[t.c] < lim && keep(t); });
  }
  function colour(c, fresh) {
    if (fresh) return getComputedStyle(document.documentElement)
                     .getPropertyValue("--trace").trim() || "#57E0B0";
    var r = (c * 97) % 200 + 55, g = (c * 57) % 200 + 55, b = (c * 151) % 200 + 55;
    return "rgb(" + r + "," + g + "," + b + ")";
  }
  // SOFTWARE Z-BUFFER. Painter's order is WRONG for this data and the user
  // found it: the game draws characters first and the environment after, and
  // on hardware the depth test rejects the later surface. Filling in list
  // order made the environment paint straight over the soldiers, so they
  // vanished at draw 61 of task 600 -- an artefact of this viewer, not of the
  // game. NDC z is linear in screen space, so plain barycentric interpolation
  // of it is the correct test.
  var img = null, zbuf = null;
  function rasterize(list, f, freshC, age) {
    if (!img || img.width !== f.w || img.height !== f.h) {
      img = ctx.createImageData(f.w, f.h);
      zbuf = new Float32Array(f.w * f.h);
    }
    var d = img.data, W = f.w, H = f.h;
    d.fill(0); zbuf.fill(Infinity);
    var freshRGB = null;
    list.forEach(function (t) {
      var fresh = (t.c === freshC && age < 1 && freshC === lastAdded);
      var col = colour(t.c, fresh), r, g2, b;
      if (col.charAt(0) === "#") {
        r = parseInt(col.substr(1, 2), 16); g2 = parseInt(col.substr(3, 2), 16);
        b = parseInt(col.substr(5, 2), 16);
      } else {
        var m = col.match(/\\d+/g); r = +m[0]; g2 = +m[1]; b = +m[2];
      }
      var ax = t.p[0][0], ay = t.p[0][1], az = t.p[0][2];
      var bx = t.p[1][0], by = t.p[1][1], bz = t.p[1][2];
      var cx = t.p[2][0], cy = t.p[2][1], cz = t.p[2][2];
      var den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (Math.abs(den) < 1e-9) return;
      var x0 = Math.max(0, Math.floor(Math.min(ax, bx, cx)));
      var x1 = Math.min(W - 1, Math.ceil(Math.max(ax, bx, cx)));
      var y0 = Math.max(0, Math.floor(Math.min(ay, by, cy)));
      var y1 = Math.min(H - 1, Math.ceil(Math.max(ay, by, cy)));
      for (var py = y0; py <= y1; py++) {
        for (var px = x0; px <= x1; px++) {
          var l0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den;
          if (l0 < 0) continue;
          var l1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den;
          if (l1 < 0) continue;
          var l2 = 1 - l0 - l1;
          if (l2 < 0) continue;
          var z = l0 * az + l1 * bz + l2 * cz;
          var i = py * W + px;
          if (z >= zbuf[i]) continue;
          zbuf[i] = z;
          var o = i * 4;
          d[o] = r; d[o + 1] = g2; d[o + 2] = b; d[o + 3] = 255;
        }
      }
    });
    ctx.putImageData(img, 0, 0);
  }

  function draw() {
    var f = frame(), g = groups(f);
    cv.width = f.w; cv.height = f.h;
    ctx.clearRect(0, 0, f.w, f.h);
    var freshC = (!byTri && pos > 0) ? g.order[pos - 1] : -1;
    var age = (performance.now() - addedAt) / 400;
    var list = shown();
    if (wire) {
      // Wireframe deliberately ignores depth -- it is for seeing WHERE
      // geometry is, including what is hidden behind other geometry.
      list.forEach(function (t) {
        var fresh = (t.c === freshC && age < 1 && freshC === lastAdded);
        ctx.beginPath();
        ctx.moveTo(t.p[0][0], t.p[0][1]);
        ctx.lineTo(t.p[1][0], t.p[1][1]);
        ctx.lineTo(t.p[2][0], t.p[2][1]);
        ctx.closePath();
        ctx.strokeStyle = colour(t.c, fresh); ctx.lineWidth = 1; ctx.stroke();
      });
    } else {
      rasterize(list, f, freshC, age);
    }
    // RECT COMMANDS, drawn as OUTLINES on purpose. G_TEXRECT and G_FILLRECT
    // are how this game paints skies, borders and UI panels; the offline
    // renderer has no textures, so filling them would paint a solid slab over
    // the scene and read as geometry. An outline shows WHERE they are and how
    // big without pretending to show what they contain. A blank region in this
    // viewer with a rect outline around it is a texture we cannot draw -- not
    // a hole in the game.
    if (showRects && f.rects && f.rects.length) {
      ctx.save();
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      var sx = f.w / 320, sy = f.h / 240;   // rect coords are 10.2 at 320x240
      f.rects.forEach(function (rc) {
        ctx.strokeStyle = rc.kind === "tex" ? "#57E0B0" : "#E0A64A";
        ctx.strokeRect(rc.x0 * sx, rc.y0 * sy,
                       (rc.x1 - rc.x0) * sx, (rc.y1 - rc.y0) * sy);
      });
      ctx.restore();
    }
    document.getElementById("cnt").textContent = pos;
    document.getElementById("of").textContent =
      "of " + maxPos() + (byTri ? " triangles" : " draws");
    document.getElementById("r1").textContent =
      byTri ? "\\u2014" : pos + " / " + g.order.length;
    document.getElementById("r2").textContent = list.length + " / " + f.tris.length;
    document.getElementById("r3").textContent = g.order.length;
    // The reference stream is POST-cull: whatever was dropped was dropped
    // upstream and never appears here. Printing 0 would read as "the reference
    // drops nothing", which is a claim this data cannot make.
    document.getElementById("r4").textContent =
      (f.src === "reference") ? "\\u2014" : f.behind;
    var nr = (f.rects || []).length, nt = 0;
    (f.rects || []).forEach(function (rc) { if (rc.kind === "tex") nt++; });
    document.getElementById("r6").textContent =
      nr + (nr ? " (" + nt + " tex)" : "");
    var n = { d: 0, s: 0, o: 0 };
    f.tris.forEach(function (t) { n[t.k || (t.z ? "d" : "o")]++; });
    document.getElementById("r5").textContent =
      n.d + " / " + n.s + " / " + n.o;
    // Say out loud how much the filters are hiding. The reference frames draw
    // ~64% of their triangles with no depth involvement at all, so landing on
    // one with 'Screen overlay' off shows a third of the frame -- which reads
    // as missing geometry unless the page admits what it is doing.
    var names = { d: "depth-writing", s: "scene-no-depth", o: "screen overlay" };
    var hid = [];
    ["d", "s", "o"].forEach(function (k) {
      if (!show[k] && n[k]) hid.push(n[k] + " " + names[k]);
    });
    document.getElementById("hid").textContent = hid.length
      ? ("hiding " + hid.join(" + ") + " \\u2014 " +
         hid.reduce(function (a, s) { return a + parseInt(s, 10); }, 0) +
         " of " + f.tris.length + " triangles not drawn")
      : "";
    document.getElementById("foot").textContent = f.note ? f.note :
      ("Task " + f.task + " \\u00b7 " + f.matrices + " matrix set-ups \\u00b7 " +
       f.built + " triangles built, " + f.behind +
       " dropped behind the eye. Dropped geometry is counted, never mirrored into frame.");
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
    setPos(maxPos(), false);
  }

  frames.forEach(function (f, i) {
    var b = document.createElement("button");
    b.className = "chip" + (f.src === "reference" ? " ref" : "");
    b.type = "button"; b.setAttribute("aria-pressed", "false");
    b.appendChild(document.createTextNode(f.label));
    var ph = document.createElement("span");
    ph.className = "ph"; ph.textContent = f.phase;
    b.appendChild(ph);
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
  [["kd", "d"], ["ks", "s"], ["ko", "o"]].forEach(function (pair) {
    document.getElementById(pair[0]).addEventListener("click", function () {
      show[pair[1]] = !show[pair[1]];
      this.setAttribute("aria-pressed", show[pair[1]] ? "true" : "false");
      draw();
    });
  });
  document.getElementById("kr").addEventListener("click", function () {
    showRects = !showRects;
    this.setAttribute("aria-pressed", showRects ? "true" : "false");
    draw();
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
    // UP/DOWN move through the LIST, not just the scroll box. Without the
    // preventDefault the browser scrolls the rows container and the selection
    // stays put, so the highlight and the view drift apart -- which is exactly
    // what made the list feel broken.
    var d = 0;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") d = 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") d = -1;
    else if (e.key === "Home") { setPos(0, false); e.preventDefault(); return; }
    else if (e.key === "End") { setPos(maxPos(), false); e.preventDefault(); return; }
    else return;
    // PageUp/PageDown-sized jumps with a modifier, since 126 draws is a long
    // way at one step per press.
    setPos(pos + d * ((e.shiftKey || e.metaKey || e.ctrlKey) ? 10 : 1), true);
    e.preventDefault();
  });

  pickFrame(0);
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("json", nargs="*")
    ap.add_argument("-o", "--out", default="dl_viewer.html")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help or not a.json:
        print(__doc__)
        return 0 if a.help else 2

    # Several inputs are concatenated. Each frame keeps the `src` its producer
    # gave it; anything without one is ours, because ours predates the field.
    frames = []
    for path in a.json:
        data = json.loads(Path(path).read_text())
        if not data.get("frames"):
            print(f"[viewer] no frames in {path}", file=sys.stderr)
            return 1
        for f in data["frames"]:
            f.setdefault("src", "ours")
            frames.append(f)
        print(f"[viewer] {len(data['frames'])} frame(s) from {path}")
    if not frames:
        print("[viewer] nothing to show", file=sys.stderr)
        return 1

    for f in frames:
        ref = f["src"] == "reference"
        f["phase"] = "ares" if ref else phase(f["task"])
        # "ares f5100" not "ref 5100": ares frame numbers and our task numbers
        # are different clocks, and 5100 happens to occur in both. A label that
        # let them be read as the same instant would invent an alignment.
        f["label"] = ("ares f" if ref else "task ") + str(f["task"])
        f.pop("_g", None)
    # </script> inside embedded JSON would close the tag early. Escaped, not
    # hoped about -- a page that silently truncates its own data renders an
    # empty frame and looks like a geometry finding.
    blob = json.dumps({"frames": frames}, separators=(",", ":")).replace("</", "<\\/")
    Path(a.out).write_text(PAGE.replace("__DATA__", blob))
    n = sum(len(f["tris"]) for f in frames)
    print(f"[viewer] {len(frames)} frame(s), {n} triangles -> {a.out} "
          f"({Path(a.out).stat().st_size // 1024} KB)")
    for f in frames:
        print(f"  {f['label']:<12} {f['phase']:<9} {len(f['tris']):>5} tris  "
              f"{len(f.get('rects', [])):>4} rects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
