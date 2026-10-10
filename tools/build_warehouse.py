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
from build_boris import (BorisBuilder, address_map, load_spec,  # noqa: E402
                         saturated)
from tosc import GROUP, PAGER, Node  # noqa: E402

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


class WarehouseBuilder(BorisBuilder):
    """The Boris SHOW page, with this show's TD page."""

    def td_page(self, width: int, height: int) -> Node:
        td = self.spec["td"]
        page = Node(GROUP, (0, 0, width, height), name="TD",
                    color=self.colors["spiderweb"], background=False,
                    outline=False)
        pad = 10
        header_h = 28
        label_h = 22
        strip_fader_h = 60
        strip_h = 2 * (label_h + strip_fader_h) + pad
        top_h = height - strip_h - 3 * pad
        body_y = pad + header_h
        body_h = top_h - header_h
        gap = pad + 6

        # --- SPIDERWEB faders ---
        sw = td["spiderweb"]
        x = pad
        used = self.fader_bank(page, x, body_y, body_h, sw["faders"],
                               "spiderweb")
        self.block_header(page, (x, pad, used, header_h), sw["label"],
                          "spiderweb")
        x += used + gap

        # --- the square pad: Spiderweb camera orbit and Acuarela's brush ---
        side = body_h
        pd = td["pad"]
        self.block_header(page, (x, pad, side, header_h), pd["label"],
                          "shared")
        page.add(self.xy((x, body_y, side, side), "camera_liquid",
                         pd["x"], pd["y"], self.td_conn, color="shared"))
        x += side + gap

        # --- ACUARELA faders (its hue is in the colour strip) ---
        ac = td["acuarela"]
        used = self.fader_bank(page, x, body_y, body_h, ac["faders"],
                               "acuarela")
        self.block_header(page, (x - 20, pad, used + 40, header_h),
                          ac["label"], "acuarela")
        x += used + gap

        # --- PALETTE: switches both visuals ---
        pw = width - pad - x
        self.block_header(page, (x, pad, pw, header_h), "PALETTE", "shared")
        self.palette_group(page, (x, body_y, pw, body_h), td["palettes"],
                           "shared")

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
