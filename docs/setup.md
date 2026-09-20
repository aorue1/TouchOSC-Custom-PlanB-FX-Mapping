# Setup

## 1. Build and load the layout

```sh
make
```

Copy `build/vj-control.tosc` to the tablet (AirDrop, the TouchOSC editor's
*Send to device*, or a file share) and open it in TouchOSC.

### Verifying the layout

The generator writes the format from spec, and has not yet been round-tripped
through the TouchOSC editor. First run on a machine with TouchOSC installed:

1. Open `build/vj-control.tosc` in the TouchOSC **editor** (desktop).
2. If it opens: check the pager shows three tabs, and that a clip button's
   message reads `/composition/layers/1/clips/1/connect`.
3. If it does *not* open: save any small layout from the editor, then
   `python3 -c "import zlib,sys; sys.stdout.buffer.write(zlib.decompress(open('sample.tosc','rb').read()))"`
   and diff its XML against `build/vj-control.xml`. The differences are the
   corrections `tools/tosc.py` needs.

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
