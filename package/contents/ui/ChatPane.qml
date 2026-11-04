import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "hub"
import "markdown.mjs" as Md
import "codehtml.mjs" as Code
import "icons.mjs" as Icons

// A chat beside the popup (main.qml: openPane): its conversation, updating
// while it works, drawn the way Claude's terminal draws it (a dot before each
// reply and tool call, a tool call's outcome under it, your prompts set off),
// with each tool call folded into one line; a box to reply
// (pane.py --send: typed into tmux, put in its VS Code tab's input, or it
// goes on in the background); what it asks while it waits for a permission,
// with Allow once / Always allow / Deny, or Claude's questions to answer;
// and its review: the files it
// changed, against how they were before the chat, with Undo, Commit and
// Mark reviewed. One window for each chat (chat: main.qml openPane), kept
// hidden once it's closed, for the next chat opened.
Window {
    id: pane
    objectName: "talpyDenChatPane"   // (TipArea: tooltips drawn in this window)

    property var chat: ({})   // {chatId, sessionId, profileDir, host, name, cwd, tab}: none while it's closed
    property string lastKey: ""   // (closed: the chat it showed, opened in it again: main.qml)
    readonly property var row: root.paneRowOf(chat)   // its row in the status now (null: not listed)
    readonly property string host: chat.host || ""
    readonly property string chatId: chat.chatId || ""
    readonly property string profileDir: row && row.profileDir ? row.profileDir : (chat.profileDir || "")
    readonly property string sessionId: row && row.sessionId ? row.sessionId : (chat.sessionId || "")
    readonly property string chatName: row && row.name ? row.name : (chat.name || "")
    readonly property string chatState: row ? row.state : "done"
    readonly property bool busy: chatState === "working" || chatState === "waiting"
    readonly property string route: row && row.reply ? row.reply : "background"
    readonly property var permission: row && row.permission && chatState === "waiting" ? row.permission : null
    // A background chat that asks you something you can answer here: your reply answers it, as typing
    // in its own prompt does, never stopping the chat (VS Code shared/pane.ts replyAnswers): "deny"
    // (your words go to Claude with the No), "plan" (it keeps planning, with them), "question" (one:
    // your own words), "decline" (several: declined, with them); "": it goes as routeHint says
    readonly property string replyAnswers: {
        const p = permission
        if (!p || !row || row.kind !== "bg" || !row.pid || (p.answer !== "hook" && p.answer !== "keys"))
            return ""
        const n = p.questions ? p.questions.length : 0
        return n > 1 ? "decline" : n ? "question" : p.plan ? "plan" : "deny"
    }
    // (it asks something only its own prompt can answer: a reply waits till that's answered)
    readonly property bool replyWaits: !!permission && replyAnswers === "" && (route === "tmux" || (!!row && row.kind === "bg"))
    readonly property var queued: root.queuedMessage(chatId, host)
    property string unqueueAsk: ""   // Cancel on it clicked: asked first (its id)
    readonly property bool reviewPending: row ? root.reviewPending(row, host) : false
    // Chat (your messages and Claude's replies), Steps (its tool calls too)
    // and Review; its screen is in its window (Open its window)
    property string tab: "chat"
    // its task list (when it has one, the row's) and its subagents: a strip under the header,
    // folded; unfolded, its tasks (tasksOpen) and its subagents (agentsOpen: the header's
    // Agents tag unfolds only them, as a row's Agents tag in the popup)
    readonly property var tasks: row && row.tasks && row.tasks.total > 0 ? row.tasks : null
    readonly property var agents: row && row.agents && row.agents.total > 0 ? row.agents : null
    property bool tasksOpen: false
    property bool agentsOpen: false
    readonly property string nextTask: {
        for (const t of tasks ? tasks.items : [])
            if (t.status !== "completed")
                return t.subject
        return ""
    }
    // (its subagents, while they're unfolded: the running ones first, each after the
    // one that started it, as in the status's tree)
    readonly property var stripAgents: {
        if (!agentsOpen || !agents)
            return []
        const started = []   // (each of the chat's own subagents, with the ones it started)
        for (const a of agents.tree)
            if (a.depth === 0 || !started.length)
                started.push([a])
            else
                started[started.length - 1].push(a)
        const busy = list => list.some(a => a.status === "running")
        return [].concat(...started.filter(busy), ...started.filter(list => !busy(list)))
    }
    // without a task list, the strip's line says what its subagents do
    readonly property string agentsNow: {
        if (tasks || !agents)
            return ""
        const running = agents.tree.filter(a => a.status === "running")
        if (running.length === 1)
            return (running[0].description || running[0].type) + (running[0].activity ? ": " + running[0].activity : "")
        return running.length > 1 ? i18np("%1 running", "%1 running", running.length)
             : agents.done >= agents.total ? i18n("all done") : i18n("none running")
    }

    // the strip's line: all of it unfolds, or folds
    function toggleStrip() {
        const open = !tasksOpen && !agentsOpen
        tasksOpen = open && tasks !== null
        agentsOpen = open && agents !== null
    }
    readonly property bool conversationTab: tab === "chat" || tab === "steps"
    // Where it runs (the tag under its name): "background" (a background
    // session), "closed" (no process: a reply goes
    // on in the background), "claude" (VS Code's Claude Code panel), "tmux",
    // "vscode" (a terminal of VS Code) or "terminal" (another terminal)
    readonly property string where: !row || !row.pid ? "closed" : row.kind === "bg" ? "background"
                                    : row.entrypoint === "claude-vscode" ? "claude" : row.tmux ? "tmux"
                                    : row.vscodeTerminal || row.terminalApp === "VS Code" ? "vscode" : "terminal"

    title: i18nc("window title: a chat's name", "%1 — Talpy Chat", chatName || chatId.slice(0, 8))
    readonly property int wantedWidth: Kirigami.Units.gridUnit * 38   // (beside the popup, if there's room: main.qml)
    width: wantedWidth
    height: Kirigami.Units.gridUnit * 40
    // (never narrower than the send buttons, which don't shrink)
    minimumWidth: Math.max(Kirigami.Units.gridUnit * 22, widestSend.width + Kirigami.Units.largeSpacing * 2)
    minimumHeight: Kirigami.Units.gridUnit * 18
    color: Kirigami.Theme.backgroundColor
    onClosing: {
        cancelDictation()
        root.paneClosed(pane)
    }

    // Where it opens, and when (main.qml placePane and showPane): beside the
    // popup, once KWin is ready for it (placeAsk answered, at most a second)
    // and its conversation is read (at most 400 ms). ask: the --place-window
    // command it waits for ("": none), null: shown, nothing waited for
    property string placeAsk: ""
    property bool placeReading: false
    function placing(ask) {
        placeAsk = ask || ""
        placeReading = ask !== null
        if (ask !== null)
            placeReadTimer.restart()
        else
            placeReadTimer.stop()
        if (ask)
            placeTimer.restart()
        else
            placeTimer.stop()
    }
    Timer {
        id: placeReadTimer
        interval: 400
        onTriggered: {
            pane.placeReading = false
            root.showPane(pane)
        }
    }
    Timer {
        id: placeTimer
        interval: 1000
        onTriggered: {
            pane.placeAsk = ""
            root.showPane(pane)
        }
    }
    onLoadedChanged: root.showPane(pane)
    onLoadErrorChanged: root.showPane(pane)

    // Opened again (here, or from another copy of the widget: Hub paneRaise):
    // forward, with focus, on the tab asked for
    function forward(tab) {
        if (tab)
            pane.tab = tab
        if (visible && visibility === Window.Minimized)
            showNormal()
        raise()
        requestActivate()
    }
    // What it does once it shows its chat (main.qml openPane's then): a reply
    // from a notification in its box, for a terminal that takes no text
    // (draft: you choose how it goes), Deny with a note's field (denying), or
    // Other…'s, a question's own words (typing)
    function act(then) {
        if (!then)
            return
        if (then.draft) {
            replyBox.text = then.draft
            replyBox.cursorPosition = replyBox.text.length
            pane.askHow = true
        }
        if (then.denying)
            askColumn.denyWithNote()
        if (then.typing)
            askColumn.typeAnswer()
    }

    // ---------------------------------------------------------------- how it looks

    // Text size: the desktop's font size times paneTextPercent (A− / A+, Ctrl+wheel, Ctrl+= / Ctrl+-)
    readonly property var scales: [90, 100, 115, 130, 150, 175, 200]
    readonly property int textPercent: Math.max(80, Math.min(200, Plasmoid.configuration.paneTextPercent || 115))
    readonly property real pt: surface.Kirigami.Theme.defaultFont.pointSize * textPercent / 100
    function zoom(step) {
        let i = scales.findIndex(v => v >= textPercent)
        i = i < 0 ? scales.length - 1 : i
        Plasmoid.configuration.paneTextPercent = step === 0 ? 115 : scales[Math.max(0, Math.min(scales.length - 1, i + step))]
    }

    // Colors: Claude's own orange for its dots, headings and the working
    // line; the theme's accent for you; inline code in the blue Claude's
    // terminal uses. (From the window's surface: a Window's own Kirigami.Theme
    // isn't the desktop's colors.)
    function hex(c) {
        return Qt.rgba(c.r, c.g, c.b, 1).toString()
    }
    function mix(c, a) {   // the text color, a of it over the background
        return Qt.tint(surface.Kirigami.Theme.backgroundColor, Qt.rgba(c.r, c.g, c.b, a))
    }
    readonly property color textColor: surface.Kirigami.Theme.textColor
    readonly property bool dark: surface.Kirigami.Theme.backgroundColor.hslLightness < 0.5
    readonly property color claudeColor: dark ? "#d97757" : "#c15f3c"
    readonly property color codeColor: dark ? "#b1b9f9" : "#5769f7"
    readonly property color mutedColor: mix(textColor, 0.62)
    readonly property color borderColor: mix(textColor, 0.16)
    readonly property color youColor: surface.Kirigami.Theme.focusColor
    // Bold, as Claude's terminal draws it (Breeze's blue there): the theme's
    // accent (focusColor: a Plasma 6 window's highlightColor is a pale
    // selection tint), darker on a light theme so it reads on white. Also
    // tool names and a table's head
    readonly property color strongColor: dark ? surface.Kirigami.Theme.focusColor
                                              : Qt.darker(surface.Kirigami.Theme.focusColor, 1.45)
    readonly property var mdStyle: ({
        pt: pt, mono: monoFamily, text: hex(textColor), muted: hex(mutedColor), strong: hex(strongColor), syntax: Code.syntaxColors(dark),
        accent: hex(claudeColor), heading: hex(claudeColor), code: hex(codeColor), codeBg: hex(mix(textColor, 0.09)),
        blockBg: hex(dark ? Qt.tint(surface.Kirigami.Theme.backgroundColor, Qt.rgba(0, 0, 0, 0.28)) : mix(textColor, 0.04)),
        border: hex(borderColor), link: hex(surface.Kirigami.Theme.linkColor)
    })
    // Code and changes (codehtml.mjs): a tool call's details
    readonly property var codeStyle: Code.palette(dark, hex(textColor), mdStyle.blockBg, monoFamily, pt,
                                                  codeFm.font.pointSize && codeFm.advanceWidth("M"))
    FontMetrics {
        id: codeFm   // (a character of code: where a wrapped line goes on, under the code)
        font.family: pane.monoFamily
        font.pointSize: pane.pt * 0.88
    }

    FontMetrics {
        id: fm
        font.family: pane.chatFamily
        font.pointSize: pane.pt
    }
    // Code in a fixed-width font: your terminal's (pane.py --terminal-font, kept
    // in the settings: known as the pane opens), if it's there; else the
    // desktop's, if it is one (it can be set to any font); else monospace
    FontMetrics {
        id: fixedFm
        font.family: surface.Kirigami.Theme.fixedWidthFont.family
    }
    readonly property string terminalFamily: Plasmoid.configuration.paneTerminalFont || ""
    readonly property string monoFamily: terminalFamily !== "" && Qt.fontFamilies().indexOf(terminalFamily) >= 0 ? terminalFamily
                                         : Math.abs(fixedFm.advanceWidth("iiii") - fixedFm.advanceWidth("WWWW")) < 0.5
                                         ? surface.Kirigami.Theme.fixedWidthFont.family : "monospace"
    // The conversation and your reply: in that font, as Claude's terminal shows
    // them (roomier than most desktop fonts, every letter on its own), or, set
    // so (Settings > Chats), the desktop's
    readonly property string chatFamily: Plasmoid.configuration.paneFont === "desktop"
                                         ? surface.Kirigami.Theme.defaultFont.family : monoFamily
    readonly property real gutter: Math.round(fm.height * 1.3)   // where the dots go

    // ● before a reply or a tool call, on its first line (blinking: still going)
    component Dot: Item {
        id: dotItem
        property color color
        property bool blinking: false
        property real gutter: 0
        property real lineHeight: 0
        Layout.preferredWidth: gutter
        Layout.preferredHeight: lineHeight
        Layout.alignment: Qt.AlignTop

        Rectangle {
            id: dot
            width: Math.round(dotItem.lineHeight * 0.42)
            height: width
            radius: width / 2
            x: Math.round((dotItem.gutter - width) * 0.4)
            anchors.verticalCenter: parent.verticalCenter
            color: dotItem.color

            SequentialAnimation on opacity {
                running: dotItem.blinking
                loops: Animation.Infinite
                onRunningChanged: if (!running) dot.opacity = 1
                NumberAnimation { to: 0.25; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
            }
        }
    }

    Shortcut {
        sequences: [StandardKey.ZoomIn, "Ctrl+="]
        onActivated: pane.zoom(1)
    }
    Shortcut {
        sequences: [StandardKey.ZoomOut]
        onActivated: pane.zoom(-1)
    }
    Shortcut {
        sequence: "Ctrl+0"
        onActivated: pane.zoom(0)
    }

    // A code block's Copy, and Ctrl+C across messages. quiet: no Copied under the
    // conversation (a code block's Copy says it itself)
    TextEdit {
        id: clipboard
        visible: false
    }
    function copyText(text, quiet) {
        clipboard.text = text
        clipboard.selectAll()
        clipboard.copy()
        clipboard.text = ""
        if (quiet)
            return
        info = i18n("Copied")
        infoBad = false
        infoTimer.restart()
    }

    // Where a reply's link goes, under the pointer while it's hovered (its
    // words can say anything): one tooltip for the pane, made only while a
    // link is hovered (replyText's onLinkHovered), not one in each message
    property Item linkBox: null   // (the reply whose link it is)
    property string linkShown: ""
    property point linkAt: Qt.point(0, 0)
    function linkHovered(box, link, at) {
        linkBox = link ? box : null
        linkAt = at
        linkShown = link.indexOf("copy:") === 0 ? "" : link   // (a code block's Copy: no address)
    }
    Loader {
        active: pane.linkShown !== "" && pane.linkBox !== null
        sourceComponent: PlasmaComponents3.ToolTip {
            parent: pane.linkBox
            x: pane.linkAt.x
            y: pane.linkAt.y + Kirigami.Units.gridUnit
            visible: true
            delay: Kirigami.Units.toolTipDelay
            textFormat: Text.PlainText
            text: pane.linkShown
        }
    }

    // ---------------------------------------------------------------- the conversation

    property string stamp: ""
    property int limit: 120
    readonly property int limitMax: 2000   // (pane.py's PANE_ITEMS_MAX: Show earlier goes no further)
    property bool more: false
    property bool loaded: false
    property string loadError: ""
    property bool loadMissing: false   // (no transcript: it hasn't started yet, or it's gone: a note, not an error)
    property var openTools: ({})   // key -> unfolded
    property string info: ""
    property bool infoBad: false

    ListModel {
        id: items
    }

    function reset() {
        tasksOpen = false
        agentsOpen = false
        offers = null
        offersAt = 0
        suggestions = []
        historyAt = -1
        items.clear()
        stamp = ""
        limit = 120
        more = false
        loaded = false
        loadError = ""
        openTools = {}
        info = ""
        review = null
        reviewFor = ""
        reviewLoading = false
        commitOpen = false
        commitText.text = ""   // (the chat before's message: this one's comes with its review)
        commitEdited = false
        undoAsk = ""
        // (the reply you were typing stays with its chat, for when you're back)
        if (draftKey !== "" && replyBox.text.trim() !== "")
            drafts[draftKey] = replyBox.text
        else
            delete drafts[draftKey]
        draftKey = (chat.host || "") + "\n" + chatId
        replyBox.text = drafts[draftKey] || ""
        delete drafts[draftKey]
        // (a message on its way to the chat before still goes, and its answer is
        // said here; the watcher's for it is left out)
        askHow = false
        bigPicture = ""
        lastItems = []
        watchLine = ""
        watchFailures = 0
        chaseUntil = 0
        askColumn.cancelDeny()
        answering = 0
        answerStale.stop()
        // (a recording for the chat before stops; words on their way go in its draft)
        if (dictating === "starting" || dictating === "recording")
            cancelDictation()
        offerSetup = false
        offerModel = false
        // (what's still on its way for the chat before is left out when it
        // comes, handle(): this one's is read now)
        loading = false
        loadAgain = false
        chatAtEnd = true   // (a chat opens at its end)
        chatTop = null
        const wasTab = tab
        tab = chat.tab || "chat"
        Qt.callLater(load)
        if (tab === "review" && wasTab === "review")
            Qt.callLater(loadReview)   // (the tab stays: onTabChanged doesn't read this one's)
    }
    // Claude moved the chat to the background under a new id (main.qml followPaneChat):
    // the same conversation goes on there, so what's shown, your reply and your
    // messages on their way stay, and its new transcript is read
    function follow() {
        const was = draftKey
        draftKey = (chat.host || "") + "\n" + chatId
        if (pendingSent.some(p => p.chat === chat.from))
            pendingSent = pendingSent.map(p => p.chat === chat.from ? Object.assign({}, p, { chat: chatId }) : p)
        // (and to its new id: the ones held or waiting their turn, and the one on
        // its way, which the next ones still wait for)
        for (const m of outbox.concat(pendingSent.filter(p => p.state === "held").map(p => p.out)))
            if (m.asked.draft === was) {
                Object.assign(m.asked, { chat: chatId, draft: draftKey })
                m.args = sendArgs(m.asked)
            }
        for (const cmd in runs)
            if ((runs[cmd].kind === "send" || runs[cmd].kind === "later") && runs[cmd].draft === was)
                Object.assign(runs[cmd], { chat: chatId, draft: draftKey })
        if (inFlight[was]) {
            delete inFlight[was]
            inFlight[draftKey] = true
        }
        if (dictateFor === was)
            dictateFor = draftKey
        stamp = ""   // (another transcript: its first read is taken; the watcher then waits on it)
        watchLine = ""
        watchFailures = 0
        loading = false   // (a read for the id it had is left out when it comes: handle())
        loadAgain = false
        Qt.callLater(load)
        if (tab === "review")
            Qt.callLater(loadReview)
    }
    property bool ready: false   // (nothing runs while the window is being made)
    onChatIdChanged: if (ready) (chat.from && draftKey === (chat.host || "") + "\n" + chat.from ? follow() : reset())
    Component.onCompleted: {
        ready = true
        reset()
        run("font", "--terminal-font")   // (changed since it was last found: from now on)
    }
    // (a picture or file for this window's reply box: main.qml's target for it)
    readonly property string pasteTarget: "pane:" + host + "|" + chatId
    Connections {
        target: root
        function onImagePasted(path, target) {   // (Ctrl+V: a picture, saved; an SSH host's copied there)
            if (target !== pane.pasteTarget)
                return
            const at = replyBox.cursorPosition
            replyBox.insert(at, (at > 0 && replyBox.text.charAt(at - 1).trim() !== "" ? " " : "") + "[Image: " + path + "] ")
            replyBox.forceActiveFocus()
        }
        function onFileAttached(path, target) {   // (a file dropped on the pane: named, as Claude's @ does)
            if (target !== pane.pasteTarget)
                return
            const at = replyBox.cursorPosition
            const named = /\s/.test(path) ? "@\"" + path + "\"" : "@" + path
            replyBox.insert(at, (at > 0 && replyBox.text.charAt(at - 1).trim() !== "" ? " " : "") + named + " ")
            replyBox.forceActiveFocus()
        }
        function onPaneNote(target, message) {
            if (target !== pane.pasteTarget)
                return
            pane.info = message
            pane.infoBad = true
            infoTimer.restart()
        }
    }

    // Shown (main.qml: showPane, each time it opens): at the end of its
    // conversation (laid out only now, the window was hidden), and what you
    // type goes in the reply box at once
    function opened() {
        requestActivate()
        if (conversationTab) {
            keepEnd()
            replyBox.forceActiveFocus()
        }
    }

    function paneArgs() {
        return (profileDir ? " --profile " + root.shellQuote(profileDir) : "")
               + (host ? " --host " + root.shellQuote(host) : "") + root.configDirArgs
    }

    // (the time makes a click run its command again; the conversation, read
    // every 1.5 s, goes without, so its name repeats while nothing changes:
    // every executable DataSource in plasmashell keeps each name, hub/Exec.qml)
    function run(kind, args, sent) {
        start(args + (kind === "conversation" ? "" : " # " + Date.now()),   // (read again and again: one name)
              { kind: kind, chat: chatId, host: host, target: row || chat, sent: sent || "", draft: draftKey })
    }
    // (asked: what run() keeps of it; a message that waited its turn, outbox, has the chat it was written to)
    function start(args, asked) {
        const cmd = "python3 -I " + root.shellQuote(root.codeDir + "pane.py") + " " + args
        runs[cmd] = asked
        runner.connectSource(cmd)
    }
    // command -> {kind, chat: the chat it's for, host, target: its row (openRow), sent: the box's text a message
    // took, draft: that chat's key in drafts}
    property var runs: ({})
    // A command whose answer never came (plasmashell lost it) is given up
    // after this, and a read runs again (hub/Exec.qml; a host's goes over ssh)
    readonly property int staleMs: 120000
    property bool loading: false
    property real loadingSince: 0
    property bool loadAgain: false   // (something changed while it was read: read it again then)

    function load() {
        if (!chatId)
            return
        if (loading && Date.now() - loadingSince < staleMs) {
            loadAgain = true
            return
        }
        loading = true
        loadingSince = Date.now()
        run("conversation", "--conversation " + root.shellQuote(chatId) + " --limit " + limit
            + (stamp ? " --if-changed " + root.shellQuote(stamp) : "") + paneArgs())
    }

    // Live (hub/Hub.qml): with the live hook, the conversation is read the
    // moment the chat does a step or changes state, and the timer is only
    // there for what comes without one (a long reply being written)
    readonly property bool followsLive: !host && root.watching && root.liveHook
    // (minimized, it reads nothing: once it's back, the conversation now)
    readonly property bool shown: visible && visibility !== Window.Minimized
    onShownChanged: if (shown && loaded) load()
    Timer {
        // (with the watcher, only for what it can't see: a moment it wasn't running)
        interval: pane.host ? 5000 : pane.watchOk ? 15000 : pane.followsLive ? 5000 : 1500
        running: pane.shown && pane.chatId !== ""
        repeat: true
        onTriggered: pane.load()
    }

    // The watcher: a chat of this computer is read the moment its transcript
    // changes (pane.py --conversation --wait: it waits for that, up to 50 s,
    // and runs again), so your message and what Claude writes show at once,
    // not at the next look. Not for an SSH host's (a look every 5 s, and
    // often just after you sent something, chase)
    readonly property bool watching: shown && !host && chatId !== "" && loaded && stamp !== "" && watchFailures < 3
    readonly property bool watchOk: watching && watchLine !== "" && watchFailures === 0
    property string watchLine: ""     // the one running (an answer from another is left out)
    property real watchStartedAt: 0
    property int watchFailures: 0     // (three in a row: looks only, till another chat is opened)
    onWatchingChanged: if (watching) watchNow()
    // (each time what's shown changes: one for it; the one before answers with
    // the next change, or in 50 s, and is left out)
    function watchNow() {
        if (!watching || watchRetry.running)
            return
        const line = "python3 -I " + root.shellQuote(root.codeDir + "pane.py") + " --conversation " + root.shellQuote(chatId)
                     + " --limit " + limit + " --if-changed " + root.shellQuote(stamp) + " --wait 50" + paneArgs()
        if (line === watchLine && Date.now() - watchStartedAt < watcher.staleMs)
            return
        watchLine = line
        watchStartedAt = Date.now()
        watcher.connectSource(line)
    }
    Exec {
        id: watcher
        staleMs: 70000   // (pane.py waits 50 s at the most)
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source !== pane.watchLine)
                return   // (for the chat before, or a run given up on)
            pane.watchLine = ""
            const result = root.helperResult(data)
            if (!result.ok) {
                pane.watchFailures += 1
                watchRetry.restart()
                return
            }
            pane.watchFailures = 0
            // (nothing new, at once: a pane.py that doesn't wait, an old one on the way: in 5 s, never
            // again and again. A change shows at once, and the next one is waited for)
            if (result.unchanged && Date.now() - pane.watchStartedAt < 1000) {
                watchRetry.restart()
                return
            }
            pane.takeConversation(result)
            Qt.callLater(pane.watchNow)
        }
    }
    Timer {
        id: watchRetry
        interval: 5000
        onTriggered: pane.watchNow()
    }

    // Just after your message went: read often till the conversation has it
    // (the watcher has it at once; this is for an SSH host's chat, and in case)
    property real chaseUntil: 0
    Timer {
        interval: pane.host ? 1000 : 400
        running: pane.shown && pane.chaseUntil > 0
        repeat: true
        onTriggered: {
            if (Date.now() > pane.chaseUntil || !pane.pendingSent.some(p => p.state === "sent" && p.chat === pane.chatId))
                pane.chaseUntil = 0
            else
                pane.load()
        }
    }
    Connections {
        target: Hub
        function onLive(views) {
            if (pane.shown && !pane.host && pane.sessionId && views.some(v => v.sessionId === pane.sessionId))
                pane.load()
        }
    }

    // A read's answer, or the watcher's. The two can cross: one read before
    // what's shown (a shorter transcript), or for another length (Show
    // earlier meanwhile), isn't taken
    function takeConversation(result) {
        loadError = ""
        if (result.unchanged || !fresher(result.stamp))
            return
        const following = !loaded || nearEnd()
        stamp = result.stamp || ""
        more = !!result.more
        lastItems = result.items || []
        const handoff = {}
        merge(withPending(lastItems, handoff), handoff)
        loaded = true
        if (following)
            keepEnd()
        Qt.callLater(watchNow)
    }
    function fresher(s) {   // (a stamp: "<size>:<time>/<length>"; a transcript only grows)
        const a = String(s || "").split("/")
        if (a.length > 1 && a[1] !== String(limit))
            return false
        if (!stamp)
            return true
        const b = stamp.split("/")
        return a[1] !== b[1] || Number(a[0].split(":")[0]) >= Number(b[0].split(":")[0])
    }

    // The items in place (by key): rows keep their state, the list its position.
    // handoff: {key: "pending-N"}, your message now in the conversation as key:
    // its row stays, under its new key (not taken out and made again)
    function merge(list, handoff) {
        const wanted = {}
        list.forEach(i => wanted[i.key] = true)
        if (handoff) {
            const shown = {}
            for (let i = 0; i < items.count; i++)
                shown[items.get(i).key] = i
            for (const key in handoff) {
                const at = shown[handoff[key]]
                if (at !== undefined && shown[key] === undefined && wanted[key])
                    items.setProperty(at, "key", key)
            }
        }
        for (let i = items.count - 1; i >= 0; i--) {
            if (!wanted[items.get(i).key])
                items.remove(i)
        }
        for (let i = 0; i < list.length; i++) {
            const it = list[i]
            const flat = { kind: it.kind, key: String(it.key), text: it.text || "", line: it.line || "",
                           name: it.name || "", status: it.status || "", input: it.input || "", output: it.output || "",
                           summary: it.summary || "", at: it.at || 0, bad: !!it.error, prev: i > 0 ? list[i - 1].kind : "",
                           diff: (it.diff || []).join("\n"), queued: !!it.queued, until: it.until || 0,
                           pictures: (it.pictures || []).join("\n"), here: (it.here || []).join("\n") }
            if (i < items.count && items.get(i).key === flat.key) {
                const old = items.get(i)
                if (old.text !== flat.text || old.status !== flat.status || old.output !== flat.output
                        || old.input !== flat.input || old.summary !== flat.summary || old.prev !== flat.prev || old.diff !== flat.diff
                        || old.queued !== flat.queued || old.until !== flat.until || old.pictures !== flat.pictures
                        || old.here !== flat.here)
                    items.set(i, flat)
            } else if (i < items.count) {
                items.insert(i, flat)
            } else {
                items.append(flat)
            }
        }
        while (items.count > list.length)
            items.remove(items.count - 1)
    }

    // The end of the conversation in view, with its working line, when you
    // were at the end (scrolled up, it stays where you are). Rich text rows
    // take a moment to get their height, and the list is laid out again as
    // the window shows: it keeps the end in view while they do, till you
    // scroll. (Not told by the list moving up: laid out again, it moves
    // itself, and the end was lost as the pane opened.)
    function nearEnd() {
        return list.originY + list.contentHeight - list.contentY - list.height < Kirigami.Units.gridUnit * 2
    }
    function followEnd() {
        list.contentY = Math.max(list.originY, list.originY + list.contentHeight - list.height)
    }
    function scrolling() {   // (a drag, or its scroll bar; the wheel: list's WheelHandler)
        return list.moving || scroll.PlasmaComponents3.ScrollBar.vertical.pressed
    }
    Timer {
        id: settle
        property int left: 0
        interval: 80
        repeat: true
        onTriggered: {
            if (pane.scrolling()) {
                stop()
                return
            }
            pane.followEnd()
            if (--left <= 0)
                stop()
        }
    }
    function keepEnd() {
        followEnd()
        settle.left = 10
        settle.restart()
    }
    // A row that gets its height as it's laid out, or the list's own height
    // changed (the window fitted beside the popup as it opens): the end, or
    // the message at the top (holdTop), is kept in the same frame
    function keepPlace() {
        if (scrolling())
            return
        if (settle.running)
            followEnd()
        else if (holdTop.running)
            showTop()
    }
    onChatStateChanged: {
        if (shown)
            load()   // (its turn began or ended, it asks something: the conversation now)
        if (loaded && nearEnd())
            keepEnd()   // (the working line comes or goes)
    }

    // ---------------------------------------------------------------- what the box offers
    //
    // As you type (pane.py --complete, read once a chat, again after a minute):
    // / at the start: Claude's commands, yours and the project's, and skills; @:
    // the project's files; ↑ / ↓ in an empty box (or on its first / last line):
    // your prompts, this chat's first, then your past ones in its folder. Tab or
    // Enter takes the one marked, Esc closes the list.
    property var offers: null          // {commands, files, history}
    property real offersAt: 0
    property var suggestions: []       // [{text, about, insert}]
    property int suggestion: 0
    property int tokenStart: -1
    property string dismissed: ""      // (the word Esc closed the list for)
    property int historyAt: -1
    property string historyDraft: ""

    function loadOffers() {
        if (!chatId || Date.now() - offersAt < 60000)
            return
        offersAt = Date.now()
        run("complete", "--complete " + root.shellQuote(chatId) + paneArgs())
    }

    function suggest() {
        const before = replyBox.text.slice(0, replyBox.cursorPosition)
        const command = /^\/([^\s]*)$/.exec(before)
        const file = /(^|\s)@("?)([^\s"]*)$/.exec(before)
        const token = command ? before : file ? before.slice(before.length - file[0].length + file[1].length) : ""
        if (!token || token === dismissed || !offers) {
            if (token && !offers)
                loadOffers()
            suggestions = []
            return
        }
        loadOffers()
        const q = (command ? command[1] : file[3]).toLowerCase()
        let found
        if (command) {
            found = offers.commands.filter(c => c.name.toLowerCase().indexOf(q) >= 0)
                .sort((a, b) => (a.name.toLowerCase().startsWith("/" + q) ? 0 : 1) - (b.name.toLowerCase().startsWith("/" + q) ? 0 : 1))
                .map(c => ({ text: c.name, about: c.about + (c.kind === "Claude" ? "" : " · " + c.kind), insert: c.name + " " }))
        } else {
            const rank = f => {
                const base = f.slice(f.lastIndexOf("/") + 1).toLowerCase()
                return base.startsWith(q) ? 0 : base.indexOf(q) >= 0 ? 1 : 2
            }
            found = offers.files.filter(f => f.toLowerCase().indexOf(q) >= 0).slice(0, 400)
                .sort((a, b) => rank(a) - rank(b) || a.length - b.length)
                .map(f => ({ text: "@" + f, about: "", insert: (/\s/.test(f) ? "@\"" + f + "\"" : "@" + f) + " " }))
        }
        tokenStart = before.length - token.length
        suggestions = found.slice(0, 8)
        suggestion = 0
    }

    function takeSuggestion(i) {
        const s = suggestions[i]
        if (!s)
            return
        const at = replyBox.cursorPosition
        replyBox.remove(tokenStart, at)
        replyBox.insert(tokenStart, s.insert)
        suggestions = []
    }

    // ↑ / ↓: your prompts, newest first, each once (what you were typing comes
    // back after the last). This chat's own first: the ones you just sent, then
    // the conversation's (Claude's prompt history, history.jsonl, has only some
    // of the messages sent from outside its terminal, and is read once a
    // minute); then your past prompts in its folder. (The list as it was at the
    // first ↑: the conversation can change while you go through it)
    property var historyList: []
    function promptHistory() {
        const out = [], seen = {}
        const add = t => {
            const text = String(t || "").trim(), key = norm(text)
            if (text && !seen[key]) {
                seen[key] = true
                out.push(text)
            }
        }
        const mine = pendingSent.filter(p => p.chat === chatId && p.host === (host || "") && p.state !== "held")
        for (let i = mine.length - 1; i >= 0; i--)
            add(mine[i].text)
        for (let i = lastItems.length - 1; i >= 0; i--)
            if (lastItems[i].kind === "you")
                add(lastItems[i].text)
        for (const t of offers ? offers.history : [])
            add(t)
        return out
    }
    function historyStep(step) {
        if (historyAt < 0)
            historyList = promptHistory()
        const list = historyList
        if (!list.length)
            return false
        if (historyAt < 0)
            historyDraft = replyBox.text
        const next = Math.max(-1, Math.min(list.length - 1, historyAt + step))
        if (next === historyAt)
            return true
        historyAt = next
        replyBox.text = next < 0 ? historyDraft : list[next]
        replyBox.cursorPosition = replyBox.text.length
        return true
    }

    // asked: the run it answers ({kind, chat, host, target}: run())
    function handle(kind, result, asked) {
        if (kind === "font") {
            if (result.ok && typeof result.family === "string" && result.family !== Plasmoid.configuration.paneTerminalFont)
                Plasmoid.configuration.paneTerminalFont = result.family
            return
        }
        if (kind === "send" || kind === "later")
            sentDone(asked, result)   // (shown as sent, or back in its box; the next one to that chat goes)
        // An answer for the chat shown before (another one was opened since,
        // reset()): none of it goes into this one's conversation, review, box
        // or buttons. A message sent there still goes where it was going.
        if (asked.chat !== chatId) {
            if (kind === "send" || kind === "later") {
                if (result.ok && result.how === "vscode" && result.link)
                    root.openVscodeLink(asked.target ? asked.target.sessionId || asked.chat : asked.chat, result.link, asked.host)
                else if (result.ok && result.how === "copy" && result.copied)
                    root.openRow(asked.target, asked.host)
                else if (!result.ok || result.how === "ask" || result.how === "copy") {
                    // (it didn't go, and the box it was in is this chat's now: said here)
                    info = i18n("Your message to %1 didn't go (it's back in its reply box): %2",
                                asked.target && asked.target.name ? asked.target.name : i18n("the chat before"),
                                result.message || i18n("its terminal takes no text"))
                    infoBad = true
                    infoTimer.restart()
                }
                // (it went: out of that chat's draft)
                if (kind === "send" && result.ok && result.how !== "ask" && !(result.how === "copy" && !result.copied)
                        && drafts[asked.draft] !== undefined) {
                    const left = withoutSent(drafts[asked.draft], asked.sent)
                    if (left.trim())
                        drafts[asked.draft] = left
                    else
                        delete drafts[asked.draft]
                }
            }
            if (kind !== "conversation" && kind !== "review" && kind !== "complete") {
                root.refresh()   // (what was done there shows in the popup)
                if (asked.host)
                    root.pollHost(asked.host)
            }
            return
        }
        if (kind === "complete") {
            if (result.ok)
                offers = { commands: result.commands || [], files: result.files || [], history: result.history || [] }
            Qt.callLater(suggest)
            return
        }
        if (kind === "conversation") {
            loading = false
            if (loadAgain) {
                loadAgain = false
                Qt.callLater(load)
            }
            if (!result.ok) {
                loadError = result.message || i18n("Can't read this chat")
                loadMissing = !!result.missing
                return
            }
            takeConversation(result)
            return
        }
        if (kind === "review") {
            reviewLoading = false
            review = result.ok ? result : null
            reviewFor = result.ok ? asked.chat : ""
            reviewError = result.ok ? "" : (result.message || "")
            if (result.ok && !commitEdited)
                commitText.text = result.message || ""
            return
        }
        info = result.message || (result.ok ? "" : i18n("That didn't work"))
        infoBad = !result.ok
        infoTimer.restart()
        if (kind === "send" && result.ok) {
            if (result.how === "ask") {
                askHow = true
                info = ""
                return
            }
            if (result.how === "vscode" && result.link)
                root.openVscodeLink(sessionId || chatId, result.link, host)
            if (result.how === "copy") {
                if (!result.copied) {   // (your message stays in the box)
                    infoBad = true
                    return
                }
                root.openRow(row || chat, host)
            }
            replyBox.text = withoutSent(replyBox.text, asked.sent)
            askHow = false
        }
        if (kind === "deny" || kind === "answer") {
            answering = Math.max(0, answering - 1)
            if (result.ok && asked.sent)   // (your reply answered it: out of the box)
                replyBox.text = withoutSent(replyBox.text, asked.sent)
        }
        if (kind === "commit" && result.ok) {
            commitOpen = false
            commitEdited = false
        }
        if (kind === "undo" || kind === "commit" || kind === "reviewed")
            loadReview()
        root.refresh()
        if (host)
            root.pollHost(host)
        stamp = ""   // (read it again now)
        load()
    }

    Exec {
        id: runner
        staleMs: pane.staleMs - 30000   // (less: the read load() gives up on runs again, not taken for one still running)
        onNewData: (source, data) => {
            disconnectSource(source)
            const asked = pane.runs[source] || { kind: "", chat: "", host: "", target: null }
            delete pane.runs[source]
            pane.handle(asked.kind, root.helperResult(data), asked)
        }
    }

    Timer {
        id: infoTimer
        interval: 12000
        onTriggered: pane.info = ""
    }

    // ---------------------------------------------------------------- dictating
    //
    // The microphone button: record, then whisper (whisper.cpp, or the
    // faster-whisper the widget sets up) writes it down here (dictate.py;
    // nothing leaves the computer) and it goes in at the cursor
    // "", "starting" (--status, --start on their way: no second recorder
    // meanwhile), "recording", "writing", "model" (a model being downloaded), "setup"
    property string dictating: ""
    property bool cancelStart: false     // cancelled (or the pane closed) while it started: stopped once it has
    property string dictateId: ""
    property real dictateSince: 0
    property string dictateFor: ""       // the chat (its draftKey) the words being written down are for
    property var dictateState: null      // dictate.py --status
    property bool offerModel: false      // (asks before it downloads one)
    property bool offerSetup: false      // (asks before it sets dictation up)

    function dictateRun(args) {
        dictateExec.connectSource("python3 -I " + root.shellQuote(root.codeDir + "dictate.py") + " " + args + " # " + Date.now())
    }
    function dictate() {
        if (dictating === "recording") {
            dictating = "writing"
            dictateFor = draftKey
            dictateRun("--stop " + dictateId + " --language " + root.shellQuote(Plasmoid.configuration.dictateLanguage || "auto"))
        } else if (dictating === "") {
            dictating = "starting"
            cancelStart = false
            dictateId = ""
            dictateRun("--status")
        }
    }
    function cancelDictation() {
        if (dictating === "starting") {
            // (the start sees it; when the pane closes, its answers don't
            // come, and dictate.py's --start stops one cancelled meanwhile)
            cancelStart = true
            if (dictateId)
                dictateRun("--cancel " + dictateId)
            return
        }
        if (dictating === "recording")
            dictateRun("--cancel " + dictateId)
        dictating = ""
    }
    function noteDictation(message, bad) {
        pane.info = message
        pane.infoBad = bad
        infoTimer.restart()
    }
    Exec {
        id: dictateExec
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (source.indexOf(" --status") >= 0) {
                if (pane.dictating !== "starting" || pane.dictateId)
                    return   // (an answer that came too late: dictateStale gave up on it)
                pane.dictateState = result
                if (result.ok && !pane.cancelStart) {
                    pane.dictateId = "r" + Date.now()
                    pane.dictateRun("--start " + pane.dictateId)   // (still "starting")
                    return
                }
                pane.dictating = ""
                if (pane.cancelStart || result.ok)
                    return   // (cancelled before it started)
                if (result.recorder && result.canSetup) {
                    pane.offerSetup = true
                } else if (result.recorder && result.tool && !result.model) {
                    pane.offerModel = true
                } else {
                    pane.noteDictation(i18n("To dictate, install %1.", (result.missing || []).join(i18n(" and "))), true)
                }
            } else if (source.indexOf(" --start ") >= 0) {
                const id = source.split(" --start ")[1].split(" ")[0]
                if (pane.cancelStart || id !== pane.dictateId || pane.dictating !== "starting") {
                    // (cancelled while it started, or given up on: it stops now, and its recording is deleted)
                    if (result.ok)
                        pane.dictateRun("--cancel " + id)
                    if (id === pane.dictateId)
                        pane.dictating = ""
                } else if (result.ok) {
                    pane.dictating = "recording"
                    pane.dictateSince = Date.now()
                    pane.recordedMs = 0
                } else {
                    pane.dictating = ""
                    pane.noteDictation(result.message, true)
                }
            } else if (source.indexOf(" --stop ") >= 0) {
                pane.dictating = ""
                if (result.ok && result.text && pane.dictateFor !== pane.draftKey) {
                    // (the pane shows another chat now: they go in the draft of the one they're for)
                    const was = pane.drafts[pane.dictateFor] || ""
                    pane.drafts[pane.dictateFor] = was + (was && was.slice(-1).trim() !== "" ? " " : "") + result.text + " "
                } else if (result.ok && result.text) {
                    const at = replyBox.cursorPosition
                    replyBox.insert(at, (at > 0 && replyBox.text.charAt(at - 1).trim() !== "" ? " " : "") + result.text + " ")
                    replyBox.forceActiveFocus()
                } else {
                    pane.noteDictation(result.message, true)
                }
            } else if (source.indexOf(" --get-model ") >= 0 || source.indexOf(" --setup") >= 0) {
                pane.dictating = ""
                pane.noteDictation(result.message, !result.ok)
            }
        }
    }
    Timer {
        id: dictateStale   // (an answer plasmashell lost doesn't keep the microphone greyed out)
        interval: 20000
        running: pane.dictating === "starting"
        onTriggered: {
            pane.cancelDictation()   // (what answers late stops)
            pane.dictating = ""
        }
    }
    property real recordedMs: 0          // (the time on the button while it records)
    Timer {
        interval: 1000
        repeat: true
        running: pane.dictating === "recording"
        onTriggered: pane.recordedMs = Date.now() - pane.dictateSince
    }

    // ---------------------------------------------------------------- replying

    property bool askHow: false   // its terminal takes no text: background or copy?
    // what you were typing to the other chats ("host\nchatId" -> text): this copy's
    // windows share it, so it's there whichever window the chat opens in again
    readonly property var drafts: root.paneDrafts
    property string draftKey: ""  // the chat the box's text is for

    // Your message, at once: Enter, and it's in the conversation (as being
    // sent, then as yours, till the transcript has it: withPending) and the
    // box is empty for the next one. Messages to a chat go one at a time, in
    // the order you sent them (outbox: one sent while another is on its way
    // waits for it, it's never dropped); to other chats meanwhile, at once.
    // One that doesn't go is back in its box, and the pane says why.
    property bool sending: false  // a message on its way (inFlight isn't empty)
    property var inFlight: ({})   // draft key -> true: a message to that chat on its way
    property var outbox: []       // [{args, asked}]: waiting for the one before to that chat
    property var pendingSent: []  // [{id, chat, host, text, at, state: "sending"|"sent", sentAt, known}]
    property int sentCount: 0
    property var lastItems: []    // pane.py's items as last read (the pending ones go after them)

    // (one whose answer never comes, plasmashell lost it: given up after
    // staleMs, so the ones after it go, and said)
    Timer {
        interval: 10000
        repeat: true
        running: pane.sending
        onTriggered: {
            for (const cmd in pane.runs) {
                const a = pane.runs[cmd]
                if ((a.kind === "send" || a.kind === "later") && Date.now() - (a.startedAt || 0) > pane.staleMs) {
                    delete pane.runs[cmd]
                    pane.handle(a.kind, { ok: false, message: i18n("No answer in time: look whether it got there before you send it again") }, a)
                }
            }
        }
    }

    function send(how, afterTurn) {
        const text = replyBox.text.trim()
        if (!text)
            return
        // (it goes on the command line: one too long for it is refused here, as
        // VS Code does, and stays in the box)
        if (text.length > 100000 || utf8Length(text) > 120000) {
            info = i18n("That message is too long")
            infoBad = true
            infoTimer.restart()
            return
        }
        // (a background chat that asks you something: your words answer it, as in its own prompt; never stopped for it)
        if (replyAnswers && !afterTurn && how !== "copy") {
            if (answering === 0)
                answer(replyAnswers === "question" ? "answer" : replyAnswers === "plan" ? "keep" : "deny", replyAnswers === "question" ? "" : text,
                       replyAnswers === "question" ? { [permission.questions[0].question]: [text] } : null, replyBox.text)
            return
        }
        // (shown at once where it goes to the chat itself: not a copy, put on the clipboard with
        // its tab opened, nor one for VS Code's input, or Enter for a terminal (a copy too):
        // the box keeps those till then)
        const shows = !afterTurn && how !== "copy"
                      && (how === "background" || route === "background" || route === "tmux")
        if (!shows && !afterTurn && (inFlight[draftKey] || outbox.some(m => m.asked.draft === draftKey)))
            return   // (one the box keeps is on its way: an Enter again doesn't send it twice)
        // (Claude at work: it waits a moment, queued, to be taken back, as ↑ does in Claude's terminal.
        // Not when its turn is over and only a background command runs: Claude takes it in at once)
        const holds = shows && chatState === "working" && !(row && row.reason === "background shell")
        const id = ++sentCount
        const asked = { kind: afterTurn ? "later" : "send", chat: chatId, host: host, target: row || chat,
                        sent: shows || afterTurn ? "" : replyBox.text, draft: draftKey, text: text, id: id, startedAt: 0,
                        how: how || "auto" }
        const out = { asked: asked, args: sendArgs(asked) }
        if (!holds)
            outbox = outbox.concat([out])
        if (shows) {
            const known = {}   // (your prompts shown now: the one this becomes is another)
            for (const it of lastItems)
                if (it.kind === "you")
                    known[String(it.key)] = true
            now = Date.now()
            pendingSent = pendingSent.concat([{ id: id, chat: chatId, host: host || "", text: text, at: Date.now(),
                                                state: holds ? "held" : "sending", sentAt: 0, known: known,
                                                until: holds ? Date.now() + holdMs : 0, out: holds ? out : null }])
            replyBox.text = ""
            historyAt = -1
            suggestions = []
            askHow = false
            showPending()
            keepEnd()
        } else if (afterTurn) {
            replyBox.text = ""
        }
        pump()
    }
    // pane.py --send's arguments for your message (asked), to the chat shown
    function sendArgs(asked) {
        return "--send " + root.shellQuote(asked.chat) + " --text " + root.shellQuote(asked.text)
               + (sessionId ? " --session " + root.shellQuote(sessionId) : "") + " --how " + asked.how
               + (asked.kind === "later" ? " --after-turn --name " + root.shellQuote(chatName) : "") + paneArgs()
    }
    // Held (sent while Claude works): it goes to Claude when its moment is up
    // (Claude takes it in at its next step), or at once with Send now; Edit
    // (or ↑ in an empty box) takes it back into its box, Remove drops it
    readonly property int holdMs: 5000
    readonly property real queueButtonHeight: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
    property real now: 0   // (the countdowns', while one is held)
    Timer {
        interval: 250
        repeat: true
        running: pane.pendingSent.some(p => p.state === "held")
        onTriggered: {
            pane.now = Date.now()
            for (const p of pane.pendingSent.filter(x => x.state === "held" && x.until <= pane.now))
                pane.release("pending-" + p.id)
        }
    }
    function heldOf(key) {
        return pendingSent.find(p => "pending-" + p.id === key && p.state === "held") || null
    }
    function release(key) {
        const p = heldOf(key)
        if (!p)
            return
        p.state = "sending"
        outbox = outbox.concat([p.out])
        pendingSent = pendingSent.slice()
        if (p.chat === chatId)
            showPending()
        pump()
    }
    function takeBack(key, edit) {
        const p = heldOf(key)
        if (!p)
            return false
        pendingSent = pendingSent.filter(x => x !== p)
        if (edit)
            giveBack(p.out.asked)
        if (p.chat === chatId)
            showPending()
        replyBox.forceActiveFocus()
        return true
    }
    // ↑ in an empty box: the newest one held for this chat, back in it
    function takeBackLast() {
        const mine = pendingSent.filter(p => p.state === "held" && p.chat === chatId && p.host === (host || ""))
        return mine.length > 0 && takeBack("pending-" + mine[mine.length - 1].id, true)
    }
    // Each chat's next message, once the one before to it has its answer
    function pump() {
        const left = []
        for (const m of outbox) {
            if (inFlight[m.asked.draft]) {
                left.push(m)
                continue
            }
            inFlight[m.asked.draft] = true
            m.asked.startedAt = Date.now()
            start(m.args + " # " + Date.now() + "." + m.asked.id, m.asked)
        }
        outbox = left
        sending = Object.keys(inFlight).length > 0
    }
    // What came of a message (its answer): gone to the chat, shown as yours
    // till the conversation has it (read often meanwhile); in VS Code's input
    // or on the clipboard, not here; else back in its box
    function sentDone(asked, result) {
        delete inFlight[asked.draft]
        const p = pendingSent.find(x => x.id === asked.id)
        if (p) {
            if (result.ok && (result.how === "typed" || result.how === "background")) {
                p.state = "sent"
                p.sentAt = Date.now()
                pendingSent = pendingSent.slice()
                chaseUntil = Date.now() + 10000
            } else {
                pendingSent = pendingSent.filter(x => x !== p)
                if (!(result.ok && (result.how === "vscode" || (result.how === "copy" && result.copied))))
                    giveBack(asked)
            }
            if (asked.chat === chatId)
                showPending()
        } else if (asked.kind === "later" && !result.ok) {
            giveBack(asked)   // (Send when this turn ends: its box was emptied as you clicked)
        }
        Qt.callLater(pump)
    }
    // (back in the box of the window that shows its chat now, this one or
    // another; else in its draft, for when it's opened)
    function giveBack(asked) {
        const win = asked.draft === draftKey ? pane : root.paneWindows.find(w => w.draftKey === asked.draft) || null
        if (win) {
            win.putBack(asked.text)
        } else {
            const was = drafts[asked.draft] || ""
            drafts[asked.draft] = asked.text + (was.trim() ? "\n" + was : "")
        }
    }
    function putBack(text) {   // (before what's in the box now)
        const now = replyBox.text
        replyBox.text = text + (now.trim() ? "\n" + now : "")
        replyBox.cursorPosition = text.length
    }

    // A selection across messages, as on a web page (VS Code's tab): each
    // message is a text of its own, where a drag selects only in it; one
    // that goes on into the next ones selects them too, the whole of each it
    // passes and the last up to the pointer. Ctrl+C in a message copies all
    // of it, each message's text after a blank line
    // (each by its key, its index a hint: a new step can take rows off the top, every index moving)
    property string selFrom: ""   // the message the drag started in
    property int selFromAt: -1
    property string selLast: ""   // (its text box keeps its selection till another is pressed)
    property int selLastAt: -1
    property var selOthers: ({})  // key -> its index when selected: the other messages selected now
    function boxAt(index) {
        const d = index >= 0 ? list.itemAtIndex(index) : null
        return d && d.textBox ? d.textBox : null
    }
    function keyAt(index) {
        return index >= 0 && index < items.count ? items.get(index).key : ""
    }
    function selIndex(key, at) {   // (at: where it was)
        if (key === "")
            return -1
        if (keyAt(at) === key)
            return at
        for (let i = items.count - 1; i >= 0; i--)
            if (items.get(i).key === key)
                return i
        return -1
    }
    function selectStart(p) {   // (p: in the list)
        for (const k in selOthers) {
            const b = boxAt(selIndex(k, selOthers[k]))
            if (b)
                b.deselect()
        }
        selOthers = {}
        const i = list.indexAt(p.x + list.contentX, p.y + list.contentY)
        const last = selIndex(selLast, selLastAt)
        if (last >= 0 && last !== i && boxAt(last))
            boxAt(last).deselect()
        selFromAt = boxAt(i) ? i : -1
        selFrom = keyAt(selFromAt)
        selLast = selFrom
        selLastAt = selFromAt
    }
    function selectAcross(p) {
        const i = list.indexAt(p.x + list.contentX, p.y + list.contentY)
        const from = selIndex(selFrom, selFromAt)
        if (from < 0 || i < 0)
            return
        selFromAt = from
        const next = {}
        if (i !== from) {
            const down = i > from
            for (let k = down ? from + 1 : i; down ? k <= i : k < from; k++) {
                const b = boxAt(k)
                if (!b)
                    continue   // (a tool call, a note: no text to select)
                if (k === i) {
                    const q = b.mapFromItem(list, p.x, p.y)
                    const at = b.positionAt(q.x, q.y)
                    if (down)
                        b.select(0, at)
                    else
                        b.select(at, b.length)
                } else {
                    b.selectAll()
                }
                next[keyAt(k)] = k
            }
        }
        for (const k in selOthers) {
            if (next[k] === undefined) {
                const b = boxAt(selIndex(k, selOthers[k]))
                if (b)
                    b.deselect()
            }
        }
        selOthers = next
    }
    function selectionText() {
        return Object.keys(selOthers).map(k => selIndex(k, selOthers[k])).concat([selIndex(selFrom, selFromAt)])
            .filter(i => i >= 0).sort((a, b) => a - b)
            .map(i => boxAt(i)).filter(b => b && b.selectedText !== "")
            .map(b => b.selectedText.replace(/[\u2028\u2029]/g, "\n")).join("\n\n")
    }
    function copyAcross(event) {   // (Ctrl+C in a message: with others selected too, all of it)
        if (event.matches(StandardKey.Copy) && Object.keys(selOthers).length > 0) {
            copyText(selectionText())
            event.accepted = true
        }
    }

    // The pictures a text names ([Image: /path]), each once; the text with
    // each as [Image #1], [Image #2]…, as Claude's terminal writes them (its
    // picture under it). (The pattern written in each: a regex kept in a
    // property is Qt's QRegularExpression, with no .source)
    function pictureNames(text) {
        const out = [], pattern = /\[Image: (\/[^\]\n]+)\]/g
        let m
        while ((m = pattern.exec(text || "")) !== null)
            if (out.indexOf(m[1]) < 0)
                out.push(m[1])
        return out
    }
    function shownText(text) {
        const seen = {}
        let n = 0
        return String(text || "").replace(/\[Image: (\/[^\]\n]+)\]/g, (all, path) => "[Image #" + (seen[path] || (seen[path] = ++n)) + "]")
    }

    // A picture of yours, big (its thumbnail clicked): over the pane, till a click, × or Esc
    property string bigPicture: ""
    Shortcut {
        sequence: "Escape"
        enabled: pane.bigPicture !== ""
        onActivated: pane.bigPicture = ""
    }

    // The conversation with your messages on their way after it: each till
    // the conversation has it (a prompt of yours that wasn't there when you
    // sent it, with its words; or, after a moment, any new one of this
    // computer's chat: Claude can have changed them, a picture's say), or
    // 30 s after it went (it went: the conversation just doesn't show it)
    function norm(s) {
        return String(s || "").replace(/\s+/g, " ").trim()
    }
    function withPending(list, handoff) {   // (handoff: {key: "pending-N"}, each one found as key)
        const mine = pendingSent.filter(p => p.chat === chatId && p.host === (host || ""))
        if (!mine.length)
            return list
        const claimed = {}
        const now = Date.now()
        const done = {}
        for (const p of mine) {
            if (p.state === "held")
                continue   // (not sent yet: nothing in the conversation is it)
            const want = norm(p.text)
            const found = list.find(it => {
                const key = String(it.key)
                if (it.kind !== "you" || p.known[key] || claimed[key])
                    return false
                const said = norm(it.text)
                const cut = said.endsWith("…") ? said.slice(0, -1).trim() : ""
                return said === want || (cut !== "" && want.indexOf(cut) === 0)
                    || (!p.host && p.state === "sent" && now - p.sentAt > 3000 && (it.at || 0) >= p.at - 2000)
            })
            if (found) {
                claimed[String(found.key)] = true
                if (handoff)
                    handoff[String(found.key)] = "pending-" + p.id
            }
            if (found || (p.state === "sent" && now - p.sentAt > 30000))
                done[p.id] = true
        }
        if (Object.keys(done).length)
            pendingSent = pendingSent.filter(p => !done[p.id])
        return list.concat(pendingSent.filter(p => p.chat === chatId && p.host === (host || ""))
                                      .map(p => ({ kind: "you", key: "pending-" + p.id, text: p.text, status: p.state, at: p.at, until: p.until,
                                                   pictures: pictureNames(p.text) })))
    }
    function showPending() {
        if (loaded) {
            const following = nearEnd()
            const handoff = {}
            merge(withPending(lastItems, handoff), handoff)
            if (following)
                keepEnd()
        }
    }
    function utf8Length(text) {
        let n = 0
        for (const c of text) {
            const code = c.codePointAt(0)
            n += code < 0x80 ? 1 : code < 0x800 ? 2 : code < 0x10000 ? 3 : 4
        }
        return n
    }
    // The box without the message that went (what you typed after it stays)
    function withoutSent(box, sent) {
        return sent && box.indexOf(sent) === 0 ? box.slice(sent.length).replace(/^\s+/, "") : box
    }

    readonly property string routeHint: {
        const where = host ? " " + i18n("(on %1)", root.hostLabel(host)) : ""
        if (replyAnswers === "deny")
            return i18n("It's asking for a permission: your message denies it and goes to Claude with the No, as if you typed it in its prompt.") + where
        if (replyAnswers === "plan")
            return i18n("It's asking about its plan: your message keeps it planning and goes to Claude as what to change.") + where
        if (replyAnswers === "question")
            return i18n("It's asking you a question: your message is your answer, in your own words.") + where
        if (replyAnswers === "decline")
            return i18n("It's asking you questions: your message declines them and goes to Claude with the No.") + where
        if (route === "tmux")
            return i18n("Typed into its tmux pane.") + where
        if (route === "vscode")
            return i18n("Goes into the chat's input in VS Code: press Enter there.") + where
        if (route === "terminal")
            return i18n("Its terminal takes no text from outside: Enter copies your message and opens its tab, to paste it there. Send, go on in the background: Claude there quits and the chat goes on in the background.") + where
        if (row && row.pid && row.kind === "bg")
            return i18n("Goes into its background session, as if you typed it there.") + where
        return i18n("The chat goes on in the background with your message.") + where
    }

    // ---------------------------------------------------------------- permission prompt

    property int answering: 0   // answers on their way

    // (answers that never come back: the buttons work again after a while)
    Timer {
        id: answerStale
        interval: pane.staleMs
        onTriggered: pane.answering = 0
    }

    // answers: a question's, {question: [labels or text]} (decision "answer").
    // It answers what the pane shows only: the hook's request, or in tmux
    // the tool call it asks about (--expect: if it asks something else now,
    // nothing is pressed, and the pane says so)
    function answer(decision, note, answers, sent) {   // (sent: your reply it is, out of the box once it went)
        const p = permission
        if (!p || (p.answer !== "hook" && p.answer !== "keys"))
            return
        answering += 1
        answerStale.restart()
        if (p.answer === "hook")
            run(decision === "deny" ? "deny" : "answer", "--answer " + root.shellQuote(p.request) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (answers ? " --answers " + root.shellQuote(JSON.stringify(answers)) : "")
                + (host ? " --host " + root.shellQuote(host) : "") + root.configDirArgs, sent)
        else if (p.answer === "keys")
            run(decision === "deny" ? "deny" : "answer", "--keys " + root.shellQuote(sessionId) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (p.toolUse ? " --expect " + root.shellQuote(p.toolUse) : "") + paneArgs(), sent)
    }

    // ---------------------------------------------------------------- review

    property var review: null
    property string reviewFor: ""   // the chat that review is of: Undo and Commit act on that one only
    readonly property bool reviewIsThis: review !== null && reviewFor !== "" && reviewFor === chatId
    property bool reviewLoading: false
    property string reviewError: ""
    property var openFiles: ({})
    property bool commitOpen: false
    property bool commitEdited: false
    property string undoAsk: ""   // "*": all, else a file's path, asked to confirm

    function loadReview() {
        if (!chatId)
            return
        reviewLoading = true
        run("review", "--review " + root.shellQuote(chatId) + paneArgs())
    }
    // From Chat to Steps and back the list changes: it stays at its end if
    // it was, else on the message at its top. The list shows listTab's
    // items, set only here, after where it was is noted, and laid out again
    // at once: no frame shows it elsewhere (Steps' tool calls came in below
    // the view, and for a few frames it showed an older part of the chat)
    property string listTab: "chat"
    onTabChanged: {
        if (tab === "review" && review === null)
            loadReview()
        if (chatTab) {   // (leaving the Chat or Steps tab)
            chatAtEnd = !loaded || nearEnd()
            chatTop = chatAtEnd ? null : topMessage()
        }
        chatTab = tab === "chat" || tab === "steps"
        if (chatTab) {
            if (listTab !== tab) {
                listTab = tab
                list.forceLayout()
            }
            if (chatAtEnd || !chatTop) {   // (only tool calls below its top: the last turn's)
                keepEnd()
            } else {
                showTop()
                holdTop.restart()
            }
        }
    }
    property bool chatTab: true
    property bool chatAtEnd: true
    property var chatTop: null   // [key, how far below the list's top it was]
    // (rows shown for the first time get their height as they're laid out:
    // the message stays where it was while they do, unless you scroll)
    Timer {
        id: holdTop
        interval: 800
    }

    // The message at the top of the list (not a tool call: it's on both
    // tabs): [its key, how far below the list's top it is]
    function topMessage() {
        for (let i = Math.max(0, list.indexAt(list.width / 2, list.contentY)); i < items.count; i++) {
            const entry = list.itemAtIndex(i)
            if (entry && entry.kind !== "tool" && entry.y + entry.height > list.contentY)
                return [entry.key, entry.y - list.contentY]
        }
        return null
    }
    function showTop() {
        for (let i = 0; chatTop && i < items.count; i++) {
            const entry = items.get(i).key === chatTop[0] ? list.itemAtIndex(i) : null
            if (entry) {
                list.contentY = Math.max(list.originY, Math.min(entry.y - chatTop[1],
                                                                list.originY + list.contentHeight - list.height))
                return
            }
        }
    }

    readonly property real editedAt: row && row.review ? row.review.editedAt || 0 : 0
    onEditedAtChanged: if (tab === "review") loadReview()

    function undo(path) {
        undoAsk = ""
        if (!reviewIsThis)
            return   // (the files shown aren't this chat's: its own review comes first)
        run("undo", "--undo " + root.shellQuote(chatId) + (path !== "*" ? " --file " + root.shellQuote(path) : "") + paneArgs())
    }

    function totals(files) {
        let added = 0, removed = 0
        for (const f of files || []) {
            added += f.added || 0
            removed += f.removed || 0
        }
        return [added, removed]
    }

    // (the send buttons at their widest, all three, never shown: the window's
    // least width doesn't change as the chat's state does, so it doesn't resize)
    Row {
        id: widestSend
        visible: false
        spacing: Kirigami.Units.smallSpacing
        PlasmaComponents3.Button { icon.name: Icons.plasma.copy; text: i18n("Copy and open its tab") }
        PlasmaComponents3.Button { icon.name: Icons.plasma.later; text: i18n("Send when this turn ends") }
        PlasmaComponents3.Button { icon.name: Icons.plasma.send; text: i18n("Send, go on in the background") }
    }

    // ---------------------------------------------------------------- what's shown

    Rectangle {
        id: surface
        anchors.fill: parent
        color: Kirigami.Theme.backgroundColor
        Kirigami.Theme.colorSet: Kirigami.Theme.Window
        Kirigami.Theme.inherit: false
        // Files and pictures dropped on the pane go in your reply (a picture as
        // a pasted one, a file named with @), while the Chat tab shows
        DropArea {
            id: dropArea
            anchors.fill: parent
            z: 10
            enabled: pane.conversationTab
            keys: ["text/uri-list"]
            onDropped: drop => {
                const paths = (drop.urls || []).map(u => String(u)).filter(u => u.startsWith("file://"))
                                               .map(u => decodeURIComponent(u.slice(7)))
                if (paths.length) {
                    root.attachFiles(paths, pane.host, pane.pasteTarget)
                    drop.acceptProposedAction()
                }
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                visible: dropArea.containsDrag
                radius: Kirigami.Units.cornerRadius * 2
                color: Qt.rgba(Kirigami.Theme.focusColor.r, Kirigami.Theme.focusColor.g, Kirigami.Theme.focusColor.b, 0.12)
                border.width: 2
                border.color: Kirigami.Theme.focusColor

                PlasmaComponents3.Label {
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: pane.host ? i18n("Drop a picture: it's copied to %1 for your reply", root.hostLabel(pane.host))
                                    : i18n("Drop to add it to your reply")
                    font.pointSize: pane.pt * 1.2
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            // Its name, where it runs and what it's doing
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    Layout.preferredWidth: Math.round(fm.height * 0.5)
                    Layout.preferredHeight: Layout.preferredWidth
                    radius: width / 2
                    color: root.stateColor(pane.chatState)
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    text: pane.chatName
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    font.pointSize: pane.pt * 1.25
                    font.weight: Font.Bold
                }
                Tag {
                    visible: pane.host !== ""
                    text: root.hostLabel(pane.host)
                    tooltip: root.isContainer(pane.host) ? i18n("This chat runs in the container %1.", root.hostLabel(pane.host))
                                                         : i18n("This chat runs on the SSH host %1.", pane.host)
                }
                // what it's doing, in its state's color
                Rectangle {
                    readonly property color tone: pane.row ? root.stateColor(pane.chatState) : pane.mutedColor
                    implicitWidth: stateLabel.implicitWidth + Kirigami.Units.largeSpacing * 1.5
                    implicitHeight: stateLabel.implicitHeight + Kirigami.Units.smallSpacing
                    radius: height / 2
                    color: Qt.rgba(tone.r, tone.g, tone.b, 0.16)

                    PlasmaComponents3.Label {
                        id: stateLabel
                        anchors.centerIn: parent
                        textFormat: Text.PlainText
                        text: pane.row ? root.stateText(pane.row) : i18n("not running")
                        color: pane.chatState === "waiting" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
                        font.weight: pane.chatState === "waiting" ? Font.Bold : Font.Normal
                    }
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.zoomOut
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Smaller text")
                    enabled: pane.textPercent > pane.scales[0]
                    onClicked: pane.zoom(-1)
                    PlasmaComponents3.ToolTip.text: i18n("Smaller text (Ctrl+-, Ctrl+wheel)")
                    PlasmaComponents3.ToolTip.visible: hovered
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.zoomIn
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Larger text")
                    enabled: pane.textPercent < pane.scales[pane.scales.length - 1]
                    onClicked: pane.zoom(1)
                    PlasmaComponents3.ToolTip.text: i18n("Larger text (Ctrl+=, Ctrl+wheel; Ctrl+0: as it was)")
                    PlasmaComponents3.ToolTip.visible: hovered
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.openWindow
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Open its window")
                    onClicked: root.openRow(pane.row || pane.chat, pane.host)

                    TipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Open its window")
                        subText: i18n("The terminal or VS Code tab the chat runs in; a chat that isn't open reopens in a terminal or in VS Code, as the Terminal | VS Code switch of Recent chats says.")
                    }
                }
            }
            // where it runs, and its folder
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Math.round(fm.height * 0.5) + Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Tag {
                    text: pane.where === "background" ? i18nc("where a chat runs", "Background")
                          : pane.where === "closed" ? i18nc("where a chat runs", "Not open")
                          : pane.where === "claude" ? i18nc("where a chat runs: the Claude Code extension's panel", "Claude Code panel")
                          : pane.where === "tmux" ? "Tmux"
                          : pane.where === "vscode" ? i18nc("where a chat runs", "VS Code terminal")
                          : i18nc("where a chat runs", "Terminal")
                    tooltip: pane.where === "background" ? i18n("A background chat: Claude's background service runs it, with no terminal of its own. Open its window to see it in a terminal (claude attach).")
                             : pane.where === "closed" ? i18n("No terminal or tab has it open: a reply goes on with it in the background.")
                             : pane.where === "claude" ? i18n("It runs in VS Code's Claude Code panel (the Claude Code extension).")
                             : pane.where === "tmux" ? i18n("It runs in a tmux pane.")
                             : pane.where === "vscode" ? i18n("It runs in a terminal of VS Code.")
                             : pane.row && pane.row.terminalApp ? i18n("It runs in a terminal (%1).", pane.row.terminalApp)
                             : i18n("It runs in a terminal.")
                }
                // a background session shown in a terminal too (claude attach)
                Tag {
                    readonly property var shownIn: pane.where === "background" && pane.row && pane.row.attached ? pane.row.attached : null
                    visible: shownIn !== null
                    text: !shownIn ? "" : shownIn.in === "tmux" ? "Tmux"
                          : shownIn.in === "vscode" ? i18nc("where a chat runs", "VS Code terminal") : i18nc("where a chat runs", "Terminal")
                    tooltip: !shownIn ? "" : shownIn.app ? i18n("Shown in a terminal too (%1): claude attach.", shownIn.app)
                                                         : i18n("Shown in a terminal too: claude attach.")
                }
                // what its row in the list says of it too: shared, its permission
                // mode, its plan, its subagents (SessionRow.qml's tags)
                Tag {
                    readonly property var info: pane.row ? pane.row.shared : null
                    visible: !!info
                    icon: Icons.plasma.share
                    text: info && info.forkOf ? i18n("Shared copy") : i18n("Shared")
                    tooltipTitle: info && info.forkOf ? i18n("Copy of a shared chat") : i18n("Shared chat")
                    tooltip: !info ? "" : info.forkOf
                             ? i18n("A copy of a chat shared between the %1 profiles: Claude forked it into a chat of its own on %2, so new messages here are only on %2.",
                                    info.profiles.join(" + "), info.forkOn)
                             : i18n("This chat is shared between the %1 profiles: it continues on whichever account you open it with. Only one Claude can have it open at a time.",
                                    info.profiles.join(" + "))
                }
                Tag {
                    readonly property string mode: pane.row && pane.row.peek ? pane.row.peek.mode || "" : ""
                    visible: root.modeText(mode) !== ""
                    text: root.modeText(mode)
                    warning: mode === "bypassPermissions"
                    tooltipTitle: i18n("Permission mode: %1", root.modeText(mode))
                    tooltip: root.modeHint(mode)
                }
                Tag {
                    visible: !!pane.row && !!pane.row.plan
                    icon: Icons.plasma.plan
                    text: i18nc("a chat's plan, click to open it", "Plan")
                    clickable: true
                    onClicked: root.openPlan(pane.row.plan.slug, pane.profileDir, pane.host)
                    tooltipTitle: pane.row && pane.row.plan ? pane.row.plan.title : ""
                    tooltip: pane.host ? i18n("The plan this chat made. Click to read it: a copy, fetched from %1.", root.hostLabel(pane.host))
                                       : i18n("The plan this chat made. Click to read it, rendered.")
                }
                // (click: what each one is doing, in the strip under the header)
                Tag {
                    readonly property var agents: pane.agents
                    visible: agents !== null
                    text: agents ? i18nc("subagents finished/total", "Agents %1/%2", agents.done, agents.total) : ""
                    active: agents !== null && agents.running > 0
                    clickable: true
                    onClicked: pane.agentsOpen = !pane.agentsOpen
                    tooltipTitle: i18n("Subagents")
                    tooltip: !agents ? "" : i18n("%1 done, %2 running, %3 stopped", agents.done, agents.running, agents.stopped)
                                            + (agents.failed ? i18n(", %1 failed", agents.failed) : "") + ". "
                                            + i18n("Click to %1 what each one is doing.", pane.agentsOpen ? i18n("hide") : i18n("show"))
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: (pane.host ? root.hostLabel(pane.host) + ":" : "") + (pane.row ? pane.row.cwdShort || pane.row.cwd || "" : pane.chat.cwd || "")
                    font.family: pane.monoFamily
                    font.pointSize: pane.pt * 0.85
                    color: pane.mutedColor
                    elide: Text.ElideMiddle
                }
            }

            // Its tasks, when it has a task list: a progress bar and "3/7 · what it's on", folded (without
            // one, its subagents: "Agents 1/3 · what the running one does"); unfolded, the tasks (✓ done,
            // ▸ the one it's on, ○ to do) and its subagents as under its row in the popup (AgentTree.qml:
            // what each does now, the running ones first; click one for more), made only then (the
            // window opens as quickly). The header's Agents tag unfolds only its subagents.
            ColumnLayout {
                visible: pane.tasks !== null || pane.agents !== null
                Layout.fillWidth: true
                spacing: 0

                MouseArea {
                    id: tasksFold
                    Layout.fillWidth: true
                    implicitHeight: tasksLine.implicitHeight + Kirigami.Units.smallSpacing
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    activeFocusOnTab: true
                    onClicked: pane.toggleStrip()
                    Keys.onReturnPressed: pane.toggleStrip()
                    Keys.onSpacePressed: pane.toggleStrip()
                    Accessible.role: Accessible.Button
                    Accessible.name: tasksText.text

                    RowLayout {
                        id: tasksLine
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: pane.tasksOpen || pane.agentsOpen ? Icons.plasma.unfolded : Icons.plasma.folded
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Layout.preferredWidth
                            opacity: 0.7
                        }
                        Rectangle {
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 5
                            Layout.preferredHeight: Math.round(Kirigami.Units.gridUnit * 0.3)
                            radius: height / 2
                            color: pane.mix(pane.textColor, 0.15)

                            Rectangle {
                                width: parent.width * (pane.tasks ? pane.tasks.done / Math.max(1, pane.tasks.total)
                                                       : pane.agents ? pane.agents.done / Math.max(1, pane.agents.total) : 0)
                                height: parent.height
                                radius: parent.radius
                                color: Kirigami.Theme.positiveTextColor
                            }
                        }
                        PlasmaComponents3.Label {
                            id: tasksText
                            Layout.fillWidth: true
                            textFormat: Text.PlainText
                            text: pane.tasks ? i18nc("tasks done/total · the one it's on", "%1/%2 · %3", pane.tasks.done, pane.tasks.total,
                                                     pane.tasks.current || (pane.tasks.done >= pane.tasks.total ? i18n("all done") : i18n("next: %1", pane.nextTask)))
                                  : pane.agents ? i18nc("subagents finished/total · what they do", "Agents %1/%2 · %3", pane.agents.done, pane.agents.total, pane.agentsNow)
                                  : ""
                            font.pointSize: pane.pt * 0.9
                            font.underline: tasksFold.containsMouse || tasksFold.activeFocus
                            elide: Text.ElideRight
                        }
                    }
                }
                Loader {
                    active: (pane.tasksOpen && pane.tasks !== null) || (pane.agentsOpen && pane.agents !== null)
                    visible: active
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                    // (a long list scrolls: the conversation keeps most of the window)
                    Layout.maximumHeight: Math.round(pane.height * 0.4)
                    sourceComponent: Flickable {
                        id: stripFlick
                        implicitHeight: stripList.implicitHeight
                        contentHeight: stripList.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        PlasmaComponents3.ScrollBar.vertical: PlasmaComponents3.ScrollBar {}

                        ColumnLayout {
                            id: stripList
                            width: stripFlick.width
                            spacing: 0
                            Repeater {
                                model: pane.tasksOpen && pane.tasks ? pane.tasks.items.length : 0
                                delegate: PlasmaComponents3.Label {
                                    required property int index
                                    readonly property var task: (pane.tasks && pane.tasks.items[index]) || root.emptyTask
                                    Layout.fillWidth: true
                                    text: (task.status === "completed" ? "✓ " : task.status === "in_progress" ? "▸ " : "○ ") + task.subject
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    opacity: task.status === "completed" ? 0.6 : 0.9
                                    font.pointSize: pane.pt * 0.85
                                    font.bold: task.status === "in_progress"
                                }
                            }
                            // its subagents, as under its row in the popup
                            AgentTree {
                                Layout.fillWidth: true
                                Layout.topMargin: pane.tasksOpen && pane.tasks ? Kirigami.Units.smallSpacing : 0
                                visible: pane.agentsOpen && pane.agents !== null
                                agents: pane.stripAgents
                                rowKey: "pane|" + pane.host + "|" + pane.chatId   // (its agents' details: unfolded here, not under its row)
                                session: pane.row || ({})
                                remoteHost: pane.host
                                pointSize: pane.pt * 0.85
                            }
                        }
                    }
                }
            }

            // Chat | Steps | Review, underlined in Claude's color
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                spacing: 0

                Repeater {
                    model: ["chat", "steps", "review"]
                    delegate: MouseArea {
                        id: tabButton
                        required property string modelData
                        readonly property bool on: pane.tab === modelData
                        implicitWidth: tabText.implicitWidth + Kirigami.Units.gridUnit * 1.5
                        implicitHeight: tabText.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: pane.tab = modelData
                        Accessible.role: Accessible.PageTab
                        Accessible.name: tabText.text

                        PlasmaComponents3.Label {
                            id: tabText
                            anchors.centerIn: parent
                            textFormat: Text.PlainText
                            text: tabButton.modelData === "chat" ? i18nc("tab: your messages and Claude's replies", "Chat")
                                  : tabButton.modelData === "steps" ? i18nc("tab: the chat with every tool call", "Steps")
                                  : pane.row && pane.row.changes
                                  ? (pane.reviewPending ? i18nc("tab: the files a chat changed, not reviewed yet", "Review ±%1 •", pane.row.changes.count)
                                                        : i18nc("tab: the files a chat changed", "Review ±%1", pane.row.changes.count))
                                  : i18n("Review")
                            font.pointSize: pane.pt
                            font.weight: tabButton.on ? Font.Bold : Font.Normal
                            color: tabButton.on || tabButton.containsMouse ? Kirigami.Theme.textColor : pane.mutedColor
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 2
                            radius: 1
                            visible: tabButton.on
                            color: pane.claudeColor
                        }
                    }
                }
                Item {
                    Layout.fillWidth: true
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: -Kirigami.Units.smallSpacing
                implicitHeight: 1
                color: pane.borderColor
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: pane.info !== ""
                text: pane.info
                wrapMode: Text.Wrap
                color: pane.infoBad ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.positiveTextColor
            }

            // ---------------------------------------------------------------- Chat and Steps
            // (one list: on the Chat tab its tool calls take no room)
            PlasmaComponents3.ScrollView {
                id: scroll
                visible: pane.conversationTab
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                ListView {
                    id: list
                    model: items
                    spacing: 0
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    // every item made and laid out once (not as it scrolls in), so the
                    // list doesn't jump while you scroll
                    cacheBuffer: 100000
                    onMovementStarted: {   // (you scroll: it doesn't pull you back)
                        settle.stop()
                        holdTop.stop()
                    }
                    onContentHeightChanged: pane.keepPlace()
                    onHeightChanged: pane.keepPlace()
                    // (the wheel or a touchpad: the scroll view's Kirigami.WheelHandler moves
                    // contentY itself, so the list isn't moving, but you scroll all the same;
                    // this one only looks, the scroll view still scrolls)
                    WheelHandler {
                        blocking: false
                        onWheel: {
                            settle.stop()
                            holdTop.stop()
                        }
                    }

                    // Ctrl+wheel: the text size
                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        onWheel: event => pane.zoom(event.angleDelta.y > 0 ? 1 : -1)
                    }

                    header: Item {
                        width: list.width
                        implicitHeight: headerColumn.implicitHeight + Kirigami.Units.largeSpacing

                        ColumnLayout {
                            id: headerColumn
                            width: parent.width

                            PlasmaComponents3.Button {
                                visible: pane.more && pane.limit < pane.limitMax
                                Layout.alignment: Qt.AlignHCenter
                                icon.name: Icons.plasma.earlier
                                text: i18n("Show earlier")
                                onClicked: {
                                    pane.limit = Math.min(pane.limitMax, pane.limit * 2)
                                    pane.stamp = ""
                                    pane.load()
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                visible: pane.more && pane.limit >= pane.limitMax
                                horizontalAlignment: Text.AlignHCenter
                                text: i18n("Only its last %1 steps are shown here.", pane.limitMax)
                                color: pane.mutedColor
                                font.pointSize: pane.pt * 0.85
                                wrapMode: Text.Wrap
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                visible: !pane.loaded || pane.loadError !== ""
                                horizontalAlignment: Text.AlignHCenter
                                text: pane.loadError || i18n("Reading the chat…")
                                color: pane.loadError && !pane.loadMissing ? Kirigami.Theme.negativeTextColor : pane.mutedColor
                                font.pointSize: pane.pt
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    // While it works: Talpy thinking (talpy/glyph.mjs) and what
                    // it's doing, in the working color
                    footer: Item {
                        width: list.width
                        implicitHeight: pane.chatState === "working" ? workingLine.implicitHeight + Kirigami.Units.gridUnit : 0
                        visible: pane.chatState === "working"

                        RowLayout {
                            id: workingLine
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            spacing: 0

                            TalpyIcon {
                                Layout.preferredWidth: pane.gutter
                                Layout.preferredHeight: Math.round(fm.height * 1.2)
                                mode: "thinking"
                                color: root.stateColor("working")
                                moving: workingLine.visible && pane.shown && pane.conversationTab
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                // (what it's doing, unless that's the tool call just above)
                                readonly property bool toolAbove: pane.listTab === "steps" && items.count > 0 && items.get(items.count - 1).status === "open"
                                readonly property string activity: pane.row ? root.doingText(pane.row, pane.host).replace(/[….\s]+$/, "") : ""
                                text: (activity && !toolAbove ? activity : i18n("Working")) + "…"
                                elide: Text.ElideRight
                                color: root.stateColor("working")
                                font.family: pane.chatFamily
                                font.pointSize: pane.pt
                            }
                        }
                    }

                    delegate: Item {
                        id: entry
                        required property int index
                        required property string kind
                        required property string key
                        required property string text
                        required property string line
                        required property string name
                        required property string status
                        required property string input
                        required property string output
                        required property string summary
                        required property string prev
                        required property bool bad
                        required property string diff
                        required property bool queued   // (yours, in Claude's queue: pane.py)
                        required property real until    // (yours, held: when it goes to Claude, ms)
                        required property string pictures   // (yours: the pictures in it, "\n"-joined: pane.py prompt_pictures)
                        required property string here       // (a host's: those of them that are a regular file here, pane.py pictures_here)
                        property Item textBox: null   // (yours, Claude's reply: its text, selectAcross)
                        readonly property bool unfolded: pane.openTools[key] === true
                        // more room before your prompt (a new turn) than between steps
                        readonly property real gap: index === 0 ? 0
                            : kind === "you" ? Kirigami.Units.gridUnit * 1.6
                            : kind === "tool" && prev === "tool" ? Kirigami.Units.smallSpacing * 1.5
                            : Kirigami.Units.gridUnit * 0.8
                        readonly property bool shows: (kind !== "tool" || pane.listTab === "steps") && listed
                        // (its row gone from the model: Qt's ListView can leave a delegate it no
                        // longer lays out where it was, drawn over the rows now there; one shifted
                        // by a row put in before it, then removed, was seen still drawn, twice)
                        readonly property bool listed: index >= 0
                        width: list.width
                        implicitHeight: gap + body.implicitHeight
                        height: shows ? implicitHeight : 0
                        visible: shows

                        Loader {
                            id: body
                            y: entry.gap
                            width: parent.width
                            sourceComponent: entry.kind === "you" ? youItem : entry.kind === "claude" ? claudeItem
                                           : entry.kind === "tool" ? toolItem : noteItem
                        }

                        // Yours: a band in your accent color, after a ›. Queued (sent
                        // while Claude works), grey, as Claude's terminal shows it, with
                        // what becomes of it: held a moment (Edit, Send now, Cancel; ↑ in the
                        // box), then in Claude's queue till it takes it in at its next step
                        Component {
                            id: youItem

                            Rectangle {
                                id: youBand
                                readonly property bool held: entry.status === "held"
                                readonly property bool waits: held || entry.queued
                                readonly property color mark: waits ? pane.mutedColor : pane.youColor
                                implicitHeight: youColumn.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                                radius: Kirigami.Units.cornerRadius
                                color: waits ? pane.mix(pane.textColor, 0.07)
                                     : Qt.tint(Kirigami.Theme.backgroundColor, Qt.rgba(pane.youColor.r, pane.youColor.g, pane.youColor.b, 0.13))

                                Rectangle {
                                    width: 3
                                    height: parent.height
                                    radius: 1.5
                                    color: youBand.mark
                                }
                                ColumnLayout {
                                    id: youColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.rightMargin: Kirigami.Units.largeSpacing
                                    spacing: Kirigami.Units.smallSpacing

                                RowLayout {
                                    id: youRow
                                    Layout.fillWidth: true
                                    spacing: 0

                                    PlasmaComponents3.Label {
                                        Layout.preferredWidth: pane.gutter
                                        Layout.alignment: Qt.AlignTop
                                        horizontalAlignment: Text.AlignHCenter
                                        textFormat: Text.PlainText
                                        text: "›"
                                        color: youBand.mark
                                        font.pointSize: pane.pt
                                        font.weight: Font.Bold
                                    }
                                    TextEdit {
                                        id: youText
                                        Component.onCompleted: entry.textBox = youText
                                        Layout.fillWidth: true
                                        text: pane.shownText(entry.text)
                                        textFormat: TextEdit.PlainText
                                        readOnly: true
                                        selectByMouse: true
                                        persistentSelection: true   // (selectAcross clears it)
                                        Keys.onPressed: event => pane.copyAcross(event)
                                        wrapMode: TextEdit.Wrap
                                        color: Kirigami.Theme.textColor
                                        selectionColor: Kirigami.Theme.focusColor
                                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        font.family: pane.chatFamily
                                        font.pointSize: pane.pt
                                        opacity: entry.status === "sending" ? 0.6 : 1
                                    }
                                    // (on its way: pane.py --send hasn't answered yet)
                                    PlasmaComponents3.Label {
                                        visible: entry.status === "sending"
                                        Layout.alignment: Qt.AlignTop
                                        Layout.leftMargin: Kirigami.Units.largeSpacing
                                        textFormat: Text.PlainText
                                        text: i18n("Sending…")
                                        color: pane.mutedColor
                                        font.pointSize: pane.pt * 0.85
                                    }
                                }
                                // Its pictures, small: a click shows one big (bigView)
                                PictureStrip {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    pictures: entry.pictures ? entry.pictures.split("\n") : []
                                    here: pane.host ? (entry.here ? entry.here.split("\n") : []) : null
                                    host: pane.host
                                    removable: false
                                    opensHere: true
                                    thumbHeight: Kirigami.Units.gridUnit * 4
                                    onOpenRequested: path => pane.bigPicture = path
                                }
                                // Queued: what becomes of it
                                RowLayout {
                                    visible: youBand.waits
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    spacing: Kirigami.Units.smallSpacing

                                    PlasmaComponents3.Label {
                                        Layout.fillWidth: true
                                        textFormat: Text.PlainText
                                        wrapMode: Text.Wrap
                                        text: youBand.held
                                              ? i18n("Queued · goes to Claude in %1 s", Math.max(1, Math.ceil((entry.until - pane.now) / 1000)))
                                              : i18n("Queued · Claude takes it in at its next step")
                                        color: pane.mutedColor
                                        font.family: pane.chatFamily
                                        font.pointSize: pane.pt * 0.85
                                    }
                                    // (framed thin, so they read as buttons; Cancel last, at the end)
                                    IconTextButton {
                                        visible: youBand.held
                                        Layout.preferredHeight: pane.queueButtonHeight
                                        icon.name: Icons.plasma.edit
                                        text: i18n("Edit")
                                        onClicked: pane.takeBack(entry.key, true)
                                        PlasmaComponents3.ToolTip.text: i18n("Back in the box, to change it (↑ in an empty box too)")
                                        PlasmaComponents3.ToolTip.visible: hovered
                                        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                                    }
                                    IconTextButton {
                                        visible: youBand.held
                                        Layout.preferredHeight: pane.queueButtonHeight
                                        icon.name: Icons.plasma.send
                                        text: i18n("Send now")
                                        onClicked: pane.release(entry.key)
                                        PlasmaComponents3.ToolTip.text: i18n("To Claude now: it takes it in at its next step")
                                        PlasmaComponents3.ToolTip.visible: hovered
                                        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                                    }
                                    IconTextButton {
                                        visible: youBand.held
                                        Layout.preferredHeight: pane.queueButtonHeight
                                        icon.name: Icons.plasma.cancel
                                        icon.color: Icons.color("cancel", Kirigami.Theme)
                                        text: i18n("Cancel")
                                        onClicked: pane.takeBack(entry.key, false)
                                        PlasmaComponents3.ToolTip.text: i18n("Don't send it")
                                        PlasmaComponents3.ToolTip.visible: hovered
                                        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                                    }
                                }
                                }
                            }
                        }

                        // Claude's reply: ● and its Markdown, rendered
                        Component {
                            id: claudeItem

                            RowLayout {
                                spacing: 0

                                Dot {
                                    color: pane.claudeColor
                                    gutter: pane.gutter
                                    lineHeight: fm.height
                                }
                                TextEdit {
                                    id: replyText
                                    // a code block's Copy: the one the pointer is on, and the one
                                    // just clicked, which reads Copied a moment (their index)
                                    property int copyHovered: -1
                                    property int copied: -1
                                    Component.onCompleted: entry.textBox = replyText
                                    Layout.fillWidth: true
                                    text: Md.toHtml(entry.text, pane.mdStyle, copied)
                                    textFormat: TextEdit.RichText
                                    readOnly: true
                                    persistentSelection: true   // (selectAcross clears it)
                                    Keys.onPressed: event => pane.copyAcross(event)
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: Kirigami.Theme.textColor
                                    selectionColor: Kirigami.Theme.focusColor
                                    selectedTextColor: Kirigami.Theme.highlightedTextColor
                                    font.family: pane.chatFamily
                                    font.pointSize: pane.pt
                                    onLinkActivated: link => {
                                        if (link.indexOf("copy:") === 0) {
                                            copied = Number(link.slice(5))
                                            pane.copyText(Md.clipboardCode(Md.codeBlocks(entry.text)[copied] || ""), true)
                                            copiedTimer.restart()
                                        } else
                                            Qt.openUrlExternally(link)
                                    }
                                    onLinkHovered: link => {
                                        copyHovered = link.indexOf("copy:") === 0 ? Number(link.slice(5)) : -1
                                        pane.linkHovered(replyText, link, replyHover.point.position)
                                    }

                                    // Where a code block's Copy (label: Copy or Copied) is drawn: the
                                    // label's place in the text whose link is that block's (not a
                                    // "Copy" in the reply's words or in its code)
                                    function copyRect(block, label) {
                                        const plain = getText(0, length)
                                        for (let i = plain.indexOf(label); i >= 0; i = plain.indexOf(label, i + 1)) {
                                            const r = positionToRectangle(i)
                                            if (linkAt(r.x + 1, r.y + r.height / 2) === "copy:" + block) {
                                                const end = positionToRectangle(i + label.length)
                                                return Qt.rect(r.x, r.y, end.x - r.x, r.height)
                                            }
                                        }
                                        return Qt.rect(0, 0, 0, 0)
                                    }

                                    Timer {
                                        id: copiedTimer
                                        interval: 1500
                                        onTriggered: replyText.copied = -1
                                    }

                                    // The Copy the pointer is on (else the one that reads Copied)
                                    // framed thin in the accent, as a button: rich text has no
                                    // hover of its own, so the frame is drawn over its link
                                    Rectangle {
                                        readonly property int block: replyText.copyHovered >= 0 ? replyText.copyHovered : replyText.copied
                                        readonly property rect at: block < 0 || replyText.width <= 0 || replyText.contentHeight <= 0
                                                                   ? Qt.rect(0, 0, 0, 0)
                                                                   : replyText.copyRect(block, block === replyText.copied ? "Copied" : "Copy")
                                        visible: at.width > 0
                                        x: at.x - Kirigami.Units.smallSpacing
                                        y: at.y - 1
                                        width: at.width + 2 * Kirigami.Units.smallSpacing
                                        height: at.height + 2
                                        radius: Kirigami.Units.cornerRadius
                                        color: "transparent"
                                        border.width: 1
                                        border.color: Kirigami.Theme.focusColor
                                    }

                                    HoverHandler {
                                        id: replyHover
                                        cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor
                                    }
                                }
                            }
                        }

                        // A tool call: ● Bash(pytest) in green, red or (still going) blinking,
                        // and under it ⎿ what came of it; click for what it ran and got
                        Component {
                            id: toolItem

                            ColumnLayout {
                                id: toolBox
                                spacing: Kirigami.Units.smallSpacing
                                readonly property bool asking: !!pane.permission && entry.status === "open" && entry.index === items.count - 1
                                readonly property bool going: entry.status === "open" && pane.busy
                                readonly property string args: entry.line.indexOf(entry.name + ": ") === 0 ? entry.line.slice(entry.name.length + 2) : ""

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: toolRow.implicitHeight + Kirigami.Units.smallSpacing
                                    radius: Kirigami.Units.cornerRadius
                                    color: toolHover.hovered ? pane.mix(pane.textColor, 0.06) : "transparent"

                                    RowLayout {
                                        id: toolRow
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 0

                                        Dot {
                                            Layout.alignment: Qt.AlignTop
                                            color: entry.status === "ok" ? Kirigami.Theme.positiveTextColor
                                                 : entry.status === "error" ? Kirigami.Theme.negativeTextColor
                                                 : toolBox.asking ? Kirigami.Theme.neutralTextColor : pane.mutedColor
                                            blinking: toolBox.going && pane.visible
                                            gutter: pane.gutter
                                            lineHeight: fm.height
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 0

                                            // Bash  git status: the tool, then what it got, set apart in code's font
                                            PlasmaComponents3.Label {
                                                Layout.fillWidth: true
                                                textFormat: Text.StyledText
                                                text: "<b><font color=\"" + pane.hex(pane.strongColor) + "\">" + Md.escape(toolBox.args ? entry.name : entry.line) + "</font></b>"
                                                      + (toolBox.args ? "&nbsp;&nbsp;<font face=\"" + pane.monoFamily + "\" color=\"" + pane.hex(pane.codeColor) + "\">"
                                                                        + Md.escape(toolBox.args) + "</font>" : "")
                                                wrapMode: Text.Wrap
                                                maximumLineCount: entry.unfolded ? 20 : 2
                                                elide: Text.ElideRight
                                                font.family: pane.chatFamily
                                                font.pointSize: pane.pt
                                            }
                                            PlasmaComponents3.Label {
                                                Layout.fillWidth: true
                                                visible: text !== ""
                                                textFormat: Text.PlainText
                                                text: entry.summary ? "⎿  " + entry.summary
                                                    : toolBox.asking ? "⎿  " + i18n("Waiting for your answer")
                                                    : ""
                                                elide: Text.ElideRight
                                                font.family: pane.chatFamily
                                                font.pointSize: pane.pt * 0.92
                                                color: entry.status === "error" ? Kirigami.Theme.negativeTextColor
                                                     : toolBox.asking ? Kirigami.Theme.neutralTextColor : pane.mutedColor
                                            }
                                            // An edit's change, right under it (its first lines; unfolded, all
                                            // of it). Made only for an edit: the pane opens as quickly as before
                                            Loader {
                                                active: entry.diff !== ""
                                                visible: active
                                                Layout.fillWidth: true
                                                Layout.topMargin: active ? Kirigami.Units.smallSpacing : 0
                                                sourceComponent: DiffView {
                                                    lines: entry.diff.split("\n")
                                                    path: toolBox.args
                                                    maxRows: entry.unfolded ? 0 : 6
                                                    canSplit: entry.unfolded
                                                    pt: pane.pt
                                                    mono: pane.monoFamily
                                                    base: pane.mdStyle.blockBg
                                                }
                                            }
                                        }
                                    }
                                    HoverHandler {
                                        id: toolHover
                                        cursorShape: Qt.PointingHandCursor
                                    }
                                    TapHandler {
                                        onTapped: {
                                            const next = Object.assign({}, pane.openTools)
                                            next[entry.key] = !entry.unfolded
                                            pane.openTools = next
                                        }
                                    }
                                }
                                // Unfolded: the command and what it printed, the lines it read
                                // (numbered, in the file's colors), or what it was asked and got
                                // (codehtml.mjs; an edit's change is above, its error here)
                                Loader {
                                    active: entry.unfolded && (entry.input !== "" || entry.output !== "")
                                            && (entry.diff === "" || entry.status === "error")
                                    visible: active
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    sourceComponent: Rectangle {
                                        implicitHeight: detail.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                                        radius: Kirigami.Units.cornerRadius
                                        color: pane.mdStyle.blockBg
                                        border.width: 1
                                        border.color: pane.borderColor

                                        TextEdit {
                                            id: detail
                                            anchors.fill: parent
                                            anchors.margins: Kirigami.Units.largeSpacing * 0.75
                                            text: Code.toolHtml({ name: entry.name, input: entry.input, output: entry.output, status: entry.status },
                                                                toolBox.args, pane.codeStyle)
                                            textFormat: TextEdit.RichText
                                            readOnly: true
                                            selectByMouse: true
                                            wrapMode: TextEdit.Wrap
                                            color: Kirigami.Theme.textColor
                                            selectionColor: Kirigami.Theme.focusColor
                                            selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        }
                                    }
                                }
                            }
                        }

                        // A note: interrupted, a usage limit, compacted (── Interrupted ──)
                        Component {
                            id: noteItem

                            RowLayout {
                                spacing: Kirigami.Units.largeSpacing

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 1
                                    color: entry.bad ? Kirigami.Theme.negativeTextColor : pane.borderColor
                                }
                                PlasmaComponents3.Label {
                                    Layout.maximumWidth: list.width * 0.75
                                    textFormat: Text.PlainText
                                    text: entry.text
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.Wrap
                                    font.family: pane.chatFamily
                                    font.italic: true
                                    font.pointSize: pane.pt * 0.9
                                    color: entry.bad ? Kirigami.Theme.negativeTextColor : pane.mutedColor
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 1
                                    color: entry.bad ? Kirigami.Theme.negativeTextColor : pane.borderColor
                                }
                            }
                        }
                    }
                }
            }

            // A drag in a message that goes on into the next ones selects them
            // too (selectAcross); a handler on top of the list, passive, so the
            // text box under it still takes the press, and links, buttons and
            // scrolling are as they were (it only looks, while you drag)
            Item {
                id: selectOver
                parent: scroll
                anchors.fill: parent
                z: 10
                PointHandler {
                    acceptedButtons: Qt.LeftButton
                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                    onActiveChanged: if (active) pane.selectStart(selectOver.mapToItem(list, point.position.x, point.position.y))
                    onPointChanged: if (active) pane.selectAcross(selectOver.mapToItem(list, point.position.x, point.position.y))
                }
            }

            // What it asks while it waits: Allow once / Always allow / Deny, or its questions
            // (at most half the pane, scrolling, so the conversation stays in sight)
            Rectangle {
                visible: pane.conversationTab && pane.permission !== null
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(askColumn.implicitHeight + Kirigami.Units.largeSpacing * 2, pane.height / 2)
                radius: Kirigami.Units.cornerRadius
                color: Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.08)
                border.width: 1
                border.color: Kirigami.Theme.neutralTextColor

                PlasmaComponents3.ScrollView {
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    contentWidth: availableWidth
                    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                    PermissionAsk {
                        id: askColumn
                        width: parent.width
                        permission: pane.permission
                        busy: pane.answering > 0
                        pt: pane.pt
                        mono: pane.monoFamily
                        diffLines: 12
                        planHeight: Kirigami.Units.gridUnit * 1000   // (the box scrolls)
                        onAnswered: (decision, note, answers) => pane.answer(decision, note, answers)
                        // (a plan too long to show whole: its file, by its name)
                        onWholePlan: root.openPlan(permission.plan.file.split("/").pop().replace(/\.md$/, ""), pane.profileDir, pane.host)
                    }
                }
            }

            // Your reply
            ColumnLayout {
                visible: pane.conversationTab
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    visible: pane.queued !== null
                    Layout.fillWidth: true

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        text: pane.queued ? i18n("Sent when this turn ends: %1", pane.queued.prompt) : ""
                        elide: Text.ElideRight
                        color: Kirigami.Theme.focusColor
                    }
                    PlasmaComponents3.ToolButton {
                        icon.name: Icons.plasma.cancel
                        icon.color: Icons.color("cancel", Kirigami.Theme)
                        text: i18n("Cancel")
                        onClicked: pane.unqueueAsk = pane.unqueueAsk === pane.queued.id ? "" : pane.queued.id
                    }
                }
                // (asked first, as the popup's queued line: what you wrote is gone with it)
                ConfirmLine {
                    Layout.fillWidth: true
                    visible: pane.queued !== null && pane.unqueueAsk === pane.queued.id
                    text: i18n("Cancel your message to “%1”? It isn't sent, and its text is gone.",
                               pane.queued && pane.queued.name ? pane.queued.name : pane.chatName || i18n("the chat"))
                    confirmText: i18n("Cancel it")
                    confirmIcon: "cancel"
                    cancelText: i18n("Keep it")
                    onConfirmed: {
                        pane.unqueueAsk = ""
                        root.unqueue(pane.queued)
                    }
                    onCancelled: pane.unqueueAsk = ""
                }
                // What it offers for what you're typing (/ commands, @ files)
                Rectangle {
                    visible: pane.suggestions.length > 0 && replyBox.activeFocus
                    Layout.fillWidth: true
                    Layout.leftMargin: pane.gutter
                    implicitHeight: offerList.implicitHeight + 2
                    radius: Kirigami.Units.cornerRadius
                    color: pane.mix(pane.textColor, 0.06)
                    border.width: 1
                    border.color: pane.borderColor

                    Column {
                        id: offerList
                        x: 1
                        y: 1
                        width: parent.width - 2
                        Repeater {
                            model: pane.suggestions.length
                            delegate: Rectangle {
                                required property int index
                                readonly property var offer: pane.suggestions[index] || { text: "", about: "" }
                                width: offerList.width
                                height: offerRow.implicitHeight + Kirigami.Units.smallSpacing
                                radius: Kirigami.Units.cornerRadius
                                color: index === pane.suggestion ? Qt.rgba(pane.youColor.r, pane.youColor.g, pane.youColor.b, 0.22) : "transparent"
                                RowLayout {
                                    id: offerRow
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: Kirigami.Units.smallSpacing
                                    anchors.rightMargin: Kirigami.Units.smallSpacing
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        text: offer.text
                                        font.family: pane.monoFamily
                                        font.pointSize: pane.pt * 0.95
                                        color: index === pane.suggestion ? pane.youColor : pane.textColor
                                        elide: Text.ElideMiddle
                                        Layout.maximumWidth: offerList.width * 0.6
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        Layout.fillWidth: true
                                        text: offer.about
                                        color: pane.mutedColor
                                        font.pointSize: pane.pt * 0.85
                                        elide: Text.ElideRight
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        pane.takeSuggestion(index)
                                        replyBox.forceActiveFocus()
                                    }
                                }
                            }
                        }
                    }
                }
                // a box like Claude's prompt: › and what you type, framed (your accent while you type)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(fm.height * 9, Math.max(fm.height * 3.2, replyBox.implicitHeight + Kirigami.Units.smallSpacing * 2))
                    radius: Kirigami.Units.cornerRadius * 1.5
                    color: pane.mix(pane.textColor, 0.035)
                    border.width: replyBox.activeFocus ? 2 : 1
                    border.color: replyBox.activeFocus ? pane.youColor : pane.borderColor
                    opacity: replyBox.enabled ? 1 : 0.6

                    PlasmaComponents3.Label {
                        x: 0
                        y: Kirigami.Units.smallSpacing + replyBox.topPadding
                        width: pane.gutter
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                        text: "›"
                        color: replyBox.activeFocus ? pane.youColor : pane.mutedColor
                        font.pointSize: pane.pt
                        font.weight: Font.Bold
                    }
                    PlasmaComponents3.ScrollView {
                        anchors.fill: parent
                        anchors.leftMargin: pane.gutter - replyBox.leftPadding
                        anchors.topMargin: Kirigami.Units.smallSpacing
                        anchors.bottomMargin: Kirigami.Units.smallSpacing
                        anchors.rightMargin: Kirigami.Units.smallSpacing
                        // (what you write wraps; the hint, wider than the box in a
                        // fixed-width font, ends in … instead of scrolling sideways)
                        contentWidth: availableWidth
                        PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                        PlasmaComponents3.TextArea {
                            id: replyBox
                            background: null
                            placeholderText: pane.permission && !pane.replyAnswers ? i18n("It's asking you something: answer that first")
                                                             : i18n("Reply to Claude… (Enter sends, Shift+Enter: new line; Ctrl+V or drop: a picture or a file too)")
                            wrapMode: TextEdit.Wrap
                            font.family: pane.chatFamily
                            font.pointSize: pane.pt
                            enabled: !pane.replyWaits
                            // Enter sends, as in Claude's own prompt (Shift+Enter: a new line). For a
                            // terminal that takes no text from outside, Enter copies it and opens its
                            // tab (pane.py how enter): Claude there never quits on an Enter.
                            // Ctrl+V with no text on the clipboard: its picture (an SSH host's
                            // chat asks to copy it there).
                            onTextChanged: {
                                if (pane.historyAt >= 0 && text !== pane.historyList[pane.historyAt])
                                    pane.historyAt = -1   // (typed into a past prompt: it's yours now)
                                pane.suggest()
                            }
                            onCursorPositionChanged: pane.suggest()
                            onActiveFocusChanged: if (activeFocus) pane.loadOffers()
                            Keys.onPressed: event => {
                                if (pane.suggestions.length) {
                                    if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                                        const n = pane.suggestions.length
                                        pane.suggestion = (pane.suggestion + (event.key === Qt.Key_Down ? 1 : n - 1)) % n
                                        event.accepted = true
                                        return
                                    }
                                    if (event.key === Qt.Key_Tab || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                        pane.takeSuggestion(pane.suggestion)
                                        event.accepted = true
                                        return
                                    }
                                    if (event.key === Qt.Key_Escape) {
                                        pane.dismissed = text.slice(pane.tokenStart, cursorPosition)
                                        pane.suggestions = []
                                        event.accepted = true
                                        return
                                    }
                                }
                                // (↑ in an empty box: your queued message, still held, back in it first)
                                if (event.key === Qt.Key_Up && event.modifiers === Qt.NoModifier && text === "" && pane.takeBackLast()) {
                                    event.accepted = true
                                    return
                                }
                                if ((event.key === Qt.Key_Up && text.lastIndexOf("\n", cursorPosition - 1) < 0)
                                        || (event.key === Qt.Key_Down && pane.historyAt >= 0 && text.indexOf("\n", cursorPosition) < 0)) {
                                    if (event.modifiers === Qt.NoModifier && (text === "" || pane.historyAt >= 0 || event.key === Qt.Key_Down)
                                            && pane.historyStep(event.key === Qt.Key_Up ? 1 : -1)) {
                                        event.accepted = true
                                        return
                                    }
                                }
                                if (event.matches(StandardKey.Paste) && !canPaste) {
                                    event.accepted = true
                                    root.pasteImage(pane.host, pane.pasteTarget)
                                    return
                                }
                                if (event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter)
                                    return
                                if (event.modifiers & Qt.ShiftModifier) {
                                    if (selectedText)
                                        remove(selectionStart, selectionEnd)
                                    insert(cursorPosition, "\n")
                                } else if (preeditText === "") {   // (not while an input method composes)
                                    pane.send("enter", false)
                                } else {
                                    return
                                }
                                event.accepted = true
                            }
                        }
                    }
                }
                // The pictures your reply names, small (× takes one out)
                PictureStrip {
                    id: replyPictures
                    Layout.fillWidth: true
                    Layout.leftMargin: pane.gutter
                    pictures: named(replyBox.text)
                    host: pane.host
                    removeText: i18n("Take it out of your reply")
                    onRemoveRequested: path => replyBox.text = without(replyBox.text, path)
                }
                // A picture for an SSH host's chat: copied there once you say so
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!pane.host && !!root.pictureOffer && root.pictureOffer.host === pane.host
                             && root.pictureOffer.target === pane.pasteTarget
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
                        text: i18n("Copy this picture to %1? Claude there can only open it there.", root.hostLabel(pane.host))
                        confirmText: i18n("Copy")
                        onConfirmed: root.copyPicture()
                        onCancelled: root.pictureOffer = null
                    }
                }
                PlasmaComponents3.Label {
                    visible: !!pane.host && root.pictureCopyingTo === pane.host && root.pictureCopyTarget === pane.pasteTarget
                    textFormat: Text.PlainText
                    text: i18n("Copying the picture to %1…", root.hostLabel(pane.host))
                    color: pane.mutedColor
                }
                // Nothing to write it down with: dictation is set up once you say so
                ConfirmLine {
                    Layout.fillWidth: true
                    visible: pane.offerSetup
                    text: i18n("Set up dictation? It installs faster-whisper, speech to text that runs on this computer, and its base speech model: about %1 MB from pypi.org and huggingface.co into ~/.local/share/talpy-den/whisper, no sudo needed; a few minutes. What you say never leaves the computer. Other models: in the settings.",
                               pane.dictateState ? pane.dictateState.setupMb : 612)
                    confirmText: i18n("Set up")
                    onConfirmed: {
                        pane.offerSetup = false
                        pane.dictating = "setup"
                        pane.dictateRun("--setup")
                    }
                    onCancelled: pane.offerSetup = false
                }
                // whisper is there but no speech model: one is downloaded once you say so
                ConfirmLine {
                    Layout.fillWidth: true
                    visible: pane.offerModel
                    text: i18n("To dictate, %1 needs a speech model: download its base model (142 MB) from huggingface.co? It's kept in ~/.local/share/talpy-den/whisper; what you say never leaves the computer. Other models: in the settings.",
                               pane.dictateState && pane.dictateState.engine ? pane.dictateState.engine : "whisper")
                    confirmText: i18n("Download")
                    onConfirmed: {
                        pane.offerModel = false
                        pane.dictating = "model"
                        pane.dictateRun("--get-model base")
                    }
                    onCancelled: pane.offerModel = false
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: pane.routeHint
                    wrapMode: Text.Wrap
                    font.pointSize: pane.pt * 0.85
                    color: pane.mutedColor
                }
                // Your tools, and the send buttons beside them or, when both
                // don't fit (a button keeps its width), under them
                GridLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0   // (its width is the pane's, never what it asks for)
                    columns: replyTools.implicitWidth + columnSpacing + sendButtons.implicitWidth <= width ? 2 : 1
                    columnSpacing: Kirigami.Units.smallSpacing
                    rowSpacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        id: replyTools
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.ToolButton {
                            icon.name: pane.dictating === "recording" ? Icons.plasma.stop : Icons.plasma.dictate
                            icon.color: pane.dictating === "recording" ? Kirigami.Theme.negativeTextColor : "transparent"
                            enabled: pane.dictating === "" || pane.dictating === "recording"
                            text: pane.dictating === "recording" ? i18n("Stop: write it down") + " · " + root.duration(Math.max(1000, pane.recordedMs))
                                  : pane.dictating === "writing" ? i18n("Writing it down…")
                                  : pane.dictating === "model" ? i18n("Downloading the speech model…")
                                  : pane.dictating === "setup" ? i18n("Setting up dictation (a few minutes)…")
                                  : pane.dictating === "starting" ? i18n("Starting the microphone…") : i18n("Dictate")
                            display: pane.dictating === "" || pane.dictating === "starting" ? PlasmaComponents3.AbstractButton.IconOnly
                                                                                              : PlasmaComponents3.AbstractButton.TextBesideIcon
                            onClicked: pane.dictate()

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Dictate")
                                subText: i18n("Say your reply: click again to stop, and it's written down where you're typing. On this computer only (whisper): what you say doesn't leave it. The speech model: in the settings.")
                            }
                        }
                        PlasmaComponents3.ToolButton {
                            visible: pane.dictating === "recording"
                            icon.name: Icons.plasma.cancel
                            icon.color: Icons.color("cancel", Kirigami.Theme)
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            text: i18n("Stop, don't write it down")
                            onClicked: pane.cancelDictation()
                        }
                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.attach
                            text: i18n("Attach files…")
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            onClicked: root.pickFiles(pane.host, pane.pasteTarget, pane.row ? pane.row.cwd || "" : pane.chat.cwd || "")

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Attach files…")
                                subText: pane.host ? i18n("Pick pictures for your reply (copied to %1 once you say so).", root.hostLabel(pane.host))
                                                   : i18n("Pick files for your reply: a picture goes in as one, another file is named for Claude to read. You can drop them on the pane too.")
                            }
                        }
                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.screenshot
                            text: i18n("Screenshot…")
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            onClicked: root.takeScreenshot(pane.host, pane.pasteTarget)

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Screenshot…")
                                subText: i18n("Pick a region of the screen: its picture goes in your reply. Files and pictures can be dropped on the pane too.")
                            }
                        }
                        Item {
                            Layout.fillWidth: true
                        }
                    }
                    RowLayout {
                        id: sendButtons
                        Layout.alignment: Qt.AlignRight
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Button {
                            visible: pane.route === "terminal" || pane.askHow
                            enabled: replyBox.text.trim() !== ""
                            icon.name: Icons.plasma.copy
                            text: i18n("Copy and open its tab")
                            onClicked: pane.send("copy", false)
                        }
                        PlasmaComponents3.Button {
                            visible: pane.busy
                            enabled: replyBox.text.trim() !== ""
                            icon.name: Icons.plasma.later
                            text: i18n("Send when this turn ends")
                            onClicked: pane.send(pane.route === "terminal" || pane.askHow ? "background" : "auto", true)

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Send when this turn ends")
                                subText: i18n("Talpy Den keeps it and sends it once Claude's turn is over (also with the popup closed).")
                            }
                        }
                        PlasmaComponents3.Button {
                            // (a terminal that takes no text, known or just found out: not while
                            // Claude works there, it would quit mid-turn; Send when this turn ends)
                            enabled: replyBox.text.trim() !== "" && !((pane.route === "terminal" || pane.askHow) && pane.busy)
                                     && !pane.replyWaits && !(pane.replyAnswers && pane.answering > 0)
                            icon.name: pane.replyAnswers === "plan" ? Icons.plasma.edit : pane.replyAnswers === "deny" || pane.replyAnswers === "decline" ? Icons.plasma.deny
                                       : Icons.plasma.send
                            icon.color: pane.replyAnswers === "deny" || pane.replyAnswers === "decline" ? Icons.color("deny", Kirigami.Theme) : "transparent"
                            text: pane.replyAnswers === "deny" ? i18n("Deny with this note")
                                  : pane.replyAnswers === "plan" ? i18n("Keep planning with this note")
                                  : pane.replyAnswers === "question" ? i18n("Send as your answer")
                                  : pane.replyAnswers === "decline" ? i18n("Decline with this note")
                                  : pane.route === "terminal" || pane.askHow ? i18n("Send, go on in the background") : i18n("Send")
                            onClicked: pane.send(pane.route === "terminal" || pane.askHow ? "background" : "auto", false)
                        }
                    }
                }
            }

            // ---------------------------------------------------------------- Review
            PlasmaComponents3.ScrollView {
                visible: pane.tab === "review"
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                ColumnLayout {
                    width: parent.width
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: pane.review === null
                        text: pane.reviewLoading ? i18n("Comparing its files with how they were before the chat…")
                                                 : pane.reviewError || i18n("Nothing to review yet")
                        color: pane.reviewError ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                        font.pointSize: pane.pt
                        opacity: 0.7
                        wrapMode: Text.Wrap
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: pane.review !== null && pane.review.files.length === 0
                        text: i18n("No changed files: they're as they were before this chat.")
                        font.pointSize: pane.pt
                        opacity: 0.7
                        wrapMode: Text.Wrap
                    }

                    // the files, +/- lines, their diffs
                    RowLayout {
                        visible: pane.review !== null && pane.review.files.length > 0
                        Layout.fillWidth: true

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            readonly property var sums: pane.totals(pane.review ? pane.review.files : [])
                            text: pane.review ? i18np("%1 file changed since the chat started", "%1 files changed since the chat started",
                                                     pane.review.files.length) + "  +" + sums[0] + " −" + sums[1] : ""
                            font.bold: true
                            font.pointSize: pane.pt
                        }
                        TestsBadge {
                            review: pane.row ? pane.row.review : (pane.review ? { tests: pane.review.tests } : null)
                        }
                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.sideBySide
                            checkable: true
                            checked: Plasmoid.configuration.diffSideBySide
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            text: i18n("Side by side")
                            onToggled: Plasmoid.configuration.diffSideBySide = checked

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Side by side")
                                subText: i18n("Each change as before | after, where the pane is wide enough; else removed and added lines one after the other.")
                            }
                        }
                    }
                    Repeater {
                        model: pane.review ? pane.review.files.length : 0
                        delegate: ColumnLayout {
                            id: fileItem
                            required property int index
                            readonly property var file: pane.review && pane.review.files[index] ? pane.review.files[index] : ({ label: "", path: "", diff: [] })
                            readonly property bool unfolded: pane.openFiles[file.path] === true
                            Layout.fillWidth: true
                            spacing: 0

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing

                                Kirigami.Icon {
                                    source: fileItem.unfolded ? Icons.plasma.unfolded : Icons.plasma.folded
                                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                    Layout.preferredHeight: Layout.preferredWidth
                                    opacity: 0.6
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    text: fileItem.file.label + (fileItem.file.created ? "  " + i18nc("a file the chat made", "(new)") : "")
                                          + (fileItem.file.deleted ? "  " + i18nc("a file the chat removed", "(removed)") : "")
                                    elide: Text.ElideMiddle
                                    font.family: pane.monoFamily
                                    font.pointSize: pane.pt

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            const next = Object.assign({}, pane.openFiles)
                                            next[fileItem.file.path] = !fileItem.unfolded
                                            pane.openFiles = next
                                        }
                                    }
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    visible: fileItem.file.added !== null && fileItem.file.added !== undefined
                                    text: "+" + fileItem.file.added
                                    color: Kirigami.Theme.positiveTextColor
                                    font.family: pane.monoFamily
                                    font.pointSize: pane.pt
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    visible: fileItem.file.removed !== null && fileItem.file.removed !== undefined
                                    text: "−" + fileItem.file.removed
                                    color: Kirigami.Theme.negativeTextColor
                                    font.family: pane.monoFamily
                                    font.pointSize: pane.pt
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    visible: !!fileItem.file.binary || !!fileItem.file.unknown
                                    text: fileItem.file.binary ? i18n("binary") : i18n("no earlier version kept")
                                    opacity: 0.6
                                    font.pointSize: pane.pt * 0.85
                                }
                                PlasmaComponents3.ToolButton {
                                    visible: !fileItem.file.unknown
                                    icon.name: Icons.plasma.undo
                                    display: PlasmaComponents3.AbstractButton.IconOnly
                                    text: i18n("Undo this file")
                                    onClicked: pane.undoAsk = fileItem.file.path

                                    TipArea {
                                        textFormat: Text.PlainText
                                        anchors.fill: parent
                                        mainText: i18n("Undo this file")
                                        subText: i18n("Asks first. Puts it back as it was before this chat.")
                                    }
                                }
                            }
                            ConfirmLine {
                                visible: pane.undoAsk === fileItem.file.path
                                Layout.fillWidth: true
                                text: fileItem.file.created ? i18n("Delete %1 for good? The chat made it; what you changed in it since is lost too.", fileItem.file.label)
                                                            : i18n("Put %1 back as it was before this chat? Later changes to it are lost too.", fileItem.file.label)
                                confirmText: i18n("Undo")
                                confirmIcon: "undo"
                                onConfirmed: pane.undo(fileItem.file.path)
                                onCancelled: pane.undoAsk = ""
                            }
                            PlasmaComponents3.Label {
                                visible: fileItem.unfolded && !!fileItem.file.unknown && !!fileItem.file.now && fileItem.file.now.length > 0
                                Layout.fillWidth: true
                                Layout.leftMargin: Kirigami.Units.gridUnit
                                textFormat: Text.PlainText
                                text: i18n("No earlier version was kept, so this is how it is now:")
                                font.pointSize: pane.pt * 0.85
                                opacity: 0.7
                                wrapMode: Text.Wrap
                            }
                            Loader {
                                active: fileItem.unfolded && ((fileItem.file.diff || []).length > 0 || (fileItem.file.now || []).length > 0)
                                visible: active
                                Layout.fillWidth: true
                                Layout.leftMargin: Kirigami.Units.gridUnit
                                sourceComponent: DiffView {
                                    lines: fileItem.file.diff || []
                                    now: fileItem.file.unknown ? fileItem.file.now || [] : []
                                    path: fileItem.file.path
                                    pt: pane.pt
                                    mono: pane.monoFamily
                                    base: pane.mdStyle.blockBg
                                }
                            }
                        }
                    }
                }
            }
            // Commit only these files, with a message from its name and recap
            // (over the buttons that open them, not at the end of a long list, out of sight)
            ColumnLayout {
                visible: pane.tab === "review" && pane.commitOpen && pane.review !== null
                Layout.fillWidth: true

                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: pane.review && pane.review.repos.length
                          ? i18n("Commit only these files in %1 (yours that aren't this chat's stay as they are):", pane.review.repos.join(", "))
                          : i18n("None of these files is in a git repository.")
                    wrapMode: Text.Wrap
                    font.pointSize: pane.pt
                }
                PlasmaComponents3.TextArea {
                    id: commitText
                    Layout.fillWidth: true
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 6
                    wrapMode: TextEdit.Wrap
                    font.family: pane.monoFamily
                    font.pointSize: pane.pt
                    onTextChanged: if (activeFocus) pane.commitEdited = true
                }
                RowLayout {
                    Item {
                        Layout.fillWidth: true
                    }
                    PlasmaComponents3.Button {
                        text: i18n("Cancel")
                        onClicked: pane.commitOpen = false
                    }
                    PlasmaComponents3.Button {
                        enabled: commitText.text.trim() !== "" && pane.reviewIsThis && pane.review.repos.length > 0
                        icon.name: Icons.plasma.commit
                        text: i18n("Commit")
                        onClicked: pane.run("commit", "--commit " + root.shellQuote(pane.chatId) + " --message "
                                            + root.shellQuote(commitText.text) + pane.paneArgs())
                    }
                }
            }
            ConfirmLine {
                visible: pane.tab === "review" && pane.undoAsk === "*"
                Layout.fillWidth: true
                text: i18n("Put all of them back as they were before this chat? Files it made are deleted for good; later changes to them are lost too.")
                confirmText: i18n("Undo all")
                confirmIcon: "undo"
                onConfirmed: pane.undo("*")
                onCancelled: pane.undoAsk = ""
            }
            RowLayout {
                visible: pane.tab === "review"
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.refresh
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Compare again")
                    onClicked: pane.loadReview()
                }
                Item {
                    Layout.fillWidth: true
                }
                PlasmaComponents3.Button {
                    enabled: pane.reviewIsThis && pane.review.files.length > 0
                    icon.name: Icons.plasma.undo
                    text: i18n("Undo all…")
                    onClicked: pane.undoAsk = "*"
                }
                PlasmaComponents3.Button {
                    enabled: pane.reviewIsThis && pane.review.files.length > 0 && pane.review.repos.length > 0
                    icon.name: Icons.plasma.commit
                    text: i18n("Commit these files…")
                    onClicked: pane.commitOpen = !pane.commitOpen
                }
                PlasmaComponents3.Button {
                    // (by the mark itself: while the chat works it isn't "to review", nor reviewed)
                    readonly property bool marked: !!pane.row && !!pane.row.review && root.reviewSeen(pane.row, pane.host)
                    icon.name: marked ? Icons.plasma.reviewed : Icons.plasma.markReviewed
                    icon.color: marked ? Icons.color("reviewed", Kirigami.Theme) : "transparent"
                    text: marked ? i18n("Reviewed") : i18n("Mark reviewed")
                    checkable: false
                    onClicked: pane.run("reviewed", "--reviewed " + root.shellQuote(pane.chatId) + (marked ? " --off" : "")
                                        + (pane.host ? " --host " + root.shellQuote(pane.host) : "") + root.configDirArgs)

                    TipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: parent.marked ? i18n("Reviewed") : i18n("Mark reviewed")
                        subText: parent.marked ? i18n("Click to mark it not reviewed.")
                                               : i18n("Its row stops saying \"to review\", until it changes files again.")
                    }
                }
            }
        }

        // A picture of yours, big: a click anywhere (or × or Esc) closes it,
        // Open shows it in your picture viewer
        Rectangle {
            id: bigView
            anchors.fill: parent
            visible: pane.bigPicture !== ""
            z: 100
            color: Qt.rgba(0, 0, 0, 0.85)

            MouseArea {
                anchors.fill: parent
                onClicked: pane.bigPicture = ""
            }
            Image {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.gridUnit * 2
                source: pane.bigPicture ? "file://" + encodeURI(pane.bigPicture) : ""
                sourceSize.width: width * Screen.devicePixelRatio
                sourceSize.height: height * Screen.devicePixelRatio
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true
            }
            RowLayout {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.openRun
                    text: i18n("Open")
                    onClicked: Qt.openUrlExternally("file://" + encodeURI(pane.bigPicture))
                    PlasmaComponents3.ToolTip.text: i18n("In your picture viewer")
                    PlasmaComponents3.ToolTip.visible: hovered
                    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.close
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Close (Esc)")
                    onClicked: pane.bigPicture = ""
                    PlasmaComponents3.ToolTip.text: text
                    PlasmaComponents3.ToolTip.visible: hovered
                    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
            }
        }
    }
}
