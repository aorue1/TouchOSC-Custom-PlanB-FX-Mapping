#!/usr/bin/env python3
"""Lift third-party components out of a vendored .tosc and graft them into ours.

Currently just the ColorPicker from vendor/colorpicker-swatches.tosc. The
component's controls and scripts are used unmodified — only its frame and the
position of its dialog are adjusted, because the component is documented as
something you resize to cover the document and then centre the dialog inside.
"""

from __future__ import annotations

import copy
import os
import zlib
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKER_TOSC = os.path.join(ROOT, "vendor", "colorpicker-swatches.tosc")


def _props(node: ET.Element) -> dict:
    out = {}
    for p in node.findall("./properties/property"):
        key = p.findtext("key") or ""
        value = p.find("value")
        out[key] = value
    return out


def _name(node: ET.Element) -> str:
    value = _props(node).get("name")
    return (value.text if value is not None else "") or ""


def _find(node: ET.Element, name: str):
    if _name(node) == name:
        return node
    kids = node.find("children")
    for kid in (list(kids) if kids is not None else []):
        found = _find(kid, name)
        if found is not None:
            return found
    return None


# Marks a grafted subtree. tools/verify.py checks where such a component sits
# but not how it is built inside: its internals are its author's business.
VENDOR_TAG = "vendor:tshoppa-colorpicker"


def _set_tag(node: ET.Element, tag: str) -> None:
    value = _props(node).get("tag")
    if value is None:
        prop = ET.SubElement(node.find("properties"), "property", {"type": "s"})
        ET.SubElement(prop, "key").text = "tag"
        value = ET.SubElement(prop, "value")
    value.text = tag


# The one edit made to a vendored component's internals: its dials and colour
# field also keep the touch once a drag starts, matching the rest of the
# surface. The current picker already sets this on all five of its continuous
# controls — its author had the same problem — so this changes nothing today
# and guarantees it for whatever gets vendored next.
GRABBING = {"FADER", "RADIAL", "XY", "ENCODER", "RADAR"}


def _grab_focus(node: ET.Element) -> int:
    changed = 0
    if node.get("type") in GRABBING:
        value = _props(node).get("grabFocus")
        if value is None:
            prop = ET.SubElement(node.find("properties"), "property",
                                 {"type": "b"})
            ET.SubElement(prop, "key").text = "grabFocus"
            value = ET.SubElement(prop, "value")
        value.text = "1"
        changed = 1
    kids = node.find("children")
    for kid in (list(kids) if kids is not None else []):
        changed += _grab_focus(kid)
    return changed


def _set_frame(node: ET.Element, x: int, y: int, w: int, h: int) -> None:
    value = _props(node).get("frame")
    if value is None:
        raise ValueError(f"control {_name(node)!r} has no frame")
    for axis, num in zip(("x", "y", "w", "h"), (x, y, w, h)):
        el = value.find(axis)
        if el is None:
            el = ET.SubElement(value, axis)
        el.text = str(int(num))


def _frame_of(node: ET.Element) -> tuple:
    value = _props(node)["frame"]
    return tuple(int(value.findtext(a) or 0) for a in ("x", "y", "w", "h"))


def _component(path: str, group_name: str, dialog_name: str,
               width: int, height: int, tag: str) -> ET.Element:
    """Lift one modal component out of a vendored layout.

    The component is an overlay covering the whole surface — so its dim pane
    can grey out what is behind the dialog — with the dialog centred inside.
    It ships with ``visible = 0`` and shows itself when notified.
    """
    raw = zlib.decompress(open(path, "rb").read())
    root = ET.fromstring(raw).find("node")
    group = _find(root, group_name)
    if group is None:
        raise ValueError(f"no {group_name} group in {path}")

    group = copy.deepcopy(group)
    _set_frame(group, 0, 0, width, height)
    _set_tag(group, tag)
    _grab_focus(group)

    dialog = _find(group, dialog_name)
    if dialog is not None:
        _, _, dw, dh = _frame_of(dialog)
        _set_frame(dialog, (width - dw) // 2, (height - dh) // 2, dw, dh)
    return group


def color_picker(width: int, height: int, path: str = PICKER_TOSC) -> ET.Element:
    """The ColorPicker overlay, framed to a width x height document."""
    return _component(path, "ColorPicker", "ColorDialog", width, height,
                      VENDOR_TAG)



if __name__ == "__main__":
    el = color_picker(1180, 820)
    grabbing = sum(1 for n in el.iter("node") if n.get("type") in GRABBING)
    print(f"ColorPicker: {len(list(el.iter('node')))} controls "
          f"({grabbing} grabbing focus), frame {_frame_of(el)}")
    dlg = _find(el, "ColorDialog")
    print(f"  dialog centred at {_frame_of(dlg)}")
