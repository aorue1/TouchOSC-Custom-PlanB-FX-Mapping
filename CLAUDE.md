# TouchOSC custom PlanB-FX controller — working notes

A TouchOSC (Mk2) control surface for an iPad Air 4 that drives **Resolume
Arena** and **TouchDesigner**. Everything is generated from one spec; nothing
in `build/` is edited by hand.

```sh
make        # build both layouts, regenerate docs/osc-map.md, run the verifier
```

Only dependency: Python 3 + PyYAML.

## Where things are

| Path | What |
| --- | --- |
| `spec/mapping.yaml` | Single source of truth: sizes, counts, colours, every OSC address |
| `tools/build_tosc.py` | Lays out the pages; holds the Lua scripts as templates |
| `tools/tosc.py` | Writes the `.tosc` format. Knows nothing about VJing |
| `tools/vendor.py` | Grafts the vendored ColorPicker (`vendor/`) into the layout |
| `tools/verify.py` | Fails the build on overlaps, escapes, tiny targets, address clashes |
| `touchdesigner/osc_router.py` | OSC In DAT callbacks: address → TD parameter |
| `build/vj-control-{landscape,portrait}.tosc` | What goes on the iPad |
| `docs/setup.md`, `README.md` | Full user docs, incl. annotated page screenshots |

## Live setup

- Computer running TD and Resolume: **192.168.20.231**
- iPad TouchOSC → Connections → OSC:
  - **Connection 1** → 192.168.20.231, send **7000** (Resolume), receive 9000
  - **Connection 2** → 192.168.20.231, send **7001** (TouchDesigner), receive 9001
- TouchDesigner: **OSC In DAT on 7001**, Callbacks DAT → a Text DAT holding
  `touchdesigner/osc_router.py`
- TouchDesigner MCP: local, port **9981**

## Current task

Map **XY pad 2** to rotate the camera in the open TD project.

`touchdesigner/osc_router.py` already has it: `/td/pad/2/x` → `ry`
(−180..180, pan) and `/td/pad/2/y` → `rx` (−60..60, tilt), against
`CAMERA = "/project1/cam1"`, which is a **guess**. Use the TD MCP to find the real
camera path, set `CAMERA`, and confirm the camera turns.

**Check first that OSC arrives at all.** Messages were never sent until two
writer bugs were fixed (see below). The fixed build has not been confirmed on
the device yet. Moving a TD fader should put `/td/fader/1  0.43`-style rows in
the OSC In DAT. A fresh fader made in the iPad's own editor already reached TD,
so the network is known good.

The user may instead want the camera to **orbit** the scene rather than turn
in place. The usual way is to rotate a parent COMP the camera sits in, rather
than the camera itself.

## Format rules learned the hard way

Each cost a round on the device. They are the reason the writer looks the way
it does, so don't "simplify" them away.

- **OSC message fields are child elements**, never attributes:
  `<enabled>1</enabled>`, `<connections>…</connections>`,
  `<partial><type>…</type><conversion>…</conversion><value>…</value>…`. The app
  silently ignores attributes.
- **A path is a run of partials that concatenate**, with each `/` its own partial.
- **No `<values>` block** on OSC messages. Receiving works through the VALUE
  argument partial.
- **The connection mask reads right to left**: `00001` is connection 1, `00010`
  is connection 2. Lua `sendOSC` takes the opposite order (a table whose first
  entry is connection 1). Build each from the slot number, never one from the other.
- **The `.tosc` is compact XML**, like the editor writes. The `.xml` beside it is
  indented only so diffs read well.
- **A LABEL's caption is a value** named `text`, not a property; `color` is its
  fill, and `textColor` is the text.
- **Pager tabs come from a `tabLabel` property**, and each page frame is offset
  `y = tabbarSize` below the tab bar.
- **A BUTTON draws no text**: captions are non-interactive LABELs on top.
- **All continuous controls set `grabFocus`** (writer default). Buttons don't, so
  sliding off a button still aborts a mis-press.
- **Built-in TD parameter names are lowercase** in Python (`tx`, `ry`, `amp`).

Reference for the format: the editor-saved files in `vendor/` (410 real OSC
messages), and NicoG60/TouchMCU. Copy from those; don't infer from behaviour.

## Verified vs not

**Verified on the device:** layout loads; tab bars; captions; Lua runs (speed
multiple and BPM labels, FX dials painting by value); a fresh editor fader
reaches TD over the network.

**Not yet verified:** that this layout's own messages now send (expected after
the mask fix); everything against a running Resolume. The guessed Resolume
addresses are tabled in `README.md` → *Addresses that still need confirming*:
FX effect/param names, clip next/prev, colour, tempo, speed range, and
clip/layer names. Confirm each in Arena via *Shortcuts → Edit OSC*.

## Working conventions

- Change `spec/mapping.yaml`, run `make`. Never hand-edit `build/`.
- Node IDs are deterministic, so an unchanged spec rebuilds byte-for-byte and
  `git diff build/*.xml` shows exactly what moved.
- Push to `main`. The repo is public and MIT licensed.
- Commit messages explain *why*. Docs live in `README.md` and `docs/setup.md`;
  keep them in step with behaviour.
- After a layout change, `./tools/render_diagrams.sh` regenerates the README
  diagrams over the device screenshots in `docs/img/screen-*.webp`.
