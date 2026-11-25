#!/usr/bin/env python3
"""The refresh rate of the screen a Talpy Chat window is on, as Plasma knows it.

    python3 -I screen_rate.py NAME

NAME is the screen's name as Qt gives it (QML's Screen.name: on Plasma, the
output's connector, such as eDP-1 or DP-2). Asks Plasma's kscreen-doctor
(-j: each output, its modes and the one it's in) and prints one JSON line:

    {"ok": true, "name": "eDP-1", "hz": 60.033, "rates": [59.882, 59.946, 60.033]}

the refresh rate of that output's current mode, and those of all its modes;
or, when kscreen-doctor isn't there, fails, or has no output on by that name,

    {"ok": false, "rates": [...], "message": "..."}

(rates: every output's modes, when it could say). An empty NAME (a platform
that names no screen) is the output that is on, when only one is.

Talpy Chat's scroller (WheelScroll.qml, wheel.mjs) steps its list once each
frame its window draws, and how far each step goes is the screen's frame: it
asks this once as it starts, and again when its window moves to another
screen. Nothing else runs it.

Python 3.7+ and the standard library only.
"""

import json
import shutil
import subprocess
import sys


def doctor():
    """kscreen-doctor -j's answer (a dict), or why there is none (a str)."""
    exe = shutil.which("kscreen-doctor")
    if not exe:
        return "kscreen-doctor isn't installed"
    try:
        r = subprocess.run([exe, "-j"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "kscreen-doctor didn't answer: {}".format(exc)
    if r.returncode != 0:
        said = r.stderr.decode("utf-8", "replace").strip().splitlines()
        return "kscreen-doctor failed: " + (said[-1] if said else "exit {}".format(r.returncode))
    out = r.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(out[out.find("{"):]) if "{" in out else None
    except ValueError:
        data = None
    return data if isinstance(data, dict) else "kscreen-doctor's answer isn't one it knows"


def hz_of(mode):
    """A mode's refresh rate (a second's frames, rounded to a thousandth), or None."""
    rate = mode.get("refreshRate") if isinstance(mode, dict) else None
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and 1 <= rate <= 1000:
        return round(float(rate), 3)
    return None


def current_hz(output):
    """The refresh rate of the mode an output is in, or None."""
    current = str(output.get("currentModeId"))
    for mode in output.get("modes") or []:
        if isinstance(mode, dict) and str(mode.get("id")) == current:
            return hz_of(mode)
    return None


def rates_of(outputs):
    return sorted({r for o in outputs for r in (hz_of(m) for m in o.get("modes") or []) if r is not None})


def rate_of(data, name):
    """What screen NAME's refresh rate is, from kscreen-doctor's answer (see the module's text)."""
    outputs = [o for o in data.get("outputs") or [] if isinstance(o, dict)]
    on = [o for o in outputs if o.get("enabled") and current_hz(o) is not None]
    if name:
        match = [o for o in on if o.get("name") == name]
    else:
        match = on if len(on) == 1 else []
    if match:
        o = match[0]
        return {"ok": True, "name": o.get("name") or "", "hz": current_hz(o), "rates": rates_of([o])}
    why = "no screen on is named {}".format(name) if name else "the window's screen has no name, and {} are on".format(len(on))
    return {"ok": False, "rates": rates_of(outputs), "message": why}


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1:
        sys.exit(__doc__)
    data = doctor()
    result = rate_of(data, args[0]) if isinstance(data, dict) else {"ok": False, "rates": [], "message": data}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
