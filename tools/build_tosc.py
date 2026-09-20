#!/usr/bin/env python3
"""Build the VJ control surface from spec/mapping.yaml.

    python3 tools/build_tosc.py [-o build/vj-control.tosc]

Emits the .tosc next to an uncompressed .xml of the same name so layout
changes stay reviewable in git diffs.
"""

from __future__ import annotations

import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tosc  # noqa: E402
from tosc import BUTTON, FADER, GROUP, LABEL, PAGER, RADIAL, XY, Node, OscMessage  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "mapping.yaml")

# Momentary vs latching, in TouchOSC's buttonType encoding.
MOMENTARY, TOGGLE = 0, 1


def load_spec(path: str = SPEC) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


class Builder:
    def __init__(self, spec: dict):
        self.spec = spec
        self.colors = {k: tuple(v) for k, v in spec["colors"].items()}
        self.res_conn = tosc.connections(spec["connections"]["resolume"]["slot"])
        self.td_conn = tosc.connections(spec["connections"]["touchdesigner"]["slot"])
        self.both_conn = tosc.connections(
            spec["connections"]["resolume"]["slot"],
            spec["connections"]["touchdesigner"]["slot"],
        )

    # -- small control factories ------------------------------------------
    def label(self, frame, text, size=14, color="text") -> Node:
        return Node(
            LABEL,
            frame,
            name=f"lbl_{text}",
            text=text,
            text_size=size,
            color=self.colors[color],
            background=False,
            outline=False,
        )

    def button(self, frame, name, path, conns, *, toggle=False, color="panel",
               text="", constant_args=()) -> Node:
        btn = Node(
            BUTTON,
            frame,
            name=name,
            text=text,
            color=self.colors[color],
            button_type=TOGGLE if toggle else MOMENTARY,
        )
        btn.messages.append(
            OscMessage(
                path,
                conns,
                send_value=not constant_args,
                constant_args=constant_args,
                trigger="ANY" if toggle else "RISE",
            )
        )
        return btn

    def fader(self, frame, name, path, conns, *, horizontal=False, color="panel") -> Node:
        fdr = Node(
            FADER,
            frame,
            name=name,
            color=self.colors[color],
            orientation=1 if horizontal else 0,
        )
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

    # -- pages -------------------------------------------------------------
    def global_strip(self, width: int, height: int) -> Node:
        res = self.spec["resolume"]
        td = self.spec["touchdesigner"]
        strip = Node(GROUP, (0, 0, width, height), name="globals",
                     color=self.colors["bg"], outline=False)
        strip.add(self.label((12, 8, 220, height - 16), self.spec["layout"]["name"], size=22))

        # Blackout drives Resolume master and the TD intensity bus at once.
        blackout = Node(BUTTON, (width - 190, 8, 178, height - 16), name="blackout",
                        text="BLACKOUT", color=self.colors["danger"], button_type=TOGGLE)
        blackout.messages.append(OscMessage(res["master"], self.res_conn, send_value=False,
                                            constant_args=(0.0,), trigger="RISE"))
        blackout.messages.append(OscMessage(td["blackout"], self.td_conn))
        strip.add(blackout)

        strip.add(self.button((width - 380, 8, 178, height - 16), "tap",
                              res["tempo_tap"], self.res_conn,
                              color="accent", text="TAP", constant_args=(1.0,)))
        strip.add(self.fader((250, 14, width - 650, height - 28), "master_global",
                             res["master"], self.res_conn, horizontal=True, color="resolume"))
        return strip

    def resolume_page(self, width: int, height: int) -> Node:
        res = self.spec["resolume"]
        grid = self.spec["grid"]
        layers, clips = grid["layers"], grid["clips"]
        page = Node(GROUP, (0, 0, width, height), name="RESOLUME",
                    color=self.colors["bg"], outline=False)

        col_w = width // (layers + 1)          # last column holds master + speed
        pad = 6
        header_h = 30
        strip_h = 44                            # bypass / solo / clear row
        fader_h = 150
        clip_area = height - header_h - strip_h - fader_h - 5 * pad
        clip_h = clip_area // clips

        for li in range(layers):
            layer = li + 1
            x = li * col_w
            page.add(self.label((x, 2, col_w, header_h), f"LAYER {layer}", size=16,
                                color="resolume"))
            y = header_h + pad
            for ci in range(clips):
                clip = ci + 1
                path = res["clip_connect"].format(layer=layer, clip=clip)
                page.add(self.button(
                    (x + pad, y + ci * clip_h, col_w - 2 * pad, clip_h - pad),
                    f"L{layer}C{clip}", path, self.res_conn,
                    color="panel", text=str(clip), constant_args=(1.0,)))

            y = header_h + pad + clip_area + pad
            btn_w = (col_w - 4 * pad) // 3
            for i, (key, text) in enumerate((
                ("layer_bypass", "BYP"), ("layer_solo", "SOLO"), ("layer_clear", "CLR"),
            )):
                path = res[key].format(layer=layer)
                toggle = key != "layer_clear"
                page.add(self.button(
                    (x + pad + i * (btn_w + pad), y, btn_w, strip_h - pad),
                    f"L{layer}_{text}", path, self.res_conn,
                    toggle=toggle, color="panel", text=text,
                    constant_args=() if toggle else (1.0,)))

            y += strip_h
            page.add(self.fader(
                (x + pad, y, col_w - 2 * pad, fader_h - pad),
                f"L{layer}_opacity", res["layer_opacity"].format(layer=layer),
                self.res_conn, color="resolume"))

        # Master column.
        x = layers * col_w
        page.add(self.label((x, 2, col_w, header_h), "MASTER", size=16, color="accent"))
        half = (height - header_h - 3 * pad) // 2
        page.add(self.label((x + pad, header_h + pad, col_w - 2 * pad, 24), "MASTER", size=12))
        page.add(self.fader((x + pad, header_h + pad + 24, col_w - 2 * pad, half - 24),
                            "master", res["master"], self.res_conn, color="accent"))
        y = header_h + 2 * pad + half
        page.add(self.label((x + pad, y, col_w - 2 * pad, 24), "SPEED", size=12))
        page.add(self.fader((x + pad, y + 24, col_w - 2 * pad, half - 70),
                            "speed", res["speed"], self.res_conn, color="accent"))
        page.add(self.button((x + pad, height - 46 - pad, col_w - 2 * pad, 46),
                             "resync", res["tempo_resync"], self.res_conn,
                             color="accent", text="RESYNC", constant_args=(1.0,)))
        return page

    def fx_page(self, width: int, height: int) -> Node:
        res = self.spec["resolume"]
        grid = self.spec["grid"]
        layers = grid["layers"]
        fx_list = res["fx_names"][: grid["fx_params"]]
        page = Node(GROUP, (0, 0, width, height), name="FX",
                    color=self.colors["bg"], outline=False)

        label_w = 90
        col_w = (width - label_w) // len(fx_list)
        row_h = height // layers
        pad = 6

        for i, fx in enumerate(fx_list):
            page.add(self.label((label_w + i * col_w, 0, col_w, 22), fx["name"],
                                size=12, color="resolume"))

        for li in range(layers):
            layer = li + 1
            y = li * row_h + 22
            page.add(self.label((0, y + row_h // 3, label_w, 24), f"L{layer}", size=16,
                                color="resolume"))
            for i, fx in enumerate(fx_list):
                x = label_w + i * col_w
                path = res["fx_param"].format(layer=layer, fx=fx["fx"], param=fx["param"])
                knob_h = row_h - 22 - 2 * pad - 26
                page.add(self.radial((x + pad, y, col_w - 2 * pad, knob_h),
                                     f"L{layer}_{fx['fx']}", path, self.res_conn,
                                     color="panel"))
                bypass = res["fx_bypass"].format(layer=layer, fx=fx["fx"])
                page.add(self.button((x + pad, y + knob_h + 2, col_w - 2 * pad, 24),
                                     f"L{layer}_{fx['fx']}_byp", bypass, self.res_conn,
                                     toggle=True, color="panel", text="byp"))
        return page

    def td_page(self, width: int, height: int) -> Node:
        td = self.spec["touchdesigner"]
        grid = self.spec["grid"]
        page = Node(GROUP, (0, 0, width, height), name="TOUCHDESIGNER",
                    color=self.colors["bg"], outline=False)
        pad = 8

        # Left half: fader bank with toggles underneath.
        bank_w = width // 2
        n = grid["td_faders"]
        col_w = bank_w // n
        fader_h = height - 150
        page.add(self.label((0, 0, bank_w, 24), "PARAM BANK", size=14, color="td"))
        for i in range(n):
            x = i * col_w
            page.add(self.fader((x + pad, 26, col_w - 2 * pad, fader_h - 26),
                                f"td_fader_{i + 1}", td["fader"].format(n=i + 1),
                                self.td_conn, color="td"))
            page.add(self.label((x, fader_h + 2, col_w, 20), str(i + 1), size=12))

        tog_y = fader_h + 24
        for i in range(grid["td_toggles"]):
            x = i * col_w
            page.add(self.button((x + pad, tog_y, col_w - 2 * pad, 48),
                                 f"td_toggle_{i + 1}", td["toggle"].format(n=i + 1),
                                 self.td_conn, toggle=True, color="td", text=str(i + 1)))
            page.add(self.button((x + pad, tog_y + 52, col_w - 2 * pad, 48),
                                 f"td_trigger_{i + 1}", td["trigger"].format(n=i + 1),
                                 self.td_conn, color="panel", text=f"T{i + 1}",
                                 constant_args=(1.0,)))

        # Right half: XY pads plus scene / intensity.
        rx = bank_w
        page.add(self.label((rx, 0, bank_w, 24), "XY / SCENE", size=14, color="td"))
        pads = grid["td_pads"]
        pad_w = (bank_w - (pads + 1) * pad) // pads
        pad_h = height - 200
        for i in range(pads):
            x = rx + pad + i * (pad_w + pad)
            page.add(self.xy((x, 26, pad_w, pad_h), f"td_pad_{i + 1}",
                             td["pad"].format(n=i + 1) + "/x",
                             td["pad"].format(n=i + 1) + "/y",
                             self.td_conn))
            page.add(self.label((x, 26 + pad_h + 2, pad_w, 20), f"PAD {i + 1}", size=12))

        y = 26 + pad_h + 28
        page.add(self.label((rx + pad, y, 120, 24), "INTENSITY", size=12))
        page.add(self.fader((rx + 130, y, bank_w - 150, 48), "td_intensity",
                            td["intensity"], self.td_conn, horizontal=True, color="td"))
        y += 56
        page.add(self.label((rx + pad, y, 120, 24), "SCENE", size=12))
        page.add(self.fader((rx + 130, y, bank_w - 150, 48), "td_scene",
                            td["scene"], self.td_conn, horizontal=True, color="td"))
        return page

    # -- assembly ----------------------------------------------------------
    def build(self) -> Node:
        layout = self.spec["layout"]
        w, h = layout["width"], layout["height"]
        strip_h = layout["tabbar_height"]

        root = Node(GROUP, (0, 0, w, h), name="root", color=self.colors["bg"], outline=False)
        root.add(self.global_strip(w, strip_h))

        pager_h = h - strip_h
        page_h = pager_h - layout["tabbar_height"]
        pager = Node(
            PAGER,
            (0, strip_h, w, pager_h),
            name="views",
            color=self.colors["panel"],
            extra_props={
                "tabLabels": ("b", 1),
                "tabbarDoubleTap": ("b", 0),
                "tabbarSize": ("i", layout["tabbar_height"]),
            },
        )
        pager.add(self.resolume_page(w, page_h))
        pager.add(self.fx_page(w, page_h))
        pager.add(self.td_page(w, page_h))
        root.add(pager)
        return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-s", "--spec", default=SPEC)
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "build", "vj-control.tosc"))
    args = ap.parse_args()

    spec = load_spec(args.spec)
    root = Builder(spec).build()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    xml_out = os.path.splitext(args.out)[0] + ".xml"
    tosc.write(root, args.out, xml_out)
    print(f"wrote {args.out}")
    print(f"wrote {xml_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
