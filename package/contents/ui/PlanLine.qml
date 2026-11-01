import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A plan a chat in plan mode wrote (<config>/plans, or its project's own
// plans folder: plan.inProject): click to read it; on hover (or Tab, or a
// finger's hold) its buttons: star, edit, send your changes to its chat,
// carry it out in a new chat, continue the chat that made it, share (not
// one in a project's folder: every account has it), delete, hide. Under an
// account's ★ Starred plans and in its project (ProjectsView.qml). A plan
// whose project isn't known (its chat went before Talpy Den saw it) says
// "chat gone" where its folder would be, as the Projects tab's card of
// plans whose chat is gone (chatGoneCard: in that card, it needn't).
ColumnLayout {
    id: planLine

    property var plan: root.emptyPlan
    property var group: root.emptyGroup
    property string remoteHost: ""
    property string accountTag: ""   // (in a project on several accounts: the one it's on)
    property string project: ""   // (in a project: its folder; the line's folder says only the part below it)
    property bool chatGoneCard: false   // (in the Projects tab's card of plans whose chat is gone)
    property real folderWidth: Kirigami.Units.gridUnit * 8
    readonly property real endWidth: root.endWidth(folderWidth)
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
                subText: (planLine.remoteHost ? i18n("Click to read it: a copy, fetched from %1.", root.hostLabel(planLine.remoteHost))
                                             : i18n("Click to read it, rendered."))
                         + (!planLine.remoteHost || root.vscodeInstalled ? " " + i18n("To change it, the edit button next to it opens its file.") : "")
                         + (planLine.plan.cwd ? "\n" + i18n("Folder: %1", (planLine.remoteHost ? root.hostLabel(planLine.remoteHost) + ":" : "") + planLine.plan.cwd) : "")
                         + (planLine.plan.shared ? "\n" + i18n("Shared with your other accounts.") : "")
                         + (planLine.plan.inProject ? "\n" + i18n("In its project's plans folder: every account has it.") : "")
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
        // its folder, a starred one's ★ and how long ago, at the line's end
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
                    text: planLine.plan.cwd ? root.folderIn(planLine.plan.cwd, planLine.project, planLine.plan.cwdShort || "")
                          : planLine.chatGoneCard ? ""
                          : i18nc("a plan whose chat is gone, so its project isn't known (where its folder would be)", "chat gone")
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideMiddle
                    PlasmaCore.ToolTipArea {   // (the whole folder: the line may be cut short)
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        active: !!planLine.plan.cwd || !planLine.chatGoneCard
                        mainText: planLine.plan.cwd ? i18n("Folder") : i18n("Its chat is gone")
                        subText: planLine.plan.cwd ? (planLine.remoteHost ? root.hostLabel(planLine.remoteHost) + ":" : "") + planLine.plan.cwd
                                 : i18n("The chat that made it went before Talpy Den saw it, so its project isn't known. The Projects tab lists it under Plans whose chat is gone.")
                    }
                }
                // starred: a ★ (click: unstar it), hidden while the buttons show (their star unstars it)
                StarMark {
                    starred: !!planLine.plan.starred
                    hidden: planButtons.shown
                    tooltip: root.starHint("plans", false) + " " + root.starHint("plans", true)
                    onClicked: root.setStar("plans", planLine.plan.slug, planLine.remoteHost, false)
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

                HoverButton {
                    // star it: it stays listed under Starred; a starred one's yellow ★ (its
                    // line's ★ hides while the buttons show) unstars it
                    icon.name: planLine.plan.starred ? Icons.plasma.starred : Icons.plasma.star
                    icon.color: Icons.color(planLine.plan.starred ? "starred" : "star", Kirigami.Theme)
                    text: planLine.plan.starred ? i18n("Unstar") : i18n("Star")
                    onClicked: root.setStar("plans", planLine.plan.slug, planLine.remoteHost, !planLine.plan.starred)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: planLine.plan.starred ? i18n("Unstar this plan") : i18n("Star this plan")
                        subText: root.starHint("plans", false) + (planLine.plan.starred ? " " + root.starHint("plans", true) : "")
                    }
                }
                // the plan's Markdown file itself, to change it (an SSH host's: in VS Code, over Remote-SSH)
                HoverButton {
                    visible: !planLine.remoteHost || root.vscodeInstalled
                    icon.name: Icons.plasma.edit
                    text: i18n("Edit the plan")
                    onClicked: root.editPlan(planLine.plan, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Edit the plan")
                        subText: planLine.remoteHost
                                 ? i18n("Opens its Markdown file on %1 in VS Code (Remote - SSH). What you change there is the plan.", root.hostLabel(planLine.remoteHost))
                                 : i18n("Opens its Markdown file in your text editor (VS Code, if the settings open plans there). What you change there is the plan.")
                    }
                }
                // what you changed in it, to the chat that made it (main.qml: sendPlanFeedback)
                // (a plan whose chat is gone keeps this button's place, greyed out, so every line's buttons and time stay in the same columns)
                HoverButton {
                    visible: !planLine.remoteHost
                    usable: !!planLine.plan.chatId
                    icon.name: Icons.plasma.send
                    text: i18n("Send your changes to Claude")
                    onClicked: root.sendPlanFeedback(planLine.plan.slug, planLine.plan.profileDir, planLine.plan.chatId)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Send your changes to Claude")
                        // (greyed out: why, as VS Code's)
                        subText: !planLine.plan.chatId ? i18n("The chat that made it isn't here any more, so there's no chat to send your changes to.")
                                 : (planLine.plan.edited ? i18n("You changed this plan since Claude wrote it.") + " " : "")
                                 + i18n("Sends what you changed in it (and notes you wrote into it) to the chat that made it: Claude revises the plan, in plan mode. In tmux it's typed in for you; else it goes to the clipboard and the chat comes up, to paste it there. A chat that isn't open reopens in plan mode with it.")
                    }
                }
                HoverButton {
                    id: planGo
                    icon.name: Icons.plasma.startNow
                    text: i18n("Carry it out…")
                    checked: root.planComposer === planLine.composerKey
                    onClicked: root.togglePlanComposer(planLine.composerKey)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Carry it out in a new chat")
                        subText: i18n("A new chat starts with the plan as its first message: in a terminal, in VS Code or in the background, in the plan's folder or another one.")
                    }
                }
                HoverButton {
                    icon.name: Icons.plasma.origin
                    usable: !!planLine.plan.chatId
                    text: i18n("Continue the chat that made it")
                    onClicked: root.continuePlanChat(planLine.plan, planLine.group, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Continue the chat that made it")
                        subText: !planLine.plan.chatId ? i18n("The chat that made it isn't here any more.")
                                 : i18n("To change the plan with Claude: its chat comes up, or reopens (in a terminal or VS Code, as the switch of Recent chats says).")
                    }
                }
                HoverButton {
                    id: planShare
                    // (not one in a project's own folder: every account has it there)
                    visible: root.shareAccountsOf(planLine.remoteHost).length >= 2 && !planLine.plan.inProject
                    icon.name: Icons.plasma.share
                    text: i18n("Share it with another account…")
                    onClicked: root.openPlanMenu(planShare, planLine.plan, planLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Share this plan")
                        subText: i18n("A shared plan is one file on each account: a change shows on all of them. Sharing a chat shares its plan too.")
                    }
                }
                HoverButton {
                    // to the Trash, after a question (DeleteAsk under the line)
                    icon.name: Icons.plasma.delete
                    icon.color: Icons.color("delete", Kirigami.Theme)
                    text: i18n("Delete…")
                    onClicked: root.askDelete(planLine.composerKey, "plan", planLine.plan.slug, planLine.plan.profileDir,
                                              planLine.remoteHost, "")

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Delete this plan…")
                        subText: root.deleteHint("plan")
                    }
                }
                HoverButton {
                    // hide it here (nothing is deleted)
                    icon.name: Icons.plasma.hide
                    text: i18n("Hide this plan")
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
