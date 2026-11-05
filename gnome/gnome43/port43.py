#!/usr/bin/env python3
"""Turn a built GNOME 45+ extension folder into one for GNOME Shell 43/44.

    python3 -I gnome/gnome43/port43.py EXT_DIR

gnome/build.sh --gnome43 runs it on its output before zipping. It rewrites
the ES modules (import/export) into GNOME 43's legacy imports, points the
GNOME 45+ APIs the code uses at compat43.js / compat43prefs.js, and sets
shell-version. Every API patch must match where it's expected: when the
upstream code changes, the build stops instead of shipping something that
fails at runtime.
"""
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_VERSIONS = ["43", "44"]

# (file, old, new, expected count; None: at least one)
PATCHES = [
    # St.BoxLayout has no orientation property before GNOME 48
    ("ui/widgets.js", "orientation: Clutter.Orientation.VERTICAL", "vertical: true", 1),
    ("ui/pets.js", "orientation: Clutter.Orientation.VERTICAL", "vertical: true", None),
    # St.ScrollView: set_child() and vadjustment came in GNOME 46
    ("indicator.js", "this._scroll.set_child(", "this._scroll.add_actor(", 1),
    ("indicator.js", "this._scroll.vadjustment", "this._scroll.vscroll.adjustment", None),
    # MessageTray's constructors took positional arguments before GNOME 46
    ("notifier.js", "new MessageTray.Source({", "Compat.newSource({", 1),
    ("notifier.js", "new MessageTray.Notification({", "Compat.newNotification({", 1),
    ("notifier.js", "source.addNotification(", "source.showNotification(", 1),
    # libadwaita 1.2 and GTK 4.8
    ("prefs.js", "Adw.SpinRow.new_with_range(", "Compat.SpinRow.new_with_range(", 2),
    ("prefs.js", "new Adw.SwitchRow(", "new Compat.SwitchRow(", 2),
    ("prefs.js", "new Gtk.FileDialog(", "new Compat.FileDialog(", 1),
]

# APIs that must not be left in the converted code: newer GNOME Shell,
# libadwaita (1.3+), GTK (4.10+) and JavaScript (gjs 1.74 is SpiderMonkey
# 102) than GNOME 43/44 have
FORBIDDEN = [
    "Clutter.Orientation", ".set_child(", ".vadjustment", ".hadjustment", "Cogl.Color",
    "global.compositor", "addNotification(", "import.meta",
    "Adw.SpinRow", "Adw.SwitchRow", "Adw.ButtonRow", "Adw.PreferencesDialog", "Adw.AlertDialog", "Adw.Dialog",
    "Adw.Banner", "Adw.Spinner", "Adw.WrapBox", "Adw.ToggleGroup", "Adw.NavigationPage", "Adw.NavigationView",
    "Adw.ToolbarView", "Adw.BottomSheet", "Adw.MultiLayoutView", "Adw.ShortcutsDialog",
    "Gtk.FileDialog", "Gtk.AlertDialog", "Gtk.UriLauncher", "Gtk.FileLauncher", "Gtk.ColorDialog", "Gtk.FontDialog",
    ".findLast(", ".findLastIndex(", ".toSorted(", ".toReversed(", ".toSpliced(", "Object.groupBy(",
    "Map.groupBy(", "structuredClone(", "Promise.withResolvers(", "Promise.try(", "Array.fromAsync(",
    "Iterator.from(", "Intl.Segmenter", "Intl.DurationFormat", "RegExp.escape(", "Math.sumPrecise(",
    ".isWellFormed(", ".toWellFormed(", ".union(", ".intersection(", ".symmetricDifference(",
    ".isSubsetOf(", ".isSupersetOf(", ".isDisjointFrom(", ".difference(", ".with(",
]
# ...and iterator helpers (SpiderMonkey 131): keys()/values()/entries() then map(), filter()...
FORBIDDEN_RE = [
    re.compile(r"\.(?:keys|values|entries)\(\)\.(?:map|filter|take|drop|flatMap|reduce|toArray|forEach|some|every|find)\("),
]

GI = re.compile(r"^import (\w+) from 'gi://(\w+)(?:\?version=[\d.]+)?';$")
CAIRO = re.compile(r"^import Cairo from 'cairo';$")
SHELL_UI = re.compile(r"^import \* as (\w+) from 'resource:///org/gnome/shell/ui/(\w+)\.js';$")
BASE = re.compile(r"^import \{(Extension|ExtensionPreferences)\} from 'resource:///org/gnome/"
                  r"(?:shell/extensions/extension|Shell/Extensions/js/extensions/prefs)\.js';$")
LOCAL_NS = re.compile(r"^import \* as (\w+) from '(\.{1,2}/[\w/]+)\.js';$")
LOCAL_NAMED = re.compile(r"^import \{([^}]+)\} from '(\.{1,2}/[\w/]+)\.js';$")
ME = "const Me = imports.misc.extensionUtils.getCurrentExtension();"


def fail(msg):
    sys.exit(f"port43: {msg}")


def module_path(root, file, spec):
    """'./ui/widgets' seen from file -> 'Me.imports.ui.widgets'"""
    target = (file.parent / spec).resolve().relative_to(root.resolve())
    return "Me.imports." + ".".join(target.parts)


def convert(root, file):
    rel = file.relative_to(root).as_posix()
    is_prefs = rel == "prefs.js"
    text = file.read_text(encoding="utf-8")

    for f, old, new, count in PATCHES:
        if f != rel:
            continue
        n = text.count(old)
        if (count is None and n == 0) or (count is not None and n != count):
            fail(f"{rel}: expected {count or 'some'} of {old!r}, found {n}; the GNOME 43 port needs updating")
        text = text.replace(old, new)

    out, first_import, default_class = [], None, None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        new = None
        if line.startswith("import "):
            if m := GI.match(line):
                new = f"const {m[1]} = imports.gi.{m[2]};"
            elif CAIRO.match(line):
                new = "const Cairo = imports.cairo;"
            elif m := SHELL_UI.match(line):
                new = f"const {m[1]} = imports.ui.{m[2]};"
            elif m := BASE.match(line):
                new = f"const {{{m[1]}}} = Me.imports.{'compat43prefs' if is_prefs else 'compat43'};"
            elif m := LOCAL_NS.match(line):
                new = f"const {m[1]} = {module_path(root, file, m[2])};"
            elif m := LOCAL_NAMED.match(line):
                names = ", ".join(re.sub(r"^(\w+) as (\w+)$", r"\1: \2", n.strip()) for n in m[1].split(","))
                new = f"const {{{names}}} = {module_path(root, file, m[2])};"
            else:
                fail(f"{rel}:{i + 1}: can't convert: {line}")
            if first_import is None:
                first_import = len(out)
            out.append(new)
        elif line.startswith("export "):
            if m := re.match(r"^export default class (\w+)( extends \w+)? \{$", line):
                default_class = m[1]
                out.append(line[len("export default "):])
            elif m := re.match(r"^export class (\w+)(.*)$", line):
                out.append(f"var {m[1]} = class {m[1]}{m[2]}")
                # close the class expression with a semicolon
                j = next((j for j in range(i + 1, len(lines)) if lines[j] == "}"), None)
                if j is None:
                    fail(f"{rel}:{i + 1}: no closing brace for class {m[1]}")
                lines[j] = "};"
            elif re.match(r"^export (async )?function ", line):
                out.append(line[len("export "):])
            elif m := re.match(r"^export (?:const|let|var) (.*)$", line):
                out.append(f"var {m[1]}")
            else:
                fail(f"{rel}:{i + 1}: can't convert: {line}")
        else:
            out.append(line)
        i += 1

    # before the imports: 'use strict' (ES modules always are), Me, Compat
    body = "\n".join(out)
    at = first_import if first_import is not None else 0
    if "Compat." in body:
        out.insert(at, f"const Compat = Me.imports.{'compat43prefs' if is_prefs else 'compat43'};")
    if "Me.imports." in body or "Compat." in body:
        out.insert(at, ME)
    out.insert(at, "'use strict';")
    if default_class:
        if rel == "extension.js":
            out += ["", "function init(meta) {", f"    return new {default_class}(meta);", "}"]
        elif is_prefs:
            out += ["", "function init() {", "}", "",
                    "function fillPreferencesWindow(window) {",
                    f"    new {default_class}().fillPreferencesWindow(window);", "}"]
        else:
            fail(f"{rel}: unexpected default export")
    text = "\n".join(out) + "\n"

    for bad in FORBIDDEN:
        if bad in text:
            fail(f"{rel}: still uses {bad} after conversion; the GNOME 43 port needs updating")
    for bad in FORBIDDEN_RE:
        if m := bad.search(text):
            fail(f"{rel}: still uses {m[0]} after conversion; the GNOME 43 port needs updating")
    file.write_text(text, encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        fail("usage: port43.py EXT_DIR")
    root = Path(sys.argv[1])
    for name in ("compat43.js", "compat43prefs.js"):
        shutil.copy(HERE / name, root / name)
    for file in sorted(root.rglob("*.js")):
        if file.name not in ("compat43.js", "compat43prefs.js"):
            convert(root, file)
    meta_path = root / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["shell-version"] = SHELL_VERSIONS
    meta["version-name"] = f"{meta.get('version-name', '')}-gnome43".lstrip("-")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
