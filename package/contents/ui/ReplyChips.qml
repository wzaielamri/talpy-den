import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Suggested replies above Talpy Chat's reply box (ChatPane.qml, a Loader: read and made
// only while there are chips, so every window opens as quickly; VS Code chat.tsx the same,
// with shared/pane.ts's rules and words): small framed chips once Claude's turn is over,
// the answers to its question first, in your accent (the option it recommends in bold),
// then your usual replies, plain. A click sends one as if you typed it; Shift+click puts it
// in the box first; Alt+1…4 in the box; right-click: Edit before sending, and Don't suggest
// this for one of your usual replies.
Flow {
    id: row
    objectName: "replyChips"   // (tools/bench: the frame they're drawn in)
    spacing: Kirigami.Units.smallSpacing
    Accessible.role: Accessible.ToolBar
    Accessible.name: i18n("Suggested replies")

    Repeater {
        model: pane.chipsShown
        delegate: Rectangle {
            id: chip
            required property var modelData
            readonly property color tone: modelData.usual ? pane.textColor : pane.youColor
            height: pane.queueButtonHeight
            width: Math.min(row.width, label.implicitWidth + Kirigami.Units.smallSpacing * 3)
            radius: Kirigami.Units.cornerRadius
            // (framed thin, as a held message's buttons; tinted while pressed or under the pointer)
            color: mouse.pressed ? Qt.rgba(tone.r, tone.g, tone.b, 0.16) : mouse.containsMouse ? Qt.rgba(tone.r, tone.g, tone.b, 0.08) : "transparent"
            border.width: 1
            border.color: mouse.containsMouse ? Kirigami.Theme.focusColor : Qt.rgba(tone.r, tone.g, tone.b, modelData.usual ? 0.3 : 0.55)
            Accessible.role: Accessible.Button
            Accessible.name: (modelData.usual ? i18n("Your usual reply") : i18n("Answer")) + ": " + modelData.send
            Accessible.description: modelData.title
            Accessible.onPressAction: pane.takeChip(modelData, false)

            PlasmaComponents3.Label {
                id: label
                anchors.fill: parent
                anchors.leftMargin: Kirigami.Units.smallSpacing * 1.5
                anchors.rightMargin: Kirigami.Units.smallSpacing * 1.5
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                text: chip.modelData.label
                color: chip.tone
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.bold: chip.modelData.recommended
                elide: Text.ElideRight
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: event => {
                    if (event.button === Qt.RightButton) {
                        menu.chip = chip.modelData
                        menu.popup()
                    } else {
                        pane.takeChip(chip.modelData, (event.modifiers & Qt.ShiftModifier) !== 0)
                    }
                }
            }
            PlasmaComponents3.ToolTip.text: modelData.title
            PlasmaComponents3.ToolTip.visible: mouse.containsMouse && !menu.visible
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    PlasmaComponents3.Menu {
        id: menu
        property var chip: null
        PlasmaComponents3.MenuItem {
            icon.name: Icons.plasma.edit
            text: i18n("Edit before sending")
            onTriggered: pane.takeChip(menu.chip, true)
        }
        PlasmaComponents3.MenuItem {
            visible: !!menu.chip && menu.chip.usual
            height: visible ? implicitHeight : 0
            icon.name: Icons.plasma.hide
            text: i18n("Don't suggest this")
            onTriggered: pane.hideChip(menu.chip)
        }
    }
}
