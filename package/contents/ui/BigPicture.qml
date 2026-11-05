import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A picture of yours in Talpy Chat, big (its thumbnail clicked): a click anywhere (or × or Esc)
// closes it, Open shows it in your picture viewer. ChatPane.qml's Loader: read and made only while
// one shows
Rectangle {
    color: Qt.rgba(0, 0, 0, 0.85)

    MouseArea {
        anchors.fill: parent
        onClicked: pane.bigPicture = ""
    }
    Image {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.gridUnit * 2
        source: pane.bigPicture ? "file://" + encodeURI(pane.bigPicture) : ""
        sourceSize.width: width * Screen.devicePixelRatio
        sourceSize.height: height * Screen.devicePixelRatio
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        smooth: true
    }
    RowLayout {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.openRun
            text: i18n("Open")
            onClicked: Qt.openUrlExternally("file://" + encodeURI(pane.bigPicture))
            PlasmaComponents3.ToolTip.text: i18n("In your picture viewer")
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.close
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Close (Esc)")
            onClicked: pane.bigPicture = ""
            PlasmaComponents3.ToolTip.text: text
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }
}
