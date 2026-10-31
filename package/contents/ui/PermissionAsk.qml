import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "markdown.mjs" as Md
import "icons.mjs" as Icons

// What a chat waiting for a permission asks (talpy_den.py:
// note_permissions): the command, or the file and the change; then Allow
// once, Always allow and Deny (with a note), where the widget can answer it
// (answer "hook": through the hook, "keys": in its tmux pane). Claude's
// questions: each with its options (QuestionForm.qml), then Send answers
// and Decline (with a note). A chat leaving plan mode: its plan, then
// Approve and accept edits (the main one), Approve, Keep planning (with what
// to change), in the order of Claude's own dialog.
ColumnLayout {
    id: ask

    property var permission: null
    property bool busy: false        // an answer is on its way
    property int diffLines: 6
    property bool compact: false     // (in a row)
    property bool denying: false
    // decision allow|always|deny, or "answer" with answers {question: [labels or text]}
    signal answered(string decision, string note, var answers)

    readonly property bool canAnswer: !!permission && (permission.answer === "hook" || permission.answer === "keys")
    readonly property var diff: permission && permission.diff ? permission.diff : []
    readonly property var questions: permission && permission.questions ? permission.questions : []
    readonly property bool asksQuestions: questions.length > 0
    readonly property var plan: permission && permission.plan ? permission.plan : null
    property real planHeight: Kirigami.Units.gridUnit * 9   // (in a row: more in the pane)
    // Its text size and code font (the pane's, which you can make larger)
    property real pt: Kirigami.Theme.defaultFont.pointSize
    property string mono: "monospace"
    readonly property real smallPt: Kirigami.Theme.smallFont.pointSize * pt / Kirigami.Theme.defaultFont.pointSize
    signal wholePlan()
    spacing: Kirigami.Units.smallSpacing

    function hex(c) {
        return Qt.rgba(c.r, c.g, c.b, 1).toString()
    }
    function mix(c, a) {
        return Qt.tint(Kirigami.Theme.backgroundColor, Qt.rgba(c.r, c.g, c.b, a))
    }
    readonly property bool dark: Kirigami.Theme.backgroundColor.hslLightness < 0.5
    readonly property var planStyle: ({
        pt: ask.pt, mono: ask.mono, text: hex(Kirigami.Theme.textColor),
        muted: hex(mix(Kirigami.Theme.textColor, 0.62)), accent: dark ? "#d97757" : "#c15f3c", heading: dark ? "#d97757" : "#c15f3c",
        code: dark ? "#b1b9f9" : "#5769f7", codeBg: hex(mix(Kirigami.Theme.textColor, 0.09)), blockBg: hex(mix(Kirigami.Theme.textColor, 0.05)),
        border: hex(mix(Kirigami.Theme.textColor, 0.16)), link: hex(Kirigami.Theme.linkColor)
    })
    // (another prompt, or another chat's: a Deny… begun for the one before is dropped, with its note)
    readonly property string requestKey: permission ? (permission.request || permission.line || "") : ""
    onRequestKeyChanged: cancelDeny()

    function cancelDeny() {
        denying = false
        noteField.text = ""
    }

    // Deny… (Decline… a question): its note field (optional), ready to type in
    function denyWithNote() {
        if (!canAnswer)
            return
        denying = true
        noteField.forceActiveFocus()
    }

    // A question's own-words field, ready to type in
    function typeAnswer() {
        if (canAnswer && asksQuestions)
            questionForm.typeAnswer()
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        font.bold: true
        font.pointSize: ask.pt
        wrapMode: Text.Wrap
        text: !ask.permission ? ""
              : ask.plan ? i18n("Claude has a plan, ready to start:")
              : ask.asksQuestions ? (ask.questions.length > 1 ? i18n("Claude asks you %1 questions:", ask.questions.length)
                                                              : i18n("Claude asks you:"))
              : ask.permission.command ? i18n("Claude asks to run:")
              : ask.permission.file ? i18n("Claude asks to change %1:", ask.permission.file)
              : i18n("Claude asks: %1", ask.permission.line)
    }
    Rectangle {
        visible: !!ask.permission && ask.permission.command !== ""
        Layout.fillWidth: true
        implicitHeight: commandText.implicitHeight + Kirigami.Units.smallSpacing * 2
        radius: Kirigami.Units.cornerRadius
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.07)

        TextEdit {
            id: commandText
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            text: ask.permission ? ask.permission.command : ""
            textFormat: TextEdit.PlainText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.WrapAnywhere
            color: Kirigami.Theme.textColor
            selectionColor: Kirigami.Theme.focusColor
            font.family: ask.mono
            font.pointSize: ask.smallPt
        }
    }
    // The plan, rendered (in a row: its start, the pane shows all of it)
    Rectangle {
        id: planBox
        visible: ask.plan !== null
        Layout.fillWidth: true
        implicitHeight: Math.min(planText.implicitHeight, ask.planHeight) + Kirigami.Units.smallSpacing * 2
        radius: Kirigami.Units.cornerRadius
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
        border.width: 1
        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.12)
        clip: true

        TextEdit {
            id: planText
            x: Kirigami.Units.smallSpacing
            y: Kirigami.Units.smallSpacing
            width: parent.width - Kirigami.Units.smallSpacing * 2
            text: ask.plan ? Md.toHtml(ask.plan.text, ask.planStyle) : ""
            textFormat: TextEdit.RichText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: Kirigami.Theme.textColor
            selectionColor: Kirigami.Theme.focusColor
            onLinkActivated: link => Qt.openUrlExternally(link)
        }
    }
    PlasmaComponents3.Label {
        // (in the pane: a plan cut short, its file opens)
        visible: ask.plan !== null && (planText.implicitHeight > ask.planHeight || (ask.plan.cut && !!ask.plan.file))
        textFormat: Text.StyledText
        Layout.fillWidth: true
        text: "<a href=\"#\">" + i18n("Read the whole plan") + "</a>"
        font.pointSize: ask.smallPt
        onLinkActivated: ask.wholePlan()
    }
    DiffView {
        visible: ask.diff.length > 0
        Layout.fillWidth: true
        lines: ask.diff
        maxRows: ask.diffLines
        pt: ask.smallPt / 0.88
        mono: ask.mono
        path: ask.permission ? ask.permission.file || "" : ""
    }
    QuestionForm {
        id: questionForm
        visible: ask.asksQuestions
        enabled: ask.canAnswer && !ask.busy
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        questions: ask.questions
        requestKey: ask.permission ? (ask.permission.request || ask.permission.line) : ""
        compact: ask.compact
        pt: ask.pt
    }
    RowLayout {
        visible: ask.canAnswer && ask.asksQuestions && !ask.denying
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Button {
            enabled: !ask.busy && questionForm.complete
            icon.name: Icons.plasma.send
            text: i18n("Send answers")
            onClicked: ask.answered("answer", "", questionForm.answers())
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.deny
            icon.color: Icons.color("deny", Kirigami.Theme)
            text: i18n("Decline…")
            onClicked: ask.denyWithNote()
        }
        Item {
            Layout.fillWidth: true
        }
    }
    Flow {
        visible: ask.canAnswer && ask.plan !== null && !ask.denying
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.always
            icon.color: Icons.color("always", Kirigami.Theme)
            text: i18n("Approve, accept edits")
            font.bold: true
            onClicked: ask.answered("approve-edits", "", null)

            TipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Approve and accept edits")
                subText: i18n("It starts on the plan and changes files without asking for the rest of this chat (accept edits mode); commands still ask.")
            }
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.allow
            icon.color: Icons.color("allow", Kirigami.Theme)
            text: i18n("Approve")
            onClicked: ask.answered("approve", "", null)

            TipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Approve")
                subText: i18n("It starts on the plan and asks before each change, as \"Yes, manually approve edits\" in its dialog.")
            }
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.edit
            text: i18n("Keep planning…")
            onClicked: ask.denyWithNote()
        }
    }
    RowLayout {
        visible: ask.canAnswer && !ask.asksQuestions && ask.plan === null && !ask.denying
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.allow
            icon.color: Icons.color("allow", Kirigami.Theme)
            text: i18n("Allow once")
            onClicked: ask.answered("allow", "", null)
        }
        PlasmaComponents3.Button {
            visible: ask.permission && (ask.permission.answer === "keys" || ask.permission.always !== "")
            enabled: !ask.busy
            icon.name: Icons.plasma.always
            icon.color: Icons.color("always", Kirigami.Theme)
            text: i18n("Always allow")
            onClicked: ask.answered("always", "", null)

            TipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Always allow")
                subText: !ask.permission ? ""
                         : ask.permission.answer === "keys" ? i18n("Like \"Yes, and don't ask again\" in its dialog (for an edit, \"Yes, allow all edits during this session\").")
                         : i18n("From now on, without asking: %1. Saved in the project's .claude/settings.local.json, as Claude's own \"don't ask again\" does.",
                                ask.permission.always)
            }
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy
            icon.name: Icons.plasma.deny
            icon.color: Icons.color("deny", Kirigami.Theme)
            text: i18n("Deny…")
            onClicked: ask.denyWithNote()
        }
        Item {
            Layout.fillWidth: true
        }
    }
    RowLayout {
        visible: ask.canAnswer && ask.denying
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.TextField {
            id: noteField
            Layout.fillWidth: true
            font.pointSize: ask.pt
            placeholderText: ask.plan ? i18n("What should change in the plan? (optional)") : i18n("What should Claude do instead? (optional)")
            onAccepted: denyButton.clicked()
        }
        PlasmaComponents3.Button {
            id: denyButton
            enabled: !ask.busy
            icon.name: ask.plan ? Icons.plasma.edit : Icons.plasma.deny
            icon.color: ask.plan ? "transparent" : Icons.color("deny", Kirigami.Theme)
            text: ask.plan ? i18n("Keep planning") : ask.asksQuestions ? i18n("Decline") : i18n("Deny")
            onClicked: {
                ask.answered(ask.plan ? "keep" : "deny", noteField.text.trim(), null)
                ask.cancelDeny()
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.undo
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Cancel")
            onClicked: ask.cancelDeny()
        }
    }
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: !!ask.permission && !ask.canAnswer
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        font.pointSize: ask.smallPt
        opacity: 0.7
        text: ask.plan
              ? i18n("Approve it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings (it takes plans too) to approve it here.")
              : ask.asksQuestions
              ? i18n("Answer it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings (it answers Claude's questions too) to answer it here.")
              : i18n("Answer it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings to answer it here.")
    }
}
