"""OSC In DAT callbacks for the TouchOSC surface (TouchDesigner side).

Setup
-----
1. Add an ``OSC In DAT``, Network Port 7001 (connections.touchdesigner.port
   in spec/mapping.yaml), Active on.
2. Paste this file into a Text DAT and point the OSC In DAT's
   **Callbacks DAT** parameter at it.
3. Fill in the tables below. Every value arrives from the iPad as 0..1 and is
   scaled into the low..high range given for it.

Parameter names are TouchDesigner's *internal* Python names: built-in
parameters are lowercase (``tx``, ``ry``, ``amp``, ``colorr``); custom
parameters start with a capital. Hover a parameter in TD to see its name.

A path or parameter that does not exist is reported once in the textport
rather than skipped silently, so a typo shows up instead of just doing nothing.

Only one operator can listen on a port: if this DAT has 7001, an OSC In CHOP
cannot also have it. Use one or the other.
"""

# Change this to your camera's path if it is not the default. The path is
# shown at the top of the camera's parameter window.
CAMERA = "/project1/cam1"

# address -> (operator path, parameter, low, high)
MAPPING = {
    # Pad 2 turns the camera: x pans left/right, y tilts up/down. The centre
    # of the pad is straight ahead. Swap low and high to invert an axis.
    "/td/pad/2/x": (CAMERA, "ry", -180.0, 180.0),
    "/td/pad/2/y": (CAMERA, "rx", -60.0, 60.0),

    # Examples, kept off until pointed at operators that exist in the project:
    # "/td/fader/1":   ("/project1/noise1", "amp", 0.0, 2.0),
    # "/td/pad/1/x":   ("/project1/geo1", "tx", -5.0, 5.0),
    # "/td/intensity": ("/project1/level1", "opacity", 0.0, 1.0),
    # "/td/color/r":   ("/project1/constant1", "colorr", 0.0, 1.0),
    # "/td/color/g":   ("/project1/constant1", "colorg", 0.0, 1.0),
    # "/td/color/b":   ("/project1/constant1", "colorb", 0.0, 1.0),
}

# address -> (operator path, parameter): on at >= 0.5, off below.
TOGGLES = {
    # "/td/toggle/1": ("/project1/geo1", "display"),
}

# address -> (operator path, parameter): pulsed once when pressed.
TRIGGERS = {
    # "/td/trigger/1": ("/project1/moviefilein1", "reloadpulse"),
}


_reported = set()


def _warn_once(key, text):
    """Say it once: these callbacks run on every message, many per second."""
    if key not in _reported:
        _reported.add(key)
        debug(text)


def _par(op_path, par_name, address):
    target = op(op_path)
    if target is None:
        _warn_once((address, "op"), f"{address}: no operator at {op_path}")
        return None
    par = getattr(target.par, par_name, None)
    if par is None:
        _warn_once((address, "par"),
                   f"{address}: {op_path} has no parameter '{par_name}' "
                   "(built-in names are lowercase)")
    return par


def _first_float(args, default=0.0):
    for arg in args:
        try:
            return float(arg)
        except (TypeError, ValueError):
            continue
    return default


def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    value = _first_float(args)

    entry = MAPPING.get(address)
    if entry is not None:
        op_path, par_name, low, high = entry
        par = _par(op_path, par_name, address)
        if par is not None:
            par.val = low + (high - low) * value
        return

    entry = TOGGLES.get(address)
    if entry is not None:
        par = _par(*entry, address)
        if par is not None:
            par.val = value >= 0.5
        return

    entry = TRIGGERS.get(address)
    if entry is not None:
        par = _par(*entry, address)
        if par is not None and value >= 0.5:
            par.pulse()
        return

    if address == "/td/blackout" and value >= 0.5:
        for op_path, par_name, low, high in MAPPING.values():
            par = _par(op_path, par_name, address)
            if par is not None:
                par.val = low
        return

    # Unmapped controls are normal while a project is half-wired; mention
    # each one once so the textport stays readable.
    _warn_once((address, "unmapped"), f"unmapped OSC address: {address}")
