import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// A line between days in Talpy Chat's conversation, before the first item of
// each later day the tab shows: ── Yesterday ── ("Today", "Yesterday", "Mon 3
// Nov"; the year when it isn't this one). ChatPane.qml's list makes it as a
// section header, read and made only for a chat with more than one day; its
// "Today" moves on at midnight (pane.today). VS Code chat.tsx .pane-day: the
// same words and rule (shared/pane.ts dayBreaks, dayLabel).
Item {
    property real day: 0

    implicitHeight: line.implicitHeight + Kirigami.Units.gridUnit * 1.1

    RowLayout {
        id: line
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        spacing: Kirigami.Units.largeSpacing

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: pane.borderColor
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: pane.dayLabel(day)
            color: pane.mutedColor
            font.family: pane.chatFamily
            font.pointSize: pane.pt * 0.8
            font.weight: Font.DemiBold
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: pane.borderColor
        }
    }
}
