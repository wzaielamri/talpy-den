"""The release workflow's notes (.github/workflows/release.yml, its Notes
step): the CHANGELOG entries of the version, fitted in what GitHub takes."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 125_000  # (GitHub's, for a release's notes: 1.17.0's first try was refused, 175,000)


def notes_step():
    """The Notes step's script, as the runner gets it."""
    text = (ROOT / ".github/workflows/release.yml").read_text()
    start = text.index("      - name: Notes\n        run: |\n") + len("      - name: Notes\n        run: |\n")
    end = text.index("\n      - name: ", start)
    lines = text[start:end].split("\n")
    return "\n".join(line[10:] if line.startswith(" " * 10) else line.strip() for line in lines) + "\n"


class ReleaseNotesTests(unittest.TestCase):
    def notes(self, version, root_log, vscode_log):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "vscode").mkdir()
            Path(tmp, "CHANGELOG.md").write_text(root_log)
            Path(tmp, "vscode/CHANGELOG.md").write_text(vscode_log)
            subprocess.run(["bash", "-e", "-c", notes_step()], cwd=tmp, check=True,
                           env=dict(os.environ, VERSION=version, TAG="v" + version))
            return Path(tmp, "notes.md").read_text()

    def test_this_releases_notes_fit(self):
        version = re.search(r'"Version": "([0-9.]+)"', (ROOT / "package/metadata.json").read_text()).group(1)
        root_log, vscode_log = (ROOT / "CHANGELOG.md").read_text(), (ROOT / "vscode/CHANGELOG.md").read_text()
        notes = self.notes(version, root_log, vscode_log)
        self.assertLess(len(notes), LIMIT)
        if "### Highlights" in root_log.split(f"## {version}", 1)[1].split("\n## ", 1)[0]:
            self.assertTrue(notes.startswith("## Highlights\n"))  # (only those, and links to every change)
            self.assertIn(f"blob/v{version}/CHANGELOG.md", notes)
            self.assertNotIn("### Every change", notes)
        else:
            self.assertTrue(notes.startswith("## KDE Plasma and GNOME\n"))
        self.assertIn("## Install", notes)
        self.assertIn(f"talpy-den-{version}.vsix", notes)

    def test_short_notes_keep_both_lists_long_ones_link_and_cut_after_an_entry(self):
        head = "# Changelog\n\n## 9.9.9 (2030-01-01)\n\n"
        short = self.notes("9.9.9", head + "- **One:** it works.\n", head.replace(" (2030-01-01)", "") + "- **Two:** it\n  works too.\n")
        self.assertIn("- **One:** it works.\n\n## VS Code\n\n- **Two:** it\n  works too.\n", short)
        # the widget's list fits, the VS Code one doesn't: a link to it
        many = "".join(f"- **Change {i}:** " + "x" * 600 + "\n" for i in range(150))
        notes = self.notes("9.9.9", head + many, head + many)
        self.assertLess(len(notes), LIMIT)
        self.assertIn("- **Change 149:**", notes)
        self.assertIn("## VS Code\n\nIts changes are in [vscode/CHANGELOG.md](https://github.com/wzaielamri/talpy-den/blob/v9.9.9/vscode/CHANGELOG.md).", notes)
        # longer still: the list stops after a whole entry, with a link to the rest
        more = "".join(f"- **Change {i}:** " + "x" * 600 + "\n" for i in range(400))
        notes = self.notes("9.9.9", head + more, head + more)
        self.assertLess(len(notes), LIMIT)
        self.assertNotIn("- **Change 399:**", notes)
        cut = notes[:notes.index("\n\n… and more")]
        self.assertRegex(cut, r"- \*\*Change \d+:\*\* x{600}$")  # (a whole entry, then the link)
        self.assertIn("… and more: the whole list is in [CHANGELOG.md](https://github.com/wzaielamri/talpy-den/blob/v9.9.9/CHANGELOG.md).", notes)
        self.assertIn("## Install", notes)


if __name__ == "__main__":
    unittest.main()
