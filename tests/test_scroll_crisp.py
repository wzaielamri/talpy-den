"""Talpy Chat's text stays crisp and moves as one while it scrolls (Plasma's
ChatPane.qml and its lists, VS Code's chat.tsx and styles.css), read as text
where nothing runs them.

Plasma: Qt draws text snapped to the nearest pixel, each item on its own. The
wheel (Kirigami's WheelHandler eases each notch over 200 ms) moved the list to
fractional positions on almost every frame, and most rows sat at fractional
heights (a gap of 1.6 grid units: 28.8 px), so in one frame of a notch some
lines moved 27 px and the rest 28: the conversation shimmered as it scrolled.
Now the list moves by whole pixels (pixelAligned) and every row starts on one,
so all of it moves together, each frame by the same whole pixels. The side
questions, the bookmarks, the tasks and the Review tab scroll the same way.
Nothing new runs while nothing moves.

VS Code: Chromium already scrolls by whole pixels, and a frame in the middle of
a scroll is the one at rest moved by whole pixels, its text as sharp (measured
in the harness): these keep the conversation free of what would give its rows
a layer of their own (drawn once, then moved or scaled: blurred) or a smooth
scroll of the page's own fighting yours.
"""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
SIDE = (UI / "SidePanel.qml").read_text()
MARKS = (UI / "BookmarkList.qml").read_text()
REVIEW = (UI / "ReviewPage.qml").read_text()
DAY = (UI / "DayLine.qml").read_text()
CSS = (ROOT / "vscode/webview/styles.css").read_text()
CHAT = (ROOT / "vscode/webview/chat.tsx").read_text()


def block(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


class PlasmaWholePixelTests(unittest.TestCase):
    def conversation(self):
        return block(PANE, "                ListView {\n                    id: list\n", "section.property")

    def test_the_conversation_moves_by_whole_pixels(self):
        self.assertIn("pixelAligned: true", self.conversation())

    def test_its_other_lists_too(self):
        self.assertIn("pixelAligned: true", block(PANE, "id: stripFlick", "ColumnLayout {"))   # (the tasks)
        self.assertIn("pixelAligned: true", block(SIDE, "id: entries", "delegate:"))           # (side questions)
        self.assertIn("pixelAligned: true", block(MARKS, "id: entries", "delegate:"))          # (bookmarks)
        # (the Review tab: its scroll view makes the Flickable itself)
        self.assertIn("Component.onCompleted: contentItem.pixelAligned = true", block(REVIEW, "PlasmaComponents3.ScrollView {", "ColumnLayout {"))

    def test_every_row_starts_on_a_whole_pixel(self):
        delegate = block(PANE, "delegate: Item {\n                        id: entry", "Loader {\n                            id: body")
        gap = block(delegate, "readonly property real gap:", "// (the Chat tab")
        self.assertIn("readonly property real gap: Math.round(", gap)
        self.assertIn("implicitHeight: gap + Math.ceil(body.implicitHeight)", delegate)
        self.assertIn("implicitHeight: Math.ceil(headerColumn.implicitHeight + Kirigami.Units.largeSpacing)", PANE)
        self.assertIn("implicitHeight: Math.ceil(line.implicitHeight + Kirigami.Units.gridUnit * 1.1)", DAY)   # (a day's line)
        footer = block(PANE, "footer: Item {", "RowLayout {")
        self.assertIn("Math.ceil(workingLine.implicitHeight + shellLines.height + Kirigami.Units.gridUnit)", footer)
        self.assertIn("height: listed ? Math.ceil(body.implicitHeight) : 0", SIDE)
        self.assertIn("height: Math.ceil(Math.max(snippet.implicitHeight, side.height) + Kirigami.Units.smallSpacing * 2)", MARKS)

    def test_nothing_new_moves_while_idle(self):
        # (whole pixels are Qt's rounding of where the list is: no animation, timer or layer of ours)
        for text in (PANE, SIDE, MARKS, REVIEW):
            self.assertNotIn("Behavior on contentY", text)
            self.assertNotIn("layer.enabled", text)
            self.assertIsNone(re.search(r'property:\s*"contentY"', text))
        # (Qt's text, as the desktop draws it: no render type of our own)
        self.assertNotIn("renderType", PANE)


class VsCodeCrispTests(unittest.TestCase):
    def rules(self, *names):
        """The bodies of the CSS rules for exactly these selectors (each compound: .pane-item.turn too)."""
        out = []
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)):
            for one in sel.split(","):
                one = one.strip()
                if any(re.fullmatch(re.escape(n) + r"(\.[\w-]+)*", one) for n in names):
                    out.append((one, body))
        return out

    def test_the_list_and_its_rows_have_no_layer_of_their_own(self):
        rules = self.rules(".pane-list", ".pane-item")
        self.assertGreaterEqual(len(rules), 5)
        for sel, body in rules:
            for prop in ("will-change", "transform", "filter", "backface-visibility", "perspective", "contain:",
                         "content-visibility", "zoom", "scroll-behavior"):
                self.assertNotIn(prop, body, sel)

    def test_no_smooth_scroll_of_its_own(self):
        self.assertNotIn("scroll-behavior", CSS)
        self.assertNotIn('behavior: "smooth"', CHAT)


if __name__ == "__main__":
    unittest.main()
