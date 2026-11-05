"""install.sh in a made-up home: stand-ins for kpackagetool6, gdbus and
GNOME's tools only note how they were called, so nothing is installed for
real."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = "#!/bin/sh\necho \"$(basename \"$0\") $*\" >> \"$STUB_LOG\"\n"


class InstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.bin = Path(tmp.name) / "bin"
        self.log = Path(tmp.name) / "stubs.log"
        self.home.mkdir()
        self.bin.mkdir()
        for name in ("kpackagetool6", "gdbus", "gnome-extensions", "gsettings"):
            self.stub(name, STUB)

    def stub(self, name, text):
        (self.bin / name).write_text(text)
        (self.bin / name).chmod(0o755)

    def install(self, *args, env=None):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
               "XDG_CURRENT_DESKTOP": "KDE", **(env or {})}
        return subprocess.run(["bash", str(ROOT / "install.sh"), "--yes", *args], capture_output=True, text=True,
                               env=env, stdin=subprocess.DEVNULL)

    def statusline(self, command, text):
        script = self.home / ".claude/statusline.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(text)
        script.chmod(0o750)
        (self.home / ".claude/settings.json").write_text('{"statusLine": {"type": "command", "command": "%s"}}' % command)
        return script

    def test_no_status_line_says_how_to_add_it(self):
        out = self.install()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("No Claude profile runs a status-line script", out.stdout)
        self.assertNotIn("not found:", out.stdout)

    def test_home_variable_and_no_last_newline(self):
        script = self.statusline("bash $HOME/.claude/statusline.sh", "#!/bin/bash\ninput=\"$(cat)\"")
        out = self.install()
        self.assertEqual(out.returncode, 0, out.stderr)
        text = script.read_text()
        self.assertTrue(text.startswith("#!/bin/bash\ninput=\"$(cat)\"\n# >>> talpy-den >>>\n"), text)
        self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o750)  # its mode kept
        self.assertEqual(len(list(script.parent.glob("statusline.sh.bak.*"))), 1)
        self.assertIn("already up to date", self.install().stdout)
        ran = subprocess.run(["bash", str(script)], input='{"session_id": "s1"}', capture_output=True, text=True,
                             env={**os.environ, "HOME": str(self.home)})
        self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_a_script_without_the_sh_suffix(self):
        script = self.statusline("~/.claude/statusline.sh", "")
        script.rename(self.home / ".claude/statusline")
        (self.home / ".claude/statusline").write_text("#!/bin/sh\ninput=$(cat)\necho ok\n")
        (self.home / ".claude/settings.json").write_text('{"statusLine": {"command": "~/.claude/statusline"}}')
        self.install()
        self.assertIn("# >>> talpy-den >>>", (self.home / ".claude/statusline").read_text())

    def test_the_script_vs_codes_wrapper_runs_is_left_alone(self):
        wrapped = self.home / ".claude/statusline"
        wrapped.parent.mkdir(parents=True)
        wrapped.write_text("#!/bin/bash\ninput=$(cat)\necho ok\n")
        wrapper = self.home / ".local/share/talpy-den/statusline.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/usr/bin/env bash\ninput=$(cat)\n# >>> talpy-den >>>\n# <<< talpy-den <<<\n")
        (self.home / ".claude/settings.json").write_text(json.dumps(
            {"statusLine": {"command": "%s '~/.claude/statusline'" % wrapper}}))
        self.install()
        self.assertEqual(wrapper.read_text().count("# >>> talpy-den >>>"), 1)
        self.assertNotIn("talpy-den", wrapped.read_text())

    def test_a_line_that_goes_on_isnt_the_place(self):
        script = self.statusline("~/.claude/statusline.sh", "#!/bin/sh\ninput=$(cat) && echo \"$input\"\n")
        out = self.install()
        self.assertIn("no 'input=$(cat)' line found", out.stderr)
        self.assertNotIn("talpy-den", script.read_text())

    def test_an_upgrade_replaces_the_snippet_and_hook_of_the_first_name(self):
        old = ("#!/bin/sh\ninput=$(cat)\n# >>> claude-widget >>>\n: old snippet\n# <<< claude-widget <<<\n")
        script = self.statusline("~/.claude/statusline.sh", old)
        hook = "python3 -I %s/.local/share/claude-widget/permission-hook.py" % self.home
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        settings["hooks"] = {"PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": hook}]}]}
        (self.home / ".claude/settings.json").write_text(json.dumps(settings))
        out = self.install()
        self.assertEqual(out.returncode, 0, out.stderr)
        text = script.read_text()
        self.assertNotIn("claude-widget", text)
        self.assertEqual(text.count("# >>> talpy-den >>>"), 1)
        settings = (self.home / ".claude/settings.json").read_text()
        self.assertNotIn("claude-widget", settings)
        self.assertEqual(settings.count("permission-hook.py"), 2)  # (one command: its check, then python3)
        self.assertIn(".local/share/talpy-den/permission-hook.py", settings)
        out = self.install("--uninstall")
        self.assertNotIn(">>>", script.read_text())

    def test_the_old_vs_code_extension_is_named_until_vs_code_uninstalled_it(self):
        extensions = self.home / ".vscode/extensions"
        (extensions / "wzaielamri.claude-status-1.15.2").mkdir(parents=True)
        hint = "The VS Code extension is now Talpy Den too"
        self.assertIn(hint, self.install().stdout)
        # (VS Code keeps an uninstalled one's folder until it starts again)
        (extensions / ".obsolete").write_text('{"wzaielamri.claude-status-1.15.2":true}')
        self.assertNotIn(hint, self.install().stdout)

    def test_uninstall_keeps_the_snippet_another_front_end_uses(self):
        script = self.statusline("~/.claude/statusline.sh", "#!/bin/sh\ninput=$(cat)\n")
        self.install()
        (self.home / ".vscode/extensions/wzaielamri.talpy-den-1.10.0").mkdir(parents=True)
        out = self.install("--uninstall")
        self.assertIn("Kept the status-line snippet: the VS Code extension still uses it.", out.stdout)
        self.assertIn("talpy-den", script.read_text())

    def test_the_permission_hook_with_plasma(self):
        self.statusline("~/.claude/statusline.sh", "#!/bin/sh\ninput=$(cat)\n")
        out = self.install()
        self.assertIn("Permission prompts can be answered from Talpy Den", out.stdout)
        settings = (self.home / ".claude/settings.json").read_text()
        self.assertIn(".local/share/talpy-den/permission-hook.py", settings)
        self.assertTrue((self.home / ".local/share/talpy-den/permission-hook.py").is_file())
        self.assertIn("the hook is up to date", self.install().stdout)  # (an upgrade keeps it, brought up to date)
        out = self.install("--uninstall")
        self.assertNotIn("permission-hook", (self.home / ".claude/settings.json").read_text())
        self.assertFalse((self.home / ".local/share/talpy-den/permission-hook.py").exists())

    @unittest.skipUnless(shutil.which("kwriteconfig6") and shutil.which("kreadconfig6"), "needs KDE's kwriteconfig6")
    def test_the_chat_panes_icon(self):
        rules = self.home / ".config/kwinrulesrc"
        rules.parent.mkdir(parents=True)
        mine = "[General]\ncount=1\nrules=mine\n\n[mine]\nDescription=my rule\n"
        rules.write_text(mine)
        out = self.install()
        self.assertIn("The chat pane shows Talpy in the taskbar", out.stdout)
        text = rules.read_text()
        self.assertIn("count=2\nrules=mine,talpy-den-chat-pane\n", text)
        self.assertIn("[talpy-den-chat-pane]\n", text)
        self.assertIn("title=— Talpy Chat\n", text)
        # (the rule matches the pane's title: the two can't drift apart)
        self.assertIn('"%1 — Talpy Chat"', (ROOT / "package/contents/ui/ChatPane.qml").read_text())
        self.assertIn("desktopfile=org.wzaielamri.talpyden.chat\ndesktopfilerule=2\n", text)
        self.assertIn("[mine]\nDescription=my rule\n", text)
        desktop = self.home / ".local/share/applications/org.wzaielamri.talpyden.chat.desktop"
        self.assertIn(f"Icon={self.home}/.local/share/plasma/plasmoids/org.wzaielamri.talpyden/contents/icons/talpy-chat.svg\n",
                      desktop.read_text())
        self.assertTrue((ROOT / "package/contents/icons/talpy-chat.svg").is_file())   # (Talpy Chat's icon: Talpa with a speech bubble)
        self.assertIn("org.kde.KWin.reconfigure", self.log.read_text())
        out = self.install()  # (an upgrade: the same rule, once)
        self.assertNotIn("The chat pane shows Talpy", out.stdout)
        self.assertIn("count=2\nrules=mine,talpy-den-chat-pane\n", rules.read_text())
        self.install("--uninstall")
        self.assertEqual(rules.read_text(), mine)
        self.assertFalse(desktop.exists())

    def test_widgets_of_the_first_name_stay_where_they_are_with_their_settings(self):
        rc = self.home / ".config/plasma-org.kde.plasma.desktop-appletsrc"
        rc.parent.mkdir(parents=True)
        layout = ("[Containments][2][Applets][7]\nimmutability=1\nplugin=org.wzaielamri.claudestatus\n\n"
                  "[Containments][2][Applets][7][Configuration][General]\nrecentChats=3\n\n"
                  "[Containments][2][Applets][8]\nplugin=org.kde.plasma.systemtray\n\n"
                  "[Containments][9][General]\nextraItems=org.kde.plasma.battery,org.wzaielamri.claudestatus\n"
                  "knownItems=org.wzaielamri.claudestatus,org.wzaielamri.talpyden\n\n"
                  "[Containments][9][Applets][10]\nplugin=org.wzaielamri.claudestatus\n"
                  "[Containments][9][Applets][11]\nplugin=org.wzaielamri.claudestatus.other\n")
        rc.write_text(layout)
        (self.home / ".local/share/plasma/plasmoids/org.wzaielamri.claudestatus").mkdir(parents=True)
        # plasmashell runs under systemd: stopped while its layout changes
        self.stub("systemctl", STUB + 'case "$*" in *stop*|*start*) grep -c claudestatus "$RC" >> "$STUB_LOG";; esac\n')
        out = self.install("--plasma", env={"RC": str(rc)})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Your 2 Claude Status widget(s) are now Talpy Den", out.stdout)
        self.assertIn("Widget installed in place of Claude Status.", out.stdout)
        self.assertNotIn("add Talpy Den to your panel", out.stdout)
        self.assertEqual(rc.read_text(), layout.replace("plugin=org.wzaielamri.claudestatus\n", "plugin=org.wzaielamri.talpyden\n")
                         .replace("battery,org.wzaielamri.claudestatus", "battery,org.wzaielamri.talpyden")
                         .replace("knownItems=org.wzaielamri.claudestatus,org.wzaielamri.talpyden", "knownItems=org.wzaielamri.talpyden"))
        (backup,) = rc.parent.glob(rc.name + ".bak.*")
        self.assertEqual(backup.read_text(), layout)
        calls = [line for line in self.log.read_text().splitlines()
                 if line.startswith(("kpackagetool6", "systemctl --user st")) or line.isdigit()]
        self.assertEqual(calls, ["kpackagetool6 -t Plasma/Applet -i %s/package" % ROOT,
                                 "systemctl --user stop plasma-plasmashell.service", "5",
                                 "systemctl --user start plasma-plasmashell.service", "1",  # (.claudestatus.other)
                                 "kpackagetool6 -t Plasma/Applet -r org.wzaielamri.claudestatus"])
        # (what kpackagetool6 did) nothing of the first name left: nothing to move again
        (self.home / ".local/share/plasma/plasmoids/org.wzaielamri.claudestatus").rmdir()
        self.assertNotIn("Claude Status widget", self.install("--plasma", env={"RC": str(rc)}).stdout)
        self.assertEqual(len(list(rc.parent.glob(rc.name + ".bak.*"))), 1)

    def test_the_gnome_extension_of_the_first_name_leaves_its_settings(self):
        (self.home / ".local/share/gnome-shell/extensions/claude-status@wzaielamri.github.io").mkdir(parents=True)
        (self.home / "dconf").mkdir()
        (self.home / "dconf/claude-status").write_text("[/]\nshow-pet=false\n")
        self.stub("dconf", '#!/bin/sh\nf="$HOME/dconf/$(basename "$2")"\n'
                           'case "$1" in dump) cat "$f" 2>/dev/null;; load) cat > "$f";; esac\n')
        self.stub("gnome-shell", "#!/bin/sh\necho 'GNOME Shell 49.1'\n")
        self.stub("glib-compile-schemas", STUB)
        out = self.install("--gnome")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Replaced the old Claude Status extension.", out.stdout)
        self.assertEqual((self.home / "dconf/talpy-den").read_text(), "[/]\nshow-pet=false\n")
        self.assertIn("gnome-extensions uninstall claude-status@wzaielamri.github.io", self.log.read_text())

    def test_gnome_45_to_48_refused(self):
        legacy = self.home / ".local/share/gnome-shell/extensions/claude-status@wzaielamri.github.io"
        legacy.mkdir(parents=True)
        self.stub("gnome-shell", "#!/bin/sh\necho 'GNOME Shell 46.0'\n")
        out = self.install("--gnome")
        self.assertEqual(out.returncode, 1)
        self.assertIn("GNOME Shell 46 isn't supported", out.stderr)
        log = self.log.read_text() if self.log.exists() else ""
        self.assertNotIn("gnome-extensions install", log)
        # the extension of the first name is left as it was
        self.assertTrue(legacy.is_dir())
        self.assertNotIn("claude-status", log)

    def test_a_failed_build_leaves_the_installed_extension(self):
        legacy = self.home / ".local/share/gnome-shell/extensions/claude-status@wzaielamri.github.io"
        legacy.mkdir(parents=True)
        self.stub("gnome-shell", "#!/bin/sh\necho 'GNOME Shell 43.9'\n")
        self.stub("glib-compile-schemas", "#!/bin/sh\nexit 1\n")
        self.stub("dconf", STUB)
        out = self.install("--gnome")
        self.assertNotEqual(out.returncode, 0)
        log = self.log.read_text() if self.log.exists() else ""
        self.assertTrue(legacy.is_dir())
        self.assertNotIn("Replaced the old Claude Status extension.", out.stdout)
        self.assertNotIn("claude-status", log)
        self.assertNotIn("gnome-extensions install", log)

    # (gnome/gnome43/port43.py, which install.sh runs there, needs Python 3.8;
    # the systems with GNOME 43 and 44 have 3.10 or newer)
    @unittest.skipIf(subprocess.run(["python3", "-c", "import sys; sys.exit(sys.version_info < (3, 8))"]).returncode,
                     "python3 is older than 3.8")
    def test_gnome_43_gets_the_converted_extension(self):
        legacy = self.home / ".local/share/gnome-shell/extensions/claude-status@wzaielamri.github.io"
        legacy.mkdir(parents=True)
        self.stub("gnome-shell", "#!/bin/sh\necho 'GNOME Shell 43.9'\n")
        self.stub("glib-compile-schemas", STUB)
        self.stub("dconf", STUB)
        out = self.install("--gnome")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Replaced the old Claude Status extension.", out.stdout)
        log = self.log.read_text()
        self.assertIn("gnome-extensions uninstall claude-status@wzaielamri.github.io", log)
        self.assertIn("gnome-extensions install --force", log)
        built = ROOT / "gnome/build/talpy-den@wzaielamri.github.io"
        self.assertEqual(json.loads((built / "metadata.json").read_text())["shell-version"], ["43", "44"])
        self.assertTrue((built / "compat43prefs.js").is_file())


if __name__ == "__main__":
    unittest.main()
