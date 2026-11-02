"""A right-click on the dashboard on the desktop opens the widget's menu
(MenuCatcher.qml): the dashboard is a Page (PlasmaExtras.Representation) and
its lists ScrollViews, which take every mouse button, so Plasma's desktop
never got the right press. The catcher lies over it all and takes the right
button only: a left click, the wheel and a right click in a text field go to
what's under it, as before."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_pets import NEEDS_PLASMA_QML

UI = Path(__file__).resolve().parent.parent / "package/contents/ui"

PAGE = """import QtQuick
import QtQuick.Controls as QQC2
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.components as PlasmaComponents3
import "%s"
Item {
    id: root
    width: 400; height: 300
    property string log: ""
    function note(s) { log = log + s + " " }
    // the desktop under the widget: it would open the widget's menu on a right press
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        onPressed: root.note("desktop")
    }
    PlasmaExtras.Representation {
        id: full
        anchors.fill: parent
        header: PlasmaExtras.PlasmoidHeading {
            PlasmaComponents3.TextField { id: field; width: 200; placeholderText: "search" }
        }
        PlasmaComponents3.ScrollView {
            anchors.fill: parent
            ListView {
                model: 20
                delegate: MouseArea {
                    width: 380; height: 20
                    onClicked: root.note("row" + index)
                    onWheel: wheel => { root.note("wheel"); wheel.accepted = false }
                    PlasmaComponents3.Label { text: "row " + index }
                }
            }
        }
        Loader {
            parent: full
            anchors.fill: parent
            z: 1000
            sourceComponent: MenuCatcher {
                covers: full
                onMenu: at => root.note("menu")
            }
        }
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
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(200)
row, field, empty = QPoint(100, 80), QPoint(60, 20), QPoint(300, 20)
steps = [
    lambda: QTest.mouseClick(view, Qt.RightButton, Qt.NoModifier, row),     # on a list's line
    lambda: QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, row),      # a left click
    lambda: QTest.mouseClick(view, Qt.RightButton, Qt.NoModifier, empty),   # on the heading, beside the field
    lambda: QTest.mouseClick(view, Qt.RightButton, Qt.NoModifier, field),   # in the text field
]
for step in steps:
    r.setProperty("log", ""); step(); QTest.qWait(200); print(repr(r.property("log").strip()))
"""


@NEEDS_PLASMA_QML
class MenuCatcherTests(unittest.TestCase):
    def test_a_right_click_anywhere_but_in_a_text_field_opens_the_menu(self):
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "page.qml"
            qml.write_text(PAGE % UI.as_uri())
            out = subprocess.run(["python3", "-c", SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        steps = [eval(line) for line in out.stdout.split("\n") if line]
        self.assertRegex(steps[1] if len(steps) > 1 else "", r"^row\d+$")   # a left click goes to the line, as before
        steps[1:2] = ["row"]
        self.assertEqual(steps, [
            "menu",   # a right click on a list's line: the menu
            "row",
            "menu",   # on the heading too
            "",       # in the text field: its own menu (not the widget's, nor the desktop's)
        ], out.stderr[-2000:])

    def test_the_dashboard_has_it_on_the_desktop_only(self):
        full = (UI / "FullRepresentation.qml").read_text()
        catcher = full[full.index("sourceComponent: MenuCatcher {") - 200:]
        self.assertIn("parent: full", catcher)          # (over the heading too, not only the page's content)
        self.assertIn("active: root.onDesktop", catcher)  # (in the panel's popup Plasma has none either)
        self.assertIn("z: 1000", catcher)
        main = (UI / "main.qml").read_text()
        menu = main[main.index("function openWidgetMenu("):main.index("function openHostsMenu(")]
        self.assertIn("Plasmoid.contextualActions", menu)
        self.assertIn('Plasmoid.internalAction("configure")', menu)
        self.assertIn("action.visible", menu)


# The hosts picker's Reload (main.qml's own functions, in a real Plasma menu):
# a Qt menu closes on any click, so Reload opens it again where it was, says
# Reloading… until every list it asked for answered, then Reload again. And
# its section headers stay headers, where they belong, when it changes while
# it's open (Plasma makes them only as it opens: refilled while open, they
# were plain lines and the old ones stayed at the top)
PICKER = """import QtQuick
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.components as PlasmaComponents3
Item {
    id: root
    width: 400; height: 300
    property bool dashboardShown: true
    property string hostsMenuShown: ""
    property var hostItems: []
    property string log: ""
    function i18n(s) { return s }
    function loadHosts() {}
    function toggleHost(host) { log = log + "toggle:" + host + " " }
    function reloadHosts() { log = log + "reload "; return { "cmd-a": true, "cmd-b": true } }
    property bool more: false   // (a container more: the menu's lines change)
    function hostsMenuModel() {
        const items = [{ section: true, text: "SSH hosts" }, { text: "lab", checkable: true, host: "lab" },
                       { section: true, text: "Containers" }, { text: "box", checkable: true, host: "podman:box" }]
        if (more)
            items.push({ text: "web", checkable: true, host: "podman:web" })
        items.push({ separator: true })
%(item)s
        return items
    }
    PlasmaComponents3.ToolButton { id: hostsButton; text: "hosts"; onClicked: root.openHostsMenu(hostsButton) }
%(code)s
}
"""

PICKER_SCRIPT = """import sys
from PySide6.QtCore import QUrl, QPoint, Qt, QMetaObject, Q_ARG
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
view = QQuickView(); view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    sys.exit(str([e.toString() for e in view.errors()]))
r = view.rootObject()
view.show(); QTest.qWaitForWindowExposed(view); QTest.qWait(200)
def menu():
    return next((w for w in app.topLevelWidgets() if isinstance(w, QMenu)), None)
def shown():
    m = menu()
    if not m or not m.isVisible():
        return "closed"
    return " | ".join(("# " if a.isSeparator() else "") + a.text().replace("&", "") + ("" if a.isEnabled() else " (off)")
                      for a in m.actions() if a.text() or not a.isSeparator())   # (a header: "# " and its name)
def click(text):
    m = menu()
    a = next(a for a in m.actions() if a.text().replace("&", "") == text)
    QTest.mouseClick(m, Qt.LeftButton, Qt.NoModifier, m.actionGeometry(a).center()); QTest.qWait(300)
def answer(cmd):
    QMetaObject.invokeMethod(r, "hostsReloadAnswered", Q_ARG("QVariant", cmd))
    QMetaObject.invokeMethod(r, "refreshHostsMenu"); QTest.qWait(200)
QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(20, 10)); QTest.qWait(300)
print(repr(shown()))
click("Reload"); print(repr(shown()))
answer("cmd-a"); print(repr(shown()))
answer("cmd-b"); print(repr(shown()))
r.setProperty("more", True); QMetaObject.invokeMethod(r, "refreshHostsMenu"); QTest.qWait(300); print(repr(shown()))
click("lab"); print(repr(shown()))
r.setProperty("dashboardShown", False)   # (closed before the menu could open again)
QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(20, 10)); QTest.qWait(300)
click("Reload"); print(repr(shown()))
print(repr(r.property("log").strip()))
"""


def main_qml_block(main, start):
    """The block of main.qml starting at start (4 spaces in) up to its closing brace (a property: its lines)."""
    i = main.index("\n    " + start) + 1
    if start.startswith(("property ", "readonly property ")):
        end = main.index("\n", i)
        while sum(main.count(o, i, end) - main.count(c, i, end) for o, c in ("()", "{}", "[]")) > 0:
            end = main.index("\n", end + 1)
        return main[i:end + 1]
    return main[i:main.index("\n    }\n", i) + 7]


@NEEDS_PLASMA_QML
class PickerReloadTests(unittest.TestCase):
    def test_reload_keeps_the_picker_open_with_its_headers_and_says_so_until_the_lists_answered(self):
        main = (UI / "main.qml").read_text()
        code = "".join(main_qml_block(main, start) for start in (
            "property var hostsReloadWaits", "property bool hostsReloading", "function openHostsMenu(",
            "function refreshHostsMenu(", "readonly property var hostItemDefaults", "property string hostsMenuShape",
            "function hostsMenuShapeOf(", "function fillHostsMenu(", "function reloadHostsMenu(",
            "function reopenHostsMenu(", "function hostsReloadAnswered(", "function hostsReloadDone(",
            "Timer {\n        id: hostsReloadTimer", "PlasmaExtras.Menu {\n        id: hostsMenu",
            "Component {\n        id: hostItem"))
        model = main[main.index("function hostsMenuModel("):]
        item = model[model.index("        items.push(hostsReloading"):model.index("        return items")]
        item = item.replace("Icons.plasma.refresh", '"view-refresh"')
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "page.qml"
            qml.write_text(PICKER % {"item": item, "code": code})
            out = subprocess.run(["python3", "-c", PICKER_SCRIPT, str(qml)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        self.assertEqual([eval(line) for line in out.stdout.split("\n") if line], [
            "# SSH hosts | lab | # Containers | box | Reload",
            "# SSH hosts | lab | # Containers | box | Reloading… (off)",   # (open again, at once)
            "# SSH hosts | lab | # Containers | box | Reloading… (off)",   # one list answered, one to go
            "# SSH hosts | lab | # Containers | box | Reload",             # (changed where it is)
            "# SSH hosts | lab | # Containers | box | web | Reload",       # a line more: made anew, still open
            "closed",                    # picking a host closes it, as before
            "closed",                    # the dashboard closed meanwhile: not opened on its own
            "reload toggle:lab reload",
        ], out.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
