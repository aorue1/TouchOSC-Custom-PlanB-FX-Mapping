#!/usr/bin/env python3
"""Build the VJ control surface from spec/mapping.yaml.

    python3 tools/build_tosc.py                     # both orientations
    python3 tools/build_tosc.py -r portrait         # just one

A TouchOSC document has a single fixed size, so one file cannot reflow when
the iPad is rotated. Instead both orientations are generated from the same
spec: the pages rearrange themselves to suit the aspect ratio, and the OSC
addresses are identical, so the two files are interchangeable mid-set.
"""

from __future__ import annotations

import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
import vendor  # noqa: E402
from tosc import (BOX, BUTTON, FADER, GROUP, LABEL, PAGER, RADIAL, XY,  # noqa: E402
                  Node, OscMessage, Orientation, Outline, Raw, Response, Shape)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "mapping.yaml")
BUILD = os.path.join(ROOT, "build")

# FX controls colour themselves by value, interpolating between the three
# stops in the spec. Built per layout so the stops stay data, not code.
FX_COLOR_TEMPLATE = """
local low  = {{ {low} }}
local mid  = {{ {mid} }}
local high = {{ {high} }}

local function mix(a, b, t)
  return a + (b - a) * t
end

local function paint()
  local v = self.values.x
  local c1, c2, t
  if v < 0.5 then
    c1, c2, t = low, mid, v * 2
  else
    c1, c2, t = mid, high, (v - 0.5) * 2
  end
  self.color = Color(mix(c1[1], c2[1], t), mix(c1[2], c2[2], t),
                     mix(c1[3], c2[3], t), 1)
end

function init()
  paint()
end

function onValueChanged(key)
  if key == 'x' then paint() end
end
""".strip()


def fx_color_script(scale: dict) -> str:
    """Bake the spec's colour stops into the per-control repaint script."""
    def stop(key):
        return ", ".join(f"{float(c):.3f}" for c in scale[key][:3])
    return FX_COLOR_TEMPLATE.format(low=stop("low"), mid=stop("mid"),
                                    high=stop("high"))


def bake(script: str, **values) -> str:
    """Substitute @TOKEN@ placeholders in a Lua script.

    Not str.format: these scripts are full of Lua table braces, which format
    would try to read as fields of its own.
    """
    for key, value in values.items():
        text = value if isinstance(value, str) else f"{float(value):.2f}"
        script = script.replace(f"@{key.upper()}@", text)
    return script.strip()


# A numeric keypad, built here rather than vendored: the TextInput module is a
# full QWERTY keyboard, and for a BPM every key but the digits is in the way.
NUMPAD_SCRIPT = """
local caller = nil
local entry = ''
local display = self.children.dialog.children.display

local function refresh()
  display.values.text = (entry == '' and '0' or entry)
end

local handlers = {}

handlers.showNumPad = function(val)
  caller = val and val.callback or nil
  entry = (val and val.initial) and tostring(val.initial) or ''
  refresh()
  self.visible = true
end

handlers.key = function(ch)
  if ch == 'del' then
    entry = string.sub(entry, 1, -2)
  elseif ch == '.' then
    if not string.find(entry, '%.') then entry = entry .. '.' end
  elseif string.len(entry) < 6 then
    entry = entry .. ch
  end
  refresh()
end

handlers.ok = function()
  local n = tonumber(entry)
  self.visible = false
  if caller and n then caller:notify('numberEntered', n) end
end

handlers.cancel = function()
  self.visible = false
  if caller then caller:notify('numPadCanceled') end
end

function onReceiveNotify(key, val)
  local h = handlers[key]
  if h then h(val) end
end
"""

NUMPAD_KEY_SCRIPT = """
local KEY = '@KEY@'

function onValueChanged(key)
  if key == 'x' and self.values.x == 0 then
    self.parent.parent:notify('key', KEY)
  end
end
"""

NUMPAD_ACTION_SCRIPT = """
local ACTION = '@ACTION@'

function onValueChanged(key)
  if key == 'x' and self.values.x == 0 then
    self.parent.parent:notify(ACTION)
  end
end
"""

# The dim pane is one control, so it notifies the pad directly.
NUMPAD_PANE_SCRIPT = """
function onValueChanged(key)
  if key == 'x' and self.values.x == 0 then
    self.parent:notify('cancel')
  end
end
"""

# BPM field. The hidden fader holds the value and carries the OSC; the label
# reads it back, the nudge buttons step it, and the display can be tapped to
# type an exact number through the vendored keyboard -- tapping a tempo is not
# always realistic.
BPM_HELPERS = """
local MIN, MAX = @MIN@, @MAX@
local f = self.parent.children.bpm_value

local function bpm()
  return MIN + f.values.x * (MAX - MIN)
end

local function setBpm(v)
  if v < MIN then v = MIN elseif v > MAX then v = MAX end
  f.values.x = (v - MIN) / (MAX - MIN)
end
"""

BPM_EDIT_SCRIPT = BPM_HELPERS + """
function onValueChanged(key)
  -- On release: the keyboard's overlay would swallow a touch still held.
  if key == 'x' and self.values.x == 0 then
    root.children.NumPad:notify('showNumPad', {
      callback = self,
      initial = string.format('%.1f', bpm())
    })
  end
end

function onReceiveNotify(key, val)
  if key == 'numberEntered' then
    setBpm(val)
  end
end
"""

BPM_NUDGE_SCRIPT = BPM_HELPERS + """
local STEP = @STEP@
local dir = string.find(self.name, 'plus') and 1 or -1

function onValueChanged(key)
  if key == 'x' and self.values.x == 0 then
    setBpm(bpm() + dir * STEP)
  end
end
"""

BPM_DISPLAY_SCRIPT = BPM_HELPERS + """
function update()
  self.values.text = string.format('%.1f BPM', bpm())
end
"""

# Opens the vendored ColorPicker and writes the result into the R/G/B faders
# beside it, which are what actually send the OSC.
SWATCH_SCRIPT = """
local base = self.name:gsub('_swatch$', '')
local sib = self.parent.children
local chip = sib[base .. '_chip']

-- Opens on RELEASE, not press. The picker's overlay hides itself on any
-- touch, so opening it under a finger that is still down closes it again on
-- the spot -- which looks like the dialog flickering.
function onValueChanged(key)
  if key == 'x' and self.values.x == 0 then
    root.children.ColorPicker:notify('pickColor', {
      callback = self,
      initial = chip.color
    })
  end
end

function onReceiveNotify(key, val)
  if key == 'colorPicked' then
    chip.color = val
    sib[base .. '_r'].values.x = val.r
    sib[base .. '_g'].values.x = val.g
    sib[base .. '_b'].values.x = val.b
  end
end
""".strip()

# Momentary vs latching, in TouchOSC's buttonType encoding.
MOMENTARY, TOGGLE = 0, 1
# Smallest comfortable touch target; tools/verify.py enforces the same number.
MIN_TOUCH = 28


def load_spec(path: str = SPEC) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


class Builder:
    def __init__(self, spec: dict, orientation: str = "landscape"):
        self.spec = spec
        self.orientation = orientation
        size = spec["layout"]["orientations"][orientation]
        self.width, self.height = size["width"], size["height"]
        self.portrait = self.height > self.width
        self.colors = {k: tuple(v) for k, v in spec["colors"].items()}
        self.fx_script = fx_color_script(spec["fx_scale"])
        self.colors["fx_low"] = tuple(spec["fx_scale"]["low"])
        self.res_conn = tosc.connections(spec["connections"]["resolume"]["slot"])
        self.td_conn = tosc.connections(spec["connections"]["touchdesigner"]["slot"])

    # -- small control factories ------------------------------------------
    def label(self, frame, text, size=14, color="text") -> Node:
        return Node(LABEL, frame, name=f"lbl_{text}", text=text, text_size=size,
                    text_color=self.colors[color], background=False,
                    outline=False, interactive=False)

    def name_feed(self, label: Node, address: str) -> Node:
        """Let a label take its caption from the host, if the host sends one.

        The label keeps whatever it was built with until a message arrives, so
        an address that turns out to be wrong just leaves the number showing.
        """
        if self.spec.get("feedback", {}).get("enabled"):
            label.messages.append(OscMessage(address, self.res_conn,
                                             send_value=False, send=False,
                                             receive=True, receive_key="text",
                                             conversion="STRING"))
        return label

    def add_button(self, parent: Node, frame, name, path, conns, *, toggle=False,
                   color="panel", text="", text_size=14, constant_args=()) -> Node:
        """Place a button and, if it has a caption, a label on top of it.

        A TouchOSC BUTTON draws no text of its own, so the caption is a
        separate non-interactive LABEL sharing the button's frame — added
        after the button so it draws over it, and non-interactive so touches
        fall through to the button underneath.
        """
        btn = self.button(frame, name, path, conns, toggle=toggle, color=color,
                          constant_args=constant_args)
        parent.add(btn)
        if text:
            parent.add(self.label(frame, text, size=text_size))
        return btn

    def button(self, frame, name, path, conns, *, toggle=False, color="panel",
               constant_args=()) -> Node:
        btn = Node(BUTTON, frame, name=name, color=self.colors[color],
                   button_type=TOGGLE if toggle else MOMENTARY)
        btn.messages.append(OscMessage(path, conns, send_value=not constant_args,
                                       constant_args=constant_args,
                                       trigger="ANY" if toggle else "RISE"))
        return btn

    def fader(self, frame, name, path, conns, *, horizontal=False, color="panel",
              script="", response=None) -> Node:
        fdr = Node(FADER, frame, name=name, color=self.colors[color], script=script,
                   response=response,
                   orientation=Orientation.EAST if horizontal else Orientation.NORTH)
        fdr.messages.append(OscMessage(path, conns))
        return fdr

    def radial(self, frame, name, path, conns, color="panel", script="",
               response=None) -> Node:
        knob = Node(RADIAL, frame, name=name, color=self.colors[color],
                    script=script, response=response)
        knob.messages.append(OscMessage(path, conns))
        return knob

    def xy(self, frame, name, path_x, path_y, conns, color="td") -> Node:
        pad = Node(XY, frame, name=name, color=self.colors[color])
        pad.messages.append(OscMessage(path_x, conns))
        pad.messages.append(OscMessage(path_y, conns))
        return pad

    # -- global strip ------------------------------------------------------
    def brand_mark(self, parent: Node, x: int, y: int, height: int) -> int:
        """Wordmark in the top-left. Returns its right edge.

        Text only: TouchOSC loads no images, and a mark drawn from primitives
        read as a pseudo-logo rather than the real one.
        """
        brand = self.spec["branding"]
        width = 0 if self.portrait else 150
        if width:
            parent.add(Node(LABEL, (x, y + 8, width, height - 16),
                            name="brand_wordmark", text=brand["wordmark"],
                            text_size=20, text_color=self.colors["brand"],
                            background=False, outline=False, interactive=False))
        return x + width

    def global_strip(self, width: int, height: int) -> Node:
        res, td = self.spec["resolume"], self.spec["touchdesigner"]
        strip = Node(GROUP, (0, 0, width, height), name="globals",
                     color=self.colors["bg"], outline=False)
        pad = 8
        btn_w = 150 if self.portrait else 178

        # Portrait is too narrow for the wordmark, so the badge stands alone.
        title_w = self.brand_mark(strip, 12, 0, height)

        blackout_frame = (width - btn_w - pad, 8, btn_w, height - 16)
        blackout = Node(BUTTON, blackout_frame, name="blackout",
                        color=self.colors["danger"], button_type=TOGGLE)
        blackout.messages.append(OscMessage(res["master"], self.res_conn,
                                            send_value=False, constant_args=(0.0,),
                                            trigger="RISE"))
        blackout.messages.append(OscMessage(td["blackout"], self.td_conn))
        strip.add(blackout)
        strip.add(self.label(blackout_frame, "BLACKOUT", size=15))

        self.add_button(strip, (width - 2 * btn_w - 2 * pad, 8, btn_w, height - 16),
                        "tap", res["tempo_tap"], self.res_conn,
                        color="accent", text="TAP", text_size=16,
                        constant_args=(1.0,))

        fader_x = title_w + 2 * pad
        fader_w = width - 2 * btn_w - 3 * pad - fader_x
        strip.add(self.fader((fader_x, 14, fader_w, height - 28), "master_global",
                             res["master"], self.res_conn, horizontal=True,
                             color="resolume"))
        return strip

    # -- pages -------------------------------------------------------------
    def resolume_page(self, width: int, height: int) -> Node:
        """Layer columns over a two-row banked clip grid; master on the right.

        TouchOSC has no scrolling control, so clips are reached by banking.
        Two rows of tabs rather than one: the first picks a group, the second
        a bank within it, so 4 rows of clip buttons still reach 32 clips per
        layer. Fewer rows on screen leaves the opacity faders long, which is
        what they are actually used for during a set.

        Only the clip buttons move when banking — the nav row, state strip and
        faders stay put, so nothing shifts under your hand.
        """
        res, grid = self.spec["resolume"], self.spec["grid"]
        fb = self.spec.get("feedback", {})
        layers, clips = grid["layers"], grid["clips"]
        banks, groups = grid["banks"], grid["bank_groups"]
        page = Node(GROUP, (0, 0, width, height), name="RESOLUME",
                    color=self.colors["resolume"], background=False, outline=False)

        col_w = width // (layers + 1)
        grid_w = layers * col_w
        pad = 6
        header_h = 26
        nav_h = 44
        strip_h = 44
        tab_h = grid["bank_tabbar"]
        clip_h = grid["clip_height"]
        clip_area = clips * clip_h + 2 * tab_h
        fader_y = header_h + clip_area + nav_h + strip_h + 3 * pad
        fader_h = height - fader_y - pad
        per_bank = clips
        per_group = per_bank * banks

        for li in range(layers):
            header = self.label((li * col_w, 2, col_w, header_h),
                                f"LAYER {li + 1}", size=15, color="resolume")
            header.name = f"L{li + 1}_name"
            page.add(self.name_feed(header, fb["layer_name"].format(layer=li + 1)))

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

        outer = tabs("clipgroups", (0, header_h, grid_w, clip_area), 12)
        group_h = clip_area - tab_h
        bank_h = group_h - tab_h
        for g in range(groups):
            g_first = g * per_group + 1
            g_page = Node(GROUP, (0, tab_h, grid_w, group_h),
                          name=f"group{g + 1}", background=False, outline=False,
                          tab_label=f"{g_first}-{g_first + per_group - 1}")
            inner = tabs(f"banks{g + 1}", (0, 0, grid_w, group_h), 11)
            for b in range(banks):
                b_first = g_first + b * per_bank
                bank = Node(GROUP, (0, tab_h, grid_w, bank_h),
                            name=f"g{g + 1}bank{b + 1}", background=False,
                            outline=False,
                            tab_label=f"{b_first}-{b_first + per_bank - 1}")
                for li in range(layers):
                    x = li * col_w
                    for ci in range(clips):
                        clip = b_first + ci
                        frame = (x + pad, ci * clip_h, col_w - 2 * pad,
                                 clip_h - pad)
                        self.add_button(
                            bank, frame, f"L{li + 1}C{clip}",
                            res["clip_connect"].format(layer=li + 1, clip=clip),
                            self.res_conn, color="panel", constant_args=(1.0,))
                        caption = self.label(frame, str(clip), size=13)
                        caption.name = f"L{li + 1}C{clip}_name"
                        self.name_feed(caption, fb["clip_name"].format(
                            layer=li + 1, clip=clip))
                        bank.add(caption)
                inner.add(bank)
            g_page.add(inner)
            outer.add(g_page)
        page.add(outer)

        # --- per-layer nav, state strip and opacity ---
        nav_y = header_h + clip_area + pad
        strip_y = nav_y + nav_h
        for li in range(layers):
            layer = li + 1
            x = li * col_w
            half = (col_w - 3 * pad) // 2
            for i, (key, text) in enumerate((("clip_prev", "PREV"),
                                             ("clip_next", "NEXT"))):
                self.add_button(page, (x + pad + i * (half + pad), nav_y,
                                       half, nav_h - pad),
                                f"L{layer}_{text}", res[key].format(layer=layer),
                                self.res_conn, color="panel", text=text,
                                text_size=12, constant_args=(1.0,))

            btn_w = (col_w - 4 * pad) // 3
            for i, (key, text) in enumerate((
                ("layer_bypass", "BYP"), ("layer_solo", "SOLO"), ("layer_clear", "CLR"),
            )):
                toggle = key != "layer_clear"
                self.add_button(
                    page, (x + pad + i * (btn_w + pad), strip_y, btn_w, strip_h - pad),
                    f"L{layer}_{text}", res[key].format(layer=layer), self.res_conn,
                    toggle=toggle, color="panel", text=text, text_size=11,
                    constant_args=() if toggle else (1.0,))

            page.add(self.fader((x + pad, fader_y, col_w - 2 * pad, fader_h),
                                f"L{layer}_opacity",
                                res["layer_opacity"].format(layer=layer),
                                self.res_conn, color="resolume"))

        # --- master column: speed, BPM, colour, tempo buttons ---
        x = layers * col_w
        inner_w = col_w - 2 * pad
        page.add(self.label((x, 2, col_w, header_h), "MASTER", size=15, color="accent"))
        y = header_h + pad
        page.add(self.label((x + pad, y, inner_w, 22), "SPEED", size=12))
        buttons_top = height - 2 * 52 - pad
        speed_h = int(height * 0.26)
        page.add(self.fader((x + pad, y + 22, inner_w, speed_h),
                            "speed", res["speed"], self.res_conn, color="accent"))

        y = y + 22 + speed_h + pad
        bpm_h = 96
        self.bpm_field(page, (x + pad, y, inner_w, bpm_h))
        y += bpm_h + pad

        self.color_swatch(page, (x + pad, y, inner_w, buttons_top - y - pad),
                          "resolume", self.spec["colorpicker"]["resolume"],
                          self.res_conn, "resolume")
        self.add_button(page, (x + pad, buttons_top + 4, inner_w, 48),
                        "resync", res["tempo_resync"], self.res_conn,
                        color="accent", text="RESYNC", text_size=12,
                        constant_args=(1.0,))
        self.add_button(page, (x + pad, buttons_top + 56, inner_w, 48),
                        "tap_page", res["tempo_tap"], self.res_conn,
                        color="accent", text="TAP", text_size=15,
                        constant_args=(1.0,))
        return page

    def fx_page(self, width: int, height: int) -> Node:
        """Layers down, effects across, one dial per cell and nothing else.

        The list is short on purpose — only the effects reached for in a set —
        and there are no bypass buttons: dialling to zero is the bypass, so the
        whole cell belongs to the dial. Dials respond to drag rather than to
        the touch position, so a mistap does nothing at all, and they hold the
        touch once a drag starts, so sliding past a dial's edge does not hand
        the gesture to its neighbour.
        """
        res, grid = self.spec["resolume"], self.spec["grid"]
        layers = grid["layers"]
        fx_list = res["fx_names"][: grid["fx_params"]]
        with_comp = grid.get("fx_composition", False)
        page = Node(GROUP, (0, 0, width, height), name="FX",
                    color=self.colors["accent"], background=False, outline=False)

        # Generous gutters: a finger that lands off-target hits dead space
        # rather than the neighbouring effect.
        pad = 8
        head_h = 22
        gutter = 72
        response = (Response.RELATIVE if grid.get("fx_relative", True)
                    else Response.ABSOLUTE)

        rows = layers + (1 if with_comp else 0)
        col_w = (width - gutter) // len(fx_list)
        row_h = (height - head_h) // rows

        def target(r):
            """(caption, parameter address) for row r."""
            if with_comp and r == layers:
                return ("COMP", res["fx_comp_param"])
            return (f"L{r + 1}", res["fx_param"])

        for c, fx in enumerate(fx_list):
            page.add(self.label((gutter + c * col_w, 0, col_w, head_h),
                                fx["name"], size=14, color="resolume"))

        for r in range(rows):
            caption, param_addr = target(r)
            y = head_h + r * row_h
            page.add(self.label((0, y + row_h // 3, gutter, 26), caption,
                                size=15,
                                color="accent" if caption == "COMP" else "resolume"))
            for c, fx in enumerate(fx_list):
                x = gutter + c * col_w
                cell_w = col_w - 2 * pad
                cell_h = row_h - 2 * pad
                name = f"{caption}_{fx['fx']}"
                addr = param_addr.format(layer=r + 1, fx=fx["fx"],
                                         param=fx["param"])
                accent = "accent" if caption == "COMP" else "fx_low"

                # No bypass button: dialling to zero is the bypass, and the
                # whole cell goes to the dial instead.
                size = min(cell_w, cell_h)
                page.add(self.radial((x + pad + (cell_w - size) // 2,
                                      y + pad + (cell_h - size) // 2,
                                      size, size), name, addr,
                                     self.res_conn, color=accent,
                                     script=self.fx_script, response=response))
        return page

    def td_page(self, width: int, height: int) -> Node:
        """Param bank and XY pads.

        Landscape puts them side by side; portrait stacks the bank above the
        pads, which suits the taller aspect better than two narrow halves.
        """
        td, grid = self.spec["touchdesigner"], self.spec["grid"]
        page = Node(GROUP, (0, 0, width, height), name="TOUCHDESIGNER",
                    color=self.colors["td"], background=False, outline=False)
        pad = 8
        n = grid["td_faders"]

        if self.portrait:
            bank = (0, 0, width, int(height * 0.58))
            side = (0, bank[3], width, height - bank[3])
        else:
            bank = (0, 0, width // 2, height)
            side = (width // 2, 0, width - width // 2, height)

        # --- fader bank with toggles and triggers beneath ---
        bx, by, bw, bh = bank
        col_w = bw // n
        rows_h = 2 * 48 + 4 + 24            # toggle + trigger + label
        fader_h = bh - rows_h - 26
        page.add(self.label((bx, by, bw, 24), "PARAM BANK", size=14, color="td"))
        for i in range(n):
            x = bx + i * col_w
            page.add(self.fader((x + pad, by + 26, col_w - 2 * pad, fader_h),
                                f"td_fader_{i + 1}", td["fader"].format(n=i + 1),
                                self.td_conn, color="td"))
            page.add(self.label((x, by + 26 + fader_h, col_w, 22), str(i + 1), size=12))
        tog_y = by + 26 + fader_h + 24
        for i in range(grid["td_toggles"]):
            x = bx + i * col_w
            self.add_button(page, (x + pad, tog_y, col_w - 2 * pad, 48),
                            f"td_toggle_{i + 1}", td["toggle"].format(n=i + 1),
                            self.td_conn, toggle=True, color="td", text=str(i + 1))
            self.add_button(page, (x + pad, tog_y + 52, col_w - 2 * pad, 48),
                            f"td_trigger_{i + 1}", td["trigger"].format(n=i + 1),
                            self.td_conn, color="panel", text=f"T{i + 1}",
                            text_size=12, constant_args=(1.0,))

        # --- XY pads plus intensity and scene ---
        sx, sy, sw, sh = side
        page.add(self.label((sx, sy, sw, 24), "XY / SCENE", size=14, color="td"))
        pads = grid["td_pads"]
        strips_h = 2 * 56
        colour_h = 164
        pad_w = (sw - (pads + 1) * pad) // pads
        pad_h = sh - strips_h - colour_h - 26 - 24
        for i in range(pads):
            x = sx + pad + i * (pad_w + pad)
            page.add(self.xy((x, sy + 26, pad_w, pad_h), f"td_pad_{i + 1}",
                             td["pad"].format(n=i + 1) + "/x",
                             td["pad"].format(n=i + 1) + "/y", self.td_conn))
            page.add(self.label((x, sy + 26 + pad_h, pad_w, 22), f"PAD {i + 1}", size=12))

        y = sy + 26 + pad_h + 24
        self.color_swatch(page, (sx + pad, y, sw - 2 * pad, colour_h - pad),
                          "touchdesigner", self.spec["colorpicker"]["touchdesigner"],
                          self.td_conn, "td")
        y += colour_h
        for label_text, path, name in (("INTENSITY", td["intensity"], "td_intensity"),
                                       ("SCENE", td["scene"], "td_scene")):
            page.add(self.label((sx + pad, y, 110, 24), label_text, size=12))
            page.add(self.fader((sx + 120, y, sw - 130 - pad, 48), name, path,
                                self.td_conn, horizontal=True, color="td"))
            y += 56
        return page

    def num_pad(self, width: int, height: int) -> Node:
        """A modal numeric keypad: digits, a dot, backspace, cancel and OK.

        Same shape as the vendored dialogs — a hidden overlay covering the
        surface, shown when notified — but built here, because the vendored
        keyboard is a full QWERTY and for a BPM every key but the digits is in
        the way.

            NumPad:notify('showNumPad', { callback = aControl, initial = '128' })

        The caller is notified with `numberEntered` and a number, or
        `numPadCanceled`.
        """
        pad = 15
        key_w, key_h, gap = 90, 70, 10
        dlg_w = 3 * key_w + 2 * gap + 2 * pad
        dlg_h = 60 + 4 * key_h + 3 * gap + 50 + 4 * pad
        dx, dy = (width - dlg_w) // 2, (height - dlg_h) // 2

        overlay = Node(GROUP, (0, 0, width, height), name="NumPad",
                       background=False, outline=False, visible=False,
                       script=NUMPAD_SCRIPT)
        # Tapping outside the dialog cancels, like the vendored dialogs do.
        overlay.add(Node(BUTTON, (0, 0, width, height), name="pane",
                         color=(0.0, 0.0, 0.0, 0.7), button_type=MOMENTARY,
                         background=True, outline=False,
                         script=NUMPAD_PANE_SCRIPT))

        dialog = Node(GROUP, (dx, dy, dlg_w, dlg_h), name="dialog",
                      color=self.colors["panel"], background=True, outline=True)
        display = Node(LABEL, (pad, pad, dlg_w - 2 * pad, 60), name="display",
                       text="0", text_size=30, text_color=self.colors["text"],
                       background=True, outline=True, interactive=False,
                       color=self.colors["bg"])
        dialog.add(display)

        keys = (("7", "8", "9"), ("4", "5", "6"), ("1", "2", "3"),
                (".", "0", "del"))
        for r, row in enumerate(keys):
            for c, key in enumerate(row):
                kx = pad + c * (key_w + gap)
                ky = pad + 60 + pad + r * (key_h + gap)
                dialog.add(Node(BUTTON, (kx, ky, key_w, key_h),
                                name=f"key_{key}", color=self.colors["panel"],
                                button_type=MOMENTARY,
                                script=bake(NUMPAD_KEY_SCRIPT, key=key)))
                dialog.add(self.label((kx, ky, key_w, key_h),
                                      "\u232b" if key == "del" else key, size=24))

        act_y = dlg_h - pad - 50
        act_w = (dlg_w - 2 * pad - gap) // 2
        for i, (action, caption, colour) in enumerate(
                (("cancel", "CANCEL", "panel"), ("ok", "OK", "accent"))):
            ax = pad + i * (act_w + gap)
            dialog.add(Node(BUTTON, (ax, act_y, act_w, 50), name=f"act_{action}",
                            color=self.colors[colour], button_type=MOMENTARY,
                            script=bake(NUMPAD_ACTION_SCRIPT, action=action)))
            dialog.add(self.label((ax, act_y, act_w, 50), caption, size=16))
        overlay.add(dialog)
        return overlay

    def bpm_field(self, parent: Node, frame) -> Node:
        """Editable BPM: type it, nudge it, or leave the tap button to it.

        The value lives in a hidden fader, which is also what sends the OSC.
        The display reads that fader back each frame, so typing, nudging and
        anything Resolume sends all show up the same way.
        """
        x, y, w, h = frame
        tempo = self.spec["tempo"]
        fmt = dict(min=float(tempo["min_bpm"]), max=float(tempo["max_bpm"]),
                   step=float(tempo["nudge"]))
        span = fmt["max"] - fmt["min"]
        start = (float(tempo["default_bpm"]) - fmt["min"]) / span

        group = Node(GROUP, frame, name="bpm", background=False, outline=False)
        gap = 4
        nudge_h = min(44, (h - gap) // 2)
        display_h = h - nudge_h - gap

        group.add(Node(BOX, (0, 0, w, display_h), name="bpm_chip",
                       color=self.colors["panel"], shape=Shape.RECTANGLE,
                       background=True, outline=True, interactive=False))
        group.add(Node(BUTTON, (0, 0, w, display_h), name="bpm_edit",
                       color=self.colors["accent"], button_type=MOMENTARY,
                       background=False, outline=False,
                       script=bake(BPM_EDIT_SCRIPT, **fmt)))
        display = self.label((0, 0, w, display_h), "BPM", size=16,
                             color="accent")
        display.name = "bpm_display"
        display.script = bake(BPM_DISPLAY_SCRIPT, **fmt)
        group.add(display)

        half = (w - gap) // 2
        for i, (suffix, caption) in enumerate((("minus", "-"), ("plus", "+"))):
            bx = i * (half + gap)
            group.add(Node(BUTTON, (bx, display_h + gap, half, nudge_h),
                           name=f"bpm_{suffix}", color=self.colors["panel"],
                           button_type=MOMENTARY,
                           script=bake(BPM_NUDGE_SCRIPT, **fmt)))
            group.add(self.label((bx, display_h + gap, half, nudge_h),
                                 caption, size=20))

        group.add(Node(FADER, (0, 0, w, display_h), name="bpm_value",
                       color=self.colors["accent"], visible=False,
                       value_default=start,
                       messages=[OscMessage(self.spec["resolume"]["tempo"],
                                            self.res_conn)]))
        parent.add(group)
        return group

    def color_swatch(self, parent: Node, frame, name: str, addrs: dict,
                     conns: str, accent: str) -> Node:
        """A swatch button that opens the ColorPicker.

        The three RGB faders behind it are hidden: the picker is the interface,
        and a set of sliders saying the same thing twice is just clutter. They
        remain because they are what sends the OSC — the vendored component
        sends none, and TouchOSC's scripting has no OSC send — so the callback
        writes into them and their own messages go out as usual.
        """
        x, y, w, h = frame
        group = Node(GROUP, frame, name=f"{name}_color", background=False,
                     outline=False)

        # The chip shows the colour; the button on top of it only catches the
        # tap. A BUTTON draws its own fill at partial opacity while idle, so
        # using one as the swatch shows a washed-out version of the colour --
        # misleading when the whole point is to see what you are sending.
        group.add(Node(BOX, (0, 0, w, h), name=f"{name}_chip",
                       color=self.colors[accent], shape=Shape.RECTANGLE,
                       background=True, outline=True, interactive=False))
        group.add(Node(BUTTON, (0, 0, w, h), name=f"{name}_swatch",
                       color=self.colors[accent], button_type=MOMENTARY,
                       background=False, outline=False, script=SWATCH_SCRIPT))
        group.add(self.label((0, 0, w, h), "COLOUR", size=13))

        for chan in ("red", "green", "blue"):
            group.add(Node(FADER, (0, 0, w, h), name=f"{name}_{chan[0]}",
                           color=self.colors[accent], visible=False,
                           messages=[OscMessage(addrs[chan], conns)]))
        parent.add(group)
        return group

    # -- assembly ----------------------------------------------------------
    def build(self) -> Node:
        layout = self.spec["layout"]
        w, h = self.width, self.height
        strip_h = layout["tabbar_height"]

        root = Node(GROUP, (0, 0, w, h), name="root", color=self.colors["bg"],
                    outline=False)
        root.add(self.global_strip(w, strip_h))

        pager_h = h - strip_h
        page_h = pager_h - layout["tabbar_height"]
        pager = Node(PAGER, (0, strip_h, w, pager_h), name="views",
                     color=self.colors["panel"],
                     background=False, outline=False,
                     extra_props={
                         "tabbar": ("b", 1),
                         "tabbarSize": ("i", layout["tabbar_height"]),
                         "tabbarDoubleTap": ("b", 0),
                         "tabLabels": ("b", 1),
                         "textSizeOff": ("i", 15),
                         "textSizeOn": ("i", 15),
                     })
        tab_h = layout["tabbar_height"]
        pages = ((self.resolume_page(w, page_h), "RESOLUME"),
                 (self.fx_page(w, page_h), "FX"),
                 (self.td_page(w, page_h), "TOUCHDESIGNER"))
        for page, tab in pages:
            # Child coordinates stay relative to the page, so only the page's
            # own frame moves down past the tab bar.
            page.frame = (0, tab_h, w, page_h)
            page.tab_label = tab
            pager.add(page)
        root.add(pager)
        # The picker is a modal overlay: it covers the surface so its pane can
        # dim everything behind the dialog, and must come last so it draws on
        # top of the pages. It ships hidden and shows itself when notified.
        root.add(Raw(vendor.color_picker(w, h)))
        root.add(self.num_pad(w, h))
        return root


def build_one(spec: dict, orientation: str, outdir: str) -> str:
    root = Builder(spec, orientation).build()
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"vj-control-{orientation}.tosc")
    tosc.write(root, out, os.path.splitext(out)[0] + ".xml")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-s", "--spec", default=SPEC)
    ap.add_argument("-d", "--outdir", default=BUILD)
    ap.add_argument("-r", "--orientation", choices=("landscape", "portrait", "both"),
                    default="both")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    wanted = (["landscape", "portrait"] if args.orientation == "both"
              else [args.orientation])
    for orientation in wanted:
        out = build_one(spec, orientation, args.outdir)
        print(f"wrote {out}")
        print(f"wrote {os.path.splitext(out)[0] + '.xml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
