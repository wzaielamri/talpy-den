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
        self.assertEqual(line.count("HoverButton {"), buttons.count("HoverButton {"))
        self.assertEqual(buttons.count("HoverButton {"), 2)
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

    def test_a_lines_name_stops_where_its_hover_buttons_start(self):
        # A line's end (CoveredEnd) is at least as wide as its buttons while they show, so the
        # name before it is cut there, not run under them (a starred plan has no folder)
        end = (UI / "CoveredEnd.qml").read_text()
        self.assertIn("import QtQuick.Layouts", end)
        self.assertIn("Layout.minimumWidth: covered", end)
        for name in ("PlanLine.qml", "RecentLine.qml", "MemoryLine.qml"):
            self.assertRegex((UI / name).read_text(), r"covered: \w+Buttons\.covering", name)

    def test_a_kept_chat_shows_its_tag_with_nothing_else_to_say(self):
        # A kept chat at work with no step or tasks (yet): its Keeps going still shows, as in VS Code,
        # whose line with it shows whenever the chat is kept, goes on later or can (handover || goOn || goingOn || kept)
        repo = UI.parent.parent.parent
        row = (UI / "SessionRow.qml").read_text()
        end = row.index("implicitHeight: stepRow.implicitHeight")
        visible = row[row.rindex("visible:", 0, end):end]
        for part in ('row.stepText !== ""', "row.tasks !== null", "row.kept !== null", "row.goingOn !== null",
                     "row.handover !== null", "row.goOnAt > 0"):
            self.assertIn(part, visible)
        tsx = (repo / "vscode/webview/components/SessionRow.tsx").read_text()
        self.assertIn("{handover || goOn || goingOn || kept ? (", tsx)
        # and at the line's right end in both, as Plasma's step line puts them after its text
        css = (repo / "vscode/webview/styles.css").read_text()
        rule = css[css.index(".handover {"):]
        self.assertIn("justify-content: flex-end;", rule[:rule.index("}")])

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

    def test_the_projects_tab_reads_each_ssh_host_shown_on_its_own(self):
        # The Projects tab listed only this computer's projects (2026-11-05):
        # each host shown is read there, on its own, and its lines act there
        repo = UI.parent.parent.parent
        main = (UI / "main.qml").read_text()
        load = main[main.index("function loadProjects()"):main.index("function loadLocalProjects()")]
        self.assertIn("for (const host of answeredHosts)", load)
        self.assertIn("loadHostProjects(host)", load)
        self.assertIn('" --projects --on " + shellQuote(host)', main)
        self.assertNotIn("if (!what.host && root.projectsShown)", main)   # (a host's change reads that host again)
        self.assertEqual(main.count("root.reloadProjects(what.host)"), 3)
        qml = (UI / "ProjectsView.qml").read_text()
        for wired in ("remoteHost: card.host", "root.groupOfProfile(chat.profileDir, card.host)", "root.newChatInProject(card.project, card.host)",
                      'root.hideItem("projects", card.project.path, card.host)', "c.host === dragged.host", '"drop|" + card.key'):
            self.assertIn(wired, qml)
        self.assertEqual(qml.count("remoteHost: card.host"), 3)   # (its chats, plans and memories)
        view = (repo / "vscode/src/view.ts").read_text()
        self.assertIn("this.dash.answeringHosts().map((h) => this.dash.readHostProjects(h))", view)
        self.assertNotIn("m.host ? null : findProject", view)
        backend = (repo / "vscode/src/backend.ts").read_text()
        self.assertIn('["week.py", "--projects", "--on", host]', backend)
        tsx = (repo / "vscode/webview/components/ProjectsView.tsx").read_text()
        self.assertIn("<HostProjectsSection", tsx)
        self.assertIn("drag.host === host", tsx)

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
        self.assertIn("root.showProject(projectRow.project.folder || projectRow.project.path)", (UI / "WeekView.qml").read_text())


STAR = """import QtQuick
import QtQuick.Layouts
import "%s"
Item {
    id: root
    width: 300; height: 40
    property bool buttonsShown: false
    RowLayout {
        StarMark { id: on; objectName: "on"; starred: true; hidden: root.buttonsShown }
        StarMark { id: off; objectName: "off"; starred: false }
    }
    function report() {
        const icon = m => m.children[0].item
        return [on.implicitWidth, off.implicitWidth, icon(on) !== null && icon(on).visible !== false && on.children[0].visible,
                icon(off) === null].join(" ")
    }
}
"""

STAR_SCRIPT = """import sys
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(50)
from PySide6.QtCore import QMetaObject, Q_RETURN_ARG, Q_ARG
def report():
    return QMetaObject.invokeMethod(r, "report", Q_RETURN_ARG("QVariant"))
print(repr(report()))
r.setProperty("buttonsShown", True); QTest.qWait(50)
print(repr(report()))
"""


class StarMarkTests(unittest.TestCase):
    """The ★ of a starred chat or plan stands right before the time at its
    line's end, every line keeping its room so the times line up, and hides
    while the line's buttons show (hover, Tab, a finger's hold), their star
    button unstarring it, as in VS Code (2026-11-01)"""

    def test_it_stands_right_before_the_time_and_hides_under_the_buttons(self):
        for name, line, buttons, starred in (("RecentLine.qml", "recentLine", "recentButtons", "recentLine.chat.starred"),
                                             ("PlanLine.qml", "planLine", "planButtons", "planLine.plan.starred")):
            with self.subTest(name):
                qml = (UI / name).read_text()
                end = qml[qml.index("CoveredEnd {"):qml.index("HoverButtons {")]
                star = end.index("StarMark {")
                self.assertLess(end.index("horizontalAlignment: Text.AlignRight"), star)   # (after its folder)
                self.assertLess(star, end.index("Layout.preferredWidth: root.agoWidth"))   # (before the time)
                self.assertEqual(qml.count("StarMark {"), 1)                               # (nowhere else on the line)
                self.assertIn("starred: !!%s" % starred, end)                              # (its room on every line)
                self.assertIn("hidden: %s.shown" % buttons, end)                           # (hover, Tab and a hold)
                self.assertIn("readonly property real endWidth: root.endWidth(folderWidth)", qml)
                # the buttons' star stars it, or (yellow) unstars it
                toggle = qml[qml.index("icon.name: %s ? Icons.plasma.starred : Icons.plasma.star" % starred):]
                toggle = toggle[:toggle.index("PlasmaCore.ToolTipArea")]
                self.assertIn('Icons.color(%s ? "starred" : "star", Kirigami.Theme)' % starred, toggle)
                self.assertRegex(toggle, r"root\.setStar\([^)]*, !%s\)" % re.escape(starred))
                self.assertNotIn("visible: !%s" % starred, qml)
        main = (UI / "main.qml").read_text()
        self.assertIn("return folderWidth + Kirigami.Units.iconSizes.small + agoWidth + 2 * Kirigami.Units.smallSpacing", main)
        # lines without a star keep its room: a memory's (in a project's lists) and what Find a chat found
        memory = (UI / "MemoryLine.qml").read_text()
        self.assertIn("readonly property real endWidth: root.endWidth(folderWidth)", memory)
        for name, text in (("MemoryLine.qml", memory), ("FoundEnd.qml", (UI / "FoundEnd.qml").read_text())):
            room = text.index("Layout.preferredWidth: Kirigami.Units.iconSizes.small\n")
            self.assertLess(room, text.index("Layout.preferredWidth: root.agoWidth"), name)
        self.assertIn("starred: !!row.session.starred", (UI / "SessionRow.qml").read_text())   # (a running chat's: after its name)

    def test_vscode_puts_it_right_before_the_time_too(self):
        components = Path(__file__).resolve().parent.parent / "vscode/webview/components"
        for name, item in (("RecentLine.tsx", "c"), ("PlanLine.tsx", "p")):
            with self.subTest(name):
                tsx = (components / name).read_text()
                folder, star, ago = (tsx.index('class="recent-folder'), tsx.index('class="star-mark"'), tsx.index('class="recent-ago'))
                self.assertLess(folder, star)
                self.assertLess(star, ago)
                self.assertIn(': <span class="star-mark" aria-hidden="true" />}', tsx)   # (its room on every line)
                self.assertIn("tabIndex={-1}", tsx)   # (the buttons' star has the keyboard)
                self.assertIn("icon={%s.starred ? I.starred : I.star}" % item, tsx)
                self.assertIn("tone={%s.starred ? T.starred : undefined}" % item, tsx)
                self.assertIn("on: !%s.starred" % item, tsx)
                self.assertNotIn("{%s.starred ? null : (" % item, tsx)
        memory = (components / "MemoryLine.tsx").read_text()
        self.assertLess(memory.index('<span class="star-mark" aria-hidden="true" />'), memory.index('class="recent-ago'))
        css = (components.parent / "styles.css").read_text()
        self.assertRegex(css, r"\.recent-item > \.star-mark \{\s+width: 16px;")
        self.assertRegex(css, r"\.recent-item:hover > \.star-mark,\s+\.recent-item:has\(:focus-visible\) > \.star-mark \{\s+visibility: hidden;")

    @NEEDS_PLASMA_QML
    def test_a_line_without_a_star_keeps_its_room_and_makes_nothing_in_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "star.qml"
            qml.write_text(STAR % UI.as_uri())
            out = subprocess.run(["python3", "-c", STAR_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(steps, ["16 16 true true",      # starred: shown; not: as wide, nothing made
                                 "16 16 false true"],    # the buttons show: hidden, its room kept
                         out.stderr[-2000:])


BUTTONS = """import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import "%s"
Item {
    id: root
    width: 300; height: 40
    property int clicks: 0
    property int offClicks: 0
    RowLayout {
        spacing: 0
        HoverButton { id: on; icon.name: "document-edit"; text: "Edit"; onClicked: root.clicks++ }
        HoverButton { id: off; icon.name: "document-send"; text: "Send"; usable: false; onClicked: root.offClicks++ }
        IconTextButton { id: words; icon.name: "clock"; text: "Go on at 03:00"; Layout.preferredHeight: 18 }
    }
    function report() {
        const icon = words.contentItem.children[0].children[0]   // (its row: a grid with the icon, then its words)
        return [on.width, on.height, on.contentItem.width, on.contentItem.height, on.contentItem.opacity,
                off.contentItem.opacity, off.focusPolicy === Qt.NoFocus, off.hoverEnabled,
                icon.width, icon.height, words.spacing, root.clicks, root.offClicks].join(" ")
    }
}
"""

BUTTONS_SCRIPT = """import sys
from PySide6.QtCore import QUrl, QPoint, Qt, QMetaObject, Q_RETURN_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(100)
QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(10, 20)); QTest.qWait(50)
QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(30, 20)); QTest.qWait(50)
print(repr(QMetaObject.invokeMethod(r, "report", Q_RETURN_ARG("QVariant"))))
"""


class HoverButtonTests(unittest.TestCase):
    """A line's buttons draw their icons at 16 px, as the line's own icons
    and VS Code's: the theme's button margins left a 20 px button 10 px for
    its icon, drawn at 8 to 10 px (2026-11-02). A greyed out one shows its
    icon at 40%, as VS Code's, where enabled: false left 13%."""

    def test_every_lines_buttons_are_hover_buttons(self):
        for name in ("RecentLine.qml", "PlanLine.qml", "MemoryLine.qml", "SessionRow.qml", "GroupSection.qml"):
            qml = (UI / name).read_text()
            for start in [m.start() for m in re.finditer(r"\n\s+HoverButtons \{", qml)]:
                block = qml[start:qml.index("\n" + " " * (qml.index("H", start) - start - 1) + "}", start)]
                with self.subTest(name):
                    self.assertIn("RowLayout {", block)
                    self.assertGreater(block.count("HoverButton {"), 0)
                    self.assertNotIn("ToolButton", block)
                    self.assertNotRegex(block, r"\n\s+enabled:")          # (greyed out: usable, at 40%)
                    self.assertNotIn("icon.width", block)                 # (its size: HoverButton's)
        projects = (UI / "ProjectsView.qml").read_text()
        head = projects[projects.index("id: headButtons"):projects.index("id: headButtons") + 2500]
        self.assertEqual(head.count("HoverButton {"), 2)
        self.assertNotIn("ToolButton", head)
        button = (UI / "HoverButton.qml").read_text()
        self.assertIn("leftPadding: (Layout.preferredWidth - iconSize) / 2", button)
        self.assertIn("opacity: button.usable ? 1 : 0.4", button)

    def test_a_chats_words_buttons_are_as_tight_as_its_tag(self):
        row = (UI / "SessionRow.qml").read_text()
        line = row[row.index("// A usage limit stopped it: what's next"):row.index("Loader {\n                    active: row.hasPeek")]
        self.assertEqual(line.count("IconTextButton {"), 3)                # Continue on…, Go on at…, Keep going
        self.assertNotIn("ToolButton", line)
        # (2026-11-02, the user: closer together) 4 px apart, in a row of their
        # own 12 px from the words before them, as VS Code's
        self.assertEqual(line.count("Layout.leftMargin"), 1)
        # (made only when one shows: most rows have none)
        self.assertIn("Loader {   // (made only when it shows: most rows have none of these)\n"
                      "                    active: row.handover !== null || row.goOnAt > 0 || row.goingOn !== null || row.kept !== null\n"
                      "                    visible: active\n"
                      "                    Layout.leftMargin: Kirigami.Units.smallSpacing * 2\n"
                      "                    sourceComponent: RowLayout {\n"
                      "                        spacing: Kirigami.Units.smallSpacing\n", line)
        self.assertIn("on: row.goingOn !== null", line)                    # Goes on at…: a toggle that's on
        self.assertNotIn("Rectangle {", line)                              # (its frame: IconTextButton's)
        button = (UI / "IconTextButton.qml").read_text()
        self.assertIn("spacing: Kirigami.Units.smallSpacing / 2", button)  # (as Tag.qml's icon and words)
        # framed thin, as the Tag beside them, so they read as buttons, not words
        # (the user, of Continue on…); on: a faint tint in the frame too
        frame = button[button.index("    Rectangle {"):]
        self.assertIn("border.width: 1", frame)
        self.assertIn("border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)", frame)
        self.assertIn('color: button.on ? Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08) : "transparent"', frame)
        self.assertIn(": Qt.rgba(theme.textColor.r, theme.textColor.g, theme.textColor.b, 0.3)",   # (theme: a row's colors, or Kirigami's)
                      (UI / "Tag.qml").read_text())
        # VS Code: the same frame, 4 px apart; narrow, a button's words shorten
        # instead of the line running out past the row's left edge, over its
        # colour bar (the user's screenshot, 2026-11-02)
        repo = UI.parent.parent.parent
        css = (repo / "vscode/webview/styles.css").read_text()
        text_btn = css[css.index(".icon-btn.text-btn {"):][:300]
        self.assertIn("box-shadow: inset 0 0 0 1px var(--cs-tag-border);", text_btn[:text_btn.index("}")])
        handover = css[css.index(".handover {"):][:200]
        self.assertIn("gap: 3px 4px;", handover[:handover.index("}")])
        shrink = css[css.index(".handover > .icon-btn {"):][:200]
        for rule in ("flex: 0 1 auto;", "min-width: 0;", "max-width: 100%;"):
            self.assertIn(rule, shrink[:shrink.index("}")])
        words = css[css.index(".btn-words {"):][:200]
        for rule in ("min-width: 0;", "overflow: hidden;", "text-overflow: ellipsis;"):
            self.assertIn(rule, words[:words.index("}")])
        tsx = (repo / "vscode/webview/components/SessionRow.tsx").read_text()
        self.assertEqual(tsx.count('class="text-btn"'), 4)
        self.assertEqual(tsx.count('<span class="btn-words">'), 4)
        self.assertIn("x: tag.icon !== \"\" ? mark.x + mark.width + Kirigami.Units.smallSpacing / 2", (UI / "Tag.qml").read_text())

    @NEEDS_PLASMA_QML
    def test_their_icons_are_16_px_and_a_greyed_one_takes_no_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "buttons.qml"
            qml.write_text(BUTTONS % UI.as_uri())
            out = subprocess.run(["python3", "-c", BUTTONS_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(steps, ["20 22 16 16 1 0.4 true false 16 16 2 1 0"], out.stderr[-2000:])


# A recent chat's line (a column without spacing: the shade first in it) and
# a chat's row (a row: the shade in its first item, the pet's bar), each with
# a twin without a shade, to see that the shade takes no room
SHADE = """import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import "%s"
Item {
    id: root
    width: 400; height: 300
    function at(item, from) { const p = item.mapToItem(from || root, 0, 0); return [Math.round(p.x), Math.round(p.y)] }
    function box(item) { return at(item).concat([Math.round(item.width), Math.round(item.height)]) }
    function report() {
        return JSON.stringify({
            line: box(lineA), name: box(nameA), lineName: at(nameA, lineA), lineTwin: at(twinNameA, twinA), lineH: [lineA.height, twinA.height],
            row: box(rowB), rowBar: at(barB, rowB), rowName: at(nameB, rowB), rowTwin: [at(twinBarB, twinB), at(twinNameB, twinB)],
            lineShade: box(shadeA.children[0].item), rowShade: box(shadeB.children[0].item)})
    }
    function shown() { return [shadeA.children[0].item.visible, shadeB.children[0].item.visible].join(" ") }
    ColumnLayout {
        x: 20; y: 10; width: 360
        spacing: 4
        ColumnLayout {
            id: lineA
            Layout.fillWidth: true
            spacing: 0
            HoverHandler { id: hoverA }
            HoverShade { id: shadeA; made: true; target: lineA; shown: hoverA.hovered; side: 4; pad: 2 }   // (made: made on a first hover)
            RowLayout {
                Layout.fillWidth: true
                PlasmaComponents3.Label {
                    id: nameA; text: "a recent chat"
                    MouseArea { anchors.fill: parent; hoverEnabled: true }   // (as its name's: it takes the hover)
                }
            }
            PlasmaComponents3.Label { text: "its second line" }
        }
        ColumnLayout {
            id: twinA
            Layout.fillWidth: true
            spacing: 0
            RowLayout { Layout.fillWidth: true; PlasmaComponents3.Label { id: twinNameA; text: "a recent chat" } }
            PlasmaComponents3.Label { text: "its second line" }
        }
        RowLayout {
            id: rowB
            Layout.fillWidth: true
            spacing: 6
            HoverHandler { id: hoverB }
            Rectangle {
                id: barB; Layout.fillHeight: true; Layout.preferredWidth: 6; color: "orange"
                HoverShade { id: shadeB; made: true; z: -1; target: rowB; shown: hoverB.hovered; side: 4; pad: 2 }
            }
            PlasmaComponents3.Label { id: nameB; text: "a chat"; Layout.fillWidth: true }
        }
        RowLayout {
            id: twinB
            Layout.fillWidth: true
            spacing: 6
            Rectangle { id: twinBarB; Layout.fillHeight: true; Layout.preferredWidth: 6; color: "orange" }
            PlasmaComponents3.Label { id: twinNameB; text: "a chat"; Layout.fillWidth: true }
        }
    }
}
"""

SHADE_SCRIPT = """import json, sys
from PySide6.QtCore import QUrl, QPoint, QMetaObject, Q_RETURN_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(100)
call = lambda name: QMetaObject.invokeMethod(r, name, Q_RETURN_ARG("QVariant"))
geo = json.loads(call("report")); print(repr(json.dumps(geo)))
mid = lambda b, dx=None: QPoint(b[0] + (b[2] // 2 if dx is None else dx), b[1] + b[3] // 2)
QTest.mouseMove(view, QPoint(390, 290)); QTest.qWait(400); print(repr(call("shown")))
for at in (mid(geo["name"]), mid(geo["line"], geo["line"][2] - 10), mid(geo["row"]), QPoint(390, 290)):
    QTest.mouseMove(view, at); QTest.qWait(400); print(repr(call("shown")))
"""


@NEEDS_PLASMA_QML
class HoverShadeTests(unittest.TestCase):
    """A line is shaded while the pointer is on it (2026-11-02), as a row in
    VS Code's list (--vscode-list-hoverBackground) and GNOME's: a chat's row,
    a recent or starred chat's line, a plan's, a memory's, a queued task's, a
    Focus or project line, a subagent, a project's own line in the Projects
    tab. Plasma's had only its buttons."""

    def test_it_covers_the_whole_line_takes_no_room_and_follows_the_pointer(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "shade.qml"
            qml.write_text(SHADE % UI.as_uri())
            out = subprocess.run(["python3", "-c", SHADE_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertEqual(len(steps), 6, out.stderr[-2000:])
        geo = json.loads(steps[0])
        # no room taken: what's in the line stands where it stands without a shade
        self.assertEqual(geo["lineName"], geo["lineTwin"])
        self.assertEqual(geo["lineH"][0], geo["lineH"][1])
        self.assertEqual([geo["rowBar"], geo["rowName"]], geo["rowTwin"])
        # the whole line, side (4) past its left and right, pad (2) above and below
        x, y, w, h = geo["line"]
        self.assertEqual(geo["lineShade"], [x - 4, y - 2, w + 8, h + 4])
        x, y, w, h = geo["row"]
        self.assertEqual(geo["rowShade"], [x - 4, y - 2, w + 8, h + 4])
        self.assertEqual(steps[1:], [
            "false false",   # nothing under the pointer
            "true false",    # on the line's name (which takes the hover itself)
            "true false",    # past its words, on the line
            "false true",    # on the chat's row: only its shade
            "false false",   # off both
        ], out.stderr[-2000:])

    def test_every_line_vscode_shades_is_shaded_in_plasma_under_all_of_it(self):
        # First in the line, before what it draws, so it's drawn under it: in
        # a column without spacing (a layout adds its spacing after even an
        # empty item), in a plain item, or in a chat's row's first item (the
        # pet's bar), under that too
        for name, start, first, column in (("RecentLine.qml", "id: recentLine", "RowLayout {", True),
                                           ("PlanLine.qml", "id: planLine", "RowLayout {", True),
                                           ("MemoryLine.qml", "id: memoryLine", "RowLayout {", True),
                                           ("GroupSection.qml", "id: queuedLine", "RowLayout {", True),
                                           ("FocusLine.qml", "id: line", "RowLayout {", False),
                                           ("AgentTree.qml", "id: agentHead", "ColumnLayout {", False),
                                           ("ProjectsView.qml", "id: head", "ColumnLayout {", False),
                                           ("SessionRow.qml", "color: row.petColor", "\n    Rectangle {", False)):
            with self.subTest(name):
                qml = (UI / name).read_text()
                line = qml[qml.index(start):]
                self.assertIn("HoverShade {", line)
                self.assertLess(line.index("HoverShade {"), line.index(first))
                shade = line[line.index("HoverShade {"):]
                shade = shade[:shade.index("}")]
                self.assertRegex(shade, r"shown: \w+\.(hovered|containsMouse)\n")
                if column:
                    self.assertRegex(line[:line.index("HoverShade {")], r"\n\s+spacing: 0\b")
        row = (UI / "SessionRow.qml").read_text()
        bar = row[row.index("// A bar in the color of the chat's pet"):]
        bar = bar[:bar.index("\n    Rectangle {", bar.index("color: row.petColor"))]
        self.assertRegex(bar, r"HoverShade \{\s+z: -1\s+target: row\n")
        css = (UI.parent.parent.parent / "vscode/webview/styles.css").read_text()
        for selector in (".session:hover", ".recent-item:hover", ".agent-head:hover", ".focus-line:hover", ".project-head:hover"):
            with self.subTest(selector):
                rule = css[css.index("\n" + selector + " {"):]   # (its own rule, not high contrast's)
                self.assertIn("background: var(", rule[:rule.index("}")])


if __name__ == "__main__":
    unittest.main()
