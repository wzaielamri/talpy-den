import QtQuick
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The pictures a task or a reply names ([Image: /path], pasted in), small:
// a click shows one (opensHere: openRequested, the chat pane shows it big;
// else your picture viewer), × takes it out (removeRequested; removable
// false: none, a message's that went). An SSH host's picture shows its copy
// here (root.pictureCopies), else (here) the file of its path here when
// that's a regular file (pane.py pictures_here).
Flow {
    id: strip

    property var pictures: []   // their paths (on host)
    property string host: ""
    property var here: null     // a host's chat: those that are a regular file here too (null: all, this computer's)
    property string removeText: i18n("Take it out")
    property real thumbHeight: Kirigami.Units.gridUnit * 3
    property bool removable: true
    property bool opensHere: false
    signal removeRequested(string path)
    signal openRequested(string path)   // (its file here: a host's copy)

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
            // (its file here: a host's copy, else its path when it's listed here)
            readonly property string file: root.pictureCopies[modelData]
                                           || (strip.here === null || strip.here.indexOf(modelData) >= 0 ? modelData : "")
            height: strip.thumbHeight
            width: thumb.implicitHeight > 0 ? Math.min(height * 8 / 3, height * thumb.implicitWidth / thumb.implicitHeight)
                                            : height

            Image {
                id: thumb
                anchors.fill: parent
                source: picture.file ? "file://" + encodeURI(picture.file) : ""
                sourceSize.height: parent.height * Screen.devicePixelRatio
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                asynchronous: true
            }
            PlasmaComponents3.Label {
                anchors.centerIn: parent
                visible: thumb.status === Image.Error || !picture.file
                textFormat: Text.PlainText
                text: i18n("Not there")
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (thumb.status === Image.Error || !picture.file)
                        return
                    if (strip.opensHere)
                        strip.openRequested(picture.file)
                    else
                        Qt.openUrlExternally(thumb.source)
                }
            }
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: strip.opensHere ? i18n("Click to see it big") : i18n("A picture for Claude")
                subText: strip.host ? i18n("%1, on %2", picture.modelData, root.hostLabel(strip.host)) : picture.modelData
            }
            Rectangle {   // (the × shows on any picture)
                visible: strip.removable
                anchors.fill: remove
                radius: width / 2
                color: Kirigami.Theme.backgroundColor
                opacity: 0.85
            }
            PlasmaComponents3.ToolButton {
                id: remove
                visible: strip.removable
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
