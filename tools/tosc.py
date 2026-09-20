"""Minimal writer for the TouchOSC (Hexler, 2021+) ``.tosc`` layout format.

A ``.tosc`` file is a zlib-compressed XML document whose root element is
``<lexml version="3">`` holding a single root ``<node>``. Every node carries
``<properties>``, ``<values>``, ``<messages>`` and ``<children>``.

This module deliberately covers only what the VJ layout needs: groups, pagers,
labels, buttons, faders and XY pads, each with a single outgoing OSC message.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

# Control types used by this project. TouchOSC knows more of them.
GROUP = "GROUP"
PAGER = "PAGER"
LABEL = "LABEL"
BUTTON = "BUTTON"
FADER = "FADER"
XY = "XY"
RADIAL = "RADIAL"

Color = tuple  # (r, g, b, a) floats 0-1


# Node IDs are derived from a counter rather than uuid4 so that two builds of
# an unchanged spec produce an identical file and diffs stay readable.
_ID_NAMESPACE = uuid.UUID("6f1a1d6c-2f5b-4a3e-9f8a-7c2d4b1e0a55")
_id_counter = 0


def reset_ids() -> None:
    global _id_counter
    _id_counter = 0


def node_id() -> str:
    global _id_counter
    _id_counter += 1
    return str(uuid.uuid5(_ID_NAMESPACE, f"node-{_id_counter}"))


def _prop(parent: ET.Element, ptype: str, key: str, value) -> ET.Element:
    p = ET.SubElement(parent, "property", {"type": ptype})
    ET.SubElement(p, "key").text = key
    if ptype == "r":  # rectangle / frame
        v = ET.SubElement(p, "value")
        for axis, num in zip(("x", "y", "w", "h"), value):
            ET.SubElement(v, axis).text = str(int(num))
    elif ptype == "c":  # color
        v = ET.SubElement(p, "value")
        for chan, num in zip(("r", "g", "b", "a"), value):
            ET.SubElement(v, chan).text = f"{float(num):.6f}"
    else:
        ET.SubElement(p, "value").text = str(value)
    return p


def connections(*slots: int) -> str:
    """Build TouchOSC's 5-character connection mask, e.g. slot 1 -> "10000"."""
    mask = ["0"] * 5
    for slot in slots:
        if not 1 <= slot <= 5:
            raise ValueError(f"connection slot out of range: {slot}")
        mask[slot - 1] = "1"
    return "".join(mask)


@dataclass
class OscMessage:
    """One outgoing OSC message attached to a control."""

    path: str
    conns: str
    send_value: bool = True          # append the control's value as a float
    constant_args: tuple = ()        # extra fixed float arguments, sent first
    trigger: str = "ANY"             # ANY | RISE | FALL
    receive: bool = True

    def to_xml(self, parent: ET.Element) -> ET.Element:
        osc = ET.SubElement(
            parent,
            "osc",
            {
                "enabled": "1",
                "send": "1",
                "receive": "1" if self.receive else "0",
                "feedback": "0",
                "connections": self.conns,
            },
        )
        triggers = ET.SubElement(osc, "triggers")
        trig = ET.SubElement(triggers, "trigger")
        ET.SubElement(trig, "var").text = "x"
        ET.SubElement(trig, "condition").text = self.trigger

        path = ET.SubElement(osc, "path")
        for part in self.path.strip("/").split("/"):
            ET.SubElement(
                path,
                "partial",
                {
                    "type": "CONSTANT",
                    "conversion": "STRING",
                    "value": part,
                    "scaleMin": "0",
                    "scaleMax": "1",
                },
            )

        args = ET.SubElement(osc, "arguments")
        for const in self.constant_args:
            ET.SubElement(
                args,
                "partial",
                {
                    "type": "CONSTANT",
                    "conversion": "FLOAT",
                    "value": str(const),
                    "scaleMin": "0",
                    "scaleMax": "1",
                },
            )
        if self.send_value:
            ET.SubElement(
                args,
                "partial",
                {
                    "type": "VALUE",
                    "conversion": "FLOAT",
                    "value": "x",
                    "scaleMin": "0",
                    "scaleMax": "1",
                },
            )
        return osc


@dataclass
class Node:
    type: str
    frame: tuple                       # (x, y, w, h)
    name: str = ""
    color: Color | None = None
    text: str = ""
    text_size: int = 14
    outline: bool = True
    background: bool = True
    button_type: int | None = None     # 0 momentary, 1 toggle-release, 2 toggle-press
    response: int | None = None
    orientation: int | None = None     # FADER: 0 vertical, 1 horizontal
    extra_props: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def add(self, child: "Node") -> "Node":
        self.children.append(child)
        return child

    def to_xml(self, parent: ET.Element | None = None) -> ET.Element:
        attrs = {"ID": node_id(), "type": self.type}
        el = ET.Element("node", attrs) if parent is None else ET.SubElement(parent, "node", attrs)

        props = ET.SubElement(el, "properties")
        _prop(props, "s", "name", self.name)
        _prop(props, "r", "frame", self.frame)
        if self.color is not None:
            _prop(props, "c", "color", self.color)
        _prop(props, "b", "background", 1 if self.background else 0)
        _prop(props, "b", "outline", 1 if self.outline else 0)
        if self.type == LABEL or self.text:
            _prop(props, "s", "text", self.text)
            _prop(props, "i", "textSize", self.text_size)
            _prop(props, "i", "textAlignH", 2)  # centre
        if self.button_type is not None:
            _prop(props, "i", "buttonType", self.button_type)
        if self.response is not None:
            _prop(props, "i", "response", self.response)
        if self.orientation is not None:
            _prop(props, "i", "orientation", self.orientation)
        for key, (ptype, value) in self.extra_props.items():
            _prop(props, ptype, key, value)

        values = ET.SubElement(el, "values")
        val = ET.SubElement(values, "value")
        key = "touch" if self.type in (BUTTON, LABEL, GROUP, PAGER) else "x"
        ET.SubElement(val, "key").text = key
        ET.SubElement(val, "locked").text = "0"
        ET.SubElement(val, "lockedDefaultCurrent").text = "0"
        ET.SubElement(val, "default").text = "false" if key == "touch" else "0.0"
        ET.SubElement(val, "defaultPull").text = "0"
        if self.type in (BUTTON, FADER, XY, RADIAL):
            xval = ET.SubElement(values, "value")
            ET.SubElement(xval, "key").text = "x"
            ET.SubElement(xval, "locked").text = "0"
            ET.SubElement(xval, "lockedDefaultCurrent").text = "0"
            ET.SubElement(xval, "default").text = "0.0"
            ET.SubElement(xval, "defaultPull").text = "0"
        if self.type == XY:
            yval = ET.SubElement(values, "value")
            ET.SubElement(yval, "key").text = "y"
            ET.SubElement(yval, "locked").text = "0"
            ET.SubElement(yval, "lockedDefaultCurrent").text = "0"
            ET.SubElement(yval, "default").text = "0.0"
            ET.SubElement(yval, "defaultPull").text = "0"

        messages = ET.SubElement(el, "messages")
        for msg in self.messages:
            msg.to_xml(messages)

        kids = ET.SubElement(el, "children")
        for child in self.children:
            child.to_xml(kids)
        return el


def to_xml_bytes(root: Node) -> bytes:
    reset_ids()
    lexml = ET.Element("lexml", {"version": "3"})
    lexml.append(root.to_xml())
    ET.indent(lexml, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(lexml, encoding="utf-8")


def write(root: Node, tosc_path: str, xml_path: str | None = None) -> None:
    raw = to_xml_bytes(root)
    with open(tosc_path, "wb") as fh:
        fh.write(zlib.compress(raw))
    if xml_path:
        with open(xml_path, "wb") as fh:
            fh.write(raw)
