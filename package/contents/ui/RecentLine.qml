import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A chat to pick up again: one of an account's recent or starred chats, or
// of a project's (ProjectsView.qml). A click opens it beside the popup (or
// reopens it, in a terminal or in VS Code); its tags say what stopped it or
// what's to review; on hover (or Tab, or a finger's hold) its buttons:
// reopen, star, share, delete.
ColumnLayout {
    id: recentLine

    property var chat: ({ key: "", sessionId: "", name: "", cwd: "", cwdShort: "", lastActive: 0, profileDir: "",
                          profile: "", shared: false, openCommand: "", starred: false })
    property var group: root.emptyGroup
    property string remoteHost: ""
    property string accountTag: ""   // (in a project on several accounts: the one it's on)
    property string project: ""   // (in a project: its folder; the line's folder says only the part below it)
    // the folder and how long ago at the line's end: columns of one width in
    // every list, so what's before them lines up, and the folders and times too
    property real folderWidth: Kirigami.Units.gridUnit * 8
    readonly property real endWidth: folderWidth + Kirigami.Units.smallSpacing + root.agoWidth
    // where it reopens: as the Terminal | VS Code switch of the account's chats says (OpenInSwitch.qml)
    readonly property bool inVscode: root.openInVscode(group, remoteHost, true)
    readonly property bool terminalHere: root.cliHere(remoteHost)
    readonly property string rowKey: (recentLine.remoteHost ? recentLine.remoteHost + "|" : "") + chat.key
    readonly property bool canOpen: recentLine.inVscode
                                    || (recentLine.terminalHere && (!recentLine.remoteHost || !!chat.openCommand))

    // a click on its name
    function click() {
        if (Plasmoid.configuration.clickOpensPane)
            root.openPane(chat, recentLine.remoteHost, "chat")
        else if (canOpen)
            open()
    }

    function open() {
        if (recentLine.remoteHost && recentLine.inVscode)
            root.remoteResumeVscode(recentLine.remoteHost, chat.sessionId, chat.cwd)
        else if (recentLine.remoteHost)
            root.remoteOpen(recentLine.remoteHost, chat.openCommand)
        else if (recentLine.inVscode)
            root.resumeInVscode(chat.sessionId, chat.profileDir)
        else
            root.jumpTo(chat.sessionId, chat.profileDir)
    }

    Layout.fillWidth: true
    Layout.rightMargin: Kirigami.Units.smallSpacing
    spacing: 0

    HoverHandler {
        id: recentHover
    }
    TouchHold {
        buttons: recentButtons
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            id: recentName
            textFormat: Text.PlainText
            text: recentLine.chat.name
            font.underline: recentMouse.containsMouse || activeFocus
            opacity: recentLine.canOpen || Plasmoid.configuration.clickOpensPane ? 1 : 0.6
            elide: Text.ElideRight
            Layout.fillWidth: true
            // (Tab: its buttons show; Enter: as a click)
            activeFocusOnTab: true
            Keys.onReturnPressed: recentLine.click()
            Keys.onEnterPressed: recentLine.click()

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                width: recentName.contentWidth
                height: parent.height
                mainText: recentLine.chat.name
                subText: (Plasmoid.configuration.clickOpensPane
                          ? i18n("Click to open it beside the popup: its conversation, a box to reply, and what it changed.")
                            + (recentLine.canOpen ? "\n" + i18n("The reopen button (on hover): %1", recentLine.inVscode ? root.vscodeHint(recentLine.group, recentLine.remoteHost, true)
                                                                                                                         : root.terminalHint(recentLine.remoteHost, true)) : "")
                          : recentLine.canOpen ? (recentLine.inVscode ? root.vscodeHint(recentLine.group, recentLine.remoteHost, true)
                                                                        : root.terminalHint(recentLine.remoteHost, true))
                          : root.terminalHint(recentLine.remoteHost, true) + "\n" + root.vscodeHint(recentLine.group, recentLine.remoteHost, true))
                         + (recentLine.chat.cwd ? "\n" + i18n("Folder: %1", (recentLine.remoteHost ? recentLine.remoteHost + ":" : "") + recentLine.chat.cwd) : "")
                         + (recentLine.chat.shared ? "\n" + i18n("Shared between accounts; last used on %1.", recentLine.chat.profile) : "")
                         + (recentLine.chat.stopped ? "\n\n" + root.stopText(recentLine.chat.stopped) : "")
                         + (recentLine.chat.recap ? "\n\n" + i18n("Recap: %1", recentLine.chat.recap.text) : "")

                MouseArea {
                    id: recentMouse
                    anchors.fill: parent
                    enabled: recentLine.canOpen || Plasmoid.configuration.clickOpensPane
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (!recentButtons.holding) recentLine.click()

                    TouchHold {
                        buttons: recentButtons
                    }
                }
            }
        }
Kirigami.Icon {
            source: Icons.plasma.share
            visible: recentLine.chat.shared
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            Layout.alignment: Qt.AlignVCenter
            opacity: 0.6
        }
        Loader {   // (made only where there is one: in a project on several accounts)
            active: recentLine.accountTag !== ""
            visible: active
            sourceComponent: AccountTag {
                text: recentLine.accountTag
            }
        }
        // a usage limit stopped it (talpy_den.py: limit_stop): until it resets;
        // click: it goes on by itself then (queued; again: cancelled)
        Loader {   // (made only when it shows: most lines have none of these tags)
            active: root.queuedChat(recentLine.chat.sessionId, recentLine.remoteHost) !== null
                    || (!!recentLine.chat.stopped && recentLine.chat.stopped.kind === "limit" && !recentLine.chat.stopped.over)
            visible: active && !!item && item.visible
            sourceComponent: Tag {
                readonly property real goOnAt: root.goOnAt(recentLine.chat)
                readonly property var goingOn: root.queuedChat(recentLine.chat.sessionId, recentLine.remoteHost)
                visible: goingOn !== null
                         || (!!recentLine.chat.stopped && recentLine.chat.stopped.kind === "limit" && !recentLine.chat.stopped.over)
                icon: goingOn ? Icons.plasma.goOnAt : ""
                text: goingOn ? root.startText(goingOn.startAt)
                              : i18n("Limit")
                warning: goingOn === null
                active: goingOn !== null
                clickable: goingOn !== null || goOnAt > 0
                tooltipTitle: goingOn ? i18n("Goes on by itself at %1", root.startText(goingOn.startAt))
                                      : i18n("A usage limit stopped it")
                tooltip: (goingOn ? i18n("In the background, in the permission mode it had, telling Claude that the limit has reset (if it didn't go on before then).")
                          : (recentLine.chat.stopped ? recentLine.chat.stopped.text : "")
                            + (goOnAt > 0 ? "\n\n" + i18n("Click to have it go on by itself in the background at %1, a minute after the limit resets, once.", root.startText(goOnAt))
                                            + (recentLine.remoteHost ? "" : " " + i18n("Keep going beside it: after later limits too, until it's done.")) : ""))
                         + (goingOn ? "\n\n" + i18n("Click to cancel it.")
                                      + (root.keptChat(recentLine.chat.sessionId) !== null && !recentLine.remoteHost
                                         ? " " + i18n("It stops keeping going after usage limits too.") : "") : "")
                onClicked: {
                    if (goingOn)
                        root.unqueue(goingOn)
                    else
                        root.queueContinue(recentLine.chat, recentLine.remoteHost, recentLine.group.title, false)
                }
            }
        }
        // it keeps going (click: not any more), or a limit stopped it and it can (click: it does)
        Loader {   // (made only when it may show)
            active: !recentLine.remoteHost && (root.keptChat(recentLine.chat.sessionId) !== null || root.goOnAt(recentLine.chat) > 0)
            visible: active && !!item && item.visible
            sourceComponent: Tag {
                readonly property var kept: recentLine.remoteHost ? null : root.keptChat(recentLine.chat.sessionId)
                readonly property bool canKeep: kept === null && !recentLine.remoteHost && root.goOnAt(recentLine.chat) > 0
                                                && root.queuedChat(recentLine.chat.sessionId, recentLine.remoteHost) === null
                visible: kept !== null || canKeep
                icon: Icons.plasma.keepGoing
                active: kept !== null && !kept.error
                warning: kept !== null && (!!kept.error || !!kept.note)
                clickable: true
                tooltipTitle: kept ? i18n("Keeps going until it's done") : i18n("Keep going until it's done")
                tooltip: kept ? root.keptText(kept)
                              : i18n("Click to have it go on by itself in the background at %1, a minute after the limit resets, in the permission mode it had, and again after each later limit that stops it, until a turn of it ends by itself.",
                                     root.startText(root.goOnAt(recentLine.chat)))
                onClicked: {
                    if (kept)
                        root.keepGoing(recentLine.chat, false)
                    else
                        root.queueContinue(recentLine.chat, recentLine.remoteHost, recentLine.group.title, true)
                }
            }
        }
        // it changed files: to review until you mark it reviewed (ChatPane.qml)
        Loader {   // (made only when it shows)
            active: root.reviewPending(recentLine.chat, recentLine.remoteHost)
            visible: active && !!item && item.visible
            sourceComponent: Tag {
                visible: root.reviewPending(recentLine.chat, recentLine.remoteHost)
                text: i18nc("a finished chat's changes, not reviewed yet", "To review")
                active: true
                clickable: true
                onClicked: root.openPane(recentLine.chat, recentLine.remoteHost, "review")
                tooltipTitle: i18n("Not reviewed yet")
                tooltip: i18n("It changed files. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed.")
            }
        }
        Loader {   // (made only when it shows)
            active: root.reviewPending(recentLine.chat, recentLine.remoteHost)
            visible: active && !!item && item.visible
            sourceComponent: TestsBadge {
                review: root.reviewPending(recentLine.chat, recentLine.remoteHost) ? recentLine.chat.review : null
            }
        }
        // starred: a ★ (click: unstar it)
        StarMark {
            visible: !!recentLine.chat.starred
            tooltip: root.starHint("chats", false) + " " + root.starHint("chats", true)
            onClicked: root.setStar("chats", recentLine.chat.sessionId, recentLine.remoteHost, false)
        }
        // its folder and how long ago, at the line's end
        CoveredEnd {
            id: recentEnd
            covered: recentButtons.covering
            Layout.preferredWidth: recentLine.endWidth
            implicitHeight: recentFolder.implicitHeight

            RowLayout {
                width: recentEnd.width
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    id: recentFolder
                    Layout.preferredWidth: recentLine.folderWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: root.folderIn(recentLine.chat.cwd, recentLine.project, recentLine.chat.cwdShort || "~")
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideMiddle
                    PlasmaCore.ToolTipArea {   // (the whole folder: the line may be cut short)
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        active: !!recentLine.chat.cwd
                        mainText: i18n("Folder")
                        subText: (recentLine.remoteHost ? recentLine.remoteHost + ":" : "") + recentLine.chat.cwd
                    }
                }
                PlasmaComponents3.Label {
                    Layout.preferredWidth: root.agoWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: root.ago(root.now - recentLine.chat.lastActive)
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
        }
        // on hover, over the line's end
        HoverButtons {
            id: recentButtons
            lineHeight: recentName.implicitHeight
            shown: recentHover.hovered || recentName.activeFocus || recentButtons.focused || recentButtons.held
                   || root.deleteAsk.key === recentLine.rowKey
            under: recentEnd

            RowLayout {   // (made the first time they show)
                spacing: 0

                PlasmaComponents3.ToolButton {
                    // with clicks opening the pane: reopen the chat itself
                    visible: Plasmoid.configuration.clickOpensPane && recentLine.canOpen
                    icon.name: Icons.plasma.openWindow
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Reopen this chat")
                    Layout.preferredHeight: recentButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: recentButtons.buttonWidth
                    onClicked: recentLine.open()

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Reopen this chat")
                        subText: recentLine.inVscode ? root.vscodeHint(recentLine.group, recentLine.remoteHost, true)
                                                       : root.terminalHint(recentLine.remoteHost, true)
                    }
                }
                PlasmaComponents3.ToolButton {
                    // star it: it stays listed under Starred (a starred one has its ★)
                    visible: !recentLine.chat.starred
                    icon.name: Icons.plasma.star
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Star")
                    Layout.preferredHeight: recentButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: recentButtons.buttonWidth
                    onClicked: root.setStar("chats", recentLine.chat.sessionId, recentLine.remoteHost, true)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Star this chat")
                        subText: root.starHint("chats", false)
                    }
                }
                PlasmaComponents3.ToolButton {
                    id: recentShare
                    visible: root.shareAccountsOf(recentLine.remoteHost).length >= 2
                    icon.name: Icons.plasma.share
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Share or continue on another account…")
                    Layout.preferredHeight: recentButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: recentButtons.buttonWidth
                    onClicked: root.openShareMenu(recentShare, {
                        chatId: recentLine.chat.sessionId, name: recentLine.chat.name,
                        profileDir: recentLine.chat.profileDir, shared: recentLine.chat.shared, host: recentLine.remoteHost
                    }, recentLine.rowKey)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Continue on another account")
                        subText: root.shareHint(recentLine.remoteHost)
                    }
                }
                PlasmaComponents3.ToolButton {
                    // to the Trash, after a question (DeleteAsk under the line)
                    icon.name: Icons.plasma.delete
                    icon.color: Icons.color("delete", Kirigami.Theme)
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Delete…")
                    Layout.preferredHeight: recentButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: recentButtons.buttonWidth
                    onClicked: root.askDelete(recentLine.rowKey, "chat", recentLine.chat.sessionId,
                                              recentLine.chat.profileDir, recentLine.remoteHost, "")

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Delete this chat…")
                        subText: root.deleteHint("chat")
                    }
                }
            }
        }
    }

    KeepOnlyMessage {
        Layout.fillWidth: true
        shown: root.shareConfirm.key === recentLine.rowKey
    }
    DeleteAsk {
        Layout.fillWidth: true
        itemKey: recentLine.rowKey
    }
}
