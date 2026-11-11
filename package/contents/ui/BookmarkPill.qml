import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The chat's bookmarks at the end of Talpy Chat's tab row: the ribbon and how many; a click lists them
// beside the conversation (BookmarkList.qml), again hides them; from Review, it goes to Chat first.
// ChatPane.qml makes it only for a chat with a bookmark, or while they're listed; as tall as a tab
// (a tab's own rule), on every tab, so the row never changes. Framed thin while they're listed. Light
// (a plain text, its tooltip the tabs' own kind): it's made as a chat's window shows its first read
MouseArea {
    id: pill

    readonly property bool open: pane.bookmarksOn && pane.conversationTab

    implicitWidth: line.implicitWidth + Kirigami.Units.largeSpacing * 1.5
    implicitHeight: count.implicitHeight + Kirigami.Units.largeSpacing * 1.5
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    Accessible.role: Accessible.Button
    Accessible.name: i18n("Bookmarks")
    onClicked: {
        if (!pane.conversationTab) {
            pane.tab = "chat"
            pane.bookmarksOn = true
        } else
            pane.bookmarksOn = !pane.bookmarksOn
    }

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: Kirigami.Units.smallSpacing
        anchors.bottomMargin: Kirigami.Units.smallSpacing
        radius: Kirigami.Units.cornerRadius
        color: "transparent"
        border.width: 1
        border.color: pill.open ? pane.mix(pane.textColor, 0.3) : "transparent"
    }
    Row {
        id: line
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            anchors.verticalCenter: parent.verticalCenter
            width: Kirigami.Units.iconSizes.small
            height: width
            source: Icons.plasma.bookmarked
            isMask: true
            color: pill.containsMouse || pill.open ? pane.textColor : pane.mutedColor
        }
        Text {
            id: count
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: pane.bookmarks.length
            font.pointSize: pane.pt
            color: pill.containsMouse || pill.open ? pane.textColor : pane.mutedColor
        }
    }

    PlasmaComponents3.ToolTip.text: i18n("Bookmarks in this chat (Ctrl+Shift+B)") + "\n" + i18n("Alt+↑ / Alt+↓: the one before / after what you read")
    PlasmaComponents3.ToolTip.visible: containsMouse
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
