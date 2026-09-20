"""Writer for the TouchOSC (Hexler, 2021+) ``.tosc`` layout format.

A ``.tosc`` file is a zlib-compressed XML document whose root element is
``<lexml version="3">`` holding a single root ``<node>``. Every node carries
``<properties>``, ``<values>``, ``<messages>`` and ``<children>``.

Property names and enum values follow NicoG60/TouchMCU, a working Mk2 layout
generator, rather than being inferred from the app's behaviour. Two details
that cost this project a round each on the device:

* a LABEL's caption is a *value* named ``text``; its ``color`` property is the
  background fill and ``textColor`` is the text;
* a pager's pages take their tab caption from a ``tabLabel`` property — the
  node's ``name`` is not used — and each page's frame must be offset below the
  tab bar, not drawn from the pager's top edge.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from xml.etree import ElementTree as ET

# Control types.
BOX = "BOX"
GROUP = "GROUP"
PAGER = "PAGER"
LABEL = "LABEL"
BUTTON = "BUTTON"
FADER = "FADER"
XY = "XY"
RADIAL = "RADIAL"

Color = tuple  # (r, g, b, a) floats 0-1

WHITE = (1.0, 1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0, 1.0)


class Shape(IntEnum):
    RECTANGLE = 1
    CIRCLE = 2
    TRIANGLE = 3
    DIAMOND = 4
    PENTAGON = 5
    HEXAGON = 6


class Outline(IntEnum):
    FULL = 0
    CORNERS = 1
    EDGES = 2


class Orientation(IntEnum):
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3


class AlignH(IntEnum):
    LEFT = 0
    RIGHT = 1
    CENTER = 2


class AlignV(IntEnum):
    TOP = 0
    BOTTOM = 1
    MIDDLE = 2


class ButtonType(IntEnum):
    MOMENTARY = 0
    TOGGLE_RELEASE = 1
    TOGGLE_PRESS = 2


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


def _prop(parent: ET.Element, ptype: str, key: str, value) -> None:
    p = ET.SubElement(parent, "property", {"type": ptype})
    ET.SubElement(p, "key").text = key
    v = ET.SubElement(p, "value")
    if ptype == "r":
        for axis, num in zip(("x", "y", "w", "h"), value):
            ET.SubElement(v, axis).text = str(int(num))
    elif ptype == "c":
        for chan, num in zip(("r", "g", "b", "a"), value):
            ET.SubElement(v, chan).text = f"{float(num):.6f}"
    elif ptype == "b":
        v.text = "1" if value else "0"
    else:
        v.text = str(value)


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

    def to_xml(self, parent: ET.Element) -> None:
        osc = ET.SubElement(parent, "osc", {
            "enabled": "1", "send": "1",
            "receive": "1" if self.receive else "0",
            "feedback": "0", "connections": self.conns,
        })
        triggers = ET.SubElement(osc, "triggers")
        trig = ET.SubElement(triggers, "trigger")
        ET.SubElement(trig, "var").text = "x"
        ET.SubElement(trig, "condition").text = self.trigger

        path = ET.SubElement(osc, "path")
        for part in self.path.strip("/").split("/"):
            ET.SubElement(path, "partial", {
                "type": "CONSTANT", "conversion": "STRING",
                "value": part, "scaleMin": "0", "scaleMax": "1",
            })

        args = ET.SubElement(osc, "arguments")
        for const in self.constant_args:
            ET.SubElement(args, "partial", {
                "type": "CONSTANT", "conversion": "FLOAT",
                "value": str(const), "scaleMin": "0", "scaleMax": "1",
            })
        if self.send_value:
            ET.SubElement(args, "partial", {
                "type": "VALUE", "conversion": "FLOAT",
                "value": "x", "scaleMin": "0", "scaleMax": "1",
            })


@dataclass
class Node:
    type: str
    frame: tuple                       # (x, y, w, h)
    name: str = ""
    color: Color = (0.25, 0.25, 0.25, 1.0)
    text: str = ""
    text_size: int = 14
    text_color: Color = WHITE
    outline: bool = True
    outline_style: int = Outline.CORNERS
    background: bool = True
    interactive: bool = True
    visible: bool = True
    corner_radius: int = 1
    shape: int | None = None           # BOX / BUTTON
    button_type: int | None = None
    orientation: int = Orientation.NORTH
    tab_label: str | None = None       # set on a pager's pages
    script: str = ""
    extra_props: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def add(self, child: "Node") -> "Node":
        self.children.append(child)
        return child

    def _properties(self, el: ET.Element) -> None:
        props = ET.SubElement(el, "properties")
        _prop(props, "s", "name", self.name)
        _prop(props, "s", "tag", "")
        _prop(props, "r", "frame", self.frame)
        _prop(props, "c", "color", self.color)
        _prop(props, "b", "visible", self.visible)
        _prop(props, "b", "interactive", self.interactive)
        _prop(props, "b", "background", self.background)
        _prop(props, "b", "outline", self.outline)
        _prop(props, "i", "outlineStyle", int(self.outline_style))
        _prop(props, "b", "grabFocus", False)
        _prop(props, "i", "pointerPriority", 0)
        _prop(props, "i", "cornerRadius", self.corner_radius)
        _prop(props, "i", "orientation", int(self.orientation))
        _prop(props, "s", "script", self.script)

        if self.shape is not None:
            _prop(props, "i", "shape", int(self.shape))
        if self.type == LABEL:
            _prop(props, "i", "font", 0)
            _prop(props, "i", "textSize", self.text_size)
            _prop(props, "i", "textLength", 0)
            _prop(props, "i", "textAlignH", int(AlignH.CENTER))
            _prop(props, "i", "textAlignV", int(AlignV.MIDDLE))
            _prop(props, "c", "textColor", self.text_color)
            _prop(props, "b", "textClip", True)
        if self.button_type is not None:
            _prop(props, "i", "buttonType", int(self.button_type))
            _prop(props, "b", "press", True)
            _prop(props, "b", "release", True)
            _prop(props, "b", "valuePosition", False)
        if self.tab_label is not None:
            # A page's tab caption; its node name is not used by the tab bar.
            _prop(props, "s", "tabLabel", self.tab_label)
            _prop(props, "c", "tabColorOff", (0.10, 0.10, 0.10, 1.0))
            _prop(props, "c", "tabColorOn", (0.25, 0.25, 0.25, 1.0))
            _prop(props, "c", "textColorOff", (0.70, 0.70, 0.72, 1.0))
            _prop(props, "c", "textColorOn", WHITE)
        for key, (ptype, value) in self.extra_props.items():
            _prop(props, ptype, key, value)

    def _values(self, el: ET.Element) -> None:
        values = ET.SubElement(el, "values")

        def _value(key: str, default: str) -> None:
            v = ET.SubElement(values, "value")
            ET.SubElement(v, "key").text = key
            ET.SubElement(v, "locked").text = "0"
            ET.SubElement(v, "lockedDefaultCurrent").text = "0"
            ET.SubElement(v, "defaultPull").text = "0"
            ET.SubElement(v, "default").text = default

        if self.type == LABEL:
            _value("text", self.text)
            return
        _value("touch", "false")
        if self.type in (BUTTON, FADER, XY, RADIAL, PAGER):
            _value("x", "0.0")
        if self.type == XY:
            _value("y", "0.0")

    def to_xml(self, parent: ET.Element | None = None) -> ET.Element:
        attrs = {"ID": node_id(), "type": self.type}
        el = ET.Element("node", attrs) if parent is None else ET.SubElement(parent, "node", attrs)
        self._properties(el)
        self._values(el)

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
