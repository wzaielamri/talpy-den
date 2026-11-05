import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "keys.mjs" as PaneKeys
import "icons.mjs" as Icons

// Talpy Chat's keys, over its window (? in an empty box; ChatPane.qml's Loader: read and made only
// while it shows): keys.mjs's table, Plasma's keys. Esc, × or a click outside closes it. VS Code
// chat.tsx KeysHelp: the same list, VS Code's keys. (The words are keys.mjs's: there are no
// translations of Talpy Den yet)
Rectangle {
    id: help
    color: Qt.rgba(0, 0, 0, 0.35)

    MouseArea {
        anchors.fill: parent
        onClicked: pane.helpOn = false
    }
    Rectangle {
        id: card
        anchors.horizontalCenter: parent.horizontalCenter
        y: Kirigami.Units.gridUnit * 2
        width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 34)
        height: Math.min(parent.height - y - Kirigami.Units.gridUnit, body.implicitHeight + Kirigami.Units.largeSpacing * 2)
        radius: Kirigami.Units.cornerRadius
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: pane.borderColor

        MouseArea {   // (a click on it isn't one outside)
            anchors.fill: parent
        }
        PlasmaComponents3.ScrollView {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            contentWidth: availableWidth
            PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

            ColumnLayout {
                id: body
                width: parent.width
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: i18n("Keys")
                        font.bold: true
                        font.pointSize: pane.pt
                    }
                    PlasmaComponents3.ToolButton {
                        icon.name: Icons.plasma.close
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Close (Esc)")
                        onClicked: pane.helpOn = false
                        PlasmaComponents3.ToolTip.text: text
                        PlasmaComponents3.ToolTip.visible: hovered
                        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                }
                Repeater {
                    model: PaneKeys.KEY_GROUPS
                    delegate: ColumnLayout {
                        id: group
                        required property string modelData
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            Layout.topMargin: Kirigami.Units.smallSpacing
                            textFormat: Text.PlainText
                            text: group.modelData
                            font.bold: true
                            font.pointSize: pane.pt * 0.95
                            color: pane.mutedColor
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Kirigami.Units.largeSpacing
                            rowSpacing: Kirigami.Units.smallSpacing * 0.5

                            Repeater {
                                model: PaneKeys.KEYS.filter(k => k.group === group.modelData && k.plasma !== "")
                                delegate: PlasmaComponents3.Label {
                                    required property var modelData
                                    required property int index
                                    // (two cells a key: its key, then what it does)
                                    Layout.preferredWidth: keysWidth.advanceWidth + Kirigami.Units.smallSpacing
                                    textFormat: Text.PlainText
                                    text: modelData.plasma
                                    font.family: pane.monoFamily
                                    font.pointSize: pane.pt * 0.9
                                    Layout.alignment: Qt.AlignTop
                                    Layout.row: index
                                    Layout.column: 0
                                }
                            }
                            Repeater {
                                model: PaneKeys.KEYS.filter(k => k.group === group.modelData && k.plasma !== "")
                                delegate: PlasmaComponents3.Label {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.row: index
                                    Layout.column: 1
                                    textFormat: Text.PlainText
                                    text: modelData.what
                                    wrapMode: Text.Wrap
                                    font.pointSize: pane.pt * 0.9
                                }
                            }
                        }
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    text: i18n("Talpy Den's own keyboard shortcut can also open the chat that needs you in Talpy Chat: Settings → Notifications.")
                    color: pane.mutedColor
                    font.pointSize: pane.pt * 0.85
                }
            }
        }
    }
    // (every key column as wide as the widest key, so the words line up from group to group)
    TextMetrics {
        id: keysWidth
        font.family: pane.monoFamily
        font.pointSize: pane.pt * 0.9
        text: PaneKeys.KEYS.map(k => k.plasma).reduce((a, b) => (b.length > a.length ? b : a), "")
    }
}
