"""OSC In DAT callbacks for the TouchOSC VJ surface (TouchDesigner side).

Setup
-----
1. Add an ``OSC In DAT``, set Network Port to 7001 (must match
   ``spec/mapping.yaml`` -> connections.touchdesigner.port).
2. Set its callbacks DAT to a Text DAT holding this file.
3. Point the entries in ``MAPPING`` at the operators/parameters you want driven.

Anything not listed in ``MAPPING`` is still readable as a channel from a
parallel ``OSC In CHOP`` on the same port — the addresses are flat
(``/td/fader/1`` -> channel ``td/fader/1``) precisely so that works.
"""

# address -> (operator path, parameter name, low, high)
# Values arrive normalised 0..1 from TouchOSC and are scaled into [low, high].
MAPPING = {
    "/td/fader/1": ("/project1/geo1", "Sx", 0.0, 4.0),
    "/td/fader/2": ("/project1/geo1", "Sy", 0.0, 4.0),
    "/td/fader/3": ("/project1/noise1", "Amp", 0.0, 2.0),
    "/td/fader/4": ("/project1/noise1", "Period", 0.01, 8.0),
    "/td/pad/1/x": ("/project1/geo1", "Tx", -5.0, 5.0),
    "/td/pad/1/y": ("/project1/geo1", "Ty", -5.0, 5.0),
    "/td/intensity": ("/project1/level1", "Opacity", 0.0, 1.0),
    # Colour picker: the three channels arrive independently, already 0..1.
    "/td/color/r": ("/project1/constant1", "Colorr", 0.0, 1.0),
    "/td/color/g": ("/project1/constant1", "Colorg", 0.0, 1.0),
    "/td/color/b": ("/project1/constant1", "Colorb", 0.0, 1.0),
}

# Addresses that toggle a parameter on/off rather than scaling a range.
TOGGLES = {
    "/td/toggle/1": ("/project1/geo1", "Display"),
}

# Addresses that pulse a parameter once on the rising edge.
TRIGGERS = {
    "/td/trigger/1": ("/project1/moviefilein1", "Reloadpulse"),
}


def _first_float(args, default=0.0):
    for arg in args:
        try:
            return float(arg)
        except (TypeError, ValueError):
            continue
    return default


def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    value = _first_float(args)

    if address == "/td/blackout":
        for op_path, par_name, low, high in MAPPING.values():
            target = op(op_path)
            if target is not None and value >= 0.5:
                setattr(target.par, par_name, low)
        return

    entry = MAPPING.get(address)
    if entry is not None:
        op_path, par_name, low, high = entry
        target = op(op_path)
        if target is not None:
            setattr(target.par, par_name, low + (high - low) * value)
        return

    entry = TOGGLES.get(address)
    if entry is not None:
        op_path, par_name = entry
        target = op(op_path)
        if target is not None:
            setattr(target.par, par_name, value >= 0.5)
        return

    entry = TRIGGERS.get(address)
    if entry is not None and value >= 0.5:
        op_path, par_name = entry
        target = op(op_path)
        if target is not None:
            target.par[par_name].pulse()
        return

    debug(f"unmapped OSC address: {address} {args}")
