#!/usr/bin/env python3
"""Build build/orientation-probe.tosc — a one-control layout that answers a
question the manual does not: does TouchOSC tell a script when the device is
rotated?

TouchOSC's scripting API has a `resize()` callback, but a document has a fixed
size and the app's AUTO rotation only rotates the rendered surface. If
`resize()` fires on rotation and reports swapped dimensions, a single layout
could rearrange itself and we would not need two files. If the readout never
changes, two files is the only honest answer.

Open the probe on the iPad, switch to control surface mode, set Preferences ->
Control Surface -> Rotation to AUTO, and rotate the device.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
from tosc import GROUP, LABEL, Node  # noqa: E402
from build_tosc import BUILD, load_spec  # noqa: E402

SCRIPT = """
-- Probe: report the layout's own idea of its size, and count resize events.
local resizes = 0

local function readout()
  local r = root.frame
  local s = self.frame
  self.values.text = string.format(
    "root %dx%d | self %dx%d | resize events: %d", r.w, r.h, s.w, s.h, resizes)
end

function init()
  readout()
end

function resize()
  resizes = resizes + 1
  readout()
end

function update()
  readout()
end
""".strip()


def main() -> int:
    spec = load_spec()
    colors = {k: tuple(v) for k, v in spec["colors"].items()}
    # Square, so neither orientation is obviously "native" to the document.
    side = 800
    root = Node(GROUP, (0, 0, side, side), name="root", color=colors["bg"],
                outline=False)
    root.add(Node(LABEL, (20, 20, side - 40, 80), name="title",
                  text="Rotate the iPad. Does the readout change?",
                  text_size=20, color=colors["text"],
                  background=False, outline=False))
    root.add(Node(LABEL, (20, 120, side - 40, 120), name="readout",
                  text="probe: script has not run", text_size=18,
                  color=colors["accent"], background=True, outline=True,
                  extra_props={"script": ("s", SCRIPT)}))

    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "orientation-probe.tosc")
    tosc.write(root, out, os.path.splitext(out)[0] + ".xml")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
