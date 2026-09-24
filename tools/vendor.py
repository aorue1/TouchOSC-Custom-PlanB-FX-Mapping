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
TEXTINPUT_TOSC = os.path.join(ROOT, "vendor", "textinput.tosc")


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
TEXTINPUT_TAG = "vendor:tshoppa-textinput"


def _set_tag(node: ET.Element, tag: str) -> None:
    value = _props(node).get("tag")
    if value is None:
        prop = ET.SubElement(node.find("properties"), "property", {"type": "s"})
        ET.SubElement(prop, "key").text = "tag"
        value = ET.SubElement(prop, "value")
    value.text = tag


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


def _scale(node: ET.Element, factor: float) -> None:
    """Scale a control and everything under it about the group's origin."""
    x, y, w, h = _frame_of(node)
    _set_frame(node, round(x * factor), round(y * factor),
               round(w * factor), round(h * factor))
    kids = node.find("children")
    for kid in (list(kids) if kids is not None else []):
        _scale(kid, factor)


def _fit_children(group: ET.Element, width: int, height: int,
                  margin: int = 8) -> None:
    """Centre a component whose parts are laid out loose, scaling to fit.

    The keyboard is built for a 1024x768 document and is 826pt wide, which
    does not fit an 820pt-wide portrait layout, so it is scaled down before
    being centred rather than hanging off the edge.
    """
    kids = group.find("children")
    children = list(kids) if kids is not None else []
    if not children:
        return

    frames = [_frame_of(c) for c in children]
    left = min(f[0] for f in frames)
    top = min(f[1] for f in frames)
    right = max(f[0] + f[2] for f in frames)
    bottom = max(f[1] + f[3] for f in frames)

    factor = min(1.0, (width - 2 * margin) / (right - left),
                 (height - 2 * margin) / (bottom - top))
    if factor < 1.0:
        for child in children:
            _scale(child, factor)
        left, top = left * factor, top * factor
        right, bottom = right * factor, bottom * factor

    dx = round((width - (right - left)) / 2 - left)
    dy = round((height - (bottom - top)) / 2 - top)
    for child in children:
        x, y, w, h = _frame_of(child)
        _set_frame(child, x + dx, y + dy, w, h)


def _component(path: str, group_name: str, dialog_name: str,
               width: int, height: int, tag: str) -> ET.Element:
    """Lift one modal component out of a vendored layout.

    Each of these is an overlay that covers the whole surface — so its dim
    pane can grey out what is behind the dialog — with the dialog itself
    centred inside. Both ship with ``visible = 0`` and show themselves when
    notified.
    """
    raw = zlib.decompress(open(path, "rb").read())
    root = ET.fromstring(raw).find("node")
    group = _find(root, group_name)
    if group is None:
        raise ValueError(f"no {group_name} group in {path}")

    group = copy.deepcopy(group)
    _set_frame(group, 0, 0, width, height)
    _set_tag(group, tag)

    dialog = _find(group, dialog_name) if dialog_name else None
    if dialog is not None:
        _, _, dw, dh = _frame_of(dialog)
        _set_frame(dialog, (width - dw) // 2, (height - dh) // 2, dw, dh)
    else:
        _fit_children(group, width, height)
    return group


def color_picker(width: int, height: int, path: str = PICKER_TOSC) -> ET.Element:
    """The ColorPicker overlay, framed to a width x height document."""
    return _component(path, "ColorPicker", "ColorDialog", width, height,
                      VENDOR_TAG)


def text_input(width: int, height: int, path: str = TEXTINPUT_TOSC) -> ET.Element:
    """The TextInput keyboard overlay, framed to a width x height document."""
    return _component(path, "TextInput", "", width, height, TEXTINPUT_TAG)


if __name__ == "__main__":
    for label, el, dialog in (("ColorPicker", color_picker(1180, 820), "ColorDialog"),
                              ("TextInput", text_input(1180, 820), "TextInputDialog")):
        print(f"{label}: {len(list(el.iter('node')))} controls, frame {_frame_of(el)}")
        dlg = _find(el, dialog)
        print(f"  dialog at {_frame_of(dlg) if dlg is not None else '(not found)'}")
