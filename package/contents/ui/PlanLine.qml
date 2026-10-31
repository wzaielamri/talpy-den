import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A plan a chat in plan mode wrote (<config>/plans): click to read it; on
// hover (or Tab, or a finger's hold) its buttons: star, edit, send your
// changes to its chat, carry it out in a new chat, continue the chat that
// made it, share, delete, hide. Under an account's ★ Starred plans and in
// its project (ProjectsView.qml).
ColumnLayout {
    id: planLine

    property var plan: root.emptyPlan
    property var group: root.emptyGroup
    property string remoteHost: ""
    property string accountTag: ""   // (in a project on several accounts: the one it's on)
    property string project: ""   // (in a project: its folder; the line's folder says only the part below it)
    property real folderWidth: Kirigami.Units.gridUnit * 8
    readonly property real endWidth: folderWidth + Kirigami.Units.smallSpacing + root.agoWidth
    readonly property string composerKey: (planLine.remoteHost ? planLine.remoteHost + "|" : "") + plan.key

    Layout.fillWidth: true
    Layout.rightMargin: Kirigami.Units.smallSpacing
    spacing: Kirigami.Units.smallSpacing / 2

    HoverHandler {
        id: planHover
    }
    TouchHold {
        buttons: planButtons
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: Icons.plasma.plan
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            opacity: 0.7
        }
        PlasmaComponents3.Label {
            id: planName
            textFormat: Text.PlainText
            text: planLine.plan.title
            font.underline: planMouse.containsMouse || activeFocus
            elide: Text.ElideRight
            Layout.fillWidth: true
            // (Tab: its buttons show; Enter: as a click)
            activeFocusOnTab: true
            Keys.onReturnPressed: root.openPlan(planLine.plan.slug, planLine.plan.profileDir, planLine.remoteHost)
            Keys.onEnterPressed: root.openPlan(planLine.plan.slug, planLine.plan.profileDir, planLine.remoteHost)

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                width: planName.contentWidth
                height: parent.height
                mainText: planLine.plan.title
                subText: (planLine.remoteHost ? i18n("Click to read it: a copy, fetched from %1.", planLine.remoteHost)
                                             : i18n("Click to read it, rendered."))
                         + (!planLine.remoteHost || root.vscodeInstalled ? " " + i18n("To change it, the edit button next to it opens its file.") : "")
                         + (planLine.plan.cwd ? "\n" + i18n("Folder: %1", (planLine.remoteHost ? planLine.remoteHost + ":" : "") + planLine.plan.cwd) : "")
                         + (planLine.plan.shared ? "\n" + i18n("Shared with your other accounts.") : "")
                         + (planLine.plan.chatId ? "" : "\n" + i18n("The chat that made it isn't here any more."))

                MouseArea {
                    id: planMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (!planButtons.holding) root.openPlan(planLine.plan.slug, planLine.plan.profileDir, planLine.remoteHost)

                    TouchHold {
                        buttons: planButtons
                    }
                }
            }
        }
Kirigami.Icon {
            source: Icons.plasma.share
            visible: planLine.plan.shared
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            Layout.alignment: Qt.AlignVCenter
            opacity: 0.6
        }
        Loader {   // (made only where there is one: in a project on several accounts)
            active: planLine.accountTag !== ""
            visible: active
            sourceComponent: AccountTag {
                text: planLine.accountTag
            }
        }
        // you changed it since Claude wrote it: send that to its chat (as in VS Code)
        Loader {   // (made only when it shows)
            active: !!planLine.plan.edited && !!planLine.plan.chatId && !planLine.remoteHost
            visible: active && !!item && item.visible
            sourceComponent: Tag {
                visible: !!planLine.plan.edited && !!planLine.plan.chatId && !planLine.remoteHost
                icon: Icons.plasma.send
                text: i18nc("send your changes to the plan to the chat", "Send")
                active: true
                clickable: true
                tooltipTitle: i18n("Send your changes to Claude")
                tooltip: i18n("You changed this plan since Claude wrote it. Click to send what you changed (and notes you wrote into it) to the chat that made it: Claude revises the plan, in plan mode.")
                onClicked: root.sendPlanFeedback(planLine.plan.slug, planLine.plan.profileDir, planLine.plan.chatId)
            }
        }
        // starred: a ★ (click: unstar it)
        StarMark {
            visible: !!planLine.plan.starred
            tooltip: root.starHint("plans", false) + " " + root.starHint("plans", true)
            onClicked: root.setStar("plans", planLine.plan.slug, planLine.remoteHost, false)
        }
        // its folder and how long ago, at the line's end
        CoveredEnd {
            id: planEnd
            covered: planButtons.covering
            Layout.preferredWidth: planLine.endWidth
            implicitHeight: planWhen.implicitHeight

            RowLayout {
                width: planEnd.width
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    id: planWhen
                    Layout.preferredWidth: planLine.folderWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: root.folderIn(planLine.plan.cwd, planLine.project, planLine.plan.cwdShort || "")
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideMiddle
                    PlasmaCore.ToolTipArea {   // (the whole folder: the line may be cut short)
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        active: !!planLine.plan.cwd
                        mainText: i18n("Folder")
                        subText: (planLine.remoteHost ? planLine.remoteHost + ":" : "") + planLine.plan.cwd
                    }
                }
                PlasmaComponents3.Label {
                    Layout.preferredWidth: root.agoWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: root.ago(root.now - planLine.plan.updatedAt)
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
        }
        // on hover (and while its new chat box is open), over the line's end
        HoverButtons {
            id: planButtons
            lineHeight: planName.implicitHeight
            shown: planHover.hovered || planName.activeFocus || planButtons.focused || planButtons.held
                   || root.planComposer === planLine.composerKey || root.deleteAsk.key === planLine.composerKey
            under: planEnd

            RowLayout {   // (made the first time they show)
                spacing: 0

                PlasmaComponents3.ToolButton {
                    // star it: it stays listed under Starred (a starred one has its ★)
                    visible: !planLine.plan.starred
                    icon.name: Icons.plasma.star
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Star")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.setStar("plans", planLine.plan.slug, planLine.remoteHost, true)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Star this plan")
                        subText: root.starHint("plans", false)
                    }
                }
                // the plan's Markdown file itself, to change it (an SSH host's: in VS Code, over Remote-SSH)
                PlasmaComponents3.ToolButton {
                    visible: !planLine.remoteHost || root.vscodeInstalled
                    icon.name: Icons.plasma.edit
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Edit the plan")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.editPlan(planLine.plan, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Edit the plan")
                        subText: planLine.remoteHost
                                 ? i18n("Opens its Markdown file on %1 in VS Code (Remote - SSH). What you change there is the plan.", planLine.remoteHost)
                                 : i18n("Opens its Markdown file in your text editor (VS Code, if the settings open plans there). What you change there is the plan.")
                    }
                }
                // what you changed in it, to the chat that made it (main.qml: sendPlanFeedback)
                // (a plan whose chat is gone keeps this button's place, greyed out, so every line's buttons and time stay in the same columns)
                PlasmaComponents3.ToolButton {
                    visible: !planLine.remoteHost
                    enabled: !!planLine.plan.chatId
                    icon.name: Icons.plasma.send
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Send your changes to Claude")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.sendPlanFeedback(planLine.plan.slug, planLine.plan.profileDir, planLine.plan.chatId)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Send your changes to Claude")
                        subText: (planLine.plan.edited ? i18n("You changed this plan since Claude wrote it.") + " " : "")
                                 + i18n("Sends what you changed in it (and notes you wrote into it) to the chat that made it: Claude revises the plan, in plan mode. In tmux it's typed in for you; else it goes to the clipboard and the chat comes up, to paste it there. A chat that isn't open reopens in plan mode with it.")
                    }
                }
                PlasmaComponents3.ToolButton {
                    id: planGo
                    icon.name: Icons.plasma.startNow
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Carry it out…")
                    checked: root.planComposer === planLine.composerKey
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.togglePlanComposer(planLine.composerKey)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Carry it out in a new chat")
                        subText: i18n("A new chat starts with the plan as its first message: in a terminal, in VS Code or in the background, in the plan's folder or another one.")
                    }
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.origin
                    enabled: !!planLine.plan.chatId
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Continue the chat that made it")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.continuePlanChat(planLine.plan, planLine.group, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Continue the chat that made it")
                        subText: i18n("To change the plan with Claude: its chat comes up, or reopens (in a terminal or VS Code, as the switch of Recent chats says).")
                    }
                }
                PlasmaComponents3.ToolButton {
                    id: planShare
                    visible: root.shareAccountsOf(planLine.remoteHost).length >= 2
                    icon.name: Icons.plasma.share
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Share it with another account…")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.openPlanMenu(planShare, planLine.plan, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Share this plan")
                        subText: i18n("A shared plan is one file on each account: a change shows on all of them. Sharing a chat shares its plan too.")
                    }
                }
                PlasmaComponents3.ToolButton {
                    // to the Trash, after a question (DeleteAsk under the line)
                    icon.name: Icons.plasma.delete
                    icon.color: Icons.color("delete", Kirigami.Theme)
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Delete…")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.askDelete(planLine.composerKey, "plan", planLine.plan.slug, planLine.plan.profileDir,
                                              planLine.remoteHost, "")

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Delete this plan…")
                        subText: root.deleteHint("plan")
                    }
                }
                PlasmaComponents3.ToolButton {
                    // hide it here (nothing is deleted)
                    icon.name: Icons.plasma.hide
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Hide this plan")
                    Layout.preferredHeight: planButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: planButtons.buttonWidth
                    onClicked: root.hideItem("plans", planLine.plan.slug, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Hide this plan")
                        subText: root.hideHint("plans", planLine.remoteHost)
                    }
                }
            }
        }
    }

    DeleteAsk {
        Layout.fillWidth: true
        itemKey: planLine.composerKey
    }
    // (made only while it's open: one under every plan made the list
    // slow to open; made hidden, then shown, it takes the task and
    // the focus as it shows)
    Loader {
        id: planBox
        readonly property bool shown: root.planComposer === planLine.composerKey
        active: shown
        visible: shown
        Layout.fillWidth: true
        onLoaded: item.visible = Qt.binding(() => planBox.shown)

        sourceComponent: NewChatBox {
            visible: false
            group: planLine.group
            remoteHost: planLine.remoteHost
            plan: planLine.plan
        }
    }
}
