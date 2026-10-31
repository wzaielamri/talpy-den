import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// Under a chat's, a plan's or a memory's line once its Delete… button is
// clicked (main.qml: askDelete): what goes to the Trash and on which accounts
// (jump.py --describe), with Delete and Cancel; or why it can't be deleted
// (open in a session, gone, the account's CLAUDE.md). Made only for the line
// it's asked for: one under every line made a list slow to open.
Loader {
    id: ask

    property string itemKey: ""   // the line's key (root.deleteAsk.key)
    readonly property var asked: root.deleteAsk

    active: itemKey !== "" && asked.key === itemKey
    visible: active

    sourceComponent: ColumnLayout {
        spacing: 0

        PlasmaComponents3.Label {
            visible: ask.asked.busy
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: i18n("Looking at what it would delete…")
            opacity: 0.6
            font: Kirigami.Theme.smallFont
        }
        ConfirmLine {
            visible: !ask.asked.busy && ask.asked.question !== ""
            Layout.fillWidth: true
            text: ask.asked.question
            confirmText: i18n("Delete")
            confirmIcon: "delete"
            onConfirmed: root.confirmDelete()
            onCancelled: root.deleteAsk = root.noDeleteAsk
        }
        RowLayout {
            visible: !ask.asked.busy && ask.asked.question === "" && ask.asked.message !== ""
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: ask.asked.message
                wrapMode: Text.Wrap
                color: Kirigami.Theme.negativeTextColor
            }
            PlasmaComponents3.Button {
                text: i18n("OK")
                onClicked: root.deleteAsk = root.noDeleteAsk
            }
        }
    }
}
