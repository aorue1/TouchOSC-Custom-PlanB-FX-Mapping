# TouchOSC → Resolume Arena + TouchDesigner

A custom TouchOSC control surface that drives **Resolume Arena** and
**TouchDesigner** from one tablet, with a tab bar to switch between views.
Built for an iPad Air (4th gen), in both portrait and landscape.

```
┌──────────────────────────────────────────────────────────┐
│  VJ Control   [ master ─────────── ]   [TAP]  [BLACKOUT] │  always visible
├──────────────────────────────────────────────────────────┤
│  RESOLUME  │  FX  │  TOUCHDESIGNER                       │  pager tabs
│                                                          │
│   (page content)                                         │
└──────────────────────────────────────────────────────────┘
```

* **RESOLUME** — 4 layers × 8 clip-launch buttons, per-layer bypass/solo/clear,
  per-layer opacity faders, master + speed + resync column.
* **FX** — a knob and a bypass per effect per layer (8 effects × 4 layers).
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

The pages rearrange to suit the aspect ratio — in portrait the FX matrix
transposes (layers across, effects down) and the TouchDesigner page stacks the
fader bank above the XY pads instead of placing them side by side. Every OSC
address is identical in both, so the two files are interchangeable: load the
other one and carry on, no re-mapping on either host.

Keep both on the iPad and switch from TouchOSC's layout list. A truly
self-reflowing single layout would need the scripting API to report device
rotation; `make probe` builds `build/orientation-probe.tosc` to find out
whether it does — see [`docs/setup.md`](docs/setup.md#the-rotation-probe).

## Status

The generated `.tosc` opens in the TouchOSC desktop editor and control surface
mode. Captions were wrong in the first build (written as properties rather than
values, so everything read "Label") and are now written as values, with button
captions as non-interactive overlay labels — that fix is built but not yet
confirmed on the iPad. What each control *does* against a live Resolume
composition and TD network is still unconfirmed.

## Docs

* [`docs/setup.md`](docs/setup.md) — wiring up Resolume, TouchDesigner and the tablet
* [`docs/osc-map.md`](docs/osc-map.md) — generated address reference
