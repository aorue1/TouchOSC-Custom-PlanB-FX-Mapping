#!/usr/bin/env python3
"""Render annotated layout diagrams for the docs, one per page.

    python3 tools/page_diagram.py                 # all pages -> docs/img/*.svg

Each diagram is the page as TouchOSC draws it, with numbered callouts over the
regions that need explaining and a legend beside them. Callouts are anchored to
controls by name, so a layout change moves the callout with the control instead
of leaving the docs quietly wrong.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402
from inspect_tosc import read_xml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
OUT_DIR = os.path.join(ROOT, "docs", "img")

LEGEND_W = 330
# Width the screenshot is displayed at in the diagram. The layout's own
# geometry is scaled to match, so callouts land on the real controls.
SHOT_W = 1400
PAD = 24
INK = "#e8e8ea"
ACCENT = "#ffd23f"

# Per page: (file stem, page index, title, subtitle, callouts).
# A callout is (label, [control names], note). A name of the form
# "tabbar:<pager>" targets that pager's tab strip, which is drawn by the
# renderer but is not made of controls.
PAGES = [
    ("resolume", 0, "RESOLUME", "Columns, clips, layer state and master", [
        ("Page tabs", ["tabbar:views"],
         "Switches between the three pages. There is no global strip: Resolume "
         "is always the master, so its master opacity and tempo live on this "
         "page and every page keeps the 60pt a strip would have taken."),
        ("Column triggers", ["columns"],
         "Fires a whole column across every layer at once. Six at a time; the "
         "arrows shift to the next six, rewriting the captions."),
        ("Clip group", ["tabbar:clipgroups"],
         "First bank row: picks a group of 16 clips."),
        ("Clip bank", ["tabbar:banks1"],
         "Second bank row: picks 4 clips within the group. Two rows reach 32 "
         "clips per layer while keeping 4 rows on screen."),
        ("Clip grid", ["L1C1", "L4C4"],
         "One column per layer. Tapping connects that clip. Captions show the "
         "clip number, or its name if Resolume is sending them."),
        ("Clip nav", ["L1_PREV", "L4_NEXT"],
         "Previous / next clip on that layer, without hunting the grid."),
        ("Layer state", ["L1_BYP", "L4_CLR"],
         "Bypass and solo latch; clear is momentary."),
        ("Opacity", ["L1_opacity", "L4_opacity"],
         "Per-layer opacity. These stay put when you change bank, so the "
         "faders never move under your hand."),
        ("Speed and master", ["speed", "master"],
         "Composition speed beside Resolume's master opacity. Neither needs "
         "width, so they sit as two narrow columns."),
        ("Colour", ["resolume_color"], "Opens the colour picker."),
        ("Tempo", ["bpm", "resync", "tap_page"],
         "BPM sits with resync and tap because they are the same job: tap it "
         "for a numeric keypad when tapping a tempo is not realistic, or nudge "
         "with -/+."),
    ]),
    ("fx", 1, "FX", "Four effects across five targets", [
        ("Effects", ["lbl_Hue", "lbl_Datamosh"],
         "Only the effects reached for in a set. The list is spec-driven: "
         "add or remove entries in resolume.fx_names."),
        ("Layers", ["lbl_L1", "lbl_L4"], "One row per layer."),
        ("Composition", ["lbl_COMP"],
         "The same effects at composition level, over everything."),
        ("Dials", ["L1_huerotate", "L4_datamosh"],
         "Drag to adjust — a tap does nothing, so a mistap costs nothing. "
         "Dial to zero to bypass; there is no separate bypass button."),
        ("Colour = value", ["COMP_huerotate", "COMP_datamosh"],
         "Each dial paints itself from its value: deep blue at rest, cyan "
         "halfway, green at full, so the page reads as a level meter."),
    ]),
    ("touchdesigner", 2, "TOUCHDESIGNER", "Generic parameter bank", [
        ("Faders", ["td_fader_1", "td_fader_8"],
         "Eight faders on /td/fader/1..8. An OSC In CHOP turns these straight "
         "into channels."),
        ("Toggles", ["td_toggle_1", "td_toggle_8"],
         "Latching, on /td/toggle/1..8."),
        ("Triggers", ["td_trigger_1", "td_trigger_8"],
         "Momentary, on /td/trigger/1..8 — one-shots, reloads, bangs."),
        ("XY pads", ["td_pad_1", "td_pad_2"],
         "Two axes each: /td/pad/n/x and /td/pad/n/y."),
        ("Colour", ["touchdesigner_color"],
         "Opens the same picker as the Resolume page, sending to "
         "/td/color/r|g|b."),
        ("Intensity / scene", ["td_intensity", "td_scene"],
         "Two spare buses for whatever a patch needs most."),
    ]),
]


def frames(path: str, page_index: int) -> dict:
    """Absolute frame of every visible control, by name, plus tab strips."""
    root = read_xml(path).find("node")
    found: dict[str, tuple] = {}

    def walk(node: ET.Element, ox: float, oy: float):
        p = preview.props(node)
        frame = p.get("frame", {})
        x = ox + float(frame.get("x", 0))
        y = oy + float(frame.get("y", 0))
        w = float(frame.get("w", 0))
        h = float(frame.get("h", 0))
        if p.get("visible", "1") == "0":
            return
        name = p.get("name")
        if isinstance(name, str) and name and name not in found:
            found[name] = (x, y, w, h)

        kids = node.find("children")
        children = list(kids) if kids is not None else []
        if node.get("type") == "PAGER" and children:
            bar = float(p.get("tabbarSize") or 0)
            found.setdefault(f"tabbar:{name}", (x, y, w, bar))
            # Only the page on show is laid out where the render draws it.
            children = [children[min(page_index if name == "views" else 0,
                                     len(children) - 1)]]
        for kid in children:
            walk(kid, x, y)

    walk(root, 0, 0)
    return found


def union(boxes: list[tuple]) -> tuple:
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    bottom = max(b[1] + b[3] for b in boxes)
    return (left, top, right - left, bottom - top)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def wrap(text: str, width: int) -> list:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def diagram(path: str, page_index: int, title: str, subtitle: str,
            callouts: list, out: str, shot: str | None = None) -> str:
    root = read_xml(path).find("node")
    frame = preview.props(root).get("frame", {})
    pw, ph = float(frame.get("w", 0)), float(frame.get("h", 0))

    preview.PAGE_INDEX[0] = page_index
    preview.SHOW_HIDDEN[0] = False
    boxes = frames(path, page_index)

    if shot:
        # A photograph of the real surface beats a drawing of it. The layout
        # is a fixed size and the screenshot is that layout scaled, so one
        # factor maps every control's frame onto the image.
        scale = SHOT_W / pw
        pw, ph = SHOT_W, ph * scale
        boxes = {k: tuple(v * scale for v in box) for k, box in boxes.items()}
        # Embedded, not referenced: an SVG rendered inside an <img> (which is
        # how a browser and GitHub both treat it) does not load external
        # images, so a linked screenshot silently renders as nothing.
        data = base64.b64encode(open(shot, "rb").read()).decode()
        body = [f'<image href="data:image/webp;base64,{data}" x="0" y="0" '
                f'width="{pw:.0f}" height="{ph:.0f}"/>']
    else:
        body = []
        preview.draw(root, 0, 0, body)
    marks, legend = [], []
    # A long legend in one column leaves the page render floating in empty
    # space, so past a handful of callouts it runs in two.
    columns = 2 if len(callouts) > 7 else 1
    col_w = LEGEND_W if columns == 1 else LEGEND_W - 40
    per_col = -(-len(callouts) // columns)
    ly = PAD + 74
    col = 0
    for i, (label, names, note) in enumerate(callouts, start=1):
        targets = [boxes[n] for n in names if n in boxes]
        if not targets:
            raise SystemExit(f"{title}: no control named any of {names}")
        x, y, w, h = union(targets)
        # A control against an edge would push its outline and badge off the
        # canvas, so both are clamped back inside it.
        rx, ry = max(x - 3, 1.5), max(y - 3, 1.5)
        bx, by = max(x + 13, 17), max(y + 13, 17)
        marks.append(
            f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{x + w + 3 - rx:.1f}" '
            f'height="{y + h + 3 - ry:.1f}" fill="none" stroke="{ACCENT}" '
            f'stroke-width="2.5" rx="4" opacity="0.95"/>')
        marks.append(
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="15" fill="{ACCENT}"/>'
            f'<text x="{bx:.1f}" y="{by + 6:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="16" '
            f'font-weight="bold" fill="#141416">{i}</text>')

        if i > 1 and (i - 1) % per_col == 0:
            col += 1
            ly = PAD + 74
        lx = pw + PAD + col * col_w

        legend.append(
            f'<circle cx="{lx + 14:.1f}" cy="{ly - 5:.1f}" r="14" '
            f'fill="{ACCENT}"/>'
            f'<text x="{lx + 14:.1f}" y="{ly + 1:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="15" '
            f'font-weight="bold" fill="#141416">{i}</text>')
        legend.append(
            f'<text x="{lx + 38:.1f}" y="{ly:.1f}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="16" '
            f'font-weight="bold" fill="{INK}">{esc(label)}</text>')
        ly += 22
        for line in wrap(note, 34 if columns == 2 else 40):
            legend.append(
                f'<text x="{lx + 38:.1f}" y="{ly:.1f}" '
                f'font-family="Helvetica,Arial,sans-serif" font-size="13.5" '
                f'fill="#a9a9b2">{esc(line)}</text>')
            ly += 18
        ly += 14
        tallest = max(locals().get("tallest", 0), ly)

    width = pw + columns * col_w + 2 * PAD
    # Room below the image as well as above it, or the last row of controls
    # sits flush against the edge and reads as cropped.
    height = max(ph, tallest) + 2 * PAD
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        f'<rect width="100%" height="100%" fill="#141416"/>',
        f'<g>{"".join(body)}</g>',
        "".join(marks),
        f'<text x="{pw + PAD:.1f}" y="{PAD + 22:.1f}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="26" '
        f'font-weight="bold" fill="{INK}">{esc(title)}</text>',
        f'<text x="{pw + PAD:.1f}" y="{PAD + 46:.1f}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="14" '
        f'fill="#a9a9b2">{esc(subtitle)}</text>',
        "".join(legend),
        "</svg>",
    ]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        fh.write("\n".join(svg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-l", "--layout",
                    default=os.path.join(BUILD, "vj-control-landscape.tosc"))
    ap.add_argument("-d", "--outdir", default=OUT_DIR)
    args = ap.parse_args()

    for stem, index, title, subtitle, callouts in PAGES:
        shot = os.path.join(args.outdir, f"screen-{stem}.webp")
        out = diagram(args.layout, index, title, subtitle, callouts,
                      os.path.join(args.outdir, f"page-{stem}.svg"),
                      shot if os.path.exists(shot) else None)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
