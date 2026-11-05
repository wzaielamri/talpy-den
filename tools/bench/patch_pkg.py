#!/usr/bin/env python3
"""tools/render_popup.sh's PATCH for the budgets (bench.py): the package copy
it renders never acts on a chat, and its popup holds still.

    python3 -I patch_pkg.py PKG

- pane.py answers --send with "sent in the background" without sending
  anything, and refuses every other action that would reach a chat or change
  a file (answers, keys, undo, commit, hooks, a reply hidden): reads (the
  conversation and how its turn ended, what the reply box offers, your usual
  replies, the review, the terminal's font) run as they are.
- The pets are off (showPet, chatPets 0): offscreen, every window is drawn on
  the one thread, and a pet's animation in the popup would be in each number.
"""

import sys
from pathlib import Path

pkg = Path(sys.argv[1])


def patch(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path.name} changed ({old.strip()[:60]!r}): update tools/bench/patch_pkg.py"
    path.write_text(text.replace(old, new, 1))


patch(pkg / "contents/code/pane.py", "def main(argv=None):\n    args = sys.argv[1:] if argv is None else list(argv)\n",
      """def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    # (tools/bench: never sent, never answered; reads only)
    acting = [a for a in args if a.startswith("--") and a not in (
        "--conversation", "--complete", "--review", "--terminal-font", "--limit", "--if-changed", "--wait",
        "--suggest", "--replies", "--cwd", "--profile", "--host", "--config-dir", "--remote", "--pretty")]
    if "--send" in args:
        print(json.dumps({"ok": True, "how": "background", "message": "bench: not sent"}))
        return
    if acting:
        print(json.dumps({"ok": False, "message": "bench: " + " ".join(acting) + " not run"}))
        return
""")
xml = pkg / "contents/config/main.xml"
patch(xml, '<entry name="showPet" type="Bool">\n      <label>Show Talpy, the pet, in the popup and in notifications</label>\n      <default>true</default>',
      '<entry name="showPet" type="Bool">\n      <label>Show Talpy, the pet, in the popup and in notifications</label>\n      <default>false</default>')
text = xml.read_text()
at = text.index('<entry name="chatPets" type="Int">')
end = text.index("</entry>", at)
assert "<default>5</default>" in text[at:end], "main.xml's chatPets changed: update tools/bench/patch_pkg.py"
xml.write_text(text[:at] + text[at:end].replace("<default>5</default>", "<default>0</default>") + text[end:])
