#!/usr/bin/env python3
"""Sanity-check the built layout.

Catches the mistakes that are invisible in code but obvious on a tablet:
controls hanging outside their parent, controls sitting on top of each other,
zero/negative sizes, and duplicate OSC addresses.

    python3 tools/verify.py            # checks every layout in build/
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")

# Controls smaller than this are hard to hit accurately on a tablet.
MIN_TOUCH_PX = 28
# Containers are exempt from the touch-target and overlap rules.
CONTAINERS = {"GROUP", "PAGER"}


def frame_of(node: ET.Element):
    for prop in node.findall("./properties/property"):
        if prop.findtext("key") == "frame":
            v = prop.find("value")
            return tuple(int(v.findtext(a)) for a in ("x", "y", "w", "h"))
    return None


def is_decorative(node: ET.Element) -> bool:
    """True for anything that cannot be touched.

    Captions and logo artwork are meant to overlap the controls they sit on
    and are exempt from the touch-target rule; they carry interactive=0, which
    is also what makes touches fall through to the control underneath.
    """
    if node.get("type") in CONTAINERS:
        return True
    for key, _, text in ((p.findtext("key"), p.get("type"), _prop_text(p))
                         for p in node.findall("./properties/property")):
        if key == "interactive":
            return text in ("0", "false", "False")
    return False


def _prop_text(prop: ET.Element) -> str:
    value = prop.find("value")
    return (value.text if value is not None else "") or ""


def name_of(node: ET.Element) -> str:
    for prop in node.findall("./properties/property"):
        if prop.findtext("key") == "name":
            return prop.findtext("value") or ""
    return ""


def address_of(node: ET.Element):
    """Addresses this control sends its own value to.

    Messages carrying only constant arguments (a button firing a fixed value,
    e.g. blackout writing 0 to the master) are excluded: several controls may
    legitimately command one address that way. Two controls streaming their
    own value to the same address is the actual bug, because without feedback
    they drift apart.
    """
    out = []
    for osc in node.findall("./messages/osc"):
        sends_value = any(p.get("type") == "VALUE" for p in osc.findall("./arguments/partial"))
        if not sends_value:
            continue
        parts = [p.get("value", "") for p in osc.findall("./path/partial")]
        out.append("/" + "/".join(parts))
    return out


def overlaps(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def children_of(node: ET.Element):
    kids = node.find("children")
    return list(kids) if kids is not None else []


def check(path: str) -> list[str]:
    tree = ET.parse(path)
    root = tree.getroot().find("node")
    problems: list[str] = []
    addresses: dict[str, list[str]] = defaultdict(list)

    def walk(node: ET.Element, trail: str):
        frame = frame_of(node)
        here = f"{trail}/{name_of(node) or node.get('type')}"
        kids = children_of(node)

        siblings = []
        for kid in kids:
            kframe = frame_of(kid)
            kname = name_of(kid) or kid.get("type")
            ktype = kid.get("type")
            if kframe is None:
                problems.append(f"{here}/{kname}: no frame")
                continue
            x, y, w, h = kframe
            if w <= 0 or h <= 0:
                problems.append(f"{here}/{kname}: non-positive size {w}x{h}")
            elif not is_decorative(kid) and min(w, h) < MIN_TOUCH_PX:
                problems.append(f"{here}/{kname}: {w}x{h} is below the "
                                f"{MIN_TOUCH_PX}px touch minimum")
            if frame is not None:
                _, _, pw, ph = frame
                if x < 0 or y < 0 or x + w > pw or y + h > ph:
                    problems.append(f"{here}/{kname}: frame {kframe} escapes "
                                    f"parent {pw}x{ph}")
            if not is_decorative(kid):
                siblings.append((kname, kframe))
            for addr in address_of(kid):
                addresses[addr].append(f"{here}/{kname}")

        for i, (n1, f1) in enumerate(siblings):
            for n2, f2 in siblings[i + 1:]:
                if overlaps(f1, f2):
                    problems.append(f"{here}: {n1} {f1} overlaps {n2} {f2}")

        for kid in kids:
            walk(kid, here)

    walk(root, "")

    for addr, users in sorted(addresses.items()):
        # A pad legitimately sends /x and /y; anything else duplicated is a bug.
        if len(set(users)) > 1:
            problems.append(f"address {addr} sent by {len(users)} controls: "
                            f"{', '.join(sorted(set(users)))}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml", nargs="*", help="defaults to every .xml in build/")
    args = ap.parse_args()

    targets = args.xml or sorted(
        os.path.join(BUILD, f) for f in os.listdir(BUILD) if f.endswith(".xml"))
    if not targets:
        print("nothing to verify; run tools/build_tosc.py first")
        return 1

    total = 0
    for target in targets:
        problems = check(target)
        total += len(problems)
        for p in problems:
            print(p)
        print(f"{len(problems)} problem(s) in {os.path.relpath(target, ROOT)}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
