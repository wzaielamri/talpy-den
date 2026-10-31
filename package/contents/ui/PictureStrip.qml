import QtQuick
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The pictures a task or a reply names ([Image: /path], pasted in), small:
// a click shows one, × takes it out (removeRequested). An SSH host's picture
// shows its copy here (root.pictureCopies).
Flow {
    id: strip

    property var pictures: []   // their paths (on host)
    property string host: ""
    property string removeText: i18n("Take it out")
    property real thumbHeight: Kirigami.Units.gridUnit * 3
    signal removeRequested(string path)

    visible: pictures.length > 0
    spacing: Kirigami.Units.smallSpacing

    // The pictures a text names, each once
    function named(text) {
        const out = [], pattern = /\[Image: (\/[^\]\n]+)\]/g
        let m
        while ((m = pattern.exec(text || "")) !== null) {
            if (out.indexOf(m[1]) < 0)
                out.push(m[1])
        }
        return out
    }

    // text without the picture at path
    function without(text, path) {
        const token = "[Image: " + path + "]"
        return text.split(token + " ").join("").split(token).join("")
    }

    Repeater {
        model: strip.pictures
        delegate: Item {
            id: picture
            required property string modelData
            height: strip.thumbHeight
            width: thumb.implicitHeight > 0 ? Math.min(height * 8 / 3, height * thumb.implicitWidth / thumb.implicitHeight)
                                            : height

            Image {
                id: thumb
                anchors.fill: parent
                source: "file://" + encodeURI(root.pictureCopies[picture.modelData] || picture.modelData)   // (a host's: its copy here)
                sourceSize.height: parent.height * Screen.devicePixelRatio
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                asynchronous: true
            }
            PlasmaComponents3.Label {
                anchors.centerIn: parent
                visible: thumb.status === Image.Error
                textFormat: Text.PlainText
                text: i18n("Not there")
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: Qt.openUrlExternally(thumb.source)
            }
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("A picture for Claude")
                subText: strip.host ? i18n("%1, on %2", picture.modelData, strip.host) : picture.modelData
            }
            Rectangle {   // (the × shows on any picture)
                anchors.fill: remove
                radius: width / 2
                color: Kirigami.Theme.backgroundColor
                opacity: 0.85
            }
            PlasmaComponents3.ToolButton {
                id: remove
                anchors.top: parent.top
                anchors.right: parent.right
                icon.name: Icons.plasma.cancel
                icon.color: Icons.color("cancel", Kirigami.Theme)
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: strip.removeText
                implicitWidth: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
                implicitHeight: implicitWidth
                onClicked: strip.removeRequested(picture.modelData)
            }
        }
    }
}
