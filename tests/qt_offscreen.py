"""How the tests run Qt (PySide6, offscreen) without your session bus, and
without leaving anything running.

Your environment let Qt's KDE theme talk to your session bus; and under a bus
of their own (dbus-run-session: test_beat's, or the whole suite run so) it
started xdg-desktop-portal, ksecretd and the like on it, which outlived it
(2026-11-22). Now:

qt_env(**extra): os.environ for Qt offscreen, with DBUS_SESSION_BUS_ADDRESS
pointing nowhere (set, so libdbus doesn't autolaunch one): Qt reaches no
session bus at all, so it starts nothing and never uses yours.

plain=True: no desktop's theme (as with own_bus) and no display either, so
what a test measures doesn't depend on your desktop (test_scroll_smooth's
runner).

run_qt(argv, own_bus=False, timeout=60, plain=False, **extra): argv run so, as
subprocess.run(capture_output, text). own_bus: for a test that needs a bus
(test_beat's screen lock), one of its own (dbus-run-session) with no
desktop's theme (nothing gets started on it), its output through files (what
a bus starts holds pipes open), and whatever is still running from that bus
afterwards ended by pid (reap): the result's .bus and .reaped say which."""
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

NO_BUS = "unix:path=/nonexistent/talpy-den-tests-no-session-bus"
# (what makes Qt take the desktop's theme, which reaches xdg-desktop-portal over the bus)
DESKTOP = ("KDE_FULL_SESSION", "KDE_SESSION_VERSION", "KDE_SESSION_UID", "GNOME_DESKTOP_SESSION_ID")


def qt_env(own_bus=False, plain=False, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DBUS_SESSION_BUS_", "DBUS_STARTER_"))}
    env["QT_QPA_PLATFORM"] = "offscreen"
    if own_bus or plain:   # (no desktop's theme: nothing to start on a bus; and with plain, no display either)
        env = {k: v for k, v in env.items() if k not in DESKTOP + (("DISPLAY", "WAYLAND_DISPLAY") if plain else ())}
        env.update(QT_QPA_PLATFORMTHEME="", XDG_CURRENT_DESKTOP="", DESKTOP_SESSION="")
    if not own_bus:   # (dbus-run-session names its own)
        env["DBUS_SESSION_BUS_ADDRESS"] = NO_BUS
    env.update(extra)
    return env


def on_bus(addr):
    """{pid: name} of the processes whose environment names that session bus (started on it)."""
    want = [(k + "=" + addr.strip()).encode() + b"\0" for k in ("DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_ADDRESS")]
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            env = Path(f"/proc/{pid}/environ").read_bytes()
            name = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            continue
        if any(w in env for w in want):
            out[int(pid)] = name
    return out


def reap(addr):
    """End, by pid, what is still running from that session bus once it's gone: {pid: name} of those ended."""
    left = on_bus(addr)
    for pid in left:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 3
    while time.time() < deadline and any(Path(f"/proc/{pid}").exists() for pid in left):
        time.sleep(0.05)
    for pid in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return left


def run_qt(argv, own_bus=False, timeout=60, plain=False, **extra):
    env = qt_env(own_bus, plain, **extra)
    if not own_bus:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    with tempfile.TemporaryDirectory() as tmp:
        addr, out, err = (Path(tmp) / n for n in ("bus", "out", "err"))
        try:
            with open(out, "wb") as o, open(err, "wb") as e:
                done = subprocess.run(["dbus-run-session", "--", "sh", "-c", 'echo "$DBUS_SESSION_BUS_ADDRESS" > "$0"; exec "$@"',
                                       str(addr), *argv], stdin=subprocess.DEVNULL, stdout=o, stderr=e, timeout=timeout, env=env)
        finally:
            bus = addr.read_text().strip() if addr.exists() else ""
            reaped = reap(bus) if bus else {}
        r = subprocess.CompletedProcess(argv, done.returncode, out.read_text(errors="replace"), err.read_text(errors="replace"))
    r.bus, r.reaped = bus, reaped
    return r
