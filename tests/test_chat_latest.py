"""Talpy Chat far back and back again (Plasma's ChatPane.qml, VS Code's chat.tsx).

A bookmark further back than what's shown is read for (pane.py --reach: up to
2000 items), and so is Show earlier. Plasma's list made every row of what came
in, in one go (1,900 rows held the window up 12 s): now it makes those near
what you read first and the rest a few at a time, as many as take a few ms,
till every row is made again; a jump or a search's step far from what's made
meanwhile makes only the rows near where it goes.

"↓ Latest" floats over the bottom of the conversation whenever it isn't at its
newest (after a bookmark, a search's match, scrolling up), "↓ 3 new" once
something came in below meanwhile; a click goes back to the newest, and a chat
read further back is read as at first again (Plasma trims the rows above at
once; VS Code's host gets "latest"), so each read after is as quick as before.
A read further back still on its way is given up. Nothing in the button moves.
"""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
BELOW = (UI / "NewBelow.qml").read_text()
MARKS = (UI / "Bookmarks.qml").read_text()
FIND = (UI / "FindBar.qml").read_text()
CHAT = (ROOT / "vscode/webview/chat.tsx").read_text()
SHARED = (ROOT / "core/src/shared/pane.ts").read_text()
HOST = (ROOT / "core/src/chatPanes.ts").read_text()


def function(text, name):
    start = text.index(f"function {name}(")
    return text[start:text.index("\n    }\n", start)]


class PlasmaRowsAFewAtATimeTests(unittest.TestCase):
    def test_the_list_makes_every_row_unless_many_came_in_at_once(self):
        self.assertIn("cacheBuffer: pane.fillBuffer >= 0 ? pane.fillBuffer : 100000", PANE)
        self.assertIn("property real fillBuffer: -1", PANE)
        merge = function(PANE, "merge")
        # (counted once those gone are out: what's left is what comes in)
        self.assertIn("if (items.count > 0 && list.length - items.count > fillMin)\n            startFill()", merge)
        self.assertLess(merge.index("items.remove(from, i - from + 1)"), merge.index("startFill()"))
        self.assertLess(merge.index("startFill()"), merge.index("items.insert(i, withFold(flat, it))"))
        reset = function(PANE, "reset")
        self.assertIn("fillBuffer = -1", reset)

    def test_those_gone_go_a_run_at_a_time(self):
        merge = function(PANE, "merge")
        self.assertIn("while (from > 0 && !wanted[items.get(from - 1).key])", merge)
        self.assertNotIn("items.remove(i)\n", merge)

    def test_it_starts_near_what_you_read_and_grows_by_what_a_step_costs(self):
        start = function(PANE, "startFill")
        self.assertIn("fillBuffer = Math.round(list.height)", start)
        more = function(PANE, "fillMore")
        self.assertIn("fillBuffer = next >= 100000 ? -1 : next", more)   # (every row again, then nothing runs)
        self.assertIn("cost > 24 ? Math.max(fm.height * 6, filling.step / 2)", more)
        self.assertIn("cost < 8 ? Math.min(20000, filling.step * 2)", more)
        timer = PANE[PANE.index("        id: filling\n"):]
        timer = timer[:timer.index("    }\n")]
        self.assertIn("running: pane.fillBuffer >= 0 && pane.shown", timer)
        self.assertIn("onTriggered: pane.fillMore()", timer)

    def test_a_far_move_meanwhile_makes_only_the_rows_near_where_it_goes(self):
        near = function(PANE, "fillNear")
        self.assertIn("if (fillBuffer >= 0)\n            startFill()", near)
        jump = MARKS[MARKS.index("function jumpNow() {"):MARKS.index("// Alt+↑ (back)")]
        # (not following the end first: it took the list back between tries, a bookmark took 2 s)
        self.assertLess(jump.index("settle.stop()"), jump.index("list.positionViewAtIndex(i, ListView.Beginning)"))
        self.assertLess(jump.index("pane.fillNear()"), jump.index("list.positionViewAtIndex(i, ListView.Beginning)"))
        go = FIND[FIND.index("function goTo() {"):]
        go = go[:go.index("\n    }\n")]
        self.assertIn("if (i >= 0 && !list.itemAtIndex(i)) {", go)
        self.assertLess(go.index("pane.fillNear()"), go.index("list.positionViewAtIndex(i, ListView.Center)"))

    def test_a_read_for_a_bookmark_goes_to_it_not_the_end(self):
        take = function(PANE, "takeConversation")
        self.assertIn('if (following && !(reach && result.reached === "here"))', take)


class LatestButtonTests(unittest.TestCase):
    def loader(self):
        start = PANE.index('// "↓ Latest" at the list\'s bottom')
        return PANE[start:PANE.index("            }\n", start)]

    def test_plasma_shows_it_whenever_the_list_isnt_at_its_newest(self):
        loader = self.loader()
        # (endKept: noted once the list has moved, so a read that keeps the end makes none)
        self.assertIn("active: !pane.endKept && pane.loaded && items.count > 0 && pane.conversationTab", loader)
        self.assertIn('source: active ? "NewBelow.qml" : ""', loader)
        self.assertIn("parent: scroll", loader)   # (over the list: it moves nothing)

    def test_plasma_says_latest_or_how_many_came_in_and_goes_back(self):
        self.assertIn('pane.unseen > 0 ? i18np("↓ %1 new", "↓ %1 new", pane.unseen) : i18n("↓ Latest")', BELOW)
        self.assertIn('i18n("Back to the latest point of the chat")', BELOW)
        self.assertIn("onTapped: pane.toEnd()", BELOW)
        # (nothing in it moves: no animation, no timer, Plasma's shared beat untouched)
        for moving in ("Animation", "Behavior", "Timer", "Beat."):
            self.assertNotIn(moving, BELOW)
        # (its colours: the accent, as before)
        self.assertIn("color: Kirigami.Theme.focusColor", BELOW)

    def test_plasma_back_at_the_newest_reads_as_at_first_again(self):
        to_end = function(PANE, "toEnd")
        self.assertIn("if (limit > limitFirst || reachKey !== \"\") {", to_end)
        self.assertIn("limit = limitFirst", to_end)
        self.assertIn('reachKey = ""', to_end)
        self.assertIn('bookmarkLogic.item.going = ""', to_end)
        # (the rows above go at once, before the read: at the end first, only the rows shown there made,
        # a few at a time, then those above go, out of view)
        trim = to_end[to_end.index("if (lastItems.length > limitFirst) {"):]
        order = [trim.index(s) for s in ("startFill()", "followEnd()", "lastItems = lastItems.slice(-limitFirst)",
                                          "merge(withPending(lastItems, handoff), handoff)", "more = true")]
        self.assertEqual(order, sorted(order))
        self.assertLess(to_end.index("more = true"), to_end.index("load()"))
        self.assertTrue(to_end.rstrip().endswith("keepEnd()"))
        self.assertIn("readonly property int limitFirst: 120", PANE)

    def test_a_read_further_back_given_up_isnt_taken(self):
        take = function(PANE, "takeConversation")
        self.assertIn("const reach = !!result.reach && result.limit > 0 && result.reach === reachKey", take)
        self.assertIn("if (reach) {\n            limit = result.limit\n            reachKey = \"\"", take)

    def test_vscode_shows_it_whenever_the_list_isnt_at_its_newest(self):
        block = CHAT[CHAT.index("{/* (↓ Latest whenever it isn't at its newest"):]
        block = block[:block.index(") : null}")]
        self.assertIn("{seen && loaded && shownItems.length ? (", block)
        self.assertIn('<span aria-hidden="true">↓ </span>{newText(unseen)}', block)
        self.assertIn("title={newHint(unseen)} onClick={toEnd}", block)
        self.assertIn('return n > 0 ? `${n} new` : "Latest";', SHARED)
        self.assertIn('"Back to the latest point of the chat"', SHARED)

    def test_vscode_back_at_the_newest_tells_the_host(self):
        to_end = CHAT[CHAT.index("  const toEnd = () => {"):]
        to_end = to_end[:to_end.index("\n  };\n")]
        for line in ("follow.current = true;", 'setGoing("");', "setPendingJump(null);", 'post({ type: "latest" });'):
            self.assertIn(line, to_end)
        self.assertIn('| { type: "latest" }', SHARED)
        latest = HOST[HOST.index('      case "latest":'):]
        latest = latest[:latest.index("        break;")]
        self.assertIn("if (this.limit <= LIMIT && !this.reachKey) break;", latest)
        self.assertIn("this.limit = LIMIT;", latest)
        self.assertIn('this.reachKey = "";', latest)
        self.assertIn('this.stamp = "";', latest)
        self.assertIn("r.reach === this.reachKey", HOST)

    def test_the_same_words_in_both(self):
        for words in ("Click to go back to the latest.", "Back to the latest point of the chat"):
            self.assertIn(words, BELOW)
            self.assertIn(words, SHARED)
        self.assertTrue(re.search(r"↓ %1 new", BELOW))
        self.assertIn("newText(unseen)", CHAT)

    def test_no_key_of_its_own(self):
        # (the keys past the last message or bookmark go there already: Ctrl+↓, Alt+↓; Ctrl+End is the
        # reply box's own)
        keys = (UI / "keys.mjs").read_text()
        self.assertNotIn('"latest"', keys)
        self.assertIn("(past the last: the end)", keys)


if __name__ == "__main__":
    unittest.main()
