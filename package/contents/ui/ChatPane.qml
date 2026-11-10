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

    property var chat: ({})   // {chatId, sessionId, profileDir, host, name, cwd, tab, fresh, startedAt}: none while it's closed
    // A new chat (main.qml openNewChat): {profile, account, cwd, short, plan}, till your first
    // message starts it in the background (pane.py --start); its chatId stands in till then
    readonly property var fresh: chat.fresh || null
    property string lastKey: ""   // (closed: the chat it showed, opened in it again: main.qml)
    readonly property var row: root.paneRowOf(chat)   // its row in the status now (null: not listed)
    readonly property string host: chat.host || ""
    readonly property string chatId: chat.chatId || ""
    readonly property string profileDir: row && row.profileDir ? row.profileDir : (chat.profileDir || "")
    readonly property string sessionId: row && row.sessionId ? row.sessionId : (chat.sessionId || "")
    readonly property string chatName: row && row.name ? row.name : (chat.name || (fresh ? i18n("New chat in %1", fresh.short) : ""))
    // Your first message started it, and it isn't listed yet: "Starting…" on its working line
    readonly property bool starting: (!!fresh && pendingSent.some(p => p.chat === chatId && p.state !== "held"))
                                     || (!!chat.startedAt && !row)
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
    readonly property bool replyDenies: replyAnswers === "deny" || replyAnswers === "decline"
    readonly property bool replyKeepsPlanning: replyAnswers === "plan"
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
    // Where it runs (the tag under its name): "new" (not started yet: fresh),
    // "background" (a background session), "closed" (no process: a reply goes
    // on in the background), "claude" (VS Code's Claude Code panel), "tmux",
    // "vscode" (a terminal of VS Code) or "terminal" (another terminal)
    readonly property string where: starting ? "background" : fresh ? "new" : !row || !row.pid ? "closed" : row.kind === "bg" ? "background"
                                    : row.entrypoint === "claude-vscode" ? "claude" : row.tmux ? "tmux"
                                    : row.vscodeTerminal || row.terminalApp === "VS Code" ? "vscode" : "terminal"
    // Stop on its working line, while Claude works on its turn (as Esc in its terminal: what Claude
    // does now stops, the chat stays and takes your next message): a chat in tmux (Ctrl+C in its
    // pane), a background chat on a Claude Code version that was checked on (its row's bgStop: Esc
    // through Claude's background service). pane.py --interrupt; VS Code: shared/pane.ts stopOf
    readonly property bool atWork: chatState === "working" && !!row && row.reason !== "background shell"
    readonly property bool canStop: atWork && !!row.pid && (where === "tmux" || (where === "background" && !!row.bgStop))
    // (else, on its working line's tooltip: where it can be stopped)
    readonly property string stopElsewhere: !atWork || canStop ? ""
        : where === "claude" ? i18n("To stop it: the stop button in its Claude Code panel.")
        : where === "background" ? i18n("To stop it: open it in a terminal and press Esc there. Talpy Chat's Stop doesn't know the background chats of this Claude Code version yet.")
        : i18n("To stop it: press Esc in its terminal. Talpy Chat can't type into that terminal.")
    property bool stopping: false   // (Stop clicked: "Stopping…" till its turn ends, it says why not, or 15 s)
    onAtWorkChanged: if (!atWork) stopping = false
    function stop() {
        if (stopping || !canStop)
            return
        stopping = true
        stopWait.restart()
        run("interrupt", "--interrupt " + root.shellQuote(chatId)
            + (sessionId && sessionId !== chatId ? " --session " + root.shellQuote(sessionId) : "") + paneArgs())
    }
    Timer {
        id: stopWait
        interval: 15000
        onTriggered: pane.stopping = false
    }

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
    // Copy on a message (hover: MessageTools.qml says Copied), or Ctrl+Shift+C: all of it. A text
    // Talpy Chat keeps cut ("…" on a line of its own at its end) is read whole from the transcript
    // first (pane.py --reply-text, off this thread); Copied once it's on the clipboard, else why not
    property string copiedKey: ""
    Timer {
        id: copiedTimer
        interval: 1500
        onTriggered: pane.copiedKey = ""
    }
    function copied(key, hover) {
        if (hover) {
            copiedKey = key
            copiedTimer.restart()
        } else {
            info = i18n("Copied Claude's last reply")
            infoBad = false
            infoTimer.restart()
        }
    }
    function copyItem(key, text, hover) {
        if (!text)
            return
        if (!text.endsWith("\n…") || fresh) {
            copyText(text, true)
            copied(key, hover)
            return
        }
        start("--reply-text " + root.shellQuote(chatId) + " --key " + root.shellQuote(key)
              + paneArgs() + " # " + Date.now(),
              { kind: "copy", chat: chatId, host: host, key: key, hover: hover })
    }
    function copyLast() {
        for (let i = lastItems.length - 1; i >= 0; i--)
            if (lastItems[i].kind === "claude")
                return copyItem(String(lastItems[i].key), lastItems[i].text || "", false)
        info = i18n("Claude hasn't replied in this chat yet")
        infoBad = true
        infoTimer.restart()
    }

    // ---------------------------------------------------------------- keys
    //
    // Talpy Chat's keys (keys.mjs; VS Code's the same; ? in an empty box lists them, KeysHelp.qml).
    // Not Shortcuts: Plasma gives every button an Alt+letter of its own (Kirigami's mnemonics, one
    // list for all of Plasma), so a Shortcut on Alt+A would be one of two and work every other
    // press. surface and the reply box take them first, at the ShortcutOverride, only when they're
    // Talpy Chat's and do something now; the box keeps the editing keys it takes itself (Ctrl+Home,
    // Shift+arrows…). What each does: PaneKeys.qml, read and made once the window shows (so a
    // window opens as quickly); keyAction: the key's id, or "" (not ours, or nothing to do now)
    Loader {
        id: paneKeys
        active: false
        asynchronous: true
        source: active ? "PaneKeys.qml" : ""
    }
    Loader {
        id: editMenu
        active: false
        source: active ? "EditMenu.qml" : ""
    }
    function keyAction(event) {
        return paneKeys.item ? paneKeys.item.keyAction(event) : ""
    }
    function takeKey(event) {
        return !!paneKeys.item && paneKeys.item.takeKey(event)
    }
    property bool helpOn: false
    property var ghostOff: null   // (Esc on the grey completion: none for that text)
    property real activeAt: 0     // (when it was last in front: Ctrl+Tab, main.qml nextPaneWindow)
    onActiveChanged: if (active) activeAt = Date.now()
    // (focus that falls back to the window, a field gone or turned off: surface's, so the keys still work)
    onActiveFocusItemChanged: if (active && activeFocusItem === contentItem) surface.forceActiveFocus()

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
    property var openTools: ({})   // key -> unfolded: a step's details, a long text ("<key>/out": its output); unsaid: foldOpen's
    // Long texts fold (find.mjs foldOf: past about 40 lines, their first 24 show, then Show more:
    // FoldMore.qml). Unsaid, what the window first read folds, but Claude's last reply then; what
    // comes in while it shows doesn't (you watch it come); only a click, a search's step into it and
    // Ctrl+O change one. Ctrl+O unfolds every long text and answered question or plan (allOpen; not a
    // step's details), again: each back as it was
    property bool allOpen: false
    property int allGen: 0         // (each Ctrl+O's: a row is unfolded once its turn came, late === allGen: FoldAll.qml)
    property int lateDefault: 0    // (and a row made after its turns: at once)
    property var openBefore: ({})
    property var firstRead: null   // {at, last}: when it first read the chat, Claude's last reply then
    function foldText(text, how) {   // (FoldHelp.qml, find.mjs: read only once a text may be long)
        let lines = 1
        for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1))
            lines++
        if (lines + text.length / 100 <= 40)
            return null
        foldHelp.active = true
        return foldHelp.item.foldOf(text, how)
    }
    Loader {
        id: foldHelp
        active: false
        source: active ? "FoldHelp.qml" : ""
    }
    Loader {
        id: foldAllRows   // (Ctrl+O: the rows unfolded a few at a time, nearest what you read first)
        active: false
        source: active ? "FoldAll.qml" : ""
    }
    // (Ctrl+O: every long text and answered question or plan unfolded, not a step's details; again,
    // each back as it was; what you read stays where it is while it's laid out again)
    function foldAll() {
        const end = !loaded || nearEnd()
        chatTop = end ? null : topMessage(true)
        const next = Object.assign({}, openTools), kept = {}
        for (const it of shownList) {
            const keys = it.kind === "you" || it.kind === "claude" ? [String(it.key), it.key + "/out"]
                       : it.kind === "tool" && askedShows(it.asked, false) ? [String(it.key)] : []
            for (const k of keys) {
                if (!allOpen && next[k] !== undefined)
                    kept[k] = next[k]
                if (allOpen || next[k] === false)   // (one you unfolded stays so meanwhile, not folded a moment)
                    delete next[k]
            }
        }
        if (allOpen) {
            allOpen = false
            openTools = Object.assign(next, openBefore)
        } else {
            openBefore = kept
            openTools = next
            allGen++
            allOpen = true
            foldAllRows.active = true
            foldAllRows.item.unfoldAll()
        }
        if (end)
            keepEnd()
        else {
            showTop()
            holdTop.interval = 2500   // (every step's details are made a few a frame)
            holdTop.restart()
        }
    }
    // Show more / Show less (now: it shows all of it now); Show less keeps its button where it was,
    // under the pointer: the text above it folds away, not what's below
    property Item foldButton: null
    property real foldButtonAt: 0
    function toggleFold(key, now, button) {
        const next = Object.assign({}, openTools)
        next[key] = !now
        foldButton = now ? button : null
        foldButtonAt = now ? button.mapToItem(list, 0, 0).y : 0
        openTools = next
        if (now)
            foldKeep.restart()
    }
    Timer {
        id: foldKeep
        interval: 0
        property int left: 2
        onTriggered: {
            const b = pane.foldButton
            if (b && b.visible) {
                settle.stop()
                holdTop.stop()
                list.contentY += b.mapToItem(list, 0, 0).y - pane.foldButtonAt
            }
            if (--left > 0)
                restart()
            else {
                left = 2
                pane.foldButton = null
            }
        }
    }
    // Search (Ctrl+F): FindBar.qml over the list's top right, read and made only while it's open
    // (what it looks for stays for the next time); the conversation as the list shows it, in order
    property bool findOn: false
    property string findQuery: ""
    property var shownList: []
    function openFind() {
        if (!conversationTab)
            return
        if (findOn && findBar.item)
            findBar.item.focusField()
        findOn = true
    }
    function closeFind() {
        findOn = false
        replyBox.forceActiveFocus()
    }
    property string info: ""
    property bool infoBad: false

    ListModel {
        id: items
    }

    function reset() {
        tasksOpen = false
        agentsOpen = false
        stopping = false
        offers = null
        offersAt = 0
        sendAfterOffers = ""
        commandBusy = false
        suggestions = []
        historyAt = -1
        turnEnded = ""
        turnOver = false
        asks = null
        contextLeft = null
        turnNow = null
        usual = null
        usualAt = 0
        chipsSeen = []
        chipsIgnored = 0
        items.clear()
        seenKeys = null
        unseen = 0
        stamp = ""
        limit = 120
        more = false
        loaded = false
        loadError = ""
        openTools = {}
        allOpen = false
        openBefore = {}
        firstRead = null
        shownList = []
        findOn = false   // (another chat: its find bar closed; what it looked for stays for Ctrl+F)
        info = ""
        review = null
        reviewFor = ""
        reviewLoading = false
        commitOpen = false
        commitMessage = ""   // (the chat before's message: this one's comes with its review)
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
                Object.assign(m.asked, { chat: chatId, draft: draftKey, fresh: null })
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
        newDay()   // (when midnight is: two Dates)
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
    function run(kind, args, sent, answerId) {   // (answerId: an answer's, shown at once: addAnswer)
        start(args + (kind === "conversation" ? "" : " # " + Date.now()),   // (read again and again: one name)
              { kind: kind, chat: chatId, host: host, target: row || chat, sent: sent || "", draft: draftKey, answerId: answerId || 0 })
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
        if (fresh) {   // (nothing to read yet: it's shown empty, ready for your first message)
            loaded = true
            return
        }
        if (loading && Date.now() - loadingSince < staleMs) {
            loadAgain = true
            return
        }
        loading = true
        loadingSince = Date.now()
        run("conversation", "--conversation " + root.shellQuote(chatId) + " --limit " + limit
            + (stamp ? " --if-changed " + root.shellQuote(stamp) : "") + (suggestOn ? " --suggest" : "") + paneArgs())
    }

    // Live (hub/Hub.qml): with the live hook, the conversation is read the
    // moment the chat does a step or changes state, and the timer is only
    // there for what comes without one (a long reply being written)
    readonly property bool followsLive: !host && root.watching && root.liveHook
    // (minimized, it reads nothing: once it's back, the conversation now)
    readonly property bool shown: visible && visibility !== Window.Minimized
    onShownChanged: {
        if (shown)
            paneKeys.active = true   // (its keys: made once it shows)
        if (shown)
            newDay()
        if (shown && loaded)
            load()
    }
    Timer {
        // (with the watcher, only for what it can't see: a moment it wasn't running)
        interval: pane.host ? 5000 : pane.watchOk ? 15000 : pane.followsLive ? 5000 : 1500
        running: pane.shown && pane.chatId !== "" && !pane.fresh
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
                     + " --limit " + limit + " --if-changed " + root.shellQuote(stamp) + " --wait 50" + (suggestOn ? " --suggest" : "") + paneArgs()
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
        if (firstRead === null && lastItems.length) {
            let last = ""
            for (let i = lastItems.length - 1; i >= 0 && last === ""; i--)
                if (lastItems[i].kind === "claude")
                    last = String(lastItems[i].key)
            firstRead = { at: Date.now(), last: last }
        }
        const handoff = {}
        merge(withPending(lastItems, handoff), handoff)
        countUnseen()
        // (how its turn ended: its chips, made once the conversation is in the list)
        turnEnded = result.ended || ""
        turnOver = !!result.over
        asks = result.asks || null
        contextLeft = result.context || null
        turnNow = result.turn || null
        if (turnEnded !== "" && usual === null)
            usualSoon.restart()
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
        // Each item's day (its start, ms), the latest so far (a message still in Claude's queue is
        // listed last, with the time you sent it), the first one's for those before any time; a
        // Date is made once a day, not once an item. The days each tab shows something of, and
        // the first of them: DayLine.qml's (VS Code shared/pane.ts dayBreaks: the same rule)
        const first = list.find(it => it.at)
        let day = first ? dayStart(first.at) : 0
        let dayEnd = first ? dayStart(first.at, 1) : 0
        const days = { chat: {}, steps: {} }, firsts = { chat: 0, steps: 0 }
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
            if (it.at && it.at >= dayEnd) {
                day = dayStart(it.at)
                dayEnd = dayStart(it.at, 1)
            }
            if (it.kind !== "tool" || askedShows(it.asked, false) || (it.asked && it.asked.state === "denied")) {
                days.chat[day] = true
                firsts.chat = firsts.chat || day
            }
            days.steps[day] = true
            firsts.steps = firsts.steps || day
            const flat = { kind: it.kind, key: String(it.key), text: it.text || "", line: it.line || "",
                           name: it.name || "", status: it.status || "", input: it.input || "", output: it.output || "",
                           summary: it.summary || "", at: it.at || 0, bad: !!it.error, prev: i > 0 ? list[i - 1].kind : "",
                           diff: (it.diff || []).join("\n"), queued: !!it.queued, until: it.until || 0,
                           pictures: (it.pictures || []).join("\n"), here: (it.here || []).join("\n"),
                           asked: it.asked ? JSON.stringify(it.asked) : "", answered: it.answered || "",
                           command: it.command ? JSON.stringify(it.command) : "", day: day, fold: "" }
            if (i < items.count && items.get(i).key === flat.key) {
                const old = items.get(i)
                if (old.text !== flat.text || old.status !== flat.status || old.output !== flat.output
                        || old.input !== flat.input || old.summary !== flat.summary || old.prev !== flat.prev || old.diff !== flat.diff
                        || old.queued !== flat.queued || old.until !== flat.until || old.pictures !== flat.pictures
                        || old.here !== flat.here || old.asked !== flat.asked || old.answered !== flat.answered
                        || old.command !== flat.command || old.day !== flat.day)
                    items.set(i, withFold(flat, it))
            } else if (i < items.count) {
                items.insert(i, withFold(flat, it))
            } else {
                items.append(withFold(flat, it))
            }
        }
        while (items.count > list.length)
            items.remove(items.count - 1)
        shownList = list
        daysShown = days
        firstDays = firsts
    }

    // (a row put in or changed: where its long text folds, worked out then, not at each read)
    function withFold(flat, it) {
        const text = it.kind === "claude" ? foldText(flat.text, "markdown")
                   : it.kind === "you" ? foldText(it.command && it.command.shell ? flat.text.replace(/^!\s*/, "") : shownText(flat.text), "plain") : null
        const out = it.kind === "you" && it.command && it.command.output ? foldText(it.command.output, "ansi") : null
        if (text || out)
            flat.fold = JSON.stringify({ cut: text ? text.shown : "", more: text ? text.more : 0, outCut: out ? out.shown : "", outMore: out ? out.more : 0,
                                         open: !firstRead || flat.key === firstRead.last || (it.at || 0) > firstRead.at })
        return flat
    }

    // Times (VS Code shared/pane.ts: the same words and rules): a line before the first item of each
    // later day the tab shows ("Today", "Yesterday", "Mon 3 Nov"; the year when it isn't this one:
    // DayLine.qml, the list's section headers), and a message's time on hover ("14:32"; "Yesterday
    // 14:32" for an earlier day: MessageTools.qml)
    property var daysShown: ({ chat: {}, steps: {} })   // tab -> {day: true}
    property var firstDays: ({ chat: 0, steps: 0 })   // tab -> its first day (no line before it)
    function dayStart(ms, after) {   // (the start of ms's day, or of the day after days later)
        const d = new Date(ms)
        return new Date(d.getFullYear(), d.getMonth(), d.getDate() + (after || 0)).getTime()
    }
    function dayLabel(at) {
        const days = Math.round((dayStart(today) - dayStart(at)) / 86400000)
        if (days <= 0)
            return i18n("Today")   // (a host's clock a little ahead: today too)
        if (days === 1)
            return i18n("Yesterday")
        const d = new Date(at)
        return Qt.locale().toString(d, d.getFullYear() !== new Date(today).getFullYear() ? "ddd d MMM yyyy" : "ddd d MMM")
    }
    function timeText(at) {
        return dayStart(at) >= dayStart(Date.now()) ? root.clockText(at)
             : i18nc("a message's day and time", "%1 %2", dayLabel(at), root.clockText(at))
    }
    // Today, for the lines' "Today" and "Yesterday": it moves on at midnight, with one timer that
    // runs only while the window shows (and when it shows again on another day)
    property real today: Date.now()
    function newDay() {
        const now = new Date()
        if (new Date(today).toDateString() !== now.toDateString())
            today = now.getTime()
        midnight.interval = dayStart(now.getTime(), 1) - now.getTime() + 1000
    }
    Timer {
        id: midnight
        interval: 3600000
        repeat: true
        running: pane.shown
        onTriggered: pane.newDay()
    }

    // What came in below while you're scrolled up ("3 new ↓" over the list's bottom: NewBelow.qml):
    // the keys there when you left the end, till you're back at it (VS Code shared/pane.ts newBelow)
    property var seenKeys: null
    property int unseen: 0
    readonly property bool atEnd: list.originY + list.contentHeight - list.contentY - list.height < Kirigami.Units.gridUnit * 2
    onAtEndChanged: {
        if (atEnd) {
            seenKeys = null
            unseen = 0
        } else if (seenKeys === null && loaded) {
            const keys = {}
            for (let i = 0; i < items.count; i++)
                keys[items.get(i).key] = true
            seenKeys = keys
        }
    }
    // (those after the last one there then, that the tab shows: Show earlier's come in above)
    function countUnseen() {
        if (seenKeys === null || settle.running)
            return   // (following the end: it's coming into view)
        let n = 0
        for (let i = items.count - 1; i >= 0; i--) {
            const it = items.get(i)
            if (seenKeys[it.key]) {
                unseen = n
                return
            }
            if (listTab === "steps" || it.kind !== "tool" || (it.asked !== "" && (askedShows(JSON.parse(it.asked), false) || JSON.parse(it.asked).state === "denied")))
                n++
        }
        unseen = 0   // (none of those there then: nothing to tell)
    }
    function toEnd() {
        seenKeys = null
        unseen = 0
        keepEnd()
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
        // (a new chat's: its folder's, and your prompts there)
        run("complete", fresh ? "--complete - --cwd " + root.shellQuote(fresh.cwd) + paneArgs()
                              : "--complete " + root.shellQuote(chatId) + paneArgs())
    }

    function suggest() {
        const before = replyBox.text.slice(0, replyBox.cursorPosition)
        // (/model or /effort and a space, on a chat Talpy Chat sets them for: its own list of them)
        const pick = /^\/(model|effort)\s+(\S*)$/.exec(before)
        if (pick && before !== dismissed && (commandRun("/" + pick[1]) || {}).run === "picker") {
            tokenStart = 0
            suggestions = pickerItems(pick[1], pick[2])
            suggestion = 0
            return
        }
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
            // (each with how it runs on this chat: commandRun; one that can't, greyed, says why)
            found = offers.commands.filter(c => c.name.toLowerCase().indexOf(q) >= 0)
                .sort((a, b) => (a.name.toLowerCase().startsWith("/" + q) ? 0 : 1) - (b.name.toLowerCase().startsWith("/" + q) ? 0 : 1)
                                || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))   // (Qt's sort isn't stable)
                .slice(0, 8)
                .map(c => {
                    const ran = commandRun(c.name) || { run: "here", why: "" }
                    return { text: c.name, about: ran.run === "off" ? ran.why : c.about + (c.kind === "Claude" ? "" : " · " + c.kind)
                                                                     + (ran.run === "picker" ? " · " + i18n("this chat") : ""),
                             insert: c.name + " ", off: ran.run === "off",
                             tag: ran.run === "terminal" ? i18nc("a command opens in the chat's terminal", "Terminal")
                                : ran.run === "page" ? i18nc("a command opens Talpy Den's own page for it", "Talpy Den") : "",
                             tip: ran.run === "terminal" ? i18n("%1 %2: it opens in the chat's terminal, typed in for you there.", c.name, ran.why)
                                : ran.run === "page" ? i18n("Opens Talpy Den's Permissions tab: what Claude may do without asking, in every chat.")
                                : ran.run === "picker" ? i18n("For this chat alone: in its terminal, Claude's %1 would also make it your default for every new chat.", c.name) : "" }
                })
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
        if (s.run) {   // (a model or effort of the picker's list: set at once)
            dismissed = replyBox.text.slice(0, replyBox.cursorPosition)
            const p = pickerOf(s.insert)
            if (p && p.value)
                setOptions(p.kind, p.value)
        }
    }

    // ---------------------------------------------------------------- commands
    //
    // A command in the box (/compact, /config, !ls): how Talpy Chat runs it on this chat
    // (VS Code's shared/pane.ts commandRun: the same rule and words), from the / list's
    // offers (pane.py --complete: commands.py's kinds, as checked live per route):
    // {run: "here" (sent as it is: it runs, and what it prints shows under it), "page"
    // (Talpy Den's own page for it: /permissions, the Permissions tab), "terminal" (it needs
    // Claude's own panel or dialog, where a background chat would sit unseen: opened in the
    // chat's terminal, typed in for you there or on the clipboard, to press Enter there) or
    // "off" (it can't run on this chat: why), name, why}; null: a message (or not known)
    function commandRun(text) {
        const t = String(text || "").trim()
        if (/^![^!]/.test(t)) {   // (Claude's ! mode: a shell command, in its prompt only)
            if (where === "new")
                return { run: "off", name: "!", why: i18n("A new chat starts in the background, where Claude reads ! as a message: start it first, then run the command in its terminal.") }
            if (where === "closed")
                return { run: "off", name: "!", why: i18n("A chat that isn't running reads ! as a message, not as a shell command: open it in its terminal to run it there.") }
            return { run: route === "terminal" ? "terminal" : "here", name: "!", why: "" }
        }
        const m = /^\/([^\s\/]+)(?:\s+([\s\S]*))?$/.exec(t)
        if (!m)
            return null
        // (the list's kinds unread, they couldn't be: these three never go as a message all the same)
        const c = offers ? offers.commands.find(x => x.name === "/" + m[1]) || (offers.typed || {})[m[1]] || null
                : m[1] === "model" ? { run: "picker", why: i18n("saves it as your default model for every new chat") }
                : m[1] === "effort" ? { run: "picker", why: i18n("saves it as your default effort for every new chat") }
                : m[1] === "config" ? { run: "terminal", why: i18n("needs Claude's own screen") } : null
        if (!c || !c.run)
            return null
        let run = m[2] && m[2].trim() && c.runArgs ? c.runArgs : c.run
        const name = c.of || "/" + m[1]
        // Talpy Chat's own list (/model, /effort): for a background or closed chat alone (pane.py
        // --set-options); a new one has its ⚙ line; one in a terminal opens Claude's own there
        if (run === "picker") {
            if (where === "new")
                return { run: "off", name: name, why: m[1] === "effort" ? i18n("Pick its effort on the ⚙ line above: it starts with it.")
                                                                        : i18n("Pick its model on the ⚙ line above: it starts with it.") }
            if (where !== "background" && where !== "closed")
                run = "terminal"
        }
        if (run === "terminal" && route === "vscode")
            run = "here"   // (its Claude Code panel's input: you press Enter there, in Claude's own)
        if (run === "terminal" && where === "new")
            return { run: "off", name: name, why: i18n("%1 %2: start the chat first, then it opens in its terminal.", name, c.why || "") }
        return run === "picker" ? { run: run, name: name, why: c.why || "", arg: (m[2] || "").trim() } : { run: run, name: name, why: c.why || "" }
    }
    // Talpy Chat's model and effort list (commandRun "picker"; VS Code's pickerOf, pickLabel, pickerItems)
    readonly property var chatModels: [["opus", i18n("Opus")], ["sonnet", i18n("Sonnet")], ["fable", i18n("Fable")], ["haiku", i18n("Haiku")],
                                       ["", i18n("Claude's default model")]]
    readonly property var chatEfforts: [["low", i18n("Low")], ["medium", i18n("Medium")], ["high", i18n("High")], ["xhigh", i18n("Extra high")],
                                        ["max", i18n("Max")], ["", i18n("Claude's default effort")]]
    function pickerOf(text) {
        const m = /^\/(model|effort)(?:\s+(\S*))?\s*$/.exec(String(text || "").trim())
        return m ? { kind: m[1], value: m[2] || "" } : null
    }
    function pickLabel(kind, value) {
        const v = String(value || "").toLowerCase()
        if (v === "" || v === "default")
            return kind === "model" ? i18n("Claude's default model") : i18n("Claude's default effort")
        const known = (kind === "model" ? chatModels : chatEfforts).find(k => k[0] === v)
        return kind === "effort" ? i18n("%1 effort", known ? known[1] : value) : known ? known[1] : value
    }
    function pickerItems(kind, q) {
        const query = String(q || "").toLowerCase()
        return (kind === "model" ? chatModels : chatEfforts)
            .filter(k => !query || (k[0] || "default").startsWith(query) || k[1].toLowerCase().split(/[\s']+/).some(w => w.startsWith(query)))
            .map(k => ({ text: k[1], about: i18n("for this chat alone"), insert: "/" + kind + " " + (k[0] || "default"), run: true, off: false, tag: "", tip: "" }))
    }
    property bool pickBusy: false   // (a pick on its way: pane.py --set-options)
    function setOptions(kind, value) {
        if (pickBusy)
            return
        pickBusy = true
        start("--set-options " + root.shellQuote(chatId) + " --" + kind + " " + root.shellQuote(value === "default" ? "" : value)
              + paneArgs() + " # " + Date.now(), { kind: "options", chat: chatId, host: host, text: replyBox.text.trim() })
    }
    readonly property var commandNow: commandRun(replyBox.text)
    property string sendAfterOffers: ""   // ("how later"): a / command sent while the offers were being read
    property bool offersFailed: false
    property bool commandBusy: false      // (one on its way to its terminal: --type-in)
    property real commandSince: 0
    // A command for Claude's own panel: put in the chat's terminal, for you to press Enter there
    function openWithCommand(text) {
        if (commandBusy && Date.now() - commandSince < 20000)
            return   // (a second Enter meanwhile doesn't type it twice)
        commandBusy = true
        commandSince = Date.now()
        const target = row || chat
        start("--type-in " + root.shellQuote(chatId) + " --text " + root.shellQuote(text)
              + (sessionId ? " --session " + root.shellQuote(sessionId) : "") + paneArgs() + " # " + Date.now(),
              { kind: "typein", chat: chatId, host: host, target: target, text: text })
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
            if (lastItems[i].kind === "you" && !lastItems[i].answered)   // (your answers aren't prompts to send again)
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

    // ---------------------------------------------------------------- suggested replies
    //
    // Once Claude's turn is over and the box is empty: small chips above it (ReplyChips.qml),
    // the answers to the question Claude ended with (pane.py --conversation --suggest: asks),
    // then what you usually reply after a turn that ended the same way (pane.py --replies, from
    // your chats on its account: asked once a window, again after a send a minute later). What
    // you type is completed in grey from your usual replies (Tab or → takes it: ReplyGhost.qml).
    // VS Code's shared/pane.ts has the same rules and words (chipsOf, chipsWanted, chipsAfterSend,
    // completionOf). Suggest replies off: nothing is read or worked out for it.
    readonly property bool suggestOn: Plasmoid.configuration.suggestReplies !== false
    onSuggestOnChanged: {
        if (!ready)
            return   // (its binding's first value, as the window is made: reset() reads it then)
        usual = null
        usualAt = 0
        stamp = ""   // (read again, with or without how its turn ended)
        load()
    }
    // How full its context is (pane.py: talpy_den.context_left; null: not known), the header's tag; Claude's
    // turn so far while it's going on (talpy_den.TurnSoFar: {startedAt, steps}), its working line's end
    property var contextLeft: null
    property var turnNow: null
    property string turnEnded: ""      // how its last turn ended ("": mid-turn, a message queued, or not asked)
    property bool turnOver: false      // (the transcript says so; else the chat's state does)
    property var asks: null            // the question it ended with, as chips
    property var usual: null           // {chips: {how a turn ended: [your replies then]}, ranked: [all of them]}
    property real usualAt: 0
    property var hiddenReplies: ({})   // reply key -> true: Don't suggest this, gone at once
    property var chipsSeen: []         // the chips this turn showed (backing off: ReplyChips.qml says)
    property int chipsIgnored: 0
    property bool chipsResting: false
    property real sentAt: 0
    Timer {
        id: chipsRest   // (backing off: none for half an hour)
        interval: 30 * 60000
        onTriggered: pane.chipsResting = false
    }

    // (asked a moment after the box takes the focus or a turn has ended, not as the window
    // opens: a process started then delays its first frame)
    Timer {
        id: usualSoon
        interval: 600
        onTriggered: pane.loadUsual()
    }
    function loadUsual() {
        if (!suggestOn || !chatId || Date.now() - usualAt < 60000)
            return
        usualAt = Date.now()
        run("replies", fresh ? "--replies - --cwd " + root.shellQuote(fresh.cwd) + paneArgs()
                             : "--replies " + root.shellQuote(chatId) + paneArgs())
    }
    // A reply as replies are compared (pane.py reply_key): case, outer quotes, final punctuation, extra spaces left out
    function replyKey(text) {
        return String(text || "").normalize("NFKC").toLowerCase().trim().replace(/^["'`“”‘’]+|["'`“”‘’]+$/g, "")
            .replace(/[\s.!?,;:…。！？]+$/, "").split(/\s+/).filter(w => w !== "").join(" ")
    }
    // Shown (the list itself: ReplyChips.qml): Suggest replies on, a chat that's going (not a
    // new one), its turn over (the transcript says so, else the chat isn't at work and nothing went
    // to it a moment ago), not asking for a permission, the box empty, nothing of yours on its way
    // or queued, not backed off; and Claude asked something, or you have a usual reply for that
    readonly property bool chipsPending: pendingSent.some(p => p.chat === chatId && p.host === (host || "")) || answersOut.some(a => a.chat === chatId)
                                         || queued !== null || lastItems.some(i => !!i.queued)
    readonly property bool chipsOn: {
        if (!suggestOn || !conversationTab || !!fresh || starting || turnEnded === "" || chipsResting || chipsPending
                || chatState === "waiting" || replyBox.text.trim() !== "")
            return false
        if (!turnOver && (chatState === "working" || Date.now() - sentAt <= 15000))
            return false
        return (!!asks && !!asks.choices && asks.choices.length > 0)
               || ((usual && usual.chips && usual.chips[turnEnded]) || []).some(t => !hiddenReplies[replyKey(t)])
    }
    onChipsOnChanged: if (loaded && nearEnd()) keepEnd()   // (the row above the box comes or goes: the end stays in view)
    // A chip (ReplyChips.qml): sent as if typed (Enter); edit: in the box first (Shift+click, Edit
    // before sending). Here, not there: the row goes as the box takes its words
    function takeChip(chip, edit) {
        if (!chip)
            return
        replyBox.text = chip.send
        if (!edit) {
            send("enter", false)
            return
        }
        replyBox.cursorPosition = replyBox.length
        replyBox.forceActiveFocus()
    }
    function hideChip(chip) {
        if (!chip)
            return
        const hidden = Object.assign({}, hiddenReplies)
        hidden[replyKey(chip.send)] = true
        hiddenReplies = hidden
        run("hide", "--hide-reply " + root.shellQuote(chip.send) + (host ? " --host " + root.shellQuote(host) : ""))
        replyBox.forceActiveFocus()
    }
    // (what you type, completed in grey from your usual replies: ReplyGhost.qml, while one can be)
    readonly property bool ghostOn: suggestOn && usual !== null && conversationTab && replyBox.activeFocus && suggestions.length === 0
                                    && replyBox.text !== "" && replyBox.cursorPosition === replyBox.length && replyBox.preeditText === ""
                                    && replyBox.text !== ghostOff

    // asked: the run it answers ({kind, chat, host, target}: run())
    function handle(kind, result, asked) {
        if (kind === "font") {
            if (result.ok && typeof result.family === "string" && result.family !== Plasmoid.configuration.paneTerminalFont)
                Plasmoid.configuration.paneTerminalFont = result.family
            return
        }
        if (kind === "copy") {   // (all of a reply shown cut: on the clipboard now, Copied)
            if (result.ok && typeof result.text === "string") {
                copyText(result.text, true)
                copied(asked.key, asked.hover)
            } else {
                info = i18n("Couldn't copy all of it: %1", result.message || i18n("it couldn't be read"))
                infoBad = true
                infoTimer.restart()
            }
            return
        }
        if (kind === "replies" || kind === "hide") {   // (your usual replies, for this chat only; one hidden: nothing to say)
            if (kind === "replies" && result.ok && asked.chat === chatId && suggestOn)
                usual = { chips: result.chips || {}, ranked: result.ranked || [] }
            return
        }
        // (a model or effort picked for this chat alone: set, or why not)
        if (kind === "options") {
            pickBusy = false
            info = result.message || (result.ok ? "" : i18n("That didn't work"))
            infoBad = !result.ok
            infoTimer.restart()
            if (result.ok && asked.chat === chatId && pickerOf(replyBox.text))
                replyBox.text = ""   // (the /model you picked goes)
            if (result.ok)
                root.refresh()
            return
        }
        // (a command opened in its chat's terminal: there, whichever chat this window shows now)
        if (kind === "typein") {
            commandBusy = false
            info = result.message || (result.ok ? "" : i18n("That didn't work"))
            infoBad = !result.ok
            infoTimer.restart()
            if (!result.ok)
                return
            if (asked.chat === chatId && replyBox.text.trim() === asked.text)
                replyBox.text = ""   // (it's there now: out of the box)
            if (result.how === "vscode" && result.link) {
                root.openVscodeLink(asked.target ? asked.target.sessionId || asked.chat : asked.chat, result.link, asked.host)
                return
            }
            if (result.how === "copy" && !result.copied && result.text)
                copyText(result.text, true)   // (an SSH host's chat: this computer's clipboard)
            root.openRow(asked.target, asked.host, true)
            return
        }
        if (kind === "send" || kind === "later")
            sentDone(asked, result)   // (shown as sent, or back in its box; the next one to that chat goes)
        if ((kind === "deny" || kind === "answer") && asked.answerId)
            answerGone(asked.answerId, !!result.ok)   // (your answer, shown at once: it went, or it's taken out)
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
                offers = { commands: result.commands || [], files: result.files || [], history: result.history || [],
                           typed: result.typed || {} }
            Qt.callLater(suggest)
            if (sendAfterOffers) {   // (a / command sent before they were in: now, as what it is)
                const how = sendAfterOffers
                sendAfterOffers = ""
                offersFailed = !result.ok
                send(how.split(" ")[0], how.split(" ")[1] === "later")
                offersFailed = false
            }
            return
        }
        if (kind === "conversation") {
            loading = false
            if (loadAgain) {
                loadAgain = false
                Qt.callLater(load)
            }
            if (!result.ok) {
                // (a chat just started has no transcript for a moment: your message shows meanwhile)
                if (result.missing && chat.startedAt && Date.now() - chat.startedAt < 60000) {
                    loadError = ""
                    return
                }
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
                commitMessage = result.message || ""
            return
        }
        if (kind === "interrupt") {
            // (stopped: the conversation says Interrupted, and its working line goes)
            if (!result.ok) {
                stopping = false
                info = i18n("Couldn't stop it: %1", result.message || i18n("That didn't work"))
                infoBad = true
                infoTimer.restart()
            }
            root.refresh()
            if (host)
                root.pollHost(host)
            stamp = ""
            load()
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

    // Your answers on their way, to what the chat asks (from here, its row or a notification):
    // shown at once as yours till the conversation has them (withAnswers; VS Code shared/pane.ts
    // PendingAnswer): [{id, chat, host, text, answered, at, for: the key of the call it answers
    // ("": not known), known: your answers' keys then, state: "sending"|"sent", sentAt}]
    property var answersOut: []
    property int answerCount: 0
    readonly property var answeringFor: {   // the calls an answer on its way is to: their question shows
        const out = {}
        for (const p of answersOut)
            if (p.for && p.chat === chatId && p.host === (host || ""))
                out[p.for] = true
        return out
    }
    // One question's answer as Claude's dialog sends it (pane.py answer_text): the option chosen
    // or what you typed; several, ", " between them (one with ", " or a quote in it quoted)
    function joinAnswer(values, multi) {
        const given = (values || []).map(v => String(v).trim()).filter(v => v !== "")
        if (!multi)
            return given.length ? given[0] : ""
        return given.map(v => v.indexOf(", ") >= 0 || v.indexOf('"') >= 0 ? JSON.stringify(v) : v).join(", ")
    }
    // What your answer to a prompt says, as the conversation will have it (pane.py your_answer):
    // the options you picked or what you typed, one line a question when there are several
    // ("Header: answer"); Approved the plan, or Keep planning and your note; a Deny's or a
    // Decline's note. "": nothing of yours to show (an Allow, a Deny or a Decline without a note)
    function answerText(ask, decision, note, answers) {
        const said = String(note || "").trim()
        if (ask.plan) {
            if (decision === "approve" || decision === "approve-edits")
                return i18n("Approved the plan")
            return decision === "keep" || decision === "deny" ? i18n("Keep planning") + (said ? "\n" + said : "") : ""
        }
        if (decision === "answer" && answers) {
            const given = (ask.questions || []).map(q => ({ q: q, text: joinAnswer(answers[q.question], q.multiSelect) }))
                                               .filter(a => a.text !== "")
            return given.map(a => (given.length > 1 ? (a.q.header || a.q.question) + ": " : "") + a.text).join("\n")
        }
        return decision === "deny" ? said : ""
    }
    // The call an answer is to: the one it asks about (its tool use), else its tool's newest call with no result yet
    function answerFor(list, ask) {
        if (ask.toolUse && list.some(it => String(it.key) === ask.toolUse))
            return ask.toolUse
        for (let i = list.length - 1; i >= 0; i--)
            if (list[i].kind === "tool" && list[i].status === "open" && list[i].name === ask.tool)
                return String(list[i].key)
        return ""
    }
    // Your answer to what this chat asks (ask: its permission as answered), shown at once: its id, 0 for none to show
    function addAnswer(ask, decision, note, answers) {
        const text = ask ? answerText(ask, decision, note, answers) : ""
        if (!text)
            return 0
        const id = ++answerCount
        answersOut = answersOut.concat([{ id: id, chat: chatId, host: host || "", text: text, at: Date.now(),
                                          answered: ask.plan ? "plan" : ask.questions && ask.questions.length ? "question" : "permission",
                                          for: answerFor(lastItems, ask), known: lastItems.filter(it => !!it.answered).map(it => String(it.key)),
                                          state: "sending", sentAt: 0 }])
        const following = loaded && nearEnd()
        showPending()
        if (following)
            keepEnd()
        return id
    }
    // It went (shown as yours till the conversation has it), or it didn't (taken out)
    function answerGone(id, ok) {
        if (!answersOut.some(p => p.id === id))
            return
        answersOut = ok ? answersOut.map(p => p.id === id ? Object.assign({}, p, { state: "sent", sentAt: Date.now() }) : p)
                        : answersOut.filter(p => p.id !== id)
        showPending()
    }
    // The conversation with your answers on their way after it: each till the conversation has its
    // call's answer (or its call a result, with nothing of yours to show), or, its call not known, an
    // answer of yours that wasn't there; or 30 s after it went (an answer never told: 2 min)
    function withAnswers(list, handoff) {
        const mine = answersOut.filter(p => p.chat === chatId && p.host === (host || ""))
        if (!mine.length)
            return list
        const now = Date.now()
        const done = {}
        for (const p of mine) {
            const found = p.for ? list.find(it => String(it.key) === p.for + "/answer" || (String(it.key) === p.for && it.status !== "open"))
                                : list.find(it => !!it.answered && p.known.indexOf(String(it.key)) < 0)
            if (found && found.answered && handoff)
                handoff[String(found.key)] = "answer-" + p.id
            if (found || (p.state === "sent" && now - p.sentAt > 30000) || now - p.at > staleMs)
                done[p.id] = true
        }
        if (Object.keys(done).length)
            answersOut = answersOut.filter(p => !done[p.id])
        return list.concat(answersOut.filter(p => p.chat === chatId && p.host === (host || ""))
                                     .map(p => ({ kind: "you", key: "answer-" + p.id, text: p.text, at: p.at, answered: p.answered,
                                                  status: p.state === "sending" ? "sending" : "" })))
    }
    // Is it a question or a plan to show as Claude's, in Chat and Steps: once you answered it (or as
    // your answer to it goes: answering)? (a: its asked, pane.py asked_of)
    function askedShows(a, answering) {
        if (!a || (!a.questions && a.plan === undefined))
            return false
        return a.state === "open" ? answering : a.state !== "failed" && a.state !== "denied"
    }

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

    // A new chat's task, sent as its first message the moment its window opens (main.qml
    // openNewChat); a plan's alone: Claude's words for it, as a task without any (pane.py --start)
    function startWith(text) {
        replyBox.text = text || (fresh && fresh.plan ? "Implement this plan." : "")
        send("auto", false)
    }

    function send(how, afterTurn, now) {   // (now: Ctrl+Enter, no 5 s wait while Claude works)
        const text = replyBox.text.trim()
        if (!text)
            return
        // A command: as its kind says on this chat (commandRun). One typed before the / list's
        // offers were read waits for them (else /model would go as a message, and save your default)
        if (/^\/\S/.test(text) && !offers && !offersFailed && !replyAnswers) {
            sendAfterOffers = (how || "auto") + (afterTurn ? " later" : "")
            offersAt = 0
            loadOffers()
            return
        }
        const ran = replyAnswers ? null : commandRun(text)
        if (ran && ran.run === "off") {
            info = ran.why
            infoBad = true
            infoTimer.restart()
            return
        }
        if (ran && ran.run === "page") {
            replyBox.text = ""
            root.openPermissions()
            return
        }
        if (ran && ran.run === "terminal") {
            openWithCommand(text)
            return
        }
        if (ran && ran.run === "picker") {   // (/model, /effort: for this chat alone; with no name, its list)
            const p = pickerOf(text)
            if (!p)
                return
            if (!p.value) {
                dismissed = ""
                replyBox.text = "/" + p.kind + " "
                replyBox.cursorPosition = replyBox.text.length
                return
            }
            setOptions(p.kind, p.value)
            return
        }
        // (it goes on the command line: one too long for it is refused here, as
        // VS Code does, and stays in the box)
        if (text.length > 100000 || utf8Length(text) > 120000) {
            info = i18n("That message is too long")
            infoBad = true
            infoTimer.restart()
            return
        }
        // (backing off, as Claude Code does with its own suggestions: chips showed this turn, and
        // you sent none of them, typed or clicked; 5 in a row, and none for half an hour)
        if (chipsSeen.length) {
            const key = replyKey(text)
            if (chipsSeen.some(c => replyKey(c.send) === key)) {
                chipsIgnored = 0
            } else if (++chipsIgnored >= 5) {
                chipsIgnored = 0
                chipsResting = true
                chipsRest.restart()
            }
            chipsSeen = []
        }
        sentAt = Date.now()
        loadUsual()
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
        const holds = shows && chatState === "working" && !(row && row.reason === "background shell") && !now
        const id = ++sentCount
        const asked = { kind: afterTurn ? "later" : "send", chat: chatId, host: host, target: row || chat,
                        sent: shows || afterTurn ? "" : replyBox.text, draft: draftKey, text: text, id: id, startedAt: 0,
                        how: how || "auto", fresh: fresh }
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
    // pane.py --send's arguments for your message (asked), to the chat shown; a new chat's first
    // one starts it (--start: in the background, on its account, in its folder, with the model,
    // effort and mode of its ⚙ line, the new-chat ones; with the permission hook for it alone)
    function sendArgs(asked) {
        const f = asked.fresh
        if (f)
            return "--start " + root.shellQuote(f.profile) + " --cwd " + root.shellQuote(f.cwd) + " --text " + root.shellQuote(asked.text)
                   + root.chatOptions + (f.plan ? " --plan " + root.shellQuote(f.plan.slug) + " --plan-profile " + root.shellQuote(f.plan.profileDir) : "")
                   + root.configDirArgs
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
        // A new chat's first message: it started, and the window goes on with it under its id
        // (follow()); or it didn't, and the ones written meanwhile are back in the box too
        if (asked.fresh && result.ok && result.chat && asked.chat === chatId) {
            chat = Object.assign({}, chat, { chatId: result.chat, sessionId: result.chat, fresh: null, from: asked.chat,
                                             profileDir: result.profileDir || chat.profileDir, startedAt: Date.now() })
            root.paneListChanged()
        } else if (asked.fresh && !result.ok) {
            const waiting = outbox.filter(m => m.asked.draft === asked.draft)
            outbox = outbox.filter(m => m.asked.draft !== asked.draft)
            pendingSent = pendingSent.filter(x => !waiting.some(m => m.asked.id === x.id))
            for (const m of waiting)
                giveBack(m.asked)
            if (asked.chat === chatId)
                showPending()
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
    function copyAcross(event) {   // (Ctrl+C in a message: with others selected too, all of it; Ctrl+A: every message)
        if (event.matches(StandardKey.Copy) && Object.keys(selOthers).length > 0) {
            copyText(selectionText())
            event.accepted = true
        } else if (event.matches(StandardKey.SelectAll)) {
            selectAllMessages()
            event.accepted = true
        }
    }
    function selectAllMessages() {   // (as on a web page: the whole conversation, each message's text)
        let first = -1
        const others = {}
        for (let i = 0; i < items.count; i++) {
            const b = boxAt(i)
            if (!b)
                continue
            b.selectAll()
            if (first < 0)
                first = i
            else
                others[keyAt(i)] = i
        }
        selFromAt = first
        selFrom = keyAt(first)
        selLast = selFrom
        selLastAt = first
        selOthers = others
    }

    // The right-click menu (EditMenu.qml: Copy, Copy message, Select all on the conversation; Undo,
    // Redo, Cut, Copy, Paste, Select all on the reply box): one for the window, made the first time
    function editMenuAt(where, p) {
        editMenu.active = true
        if (editMenu.item)
            editMenu.item.openAt(where, p)
    }
    function pasteInBox() {   // (as Ctrl+V: text, else the clipboard's picture)
        replyBox.forceActiveFocus()
        if (replyBox.canPaste)
            replyBox.paste()
        else
            root.pasteImage(pane.host, pane.pasteTarget)
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
    property string bigPicture: ""   // (Esc: doKey)

    // The conversation with your messages on their way after it: each till
    // the conversation has it (a prompt of yours that wasn't there when you
    // sent it, with its words; or, after a moment, any new one of this
    // computer's chat: Claude can have changed them, a picture's say), or
    // 30 s after it went (it went: the conversation just doesn't show it)
    function norm(s) {
        return String(s || "").replace(/\s+/g, " ").trim()
    }
    function withPending(list, handoff) {   // (handoff: {key: "pending-N"}, each one found as key)
        list = withAnswers(list, handoff)
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
            const bare = want[0] === "!" ? norm(want.slice(1)) : ""   // (a shell command waits in Claude's queue without its !)
            const found = list.find(it => {
                const key = String(it.key)
                if (it.kind !== "you" || it.answered || p.known[key] || claimed[key])
                    return false
                const said = norm(it.text)
                const cut = said.endsWith("…") ? said.slice(0, -1).trim() : ""
                return said === want || (bare !== "" && said === bare) || (cut !== "" && want.indexOf(cut) === 0)
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
                                                   pictures: pictureNames(p.text),
                                                   command: /^[\/!]\S/.test(p.text) ? (p.text[0] === "!" ? { shell: true } : {}) : null })))
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
        // (a command: where it runs, commandRun; one that can't run here says why first)
        const ran = replyAnswers ? null : commandNow
        if (ran && ran.run === "off")
            return ran.why
        if (ran && ran.run === "page")
            return i18n("Enter opens Talpy Den's Permissions tab: what Claude may do without asking, in every chat.")
        if (ran && ran.run === "picker") {
            const p = pickerOf(ran.name)
            const kind = p ? p.kind : "model"
            const exact = !!ran.arg && pickerItems(kind, "").some(s => s.insert === "/" + kind + " " + ran.arg.toLowerCase())
            const named = !ran.arg ? "" : exact || !pickerItems(kind, ran.arg).length ? pickLabel(kind, ran.arg) : ""
            return (named ? i18n("Enter: %1 for this chat alone", named)
                    : ran.arg ? (kind === "effort" ? i18n("Enter: the effort level picked in the list, for this chat alone")
                                                   : i18n("Enter: the model picked in the list, for this chat alone"))
                    : kind === "effort" ? i18n("Enter lists the effort levels: for this chat alone") : i18n("Enter lists the models: for this chat alone"))
                + " " + i18n("(in its terminal, Claude's %1 would also make it your default for every new chat).", ran.name) + where
        }
        if (ran && ran.run === "terminal" && ran.name === "!")
            return i18n("Its terminal takes no text from outside: Enter copies the command and opens its terminal, to paste it there.") + where
        if (ran && ran.run === "terminal")
            return (route === "tmux" ? i18n("%1 %2: Enter types it into its tmux pane, for you to press Enter there.", ran.name, ran.why)
                                     : i18n("%1 %2: Enter opens the chat's terminal, with the command on the clipboard to paste there.", ran.name, ran.why)) + where
        if (ran && ran.name === "!")
            return i18n("A shell command, as Claude's ! mode: it runs in the chat's folder, then Claude answers what it printed.") + where
        if (starting)
            return i18n("The chat starts in the background with your message.")
        if (fresh)
            return i18n("Your first message starts the chat in the background, on %1 in %2: you answer what it asks here.", fresh.account, fresh.short)
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
            return i18n("Goes into the background chat as it runs, as if you typed it there.") + where
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
        const shown = addAnswer(p, decision, note, answers)   // (yours at once, till the conversation has it)
        if (p.answer === "hook")
            run(decision === "deny" ? "deny" : "answer", "--answer " + root.shellQuote(p.request) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (answers ? " --answers " + root.shellQuote(JSON.stringify(answers)) : "")
                + (host ? " --host " + root.shellQuote(host) : "") + root.configDirArgs, sent, shown)
        else if (p.answer === "keys")
            run(decision === "deny" ? "deny" : "answer", "--keys " + root.shellQuote(sessionId) + " --decision " + decision
                + (note ? " --note " + root.shellQuote(note) : "")
                + (p.toolUse ? " --expect " + root.shellQuote(p.toolUse) : "") + paneArgs(), sent, shown)
    }

    // ---------------------------------------------------------------- review

    property var review: null
    property string reviewFor: ""   // the chat that review is of: Undo and Commit act on that one only
    readonly property bool reviewIsThis: review !== null && reviewFor !== "" && reviewFor === chatId
    property bool reviewLoading: false
    property string reviewError: ""
    property var openFiles: ({})
    property string commitMessage: ""   // (Commit these files…'s message: ReviewPage.qml)
    property bool commitOpen: false
    property bool commitEdited: false
    property string undoAsk: ""   // "*": all, else a file's path, asked to confirm

    function loadReview() {
        if (!chatId || fresh)
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
        if (tab === "review")
            reviewPage.active = true   // (its page: made now, then kept)
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
                countUnseen()
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
        onRunningChanged: if (!running) interval = 800
    }

    // The message at the top of the list (not a tool call: it's on both
    // tabs; any row this tab shows: here): [its key, how far below the list's top it is]
    function topMessage(here) {
        for (let i = Math.max(0, list.indexAt(list.width / 2, list.contentY)); i < items.count; i++) {
            const entry = list.itemAtIndex(i)
            if (entry && (here ? entry.shows : entry.kind !== "tool") && entry.y + entry.height > list.contentY)
                return [entry.key, entry.y - list.contentY, i]
        }
        return null
    }
    function showTop() {
        const at = chatTop && chatTop[2] !== undefined && chatTop[2] < items.count && items.get(chatTop[2]).key === chatTop[0] ? list.itemAtIndex(chatTop[2]) : null
        if (at) {
            list.contentY = Math.max(list.originY, Math.min(at.y - chatTop[1], list.originY + list.contentHeight - list.height))
            return
        }
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
        // Talpy Chat's keys, wherever the focus is in it (keyAction)
        Keys.onShortcutOverride: event => event.accepted = pane.keyAction(event) !== ""
        Keys.onPressed: event => pane.takeKey(event)
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
                    color: pane.row ? root.stateColor(pane.chatState) : pane.starting ? root.stateColor("working") : pane.mutedColor
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
                        // (while the working line says the turn's own time, the header doesn't say a second one)
                        text: pane.row ? root.stateText(pane.chatState === "working" && pane.turnNow !== null
                                                        ? Object.assign({}, pane.row, { since: 0 }) : pane.row)
                              : pane.starting ? i18nc("a chat's state", "starting")
                              : pane.fresh ? i18nc("a chat's state: not started yet", "new") : i18n("not running")
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
                    // (a background chat's: a terminal on it, claude attach, also where its window is this one)
                    readonly property bool attaches: pane.where === "background" && !!pane.row && !!pane.row.pid
                    visible: !pane.fresh && !(pane.starting && !pane.row)
                    icon.name: attaches ? Icons.plasma.terminal : Icons.plasma.openWindow
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: attaches ? i18n("Open in a terminal") : i18n("Open its window")
                    onClicked: root.openRow(pane.row || pane.chat, pane.host, true)

                    TipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("%1 (Ctrl+Shift+O)", parent.text)
                        subText: parent.attaches ? i18n("The background chat in a terminal too (claude attach): what it shows there, and its own prompts. It goes on running; nothing is lost.")
                                 : i18n("The terminal or VS Code tab the chat runs in; a chat that isn't open reopens in a terminal or in VS Code, as the Open in switch of Recent chats says.")
                    }
                }
            }
            // where it runs, and its folder
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Math.round(fm.height * 0.5) + Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Tag {
                    text: pane.where === "new" ? i18nc("where a chat runs: not started yet", "New")
                          : pane.where === "background" ? i18nc("where a chat runs", "Background")
                          : pane.where === "closed" ? i18nc("where a chat runs", "Not open")
                          : pane.where === "claude" ? i18nc("where a chat runs: the Claude Code extension's panel", "Claude Code panel")
                          : pane.where === "tmux" ? "Tmux"
                          : pane.where === "vscode" ? i18nc("where a chat runs", "VS Code terminal")
                          : i18nc("where a chat runs", "Terminal")
                    tooltip: pane.where === "new" ? i18n("Not started yet: your first message starts it in the background, on %1.", pane.fresh ? pane.fresh.account : "")
                             : pane.where === "background" ? i18n("A background chat: Claude's background service runs it, with no terminal of its own. Open in a terminal shows it in one too (claude attach).")
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
                // how full its context is: what's left till Claude compacts the chat on its own, in the warning
                // colour once Claude Code says it's close (VS Code shared/pane.ts contextText, contextHint)
                Tag {
                    readonly property var ctx: pane.fresh ? null : pane.contextLeft
                    visible: ctx !== null
                    text: ctx ? i18n("Context %1% left", ctx.left) : ""
                    caution: !!ctx && ctx.near
                    tooltip: !ctx ? "" : i18n("%1 of its %2 tokens of context are used. Claude compacts the chat on its own at about %3: it sums up the conversation so far and goes on from that.",
                                              root.formatTokens(ctx.used), root.formatTokens(ctx.window), root.formatTokens(ctx.compactAt))
                                         + (ctx.near ? " " + i18n("That's soon: run /compact now to say what it keeps, if you'd rather choose.") : "")
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: (pane.host ? root.hostLabel(pane.host) + ":" : "") + (pane.row ? pane.row.cwdShort || pane.row.cwd || ""
                                                                                  : pane.fresh ? pane.fresh.short : pane.chat.cwd || "")
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
                    model: pane.fresh ? ["chat", "steps"] : ["chat", "steps", "review"]
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
                        PlasmaComponents3.ToolTip.text: modelData === "chat" ? i18n("Your messages and Claude's replies (Ctrl+1)")
                                                        : modelData === "steps" ? i18n("Claude's steps too: each tool call (Ctrl+2)") : i18n("The files it changed (Ctrl+3)")
                        PlasmaComponents3.ToolTip.visible: containsMouse
                        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay

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

                    // A line between days, before the first item of each later day the tab shows
                    // (DayLine.qml: read and made only for a chat with more than one day)
                    section.property: "day"
                    section.delegate: Loader {
                        required property string section
                        width: list.width
                        active: section !== String(pane.firstDays[pane.listTab]) && pane.daysShown[pane.listTab][section] === true
                        source: active ? "DayLine.qml" : ""
                        onLoaded: item.day = Qt.binding(() => Number(section))
                    }

                    // The message under the pointer (yours, or Claude's reply): its time and Copy over
                    // its top right corner (MessageTools.qml: one for the list, made the first time
                    // a message is hovered, moved to the one hovered; nothing more per message)
                    HoverHandler {
                        id: listHover
                    }
                    property Item hoverRow: {   // (a binding; a render sets one to draw its tools)
                        if (!listHover.hovered)
                            return null
                        const p = listHover.point.position
                        void list.contentY   // (scrolled under the pointer: the one there now)
                        const at = listHover.parent.mapToItem(list.contentItem, p.x, p.y)
                        const r = list.itemAt(at.x, at.y)
                        return r && r.listed && r.shows && !r.card && (r.kind === "you" || r.kind === "claude") ? r : null
                    }
                    onHoverRowChanged: if (hoverRow !== null) messageTools.active = true
                    Loader {
                        id: messageTools
                        active: false
                        source: active ? "MessageTools.qml" : ""
                    }
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

                            // (room for the find bar above the first row while it's open, so Show earlier
                            // isn't under it: the list keeps what you read where it is)
                            Item {
                                visible: pane.findOn
                                Layout.preferredHeight: Kirigami.Units.gridUnit * 1.6
                            }
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
                            // (and a new chat's, before your first message: what it is)
                            PlasmaComponents3.Label {
                                readonly property bool unsent: !!pane.fresh && items.count === 0
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                Layout.topMargin: unsent ? Kirigami.Units.gridUnit : 0
                                visible: !pane.loaded || pane.loadError !== "" || unsent
                                horizontalAlignment: Text.AlignHCenter
                                text: unsent ? (pane.fresh.plan ? i18n("A new chat on %1 in %2, to carry out “%3”.", pane.fresh.account, pane.fresh.short, pane.fresh.plan.title)
                                                                : i18n("A new chat on %1 in %2.", pane.fresh.account, pane.fresh.short))
                                               + "\n" + i18n("Your first message starts it in the background. Here you reply, answer what Claude asks and see what it changed; open it in a terminal any time.")
                                      : pane.loadError || i18n("Reading the chat…")
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
                        implicitHeight: pane.chatState === "working" || pane.starting ? workingLine.implicitHeight + Kirigami.Units.gridUnit : 0
                        visible: pane.chatState === "working" || pane.starting

                        RowLayout {
                            id: workingLine
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            width: list.width   // (the list's, as its rows': the footer can be wider, under the scroll bar)
                            spacing: 0

                            TalpyIcon {
                                Layout.preferredWidth: pane.gutter
                                Layout.preferredHeight: Math.round(fm.height * 1.2)
                                mode: "thinking"
                                color: root.stateColor("working")
                                moving: workingLine.visible && pane.shown && pane.conversationTab
                            }
                            PlasmaComponents3.Label {
                                id: workingText
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                // (what it's doing, unless that's the tool call just above)
                                readonly property bool toolAbove: pane.listTab === "steps" && items.count > 0 && items.get(items.count - 1).status === "open"
                                readonly property string activity: pane.row ? root.doingText(pane.row, pane.host).replace(/[….\s]+$/, "") : ""
                                text: pane.starting && pane.chatState !== "working" ? i18n("Starting…")
                                      : (activity && !toolAbove ? activity : i18n("Working")) + "…"
                                elide: Text.ElideRight
                                color: root.stateColor("working")
                                font.family: pane.chatFamily
                                font.pointSize: pane.pt
                                // (no Stop here: where it can be stopped, on hover; made only then)
                                Loader {
                                    anchors.fill: parent
                                    active: pane.stopElsewhere !== ""
                                    sourceComponent: TipArea {
                                        mainText: workingText.text
                                        subText: pane.stopElsewhere
                                    }
                                }
                            }
                            // Claude's turn so far, at its end before Stop ("8m 12s · 58 steps": WorkingMeta.qml, read
                            // and made only while a chat works and its turn is known; its clock ticks only then)
                            Loader {
                                active: pane.chatState === "working" && pane.turnNow !== null
                                Layout.leftMargin: active ? Kirigami.Units.smallSpacing : 0
                                source: active ? "WorkingMeta.qml" : ""
                            }
                            // Stop, at its end (StopButton.qml: read and made only for a chat it can stop,
                            // while it works; as tall with it as without, so nothing moves)
                            Loader {
                                active: pane.canStop
                                Layout.preferredHeight: pane.queueButtonHeight
                                Layout.preferredWidth: item ? item.implicitWidth : 0
                                Layout.leftMargin: active ? Kirigami.Units.smallSpacing : 0
                                source: active ? "StopButton.qml" : ""
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
                        required property string asked      // (a question or a plan Claude asked, as JSON: pane.py asked_of)
                        required property string answered   // (yours: your answer to the call before it, pane.py your_answer)
                        required property string command    // (yours: a command you ran, as JSON: pane.py commands.py)
                        required property string fold       // (a long one: where it folds, as JSON: withFold; "" for the rest)
                        property Item textBox: null   // (yours, Claude's reply: its text, selectAcross)
                        property int late: pane.lateDefault   // (Ctrl+O: its turn came, FoldAll.qml)
                        readonly property bool unfolded: pane.openTools[key] === true   // (a step's details: a click, a search's step)
                        readonly property bool allTurn: pane.allOpen && late === pane.allGen
                        readonly property var foldData: fold !== "" ? JSON.parse(fold) : null
                        readonly property bool whole: !foldData || !foldData.cut || (pane.openTools[key] !== undefined ? pane.openTools[key] : allTurn || foldData.open)
                        readonly property bool outWhole: !foldData || !foldData.outCut
                                                         || (pane.openTools[key + "/out"] !== undefined ? pane.openTools[key + "/out"] : allTurn || foldData.open)
                        readonly property var askedData: asked !== "" ? JSON.parse(asked) : null
                        readonly property var commandData: command !== "" ? JSON.parse(command) : null
                        // (a question or a plan you answered: as Claude's, in Chat and Steps)
                        readonly property bool card: kind === "tool" && pane.askedShows(askedData, pane.answeringFor[key] === true)
                        // more room before your prompt (a new turn) than between steps; your answer: right under what it answers
                        readonly property real gap: index === 0 ? 0
                            : kind === "you" && answered === "" ? Kirigami.Units.gridUnit * 1.6
                            : kind === "tool" && prev === "tool" ? Kirigami.Units.smallSpacing * 1.5
                            : Kirigami.Units.gridUnit * 0.8
                        // (the Chat tab: a call you denied with a note too, its note under it)
                        readonly property bool shows: (kind !== "tool" || pane.listTab === "steps" || card
                                                       || (askedData !== null && askedData.state === "denied")) && listed
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
                            sourceComponent: entry.card ? askedItem : entry.kind === "you" ? youItem : entry.kind === "claude" ? claudeItem
                                           : entry.kind === "tool" ? toolItem : noteItem
                        }

                        // Yours: a band in your accent color, after a ›. Queued (sent
                        // while Claude works), grey, as Claude's terminal shows it, with
                        // what becomes of it: held a moment (Edit, Send now, Cancel; ↑ in the
                        // box), then in Claude's queue till it takes it in at its next step
                        // A command you ran (/compact, !ls): in the code font ($ before a shell
                        // command, as Claude's terminal's ! mode), what it printed under it
                        // (CommandOutput.qml: read and made only for a command that printed something)
                        Component {
                            id: youItem

                            ColumnLayout {
                            spacing: 0

                            Rectangle {
                                id: youBand
                                Layout.fillWidth: true
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
                                        text: entry.commandData && entry.commandData.shell ? "$" : "›"
                                        color: youBand.mark
                                        font.pointSize: pane.pt
                                        font.weight: Font.Bold
                                    }
                                    TextEdit {
                                        id: youText
                                        objectName: "findText"
                                        Component.onCompleted: entry.textBox = youText
                                        Layout.fillWidth: true
                                        text: !entry.whole ? entry.foldData.cut
                                              : entry.commandData && entry.commandData.shell ? entry.text.replace(/^!\s*/, "") : pane.shownText(entry.text)
                                        textFormat: TextEdit.PlainText
                                        readOnly: true
                                        selectByMouse: true
                                        persistentSelection: true   // (selectAcross clears it)
                                        Keys.onPressed: event => pane.copyAcross(event)
                                        wrapMode: TextEdit.Wrap
                                        color: Kirigami.Theme.textColor
                                        selectionColor: Kirigami.Theme.focusColor
                                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        font.family: entry.commandData ? pane.monoFamily : pane.chatFamily
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
                                // (a long one: Show more · N more lines, FoldMore.qml, made only for one)
                                Loader {
                                    active: !!entry.foldData && entry.foldData.cut !== ""
                                    visible: active
                                    Layout.leftMargin: pane.gutter
                                    source: active ? "FoldMore.qml" : ""
                                }
                                // Its pictures, small: a click shows one big (BigPicture.qml); made only for one with pictures
                                Loader {
                                    active: entry.pictures !== ""
                                    visible: active
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    sourceComponent: PictureStrip {
                                        pictures: entry.pictures ? entry.pictures.split("\n") : []
                                        here: pane.host ? (entry.here ? entry.here.split("\n") : []) : null
                                        host: pane.host
                                        removable: false
                                        opensHere: true
                                        thumbHeight: Kirigami.Units.gridUnit * 4
                                        onOpenRequested: path => pane.bigPicture = path
                                    }
                                }
                                // Queued: what becomes of it (QueueLine.qml: made only for one that waits)
                                Loader {
                                    active: youBand.waits
                                    visible: active
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    source: active ? "QueueLine.qml" : ""
                                }
                                }
                            }
                            Loader {
                                active: !!entry.commandData && !!entry.commandData.output
                                visible: active
                                Layout.fillWidth: true
                                Layout.topMargin: Kirigami.Units.smallSpacing
                                source: active ? "CommandOutput.qml" : ""
                            }
                            }
                        }

                        // Claude's reply: ● and its Markdown, rendered
                        Component {
                            id: claudeItem

                            RowLayout {
                                spacing: 0

                                Dot {
                                    Layout.alignment: Qt.AlignTop
                                    color: pane.claudeColor
                                    gutter: pane.gutter
                                    lineHeight: fm.height
                                }
                                ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                TextEdit {
                                    id: replyText
                                    objectName: "findText"
                                    // a code block's Copy: the one the pointer is on, and the one
                                    // just clicked, which reads Copied a moment (their index)
                                    property int copyHovered: -1
                                    property int copied: -1
                                    Component.onCompleted: entry.textBox = replyText
                                    Layout.fillWidth: true
                                    readonly property string html: Md.toHtml(entry.whole ? entry.text : entry.foldData.cut, pane.mdStyle, copied)
                                    text: html
                                    textFormat: TextEdit.RichText
                                    readOnly: true
                                    persistentSelection: true   // (selectAcross clears it)
                                    Keys.onPressed: event => pane.copyAcross(event)
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: Kirigami.Theme.textColor
                                    // (a selection change draws a text with tables whole: WholeRedraw.qml,
                                    // else its code blocks' text was drawn twice and looked bold)
                                    selectionColor: replyRedraw.color
                                    onSelectionStartChanged: replyRedraw.again()
                                    onSelectionEndChanged: replyRedraw.again()
                                    WholeRedraw {
                                        id: replyRedraw
                                        base: Kirigami.Theme.focusColor
                                        on: replyText.html.indexOf("<table") >= 0
                                    }
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
                                // (a long one: Show more · N more lines, FoldMore.qml, made only for one)
                                Loader {
                                    active: !!entry.foldData && entry.foldData.cut !== ""
                                    visible: active
                                    source: active ? "FoldMore.qml" : ""
                                }
                                }
                            }
                        }

                        // What Claude asked, once you answered it, as Claude's (AskedCard.qml: made
                        // the first time a card shows, so a window opens as quickly as before)
                        Component {
                            id: askedItem

                            Loader {
                                Component.onCompleted: setSource("AskedCard.qml", { pane: pane, key: entry.key, asked: entry.askedData })
                                onLoaded: item.asked = Qt.binding(() => entry.askedData)
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
                                // (codehtml.mjs; an edit's change is above, its error here): ToolDetail.qml,
                                // made as it's opened, only on a tab that shows the step
                                Loader {
                                    active: entry.unfolded && entry.shows && (entry.input !== "" || entry.output !== "")
                                            && (entry.diff === "" || entry.status === "error")
                                    visible: active
                                    Layout.fillWidth: true
                                    Layout.leftMargin: pane.gutter
                                    source: active ? "ToolDetail.qml" : ""
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
                // (a right-click: Copy, Copy message, Select all, EditMenu.qml)
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: (point, button) => pane.editMenuAt("list", point.position)
                }
            }
            // Search (Ctrl+F): FindBar.qml over the list's top right, clear of its scroll bar (nothing
            // moves), read and made only while it's open
            Loader {
                id: findBar
                parent: scroll
                z: 12
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.topMargin: Kirigami.Units.smallSpacing * 0.5
                anchors.rightMargin: Kirigami.Units.gridUnit
                active: pane.findOn && pane.conversationTab
                source: active ? "FindBar.qml" : ""
            }
            // "3 new ↓" at the list's bottom while you're scrolled up and something came in below (NewBelow.qml:
            // made only then); over the list, so it moves nothing; a click goes to the end
            Loader {
                parent: scroll
                z: 11
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Kirigami.Units.largeSpacing
                active: pane.unseen > 0 && pane.conversationTab
                source: active ? "NewBelow.qml" : ""
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
                        keyed: true   // (Alt+Y / Alt+A / Alt+N: pressKey, from the keys)
                        onAnswered: (decision, note, answers) => pane.answer(decision, note, answers)
                        // (a background chat started without Talpy Den's hook: claude attach on it)
                        attachable: !pane.host && !!pane.row && pane.row.kind === "bg" && !!pane.row.pid
                        onInTerminal: root.openRow(pane.row, pane.host, true)
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
                // What it offers for what you're typing (/ commands, @ files): OfferList.qml, read and
                // made only while there's something to offer
                Loader {
                    active: pane.suggestions.length > 0 && replyBox.activeFocus
                    visible: active
                    Layout.fillWidth: true
                    Layout.leftMargin: pane.gutter
                    source: active ? "OfferList.qml" : ""
                }
                // A new chat's ⚙ line: the model, effort and permission mode it starts with
                // (NewChatOptions.qml: made, and read, only for a new chat)
                Loader {
                    active: pane.fresh !== null && !pane.starting
                    visible: active
                    Layout.fillWidth: true
                    source: active ? "NewChatOptions.qml" : ""
                }
                // Suggested replies (ReplyChips.qml: made, and read, only while there are chips)
                Loader {
                    id: chipsRow
                    active: pane.chipsOn
                    visible: active
                    Layout.fillWidth: true
                    Layout.leftMargin: pane.gutter
                    source: active ? "ReplyChips.qml" : ""
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
                                             : pane.fresh && !pane.starting ? i18n("What should Claude do? (Enter starts the chat, Shift+Enter: new line; Ctrl+V or drop: a picture or a file too)")
                                             : i18n("Reply to Claude… (Enter sends, Shift+Enter: new line; Ctrl+V or drop: a picture or a file too; ?: the keys)")
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
                            onActiveFocusChanged: {
                                if (activeFocus) {
                                    pane.loadOffers()
                                    if (pane.suggestOn && pane.usual === null)
                                        usualSoon.restart()
                                }
                            }
                            Keys.onShortcutOverride: event => {
                                if (pane.keyAction(event) !== "")
                                    event.accepted = true
                            }
                            Keys.onPressed: event => {
                                // Talpy Chat's keys first (Alt+1…4 a chip, Ctrl+Enter, Esc, ? in an empty box…: keyAction)
                                if (pane.takeKey(event))
                                    return
                                // Tab or → at the end: the grey rest of your usual reply
                                if (ghostLine.item && ghostLine.item.rest !== "" && (event.key === Qt.Key_Tab || event.key === Qt.Key_Right)
                                        && event.modifiers === Qt.NoModifier) {
                                    insert(length, ghostLine.item.rest)
                                    cursorPosition = length
                                    event.accepted = true
                                    return
                                }
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
                                if ((event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter) || (event.modifiers & (Qt.ControlModifier | Qt.AltModifier)))
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

                            // (a right-click: Undo, Redo, Cut, Copy, Paste, Select all, EditMenu.qml)
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: (point, button) => pane.editMenuAt("box", null)
                            }

                            // What you type, completed in grey from your usual replies, where the
                            // cursor is at its end (made only while there's some)
                            Loader {
                                id: ghostLine
                                active: pane.ghostOn
                                readonly property rect at: active && replyBox.length >= 0 ? replyBox.positionToRectangle(replyBox.length) : Qt.rect(0, 0, 0, 0)
                                x: at.x
                                y: at.y
                                width: Math.max(0, replyBox.width - replyBox.rightPadding - at.x)
                                source: active ? "ReplyGhost.qml" : ""
                            }
                        }
                    }
                }
                // The pictures your reply names, small (× takes one out): made only for a reply that names one
                Loader {
                    active: replyBox.text.indexOf("[Image: ") >= 0
                    visible: active
                    Layout.fillWidth: true
                    Layout.leftMargin: pane.gutter
                    sourceComponent: PictureStrip {
                        pictures: named(replyBox.text)
                        host: pane.host
                        removeText: i18n("Take it out of your reply")
                        onRemoveRequested: path => replyBox.text = without(replyBox.text, path)
                    }
                }
                // Copy a picture to an SSH host, set dictation up, download a speech model: asked first
                // (ReplyAsks.qml, read and made only while one is asked)
                Loader {
                    active: pane.offerSetup || pane.offerModel
                            || (!!pane.host && ((!!root.pictureOffer && root.pictureOffer.host === pane.host && root.pictureOffer.target === pane.pasteTarget)
                                                || (root.pictureCopyingTo === pane.host && root.pictureCopyTarget === pane.pasteTarget)))
                    visible: active
                    Layout.fillWidth: true
                    source: active ? "ReplyAsks.qml" : ""
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
                                                   : i18n("Pick files for your reply: a picture goes in as one, another file is named for Claude to read. You can drop them on this window too.")
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
                                subText: i18n("Pick a region of the screen: its picture goes in your reply. Files and pictures can be dropped on this window too.")
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
                            enabled: replyBox.text.trim() !== "" && (!pane.commandNow || pane.commandNow.run === "here")
                            icon.name: Icons.plasma.later
                            text: i18n("Send when this turn ends")
                            onClicked: pane.send(pane.route === "terminal" || pane.askHow ? "background" : "auto", true)

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Send when this turn ends (Alt+Enter)")
                                subText: i18n("Talpy Den keeps it and sends it once Claude's turn is over (also with the popup closed).")
                            }
                        }
                        PlasmaComponents3.Button {
                            // (a terminal that takes no text, known or just found out: not while
                            // Claude works there, it would quit mid-turn; Send when this turn ends)
                            // (a command for Claude's own panel: Open in a terminal; one that can't run here: greyed, the line above says why)
                            readonly property string commandRun: pane.replyAnswers || !pane.commandNow ? "" : pane.commandNow.run
                            enabled: replyBox.text.trim() !== "" && commandRun !== "off"
                                     && !((pane.route === "terminal" || pane.askHow) && pane.busy && commandRun !== "terminal" && commandRun !== "page")
                                     && !pane.replyWaits && !(pane.replyAnswers && pane.answering > 0)
                            icon.name: commandRun === "terminal" ? Icons.plasma.terminal : commandRun === "page" ? Icons.plasma.permissions
                                       : pane.replyDenies ? Icons.plasma.deny : pane.replyKeepsPlanning ? Icons.plasma.edit : Icons.plasma.send
                            icon.color: pane.replyDenies && commandRun === "" ? Icons.color("deny", Kirigami.Theme) : "transparent"
                            text: commandRun === "terminal" ? i18n("Open in a terminal")
                                  : commandRun === "page" ? i18n("Open Permissions")
                                  : commandRun === "picker" ? (pane.commandNow.arg ? i18n("Set for this chat") : i18n("List them"))
                                  : pane.replyAnswers === "deny" ? i18n("Deny with this note")
                                  : pane.replyAnswers === "plan" ? i18n("Keep planning with this note")
                                  : pane.replyAnswers === "question" ? i18n("Send as your answer")
                                  : pane.replyAnswers === "decline" ? i18n("Decline with this note")
                                  : pane.route === "terminal" || pane.askHow ? i18n("Send, go on in the background")
                                  : pane.fresh && !pane.starting ? i18nc("a new chat's first message: start the chat with it", "Start") : i18n("Send")
                            onClicked: pane.send(commandRun !== "" && commandRun !== "here" ? "auto"
                                                 : pane.route === "terminal" || pane.askHow ? "background" : "auto", false)
                            // (its key: Enter in the box; on in the background, Ctrl+Shift+Enter; Claude at work, Ctrl+Enter skips the wait)
                            PlasmaComponents3.ToolTip.text: commandRun !== "" ? "" : pane.replyAnswers ? i18n("Enter")
                                : pane.route === "terminal" || pane.askHow ? i18n("Send, go on in the background (Ctrl+Shift+Enter)")
                                : pane.atWork ? i18n("Send (Enter; Ctrl+Enter: without the 5 s wait while Claude works)") : i18n("Send (Enter)")
                            PlasmaComponents3.ToolTip.visible: hovered && PlasmaComponents3.ToolTip.text !== ""
                            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                        }
                    }
                }
            }

            // ---------------------------------------------------------------- Review
            // (ReviewPage.qml: made the first time the tab shows, then kept)
            Loader {
                id: reviewPage
                visible: pane.tab === "review"
                active: false
                Layout.fillWidth: true
                Layout.fillHeight: true
                source: active ? "ReviewPage.qml" : ""
            }
        }

        // Talpy Chat's keys (? in an empty box): KeysHelp.qml, read and made only while it shows
        Loader {
            anchors.fill: parent
            z: 90
            active: pane.helpOn
            source: active ? "KeysHelp.qml" : ""
        }

        // A picture of yours, big: a click anywhere (or × or Esc) closes it, Open shows it in
        // your picture viewer (BigPicture.qml, read and made only while one shows)
        Loader {
            anchors.fill: parent
            z: 100
            active: pane.bigPicture !== ""
            source: active ? "BigPicture.qml" : ""
        }
    }
}
