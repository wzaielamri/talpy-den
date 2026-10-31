import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// One Claude account: plan limits, token totals, its sessions (which may
// come from several config dirs logged into that account) and recent chats.
// With remoteHost set, the account is on that SSH host: its actions run there.
ColumnLayout {
    id: section

    property var group
    property bool last: false
    property string remoteHost: ""
    property int accounts: 1          // how many accounts its machine has (the default one is marked)

    readonly property string groupKey: (remoteHost ? remoteHost + "/" : "") + group.id
    // the folder and how long ago at the end of a recent chat's, a plan's or
    // CLAUDE.md's line: columns of one width in all, so what's before them
    // lines up, and the folders and times too
    readonly property real folderWidth: Kirigami.Units.gridUnit * 8
    readonly property var queued: root.queuedFor(group, remoteHost)
    // Recent chats: the status' (a page more than shows), then a bigger
    // check's past those (root.fetchRecent), each once; how many show, and
    // how many are wanted (a page more than show: asked for when they aren't there)
    readonly property var recent: group.recent || []
    readonly property bool recentOpen: !!root.expandedRecent[groupKey]
    readonly property var recentMore: recentOpen ? root.recentMore[groupKey] || null : null
    readonly property var recentAll: {
        if (!recentMore)
            return recent
        const listed = {}
        for (const c of recent)
            listed[c.sessionId] = true
        return recent.concat(recentMore.recent.filter(c => !listed[c.sessionId]))
    }
    // (a check that listed more got fewer than it asked for: that's all of them)
    readonly property int recentCount: recentMore && recentMore.recent.length < recentMore.asked
                                       ? recentAll.length : Math.max(group.recentCount || 0, recent.length)
    readonly property int recentShown: Math.min(recentAll.length, root.pageSize * root.pagesShown(groupKey + "|recent"))
    readonly property int recentWanted: recentOpen ? Math.min(recentCount, root.pageSize * (root.pagesShown(groupKey + "|recent") + 1)) : 0
    onRecentWantedChanged: {
        if (recentAll.length < recentWanted)
            root.fetchRecent(groupKey, group.id, remoteHost, recentWanted)
    }
    // the chats and plans you starred, however old: all of them in the status
    readonly property var starred: group.starred || []
    readonly property var starredPlans: group.starredPlans || []
    readonly property bool starredOpen: !!root.expandedStarred[groupKey + "|chats"]
    readonly property bool starredPlansOpen: !!root.expandedStarred[groupKey + "|plans"]
    readonly property int starredShown: Math.min(starred.length, root.pageSize * root.pagesShown(groupKey + "|chats"))
    readonly property int starredPlansShown: Math.min(starredPlans.length, root.pageSize * root.pagesShown(groupKey + "|plans"))
    // (their lines' models: a page more made, none taken away while they show; folded, a list has none)
    PageRows {
        id: recentRows
        size: section.recentShown
    }
    PageRows {
        id: starredRows
        size: section.starredShown
    }
    PageRows {
        id: starredPlanRows
        size: section.starredPlansShown
    }

    readonly property var tokens: group.tokens
    readonly property bool hasTokens: tokens !== null && tokens !== undefined
    readonly property bool hasStats: !!group.stats
    readonly property bool statsOpen: hasStats && root.expandedStats[groupKey] === true
    readonly property bool multiProfile: group.profiles.length > 1

    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing

        Kirigami.Heading {
            id: heading
            textFormat: Text.PlainText
            level: 2   // (as the Recap tab's section titles)
            font.weight: Font.Bold
            text: section.group.title
            elide: Text.ElideRight
            Layout.maximumWidth: section.width - newChatButton.width - (defaultTag.visible ? defaultTag.width : 0) - Kirigami.Units.gridUnit * 6
        }
        // The default account: listed first, VS Code's Claude and plain claude run on it
        Tag {
            id: defaultTag
            visible: !!section.group.defaultHere && section.accounts > 1
            text: i18n("Default")
            tooltipTitle: section.remoteHost ? i18n("The default account on %1", section.remoteHost) : i18n("The default account")
            tooltip: (section.remoteHost
                      ? i18n("Listed first; VS Code's Claude on %1 (its VS Code server) and plain claude there run on it.", section.remoteHost)
                      : i18n("Listed first, its 5-hour usage is next to the panel icon, and VS Code's Claude and plain claude run on it."))
                     + " " + i18n("Change it in Talpy Den's settings: Accounts, Make Default.")
        }
        PlasmaComponents3.ToolButton {
            id: newChatButton
            // (a speech bubble with a plus: a + beside the account reads as
            // "add an account"), drawn at the 16 px it's made for
            icon.source: root.iconDir + "chat-new-symbolic.svg"
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("New chat")
            Layout.preferredHeight: heading.implicitHeight
            Layout.preferredWidth: Layout.preferredHeight
            readonly property real iconPadding: Math.max(0, Math.floor((Layout.preferredHeight - Kirigami.Units.iconSizes.small) / 2))
            topPadding: iconPadding
            bottomPadding: iconPadding
            leftPadding: iconPadding
            rightPadding: iconPadding
            checked: root.newChatGroup === section.groupKey
            onClicked: root.toggleNewChat(section.groupKey)

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("New chat on %1", section.group.title)
                subText: (section.remoteHost
                          ? i18n("Lists this account's folders on %1: start a new Claude chat in one, in a terminal (over ssh) or in VS Code.", section.remoteHost)
                          : i18n("Lists this account's recent folders: start a new Claude chat in one, in a terminal or in VS Code."))
                         + " " + i18n("Write a task first and the chat starts with it, also in the background.")
            }
        }
        Item {
            Layout.fillWidth: true
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            visible: section.multiProfile
            text: section.group.profiles.join(" + ")
            opacity: 0.6
            font: Kirigami.Theme.smallFont
        }
    }

    // New chat (the + above): what Claude should do (optional) and the
    // account's folders (NewChatBox.qml)
    NewChatBox {
        visible: root.newChatGroup === section.groupKey
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        group: section.group
        remoteHost: section.remoteHost
    }

    // This account's chats as pets (PetStrip.qml), the ones that need you or
    // work first. It slides open when the account has a chat in the list.
    PetStrip {
        id: stage
        readonly property bool wanted: Plasmoid.configuration.showPet && Plasmoid.configuration.chatPets > 0
                                       && (stage.chats.length > 0 || stage.petCount > 0)
        property real shownHeight: wanted ? implicitHeight : 0
        Behavior on shownHeight {
            NumberAnimation { duration: 260; easing.type: Easing.InOutQuad }
        }
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        Layout.preferredHeight: shownHeight
        visible: shownHeight > 0
        stageKey: section.groupKey
        chats: {
            const rank = { waiting: 0, working: 1, idle: 2, done: 3 }
            const out = [], seen = {}
            for (const s of section.group.sessions) {
                const key = root.petKeyOf(s, section.remoteHost)
                if (key in seen)
                    continue
                seen[key] = true
                out.push({ key: key, session: s, host: section.remoteHost, order: out.length })
            }
            return out.sort((a, b) => (rank[a.session.state] - rank[b.session.state]) || (a.order - b.order))
        }
    }

    // Not logged in to an account (a new one, or logged out): Claude's own
    // login, in a terminal (over ssh for a host's)
    RowLayout {
        visible: !!section.group.loggedOut
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: Icons.plasma.accountOut
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            elide: Text.ElideRight
            text: i18n("Not logged in")
            opacity: 0.8
        }
        PlasmaComponents3.Button {
            text: i18n("Log in…")
            icon.name: Icons.plasma.signIn
            enabled: !section.remoteHost || !!section.group.loginCommand

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Log in to %1", section.group.title)
                subText: section.remoteHost
                         ? i18n("Opens a terminal with Claude's own login on %1 (over ssh): open the address it shows in your browser, sign in, and paste the code you get back.", section.remoteHost)
                         : i18n("Opens a terminal with Claude's own login (claude auth login): sign in in your browser with the account for this folder. Talpy Den never sees the login.")
            }
            onClicked: root.logIn(section.group, section.remoteHost)
        }
    }

    // Plan limits (from the status line); not where they show elsewhere (root.withUsage)
    ColumnLayout {
        visible: !section.group.limitsHidden && !section.group.loggedOut
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing / 2

        Repeater {
            // a count, not the array: a new array every poll would make the
            // bars anew (and close the forecast's tooltip under the mouse)
            model: section.group.limits ? section.group.limits.windows.length : 0
            delegate: UsageBar {
                required property int index
                readonly property var window: (section.group.limits ? section.group.limits.windows[index] : null)
                                              || ({ label: "", pct: 0, forecast: null, resetsAt: 0 })
                Layout.fillWidth: true
                label: window.label
                pct: window.pct
                detail: root.resetText(window)
                forecast: window.forecast || null
                resetsAt: window.resetsAt || 0
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            elide: Text.ElideRight
            opacity: 0.6
            font: Kirigami.Theme.smallFont
            // (a fetch on its way, Refresh's or while a chat works: the numbers come within a minute)
            readonly property bool fetching: !!section.group.usageFetchAt && root.now - section.group.usageFetchAt < 70000
                                             && (!section.group.limits || section.group.limits.updatedAt < section.group.usageFetchAt)
            text: fetching ? i18n("Fetching the plan usage…")
                  : !section.group.limits ? i18n("No plan usage yet: shows after this account's next reply")
                  : section.group.limitsFrom
                    ? (root.now - section.group.limits.updatedAt < 60000 ? i18n("Plan usage updated just now, on %1", section.group.limitsFrom)
                       : i18n("Plan usage as of %1 ago, on %2", root.duration(root.now - section.group.limits.updatedAt), section.group.limitsFrom))
                  : root.now - section.group.limits.updatedAt < 60000 ? i18n("Plan usage updated just now")
                  : i18n("Plan usage as of %1 ago", root.duration(root.now - section.group.limits.updatedAt))

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: !section.group.limits
                mainText: i18n("No plan usage yet")
                subText: i18n("Plan limits come from the Claude Code status line (statusline-snippet.sh). They update whenever a chat of this account gets a reply.")
            }
        }
    }

    // Token totals (from local transcripts); click for the last days (the
    // arrow before them, as in the VS Code extension)
    RowLayout {
        visible: section.hasTokens
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing / 2

        Kirigami.Icon {
            visible: section.hasStats
            source: section.statsOpen ? Icons.plasma.unfolded : Icons.plasma.folded
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            opacity: 0.6

            TapHandler {
                onTapped: root.toggleStats(section.groupKey)
            }
        }
        PlasmaComponents3.Label {
            id: tokenLabel
            textFormat: Text.PlainText
            Layout.fillWidth: true
            elide: Text.ElideRight
            text: section.hasTokens
                  ? i18n("Tokens today %1 (%2 out) · 7 days %3 (%4 out)",
                         root.formatTokens(section.tokens.today.total), root.formatTokens(section.tokens.today.output),
                         root.formatTokens(section.tokens.week.total), root.formatTokens(section.tokens.week.output))
                  : ""

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: section.hasTokens
                mainText: i18n("Tokens (this machine's transcripts only)")
                subText: {
                    if (!section.hasTokens)
                        return ""
                    const t = section.tokens
                    const fmt = b => i18n("input %1 · output %2 · cache read %3 · cache write %4 · %5 replies",
                                          root.formatTokens(b.input), root.formatTokens(b.output),
                                          root.formatTokens(b.cacheRead), root.formatTokens(b.cacheWrite), b.messages)
                    const models = t.models.map(m => m.model.replace(/^claude-/, "") + ": " + root.formatTokens(m.total))
                    return i18n("Today: %1", fmt(t.today)) + "\n" + i18n("Last 7 days: %1", fmt(t.week))
                           + (models.length ? "\n" + i18n("By model (7 days): %1", models.join(", ")) : "")
                           + (t.week.shared > 0
                              ? "\n" + i18n("Includes %1 today (%2 in 7 days) from chats shared with another profile. A transcript doesn't say which account paid, so shared chats count on both.",
                                             root.formatTokens(t.today.shared), root.formatTokens(t.week.shared))
                              : "")
                           + (section.hasStats ? "\n\n" + (section.statsOpen ? i18n("Click to fold the last days up again.")
                                                                             : i18n("Click for the last days: tokens per day, your busiest folders and models.")) : "")
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: section.hasStats
                    cursorShape: section.hasStats ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: root.toggleStats(section.groupKey)
                }
            }
        }
    }

    // The last days, unfolded from the token line
    StatsPanel {
        visible: section.statsOpen
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        stats: section.hasStats ? section.group.stats : null
    }

    // Sessions
    // (where their list starts: a row slides when it moves in the list, not
    // when what's above the list grows, its Tokens panel say: SessionRow.placed)
    Item {
        id: sessionsTop
        Layout.fillWidth: true
        Layout.preferredHeight: 0
        Layout.bottomMargin: -section.spacing
    }
    Repeater {
        model: section.group.sessions.length
        delegate: SessionRow {
            required property int index
            Layout.fillWidth: true
            listTop: sessionsTop
            session: section.group.sessions[index] || root.emptySession
            showProfile: section.multiProfile
            remoteHost: section.remoteHost
            account: section.group.title
        }
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: section.group.sessions.length === 0
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        text: i18n("No running chats")
        opacity: 0.6
    }

    // Tasks waiting for this account's usage limit to reset, or for the time you picked (main.qml: the queue)
    Repeater {
        model: section.queued.length
        delegate: ColumnLayout {
            id: queuedLine

            required property int index
            readonly property var task: section.queued[index]
                                        || ({ id: "", prompt: "", planTitle: "", folder: "", folderShort: "", startAt: 0, error: "", due: false,
                                              chat: null, name: "" })
            readonly property string what: root.queuedWhat(task)
            readonly property string folder: (task.host ? task.host + ":" : "") + (task.folder || "~")

            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            Layout.rightMargin: Kirigami.Units.smallSpacing
            spacing: 0

            // a line as a recent chat's: its mark, what it is, and at its end its
            // folder and when it starts; Start now and Cancel on hover (or Tab,
            // or a finger's hold), over that end
            HoverHandler {
                id: queuedHover
            }
            TouchHold {
                buttons: queuedButtons
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: queuedLine.task.error ? Icons.plasma.warning : Icons.plasma.goOnAt
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Layout.preferredWidth
                    Layout.alignment: Qt.AlignVCenter
                    opacity: queuedLine.task.error ? 1 : 0.7
                }
                PlasmaComponents3.Label {
                    id: queuedName
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: queuedLine.what.split("\n")[0]
                    elide: Text.ElideRight
                    activeFocusOnTab: true   // (Tab: its buttons show)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: queuedLine.task.scheduled ? i18n("Starts later") : queuedLine.task.chat ? i18n("Goes on after the usage limit")
                                                            : i18n("Waits for the usage limit")
                        subText: queuedLine.what + "\n\n"
                                 + (queuedLine.task.chat
                                    ? i18n("The chat goes on in the background in %1, at %2, telling Claude that the limit has reset. A Claude that still has it open (in a terminal, or in the background) quits first; if it went on before then, nothing happens.",
                                           queuedLine.folder, root.startText(queuedLine.task.startAt))
                                    : i18n("Starts in the background in %1, at %2.", queuedLine.folder, root.startText(queuedLine.task.startAt)))

                        TouchHold {
                            buttons: queuedButtons
                        }
                    }
                }
                // its folder and when it starts, at the line's end
                CoveredEnd {
                    id: queuedEnd
                    covered: queuedButtons.covering
                    Layout.preferredWidth: Math.min(queuedWhen.implicitWidth, Kirigami.Units.gridUnit * 12)
                    implicitHeight: queuedWhen.implicitHeight

                    PlasmaComponents3.Label {
                        id: queuedWhen
                        width: queuedEnd.width
                        horizontalAlignment: Text.AlignRight
                        textFormat: Text.PlainText
                        text: queuedLine.task.error ? i18n("didn't start")
                              : queuedLine.task.due || queuedLine.task.startAt <= root.now ? i18n("starting…")
                              : queuedLine.task.startAt - root.now > 12 * 3600000
                              ? i18nc("queued task: folder, when it starts", "%1 · starts %2", queuedLine.task.folderShort || "~",
                                      root.startText(queuedLine.task.startAt))
                              : i18nc("queued task: folder, when it starts", "%1 · starts in %2", queuedLine.task.folderShort || "~",
                                      root.duration(queuedLine.task.startAt - root.now))
                        color: queuedLine.task.error ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                        opacity: queuedLine.task.error ? 1 : 0.6
                        font: Kirigami.Theme.smallFont
                        elide: Text.ElideLeft
                    }
                }
                HoverButtons {
                    id: queuedButtons
                    lineHeight: queuedName.implicitHeight
                    shown: queuedHover.hovered || queuedName.activeFocus || queuedButtons.focused || queuedButtons.held
                           || root.unqueueAsk === queuedLine.task.id
                    under: queuedEnd

                    RowLayout {   // (made the first time they show)
                        spacing: 0

                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.startNow
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            text: i18n("Start it now")
                            enabled: !root.isStarting(queuedLine.task.id)
                            Layout.preferredHeight: queuedButtons.buttonSize
                            Layout.preferredWidth: queuedButtons.buttonWidth
                            icon.width: Kirigami.Units.iconSizes.small
                            icon.height: Kirigami.Units.iconSizes.small
                            Layout.alignment: Qt.AlignTop
                            onClicked: root.startQueued(queuedLine.task)

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Start it now")
                                subText: queuedLine.task.scheduled ? i18n("In the background, without waiting for its time.")
                                         : i18n("In the background, without waiting for the limit to reset. While the limit lasts, Claude stops again at once.")
                            }
                        }
                        PlasmaComponents3.ToolButton {
                            // (what you wrote for it is asked about first: it's gone with it)
                            readonly property bool wrote: !queuedLine.task.chat || !!queuedLine.task.afterTurn
                            readonly property bool kept: !!queuedLine.task.chat && !queuedLine.task.afterTurn && !queuedLine.task.host
                                                         && root.keptChat(queuedLine.task.chat) !== null
                            icon.name: Icons.plasma.cancel
                            icon.color: Icons.color("cancel", Kirigami.Theme)
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            text: i18n("Cancel it")
                            Layout.preferredHeight: queuedButtons.buttonSize
                            Layout.preferredWidth: queuedButtons.buttonWidth
                            icon.width: Kirigami.Units.iconSizes.small
                            icon.height: Kirigami.Units.iconSizes.small
                            Layout.alignment: Qt.AlignTop
                            onClicked: {
                                if (wrote)
                                    root.unqueueAsk = root.unqueueAsk === queuedLine.task.id ? "" : queuedLine.task.id
                                else
                                    root.unqueue(queuedLine.task)
                            }

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Cancel it")
                                subText: i18n("It doesn't start.") + (parent.kept ? " " + i18n("It stops keeping going after usage limits too.") : "")
                                         + (parent.wrote ? " " + i18n("It asks first: what you wrote for it is gone with it.") : "")
                            }
                        }
                    }
                }
            }
            ConfirmLine {
                visible: root.unqueueAsk !== "" && root.unqueueAsk === queuedLine.task.id
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                text: queuedLine.task.afterTurn ? i18n("Cancel your message to “%1”? It isn't sent, and its text is gone.", queuedLine.task.name || i18n("the chat"))
                                                : i18n("Cancel this task? It doesn't start, and what you wrote for it is gone.")
                confirmText: i18n("Cancel it")
                cancelText: i18n("Keep it")
                onConfirmed: {
                    root.unqueueAsk = ""
                    root.unqueue(queuedLine.task)
                }
                onCancelled: root.unqueueAsk = ""
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                visible: queuedLine.task.error !== ""
                text: queuedLine.task.error
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
            }
        }
    }

    // Chats shared with this account that are in use on another one (they're
    // listed there, once): a line pointing to them
    Repeater {
        model: (section.group.sharedHere || []).length
        delegate: RowLayout {
            id: sharedLine

            required property int index
            readonly property var chat: section.group.sharedHere[index]
                                        || ({ sessionId: "", profileDir: "", name: "", profile: "", state: "idle",
                                              reason: "", since: null, stoppedHere: false, copy: false, openCommand: "" })

            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            Layout.rightMargin: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: Icons.plasma.share
                color: root.stateColor(sharedLine.chat.state)
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Layout.preferredWidth
                Layout.alignment: Qt.AlignVCenter
            }
            PlasmaComponents3.Label {
                id: sharedName
                textFormat: Text.PlainText
                text: sharedLine.chat.name
                opacity: 0.8
                font.underline: sharedMouse.containsMouse
                elide: Text.ElideRight
                Layout.fillWidth: true

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    width: sharedName.contentWidth
                    height: parent.height
                    mainText: sharedLine.chat.copy ? i18n("Shared chat, continued on %1 as a copy", sharedLine.chat.profile)
                              : sharedLine.chat.state === "done" ? i18n("Shared chat, last used on %1", sharedLine.chat.profile)
                              : i18n("Shared chat, open on %1", sharedLine.chat.profile)
                    subText: (sharedLine.chat.copy
                              ? i18n("This chat is shared with this account too, but it continued on %1 in a copy Claude forked from it. New messages are only in that copy. Click to go to it.", sharedLine.chat.profile)
                              : i18n("This chat is shared with this account too. It's listed once, under the account it's used on. Click to go to it."))
                             + (sharedLine.chat.stoppedHere ? "\n" + i18n("Its background chat on this account was stopped.") : "")

                    MouseArea {
                        id: sharedMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        // as a click on the chat's own name (its row, under the account it's used on)
                        onClicked: {
                            const row = root.listedRow(sharedLine.chat.sessionId, sharedLine.chat.profileDir, section.remoteHost)
                            if (row)
                                root.clickChat(row, section.remoteHost)
                            else if (section.remoteHost)
                                root.remoteOpen(section.remoteHost, sharedLine.chat.openCommand)
                            else
                                root.jumpTo(sharedLine.chat.sessionId, sharedLine.chat.profileDir)
                        }
                    }
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                text: sharedLine.chat.copy
                      ? i18nc("shared chat continued in a copy: where, its state", "copy on %1 · %2", sharedLine.chat.profile, root.stateText(sharedLine.chat))
                      : i18nc("shared chat: where it is, its state", "on %1 · %2", sharedLine.chat.profile, root.stateText(sharedLine.chat))
                opacity: 0.6
                font: Kirigami.Theme.smallFont
                elide: Text.ElideRight
                Layout.maximumWidth: Kirigami.Units.gridUnit * 12
            }
        }
    }

    // Recent chats: this account's latest other chats, to pick one up
    // again, a page at a time ("Show N more"; the status lists one page
    // more than shows, a check for more is asked for past that)
    PlasmaComponents3.ToolButton {
        visible: section.recentCount > 0
        Layout.leftMargin: Kirigami.Units.smallSpacing
        flat: true
        icon.name: section.recentOpen ? Icons.plasma.unfolded : Icons.plasma.folded
        text: section.recentShown < section.recentCount
              ? i18nc("recent chats: how many show, of how many", "Recent chats (%1 of %2)", section.recentShown, section.recentCount)
              : i18n("Recent chats (%1)", section.recentCount)
        font: Kirigami.Theme.smallFont
        onClicked: root.toggleRecent(section.groupKey, section.recentOpen)

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Recent chats")
            subText: (Plasmoid.configuration.clickOpensPane
                      ? i18n("This account's latest chats that aren't listed above, newest first. Click one to open it beside the popup; its reopen button (on hover) reopens it in a terminal or in VS Code (the switch at the top of the list).")
                      : i18n("This account's latest chats that aren't listed above, newest first. Click one to reopen it, in a terminal or in VS Code (the switch at the top of the list)."))
                     + " " + i18n("Show more lists more of them; folded again, it lists the first ones again. Every chat of a project is in the Projects tab.")
        }
    }

    // Where they reopen: the same Terminal | VS Code choice as for new chats
    // (under ★ Starred chats while Recent chats is folded)
    OpenInSwitch {
        visible: section.recentOpen
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.gridUnit
        Layout.rightMargin: Kirigami.Units.smallSpacing
        group: section.group
        remoteHost: section.remoteHost
        resuming: true
    }

    Repeater {
        model: section.recentOpen ? recentRows : 0
        delegate: RecentLine {
            required property int index
            Layout.leftMargin: Kirigami.Units.gridUnit
            chat: section.recentAll[index] || root.emptyRecent
            group: section.group
            remoteHost: section.remoteHost
            folderWidth: section.folderWidth
        }
    }
    MoreButton {
        open: section.recentOpen
        listKey: section.groupKey + "|recent"
        shown: section.recentShown
        count: section.recentCount
    }

    // ★ Starred chats: the ones you starred (☆ on a chat), however old, a page at a time
    PlasmaComponents3.ToolButton {
        visible: section.starred.length > 0
        Layout.leftMargin: Kirigami.Units.smallSpacing
        flat: true
        icon.name: section.starredOpen ? Icons.plasma.unfolded : Icons.plasma.folded
        text: section.starredShown < section.starred.length
              ? i18nc("starred chats: how many show, of how many", "★ Starred chats (%1 of %2)", section.starredShown, section.starred.length)
              : i18nc("starred chats, how many", "★ Starred chats (%1)", section.starred.length)
        font: Kirigami.Theme.smallFont
        onClicked: root.toggleStarred(section.groupKey + "|chats", section.starredOpen)

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Starred chats")
            subText: i18n("The chats of this account you starred (☆ next to a chat), newest first, however old they are; not the ones listed above. Click a chat's ★ to unstar it.")
        }
    }
    OpenInSwitch {
        visible: section.starredOpen && !section.recentOpen
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.gridUnit
        Layout.rightMargin: Kirigami.Units.smallSpacing
        group: section.group
        remoteHost: section.remoteHost
        resuming: true
    }
    Repeater {
        model: section.starredOpen ? starredRows : 0
        delegate: RecentLine {
            required property int index
            Layout.leftMargin: Kirigami.Units.gridUnit
            chat: section.starred[index] || root.emptyRecent
            group: section.group
            remoteHost: section.remoteHost
            folderWidth: section.folderWidth
        }
    }
    MoreButton {
        open: section.starredOpen
        listKey: section.groupKey + "|chats"
        shown: section.starredShown
        count: section.starred.length
    }

    // ★ Starred plans: the plans you starred, however old, a page at a time
    // (every plan is in its project, in the Projects tab)
    PlasmaComponents3.ToolButton {
        visible: section.starredPlans.length > 0
        Layout.leftMargin: Kirigami.Units.smallSpacing
        flat: true
        icon.name: section.starredPlansOpen ? Icons.plasma.unfolded : Icons.plasma.folded
        text: section.starredPlansShown < section.starredPlans.length
              ? i18nc("starred plans: how many show, of how many", "★ Starred plans (%1 of %2)", section.starredPlansShown, section.starredPlans.length)
              : i18nc("starred plans, how many", "★ Starred plans (%1)", section.starredPlans.length)
        font: Kirigami.Theme.smallFont
        onClicked: root.toggleStarred(section.groupKey + "|plans", section.starredPlansOpen)

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Starred plans")
            subText: i18n("The plans of this account you starred (☆ next to a plan), newest first, however old they are. Click one to read it; carry it out in a new chat, go back to the chat that made it, or share it with your other accounts. Click a plan's ★ to unstar it. Every plan is in its project, in the Projects tab.")
        }
    }
    Repeater {
        model: section.starredPlansOpen ? starredPlanRows : 0
        delegate: PlanLine {
            required property int index
            Layout.leftMargin: Kirigami.Units.gridUnit
            plan: section.starredPlans[index] || root.emptyPlan
            group: section.group
            remoteHost: section.remoteHost
            folderWidth: section.folderWidth
        }
    }
    MoreButton {
        open: section.starredPlansOpen
        listKey: section.groupKey + "|plans"
        shown: section.starredPlansShown
        count: section.starredPlans.length
    }

    // The account's CLAUDE.md: your instructions for every chat on it (read it, or edit it)
    Repeater {
        model: (section.group.instructions || []).length
        delegate: MemoryLine {
            required property int index
            Layout.leftMargin: Kirigami.Units.smallSpacing
            memory: section.group.instructions[index] || root.emptyMemory
            remoteHost: section.remoteHost
            folderWidth: section.folderWidth
        }
    }


    Kirigami.Separator {
        visible: !section.last
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
    }
}
