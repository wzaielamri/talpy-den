import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// What Talpy Chat's reply box offers for what you're typing: at the start, / Claude's commands, yours
// and the project's, and skills (where each runs: its tag, greyed with why where it can't); @ the
// project's files (ChatPane.qml's suggestions). ↑ / ↓ move, Tab or Enter takes one, Esc closes it. A
// file of its own, read and made only while there's something to offer, so a window opens as quickly
Rectangle {
    implicitHeight: offerList.implicitHeight + 2
    radius: Kirigami.Units.cornerRadius
    color: pane.mix(pane.textColor, 0.06)
    border.width: 1
    border.color: pane.borderColor

    Column {
        id: offerList
        x: 1
        y: 1
        width: parent.width - 2
        Repeater {
            model: pane.suggestions.length
            delegate: Rectangle {
                required property int index
                readonly property var offer: pane.suggestions[index] || { text: "", about: "" }
                opacity: offer.off ? 0.55 : 1
                width: offerList.width
                height: offerRow.implicitHeight + Kirigami.Units.smallSpacing
                radius: Kirigami.Units.cornerRadius
                color: index === pane.suggestion ? Qt.rgba(pane.youColor.r, pane.youColor.g, pane.youColor.b, 0.22) : "transparent"
                RowLayout {
                    id: offerRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Kirigami.Units.smallSpacing
                    anchors.rightMargin: Kirigami.Units.smallSpacing
                    // (/model and /effort's list: ✓ before what the chat uses now; every row of it
                    // keeps that room, so the names line up)
                    Item {
                        visible: !!offer.run
                        Layout.preferredWidth: Math.round(fm.height * 0.9)
                        Layout.preferredHeight: fm.height
                        Kirigami.Icon {
                            visible: !!offer.now
                            source: Icons.plasma.picked
                            width: Math.round(fm.height * 0.75)
                            height: width
                            anchors.verticalCenter: parent.verticalCenter
                            color: pane.textColor
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        text: offer.text
                        font.family: pane.monoFamily
                        font.pointSize: pane.pt * 0.95
                        color: index === pane.suggestion ? pane.youColor : pane.textColor
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: offerList.width * 0.6
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        text: offer.about
                        color: pane.mutedColor
                        font.pointSize: pane.pt * 0.85
                        elide: Text.ElideRight
                    }
                    // where it runs, when not here: the chat's terminal, Talpy Den's own page
                    PlasmaComponents3.Label {
                        visible: !!offer.tag
                        textFormat: Text.PlainText
                        text: offer.tag || ""
                        color: pane.mutedColor
                        font.pointSize: pane.pt * 0.8
                        leftPadding: Kirigami.Units.smallSpacing
                        rightPadding: Kirigami.Units.smallSpacing
                        background: Rectangle {
                            color: "transparent"
                            border.width: 1
                            border.color: pane.borderColor
                            radius: Kirigami.Units.cornerRadius
                        }
                    }
                }
                MouseArea {
                    id: offerMouse
                    anchors.fill: parent
                    hoverEnabled: !!offer.tip || !!offer.off
                    onClicked: {
                        pane.takeSuggestion(index)
                        replyBox.forceActiveFocus()
                    }
                }
                PlasmaComponents3.ToolTip.text: offer.off ? offer.about : offer.tip || ""
                PlasmaComponents3.ToolTip.visible: offerMouse.containsMouse && PlasmaComponents3.ToolTip.text !== ""
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }
}
