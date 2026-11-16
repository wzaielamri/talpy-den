import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "sides.mjs" as Sides
import "icons.mjs" as Icons

// Side questions' toggle in Talpy Chat's tab row, right before the bookmarks' (BookmarkPill.qml): the
// panel's icon, and how many the chat has (small, muted; none: the icon alone). A click shows the panel
// (SidePanel.qml: beside the chat where the window is wide enough, else over it), on whichever tab;
// again hides it. On: framed thin, no fill. ChatPane.qml makes it after the window's first frame (a
// Loader, asynchronous), not for a new chat; on every tab, no taller than a tab, so the row never
// changes. Light: plain items, its tooltip the tabs' own kind. VS Code chat.tsx: the same words.
MouseArea {
    id: toggle

    readonly property bool open: pane.sideShows

    implicitWidth: line.implicitWidth + Kirigami.Units.largeSpacing * 1.5
    implicitHeight: Kirigami.Units.iconSizes.small + Kirigami.Units.largeSpacing * 1.5
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    Accessible.role: Accessible.Button
    Accessible.name: Sides.SIDE_BUTTON
    onClicked: pane.showSides(!toggle.open, true)

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: Kirigami.Units.smallSpacing
        anchors.bottomMargin: Kirigami.Units.smallSpacing
        radius: Kirigami.Units.cornerRadius
        color: "transparent"
        border.width: 1
        border.color: toggle.open ? pane.mix(pane.textColor, 0.3) : "transparent"
    }
    Row {
        id: line
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            anchors.verticalCenter: parent.verticalCenter
            width: Kirigami.Units.iconSizes.small
            height: width
            source: root.iconDir + Icons.plasma.sideQuestions
            isMask: true
            color: toggle.containsMouse || toggle.open ? pane.textColor : pane.mutedColor
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: pane.sideCount > 0
            textFormat: Text.PlainText
            text: pane.sideCount
            font.pointSize: pane.pt * 0.85
            color: pane.mutedColor
        }
    }

    PlasmaComponents3.ToolTip.text: Sides.SIDE_TIP
    PlasmaComponents3.ToolTip.visible: containsMouse
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
