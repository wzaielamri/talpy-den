import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// One line of what the search found besides chats (SearchResults.qml): a
// project folder, a plan or a memory. Click it: activated(). At its end its
// folder (or what's in it) and how long ago, in the columns of a recent
// chat's line (RecentLine.qml), so the lines of every kind line up.
RowLayout {
    id: line

    property string icon
    property string text
    property string folder
    property string ago
    property string account   // shown where there's more than one
    property string tipTitle
    property string tip
    signal activated()

    Layout.fillWidth: true
    Layout.leftMargin: Kirigami.Units.gridUnit
    Layout.rightMargin: Kirigami.Units.smallSpacing
    spacing: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        source: line.icon
        Layout.preferredWidth: Kirigami.Units.iconSizes.small
        Layout.preferredHeight: Layout.preferredWidth
        opacity: 0.7
    }
    PlasmaComponents3.Label {
        id: label
        textFormat: Text.PlainText
        text: line.text
        font.underline: mouse.containsMouse
        opacity: line.enabled ? 1 : 0.6
        elide: Text.ElideRight
        Layout.fillWidth: true

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            width: label.contentWidth
            height: parent.height
            mainText: line.tipTitle
            subText: line.tip

            MouseArea {
                id: mouse
                anchors.fill: parent
                enabled: line.enabled
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: line.activated()
            }
        }
    }
    Tag {
        visible: line.account !== ""
        text: line.account
    }
    FoundEnd {
        folder: line.folder
        ago: line.ago
    }
}
