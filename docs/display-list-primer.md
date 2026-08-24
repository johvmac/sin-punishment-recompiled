# Reading a display list — enough to check my claims

**Written for U11.** You asked to be introduced to the N64 display list so you
can check rendering claims directly instead of taking them on trust. This is my
half; reading it is yours. It should take about fifteen minutes.

**What you should be able to do at the end:** look at one line of our census
output and say what the game asked the graphics hardware to do — and, more
usefully, spot the one line in our own output that almost everybody reads
wrong, including me, twice.

**What this deliberately is not:** a survey of the microcode, or a list of what
each command number means. Those are the parts I get wrong. A363 is the
standing reminder — opcode names in this project have been half-recalled
convention more than once, and one of them (`0x02`) is still marked unverified
in the ledger today. Everything below is either read out of our own source, our
own captures, or flagged as mine.

---

## 1. What a display list is

The N64 has two processors that matter here. The CPU runs the game — physics,
input, where the enemies are. It does **not** draw. Drawing is done by a
separate graphics chip.

The two do not share a conversation. Each frame, the CPU writes out a list of
instructions — "set the texture to this", "draw these triangles", "fill this
rectangle" — into memory, and then hands the graphics chip a pointer to the
start of it. The chip walks the list from top to bottom, executing each command
in order, and stops when it hits the end.

That list is the **display list**. It is the complete and only record of what
the game asked for in that frame.

This matters more than it sounds. A frame that comes out wrong has exactly two
possible causes: **the game asked for the wrong thing**, or **the game asked for
the right thing and our renderer did it wrong**. The display list sits precisely
on that boundary. It is the last thing that is unambiguously the game's fault,
and the first thing that is unambiguously ours.

Almost every open question in this project is a version of "which side of that
line is this on".

Two more properties worth knowing:

- **Lists can call other lists.** A command can say "go and run the list at this
  address, then come back". Games use this constantly — the list for a level is
  mostly a sequence of calls out to per-object lists. Our census reports this as
  `depth=2` (the list called sub-lists, but those did not call further) and
  reports each child separately.
- **Commands are stateful.** Most commands do not draw anything; they change a
  setting that later drawing commands use. "Set the texture", "set the colour",
  "set the render target". The drawing commands then act on whatever the current
  settings happen to be. **This is the source of the trap in section 5**, and it
  is the single most important thing on this page.

---

## 2. Where our numbers come from

We have instrumentation inside the emulator that intercepts the display list at
the moment the game submits it, walks it the same way the hardware would, and
prints a summary. It is in
[`events.cpp`](lib/N64ModernRuntime/ultramodern/src/events.cpp) and its output
is tagged `[dlcensus]`, `[dlrect]` and `[dlchild]`.

It reads what the game *submitted*. It says nothing about what our renderer
subsequently *did*. Keep those apart and most of the ledger's careful wording
starts making sense.

Printing every frame would be unreadable, so the detailed histogram prints every
Nth frame. **N defaults to 301, and the odd number is not an accident** — the
game rotates between three framebuffers, one per frame, so any interval
divisible by three samples the same buffer forever. The old default was 300 and
it did exactly that, unnoticed, for the entire project until A367. The
instrument now warns if you pick a bad interval.

---

## 3. One real frame

This is task 300 from `evidence/2026-08-21/mtx.log`, unedited. It is a real
frame from our own build.

```
[dlcensus] task=300 HISTOGRAM (opcode:count, nonzero only)
[dlrect] task=300 nrect=7 ncimg=3
[dlrect]   fill   12,   8 -  307, 231  seq=20     color=0x00010001  into=0x803DA800  cycle=FILL
[dlrect]   fill   12,   8 -  307, 231  seq=25     color=0xFFFCFFFC  into=0x80000400  cycle=FILL
[dlrect]   fill    0, 192 -  321, 224  seq=1033   color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
[dlrect]   fill   12,   7 -  308,   9  seq=1270   color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
[dlrect]   fill   12, 230 -  308, 232  seq=1271   color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
[dlrect]   fill   11,   8 -   13, 231  seq=1272   color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
[dlrect]   fill  307,   8 -  309, 231  seq=1273   color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
[dlrect] task=300 tris seq 64..1024 (n=345) nscis=5 nvp=1 unresolved=0
[dlrect]   vp   seq=28     @0x802C3B20 scale=640,480,511 trans=640,480,511  => x 0..320  y 0..240
[dlrect]   scis    0,   0 -  320, 239  seq=1266
[dlrect]   cimg 0x803DA800
[dlrect]   cimg 0x80000400
[dlrect]   cimg 0x803DA800
```

(I have dropped four repeated scissor lines, a matrix line, and the opcode
histogram; nothing below depends on them.)

---

## 4. Reading one line end to end

Take the fourth rectangle:

```
[dlrect]   fill   12,   7 -  308,   9  seq=1270  color=0xFFFCFFFC  into=0x803DA800  cycle=1CYCLE
```

Field by field:

- **`fill 12,7 - 308,9`** — a rectangle from x=12,y=7 to x=308,y=9. The screen is
  320×240, so this is a strip 296 pixels wide and 2 pixels tall, near the top. A
  border. *(The coordinates arrive as 12-bit fields which the instrument shifts
  right by two — the hardware carries quarter-pixel precision and we discard the
  fraction. That decode is flagged in our own source as an assumption. It is
  weakly corroborated by the fact that the results land on screen instead of in
  the thousands.)*
- **`seq=1270`** — this was the 1,270th command in the list. **Sequence numbers
  are how you establish order, and order is usually the real evidence.** This
  rectangle is drawn near the very end of the frame, after all 345 triangle
  commands (`tris seq 64..1024 (n=345)`). It is drawn on top of the scene, not
  behind it.

  **Note "commands", not "triangles" — this is section 8 in miniature.** What the
  instrument counts is certain: 345 occurrences of two particular command
  numbers, and the histogram breaks them down as 32 of one and 313 of the other.
  Convention says the second kind carries *two* triangles, which would make the
  real figure 658. That convention is the part I would be quoting rather than
  measuring, so the census reports the count it can defend and leaves the
  multiplication to whoever wants to argue for it.
- **`color=0xFFFCFFFC`** — the fill colour register at the moment this command
  ran. **See section 5 before you believe this means anything.**
- **`into=0x803DA800`** — the render target in effect. Where the pixels go.
- **`cycle=1CYCLE`** — which of four rendering modes the chip was in.

So: *near the end of the frame, the game drew a thin horizontal bar across the
top of the screen.* Four of these lines together (`seq` 1270–1273: top, bottom,
left, right) are a rectangular border drawn around the picture. If you have
noticed a frame around the image in our captures, that is these four commands.

That is the whole skill. Position, order, destination, mode.

---

## 5. The trap, and it caught me twice

Look again at those five `1CYCLE` rectangles. They all say
`color=0xFFFCFFFC`. The obvious reading is "the game drew five white-ish
rectangles".

**That reading is wrong, and A356 established why by measurement.**

`cycle=FILL` is a mode in which the chip wipes a rectangle with the fill-colour
register. `cycle=1CYCLE` is normal shaded rendering, in which the fill-colour
register **is not used at all**. The census prints it anyway, because it prints
the machine's state at the moment of each command — deliberately, and it says so
at the point it samples it.

So on a `1CYCLE` line, `color=` is **leftover state from some earlier command**.
It is genuinely there in the hardware; it simply has no effect. Across the whole
of that capture, 276 of 289 rectangles into the framebuffer carry
`color=0xFFFCFFFC` in `1CYCLE` mode — all of them inheriting it from the depth
clear at `seq=25`, and none of them a white rectangle.

This is worth dwelling on because it is the general shape of the problem. **The
census reports state faithfully; whether a given piece of state matters depends
on another field.** A342 doubted a correct earlier finding on exactly this
basis, and it took a re-read of the same file to resolve it.

**The practical rule: on a `[dlrect]` line, read `cycle=` before you read
`color=`.** If it does not say `FILL`, the colour is noise.

---

## 6. What the first two lines actually say

Now the interesting pair, which is a complete worked example of reading order:

```
fill 12,8 - 307,231  seq=20  color=0x00010001  into=0x803DA800  cycle=FILL
fill 12,8 - 307,231  seq=25  color=0xFFFCFFFC  into=0x80000400  cycle=FILL
```

Same rectangle — the full drawable area — twice, in `FILL` mode, five commands
apart, into two different destinations.

`0x803DA800` is one of the three framebuffers. The other two are `0x8038F800`
and `0x803B5000`; each is 0x25800 bytes from the next, and 320 × 240 × 2 bytes
per pixel is exactly 0x25800. That is the picture, and the game rotates through
the three of them one per frame.

`0x80000400` is not a framebuffer. **It is the depth buffer**, and the way we
know is worth understanding because it is a good example of the reasoning this
project prefers:

- **The order says so.** Every tutorial frame points the render target at
  `0x80000400`, wipes all of it, then points the target at the framebuffer and
  starts drawing. That is the standard idiom for clearing depth on this
  hardware — you clear it by aiming the colour-image register at it.
- **The uniformity says so.** In that whole capture, all 25 wipes into
  `0x80000400` are byte-for-byte identical — same rectangle, same colour, always
  `FILL`. Meanwhile `0x803DA800` receives 289 rectangles of varied geometry and
  colour. *A destination that only ever receives one identical full-area wipe is
  not a colour target.*
- **A separate field agrees.** A363 later found the explicit
  set-depth-image command present once or twice per frame, from the opcode
  histogram — a different measurement, made for a different reason, that lands
  in the same place.

Three independent readings, none of which is "0x80000400 is a low address so it
is probably the Z-buffer".

**The part that is mine and unverified:** reading `0xFFFC` as "maximum depth" is
recalled convention. The constant is not defined anywhere in this tree; I
checked. The identification above does not rest on it — which is the point of
saying so.

---

## 7. What this instrument cannot tell you

Four honest limits, so you can push back when I overreach:

1. **It reports what the game asked for, not what happened.** Every conclusion
   from a census is about the game's request. Whether RT64 honoured it is a
   different question needing a different instrument.
2. **It samples.** Detail prints every 301st frame. Scene identity has been
   wrongly assigned twice on this project from sampling (A93, A161) — the
   observation right, the quantifier wrong. "Every frame" in an entry sourced
   from a census means "every frame I looked at", and you are entitled to ask
   how many that was.
3. **It counts some things it does not decode.** The opcode histogram is
   reliable as *counts of numbered commands*. The mapping from number to name is
   convention, and A363 records where that has already gone wrong.
4. **One known soft spot.** The render-target address is the only pointer in the
   walker not passed through address resolution. It has not mattered so far —
   every observed value was already a plain address — but a game using a
   different addressing mode there would print something misleading. Recorded,
   not fixed.

---

## 8. Certain, and mine

| Claim | Standing |
|---|---|
| The display list is the game's complete per-frame request | Certain — this is what the hardware does |
| The census walks the submitted list and prints its state | Certain — read from our source |
| `seq=` is command order within the frame | Certain — read from our source |
| Coordinates are 12-bit fields shifted right by 2 | Certain as *code*; the pixel interpretation is flagged as an assumption in the source itself |
| `n=345` counts triangle *commands* | Certain — read from our source |
| That this is 658 actual triangles | **Mine.** Depends on the two-per-command convention |
| On `1CYCLE` lines the colour is stale and inert | **Measured** — A356, 276 of 289 rects |
| `0x80000400` is the depth buffer | **Measured** — A356 by order and uniformity, corroborated independently by A363 |
| Three framebuffers, 0x25800 apart, one per frame | **Measured** — A367 |
| `0xFFFC` means maximum depth | **Mine.** Recalled convention, not defined in this tree |
| What opcode `0x02` is called | **Mine, and explicitly unverified** — A363 |
| Anything about why a scene renders wrong | Not established by any of this |

---

## 9. Three questions you can now ask me

These are the ones where a census can actually settle it, and where I would have
to answer with a line rather than a paragraph:

1. **"Did the game ask for it at all?"** If something is missing from the
   picture, are there triangles and textures in the list for it? A missing thing
   that was never requested is the game's problem; a missing thing that was
   requested is ours.
2. **"Where was it drawn to, and in what order?"** `into=` and `seq=`. Something
   drawn into the wrong target, or drawn before the thing that covers it, looks
   identical to something not drawn at all.
3. **"How many frames is that actually true of?"** The honest answer is a number
   and it is usually smaller than the claim implies.

If a claim of mine cannot be pinned to one of those, it is probably an argument
rather than a measurement — and by this project's own rule, an argument can flag
a measured finding but cannot overturn one.
