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
# Whether to draw controls marked invisible; set from --hidden.
SHOW_HIDDEN = [False]


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


TRACK = "#0f0f12"          # the recessed face a control is drawn into
EDGE = "rgba(255,255,255,0.10)"


def corners(x, y, w, h, colour, length=None):
    """TouchOSC's default outline: brackets at the corners, not a full box."""
    # Short brackets: at clip-grid density, long ones from adjacent controls
    # meet and read as a cross-hatch rather than as separate controls.
    n = length or min(9.0, w / 5, h / 5)
    d = []
    for cx, cy, sx, sy in ((x, y, 1, 1), (x + w, y, -1, 1),
                           (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        d.append(f'M {cx + sx * n:.1f} {cy:.1f} L {cx:.1f} {cy:.1f} '
                 f'L {cx:.1f} {cy + sy * n:.1f}')
    return [f'<path d="{" ".join(d)}" fill="none" stroke="{colour}" '
            f'stroke-width="1.6" opacity="0.85"/>']


def value_of_x(p) -> float:
    return 0.0


def fader(x, y, w, h, colour, p):
    """Dark track, a bar from the low end, and grid ticks when it snaps."""
    vertical = int(p.get("orientation") or 0) in (0, 2)
    out = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
           f'rx="3" fill="{TRACK}" stroke="{EDGE}" stroke-width="1"/>']

    steps = int(p.get("gridSteps") or 0) if p.get("grid") == "1" else 0
    if steps > 1:
        for i in range(1, steps):
            t = i / steps
            if vertical:
                gy = y + h - t * h
                out.append(f'<line x1="{x + 3:.1f}" y1="{gy:.1f}" '
                           f'x2="{x + w - 3:.1f}" y2="{gy:.1f}" '
                           f'stroke="{EDGE}" stroke-width="1"/>')
            else:
                gx = x + t * w
                out.append(f'<line x1="{gx:.1f}" y1="{y + 3:.1f}" '
                           f'x2="{gx:.1f}" y2="{y + h - 3:.1f}" '
                           f'stroke="{EDGE}" stroke-width="1"/>')

    # A doc image of controls all sitting at zero reads as broken rather than
    # idle, so the bar is drawn at a nominal level to show which way it runs.
    level = 0.34
    if vertical:
        bh = h * level
        out.append(f'<rect x="{x + 2:.1f}" y="{y + h - bh:.1f}" '
                   f'width="{w - 4:.1f}" height="{bh - 2:.1f}" rx="2" '
                   f'fill="{colour}" opacity="0.9"/>')
        out.append(f'<line x1="{x + 2:.1f}" y1="{y + h - bh:.1f}" '
                   f'x2="{x + w - 2:.1f}" y2="{y + h - bh:.1f}" '
                   f'stroke="#fff" stroke-width="1.5" opacity="0.75"/>')
    else:
        bw = w * level
        out.append(f'<rect x="{x + 2:.1f}" y="{y + 2:.1f}" width="{bw - 2:.1f}" '
                   f'height="{h - 4:.1f}" rx="2" fill="{colour}" opacity="0.9"/>')
        out.append(f'<line x1="{x + bw:.1f}" y1="{y + 2:.1f}" '
                   f'x2="{x + bw:.1f}" y2="{y + h - 2:.1f}" '
                   f'stroke="#fff" stroke-width="1.5" opacity="0.75"/>')
    return out


def radial(x, y, w, h, colour, p):
    """A ring dial: dark face, track ring, coloured arc and a pointer."""
    import math
    cx, cy = x + w / 2, y + h / 2
    r = min(w, h) / 2 - 2
    start, sweep = 135.0, 270.0
    level = 0.34
    out = [f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{TRACK}" '
           f'stroke="{EDGE}" stroke-width="1"/>']

    def arc(frm, to, stroke, width, opacity):
        rr = r - width / 2 - 1
        a0, a1 = math.radians(frm), math.radians(to)
        x0, y0 = cx + rr * math.cos(a0), cy + rr * math.sin(a0)
        x1, y1 = cx + rr * math.cos(a1), cy + rr * math.sin(a1)
        large = 1 if (to - frm) % 360 > 180 else 0
        return (f'<path d="M {x0:.1f} {y0:.1f} A {rr:.1f} {rr:.1f} 0 {large} 1 '
                f'{x1:.1f} {y1:.1f}" fill="none" stroke="{stroke}" '
                f'stroke-width="{width:.1f}" stroke-linecap="round" '
                f'opacity="{opacity}"/>')

    thickness = max(3.0, r * 0.22)
    out.append(arc(start, start + sweep, EDGE, thickness, 1))
    out.append(arc(start, start + sweep * level, colour, thickness, 0.95))

    ang = math.radians(start + sweep * level)
    inner = r - thickness - 2
    out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
               f'x2="{cx + inner * math.cos(ang):.1f}" '
               f'y2="{cy + inner * math.sin(ang):.1f}" stroke="#fff" '
               f'stroke-width="1.8" opacity="0.8" stroke-linecap="round"/>')
    return out


def xy_pad(x, y, w, h, colour):
    """Dark field with crosshairs and a cursor."""
    px, py = x + w * 0.42, y + h * 0.55
    return [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" '
        f'fill="{TRACK}" stroke="{EDGE}" stroke-width="1"/>',
        f'<line x1="{x:.1f}" y1="{py:.1f}" x2="{x + w:.1f}" y2="{py:.1f}" '
        f'stroke="{colour}" stroke-width="1" opacity="0.5"/>',
        f'<line x1="{px:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{y + h:.1f}" '
        f'stroke="{colour}" stroke-width="1" opacity="0.5"/>',
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="none" '
        f'stroke="{colour}" stroke-width="2"/>',
    ]


def button(x, y, w, h, colour, has_bg, has_outline, shape):
    """A dark face tinted with the button's colour, plus corner brackets."""
    if shape == CIRCLE:
        body = (f'<ellipse cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" '
                f'rx="{w / 2:.1f}" ry="{h / 2:.1f}"')
    else:
        body = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                f'height="{h:.1f}" rx="3"')
    out = []
    if has_bg:
        out.append(f'{body} fill="{TRACK}"/>')
        out.append(f'{body} fill="{colour}" opacity="0.22"/>')
    if has_outline:
        out.extend(corners(x, y, w, h, colour))
    return out


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
    if p.get("visible", "1") == "0" and not SHOW_HIDDEN[0]:
        # Modal overlays ship hidden and show themselves when notified;
        # drawing them would bury the page they sit over.
        return
    fill = css_color(p.get("color"))
    has_bg = p.get("background", "1") == "1"
    has_outline = p.get("outline", "1") == "1"
    shape = int(p.get("shape") or RECTANGLE)

    if ntype in ("GROUP", "PAGER"):
        if has_bg:
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                       f'height="{h:.1f}" fill="{fill}" rx="3"/>')
    elif ntype == "FADER":
        out.extend(fader(x, y, w, h, fill, p))
    elif ntype == "RADIAL":
        out.extend(radial(x, y, w, h, fill, p))
    elif ntype == "XY":
        out.extend(xy_pad(x, y, w, h, fill))
    elif ntype == "BUTTON":
        out.extend(button(x, y, w, h, fill, has_bg, has_outline, shape))
    elif ntype == "BOX":
        body = (f'<ellipse cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" '
                f'rx="{w / 2:.1f}" ry="{h / 2:.1f}"' if shape == CIRCLE
                else f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                     f'height="{h:.1f}" rx="3"')
        out.append(f'{body} fill="{fill if has_bg else "none"}" '
                   f'stroke="{fill if has_outline else "none"}" stroke-width="1.5"/>')

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
        # Draw the tab bar: a pager's tabs are not controls, so without this
        # the page looks like it has an unexplained empty strip at the top.
        bar_h = float(p.get("tabbarSize") or 0)
        if bar_h:
            tab_w = w / len(children)
            active = min(PAGE_INDEX[0], len(children) - 1)
            for i, page_node in enumerate(children):
                tp = props(page_node)
                tx = x + i * tab_w
                on = i == active
                out.append(f'<rect x="{tx:.1f}" y="{y:.1f}" width="{tab_w:.1f}" '
                           f'height="{bar_h:.1f}" fill="'
                           f'{css_color(tp.get("tabColorOn" if on else "tabColorOff"), "#222")}"'
                           f' stroke="#000" stroke-width="0.5"/>')
                label = tp.get("tabLabel") or ""
                if isinstance(label, str) and label:
                    size = float(p.get("textSizeOn" if on else "textSizeOff") or 14)
                    out.append(
                        f'<text x="{tx + tab_w / 2:.1f}" '
                        f'y="{y + bar_h / 2 + size * 0.36:.1f}" '
                        f'font-family="Helvetica,Arial,sans-serif" '
                        f'font-size="{size:.0f}" fill="'
                        f'{css_color(tp.get("textColorOn" if on else "textColorOff"), "#ddd")}"'
                        f' text-anchor="middle">{label}</text>')

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
    ap.add_argument("--hidden", action="store_true",
                    help="also draw controls marked invisible")
    args = ap.parse_args()

    PAGE_INDEX[0] = args.page
    SHOW_HIDDEN[0] = args.hidden
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
