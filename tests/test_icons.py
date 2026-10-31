"""One icon per meaning in every front end (package/contents/ui/icons.mjs),
plain in the theme's text color unless it says something is wrong."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "package/contents/ui"
WEBVIEW = REPO / "vscode/webview"
GNOME = REPO / "gnome/extension"
BREEZE = Path("/usr/share/icons/breeze")
# Breeze's colors other than its text color (as written in its SVGs)
COLORS = re.compile(r"ColorScheme-(?:Negative|Positive|Neutral)Text|ColorScheme-Highlight\b|ColorScheme-Accent"
                    r"|#(?:27ae60|da4453|f67400|3daee9|1d99f3|fdbc4b|e74c3c|2980b9|8e44ad|16a085|f47750|9b59b6)", re.I)
SIZES = ("16", "22", "24")   # (the sizes the buttons and marks draw them at)
APPS = {"vscodeApp"}         # (an app's own icon, from the app: not Breeze's)


def table():
    """The table as {meaning: [plasma, vscode, gnome]} and its colored meanings, read by Node."""
    script = ("import * as I from %s;\n"
              "const t = {}; for (const m of I.meanings) t[m] = [I.plasma[m], I.vscode[m], I.gnome[m]];\n"
              "console.log(JSON.stringify({table: t, colored: I.COLORED}));\n") % json.dumps((UI / "icons.mjs").as_uri())
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    return data["table"], data["colored"]


def breeze_files(name):
    return [p for size in SIZES for p in BREEZE.glob(f"*/{size}/{name}.svg")]


def colored(name):
    """The Breeze files of that name (any context, at the sizes used) that draw in a color"""
    return [str(p.relative_to(BREEZE)) for p in breeze_files(name) if COLORS.search(p.resolve().read_text(errors="replace"))]


@unittest.skipUnless(shutil.which("node"), "needs node")
class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.colored = table()

    def test_every_meaning_has_a_plasma_and_gnome_icon(self):
        for meaning, (plasma, _, gnome) in self.table.items():
            self.assertTrue(plasma, meaning)
            self.assertTrue(gnome, meaning)

    def test_the_webview_asks_only_for_what_it_draws(self):
        used = set()
        for f in list((WEBVIEW / "components").glob("*.tsx")) + [WEBVIEW / "chat.tsx"]:
            used |= set(re.findall(r"\bI\.(\w+)", f.read_text()))
        self.assertTrue(used)
        self.assertEqual(sorted(m for m in used if self.table.get(m, [0, None])[1] is None), [])

    def test_the_vscode_icons_are_drawn(self):
        shapes = set(re.findall(r"^\s+(\w+): ", (WEBVIEW / "util/icons.tsx").read_text().split("const shapes", 1)[1]
                                .split("\n};", 1)[0], re.M))
        for meaning, (_, vscode, _) in self.table.items():
            if vscode is not None:
                self.assertIn(vscode, shapes, f"{meaning}: no {vscode} in icons.tsx")

    def test_plasma_files_exist(self):
        for meaning, (plasma, _, _) in self.table.items():
            if plasma.endswith(".svg"):
                self.assertTrue((REPO / "package/contents/icons" / plasma).exists(), meaning)

    @unittest.skipUnless(BREEZE.is_dir(), "needs the Breeze icons")
    def test_breeze_has_them_and_only_wrong_is_colored(self):
        for meaning, (plasma, _, _) in self.table.items():
            if plasma.endswith(".svg") or meaning in APPS:
                continue
            self.assertTrue(breeze_files(plasma), f"{meaning}: Breeze has no {plasma}")
            if meaning not in self.colored:
                self.assertEqual(colored(plasma), [], f"{meaning}: {plasma} is colored")

    @unittest.skipUnless(BREEZE.is_dir(), "needs the Breeze icons")
    def test_the_wrong_ones_are_colored(self):
        for meaning in self.colored:
            self.assertTrue(colored(self.table[meaning][0]), meaning)


def breeze_name(word):
    return BREEZE.is_dir() and bool(list(BREEZE.glob(f"*/*/{word}.svg")))


class UseTests(unittest.TestCase):
    """The front ends ask the table for a meaning, never for an icon by its name"""

    ICON_SITE = re.compile(r"\b(?:icon\.name|iconName|icon|source)\s*:(.*)")

    def test_plasma_names_no_icon(self):
        exempt = {"Plasmoid.icon", "vscode"}   # (the widget's own icon; VS Code's app icon)
        found = []
        for qml in sorted(UI.glob("*.qml")):
            for n, line in enumerate(qml.read_text().splitlines(), 1):
                m = self.ICON_SITE.search(line.split("//")[0])
                if not m or any(e in line for e in ("Plasmoid.icon:",)):
                    continue
                for word in re.findall(r'"([a-z][a-z0-9-]*)"', m.group(1)):
                    if word not in exempt and (breeze_name(word) or word.endswith("-symbolic")):
                        found.append(f"{qml.name}:{n} {word}")
        self.assertEqual(found, [])

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_every_meaning_asked_for_is_in_the_table(self):
        meanings = set(table()[0])
        used = []
        for qml in UI.glob("*.qml"):
            used += [(qml.name, m) for m in re.findall(r"Icons\.plasma\.(\w+)", qml.read_text())]
        for f in list((WEBVIEW / "components").glob("*.tsx")) + [WEBVIEW / "chat.tsx"]:
            used += [(f.name, m) for m in re.findall(r"\bI\.(\w+)", f.read_text())]
        for f in list(GNOME.glob("*.js")) + list((GNOME / "ui").glob("*.js")):
            used += [(f.name, m) for m in re.findall(r"Icons\.gnome\.(\w+)", f.read_text())]
        self.assertTrue(used)
        self.assertEqual([u for u in used if u[1] not in meanings], [])

    def test_vscode_names_no_icon(self):
        found = []
        for f in sorted(list((WEBVIEW / "components").glob("*.tsx")) + [WEBVIEW / "chat.tsx"]):
            for n, line in enumerate(f.read_text().splitlines(), 1):
                for m in re.finditer(r'\b(?:icon|name)="([a-zA-Z]+)"', line):
                    if "<Icon" in line or "icon=" in m.group(0):
                        found.append(f"{f.name}:{n} {m.group(1)}")
        self.assertEqual(found, [])

    def test_gnome_names_no_icon(self):
        found = []
        for f in sorted(list(GNOME.glob("*.js")) + list((GNOME / "ui").glob("*.js"))):
            for n, line in enumerate(f.read_text().splitlines(), 1):
                code = line.split("//")[0]
                for word in re.findall(r"'([a-z][a-z0-9.-]*-symbolic)'", code):
                    found.append(f"{f.name}:{n} {word}")
        self.assertEqual(found, [])

    def test_buttons_tags_and_marks_have_icons_not_characters(self):
        # (a clock, check, arrows, ⇄, ↗, ✎, ↩ or ★ typed as text are smaller than
        # the buttons' icons; the task list's ✓ ▸ ○ and a step's ▸ stay text)
        glyphs = re.compile(r"[⏱✓✗↻⚠⇄↗✎↩★▾]")
        found = []
        files = sorted(list((WEBVIEW / "components").glob("*.tsx")) + [WEBVIEW / "chat.tsx"] + list(UI.glob("*.qml"))
                       + list(GNOME.glob("ui/*.js")))
        for f in files:
            for n, line in enumerate(f.read_text().splitlines(), 1):
                code = line.strip()
                if code.startswith("//") or not glyphs.search(code):
                    continue
                if re.search(r"(title|tooltip|subText|mainText|aria-label)\b|[Ss]tarred|starHint", code):
                    continue   # (words about them, in tooltips and the Starred folds' titles)
                if 'status === "completed" ? "✓ "' in code:
                    continue   # (the task list: ✓ done, ▸ the one it's on, ○ to do)
                found.append(f"{f.name}:{n}: {code[:80]}")
        self.assertEqual(found, [])

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_colored_icons_say_something_and_are_colored_everywhere(self):
        tones = json.loads(subprocess.run(["node", "--input-type=module", "-e",
            "import { TONES } from %s; console.log(JSON.stringify(TONES));" % json.dumps((UI / "icons.mjs").as_uri())],
            capture_output=True, text=True, check=True).stdout)
        self.assertEqual({m for m, t in tones.items() if t == "negative"}, {"cancel", "deny", "delete", "erase", "error", "failed"})
        self.assertEqual({m for m, t in tones.items() if t == "positive"}, {"done", "reviewed", "allow", "always", "allowed"})
        self.assertEqual(tones["starred"], "star")
        self.assertNotIn("hide", tones)       # (most icons stay plain)
        # Plasma: every button with such an icon colors it (the icon, not the button)
        missing = []
        for qml in sorted(UI.glob("*.qml")):
            lines = qml.read_text().splitlines()
            for n, line in enumerate(lines):
                m = re.search(r"icon\.name: Icons\.plasma\.(cancel|delete|erase|deny|allow|always)$", line.strip())
                if m and 'icon.color: Icons.color("%s"' % m.group(1) not in lines[n + 1]:
                    missing.append(f"{qml.name}:{n + 1}")
        self.assertEqual(missing, [])
        # VS Code: its delete and cancel buttons too
        for f in sorted(list((WEBVIEW / "components").glob("*.tsx")) + [WEBVIEW / "chat.tsx"]):
            for n, line in enumerate(f.read_text().splitlines(), 1):
                m = re.search(r"icon=\{I\.(cancel|delete)\}", line)
                if m:
                    self.assertIn("tone={T.%s}" % m.group(1), line, f"{f.name}:{n}")


if __name__ == "__main__":
    unittest.main()
