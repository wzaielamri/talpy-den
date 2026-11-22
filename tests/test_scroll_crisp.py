"""Regression guards: Talpy Chat's text stays sharp while it scrolls (Plasma's
ChatPane.qml and the widget's other scrolling views, VS Code's styles.css),
read as text where nothing runs them.

Plasma: Qt draws each text snapped to the nearest pixel, on its own, and the
conversation's rows sit at fractions of a pixel (a gap of 1.6 grid units:
28.8 px). The wheel (Kirigami's WheelHandler eases each notch over 200 ms)
moved the list to fractional positions on almost every frame, so lines rounded
differently from frame to frame: in one frame of a notch some moved 27 px and
the rest 28, a shimmer as it scrolled. Moved by whole pixels only
(pixelAligned), every line rounds the same way each frame, so all of it moves
together; the rows stay where they were. The side questions, the bookmarks,
the tasks, a plan or page shown in the chat, the box of what Claude asks, the
Review tab, and the popup's chats, projects, usage and permissions scroll the
same way (a scroll view's Flickable is its own: aligned when it's made).
Nothing new runs while nothing moves.

VS Code: not reproduced in a headless browser (its scroll moves every band of
text by the same whole pixels, its text as sharp, at device scale 1, 1.25 and
1.5); two likely causes changed: an opaque scroller (the conversation and the
side questions take the page's own background, so Chromium can scroll them on
the GPU and keep the text's subpixel edges: a see-through one it composites
loses them) and no layer for the blinking dot (it steps on the page's beat).
It needs the owner's eye.
"""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
CSS = (ROOT / "vscode/webview/styles.css").read_text()
CHAT = (ROOT / "vscode/webview/chat.tsx").read_text()


def qml(name):
    return (UI / name).read_text()


def item(text, ident):
    """The QML object whose id is ident: from its opening line to its closing brace, whatever the indentation."""
    at = re.search(r"\bid:\s*" + re.escape(ident) + r"\b", text)
    assert at, ident
    start = text.rindex("{", 0, at.start())
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[text.rindex("\n", 0, start) + 1:i + 1]
    raise AssertionError(ident)


def own(block):
    """block's own lines, its handlers' bodies included: without the objects nested in it (its delegate's
    rows aren't the list)."""
    out, depth, handler = [], 0, False
    for line in block.splitlines()[1:]:
        if depth == 0:
            out.append(line)
            handler = bool(re.match(r"\s*(Component\.)?on\w+\s*:", line))
        elif handler:
            out.append(line)
        depth += line.count("{") - line.count("}")
    return "\n".join(out)


def css_rules(*names):
    """The bodies of the CSS rules for exactly these selectors (each compound: .pane-item.turn too)."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)):
        for one in sel.split(","):
            one = one.strip()
            if any(re.fullmatch(re.escape(n) + r"(\.[\w-]+)*", one) for n in names):
                out.append((one, body))
    return out


class PlasmaWholePixelTests(unittest.TestCase):
    def test_the_conversation_moves_by_whole_pixels(self):
        self.assertIn("pixelAligned: true", own(item(PANE, "list")))

    def test_its_other_lists_too(self):
        self.assertIn("pixelAligned: true", own(item(PANE, "stripFlick")))           # (the tasks)
        self.assertIn("pixelAligned: true", own(item(qml("SidePanel.qml"), "entries")))     # (side questions)
        self.assertIn("pixelAligned: true", own(item(qml("BookmarkList.qml"), "entries")))  # (bookmarks)

    def test_scroll_views_align_their_own_flickable(self):
        aligned = "contentItem.pixelAligned = true"
        self.assertIn(aligned, own(item(qml("MadeLine.qml"), "textScroll")))        # (a plan or a page, in the chat)
        self.assertIn(aligned, own(item(qml("FullRepresentation.qml"), "scroll")))  # (the popup's chats)
        for name in ("ProjectsView.qml", "WeekView.qml", "PermsView.qml"):
            self.assertIn(aligned, own(item(qml(name), "view")), name)
        review = qml("ReviewPage.qml")
        view = review[review.index("PlasmaComponents3.ScrollView {"):]
        self.assertIn(aligned, own(view[:view.index("ColumnLayout {")] + "\n"))
        asking = PANE[:PANE.index("PermissionAsk {\n                        id: askColumn")]
        asking = asking[asking.rindex("PlasmaComponents3.ScrollView {"):]
        self.assertIn(aligned, asking)                                              # (what Claude asks)

    def test_the_rows_keep_their_places(self):
        # (whole-pixel scrolling is enough: rows rounded too would only add space)
        self.assertIn("implicitHeight: gap + body.implicitHeight", PANE)
        self.assertNotIn("Math.ceil(body.implicitHeight)", PANE)

    def test_nothing_new_moves_while_idle(self):
        # (whole pixels are Qt's rounding of where a list is: no animation, timer or layer of ours)
        for name in ("ChatPane.qml", "SidePanel.qml", "BookmarkList.qml", "ReviewPage.qml", "MadeLine.qml"):
            text = qml(name)
            self.assertNotIn("Behavior on contentY", text, name)
            self.assertNotIn("layer.enabled", text, name)
            self.assertIsNone(re.search(r'property:\s*"contentY"', text), name)
        # (Qt's text, as the desktop draws it: no render type of our own)
        self.assertNotIn("renderType", PANE)


class VsCodeCrispTests(unittest.TestCase):
    def test_the_scrollers_are_opaque_in_the_pages_own_background(self):
        page = css_rules("body.chat-page")
        self.assertIn("background: var(--vscode-editor-background, transparent);", page[0][1])
        (_, conversation), = [r for r in css_rules(".pane-list") if r[0] == ".pane-list" and "overflow-y" in r[1]]
        self.assertIn("background: var(--vscode-editor-background, transparent);", conversation)
        side = [b for s, b in css_rules(".pane-side") if s == ".pane-side"][-1]
        (_, sides), = css_rules(".pane-side-list")
        self.assertIn("background: var(--vscode-editor-background, var(--td-bg));", side)
        self.assertIn("background: var(--vscode-editor-background, var(--td-bg));", sides)

    def test_the_list_its_rows_and_the_blinking_dot_have_no_layer_of_their_own(self):
        rules = css_rules(".pane-list", ".pane-item", ".pane-side-list")
        self.assertGreaterEqual(len(rules), 7)
        for sel, body in rules:
            for prop in ("will-change", "transform", "filter", "backface-visibility", "perspective", "contain:",
                         "content-visibility", "zoom", "scroll-behavior"):
                self.assertNotIn(prop, body, sel)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)):
            if "pane-dot" in sel:
                self.assertNotIn("will-change", body, sel.strip())

    def test_no_smooth_scroll_of_its_own(self):
        self.assertNotIn("scroll-behavior", CSS)
        self.assertNotIn('behavior: "smooth"', CHAT)


if __name__ == "__main__":
    unittest.main()
