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
                  Node, OscMessage, Orientation, Outline, Raw, Shape)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "mapping.yaml")
BUILD = os.path.join(ROOT, "build")

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

    def fader(self, frame, name, path, conns, *, horizontal=False, color="panel") -> Node:
        fdr = Node(FADER, frame, name=name, color=self.colors[color],
                   orientation=Orientation.EAST if horizontal else Orientation.NORTH)
        fdr.messages.append(OscMessage(path, conns))
        return fdr

    def radial(self, frame, name, path, conns, color="panel") -> Node:
        knob = Node(RADIAL, frame, name=name, color=self.colors[color])
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
        """Layer columns with a banked clip grid; master column on the right.

        TouchOSC has no scrolling control, so more clips than fit on screen are
        reached by banking: the clip grid lives in its own pager whose tabs are
        clip ranges (1-8, 9-16, ...). Banking moves every layer's column at
        once, and only the clip buttons move — opacity, bypass and the nav row
        stay put, so the controls you hold during a set never shift under you.
        """
        res, grid = self.spec["resolume"], self.spec["grid"]
        fb = self.spec.get("feedback", {})
        layers, clips, banks = grid["layers"], grid["clips"], grid["banks"]
        page = Node(GROUP, (0, 0, width, height), name="RESOLUME",
                    color=self.colors["resolume"], background=False, outline=False)

        col_w = width // (layers + 1)
        grid_w = layers * col_w
        pad = 6
        header_h = 26
        nav_h = 44
        strip_h = 44
        fader_h = 200 if self.portrait else 150
        bank_tab_h = grid["bank_tabbar"]
        clip_area = height - header_h - nav_h - strip_h - fader_h - 5 * pad

        for li in range(layers):
            header = self.label((li * col_w, 2, col_w, header_h),
                                f"LAYER {li + 1}", size=15, color="resolume")
            header.name = f"L{li + 1}_name"
            page.add(self.name_feed(header, fb["layer_name"].format(layer=li + 1)))

        # --- banked clip grid ---
        bank_pager = Node(PAGER, (0, header_h, grid_w, clip_area),
                          name="clipbanks", color=self.colors["panel"],
                          background=False, outline=False,
                          extra_props={
                              "tabbar": ("b", 1),
                              "tabbarSize": ("i", bank_tab_h),
                              "tabbarDoubleTap": ("b", 0),
                              "tabLabels": ("b", 1),
                              "textSizeOff": ("i", 12),
                              "textSizeOn": ("i", 12),
                          })
        bank_h = clip_area - bank_tab_h
        clip_h = bank_h // clips
        for b in range(banks):
            first = b * clips + 1
            bank = Node(GROUP, (0, bank_tab_h, grid_w, bank_h),
                        name=f"bank{b + 1}", color=self.colors["bg"],
                        background=False, outline=False,
                        tab_label=f"{first}-{first + clips - 1}")
            for li in range(layers):
                x = li * col_w
                for ci in range(clips):
                    clip = first + ci
                    frame = (x + pad, ci * clip_h, col_w - 2 * pad, clip_h - pad)
                    self.add_button(
                        bank, frame, f"L{li + 1}C{clip}",
                        res["clip_connect"].format(layer=li + 1, clip=clip),
                        self.res_conn, color="panel", constant_args=(1.0,))
                    caption = self.label(frame, str(clip), size=13)
                    caption.name = f"L{li + 1}C{clip}_name"
                    self.name_feed(caption, fb["clip_name"].format(
                        layer=li + 1, clip=clip))
                    bank.add(caption)
            bank_pager.add(bank)
        page.add(bank_pager)

        # --- per-layer nav, state strip and opacity ---
        nav_y = header_h + clip_area + pad
        strip_y = nav_y + nav_h
        fader_y = strip_y + strip_h
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

            page.add(self.fader((x + pad, fader_y, col_w - 2 * pad, fader_h - pad),
                                f"L{layer}_opacity",
                                res["layer_opacity"].format(layer=layer),
                                self.res_conn, color="resolume"))

        # --- master column ---
        x = layers * col_w
        page.add(self.label((x, 2, col_w, header_h), "MASTER", size=15, color="accent"))
        y = header_h + pad
        page.add(self.label((x + pad, y, col_w - 2 * pad, 22), "SPEED", size=12))
        fader_bottom = height - 2 * 52 - pad
        speed_h = min(fader_bottom - y - 22, int(height * 0.34))
        page.add(self.fader((x + pad, y + 22, col_w - 2 * pad, speed_h),
                            "speed", res["speed"], self.res_conn, color="accent"))

        colour_y = y + 22 + speed_h + pad
        self.color_swatch(page, (x + pad, colour_y, col_w - 2 * pad,
                                 fader_bottom - colour_y - pad),
                          "resolume", self.spec["colorpicker"]["resolume"],
                          self.res_conn, "resolume")
        self.add_button(page, (x + pad, fader_bottom + 4, col_w - 2 * pad, 48),
                        "resync", res["tempo_resync"], self.res_conn,
                        color="accent", text="RESYNC", text_size=12,
                        constant_args=(1.0,))
        self.add_button(page, (x + pad, fader_bottom + 56, col_w - 2 * pad, 48),
                        "tap_page", res["tempo_tap"], self.res_conn,
                        color="accent", text="TAP", text_size=15,
                        constant_args=(1.0,))
        return page

    def fx_page(self, width: int, height: int) -> Node:
        """Knob matrix of effects against layers.

        Landscape runs effects across and layers down; portrait transposes so
        the knobs stay roughly square instead of stretching into thin columns.
        """
        res, grid = self.spec["resolume"], self.spec["grid"]
        layers = grid["layers"]
        fx_list = res["fx_names"][: grid["fx_params"]]
        page = Node(GROUP, (0, 0, width, height), name="FX",
                    color=self.colors["accent"], background=False, outline=False)

        pad = 6
        head_h = 22
        byp_h = 32
        gutter = 70 if self.portrait else 90

        # cols x rows: effects across in landscape, layers across in portrait.
        across = layers if self.portrait else len(fx_list)
        down = len(fx_list) if self.portrait else layers
        col_w = (width - gutter) // across
        row_h = (height - head_h) // down

        def across_title(i):
            return f"L{i + 1}" if self.portrait else fx_list[i]["name"]

        def down_title(i):
            return fx_list[i]["name"] if self.portrait else f"L{i + 1}"

        for i in range(across):
            page.add(self.label((gutter + i * col_w, 0, col_w, head_h), across_title(i),
                                size=12, color="resolume"))

        for r in range(down):
            y = head_h + r * row_h
            page.add(self.label((0, y + row_h // 3, gutter, 24), down_title(r),
                                size=13, color="resolume"))
            for c in range(across):
                layer = (c if self.portrait else r) + 1
                fx = fx_list[r if self.portrait else c]
                x = gutter + c * col_w
                cell_w = col_w - 2 * pad
                knob_h = row_h - 2 * pad - byp_h - 2
                addr = res["fx_param"].format(layer=layer, fx=fx["fx"],
                                              param=fx["param"])
                name = f"L{layer}_{fx['fx']}"
                if cell_w > knob_h * 1.4:
                    # A wide, short cell (portrait) makes a poor dial; a
                    # horizontal fader uses the width and reads at a glance.
                    page.add(self.fader((x + pad, y + pad, cell_w, knob_h), name,
                                        addr, self.res_conn, horizontal=True,
                                        color="panel"))
                else:
                    # Keep dials circular: square them and centre in the cell.
                    size = min(cell_w, knob_h)
                    page.add(self.radial((x + pad + (cell_w - size) // 2,
                                          y + pad + (knob_h - size) // 2,
                                          size, size), name, addr,
                                         self.res_conn, color="panel"))
                self.add_button(page, (x + pad, y + pad + knob_h + 2,
                                       col_w - 2 * pad, byp_h),
                                f"L{layer}_{fx['fx']}_byp",
                                res["fx_bypass"].format(layer=layer, fx=fx["fx"]),
                                self.res_conn, toggle=True, color="panel",
                                text="byp", text_size=11)
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
