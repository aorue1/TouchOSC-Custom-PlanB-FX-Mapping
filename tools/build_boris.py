#!/usr/bin/env python3
"""Build the Boris Brejcha gig layout from spec/boris.yaml.

    python3 tools/build_boris.py        # -> build/boris-landscape.tosc

A show-specific surface built next to the generic one. It reuses the generic
builder's control factories and the same .tosc writer, so every format fix
made there (child-element messages, the right-to-left connection mask,
grabFocus, receive-capable values) applies here too.

Two pages: SHOW for Resolume and TD for TouchDesigner. Every TD control both
sends and receives on its address, so the iPad follows the APC40 and the
computer as well as driving them.
"""

from __future__ import annotations

import colorsys
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
from build_tosc import Builder, bake, load_spec, MOMENTARY, TOGGLE  # noqa: E402
from tosc import BOX, BUTTON, GROUP, LABEL, PAGER, Node, OscMessage, Shape  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "boris.yaml")
BUILD = os.path.join(ROOT, "build")
DOCS = os.path.join(ROOT, "docs")

DARK_TEXT = (0.08, 0.08, 0.10, 1.0)


# A toggle that shows its state as a solid block of colour rather than as a
# button's own fill, which TouchOSC draws dimmed while off and so cannot make
# "off" look emphatic. The chip carries the colour, a transparent button on
# top takes the touch, and the caption says which state it is in. The script
# repaints on every change of value -- a touch or an incoming message alike --
# which is what lets a toggle TD flips (Boris lock) show up on the iPad.
STATE_TOGGLE_SCRIPT = """
local ON = Color(@ON_R@, @ON_G@, @ON_B@, 1)
local OFF = Color(@OFF_R@, @OFF_G@, @OFF_B@, 1)
local DARK = Color(0.08, 0.08, 0.10, 1)
local LIGHT = Color(0.92, 0.92, 0.94, 1)
local ON_TEXT = '@ON_TEXT@'
local OFF_TEXT = '@OFF_TEXT@'
local DARK_WHEN_OFF = @DARK_WHEN_OFF@

local function paint()
  local on = self.values.x > 0.5
  local sib = self.parent.children
  sib.chip.color = on and ON or OFF
  sib.cap.values.text = on and ON_TEXT or OFF_TEXT
  if on or DARK_WHEN_OFF then
    sib.cap.textColor = DARK
  else
    sib.cap.textColor = LIGHT
  end
end

function init()
  paint()
end

function onValueChanged(key)
  if key == 'x' then paint() end
end
"""

# Palette list: momentary buttons that each send 1 on press, and the group
# keeps the last one pressed lit so the current palette is visible.
PALETTE_GROUP_SCRIPT = """
local N = @COUNT@
local LIT = Color(@LIT_R@, @LIT_G@, @LIT_B@, 1)
local UNLIT = Color(@UNLIT_R@, @UNLIT_G@, @UNLIT_B@, 1)
local DARK = Color(0.08, 0.08, 0.10, 1)
local LIGHT = Color(0.92, 0.92, 0.94, 1)

local function paint(selected)
  for i = 1, N do
    local chip = self.children['pal_chip_' .. i]
    local cap = self.children['pal_cap_' .. i]
    if chip then chip.color = (i == selected) and LIT or UNLIT end
    if cap then cap.textColor = (i == selected) and DARK or LIGHT end
  end
end

function init()
  paint(0)
end

function onReceiveNotify(key, value)
  if key == 'pick' then paint(value) end
end
"""

PALETTE_BUTTON_SCRIPT = """
local INDEX = @INDEX@

function onValueChanged(key)
  if key == 'x' and self.values.x == 1 then
    self.parent:notify('pick', INDEX)
  end
end
"""

# Blackout drives the master fader to zero, so the fader visibly drops and the
# iPad never shows a master Resolume does not have. The button also sends the
# 0 directly (see show_page).
BLACKOUT_SCRIPT = """
function onValueChanged(key)
  if key == 'x' and self.values.x == 1 then
    self.parent.children.master.values.x = 0
  end
end
"""


def rgb(color) -> dict:
    return {"r": color[0], "g": color[1], "b": color[2]}


class BorisBuilder(Builder):
    """The generic builder's factories, with this show's pages."""

    def __init__(self, spec: dict):
        # Only what the inherited factories use: colours and connections.
        self.spec = spec
        self.width = spec["layout"]["width"]
        self.height = spec["layout"]["height"]
        self.portrait = False
        self.colors = {k: tuple(v) for k, v in spec["colors"].items()}
        self.res_slot = spec["connections"]["resolume"]["slot"]
        self.res_conn = tosc.connections(self.res_slot)
        self.td_conn = tosc.connections(spec["connections"]["touchdesigner"]["slot"])

    # -- show-specific factories --------------------------------------------

    def caption(self, frame, text, size, color="text", name=None) -> Node:
        lbl = self.label(frame, text, size=size, color=color)
        if name:
            lbl.name = name
        return lbl

    def stacked_caption(self, parent, frame, text, size, color="text"):
        """A caption under a narrow fader: one line, or two if it has a space.

        TouchOSC clips text to its label rather than wrapping it, so a long
        name under a narrow fader would be cut off. Two short lines stay whole.
        """
        x, y, w, h = frame
        words = text.split(" ", 1)
        if len(words) == 1:
            parent.add(self.caption(frame, text, size, color))
        else:
            half = h // 2
            parent.add(self.caption((x, y, w, half), words[0], size, color))
            parent.add(self.caption((x, y + half, w, h - half), words[1], size,
                                    color))

    def state_toggle(self, parent, frame, name, address, conns, *, on_color,
                     off_color="unlit", on_text, off_text, text_size=14,
                     start_on=False):
        on, off = self.colors[on_color], self.colors[off_color]
        x, y, w, h = frame
        group = Node(GROUP, frame, name=name, background=False, outline=False)
        group.add(Node(BOX, (0, 0, w, h), name="chip",
                       color=on if start_on else off,
                       shape=Shape.RECTANGLE, background=True, outline=False,
                       interactive=False))
        # Until TD sends its real state, the toggle shows its start value --
        # so a toggle whose "off" is alarming can start in its normal state.
        btn = Node(BUTTON, (0, 0, w, h), name="btn", color=on,
                   button_type=TOGGLE, background=False, outline=True,
                   value_default=1.0 if start_on else 0.0,
                   script=bake(
                       STATE_TOGGLE_SCRIPT,
                       on_r=on[0], on_g=on[1], on_b=on[2],
                       off_r=off[0], off_g=off[1], off_b=off[2],
                       on_text=on_text, off_text=off_text,
                       # A strong colour like danger red reads better with
                       # dark text; the dim "unlit" grey needs light text.
                       dark_when_off="true" if off_color != "unlit" else "false"))
        btn.messages.append(OscMessage(address, conns))
        group.add(btn)
        cap = self.caption((0, 0, w, h), on_text if start_on else off_text,
                           text_size, name="cap")
        # Same rule as the script, so the first frame matches: dark text on a
        # lit chip or a strong "off" colour, light text on the dim unlit grey.
        if start_on or off_color != "unlit":
            cap.text_color = DARK_TEXT
        group.add(cap)
        parent.add(group)
        return group

    def block_header(self, parent, frame, text, color):
        parent.add(self.caption(frame, text, 17, color))

    # -- page 1: SHOW --------------------------------------------------------

    def show_page(self, width: int, height: int) -> Node:
        show = self.spec["show"]
        addr = show["addresses"]
        clips = show["clips"]
        page = Node(GROUP, (0, 0, width, height), name="SHOW",
                    color=self.colors["resolume"], background=False,
                    outline=False)

        pad = 8
        right_w = 170                       # master column
        main_w = width - right_w            # layer rows, scenes, crossfader
        name_w = 132                        # layer names
        opacity_w = 150
        clear_w = 66
        clip_x = name_w + pad
        clip_area = main_w - clip_x - opacity_w - clear_w - 3 * pad
        clip_w = (clip_area - (clips - 1) * pad) // clips

        def clip_frame(i, y, h):
            return (clip_x + i * (clip_w + pad), y, clip_w, h)

        # --- scenes: whole columns, aligned over the clip grid ---
        scenes_h = 64
        page.add(self.caption((0, pad, name_w, scenes_h), "SCENES", 15,
                              "accent"))
        for i in range(clips):
            column = i + 1
            self.add_button(page, clip_frame(i, pad, scenes_h),
                            f"scene_{column}",
                            addr["column_connect"].format(column=column),
                            self.res_conn, color="accent",
                            text=f"SCENE {column}", text_size=12,
                            constant_args=(1.0,))
        page.add(self.caption((clip_x + clip_area + pad, pad,
                               opacity_w, scenes_h), "OPACITY", 12))

        # --- crossfader: the most important control, full width at the foot ---
        xf_label_h = 24
        xf_h = 84
        xf_y = height - xf_h - pad
        rows_top = pad + scenes_h + pad
        rows_bottom = xf_y - xf_label_h - pad

        # --- layer rows, layer 5 at the top as in Resolume ---
        layers = show["layers"]
        row_h = (rows_bottom - rows_top) // len(layers)
        for r, layer in enumerate(layers):
            n = layer["layer"]
            y = rows_top + r * row_h
            h = row_h - pad
            page.add(self.caption((0, y, name_w, h), layer["name"], 13,
                                  "resolume", name=f"layer{n}_name"))
            if layer.get("opacity_only"):
                # No clips, no clear and no bypass: nothing to mistap.
                page.add(self.caption((clip_x, y, clip_area, h),
                                      layer["note"], 13, "text"))
            else:
                for i in range(clips):
                    clip = i + 1
                    self.add_button(page, clip_frame(i, y, h),
                                    f"layer{n}_clip{clip}",
                                    addr["clip_connect"].format(layer=n,
                                                                clip=clip),
                                    self.res_conn, color="panel",
                                    text=str(clip), text_size=14,
                                    constant_args=(1.0,))
                self.add_button(page, (main_w - clear_w - pad, y, clear_w, h),
                                f"layer{n}_clear",
                                addr["layer_clear"].format(layer=n),
                                self.res_conn, color="panel", text="CLEAR",
                                text_size=11, constant_args=(1.0,))
            page.add(self.fader((clip_x + clip_area + pad, y, opacity_w, h),
                                f"layer{n}_opacity",
                                addr["layer_opacity"].format(layer=n),
                                self.res_conn, horizontal=True,
                                color="resolume"))

        # --- crossfader ---
        xf_w = main_w - 2 * pad
        page.add(self.caption((pad, xf_y - xf_label_h, 220, xf_label_h),
                              "◀ PANORAMA  (A)", 15, "resolume"))
        page.add(self.caption((pad + (xf_w - 200) // 2, xf_y - xf_label_h,
                               200, xf_label_h), "CROSSFADER", 13, "text"))
        page.add(self.caption((pad + xf_w - 220, xf_y - xf_label_h, 220,
                               xf_label_h), "(B)  MIRROR ▶", 15, "resolume"))
        page.add(self.fader((pad, xf_y, xf_w, xf_h), "crossfader",
                            addr["crossfader"], self.res_conn, horizontal=True,
                            color="resolume"))

        # --- master column: master / blackout, then tempo ---
        x = main_w + pad
        col_w = right_w - 2 * pad
        btn_h = 56
        page.add(self.caption((x, pad, col_w, 22), "MASTER / BLACKOUT", 12,
                              "master"))
        tempo_y = height - pad - btn_h
        blackout_y = tempo_y - pad - btn_h
        master_top = pad + 24
        page.add(self.fader((x, master_top, col_w,
                             blackout_y - pad - master_top), "master",
                            addr["master"], self.res_conn, color="master"))

        blackout = Node(BUTTON, (x, blackout_y, col_w, btn_h), name="blackout",
                        color=self.colors["danger"], button_type=MOMENTARY,
                        script=bake(BLACKOUT_SCRIPT))
        # Belt and braces for a panic control: the button also sends the 0
        # itself, so master goes dark even if a script-moved fader turns out
        # not to send. A duplicate 0 does no harm.
        blackout.messages.append(OscMessage(addr["master"], self.res_conn,
                                            send_value=False,
                                            constant_args=(0.0,),
                                            trigger="RISE"))
        page.add(blackout)
        page.add(self.caption((x, blackout_y, col_w, btn_h), "BLACKOUT", 15))

        half = (col_w - pad) // 2
        for i, (name, key, text) in enumerate((("tap", "tempo_tap", "TAP"),
                                               ("resync", "tempo_resync",
                                                "RESYNC"))):
            self.add_button(page, (x + i * (half + pad), tempo_y, half, btn_h),
                            name, addr[key], self.res_conn, color="accent",
                            text=text, text_size=12, constant_args=(1.0,))
        return page

    # -- page 2: TD ------------------------------------------------------------

    def fader_bank(self, parent, x, y, h, faders, color, *, fader_w=56,
                   gap=8, caption_h=30):
        for i, f in enumerate(faders):
            fx = x + i * (fader_w + gap)
            name = "td_" + f["label"].lower().replace(" ", "_")
            parent.add(self.fader((fx, y, fader_w, h - caption_h), name,
                                  f["address"], self.td_conn, color=color))
            self.stacked_caption(parent, (fx - gap // 2, y + h - caption_h + 2,
                                          fader_w + gap, caption_h - 2),
                                 f["label"], 11)
        return len(faders) * fader_w + (len(faders) - 1) * gap

    def td_page(self, width: int, height: int) -> Node:
        td = self.spec["td"]
        page = Node(GROUP, (0, 0, width, height), name="TD",
                    color=self.colors["spiderweb"], background=False,
                    outline=False)
        pad = 10
        header_h = 28
        hue_h = 100
        top_h = height - hue_h - 3 * pad

        spider_w, side_w = 480, 452
        boris_w = width - spider_w - side_w - 4 * pad
        sx = pad
        dx = sx + spider_w + pad
        bx = dx + side_w + pad
        body_y = pad + header_h
        body_h = top_h - header_h

        # --- SPIDERWEB ---
        sw = td["spiderweb"]
        self.block_header(page, (sx, pad, spider_w, header_h), sw["label"],
                          "spiderweb")
        used = self.fader_bank(page, sx, body_y, body_h, sw["faders"],
                               "spiderweb")
        px = sx + used + pad + 6
        pw = sx + spider_w - px
        toggle_h = 92
        pad_h = body_h - toggle_h - pad - 24
        page.add(self.xy((px, body_y, pw, pad_h), "camera_orbit",
                         sw["pad"]["x"], sw["pad"]["y"], self.td_conn,
                         color="spiderweb"))
        page.add(self.caption((px, body_y + pad_h, pw, 24), sw["pad"]["label"],
                              12, "spiderweb"))
        self.state_toggle(page, (px, body_y + body_h - toggle_h, pw, toggle_h),
                          "panorama", sw["toggle"]["address"], self.td_conn,
                          on_color="spiderweb", on_text=sw["toggle"]["on_text"],
                          off_text=sw["toggle"]["off_text"], text_size=13)

        # --- SIDE AUDIOS ---
        sd = td["side"]
        self.block_header(page, (dx, pad, side_w, header_h), sd["label"], "side")
        used = self.fader_bank(page, dx, body_y, body_h, sd["faders"], "side")
        cx = dx + used + pad + 6
        cw = dx + side_w - cx
        auto_h = 76
        self.state_toggle(page, (cx, body_y, cw, auto_h), "auto_height",
                          sd["toggle"]["address"], self.td_conn,
                          on_color="side", on_text=sd["toggle"]["on_text"],
                          off_text=sd["toggle"]["off_text"], text_size=12)

        palettes = sd["palettes"]
        pal_y = body_y + auto_h + pad
        page.add(self.caption((cx, pal_y, cw, 22), "PALETTE", 12, "side"))
        pal_y += 24
        pal_h = (body_y + body_h - pal_y - (len(palettes) - 1) * 6) // len(palettes)
        side_lit = self.colors["side"]
        unlit = self.colors["unlit"]
        group = Node(GROUP, (cx, pal_y, cw, body_y + body_h - pal_y),
                     name="palette", background=False, outline=False,
                     script=bake(PALETTE_GROUP_SCRIPT, count=len(palettes),
                                 lit_r=side_lit[0], lit_g=side_lit[1],
                                 lit_b=side_lit[2], unlit_r=unlit[0],
                                 unlit_g=unlit[1], unlit_b=unlit[2]))
        for i, p in enumerate(palettes):
            frame = (0, i * (pal_h + 6), cw, pal_h)
            group.add(Node(BOX, frame, name=f"pal_chip_{i + 1}", color=unlit,
                           shape=Shape.RECTANGLE, background=True,
                           outline=False, interactive=False))
            btn = Node(BUTTON, frame, name=f"pal_{i + 1}", color=side_lit,
                       button_type=MOMENTARY, background=False, outline=True,
                       script=bake(PALETTE_BUTTON_SCRIPT, index=i + 1))
            btn.messages.append(OscMessage(p["address"], self.td_conn,
                                           send_value=False,
                                           constant_args=(1.0,),
                                           trigger="RISE"))
            group.add(btn)
            group.add(self.caption(frame, p["name"], 12,
                                   name=f"pal_cap_{i + 1}"))
        page.add(group)

        # --- BORIS ---
        bo = td["boris"]
        self.block_header(page, (bx, pad, boris_w, header_h), bo["label"],
                          "boris")
        large = 2.0
        weights = [large if t.get("size") == "large" else 1.0
                   for t in bo["toggles"]]
        free = body_h - (len(weights) - 1) * pad
        y = body_y
        for t, wgt in zip(bo["toggles"], weights):
            h = int(free * wgt / sum(weights))
            name = "boris_" + t["address"].rsplit("/", 1)[-1]
            self.state_toggle(page, (bx, y, boris_w, h), name, t["address"],
                              self.td_conn, on_color="boris",
                              off_color=t.get("off_color", "unlit"),
                              on_text=t["on_text"], off_text=t["off_text"],
                              start_on=bool(t.get("start_on", False)),
                              text_size=16 if wgt > 1 else 13)
            y += h + pad

        # --- HUE strip, over a rainbow ---
        hu = td["hue"]
        hy = top_h + 2 * pad
        page.add(self.caption((pad, hy, width - 2 * pad, 24), hu["label"], 14,
                              "hue"))
        fy = hy + 26
        fw = width - 2 * pad
        fh = hue_h - 26
        # TouchOSC draws no gradients, so the rainbow is a run of thin boxes.
        segments = 60
        seg_w = fw / segments
        for i in range(segments):
            r, g, b = colorsys.hsv_to_rgb(i / segments, 0.75, 0.85)
            x0 = pad + round(i * seg_w)
            x1 = pad + round((i + 1) * seg_w)
            page.add(Node(BOX, (x0, fy, x1 - x0, fh), name=f"hue_band_{i}",
                          color=(r, g, b, 1.0), shape=Shape.RECTANGLE,
                          background=True, outline=False, interactive=False))
        # The fader draws only its cursor, so the rainbow stays visible: a
        # coloured bar would cover the very colours it selects between. The
        # cursor is white so it reads against every hue, the pink outline
        # carries the part colour.
        hue = self.fader((pad, fy, fw, fh), "hue", hu["address"], self.td_conn,
                         horizontal=True, color="master")
        hue.background = False
        hue.outline = False
        hue.extra_props = {"bar": ("b", False), "cursor": ("b", True)}
        page.add(Node(BOX, (pad, fy, fw, fh), name="hue_frame",
                      color=self.colors["hue"], shape=Shape.RECTANGLE,
                      background=False, outline=True,
                      outline_style=tosc.Outline.FULL, interactive=False))
        page.add(hue)
        return page

    # -- assembly --------------------------------------------------------------

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
                          (self.td_page(w, page_h), "TD")):
            page.frame = (0, tab_h, w, page_h)
            page.tab_label = tab
            pager.add(page)
        root.add(pager)
        return root


def address_map(root: Node, out: str) -> None:
    """Write every control's name and address, for checking against TD."""
    rows = []

    def walk(node, page):
        if node.type == GROUP and node.tab_label:
            page = node.tab_label
        for msg in getattr(node, "messages", []):
            conn = "TD" if msg.conns.endswith("10") else "Resolume"
            rows.append((page or "", node.name, msg.path, conn))
        for child in getattr(node, "children", []):
            walk(child, page)

    walk(root, None)
    lines = ["# Boris layout · OSC address map", "",
             "Generated by `tools/build_boris.py` from `spec/boris.yaml`.", "",
             "| Page | Control | Address | Sent to |", "| --- | --- | --- | --- |"]
    for page, name, path, conn in rows:
        lines.append(f"| {page} | `{name}` | `{path}` | {conn} |")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    spec = load_spec(SPEC)
    root = BorisBuilder(spec).build()
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "boris-landscape.tosc")
    tosc.write(root, out, os.path.splitext(out)[0] + ".xml")
    address_map(root, os.path.join(DOCS, "boris-osc-map.md"))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
