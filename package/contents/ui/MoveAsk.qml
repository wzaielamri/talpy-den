import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Under a plan's line once its Move to project… (or Move back) button is
// clicked, or at the top of the project card a plan was dropped on
// (main.qml: askMove): where the plan goes (jump.py --move-plan
// --describe), the project to pick (Move to project…), "Keep this project's
// new plans there too" when the project names no plans folder (checked: its
// settings.local.json names .claude/plans, so Claude's chats there find the
// plan by its name), whether git would show it there, and Keep both or
// Replace when a plan of that name is there. Nothing moves until Move:
// Cancel, Esc or a click anywhere else lets it be (FullRepresentation's
// catcher), and Cancel has the keyboard, so Enter never moves it. Made only
// for the line or card it's asked for.
Loader {
    id: ask

    property string itemKey: ""   // the line's key, or "drop|" + the card's folder (root.moveAsk.key)
    readonly property var asked: root.moveAsk

    active: itemKey !== "" && asked.key === itemKey
    visible: active

    sourceComponent: ColumnLayout {
        id: box

        readonly property var a: ask.asked.answer || ({})
        readonly property bool ready: !ask.asked.busy && ask.asked.message === "" && ask.asked.answer !== null
        readonly property bool back: ask.asked.back
        readonly property bool picked: back || !!a.project
        readonly property var choices: a.choices || []
        readonly property bool comboOpen: picker.popup.visible   // (the catcher lets its list be)
        readonly property color dim: Kirigami.Theme.disabledTextColor

        spacing: Kirigami.Units.smallSpacing / 2
        focus: true
        Keys.onEscapePressed: root.cancelMove()
        Component.onCompleted: {
            root.moveAskItem = box
            box.forceActiveFocus()
        }
        Component.onDestruction: if (root.moveAskItem === box) root.moveAskItem = null
        onReadyChanged: if (ready) cancelButton.forceActiveFocus()

        PlasmaComponents3.Label {
            visible: ask.asked.busy
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: i18n("Looking at where it would go…")
            opacity: 0.6
            font: Kirigami.Theme.smallFont
        }
        // why it can't move
        RowLayout {
            visible: !ask.asked.busy && ask.asked.message !== ""
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
                onClicked: root.cancelMove()
            }
        }
        // the question, with the project to pick
        RowLayout {
            visible: box.ready
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                Layout.fillWidth: !picker.visible
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: Kirigami.Theme.neutralTextColor
                text: box.back ? i18n("Move “%1” back to %2?", box.a.title || "", box.a.account || "")
                      : ask.asked.pick ? i18nc("then the project, picked from a list", "Move “%1” to", box.a.title || "")
                      : i18n("Move “%1” to %2?", box.a.title || "", box.a.projectShort || "")
            }
            PlasmaComponents3.ComboBox {
                id: picker
                visible: ask.asked.pick && !box.back
                Layout.fillWidth: true
                model: box.choices.map(c => c.short)
                currentIndex: box.choices.findIndex(c => c.path === box.a.project)
                displayText: currentIndex < 0 ? i18n("Pick a project…") : currentText
                onActivated: index => {
                    const c = box.choices[index]
                    if (c && c.path !== box.a.project)
                        root.askMove(ask.asked.key, { slug: ask.asked.slug, profileDir: ask.asked.profileDir },
                                     ask.asked.host, c.path, false, true)
                }
            }
        }
        PlasmaComponents3.Label {
            visible: box.ready && box.picked && !!box.a.targetShort
            Layout.fillWidth: true
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("It goes to %1.", box.a.targetShort || "")
            color: box.dim
            font: Kirigami.Theme.smallFont
        }
        // the project names no plans folder: its settings.local.json can (else Claude's chats there won't find it)
        PlasmaComponents3.CheckBox {
            id: keepThere
            visible: box.ready && box.picked && !box.back && box.a.setting === ""
            text: i18n("Keep this project's new plans there too")
            checked: ask.asked.keepThere
            onToggled: root.moveAsk = Object.assign({}, root.moveAsk, { keepThere: checked })
        }
        PlasmaComponents3.Label {
            visible: keepThere.visible
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.gridUnit
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: ask.asked.keepThere ? i18n("Adds plansDirectory to %1.", box.a.settingsFile || "")
                                      : i18n("Without it, Claude's chats there won't find the plan by its name.")
            color: ask.asked.keepThere ? box.dim : Kirigami.Theme.neutralTextColor
            font: Kirigami.Theme.smallFont
        }
        PlasmaComponents3.Label {
            visible: box.ready && box.picked && box.a.git === true
            Layout.fillWidth: true
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("It would show up in git there.")
            color: Kirigami.Theme.neutralTextColor
            font: Kirigami.Theme.smallFont
        }
        PlasmaComponents3.Label {
            visible: box.ready && box.back && !!box.a.lost
            Layout.fillWidth: true
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("Claude's chats in %1 look for plans in its own folder: they won't find it there.", box.a.projectShort || "")
            color: Kirigami.Theme.neutralTextColor
            font: Kirigami.Theme.smallFont
        }
        PlasmaComponents3.Label {
            visible: box.ready && !!box.a.exists
            Layout.fillWidth: true
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("There's another plan called %1 there: keep both (this one becomes %2), or replace it (it goes to the Trash)?",
                       box.a.slug || "", box.a.free || "")
            color: Kirigami.Theme.neutralTextColor
        }
        RowLayout {
            visible: box.ready
            Layout.alignment: Qt.AlignRight
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Button {
                visible: !box.a.exists
                enabled: box.picked
                text: i18nc("move the plan", "Move")
                icon.name: box.back ? Icons.plasma.moveBack : Icons.plasma.moveToProject
                onClicked: root.confirmMove("")
            }
            PlasmaComponents3.Button {
                visible: !!box.a.exists
                text: i18n("Keep both")
                icon.name: box.back ? Icons.plasma.moveBack : Icons.plasma.moveToProject
                onClicked: root.confirmMove("keep")
            }
            PlasmaComponents3.Button {
                visible: !!box.a.exists
                text: i18n("Replace")
                onClicked: root.confirmMove("replace")
            }
            PlasmaComponents3.Button {
                id: cancelButton
                text: i18n("Cancel")
                onClicked: root.cancelMove()
            }
        }
    }
}
