#!/usr/bin/env python3
"""Render a .tosc layout to SVG so it can be judged without syncing to a device.

    python3 tools/preview.py build/vj-control-portrait.tosc -o build/portrait.svg
    python3 tools/preview.py build/vj-control-landscape.tosc --node brand_mark

This approximates TouchOSC's rendering — enough to check composition, colour
and legibility. It is not the app: gradients, cursors, tab bars and fader
handles are all drawn plainly here.
"""

from __future__ import annotations

import argparse
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspect_tosc import read_xml  # noqa: E402

RECTANGLE, CIRCLE, TRIANGLE, DIAMOND, PENTAGON, HEXAGON = range(1, 7)

# Which pager page to render; set from --page.
PAGE_INDEX = [0]


def props(node: ET.Element) -> dict:
    out = {}
    for p in node.findall("./properties/property"):
        key = p.findtext("key") or ""
        value = p.find("value")
        if value is not None and len(value):
            out[key] = {c.tag: c.text for c in value}
        else:
            out[key] = (value.text if value is not None else "") or ""
    return out


def value_of(node: ET.Element, key: str) -> str:
    for v in node.findall("./values/value"):
        if v.findtext("key") == key:
            return v.findtext("default") or ""
    return ""


def css_color(c: dict | str, default="#888") -> str:
    if not isinstance(c, dict):
        return default
    try:
        r, g, b = (int(float(c.get(k, 0)) * 255) for k in "rgb")
        a = float(c.get("a", 1))
    except (TypeError, ValueError):
        return default
    return f"rgba({r},{g},{b},{a:.3f})"


def draw(node: ET.Element, ox: float, oy: float, out: list) -> None:
    p = props(node)
    frame = p.get("frame", {})
    try:
        x = ox + float(frame.get("x", 0))
        y = oy + float(frame.get("y", 0))
        w = float(frame.get("w", 0))
        h = float(frame.get("h", 0))
    except (TypeError, ValueError):
        return

    ntype = node.get("type", "")
    fill = css_color(p.get("color"))
    has_bg = p.get("background", "1") == "1"
    has_outline = p.get("outline", "1") == "1"
    shape = int(p.get("shape") or RECTANGLE)

    if ntype not in ("GROUP", "PAGER", "LABEL"):
        body = ""
        if shape == CIRCLE:
            body = (f'<ellipse cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" '
                    f'rx="{w / 2:.1f}" ry="{h / 2:.1f}"')
        else:
            body = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2"'
        out.append(f'{body} fill="{fill if has_bg else "none"}" '
                   f'stroke="{fill if has_outline else "none"}" stroke-width="1.5"/>')
    elif ntype in ("GROUP", "PAGER") and has_bg:
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                   f'fill="{fill}"/>')

    if ntype == "LABEL":
        text = value_of(node, "text")
        size = float(p.get("textSize") or 14)
        color = css_color(p.get("textColor"), "#fff")
        if has_bg:
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                       f'height="{h:.1f}" fill="{fill}"/>')
        out.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + size * 0.36:.1f}" '
                   f'font-family="Helvetica,Arial,sans-serif" font-size="{size:.0f}" '
                   f'fill="{color}" text-anchor="middle">'
                   f'{text.replace("&", "&amp;").replace("<", "&lt;")}</text>')

    kids = node.find("children")
    children = list(kids) if kids is not None else []
    if ntype == "PAGER" and children:
        # Only one page is on screen at a time; drawing them all just stacks
        # every page's controls on top of each other.
        children = [children[min(PAGE_INDEX[0], len(children) - 1)]]
    for kid in children:
        draw(kid, x, y, out)


def find_node(node: ET.Element, name: str):
    if (props(node).get("name") or "") == name:
        return node
    kids = node.find("children")
    for kid in (list(kids) if kids is not None else []):
        found = find_node(kid, name)
        if found is not None:
            return found
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("-o", "--out")
    ap.add_argument("-n", "--node", help="render only this named control")
    ap.add_argument("-z", "--zoom", type=float, default=1.0)
    ap.add_argument("-p", "--page", type=int, default=0,
                    help="which pager page to draw (0-based)")
    args = ap.parse_args()

    PAGE_INDEX[0] = args.page
    root = read_xml(args.path)
    node = root.find("node") if root.tag == "lexml" else root
    if args.node:
        node = find_node(node, args.node)
        if node is None:
            print(f"no control named {args.node!r}")
            return 1

    frame = props(node).get("frame", {})
    w = float(frame.get("w", 100)) * args.zoom
    h = float(frame.get("h", 100)) * args.zoom
    body: list[str] = []
    # Re-origin: a control's own frame offset is relative to a parent that is
    # not being drawn, so cancel it or the render sits off-canvas.
    draw(node, -float(frame.get("x", 0)), -float(frame.get("y", 0)), body)

    out = args.out or os.path.splitext(args.path)[0] + (
        f"-{args.node}.svg" if args.node else f"-page{args.page}.svg")
    with open(out, "w") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
                 f'height="{h:.0f}" viewBox="0 0 {w / args.zoom:.0f} '
                 f'{h / args.zoom:.0f}">\n'
                 f'<rect width="100%" height="100%" fill="#1c1c20"/>\n'
                 + "\n".join(body) + "\n</svg>\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
