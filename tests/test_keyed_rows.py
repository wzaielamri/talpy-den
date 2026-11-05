"""A list's rows kept by key (KeyedRows.qml): a check that changes one chat
runs that row's bindings again, one that brings or takes a chat makes or
drops that row only, and many rows at once come a few a frame. A Repeater
given a number made every row of an account anew whenever a chat came or went
(Hide: 19 s with 35 rows, 2026-11-05), and its rows' themed items (a Label,
an Icon, a Rectangle colored from the theme) cost milliseconds each to make
and to take out of a big popup: the rows are light now (ListPalette.qml,
RowText.qml) and make what they rarely show only when it shows."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_pets import NEEDS_PLASMA_QML

UI = Path(__file__).resolve().parent.parent / "package/contents/ui"

LIST = """import QtQuick
import QtQuick.Layouts
import "%s"
Item {
    id: root
    width: 300; height: 600
    property int made: 0
    property int gone: 0
    readonly property var counter: ({ reads: 0 })   // (no binding hangs on it)
    property int reads: 0
    property int budget: 0
    KeyedRows { id: rows; budgetMs: root.budget }
    ColumnLayout {
        id: column
        width: 300
        spacing: 0
        Repeater {
            id: rep
            model: rows.model
            delegate: Rectangle {
                required property string key
                required property string rev
                readonly property var item: { rev; root.counter.reads++; return rows.item(key) || ({ name: "" }) }
                property string name: item.name
                Layout.fillWidth: true
                implicitHeight: 10
                Component.onCompleted: { root.made++; if (root.budget > 0) { const t = Date.now(); while (Date.now() - t < 4) {} } }
                Component.onDestruction: root.gone++
            }
        }
    }
    function sync(list) {
        rows.sync(list, it => it.id, it => it.rev, it => it.was || "")
    }
    function shown() {
        reads = counter.reads
        const out = []
        for (let i = 0; i < rep.count; i++)
            out.push([rep.itemAt(i).name, Math.round(rep.itemAt(i).y)])
        return JSON.stringify(out)
    }
    property var kept: null
    function keep() { kept = []; for (let i = 0; i < rep.count; i++) kept.push(rep.itemAt(i)) }
    function same(i, j) { return rep.itemAt(i) === kept[j] }
}
"""

LIST_SCRIPT = """import sys, json
from PySide6.QtCore import QUrl, QMetaObject, Q_RETURN_ARG, Q_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view)
def call(name, *args):
    return QMetaObject.invokeMethod(r, name, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
def sync(items):
    call("sync", items); QTest.qWait(80)
def state(label):
    shown = json.loads(call("shown"))
    print(repr([label, r.property("made"), r.property("gone"), r.property("reads"), shown]))
row = lambda i, rev="1", was="": {"id": i, "name": i, "rev": rev, "was": was}
sync([row("a"), row("b"), row("c")]); state("three")
call("keep")
sync([row("a"), row("b"), row("c")]); state("the same again: nothing runs")
sync([row("a"), row("b", "2"), row("c")]); state("b changed: only its row reads it")
sync([row("a"), row("c")]); state("b went: its row only")
print(repr(["kept", call("same", 0, 0), call("same", 1, 2)]))
call("keep")
sync([row("c"), row("a"), row("d")]); state("c moved up, d came")
print(repr(["moved", call("same", 0, 1), call("same", 1, 0)]))
call("keep")
sync([row("c"), row("a"), row("e", "1", "d")]); state("d moved to e: its row kept")
print(repr(["renamed", call("same", 2, 2)]))
sync([row("a"), row("a"), row("c")]); state("a twice: two rows")
r.setProperty("budget", 12)
sync([]); QTest.qWait(30)
r.setProperty("made", 0)
call("sync", [row("n%d" % i) for i in range(40)]); print(repr(["first go", r.property("made")]))
QTest.qWait(40); print(repr(["a frame or two", r.property("made")]))
QTest.qWait(800); print(repr(["all", r.property("made"), len(json.loads(call("shown")))]))
"""


BUTTON = """import QtQuick
import QtQuick.Layouts
import "%s"
Item {
    id: root
    width: 200; height: 40
    property int clicks: 0
    RowLayout {
        Text { id: name; text: "a chat"; activeFocusOnTab: true }
        HoverButton { id: a; icon.name: "document-edit"; text: "Edit"; onClicked: root.clicks++ }
        HoverButton { id: b; icon.name: "document-send"; text: "Send"; usable: false; onClicked: root.clicks += 100 }
    }
    function report() {
        return [a.activeFocus, a.visualFocus, b.activeFocus, root.clicks, a.children[0].active, a.Accessible.name].join(" ")
    }
    function focusName() { name.forceActiveFocus() }
}
"""

BUTTON_SCRIPT = """import sys
from PySide6.QtCore import QUrl, QPoint, Qt, QMetaObject, Q_RETURN_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(50)
report = lambda: print(repr(QMetaObject.invokeMethod(r, "report", Q_RETURN_ARG("QVariant"))))
report()
QMetaObject.invokeMethod(r, "focusName"); QTest.keyClick(view, Qt.Key_Tab); QTest.qWait(50); report()
QTest.keyClick(view, Qt.Key_Space); QTest.keyClick(view, Qt.Key_Return); QTest.qWait(50); report()
QTest.keyClick(view, Qt.Key_Tab); QTest.qWait(50); report()
"""


class KeyedRowsTests(unittest.TestCase):
    @NEEDS_PLASMA_QML
    def test_a_change_touches_only_the_rows_that_came_went_moved_or_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "list.qml"
            qml.write_text(LIST % UI.as_uri())
            out = subprocess.run(["python3", "-c", LIST_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(steps[:10], [
            ["three", 3, 0, 3, [["a", 0], ["b", 10], ["c", 20]]],
            ["the same again: nothing runs", 3, 0, 3, [["a", 0], ["b", 10], ["c", 20]]],
            ["b changed: only its row reads it", 3, 0, 4, [["a", 0], ["b", 10], ["c", 20]]],
            ["b went: its row only", 3, 1, 4, [["a", 0], ["c", 10]]],
            ["kept", True, True],
            ["c moved up, d came", 4, 1, 5, [["c", 0], ["a", 10], ["d", 20]]],   # (laid out in their new order)
            ["moved", True, True],
            ["d moved to e: its row kept", 4, 1, 6, [["c", 0], ["a", 10], ["e", 20]]],
            ["renamed", True],
            ["a twice: two rows", 5, 2, 7, [["a", 0], ["a", 10], ["c", 20]]],
        ], out.stdout + out.stderr[-3000:])
        # many at once: from the next frame (the list's own draws first), a few a frame (each row
        # takes 4 ms here, a frame's go 12 ms), all of them soon after
        first, some, everything = steps[10], steps[11], steps[12]
        self.assertEqual(first, ["first go", 0])
        self.assertGreaterEqual(some[1], 1)
        self.assertLess(some[1], 20)
        self.assertEqual(everything, ["all", 40, 40])

    @NEEDS_PLASMA_QML
    def test_a_light_hover_button_takes_tab_and_keys_and_draws_its_frames_only_when_needed(self):
        # (a PlasmaComponents3.ToolButton each took milliseconds to make in a big popup: a line's
        # first hover made seven; now plain items, the theme's frames made only while one shows)
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "button.qml"
            qml.write_text(BUTTON % UI.as_uri())
            out = subprocess.run(["python3", "-c", BUTTON_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(steps, [
            "false false false 0 false Edit",   # nothing made for its frames
            "true true false 0 true Edit",      # Tab from the name: focused, its focus frame made
            "true true false 2 true Edit",      # Space and Enter click it
            "false false false 2 false Edit",   # Tab: past the greyed out one (no focus), frames gone
        ], out.stderr[-2000:])

    def test_an_accounts_chats_are_rows_kept_by_chat(self):
        section = (UI / "GroupSection.qml").read_text()
        self.assertIn("model: sessionRows.model", section)
        self.assertNotIn("model: section.group.sessions.length", section)
        row = section[section.index("model: sessionRows.model"):]
        row = row[:row.index("\n    }\n")]
        for wired in ("required property string key", "required property string rev",
                      "return sessionRows.item(key) || root.emptySession", "colors: listColors"):
            self.assertIn(wired, row)
        # by the chat's row key, its rev, and a chat moved to another id keeps its row
        self.assertIn("sessionRows.sync(section.sessions, s => root.rowKeyOf(s, host), s => s.rev,", section)
        self.assertIn("s.movedFrom && s.movedFrom.id ? root.rowKeyOf(", section)
        # made once the dashboard shows (a panel's popup: in its own window)
        self.assertIn("(!root.dashboardShown && sessionRows.model.count === 0)", section)
        keyed = (UI / "KeyedRows.qml").read_text()
        for part in ("model.move(was, at, 1)", "model.insert(at, {", "model.remove(i, 1)", 'model.setProperty(i, "rev"',
                     "budgetMs", "FrameAnimation {"):
            self.assertIn(part, keyed)

    def test_hide_takes_a_row_away_at_once_and_brings_it_back_if_it_fails(self):
        main = (UI / "main.qml").read_text()
        hide = main[main.index("    function hideItem(kind, id, host) {"):]
        hide = hide[:hide.index("\n    }\n")]
        self.assertLess(hide.index("hidingNow = Object.assign"), hide.index("hideRun("))   # (gone before jump.py runs)
        section = (UI / "GroupSection.qml").read_text()
        self.assertIn('if (!hiding["chats|" + section.remoteHost + "|" + s.sessionId])', section)
        self.assertIn("for (const s of section.sessions) {", section)   # (its pet goes too)
        # the status itself isn't filtered: what's tracked from it sees what's there
        handle = main[main.index("function handleOutput("):main.index("function celebrateResets(")]
        self.assertIn("status = parsed", handle)
        self.assertIn('dropHidden("", parsed)', handle)
        self.assertNotRegex(handle, r"status = .*hiding")
        hider = main[main.index("id: hider"):main.index("id: hideFailedTimer")]
        self.assertIn("delete next[what.key]", hider)          # (back in its list)
        self.assertIn("root.hideFailed = { key: what.key, message: result.message }", hider)
        row = (UI / "SessionRow.qml").read_text()
        self.assertIn('root.hideFailed.key === "chats|" + row.remoteHost + "|" + row.session.sessionId', row)
        self.assertIn('i18n("Couldn\'t hide it: %1", root.hideFailed.message)', row)

    def test_a_row_makes_only_what_it_shows(self):
        row = (UI / "SessionRow.qml").read_text()
        for made in ("sourceComponent: PermissionAsk {", "sourceComponent: Kirigami.InlineMessage {",
                     "active: row.showPeek && row.hasPeek", "active: row.hasPeek\n",
                     "active: row.handover !== null || row.goOnAt > 0 || row.goingOn !== null || row.kept !== null"):
            self.assertIn(made, row)
        # its tags: each made only when it shows, with the row's colors
        tags = row[row.index("id: tagLine"):row.index("// Its state, at the line's end")]
        self.assertEqual(len(re.findall(r"\n\s+(Tag|TestsBadge) \{", tags)), 0)
        self.assertEqual(tags.count("sourceComponent: Tag {") + tags.count("sourceComponent: TestsBadge {"), 13)
        self.assertEqual(tags.count("colors: row.colors"), 13)
        # its texts: plain Text with the row's colors, not a Label each
        self.assertNotIn("PlasmaComponents3.Label", row)
        self.assertNotIn("TextMetrics", row)
        self.assertNotIn("FontMetrics", row)
        for name in ("RecentLine.qml", "PlanLine.qml", "MemoryLine.qml"):
            line = (UI / name).read_text()
            self.assertNotIn("PlasmaComponents3.Label", line, name)
            self.assertIn("colors: ", line, name)
        tag = (UI / "Tag.qml").read_text()
        self.assertIn("readonly property var theme: colors || Kirigami.Theme", tag)
        self.assertIn("active: tag.icon !== \"\"", tag)
        self.assertNotIn("import org.kde.plasma.components", tag)
        tip = (UI / "TipArea.qml").read_text()
        self.assertIn("hover.hovered && Window.window !== null", tip)   # (its window asked only on hover)
        palette = (UI / "ListPalette.qml").read_text()
        for name in ("textColor", "negativeTextColor", "smallFont", "ctxWidth", "whoWidth"):
            self.assertIn("readonly property ", palette)
            self.assertIn(name, palette)
        text = (UI / "RowText.qml").read_text()
        self.assertIn("textFormat: Text.PlainText", text)
        self.assertIn("Accessible.name: text", text)

    def test_copies_share_a_check_and_covered_ones_rest(self):
        main = (UI / "main.qml").read_text()
        hub = (UI / "hub/Hub.qml").read_text()
        self.assertIn("function parse(text) {", hub)
        handle = main[main.index("function handleOutput("):main.index("function celebrateResets(")]
        self.assertIn("parsed = Hub.parse(stdout)", handle)
        self.assertNotIn("JSON.parse(stdout)", handle)
        # a copy on the desktop under windows holds the newest answers back (not the copy that notifies,
        # nor one with a Talpy Chat window open), and shows them once uncovered, its trackers primed again
        self.assertIn("readonly property bool holdAnswers: onDesktop && shownInPlace && coveredByWindow && !notifier", main)
        self.assertIn("&& !paneWindows.some(w => w.visible)", main)
        hold = main[main.index("function applyHeld(force) {"):main.index("    Connections {\n        target: Hub")]
        self.assertIn('primedSources = Object.assign({}, primedSources, { "": false })', hold)
        self.assertIn("handleRemote(host, held[host])", hold)
        self.assertIn("root.applyHeld(true)", main)   # (the shortcut: what it held back first)
        # the answer's stamp: what's new is known from its first line
        self.assertIn('/^\\{"stamp": *"(\\w+)"/', main)
        code = (UI.parent / "code/talpy_den.py").read_text()
        self.assertIn("text = stamped(text)", code)
        self.assertIn('ROW_LISTS = ("sessions", "recent", "starred", "starredPlans", "instructions")', code)

    def test_what_shows_rarely_is_made_when_it_first_shows(self):
        section = (UI / "GroupSection.qml").read_text()
        for made in ("sourceComponent: NewChatBox {", "sourceComponent: StatsPanel {", "sourceComponent: OpenInSwitch {",
                     "sourceComponent: MoreButton {"):
            self.assertIn(made, section)
        self.assertNotRegex(section, r"\n    (NewChatBox|StatsPanel|OpenInSwitch|MoreButton) \{")
        full = (UI / "FullRepresentation.qml").read_text()
        for made in ("sourceComponent: SearchResults {}", "sourceComponent: FocusView {}", "sourceComponent: Kirigami.InlineMessage {",
                     "sourceComponent: PlasmaExtras.PlaceholderMessage {"):
            self.assertIn(made, full)
        projects = full[full.index('source: "ProjectsView.qml"') - 400:full.index('source: "ProjectsView.qml"')]
        self.assertIn('active: root.popupTab === "projects" || made', projects)   # (kept once made)
        view = (UI / "ProjectsView.qml").read_text()
        self.assertIn("model: view.cardRows.model", view)
        main = (UI / "main.qml").read_text()
        self.assertIn("if (text !== root.projectsText || root.projectsData === null)", main)
        # tooltips' words: worked out while the pointer is on them
        row = (UI / "SessionRow.qml").read_text()
        self.assertIn("function openHint() {", row)
        self.assertIn('mainText: !containsMouse ? "" : Plasmoid.configuration.clickOpensPane', row)
        self.assertIn("function reopenHint() {", (UI / "RecentLine.qml").read_text())


if __name__ == "__main__":
    unittest.main()
