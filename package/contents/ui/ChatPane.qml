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
// Mark reviewed. One window, for the chat root.paneChat.
Window {
    id: pane
    objectName: "talpyDenChatPane"   // (TipArea: tooltips drawn in this window)

    readonly property var chat: root.paneChat || ({})
    readonly property var row: root.paneRow   // its row in the status now (null: not listed)
    readonly property string host: chat.host || ""
    readonly property string chatId: chat.chatId || ""
    readonly property string profileDir: row && row.profileDir ? row.profileDir : (chat.profileDir || "")
    readonly property string sessionId: row && row.sessionId ? row.sessionId : (chat.sessionId || "")
    readonly property string chatName: row && row.name ? row.name : (chat.name || "")
    readonly property string chatState: row ? row.state : "done"
    readonly property bool busy: chatState === "working" || chatState === "waiting"
    readonly property string route: row && row.reply ? row.reply : "background"
    readonly property var permission: row && row.permission && chatState === "waiting" ? row.permission : null
    readonly property var queued: root.queuedMessage(chatId, host)
    readonly property bool reviewPending: row ? root.reviewPending(row, host) : false
    // Chat (your messages and Claude's replies), Steps (its tool calls too)
    // and Review; its screen is in its window (Open its window)
    property string tab: "chat"
    // its task list (when it has one, the row's): a strip under the header, folded (tasksOpen: unfolded)
    readonly property var tasks: row && row.tasks && row.tasks.total > 0 ? row.tasks : null
    property bool tasksOpen: false
    readonly property string nextTask: {
        for (const t of tasks ? tasks.items : [])
            if (t.status !== "completed")
                return t.subject
        return ""
    }
    // (its subagents, the running ones first, when the strip is unfolded)
    readonly property var taskAgents: !tasksOpen || !row || !row.agents ? []
        : row.agents.tree.filter(a => a.status === "running").concat(row.agents.tree.filter(a => a.status !== "running"))
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
        root.closePane()
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
    readonly property var mdStyle: ({
        pt: pt, mono: monoFamily, text: hex(textColor), muted: hex(mutedColor),
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
        font.pointSize: pane.pt
    }
    // Code in a fixed-width font: the desktop's, if it is one (it can be set to any font), else monospace
    FontMetrics {
        id: fixedFm
        font.family: surface.Kirigami.Theme.fixedWidthFont.family
    }
    readonly property string monoFamily: Math.abs(fixedFm.advanceWidth("iiii") - fixedFm.advanceWidth("WWWW")) < 0.5
                                         ? surface.Kirigami.Theme.fixedWidthFont.family : "monospace"
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

    // A code block's Copy
    TextEdit {
        id: clipboard
        visible: false
    }
    function copyText(text) {
        clipboard.text = text
        clipboard.selectAll()
        clipboard.copy()
        clipboard.text = ""
        info = i18n("Copied")
        infoBad = false
        infoTimer.restart()
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
        sending = false
        sendStale.stop()
        askHow = false
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
    property bool ready: false   // (nothing runs while the window is being made)
    onChatIdChanged: if (ready) reset()
    Component.onCompleted: {
        ready = true
        reset()
    }
    Connections {
        target: root
        function onPaneDraftChanged() {   // (a reply from a notification, for a terminal that takes no text)
            if (root.paneDraft) {
                replyBox.text = root.paneDraft
                replyBox.cursorPosition = replyBox.text.length
                pane.askHow = true
                root.paneDraft = ""
            }
        }
        function onImagePasted(path, target) {   // (Ctrl+V: a picture, saved; an SSH host's copied there)
            if (target !== "pane")
                return
            const at = replyBox.cursorPosition
            replyBox.insert(at, (at > 0 && replyBox.text.charAt(at - 1).trim() !== "" ? " " : "") + "[Image: " + path + "] ")
            replyBox.forceActiveFocus()
        }
        function onFileAttached(path, target) {   // (a file dropped on the pane: named, as Claude's @ does)
            if (target !== "pane")
                return
            const at = replyBox.cursorPosition
            const named = /\s/.test(path) ? "@\"" + path + "\"" : "@" + path
            replyBox.insert(at, (at > 0 && replyBox.text.charAt(at - 1).trim() !== "" ? " " : "") + named + " ")
            replyBox.forceActiveFocus()
        }
        function onPaneNote(message) {
            pane.info = message
            pane.infoBad = true
            infoTimer.restart()
        }
        function onPaneDenyingChanged() {   // (Deny with a note, from a notification)
            if (root.paneDenying) {
                askColumn.denyWithNote()
                root.paneDenying = false
            }
        }
        function onPaneTypingChanged() {   // (Other…, from a question's notification)
            if (root.paneTyping) {
                askColumn.typeAnswer()
                root.paneTyping = false
            }
        }
        function onPaneChatChanged() {
            if (root.paneChat && root.paneChat.tab)
                pane.tab = root.paneChat.tab
            pane.raise()
            pane.requestActivate()
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
        const cmd = "python3 -I " + root.shellQuote(root.codeDir + "pane.py") + " " + args
                    + (kind === "conversation" ? "" : " # " + Date.now())   // (read again and again: one name)
        runs[cmd] = { kind: kind, chat: chatId, host: host, target: row || chat, sent: sent || "", draft: draftKey }
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
        interval: pane.host || pane.followsLive ? 5000 : 1500
        running: pane.shown && pane.chatId !== ""
        repeat: true
        onTriggered: pane.load()
    }
    Connections {
        target: Hub
        function onLive(views) {
            if (pane.shown && !pane.host && pane.sessionId && views.some(v => v.sessionId === pane.sessionId))
                pane.load()
        }
    }

    // The items in place (by key): rows keep their state, the list its position
    function merge(list) {
        const wanted = {}
        list.forEach(i => wanted[i.key] = true)
        for (let i = items.count - 1; i >= 0; i--) {
            if (!wanted[items.get(i).key])
                items.remove(i)
        }
        for (let i = 0; i < list.length; i++) {
            const it = list[i]
            const flat = { kind: it.kind, key: String(it.key), text: it.text || "", line: it.line || "",
                           name: it.name || "", status: it.status || "", input: it.input || "", output: it.output || "",
                           summary: it.summary || "", at: it.at || 0, bad: !!it.error, prev: i > 0 ? list[i - 1].kind : "",
                           diff: (it.diff || []).join("\n") }
            if (i < items.count && items.get(i).key === flat.key) {
                const old = items.get(i)
                if (old.text !== flat.text || old.status !== flat.status || old.output !== flat.output
                        || old.input !== flat.input || old.summary !== flat.summary || old.prev !== flat.prev || old.diff !== flat.diff)
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
    // your past prompts in its folder. Tab or Enter takes the one marked, Esc
    // closes the list.
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

    // ↑ / ↓: your past prompts there, newest first (what you were typing comes back after the last)
    function historyStep(step) {
        const list = offers ? offers.history : []
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
                    info = i18n("Your message to %1 didn't go: %2", asked.target && asked.target.name ? asked.target.name : i18n("the chat before"),
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
            loadError = ""
            if (result.unchanged)
                return
            const following = !loaded || nearEnd()
            stamp = result.stamp || ""
            more = !!result.more
            merge(result.items || [])
            loaded = true
            if (following)
                keepEnd()
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
        if (kind === "send" || kind === "later") {
            sending = false
            sendStale.stop()
        }
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
        if (kind === "deny" || kind === "answer")
            answering = Math.max(0, answering - 1)
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
    property var drafts: ({})     // what you were typing to the other chats ("host\nchatId" -> text)
    property string draftKey: ""  // the chat the box's text is for
    property bool sending: false  // a message on its way: none other till it's there (an Enter again, a click)

    // (one that never comes back: Send works again after a while)
    Timer {
        id: sendStale
        interval: pane.staleMs
        onTriggered: pane.sending = false
    }

    function send(how, afterTurn) {
        const text = replyBox.text.trim()
        if (!text || sending)
            return
        // (it goes on the command line: one too long for it is refused here, as
        // VS Code does, and stays in the box)
        if (text.length > 100000 || utf8Length(text) > 120000) {
            info = i18n("That message is too long")
            infoBad = true
            infoTimer.restart()
            return
        }
        sending = true
        sendStale.restart()
        run(afterTurn ? "later" : "send", "--send " + root.shellQuote(chatId) + " --text " + root.shellQuote(text)
            + (sessionId ? " --session " + root.shellQuote(sessionId) : "") + " --how " + (how || "auto")
            + (afterTurn ? " --after-turn --name " + root.shellQuote(chatName) : "") + paneArgs(), replyBox.text)
        if (afterTurn)
            replyBox.text = ""
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
        const where = host ? " " + i18n("(on %1)", host) : ""
        if (route === "tmux")
            return i18n("Typed into its tmux pane.") + where
        if (route === "vscode")
            return i18n("Goes into the chat's input in VS Code: press Enter there.") + where
        if (route === "terminal")
            return i18n("Its terminal takes no text from outside: Enter copies your message and opens its tab, to paste it there. Send, go on in the background: Claude there quits and the chat goes on in the background.") + where
        if (row && row.pid && row.kind === "bg")
            return i18n("Its background chat stops, then goes on with your message.") + where
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
    function answer(decision, note, answers) {
        const p = permission
        if (!p || (p.answer !== "hook" && p.answer !== "keys"))
            return
        answering += 1
        answerStale.restart()
        if (p.answer === "hook")
            run(decision === "deny" ? "deny" : "answer", "--answer " + root.shellQuote(p.request) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (answers ? " --answers " + root.shellQuote(JSON.stringify(answers)) : "")
                + (host ? " --host " + root.shellQuote(host) : "") + root.configDirArgs)
        else if (p.answer === "keys")
            run(decision === "deny" ? "deny" : "answer", "--keys " + root.shellQuote(sessionId) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (p.toolUse ? " --expect " + root.shellQuote(p.toolUse) : "") + paneArgs())
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
                    root.attachFiles(paths, pane.host, "pane")
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
                    text: pane.host ? i18n("Drop a picture: it's copied to %1 for your reply", pane.host)
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
                    text: pane.host
                    tooltip: i18n("This chat runs on the SSH host %1.", pane.host)
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
                        subText: i18n("The terminal or VS Code tab the chat runs in; a chat that isn't open reopens in a terminal.")
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
                    tooltip: pane.host ? i18n("The plan this chat made. Click to read it: a copy, fetched from %1.", pane.host)
                                       : i18n("The plan this chat made. Click to read it, rendered.")
                }
                Tag {
                    readonly property var agents: pane.row && pane.row.agents ? pane.row.agents : null
                    visible: agents !== null && agents.total > 0
                    text: agents ? i18nc("subagents finished/total", "Agents %1/%2", agents.done, agents.total) : ""
                    active: agents !== null && agents.running > 0
                    tooltipTitle: i18n("Subagents")
                    tooltip: !agents ? "" : i18n("%1 done, %2 running, %3 stopped", agents.done, agents.running, agents.stopped)
                                            + (agents.failed ? i18n(", %1 failed", agents.failed) : "")
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: (pane.host ? pane.host + ":" : "") + (pane.row ? pane.row.cwdShort || pane.row.cwd || "" : pane.chat.cwd || "")
                    font.family: pane.monoFamily
                    font.pointSize: pane.pt * 0.85
                    color: pane.mutedColor
                    elide: Text.ElideMiddle
                }
            }

            // Its tasks, when it has a task list: a progress bar and "3/7 · what it's on", folded; unfolded,
            // the tasks (✓ done, ▸ the one it's on, ○ to do) and its subagents with what each does now, made
            // only then (the window opens as quickly)
            ColumnLayout {
                visible: pane.tasks !== null
                Layout.fillWidth: true
                spacing: 0

                MouseArea {
                    id: tasksFold
                    Layout.fillWidth: true
                    implicitHeight: tasksLine.implicitHeight + Kirigami.Units.smallSpacing
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    activeFocusOnTab: true
                    onClicked: pane.tasksOpen = !pane.tasksOpen
                    Keys.onReturnPressed: pane.tasksOpen = !pane.tasksOpen
                    Keys.onSpacePressed: pane.tasksOpen = !pane.tasksOpen
                    Accessible.role: Accessible.Button
                    Accessible.name: tasksText.text

                    RowLayout {
                        id: tasksLine
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: pane.tasksOpen ? Icons.plasma.unfolded : Icons.plasma.folded
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
                                width: parent.width * (pane.tasks ? pane.tasks.done / Math.max(1, pane.tasks.total) : 0)
                                height: parent.height
                                radius: parent.radius
                                color: Kirigami.Theme.positiveTextColor
                            }
                        }
                        PlasmaComponents3.Label {
                            id: tasksText
                            Layout.fillWidth: true
                            textFormat: Text.PlainText
                            text: !pane.tasks ? ""
                                  : i18nc("tasks done/total · the one it's on", "%1/%2 · %3", pane.tasks.done, pane.tasks.total,
                                          pane.tasks.current || (pane.tasks.done >= pane.tasks.total ? i18n("all done") : i18n("next: %1", pane.nextTask)))
                            font.pointSize: pane.pt * 0.9
                            font.underline: tasksFold.containsMouse || tasksFold.activeFocus
                            elide: Text.ElideRight
                        }
                    }
                }
                Loader {
                    active: pane.tasksOpen && pane.tasks !== null
                    visible: active
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                    sourceComponent: ColumnLayout {
                        spacing: 0
                        Repeater {
                            model: pane.tasks ? pane.tasks.items.length : 0
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
                        // its subagents: what each does now (the ones still running first)
                        Repeater {
                            model: pane.taskAgents.length
                            delegate: RowLayout {
                                required property int index
                                readonly property var agent: pane.taskAgents[index] || ({ status: "", description: "", type: "", activity: "" })
                                Layout.fillWidth: true
                                Layout.topMargin: index === 0 ? Kirigami.Units.smallSpacing : 0
                                spacing: Kirigami.Units.smallSpacing
                                Rectangle {
                                    Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 0.4)
                                    Layout.preferredHeight: Layout.preferredWidth
                                    radius: width / 2
                                    // (as the row's subagents: SessionRow.qml)
                                    color: agent.status === "running" ? Kirigami.Theme.focusColor
                                         : agent.status === "done" ? Kirigami.Theme.positiveTextColor
                                         : agent.status === "failed" ? Kirigami.Theme.negativeTextColor : pane.mix(pane.textColor, 0.35)
                                }
                                PlasmaComponents3.Label {
                                    Layout.fillWidth: true
                                    textFormat: Text.PlainText
                                    text: (agent.description || agent.type)
                                          + (agent.status === "running" ? (agent.activity ? ": " + agent.activity : "")
                                             : " · " + (agent.status === "done" ? i18n("done") : agent.status === "failed" ? i18n("failed")
                                                        : i18n("stopped")))
                                    elide: Text.ElideRight
                                    opacity: agent.status === "running" ? 0.9 : 0.6
                                    font.pointSize: pane.pt * 0.85
                                }
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
                        readonly property bool unfolded: pane.openTools[key] === true
                        // more room before your prompt (a new turn) than between steps
                        readonly property real gap: index === 0 ? 0
                            : kind === "you" ? Kirigami.Units.gridUnit * 1.6
                            : kind === "tool" && prev === "tool" ? Kirigami.Units.smallSpacing * 1.5
                            : Kirigami.Units.gridUnit * 0.8
                        readonly property bool shows: kind !== "tool" || pane.listTab === "steps"
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

                        // Yours: a band in your accent color, after a ›
                        Component {
                            id: youItem

                            Rectangle {
                                implicitHeight: youRow.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                                radius: Kirigami.Units.cornerRadius
                                color: Qt.tint(Kirigami.Theme.backgroundColor, Qt.rgba(pane.youColor.r, pane.youColor.g, pane.youColor.b, 0.13))

                                Rectangle {
                                    width: 3
                                    height: parent.height
                                    radius: 1.5
                                    color: pane.youColor
                                }
                                RowLayout {
                                    id: youRow
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.rightMargin: Kirigami.Units.largeSpacing
                                    spacing: 0

                                    PlasmaComponents3.Label {
                                        Layout.preferredWidth: pane.gutter
                                        Layout.alignment: Qt.AlignTop
                                        horizontalAlignment: Text.AlignHCenter
                                        textFormat: Text.PlainText
                                        text: "›"
                                        color: pane.youColor
                                        font.pointSize: pane.pt
                                        font.weight: Font.Bold
                                    }
                                    TextEdit {
                                        Layout.fillWidth: true
                                        text: entry.text
                                        textFormat: TextEdit.PlainText
                                        readOnly: true
                                        selectByMouse: true
                                        wrapMode: TextEdit.Wrap
                                        color: Kirigami.Theme.textColor
                                        selectionColor: Kirigami.Theme.focusColor
                                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        font.family: Kirigami.Theme.defaultFont.family
                                        font.pointSize: pane.pt
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
                                    Layout.fillWidth: true
                                    text: Md.toHtml(entry.text, pane.mdStyle)
                                    textFormat: TextEdit.RichText
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: Kirigami.Theme.textColor
                                    selectionColor: Kirigami.Theme.focusColor
                                    selectedTextColor: Kirigami.Theme.highlightedTextColor
                                    font.family: Kirigami.Theme.defaultFont.family
                                    font.pointSize: pane.pt
                                    onLinkActivated: link => {
                                        if (link.indexOf("copy:") === 0)
                                            pane.copyText(Md.codeBlocks(entry.text)[Number(link.slice(5))] || "")
                                        else
                                            Qt.openUrlExternally(link)
                                    }

                                    HoverHandler {
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
                                                text: toolBox.args ? "<b>" + Md.escape(entry.name) + "</b>&nbsp;&nbsp;<font face=\"" + pane.monoFamily
                                                                     + "\" color=\"" + pane.hex(pane.codeColor) + "\">" + Md.escape(toolBox.args) + "</font>"
                                                                   : "<b>" + Md.escape(entry.line) + "</b>"
                                                wrapMode: Text.Wrap
                                                maximumLineCount: entry.unfolded ? 20 : 2
                                                elide: Text.ElideRight
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
                        onClicked: root.unqueue(pane.queued)
                    }
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

                        PlasmaComponents3.TextArea {
                            id: replyBox
                            background: null
                            placeholderText: pane.permission ? i18n("It's asking you something: answer that first")
                                                             : i18n("Reply to Claude… (Enter sends, Shift+Enter: new line; Ctrl+V or drop: a picture or a file too)")
                            wrapMode: TextEdit.Wrap
                            font.pointSize: pane.pt
                            enabled: !(pane.permission && pane.route === "tmux")
                            // Enter sends, as in Claude's own prompt (Shift+Enter: a new line). For a
                            // terminal that takes no text from outside, Enter copies it and opens its
                            // tab (pane.py how enter): Claude there never quits on an Enter.
                            // Ctrl+V with no text on the clipboard: its picture (an SSH host's
                            // chat asks to copy it there).
                            onTextChanged: {
                                if (pane.historyAt >= 0 && text !== (pane.offers ? pane.offers.history[pane.historyAt] : ""))
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
                                    root.pasteImage(pane.host, "pane")
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
                             && root.pictureOffer.target === "pane"
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
                        text: i18n("Copy this picture to %1? Claude there can only open it there.", pane.host)
                        confirmText: i18n("Copy")
                        onConfirmed: root.copyPicture()
                        onCancelled: root.pictureOffer = null
                    }
                }
                PlasmaComponents3.Label {
                    visible: !!pane.host && root.pictureCopyingTo === pane.host && root.pictureCopyTarget === "pane"
                    textFormat: Text.PlainText
                    text: i18n("Copying the picture to %1…", pane.host)
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
                            onClicked: root.pickFiles(pane.host, "pane", pane.row ? pane.row.cwd || "" : pane.chat.cwd || "")

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Attach files…")
                                subText: pane.host ? i18n("Pick pictures for your reply (copied to %1 once you say so).", pane.host)
                                                   : i18n("Pick files for your reply: a picture goes in as one, another file is named for Claude to read. You can drop them on the pane too.")
                            }
                        }
                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.screenshot
                            text: i18n("Screenshot…")
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            onClicked: root.takeScreenshot(pane.host, "pane")

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
                            enabled: replyBox.text.trim() !== "" && !pane.sending
                            icon.name: Icons.plasma.copy
                            text: i18n("Copy and open its tab")
                            onClicked: pane.send("copy", false)
                        }
                        PlasmaComponents3.Button {
                            visible: pane.busy
                            enabled: replyBox.text.trim() !== "" && !pane.sending
                            icon.name: Icons.plasma.later
                            text: i18n("Send when this turn ends")
                            onClicked: pane.send(pane.route === "terminal" ? "background" : "auto", true)

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Send when this turn ends")
                                subText: i18n("Talpy Den keeps it and sends it once Claude's turn is over (also with the popup closed).")
                            }
                        }
                        PlasmaComponents3.Button {
                            enabled: replyBox.text.trim() !== "" && !pane.sending && !(pane.route === "terminal" && pane.busy)
                                     && !(pane.permission && pane.route === "tmux")
                            icon.name: Icons.plasma.send
                            text: pane.sending ? i18n("Sending…") : pane.route === "terminal" || pane.askHow ? i18n("Send, go on in the background") : i18n("Send")
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
    }
}
