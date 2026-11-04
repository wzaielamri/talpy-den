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
    // A background chat's, which a terminal can show (Talpy Chat): where it can't be answered
    // here, Answer it in a terminal (claude attach: Claude's own prompt), inTerminal
    property bool attachable: false
    // decision allow|always|deny, or "answer" with answers {question: [labels or text]}
    signal answered(string decision, string note, var answers)
    signal inTerminal()

    readonly property bool canAnswer: !!permission && (permission.answer === "hook" || permission.answer === "keys")
    readonly property var diff: permission && permission.diff ? permission.diff : []
    // What it asks with when there's no command or change to show (an MCP tool's, a page's): "key: value"
    // lines; in a row the first argRows, one line each, the pane all of them
    readonly property var args: permission && permission.args ? permission.args : []
    readonly property int argRows: 3
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
    // Another prompt in the place of the one shown (a parallel subagent's, the next one): its buttons wait a
    // moment, so a click meant for the one before doesn't answer it, and it says it's new (not the hook's
    // request coming for the prompt shown: the same thing asked)
    property var shown: null          // {request, what} of the prompt shown
    property bool settling: false     // (its buttons wait)
    property bool fresh: false        // (it says "New prompt")
    onRequestKeyChanged: {
        cancelDeny()
        const what = permission ? [permission.tool, permission.line, permission.command, permission.file].join("\n") : ""
        const request = permission ? permission.request || "" : ""
        if (shown && permission && (what !== shown.what || (request && shown.request && request !== shown.request))) {
            settling = fresh = true
            settleTimer.restart()
            freshTimer.restart()
        }
        shown = permission ? { request: request, what: what } : null
    }
    Timer {
        id: settleTimer
        interval: 600
        onTriggered: ask.settling = false
    }
    Timer {
        id: freshTimer
        interval: 3000
        onTriggered: ask.fresh = false
    }

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
        text: (ask.fresh && ask.permission ? i18n("New prompt · ") : "") + (!ask.permission ? ""
              : ask.plan ? i18n("Claude has a plan, ready to start:")
              : ask.asksQuestions ? (ask.questions.length > 1 ? i18n("Claude asks you %1 questions:", ask.questions.length)
                                                              : i18n("Claude asks you:"))
              : ask.permission.command ? i18n("Claude asks to run:")
              : ask.permission.file ? i18n("Claude asks to change %1:", ask.permission.file)
              : i18n("Claude asks: %1", ask.permission.line))
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
    Rectangle {
        visible: ask.args.length > 0
        Layout.fillWidth: true
        implicitHeight: argsColumn.implicitHeight + Kirigami.Units.smallSpacing * 2
        radius: Kirigami.Units.cornerRadius
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.07)

        Column {
            id: argsColumn
            x: Kirigami.Units.smallSpacing
            y: Kirigami.Units.smallSpacing
            width: parent.width - Kirigami.Units.smallSpacing * 2

            Repeater {
                model: ask.compact ? ask.args.slice(0, ask.argRows) : ask.args
                PlasmaComponents3.Label {
                    width: argsColumn.width
                    // (in a row: on one line, cut with … where it doesn't fit)
                    text: ask.compact ? modelData.replace(/\s+/g, " ") : modelData
                    textFormat: Text.PlainText
                    wrapMode: ask.compact ? Text.NoWrap : Text.WrapAnywhere
                    elide: ask.compact ? Text.ElideRight : Text.ElideNone
                    font.family: ask.mono
                    font.pointSize: ask.smallPt
                }
            }
            PlasmaComponents3.Label {
                visible: ask.compact && ask.args.length > ask.argRows
                width: argsColumn.width
                textFormat: Text.PlainText
                elide: Text.ElideRight
                font.pointSize: ask.smallPt
                opacity: 0.7
                text: i18n("… %1 more: Talpy Chat shows them all", ask.args.length - ask.argRows)
            }
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

            // where a link goes, under the pointer while it's hovered (made only then)
            HoverHandler {
                id: planHover
            }
            Loader {
                active: planText.hoveredLink !== ""
                sourceComponent: PlasmaComponents3.ToolTip {
                    parent: planText
                    x: planHover.point.position.x
                    y: planHover.point.position.y + Kirigami.Units.gridUnit
                    visible: true
                    delay: Kirigami.Units.toolTipDelay
                    textFormat: Text.PlainText
                    text: planText.hoveredLink
                }
            }
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
        enabled: ask.canAnswer && !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling && questionForm.complete
            icon.name: Icons.plasma.send
            text: i18n("Send answers")
            onClicked: ask.answered("answer", "", questionForm.answers())
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling
            icon.name: Icons.plasma.allow
            icon.color: Icons.color("allow", Kirigami.Theme)
            text: i18n("Allow once")
            onClicked: ask.answered("allow", "", null)
        }
        PlasmaComponents3.Button {
            visible: ask.permission && (ask.permission.answer === "keys" || ask.permission.always !== "")
            enabled: !ask.busy && !ask.settling
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
                         : i18n("From now on, without asking: %1.", ask.permission.always)
            }
        }
        PlasmaComponents3.Button {
            enabled: !ask.busy && !ask.settling
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
            enabled: !ask.busy && !ask.settling
            icon.name: ask.plan ? Icons.plasma.edit : Icons.plasma.deny
            icon.color: ask.plan ? "transparent" : Icons.color("deny", Kirigami.Theme)
            text: ask.plan ? i18n("Keep planning") : ask.asksQuestions ? i18n("Decline") : i18n("Deny")
            onClicked: {
                ask.answered(ask.plan ? "keep" : "deny", noteField.text.trim(), null)
                ask.cancelDeny()
            }
        }
        // (a plain Cancel, as every confirm line's: the undo arrow is a file's Undo)
        PlasmaComponents3.Button {
            text: i18n("Cancel")
            onClicked: ask.cancelDeny()
        }
    }
    // Never stuck: a background chat Talpy Den can't answer (started without its hook) asks in a
    // terminal, claude attach
    PlasmaComponents3.Button {
        visible: !!ask.permission && !ask.canAnswer && ask.attachable
        icon.name: Icons.plasma.terminal
        text: i18n("Answer it in a terminal")
        onClicked: ask.inTerminal()
    }
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: !!ask.permission && !ask.canAnswer
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        font.pointSize: ask.smallPt
        opacity: 0.7
        text: ask.attachable
              ? i18n("This background chat started without Talpy Den's hook, so what it asks can't be answered here: answer it in a terminal (claude attach shows Claude's own prompt), or turn on \"Answer permission prompts from Talpy Den\" in the settings for the next ones.")
              : ask.plan
              ? i18n("Approve it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings (it takes plans too) to approve it here.")
              : ask.asksQuestions
              ? i18n("Answer it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings (it answers Claude's questions too) to answer it here.")
              : i18n("Answer it in the chat, or turn on \"Answer permission prompts from Talpy Den\" in the settings to answer it here.")
    }
}
