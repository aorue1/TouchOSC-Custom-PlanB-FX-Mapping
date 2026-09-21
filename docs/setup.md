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

`/td/blackout` is handled specially by the router: it drops every mapped
parameter to its low value.

## 5. Clip banks and names

TouchOSC has no scrolling control, so more clips than fit on screen are reached
by **banking**. The clip grid sits in its own pager whose tabs are clip ranges
(1-8, 9-16, ...), 4 banks of 8 by default — `clips:` and `banks:` in the spec.
Banking moves every layer at once, and only the clip buttons move: opacity,
bypass/solo/clear and the PREV/NEXT row stay where they are, so the controls
you hold during a set never shift under your hand.

Each layer also has PREV/NEXT clip buttons. **Their addresses are unverified**,
as are the colour parameters — confirm both in Arena under Shortcuts > Edit OSC.

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

## 6. The colour picker

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

## 7. The FX page

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

## 8. Changing the surface

Everything about the layout comes from `spec/mapping.yaml` — grid sizes,
colours, ports, addresses. Change it and re-run `make`. The uncompressed
`build/vj-control.xml` is committed alongside the `.tosc` so a rebuild shows a
readable diff of what actually moved.
