"""Talpy Chat far back and back again: Plasma's QML wiring (ChatPane.qml,
Bookmarks.qml, PaneKeys.qml, FindBar.qml, NewBelow.qml) and VS Code's page
(chat.tsx), read as text where nothing runs them.

A bookmark further back than what's shown is read for (pane.py --reach: up to
2000 items), and so is Show earlier. Plasma's list made every row of what came
in, in one go (1,900 rows held the window up 12 s): now it makes those near
what you read first and the rest a few at a time (fill.mjs: its arithmetic and
its duty cap have node tests, vscode/test/fill.test.ts); a jump, a search's
step or a key far from what's made meanwhile makes only the rows near where it
goes, and Alt+↑ / Alt+↓, Ctrl+↑ / Ctrl+↓ go by the list's order, so a row not
made yet isn't taken for none (bookmarks.mjs step: pane.test.ts).

"↓ Latest" floats over the bottom of the conversation whenever it isn't at its
newest (after a bookmark, a search's match, scrolling up), "↓ 3 new" once
something came in below meanwhile; the button, Ctrl+↓ and Alt+↓ past the last
go back to the newest, and a chat read further back is read as at first again
(Plasma keeps the newest rows at once; VS Code's host gets "latest", tested in
pane.test.ts), so each read after is as quick as before. A read further back,
a jump's tries or a search's step still on their way are given up. Nothing in
the button moves.
"""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
BELOW = (UI / "NewBelow.qml").read_text()
MARKS = (UI / "Bookmarks.qml").read_text()
FIND = (UI / "FindBar.qml").read_text()
KEYS = (UI / "PaneKeys.qml").read_text()
CHAT = (ROOT / "vscode/webview/chat.tsx").read_text()
SHARED = (ROOT / "core/src/shared/pane.ts").read_text()


def function(text, name):
    start = text.index(f"function {name}(")
    return text[start:text.index("\n    }\n", start)]


class PlasmaRowsAFewAtATimeTests(unittest.TestCase):
    def test_the_list_makes_every_row_unless_many_came_in_at_once(self):
        self.assertIn("cacheBuffer: pane.fillBuffer >= 0 ? pane.fillBuffer : 100000", PANE)
        self.assertIn("property real fillBuffer: -1", PANE)
        merge = function(PANE, "merge")
        # (counted once those gone are out, a run at a time: what's left is what comes in)
        self.assertIn("items.remove(from, i - from + 1)", merge)
        self.assertNotIn("items.remove(i)\n", merge)
        self.assertIn("if (items.count > 0 && list.length - items.count > fillMin)\n            startFill()", merge)
        self.assertLess(merge.index("items.remove(from, i - from + 1)"), merge.index("startFill()"))
        self.assertLess(merge.index("startFill()"), merge.index("items.insert(i, withFold(flat, it))"))
        self.assertIn("fillBuffer = -1", function(PANE, "reset"))

    def test_its_steps_are_fill_mjs_and_its_timer_runs_only_while_it_fills(self):
        self.assertIn('import "fill.mjs" as Fill', PANE)
        start = function(PANE, "startFill")
        self.assertIn("Fill.fillStart(list.height, fm.height)", start)
        self.assertIn("filling.interval = f.interval", start)   # (the shortest wait again)
        more = function(PANE, "fillMore")
        self.assertIn("fillBuffer = Fill.fillNext(fillBuffer, filling.step)", more)
        self.assertIn("Fill.fillPace(filling.step, Math.max(Date.now() - t, late), fm.height)", more)
        self.assertIn("filling.interval = pace.interval", more)   # (the duty cap)
        timer = PANE[PANE.index("        id: filling\n"):]
        timer = timer[:timer.index("    }\n")]
        self.assertIn("running: pane.fillBuffer >= 0 && pane.shown", timer)
        self.assertIn("onTriggered: pane.fillMore()", timer)

    def test_a_smaller_buffer_places_the_ribbons_again(self):
        # (the rows it no longer holds went, their bookmark ribbons too, and an idle chat places none)
        self.assertIn("bookmarkLogic.item.placeSoon()", function(PANE, "startFill"))

    def test_a_far_move_meanwhile_makes_only_the_rows_near_where_it_goes(self):
        self.assertIn("if (fillBuffer >= 0)\n            startFill()", function(PANE, "fillNear"))
        jump = MARKS[MARKS.index("function jumpNow() {"):MARKS.index("// Alt+↑ (back)")]
        # (not following the end first: it took the list back between tries, a bookmark took 2 s)
        self.assertLess(jump.index("settle.stop()"), jump.index("list.positionViewAtIndex(i, ListView.Beginning)"))
        self.assertLess(jump.index("pane.fillNear()"), jump.index("list.positionViewAtIndex(i, ListView.Beginning)"))
        go = function(FIND, "goTo")
        self.assertIn("if (i >= 0 && !list.itemAtIndex(i)) {", go)
        self.assertLess(go.index("pane.fillNear()"), go.index("list.positionViewAtIndex(i, ListView.Center)"))

    def test_at_the_end_it_stays_there_while_rows_are_made(self):
        # (back at the newest, ↓ Latest, the end went 200 px out of view as the rows above were made: the
        # end is followed till they're all made, as long as you don't scroll or jump, which stop settle)
        settle = PANE[PANE.index("        id: settle\n"):]
        settle = settle[:settle.index("\n    }\n")]
        self.assertIn("if (--left <= 0 && pane.fillBuffer < 0)\n                stop()", settle)

    def test_a_read_for_a_bookmark_goes_to_it_not_the_end(self):
        self.assertIn('if (following && !(reach && result.reached === "here"))', function(PANE, "takeConversation"))


class PlasmaKeysByTheListsOrderTests(unittest.TestCase):
    """Right after a far jump, rows away from it aren't made yet: Alt+↓ went to the end (and threw
    the read away), as no made row was below."""

    def test_the_view_has_an_index(self):
        view = function(PANE, "viewIndex")
        self.assertIn("list.indexAt(list.width / 2, list.contentY + dy)", view)
        self.assertIn("? -1 : items.count", view)

    def test_alt_arrows_give_each_loaded_bookmark_its_index(self):
        step = function(MARKS, "step")
        self.assertIn("order[m.key] = loaded.get(m.key)", step)
        self.assertIn("Bm.step(pane.bookmarks, states, tops, list.contentY, back, order, pane.viewIndex())", step)
        # (one whose row isn't made: gone to as any, its rows made near it, jumpNow)
        self.assertIn("jump(r.key, false)", step)

    def test_ctrl_arrows_go_to_a_message_whose_row_isnt_made_and_the_end_only_after_the_last(self):
        jump = function(KEYS, "jumpPrompt")
        self.assertIn("const top = list.contentY, view = pane.viewIndex()", jump)
        self.assertIn("if (down ? i > view : i < view) {", jump)
        made = jump[jump.index("else if (toIndex >= 0) {"):]
        self.assertLess(made.index("pane.fillNear()"), made.index("list.positionViewAtIndex(toIndex, ListView.Beginning)"))
        self.assertTrue(jump.rstrip().endswith("} else if (down)\n            pane.toEnd()"))


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
        self.assertIn("onTapped: pane.toEnd()", BELOW)
        # (nothing in it moves: no animation, no timer, Plasma's shared beat untouched)
        for moving in ("Animation", "Behavior", "Timer", "Beat."):
            self.assertNotIn(moving, BELOW)
        self.assertIn("color: Kirigami.Theme.focusColor", BELOW)   # (the accent, as before)

    def test_plasma_back_at_the_newest_reads_as_at_first_again(self):
        to_end = function(PANE, "toEnd")
        self.assertIn('if (limit > limitFirst || reachKey !== "") {', to_end)
        self.assertIn("limit = limitFirst", to_end)
        # (the rows above go at once, before the read: at the end first, only the rows shown there
        # made, then those above go, out of view)
        trim = to_end[to_end.index("if (lastItems.length > limitFirst) {"):]
        order = [trim.index(s) for s in ("startFill()", "followEnd()", "lastItems = lastItems.slice(-limitFirst)",
                                          "merge(withPending(lastItems, handoff), handoff)", "more = true")]
        self.assertEqual(order, sorted(order))
        self.assertLess(to_end.index("more = true"), to_end.index("load()"))
        self.assertTrue(to_end.rstrip().endswith("keepEnd()"))

    def test_plasma_back_at_the_newest_nothing_takes_the_list_back_up(self):
        to_end = function(PANE, "toEnd")
        for stop in ("holdTop.stop()", "bookmarkLogic.item.stop()", "findBar.item.stopGoing()"):
            self.assertLess(to_end.index(stop), to_end.index("keepEnd()"), stop)
        stop = function(MARKS, "stop")
        for line in ('going = ""', 'jumpKey = ""', 'jumpDrawn = ""', "jumpTries = 0", "jumpRetry.stop()"):
            self.assertIn(line, stop)
        going = function(FIND, "stopGoing")
        self.assertIn("go.stop()", going)
        self.assertIn("goTries = 0", going)

    def test_a_read_further_back_given_up_isnt_taken(self):
        take = function(PANE, "takeConversation")
        self.assertIn("const reach = !!result.reach && result.limit > 0 && result.reach === reachKey", take)

    def test_vscode_shows_it_whenever_the_list_isnt_at_its_newest_and_tells_the_host(self):
        block = CHAT[CHAT.index("{/* (↓ Latest whenever it isn't at its newest"):]
        block = block[:block.index(") : null}")]
        self.assertIn("{seen && loaded && shownItems.length ? (", block)
        self.assertIn('<span aria-hidden="true">↓ </span>{newText(unseen)}', block)
        self.assertIn("title={newHint(unseen)} onClick={toEnd}", block)
        to_end = CHAT[CHAT.index("  const toEnd = () => {"):]
        to_end = to_end[:to_end.index("\n  };\n")]
        for line in ("follow.current = true;", 'setGoing("");', "setPendingJump(null);", 'post({ type: "latest" });'):
            self.assertIn(line, to_end)

    def test_the_same_words_in_both(self):
        for words in ("Click to go back to the latest.", "Back to the latest point of the chat"):
            self.assertIn(words, BELOW)
            self.assertIn(words, SHARED)

    def test_no_key_of_its_own(self):
        # (the keys past the last message or bookmark go there already: Ctrl+↓, Alt+↓; Ctrl+End is the
        # reply box's own)
        keys = (UI / "keys.mjs").read_text()
        self.assertNotIn('"latest"', keys)
        self.assertIn("(past the last: the end)", keys)


if __name__ == "__main__":
    unittest.main()
