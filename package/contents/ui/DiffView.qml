import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "codehtml.mjs" as Code
import "icons.mjs" as Icons

// A diff (its unified lines, as pane.py and the asks give them) as
// codehtml.mjs draws it: numbered, + and −, tinted lines with the changed
// words marked, in the file's syntax colors; side by side (before | after)
// with the setting on and room for it (the button in the corner switches,
// for every diff). Or a file's lines as they are now (`now`, no earlier
// version to compare with). One rich text, made once it shows, and kept
// while hidden (a hidden tab's rows keep their heights, so its list stays where
// it was).
Rectangle {
    id: diffView

    property var lines: []
    property var now: []                  // (instead of lines: how the file is)
    property string path: ""              // the file (its syntax colors)
    property int maxRows: 0               // rows shown, 0: all
    property bool canSplit: true          // the switch in the corner (on hover)
    property real pt: Kirigami.Theme.smallFont.pointSize / 0.88
    property string mono: "monospace"
    property color base: Qt.tint(Kirigami.Theme.backgroundColor, Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                                                         Kirigami.Theme.textColor.b, 0.04))
    readonly property bool dark: Kirigami.Theme.backgroundColor.hslLightness < 0.5
    // (about 48 characters a side, else one after the other)
    // (only lines added, or only removed: nothing to set side by side)
    readonly property bool sideBySide: canSplit && Plasmoid.configuration.diffSideBySide && now.length === 0
                                       && width > pt * 1.333 * 0.88 * 0.6 * 2 * 48
                                       && lines.some(l => l.charAt(0) === "-") && lines.some(l => l.charAt(0) === "+")
    function hex(c) {
        return Qt.rgba(c.r, c.g, c.b, 1).toString()
    }
    FontMetrics {
        id: codeFm   // (a character of the code: where a wrapped line goes on, under the code)
        font.family: diffView.mono
        font.pointSize: diffView.pt * 0.88
    }
    readonly property var codeStyle: Code.palette(dark, hex(Kirigami.Theme.textColor), hex(base), mono, pt,
                                                  codeFm.font.pointSize && codeFm.advanceWidth("M"))
    property bool shown: false
    onVisibleChanged: if (visible) shown = true
    Component.onCompleted: if (visible) shown = true

    implicitHeight: code.implicitHeight + Kirigami.Units.smallSpacing * 2
    radius: Kirigami.Units.cornerRadius
    color: base
    clip: true

    TextEdit {
        id: code
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        textFormat: TextEdit.RichText
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: Kirigami.Theme.textColor
        selectionColor: Kirigami.Theme.focusColor
        selectedTextColor: Kirigami.Theme.highlightedTextColor
        text: !diffView.shown ? ""
            : diffView.now.length ? Code.listingHtml(diffView.now, diffView.path, diffView.codeStyle, diffView.maxRows)
            : diffView.sideBySide ? Code.splitHtml(diffView.lines, diffView.path, diffView.codeStyle, diffView.maxRows)
            : Code.diffHtml(diffView.lines, diffView.path, diffView.codeStyle, diffView.maxRows)
    }

    HoverHandler {
        id: hover
    }
    // (made when the mouse is over it: a diff costs little more than its text)
    Loader {
        active: diffView.canSplit && diffView.now.length === 0 && hover.hovered
        anchors.top: parent.top
        anchors.right: parent.right
        sourceComponent: PlasmaComponents3.ToolButton {
        icon.name: Plasmoid.configuration.diffSideBySide ? Icons.plasma.aboveBelow : Icons.plasma.sideBySide
        display: PlasmaComponents3.AbstractButton.IconOnly
        text: Plasmoid.configuration.diffSideBySide ? i18n("One after the other") : i18n("Side by side")
        onClicked: Plasmoid.configuration.diffSideBySide = !Plasmoid.configuration.diffSideBySide

        TipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: parent.text
            subText: Plasmoid.configuration.diffSideBySide ? i18n("Changes as removed and added lines, one after the other.")
                                                           : i18n("Changes as before | after, where there's room.")
        }
        }
    }
}
