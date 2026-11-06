import claude_guard  # noqa: F401  (first: no test runs the real claude)
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
spec = importlib.util.spec_from_file_location("notify_sound", CODE / "notify_sound.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


class Patch:
    def __init__(self, **attrs):
        self.attrs, self.saved = attrs, {}

    def __enter__(self):
        for k, v in self.attrs.items():
            self.saved[k] = getattr(ns, k)
            setattr(ns, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(ns, k, v)


def which(available):
    return type("W", (), {"which": staticmethod(lambda n: f"/usr/bin/{n}" if n in available else None)})


class FindSoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sounds"
        for path in ("ocean/stereo/complete.oga", "freedesktop/stereo/complete.oga",
                     "freedesktop/stereo/bell.oga", "mine/stereo/dialog-error.wav", "parent/stereo/bell.ogg"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_bytes(b"x")
        (self.root / "mine/index.theme").write_text("[Sound Theme]\nName=Mine\nInherits=parent\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_theme_then_inherited_then_freedesktop(self):
        dirs = [self.root]
        self.assertEqual(ns.find_sound("complete", dirs, "ocean"), self.root / "ocean/stereo/complete.oga")
        self.assertEqual(ns.find_sound("bell", dirs, "ocean"), self.root / "freedesktop/stereo/bell.oga")
        self.assertEqual(ns.find_sound("bell", dirs, "mine"), self.root / "parent/stereo/bell.ogg")
        self.assertEqual(ns.find_sound("dialog-error", dirs, "mine"), self.root / "mine/stereo/dialog-error.wav")
        self.assertIsNone(ns.find_sound("nope", dirs, "ocean"))
        self.assertEqual(ns.find_sound("nope, bell,complete", dirs, "ocean"), self.root / "freedesktop/stereo/bell.oga")
        self.assertIsNone(ns.find_sound("", dirs, "ocean"))

    def test_file_paths_and_urls(self):
        f = self.root / "ocean/stereo/complete.oga"
        self.assertEqual(ns.find_sound(str(f)), f)
        self.assertEqual(ns.find_sound("file://" + str(f).replace("/", "/")), f)
        spaced = Path(self.tmp.name) / "my sounds/ding.wav"
        spaced.parent.mkdir()
        spaced.write_bytes(b"x")
        self.assertEqual(ns.find_sound("file://" + str(spaced).replace(" ", "%20")), spaced)
        self.assertIsNone(ns.find_sound(str(self.root / "missing.oga")))

    def test_theme_name_from_gtk_settings(self):
        config = Path(self.tmp.name) / "config"
        (config / "gtk-3.0").mkdir(parents=True)
        (config / "gtk-3.0/settings.ini").write_text("[Settings]\ngtk-sound-theme-name = freedesktop\n")
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config)
        try:
            self.assertEqual(ns.theme_name(), "freedesktop")
            (config / "gtk-3.0/settings.ini").write_text("[Settings]\n")
            self.assertEqual(ns.theme_name(), "ocean")
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME")
            else:
                os.environ["XDG_CONFIG_HOME"] = old


class PlayerTests(unittest.TestCase):
    def test_prefers_pipewire_with_notification_role(self):
        with Patch(shutil=which({"pw-play", "paplay"})):
            self.assertEqual(ns.player_command(Path("/s/a.oga"), 80),
                             ["pw-play", "--media-role=Notification", "--volume=0.80", "/s/a.oga"])
        with Patch(shutil=which({"paplay"})):
            self.assertEqual(ns.player_command(Path("/s/a.oga"), 50), ["paplay", "--volume=32768", "/s/a.oga"])
        with Patch(shutil=which({"canberra-gtk-play"})):
            cmd = ns.player_command(Path("/s/a.oga"), 100)
            self.assertEqual(cmd[:3] + cmd[4:5], ["canberra-gtk-play", "-f", "/s/a.oga", "0.0"])
        with Patch(shutil=which({"aplay"})):
            self.assertIsNone(ns.player_command(Path("/s/a.oga"), 100))
            self.assertEqual(ns.player_command(Path("/s/a.wav"), 100), ["aplay", "-q", "/s/a.wav"])
        with Patch(shutil=which(set())):
            self.assertIsNone(ns.player_command(Path("/s/a.oga"), 100))

    def test_do_not_disturb(self):
        def run(out, code=0):
            return type("S", (), {"run": staticmethod(lambda *a, **k: type("R", (), {"returncode": code, "stdout": out})()),
                                  "TimeoutExpired": TimeoutError})
        with Patch(shutil=which({"gdbus"}), subprocess=run("(<true>,)\n")):
            self.assertTrue(ns.do_not_disturb())
        with Patch(shutil=which({"gdbus"}), subprocess=run("(<false>,)\n")):
            self.assertFalse(ns.do_not_disturb())
        with Patch(shutil=which({"gdbus"}), subprocess=run("", 1)):
            self.assertFalse(ns.do_not_disturb())  # no notification server: play anyway
        with Patch(shutil=which(set())):
            self.assertFalse(ns.do_not_disturb())

    def test_play_respects_do_not_disturb_unless_forced(self):
        started = []
        fake = type("S", (), {"Popen": staticmethod(lambda cmd, **k: started.append(cmd)), "DEVNULL": None})
        with tempfile.NamedTemporaryFile(suffix=".oga") as f:
            with Patch(do_not_disturb=lambda: True, subprocess=fake, shutil=which({"pw-play"})):
                self.assertEqual(ns.play(f.name, 80), (True, "Quiet: Do Not Disturb is on"))
                self.assertEqual(started, [])
                ok, msg = ns.play(f.name, 80, force=True)
                self.assertTrue(ok, msg)
            with Patch(do_not_disturb=lambda: False, subprocess=fake, shutil=which({"pw-play"})):
                self.assertEqual(ns.play(f.name, 0), (True, "Muted"))
                ok, msg = ns.play(f.name, 40)
                self.assertTrue(ok, msg)
            self.assertEqual([c[0] for c in started], ["pw-play", "pw-play"])
            with Patch(do_not_disturb=lambda: False, subprocess=fake, shutil=which(set())):
                self.assertEqual(ns.play(f.name, 40)[0], False)

    def test_main_prints_json(self):
        out = io.StringIO()
        with Patch(play=lambda sound, volume, force: (True, f"{sound} {volume} {force}")), redirect_stdout(out):
            ns.main(["complete", "--volume", "55", "--force"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": True, "message": "complete 55 True"})

    def test_theme_named_on_the_command_line(self):
        """GNOME keeps its sound theme in its own settings: the extension names it."""
        out = io.StringIO()
        with Patch(play=lambda sound, volume, force, theme=None: (True, f"{sound} {theme}")), redirect_stdout(out):
            ns.main(["complete", "--theme", "Yaru"])
        self.assertEqual(json.loads(out.getvalue())["message"], "complete Yaru")
        looked = []
        with tempfile.NamedTemporaryFile(suffix=".oga") as f:
            fake = type("S", (), {"Popen": staticmethod(lambda cmd, **k: None), "DEVNULL": None})
            with Patch(do_not_disturb=lambda: False, subprocess=fake, shutil=which({"pw-play"}),
                       find_sound=lambda sound, theme=None: looked.append(theme) or Path(f.name)):
                ns.play("complete", 50, theme="Yaru")
                ns.play("complete", 50)
        self.assertEqual(looked, ["Yaru", None])


if __name__ == "__main__":
    unittest.main()
