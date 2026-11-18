"""Opening a chat in Talpy Chat puts the cursor in its reply box, in Plasma and VS Code alike: a click on its row,
a notification, another program's request (Talpy Den Display's tap), its window brought up again."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "package/contents/ui"
VSCODE = REPO / "vscode"


def body_of(text, signature):
    """The body of the QML/JS function starting at signature (up to its closing brace at the same indent)."""
    start = text.index(signature)
    indent = text[:start].rsplit("\n", 1)[-1]
    end = text.index("\n" + indent + "}", start)
    return text[start:end]


class ReplyFocusTests(unittest.TestCase):
    def test_the_window_puts_the_cursor_in_its_reply_box(self):
        pane = (UI / "ChatPane.qml").read_text()
        focus = body_of(pane, "function focusReply()")
        self.assertIn("replyBox.forceActiveFocus()", focus)
        self.assertIn('tab === "chat"', focus)   # (its Review tab keeps its own)
        # brought up again (a click, a notification, a request): the reply box
        self.assertIn("focusReply()", body_of(pane, "function forward(tab)"))
        # a new window: its reply box too, once it's made
        self.assertRegex(body_of(pane, "Component.onCompleted: {"), r"focusReply\(\)")
        # what the opener asked for after that has the last word (a draft in the box; Deny's note; a question's own words)
        act = body_of(pane, "function act(then)")
        self.assertIn("replyBox.forceActiveFocus()", act[act.index("then.draft"):act.index("then.denying")])

    def test_a_request_for_a_chat_whose_window_is_open_brings_up_that_window(self):
        main = (UI / "main.qml").read_text()
        taker = body_of(main, "Exec {\n        id: openTaker")
        self.assertIn("root.paneOpenFor(want.s, want.host)", taker)
        self.assertRegex(taker, r'openPane\(want\.s, want\.host, "chat"\)')
        self.assertIn("root.clickChat(want.s, want.host)", taker)
        holder = body_of(main, "function paneOpenFor(s, host)")
        self.assertIn("Hub.paneHolder(key, \"\")", holder)
        self.assertIn("paneWindowOf(key)", holder)

    def test_vscode_tab_puts_the_cursor_in_its_reply_box(self):
        page = (VSCODE / "webview/chat.tsx").read_text()
        self.assertRegex(page, r'm\.type === "focusReply"\)\s*window\.setTimeout\(\(\) => reply\.current\?\.focus\(\), 0\)')
        types = (VSCODE / "src/shared/pane.ts").read_text()
        self.assertIn('| { type: "focusReply" }', types)


if __name__ == "__main__":
    unittest.main()
