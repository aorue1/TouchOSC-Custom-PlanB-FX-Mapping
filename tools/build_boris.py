#!/usr/bin/env python3
"""Build the Boris Brejcha gig layout from spec/boris.yaml.

    python3 tools/build_boris.py        # -> build/boris-landscape.tosc

A show-specific surface built next to the generic one. It reuses the generic
builder's control factories and the same .tosc writer, so every format fix
made there (child-element messages, the right-to-left connection mask,
grabFocus, receive-capable values) applies here too.

Three pages: SHOW and FX for Resolume, TD for TouchDesigner. Every TD control both
sends and receives on its address, so the iPad follows the APC40 and the
computer as well as driving them.
"""

from __future__ import annotations

import colorsys
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
from build_tosc import (Builder, bake, fx_color_script, load_spec,  # noqa: E402
                        MOMENTARY, TOGGLE)
from tosc import (BOX, BUTTON, GROUP, LABEL, PAGER, Node, OscMessage,  # noqa: E402
                  Response, Shape)

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


def desaturate(color, t):
    """`color` at saturation t: 0 is its grey, 1 the colour itself."""
    grey = 0.3 * color[0] + 0.59 * color[1] + 0.11 * color[2]
    return tuple(grey + (c - grey) * t for c in color[:3]) + (1.0,)


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
        self.fx_script = fx_color_script(spec["fx_scale"])
        self.colors["fx_low"] = tuple(spec["fx_scale"]["low"])

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

    def banded_fader(self, parent, frame, name, address, conns, *, outline,
                     band, default=None, scale=(0.0, 1.0), segments=60):
        """A horizontal fader drawn over a strip of colour showing what it does.

        TouchOSC draws no gradients, so the strip is a run of thin boxes, with
        band(t) the colour at position t (0 left, 1 right). The fader draws
        only its cursor, white so it reads against every band: a coloured bar
        would cover the very colours it selects between. The outline carries
        the part colour.
        """
        x, y, w, h = frame
        seg_w = w / segments
        for i in range(segments):
            x0 = x + round(i * seg_w)
            x1 = x + round((i + 1) * seg_w)
            parent.add(Node(BOX, (x0, y, x1 - x0, h), name=f"{name}_band_{i}",
                            color=band((i + 0.5) / segments),
                            shape=Shape.RECTANGLE, background=True,
                            outline=False, interactive=False))
        fdr = self.fader(frame, name, address, conns, horizontal=True,
                         color="master")
        fdr.background = False
        fdr.outline = False
        fdr.extra_props = {"bar": ("b", False), "cursor": ("b", True)}
        if default is not None:
            fdr.value_default = default
        fdr.messages[0].scale = scale
        parent.add(Node(BOX, frame, name=f"{name}_frame",
                        color=self.colors[outline], shape=Shape.RECTANGLE,
                        background=False, outline=True,
                        outline_style=tosc.Outline.FULL, interactive=False))
        parent.add(fdr)
        return fdr

    def block_header(self, parent, frame, text, color):
        parent.add(self.caption(frame, text, 17, color))

    # -- page 1: SHOW --------------------------------------------------------

    def show_page(self, width: int, height: int) -> Node:
        """Scenes, banked clip rows per layer, crossfader, master column.

        Clips bank as on the generic layout -- a tab row of groups over a tab
        row of banks -- and only the clip buttons move: names, PREV/NEXT,
        CLEAR and opacity stay put, so nothing shifts under a finger.
        """
        show = self.spec["show"]
        addr = show["addresses"]
        clips, banks, groups = show["clips"], show["banks"], show["bank_groups"]
        page = Node(GROUP, (0, 0, width, height), name="SHOW",
                    color=self.colors["resolume"], background=False,
                    outline=False)

        pad = 8
        right_w = 186                       # master column
        main_w = width - right_w            # layer rows, scenes, crossfader
        name_w = 118                        # layer names
        nav_w = 62                          # PREV over NEXT
        clear_w = 62
        opacity_w = 136
        clip_x = name_w + pad
        clip_area = (main_w - clip_x - nav_w - clear_w - opacity_w - 4 * pad)
        clip_w = (clip_area - (clips - 1) * pad) // clips
        clip_area = clips * clip_w + (clips - 1) * pad
        nav_x = clip_x + clip_area + pad
        clear_x = nav_x + nav_w + pad
        opacity_x = clear_x + clear_w + pad

        def clip_frame(i, y, h):
            return (clip_x + i * (clip_w + pad), y, clip_w, h)

        # --- scenes: whole columns, aligned over the first clip bank ---
        scenes_h = 60
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

        # --- crossfader: the most important control, full width at the foot ---
        xf_label_h = 24
        xf_h = 80
        xf_y = height - xf_h - pad
        rows_bottom = xf_y - xf_label_h - pad

        # --- bank tabs, then layer rows (layer 5 at the top, as in Resolume) ---
        tab_h = 34
        tabs_y = pad + scenes_h + pad
        rows_top = tabs_y + 2 * tab_h
        layers = show["layers"]
        row_h = (rows_bottom - rows_top) // len(layers)
        rows_h = row_h * len(layers)
        for caption, x, w in (("BANK", 0, name_w), ("CLIP", nav_x, nav_w),
                              ("", clear_x, clear_w),
                              ("OPACITY", opacity_x, opacity_w)):
            if caption:
                page.add(self.caption((x, tabs_y + tab_h, w, tab_h), caption,
                                      12))

        def tabs(name, frame, size):
            return Node(PAGER, frame, name=name, color=self.colors["panel"],
                        background=False, outline=False,
                        extra_props={
                            "tabbar": ("b", 1),
                            "tabbarSize": ("i", tab_h),
                            "tabbarDoubleTap": ("b", 0),
                            "tabLabels": ("b", 1),
                            "textSizeOff": ("i", size),
                            "textSizeOn": ("i", size),
                        })

        per_group = clips * banks
        outer = tabs("clipgroups", (clip_x, tabs_y, clip_area,
                                    2 * tab_h + rows_h), 12)
        for g in range(groups):
            g_first = g * per_group + 1
            g_page = Node(GROUP, (0, tab_h, clip_area, tab_h + rows_h),
                          name=f"group{g + 1}", background=False,
                          outline=False,
                          tab_label=f"CLIPS {g_first}-{g_first + per_group - 1}")
            inner = tabs(f"banks{g + 1}", (0, 0, clip_area, tab_h + rows_h),
                         11)
            for b in range(banks):
                b_first = g_first + b * clips
                bank = Node(GROUP, (0, tab_h, clip_area, rows_h),
                            name=f"g{g + 1}bank{b + 1}", background=False,
                            outline=False,
                            tab_label=f"{b_first}-{b_first + clips - 1}")
                for r, layer in enumerate(layers):
                    n = layer["layer"]
                    for i in range(clips):
                        clip = b_first + i
                        self.add_button(
                            bank, (i * (clip_w + pad), r * row_h, clip_w,
                                   row_h - pad),
                            f"layer{n}_clip{clip}",
                            addr["clip_connect"].format(layer=n, clip=clip),
                            self.res_conn, color="panel", text=str(clip),
                            text_size=14, constant_args=(1.0,))
                inner.add(bank)
            g_page.add(inner)
            outer.add(g_page)
        page.add(outer)

        for r, layer in enumerate(layers):
            n = layer["layer"]
            y = rows_top + r * row_h
            h = row_h - pad
            if layer.get("note"):
                page.add(self.caption((0, y, name_w, h * 2 // 3),
                                      layer["name"], 13, "resolume",
                                      name=f"layer{n}_name"))
                page.add(self.caption((0, y + h // 2, name_w, h // 2),
                                      layer["note"], 10, "text"))
            elif len(layer["name"]) > 12:
                # Too long for one line at this width: TouchOSC clips, it
                # does not wrap.
                self.stacked_caption(page, (0, y + h // 4, name_w, h // 2),
                                     layer["name"], 13, "resolume")
            else:
                page.add(self.caption((0, y, name_w, h), layer["name"], 13,
                                      "resolume", name=f"layer{n}_name"))
            half = (h - pad) // 2
            for i, (key, text) in enumerate((("clip_prev", "◀ PREV"),
                                             ("clip_next", "NEXT ▶"))):
                self.add_button(page, (nav_x, y + i * (half + pad), nav_w,
                                       half),
                                f"layer{n}_{key}", addr[key].format(layer=n),
                                self.res_conn, color="panel", text=text,
                                text_size=11, constant_args=(1.0,))
            # Never a bypass button on any row; Side Audios has no CLEAR.
            if not layer.get("no_clear"):
                self.add_button(page, (clear_x, y, clear_w, h),
                                f"layer{n}_clear",
                                addr["layer_clear"].format(layer=n),
                                self.res_conn, color="panel", text="CLEAR",
                                text_size=11, constant_args=(1.0,))
            page.add(self.fader((opacity_x, y, opacity_w, h),
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

        # --- master column: master, saturation, blackout, tempo ---
        x = main_w + pad
        col_w = right_w - 2 * pad
        btn_h = 56
        sat_h = 64
        label_h = 22
        page.add(self.caption((x, pad, col_w, label_h), "MASTER / BLACKOUT",
                              12, "master"))
        tempo_y = height - pad - btn_h
        blackout_y = tempo_y - pad - btn_h
        sat_y = blackout_y - 2 * pad - sat_h
        master_top = pad + label_h + 2
        page.add(self.fader((x, master_top, col_w,
                             sat_y - label_h - 2 * pad - master_top), "master",
                            addr["master"], self.res_conn, color="master"))

        # Beside master: whole-output saturation, grey (B&W) to full colour.
        sat = show["saturation"]
        page.add(self.caption((x, sat_y - label_h - 2, col_w, label_h),
                              sat["label"], 11, "resolume"))
        self.banded_fader(page, (x, sat_y, col_w, sat_h), "res_saturation",
                          sat["address"], self.res_conn, outline="resolume",
                          band=lambda t: desaturate(self.colors["resolume"], t),
                          default=1.0, scale=(0.0, float(sat["top"])))

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

    # -- page 2: FX ------------------------------------------------------------

    def fx_page(self, width: int, height: int) -> Node:
        """Layers down, effects across, one drag-only dial per cell.

        The generic FX page's rules: no bypass buttons (dial to zero), wide
        gutters, relative response so a tap does nothing, and grabFocus so a
        drag never jumps to the neighbouring dial.
        """
        fx = self.spec["fx"]
        effects = fx["effects"]
        comp_sat = self.spec["show"]["saturation"]["address"]
        page = Node(GROUP, (0, 0, width, height), name="FX",
                    color=self.colors["accent"], background=False,
                    outline=False)
        pad = 8
        head_h = 24
        gutter = 140
        rows = [(f"layer{l['layer']}", l["name"], "resolume",
                 lambda e, n=l["layer"]: fx["layer_param"].format(
                     layer=n, fx=e["fx"], param=e["param"]))
                for l in self.spec["show"]["layers"]]
        rows.append(("comp", "COMPOSITION", "accent",
                     lambda e: fx["comp_param"].format(fx=e["fx"],
                                                       param=e["param"])))
        col_w = (width - gutter) // len(effects)
        row_h = (height - head_h) // len(rows)

        for c, e in enumerate(effects):
            page.add(self.caption((gutter + c * col_w, 0, col_w, head_h),
                                  e["name"], 14, "resolume"))
        for r, (key, caption, color, address) in enumerate(rows):
            y = head_h + r * row_h
            page.add(self.caption((pad, y, gutter - pad, row_h), caption, 13,
                                  color))
            for c, e in enumerate(effects):
                x = gutter + c * col_w
                path = address(e)
                if path == comp_sat:
                    # Owned by the SHOW page's saturation fader.
                    page.add(self.caption((x, y, col_w, row_h),
                                          "ON SHOW PAGE", 11, "text"))
                    continue
                size = min(col_w, row_h) - 2 * pad
                page.add(self.radial((x + (col_w - size) // 2,
                                      y + (row_h - size) // 2, size, size),
                                     f"{key}_{e['fx']}", path, self.res_conn,
                                     color="accent" if key == "comp"
                                     else "fx_low",
                                     script=self.fx_script,
                                     response=Response.RELATIVE))
        return page

    # -- page 3: TD ------------------------------------------------------------

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
        label_h = 22
        strip_fader_h = 60
        master_h = 2 * (label_h + strip_fader_h) + pad
        top_h = height - master_h - 3 * pad

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
        # The whole column below the header is the pad: the old Panorama
        # toggle that shared it (/td/toggle/4) is retired, on no page at all.
        pad_h = body_h - 24
        page.add(self.xy((px, body_y, pw, pad_h), "camera_orbit",
                         sw["pad"]["x"], sw["pad"]["y"], self.td_conn,
                         color="spiderweb"))
        page.add(self.caption((px, body_y + pad_h, pw, 24), sw["pad"]["label"],
                              12, "spiderweb"))

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

        # --- MASTER strip (pink): hue over a rainbow, saturation over grey
        # to pink, stacked full width. Both follow TD and the APC40.
        ms = td["master"]
        fw = width - 2 * pad
        y = top_h + 2 * pad
        hu, sa = ms["hue"], ms["saturation"]
        page.add(self.caption((pad, y, fw, label_h), hu["label"], 14, "hue"))
        y += label_h
        self.banded_fader(page, (pad, y, fw, strip_fader_h), "hue",
                          hu["address"], self.td_conn, outline="hue",
                          band=lambda t: colorsys.hsv_to_rgb(t, 0.75, 0.85)
                          + (1.0,))
        y += strip_fader_h + pad
        page.add(self.caption((pad, y, fw, label_h), sa["label"], 14, "hue"))
        y += label_h
        self.banded_fader(page, (pad, y, fw, strip_fader_h), "saturation",
                          sa["address"], self.td_conn, outline="hue",
                          band=lambda t: desaturate(self.colors["hue"], t),
                          default=float(sa.get("default", 1.0)))
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
                          (self.fx_page(w, page_h), "FX"),
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
