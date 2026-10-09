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
| `spec/boris.yaml` + `tools/build_boris.py` | Boris gig layout → `build/boris-landscape.tosc` |
| `docs/boris-osc-map.md` | Generated: every Boris control and its address |
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

## Boris Brejcha gig · Pedregal · 09 Oct 2026

A show-specific layout built next to the generic one (`make boris`), from the
brief. Three pages:
- **SHOW**: banked like the generic layout over the composition's **94
  columns** (group tabs 1-36 / 37-72 / 73-94 over bank tabs of 9; the last
  bank is 91-94; `<` `>` step through banks). Each bank page
  holds its own column buttons above its 5 layer rows of clips, so the column
  row always follows the bank (no fixed scenes row, per the brief); per
  layer PREV/NEXT, CLEAR, opacity; crossfader Panorama A ◀ ▶ B Mirror;
  SPEED (continuous, full range, two-way: matches the APC40) beside master/blackout;
  **HUE ROTATE · Resolume** (composition Hue Rotate, rainbow strip) and
  **SATURATION · Resolume** (composition Saturation effect,
  grey→colour strip, default full = normal); tap/resync.
- **FX**: the 5 layers + composition × HUE/SAT/RGB DELAY (no datamosh), drag-only
  dials. Composition HUE and SAT are SHOW faders, so those cells are captions.
- **TD**: Spiderweb (4 faders + CAMERA ORBIT pad), Side Audios (5 faders,
  auto height, 7 palettes; TREBLE left, BASS right), Boris toggles, and a COLOUR strip in two halves:
  SPIDERWEB (blue) `/td/hue/web` + `/td/saturation/web`, and SIDE + BORIS
  (yellow) `/td/hue/side` + `/td/saturation/side`; hue over a rainbow,
  saturation over grey→strong part hue, saturations default 1.

It reuses the generic builder's factories and writer.

- The TD addresses are exactly the ones TD routes on. Changing one breaks TD.
- Every TD value control sends *and* receives, so the iPad follows the APC40.
- `/td/toggle/4` (Panorama / wide) is **retired**: on no page, never re-add it.
- `/td/scene` and `/td/saturation` stay **off the iPad**: `/td/scene` is only
  for APC track fader 8 (moves both hues), `/td/saturation` is retired.
- Side Audios (layer 3) never gets a bypass button: its Bypass must stay ON in
  Resolume. It has its own clips and PREV/NEXT but no CLEAR, deliberately.
- Resolume saturation's top is `show.saturation.top` in the spec, sent as the
  VALUE partial's `scaleMax` (feedback maps back through it). If "normal" is
  not the top of Arena's range, set `top` to normal's normalised value.
- Toggles show state as a solid colour chip repainted by script on any value
  change, touch or feedback. LABELS starts ON; its OFF state is danger red.
- `on_text`/`off_text` in the YAML, never bare `on:`/`off:`: YAML reads those
  keys as booleans.

**Check at soundcheck** (none confirmed against a running Resolume yet):
crossfader direction (A = Panorama on the left), column/clip/clear/opacity and
PREV/NEXT addresses, SPEED tracking the APC40, the bank `<` `>` arrows (script sets pager pages), the composition hue rotate and saturation addresses (and saturation's range)
(Shortcuts → Edit OSC), FX effect names, BLACKOUT dropping master, and TD
feedback moving the iPad (`/td/toggle/2 1` sent to the iPad on 9001 lights
BORIS LOCK).

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
