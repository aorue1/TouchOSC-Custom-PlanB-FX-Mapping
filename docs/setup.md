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

### Captions

A LABEL's caption is a **value** named `text`, not a property, and a BUTTON
draws no text at all. The first build got both wrong, so every label showed the
default "Label" and buttons were bare. `tools/tosc.py` now writes captions as
values, and `Builder.add_button` lays a non-interactive LABEL over each button
so touches still reach the button underneath. If a caption ever goes back to
reading "Label", that is the property-vs-value mistake returning.

### The rotation probe

Whether a single self-reflowing layout is possible comes down to one unknown:
does the scripting API's `resize()` callback fire when the device is rotated?

```sh
make probe      # -> build/orientation-probe.tosc
```

Open it on the iPad, enter control surface mode, set Rotation to **AUTO** and
turn the tablet. The readout prints the root frame and a resize counter.

* If the numbers swap or the counter climbs, one layout could rearrange itself
  in Lua, and the two-file approach becomes optional.
* If nothing moves, two files is the only honest answer and the probe can go.

Tell me which happens and I will act on it.

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

## 5. Changing the surface

Everything about the layout comes from `spec/mapping.yaml` — grid sizes,
colours, ports, addresses. Change it and re-run `make`. The uncompressed
`build/vj-control.xml` is committed alongside the `.tosc` so a rebuild shows a
readable diff of what actually moved.
