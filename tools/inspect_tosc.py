#!/usr/bin/env python3
"""Inspect any .tosc file: print its control tree and the properties/values
each control type carries.

Point it at a layout saved by the TouchOSC editor to learn the exact spelling
of properties this project has had to guess at, then diff against one of ours:

    python3 tools/inspect_tosc.py sample.tosc > /tmp/theirs.txt
    python3 tools/inspect_tosc.py build/vj-control-portrait.tosc > /tmp/ours.txt
    diff /tmp/theirs.txt /tmp/ours.txt

    python3 tools/inspect_tosc.py sample.tosc --type PAGER --full
"""

from __future__ import annotations

import argparse
import os
import zlib
from collections import defaultdict
from xml.etree import ElementTree as ET


def read_xml(path: str) -> ET.Element:
    data = open(path, "rb").read()
    if not data.lstrip().startswith(b"<"):
        data = zlib.decompress(data)
    return ET.fromstring(data)


def props_of(node: ET.Element) -> list[tuple[str, str, str]]:
    out = []
    for p in node.findall("./properties/property"):
        key = p.findtext("key") or ""
        value = p.find("value")
        if value is not None and len(value):
            text = " ".join(f"{c.tag}={c.text}" for c in value)
        else:
            text = (value.text if value is not None else "") or ""
        out.append((key, p.get("type", ""), text))
    return out


def values_of(node: ET.Element) -> list[tuple[str, str]]:
    return [(v.findtext("key") or "", v.findtext("default") or "")
            for v in node.findall("./values/value")]


def name_of(node: ET.Element) -> str:
    for key, _, text in props_of(node):
        if key == "name":
            return text
    return ""


def walk(node: ET.Element, depth: int, out: list, want: str | None, full: bool):
    ntype = node.get("type", "?")
    if want is None or ntype == want:
        indent = "  " * depth
        out.append(f"{indent}{ntype} name={name_of(node)!r}")
        if full or want:
            for key, ptype, text in props_of(node):
                out.append(f"{indent}  prop {key} ({ptype}) = {text}")
            for key, default in values_of(node):
                out.append(f"{indent}  value {key} = {default!r}")
            for osc in node.findall("./messages/osc"):
                parts = [p.get("value", "") for p in osc.findall("./path/partial")]
                out.append(f"{indent}  osc /{'/'.join(parts)} "
                           f"conns={osc.get('connections')}")
    kids = node.find("children")
    for kid in (list(kids) if kids is not None else []):
        walk(kid, depth + 1, out, want, full)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("-t", "--type", help="only show controls of this type, in full")
    ap.add_argument("-f", "--full", action="store_true",
                    help="show properties and values for every control")
    ap.add_argument("-s", "--summary", action="store_true",
                    help="show which property keys each control type uses")
    args = ap.parse_args()

    root = read_xml(args.path)
    node = root.find("node") if root.tag == "lexml" else root

    if args.summary:
        keys: dict[str, set] = defaultdict(set)
        vals: dict[str, set] = defaultdict(set)
        counts: dict[str, int] = defaultdict(int)
        for n in node.iter("node"):
            t = n.get("type", "?")
            counts[t] += 1
            keys[t].update(f"{k}({p})" for k, p, _ in props_of(n))
            vals[t].update(k for k, _ in values_of(n))
        for t in sorted(counts):
            print(f"{t}  x{counts[t]}")
            print(f"  properties: {', '.join(sorted(keys[t]))}")
            print(f"  values:     {', '.join(sorted(vals[t])) or '-'}")
        return 0

    out: list[str] = []
    walk(node, 0, out, args.type, args.full)
    print("\n".join(out) if out else f"no {args.type} controls found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
