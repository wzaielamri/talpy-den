import QtQuick
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The star after a starred chat's or plan's name, yellow, as in the VS Code
// extension (a click unstars it; its row's hover buttons star one that isn't)
Kirigami.Icon {
    id: mark

    property string tooltip
    signal clicked()

    source: Icons.plasma.starred
    color: Icons.color("starred", Kirigami.Theme)
    implicitWidth: Kirigami.Units.iconSizes.small
    implicitHeight: implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.alignment: Qt.AlignVCenter
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
