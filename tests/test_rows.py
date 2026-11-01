"""A row's buttons (HoverButtons.qml) show on hover, and also for the
keyboard and a finger, which can't hover: while the line's name or one of its
buttons has the keyboard's focus (Tab), and after a press and hold
(TouchHold.qml). A mouse does what it did. They're made the first time they
show, and kept: made with every line, they made a list slow to open."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_pets import NEEDS_PLASMA_QML

UI = Path(__file__).resolve().parent.parent / "package/contents/ui"

LINE = """import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import "%s"
Item {
    id: root
    width: 400; height: 100
    property bool dashboardShown: true
    property string log: ""
    property int made: 0   // (buttons made)
    function note(s) { log = log + s + " " }
    ColumnLayout {
        width: 400
        RowLayout {
            Layout.fillWidth: true
            HoverHandler { id: lineHover }
            TouchHold { buttons: lineButtons }
            PlasmaComponents3.Label {
                id: name
                text: "a chat"
                Layout.preferredWidth: 150
                activeFocusOnTab: true
                MouseArea {
                    anchors.fill: parent
                    onClicked: if (!lineButtons.holding) root.note("click")
                    TouchHold { buttons: lineButtons }
                }
            }
            Item { Layout.fillWidth: true; implicitHeight: 20 }
            HoverButtons {
                id: lineButtons
                lineHeight: 20
                shown: lineHover.hovered || name.activeFocus || lineButtons.focused || lineButtons.held
                onShownChanged: root.note(shown ? "shown" : "hidden")
                RowLayout {
                    spacing: 0
                    PlasmaComponents3.ToolButton { text: "1"; Layout.preferredWidth: 30; onActiveFocusChanged: if (activeFocus) root.note("b1"); Component.onCompleted: root.made++ }
                    PlasmaComponents3.ToolButton { text: "2"; Layout.preferredWidth: 30; onActiveFocusChanged: if (activeFocus) root.note("b2"); Component.onCompleted: root.made++ }
                }
            }
        }
        PlasmaComponents3.Label { text: "after"; activeFocusOnTab: true; onActiveFocusChanged: if (activeFocus) root.note("after") }
    }
}
"""

SCRIPT = """import sys
from PySide6.QtCore import QUrl, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
print(repr("made %d" % r.property("made")))
view.show(); QTest.qWaitForWindowExposed(view); view.requestActivate(); QTest.qWait(100)
QTest.mouseMove(view, QPoint(390, 90)); QTest.qWait(100)
touch = QTest.createTouchDevice()
name, beside = QPoint(20, 10), QPoint(250, 10)
def hold(at, ms):
    QTest.touchEvent(view, touch).press(0, at, view).commit(); QTest.qWait(ms)
    QTest.touchEvent(view, touch).release(0, at, view).commit()
def mouse_hold(at, ms):
    QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, at); QTest.qWait(ms)
    QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, at)
steps = [lambda: QTest.keyClick(view, Qt.Key_Tab)] * 4 + [
    lambda: hold(name, 1200), lambda: hold(beside, 1200), lambda: hold(beside, 1200),
    lambda: r.setProperty("dashboardShown", False), lambda: mouse_hold(name, 1200)]
for step in steps:
    r.setProperty("log", ""); step(); QTest.qWait(300); print(repr(r.property("log").strip()))
print(repr("made %d" % r.property("made")))
"""


@NEEDS_PLASMA_QML
class RowButtonsTests(unittest.TestCase):
    def test_the_keyboard_and_a_finger_get_a_rows_buttons_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "line.qml"
            qml.write_text(LINE % UI.as_uri())
            out = subprocess.run(["python3", "-c", SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(steps, [
            "made 0",         # (none made before they show)
            "shown",          # Tab: on the name
            "b1", "b2",       # then on its buttons, which stay
            "hidden after",   # and past them
            "shown",          # a finger holds the name: no click, and they stay
            "hidden", "shown",  # held again, beside it: gone; and back
            "hidden",         # the popup hides
            "shown click",    # a mouse on the name shows them (hover) and, held, still clicks
            "made 2",         # (made once, then kept)
        ], out.stderr[-2000:])

    def test_every_line_with_buttons_shows_them_for_the_keyboard_and_a_finger(self):
        # a chat's row, a recent chat's, a plan's and a memory's line
        rows = "".join((UI / name).read_text() for name in ("SessionRow.qml", "RecentLine.qml", "PlanLine.qml", "MemoryLine.qml"))
        for name, buttons, mouse in (("nameLabel", "rowButtons", "nameMouse"), ("recentName", "recentButtons", "recentMouse"),
                                     ("planName", "planButtons", "planMouse"), ("memoryName", "memoryButtons", "memoryMouse")):
            with self.subTest(buttons):
                self.assertRegex(rows, r"%s\.activeFocus \|\| %s\.focused \|\| %s\.held" % (name, buttons, buttons))
                self.assertEqual(len(re.findall(r"TouchHold \{\s+buttons: %s\s+\}" % buttons, rows)), 2)
                self.assertIn("if (!%s.holding)" % buttons, rows)
                label = rows[rows.index("id: %s\n" % name):rows.index("id: %s\n" % mouse)]
                self.assertIn("activeFocusOnTab: true", label)
                self.assertIn("Keys.onReturnPressed", label)

    def test_a_queued_task_is_a_line_as_a_recent_chats(self):
        # One line: its mark, what it is, its folder and when it starts at the
        # end; Start now and Cancel only on hover, Tab or a finger's hold, over
        # that end (both showed all the time, and in VS Code "starts in…" had
        # a line of its own)
        qml = (UI / "GroupSection.qml").read_text()
        line = qml[qml.index("id: queuedLine\n"):qml.index("ConfirmLine {", qml.index("id: queuedLine\n"))]
        self.assertRegex(line, r"queuedName\.activeFocus \|\| queuedButtons\.focused \|\| queuedButtons\.held")
        self.assertEqual(len(re.findall(r"TouchHold \{\s+buttons: queuedButtons\s+\}", line)), 2)
        self.assertIn("covered: queuedButtons.covering", line)
        self.assertIn("under: queuedEnd", line)
        buttons = line[line.index("HoverButtons {"):]
        self.assertEqual(line.count("PlasmaComponents3.ToolButton"), buttons.count("PlasmaComponents3.ToolButton"))
        self.assertEqual(buttons.count("PlasmaComponents3.ToolButton"), 2)
        self.assertIn("Icons.plasma.startNow", buttons)
        self.assertIn("Icons.plasma.cancel", buttons)

        tsx = (UI.parent.parent.parent / "vscode/webview/components/QueuedTasks.tsx").read_text()
        row = tsx[tsx.index('<div class="recent-item queued-line"'):tsx.index("</div>\n      {t.error")]
        self.assertIn('class="queued-what"', row)
        self.assertIn('class="queued-when', row)              # (on the same line, at its end)
        self.assertIn('"row-actions"', row)                   # (hover buttons, as a recent chat's)
        self.assertIn("woken", row)                           # (made the first time they show)
        self.assertIn("icon={I.startNow}", row)
        self.assertIn("icon={I.cancel}", row)

    def test_the_tabs_stand_in_one_order_everywhere(self):
        # your chats now, then your work by project, the permissions you gave, the Recap
        repo = UI.parent.parent.parent
        full = (UI / "FullRepresentation.qml").read_text()
        self.assertIn('readonly property var tabOrder: ["chats", "projects", "perms", "week"]', full)
        self.assertNotIn('["chats", "week", "perms", "projects"]', full)
        names = re.findall(r'text: i18n\("([^"]+)"\)\n\s+onClicked: root\.popupTab = "(\w+)"', full)
        self.assertEqual([t for _, t in names], ["chats", "projects", "perms", "week"])
        ui = (repo / "vscode/webview/util/ui.ts").read_text()
        self.assertIn('TAB_ORDER: readonly Tab[] = ["chats", "projects", "perms", "week"]', ui)
        gnome = (repo / "gnome/extension/indicator.js").read_text()
        self.assertIn("[['chats', 'Talpy Den'], ['perms', 'Permissions'], ['week', 'Recap']]", gnome)

    def test_a_kept_chats_tag_says_why_it_is_red_everywhere(self):
        # Keeps going (gave up) with an error, (can't go on now) with a note, in Plasma as in VS Code
        repo = UI.parent.parent.parent
        row = (UI / "SessionRow.qml").read_text()
        tag = row[row.index("icon: Icons.plasma.keepGoing"):]
        tag = tag[:tag.index("onClicked:")]
        self.assertRegex(tag, r'row\.kept && row\.kept\.error \? i18nc\("[^"]+", "Keeps going \(gave up\)"\)')
        self.assertRegex(tag, r'row\.kept && row\.kept\.note \? i18nc\("[^"]+", "Keeps going \(can\'t go on now\)"\)')
        self.assertIn('warning: row.kept !== null && (!!row.kept.error || !!row.kept.note)', tag)
        tsx = (repo / "vscode/webview/components/SessionRow.tsx").read_text()
        self.assertIn('"Keeps going" + (kept.error ? " (gave up)" : kept.note ? " (can\'t go on now)" : "")', tsx)

    def test_delete_asks_on_its_line_everywhere(self):
        # Delete… under a chat, a plan or a memory asks on the line itself, as Plasma's DeleteAsk:
        # what it's looking at, then the question in orange with Delete (the red trash) and Cancel
        # beside it, or why it can't be deleted in red with OK; VS Code asked in a modal dialog
        repo = UI.parent.parent.parent
        plasma = (UI / "DeleteAsk.qml").read_text()
        for words in ('i18n("Looking at what it would delete…")', 'confirmText: i18n("Delete")', 'confirmIcon: "delete"', 'i18n("OK")'):
            self.assertIn(words, plasma)
        comp = repo / "vscode/webview/components"
        ask = (comp / "DeleteAsk.tsx").read_text()
        self.assertIn("Looking at what it would delete…", ask)
        self.assertIn('<div class="confirm delete-ask">', ask)
        self.assertRegex(ask, r'<Icon name=\{I\.delete\} tone=\{T\.delete\} />Delete\n')
        self.assertIn('onClick={close}>Cancel</button>', ask)
        self.assertIn('onClick={close}>OK</button>', ask)
        self.assertIn('post({ type: "deleteDescribe", key, ...what })', ask)
        for name, kind in (("SessionRow.tsx", "chat"), ("RecentLine.tsx", "chat"), ("PlanLine.tsx", "plan"), ("MemoryLine.tsx", "memory")):
            text = (comp / name).read_text()
            self.assertRegex(text, r'onClick=\{\(\) => askDelete\([^,]+, \{ kind: "%s"' % kind, name)
            self.assertIn("<DeleteAsk itemKey=", text, name)
            self.assertNotIn('post({ type: "delete"', text, name)
        actions = (repo / "vscode/src/actions.ts").read_text()
        self.assertNotIn('{ modal: true }, "Delete"', actions)

    def test_a_projects_dots_stand_top_right_and_its_buttons_cover_its_folder_line(self):
        # (the buttons kept their room after the dots on the name's line, so the
        # dots stood a few buttons in from the edge)
        qml = (UI / "ProjectsView.qml").read_text()
        head = qml[qml.index("id: projectName"):qml.index("TapHandler {", qml.index("id: projectName"))]
        self.assertLess(head.index("Row {\n"), head.index("id: metaLine"))           # dots: on the name's line
        meta = head[head.index("id: metaLine"):]
        self.assertIn("id: headButtons", meta)                                        # buttons: on the folder's
        self.assertIn("anchors.right: parent.right", meta)
        self.assertNotIn("Layout.preferredWidth", meta[meta.index("id: headButtons"):meta.index("sourceComponent")])
        self.assertIn("card.buttonsShown && headButtons.item ? headButtons.width", meta)   # (its end cut under them)
        tsx = (UI.parent.parent.parent / "vscode/webview/components/ProjectsView.tsx").read_text()
        self.assertLess(tsx.index('class="project-dots"'), tsx.index('class="project-actions"'))
        css = (UI.parent.parent.parent / "vscode/webview/styles.css").read_text()
        actions = css[css.index(".project-actions {"):]
        self.assertIn("position: absolute;", actions[:200])
        self.assertIn("bottom: 2px;", actions[:200])

    def test_a_projects_dots_take_the_rows_colour_red_for_a_limit(self):
        # Two chats a usage limit stopped showed as two green dots on their
        # project (their state is idle), where their rows are red (2026-11-01)
        repo = UI.parent.parent.parent
        main = (UI / "main.qml").read_text()
        rule = main[main.index("function rowColor(s)"):main.index("function usageColor")]
        self.assertIn('s.reason === "failed" || (s.stopped && !s.stopped.over)', rule)
        self.assertIn("negativeTextColor", rule)
        qml = (UI / "ProjectsView.qml").read_text()
        self.assertIn("root.rowColor(card.here[index].session)", qml)
        self.assertNotIn("root.stateColor(card.here[index]", qml)
        row = (repo / "vscode/webview/components/SessionRow.tsx").read_text()
        self.assertIn('return s.stopped && !s.stopped.over ? "st-failed" : stateClass(s.state, s.reason);', row)
        for name in ("ProjectsView.tsx", "FocusView.tsx"):
            tsx = (repo / "vscode/webview/components" / name).read_text()
            self.assertIn("dotClass(s)", tsx, name)
            self.assertNotIn("st-${s.state}", tsx, name)

    def test_what_a_line_rarely_needs_is_made_only_when_needed(self):
        # Opening Recent chats, Plans or Memories made every line's buttons,
        # Delete question, keep-only question, a plan's new-chat box and its
        # tags' pane tooltips at once: 30-50 ms a line (2026-10-30)
        ui = {name: (UI / name).read_text() for name in ("HoverButtons.qml", "DeleteAsk.qml", "KeepOnlyMessage.qml",
                                                         "TipArea.qml", "RecentLine.qml", "PlanLine.qml", "SessionRow.qml")}
        self.assertIn("default property Component buttons", ui["HoverButtons.qml"])
        self.assertIn("active: hover.shown || hover.made", ui["HoverButtons.qml"])
        self.assertRegex(ui["DeleteAsk.qml"], r"\nLoader \{[^}]*active: itemKey !== \"\" && asked\.key === itemKey")
        self.assertRegex(ui["KeepOnlyMessage.qml"], r"\nLoader \{[^}]*active: shown")
        self.assertIn("sourceComponent: ConfirmLine {", ui["KeepOnlyMessage.qml"])   # (a question as every one)
        self.assertIn("active: tip.inPane", ui["TipArea.qml"])
        self.assertIn("sourceComponent: NewChatBox {\n            visible: false", ui["PlanLine.qml"])
        for name in ("RecentLine.qml", "SessionRow.qml"):
            self.assertNotRegex(ui[name], r"KeepOnlyMessage \{[^}]*visible:", name)
        # a line's rarely shown tags (Limit, ↻, To review, its tests, ↩ Send) and its account: made only when they show
        for name, tags in (("RecentLine.qml", ("AccountTag {", "Tag {", "Tag {", "Tag {", "TestsBadge {")),
                           ("PlanLine.qml", ("AccountTag {", "Tag {"))):
            self.assertEqual(re.findall(r"sourceComponent: (\w*Tag \{|TestsBadge \{)", ui[name]), list(tags), name)
            self.assertEqual(len(re.findall(r"\n        (Tag|TestsBadge|AccountTag) \{", ui[name])), 0, name)

    def test_lists_grow_a_page_at_a_time_and_projects_make_their_lines_when_opened(self):
        # The main tab's lists show a page at a time ("Show N more": only the
        # new page's lines are made), the Plans and Memories folds left it for
        # the Projects tab, where a project's lines are made when it opens
        # (2026-10-31)
        section = (UI / "GroupSection.qml").read_text()
        projects = (UI / "ProjectsView.qml").read_text()
        main = (UI / "main.qml").read_text()
        for gone in ("togglePlans", "toggleMemories", "expandedPlans", "expandedMemories"):
            self.assertNotIn(gone, section + main)
        self.assertIn("ListModel {", (UI / "PageRows.qml").read_text())
        for rows in ("recentRows", "starredRows", "starredPlanRows"):
            self.assertIn("model: section.%s ? %s : 0" % ({"recentRows": "recentOpen", "starredRows": "starredOpen",
                                                           "starredPlanRows": "starredPlansOpen"}[rows], rows), section)
        self.assertEqual(section.count("MoreButton {"), 3)
        self.assertIn("section.group.instructions", section)   # (CLAUDE.md, its own line)
        self.assertIn('" --plans 0 --memories 0"', main)
        self.assertRegex(projects, r"Loader \{\s+active: card\.unfolded")
        self.assertIn("model: PageRows { size: inside.chatsShown }", projects)
        self.assertIn("active: due", projects)   # (its plans and memories: the frame after)
        self.assertIn("root.showProject(projectRow.project.path)", (UI / "WeekView.qml").read_text())


if __name__ == "__main__":
    unittest.main()
