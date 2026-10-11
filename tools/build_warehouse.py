#!/usr/bin/env python3
"""Build the Boris Warehouse afterparty layout from spec/warehouse.yaml.

    python3 tools/build_warehouse.py   # -> build/boris-warehouse-landscape.tosc

Starts from the Boris layout: the SHOW page is the Boris builder's own, so
every fix there applies here. The TD page is new, for the two visuals this
show runs, Spiderweb and Acuarela. There is no FX page.
"""

from __future__ import annotations

import colorsys
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
from build_boris import (BorisBuilder, address_map, bake,  # noqa: E402
                         load_spec, saturated, MOMENTARY)
from tosc import (BOX, BUTTON, FADER, GROUP, PAGER, Node,  # noqa: E402
                  OscMessage, Shape)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "warehouse.yaml")
BUILD = os.path.join(ROOT, "build")
DOCS = os.path.join(ROOT, "docs")


def hex_rgb(code: str) -> tuple:
    code = code.lstrip("#")
    return tuple(int(code[i:i + 2], 16) / 255 for i in (0, 2, 4))


def stops_band(stops):
    """band(t) for a hue slider: linear between measured stops, and 1.0
    wraps back to the first stop, as the visual's hue control does."""
    rgb = [hex_rgb(c) for c in stops]
    n = len(rgb)

    def band(t):
        pos = t * n
        i = int(pos) % n
        f = pos - int(pos)
        a, b = rgb[i], rgb[(i + 1) % n]
        return tuple(a[k] + (b[k] - a[k]) * f for k in range(3)) + (1.0,)
    return band


# SHAPE selector. A hidden receive-only fader holds the current value: TD's
# feedback lands on it, and a pressed option sets it too, and either way its
# script lights the matching option. Each option button sends its own value
# itself, so nothing depends on a script-moved control sending.
SHAPE_VALUE_SCRIPT = """
local N = @N@
local ON = Color(@ON_R@, @ON_G@, @ON_B@, 1)
local OFF = Color(@OFF_R@, @OFF_G@, @OFF_B@, 1)

local DARK = Color(0.08, 0.08, 0.10, 1)
local LIGHT = Color(0.92, 0.92, 0.94, 1)

local function paint()
  local pick = math.floor(self.values.x * (N - 1) + 0.5) + 1
  for i = 1, N do
    local chip = self.parent.children['shape_chip_' .. i]
    if chip then chip.color = (i == pick) and ON or OFF end
    -- Dark text on the lit chip, light on the others; a two-word option
    -- is two caption lines.
    for _, part in ipairs({'a', 'b'}) do
      local cap = self.parent.children['shape_cap_' .. i .. '_' .. part]
      if cap then cap.textColor = (i == pick) and DARK or LIGHT end
    end
  end
end

function init()
  paint()
end

function onValueChanged(key)
  if key == 'x' then paint() end
end
""".strip()

SHAPE_OPTION_SCRIPT = """
local VALUE = @VALUE@

function onValueChanged(key)
  if key == 'x' and self.values.x == 1 then
    self.parent.children.shape_value.values.x = VALUE
  end
end
""".strip()

# CENTRE puts a pad's cursor back at the middle. The button also
# sends 0.5 on both axes itself, like BLACKOUT, so the reset reaches TD even
# if a script-moved pad turns out not to send.
CENTRE_SCRIPT = """
function onValueChanged(key)
  if key == 'x' and self.values.x == 1 then
    local pad = self.parent.children.@PAD@
    pad.values.x = 0.5
    pad.values.y = 0.5
  end
end
""".strip()


# PROGRAM lights. TD reports each program's state on its own toggle address;
# a hidden receive-only fader per program takes it and repaints that
# program's chip and caption. The light can't live on the button itself: an
# incoming 1 would move the button and fire the trigger again.
PROGRAM_STATE_SCRIPT = """
local I = @I@
local ON = Color(@ON_R@, @ON_G@, @ON_B@, 1)
local OFF = Color(@OFF_R@, @OFF_G@, @OFF_B@, 1)
local DARK = Color(0.08, 0.08, 0.10, 1)
local LIGHT = Color(0.92, 0.92, 0.94, 1)

local function paint()
  local on = self.values.x > 0.5
  local chip = self.parent.children['prog_chip_' .. I]
  local cap = self.parent.children['prog_cap_' .. I]
  if chip then chip.color = on and ON or OFF end
  if cap then cap.textColor = on and DARK or LIGHT end
end

function init()
  paint()
end

function onValueChanged(key)
  if key == 'x' then paint() end
end
""".strip()


class WarehouseBuilder(BorisBuilder):
    """The Boris SHOW page, with this show's TD page."""

    def centred_pad(self, parent, frame, name, pad, color, button_frame):
        """A square pad resting at 0.5 / 0.5, with a CENTRE button."""
        xy = self.xy(frame, name, pad["x"], pad["y"], self.td_conn,
                     color=color)
        xy.value_default = 0.5
        xy.value_default_y = 0.5
        parent.add(xy)
        centre = Node(BUTTON, button_frame, name=f"{name}_centre",
                      color=self.colors[color], button_type=MOMENTARY,
                      script=bake(CENTRE_SCRIPT, pad=name))
        for path in (pad["x"], pad["y"]):
            centre.messages.append(OscMessage(path, self.td_conn,
                                              send_value=False,
                                              constant_args=(0.5,),
                                              trigger="RISE", receive=False))
        parent.add(centre)
        parent.add(self.caption(button_frame, "CENTRE", 14))
        return xy

    def program_group(self, parent, frame, programs, color):
        """Momentary buttons that fire a TD trigger; each lights from TD."""
        x, y, w, h = frame
        bh = (h - (len(programs) - 1) * 6) // len(programs)
        on, off = self.colors[color], self.colors["unlit"]
        group = Node(GROUP, frame, name="programs", background=False,
                     outline=False)
        for i, p in enumerate(programs):
            n = i + 1
            f = (0, i * (bh + 6), w, bh)
            group.add(Node(BOX, f, name=f"prog_chip_{n}", color=off,
                           shape=Shape.RECTANGLE, background=True,
                           outline=False, interactive=False))
            state = Node(FADER, f, name=f"prog_state_{n}", visible=False,
                         interactive=False,
                         script=bake(PROGRAM_STATE_SCRIPT, i=n,
                                     on_r=on[0], on_g=on[1], on_b=on[2],
                                     off_r=off[0], off_g=off[1],
                                     off_b=off[2]))
            state.messages.append(OscMessage(p["state"], self.td_conn,
                                             send=False, receive=True))
            group.add(state)
            btn = Node(BUTTON, f, name=f"prog_{n}", color=on,
                       button_type=MOMENTARY, background=False, outline=True)
            btn.messages.append(OscMessage(p["address"], self.td_conn,
                                           send_value=False,
                                           constant_args=(1.0,),
                                           trigger="RISE", receive=False))
            group.add(btn)
            group.add(self.caption(f, p["name"], 12, name=f"prog_cap_{n}"))
        parent.add(group)
        return group

    def shape_selector(self, parent, frame, shape, color):
        """One segment per option; the lit one follows TD."""
        x, y, w, h = frame
        opts = shape["options"]
        n = len(opts)
        gap = 6
        seg_w = (w - (n - 1) * gap) // n
        on, off = self.colors[color], self.colors["unlit"]
        group = Node(GROUP, frame, name="shape", background=False,
                     outline=False)
        value = Node(FADER, (0, 0, w, h), name="shape_value",
                     visible=False, interactive=False,
                     script=bake(SHAPE_VALUE_SCRIPT, n=n,
                                 on_r=on[0], on_g=on[1], on_b=on[2],
                                 off_r=off[0], off_g=off[1], off_b=off[2]))
        value.messages.append(OscMessage(shape["address"], self.td_conn,
                                         send=False, receive=True))
        group.add(value)
        for i, label in enumerate(opts):
            v = i / (n - 1)
            seg = (i * (seg_w + gap), 0, seg_w, h)
            group.add(Node(BOX, seg, name=f"shape_chip_{i + 1}",
                           color=on if i == 0 else off,
                           shape=Shape.RECTANGLE, background=True,
                           outline=False, interactive=False))
            btn = Node(BUTTON, seg, name=f"shape_{i + 1}", color=on,
                       button_type=MOMENTARY, background=False, outline=True,
                       script=bake(SHAPE_OPTION_SCRIPT, value=v))
            btn.messages.append(OscMessage(shape["address"], self.td_conn,
                                           send_value=False,
                                           constant_args=(v,),
                                           trigger="RISE", receive=False))
            group.add(btn)
            sx, sy, sw, sh = seg
            # TouchOSC clips rather than wraps, so two words go on two lines.
            words = label.split(" ", 1)
            line_h = sh // 4
            top = sy + (sh - line_h * len(words)) // 2
            for k, word in enumerate(words):
                cap = self.caption((sx, top + k * line_h, sw, line_h), word,
                                   11, name=f"shape_cap_{i + 1}_{'ab'[k]}")
                if i == 0:
                    cap.text_color = (0.08, 0.08, 0.10, 1.0)
                group.add(cap)
        parent.add(group)
        return group

    def td_page(self, width: int, height: int) -> Node:
        td = self.spec["td"]
        page = Node(GROUP, (0, 0, width, height), name="TD",
                    color=self.colors["spiderweb"], background=False,
                    outline=False)
        pad = 10
        header_h = 28
        label_h = 22
        strip_fader_h = 75
        strip_h = 2 * (label_h + strip_fader_h) + pad
        top_h = height - strip_h - 3 * pad
        body_y = pad + header_h
        body_h = top_h - header_h
        gap = 14
        fader_w, fader_gap = 48, 6
        pal_w = 150

        sw, ac = td["spiderweb"], td["acuarela"]

        def bank_w(faders):
            return len(faders) * fader_w + (len(faders) - 1) * fader_gap

        # Two square pads share what the fader banks and palettes leave.
        side = (width - 2 * pad - bank_w(sw["faders"]) - bank_w(ac["faders"])
                - pal_w - 4 * gap) // 2
        under_y = body_y + side + 12
        under_h = min(110, body_y + body_h - under_y - label_h)

        # --- SPIDERWEB faders ---
        x = pad
        used = self.fader_bank(page, x, body_y, body_h, sw["faders"],
                               "spiderweb", fader_w=fader_w, gap=fader_gap)
        self.block_header(page, (x, pad, used, header_h), sw["label"],
                          "spiderweb")
        x += used + gap

        # --- CAMERA · LIQUID pad (Spiderweb orbit + Acuarela brush), with
        # the Spiderweb SHAPE selector under it ---
        pd = td["pad"]
        self.block_header(page, (x, pad, side, header_h), pd["label"],
                          "shared")
        page.add(self.xy((x, body_y, side, side), "camera_liquid",
                         pd["x"], pd["y"], self.td_conn, color="shared"))
        shape = sw["shape"]
        page.add(self.caption((x, under_y, side, label_h),
                              f"SPIDERWEB {shape['label']}", 12, "spiderweb"))
        self.shape_selector(page, (x, under_y + label_h, side, under_h),
                            shape, "spiderweb")
        x += side + gap

        # --- ROTATION pad (turns the web itself), CENTRE under it ---
        rt = td["rotation"]
        self.block_header(page, (x, pad, side, header_h), rt["label"],
                          "spiderweb")
        self.centred_pad(page, (x, body_y, side, side), "rotation", rt,
                         "spiderweb", (x, under_y + label_h, side, under_h))
        x += side + gap

        # --- ACUARELA faders (its hue is in the colour strip) ---
        used = self.fader_bank(page, x, body_y, body_h, ac["faders"],
                               "acuarela", fader_w=fader_w, gap=fader_gap)
        self.block_header(page, (x - 20, pad, used + 40, header_h),
                          ac["label"], "acuarela")
        x += used + gap

        # --- PALETTE: switches both visuals ---
        pw = width - pad - x
        self.block_header(page, (x, pad, pw, header_h), "PALETTE", "shared")
        # PALETTE above PROGRAM in one column, every button the same height.
        pals, progs = td["palettes"], td.get("programs", [])
        btn_gap = 6
        n_btn = len(pals) + len(progs)
        prog_head = header_h if progs else 0
        bh = (body_h - prog_head - (n_btn - 1) * btn_gap) // n_btn
        pal_h = len(pals) * bh + (len(pals) - 1) * btn_gap
        self.palette_group(page, (x, body_y, pw, pal_h), pals, "shared")
        if progs:
            py = body_y + pal_h + btn_gap
            self.block_header(page, (x, py, pw, prog_head), "PROGRAM",
                              "shared")
            py += prog_head
            self.program_group(page, (x, py, pw, body_y + body_h - py),
                               progs, "shared")

        # --- COLOUR strip: Spiderweb hue over saturation on the left,
        # Acuarela hue, full height, on the right. Hue sliders show the
        # colours each visual really shows along its hue control.
        col = td["colour"]
        half_w = (width - 3 * pad) // 2
        y0 = top_h + 2 * pad

        swc = col["spiderweb"]
        y = y0
        page.add(self.caption((pad, y, half_w, label_h), swc["hue"]["label"],
                              13, "spiderweb"))
        y += label_h
        self.banded_fader(page, (pad, y, half_w, strip_fader_h), "hue_web",
                          swc["hue"]["address"], self.td_conn,
                          outline="spiderweb",
                          band=stops_band(swc["hue"]["stops"]))
        y += strip_fader_h + pad
        sa = swc["saturation"]
        page.add(self.caption((pad, y, half_w, label_h), sa["label"], 13,
                              "spiderweb"))
        y += label_h
        self.banded_fader(page, (pad, y, half_w, strip_fader_h),
                          "saturation_web", sa["address"], self.td_conn,
                          outline="spiderweb",
                          band=lambda t: saturated(self.colors["spiderweb"], t),
                          default=float(sa.get("default", 1.0)))

        ach = col["acuarela"]["hue"]
        x = pad + half_w + pad
        page.add(self.caption((x, y0, half_w, label_h), ach["label"], 13,
                              "acuarela"))
        self.banded_fader(page, (x, y0 + label_h, half_w,
                                 strip_h - label_h), "hue_acuarela",
                          ach["address"], self.td_conn, outline="acuarela",
                          band=stops_band(ach["stops"]))
        return page

    def mask_page(self, width: int, height: int) -> Node:
        """Boris mask point cloud: pads for position and rotation, the
        deformation faders, and the colourize controls along the foot."""
        mk = self.spec["mask"]
        page = Node(GROUP, (0, 0, width, height), name="MASK",
                    color=self.colors["mask"], background=False,
                    outline=False)
        pad = 10
        header_h = 28
        label_h = 22
        strip_fader_h = 75
        strip_h = 2 * (label_h + strip_fader_h) + pad
        top_h = height - strip_h - 3 * pad
        body_y = pad + header_h
        body_h = top_h - header_h
        gap = 14
        btn_h = 56

        # --- faders ---
        x = pad
        used = self.fader_bank(page, x, body_y, body_h, mk["faders"], "mask")
        self.block_header(page, (x, pad, used, header_h), "MASK", "mask")
        x += used + gap

        # --- MOVE and ROTATE, square, each with CENTRE below ---
        side = min(body_h - btn_h - pad, (width - pad - x - gap) // 2)
        # Height limits the pads, so centre them in the width they leave.
        x += (width - pad - x - (2 * side + gap)) // 2
        for key in ("move", "rotate"):
            pd = mk[key]
            self.block_header(page, (x, pad, side, header_h), pd["label"],
                              "mask")
            self.centred_pad(page, (x, body_y, side, side),
                             f"mask_{key}", pd, "mask",
                             (x, body_y + side + pad, side, btn_h))
            x += side + gap

        # --- colour strip: APPLY COLOR full width, COLOR A / B below ---
        fw = width - 2 * pad
        y = top_h + 2 * pad
        ap = mk["apply_color"]
        page.add(self.caption((pad, y, fw, label_h), ap["label"], 13, "mask"))
        page.add(self.fader((pad, y + label_h, fw, strip_fader_h),
                            "mask_apply_color", ap["address"], self.td_conn,
                            horizontal=True, color="mask"))
        y += label_h + strip_fader_h + pad
        half_w = (width - 3 * pad) // 2
        for i, key in enumerate(("color_a", "color_b")):
            c = mk[key]
            cx = pad + i * (half_w + pad)
            page.add(self.caption((cx, y, half_w, label_h), c["label"], 13,
                                  "mask"))
            # 0 = red, round the full hue circle.
            self.banded_fader(page, (cx, y + label_h, half_w, strip_fader_h),
                              f"mask_{key}", c["address"], self.td_conn,
                              outline="mask",
                              band=lambda t: colorsys.hsv_to_rgb(
                                  t, 0.75, 0.85) + (1.0,))
        return page

    def build(self) -> Node:
        w, h = self.width, self.height
        tab_h = self.spec["layout"]["tabbar_height"]
        root = Node(GROUP, (0, 0, w, h), name="root", color=self.colors["bg"],
                    outline=False)
        pager = Node(PAGER, (0, 0, w, h), name="views",
                     color=self.colors["panel"], background=False,
                     outline=False,
                     extra_props={
                         "tabbar": ("b", 1),
                         "tabbarSize": ("i", tab_h),
                         "tabbarDoubleTap": ("b", 0),
                         "tabLabels": ("b", 1),
                         "textSizeOff": ("i", 15),
                         "textSizeOn": ("i", 15),
                     })
        page_h = h - tab_h
        for page, tab in ((self.show_page(w, page_h), "SHOW"),
                          (self.td_page(w, page_h), "TD"),
                          (self.mask_page(w, page_h), "MASK")):
            page.frame = (0, tab_h, w, page_h)
            page.tab_label = tab
            pager.add(page)
        root.add(pager)
        return root


def main() -> int:
    spec = load_spec(SPEC)
    root = WarehouseBuilder(spec).build()
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "boris-warehouse-landscape.tosc")
    tosc.write(root, out, os.path.splitext(out)[0] + ".xml")
    address_map(root, os.path.join(DOCS, "warehouse-osc-map.md"),
                title="Boris Warehouse layout",
                tool="tools/build_warehouse.py", spec="spec/warehouse.yaml")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
