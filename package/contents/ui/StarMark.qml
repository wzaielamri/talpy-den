import QtQuick
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The star of a starred chat or plan, yellow, as in the VS Code extension: a
// click unstars it; its row's hover buttons star one that isn't. At a recent
// chat's or a plan's end it stands right before the time (RecentLine.qml,
// PlanLine.qml), and every line keeps its room, starred or not (starred:
// false, nothing made in it), so the times line up from line to line; it
// hides while the line's hover buttons show (hidden), their star button in
// its stead, as in VS Code. After a running chat's name (SessionRow.qml) it
// shows only where the chat is starred (visible).
Item {
    id: mark

    property string tooltip
    property bool starred: true
    property bool hidden: false
    signal clicked()

    implicitWidth: Kirigami.Units.iconSizes.small
    implicitHeight: implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.alignment: Qt.AlignVCenter

    Loader {   // (made only on a starred line: most aren't)
        anchors.fill: parent
        active: mark.starred
        visible: !mark.hidden
        sourceComponent: Kirigami.Icon {
            source: Icons.plasma.starred
            color: Icons.color("starred", Kirigami.Theme)
            opacity: markMouse.containsMouse ? 0.7 : 1

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Starred")
                subText: mark.tooltip

                MouseArea {
                    id: markMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: mark.clicked()
                }
            }
        }
    }
}
