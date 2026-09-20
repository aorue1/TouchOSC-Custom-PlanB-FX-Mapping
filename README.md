# TouchOSC → Resolume Arena + TouchDesigner

A custom TouchOSC control surface for **PlanB-FX** that drives **Resolume
Arena** and **TouchDesigner** from one tablet, with a tab bar to switch between
views. Built for an iPad Air (4th gen), in both portrait and landscape.

The wordmark lives under `branding:` in `spec/mapping.yaml`. It is text only:
TouchOSC draws controls as vector primitives and cannot load an image, so the
logo artwork cannot be placed on the surface.

```
┌──────────────────────────────────────────────────────────┐
│ [B] PlanB-FX  [ master ─────────── ]   [TAP]  [BLACKOUT] │  always visible
├──────────────────────────────────────────────────────────┤
│  RESOLUME  │  FX  │  TOUCHDESIGNER                       │  pager tabs
│                                                          │
│   (page content)                                         │
└──────────────────────────────────────────────────────────┘
```

* **RESOLUME** — 4 layers × 8 clip-launch buttons, per-layer bypass/solo/clear,
  per-layer opacity faders, master + speed + resync column.
* **FX** — a knob and a bypass per effect per layer (8 effects × 4 layers).
* **COLOR** — an XY hue/shade pad with RGB faders and a live swatch, one
  feeding Resolume and one feeding TouchDesigner.
* **TOUCHDESIGNER** — generic param bank: 8 faders, 8 toggles, 8 triggers,
  2 XY pads, intensity and scene faders.

Transport is OSC to both hosts on separate connections: Resolume on
connection 1 (port 7000), TouchDesigner on connection 2 (port 7001).

## Layout

| Path | What |
| --- | --- |
| `spec/mapping.yaml` | Single source of truth: pages, sizes, ports, every OSC address |
| `tools/tosc.py` | Writer for the TouchOSC `.tosc` format (zlib-compressed `lexml` XML) |
| `tools/build_tosc.py` | Builds the surface from the spec |
| `tools/dump_map.py` | Regenerates `docs/osc-map.md` from the spec |
| `tools/verify.py` | Geometry and address checks on the built layout |
| `touchdesigner/osc_router.py` | OSC In DAT callbacks for the TouchDesigner side |
| `tools/build_probe.py` | Builds the rotation probe described below |
| `tools/inspect_tosc.py` | Prints the control tree / property summary of any `.tosc` |
| `tools/preview.py` | Renders a layout to SVG so it can be checked without a device |
| `build/vj-control-landscape.tosc` | 1180x820 layout |
| `build/vj-control-portrait.tosc` | 820x1180 layout |
| `build/*.xml` | Same layouts uncompressed, so diffs are reviewable |

## Build

```sh
make            # build the .tosc, regenerate the address map, verify the layout
```

or directly:

```sh
python3 tools/build_tosc.py                 # both orientations
python3 tools/build_tosc.py -r portrait     # just one
python3 tools/dump_map.py                   # -> docs/osc-map.md
python3 tools/verify.py                     # non-zero exit if anything is off
```

`verify.py` reads the generated XML and fails on controls that escape their
parent, overlap a sibling, fall below a 28px touch target, or stream their
value to an address another control already owns.

Only dependency is PyYAML (`pip install pyyaml`).

## Orientation

A TouchOSC document has **one fixed size and orientation** ([layout
properties](https://hexler.net/touchosc/manual/editor-layout)), and the app's
AUTO rotation setting only rotates the rendered surface to fill the screen — it
does not rearrange controls. So a single file cannot reflow when the iPad is
turned.

Both orientations are therefore generated from the same spec, sized to the iPad
Air 4's 1180x820 points so neither letterboxes:

* `build/vj-control-landscape.tosc`
* `build/vj-control-portrait.tosc`

The pages rearrange to suit the aspect ratio. In portrait the FX matrix
transposes (layers across, effects down) and its cells become wide, so the
dials turn into horizontal faders; the TouchDesigner page stacks the fader bank
above the XY pads instead of placing them side by side. Landscape keeps
circular dials, squared and centred in their cells. Every OSC
address is identical in both, so the two files are interchangeable: load the
other one and carry on, no re-mapping on either host.

Keep both on the iPad and switch from TouchOSC's layout list.

A self-reflowing single layout would need the scripting API to report device
rotation. It does not: the probe in `tools/build_probe.py` runs a script that
prints the root frame and a resize counter, and on the iPad Air 4 with Rotation
set to AUTO neither moves when the tablet is turned. Two files is the design,
not a workaround — see [`docs/setup.md`](docs/setup.md#why-two-files-settled).

## Status

Confirmed on the iPad Air 4: the layouts open, captions render, and Lua
scripts run. What each control *does* against a live Resolume composition and
TouchDesigner network is still unconfirmed — the addresses are written from the
Resolume OSC convention, not yet tested against a running composition.

## Credits

The colour picker's hue/shade maths is adapted from the ColorPicker module of
[tshoppa/touchOSC](https://github.com/tshoppa/touchOSC), MIT licensed,
copyright (c) 2023 Schulzki.

The `.tosc` writer's property names and enums follow
[NicoG60/TouchMCU](https://github.com/NicoG60/TouchMCU).

## Docs

* [`docs/setup.md`](docs/setup.md) — wiring up Resolume, TouchDesigner and the tablet
* [`docs/osc-map.md`](docs/osc-map.md) — generated address reference
