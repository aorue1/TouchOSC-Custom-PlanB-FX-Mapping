# Setup

## 1. Build and load the layout

```sh
make
```

This writes both orientations:

* `build/vj-control-landscape.tosc` — 1180x820
* `build/vj-control-portrait.tosc` — 820x1180

Copy both to the iPad (AirDrop, the TouchOSC editor's *Send to device*, or a
file share). Keep both loaded and switch between them from TouchOSC's layout
list when you turn the tablet — a document has a fixed size, so one file cannot
reflow on rotation. The addresses are identical in both, so nothing on the
Resolume or TouchDesigner side needs to change when you switch.

In *Preferences -> Control Surface -> Rotation*, leave the setting on **NORTH**.
AUTO would rotate a layout to fill the screen when you turn the iPad, which
fights the two-file approach — you would get the landscape layout sideways
rather than the portrait one.

### Inspecting a layout

`tools/inspect_tosc.py` decompresses any `.tosc` and prints its control tree,
or a summary of which properties and values each control type carries:

```sh
python3 tools/inspect_tosc.py build/vj-control-portrait.tosc --summary
python3 tools/inspect_tosc.py sample.tosc --type PAGER      # one type, in full
```

Point it at a layout saved by the TouchOSC editor to settle any question about
how a property is spelled, then diff that against one of ours. This is the
reliable way to resolve the property guesses that the manual does not spell
out — it is how the caption bug below should have been found.

### Format notes

`tools/tosc.py` follows [NicoG60/TouchMCU](https://github.com/NicoG60/TouchMCU),
a working Mk2 layout generator, rather than inferring property names from how
the app behaves. Three mistakes that each cost a round on the device:

* **A LABEL's caption is a value named `text`**, not a property. Written as a
  property it is ignored and the control shows its default "Label".
* **A LABEL's `color` is its background fill; `textColor` is the text.** The
  LAYER headers rendered white because only `color` was set.
* **A pager's tab captions come from a `tabLabel` property on each page** — the
  node's `name` is not used — and **each page's frame must be offset below the
  tab bar** (`y = tabbarSize`), not drawn from the pager's top edge. Getting
  this wrong gives a working pager with an empty tab bar, which is exactly what
  the device showed.

A BUTTON draws no text at all, so `Builder.add_button` lays a non-interactive
LABEL over each button; `interactive=0` is what lets touches fall through to
the button underneath. `tools/inspect_tosc.py` prints any layout's properties
and values when something needs settling.

### Why two files, settled

The open question was whether the scripting API's `resize()` callback fires on
device rotation — if it did, one layout could rearrange itself in Lua.

`make probe` builds `build/orientation-probe.tosc`, which prints the root
frame and a resize counter. Tested on the iPad Air 4 in control surface mode
with Rotation set to AUTO: **the script runs and the readout displays, but
rotating the device changes neither the frame nor the counter.** TouchOSC does
not report rotation to scripts, so a self-reflowing layout is not possible and
two files is the correct design, not a compromise.

The probe stays in the repo so the result can be re-checked against a future
TouchOSC release.

### Verifying the layout

`build/vj-control.tosc` opens in the TouchOSC desktop editor — the format is
confirmed good. `make` also runs `tools/verify.py`, which fails the build on
controls that escape their parent, overlap a sibling, are too small to hit, or
fight another control for an address.

What neither of those can check is behaviour against live hosts. With Resolume
and TouchDesigner running, walk the surface once:

* a clip button connects the clip you expect, not a neighbour;
* layer opacity faders move the right layers;
* the FX knobs find their effects (they are addressed by name, see below);
* the TD page shows up as channels on the OSC In CHOP.

## 2. TouchOSC connections

In TouchOSC: *Settings → Connections → OSC*.

| Slot | Host | Send port | Used by |
| --- | --- | --- | --- |
| 1 | IP of the Resolume machine | 7000 | RESOLUME + FX pages, master, tap |
| 2 | IP of the TouchDesigner machine | 7001 | TOUCHDESIGNER page |

The slot numbers matter: the layout hard-codes which connection each control
sends on (`connections` in `spec/mapping.yaml`). If you reorder them in the
app, change the spec and rebuild rather than re-mapping by hand.

## 3. Resolume Arena

*Preferences → OSC → OSC Input*: enable it, port **7000**.

The clip grid addresses layers and clips by index, so layer 1 clip 1 is the
top-left of Arena's composition. The FX page assumes each layer's effect chain
already contains the effects named in `spec/mapping.yaml` — Arena addresses
effects by name in the chain, so add them once and save the composition.

To confirm the path for any control, use Arena's *Shortcuts → OSC* editing
mode: it shows the exact address for the control you click.

## 4. TouchDesigner

* **Raw channels**: add an `OSC In CHOP`, port **7001**. Every control shows up
  as a channel (`td/fader/1`, `td/pad/1/x`, …) ready to reference.
* **Driving parameters directly**: add an `OSC In DAT` on the same port and
  point its callbacks at `touchdesigner/osc_router.py`. Edit `MAPPING`,
  `TOGGLES` and `TRIGGERS` in that file to name your own operators and
  parameters; values arrive normalised 0..1 and are scaled into the range you
  give.

`/td/blackout` is handled specially by the router — it drops every mapped
parameter to its low value — but **nothing currently sends it**: the blackout
button lived in the global strip, which is gone. The handler and the address
are kept so a panic button can be wired back without changing anything on the
TouchDesigner side.

## 5. No global strip

Resolume is always the master, so there is no band across the top of every
page holding a master fader, tap and blackout. Master opacity sits on the
Resolume page as a narrow column beside composition speed — in white, against
speed's yellow, because two identical faders side by side is a good way to
grab the wrong one mid-set — and BPM, resync and tap are grouped beneath the
colour swatch. Every page gets back the 60pt the
strip was taking, which is why the FX dials and opacity faders are as large as
they are.

If a panic blackout is wanted later, the cheapest version is a button sending
`0` to `/composition/master` — the layout had exactly that before, and
`Builder.add_button` with `constant_args=(0.0,)` is all it takes.

## 6. Clip banks and names

TouchOSC has no scrolling control, so clips are reached by **banking**, over
two rows of tabs: the first row picks a group of 16, the second a bank of 4
within it. Four rows of clip buttons therefore reach 32 clips per layer, and
the space saved goes to the opacity faders, which is what actually gets used
mid-set.

```yaml
grid:
  clips: 4          # clip rows on screen at once
  banks: 4          # banks per group (second tab row)
  bank_groups: 2    # groups of banks (first tab row)
  clip_height: 64
  columns: 8        # composition columns on the trigger row
```

The row above the grid fires whole **columns** across every layer
(`/composition/columns/{n}/connect`), in the space the global strip used to
occupy. Six columns are on screen at once, with `<` and `>` to reach the rest:

```yaml
grid:
  columns: 6         # buttons on screen
  columns_total: 32  # columns the arrows can reach
```

Those buttons carry no OSC message of their own, because which column they
fire depends on where the arrows are. The row's group keeps the offset,
rewrites the captions when it moves, and sends the message itself with
`sendOSC` — the one place in the layout where a script sends rather than a
control. Everything else drives a real control, so the value stays visible and
can be read back.

Raising `bank_groups` extends the reach without touching the layout: 3 groups
gives 48 clips per layer, still 4 rows on screen. Banking moves every layer at
once, and only the clip buttons move — the PREV/NEXT row, bypass/solo/clear
and the faders stay where they are, so nothing shifts under your hand.

Each layer also has PREV/NEXT clip buttons. **Their addresses are unverified**,
as are the colour parameters — confirm both in Arena under Shortcuts > Edit OSC.

### The BPM field

Tapping a tempo is not always realistic, so the master column carries the
number itself. Tap it for a numeric keypad, or use the -/+ buttons to nudge it
a beat at a time. TAP and RESYNC are still there underneath.

The keypad is `Builder.num_pad`, built here rather than vendored — the
TextInputDialog module is a full QWERTY keyboard, and for a BPM every key but
the digits is in the way. It follows the same shape as the vendored dialogs: a
hidden overlay shown when notified, which notifies its caller back with
`numberEntered` or `numPadCanceled`.

The value lives in a hidden fader, which is also what sends the OSC; the
display reads that fader back every frame, so typing, nudging and anything
Resolume sends all show up the same way.

```yaml
tempo:
  min_bpm: 20       # Arena's range
  max_bpm: 500
  default_bpm: 128
  nudge: 1          # BPM per -/+ press
```

**Unverified, like the other Resolume addresses:** the layout sends a
normalised 0-1 value across that range to `/composition/tempocontroller/tempo`,
which is how Resolume treats most parameters, but it may want the BPM directly.
If the tempo jumps to something absurd when you type 128, that is the reason —
check Shortcuts > Edit OSC and adjust the spec.

### Names on the buttons

Clip buttons show their clip number and layer headers show "LAYER n" until
Resolume tells them otherwise. If it does, the caption is replaced by the real
name. That needs two things:

1. **Arena must be sending.** Preferences > OSC > OSC Output, enabled, pointing
   at the iPad's IP and the port TouchOSC receives on. Without this nothing
   arrives and the numbers simply stay.
2. **The address must be right.** The spec guesses
   `/composition/layers/{layer}/clips/{clip}/name` and
   `/composition/layers/{layer}/name`. Whether Arena publishes names there is
   unconfirmed; a wrong address costs nothing but the feature, since the label
   keeps its built-in caption.

Names arrive as OSC strings written into each label's `text` value. Set
`feedback.enabled: false` in the spec to strip the receive messages entirely.

## 7. The colour picker

Each picker is an XY pad -- hue across, shade up -- over R, G and B faders,
with a live swatch beside it. The pad only moves the faders; the faders carry
the OSC. Setting a fader from a script still fires that fader's own message,
so nothing depends on a scripted OSC send, and the faders stay usable on their
own for fine adjustment.

The hue maths is adapted from the ColorPicker module of
[tshoppa/touchOSC](https://github.com/tshoppa/touchOSC) (MIT). That module is a
modal dialog -- open it, pick, confirm -- which suits a settings screen more
than a live surface, so only the maths is borrowed and the picker here is
always on screen.

**The Resolume addresses are a guess and need confirming.** `spec/mapping.yaml`
points them at a Solid Colour effect's parameters, which is a plausible target
but unverified. In Arena, open Shortcuts > OSC and click the colour parameter
you actually want to drive; whatever address it reports goes in the spec.

On the TouchDesigner side the three channels arrive as `/td/color/r`, `/g` and
`/b`, wired in `touchdesigner/osc_router.py` to a Constant TOP by default.

## 8. Speed as tempo multiples

The speed fader snaps to multiples of the tempo — 0.25x, 0.5x, 1x, 2x, 4x —
rather than sweeping freely, and its label shows the current multiple. It
drives composition speed, which is what clips play back at; it does not touch
the tempo itself.

```yaml
speed:
  multiples: [0.25, 0.5, 1, 2, 4]
  param_min: 0.0      # what Resolume's Speed parameter spans, used to turn
  param_max: 10.0     # a multiple into the 0-1 value OSC carries
  default: 1
```

The fader's own value is which stop it is on, not the value to send, so it
carries no message: the script converts the stop to a parameter value and
sends it. `param_min`/`param_max` are **unverified** — if 1x does not come out
as normal speed, they are the pair to correct.

## 9. The FX page

Layers run down the page and effects across: L1-L4 plus a **COMP** row that
drives the same effects at composition level, over everything. One dial per
cell and nothing else — dialling to zero is the bypass, so the whole cell
belongs to the dial (119pt in landscape, 171pt in portrait).

`fx_bypass` and `fx_comp_bypass` are still in the spec but the page no longer
uses them; they are there for whatever wants an explicit bypass later.

The list is deliberately short — only the effects actually reached for in a
set — because a dense matrix of small controls is easy to mistap in the dark.
Three things guard against that:

* **Large dials.** Four effects rather than eight, and no bypass button
  sharing the cell.
* **Wide gutters.** A finger that lands off-target hits dead space instead of
  the neighbouring effect.
* **Drag-only response.** FX dials use relative response, so a stray tap does
  *nothing*: the value moves only while dragging, instead of jumping to
  wherever the finger landed. Set `fx_relative: false` in the spec for
  tap-to-jump instead.
* **Focus grab.** Every dial, fader and XY pad keeps the touch once a drag
  starts. Without it, dragging up or down past a dial's edge hands the gesture
  to the control above or below, and the value you were setting jumps to a
  neighbour instead. This is the writer's default for continuous controls
  everywhere in the layout, not a per-page setting — see below.

Adding or removing an effect is a spec edit: entries in `resolume.fx_names`
and `grid.fx_params`. Each effect must already exist in the layer's (or
composition's) chain in Arena, since Resolume addresses effects by their name
in the chain.

Every FX control repaints itself by value, interpolating between three stops:
deep blue at rest, cyan halfway, green at full. A glance across the matrix
reads as a level meter rather than a wall of identical grey, and the resting
state is legible because a control's colour tints its background as well as
its bar — grey on dark was the problem, and a bar-only fix would have left
zero looking the same.

The stops are data, in `fx_scale` in the spec:

```yaml
fx_scale:
  low:  [0.11, 0.28, 0.72, 1.0]
  mid:  [0.10, 0.78, 0.82, 1.0]
  high: [0.25, 0.95, 0.38, 1.0]
```

`tools/build_tosc.py` bakes them into the per-control script, so changing the
scale is a spec edit and a rebuild. `init()` paints the resting colour when the
surface loads, so an untouched layout still shows it; `onValueChanged` repaints
on every move. Cool at the bottom is deliberate: red at rest reads as a fault
on a dark stage.

Landscape draws these as dials, portrait as horizontal faders — the portrait
cells are wide and short, where a dial wastes the width.

## 10. Two-way values

Every continuous control now both sends and receives on its address, so when
Resolume reports a value the control moves to match. This is what makes the
tap-tempo workflow work: tap until Arena settles on, say, 124.93, read it off
the BPM field, type 125, hit RESYNC.

It needs Arena's OSC Output enabled and pointed at the iPad (see section 3).
With it off, everything still works one-way and nothing on the surface ever
moves by itself.

Receiving needs the `<values>` mapping in the message, not just the argument
partial — a message without it parses and does nothing. That mapping is now
emitted for every value message; before, only the name labels had it, so no
fader in this layout could be moved by the host.

**Sharing control with someone on the computer.** Messages carry
`feedback = 0`, so a control that moves because of an incoming message does not
send that value straight back: no echo loops. What is not solved is both
operators moving the same control at once — an absolute fader takes whatever
arrives, so if someone drags layer opacity in Arena while your finger is on it,
the fader will fight you. The FX dials are immune, being relative: an incoming
value moves them and your drag continues from there. If this turns out to bite
on the opacity faders, the two fixes are relative response on those faders
(one property) or the Pickup module from
[tshoppa/touchOSC](https://github.com/tshoppa/touchOSC), which holds a control
inert until your finger crosses its current value.

## 11. Dragging off a control

Every continuous control in the layout — the FX dials, layer opacity, master,
speed, the TouchDesigner faders and XY pads, the colour picker's own field —
carries `grabFocus`, so a drag stays with the control it started on however
far the finger travels. `tools/tosc.py` applies it to FADER, RADIAL and XY by
default rather than each page asking for it, so a control added later cannot
be forgotten, and `tools/vendor.py` forces it inside grafted components too.

Buttons deliberately do **not** grab focus: sliding off a button before
lifting is how you abort a mis-press, and grabbing the touch would take that
escape away.

## 12. Changing the surface

Everything about the layout comes from `spec/mapping.yaml` — grid sizes,
colours, ports, addresses. Change it and re-run `make`. The uncompressed
`build/vj-control.xml` is committed alongside the `.tosc` so a rebuild shows a
readable diff of what actually moved.
