import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A new chat on an account: what Claude should do (optional), then the folder
// it starts in. The + next to an account opens one; so does a plan's "Carry
// it out" (plan set: the chat carries out that plan, in its folder first).
// With a task, the chat starts with it: in a terminal (sent at once), in VS
// Code (typed in for you to send) or in the background (no window: Claude's
// background service runs it, and it's listed right away). The background
// needs a folder Claude trusts already: it can't ask there.
Rectangle {
    id: box

    property var group
    property string remoteHost: ""
    property var plan: null

    readonly property var folders: visible ? root.newChatFolders(group, remoteHost, plan) : []
    readonly property bool inVscode: root.openInVscode(group, remoteHost, false)
    readonly property bool terminalHere: root.cliHere(remoteHost)
    readonly property bool hasTask: root.taskText.trim() !== "" || plan !== null
    readonly property bool background: root.taskBackground && hasTask
    // The account is at a usage limit: a background task can wait until it resets
    readonly property var reset: visible ? root.limitReset(group, remoteHost) : null
    readonly property bool queued: background && root.taskQueued && reset !== null
    // or later, at a time you pick (0: none yet, or it has passed)
    readonly property var days: visible ? root.laterDays() : []
    readonly property bool later: background && root.taskLater
    readonly property real laterAt: later ? root.laterAt(root.taskLaterDay, root.taskLaterTime) + 0 * root.now : 0   // (checked again as time goes by)

    // A folder a chat can start in now
    function usable(folder) {
        if (later && !laterAt)
            return false
        if (background)
            return terminalHere && folder.trusted !== false
        return inVscode || (terminalHere && (!remoteHost || !!folder.newChatCommand || hasTask))
    }

    implicitHeight: column.implicitHeight + Kirigami.Units.smallSpacing * 2
    radius: Kirigami.Units.cornerRadius
    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
    border.width: 1
    border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.12)

    onVisibleChanged: {
        if (visible) {
            taskField.text = root.taskText
            taskField.forceActiveFocus()
        }
    }
    // (a box made while its list is open, e.g. a plan's after the plans were
    // folded and unfolded, never turns visible: its field takes the task too)
    Component.onCompleted: taskField.text = root.taskText

    Connections {   // (cleared once a chat starts)
        target: root
        function onTaskTextChanged() {
            if (box.visible && taskField.text !== root.taskText)
                taskField.text = root.taskText
        }
        function onImagePasted(path, target) {
            if (!box.visible || target !== "task")
                return
            const at = taskField.cursorPosition
            taskField.insert(at, (at > 0 && taskField.text.charAt(at - 1).trim() !== "" ? " " : "") + "[Image: " + path + "] ")
            taskField.forceActiveFocus()
        }
    }

    // The pictures the task names ([Image: /path], pasted in)
    readonly property var pictures: pictureStrip.named(root.taskText)

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing / 2

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            text: {
                const where = box.remoteHost ? i18nc("account on ssh host", "%1 on %2", box.group.title, root.hostLabel(box.remoteHost)) : box.group.title
                return box.plan ? i18n("Carry out “%1” on %2, in…", box.plan.title, where) : i18n("New chat on %1 in…", where)
            }
            font.bold: true
            opacity: 0.8
            elide: Text.ElideRight
        }

        // What Claude should do (Ctrl+Enter starts it in the first folder).
        // It grows with what you write, then scrolls.
        PlasmaComponents3.ScrollView {
            id: taskScroll
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            Layout.maximumHeight: Kirigami.Units.gridUnit * 15
            // (its scroll bar has room in the field: making room as it comes
            // would wrap the text anew, and that can take it away again)
            leftPadding: 0
            rightPadding: 0

            PlasmaComponents3.TextArea {
                id: taskField
                rightPadding: padding + taskScroll.T.ScrollBar.vertical.width
                wrapMode: TextEdit.Wrap
                textFormat: TextEdit.PlainText
                placeholderText: box.plan ? i18n("Anything to add? (optional)")
                                          : i18n("What should Claude do? (optional)")
                onTextChanged: root.taskText = text
                Keys.onPressed: event => {
                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                        event.accepted = true
                        const first = box.folders.find(f => box.usable(f))
                        if (first)
                            root.startChat(box.group, box.remoteHost, first, box.inVscode, box.plan)
                    } else if (event.key === Qt.Key_Escape) {
                        event.accepted = true
                        root.newChatGroup = ""
                        root.planComposer = ""
                    } else if (event.matches(StandardKey.Paste) && !taskField.canPaste) {
                        // no text on the clipboard: a picture, maybe (an SSH host's chat: asks to copy it there)
                        event.accepted = true
                        root.pasteImage(box.remoteHost, "task")
                    }
                }

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    active: !taskField.activeFocus
                    mainText: box.plan ? i18n("Carry out a plan") : i18n("Start with a task")
                    subText: (box.plan ? i18n("The chat starts with the plan as its first message, and what you add here.")
                                       : i18n("With a task, the chat starts with it as its first message. Without one, it opens empty."))
                             + " " + i18n("Then click the folder it's for (Ctrl+Enter: the first one).")
                             + "\n\n" + (box.remoteHost ? i18n("Ctrl+V pastes a picture too: Claude gets it with the task, once you let Talpy Den copy it to %1.", root.hostLabel(box.remoteHost))
                                                         : i18n("Ctrl+V pastes a picture too: Claude gets it with the task."))
                }
            }
        }

        // The pictures it names, small: a click shows one, × takes it out
        PictureStrip {
            id: pictureStrip
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            pictures: box.pictures
            host: box.remoteHost
            removeText: i18n("Take it out of the task")
            onRemoveRequested: path => taskField.text = without(taskField.text, path)
        }

        // A picture for an SSH host's chat: copied there once you say so
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: !!box.remoteHost && !!root.pictureOffer && root.pictureOffer.host === box.remoteHost
                     && root.pictureOffer.target === "task"
            spacing: Kirigami.Units.smallSpacing

            Image {
                source: root.pictureOffer ? "file://" + encodeURI(root.pictureOffer.path) : ""
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2
                Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                sourceSize.height: Kirigami.Units.gridUnit * 2 * Screen.devicePixelRatio
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }
            ConfirmLine {
                Layout.fillWidth: true
                text: i18n("Copy this picture to %1? Claude there can only open it there.", root.hostLabel(box.remoteHost))
                confirmText: i18n("Copy")
                onConfirmed: root.copyPicture()
                onCancelled: root.pictureOffer = null
            }
        }
        PlasmaComponents3.Label {
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: !!box.remoteHost && root.pictureCopyingTo === box.remoteHost && root.pictureCopyTarget === "task"
            textFormat: Text.PlainText
            text: i18n("Copying the picture to %1…", root.hostLabel(box.remoteHost))
            opacity: 0.7
        }

        // The model and reasoning effort it runs with (kept for the next chat).
        // Not for VS Code's Claude: its tab has its own model setting.
        RowLayout {
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: !box.inVscode || box.background
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                text: i18n("Model:")
                opacity: 0.8
            }
            PlasmaComponents3.ComboBox {
                readonly property var values: ["opus", "sonnet", "fable", "haiku", ""]
                model: [i18n("Opus"), i18n("Sonnet"), i18n("Fable"), i18n("Haiku"), i18n("Claude's default")]
                currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatModel))
                onActivated: Plasmoid.configuration.newChatModel = values[currentIndex]
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                text: i18n("Effort:")
                opacity: 0.8
            }
            PlasmaComponents3.ComboBox {
                readonly property var values: ["low", "medium", "high", "xhigh", "max", ""]
                model: [i18nc("reasoning effort", "Low"), i18nc("reasoning effort", "Medium"), i18nc("reasoning effort", "High"),
                        i18nc("reasoning effort", "Extra high"), i18nc("reasoning effort", "Max"), i18n("Claude's default")]
                currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatEffort))
                onActivated: Plasmoid.configuration.newChatEffort = values[currentIndex]

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Model and effort")
                    subText: i18n("The chat starts with them (claude --model, --effort); you can still change them in it (/model, /effort). The next new chat starts with the same.")
                }
            }
        }

        // and the permission mode it starts in (kept for the next chat)
        RowLayout {
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: !box.inVscode || box.background
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                text: i18n("Permissions:")
                opacity: 0.8
            }
            PlasmaComponents3.ComboBox {
                id: modeBox
                readonly property var values: ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", ""]
                model: [i18nc("permission mode", "Manual (asks first)"), i18nc("permission mode", "Accept edits"),
                        i18nc("permission mode", "Plan"), i18nc("permission mode", "Auto"), i18nc("permission mode", "Don't ask"),
                        i18nc("permission mode", "Bypass permissions"), i18n("Claude's default")]
                currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatMode))
                onActivated: Plasmoid.configuration.newChatMode = values[currentIndex]

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Permission mode")
                    subText: (modeBox.values[modeBox.currentIndex] === "default"
                              ? i18n("Manual: Claude asks you before it edits files or runs commands.")
                              : modeBox.values[modeBox.currentIndex] === ""
                              ? i18n("The mode your Claude settings start chats in.")
                              : root.modeHint(modeBox.values[modeBox.currentIndex]))
                             + "\n\n" + i18n("The chat starts in it (claude --permission-mode); Shift+Tab in the chat changes it. The next new chat starts in the same.")
                             + " " + i18n("A background chat can start in auto mode or bypass permissions only once you turned that on in a terminal: Claude says so then.")
                }
            }
        }

        PlasmaComponents3.CheckBox {
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: box.hasTask
            text: i18n("In the background")
            checked: root.taskBackground
            enabled: box.terminalHere
            onToggled: root.taskBackground = checked

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Run it in the background")
                subText: i18n("No window opens: Claude's background service runs the chat (claude --bg), and it's listed here right away, so you see when it needs you. Only in folders Claude trusts already: it can't ask there.")
            }
        }

        PlasmaComponents3.CheckBox {
            Layout.leftMargin: Kirigami.Units.gridUnit
            visible: box.background && box.reset !== null
            text: box.reset ? i18n("After the limit resets (in %1, at %2)", root.duration(box.reset.at - root.now), root.clockText(box.reset.at)) : ""
            checked: root.taskQueued
            onToggled: {
                root.taskQueued = checked
                if (checked)
                    root.taskLater = false
            }

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Wait for the usage limit")
                subText: i18n("This account is at its usage limit. The task waits under the account and starts in the background a minute after the limit resets, while Talpy Den runs (or as soon as it runs again). You can start or cancel it before.")
            }
        }

        // or later, on a day at a time (the default: right away)
        RowLayout {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.fillWidth: true
            visible: box.background
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.CheckBox {
                text: i18n("Later:")
                checked: root.taskLater
                onToggled: root.pickLater(checked)

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Start it later")
                    subText: i18n("The task waits under the account and starts in the background on the day and at the time you pick, while Talpy Den runs (or as soon as it runs again). You can start or cancel it before.")
                }
            }
            // the day: today and the next six
            PlasmaComponents3.ToolButton {
                enabled: root.taskLater && root.taskLaterDay > 0
                icon.name: Icons.plasma.previous
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("A day earlier")
                Layout.preferredHeight: laterTime.implicitHeight
                Layout.preferredWidth: Layout.preferredHeight
                onClicked: root.taskLaterDay -= 1
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                enabled: root.taskLater
                text: box.days[root.taskLaterDay] || ""
                horizontalAlignment: Text.AlignHCenter
                Layout.preferredWidth: Kirigami.Units.gridUnit * 5
            }
            PlasmaComponents3.ToolButton {
                enabled: root.taskLater && root.taskLaterDay < box.days.length - 1
                icon.name: Icons.plasma.next
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("A day later")
                Layout.preferredHeight: laterTime.implicitHeight
                Layout.preferredWidth: Layout.preferredHeight
                onClicked: root.taskLaterDay += 1
            }
            PlasmaComponents3.TextField {
                id: laterTime
                enabled: root.taskLater
                text: root.taskLaterTime
                placeholderText: i18nc("a time to type", "HH:MM")
                inputMethodHints: Qt.ImhPreferNumbers
                horizontalAlignment: TextInput.AlignHCenter
                onTextEdited: root.taskLaterTime = text
                Layout.preferredWidth: Kirigami.Units.gridUnit * 3.5
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                visible: root.taskLater
                Layout.fillWidth: true
                text: box.laterAt ? i18n("in %1", root.duration(box.laterAt - root.now))
                      : !root.taskLaterTime.trim() ? i18n("e.g. 14:30")
                      : root.laterClock(root.taskLaterTime) ? i18n("that time has passed")
                      : i18n("not a time: 24-hour HH:MM, e.g. 14:30")
                color: box.laterAt || !root.taskLaterTime.trim() ? Kirigami.Theme.textColor : Kirigami.Theme.negativeTextColor
                opacity: box.laterAt ? 0.7 : 1
                font: Kirigami.Theme.smallFont
                elide: Text.ElideRight
            }
        }

        // Where it starts otherwise: Terminal | VS Code
        OpenInSwitch {
            visible: !box.background
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            group: box.group
            remoteHost: box.remoteHost
        }

        Repeater {
            model: box.folders.length
            delegate: PlasmaComponents3.ItemDelegate {
                id: folderRow
                required property int index
                readonly property var folder: box.folders[index] || ({ path: "", short: "", newChatCommand: "", trusted: true })
                readonly property bool untrusted: box.background && folder.trusted === false
                Layout.fillWidth: true
                icon.name: folderRow.folder.short === "~" ? Icons.plasma.home : Icons.plasma.folder
                text: (folderRow.folder.short === "~" ? i18n("Home folder (~)") : folderRow.folder.short)
                      + (box.plan && index === 0 && box.plan.cwd ? "  " + i18nc("the folder a plan was made in", "(the plan's)") : "")
                enabled: box.usable(folderRow.folder)
                onClicked: root.startChat(box.group, box.remoteHost, folderRow.folder, box.inVscode, box.plan)
                // (as the delegate's own, but the folder's name as it is: one that looks like markup isn't drawn as it)
                contentItem: RowLayout {
                    spacing: folderRow.spacing
                    Kirigami.Icon {
                        source: folderRow.icon.name
                        Layout.preferredWidth: folderRow.icon.width
                        Layout.preferredHeight: folderRow.icon.height
                    }
                    Text {
                        Layout.fillWidth: true
                        text: folderRow.text
                        textFormat: Text.PlainText
                        font: folderRow.font
                        color: Kirigami.Theme.textColor
                        elide: Text.ElideRight
                    }
                }

                // (a tooltip drawn in the popup, not Plasma's shared tooltip
                // window: when Plasma quits, this list can change once more
                // and Qt then keeps its rows until the very end, and the last
                // row that had used Plasma's tooltip window took it down after
                // the event loop had stopped, which held plasmashell's exit
                // for good, until systemd aborted it)
                PlasmaComponents3.ToolTip.visible: folderRow.untrusted && folderRow.hovered
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                PlasmaComponents3.ToolTip.text: i18n("Claude doesn't trust this folder yet") + "\n"
                    + (folderRow.folder.short === "~"
                       ? i18n("Claude never keeps trusting your home folder, and a background chat can't ask: start it in a terminal, or pick a project folder.")
                       : i18n("A background chat can't ask whether you trust it: start a chat there in a terminal once and say yes."))
            }
        }

        Kirigami.Separator {
            visible: !box.remoteHost && box.folders.length > 0
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing / 2
            Layout.bottomMargin: Kirigami.Units.smallSpacing / 2
        }

        // Any folder, picked in the folder dialog (not on an SSH host)
        PlasmaComponents3.ItemDelegate {
            visible: !box.remoteHost
            enabled: box.later && !box.laterAt ? false : box.background ? box.terminalHere : (box.inVscode || box.terminalHere)
            Layout.fillWidth: true
            icon.name: Icons.plasma.chooseFolder
            text: i18n("Choose folder…")
            onClicked: root.startChat(box.group, box.remoteHost, { path: "", short: "" }, box.inVscode, box.plan)
        }
    }
}
