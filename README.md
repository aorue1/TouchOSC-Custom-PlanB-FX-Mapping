# TouchOSC → Resolume Arena + TouchDesigner

A custom TouchOSC control surface that drives **Resolume Arena** and
**TouchDesigner** from one tablet, with a tab bar to switch between views.

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
| `build/vj-control.tosc` | The layout to open in TouchOSC |
| `build/vj-control.xml` | Same layout uncompressed, so diffs are reviewable |

## Build

```sh
make            # build the .tosc, regenerate the address map, verify the layout
```

or directly:

```sh
python3 tools/build_tosc.py     # -> build/vj-control.tosc
python3 tools/dump_map.py       # -> docs/osc-map.md
python3 tools/verify.py         # non-zero exit if anything is off
```

`verify.py` reads the generated XML and fails on controls that escape their
parent, overlap a sibling, fall below a 28px touch target, or stream their
value to an address another control already owns.

Only dependency is PyYAML (`pip install pyyaml`).

## Status

The generated `.tosc` opens in the TouchOSC desktop editor, so the writer emits
a valid layout. What each control *does* once connected to a live Resolume
composition and TD network is still unconfirmed.

## Docs

* [`docs/setup.md`](docs/setup.md) — wiring up Resolume, TouchDesigner and the tablet
* [`docs/osc-map.md`](docs/osc-map.md) — generated address reference
