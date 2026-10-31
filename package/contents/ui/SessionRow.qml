import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

RowLayout {
    id: row

    property var session
    property bool showProfile: false
    property string remoteHost: ""   // set for a session on an SSH host
    property string account: ""      // its account's title

    // Where it runs, in the chat pane's words (ChatPane.qml where)
    readonly property string tag: session.pid === null ? i18nc("where a chat runs", "Not open")
                                  : session.kind === "bg" ? i18n("Background")
                                  : session.entrypoint === "claude-vscode" ? i18n("Claude Code panel")
                                  : session.tmux ? "Tmux"
                                  : session.vscodeTerminal || session.terminalApp === "VS Code" ? i18nc("where a chat runs", "VS Code terminal")
                                  : i18nc("where a chat runs", "Terminal")
    // A background session with a running process can be stopped (`claude stop`),
    // and so can a chat with a process of its own, whatever it's doing: in a
    // terminal its claude quits (the chat is kept), in VS Code its tab shows it
    // as interrupted and goes on with the next message (talpy_den.py:
    // stopping and interrupting chats). One in tmux that's working can be
    // interrupted instead: Ctrl+C in its pane, like VS Code's stop button.
    readonly property bool canEnd: session.kind === "interactive" && session.pid !== null
    readonly property bool inVscode: session.entrypoint === "claude-vscode"
    // (not when only a background command runs: its turn is over, Ctrl+C would land at its prompt)
    readonly property bool canInterrupt: canEnd && !!session.tmux && (session.state === "working" || session.state === "waiting")
                                         && session.reason !== "background shell"
    readonly property bool canStop: canEnd || (session.kind === "bg" && session.pid !== null && (!remoteHost || !!session.stopCommand))
    readonly property string stopTitle: row.canInterrupt ? i18n("Interrupt or stop this chat")
                                        : row.canEnd ? i18n("Stop this chat") : i18n("Stop this background chat")
    readonly property string stopTip: row.canInterrupt
        ? i18n("Asks first. Interrupting is like Ctrl+C in its tmux pane, or the stop button in VS Code: the current step and its subagents stop, and the chat stays open there.")
        : row.canEnd && row.inVscode
        ? i18n("Asks first. Its tab in VS Code shows it as interrupted, keeps the chat and goes on with your next message.")
        : row.canEnd && row.session.state === "idle"
        ? i18n("Asks first. Claude quits and its terminal stays open; the chat is kept and shows under Recent chats.")
        : row.canEnd
        ? i18n("Asks first. The current step is cut off, Claude quits and its terminal stays open; the chat is kept and shows under Recent chats.")
        : i18n("Asks first. The conversation is kept; claude attach resumes it.")
    // Kept in root by row key: rows are refreshed with new data every poll
    // (by the chat: a background session that ends stays open where it was).
    readonly property string rowKey: root.rowKeyOf(session, remoteHost)

    // Motion: the row is the same delegate whichever chat it shows, so when a
    // chat moves in the list (or a row above it grows) it slides from where
    // it was drawn last (root.rowSpots) to where it is; a chat new to the list
    // fades in. Placed once a layout has settled (Qt.callLater).
    // (a new row isn't where it goes until the layout has placed it: its first
    // move, or a moment after it's made, at the top)
    transform: Translate { id: slide }
    property bool laidOut: false
    // Where its list starts, if it's in one (an account's): it's placed in
    // the list then, as the VS Code extension does, so a panel unfolding
    // above the list moves the list whole and the row doesn't slide over it
    property Item listTop: null
    onRowKeyChanged: {
        stateLabel.widest = stateLabel.implicitWidth
        Qt.callLater(row.placed)
    }
    onYChanged: {
        laidOut = true
        Qt.callLater(row.placed)
    }
    onHeightChanged: Qt.callLater(row.placed)
    Timer {
        interval: 60
        running: true
        onTriggered: {
            row.laidOut = true
            row.placed()
        }
    }
    function placed() {
        if (!root.rowSpace || row.session.key === "" || !row.visible || !row.laidOut)
            return
        const y = listTop ? row.y - listTop.y : row.mapToItem(root.rowSpace, 0, 0).y
        const was = root.rowSpots[row.rowKey]
        root.rowSpots[row.rowKey] = y
        if (!root.animateRows)
            return
        if (was === undefined) {
            if (root.rowsPlaced) {
                slideIn.stop()
                appear.restart()
            }
            return
        }
        if (Math.abs(was - y) < 1)
            return
        appear.complete()
        slide.y = was - y
        slideIn.restart()
    }
    NumberAnimation {
        id: slideIn
        target: slide
        property: "y"
        to: 0
        duration: Kirigami.Units.longDuration * 1.5
        easing.type: Easing.OutCubic
    }
    ParallelAnimation {
        id: appear
        NumberAnimation { target: row; property: "opacity"; from: 0; to: 1; duration: Kirigami.Units.longDuration * 2; easing.type: Easing.OutQuad }
        NumberAnimation { target: slide; property: "x"; from: -Kirigami.Units.gridUnit; to: 0; duration: Kirigami.Units.longDuration * 2; easing.type: Easing.OutCubic }
    }
    readonly property bool confirmingStop: session.key !== "" && root.stopConfirmSession === rowKey
    // (a question gone with the chat it was about, stopped meanwhile, leaves no buttons up)
    // (and while the keyboard is on its name or a button, or a finger held it: HoverButtons)
    readonly property bool buttonsShown: rowHover.hovered || nameLabel.activeFocus || rowButtons.focused || rowButtons.held
                                         || (confirmingStop && canStop)
                                         || (session.key !== "" && root.deleteAsk.key === rowKey)
    // A finished chat can be shared, continued on another account or kept on
    // one (jump.py; on an SSH host, between its accounts: remote.py); not
    // while a session has it open.
    readonly property bool canShare: session.pid === null && session.state === "done" && !!session.chatId
                                     && root.shareAccountsOf(remoteHost).length >= 2
    readonly property bool confirmingKeepOnly: session.key !== "" && root.shareConfirm.key === rowKey
    // The color of this chat's pet (the strip at the bottom), if it has one
    readonly property string petColor: root.petColors[root.petKeyOf(session, remoteHost)] || ""
    readonly property bool showAgents: root.expandedAgents[rowKey] === true
    readonly property var agents: session.agents || null
    // A peek at the chat (talpy_den.py: chat_peek), its task list and the
    // files it changed
    readonly property var peek: session.peek || null
    readonly property var tasks: session.tasks || null
    readonly property var changes: session.changes || null
    readonly property bool showPeek: root.expandedPeek[rowKey] === true
    readonly property var recap: session.stats || null
    // Claude's own recap of the chat (talpy_den.py: recap_of), while nothing was said after it
    readonly property var summary: peek && peek.recap ? peek.recap : null
    // What stopped it: a usage limit (and when that resets) or an expired login
    readonly property var stopped: session.stopped || null
    readonly property bool hasPeek: (!!peek && (peek.prompt !== "" || peek.reply !== "")) || tasks !== null || recap !== null
                                    || summary !== null
    // Its changes open side by side in VS Code (jump.py --changes); an SSH host's files are there
    readonly property bool canCompare: changes !== null && !remoteHost && root.vscodeInstalled && !!session.chatId
    // The line under the folder: what it's doing, what it needs, what stopped
    // it, Claude's recap, or what Claude said last
    readonly property bool resting: session.state === "idle" || (session.state === "done" && !session.detail)
    readonly property bool showsRecap: resting && !stopped && summary !== null
    readonly property bool showsReply: resting && !stopped && !showsRecap && !!peek && peek.replyLine !== ""
    readonly property string doing: session.state === "working" ? root.doingText(session, remoteHost) : ""
    readonly property string stepText: session.state === "working"
                                       ? (doing ? doing : tasks && tasks.current ? tasks.current : "")
                                       : session.state === "waiting" ? (session.detail || (peek ? peek.activity : ""))
                                       : stopped ? root.stopText(stopped)
                                       : session.state === "done" && session.detail ? session.detail
                                       : showsRecap ? summary.text.split("\n")[0]
                                       : showsReply ? peek.replyLine : ""
    // Its permission mode, unless it's the default
    readonly property string modeText: root.modeText(peek ? peek.mode : null)
    // A usage limit stopped it: it can go on on another account with room left
    readonly property var handover: root.handoverTarget(session, remoteHost)
    // or by itself once the limit resets (queued), when the widget knows when
    readonly property real goOnAt: root.goOnAt(session)
    readonly property var goingOn: goOnAt || stopped ? root.queuedChat(session.chatId, remoteHost) : null
    // it keeps going until it's done: after each usage limit, it goes on by itself (root.keptChat)
    readonly property var kept: remoteHost ? null : root.keptChat(session.chatId || session.sessionId)
    readonly property string openHint: remoteHost
                                       ? (session.entrypoint === "claude-vscode" && !session.openCommand
                                          ? i18n("Show this conversation in VS Code (connected to %1)", remoteHost)
                                          : !session.openCommand ? i18n("Switch to the terminal with the ssh connection to %1", remoteHost)
                                          : session.kind === "chat" ? i18n("Reopen this chat on %1 in a terminal (ssh)", remoteHost)
                                          : i18n("Open this background chat on %1 in a terminal (ssh)", remoteHost))
                                       : session.entrypoint === "claude-vscode" ? i18n("Open this conversation in VS Code")
                                       : session.kind === "chat" ? i18n("Reopen this chat in a terminal (claude --resume)")
                                       : session.kind === "bg" && session.pid === null ? i18n("Reopen this background chat in a terminal")
                                       : session.kind === "bg" ? i18n("Show this background chat in a terminal")
                                       : i18n("Switch to the terminal running this chat")

    // Stop (the question's answer): only stopped if it's as the question
    // says now (busy: working or waiting; an idle one that got busy isn't);
    // keepOff: Keep going off for it too (jump.py --and-keep-off)
    function stop(keepOff) {
        root.stopConfirmSession = ""
        const busy = session.state !== "idle"
        if (remoteHost && canEnd)
            root.remoteEnd(remoteHost, session.sessionId, session.profileDir, busy)
        else if (remoteHost)
            root.remoteStop(remoteHost, session.stopCommand)
        else
            root.stopSession(session.sessionId, session.profileDir, busy, keepOff && kept ? kept.chat : "")
    }

    function open() {
        if (remoteHost)
            root.remoteShow(remoteHost, session)
        else
            root.jumpTo(session.sessionId, session.profileDir)
    }

    // The first other chat that changes the same files
    function openOverlap() {
        const o = (session.overlaps || [])[0]
        const other = o ? root.listedRow(o.sessionId, o.profileDir, remoteHost) : null
        if (other && remoteHost)
            root.remoteShow(remoteHost, other)
        else if (other)
            root.jumpTo(other.sessionId, other.profileDir)
    }

    spacing: Kirigami.Units.smallSpacing
    Layout.leftMargin: Kirigami.Units.smallSpacing

    // A message in the unfolded peek: who, in a column of its own, and what
    // they said beside it
    component PeekMessage: RowLayout {
        property alias who: whoLabel.text
        property alias text: saidLabel.text
        property alias lines: saidLabel.maximumLineCount
        property real whoWidth: 0
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing * 1.5

        PlasmaComponents3.Label {
            id: whoLabel
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: whoWidth
            textFormat: Text.PlainText
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            font.weight: Font.DemiBold
            opacity: 0.6
        }
        PlasmaComponents3.Label {
            id: saidLabel
            Layout.fillWidth: true
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
        }
    }
    // A link in it (Compare changes, Last turn)
    component PeekLink: PlasmaComponents3.Label {
        id: peekLink
        property string tipTitle
        property string tip
        signal clicked()
        textFormat: Text.PlainText
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        font.underline: enabled && linkMouse.containsMouse
        color: enabled ? Kirigami.Theme.linkColor : Kirigami.Theme.disabledTextColor

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: peekLink.tipTitle
            subText: peekLink.tip

            MouseArea {
                id: linkMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: peekLink.clicked()
            }
        }
    }


    HoverHandler {
        id: rowHover
    }
    TouchHold {
        buttons: rowButtons
    }
    Layout.rightMargin: Kirigami.Units.smallSpacing

    // A bar in the color of the chat's pet, to spot which pet is which
    Rectangle {
        Layout.fillHeight: true
        Layout.preferredWidth: 6
        radius: 3
        color: row.petColor || "transparent"
    }

    Rectangle {
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: Math.round((nameLabel.implicitHeight - height) / 2)
        Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 0.6)
        Layout.preferredHeight: Layout.preferredWidth
        radius: width / 2
        color: row.session.reason === "failed" || (row.stopped && !row.stopped.over) ? Kirigami.Theme.negativeTextColor
             : root.stateColor(row.session.state)
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            // The name, then its tags: beside it while the whole name and all
            // of them fit there, else under it (on more lines if need be), so
            // the tags never cut the name short (as in the VS Code extension)
            // (the hover buttons reaching past its state: its name and tags are
            // cut where they begin, in place, nothing drawn over them)
            Item {
                id: nameBox
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: nameLine.implicitHeight

                Item {
                    width: Math.max(0, nameBox.width - rowButtons.beyond)
                    height: nameBox.height
                    clip: true

                    Flow {
                        id: nameLine
                        width: nameBox.width
                        readonly property bool tagsBeside: nameLabel.implicitWidth + Kirigami.Units.smallSpacing + tagLine.extent.width <= width

                        PlasmaComponents3.Label {
                            id: nameLabel
                            textFormat: Text.PlainText
                            text: row.session.name
                            font.bold: true
                            font.underline: nameMouse.containsMouse || activeFocus
                            elide: Text.ElideRight
                            width: Math.min(implicitWidth, nameLine.width)
                            // (Tab: its buttons show; Enter: as a click)
                            activeFocusOnTab: true
                            Keys.onReturnPressed: root.clickChat(row.session, row.remoteHost)
                            Keys.onEnterPressed: root.clickChat(row.session, row.remoteHost)

                            // Click the name to jump to the session
                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                width: nameLabel.contentWidth
                                height: parent.height
                                mainText: Plasmoid.configuration.clickOpensPane
                                          ? i18n("Open this chat beside the popup: its conversation, a box to reply, and what it changed")
                                          : row.openHint

                                MouseArea {
                                    id: nameMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: if (!rowButtons.holding) root.clickChat(row.session, row.remoteHost)

                                    TouchHold {
                                        buttons: rowButtons
                                    }
                                }
                            }
                        }
                        Flow {
                            id: tagLine
                            // its shown tags in one line (a pixel spare, so they don't wrap
                            // on a rounding), and their height
                            readonly property var extent: {
                                let w = -spacing, h = 0
                                for (const t of children)
                                    if (t.visible) {
                                        w += t.implicitWidth + spacing
                                        h = Math.max(h, t.implicitHeight)
                                    }
                                return { width: w > 0 ? Math.ceil(w) + 1 : 0, height: h }
                            }
                            // (no tags: no width, so the name's line leaves it out)
                            width: !nameLine.tagsBeside ? nameLine.width : extent.width > 0 ? leftPadding + extent.width : 0
                            leftPadding: nameLine.tagsBeside ? Kirigami.Units.smallSpacing : 0
                            topPadding: nameLine.tagsBeside ? Math.max(0, Math.round((nameLabel.implicitHeight - extent.height) / 2))
                                                            : Math.round(Kirigami.Units.smallSpacing / 2)
                            spacing: Kirigami.Units.smallSpacing

                            // starred: a ★ (click: unstar it)
                            StarMark {
                                visible: !!row.session.starred
                                tooltip: i18n("Once it isn't listed here any more, it stays under ★ Starred chats. Click to unstar it.")
                                onClicked: root.setStar("chats", row.session.chatId || row.session.sessionId, row.remoteHost, false)
                            }
                            Tag {
                                visible: row.showProfile
                                text: row.session.profile
                                tooltip: i18n("The Claude profile (config folder) this chat runs in")
                            }
                            Tag {
                                visible: row.tag !== ""
                                text: row.tag
                                tooltip: row.session.pid === null ? i18n("No terminal or panel has it open: a reply goes on with it in the background.")
                                         : row.session.kind === "bg"
                                         ? i18n("A background chat: Claude's background service runs it, with no terminal of its own. Click the name to open it in a terminal (claude attach).")
                                         : row.session.entrypoint === "claude-vscode"
                                         ? i18n("Runs in VS Code's Claude Code panel. Click the name to open the conversation there.")
                                         : row.session.tmux ? i18n("It runs in a tmux pane.")
                                         : row.session.vscodeTerminal || row.session.terminalApp === "VS Code" ? i18n("It runs in a terminal of VS Code.")
                                         : row.session.terminalApp ? i18n("It runs in a terminal (%1).", row.session.terminalApp)
                                         : i18n("It runs in a terminal.")
                            }
                            // a background session shown in a terminal too (claude attach)
                            Tag {
                                readonly property var shownIn: row.session.kind === "bg" && row.session.attached ? row.session.attached : null
                                visible: shownIn !== null
                                text: !shownIn ? "" : shownIn.in === "tmux" ? "Tmux"
                                      : shownIn.in === "vscode" ? i18nc("where a chat runs", "VS Code terminal") : i18nc("where a chat runs", "Terminal")
                                tooltip: !shownIn ? "" : shownIn.app ? i18n("Shown in a terminal too (%1): claude attach.", shownIn.app)
                                                                     : i18n("Shown in a terminal too: claude attach.")
                            }
                            Tag {
                                // Chat shared across profiles (hard-linked transcript)
                                readonly property var info: row.session.shared
                                visible: !!info
                                icon: Icons.plasma.share
                                text: info && info.forkOf ? i18n("Shared copy") : i18n("Shared")
                                tooltipTitle: info && info.forkOf ? i18n("Copy of a shared chat") : i18n("Shared chat")
                                tooltip: !info ? ""
                                         : info.forkOf
                                           ? i18n("A copy of a chat shared between the %1 profiles: Claude forked it into a chat of its own on %2, so new messages here are only on %2.",
                                                  info.profiles.join(" + "), info.forkOn)
                                             + (info.movedHere ? "\n" + i18n("The shared chat continued here, so it isn't listed itself.") : "")
                                             + (info.stoppedCopies ? "\n" + i18n("Its background chat on %1 was stopped; %1 shows a link to this copy.", info.stoppedCopies.join(", ")) : "")
                                           : i18n("This chat is shared between the %1 profiles: it continues on whichever account you open it with. Only one Claude can have it open at a time.",
                                                  info.profiles.join(" + "))
                                             + (row.session.kind === "chat" ? "\n" + i18n("Listed here because it was used on %1 last.", row.session.profile) : "")
                                             + (info.openIn ? "\n" + i18n("Open in %1 right now.", info.openIn) : "")
                                             + (info.stoppedCopies ? "\n" + i18n("Its background chat on %1 was stopped; %1 shows a link to this chat.", info.stoppedCopies.join(", ")) : "")
                            }
                            Tag {
                                visible: row.agents !== null
                                text: row.agents ? i18nc("subagents finished/total", "Agents %1/%2", row.agents.done, row.agents.total) : ""
                                active: row.agents !== null && row.agents.running > 0
                                clickable: true
                                onClicked: root.toggleAgents(row.rowKey)
                                tooltipTitle: i18n("Subagents")
                                tooltip: !row.agents ? ""
                                         : i18n("%1 done, %2 running, %3 stopped", row.agents.done, row.agents.running, row.agents.stopped)
                                           + (row.agents.failed ? i18n(", %1 failed", row.agents.failed) : "") + ". "
                                           + i18n("Click to %1 what each one is doing.", row.showAgents ? i18n("hide") : i18n("show"))
                            }
                            Tag {
                                // another chat with a process changed some of the same files (talpy_den.py: note_overlaps)
                                visible: !!row.session.overlaps && row.session.overlaps.length > 0
                                icon: Icons.plasma.warning
                                text: i18nc("two chats changed the same files", "Same files")
                                warning: true
                                clickable: true
                                onClicked: row.openOverlap()
                                tooltipTitle: i18n("Another chat changes the same files")
                                tooltip: row.session.overlaps ? root.overlapText(row.session.overlaps) + "\n\n"
                                         + i18n("Two chats changing the same files can overwrite each other's work. Click to go to the other chat.") : ""
                            }
                            Tag {
                                // plan mode, auto mode, …: how freely it may act
                                visible: row.modeText !== ""
                                text: row.modeText
                                warning: !!row.peek && row.peek.mode === "bypassPermissions"
                                tooltipTitle: i18n("Permission mode: %1", row.modeText)
                                tooltip: root.modeHint(row.peek ? row.peek.mode : "")
                            }
                            Tag {
                                // the plan it made (talpy_den.py: plan_of)
                                visible: !!row.session.plan
                                icon: Icons.plasma.plan
                                text: i18nc("a chat's plan, click to open it", "Plan")
                                clickable: true
                                onClicked: root.openPlan(row.session.plan.slug, row.session.profileDir, row.remoteHost)
                                tooltipTitle: row.session.plan ? row.session.plan.title : ""
                                tooltip: row.remoteHost ? i18n("The plan this chat made. Click to read it: a copy, fetched from %1.", row.remoteHost)
                                                        : i18n("The plan this chat made. Click to read it, rendered.")
                            }
                            Tag {
                                // its file itself, to change it (an SSH host's: in VS Code, over Remote-SSH)
                                visible: !!row.session.plan && (!row.remoteHost || root.vscodeInstalled)
                                icon: Icons.plasma.edit
                                text: ""
                                clickable: true
                                onClicked: root.editPlan({ slug: row.session.plan.slug, path: row.session.plan.path,
                                                           profileDir: row.session.profileDir }, row.remoteHost)
                                tooltipTitle: i18n("Edit the plan")
                                tooltip: (row.remoteHost
                                          ? i18n("Opens its Markdown file on %1 in VS Code (Remote - SSH). What you change there is the plan.", row.remoteHost)
                                          : i18n("Opens its Markdown file in your text editor (VS Code, if the settings open plans there). What you change there is the plan."))
                                         + (row.remoteHost ? "" : " " + i18n("Then send your changes to this chat (Send to Claude): Claude revises the plan."))
                            }
                            Tag {
                                // you changed its plan since the chat last did anything (talpy_den.py: plan_edited)
                                visible: !!row.session.plan && !!row.session.plan.edited && !row.remoteHost && !!row.session.chatId
                                icon: Icons.plasma.send
                                text: i18nc("send your changes to the plan to the chat", "Send to Claude")
                                active: true
                                clickable: true
                                onClicked: root.sendPlanFeedback(row.session.plan.slug, row.session.profileDir, row.session.chatId)
                                tooltipTitle: i18n("Send your changes to Claude")
                                tooltip: i18n("You changed this plan since Claude wrote it. Click to send what you changed (and notes you wrote into it) to this chat: Claude revises the plan, in plan mode.")
                                         + "\n\n" + i18n("In tmux it's typed in for you. Else it goes to the clipboard and the chat comes up: paste it there (if Claude asks whether to go ahead with the plan, choose to keep planning first). A chat that isn't open reopens in plan mode with it.")
                            }
                            Tag {
                                visible: row.changes !== null
                                text: row.changes ? i18nc("number of files a chat changed", "±%1", row.changes.count) : ""
                                clickable: row.canCompare
                                onClicked: root.showChanges(row.session.chatId, row.session.profileDir, false)
                                tooltipTitle: row.changes ? i18np("%1 file changed", "%1 files changed", row.changes.count) : ""
                                tooltip: !row.changes ? ""
                                         : row.changes.files.join("\n")
                                           + (row.changes.count > row.changes.files.length ? "\n" + i18n("…and %1 more", row.changes.count - row.changes.files.length) : "")
                                           + "\n\n" + (row.remoteHost ? i18n("The files are on %1.", row.remoteHost)
                                                      : !root.vscodeInstalled ? i18n("Install VS Code to compare them side by side.")
                                                      : i18n("Click to compare them in VS Code: what they were before the chat, and now."))
                            }
                            Tag {
                                // it changed files and is done: to review until you mark it reviewed (ChatPane.qml)
                                visible: root.reviewPending(row.session, row.remoteHost)
                                text: i18nc("a finished chat's changes, not reviewed yet", "To review")
                                active: true
                                clickable: true
                                onClicked: root.openPane(row.session, row.remoteHost, "review")
                                tooltipTitle: i18n("Not reviewed yet")
                                tooltip: i18n("It changed files and its turn is over. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed.")
                            }
                            TestsBadge {
                                review: root.reviewPending(row.session, row.remoteHost) ? row.session.review : null
                            }
                        }
                    }
                }
            }
            // Its state, at the line's end; the hover buttons cover its end
            // (it stays where it is, as in the VS Code extension)
            CoveredEnd {
                id: stateBox
                covered: rowButtons.covering
                Layout.preferredWidth: Math.max(stateLabel.implicitWidth, stateLabel.widest)
                Layout.maximumWidth: Kirigami.Units.gridUnit * 11
                Layout.alignment: Qt.AlignTop
                implicitHeight: stateLabel.implicitHeight

                PlasmaComponents3.Label {
                    id: stateLabel
                    // (as wide as it was at its widest for this chat: "Working · 12m"
                    // turning "Idle · 0m", or the next minute, doesn't move its tags)
                    property real widest: 0
                    width: stateBox.width
                    horizontalAlignment: Text.AlignRight   // (at the line's end, however wide it was)
                    // (the hover buttons over its end: what's left of it shows, unless that's a sliver)
                    opacity: row.buttonsShown && implicitWidth - rowButtons.covering < Kirigami.Units.gridUnit * 2 ? 0 : 1
                    textFormat: Text.PlainText
                    text: root.stateText(row.session)
                    color: row.session.state === "waiting" ? Kirigami.Theme.neutralTextColor
                         : row.stopped && !row.stopped.over ? Kirigami.Theme.negativeTextColor
                         : row.stopped ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.textColor
                    font.bold: row.session.state === "waiting" || !!row.stopped
                    elide: Text.ElideRight
                    onImplicitWidthChanged: widest = Math.max(widest, implicitWidth)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        active: !!row.stopped && !row.stopped.over && row.stopped.resetsAt > root.now
                        mainText: active ? root.resetAtText(row.stopped.resetsAt) : ""
                    }
                }
            }
            // The buttons it shows on hover (and while it asks whether to
            // stop), over the line's right end, where its state is, as in the
            // VS Code extension
            HoverButtons {
                id: rowButtons
                lineHeight: nameLabel.implicitHeight
                shown: row.buttonsShown
                under: stateBox

                RowLayout {   // (made the first time they show)
                    spacing: 0

                    PlasmaComponents3.ToolButton {
                        // the other way to open it than a click on its name: its window, or the pane
                        icon.name: Plasmoid.configuration.clickOpensPane ? Icons.plasma.openWindow : Icons.plasma.openPane
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: Plasmoid.configuration.clickOpensPane ? i18n("Open its window") : i18n("Open in the chat pane")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: Plasmoid.configuration.clickOpensPane ? row.open() : root.openPane(row.session, row.remoteHost, "chat")

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: Plasmoid.configuration.clickOpensPane ? row.openHint : i18n("Open in the chat pane")
                            subText: Plasmoid.configuration.clickOpensPane ? ""
                                     : i18n("Beside the popup: its conversation, a box to reply, and what it changed.")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        // star it: once it isn't listed here any more, it stays under ★ Starred chats
                        // (a starred one has its ★ after its name)
                        visible: !!(row.session.chatId || row.session.sessionId) && !row.session.starred
                        icon.name: Icons.plasma.star
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Star")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.setStar("chats", row.session.chatId || row.session.sessionId, row.remoteHost, true)

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Star this chat")
                            subText: i18n("Once it isn't listed here any more, a starred chat stays under ★ Starred chats, however old it is.")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        // keep going until it's done: on by itself after each usage limit
                        visible: row.kept === null && root.canKeepGoing(row.session, row.remoteHost)
                        icon.name: Icons.plasma.keepGoing
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Keep going after usage limits")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.keepGoing(row.session, true)

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Keep going until it's done")
                            subText: i18n("When a usage limit stops this chat, it goes on by itself in the background a minute after the limit resets, in the permission mode it had, and again after each later one, until a turn of it ends by itself. Claude here quits first then (its terminal stays open); open the chat from here to see it.")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        id: shareButton
                        visible: row.canShare
                        icon.name: Icons.plasma.share
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Share or continue on another account…")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.openShareMenu(shareButton, {
                            chatId: row.session.chatId, name: row.session.name, profileDir: row.session.profileDir,
                            shared: !!row.session.shared && !row.session.shared.forkOf, host: row.remoteHost
                        }, row.rowKey)

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Continue on another account")
                            subText: root.shareHint(row.remoteHost)
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        // Delete a finished chat: to the Trash, after a question (DeleteAsk under the row)
                        visible: row.session.state === "done" && !!(row.session.chatId || row.session.sessionId)
                        icon.name: Icons.plasma.delete
                        icon.color: Icons.color("delete", Kirigami.Theme)
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Delete…")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.askDelete(row.rowKey, "chat", row.session.chatId || row.session.sessionId,
                                                  row.session.profileDir, row.remoteHost, "")

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Delete this chat…")
                            subText: root.deleteHint("chat")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        // Hide a finished chat here (nothing is deleted)
                        visible: row.session.state === "done"
                        icon.name: Icons.plasma.hide
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: i18n("Hide this chat")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.hideItem("chats", row.session.sessionId, row.remoteHost)

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Hide this chat")
                            subText: root.hideHint("chats", row.remoteHost)
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        visible: row.canStop
                        icon.name: Icons.plasma.stop
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: row.canInterrupt ? i18n("Interrupt or stop…") : i18n("Stop…")
                        Layout.preferredHeight: rowButtons.buttonSize
                        icon.width: Kirigami.Units.iconSizes.small
                        icon.height: Kirigami.Units.iconSizes.small
                        Layout.preferredWidth: rowButtons.buttonWidth
                        Layout.alignment: Qt.AlignTop
                        onClicked: root.stopConfirmSession = row.confirmingStop ? "" : row.rowKey

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: row.stopTitle
                            subText: row.stopTip
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                id: folderLabel
                textFormat: Text.PlainText
                text: row.session.cwdShort
                opacity: 0.7
                font: Kirigami.Theme.smallFont
                elide: Text.ElideMiddle
                Layout.fillWidth: true

                PlasmaCore.ToolTipArea {   // (the whole folder: the line may be cut short)
                    textFormat: Text.PlainText
                    width: folderLabel.contentWidth
                    height: parent.height
                    active: !!row.session.cwd
                    mainText: i18n("Folder")
                    subText: (row.remoteHost ? row.remoteHost + ":" : "") + row.session.cwd
                }
            }
            PlasmaComponents3.Label {
                readonly property bool ultracode: !!row.peek && row.peek.ultracode === true
                textFormat: Text.PlainText
                visible: !!row.session.model || ultracode
                // the model, how hard it thinks (Claude's /effort) and whether ultracode is on
                text: [row.session.model || "", row.session.effort || "", ultracode ? i18n("ultracode") : ""].filter(t => t).join(" · ")
                opacity: 0.7
                font: Kirigami.Theme.smallFont

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    active: !!row.session.effort || parent.ultracode
                    mainText: row.session.model || ""
                    subText: [row.session.effort ? i18n("Effort: %1 (how hard it thinks; /effort changes it)", row.session.effort) : "",
                              parent.ultracode ? i18n("Ultracode: Claude runs workflows of agents for every substantial task (/ultracode off turns it off)") : ""]
                             .filter(t => t).join("\n")
                }
            }
            // Context window fill
            Rectangle {
                visible: row.session.context !== null
                Layout.preferredWidth: Kirigami.Units.gridUnit * 2.5
                Layout.preferredHeight: Math.round(Kirigami.Units.gridUnit * 0.3)
                radius: height / 2
                color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

                Rectangle {
                    width: parent.width * Math.min(100, Math.max(0, row.session.context || 0)) / 100
                    height: parent.height
                    radius: parent.radius
                    color: root.usageColor(row.session.context || 0)
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                visible: row.session.context !== null
                text: i18nc("context window fill", "ctx %1%", Math.round(row.session.context || 0))
                opacity: 0.7
                font: Kirigami.Theme.smallFont
            }
        }

        // What it's doing now, what it needs, or what Claude said last, with
        // its task progress; click to read your last prompt and Claude's reply
        Item {
            Layout.fillWidth: true
            visible: row.stepText !== "" || row.tasks !== null
            implicitHeight: stepRow.implicitHeight

            // Under the line, so its buttons get their own clicks and tooltips
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: stepLabel.truncated || row.hasPeek
                mainText: row.session.state === "waiting" ? i18n("What it needs")
                          : row.session.state === "working" ? i18n("What it's doing")
                          : row.stopped ? (row.stopped.kind === "login" ? i18n("Its login expired") : i18n("A usage limit stopped it"))
                          : row.showsRecap ? i18n("Claude's recap")
                          : row.showsReply ? i18n("What Claude said last") : i18n("Result")
                subText: (stepLabel.truncated ? row.stepText + (row.hasPeek ? "\n\n" : "") : "")
                         + (!row.hasPeek ? "" : row.showPeek ? i18n("Click to fold it up again.")
                                                             : i18n("Click to read your last prompt, Claude's reply and the chat's tasks."))

                MouseArea {
                    id: stepMouse
                    anchors.fill: parent
                    enabled: row.hasPeek
                    hoverEnabled: true
                    cursorShape: row.hasPeek ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: root.togglePeek(row.rowKey)
                }
            }

            RowLayout {
                id: stepRow
                anchors.fill: parent
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    visible: row.tasks !== null
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 2.5
                    Layout.preferredHeight: Math.round(Kirigami.Units.gridUnit * 0.3)
                    radius: height / 2
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

                    Rectangle {
                        width: parent.width * (row.tasks ? row.tasks.done / Math.max(1, row.tasks.total) : 0)
                        height: parent.height
                        radius: parent.radius
                        color: Kirigami.Theme.positiveTextColor
                    }
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    visible: row.tasks !== null
                    text: row.tasks ? i18nc("tasks done/total", "%1/%2", row.tasks.done, row.tasks.total) : ""
                    opacity: 0.7
                    font: Kirigami.Theme.smallFont
                }
                PlasmaComponents3.Label {
                    id: stepLabel
                    Layout.fillWidth: true
                    text: (row.session.state === "working" && row.stepText ? "▸ "
                           : row.showsRecap ? i18nc("Claude's recap of the chat", "Recap: ")
                           : row.showsReply ? i18nc("what Claude said last", "Claude: ") : "") + row.stepText
                    textFormat: Text.PlainText
                    // (what it's doing in the working color, as in the VS Code extension)
                    readonly property bool doing: row.session.state === "working" && row.stepText !== ""
                    color: doing ? root.stateColor("working")
                         : row.session.state === "waiting" ? Kirigami.Theme.neutralTextColor
                         : row.stopped && !row.stopped.over && row.session.state !== "working" ? Kirigami.Theme.negativeTextColor
                         : Kirigami.Theme.textColor
                    elide: Text.ElideRight
                    opacity: doing ? 1 : 0.8
                    font: Kirigami.Theme.smallFont
                }
                // A usage limit stopped it: continue on another account with room left
                PlasmaComponents3.ToolButton {
                    id: handoverButton
                    visible: row.handover !== null
                    icon.name: Icons.plasma.continueOn
                    text: row.handover ? i18n("Continue on %1", row.handover.title) : ""
                    font: Kirigami.Theme.smallFont
                    Layout.preferredHeight: stepLabel.implicitHeight + Kirigami.Units.smallSpacing
                    onClicked: root.handOver(row.session, row.remoteHost, row.handover)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: row.handover ? i18n("Continue on %1", row.handover.title) : ""
                        subText: !row.handover ? ""
                                 : (row.handover.pct !== null
                                    ? i18n("%1 has used %2% of its %3 limit.", row.handover.title, Math.round(row.handover.pct), row.handover.label)
                                    : i18n("%1's plan usage isn't known here.", row.handover.title))
                                   + " " + (row.session.pid !== null
                                            ? (row.session.kind === "bg"
                                               ? i18n("This background chat is stopped first (claude stop); then the chat is shared with %1 and reopens there in a terminal.", row.handover.title)
                                               : i18n("Claude here quits first (its terminal stays open); then the chat is shared with %1 and reopens there in a terminal.", row.handover.title))
                                            : i18n("The chat is shared with %1 and reopens there in a terminal.", row.handover.title))
                    }
                }
                // or go on by itself once the limit resets (queued; again: cancelled)
                PlasmaComponents3.ToolButton {
                    visible: row.goOnAt > 0 || row.goingOn !== null
                    icon.name: Icons.plasma.goOnAt
                    // (it goes on then: framed, as a toggle that's on, as VS Code's: a thin
                    // border and a faint tint of the text's color, no fill of its own; a click cancels it)
                    Rectangle {
                        visible: row.goingOn !== null
                        anchors.fill: parent
                        z: -0.5
                        radius: Kirigami.Units.cornerRadius
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)
                        border.width: 1
                        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)
                    }
                    text: row.goingOn ? i18n("Goes on at %1", root.startText(row.goingOn.startAt))
                                      : i18n("Go on at %1", root.startText(row.goOnAt))
                    font: Kirigami.Theme.smallFont
                    Layout.preferredHeight: stepLabel.implicitHeight + Kirigami.Units.smallSpacing
                    onClicked: {
                        if (row.goingOn)
                            root.unqueue(row.goingOn)
                        else
                            root.queueContinue(row.session, row.remoteHost, row.account, false)
                    }

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: row.goingOn ? i18n("Goes on by itself at %1", root.startText(row.goingOn.startAt))
                                              : i18n("Go on once the limit resets")
                        subText: (row.goingOn ? "" : i18n("At %1, a minute after the limit resets, the chat goes on in the background, telling Claude that the limit has reset.", root.startText(row.goOnAt)) + " ")
                                 + (row.session.pid === null || row.session.pid === undefined ? ""
                                    : row.session.kind === "bg" ? i18n("This background chat is stopped first (claude stop).")
                                    : i18n("Claude here quits first (its terminal stays open); open the chat from here to see it.")) + " "
                                 + i18n("It goes on in the permission mode it had.") + " "
                                 + i18n("If it went on before then, nothing happens.")
                                 + (row.goingOn ? "" : " " + (row.remoteHost ? i18n("This happens once.")
                                                              : i18n("This happens once: to have it go on after later limits too, choose Keep going.")))
                                 + (row.goingOn ? "\n\n" + (row.kept ? i18n("Click to cancel it: then it doesn't keep going either.")
                                                                     : i18n("Click to cancel it.")) : "")
                    }
                }
                // or go on then, and after each later limit too, until it's done
                PlasmaComponents3.ToolButton {
                    visible: row.goOnAt > 0 && row.goingOn === null && row.kept === null && !row.remoteHost
                    icon.name: Icons.plasma.keepGoing
                    text: i18n("Keep going")
                    font: Kirigami.Theme.smallFont
                    Layout.preferredHeight: stepLabel.implicitHeight + Kirigami.Units.smallSpacing
                    onClicked: root.queueContinue(row.session, row.remoteHost, row.account, true)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Keep going until it's done")
                        subText: i18n("At %1, a minute after the limit resets, the chat goes on in the background, in the permission mode it had, and again after each later limit that stops it, until a turn of it ends by itself.", root.startText(row.goOnAt))
                                 + " " + (row.session.pid === null || row.session.pid === undefined ? ""
                                          : row.session.kind === "bg" ? i18n("This background chat is stopped first (claude stop).")
                                          : i18n("Claude here quits first (its terminal stays open); open the chat from here to see it."))
                    }
                }
                // it keeps going: after each usage limit, on by itself (click: not any more)
                Tag {
                    visible: row.kept !== null
                    icon: Icons.plasma.keepGoing
                    text: i18nc("a chat that goes on by itself after usage limits", "Keeps going")
                    active: row.kept !== null && !row.kept.error
                    warning: row.kept !== null && (!!row.kept.error || !!row.kept.note)
                    clickable: true
                    tooltipTitle: i18n("Keeps going until it's done")
                    tooltip: row.kept ? root.keptText(row.kept) : ""
                    onClicked: root.keepGoing(row.session, false)
                }
                Kirigami.Icon {
                    visible: row.hasPeek
                    source: row.showPeek ? Icons.plasma.peekOpen : Icons.plasma.peekClosed
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Layout.preferredWidth
                    opacity: stepMouse.containsMouse ? 0.9 : 0.4
                }
            }
        }

        // What it asks while it waits for a permission: Allow once, Always allow, Deny; or its questions
        PermissionAsk {
            visible: row.session.state === "waiting" && !!row.session.permission
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            permission: visible ? row.session.permission : null
            diffLines: 6
            compact: true
            onAnswered: (decision, note, answers) => root.answerPermission(row.session, row.remoteHost, decision, note, answers)
            onWholePlan: root.openPane(row.session, row.remoteHost, "chat")
        }

        // Your last prompt, Claude's reply since, the chat's tasks, what it
        // changed and its numbers, as the VS Code extension shows them
        Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing / 2
            visible: row.showPeek && row.hasPeek
            implicitHeight: peekColumn.implicitHeight + Kirigami.Units.smallSpacing * 2
            radius: Kirigami.Units.cornerRadius
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)

            // its left edge
            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 2
                radius: 1
                color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)
            }
            FontMetrics {
                id: whoFm
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.weight: Font.DemiBold
            }

            ColumnLayout {
                id: peekColumn
                // (who said it: a column as wide as the widest of them)
                readonly property real whoWidth: Math.ceil(Math.max(whoFm.advanceWidth(i18nc("Claude's recap of the chat", "Recap")),
                                                                    whoFm.advanceWidth(i18nc("your last prompt", "You")),
                                                                    whoFm.advanceWidth(i18nc("Claude's last reply", "Claude"))))
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                anchors.leftMargin: Kirigami.Units.smallSpacing + 3
                spacing: Kirigami.Units.smallSpacing

                // Claude's recap of the chat, written when you came back to it
                PeekMessage {
                    visible: row.summary !== null
                    who: i18nc("Claude's recap of the chat", "Recap")
                    whoWidth: peekColumn.whoWidth
                    text: row.summary ? row.summary.text : ""
                    lines: 8
                }
                PeekMessage {
                    visible: !!row.peek && row.peek.prompt !== ""
                    who: i18nc("your last prompt", "You")
                    whoWidth: peekColumn.whoWidth
                    text: row.peek ? row.peek.prompt : ""
                    lines: 3
                }
                PeekMessage {
                    visible: !!row.peek && row.peek.reply !== ""
                    who: i18nc("Claude's last reply", "Claude")
                    whoWidth: peekColumn.whoWidth
                    text: row.peek ? row.peek.reply : ""
                    lines: 14
                }

                // The chat's tasks: ✓ done, ▸ the one it's on, ○ still to do
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: row.tasks !== null
                    spacing: 0

                    Repeater {
                        model: row.tasks ? row.tasks.items.length : 0
                        delegate: PlasmaComponents3.Label {
                            required property int index
                            readonly property var task: (row.tasks && row.tasks.items[index]) || root.emptyTask
                            Layout.fillWidth: true
                            text: (task.status === "completed" ? "✓ " : task.status === "in_progress" ? "▸ " : "○ ") + task.subject
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            opacity: task.status === "completed" ? 0.6 : 0.9
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            font.bold: task.status === "in_progress"
                        }
                    }
                }

                // What it changed, side by side in VS Code
                RowLayout {
                    visible: row.changes !== null && !row.remoteHost
                    spacing: Kirigami.Units.gridUnit * 0.75

                    PeekLink {
                        text: i18np("Compare changes (%1 file)", "Compare changes (%1 files)", row.changes ? row.changes.count : 0)
                        enabled: row.canCompare
                        tipTitle: i18n("Everything this chat changed")
                        tip: root.vscodeInstalled
                             ? i18n("Opens in VS Code side by side: each file as it was before the chat first changed it, and as it is now.")
                             : i18n("Needs VS Code.")
                        onClicked: root.showChanges(row.session.chatId, row.session.profileDir, false)
                    }
                    PeekLink {
                        text: i18n("Last turn")
                        enabled: row.canCompare
                        tipTitle: i18n("What its last turn changed")
                        tip: i18n("The files as they were when you sent your last prompt, and as they are now.")
                        onClicked: root.showChanges(row.session.chatId, row.session.profileDir, true)
                    }
                }

                // The chat in numbers
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: row.recap !== null
                    text: root.recapText(row.recap, row.session.costUsd)
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    font: Kirigami.Theme.smallFont

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        active: row.recap !== null
                        mainText: i18n("This chat in numbers")
                        subText: !row.recap ? ""
                                 : (row.recap.startedAt ? i18n("Started %1 ago, last active %2 ago.", root.duration(root.now - row.recap.startedAt),
                                                               root.duration(root.now - (row.recap.lastAt || root.now))) + "\n" : "")
                                   + i18n("Tokens: input %1 · output %2 · cache read %3 · cache write %4 (subagents included).",
                                          root.formatTokens(row.recap.tokens.input), root.formatTokens(row.recap.tokens.output),
                                          root.formatTokens(row.recap.tokens.cacheRead), root.formatTokens(row.recap.tokens.cacheWrite))
                                   + "\n" + i18n("Worked: how long Claude was at it, from each prompt of yours to its last step.")
                                   + (row.session.costUsd ? "\n" + i18n("The price is what this chat would cost through the API, from the status line.") : "")
                    }
                }
            }
        }

        // Subagents as a tree: what each one is doing
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing / 2
            visible: row.showAgents && row.agents !== null
            spacing: Kirigami.Units.smallSpacing / 2

            Repeater {
                model: row.agents ? row.agents.tree.length : 0
                delegate: RowLayout {
                    id: agentRow
                    required property int index
                    readonly property var modelData: (row.agents && row.agents.tree[index]) || root.emptyAgent
                    readonly property string runKey: row.rowKey + "|" + modelData.id
                    readonly property bool open: root.expandedAgentRuns[runKey] === true
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.gridUnit * 0.9 * modelData.depth
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.alignment: Qt.AlignTop
                        text: "└"
                        opacity: 0.4
                    }
                    Rectangle {
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: Math.round(Kirigami.Units.gridUnit * 0.3)
                        Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 0.45)
                        Layout.preferredHeight: Layout.preferredWidth
                        radius: width / 2
                        color: agentRow.modelData.status === "running" ? Kirigami.Theme.focusColor
                             : agentRow.modelData.status === "done" ? Kirigami.Theme.positiveTextColor
                             : Kirigami.Theme.disabledTextColor
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        // Its lines: click for its task, its last steps and its report
                        Item {
                            Layout.fillWidth: true
                            implicitHeight: agentLines.implicitHeight

                            ColumnLayout {
                                id: agentLines
                                anchors.fill: parent
                                spacing: 0
                                RowLayout {
                                    Layout.fillWidth: true
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        Layout.fillWidth: true
                                        text: agentRow.modelData.description || agentRow.modelData.type
                                        elide: Text.ElideRight
                                        font: Kirigami.Theme.smallFont
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        // its kind, and the model it runs on
                                        text: agentRow.modelData.type + (agentRow.modelData.model ? " · " + agentRow.modelData.model : "")
                                        opacity: 0.6
                                        font: Kirigami.Theme.smallFont
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        // failed: it ended on an API error (e.g. a usage limit)
                                        text: agentRow.modelData.status === "running"
                                              ? i18n("running · %1", root.duration(root.now - (agentRow.modelData.started || root.now)))
                                              : agentRow.modelData.status === "done" ? i18n("done")
                                              : agentRow.modelData.status === "failed" ? i18n("failed") : i18n("stopped")
                                        color: agentRow.modelData.status === "failed" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                        opacity: agentRow.modelData.status === "failed" ? 1 : 0.7
                                        font: Kirigami.Theme.smallFont
                                    }
                                    Kirigami.Icon {
                                        source: agentRow.open ? Icons.plasma.unfolded : Icons.plasma.folded
                                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                        Layout.preferredHeight: Layout.preferredWidth
                                        opacity: agentMouse.containsMouse ? 0.9 : 0.4
                                    }
                                }
                                PlasmaComponents3.Label {
                                    id: activityLabel
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: agentRow.modelData.activity
                                    opacity: 0.6
                                    elide: Text.ElideRight
                                    font: Kirigami.Theme.smallFont
                                }
                            }

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: agentRow.modelData.description || agentRow.modelData.type
                                subText: (activityLabel.truncated ? agentRow.modelData.activity + "\n\n" : "")
                                         + (agentRow.open ? i18n("Click to fold it up again.")
                                                          : i18n("Click for its task, its last steps and its report."))

                                MouseArea {
                                    id: agentMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.toggleAgentRun(agentRow.runKey)
                                }
                            }
                        }

                        // What it was asked, what it did last, and what it handed back
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.topMargin: Kirigami.Units.smallSpacing / 2
                            visible: agentRow.open
                            implicitHeight: runColumn.implicitHeight + Kirigami.Units.smallSpacing * 2
                            radius: Kirigami.Units.cornerRadius
                            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)

                            ColumnLayout {
                                id: runColumn
                                anchors.fill: parent
                                anchors.margins: Kirigami.Units.smallSpacing
                                spacing: Kirigami.Units.smallSpacing / 2

                                PlasmaComponents3.Label {
                                    id: taskLabel
                                    Layout.fillWidth: true
                                    visible: !!agentRow.modelData.task
                                    text: i18nc("what a subagent was asked to do", "Task: %1", agentRow.modelData.task)
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 4
                                    elide: Text.ElideRight
                                    opacity: 0.7
                                    font: Kirigami.Theme.smallFont

                                    PlasmaCore.ToolTipArea {
                                        textFormat: Text.PlainText
                                        anchors.fill: parent
                                        active: taskLabel.truncated
                                        mainText: i18n("Its task")
                                        subText: agentRow.modelData.task
                                    }
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: root.agentNumbers(agentRow.modelData)
                                    opacity: 0.7
                                    font: Kirigami.Theme.smallFont
                                }
                                Repeater {
                                    model: (agentRow.modelData.steps || []).length
                                    delegate: PlasmaComponents3.Label {
                                        required property int index
                                        Layout.fillWidth: true
                                        text: "▸ " + ((agentRow.modelData.steps || [])[index] || "")
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        opacity: 0.8
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        font.bold: agentRow.modelData.status === "running" && index === (agentRow.modelData.steps || []).length - 1
                                    }
                                }
                                PlasmaComponents3.Label {
                                    Layout.fillWidth: true
                                    visible: !!agentRow.modelData.report
                                    text: i18nc("what a subagent handed back", "Report: %1", agentRow.modelData.report)
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 12
                                    elide: Text.ElideRight
                                    font: Kirigami.Theme.smallFont
                                }
                                PlasmaComponents3.ToolButton {
                                    icon.name: Icons.plasma.openRun
                                    text: i18n("Open the whole run")
                                    enabled: !!row.session.chatId
                                    onClicked: root.openAgentRun(row.session, agentRow.modelData.id, row.remoteHost)

                                    PlasmaCore.ToolTipArea {
                                        textFormat: Text.PlainText
                                        anchors.fill: parent
                                        mainText: i18n("Everything it did")
                                        subText: i18n("Its task, every step with the start of each result, and its report, as a Markdown file in your app for those. Claude Code itself can't open a subagent from outside.")
                                                 + (row.remoteHost ? " " + i18n("Fetched from %1 over ssh.", row.remoteHost) : "")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        KeepOnlyMessage {
            Layout.fillWidth: true
            shown: row.confirmingKeepOnly
        }

        DeleteAsk {
            Layout.fillWidth: true
            itemKey: row.session.key !== "" ? row.rowKey : ""
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: row.confirmingStop && row.canStop
            type: Kirigami.MessageType.Warning
            // rich text (an InlineMessage always guesses), so the name is escaped
            text: "<span>" + (row.canInterrupt
                  ? i18n("Interrupt “%1”? Like Ctrl+C in its tmux pane, or the stop button in VS Code: the current step and its subagents stop, and the chat stays open there. Or stop it: Claude quits and its terminal stays open.", root.escapeHtml(row.session.name))
                  : row.canEnd && row.inVscode && row.session.state === "working"
                  ? i18n("Stop “%1”? It's working right now: the current step is interrupted, as with VS Code's stop button, and anything it was running stops. Its tab keeps the chat and goes on with your next message.", root.escapeHtml(row.session.name))
                  : row.canEnd && row.inVscode && row.session.state === "waiting"
                  ? i18n("Stop “%1”? It's waiting for you: what it asks is refused, as with VS Code's stop button. Its tab keeps the chat and goes on with your next message.", root.escapeHtml(row.session.name))
                  : row.canEnd && row.inVscode
                  ? i18n("Stop “%1”? It's idle, so nothing is interrupted: its Claude process in VS Code quits. Its tab keeps the chat and goes on with your next message.", root.escapeHtml(row.session.name))
                  : row.canEnd && row.session.state === "working"
                  ? i18n("Stop “%1”? It's working right now: the current step is cut off and anything it was running stops. Claude quits and its terminal stays open; the chat is kept (Recent chats reopens it).", root.escapeHtml(row.session.name))
                  : row.canEnd && row.session.state === "waiting"
                  ? i18n("Stop “%1”? It's waiting for you: Claude quits without your answer and its terminal stays open. The chat is kept (Recent chats reopens it).", root.escapeHtml(row.session.name))
                  : row.canEnd
                  ? i18n("Stop “%1”? It's idle, so nothing is interrupted: Claude quits and its terminal stays open. The chat is kept; reopen it from Recent chats.", root.escapeHtml(row.session.name))
                  : row.session.state === "working"
                  ? i18n("Stop “%1”? It's working right now: the current step is interrupted and anything it started in the background stops too. The conversation is kept; claude attach resumes it.", root.escapeHtml(row.session.name))
                  : row.session.state === "waiting"
                  ? i18n("Stop “%1”? It's waiting for you. The conversation is kept; claude attach resumes it.", root.escapeHtml(row.session.name))
                  : i18n("Stop “%1”? It's finished, so this only shuts down its idle process. The conversation is kept.", root.escapeHtml(row.session.name)))
                  + (row.kept ? "<br>" + i18n("It keeps going after usage limits.") : "") + "</span>"
            actions: [
                Kirigami.Action {
                    text: i18n("Interrupt")
                    icon.name: Icons.plasma.interrupt
                    visible: row.canInterrupt
                    onTriggered: {
                        root.stopConfirmSession = ""
                        if (row.remoteHost)
                            root.remoteInterrupt(row.remoteHost, row.session.sessionId, row.session.profileDir)
                        else
                            root.interruptSession(row.session.sessionId, row.session.profileDir)
                    }
                },
                Kirigami.Action {
                    text: i18n("Stop")
                    icon.name: Icons.plasma.stop
                    onTriggered: row.stop(false)
                },
                Kirigami.Action {
                    // (Stop alone leaves Keep going on: it goes on after the next limit)
                    text: i18n("Stop and turn Keep going off")
                    icon.name: Icons.plasma.stop
                    visible: row.kept !== null && !row.remoteHost
                    onTriggered: row.stop(true)
                },
                Kirigami.Action {
                    text: i18n("Cancel")
                    onTriggered: root.stopConfirmSession = ""
                }
            ]
        }
    }
}
