import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import org.kde.notification
import "hub"
import "icons.mjs" as Icons

PlasmoidItem {
    id: root

    // Parsed output of contents/code/talpy_den.py (see its collect()).
    property var status: null
    property string errorText: ""
    // Per-session memory across polls, per source ("" = this computer,
    // "ssh:<host>" = an SSH host): last state, when the current turn started,
    // and the last notification so a newer one replaces it and a stale
    // "needs input" one can be closed.
    property var lastStates: ({})
    property var turnStarts: ({})
    property var lastEnded: ({})   // the turns that ended lately (a minute, while idle or done), told as finished: {chat key: {took: how long it took, at: when}}
    property var notifications: ({})
    property var primedSources: ({})
    property string actionError: ""
    property string actionInfo: ""

    // Popup state kept by row key (rows get new data every poll)
    property var expandedAgents: ({})
    property var expandedAgentRuns: ({}) // subagents showing their task, last steps and report (row key|agent id)
    property var expandedPeek: ({})     // rows showing your last prompt, Claude's reply and the tasks
    property var expandedStats: ({})    // accounts showing their last days
    property var expandedRecent: ({})
    property string stopConfirmSession: ""
    readonly property var emptyGroup: ({ id: "", name: "", title: "", plan: "", profiles: [], profileKeys: [],
                                         sessions: [], limits: null, tokens: null, projects: [], chatProfile: "",
                                         sharedHere: [], recent: [], plans: [] })
    readonly property var emptySession: ({ key: "", profileDir: "", sessionId: "", chatId: "", pid: null, name: "", cwd: "", cwdShort: "", profile: "",
                                           kind: "", entrypoint: "", state: "idle", reason: "", waitingFor: "",
                                           detail: "", since: null, startedAt: null, context: null, model: null,
                                           costUsd: null, agents: null, shared: null, effort: null, tmux: false,
                                           peek: null, changes: null, tasks: null, stats: null, plan: null, stopped: null,
                                           overlaps: null, live: null })
    readonly property var emptyFound: ({ key: "", sessionId: "", name: "", cwd: "", cwdShort: "", lastActive: 0, profile: "",
                                         profileDir: "", groupId: "", account: "", shared: false, match: "", openCommand: "" })
    readonly property var emptyPlan: ({ key: "", slug: "", title: "", path: "", profileDir: "", profile: "", updatedAt: 0,
                                        inProject: false, projectFolder: "",
                                        shared: false, chatId: null, chatProfileDir: null, cwd: "", cwdShort: "", edited: false,
                                        openCommand: null, starred: false })
    readonly property var emptyRecent: ({ key: "", sessionId: "", name: "", cwd: "", cwdShort: "", lastActive: 0, profileDir: "",
                                          profile: "", shared: false, openCommand: "", starred: false })
    readonly property var emptyMemory: ({ key: "", name: "", description: "", type: "", path: "", folder: "", folderShort: "",
                                          updatedAt: 0, folderGone: false })
    readonly property var emptyTask: ({ subject: "", status: "pending" })
    readonly property var emptyDay: ({ day: "", total: 0, output: 0, messages: 0, chats: 0, prompts: 0 })
    readonly property var emptyProject: ({ name: "", path: "", total: 0, output: 0, prompts: 0 })
    readonly property var emptyAgent: ({ id: "", parent: null, depth: 0, type: "", description: "",
                                         status: "done", activity: "", started: null, updated: null, model: null,
                                         task: "", steps: [], report: "", toolCalls: null, tokens: null })
    readonly property string waitingName: {
        for (const g of allGroups)
            for (const s of g.sessions)
                if (s.state === "waiting")
                    return s.name
        return ""
    }

    readonly property var groups: status ? status.groups.map(g => withUsage(g, "")) : []
    property real now: Date.now()   // the last check's time (handleOutput)

    // Plan usage is the account's, whichever machine it's used on. An
    // account on several (this computer and SSH hosts: the same id) shows it
    // once, where it's listed first, with the newest numbers of them all
    // (sshUsage "once"); "all" shows each machine's own, "none" no host's.
    readonly property var usageOwners: {
        const out = {}
        const note = (g, host) => {
            const o = out[g.id] || (out[g.id] = { host: host, limits: null, from: "" })
            if (g.limits && (!o.limits || g.limits.updatedAt > o.limits.updatedAt)) {
                o.limits = g.limits
                o.from = host
            }
        }
        for (const g of (status ? status.groups : []))
            note(g, "")
        for (const host of shownHosts)
            for (const g of (remote[host] && remote[host].result ? remote[host].result.groups : []))
                note(g, host)
        return out
    }

    // The plan usage bars' columns, one width in every account (here and on
    // SSH hosts), so their bars line up: the widest window label shown, and
    // room for "resets in 23h 59m" at the line's end
    FontMetrics {
        id: usageFm
    }
    FontMetrics {
        id: usageSmallFm
        font: Kirigami.Theme.smallFont
    }
    readonly property real usageLabelWidth: {
        let widest = usageFm.advanceWidth("7d")
        const groups = (status ? status.groups : []).slice()
        for (const host of shownHosts)
            groups.push(...(remote[host] && remote[host].result ? remote[host].result.groups : []))
        for (const g of groups)
            for (const w of (g.limits ? g.limits.windows : []))
                widest = Math.max(widest, usageFm.advanceWidth(w.label || ""))
        return Math.ceil(widest) + Kirigami.Units.smallSpacing
    }
    readonly property real usageResetWidth: Math.ceil(usageSmallFm.advanceWidth(i18n("resets in %1", "23h 59m")))
    // how long ago, at the end of a recent chat's, a plan's or a memory's line: room for "23h 59m ago"
    readonly property real agoWidth: Math.ceil(usageSmallFm.advanceWidth(ago((23 * 60 + 59) * 60000)))
    // such a line's end, in columns: its folder (folderWidth), a starred one's ★ right before
    // the time (StarMark.qml: its room on every line) and how long ago, so they line up
    function endWidth(folderWidth) {
        return folderWidth + Kirigami.Units.iconSizes.small + agoWidth + 2 * Kirigami.Units.smallSpacing
    }

    // group as shown on host's section ("" here): limitsHidden when its usage
    // shows elsewhere (or no host's does), with the account's numbers all the
    // same in accountLimits (for limitReset), limitsFrom when the numbers come
    // from another machine
    function withUsage(group, host) {
        const mode = Plasmoid.configuration.sshUsage
        const owner = usageOwners[group.id]
        if (host && (mode === "none" || (mode !== "all" && owner && owner.host !== host)))
            return Object.assign({}, group, { limits: null, limitsHidden: true,
                                              accountLimits: owner ? owner.limits : group.limits })
        if (mode === "all" || !owner || owner.from === host)
            return group
        return Object.assign({}, group, { limits: owner.limits, limitsFrom: owner.from })
    }

    // SSH hosts and containers (remote.py): the hosts in ~/.ssh/config, the
    // containers here and on the SSH hosts shown, the ones you picked, and
    // what each answered ({loading, ok, error, result, updatedAt; a
    // container's: stopped, gone}). A container is docker:NAME, podman:NAME
    // or nerdctl:NAME (here), ENGINE:NAME@HOST (on the SSH host HOST): picked,
    // it's listed, checked and shown like a host. With Show containers off
    // the picked ones stay picked but aren't shown, and no engine is asked
    // anything.
    property var sshHosts: []
    property var containersHere: []      // this computer's (remote.py --hosts)
    property var containerNotes: []      // an engine here that couldn't list its containers, and why
    property var hostContainers: ({})    // SSH host -> {containers, notes, at} or {error} (remote.py --containers)
    readonly property bool showContainers: Plasmoid.configuration.showContainers
    readonly property var pickedHosts: Plasmoid.configuration.sshHosts.split(",").map(h => h.trim()).filter(h => h.length)
    readonly property var shownHosts: pickedHosts.filter(h => showContainers || !isContainer(h))
    property var remote: ({})

    // {engine, name, host} of a container's id ("" host: this computer's), or null for an SSH host
    function containerOf(id) {
        const m = /^(docker|podman|nerdctl):([A-Za-z0-9][A-Za-z0-9_.-]*)(?:@(.+))?$/.exec(id || "")
        return m ? { engine: m[1], name: m[2], host: m[3] || "" } : null
    }

    function isContainer(id) {
        return containerOf(id) !== null
    }

    // How an SSH host or a container is named: lab, web, or web on lab
    function hostLabel(id) {
        const c = containerOf(id)
        return !c ? id : c.host ? i18nc("a container on an SSH host", "%1 on %2", c.name, c.host) : c.name
    }

    function hostIcon(id) {
        return isContainer(id) ? iconDir + Icons.plasma.container : Icons.plasma.host
    }

    // A container as its last listing had it ({engine, name, image, running, activeAt, folderShort, …}), or null
    function containerInfo(id) {
        const c = containerOf(id)
        if (!c)
            return null
        const list = c.host ? ((hostContainers[c.host] || {}).containers || []) : containersHere
        return list.find(x => x.id === id) || null
    }

    // "podman · ubuntu:22.04", or its dev container's project folder; (on lab)
    function containerDetail(id, withHost) {
        const c = containerOf(id)
        const info = containerInfo(id)
        const parts = [info && info.folderShort ? info.folderShort : c.engine + (info && info.image ? " · " + info.image : "")]
        if (withHost && c.host)
            parts.push(i18nc("a container's SSH host", "on %1", c.host))
        return parts.join(" · ")
    }
    // The accounts of the hosts that answered, each marked with its host. A
    // host whose last check failed still shows what it said before (dimmed,
    // HostSection.qml), and at start what it said last time until its first
    // check answers, but that doesn't count here: no badge or shortcut for a
    // chat you can't reach.
    readonly property var remoteGroups: {
        const out = []
        for (const host of shownHosts) {
            const r = remote[host]
            if (r && r.result && !r.error && !r.cached)
                for (const g of r.result.groups)
                    out.push(Object.assign({}, withUsage(g, host), { host: host }))
        }
        return out
    }
    // Everything on the dashboard: this computer's accounts, then the hosts'
    readonly property var allGroups: groups.concat(remoteGroups)
    // (a chat a usage limit stopped waits for the limit, not for you: "limit",
    // whether a process still has it open or not)
    readonly property var counts: {
        const c = { waiting: 0, working: 0, idle: 0, done: 0, limit: 0 }
        for (const g of allGroups)
            for (const s of g.sessions)
                c[atLimit(s) ? "limit" : s.state] += 1
        return c
    }

    function atLimit(s) {
        return stopOf(s) === "limit"
    }

    // What stopped a chat's turn before it was through, while that holds:
    // "limit" (a usage limit, until it resets) or "login" (it expired), else ""
    function stopOf(s) {
        return (s.state === "idle" || s.state === "done") && s.stopped && !s.stopped.over ? s.stopped.kind : ""
    }
    // What happened since you last opened the popup, for the icon: chats that
    // started needing you, and chats that finished a turn (as long as the
    // "finished" notifications ask for), keyed like lastStates.
    property var unseen: ({})
    readonly property int unseenDone: Object.keys(unseen).filter(k => unseen[k] === "done").length
    readonly property int unseenWaiting: Object.keys(unseen).filter(k => unseen[k] === "waiting").length
    readonly property string overall: {
        if (counts.waiting)
            return "waiting"
        if (counts.working)
            return "working"
        // finished jobs kept for the record don't count as running
        return allGroups.some(g => g.sessions.some(s => (s.state === "idle" || s.state === "done") && s.pid !== null))
               ? "idle" : "none"
    }

    // The pets (PetStrip.qml, Pet.qml): their moods follow the sessions, and
    // petEvent makes one react ("done", "failed", "reset", "waiting", …): the
    // pet of the chat with that row key, or the main one.
    signal petEvent(string kind, string text, string key)
    // One clock for all the pets of this widget, so its window is drawn once
    // a tick, not once for each pet; a pet draws itself only when that shows
    // something new (TalpyView.qml)
    signal petFrame(real now)
    // 60 a second in the popup (it's open for a while), 30 on the desktop
    // (always there: every picture is a new frame of the whole desktop)
    readonly property real petFrameMs: onDesktop ? 33.3 : 16.7
    // In step with the screen: a frame animation ticks as each frame is made
    // (a timer of its own drifted against the screen and showed about one
    // frame in 18 twice), every frame or every other one (half a frame of
    // slack, so a frame that comes a little early still counts). It runs
    // while a stage of pets can be seen: running, it has the whole window
    // drawn again at every frame of the screen (on the desktop, all of it).
    FrameAnimation {
        running: Plasmoid.configuration.showPet && root.playingStages.length > 0
        property real last: 0
        onTriggered: {
            const now = Date.now()
            if (now - last < root.petFrameMs - 8)
                return
            last = now
            root.petFrame(now)
        }
    }
    // Motion in the list: where each chat's row was drawn last (SessionRow.qml
    // slides a row from there when its chat moves up or down, and fades in one
    // that's new). A plain object (no bindings wake up), forgotten whenever the
    // popup hides; rowSpace is the list's content (FullRepresentation.qml).
    // Plasma's animation speed set to instant turns it off.
    property var rowSpots: ({})
    property Item rowSpace: null
    property bool rowsPlaced: false   // laid out once since the popup showed: what's new from now on fades in
    readonly property bool animateRows: !lessMotion && dashboardShown && !coveredByWindow
    // Plasma's animation speed set to instant: less motion, as a desktop that
    // asks for it gets in VS Code too: the pets don't dig about (one whose
    // spot moves is just there), are taken out of their burrow at once and
    // don't swing in your hand, the big Talpy has a cookie where he stands,
    // and his light and stars keep still (Pet.qml, PetStrip.qml). (Instant
    // makes Kirigami's durations 1 ms, not 0: animations of 0 ms misfire.)
    readonly property bool lessMotion: Kirigami.Units.longDuration <= 1
    onDashboardShownChanged: {
        rowSpots = ({})
        rowsPlaced = false
        if (dashboardShown)
            rowsPlacedTimer.restart()
        else
            cancelMove()   // (a question about moving a plan: gone with the popup, nothing moved)
    }
    Timer {
        id: rowsPlacedTimer
        interval: 1500
        onTriggered: root.rowsPlaced = true
    }

    // Each chat pet's color by pet key, for the bar next to its chat in the
    // list (every pet stage publishes its own: setPetColors)
    property var petColorsByStage: ({})
    readonly property var petColors: {
        const all = {}
        for (const stage in petColorsByStage)
            Object.assign(all, petColorsByStage[stage])
        return all
    }

    function dropPetColors(stage) {   // a stage that's gone (its account isn't listed any more)
        if (!(stage in petColorsByStage))
            return
        const next = Object.assign({}, petColorsByStage)
        delete next[stage]
        petColorsByStage = next
    }

    function setPetColors(stage, colors) {
        if (JSON.stringify(petColorsByStage[stage] || {}) === JSON.stringify(colors))
            return   // unchanged: don't make every row look again
        petColorsByStage = Object.assign({}, petColorsByStage, { [stage]: colors })
    }

    // The hero's headline: the most important thing on the dashboard
    function headlineText() {
        if (!status && errorText)
            return i18n("Status unavailable")
        if (!status)
            return i18n("Looking for your chats…")
        if (counts.waiting)
            return i18np("%1 chat needs you", "%1 chats need you", counts.waiting)
        if (counts.working)
            return i18np("%1 chat working", "%1 chats working", counts.working)
        if (counts.idle)
            return i18np("Your turn in %1 chat", "Your turn in %1 chats", counts.idle)   // Claude finished its reply
        if (counts.limit)
            return i18np("%1 chat waits for its usage limit", "%1 chats wait for their usage limit", counts.limit)
        if (counts.done)
            return i18np("%1 finished chat to look at", "%1 finished chats to look at", counts.done)
        return i18n("All quiet")
    }

    // A chat's key: its account and conversation, so its pet, its
    // notifications and whether you've seen it stay the same while its row
    // changes (e.g. a background session's row from running to finished,
    // …/live to …/job). A chat shared with two accounts is two chats here.
    function petKeyOf(session, host) {
        return (host ? "ssh:" + host + "|" : "") + (session.profileDir || "") + "/"
               + (session.chatId || session.sessionId || session.key)
    }
    property var lastWindows: ({})
    readonly property string petsDir: decodeURIComponent(Qt.resolvedUrl("../pets/").toString().replace(/^file:\/\//, ""))
    // On the desktop the dashboard is shown all the time, and is often under
    // your windows: there the pets and the spinner stop moving while a window
    // covers it all (CoverWatch.qml), since every frame redraws the screen.
    // Playful Talpy (a setting): his tricks, props, jokes, cookies and games; off, he shows only what the chats do
    readonly property bool playful: Plasmoid.configuration.playful !== false
    // A game with the big Talpy (Pet.qml): Play with Talpy asks for one (once his stage shows),
    // a click outside his stage ends it (FullRepresentation.qml), and gameStage is that stage while it's on
    property bool playWanted: false
    property bool gameStopWanted: false
    property Item gameStage: null
    function playWithTalpy() {
        if (!Plasmoid.configuration.showPet)
            return
        popupTab = "chats"
        if (!expanded && !onDesktop)
            expanded = true
        playWanted = false
        playWanted = true
    }
    readonly property bool onDesktop: Plasmoid.formFactor === PlasmaCore.Types.Planar && !inTray
    // The dashboard is on screen: the popup is open, or it's shown in place
    // (on the desktop). There, opening a chat "closes the popup" too
    // (expanded false), though the dashboard stays: its pets froze.
    readonly property bool dashboardShown: expanded || shownInPlace
    // (the dashboard is drawn where the widget is, on the desktop: no popup to
    // open, so with another copy that has one, that one notifies: hub/Hub.qml)
    readonly property bool shownInPlace: Window.window !== null && fullRepresentationItem !== null
                                         && fullRepresentationItem.Window.window === Window.window
    onShownInPlaceChanged: Hub.placed(instanceId, !shownInPlace)
    // (with the mouse on it, it can be seen: a window over it would have the mouse)
    readonly property bool coveredByWindow: coverWatch.item !== null && coverWatch.item.covered && !mouseOnWidget.hovered
    // Windows over a part of the widget on the desktop (CoverWatch.qml): what's
    // all under them holds still, as everything does once all of it is
    // covered (a stage of pets: PetStrip.qml, the spinner, the ticker).
    // clipTo: the list the item scrolls in, if any (what of it can show).
    readonly property var windowsOver: coverWatch.item !== null ? coverWatch.item.over : []
    function underWindows(item, clipTo) {
        return windowsOver.length > 0 && coverWatch.item !== null && coverWatch.item.hides(item, clipTo || null)
    }
    // The stages whose pets move now (PetStrip.qml: playing): the pets' clock
    // above runs while there's one
    property var playingStages: []
    function stagePlaying(stage, on) {
        const at = playingStages.indexOf(stage)
        if (on === (at >= 0))
            return
        const next = playingStages.slice()
        if (on)
            next.push(stage)
        else
            next.splice(at, 1)
        playingStages = next
    }
    HoverHandler {
        id: mouseOnWidget
        enabled: root.onDesktop
    }
    Loader {
        id: coverWatch
        active: root.onDesktop
        source: "CoverWatch.qml"
    }
    readonly property int agentsRunning: {
        let n = 0
        for (const g of allGroups)
            for (const s of g.sessions)
                if (s.agents && s.state !== "done")
                    n += s.agents.running
        return n
    }
    readonly property real maxFiveHour: {
        let m = 0
        for (const g of allGroups)
            for (const w of (g.limits ? g.limits.windows : []))
                if (w.key === "five_hour")
                    m = Math.max(m, w.pct)
        return m
    }
    // Accounts close to their 5-hour limit, e.g. "work: 100% of the 5-hour limit!".
    // Talpy shows it now and then (mind-blown, or out of steam at the limit).
    readonly property string highUsageText: {
        const parts = []
        for (const g of allGroups)
            for (const w of (g.limits ? g.limits.windows : []))
                if (w.key === "five_hour" && w.pct >= 90)
                    parts.push(i18n("%1: %2% of the 5-hour limit!", groupLabel(g), Math.round(w.pct)))
        return parts.join(" ")
    }
    // A working session whose context window is nearly full and that has no
    // pet of its own to show it, e.g. "fix parser: context 91% full"
    readonly property string contextFullText: {
        for (const g of allGroups)
            for (const s of g.sessions)
                if (s.state === "working" && s.context !== null && s.context >= 85 && !(petKeyOf(s, g.host) in petColors))
                    return i18n("%1: context %2% full", s.name, Math.round(s.context))
        return ""
    }
    readonly property string petMood: {
        if (!status && errorText)
            return "error"
        if (!status)
            return "loading"
        if (overall === "waiting")
            return "needs"
        if (overall === "working")
            return agentsRunning > 0 ? "agents" : "working"
        if (overall === "idle")
            return "idle"
        return "done"
    }

    // The account whose 5-hour usage goes next to the panel icon: this
    // computer's default account (listed first; VS Code's Claude and plain
    // claude run on it, see accounts.py --default), else the one with an
    // active session, else the one with the freshest numbers.
    readonly property var panelWindow: {
        const own = allGroups.find(g => !g.host && g.defaultHere && g.limits && g.limits.windows.length)
        if (own)
            return own.limits.windows[0]
        let best = null, bestScore = -1
        for (const g of allGroups) {
            if (!g.limits || !g.limits.windows.length)
                continue
            const active = g.sessions.some(s => s.state === "working" || s.state === "waiting")
            const score = (active ? 1e15 : 0) + g.limits.updatedAt
            if (score > bestScore) {
                bestScore = score
                best = g.limits.windows[0]
            }
        }
        return best
    }

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))
    readonly property string configDirArgs: Plasmoid.configuration.extraConfigDirs.split(",")
        .map(d => d.trim()).filter(d => d.length).map(d => " --config-dir " + shellQuote(d)).join("")
    readonly property string command: {
        // (poll.py runs talpy_den.py with its compiled code cached)
        let cmd = "python3 -I " + shellQuote(codeDir + "poll.py") + configDirArgs
        cmd += " --done-hours " + Math.max(0, Plasmoid.configuration.keepDoneHours)
        cmd += recentArgs
        if (!Plasmoid.configuration.showTokens)
            cmd += " --no-tokens"
        if (Plasmoid.configuration.usageCap > 0)
            cmd += " --usage-cap " + Math.round(Plasmoid.configuration.usageCap)
        cmd += " --usage-refresh " + Math.max(0, Math.round(Plasmoid.configuration.usageRefreshMinutes))
        return cmd   // (hub/Hub.qml adds --instance and --interval-ms)
    }

    // The model and reasoning effort new chats start with (the new-chat box
    // picks them), as claude's options; not for VS Code's Claude, which has its own
    readonly property string chatOptions: (Plasmoid.configuration.newChatModel
                                           ? " --model " + shellQuote(Plasmoid.configuration.newChatModel) : "")
                                          + (Plasmoid.configuration.newChatEffort
                                             ? " --effort " + shellQuote(Plasmoid.configuration.newChatEffort) : "")
                                          + (Plasmoid.configuration.newChatMode
                                             ? " --permission-mode " + shellQuote(Plasmoid.configuration.newChatMode) : "")

    // ---------------------------------------------------------------- several widgets
    // This widget can run several times, e.g. on a panel, in the system tray
    // and on each screen's desktop. The copies share one check (hub/Hub.qml);
    // the one here longest sends the notifications and sounds (one with a
    // popup before one shown in place on the desktop), and across
    // programs talpy_den.py picks one (several widgets at once). Settings
    // are shared: a change is saved for the others at the next check, and the
    // others take it over at theirs (a new copy takes over what the others use).
    readonly property string instanceId: (Plasmoid.containment ? Plasmoid.containment.id + "/" : "") + Plasmoid.id
    readonly property bool notifier: (status === null || status.notifier !== false) && Hub.leaderId === instanceId
    // In the system tray, which draws the popup's heading itself (settable for render tests)
    property bool inTray: (Plasmoid.containmentDisplayHints & PlasmaCore.Types.ContainmentDrawsPlasmoidHeading) !== 0
    readonly property var sharedKeys: ["pollInterval", "idlePollInterval", "extraConfigDirs", "notifyWaiting", "notifyDone",
        "notifyDoneMinSeconds", "notifySound", "soundVolume", "soundWaiting", "soundDone", "soundFailed", "recentChats",
        "sshHosts", "remotePollSeconds", "sshUsage", "showContainers", "containerDays", "keepDoneHours", "showUsageInPanel", "showPet", "playful", "chatPets", "showTokens",
        "newChatInVscode", "iconBlink", "awayDigest", "awayMinutes", "phoneWhileAway", "phoneFinished", "phoneDevice",
        "markdownApp", "newChatModel", "newChatEffort", "newChatMode", "usageCap", "usageRefreshMinutes", "recapRules", "clickOpensPane",
        "mondayRecap", "recapCurrency", "diffSideBySide", "paneTextPercent", "paneFont", "paneTerminalFont", "dictateLanguage"]
    property real settingsSeenAt: 0     // the newest shared settings this copy has seen
    property string settingsSeen: ""    // its own settings as of the last check (to see changes)

    function currentSettings() {
        const values = {}
        for (const key of sharedKeys)
            values[key] = Plasmoid.configuration[key]
        return values
    }

    function syncSettings(shared) {
        const first = settingsSeen === ""
        if (shared && shared.at > settingsSeenAt) {
            settingsSeenAt = shared.at
            if (shared.by !== instanceId) {
                for (const key in shared.values)
                    if (sharedKeys.indexOf(key) >= 0 && Plasmoid.configuration[key] !== shared.values[key])
                        Plasmoid.configuration[key] = shared.values[key]
                settingsSeen = JSON.stringify(currentSettings())
                return
            }
        }
        const now = JSON.stringify(currentSettings())
        if (now === settingsSeen)
            return
        settingsSeen = now
        // Changed here: save it for the others. The first check of a copy
        // saves only what's been set up, so a new copy can't replace the
        // others' settings with defaults.
        if (!first || !shared)
            settingsSaver.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --save-settings " + shellQuote(now)
                                        + " --by " + shellQuote(instanceId) + (first ? " --unless-default" : "") + " # " + Date.now())
    }

    Exec {
        id: settingsSaver
        onNewData: (source, data) => disconnectSource(source)
    }

    Plasmoid.icon: "dialog-messages"
    // In the system tray, "shown when relevant" means: while a chat runs, and
    // until you've seen what needs you or finished
    Plasmoid.status: overall === "waiting" || unseenDone > 0 ? PlasmaCore.Types.NeedsAttentionStatus
                   : inTray && overall === "none" ? PlasmaCore.Types.PassiveStatus
                   : PlasmaCore.Types.ActiveStatus

    toolTipMainText: i18n("Talpy Den")
    toolTipSubText: tooltipText()

    switchWidth: Kirigami.Units.gridUnit * 16
    switchHeight: Kirigami.Units.gridUnit * 12

    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    // The widget's keyboard shortcut (its settings' Keyboard Shortcuts page)
    // goes to the chat that needs you, or opens the popup when none does
    // (shortcutGoesToChat). Plasma opens the popup on the shortcut whatever
    // the widget says (activationTogglesExpanded only stops it from closing),
    // so a jump closes it again right away, and opening it counts as seeing
    // the chats only once it stays open (markSeen). In the system tray, the
    // tray opens the popup.
    property bool shortcutJump: false
    Connections {
        target: Plasmoid
        function onActivated() {
            if (root.inTray || !Plasmoid.configuration.shortcutGoesToChat)
                return
            const chats = root.chatsNeedingYou()
            if (!chats.length)
                return
            root.shortcutJump = true
            Qt.callLater(() => {
                root.goToNextChat(chats)
                root.expanded = false
                root.shortcutJump = false
            })
        }
    }

    // Chats that need you, most urgent first: waiting (the longest first),
    // then ones that finished a turn while you weren't looking (newest first).
    // Keys as in trackTransitions.
    function chatsNeedingYou() {
        const waiting = [], finished = []
        const seen = {}
        for (const g of allGroups) {
            for (const s of g.sessions) {
                const key = petKeyOf(s, g.host)
                if (key in seen)
                    continue   // the chat's most urgent row came first
                seen[key] = true
                if (s.state === "waiting")
                    waiting.push({ key: key, session: s, host: g.host || "" })
                else if (unseen[key] === "done")
                    finished.push({ key: key, session: s, host: g.host || "" })
            }
        }
        waiting.sort((a, b) => (a.session.since || 0) - (b.session.since || 0))
        finished.sort((a, b) => (b.session.since || 0) - (a.session.since || 0))
        return waiting.concat(finished)
    }

    property string lastNextKey: ""
    property real lastNextAt: 0

    // Pressed again within 30 s, the shortcut goes on to the next chat
    function goToNextChat(chats) {
        if (!chats.length)
            return
        let i = 0
        if (Date.now() - lastNextAt < 30000) {
            const j = chats.findIndex(c => c.key === lastNextKey)
            if (j >= 0)
                i = (j + 1) % chats.length
        }
        const c = chats[i]
        lastNextKey = c.key
        lastNextAt = Date.now()
        forgetUnseen(c.key, "done")
        if (c.host)
            remoteShow(c.host, c.session)
        else
            jumpTo(c.session.sessionId, c.session.profileDir)
    }

    // While you're away (the screen is locked) for awayMinutes, chats that
    // finish or need you don't notify one by one: when you're back, one
    // notification sums up what happened since you left (awayDigest).
    property bool away: false
    property real awaySince: 0
    property var awayEvents: []         // [{kind: done|failed|stopped|limit|login|reset, name, key}]
    property var awayDigest: null       // the last summary, at the top of the popup until you've seen it

    function awayLongEnough() {
        return away && Date.now() - awaySince >= Plasmoid.configuration.awayMinutes * 60000
    }

    function holdingBack() {
        return awayLongEnough() && Plasmoid.configuration.awayDigest
    }

    // ...and meanwhile, chats that need you (or finish) go to your phone with
    // Refresh: Claude Code fetches the plan usage of every account whose
    // numbers are over a minute old, chat at work or not (talpy_den.py
    // --fetch-usage; the status says an account's is on its way: usageFetchAt)
    function fetchUsage() {
        usageFetcher.connectSource("python3 -I " + shellQuote(codeDir + "talpy_den.py") + " --fetch-usage" + configDirArgs
                                   + " # " + Date.now())
    }

    Exec {
        id: usageFetcher
        onNewData: (source, data) => {
            disconnectSource(source)
            root.refresh()   // (its fetch on its way shows; its numbers at the checks after)
        }
    }

    // KDE Connect (phoneWhileAway; jump.py --phone)
    function toPhone(text) {
        if (!root.notifier || !Plasmoid.configuration.phoneWhileAway || !awayLongEnough())
            return
        const device = Plasmoid.configuration.phoneDevice
        phoneSender.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --phone " + shellQuote(text)
                                  + (device ? " --device " + shellQuote(device) : "") + " # " + Date.now())
    }

    Exec {
        id: phoneSender
        onNewData: (source, data) => disconnectSource(source)   // a phone out of reach just misses it
    }

    function noteAway(kind, name, key) {
        if (away)
            awayEvents = awayEvents.concat([{ kind: kind, name: name, key: key || "" }])
    }

    function setAway(locked) {
        if (locked === away)
            return
        if (locked) {
            away = true
            awaySince = Date.now()
            awayEvents = []
            return
        }
        const took = Date.now() - awaySince
        away = false
        if (Plasmoid.configuration.awayDigest && took >= Plasmoid.configuration.awayMinutes * 60000)
            sendDigest(took)
        awayEvents = []
    }

    // "Needs you: fix-parser (waiting 22m)", "Finished: a, b", … for what
    // happened while you were away (events) and the chats waiting now
    function digestLines(events, waiting) {
        const lines = []
        const names = kind => {
            const seen = []
            for (const e of events)
                if (e.kind === kind && seen.indexOf(e.name) < 0)
                    seen.push(e.name)
            return seen
        }
        const list = all => all.slice(0, 4).join(", ") + (all.length > 4 ? " " + i18nc("and more", "+%1", all.length - 4) : "")
        for (const c of waiting.slice(0, 3))
            lines.push(i18n("Needs you: %1 (waiting %2)", c.session.name + (c.host ? " · " + hostLabel(c.host) : ""),
                            duration(Date.now() - (c.session.since || Date.now()))))
        if (waiting.length > 3)
            lines.push(i18np("+%1 more needs you", "+%1 more need you", waiting.length - 3))
        const done = names("done"), failed = names("failed"), stopped = names("stopped"), limited = names("limit")
        const loggedOut = names("login"), resets = names("reset")
        if (done.length)
            lines.push(i18n("Finished: %1", list(done)))
        if (failed.length)
            lines.push(i18n("Failed: %1", list(failed)))
        if (stopped.length)
            lines.push(i18n("Stopped: %1", list(stopped)))
        if (limited.length)
            lines.push(i18n("Hit the usage limit: %1", list(limited)))
        if (loggedOut.length)
            lines.push(i18n("Login expired: %1", list(loggedOut)))
        for (const r of resets)
            lines.push(i18n("%1 limit reset", r))
        return lines
    }

    function sendDigest(took) {
        const waiting = chatsNeedingYou().filter(c => c.session.state === "waiting")
        const lines = digestLines(awayEvents, waiting)
        if (!lines.length)
            return
        const title = i18n("While you were away (%1)", duration(took))
        awayDigest = { title: title, lines: lines }
        if (!root.notifier || !(Plasmoid.configuration.notifyWaiting || Plasmoid.configuration.notifyDone))
            return
        const first = waiting.length ? waiting[0] : null
        notify("away-digest", first ? first.session : null, "digest", title, lines.join("\n"), Icons.plasma.away, first ? first.host : "")
        queueSound(waiting.length ? "waiting" : awayEvents.some(e => ["failed", "limit", "login"].indexOf(e.kind) >= 0) ? "failed" : "done")
        playQueuedSound()
    }

    // Is the screen locked? Asked every 10 s by the copy that notifies, under
    // the same name each time (no " # <time>": the last run ended long ago,
    // and every executable DataSource in plasmashell keeps each name it hears
    // of, hub/Exec.qml).
    Exec {
        id: lockWatch
        onNewData: (source, data) => {
            disconnectSource(source)
            const out = String(data["stdout"] || "")
            if (/boolean (true|false)/.test(out))
                root.setAway(out.indexOf("boolean true") >= 0)
        }
    }

    Timer {
        interval: 10000
        repeat: true
        running: root.notifier && (Plasmoid.configuration.awayDigest || Plasmoid.configuration.phoneWhileAway)
        triggeredOnStart: true
        onTriggered: lockWatch.connectSource("dbus-send --session --print-reply=literal --dest=org.freedesktop.ScreenSaver"
                                             + " /ScreenSaver org.freedesktop.ScreenSaver.GetActive")
    }

    // Runs `jump.py --changes`: the files a chat changed, side by side in VS Code
    Exec {
        id: differ
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't compare the changes: %1", result.message)
                actionErrorTimer.restart()
            }
        }
    }

    function showChanges(chatId, profileDir, turn) {
        differ.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --changes " + shellQuote(chatId)
                             + profileArg(profileDir) + (turn ? " --turn" : "") + configDirArgs + " # " + Date.now())
    }

    function toggleStats(groupKey) {
        expandedStats = Object.assign({}, expandedStats, { [groupKey]: !expandedStats[groupKey] })
    }

    // "Tue" (long: "Tuesday 15 October") for a day of the stats ("2026-10-15")
    function dayName(day, long) {
        const p = String(day).split("-").map(Number)
        if (p.length !== 3)
            return ""
        const d = new Date(p[0], p[1] - 1, p[2])
        return long ? d.toLocaleDateString(Qt.locale(), "dddd d MMMM") : Qt.locale().dayName(d.getDay(), Locale.NarrowFormat)
    }

    // A chat's recap (talpy_den.py: stats_summary), e.g. "3 prompts ·
    // worked 51m · 278 tool calls (Bash 236, Read 23) · 85.3M tokens (249k out)"
    function recapText(st, costUsd) {
        if (!st)
            return ""
        const parts = [i18np("%1 prompt", "%1 prompts", st.prompts)]
        if (st.workedMs > 0)
            parts.push(i18n("worked %1", st.workedMs < 60000 ? i18nc("less than a minute", "<1m") : duration(st.workedMs)))
        if (st.toolCalls)
            parts.push(i18np("%1 tool call", "%1 tool calls", st.toolCalls)
                       + " (" + st.tools.slice(0, 3).map(t => t[0] + " " + t[1]).join(", ") + ")")
        parts.push(i18n("%1 tokens (%2 out)", formatTokens(st.tokens.total), formatTokens(st.tokens.output)))
        if (costUsd !== null && costUsd !== undefined && costUsd > 0)
            parts.push(i18n("$%1 at API prices", costUsd.toFixed(2)))
        return parts.join(" · ")
    }

    // A row's key for what's open in it (details, subagents, a stop asked) and
    // where it was drawn: its chat, not session.key, which goes from live to
    // job when a background session ends
    function rowKeyOf(s, host) {
        return (host ? host + "|" : "") + (s.profileDir || "") + "/" + (s.chatId || s.sessionId || "")
    }

    function togglePeek(rowKey) {
        const next = Object.assign({}, expandedPeek)
        next[rowKey] = !next[rowKey]
        expandedPeek = next
    }

    // The right-click menu's default account choices show a radio button as
    // their icon, so it sits under the other entries' icons (a checkable
    // entry's own mark is drawn in a column of its own, left of them)
    readonly property string iconDir: decodeURIComponent(Qt.resolvedUrl("../icons/").toString().replace(/^file:\/\//, ""))

    function defaultIcon(account) {
        return iconDir + (account !== null && account.defaultHere === true ? "radio-on.svg" : "radio-off.svg")
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh")
            icon.name: Icons.plasma.refresh
            onTriggered: root.refresh()
        },
        // what you hid, kind by kind (each only when some are hidden)
        PlasmaCore.Action {
            text: root.showHiddenText("chats", root.hiddenCount("chats", ""))
            icon.name: Icons.plasma.showHidden
            visible: root.hiddenCount("chats", "") > 0
            onTriggered: root.showHidden("chats", "")
        },
        PlasmaCore.Action {
            text: root.showHiddenText("plans", root.hiddenCount("plans", ""))
            icon.name: Icons.plasma.showHidden
            visible: root.hiddenCount("plans", "") > 0
            onTriggered: root.showHidden("plans", "")
        },
        PlasmaCore.Action {
            text: root.showHiddenText("memories", root.hiddenCount("memories", ""))
            icon.name: Icons.plasma.showHidden
            visible: root.hiddenCount("memories", "") > 0
            onTriggered: root.showHidden("memories", "")
        },
        PlasmaCore.Action {
            text: root.showHiddenText("projects", root.hiddenCount("projects", ""))
            icon.name: Icons.plasma.showHidden
            visible: root.hiddenCount("projects", "") > 0
            onTriggered: root.showHidden("projects", "")
        },
        PlasmaCore.Action {
            text: i18n("Go to the Chat That Needs You")
            icon.name: Icons.plasma.goTo
            visible: root.chatsNeedingYou().length > 0
            onTriggered: root.goToNextChat(root.chatsNeedingYou())
        },
        // a game with the big Talpy (as four quick clicks on him: for the keyboard and touch)
        PlasmaCore.Action {
            text: i18n("Play with Talpy")
            icon.name: Icons.plasma.play
            visible: Plasmoid.configuration.showPet && root.playful
            onTriggered: root.playWithTalpy()
        },
        // Talpy plays (tricks, props, jokes, cookies, games), or only shows what the chats do
        PlasmaCore.Action {
            text: i18n("Playful Talpy")
            icon.name: Icons.plasma.playful
            checkable: true
            checked: Plasmoid.configuration.playful
            visible: Plasmoid.configuration.showPet
            onTriggered: Plasmoid.configuration.playful = checked
        },
        PlasmaCore.Action {
            text: i18n("Open Usage Page on claude.ai")
            icon.name: Icons.plasma.web
            onTriggered: Qt.openUrlExternally("https://claude.ai/settings/usage")
        },
        // The default account, as the settings' Accounts page makes it (up to four
        // here): radio buttons under a heading, as there is only one (they show
        // what the status says, so a refused switch leaves them as they were)
        PlasmaCore.Action {
            isSeparator: true
            text: i18n("Default Account")
            visible: root.defaultChoices.length > 1
        },
        PlasmaCore.Action {
            readonly property var account: root.defaultChoices[0] || null
            visible: root.defaultChoices.length > 1
            text: account ? account.title : ""
            icon.name: root.defaultIcon(account)
            onTriggered: root.makeDefault(account)
        },
        PlasmaCore.Action {
            readonly property var account: root.defaultChoices[1] || null
            visible: account !== null
            text: account ? account.title : ""
            icon.name: root.defaultIcon(account)
            onTriggered: root.makeDefault(account)
        },
        PlasmaCore.Action {
            readonly property var account: root.defaultChoices[2] || null
            visible: account !== null
            text: account ? account.title : ""
            icon.name: root.defaultIcon(account)
            onTriggered: root.makeDefault(account)
        },
        PlasmaCore.Action {
            readonly property var account: root.defaultChoices[3] || null
            visible: account !== null
            text: account ? account.title : ""
            icon.name: root.defaultIcon(account)
            onTriggered: root.makeDefault(account)
        }
    ]

    Connections {
        target: Hub
        function onOutput(command, stdout, stderr) {
            if (command === root.command)
                root.handleOutput(stdout, stderr)
            const host = root.hostOfCommand(command)
            if (host)
                root.handleRemote(host, { stdout: stdout, stderr: stderr })
        }
        function onStarted(command) {
            const host = root.hostOfCommand(command)
            if (host)
                root.setRemote(host, { loading: true })
        }
    }

    // Runs contents/code/jump.py, which brings a session to the front.
    Exec {
        id: jumper
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't open the chat: %1", result.message)
                actionErrorTimer.restart()
                root.petEvent("oops", i18n("Hmm, that didn't work."), "")
                if (!root.dashboardShown)
                    root.notify("jump-error", null, "error", i18n("Couldn't open the chat"), result.message, "dialog-error")
            }
        }
    }

    // Runs `jump.py --stop`, which stops a background session (`claude stop`)
    // or a chat in a terminal or VS Code (its claude quits), or `--interrupt`
    // (Esc for a chat in tmux).
    Exec {
        id: stopper
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (!result.ok) {
                root.actionError = i18n("Couldn't stop the chat: %1", result.message)
                actionErrorTimer.restart()
            } else {
                root.actionError = ""
                if (result.message.indexOf("killed") >= 0 || result.message.indexOf("ended") >= 0 || root.stopSays[source]) {
                    root.actionInfo = result.message   // more happened than you asked for: say so
                    actionInfoTimer.restart()
                }
            }
            delete root.stopSays[source]
            root.refresh()
        }
    }

    Timer {
        id: actionErrorTimer
        interval: 10000
        onTriggered: root.actionError = ""
    }

    Timer {
        id: actionInfoTimer
        interval: 12000
        onTriggered: root.actionInfo = ""
    }

    Component {
        id: notificationComponent
        Notification {
            id: notification
            property string sessionId
            property string profileDir
            property string kind
            property string host           // an SSH host's session...
            property string openCommand    // ...opens with this command there
            property var session: null     // (or, running there, is shown here)
            property var row: null         // the chat's row: a reply goes to it, a click opens the pane
            componentName: "plasma_workspace"
            eventId: "notification"
            hints: ({ "x-kde-display-appname": "Talpy Den" })
            defaultAction: NotificationAction {
                label: i18n("Open")
                onActivated: root.openFromNotification(notification, true)
            }
            // (one about no chat, as The default account didn't change, has only its click)
            property QtObject openChat: NotificationAction {
                label: i18n("Open chat")
                onActivated: root.openFromNotification(notification, false)
            }
            actions: sessionId !== "" || host !== "" ? [openChat] : []
            onClosed: {
                root.forgetNotification(notification)
                notification.destroy()   // (QML's notifications don't delete themselves once closed: autoDelete false)
            }
        }
    }

    // The Monday recap: once a week the last 7 days in a few words (week.py
    // --monday-recap: whichever copy of the widget or the VS Code extension
    // asks first that week gets it), and a click opens the Recap
    Component {
        id: recapNotificationComponent
        Notification {
            id: recapNote
            componentName: "plasma_workspace"
            eventId: "notification"
            hints: ({ "x-kde-display-appname": "Talpy Den" })
            iconName: Icons.plasma.recap
            defaultAction: NotificationAction {
                label: i18n("Open the Recap")
                onActivated: root.openRecap()
            }
            actions: [
                NotificationAction {
                    label: i18n("Open the Recap")
                    onActivated: root.openRecap()
                }
            ]
            onClosed: recapNote.destroy()
        }
    }
    function openRecap() {
        popupTab = "week"
        expanded = true
    }
    Timer {
        interval: 30 * 60000
        repeat: true
        triggeredOnStart: true
        running: root.notifier && Plasmoid.configuration.mondayRecap
        // (the SSH hosts shown, as the Recap it opens counts them: the ones that answered their last check)
        onTriggered: mondayAsk.connectSource("python3 -I " + root.shellQuote(root.codeDir + "week.py") + " --monday-recap"
                                             + root.shownHosts.filter(host => root.remote[host] && root.remote[host].result && !root.remote[host].error)
                                                              .map(host => " --host " + root.shellQuote(host)).join("")
                                             + root.configDirArgs)
    }
    Exec {
        id: mondayAsk
        onNewData: (source, data) => {
            disconnectSource(source)
            const r = root.helperResult(data)
            if (!r.ok || !r.due)
                return
            // (times as the Recap shows them: 20m, 3h 5m)
            const lines = [i18n("Claude worked %1 over %2; you, %3 and %4.", root.duration(r.workedMs), i18np("%1 chat", "%1 chats", r.chats),
                                root.duration(r.youMs), i18np("%1 prompt", "%1 prompts", r.prompts))]
            if (r.project)
                lines.push(i18n("Most of it in %1.", r.project))
            if (r.workedBefore > 0) {
                const change = Math.round((r.workedMs - r.workedBefore) / r.workedBefore * 100)
                lines.push(change >= 0 ? i18n("%1% more than the week before.", change) : i18n("%1% less than the week before.", -change))
            }
            recapNotificationComponent.createObject(root, { title: i18n("Your week with Claude"), text: lines.join("\n") }).sendEvent()
        }
    }

    // A chat that waits for a permission the widget can answer: its buttons,
    // in Claude's own order (Yes, Yes and don't ask again, No). The note
    // goes in the pane: Plasma puts a reply button before all the others.
    // Claude's question: one with one answer has a button per option, then
    // Other… (the pane, its field to answer in your own words); several, or
    // one with several answers, Answer… (the pane).
    Component {
        id: askNotificationComponent
        Notification {
            id: ask
            property string sessionId
            property string profileDir
            property string kind
            property string host
            property string openCommand
            property var session: null
            property var row: null         // the chat as it asked: the buttons answer that only (root.answerPermission)
            property string asked          // what it asked (root.askId): a check that finds it asks something else makes it anew
            readonly property bool withAlways: !!row && !!row.permission
                                               && (row.permission.answer === "keys" || row.permission.always !== "")
            readonly property var questions: row && row.permission && row.permission.questions ? row.permission.questions : []
            readonly property bool isPlan: !!row && !!row.permission && !!row.permission.plan
            readonly property var choices: questions.length === 1 && !questions[0].multiSelect ? questions[0].options.slice(0, 4) : []
            function choose(i) {
                root.answerPermission(ask.row, ask.host, "answer", "", { [questions[0].question]: [choices[i].label] })
            }
            property QtObject choice0: NotificationAction {
                label: ask.choices.length > 0 ? ask.choices[0].label : ""
                onActivated: ask.choose(0)
            }
            property QtObject choice1: NotificationAction {
                label: ask.choices.length > 1 ? ask.choices[1].label : ""
                onActivated: ask.choose(1)
            }
            property QtObject choice2: NotificationAction {
                label: ask.choices.length > 2 ? ask.choices[2].label : ""
                onActivated: ask.choose(2)
            }
            property QtObject choice3: NotificationAction {
                label: ask.choices.length > 3 ? ask.choices[3].label : ""
                onActivated: ask.choose(3)
            }
            property QtObject otherAction: NotificationAction {
                label: i18n("Other…")
                onActivated: root.answerInPane(ask.row, ask.host)
            }
            property QtObject answerAction: NotificationAction {
                label: i18n("Answer…")
                onActivated: root.openPane(ask.row, ask.host, "chat")
            }
            property QtObject allowAction: NotificationAction {
                label: i18n("Allow once")
                onActivated: root.answerPermission(ask.row, ask.host, "allow", "")
            }
            property QtObject alwaysAction: NotificationAction {
                label: i18n("Always allow")
                onActivated: root.answerPermission(ask.row, ask.host, "always", "")
            }
            property QtObject denyAction: NotificationAction {
                label: i18n("Deny")
                onActivated: root.answerPermission(ask.row, ask.host, "deny", "")
            }
            property QtObject noteAction: NotificationAction {
                label: i18n("Deny with a note…")
                onActivated: root.denyWithNote(ask.row, ask.host)
            }
            property QtObject approveAction: NotificationAction {
                label: i18n("Approve")
                onActivated: root.answerPermission(ask.row, ask.host, "approve", "")
            }
            property QtObject approveEditsAction: NotificationAction {
                label: i18n("Approve, accept edits")
                onActivated: root.answerPermission(ask.row, ask.host, "approve-edits", "")
            }
            property QtObject keepPlanningAction: NotificationAction {
                label: i18n("Keep planning…")
                onActivated: root.denyWithNote(ask.row, ask.host)
            }
            componentName: "plasma_workspace"
            eventId: "notification"
            hints: ({ "x-kde-display-appname": "Talpy Den" })
            defaultAction: NotificationAction {
                label: i18n("Open")
                onActivated: root.openFromNotification(ask, true)
            }
            actions: isPlan ? [approveEditsAction, approveAction, keepPlanningAction] : questions.length === 0 ? (withAlways ? [allowAction, alwaysAction, denyAction, noteAction] : [allowAction, denyAction, noteAction])
                     : choices.length ? [choice0, choice1, choice2, choice3].slice(0, choices.length).concat([otherAction])
                     : [answerAction]
            onClosed: {
                root.forgetNotification(ask)
                ask.destroy()
            }
        }
    }

    // How often this computer's chats are checked (the settings "While a
    // chat works" and "While no chat works"). Live (hub/Hub.qml runs
    // live.py --wait): a chat that starts, ends, waits or finishes its turn
    // is checked the moment its session file changes, so the checks in
    // between only catch the rest. While a chat works: every pollInterval,
    // as its steps come from the checks; with the live hook (live mode) they
    // come as they happen, so every liveWorkingMs (pollInterval is greyed
    // out then). While none works: every idlePollInterval (never more often
    // than pollInterval, without live mode).
    // Without the watching (live.py failing): every pollInterval while a
    // chat runs or the popup is open, else every idlePollInterval; a chat
    // that starts still shows soon (opening the popup checks at once). The
    // GNOME extension does that (logic.js).
    readonly property bool quiet: status !== null && overall === "none" && !root.dashboardShown
    readonly property int pollMs: Math.max(1000, Plasmoid.configuration.pollInterval)
    readonly property bool watching: Hub.liveHealthy
    readonly property bool liveHook: status !== null && status.liveHook === true
    readonly property int liveWorkingMs: 6000
    readonly property int restingMs: Math.max(watching && liveHook ? 1000 : pollMs, Plasmoid.configuration.idlePollInterval)
    readonly property int checkInterval: !watching ? (quiet ? restingMs : pollMs)
                                         : status !== null && status.counts.working > 0 ? (liveHook ? liveWorkingMs : pollMs)
                                         : restingMs

    // The checks come from hub/Hub.qml, as often as the most eager copy
    // wants them (an open popup: pollInterval)
    onCommandChanged: Hub.want(instanceId, "status", command, checkInterval, true)
    onCheckIntervalChanged: Hub.want(instanceId, "status", command, checkInterval, true)
    onLiveCommandChanged: Hub.wantLive(instanceId, liveCommand)
    Component.onDestruction: Hub.drop(instanceId)
    readonly property string liveCommand: "python3 -I " + shellQuote(codeDir + "live.py") + " --wait" + configDirArgs

    // Between checks the clock goes on (the times shown), as it did with a check every pollInterval
    Timer {
        interval: root.pollMs
        repeat: true
        running: root.watching && root.dashboardShown && root.checkInterval > root.pollMs
        onTriggered: root.now = Date.now()
    }

    // ---------------------------------------------------------------- live mode
    // What each running chat of this computer does now, step by step, from
    // the live hook (live_hook.py): its row's "live" at each check, and in
    // between what live.py hands on (Hub.live). sessionId -> the newest view.
    property var liveViews: ({})

    Connections {
        target: Hub
        function onLive(views) {
            root.noteLive(views)
        }
    }

    function noteLive(views) {
        let next = null
        for (const v of views) {
            const old = liveViews[v.sessionId]
            if (!v.sessionId || (old && (old.at || 0) >= (v.at || 0)))
                continue
            next = next || Object.assign({}, liveViews)
            if (v.state === "ended")
                delete next[v.sessionId]
            else
                next[v.sessionId] = v
        }
        if (next)
            liveViews = next
    }

    // At each check: the rows' views (kept only for the chats listed)
    function liveFromRows(groupList) {
        const next = {}
        let changed = false
        for (const g of groupList) {
            for (const s of g.sessions) {
                if (!s.pid)
                    continue
                const mine = liveViews[s.sessionId]
                const row = s.live ? Object.assign({ sessionId: s.sessionId, pid: s.pid }, s.live) : null
                const best = mine && (!row || (mine.at || 0) >= (row.at || 0)) ? mine : row
                if (best) {
                    next[s.sessionId] = best
                    changed = changed || best !== mine
                }
            }
        }
        if (changed || Object.keys(next).length !== Object.keys(liveViews).length)
            liveViews = next
    }

    // A running chat's live view (of this computer), or null
    function liveOf(s) {
        const v = s && s.pid ? liveViews[s.sessionId] : null
        return v && (!v.pid || v.pid === s.pid) ? v : null
    }

    // What a working chat does now: its live step when that's newer than
    // what the last check read from its transcript (an edit with the lines
    // it added and removed: "Edit: parser.py +12 −3")
    function doingText(s, host) {
        const v = host ? null : liveOf(s)
        const peek = s.peek || null
        if (v && v.doing && (v.at || 0) >= ((peek && peek.at) || 0)) {
            const steps = (v.steps || []).filter(st => !st.agent)
            const last = steps.length ? steps[steps.length - 1] : null
            const counts = last && last.text === v.doing && (last.add || last.del)
                         ? " +" + (last.add || 0) + " −" + (last.del || 0) : ""
            return v.doing + counts
        }
        return peek && peek.activity ? peek.activity : ""
    }

    // The focus view (FocusView.qml): the Chats tab with only what needs you
    // (oldest first), the turns that finished and you haven't looked at yet
    // (newest first) and one line for each chat at work; the rest counted,
    // each account's 5-hour usage
    readonly property bool focusView: Plasmoid.configuration.focusView
    function setFocusView(on) {
        Plasmoid.configuration.focusView = on
    }
    readonly property var focusLists: {
        if (!focusView)
            return { needs: [], finished: [], working: [], rest: "", usage: "" }
        const needs = [], finished = [], working = [], seen = {}
        const rest = { idle: 0, done: 0, limit: 0 }
        const usage = []
        for (const g of allGroups) {
            const five = g.limits ? g.limits.windows.find(w => w.key === "five_hour") : null
            if (five)
                usage.push(i18nc("an account's 5-hour usage", "%1 %2%", (g.host ? hostLabel(g.host) + ": " : "") + g.title, Math.round(five.pct)))
            for (const s of g.sessions) {
                const key = petKeyOf(s, g.host || "")
                if (key in seen)
                    continue   // (a chat's most urgent row came first)
                seen[key] = true
                const item = { key: key, session: s, host: g.host || "", account: g.title, multi: g.profiles.length > 1 }
                if (s.state === "waiting")
                    needs.push(item)
                else if (s.state === "working")
                    working.push(item)
                else if (finishedUnopened[key])
                    finished.push(item)
                else
                    rest[atLimit(s) ? "limit" : s.state === "idle" ? "idle" : "done"] += 1
            }
        }
        needs.sort((a, b) => (a.session.since || 0) - (b.session.since || 0))
        finished.sort((a, b) => (b.session.since || 0) - (a.session.since || 0))
        working.sort((a, b) => (a.session.since || 0) - (b.session.since || 0))
        const parts = []
        if (rest.idle)
            parts.push(i18np("%1 idle", "%1 idle", rest.idle))
        if (rest.limit)
            parts.push(i18np("%1 at the usage limit", "%1 at the usage limit", rest.limit))
        if (rest.done)
            parts.push(i18np("%1 done", "%1 done", rest.done))
        return { needs: needs, finished: finished, working: working, rest: parts.length ? i18n("Also: %1", parts.join(" · ")) : "",
                 usage: usage.length ? i18n("5-hour usage: %1", usage.join(" · ")) : "" }
    }

    // The hero's ticker (Ticker.qml): what each working chat does now
    readonly property var tickerItems: {
        const out = []
        for (const g of allGroups) {
            for (const s of g.sessions) {
                if (s.state !== "working")
                    continue
                const text = doingText(s, g.host || "")
                if (text)
                    out.push({ key: petKeyOf(s, g.host || ""), name: s.name, text: text, host: g.host || "", session: s })
            }
        }
        return out
    }

    function refresh() {
        Hub.refresh(command)
    }

    // Most checks say what the one before said but for their time and the
    // usage forecasts, which drift with it. Then only the clock moves on
    // (time labels) and the dashboard isn't rebuilt; the forecasts catch up
    // within 30 s.
    property string lastOutputKey: ""
    property real lastFullUpdate: 0

    function handleOutput(stdout, stderr) {
        const time = /"generatedAt": *(\d+)/.exec(stdout)
        const key = stdout.replace(/"generatedAt": *\d+/g, "").replace(/"forecast": *\{[^{}]*\}/g, "")
        if (status && time && key === lastOutputKey && Date.now() - lastFullUpdate < 30000) {
            now = Number(time[1])
            syncSettings(status.sharedSettings || null)   // (a setting changed here is saved for the others now)
            return
        }
        let parsed = null
        try {
            parsed = JSON.parse(stdout)
        } catch (e) {
            const lines = (stderr || "").trim().split("\n")
            errorText = i18n("Status script failed: %1", lines[lines.length - 1] || i18n("no output"))
            lastOutputKey = ""   // (the next good check clears it, even if it says what the last good one did)
            return
        }
        if (!parsed.ok) {
            errorText = i18n("Status unavailable: %1", parsed.error)
            lastOutputKey = ""
            return
        }
        errorText = parsed.errors.length ? parsed.errors.join("\n") : ""
        lastOutputKey = key
        lastFullUpdate = Date.now()
        now = parsed.generatedAt
        liveFromRows(parsed.groups)
        status = parsed   // first: whether this copy notifies
        trackTransitions("", parsed.groups, parsed.generatedAt, "")
        trackLimitStops("", parsed.groups, "")
        trackOverlaps("", parsed.groups, "")
        startDueTasks(parsed.queue || [])
        celebrateResets("", parsed.groups)
        syncSettings(parsed.sharedSettings || null)
    }

    function celebrateResets(source, groupList) {
        const next = Object.assign({}, lastWindows)
        const where = source ? " · " + hostLabel(source.slice("ssh:".length)) : ""   // (a host's groups don't carry their host)
        for (const g of groupList) {
            for (const w of (g.limits ? g.limits.windows : [])) {
                const key = source + "|" + g.id + "/" + w.key
                if (key in lastWindows && lastWindows[key] >= 25 && w.pct < lastWindows[key] - 20) {
                    petEvent("reset", i18n("%1 limit reset!", w.label), "")
                    noteAway("reset", w.label + where)
                }
                next[key] = w.pct
            }
        }
        lastWindows = next
    }

    // "work · Team", or "lab: work · Team" for an SSH host's account
    function groupLabel(g) {
        return g.host ? i18nc("ssh host: account", "%1: %2", hostLabel(g.host), g.name) : g.name
    }

    // Rows are tracked by account and chat (petKeyOf), not the chat id alone:
    // a chat shared across profiles is listed once per profile with the same
    // id, and keying by id made the two rows flip each other's state on every
    // poll (a notification each time).
    property var lastWaitingAlert: ({})   // row -> {at, ask}: its last "needs input" alert, and what it asked (askId)

    // One sound per poll at most (several sessions can change at once): the
    // most urgent of the notifications sent.
    property string pendingSound: ""
    readonly property var soundRank: ({ "": 0, done: 1, failed: 2, waiting: 3 })
    property string pendingSoundKind: ""

    function queueSound(kind) {
        if (!root.notifier || !Plasmoid.configuration.notifySound || soundRank[kind] <= soundRank[pendingSoundKind])
            return
        const sound = kind === "waiting" ? Plasmoid.configuration.soundWaiting
                    : kind === "failed" ? Plasmoid.configuration.soundFailed
                    : Plasmoid.configuration.soundDone
        if (sound) {
            pendingSound = sound
            pendingSoundKind = kind
        }
    }

    function playQueuedSound() {
        if (pendingSound)
            soundPlayer.connectSource("python3 -I " + shellQuote(codeDir + "notify_sound.py") + " " + shellQuote(pendingSound)
                                      + " --volume " + Plasmoid.configuration.soundVolume + " # " + Date.now())
        pendingSound = ""
        pendingSoundKind = ""
    }

    Exec {
        id: soundPlayer
        onNewData: (source, data) => disconnectSource(source)
    }

    // Notifications and pet reactions when a session changes state. source is
    // "" for this computer, "ssh:<host>" for an SSH host; each source keeps its
    // own memory, so one poll can't close another's notifications.
    function trackTransitions(source, groupList, nowMs, host) {
        const next = {}, starts = {}, ends = {}
        const before = lastStates[source] || {}
        const startedAt = turnStarts[source] || {}
        const ended = lastEnded[source] || {}
        const primed = !!primedSources[source]
        const where = host ? " · " + host : ""
        for (const g of groupList) {
            for (const s of g.sessions) {
                const sid = petKeyOf(s, host)   // starts with source + "|" for a host's
                if (sid in next)
                    continue   // a chat listed twice: its most urgent row (they come first) counts
                const prev = before[sid]
                const active = s.state === "working" || s.state === "waiting"
                next[sid] = s.state
                // A turn runs from leaving idle/done until returning to it.
                if (active)
                    starts[sid] = sid in startedAt ? startedAt[sid] : (s.since || nowMs)
                if (prev === "waiting" && s.state !== "waiting") {
                    closeNotification(sid, "waiting")  // answered: drop the stale prompt
                    forgetUnseen(sid, "waiting")
                }
                if (s.state === "working")
                    forgetUnseen(sid, "done")  // it's at it again
                if (!primed)
                    continue
                const stop = stopOf(s)
                if (stop && sid in ended) {
                    // Claude writes its transcript a moment after the turn ends, so
                    // the usage limit that ended it can show a check later: it
                    // didn't finish after all
                    turnEnded(sid, s, host, ended[sid].took, true)
                    continue
                }
                // (a check or two later too, with checks coming quickly: for a
                // minute, while it stays idle or done)
                if (sid in ended && (s.state === "idle" || s.state === "done") && nowMs - ended[sid].at < 60000)
                    ends[sid] = ended[sid]
                // A "needs you" notification that's out of date: the hook's request
                // came a check after the chat began to wait (now with its buttons),
                // or the chat asks something else now than what its buttons answer
                // (that was answered in the chat, and the next prompt came before a
                // check saw it at work)
                const told = notifications[sid]
                const alerted = lastWaitingAlert[sid]
                if (prev === "waiting" && s.state === "waiting" && told && told.kind === "waiting"
                        && (told.allowAction === undefined ? canAnswerAsk(s) : told.asked !== askId(s))) {
                    const asks = s.permission ? askText(s) : [i18n("%1 needs your input", s.name), s.detail || reasonText(s.reason)]
                    notify(sid, s, "waiting", asks[0], asks[1] + "\n" + s.cwdShort + where, "dialog-warning", host)
                    if (alerted)
                        alerted.ask = askId(s)
                } else if (prev === "waiting" && s.state === "waiting" && alerted && alerted.held && askId(s) && askId(s) !== alerted.ask) {
                    // a new prompt the minute's quiet held back (nothing told it
                    // apart from the last one then: the hook's request came a check later)
                    alertWaiting(sid, s, host, nowMs)
                }
                if (prev === s.state)
                    continue
                if (s.state === "waiting") {
                    markUnseen(sid, "waiting")
                    // At most one "needs input" alert per session per minute, unless
                    // it asks something new (the next command after you allowed one)
                    if (!alerted || nowMs - alerted.at >= 60000 || (askId(s) && askId(s) !== alerted.ask))
                        alertWaiting(sid, s, host, nowMs)
                    else
                        alerted.held = true
                } else if ((prev === "working" || (stop && prev === "waiting")) && (s.state === "idle" || s.state === "done")) {
                    // (a background session a limit stops can say it waits for a moment first)
                    const took = (s.since || nowMs) - (sid in startedAt ? startedAt[sid] : nowMs)
                    turnEnded(sid, s, host, took, false)
                    if (!stop)
                        ends[sid] = { took: took, at: nowMs }
                }
            }
        }
        // Sessions of this source that exited no longer need anything.
        const prefix = source ? source + "|" : ""
        for (const sid in notifications) {
            const mine = source ? sid.startsWith(prefix) : sid.indexOf("|") < 0
            if (mine && !(sid in next))
                closeNotification(sid, "waiting")
        }
        for (const sid in unseen) {
            const mine = source ? sid.startsWith(prefix) : sid.indexOf("|") < 0
            if (mine && !(sid in next))
                forgetUnseen(sid, "")
        }
        for (const sid in lastWaitingAlert) {
            const mine = source ? sid.startsWith(prefix) : sid.indexOf("|") < 0
            if (mine && !(sid in next))
                delete lastWaitingAlert[sid]
        }
        lastStates = Object.assign({}, lastStates, { [source]: next })
        turnStarts = Object.assign({}, turnStarts, { [source]: starts })
        lastEnded = Object.assign({}, lastEnded, { [source]: ends })
        primedSources = Object.assign({}, primedSources, { [source]: true })
        playQueuedSound()
    }

    // A chat waits for you: its pet, your phone and a notification say so
    function alertWaiting(sid, s, host, nowMs) {
        const where = host ? " · " + host : ""
        lastWaitingAlert[sid] = { at: nowMs, ask: askId(s) }
        petEvent("waiting", i18n("%1 needs you!", s.name), petKeyOf(s, host))
        toPhone(i18n("Claude: %1 needs you", s.name + where) + (s.detail ? " (" + s.detail + ")" : "")
                + " · " + s.cwdShort)
        if (Plasmoid.configuration.notifyWaiting && root.notifier && !holdingBack()) {
            const asks = s.permission ? askText(s) : [i18n("%1 needs your input", s.name), s.detail || reasonText(s.reason)]
            notify(sid, s, "waiting", asks[0], asks[1] + "\n" + s.cwdShort + where, "dialog-warning", host)
            queueSound("waiting")
        }
    }

    // A chat's turn ended (it was working, it's idle or done now) after took ms:
    // its pet reacts and a notification says how. A turn a usage limit or an
    // expired login broke off didn't finish. late: that shows only now, after
    // it was told as finished (which this takes back).
    function turnEnded(sid, s, host, took, late) {
        const where = host ? " · " + host : ""
        const stop = stopOf(s)
        const long = took >= Plasmoid.configuration.notifyDoneMinSeconds * 1000
        const pk = petKeyOf(s, host)
        if (stop === "limit")
            petEvent("limit", i18n("%1 hit the usage limit.", s.name), pk)
        else if (stop === "login")
            petEvent("stopped", i18n("%1: the login expired.", s.name), pk)
        else if (s.reason === "failed")
            petEvent("failed", i18n("%1 failed…", s.name), pk)
        else if (s.reason === "stopped")
            petEvent("stopped", i18n("%1 was stopped.", s.name), pk)
        else
            petEvent("done", i18n("%1 is done!", s.name), pk)
        if (late) {
            forgetUnseen(sid, "done")
            const i = awayEvents.map(e => e.key === sid && e.kind === "done").lastIndexOf(true)
            if (i >= 0)
                awayEvents = awayEvents.slice(0, i).concat(awayEvents.slice(i + 1))
        } else if (!stop && long) {
            markUnseen(sid, "done")
            if (!paneShows(sid))   // (its pane shows it: you're looking)
                finishedUnopened = Object.assign({}, finishedUnopened, { [sid]: true })
        }
        noteAway(stop || (s.reason === "failed" || s.reason === "stopped" ? s.reason : "done"), s.name + where, sid)
        if (Plasmoid.configuration.phoneFinished && long)
            toPhone((stop === "limit" ? i18n("Claude: %1 hit the usage limit", s.name + where)
                     : stop ? i18n("Claude: %1 stopped, the login expired", s.name + where)
                     : s.reason === "failed" ? i18n("Claude: %1 failed", s.name + where)
                     : s.reason === "stopped" ? i18n("Claude: %1 was stopped", s.name + where)
                     : i18n("Claude: %1 finished", s.name + where))
                    + (stop ? " (" + s.stopped.text + ")" : s.detail ? " (" + s.detail + ")" : "") + " · " + i18n("took %1", duration(took)))
        if (!Plasmoid.configuration.notifyDone || !root.notifier || holdingBack() || !long)
            return
        if (stop) {
            const kept = stop === "limit" && keptChat(s.chatId || s.sessionId, host)
            notify(sid, s, stop, stop === "limit" ? i18n("%1 hit the usage limit", s.name) : i18n("%1 stopped: the login expired", s.name),
                   s.stopped.text + (kept ? "\n" + i18n("It goes on by itself after the reset.") : "") + "\n"
                   + i18n("Took %1 · %2", duration(took), s.cwdShort) + where,
                   stop === "limit" ? "chronometer-pause" : "dialog-error", host)
            queueSound("failed")
        } else {
            notify(sid, s, "done", s.reason === "failed" ? i18n("%1 failed", s.name)
                                : s.reason === "stopped" ? i18n("%1 was stopped", s.name)
                                : i18n("%1 finished", s.name),
                   (s.detail ? s.detail + "\n" : "") + i18n("Took %1 · %2", duration(took), s.cwdShort) + where,
                   "dialog-ok", host)
            queueSound(s.reason === "failed" ? "failed" : "done")
        }
    }

    // plain: no buttons (no Allow / Deny, no Reply), whatever the chat asks
    function notify(key, session, kind, title, body, icon, host, plain) {
        // One notification per row: a newer one replaces the previous.
        closeNotification(key, notifications[key] ? notifications[key].kind : "")
        // (a chat waiting for a permission the widget can answer: Allow / Deny buttons)
        const asks = !plain && kind === "waiting" && canAnswerAsk(session)
        // With the pet on, notifications show Talpy in a matching pose.
        const summary = kind === "digest"   // while you were away: someone waits for you, or all went well
        const pose = kind === "done" && session && session.reason === "failed" ? "sad"
                   : summary ? (session ? "oncall" : "trophy")
                   : { waiting: "oncall", overlap: "oncall", done: "trophy", reset: "trophy", started: "trophy", error: "error",
                       limit: "limit", login: "error" }[kind]

        const props = {
            sessionId: session ? session.sessionId : "", profileDir: session ? session.profileDir || "" : "",
            host: host || "", openCommand: session && session.openCommand ? session.openCommand : "",
            session: host && session ? session : null, row: session && session.sessionId !== undefined ? session : null,
            kind: kind, title: title, text: escapeHtml(body.trim()),   // Plasma shows markup in the text
            iconName: Plasmoid.configuration.showPet && pose ? petsDir + "notify-" + pose + ".svg" : icon
        }
        if (asks)
            props.asked = askId(session)   // (what its buttons answer)
        const n = (asks ? askNotificationComponent : notificationComponent).createObject(root, props)
        if (!n)
            return
        if (!plain && !asks && session && session.sessionId && (kind === "done" || kind === "waiting")
                && !(session.permission && kind === "waiting")) {
            // reply in the notification (pane.py --send, as the chat takes one)
            n.replyAction.label = i18n("Reply")
            n.replyAction.placeholderText = i18n("Reply to %1…", session.name)
            n.replyAction.submitButtonText = i18n("Send")
            n.replyAction.submitButtonIconName = "document-send"
            n.replyAction.replied.connect(text => root.replyTo(session, host || "", text))
        }
        notifications[key] = n
        n.sendEvent()
    }

    function closeNotification(key, kind) {
        const n = notifications[key]
        if (!n || n.kind !== kind)
            return
        delete notifications[key]
        n.close()
    }

    function forgetNotification(n) {
        for (const sid in notifications) {
            if (notifications[sid] === n)
                delete notifications[sid]
        }
    }

    // clicked: a chat's notification opens the pane (as a click on its name does)
    function openFromNotification(n, clicked) {
        if (clicked && n.row && Plasmoid.configuration.clickOpensPane) {
            openPane(n.row, n.host, "chat")
            return
        }
        if (!n.sessionId && !n.host) {
            popupTab = "chats"
            root.expanded = true   // nothing waits for you, or what went wrong: show the popup
        }
        else if (n.host && n.session)
            remoteShow(n.host, n.session)
        else if (n.host)
            remoteOpen(n.host, n.openCommand)
        else
            jumpTo(n.sessionId, n.profileDir)
    }

    function toggleAgents(rowKey) {
        const next = Object.assign({}, expandedAgents)
        next[rowKey] = !next[rowKey]
        expandedAgents = next
    }

    function toggleAgentRun(key) {
        expandedAgentRuns = Object.assign({}, expandedAgentRuns, { [key]: !expandedAgentRuns[key] })
    }

    // "12 tool calls · 45.2k tokens" of a subagent, as far as it's known
    function agentNumbers(agent) {
        const parts = []
        if (agent.toolCalls !== null && agent.toolCalls !== undefined)
            parts.push(i18np("%1 tool call", "%1 tool calls", agent.toolCalls))
        if (agent.tokens)
            parts.push(i18n("%1 tokens", formatTokens(agent.tokens)))
        return parts.join(" · ")
    }

    // A subagent's whole run as a Markdown file, opened in your app for those
    // (jump.py --agent-run; remote.py fetches it from an SSH host): Claude
    // Code itself can't open a subagent from outside.
    Exec {
        id: runOpener
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't open the subagent's run: %1", result.message)
                actionErrorTimer.restart()
            }
        }
    }

    function openAgentRun(session, agentId, host) {
        if (host)
            remoteAction("run", host, "--agent-run " + shellQuote(host) + " " + shellQuote(session.chatId) + " "
                                      + shellQuote(agentId) + (session.profileDir ? " " + shellQuote(session.profileDir) : ""))
        else
            runOpener.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --agent-run " + shellQuote(agentId)
                                    + " --chat " + shellQuote(session.chatId) + profileArg(session.profileDir)
                                    + configDirArgs + " # " + Date.now())
    }

    function toggleRecent(groupKey, wasOpen) {
        expandedRecent = Object.assign({}, expandedRecent, { [groupKey]: !wasOpen })
        if (wasOpen) {
            firstPage(groupKey + "|recent")
            if (groupKey in recentMore) {
                const more = Object.assign({}, recentMore)
                delete more[groupKey]
                recentMore = more
            }
        }
    }

    // ---------------------------------------------------------------- lists a page at a time
    // Recent chats, ★ Starred chats and plans, and a project's chats show
    // pageSize at a time (the Recent chats setting), "Show N more" the next
    // page (MoreButton.qml); folded again, a list shows its first page. The
    // status lists a page more recent chats than show (so the next one is
    // there at once) and counts them all (recentCount); past that a check
    // that lists more is run once for the account (fetchRecent).
    readonly property int pageSize: Plasmoid.configuration.recentChats > 0 ? Plasmoid.configuration.recentChats : 5
    readonly property string recentArgs: " --recent " + (Plasmoid.configuration.recentChats > 0 ? 2 * Plasmoid.configuration.recentChats : 0)
                                         + " --plans 0 --memories 0"   // (only the starred plans, and CLAUDE.md: the rest is in the Projects tab)
    property var morePages: ({})    // a list's key -> how many pages past its first show
    property var recentMore: ({})   // group key -> {recent, asked}: its recent chats as a check that listed more has them
    property var recentFetches: ({})   // that check's command -> the group key and account id it's for

    function pagesShown(listKey) {
        return 1 + (morePages[listKey] || 0)
    }
    // (how many pages of it show now)
    function showMore(listKey) {
        morePages = Object.assign({}, morePages, { [listKey]: (morePages[listKey] || 0) + 1 })
        return pagesShown(listKey)
    }
    function firstPage(listKey) {
        if (listKey in morePages) {
            const pages = Object.assign({}, morePages)
            delete pages[listKey]
            morePages = pages
        }
    }
    // A check (this computer's or a host's) that lists count recent chats: for the account's next pages
    function fetchRecent(groupKey, groupId, host, count) {
        const cmd = (host ? hostCommand(host) : command) + " --recent " + count + " --no-tokens --usage-refresh 0"
        if (cmd in recentFetches)
            return
        recentFetches[cmd] = { groupKey: groupKey, groupId: groupId, host: host, count: count }
        recentFetcher.connectSource(cmd)
    }
    Exec {
        id: recentFetcher
        onNewData: (source, data) => {
            disconnectSource(source)
            const asked = root.recentFetches[source]
            delete root.recentFetches[source]
            if (!asked || !root.expandedRecent[asked.groupKey])
                return   // (folded meanwhile: its first page shows)
            let result = null
            if (asked.host) {
                const answer = root.helperResult(data)
                if (answer.ok && answer.result)
                    result = root.toLocalClock(answer.result, Date.now() - (answer.result.generatedAt || Date.now()))
            } else {
                try {
                    result = JSON.parse(data.stdout)
                } catch (e) {
                    result = null
                }
            }
            const g = result && result.groups ? result.groups.find(x => x.id === asked.groupId) : null
            if (g)
                root.recentMore = Object.assign({}, root.recentMore, { [asked.groupKey]: { recent: g.recent || [], asked: asked.count } })
        }
    }

    // New chat: the + next to an account unfolds its folders under its name
    // (NewChatBox.qml), with a field for what Claude should do. A folder
    // starts the chat there (startChat): in a terminal, in VS Code's Claude
    // extension (the switch above them) or, with a task, in the background.
    property string newChatGroup: ""   // group key of the account whose folders are open
    onNewChatGroupChanged: {
        if (newChatFolder && newChatFolder.groupKey !== newChatGroup)
            newChatFolder = null   // (the search's folder was for that box only)
    }
    property bool digestSeen: false
    onExpandedChanged: {
        if (!root.expanded) {
            newChatGroup = ""
            planComposer = ""   // (what you wrote in it stays: root.taskText)
            if (digestSeen)
                awayDigest = null
            digestSeen = false
        } else {
            Qt.callLater(markSeen)
            refresh()  // it may have been checked a while ago (see quiet)
        }
    }

    // The popup stayed open (not just flashed open by the shortcut): what it
    // shows counts as seen, and the icon stops blinking
    function markSeen() {
        if (!root.expanded || shortcutJump)
            return
        unseen = ({})
        digestSeen = awayDigest !== null
    }

    function markUnseen(sid, kind) {
        if (!root.dashboardShown)
            unseen = Object.assign({}, unseen, { [sid]: kind })
    }

    function forgetUnseen(sid, kind) {
        if (sid in unseen && (!kind || unseen[sid] === kind)) {
            const next = Object.assign({}, unseen)
            delete next[sid]
            unseen = next
        }
        if (kind !== "waiting")
            forgetFinished(sid)   // (at work again, gone, or it didn't finish after all)
    }

    // Chats that finished a turn you haven't looked at yet (the focus view's
    // "Finished" lines; the turns that are told as finished): key -> true,
    // until you open that chat (its pane or its window). Unlike unseen,
    // opening the popup leaves them.
    property var finishedUnopened: ({})

    function forgetFinished(key) {
        if (key in finishedUnopened) {
            const next = Object.assign({}, finishedUnopened)
            delete next[key]
            finishedUnopened = next
        }
    }

    function toggleNewChat(groupKey) {
        newChatGroup = newChatGroup === groupKey ? "" : groupKey
        planComposer = ""
    }

    // Here: your recent folders, then any folder you pick in the folder dialog
    // (it opens in your home folder). An SSH host's folders can't be browsed
    // from here, so its home folder stays in the list. A plan's own folder
    // (where the chat that made it ran) comes first.
    function newChatFolders(group, host, plan) {
        let folders = host ? group.projects.slice() : group.projects.filter(f => f.short !== "~")
        if (host && !folders.some(f => f.short === "~"))
            folders.push({ path: "", short: "~", newChatCommand: group.homeChatCommand || "", trusted: false })
        // a project folder the search found comes first (openFoundProject)
        const found = !plan && newChatFolder && newChatFolder.groupKey === (host ? host + "/" : "") + group.id ? newChatFolder : null
        if (found)
            folders = [folders.find(f => f.path === found.path) || found].concat(folders.filter(f => f.path !== found.path))
        if (plan && plan.cwd) {
            const own = folders.find(f => f.path === plan.cwd)
            folders = [own || { path: plan.cwd, short: plan.cwdShort || plan.cwd, newChatCommand: "" }]
                .concat(folders.filter(f => f.path !== plan.cwd))
        }
        return folders
    }

    // Chats open in a terminal or in VS Code (OpenInSwitch.qml): one choice,
    // newChatInVscode, for new and recent chats.
    // VS Code's Claude extension runs on the account its own environment and
    // settings say (talpy_den.py: vscode_profile), so its button is only
    // on that account (an SSH host's: the host's ~/.claude)
    readonly property bool vscodeInstalled: status !== null && !!status.vscode && status.vscode.installed === true

    // There's a claude command here (host: on that SSH host). When unsure
    // (no answer yet, or an error looking), it counts as there.
    function cliHere(host) {
        const result = host ? (remote[host] || {}).result : status
        return !result || !result.cli || result.cli.installed !== false
    }

    // Where this account's chats open: VS Code when you picked it, or when
    // there's no claude command but VS Code's Claude runs on this account
    // (resuming: a recent chat, which reopens on its own account)
    function openInVscode(group, host, resuming) {
        if (!vscodeInstalled || !(group.vscodeHere || (!resuming && vscodeSwitches(group, host))))
            return false
        return Plasmoid.configuration.newChatInVscode || !cliHere(host)
    }

    // A new chat on an SSH host's other account opens in VS Code too: VS
    // Code's Claude there switches to that account first, and stays on it
    // (jump.py --remote-new-vscode --account; configDir comes from the host)
    function vscodeSwitches(group, host) {
        return !!host && vscodeInstalled && !group.vscodeHere && group.configDir !== undefined
    }

    // resuming: for the recent chats' switch (they reopen) instead of new chats'
    function terminalHint(host, resuming) {
        if (!cliHere(host))
            return isContainer(host) ? i18n("Claude Code's claude command isn't installed in %1: it isn't on PATH there, in ~/.local/bin, npm's or nvm's folders, nor on the login shell's PATH.", hostLabel(host))
                 : host ? i18n("Claude Code's claude command isn't installed on %1: it isn't on PATH there, in ~/.local/bin, npm's or nvm's folders, nor on the login shell's PATH.", host)
                        : i18n("Claude Code's claude command isn't installed here: it isn't on PATH, in ~/.local/bin, npm's or nvm's folders, nor on your login shell's PATH.")
        if (resuming)
            return isContainer(host) ? i18n("Reopens the chat in %1 in a terminal (claude --resume, in the container).", hostLabel(host))
                 : host ? i18n("Reopens the chat on %1 in a terminal (ssh, claude --resume).", host)
                        : i18n("Reopens the chat in a terminal (claude --resume).")
        return isContainer(host) ? i18n("A terminal opens with Claude in %1 in the folder you click.", hostLabel(host))
             : host ? i18n("A terminal opens with Claude on %1 (ssh) in the folder you click.", host)
                    : i18n("A terminal opens with Claude in the folder you click.")
    }

    function vscodeHint(group, host, resuming) {
        const how = isContainer(host) ? i18nc("how VS Code connects to a container", "Dev Containers") : "Remote-SSH"
        const name = hostLabel(host)
        if (!vscodeInstalled)
            return host ? i18n("VS Code would connect to %1 (%2), but it isn't installed on this computer.", name, how)
                        : i18n("VS Code isn't installed on this computer.")
        if (group.vscodeHere && resuming)
            return host ? i18n("Opens VS Code connected to %1 (%2) in the chat's folder, and the chat in its Claude Code panel.", name, how)
                        : i18n("Opens the chat's folder in VS Code, and the chat in its Claude Code panel.")
        if (group.vscodeHere)
            return host ? i18n("Opens VS Code connected to %1 (%2) with a new chat in its Claude Code panel.", name, how)
                        : i18n("Opens the folder in VS Code with a new chat in its Claude Code panel.")
        if (host && !resuming && vscodeSwitches(group, host))
            return i18n("Opens VS Code connected to %1 (%3) with a new chat in its Claude Code panel. VS Code's Claude there switches to %2 for it, and stays on it.", name, group.title, how)
        if (host)
            return i18n("VS Code's Claude on %1 runs on another account: a new chat in VS Code on this one switches it.", name)
        const on = status && status.vscode ? status.vscode.on : null
        return on ? i18n("VS Code's Claude runs on %1, not %2: switch its profile to use this account there.", on, group.title)
                  : i18n("VS Code's Claude doesn't run on this account.")
    }

    Exec {
        id: launcher
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            root.draftBack(source, result.ok)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't open a new chat: %1", result.message)
                actionErrorTimer.restart()
            }
            const host = root.launcherHosts[source]
            if (host) {
                const rest = Object.assign({}, root.launcherHosts)
                delete rest[source]
                root.launcherHosts = rest
                root.pollHost(host)
            }
        }
    }

    // A reply to a chat in a Claude Code panel (pane.py --send's link): in the
    // VS Code window that runs the chat, raised first (jump.py --vscode-link);
    // an SSH host's opens as the link says
    function openVscodeLink(sessionId, link, host) {
        if (host || !sessionId)
            Qt.openUrlExternally(link)
        else
            jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --vscode-link " + shellQuote(sessionId)
                                 + " " + shellQuote(link) + configDirArgs + " # " + Date.now())
    }

    // A recent chat, reopened in VS Code's Claude extension (in its folder)
    function resumeInVscode(sessionId, profileDir) {
        jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --resume " + shellQuote(sessionId)
                             + profileArg(profileDir) + " --vscode" + configDirArgs + " # " + Date.now())
    }

    // A recent chat of an SSH host, reopened in VS Code connected to it
    function remoteResumeVscode(host, sessionId, folder) {
        jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --remote-resume-vscode " + shellQuote(host)
                             + " " + shellQuote(sessionId) + (folder ? " --cwd " + shellQuote(folder) : "") + " # " + Date.now())
    }

    // A new chat in a terminal on an SSH host (a folder's newChatCommand).
    // The list closes here, not in the folder's row: closing it destroys
    // the row, and the rest of the row's click handler lost root with it.
    function remoteNewChat(host, command) {
        newChatGroup = ""
        remoteOpen(host, command)
    }

    // VS Code connected to an SSH host, with a new chat (in folder there, or home)
    // group: the account the chat is for, when it isn't VS Code's there yet
    // text, plan: a task to type in there (its plan comes from the host)
    function remoteNewChatVscode(host, folder, group, text, plan) {
        newChatGroup = ""
        const account = group && !group.vscodeHere ? " --account " + shellQuote(group.configDir || "-") : ""
        const line = "python3 -I " + shellQuote(codeDir + "jump.py") + " --remote-new-vscode " + shellQuote(host)
                     + (folder ? " --cwd " + shellQuote(folder) : "") + account
                     + (text ? " --prompt " + shellQuote(text) : "")
                     + (plan ? " --plan " + shellQuote(plan.slug) + " --plan-profile " + shellQuote(plan.profileDir) : "")
                     + " # " + Date.now()
        launcherHosts = Object.assign({}, launcherHosts, { [line]: host })
        launcher.connectSource(line)
        return line
    }

    property var launcherHosts: ({})   // command -> SSH host it was for (checked again after: its accounts may have switched)

    // Claude's own login for an account that isn't logged in, in a terminal
    // (accounts.py --login; an SSH host's account: its loginCommand over ssh)
    function logIn(group, host) {
        if (host) {
            remoteOpen(host, group.loginCommand)
            return
        }
        loginRunner.connectSource("python3 -I " + shellQuote(codeDir + "accounts.py") + " --login " + shellQuote(group.chatProfile)
                                  + configDirArgs + " # " + Date.now())
    }

    Exec {
        id: loginRunner
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't log in: %1", result.message)
                actionErrorTimer.restart()
            }
        }
    }

    // ---------------------------------------------------------------- SSH hosts

    // ~/.ssh/config's hosts and this computer's containers (loaded at start,
    // whenever the menu opens, and on Reload), with the SSH hosts'
    // container lists as they were last fetched (shown until they're fetched again)
    Exec {
        id: hostLister
        onNewData: (source, data) => {
            disconnectSource(source)
            root.hostsReloadAnswered(source)
            const result = root.helperResult(data)
            if (!result.ok) {
                root.refreshHostsMenu()   // (Reloading… may go back to Reload)
                return
            }
            root.sshHosts = result.hosts || []
            root.containersHere = result.containers || []
            root.containerNotes = result.notes || []
            const kept = result.hostContainers || {}
            const next = Object.assign({}, root.hostContainers)
            for (const host in kept)
                if (!(host in next))
                    next[host] = kept[host]
            root.hostContainers = next
            root.refreshHostsMenu()
        }
    }

    // --container-days, --picked: the containers listed (the picked ones always), or no containers at all
    function containerArgs() {
        if (!showContainers)
            return " --no-containers"
        const picked = pickedHosts.filter(isContainer)
        return " --container-days " + Math.max(0, Plasmoid.configuration.containerDays)
               + (picked.length ? " --picked " + shellQuote(picked.join(",")) : "")
    }

    function loadHosts() {
        const cmd = "python3 -I " + shellQuote(codeDir + "remote.py") + " --hosts" + containerArgs() + " # " + Date.now()
        hostLister.connectSource(cmd)
        return cmd
    }

    // An SSH host's containers (remote.py --containers there): fetched once
    // it's connected (its first check that works after start, after failing,
    // or after you logged in) and on Reload, never on a timer
    Exec {
        id: containerLister
        onNewData: (source, data) => {
            disconnectSource(source)
            const host = root.containerListHosts[source]
            delete root.containerListHosts[source]
            root.hostsReloadAnswered(source)
            if (!host) {
                root.refreshHostsMenu()
                return
            }
            const result = root.helperResult(data)
            root.hostContainers = Object.assign({}, root.hostContainers, {
                [host]: result.ok ? { containers: result.containers || [], notes: result.notes || [], at: result.at || Date.now() }
                                  : Object.assign({}, root.hostContainers[host] || {}, { error: result.error || result.message || "" })
            })
            root.refreshHostsMenu()
        }
    }
    property var containerListHosts: ({})   // command -> its host

    function loadHostContainers(host) {
        if (!showContainers || isContainer(host))
            return ""
        const cmd = "python3 -I " + shellQuote(codeDir + "remote.py") + " --containers " + shellQuote(host)
                    + containerArgs() + " # " + Date.now()
        containerListHosts[cmd] = host
        containerLister.connectSource(cmd)
        return cmd
    }

    // The SSH hosts shown whose last check worked: their containers are in the picker
    function connectedHosts() {
        return shownHosts.filter(h => !isContainer(h) && remote[h] && remote[h].ok)
    }

    // Reload in the picker: ~/.ssh/config, this computer's containers and every connected host's
    function reloadHosts() {
        const waits = { [loadHosts()]: true }
        for (const host of connectedHosts()) {
            const cmd = loadHostContainers(host)
            if (cmd)
                waits[cmd] = true
        }
        return waits
    }

    // Reload, from the picker: a menu closes on any click, so it opens again
    // where it was (as VS Code's stays open), and says Reloading… until every
    // list it asked for has answered (or a minute and a half went by: an
    // answer plasmashell lost isn't waited for)
    property var hostsReloadWaits: ({})   // command -> true
    property bool hostsReloading: false

    function reloadHostsMenu() {
        hostsReloadWaits = reloadHosts()
        hostsReloading = true
        hostsReloadTimer.restart()
        Qt.callLater(reopenHostsMenu)   // (after the menu has closed: Qt closes it before the click's handlers run)
    }

    function reopenHostsMenu() {
        if (!dashboardShown || !hostsMenu.visualParent || !hostsMenu.visualParent.visible)
            return   // (the dashboard closed meanwhile)
        hostsMenuShown = ""
        fillHostsMenu()
        hostsMenu.openRelative()
    }

    // (each answer refills the open menu itself, after this)
    function hostsReloadAnswered(source) {
        if (!hostsReloading || !(source in hostsReloadWaits))
            return
        delete hostsReloadWaits[source]
        if (Object.keys(hostsReloadWaits).length === 0)
            hostsReloadDone()
    }

    function hostsReloadDone() {
        hostsReloadTimer.stop()
        hostsReloadWaits = ({})
        hostsReloading = false
    }

    Timer {
        id: hostsReloadTimer
        interval: 90000
        onTriggered: {
            root.hostsReloadDone()
            root.refreshHostsMenu()
        }
    }

    property bool hostsReady: false   // (Component.onCompleted ran: the setting changing at start isn't a change)

    onShowContainersChanged: {
        if (!hostsReady)
            return
        if (showContainers) {
            reloadHosts()
        } else {
            containersHere = []
            containerNotes = []
            hostContainers = ({})
        }
    }

    // Each host's and container's last answer (remote.py --last, kept from
    // its last check): shown at once, dimmed with how old it is, until its
    // first check here answers
    Exec {
        id: lastLoader
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            for (const host in (result.ok ? result.last || {} : {})) {
                const kept = result.last[host]
                const info = root.remote[host]
                if (!kept.answer || !kept.answer.result || (info && (info.ok || info.result || info.error)))
                    continue   // (it answered meanwhile)
                root.setRemote(host, { result: root.toLocalClock(kept.answer.result, kept.offset || 0), updatedAt: kept.at || 0,
                                       cached: true })
            }
        }
    }

    function loadLastAnswers() {
        if (shownHosts.length)
            lastLoader.connectSource("python3 -I " + shellQuote(codeDir + "remote.py") + " --last "
                                     + shownHosts.map(shellQuote).join(" ") + " # " + Date.now())
    }

    Component.onCompleted: {
        loadLastAnswers()
        loadHosts()
        Hub.want(instanceId, "status", command, checkInterval, true)
        Hub.placed(instanceId, !shownInPlace)
        Hub.wantLive(instanceId, liveCommand)
        wantHosts()
        hostsReady = true
    }

    // Status of the hosts you picked: polled less often than this computer,
    // once for all copies (hub/Hub.qml; a host just picked is checked at once)
    property var wantedHosts: ({})   // host -> its check's command
    readonly property string hostWish: JSON.stringify([shownHosts, Plasmoid.configuration.remotePollSeconds,
        Plasmoid.configuration.keepDoneHours, Plasmoid.configuration.recentChats, Plasmoid.configuration.showTokens,
        Plasmoid.configuration.usageRefreshMinutes])
    onHostWishChanged: wantHosts()

    // (a container that's stopped, or isn't there any more, isn't checked
    // until you press Start or Refresh: a day is as good as never)
    function wantHosts() {
        const next = {}
        const interval = Math.max(10, Plasmoid.configuration.remotePollSeconds) * 1000
        for (const host of shownHosts) {
            next[host] = hostCommand(host)
            const idle = remote[host] && (remote[host].stopped || remote[host].gone)
            Hub.want(instanceId, "ssh:" + host, next[host], idle ? 86400000 : interval, false)
        }
        for (const host in wantedHosts)
            if (!(host in next))
                Hub.unwant(instanceId, "ssh:" + host)
        wantedHosts = next
    }

    function hostOfCommand(command) {
        for (const host in wantedHosts)
            if (wantedHosts[host] === command)
                return host
        return ""
    }

    onShownHostsChanged: {
        const next = {}
        for (const host of shownHosts)
            if (host in remote)
                next[host] = remote[host]
        for (const host in remote)
            if (!(host in next))
                forgetSource("ssh:" + host)  // shown again later, it starts afresh
        remote = next
        if (searchOpen && shownHosts.some(host => !(host in searchResults)))
            runSearch()   // (a host shown while you search is searched too)
    }

    // What a source's chats were (and their notifications): gone with the source
    function forgetSource(source) {
        const prefix = source + "|"
        for (const key in notifications)
            if (key.startsWith(prefix))
                closeNotification(key, notifications[key].kind)
        for (const key in unseen)
            if (key.startsWith(prefix))
                forgetUnseen(key, "")
        for (const key in lastWaitingAlert)
            if (key.startsWith(prefix))
                delete lastWaitingAlert[key]
        const drop = map => { const out = Object.assign({}, map); delete out[source]; return out }
        lastStates = drop(lastStates)
        turnStarts = drop(turnStarts)
        lastEnded = drop(lastEnded)
        primedSources = drop(primedSources)
        // (else a limit that reset, or files two chats changed, while it was hidden is news once it's back)
        lastStops = drop(lastStops)
        lastOverlaps = drop(lastOverlaps)
        const windows = Object.assign({}, lastWindows)
        for (const key in windows)
            if (key.startsWith(prefix))
                delete windows[key]
        lastWindows = windows
    }

    // A host's answer on this computer's clock: its times ("since", "last
    // active", resets) are its own clock's, which may be off from ours
    function toLocalClock(result, offset) {
        if (Math.abs(offset) < 5000)
            return result   // network delay, or close enough
        const at = t => typeof t === "number" ? t + offset : t
        const shift = (o, keys) => { if (o) for (const k of keys) o[k] = at(o[k]) }
        result = JSON.parse(JSON.stringify(result))
        result.generatedAt = at(result.generatedAt)
        for (const g of result.groups || []) {
            for (const s of g.sessions || []) {
                shift(s, ["since", "startedAt"])
                shift(s.peek, ["at"])
                shift(s.peek && s.peek.recap, ["at"])
                shift(s.stopped, ["at", "resetsAt"])
                shift(s.movedFrom, ["at"])
                shift(s.plan, ["updatedAt"])
                shift(s.stats, ["startedAt", "lastAt"])
                for (const a of (s.agents && s.agents.tree) || [])
                    shift(a, ["started", "updated"])
            }
            for (const c of (g.recent || []).concat(g.sharedHere || [], g.starred || [])) {
                shift(c, ["lastActive", "since"])
                shift(c.recap, ["at"])
                shift(c.stopped, ["at", "resetsAt"])
            }
            for (const plan of (g.plans || []).concat(g.starredPlans || []))
                shift(plan, ["updatedAt"])
            for (const memory of g.memories || [])
                shift(memory, ["updatedAt"])
            if (g.limits) {
                shift(g.limits, ["updatedAt"])
                for (const w of g.limits.windows || []) {
                    shift(w, ["resetsAt"])
                    shift(w.forecast, ["fullAt"])
                }
            }
        }
        return result
    }

    function hostCommand(host) {
        let cmd = "python3 -I " + shellQuote(codeDir + "remote.py") + " --status " + shellQuote(host)
                  + " --done-hours " + Math.max(0, Plasmoid.configuration.keepDoneHours) + recentArgs
        if (!Plasmoid.configuration.showTokens)
            cmd += " --no-tokens"
        cmd += " --usage-refresh " + Math.max(0, Math.round(Plasmoid.configuration.usageRefreshMinutes))
        return cmd
    }

    function pollHost(host) {
        Hub.refresh(hostCommand(host))   // (one still running is run again once it's done)
    }

    function setRemote(host, patch) {
        if (shownHosts.indexOf(host) < 0)
            return  // unpicked meanwhile
        const old = remote[host] || { loading: false, ok: false, error: "", result: null, updatedAt: 0 }
        remote = Object.assign({}, remote, { [host]: Object.assign({}, old, patch) })
    }

    function handleRemote(host, data) {
        if (shownHosts.indexOf(host) < 0)
            return  // unticked while its check was running
        const answer = helperResult(data)
        const was = remote[host] || {}
        if (answer.ok && answer.result && !was.ok && !isContainer(host))
            loadHostContainers(host)   // (it's connected: its containers go in the picker)
        if (!!answer.stopped !== !!was.stopped || !!answer.gone !== !!was.gone)
            Qt.callLater(wantHosts)   // (a stopped container isn't checked until Start or Refresh)
        if (answer.ok && answer.result) {
            const offset = Date.now() - (answer.result.generatedAt || Date.now())
            const result = toLocalClock(answer.result, offset)
            trackTransitions("ssh:" + host, result.groups, result.generatedAt, host)
            trackLimitStops("ssh:" + host, result.groups, host)
            trackOverlaps("ssh:" + host, result.groups, host)
            celebrateResets("ssh:" + host, result.groups)
            // clockOffset: what its times were moved by (0: not moved), for
            // the ones left on its clock (reviewPending)
            setRemote(host, { loading: false, ok: true, error: "", result: result, updatedAt: Date.now(),
                              login: false, loggedIn: !!answer.loggedIn, clockOffset: result === answer.result ? 0 : offset,
                              stopped: false, gone: false, paused: false, cached: false })
            if (status)
                startDueTasks(status.queue || [])   // (a reply waiting for the end of a turn there: it ended)
        } else {
            // keep the last answer to show (dimmed) with the error
            setRemote(host, { loading: false, ok: false, error: answer.error || answer.message || i18n("no answer"),
                              login: !!answer.login, loggedIn: false, stopped: !!answer.stopped, gone: !!answer.gone,
                              paused: !!answer.paused, cached: false })
        }
    }

    // A host that wants a password (or a passphrase, a code, its host key
    // confirmed): remote.py --login opens a terminal where ssh asks for it,
    // so it goes to ssh only. The checks then share that connection (until
    // 30 minutes after their last use, logging out, or Disconnect). Until
    // you're in, the host is checked every few seconds.
    function loginHost(host) {
        remoteAction("login", host, "--login " + shellQuote(host))
        loginWaits = Object.assign({}, loginWaits, { [host]: Date.now() + 180000 })
    }

    function disconnectHost(host) {
        remoteAction("disconnect", host, "--disconnect " + shellQuote(host))
    }

    // A stopped container started (remote.py --start); it's checked once that's done
    function startContainer(host) {
        setRemote(host, { loading: true })
        remoteAction("start", host, "--start " + shellQuote(host))
    }

    property var loginWaits: ({})   // host -> until when it's checked often

    Timer {
        interval: 3000
        repeat: true
        running: Object.keys(root.loginWaits).length > 0
        onTriggered: {
            const next = {}
            for (const host in root.loginWaits) {
                const info = root.remote[host]
                if ((info && info.ok) || Date.now() > root.loginWaits[host] || root.shownHosts.indexOf(host) < 0)
                    continue
                next[host] = root.loginWaits[host]
                root.pollHost(host)
            }
            root.loginWaits = next
        }
    }

    // Kept chats and queued tasks of SSH hosts and containers that aren't
    // shown (not picked, or containers while Show containers is off): they go
    // on all the same, from here over ssh, so the list says so where the
    // hosts go (UnseenLine.qml): [{host, name, kept, task}], a kept chat with
    // its queued go-on
    readonly property var unseenHostItems: {
        const shown = shownHosts, out = []
        const queue = (status && status.queue) || []
        for (const k of (status && status.keep) || []) {
            if (!k.host || shown.indexOf(k.host) >= 0)
                continue
            out.push({ host: k.host, name: k.name || k.chat.slice(0, 8), kept: k,
                       task: queue.find(t => t.chat === k.chat && (t.host || "") === k.host && !t.afterTurn) || null })
        }
        for (const t of queue)
            if (t.host && shown.indexOf(t.host) < 0 && !out.some(x => x.task === t))
                out.push({ host: t.host, name: t.chat ? (t.name || t.chat.slice(0, 8)) : "", kept: null, task: t })
        return out
    }

    // An SSH host or a container joins the list (picked; a container also turns Show containers on)
    function showHost(host) {
        if (pickedHosts.indexOf(host) < 0)
            toggleHost(host)
        if (isContainer(host) && !showContainers)
            Plasmoid.configuration.showContainers = true
    }

    function toggleHost(host) {
        const list = pickedHosts.slice()
        const i = list.indexOf(host)
        if (i >= 0)
            list.splice(i, 1)
        else
            list.push(host)
        Plasmoid.configuration.sshHosts = list.join(",")
    }

    PlasmaExtras.Menu {
        id: hostsMenu
    }

    Component {
        id: hostItem
        PlasmaExtras.MenuItem {
            property string host
            property bool reload: false
            onClicked: reload ? root.reloadHostsMenu() : root.toggleHost(host)
        }
    }

    property var hostItems: []

    // The widget's menu, from a right-click on the dashboard on the desktop
    // (MenuCatcher.qml): the panel icon's actions and Configure Talpy Den….
    // (Plasma's own can't be had from here: the desktop's openContextMenu
    // looks for a widget at its own top left corner, not under the pointer,
    // and opens the desktop's menu.)
    function openWidgetMenu(item, x, y) {
        widgetMenu.clearMenuItems()
        const items = []
        for (const action of Plasmoid.contextualActions)
            if (action.visible)
                items.push(widgetMenuItem.createObject(widgetMenu, action.isSeparator ? { separator: true, section: action.text !== "",
                                                                                          text: action.text }
                                                                                        : { action: action }))
        items.push(widgetMenuItem.createObject(widgetMenu, { separator: true }))
        items.push(widgetMenuItem.createObject(widgetMenu, { action: Plasmoid.internalAction("configure") }))
        for (const menuItem of items)
            widgetMenu.addMenuItem(menuItem)
        widgetMenuItems = items
        widgetMenu.visualParent = item
        widgetMenu.open(x, y)
    }
    property var widgetMenuItems: []
    PlasmaExtras.Menu {
        id: widgetMenu
    }
    Component {
        id: widgetMenuItem
        PlasmaExtras.MenuItem {}
    }

    // The hosts picker: ~/.ssh/config's hosts, this computer's containers
    // and each connected SSH host's (running ones, and those active in the
    // last containerDays days; a picked one always, so it can be unpicked).
    // It shows the last lists at once; this computer's is read again as it
    // opens (fast), and the menu takes the new list if it's still open.
    function openHostsMenu(button) {
        loadHosts()
        hostsMenuShown = ""
        fillHostsMenu()
        hostsMenu.visualParent = button
        hostsMenu.openRelative()
    }

    property string hostsMenuShown: ""   // what the open menu lists (JSON), to refill it only on a change

    function refreshHostsMenu() {
        if (hostsMenu.status === PlasmaExtras.Menu.Open || hostsMenu.status === PlasmaExtras.Menu.Opening)
            fillHostsMenu()
    }

    // "podman · ubuntu:22.04 · stopped 3 days ago" for a container's line in the picker
    function containerLine(c) {
        const parts = [c.folderShort ? c.folderShort : c.engine + (c.image ? " · " + c.image : "")]
        if (!c.running)
            parts.push(containerStopped(c))
        if (c.sharesHome)
            parts.push(i18n("shares your home folder"))
        return c.name + "  (" + parts.join(" · ") + ")"
    }

    // "stopped 3 days ago", "stopped 5h 10m ago", "stopped"
    function containerStopped(c) {
        const age = c && c.activeAt ? Math.max(0, now - c.activeAt) : -1
        return age < 0 ? i18n("stopped") : age >= 2 * 86400000 ? i18np("stopped %1 day ago", "stopped %1 days ago", Math.floor(age / 86400000))
             : i18n("stopped %1 ago", duration(age))
    }

    function hostsMenuModel() {
        const items = [{ section: true, text: i18n("SSH hosts") }]
        for (const h of sshHosts) {
            const target = (h.user ? h.user + "@" : "") + (h.hostname || h.name) + (h.jump ? " " + i18nc("ssh through a jump host", "via %1", h.jump) : "")
            items.push({ text: target !== h.name ? h.name + "  (" + target + ")" : h.name, icon: Icons.plasma.host,
                         checkable: true, checked: pickedHosts.indexOf(h.name) >= 0, host: h.name })
        }
        // picked hosts that aren't in ~/.ssh/config (any more)
        for (const host of pickedHosts)
            if (!isContainer(host) && !sshHosts.some(h => h.name === host))
                items.push({ text: host, icon: Icons.plasma.host, checkable: true, checked: true, host: host })
        if (items.length === 1)
            items.push({ text: i18n("No hosts in ~/.ssh/config"), enabled: false })
        if (showContainers) {
            const days = Math.max(0, Plasmoid.configuration.containerDays)
            const none = days > 0 ? i18np("No containers active in the last day", "No containers active in the last %1 days", days)
                                  : i18n("No running containers")
            const places = [{ host: "", title: i18n("Containers on this computer"), list: containersHere, notes: containerNotes }]
            // (the connected hosts', and a host's whose container you picked)
            const connected = connectedHosts()
            const hosts = connected.concat(pickedHosts.map(id => (containerOf(id) || {}).host || "")
                                                      .filter((h, i, all) => h && all.indexOf(h) === i && connected.indexOf(h) < 0))
            for (const host of hosts) {
                const kept = connected.indexOf(host) >= 0 ? hostContainers[host] || {} : {}
                places.push({ host: host, title: i18n("Containers on %1", host), list: kept.containers || [],
                              notes: (kept.notes || []).concat(kept.error ? [{ message: kept.error }] : []) })
            }
            for (const place of places) {
                items.push({ section: true, text: place.title })
                const listed = place.list.filter(c => c && c.id)
                for (const c of listed)
                    items.push({ text: containerLine(c), icon: iconDir + Icons.plasma.container, checkable: true,
                                 checked: pickedHosts.indexOf(c.id) >= 0, host: c.id })
                // picked ones not listed (gone, or not listed yet)
                for (const id of pickedHosts)
                    if ((containerOf(id) || { host: null }).host === place.host && !listed.some(c => c.id === id))
                        items.push({ text: containerOf(id).name, icon: iconDir + Icons.plasma.container, checkable: true,
                                     checked: true, host: id })
                for (const note of place.notes)
                    items.push({ text: note.message, enabled: false })
                if (!listed.length && !place.notes.length && !pickedHosts.some(id => (containerOf(id) || { host: null }).host === place.host))
                    items.push({ text: none, enabled: false })
            }
        }
        items.push({ separator: true })
        items.push(hostsReloading ? { text: i18n("Reloading…"), icon: Icons.plasma.refresh, enabled: false }
                                  : { text: i18n("Reload"), icon: Icons.plasma.refresh, reload: true })
        return items
    }

    // An open menu is changed in place where it can be: Plasma makes the
    // section headers only as a menu opens (openRelative rebuilds it), so
    // items made while it was open showed their headers as plain lines, and
    // the old headers stayed at the top (clearMenuItems leaves them). Its
    // lines changed (one more container, a host gone): it's made anew and
    // Plasma rebuilds it where it is.
    readonly property var hostItemDefaults: ({ text: "", icon: "", checkable: false, checked: false, enabled: true,
                                               host: "", reload: false })
    property string hostsMenuShape: ""   // its headers and lines, without what changes in place

    function hostsMenuShapeOf(model) {
        return JSON.stringify(model.map(spec => spec.section ? "S:" + spec.text : spec.separator ? "-" : "I"))
    }

    function fillHostsMenu() {
        const model = hostsMenuModel()
        const shown = JSON.stringify(model)
        if (shown === hostsMenuShown)
            return
        hostsMenuShown = shown
        const open = hostsMenu.status === PlasmaExtras.Menu.Open || hostsMenu.status === PlasmaExtras.Menu.Opening
        const shape = hostsMenuShapeOf(model)
        if (open && shape === hostsMenuShape && hostItems.length === model.length) {
            model.forEach((spec, i) => {
                if (!spec.section && !spec.separator)
                    Object.assign(hostItems[i], hostItemDefaults, spec)
            })
            return
        }
        hostsMenuShape = shape
        hostsMenu.clearMenuItems()   // (it deletes the old items itself: destroying them again threw, and the menu stayed empty)
        const items = model.map(spec => hostItem.createObject(hostsMenu, spec))
        for (const item of items)
            hostsMenu.addMenuItem(item)
        hostItems = items
        if (open)
            hostsMenu.openRelative()   // (its headers made anew, the old ones gone)
    }

    // Actions on an SSH host: open a session in a local terminal (ssh -t),
    // stop a background session, hide a finished one
    Exec {
        id: remoteActions
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            root.draftBack(source, result.ok)
            const what = root.remoteActionKinds[source] || ""
            const host = root.remoteActionHosts[source]
            delete root.remoteActionKinds[source]   // (each command is new: these would only grow)
            delete root.remoteActionHosts[source]
            if (result.ok) {
                root.actionError = ""
                if (what === "open" || what === "run" || what === "continue" || what === "login" || what === "plan")
                    root.expanded = false
                else if (what === "share" || what === "task") {
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                }
            } else {
                root.actionError = what === "open" ? i18n("Couldn't open the chat: %1", result.message)
                                 : what === "stop" ? i18n("Couldn't stop the chat: %1", result.message)
                                 : what === "run" ? i18n("Couldn't open the subagent's run: %1", result.message)
                                 : what === "plan" ? i18n("Couldn't open the plan: %1", result.message)
                                 : what === "task" ? i18n("Couldn't start it: %1", result.message)
                                 : result.message
                actionErrorTimer.restart()
                root.petEvent("oops", i18n("Hmm, that didn't work."), "")
                if (!root.dashboardShown)   // e.g. from a notification or the shortcut: say so
                    root.notify("remote-error", null, "error", i18n("That didn't work on %1", host ? hostLabel(host) : i18n("the host")),
                                root.actionError, "dialog-error")
            }
            if (what !== "open" && what !== "run" && what !== "plan" && host)
                root.pollHost(host)
        }
    }

    property var remoteActionKinds: ({})
    property var remoteActionHosts: ({})

    function remoteAction(kind, host, args) {
        const cmd = "python3 -I " + shellQuote(codeDir + "remote.py") + " " + args + " # " + Date.now()
        remoteActionKinds = Object.assign({}, remoteActionKinds, { [cmd]: kind })
        remoteActionHosts = Object.assign({}, remoteActionHosts, { [cmd]: host })
        remoteActions.connectSource(cmd)
        return cmd
    }

    // Bring up a session of an SSH host: background sessions and finished chats
    // open in a terminal (ssh); one running there shows where it runs here (its
    // VS Code window, the terminal of one, or the terminal tab with the ssh connection)
    function remoteShow(host, session) {
        forgetFinished(petKeyOf(session, host))
        const cwd = session.cwd ? " --cwd " + shellQuote(session.cwd) : ""
        if (session.openCommand)
            remoteOpen(host, session.openCommand)
        else if (session.entrypoint === "claude-vscode")
            jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --remote-vscode " + shellQuote(host)
                                 + " " + shellQuote(session.sessionId) + cwd + " # " + Date.now())
        else
            jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --remote-terminal " + shellQuote(host)
                                 + " --name " + shellQuote(session.name || "")
                                 + (session.vscodeTerminal ? " --vscode-terminal " + Math.trunc(session.vscodeTerminal) + cwd : "")
                                 + " # " + Date.now())
    }

    function remoteOpen(host, command) {
        if (!command) {
            actionError = i18n("This chat runs in a terminal on %1; Talpy Den can't bring it here.", hostLabel(host))
            actionErrorTimer.restart()
            return
        }
        remoteAction("open", host, "--open " + shellQuote(host) + " " + shellQuote(command))
    }

    function remoteStop(host, command) {
        remoteAction("stop", host, "--run " + shellQuote(host) + " " + shellQuote(command))
    }

    // A chat with a process on the host (talpy_den.py --end there; busy:
    // you were told it's working or waiting), or one in tmux interrupted
    // keepOffChat: a chat that keeps going, to turn Keep going off for once it's stopped
    function remoteEnd(host, sessionId, profileDir, busy, keepOffChat) {
        remoteAction("stop", host, "--end " + shellQuote(host) + " " + shellQuote(sessionId)
                                   + (profileDir ? " " + shellQuote(profileDir) : "") + (busy ? " --busy" : "")
                                   + (keepOffChat ? " --keep-off " + shellQuote(keepOffChat) : ""))
    }

    function remoteInterrupt(host, sessionId, profileDir) {
        remoteAction("stop", host, "--interrupt " + shellQuote(host) + " " + shellQuote(sessionId)
                                   + (profileDir ? " " + shellQuote(profileDir) : ""))
    }

    // ---------------------------------------------------------------- shared chats
    // Share a chat with your other accounts, continue it on one of them, or
    // keep it on one only: jump.py does it (sharing.py); on an SSH host,
    // between that host's accounts, remote.py does it there.

    // The accounts a chat of this computer (host "") or of an SSH host can go to
    function shareAccountsOf(host) {
        const result = host ? (remote[host] || {}).result : status
        return result && result.canShare === true ? result.groups.filter(g => !!g.shareProfile) : []
    }

    function shareHint(host) {
        return isContainer(host) ? i18n("Share this chat with your other accounts in %1 and pick it up there (in a terminal), or keep it on one account only.", hostLabel(host))
             : host ? i18n("Share this chat with your other accounts on %1 and pick it up there (in a terminal, over ssh), or keep it on one account only.", host)
                    : i18n("Share this chat with your other accounts and pick it up there, or keep it on one account only.")
    }

    readonly property var noShareConfirm: ({ key: "", chatId: "", name: "", profileKey: "", account: "", others: "", host: "" })
    // "Keep only on …" waits for a yes: {key, chatId, name, profileKey, account, others, host}
    property var shareConfirm: noShareConfirm

    PlasmaExtras.Menu {
        id: shareMenu
    }

    Component {
        id: shareItem
        PlasmaExtras.MenuItem {
            property string kind      // continue | share | keeponly
            property string chatId
            property string chatName
            property string rowKey
            property string host
            property var account: null
            onClicked: {
                if (kind === "keeponly")
                    root.askKeepOnly(rowKey, chatId, chatName, account, host)
                else
                    root.shareAction(kind, chatId, account ? account.shareProfile : "", host)
            }
        }
    }

    property var shareItems: []

    // chat: {chatId, name, shared, profileDir, host}; rowKey: where to ask "keep only on …?"
    function openShareMenu(button, chat, rowKey) {
        shareMenu.clearMenuItems()
        const host = chat.host || ""
        const accounts = shareAccountsOf(host)
        const here = accounts.find(g => g.profileKeys.indexOf(chat.profileDir) >= 0) || null
        const items = [shareItem.createObject(shareMenu, { section: true, text: host ? i18nc("chat name on host", "%1 on %2", chat.name, hostLabel(host)) : chat.name })]
        for (const g of accounts) {
            if (g === here)
                continue
            items.push(shareItem.createObject(shareMenu, {
                text: chat.shared ? i18n("Continue on %1", g.title) : i18n("Share and continue on %1", g.title),
                icon: Icons.plasma.continueOn, kind: "continue", chatId: chat.chatId, account: g, host: host
            }))
        }
        if (!chat.shared)
            items.push(shareItem.createObject(shareMenu, { text: i18n("Share with all accounts"), icon: Icons.plasma.share,
                                                           kind: "share", chatId: chat.chatId, host: host }))
        else {
            items.push(shareItem.createObject(shareMenu, { separator: true }))
            for (const g of accounts)
                items.push(shareItem.createObject(shareMenu, {
                    text: i18n("Keep only on %1…", g.title), icon: Icons.plasma.moveTo, kind: "keeponly",
                    chatId: chat.chatId, chatName: chat.name, rowKey: rowKey, account: g, host: host
                }))
        }
        for (const item of items)
            shareMenu.addMenuItem(item)
        shareItems = items
        shareMenu.visualParent = button
        shareMenu.openRelative()
    }

    function askKeepOnly(rowKey, chatId, name, account, host) {
        shareConfirm = {
            key: rowKey, chatId: chatId, name: name, profileKey: account.shareProfile, account: account.title,
            others: shareAccountsOf(host).filter(g => g.shareProfile !== account.shareProfile).map(g => g.title).join(", "),
            host: host
        }
    }

    function confirmKeepOnly() {
        const c = shareConfirm
        shareConfirm = noShareConfirm
        shareAction("keeponly", c.chatId, c.profileKey, c.host)
    }

    Exec {
        id: sharer
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            const kind = root.shareKinds[source] || ""
            delete root.shareKinds[source]
            if (!result.ok) {
                root.actionError = result.message
                actionErrorTimer.restart()
                root.petEvent("oops", i18n("Hmm, that didn't work."), "")
            } else if (kind === "continue") {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = ""
                root.actionInfo = result.message
                actionInfoTimer.restart()
            }
            root.refresh()
        }
    }

    property var shareKinds: ({})

    function shareAction(kind, chatId, profileKey, host) {
        const flag = { continue: "--continue", share: "--share", keeponly: "--unshare" }[kind]
        if (host) {
            // remote.py --share|--continue|--unshare HOST CHAT_ID [PROFILE]
            remoteAction(kind === "continue" ? "continue" : "share", host, flag + " " + shellQuote(host) + " "
                         + shellQuote(chatId) + (profileKey ? " " + shellQuote(profileKey) : ""))
            return
        }
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " " + flag + " " + shellQuote(chatId)
                    + (profileKey ? " --profile " + shellQuote(profileKey) : "") + configDirArgs + " # " + Date.now()
        shareKinds = Object.assign({}, shareKinds, { [cmd]: kind })
        sharer.connectSource(cmd)
    }

    function helperResult(data) {
        try {
            return JSON.parse(data["stdout"])
        } catch (e) {
            const lines = (data["stderr"] || "").trim().split("\n")
            return { ok: false, message: lines[lines.length - 1] || i18n("the helper gave no answer") }
        }
    }

    // Small helper actions whose only effect is on the widget's own list
    function runHelper(args) {
        stopper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " " + args + configDirArgs + " # " + Date.now())
    }

    function dismissSession(sessionId) {
        hideItem("chats", sessionId, "")
    }

    // ---------------------------------------------------------------- hide and delete
    // Hide (×): a chat, a plan, a memory or a project leaves its list here,
    // nothing is deleted, and Show Hidden … Again brings that kind back
    // (jump.py --hide / --show-hidden; an SSH host's on that host: remote.py).
    // Delete… (the trash button, beside the ×): a chat, a plan or a memory
    // goes to the Trash, after a question that says what goes (--describe).

    readonly property var hiddenKinds: ["chats", "plans", "memories", "projects"]

    // How many of a kind are hidden here (or on host): status.dismissed for chats
    function hiddenCount(kind, host) {
        const r = host ? (remote[host] || {}).result : status
        if (!r)
            return 0
        return (kind === "chats" ? r.dismissed : kind === "plans" ? r.hiddenPlans
                : kind === "memories" ? r.hiddenMemories : r.hiddenProjects) || 0
    }

    function showHiddenText(kind, count) {
        return kind === "chats" ? i18n("Show Hidden Chats Again (%1)", count)
             : kind === "plans" ? i18n("Show Hidden Plans Again (%1)", count)
             : kind === "memories" ? i18n("Show Hidden Memories Again (%1)", count)
             : i18n("Show Hidden Projects Again (%1)", count)
    }

    function hideItem(kind, id, host) {
        hideRun(host ? "remote.py" : "jump.py", "--hide " + (host ? shellQuote(host) + " " : "") + kind + " " + shellQuote(id),
                { kind: kind, host: host || "", say: false })
    }

    function showHidden(kind, host) {
        hideRun(host ? "remote.py" : "jump.py", "--show-hidden " + (host ? shellQuote(host) + " " : "") + kind,
                { kind: kind, host: host || "", say: true })
    }

    property var hideRuns: ({})   // command -> {kind, host, say: its answer is said}
    function hideRun(script, args, what) {
        const cmd = "python3 -I " + shellQuote(codeDir + script) + " " + args + (what.host ? "" : configDirArgs) + " # " + Date.now()
        hideRuns[cmd] = what
        hider.connectSource(cmd)
    }

    Exec {
        id: hider
        onNewData: (source, data) => {
            disconnectSource(source)
            const what = root.hideRuns[source] || { kind: "", host: "", say: false }
            delete root.hideRuns[source]
            const result = root.helperResult(data)
            if (!result.ok) {
                root.actionError = result.message
                actionErrorTimer.restart()
            } else {
                root.actionError = ""
                if (what.say) {   // (Showing 2 hidden plans again)
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                }
            }
            if (what.host)
                root.pollHost(what.host)
            else
                root.refresh()
            if (!what.host && (what.kind === "projects" || root.projectsShown))
                root.loadProjects()   // (a plan or memory there, or a project)
        }
    }

    // The menu of an SSH host's hidden ones (its header's eye button)
    PlasmaExtras.Menu {
        id: hiddenMenu
    }

    Component {
        id: hiddenItem
        PlasmaExtras.MenuItem {
            property string kind
            property string host
            icon: Icons.plasma.showHidden
            onClicked: root.showHidden(kind, host)
        }
    }

    property var hiddenItems: []

    function openHiddenMenu(button, host) {
        hiddenMenu.clearMenuItems()
        const items = hiddenKinds.filter(k => hiddenCount(k, host) > 0)
                                 .map(k => hiddenItem.createObject(hiddenMenu, { text: showHiddenText(k, hiddenCount(k, host)),
                                                                                 kind: k, host: host }))
        for (const item of items)
            hiddenMenu.addMenuItem(item)
        hiddenItems = items
        hiddenMenu.visualParent = button
        hiddenMenu.openRelative()
    }

    // The × and Delete… buttons' tooltips
    function hideHint(kind, host) {
        const back = host ? i18n("The eye button next to %1's name brings it back.", hostLabel(host))
                   : kind === "chats" ? i18n("Right-click → Show Hidden Chats Again brings it back.")
                   : kind === "plans" ? i18n("Right-click → Show Hidden Plans Again brings it back.")
                   : kind === "memories" ? i18n("Right-click → Show Hidden Memories Again brings it back.")
                   : i18n("Right-click → Show Hidden Projects Again brings it back.")
        return i18n("Only hides it here; nothing is deleted.") + " "
               + (kind === "chats" ? i18n("It comes back if the chat runs again.") + " " : "") + back
    }
    function deleteHint(kind) {
        return kind === "chat" ? i18n("Moves it to the Trash, on every account it's shared with, with its subagents and checkpoints; the Recap keeps its numbers. It asks first.")
             : kind === "plan" ? i18n("Moves its file to the Trash, on every account it's on. It asks first.")
             : i18n("Moves its file to the Trash and takes its line out of MEMORY.md: Claude stops reading it in new chats in its folder. It asks first.")
    }

    // "a", "a and b", "a, b and c"
    function andList(names) {
        return names.length < 2 ? names.join("") : i18nc("the last two of a list", "%1 and %2",
                                                         names.slice(0, -1).join(", "), names[names.length - 1])
    }

    // Delete… asks first (deleteAsk, shown under the item's line: DeleteAsk.qml):
    // {key: the line's key, kind: chat | plan | memory, id, profileDir, host,
    // folder: a memory's, busy: being looked at, question, message: why it can't}
    readonly property var noDeleteAsk: ({ key: "", kind: "", id: "", profileDir: "", host: "", folder: "",
                                          busy: false, question: "", message: "" })
    property var deleteAsk: noDeleteAsk

    // (jump.py --delete-chat ID --profile P; an SSH host's: remote.py --delete-chat HOST ID P)
    function deleteArgs(kind, id, profileDir, host) {
        return "--delete-" + kind + " " + (host ? shellQuote(host) + " " + shellQuote(id)
                                                  + (profileDir && kind !== "memory" ? " " + shellQuote(profileDir) : "")
                                                : shellQuote(id) + (kind !== "memory" ? profileArg(profileDir) : ""))
    }

    function askDelete(key, kind, id, profileDir, host, folder) {
        if (deleteAsk.key === key) {   // (again: the question goes)
            deleteAsk = noDeleteAsk
            return
        }
        cancelMove()
        deleteAsk = { key: key, kind: kind, id: id, profileDir: profileDir || "", host: host || "", folder: folder || "",
                      busy: true, question: "", message: "" }
        deleteRun(deleteArgs(kind, id, profileDir, host) + " --describe", { key: key, host: host || "", describe: true })
    }

    function confirmDelete() {
        const a = deleteAsk
        deleteAsk = noDeleteAsk
        deleteRun(deleteArgs(a.kind, a.id, a.profileDir, a.host), { key: a.key, host: a.host, describe: false })
    }

    property var deleteRuns: ({})   // command -> {key, host, describe}
    function deleteRun(args, what) {
        const cmd = "python3 -I " + shellQuote(codeDir + (what.host ? "remote.py" : "jump.py")) + " " + args
                    + (what.host ? "" : configDirArgs) + " # " + Date.now()
        deleteRuns[cmd] = what
        deleter.connectSource(cmd)
    }

    Exec {
        id: deleter
        onNewData: (source, data) => {
            disconnectSource(source)
            const what = root.deleteRuns[source] || { key: "", host: "", describe: false }
            delete root.deleteRuns[source]
            const result = root.helperResult(data)
            if (what.describe) {
                const a = root.deleteAsk
                if (a.key !== what.key)   // (cancelled, or another one asked meanwhile)
                    return
                const name = result.name || ""
                const accounts = root.andList(result.accounts || [])
                // (the backend's words, here to translate)
                const question = !result.ok || !name ? result.question || ""
                               : a.kind === "chat" && accounts
                               ? i18n("Delete “%1” on %2? It goes to the Trash with its subagents and checkpoints; the Recap keeps its numbers.", name, accounts)
                               : a.kind === "plan" && accounts ? i18n("Delete the plan “%1” on %2? It goes to the Trash.", name, accounts)
                               : a.kind === "plan" && result.folder   // (one in its project's plans folder)
                               ? i18n("Delete the plan “%1” from %2? It goes to the Trash.", name, result.folder)
                               : a.kind === "memory" && a.folder
                               ? i18n("Delete the memory “%1”? It goes to the Trash, and Claude stops reading it in new chats in %2.", name, a.folder)
                               : result.question || ""
                root.deleteAsk = Object.assign({}, a, { busy: false, question: result.ok ? question : "",
                                                        message: result.ok ? "" : result.message || i18n("It can't be deleted.") })
                return
            }
            if (!result.ok) {
                root.actionError = result.message
                actionErrorTimer.restart()
            } else {
                root.actionError = ""
                root.actionInfo = result.message   // (Moved to the Trash)
                actionInfoTimer.restart()
            }
            if (what.host)
                root.pollHost(what.host)
            else
                root.refresh()
            if (!what.host && root.projectsShown)
                root.loadProjects()
        }
    }

    // Move to project… (a plan's button) and a plan dropped on another
    // project's card in the Projects tab ask first (moveAsk, shown by
    // MoveAsk.qml under the plan's line or the card it was dropped on): where
    // it goes, whether the project's settings.local.json should keep its new
    // plans there too, whether git would show it, and keep both or replace
    // when a plan of that name is there. Nothing moves until Move (or Keep
    // both, Replace); Esc, Cancel or a click anywhere else lets it be.
    // {key: where it shows, slug, profileDir, host, back (to its account),
    // folder (the project picked; "": the chat's own), pick (offer the
    // projects to pick from), busy, answer (jump.py --move-plan --describe), keepThere, message}
    readonly property var noMoveAsk: ({ key: "", slug: "", profileDir: "", host: "", back: false, folder: "", pick: false,
                                        busy: false, answer: null, keepThere: true, message: "" })
    property var moveAsk: noMoveAsk
    property Item moveAskItem: null   // (the question on screen, MoveAsk.qml: a click outside it lets it be)
    onPopupTabChanged: cancelMove()

    function askMove(key, plan, host, folder, back, pick) {
        if (moveAsk.key === key && !folder) {   // (its button again: the question goes)
            cancelMove()
            return
        }
        deleteAsk = noDeleteAsk
        moveAsk = { key: key, slug: plan.slug, profileDir: plan.profileDir || "", host: host || "", back: !!back,
                    folder: folder || "", pick: !!pick, busy: true, answer: null,
                    keepThere: moveAsk.key === key ? moveAsk.keepThere : true, message: "" }
        moveRun(moveArgs(moveAsk, "") + " --describe", { key: key, host: host || "", describe: true })
    }
    function cancelMove() {
        if (moveAsk.key !== "")
            moveAsk = noMoveAsk
    }
    // (jump.py --move-plan SLUG --profile P [--into F | --back] …; an SSH host's: remote.py --move-plan HOST SLUG P …)
    function moveArgs(a, ifExists) {
        return "--move-plan " + (a.host ? shellQuote(a.host) + " " + shellQuote(a.slug) + " " + shellQuote(a.profileDir)
                                        : shellQuote(a.slug) + profileArg(a.profileDir))
               + (a.back ? " --back" : a.folder ? " --into " + shellQuote(a.folder) : "")
               + (!a.back && !a.keepThere ? " --no-setting" : "")
               + (ifExists ? " --if-exists " + ifExists : "")
    }
    // Move (ifExists ""), Keep both ("keep") or Replace ("replace")
    function confirmMove(ifExists) {
        const a = moveAsk
        if (!a.answer || a.busy)
            return
        const into = a.answer.project && !a.back ? a.answer.project : a.folder
        moveAsk = noMoveAsk
        moveRun(moveArgs(Object.assign({}, a, { folder: into }), ifExists), { key: a.key, host: a.host, describe: false })
    }
    property var moveRuns: ({})   // command -> {key, host, describe}
    function moveRun(args, what) {
        const cmd = "python3 -I " + shellQuote(codeDir + (what.host ? "remote.py" : "jump.py")) + " " + args
                    + (what.host ? "" : configDirArgs) + " # " + Date.now()
        moveRuns[cmd] = what
        mover.connectSource(cmd)
    }
    Exec {
        id: mover
        onNewData: (source, data) => {
            disconnectSource(source)
            const what = root.moveRuns[source] || { key: "", host: "", describe: false }
            delete root.moveRuns[source]
            const result = root.helperResult(data)
            if (what.describe) {
                if (root.moveAsk.key !== what.key || !root.moveAsk.busy)   // (cancelled, or asked again meanwhile)
                    return
                root.moveAsk = Object.assign({}, root.moveAsk, { busy: false, answer: result.ok ? result : null,
                                                                 message: result.ok ? "" : result.message || i18n("It can't be moved.") })
                return
            }
            if (!result.ok) {
                root.actionError = result.message
                actionErrorTimer.restart()
            } else {
                root.actionError = ""
                root.actionInfo = result.message   // (Moved the plan to …)
                actionInfoTimer.restart()
            }
            if (what.host)
                root.pollHost(what.host)
            else
                root.refresh()
            if (!what.host && root.projectsShown)
                root.loadProjects()
        }
    }

    // profileDir picks the right copy of a chat shared across profiles
    function profileArg(profileDir) {
        return profileDir ? " --profile " + shellQuote(profileDir) : ""
    }

    // busy: you were told it's working or waiting (else only an idle one is stopped);
    // keepOffChat: a chat that keeps going, to turn Keep going off for at once (once stopped)
    function stopSession(sessionId, profileDir, busy, keepOffChat) {
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --stop " + shellQuote(sessionId)
                    + profileArg(profileDir) + (busy ? " --busy" : "")
                    + (keepOffChat ? " --and-keep-off " + shellQuote(keepOffChat) : "") + configDirArgs + " # " + Date.now()
        if (keepOffChat)
            stopSays[cmd] = true   // (its answer says what's left: Stopped. It won't go on by itself any more)
        stopper.connectSource(cmd)
    }
    property var stopSays: ({})

    // Esc in the tmux pane of a working chat
    function interruptSession(sessionId, profileDir) {
        stopper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --interrupt " + shellQuote(sessionId)
                              + profileArg(profileDir) + configDirArgs + " # " + Date.now())
    }

    function jumpTo(sessionId, profileDir) {
        const row = listedRow(sessionId, profileDir, "")
        if (row)
            forgetFinished(petKeyOf(row, ""))
        // Trailing comment keeps repeated clicks from being deduplicated by the engine.
        jumper.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " " + shellQuote(sessionId)
                             + profileArg(profileDir) + configDirArgs + " # " + Date.now())
    }

    // ---------------------------------------------------------------- usage limits that stopped chats
    // A chat a usage limit stopped (talpy_den.py: stopped_by, limit_stop)
    // says when the limit resets. Once it has, one notification per account
    // says which of its chats can go on. Meanwhile one can continue on another
    // account that still has room (handOver: shared with it, then reopened there).

    property var lastStops: ({})   // source -> {chat key: whether its limit has reset}

    function trackLimitStops(source, groupList, host) {
        const before = lastStops[source]
        const next = {}
        for (const g of groupList) {
            const freed = []
            for (const s of g.sessions) {
                if (!s.stopped || s.stopped.kind !== "limit")
                    continue
                const key = petKeyOf(s, host)
                if (key in next)
                    continue
                next[key] = !!s.stopped.over
                if (before && before[key] === false && s.stopped.over)
                    freed.push(s)
            }
            if (!freed.length)
                continue
            const where = host ? i18nc("ssh host: account", "%1: %2", hostLabel(host), g.name) : g.name
            for (const s of freed)
                petEvent("reset", i18n("%1 can go on!", s.name), petKeyOf(s, host))
            if (!root.notifier || !Plasmoid.configuration.notifyDone || holdingBack())
                continue
            const names = freed.slice(0, 4).map(s => s.name).join(", ") + (freed.length > 4 ? " " + i18nc("and more", "+%1", freed.length - 4) : "")
            notify("limit-reset|" + source + "|" + g.id, freed[0], "reset", i18n("%1: the usage limit reset", where),
                   i18np("%2 can go on.", "%1 chats can go on: %2", freed.length, names), "chronometer-reset", host)
            queueSound("done")
        }
        lastStops = Object.assign({}, lastStops, { [source]: next })
        playQueuedSound()
    }

    // ---------------------------------------------------------------- chats changing the same files
    // Two chats with a process that changed some of the same files
    // (talpy_den.py: note_overlaps): a tag on both rows, and one
    // notification per pair when it starts.

    property var lastOverlaps: ({})   // source -> {pair key: true}

    function trackOverlaps(source, groupList, host) {
        const before = lastOverlaps[source]
        const next = {}
        for (const g of groupList)
            for (const s of g.sessions)
                for (const o of (s.overlaps || [])) {
                    // (by chat: one listed twice, open on two accounts, is one chat)
                    const pair = [s.chatId || s.sessionId, o.chatId || o.sessionId].sort().join("|")
                    if (pair in next)
                        continue
                    next[pair] = true
                    if (!before || pair in before)
                        continue   // (the first check only learns)
                    petEvent("waiting", i18n("%1 and %2 change the same files!", s.name, o.name), petKeyOf(s, host))
                    if (root.notifier && Plasmoid.configuration.notifyWaiting && !holdingBack())
                        notify("overlap|" + source + "|" + pair, s, "overlap", i18n("Two chats change the same files"),
                               i18n("%1 and %2: %3", s.name, o.name, o.files.join(", ") + (o.count > o.files.length ? " …" : ""))
                               + (host ? "\n" + host : ""), "dialog-warning", host)
                }
        lastOverlaps = Object.assign({}, lastOverlaps, { [source]: next })
    }

    // "Also changed by …" for a row's tag
    function overlapText(overlaps) {
        return overlaps.map(o => i18np("Also changed by “%2”: %3", "Also changed by “%2” (%1 files): %3", o.count, o.name,
                                       o.files.join(", ") + (o.count > o.files.length ? " …" : ""))).join("\n")
    }

    // ---------------------------------------------------------------- tasks waiting for a usage limit
    // A background task can wait for its account's usage limit to reset
    // (jump.py --queue; the status lists the queue). Once one is due, the
    // copy of the widget that notifies starts it (jump.py --start-queued,
    // which takes it out of the queue first: one start, whoever asks).

    property bool taskQueued: false    // the new-chat box: start after the limit resets
    property var startingTasks: ({})   // task id -> when it was started (startQueued), until its answer comes
    // (an answer that never comes: after this it can be started again, which
    // jump.py does once whoever asks)
    readonly property int startStaleMs: 300000

    // A queued task being started now (its answer hasn't come)
    function isStarting(id) {
        const at = startingTasks[id]
        return !!at && now - at < startStaleMs
    }

    // When the usage limit this account is at resets ({at, label}), or null:
    // the latest of its full windows (or of one at the usage cap), else of
    // the chats a limit stopped
    function limitReset(group, host) {
        let best = null
        const limits = group.limits || group.accountLimits   // (also where its usage isn't shown: withUsage)
        for (const w of (limits ? limits.windows : []))
            if (w.pct >= 95 && w.resetsAt && (!best || w.resetsAt > best.at))
                best = { at: w.resetsAt, label: w.label }
        if (group.cap && (!best || group.cap.resetsAt > best.at))
            best = { at: group.cap.resetsAt, label: group.cap.label }
        if (!best)
            for (const s of group.sessions)
                if (s.stopped && s.stopped.kind === "limit" && !s.stopped.over && s.stopped.resetsAt
                        && (!best || s.stopped.resetsAt > best.at))
                    best = { at: s.stopped.resetsAt, label: "" }
        return best && best.at > now ? best : null
    }

    function clockText(ms) {
        return new Date(ms).toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
    }

    // A chat Claude moved to the background under a new id (its row's movedFrom), in a line
    function movedText(s) {
        const m = s ? s.movedFrom : null
        if (!m)
            return ""
        return (m.at ? i18n("Moved to the background at %1: Claude goes on with it under a new id.", clockText(m.at))
                     : i18n("Moved to the background: Claude goes on with it under a new id.")) + "\n\n"
    }

    // What a queued task does, in a line
    // (a chat's go-on names the chat as its row is called now, else as queued)
    function queuedWhat(t) {
        const row = t.chat ? listedRow(t.chat, "", t.host || "") : null
        return t.chat ? i18n("Go on with “%1”", (row && row.name) || t.name || t.chat.slice(0, 8))
             : t.planTitle ? i18n("Carry out “%1”", t.planTitle) + (t.prompt ? ": " + t.prompt : "")
             : t.prompt
    }

    // The queued task that goes on with this chat (here, or on host), or null
    // (not a reply waiting for its turn to end: that isn't a go-on)
    function queuedChat(chatId, host) {
        return (status && status.queue ? status.queue : []).find(t => !!t.chat && t.chat === chatId && !t.afterTurn
                                                                       && (t.host || "") === (host || ""))
               || null
    }

    // Whether a queued task's line would only repeat a row: a chat's go-on
    // whose chat is one of the account's rows, which says Goes on at …
    // (SessionRow's goingOn); not one that failed (its line says why) nor a
    // reply for when a turn ends. The queue lists only what no row shows.
    function onItsRow(t, group, host) {
        if (!t.chat || t.afterTurn || t.error)
            return false
        return group.sessions.some(s => s.chatId === t.chat && (goOnAt(s) > 0 || !!s.stopped)
                                        && (queuedChat(s.chatId, host) || {}).id === t.id)
    }

    // When a chat a usage limit stopped can go on by itself (a minute after
    // the limit resets: jump.py --queue-continue), in ms, or 0. Not one open
    // in VS Code's Claude (its tab can't be ended), nor one at work again.
    function goOnAt(session) {
        const stop = session.stopped
        if (!stop || stop.kind !== "limit" || stop.over || !stop.resetsAt || !(session.chatId || session.sessionId))
            return 0
        if (session.pid !== undefined && session.pid !== null
                && (session.entrypoint === "claude-vscode" || session.state !== "idle" || session.sessionId !== session.chatId))
            return 0
        return stop.resetsAt + 60000
    }

    // (keep: and after later limits too, until it's done; an SSH host's or a container's chats too)
    function queueContinue(session, host, account, keep) {
        const at = goOnAt(session)
        if (!at)
            return
        queuer.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --queue-continue "
                             + shellQuote(session.chatId || session.sessionId) + " --profile " + shellQuote(session.profileDir)
                             + " --at " + Math.round(at) + (session.cwd ? " --cwd " + shellQuote(session.cwd) : "")
                             + " --name " + shellQuote(session.name || "") + (host ? " --host " + shellQuote(host) : "")
                             + (keep ? " --keep" : "")
                             + " --account " + shellQuote(account) + configDirArgs + " # " + Date.now())
    }

    // ---------------------------------------------------------------- chats that keep going
    // A chat (of this computer, an SSH host or a container) can keep going
    // until it's done: after each usage limit that stops it, it goes on by
    // itself when that resets (talpy_den.py: look_after_kept, a host's from
    // its last answer; jump.py --keep-going, --keep-off, with --host). One a limit stopped
    // can start keeping going then (jump.py --queue-continue --keep).

    // The chat (of host: an SSH host or a container) that keeps going ({chat, host, note, error, …}), or null
    function keptChat(chatId, host) {
        return (status && status.keep ? status.keep : []).find(k => k.chat === chatId && (k.host || "") === (host || "")) || null
    }

    // Can a chat of this row keep going? One at work (here, on an SSH host or in a container), not in VS Code's Claude
    function canKeepGoing(session, host) {
        return !!(session.chatId || session.sessionId) && session.entrypoint !== "claude-vscode"
               && session.state === "working"
    }

    // (host's: kept here, it goes on from here over ssh, look_after_host_kept)
    function keepGoing(session, on, host) {
        const chat = session.chatId || session.sessionId
        queuer.connectSource("python3 -I " + shellQuote(codeDir + "jump.py")
                             + (on ? " --keep-going " + shellQuote(chat) + " --profile " + shellQuote(session.profileDir)
                                     + (session.cwd ? " --cwd " + shellQuote(session.cwd) : "")
                                     + " --name " + shellQuote(session.name || "")
                                   : " --keep-off " + shellQuote(chat))
                             + (host ? " --host " + shellQuote(host) : "")
                             + configDirArgs + " # " + Date.now())
    }

    // What a chat that keeps going does, for its tag's tooltip
    function keptText(kept) {
        const lines = [i18n("When a usage limit stops it, it goes on by itself in the background a minute after the limit resets, and again after each later one, until a turn of it ends by itself. When a go-on doesn't take or its turn breaks off (the connection lost), it tries again a few times.")]
        if (kept.error)
            lines.push(kept.error)
        else if (kept.note)
            lines.push(kept.note)
        lines.push(i18n("Click to stop it keeping going (a go-on that's queued already stays)."))
        return lines.join("\n\n")
    }

    // Queueing a task or a chat: says when it starts, or why it can't
    Exec {
        id: queuer
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            root.draftBack(source, result.ok)
            if (result.ok) {
                root.actionError = ""
                if (result.message) {
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                }
            } else {
                root.actionError = i18n("Couldn't queue it: %1", result.message)
                actionErrorTimer.restart()
            }
            root.refresh()
        }
    }

    // The account's queued tasks (here, or on host)
    function queuedFor(group, host) {
        return (status && status.queue ? status.queue : []).filter(t => (t.host || "") === (host || "")
                                                                         && group.profileKeys.indexOf(t.profile) >= 0)
    }

    // (the copy that notifies starts them; a task whose account is at its
    // usage limit right now waits on until that resets: jump.py --requeue)
    function startDueTasks(queue) {
        if (!root.notifier)
            return
        for (const t of queue) {
            if (t.afterTurn) {   // a reply for when the chat's turn ends: now it has (or the chat isn't listed)
                // (an SSH host's: by its last check, which worked; not while it waits for a usage limit)
                const known = !t.host || (remote[t.host] && remote[t.host].result && !remote[t.host].error)
                const s = known ? listedRow(t.chat, t.profile, t.host || "") : null
                if (known && !t.error && !isStarting(t.id) && !(t.startAt > Date.now())
                        && (!s || (s.state !== "working" && s.state !== "waiting")))
                    startOrWait(t)
                continue
            }
            if (!t.due || isStarting(t.id))
                continue
            startOrWait(t)
        }
    }

    // A task whose time came starts, unless its account is at its usage
    // limit: then it waits on until a minute after that resets
    function startOrWait(t) {
        // (its account as its section shows it: with the newest plan usage
        // of any machine it's on, withUsage, as the new-chat box queued it by)
        const group = hostGroups(t.host || "").map(g => withUsage(g, t.host || ""))
            .find(g => g.profileKeys.indexOf(t.profile) >= 0)
        const reset = group ? limitReset(group, t.host || "") : null
        if (!reset) {
            startQueued(t)
            return
        }
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --requeue " + shellQuote(t.id)
                    + " --at " + Math.round(reset.at + 60000) + configDirArgs + " # " + Date.now()
        if (t.afterTurn)
            stopSays[cmd] = true   // (your reply: It waits for the usage limit: it starts at 14:31)
        stopper.connectSource(cmd)
    }

    // now: Start it now (a chat's go-on ends the background commands it waits for at once, and says so)
    function startQueued(t, now) {
        startingTasks = Object.assign({}, startingTasks, { [t.id]: Date.now() })
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --start-queued " + shellQuote(t.id) + (now ? " --now" : "") + configDirArgs
                    + " # " + Date.now()
        queueRuns[cmd] = t
        queueRunner.connectSource(cmd)
    }

    function unqueue(t) {
        runHelper("--unqueue " + shellQuote(t.id))
    }
    property string unqueueAsk: ""   // the queued task whose Cancel it asks first (what you wrote goes with it)

    property var queueRuns: ({})   // command -> the task it starts

    Exec {
        id: queueRunner
        onNewData: (source, data) => {
            disconnectSource(source)
            const t = root.queueRuns[source]
            delete root.queueRuns[source]
            const result = root.helperResult(data)
            const what = t ? root.queuedWhat(t).split("\n")[0] : ""
            if (t) {
                const rest = Object.assign({}, root.startingTasks)
                delete rest[t.id]
                root.startingTasks = rest
            }
            if (result.ok && result.message && t && t.afterTurn) {   // your reply, sent as its turn ended
                if (root.notifier && Plasmoid.configuration.notifyDone && !root.holdingBack() && !root.dashboardShown)
                    root.notify("queued|" + t.id, null, "started", i18n("Sent to %1", t.name || i18n("the chat")),
                                t.prompt + "\n" + result.message, "document-send", "")
            } else if (result.waits !== undefined && t) {
                // a chat's go-on waits for its background commands (its line
                // says so): told once, as it starts waiting
                if (result.notify) {
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                    if (root.notifier && !root.dashboardShown)
                        root.notify("queued|" + t.id, null, "limit", i18n("“%1” waits to go on", t.name || t.chat.slice(0, 8)),
                                    result.message, "chronometer", "")
                }
            } else if (result.ok && result.message && t) {   // ("": another copy started it)
                root.petEvent("reset", i18n("Started: %1", what), "")
                if (result.ended !== undefined) {
                    // (it ended the background commands it waited for: told whatever the settings, as it began to wait)
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                    if (root.notifier && !root.dashboardShown)
                        root.notify("queued|" + t.id, null, "started", i18n("“%1” went on", t.name || t.chat.slice(0, 8)),
                                    result.message, "media-playback-start", "")
                } else if (root.notifier && Plasmoid.configuration.notifyDone && !root.holdingBack())
                    root.notify("queued|" + t.id, null, "started", i18n("Started on %1: %2", t.account, what),
                                result.message + (t.host ? " · " + t.host : ""), "media-playback-start", "")
            } else if (!result.ok && t && t.afterTurn) {   // (your reply, as VS Code says it)
                root.actionError = i18n("Couldn't send your reply to %1: %2", t.name || i18n("the chat"), result.message)
                actionErrorTimer.restart()
                if (root.notifier && !root.dashboardShown)
                    root.notify("queued|" + t.id, null, "error", i18n("Couldn't send your reply to %1", t.name || i18n("the chat")),
                                t.prompt + "\n" + result.message, "dialog-error", "")
            } else if (!result.ok && t) {
                root.actionError = i18n("Couldn't start the queued task: %1", result.message)
                actionErrorTimer.restart()
                if (root.notifier && !root.dashboardShown)
                    root.notify("queued|" + t.id, null, "error", i18n("Couldn't start the queued task"),
                                what + "\n" + result.message, "dialog-error", "")
            }
            root.refresh()
            if (t && t.host)
                root.pollHost(t.host)
        }
    }

    // The step line of a chat that something stopped
    function stopText(stopped) {
        if (stopped.kind === "login")
            return i18n("Claude's login expired. Log in again (/login), then tell it to go on.")
        if (stopped.over)
            return i18n("The limit it hit has reset: open it and tell Claude to go on.")
        return stopped.text
    }

    // Another account (here, or on the chat's SSH host) with room left in
    // the limit that stopped this chat: {title, shareProfile, pct, label}, or
    // null. Not for a chat open in VS Code's Claude, whose tab would start it
    // again here with your next message.
    function handoverTarget(session, host) {
        const stop = session.stopped
        if (!stop || stop.kind !== "limit" || stop.over || !session.chatId)
            return null
        // (a session continuing another chat: the one with the chat's own id would be ended, not this one)
        if (session.pid !== null && (session.entrypoint === "claude-vscode" || session.state !== "idle"
                                     || session.sessionId !== session.chatId))
            return null
        let best = null
        for (const g of shareAccountsOf(host)) {
            if (g.profileKeys.indexOf(session.profileDir) >= 0)
                continue
            const w = g.limits ? g.limits.windows.find(x => x.key === (stop.window || "five_hour")) : null
            const pct = w ? w.pct : null
            if (pct !== null && pct >= 95)
                continue
            if (!best || (pct !== null && (best.pct === null || pct < best.pct)))
                best = { title: g.title, shareProfile: g.shareProfile, pct: pct, label: w ? w.label : "" }
        }
        return best
    }

    // Continue it there: an idle session that has it open here quits first
    // (jump.py --continue --end-first; on an SSH host, remote.py there)
    function handOver(session, host, target) {
        const endFirst = session.pid !== null ? " --end-first" : ""
        if (host) {
            remoteAction("continue", host, "--continue " + shellQuote(host) + " " + shellQuote(session.chatId) + " "
                         + shellQuote(target.shareProfile) + endFirst)
            return
        }
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --continue " + shellQuote(session.chatId)
                    + " --profile " + shellQuote(target.shareProfile) + endFirst + configDirArgs + " # " + Date.now()
        shareKinds = Object.assign({}, shareKinds, { [cmd]: "continue" })
        sharer.connectSource(cmd)
    }

    // A chat's permission mode (talpy_den.py: mode_of), "" when it isn't known;
    // the default is Claude's manual mode
    function modeText(mode) {
        switch (mode) {
        case "default": return i18n("Manual mode")
        case "plan": return i18n("Plan mode")
        case "acceptEdits": return i18n("Accept edits")
        case "auto": return i18n("Auto mode")
        case "bypassPermissions": return i18n("Bypass permissions")
        case "dontAsk": return i18n("Don't ask")
        case "": case null: case undefined: return ""
        default: return mode
        }
    }

    function modeHint(mode) {
        switch (mode) {
        case "plan": return i18n("Plan mode: Claude looks around and writes a plan, and changes nothing until you approve it.")
        case "acceptEdits": return i18n("Claude edits files without asking; other actions still ask you.")
        case "auto": return i18n("Auto mode: Claude goes ahead with what it judges safe, and asks you about the rest.")
        case "bypassPermissions": return i18n("Claude runs everything without asking.")
        case "dontAsk": return i18n("What isn't allowed already is refused, without asking you.")
        case "default": return i18n("Manual mode: Claude asks you before it edits a file or runs a command you haven't allowed. Shift+Tab in the chat changes it.")
        default: return i18n("Shift+Tab in the chat changes it.")
        }
    }

    // ---------------------------------------------------------------- the chat pane
    // A chat beside the popup (ChatPane.qml): its conversation, a box to
    // reply, what it asks for, and its review (pane.py). A click on a chat's
    // name opens it there (or, with clickOpensPane off, the chat's window).
    // Each chat has a window of its own, as it has a tab in VS Code: another
    // chat opens in another window, the one before stays open, and a chat
    // whose window is open already brings it forward.

    // c's row in the status now: a listed session, else a recent chat (or null).
    // c: a pane's chat {chatId, sessionId, profileDir, host, name, cwd, tab}
    function paneRowOf(c) {
        if (!c || !c.chatId)
            return null
        const groupList = hostGroups(c.host || "")
        let found = null
        for (const g of groupList)
            for (const s of g.sessions || [])
                if (!found && ((s.chatId || s.sessionId) === c.chatId || s.sessionId === c.chatId))
                    found = s
        if (found)
            return found
        for (const g of groupList)
            for (const r of (g.recent || []).concat(g.starred || []))
                if (!found && r.sessionId === c.chatId)
                    found = Object.assign({ state: "done", pid: null, kind: "chat", reply: "background", chatId: r.sessionId }, r)
        return found
    }

    // This copy's chat windows: the open ones (a chat set, shown or about to
    // be) and the closed ones, hidden, kept for the next chat to open in
    // without being made again (made the first time one is needed: ChatPane.qml
    // isn't read before)
    property var paneWindows: []
    property var paneComponent: null
    property var paneDrafts: ({})   // what you were typing to each chat ("host\nchatId" -> text), any window's
    function paneKeyOf(c) {
        return c && c.chatId ? (c.host || "") + "|" + c.chatId : ""
    }
    function paneWindowOf(key) {   // (this copy's open window for that chat, or null)
        return key ? paneWindows.find(w => paneKeyOf(w.chat) === key) || null : null
    }
    // (an open pane shows the chat, petKeyOf: you're looking, or about to)
    function paneShows(sid) {
        return paneWindows.some(w => !!w.chat.chatId && petKeyOf(w.chat, w.chat.host) === sid)
    }
    // (which chats this copy's windows show: one opened from another copy comes forward here)
    function paneListChanged() {
        Hub.paneShown(instanceId, paneWindows.map(w => paneKeyOf(w.chat)).filter(k => k !== ""))
    }

    // s: a session row or a recent chat (sessionId is its chat then); tab: "chat" or "review";
    // then: what the pane does once it shows it ({draft}, {denying}, {typing}: ChatPane act).
    // A chat has one window: open in another copy's (the panel's, a
    // desktop's), that one comes forward instead, and does it; open in this
    // one's, it comes forward (ChatPane forward). Another chat opens in a
    // window of its own: a closed one (the one this chat had last, else any),
    // else a new one
    function openPane(s, host, tab, then) {
        forgetFinished(petKeyOf(s, host))
        const chatId = s.chatId || s.sessionId
        const key = (host || "") + "|" + chatId
        const holder = Hub.paneHolder(key, instanceId)
        if (holder) {
            Hub.paneRaise(holder, key, tab || "chat", then || null)
            return
        }
        const open = paneWindowOf(key)
        if (open) {
            open.forward(tab || "chat")
            open.act(then)
            return
        }
        const chat = { chatId: chatId, sessionId: s.sessionId || "", profileDir: s.profileDir || "",
                       host: host || "", name: s.name || "", cwd: s.cwd || "", tab: tab || "chat", at: Date.now(), key: s.key || "" }
        let win = paneWindows.find(w => !w.chat.chatId && w.lastKey === key) || paneWindows.find(w => !w.chat.chatId)
        if (win) {
            win.chat = chat
        } else {
            if (!paneComponent)
                paneComponent = Qt.createComponent(Qt.resolvedUrl("ChatPane.qml"))
            win = paneComponent.status === Component.Ready ? paneComponent.createObject(root, { chat: chat }) : null
            if (!win) {
                console.warn("talpy-den: the chat pane couldn't be made:", paneComponent.errorString())
                return
            }
            paneWindows = paneWindows.concat([win])
        }
        paneListChanged()
        placePane(win)
        win.act(then)
    }

    // Closed (ChatPane onClosing): hidden, and free for the next chat
    function paneClosed(win) {
        win.lastKey = paneKeyOf(win.chat)
        win.chat = ({})
        paneListChanged()
    }
    Connections {
        target: Hub
        function onPaneRaise(id, key, tab, then) {   // (this copy's window shows the chat another copy opened)
            const win = id === root.instanceId ? root.paneWindowOf(key) : null
            if (win) {
                win.forward(tab)
                win.act(then)
            }
        }
    }

    // A click on a chat: the pane, or the chat's own window
    function clickChat(s, host) {
        if (Plasmoid.configuration.clickOpensPane)
            openPane(s, host, "chat")
        else
            openRow(s, host)
    }

    // The chat's own window: its terminal or VS Code tab; one that isn't open
    // reopens (as the switch says)
    function openRow(s, host) {
        if (s && s.pid !== undefined && s.key && s.key.indexOf("/recent") < 0 && s.key.indexOf("/starred") < 0) {
            if (host)
                remoteShow(host, s)
            else
                jumpTo(s.sessionId, s.profileDir)
        } else if (s) {
            const chatId = s.chatId || s.sessionId
            openChatById(chatId, s.profileDir || "", s.cwd || "", s.openCommand || "", "", host || "")
        }
    }

    // It opens as any window does: whole, where it goes, with only KWin's
    // animation. Beside the popup, on the side with more room, KWin puts it
    // as it appears (jump.py --place-window, asked before it's shown: else it
    // shows where KWin puts new windows first, then jumps). It's shown once
    // KWin is ready and its conversation is read: at its end, not "Reading
    // the chat…" first. A read that takes longer (an SSH host's) isn't
    // waited for after 400 ms, KWin after a second (ChatPane: placeAsk,
    // placeReading and their timers; each window waits for its own).

    // [x, y, width, height] of the pane beside the popup, on the side with more
    // room, as tall as the popup; null while the popup isn't shown
    function paneGeometry(win) {
        const item = root.fullRepresentationItem
        if (!win || !item || !root.expanded || !item.visible || !item.Window.window)
            return null
        const p = item.mapToGlobal(0, 0)
        const sx = item.Screen.virtualX, sy = item.Screen.virtualY, sw = item.Screen.width, sh = item.Screen.height
        const gap = Kirigami.Units.smallSpacing
        const right = sx + sw - (p.x + item.width) - gap, left = p.x - sx - gap
        const width = Math.round(Math.max(win.minimumWidth, Math.min(win.wantedWidth, Math.max(right, left))))
        const x = right >= width || right >= left ? p.x + item.width + gap : p.x - gap - width
        const height = Math.round(Math.min(sh, Math.max(item.height, win.minimumHeight)))
        const y = p.y - sy > sh / 2 ? p.y + item.height - height : p.y   // (bottoms lined up under a bottom panel)
        return [Math.round(x), Math.round(Math.max(sy, Math.min(y, sy + sh - height))), width, height]
    }

    function placePane(win) {
        const geometry = paneGeometry(win)
        let ask = ""
        if (geometry) {
            // (at the size it'll have beside the popup from the start: KWin only moves it there)
            win.width = geometry[2]
            win.height = geometry[3]
            // (its title, with * for the chat's name: that can change before it shows. The
            // other chats' windows, open, are left where they are: KWin places only one appearing)
            ask = "python3 -I " + shellQuote(codeDir + "jump.py") + " --place-window "
                  + shellQuote(i18nc("window title: a chat's name", "%1 — Talpy Chat", "*")) + " " + geometry.join(",")
                  + " # " + Date.now()
        }
        win.placing(ask)
        if (ask)
            placer.connectSource(ask)
        showPane(win)
    }

    function showPane(win) {
        if (!win || win.visible || !win.chat.chatId || win.placeAsk !== "" || (win.placeReading && !win.loaded && win.loadError === ""))
            return
        win.placing(null)
        win.visible = true
        win.opened()
    }

    Exec {
        id: placer
        onNewData: (source, data) => {
            disconnectSource(source)
            const win = root.paneWindows.find(w => w.placeAsk === source)
            if (win) {
                win.placeAsk = ""
                root.showPane(win)
            }
        }
    }

    // Finished, changed files, and not marked reviewed since (pane.py
    // --reviewed; 0: marked not reviewed). What chats changed before the
    // widget first looked (reviewedSince) isn't to review.
    function reviewPending(s, host) {
        if (!s || !s.review || !s.review.editedAt || s.state === "working" || s.state === "waiting")
            return false
        return !reviewSeen(s, host)
    }
    // Its changes since its last edit marked reviewed (or older than what's to
    // review at all), whether it works now or not (the pane's Reviewed button)
    function reviewSeen(s, host) {
        if (!s || !s.review || !s.review.editedAt)
            return true
        const marks = status && status.reviewed ? status.reviewed : {}
        const id = s.chatId || s.sessionId
        const mark = marks[host ? host + "|" + id : id]
        const seen = mark === 0 ? 0 : Math.max(mark || 0, status && status.reviewedSince ? status.reviewedSince : 0)
        // (the marks and reviewedSince are this computer's, also an SSH host's
        // chat's: pane.py marks it here. Its last edit is on the host's clock,
        // which toLocalClock leaves its review on: moved to ours here)
        const offset = host && remote[host] ? remote[host].clockOffset || 0 : 0
        return seen >= s.review.editedAt + offset
    }

    // The message waiting to be sent when the chat's turn ends (pane.py --send --after-turn)
    function queuedMessage(chatId, host) {
        return (status && status.queue ? status.queue : []).find(t => t.afterTurn && t.chat === chatId
                                                                       && (t.host || "") === (host || "")) || null
    }

    // What a waiting chat asks, for its notification: [title, text] (s.permission set)
    function askText(s) {
        const p = s.permission
        if (p.plan)
            return [i18n("%1 has a plan ready", s.name), p.plan.title || i18n("Approve it to start, or keep planning.")]
        if (p.questions && p.questions.length)
            return [i18n("%1 asks you", s.name), p.questions.map(q => q.question).join("\n")]
        return [i18n("%1 asks for a permission", s.name), p.command || (p.file ? i18n("Change %1", p.file) : p.line)]
    }

    // Whether the widget can answer what a waiting chat asks (its permission:
    // through the hook, or with keys in tmux)
    function canAnswerAsk(s) {
        const p = s ? s.permission : null
        return !!p && (p.answer === "hook" || p.answer === "keys")
    }

    // What a waiting chat asks, to tell one prompt from the next: the hook's
    // request, else the tool call it's about (talpy_den.py: note_permissions);
    // "" when there's nothing to tell them apart by
    function askId(s) {
        const p = s ? s.permission : null
        if (!p)
            return ""
        if (p.answer === "hook")
            return p.request ? "request:" + p.request : ""
        return p.toolUse ? "tool:" + p.toolUse : ""
    }

    // An answer to what a chat asks, from its row or a notification (pane.py
    // --answer / --keys); a question's: decision "answer", answers {question: [labels or text]}.
    // s is the chat as that row or notification shows it, and the answer goes
    // to what it shows only: the hook's request, or in tmux the tool call it
    // asks about (--expect: if it asks something else now, nothing is pressed)
    function answerPermission(s, host, decision, note, answers) {
        const p = s ? s.permission : null
        if (!p || (p.answer !== "hook" && p.answer !== "keys"))
            return
        const args = p.answer === "hook"
            ? "--answer " + shellQuote(p.request)
            : "--keys " + shellQuote(s.sessionId) + profileArg(s.profileDir) + (p.toolUse ? " --expect " + shellQuote(p.toolUse) : "")
        const cmd = "python3 -I " + shellQuote(codeDir + "pane.py") + " " + args + " --decision " + decision
                    + (note ? " --note " + shellQuote(note) : "")
                    + (answers ? " --answers " + shellQuote(JSON.stringify(answers)) : "")
                    + (host ? " --host " + shellQuote(host) : "") + configDirArgs + " # " + Date.now()
        answerFor[cmd] = { session: s, host: host || "" }
        paneActions.connectSource(cmd)
    }
    property var answerFor: ({})   // command -> {session, host}: the chat an answer is for

    // Other…, from a question's notification: the chat's pane, the field to answer in your own words ready
    function answerInPane(s, host) {
        if (!s)
            return
        openPane(s, host, "chat", { typing: true })
    }

    // Deny with a note, from a notification: the chat's pane, its note field ready
    function denyWithNote(s, host) {
        if (!s)
            return
        openPane(s, host, "chat", { denying: true })
    }

    // A reply from a notification: sent as the chat takes one; one in a
    // terminal that takes no text opens the pane with it
    property var replyDrafts: ({})   // command -> {session, host, text}

    function replyTo(s, host, text) {
        text = (text || "").trim()
        if (!s || !text)
            return
        const cmd = "python3 -I " + shellQuote(codeDir + "pane.py") + " --send " + shellQuote(s.chatId || s.sessionId)
                    + " --text " + shellQuote(text) + (s.sessionId ? " --session " + shellQuote(s.sessionId) : "")
                    + profileArg(s.profileDir) + (host ? " --host " + shellQuote(host) : "") + configDirArgs + " # " + Date.now()
        replyDrafts[cmd] = { session: s, host: host || "", text: text }
        paneActions.connectSource(cmd)
    }

    Exec {
        id: paneActions
        onNewData: (source, data) => {
            disconnectSource(source)
            const draft = root.replyDrafts[source]
            delete root.replyDrafts[source]
            const asked = root.answerFor[source]
            delete root.answerFor[source]
            const result = root.helperResult(data)
            if (!result.ok) {
                root.actionError = result.message
                actionErrorTimer.restart()
                // (in tmux it asks something else now, or nothing: nothing was
                // pressed. Said in a notification while the popup is closed; the
                // next check makes that the notification of what it asks now)
                if (asked && result.changed === true && !root.dashboardShown) {
                    const s = asked.session
                    root.notify(root.petKeyOf(s, asked.host), s, "waiting", i18n("%1 doesn't ask that any more", s.name),
                                i18n("Nothing was answered. Open it to see what it asks now.") + "\n" + (s.cwdShort || "")
                                + (asked.host ? " · " + asked.host : ""), "dialog-warning", asked.host, true)
                }
            } else if (draft && result.how === "ask") {
                root.openPane(draft.session, draft.host, "chat", { draft: draft.text })   // (its terminal takes no text: you choose there)
            } else {
                if (draft && result.how === "vscode" && result.link)
                    root.openVscodeLink(draft.session.sessionId || draft.session.chatId, result.link, draft.host)
                root.actionError = ""
                if (result.message) {
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                }
            }
            root.refresh()
            if (asked && asked.host)
                root.pollHost(asked.host)   // (what it asks now there, as the pane does)
        }
    }

    // ---------------------------------------------------------------- opening a chat by its id
    // A chat found by the search, or the one that made a plan: its row when
    // it's listed, else reopened (in a terminal or VS Code, as the switch says)

    function hostGroups(host) {
        return host ? (remote[host] && remote[host].result ? remote[host].result.groups : []) : (status ? status.groups : [])
    }

    // The listed row of a chat (here, or on host), or null: on the account
    // given if it's there, else on any (a shared chat runs where it was opened)
    function listedRow(chatId, profileDir, host) {
        let other = null
        for (const g of hostGroups(host))
            for (const s of g.sessions)
                if (s.chatId === chatId || s.sessionId === chatId) {
                    if (!profileDir || g.profileKeys.indexOf(profileDir) >= 0)
                        return s
                    other = other || s
                }
        return other
    }

    function openChatById(chatId, profileDir, cwd, openCommand, groupId, host) {
        const row = listedRow(chatId, profileDir, host)
        if (row) {
            if (host)
                remoteShow(host, row)
            else
                jumpTo(row.sessionId, row.profileDir)
            return
        }
        const groupList = hostGroups(host)
        const group = groupList.find(g => g.id === groupId || g.profileKeys.indexOf(profileDir) >= 0) || null
        if (group && openInVscode(group, host, true)) {
            if (host)
                remoteResumeVscode(host, chatId, cwd)
            else
                resumeInVscode(chatId, profileDir)
        } else if (host)
            remoteOpen(host, openCommand)
        else
            jumpTo(chatId, profileDir)
    }

    // ---------------------------------------------------------------- finding a chat
    // The search at the top of the popup: every chat with all the words in its
    // name, folder or your prompts (talpy_den.py --find), here and on the
    // SSH hosts shown (remote.py --find), newest first.

    property bool searchOpen: false
    property string searchQuery: ""
    property var searchResults: ({})   // source ("" here, else the host) -> {busy, results, more, error}
    property var searchAsked: ({})     // command -> [source, query]
    // "<host>/<kind>" -> unfolded, as you clicked it (SearchResults.qml has
    // the defaults): a source (kind "source") and what it found of each kind
    property var searchFolds: ({})

    onSearchQueryChanged: searchTimer.restart()

    function searchShown(host, kind, otherwise) {
        const shown = searchFolds[host + "/" + kind]
        return shown === undefined ? otherwise : shown
    }

    function showFound(host, kinds, shown) {
        const next = Object.assign({}, searchFolds)
        for (const kind of kinds)
            next[host + "/" + kind] = shown
        searchFolds = next
    }

    Timer {
        id: searchTimer
        interval: 350
        onTriggered: root.runSearch()
    }

    function toggleSearch() {
        searchOpen = !searchOpen
        if (!searchOpen) {
            searchQuery = ""
            searchResults = ({})
            searchFolds = ({})
        }
    }

    function runSearch() {
        const query = searchQuery.trim()
        if (query.length < 2) {
            searchResults = ({})
            return
        }
        const next = {}
        const ask = (source, cmd) => {
            searchAsked[cmd] = [source, query]
            next[source] = Object.assign({ results: [], more: false, error: "" }, searchResults[source] || {}, { busy: true })
            finder.connectSource(cmd)
        }
        ask("", "python3 -I " + shellQuote(codeDir + "poll.py") + " --find " + shellQuote(query) + configDirArgs + " # " + Date.now())
        for (const host of shownHosts)
            ask(host, "python3 -I " + shellQuote(codeDir + "remote.py") + " --find " + shellQuote(host) + " " + shellQuote(query)
                      + " # " + Date.now())
        searchResults = next
    }

    Exec {
        id: finder
        onNewData: (source, data) => {
            disconnectSource(source)
            const asked = root.searchAsked[source]
            delete root.searchAsked[source]
            if (!asked || asked[1] !== root.searchQuery.trim())
                return   // an answer to what you looked for before
            const result = root.helperResult(data)
            // a host's times on this computer's clock (as toLocalClock puts its status)
            const offset = asked[0] && result.ok && result.generatedAt ? Date.now() - result.generatedAt : 0
            const local = (list, key) => (list || []).map(x => Math.abs(offset) < 5000 || typeof x[key] !== "number" ? x
                                                               : Object.assign({}, x, { [key]: x[key] + offset }))
            root.searchResults = Object.assign({}, root.searchResults, { [asked[0]]: {
                busy: false, results: result.ok ? local(result.results, "lastActive") : [], more: !!result.more,
                projects: result.ok ? local(result.projects, "lastActive") : [], plans: result.ok ? local(result.plans, "updatedAt") : [],
                memories: result.ok ? local(result.memories, "updatedAt") : [],
                error: result.ok ? "" : (result.message || result.error || i18n("no answer")) } })
        }
    }

    function openFound(result, host) {
        openChatById(result.sessionId, result.profileDir, result.cwd, result.openCommand || "", result.groupId, host)
    }

    // A project folder the search found: the new-chat box of the account its
    // newest chat is on opens, with that folder first
    property var newChatFolder: null   // {groupKey, path, short, newChatCommand}

    function openFoundProject(project, host) {
        const key = (host ? host + "/" : "") + project.groupId
        newChatFolder = { groupKey: key, path: project.folder, short: project.folderShort, newChatCommand: "" }
        planComposer = ""
        newChatGroup = key
        setFocusView(false)   // (the box is in its account's section, which the focus view leaves out)
        searchOpen = false
        searchQuery = ""
        searchResults = ({})
        searchFolds = ({})
    }

    // ---------------------------------------------------------------- the default account
    // Listed first, its usage in the panel, VS Code's Claude and plain claude
    // run on it. The right-click menu can pick another: accounts.py --default,
    // as the settings' Accounts page does, which refuses while the switch
    // would cut a chat off (one working in VS Code's Claude, or any running
    // through ~/.claude). It's said in a notification: the popup is closed then.

    readonly property var defaultChoices: status && status.canDefault === true && groups.length > 1
                                          ? groups.filter(g => !g.loggedOut && g.chatProfile) : []

    function makeDefault(group) {
        if (!group || group.defaultHere)
            return
        defaulter.connectSource("python3 -I " + shellQuote(codeDir + "accounts.py") + " --default " + shellQuote(group.chatProfile)
                                + configDirArgs + " # " + Date.now())
    }

    Exec {
        id: defaulter
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            root.notify("default-account", null, result.ok ? "started" : "error",
                        result.ok ? i18n("Default account") : i18n("The default account didn't change"),
                        result.message || i18n("no answer"), result.ok ? "user-identity" : "dialog-warning", "")
            root.refresh()
        }
    }

    // ---------------------------------------------------------------- the week
    // The popup's Recap tab (WeekView.qml): week.py reads your chats of 7 days
    // (only what their transcripts added since it last ran) when the tab opens,
    // you pick other days or click the popup's Refresh, then every 10 minutes
    // while it's in sight. The status checks never run it.

    property string popupTab: "chats"   // "chats", "week" (Recap) or "perms" (Permissions)
    property var weekRecap: null
    property bool weekBusy: false
    property string weekError: ""
    property string weekSpan: "week"  // "day", "week" (the last 7 days) or "all" (everything kept)
    property int weekBack: 0           // days (or weeks) before today's
    property string weekAccount: ""   // an account's id, or "" for all
    property string weekAsked: ""     // the command whose answer is awaited
    readonly property bool weekShown: popupTab === "week" && dashboardShown && !coveredByWindow
    readonly property string weekCurrency: Plasmoid.configuration.recapCurrency || "USD"

    onWeekShownChanged: {
        if (weekShown)
            loadWeek()
    }
    // (a new span starts at today's: both change at once, it reads once)
    onWeekSpanChanged: Qt.callLater(loadWeek)
    onWeekBackChanged: Qt.callLater(loadWeek)
    onWeekAccountChanged: Qt.callLater(loadWeek)
    onWeekCurrencyChanged: Qt.callLater(loadWeek)

    function setWeekSpan(span) {
        weekSpan = span
        weekBack = 0
    }

    Timer {
        interval: 600000   // 10 minutes
        repeat: true
        running: root.weekShown
        onTriggered: root.loadWeek()
    }

    // The Projects tab (ProjectsView.qml, week.py --projects): every project
    // with all its chats, plans and memories; read when the tab opens and
    // every 10 minutes while it shows (what goes on now comes from the
    // status). Each project is folded until you open it (kept while
    // Plasma runs); a project row of the Recap opens it here (showProject).
    property var openProjects: ({})   // project folder -> unfolded
    property string projectToShow: ""   // (opened from the Recap: scrolled to)
    function toggleProject(path, wasOpen) {
        openProjects = Object.assign({}, openProjects, { [path]: !wasOpen })
        if (wasOpen)
            for (const list of ["", "|plans", "|memories"])
                firstPage("project|" + path + list)
    }
    function showProject(path) {
        openProjects = Object.assign({}, openProjects, { [path]: true })
        projectToShow = path
        popupTab = "projects"
    }
    // A line's folder in a project: only its part below the project's folder
    // ("server" for ~/repos/api/server in ~/repos/api), nothing for the
    // project's folder itself; outside a project (or its folder), short
    function folderIn(folder, project, short) {
        if (!project || !folder)
            return short
        if (folder === project)
            return ""
        return folder.startsWith(project + "/") ? folder.slice(project.length + 1) : short
    }
    // The account (of this computer) a chat, plan or memory of a project is on
    function groupOfProfile(profileDir) {
        return groups.find(g => (g.profileKeys || []).indexOf(profileDir) >= 0) || groups[0] || emptyGroup
    }
    property var projectsData: null
    property string projectsError: ""
    property bool projectsBusy: false
    readonly property bool projectsShown: popupTab === "projects" && dashboardShown && !coveredByWindow
    onProjectsShownChanged: if (projectsShown) loadProjects()
    property bool projectsAgain: false  // read again once the read on its way is in (it may have read before a change)
    function loadProjects() {
        const cmd = "python3 -I " + shellQuote(codeDir + "week.py") + " --projects" + configDirArgs
        if (projectsReader.has(cmd)) {   // (the same command isn't run twice at once)
            projectsAgain = true
            return
        }
        projectsBusy = true
        projectsAgain = false
        projectsReader.connectSource(cmd)
    }
    Exec {
        id: projectsReader
        onNewData: (source, data) => {
            disconnectSource(source)
            root.projectsBusy = false
            const r = root.helperResult(data)
            if (r.ok) {
                root.projectsData = r
                root.projectsError = ""
            } else {
                root.projectsError = i18n("Couldn't read your projects: %1", r.error || r.message || i18n("no answer"))
            }
            if (root.projectsAgain)
                root.loadProjects()
        }
    }
    Timer {
        interval: 600000
        repeat: true
        running: root.projectsShown
        onTriggered: root.loadProjects()
    }
    // New chat here: the new-chat box of the account its newest chat is on (else its plans' or memories'), with
    // that folder first
    function newChatInProject(project) {
        const newest = project.chats[0] || (project.plans || [])[0] || (project.memories || [])[0] || null
        const g = groups.find(x => newest && (x.profileKeys || []).indexOf(newest.profileDir) >= 0) || groups[0]
        if (!g)
            return
        popupTab = "chats"
        newChatFolder = { groupKey: g.id, path: project.path, short: project.short, newChatCommand: "" }
        planComposer = ""
        newChatGroup = g.id
        setFocusView(false)   // (the box is in its account's section, which the focus view leaves out)
    }

    function loadWeek() {
        if (popupTab !== "week")
            return
        let cmd = "python3 -I " + shellQuote(codeDir + "week.py") + " --span " + weekSpan + " --back " + weekBack
        if (weekAccount)
            cmd += " --account " + shellQuote(weekAccount)
        if (weekCurrency !== "USD")
            cmd += " --currency " + shellQuote(weekCurrency)
        for (const host of shownHosts)   // (the ones that answered their last check: no waiting on one out of reach)
            if (remote[host] && remote[host].result && !remote[host].error)
                cmd += " --host " + shellQuote(host)
        weekAsked = cmd + configDirArgs + " # " + Date.now()
        weekBusy = true
        weekReader.connectSource(weekAsked)
    }

    Exec {
        id: weekReader
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source !== root.weekAsked)
                return   // an answer to days you asked for before
            root.weekBusy = false
            const result = root.helperResult(data)
            if (result.ok) {
                root.weekRecap = result
                root.weekError = ""
            } else {
                root.weekError = result.message || result.error || i18n("no answer")
            }
            if (root.limitsOpen && root.weekBack === 0)
                root.loadLimits()   // (read again with the Recap while unfolded)
        }
    }

    // The Recap's Advanced analyses (WeekView.qml, week.py --limits): how much
    // a full window of each account's plan held, week by week. Folded until
    // you open it (kept while Plasma runs), read then and with each read of
    // the Recap while open. limitsData is the answer for limitsAccount.
    property bool limitsOpen: false
    property var limitsData: null
    property string limitsAccount: ""
    property string limitsError: ""
    property string limitsAsked: ""
    function toggleLimits() {
        limitsOpen = !limitsOpen
        if (limitsOpen)
            loadLimits()
    }
    function loadLimits() {
        let cmd = "python3 -I " + shellQuote(codeDir + "week.py") + " --limits"
        if (weekAccount)
            cmd += " --account " + shellQuote(weekAccount)
        if (weekCurrency !== "USD")
            cmd += " --currency " + shellQuote(weekCurrency)
        limitsAsked = cmd + configDirArgs + " # " + weekAccount + " " + Date.now()
        limitsReader.connectSource(limitsAsked)
    }

    Exec {
        id: limitsReader
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source !== root.limitsAsked)
                return   // an answer for another account
            const result = root.helperResult(data)
            root.limitsAccount = source.slice(source.lastIndexOf(" # ") + 3).split(" ")[0]
            if (result.ok) {
                root.limitsData = result
                root.limitsError = ""
            } else {
                root.limitsError = result.message || result.error || i18n("no answer")
            }
        }
    }

    // ---------------------------------------------------------------- permissions
    // The popup's Permissions tab (PermsView.qml): week.py --permissions
    // reads the permissions you gave (your settings, the .claude settings of
    // the folders Claude ran in) and the permission prompts you answered in
    // the last 7 days when the tab opens, then every 10 minutes while it's in
    // sight. Allow, Undo and Revoke change one entry of a settings file.

    property var permsData: null
    property bool permsBusy: false
    property string permsError: ""
    readonly property bool permsShown: popupTab === "perms" && dashboardShown && !coveredByWindow
    readonly property bool suggestRules: Plasmoid.configuration.recapRules   // suggest rules for the prompts you answered
    property string ruleBusy: ""     // the rule being written or taken back: host|id
    property string ruleHost: ""     // where the last one was: an SSH host, or "" (this computer)
    property string ruleMessage: ""  // what the last one did
    property bool ruleRevoked: false // (the last one revoked a permission you gave: its message goes there)
    property bool ruleFailed: false  // (the last one changed nothing: its message is an error)

    onPermsShownChanged: {
        if (permsShown)
            loadPerms()
    }

    Timer {
        interval: 600000   // 10 minutes
        repeat: true
        running: root.permsShown
        onTriggered: root.loadPerms()
    }

    property string permsAsked: ""   // the read whose answer is awaited (one given up on is left out)
    property real permsAskedAt: 0
    property bool permsAgain: false  // read again once that's in (a rule changed meanwhile)
    // (a read or a change whose answer never comes is given up after this)
    readonly property int permsStaleMs: 300000

    function loadPerms() {
        if (popupTab !== "perms" || (permsBusy && Date.now() - permsAskedAt < permsStaleMs))
            return
        permsBusy = true
        permsAgain = false
        let cmd = "python3 -I " + shellQuote(codeDir + "week.py") + " --permissions"
        for (const host of shownHosts)   // (the ones that answered their last check: no waiting on one out of reach)
            if (remote[host] && remote[host].result && !remote[host].error)
                cmd += " --host " + shellQuote(host)
        permsAsked = cmd + configDirArgs + " # " + Date.now()
        permsAskedAt = Date.now()
        permsReader.connectSource(permsAsked)
    }

    Exec {
        id: permsReader
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source !== root.permsAsked)
                return   // a read given up on: a newer one is on its way
            root.permsBusy = false
            const result = root.helperResult(data)
            if (result.ok) {
                root.permsData = result
                root.permsError = ""
            } else {
                root.permsError = result.message || result.error || i18n("no answer")
            }
            if (root.permsAgain)
                root.loadPerms()
        }
    }

    // A rule the Permissions tab offers for prompts you answered: allow
    // (into the chats' folder's .claude/settings.local.json), or take back
    // one it added
    function changeRule(rule, allow, host) {
        let cmd = "python3 -I " + shellQuote(codeDir + "week.py")
        cmd += allow ? " --allow " + shellQuote(rule.kind) + " " + shellQuote(rule.value) + " " + shellQuote(rule.project)
                     : " --undo " + shellQuote(rule.id)
        if (host)
            cmd += " --on " + shellQuote(host)   // (week.py runs there)
        ruleBusy = (host || "") + "|" + rule.id
        ruleHost = host || ""
        ruleMessage = ""
        ruleRevoked = false
        writeRule(cmd + " # " + Date.now())
    }

    // Takes one of the permissions you gave (what lets chats go without
    // asking) out of its file
    function revokeGrant(grant, host) {
        ruleBusy = (host || "") + "|" + grant.id
        ruleHost = host || ""
        ruleMessage = ""
        ruleRevoked = true
        writeRule("python3 -I " + shellQuote(codeDir + "week.py") + " --revoke " + shellQuote(grant.id)
                  + (host ? " --on " + shellQuote(host) : configDirArgs) + " # " + Date.now())
    }

    property string ruleAsked: ""   // the change whose answer is awaited (ruleBusy)

    function writeRule(cmd) {
        ruleAsked = cmd
        ruleStale.restart()
        ruleWriter.connectSource(cmd)
    }

    // (a change whose answer never comes: the buttons work again)
    Timer {
        id: ruleStale
        interval: root.permsStaleMs
        onTriggered: root.ruleBusy = ""
    }

    Exec {
        id: ruleWriter
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source === root.ruleAsked) {   // (not one given up on: it says nothing of the one now)
                root.ruleBusy = ""
                ruleStale.stop()
                const result = root.helperResult(data)
                root.ruleFailed = !result.ok
                root.ruleMessage = result.ok ? result.message || "" : i18n("Nothing changed: %1", result.message || i18n("no answer"))
            }
            root.permsAgain = true   // (a read on its way may have read the file before)
            root.loadPerms()
        }
    }

    // ---------------------------------------------------------------- plans
    // Plans (<config>/plans/*.md, what chats in plan mode write), in their
    // project (the Projects tab) and under ★ Starred plans: open one, carry
    // it out in a new chat, continue the chat that made it, or share it with
    // your other accounts.

    property string planComposer: ""   // the plan whose "carry it out" box is open: [host|]plan key

    // ---------------------------------------------------------------- starred chats and plans
    // Chats and plans you star stay at hand: each account lists its starred
    // ones under ★ Starred chats and ★ Starred plans, however old they are
    // (jump.py --star, kept in Talpy Den's cache; an SSH host's too, kept here).

    property var expandedStarred: ({})   // groupKey + "|chats" or "|plans" -> unfolded

    function toggleStarred(key, wasOpen) {
        expandedStarred = Object.assign({}, expandedStarred, { [key]: !wasOpen })
        if (wasOpen)
            firstPage(key)
    }

    property var starRuns: ({})   // command -> the host whose chat or plan it stars ("": here)

    // kind: "chats" (id: the chat's) or "plans" (id: the plan's slug)
    function setStar(kind, id, host, on) {
        if (!id)
            return
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " "
                    + (kind === "plans" ? (on ? "--star-plan " : "--unstar-plan ") : (on ? "--star " : "--unstar "))
                    + shellQuote(id) + (host ? " --host " + shellQuote(host) : "") + configDirArgs + " # " + Date.now()
        starRuns[cmd] = host || ""
        starrer.connectSource(cmd)
    }

    function starHint(kind, starred) {
        return starred ? i18n("Click to unstar it.")
                       : kind === "plans" ? i18n("A starred plan stays listed under its account's ★ Starred plans, however old it is.")
                                          : i18n("A starred chat stays listed under its account's ★ Starred chats, however old it is.")
    }

    Exec {
        id: starrer
        onNewData: (source, data) => {
            disconnectSource(source)
            const host = root.starRuns[source] || ""
            delete root.starRuns[source]
            const result = root.helperResult(data)
            if (!result.ok) {
                root.actionError = i18n("Couldn't star it: %1", result.message)
                actionErrorTimer.restart()
            }
            if (host)
                root.pollHost(host)
            else
                root.refresh()
            if (!host && root.projectsShown)
                root.loadProjects()
        }
    }

    // A memory's icon by its kind (talpy_den.py: account_memories)
    function memoryIcon(type) {
        return Icons.plasma[Icons.memoryMeaning(type)]
    }

    // One of Claude's memories: rendered to read, or (edit) its file, to change
    // it (jump.py --open-memory / --edit-memory; an SSH host's in VS Code)
    function openMemory(memory, host, edit) {
        planOpener.connectSource("python3 -I " + shellQuote(codeDir + "jump.py")
                                 + (host ? " --remote-edit " + shellQuote(host) + " " + shellQuote(memory.path)
                                         : (edit ? " --edit-memory " : " --open-memory ") + shellQuote(memory.path))
                                 + configDirArgs + " # " + Date.now())
    }

    function togglePlanComposer(key) {
        planComposer = planComposer === key ? "" : key
        newChatGroup = ""
    }

    // A plan's Markdown file itself, to change it (jump.py --edit-plan; an
    // SSH host's in VS Code over Remote-SSH: --remote-edit)
    function editPlan(plan, host) {
        planOpener.connectSource("python3 -I " + shellQuote(codeDir + "jump.py")
                                 + (host ? " --remote-edit " + shellQuote(host) + " " + shellQuote(plan.path)
                                         : " --edit-plan " + shellQuote(plan.slug) + profileArg(plan.profileDir))
                                 + configDirArgs + " # " + Date.now())
    }

    function openPlan(slug, profileDir, host) {
        if (host)
            remoteAction("plan", host, "--plan " + shellQuote(host) + " " + shellQuote(slug)
                                       + (profileDir ? " " + shellQuote(profileDir) : ""))
        else
            planOpener.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --open-plan " + shellQuote(slug)
                                     + profileArg(profileDir) + configDirArgs + " # " + Date.now())
    }

    Exec {
        id: planOpener
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok) {
                root.actionError = ""
                root.expanded = false
            } else {
                root.actionError = i18n("Couldn't open it: %1", result.message)
                actionErrorTimer.restart()
            }
        }
    }

    // Your changes to a plan (its file, since Claude wrote it), sent to the
    // chat that made it, which revises the plan in plan mode (jump.py
    // --plan-feedback): it reopens with them, gets them typed in (tmux), or
    // they go to the clipboard and the chat comes up, to paste them there
    function sendPlanFeedback(slug, profileDir, chatId) {
        feedbackSender.connectSource("python3 -I " + shellQuote(codeDir + "jump.py") + " --plan-feedback " + shellQuote(slug)
                                     + profileArg(profileDir) + " --chat " + shellQuote(chatId) + configDirArgs + " # " + Date.now())
    }

    Exec {
        id: feedbackSender
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (!result.ok) {
                root.actionError = i18n("Couldn't send your feedback: %1", result.message)
                actionErrorTimer.restart()
                return
            }
            root.actionError = ""
            if (result.how === "clipboard" && !result.copied && result.text)
                root.copyText(result.text)
            root.actionInfo = result.message
            actionInfoTimer.restart()
            if (result.how === "clipboard")   // (the chat came up: say what to do there)
                root.notify("feedback|" + Date.now(), null, "feedback", i18n("Your feedback on the plan"), result.message, "mail-send", "")
            root.refresh()
        }
    }

    // Text on the clipboard, where no clipboard tool is (jump.py: copy_to_clipboard)
    TextEdit {
        id: clipboardText
        visible: false
    }

    function copyText(text) {
        clipboardText.text = text
        clipboardText.selectAll()
        clipboardText.copy()
        clipboardText.text = ""
    }

    function continuePlanChat(plan, group, host) {
        openChatById(plan.chatId, plan.chatProfileDir, plan.cwd, plan.openCommand || "", group.id, host)
    }

    PlasmaExtras.Menu {
        id: planMenu
    }

    Component {
        id: planItem
        PlasmaExtras.MenuItem {
            property string kind      // share | keeponly
            property string slug
            property string from      // the profile whose copy it is
            property string to        // share: only with this one ("": all); keeponly: the one it stays on
            property string host
            onClicked: root.planShare(kind, slug, from, to, host)
        }
    }

    property var planItems: []

    function openPlanMenu(button, plan, host) {
        planMenu.clearMenuItems()
        const accounts = shareAccountsOf(host)
        const here = accounts.find(g => g.profileKeys.indexOf(plan.profileDir) >= 0) || null
        const items = [planItem.createObject(planMenu, { section: true, text: plan.title })]
        for (const g of accounts)
            if (g !== here)
                items.push(planItem.createObject(planMenu, { text: i18n("Share with %1", g.title), icon: Icons.plasma.share,
                                                            kind: "share", slug: plan.slug, from: plan.profileDir,
                                                            to: g.shareProfile, host: host }))
        if (accounts.length > 2)
            items.push(planItem.createObject(planMenu, { text: i18n("Share with all accounts"), icon: Icons.plasma.share,
                                                        kind: "share", slug: plan.slug, from: plan.profileDir, to: "", host: host }))
        if (plan.shared) {
            items.push(planItem.createObject(planMenu, { separator: true }))
            for (const g of accounts)
                items.push(planItem.createObject(planMenu, { text: i18n("Keep only on %1", g.title), icon: Icons.plasma.moveTo,
                                                            kind: "keeponly", slug: plan.slug, from: plan.profileDir,
                                                            to: g.shareProfile, host: host }))
        }
        for (const item of items)
            planMenu.addMenuItem(item)
        planItems = items
        planMenu.visualParent = button
        planMenu.openRelative()
    }

    function planShare(kind, slug, from, to, host) {
        if (host) {
            // remote.py --share-plan HOST SLUG PROFILE [TO] | --unshare-plan HOST SLUG PROFILE
            remoteAction("share", host, (kind === "share" ? "--share-plan " : "--unshare-plan ") + shellQuote(host) + " "
                         + shellQuote(slug) + " " + shellQuote(kind === "share" ? from : to)
                         + (kind === "share" && to ? " " + shellQuote(to) : ""))
            return
        }
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py")
                    + (kind === "share" ? " --share-plan " + shellQuote(slug) + profileArg(from) + (to ? " --to " + shellQuote(to) : "")
                                        : " --unshare-plan " + shellQuote(slug) + profileArg(to))
                    + configDirArgs + " # " + Date.now()
        shareKinds = Object.assign({}, shareKinds, { [cmd]: "share" })
        sharer.connectSource(cmd)
    }

    // ---------------------------------------------------------------- new chats with a task
    // The + box (and a plan's "carry it out" box, NewChatBox.qml) takes what
    // Claude should do: the chat starts with it in a terminal (sent at once),
    // in VS Code (typed in for you to send) or in the background (claude
    // --bg: no window, listed right away). One box is open at a time, so its
    // text lives here, kept until a chat starts.

    property string taskText: ""
    property bool taskBackground: false
    // or later: on a day (0 today, 1 tomorrow, …) at a time ("14:30")
    property bool taskLater: false
    property int taskLaterDay: 0
    property string taskLaterTime: ""

    // The days a task can start on: today and the next six
    function laterDays() {
        const out = []
        for (let i = 0; i < 7; i++) {
            const d = new Date()
            d.setDate(d.getDate() + i)
            out.push(i === 0 ? i18n("Today") : i === 1 ? i18n("Tomorrow") : Qt.locale().toString(d, "ddd d MMM"))
        }
        return out
    }

    // When a task picked for later starts (ms): on day at clock ("9", "930",
    // "9:30", "14:30"); 0 for no time, or one that has passed
    // (a time it can read: 24-hour, 14:30, 1430 or 14)
    function laterClock(clock) {
        const m = /^(\d{1,2})(?::?(\d{2}))?$/.exec((clock || "").trim())
        return m && +m[1] <= 23 && +(m[2] || 0) <= 59 ? m : null
    }
    function laterAt(day, clock) {
        const m = laterClock(clock)
        if (!m)
            return 0
        const d = new Date()
        d.setDate(d.getDate() + day)
        d.setHours(+m[1], +(m[2] || 0), 0, 0)
        return d.getTime() > Date.now() ? d.getTime() : 0
    }

    // Ticking "Later, at": the next full hour, to change
    function pickLater(on) {
        taskLater = on
        if (!on)
            return
        taskQueued = false
        if (laterAt(taskLaterDay, taskLaterTime))
            return
        const d = new Date()
        d.setHours(d.getHours() + 1, 0, 0, 0)
        taskLaterDay = d.getDate() === new Date().getDate() ? 0 : 1
        taskLaterTime = Qt.locale("C").toString(d, "HH:mm")
    }

    // Days from today to the day of ms (0 today, 1 tomorrow)
    function daysAway(ms) {
        const d = new Date(ms), today = new Date()
        return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate())
                           - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000)
    }

    // When a queued task starts, in words: "14:30" today, "tomorrow 09:00", "Fri 24 Oct 09:00"
    function startText(ms) {
        const days = daysAway(ms)
        return days <= 0 ? clockText(ms)
             : days === 1 ? i18nc("a time tomorrow", "tomorrow %1", clockText(ms))
             : Qt.locale().toString(new Date(ms), "ddd d MMM") + " " + clockText(ms)
    }

    // When a usage limit resets, for the tooltips of its "resets in …"
    function resetAtText(ms) {
        const days = daysAway(ms)
        return days <= 0 ? i18n("Resets at %1", clockText(ms))
             : days === 1 ? i18n("Resets tomorrow at %1", clockText(ms))
             : i18n("Resets on %1 at %2", Qt.locale().toString(new Date(ms), "ddd d MMM"), clockText(ms))
    }

    function startChat(group, host, folder, inVscode, plan) {
        const text = taskText.trim()
        const hasTask = text !== "" || !!plan
        const background = taskBackground && hasTask
        const reset = background && taskQueued ? limitReset(group, host) : null
        const later = background && taskLater ? laterAt(taskLaterDay, taskLaterTime) : 0
        if (background && taskLater && !later) {
            actionError = i18n("Pick a time that's still to come, e.g. 14:30.")
            actionErrorTimer.restart()
            return
        }
        const draft = text ? { text: taskText, background: taskBackground, queued: taskQueued, later: taskLater,
                                group: newChatGroup, plan: planComposer } : null
        newChatGroup = ""
        planComposer = ""
        taskText = ""
        taskBackground = false
        taskQueued = false
        taskLater = false
        pictureOffer = null
        if (reset || later) {
            // to start a minute after the limit resets, or at the time picked
            if (!folder.path && !host)
                root.expanded = false   // the folder dialog takes over
            const queue = "python3 -I " + shellQuote(codeDir + "jump.py") + " --queue " + shellQuote(group.chatProfile)
                          + (folder.path || host ? " --cwd " + shellQuote(folder.path || "~") : " --choose-folder")
                          + " --at " + (later || Math.round(reset.at + 60000)) + (later ? " --scheduled" : "")
                          + (text ? " --prompt " + shellQuote(text) : "")
                          + (plan ? " --plan " + shellQuote(plan.slug) + " --plan-profile " + shellQuote(plan.profileDir) : "")
                          + (host ? " --host " + shellQuote(host) : "") + " --account " + shellQuote(group.title)
                          + chatOptions + configDirArgs + " # " + Date.now()
            keepDraft(queue, draft)
            queuer.connectSource(queue)
            return
        }
        if (host) {
            if (background || (hasTask && !inVscode)) {
                // remote.py --task HOST PROFILE FOLDER [--prompt TEXT] [--plan SLUG PROFILE] [--model M] [--effort E]
                //           [--permission-mode MODE] [--bg]
                keepDraft(remoteAction(background ? "task" : "open", host, "--task " + shellQuote(host) + " " + shellQuote(group.chatProfile)
                                       + " " + shellQuote(folder.path || "~") + (text ? " --prompt " + shellQuote(text) : "")
                                       + (plan ? " --plan " + shellQuote(plan.slug) + " " + shellQuote(plan.profileDir) : "")
                                       + chatOptions + (background ? " --bg" : "")), draft)
            } else if (inVscode) {
                keepDraft(remoteNewChatVscode(host, folder.path, group, text, plan), draft)
            } else {
                // (the host's command ends with claude itself: its options go after it)
                remoteNewChat(host, folder.newChatCommand ? folder.newChatCommand + chatOptions : folder.newChatCommand)
            }
            return
        }
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --new-chat " + shellQuote(group.chatProfile)
                    + (folder.path ? " --cwd " + shellQuote(folder.path) : " --choose-folder")
                    + (background ? " --bg" : inVscode ? " --vscode" : "")
                    + (text ? " --prompt " + shellQuote(text) : "")
                    + (plan ? " --plan " + shellQuote(plan.slug) + " --plan-profile " + shellQuote(plan.profileDir) : "")
                    + (background || !inVscode ? chatOptions : "") + configDirArgs + " # " + Date.now()
        if (!folder.path)
            root.expanded = false   // the folder dialog takes over
        keepDraft(cmd, draft)
        if (background)
            taskStarter.connectSource(cmd)
        else
            launcher.connectSource(cmd)
    }

    // What you wrote for a chat that's starting, by the command that starts
    // it: it comes back when the chat can't start, not to be typed again
    property var taskDrafts: ({})

    function keepDraft(cmd, draft) {
        if (draft)
            taskDrafts = Object.assign({}, taskDrafts, { [cmd]: draft })
    }

    // cmd's answer came: if it failed, its task is back in the box (opened
    // again if the popup shows no other), unless you've begun another
    function draftBack(cmd, ok) {
        const draft = taskDrafts[cmd]
        if (!draft)
            return
        const rest = Object.assign({}, taskDrafts)
        delete rest[cmd]
        taskDrafts = rest
        if (ok || taskText.trim() !== "")
            return
        taskText = draft.text
        taskBackground = draft.background
        taskQueued = draft.queued
        taskLater = draft.later
        if (root.expanded && !newChatGroup && !planComposer) {
            newChatGroup = draft.group
            planComposer = draft.plan
        }
    }

    // A task started in the background: the popup stays, and its row comes up
    Exec {
        id: taskStarter
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            root.draftBack(source, result.ok)
            if (result.ok) {
                root.actionError = ""
                if (result.message) {
                    root.actionInfo = result.message
                    actionInfoTimer.restart()
                }
            } else {
                root.actionError = i18n("Couldn't start it: %1", result.message)
                actionErrorTimer.restart()
            }
            root.refresh()
        }
    }

    // A picture pasted into the task or into a reply in the chat pane
    // (jump.py --paste-image saves the clipboard's): the box it's for (target
    // "task", or a chat window's "pane:host|chatId") puts it in where you are typing. For an SSH host's
    // chat it's copied there first, once you say so (remote.py --put-image):
    // pictureOffer is the one that box asks about.
    signal imagePasted(string path, string target)
    signal paneNote(string target, string message)   // (why a picture didn't come, said in that pane: the popup may be closed)
    property var pasteFor: ({})   // a paste's command: { host ("": here), target }
    property var pictureOffer: null   // { host, path, target }
    property string pictureCopyingTo: ""
    property string pictureCopyTarget: ""
    property var pictureCopies: ({})   // a copy's path on its host: the picture here (for its thumbnail)
    function pasteImage(host, target) {
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --paste-image # " + Date.now()
        pasteFor[cmd] = { host: host || "", target: target || "task" }
        imagePaster.connectSource(cmd)
    }
    // A region of the screen you pick (jump.py --screenshot), or files dropped
    // on a box (jump.py --attach): a picture goes in as a pasted one does;
    // any other file is named in the text (fileAttached), for this
    // computer's chats only (it isn't on an SSH host)
    signal fileAttached(string path, string target)
    function takeScreenshot(host, target) {
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --screenshot # " + Date.now()
        pasteFor[cmd] = { host: host || "", target: target || "task" }
        imagePaster.connectSource(cmd)
    }
    // The pane's + : files from the desktop's file dialog, opening in the
    // chat's folder, attached as dropped ones
    function pickFiles(host, target, folder) {
        const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --pick-files " + shellQuote(host ? "" : folder || "")
        pickFor[cmd] = { host: host || "", target: target || "task" }
        filePicker.connectSource(cmd)
    }
    property var pickFor: ({})
    Exec {
        id: filePicker
        onNewData: (source, data) => {
            disconnectSource(source)
            const pick = root.pickFor[source] || { host: "", target: "task" }
            delete root.pickFor[source]
            const result = root.helperResult(data)
            if (result.ok)
                root.attachFiles(result.paths || [], pick.host, pick.target)
            else if (pick.target.indexOf("pane:") === 0)
                root.paneNote(pick.target, result.message || "")
        }
    }
    function attachFiles(paths, host, target) {
        paths.forEach((path, i) => {
            const cmd = "python3 -I " + shellQuote(codeDir + "jump.py") + " --attach " + shellQuote(path) + " # " + Date.now() + "." + i
            pasteFor[cmd] = { host: host || "", target: target || "task" }
            imagePaster.connectSource(cmd)
        })
    }
    function copyPicture() {
        const offer = pictureOffer
        pictureOffer = null
        pictureCopyingTo = offer.host
        pictureCopyTarget = offer.target
        pictureCopier.connectSource("python3 -I " + shellQuote(codeDir + "remote.py") + " --put-image " + shellQuote(offer.host)
                                    + " " + shellQuote(offer.path) + " # " + Date.now())
    }
    Exec {
        id: imagePaster
        onNewData: (source, data) => {
            disconnectSource(source)
            const paste = root.pasteFor[source] || { host: "", target: "task" }
            delete root.pasteFor[source]
            const result = root.helperResult(data)
            if (result.ok && result.picture === false) {   // (a file, named where it is)
                if (paste.host) {
                    root.actionError = i18n("Only pictures go to %1's chat (copied there): that file is on this computer", hostLabel(paste.host))
                    actionErrorTimer.restart()
                    if (paste.target.indexOf("pane:") === 0)
                        root.paneNote(paste.target, root.actionError)
                } else {
                    root.fileAttached(result.path, paste.target)
                }
            } else if (!result.ok || !result.path) {
                if (result.message !== "No screenshot taken") {   // (you cancelled it)
                    root.actionError = result.message
                    actionErrorTimer.restart()
                    if (paste.target.indexOf("pane:") === 0)
                        root.paneNote(paste.target, result.message)
                }
            } else if (paste.host) {
                root.pictureOffer = { host: paste.host, path: result.path, target: paste.target }
            } else {
                root.imagePasted(result.path, paste.target)
            }
        }
    }
    Exec {
        id: pictureCopier
        onNewData: (source, data) => {
            disconnectSource(source)
            const result = root.helperResult(data)
            if (result.ok && result.path) {
                root.pictureCopies = Object.assign({}, root.pictureCopies, { [result.path]: result.local })
                root.imagePasted(result.path, root.pictureCopyTarget)
            } else {
                root.actionError = i18n("Couldn't copy the picture to %1: %2", root.pictureCopyingTo, result.message)
                actionErrorTimer.restart()
                if (root.pictureCopyTarget.indexOf("pane:") === 0)
                    root.paneNote(root.pictureCopyTarget, root.actionError)
            }
            root.pictureCopyingTo = ""
        }
    }

    function reasonText(reason) {
        switch (reason) {
        case "permission": return i18n("Asks for permission")
        case "question": return i18n("Has a question for you")
        case "network access": return i18n("Asks for network access")
        case "goal approval": return i18n("Proposes a goal")
        case "": return i18n("Waiting for you")
        default: return reason
        }
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'"
    }

    function stateColor(state) {
        switch (state) {
        case "waiting": return Kirigami.Theme.neutralTextColor
        case "working": return Kirigami.Theme.focusColor   // the accent (highlightColor is a pale selection tint)
        case "idle":
        case "done": return Kirigami.Theme.positiveTextColor
        case "limit": return Kirigami.Theme.negativeTextColor
        default: return Kirigami.Theme.disabledTextColor
        }
    }

    // a chat's dot's color, as its row's: red when it failed or a usage limit (or an expired login)
    // stopped it and the limit hasn't reset, else its state's
    function rowColor(s) {
        return s && (s.reason === "failed" || (s.stopped && !s.stopped.over)) ? Kirigami.Theme.negativeTextColor
             : root.stateColor(s ? s.state : "idle")
    }

    function usageColor(pct) {
        if (pct >= 90)
            return Kirigami.Theme.negativeTextColor
        if (pct >= 70)
            return Kirigami.Theme.neutralTextColor
        return Kirigami.Theme.focusColor
    }

    function duration(ms) {
        const m = Math.max(0, Math.round(ms / 60000))
        if (m < 60)
            return i18nc("duration in minutes", "%1m", m)
        const h = Math.floor(m / 60)
        if (h < 24)
            return i18nc("duration in hours and minutes", "%1h %2m", h, m % 60)
        return i18nc("duration in days and hours", "%1d %2h", Math.floor(h / 24), h % 24)
    }

    // How long ago, for the lists' ages: "just now" under a minute, not "0m ago"
    function ago(ms) {
        return ms < 60000 ? i18nc("how long ago: under a minute", "just now") : i18nc("how long ago", "%1 ago", duration(ms))
    }

    function resetText(window) {
        if (window.reset)
            return i18n("reset")
        if (!window.resetsAt)
            return ""
        // The last minute reads "<1m": a rounded "0m" looked stuck
        return i18n("resets in %1", window.resetsAt - now < 60000 ? i18nc("less than a minute", "<1m")
                                                                   : duration(window.resetsAt - now))
    }

    // The usage bar's tooltip: the pace, and where it leads (usage_forecast)
    function forecastText(f, pct, resetsAt) {
        if (!f)
            return ""
        const when = ms => {
            const d = new Date(ms)
            const time = d.toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
            return ms - now > 20 * 3600000 ? d.toLocaleDateString(Qt.locale(), "ddd") + " " + time : time
        }
        const lines = [f.basis === "hour" ? i18n("Your pace over the last hour: %1% an hour.", f.rate.toFixed(1))
                                          : i18n("Your pace in this window so far: %1% an hour.", f.rate.toFixed(1))]
        if (f.fullAt)
            lines.push(i18n("At this pace it runs out at %1, %2 before it resets.", when(f.fullAt), duration(resetsAt - f.fullAt)))
        else if (pct < 100)
            lines.push(i18n("At this pace: about %1% when it resets (the faded part of the bar).", Math.round(f.atReset)))
        lines.push(i18n("An even pace through the window would be at %1% by now (the mark).", Math.round(f.evenPct)))
        return lines.join("\n")
    }

    function stateText(s) {
        const since = s.since ? " · " + duration(now - s.since) : ""
        const reason = s.reason ? " · " + s.reason : ""
        if (s.stopped && (s.state === "idle" || s.state === "done")) {
            if (s.stopped.kind === "login")
                return i18n("Login expired")
            if (s.stopped.over)
                return i18n("Limit reset · go on")
            return s.stopped.resetsAt ? i18n("Limit · resets in %1", s.stopped.resetsAt - now < 60000
                                             ? i18nc("less than a minute", "<1m") : duration(s.stopped.resetsAt - now))
                                      : i18n("Hit a usage limit")
        }
        switch (s.state) {
        case "waiting": return i18n("Needs input") + reason
        case "working": return i18n("Working") + reason + since
        case "done":
            return (s.reason === "failed" ? i18n("Failed") : s.reason === "stopped" ? i18n("Stopped") : i18n("Done")) + since
        default: return i18n("Idle") + since
        }
    }

    // (the unit by what it rounds to: 999,960 is "1.0M", not "1000.0k")
    function formatTokens(n) {
        if (n >= 999.95e6)
            return (n / 1e9).toFixed(1) + "B"
        if (n >= 999.95e3)
            return (n / 1e6).toFixed(1) + "M"
        if (n >= 1e3)
            return (n / 1e3).toFixed(1) + "k"
        return String(n)
    }

    function summaryText() {
        const parts = []
        if (counts.waiting)
            parts.push(i18np("%1 needs input", "%1 need input", counts.waiting))
        if (counts.working)
            parts.push(i18np("%1 working", "%1 working", counts.working))   // plural forms differ in other languages
        if (counts.idle)
            parts.push(i18np("%1 idle", "%1 idle", counts.idle))
        if (counts.limit)
            parts.push(i18np("%1 at the usage limit", "%1 at the usage limit", counts.limit))
        if (counts.done)
            parts.push(i18np("%1 done", "%1 done", counts.done))
        return parts.length ? parts.join(" · ") : i18n("No chats running")
    }

    function tooltipText() {
        if (errorText && !status)
            return errorText
        const lines = [summaryText()]
        for (const g of allGroups) {
            if (!g.limits)
                continue
            lines.push((g.host ? hostLabel(g.host) + ": " : "") + g.title + ": "
                       + g.limits.windows.map(w => w.label + " " + Math.round(w.pct) + "%").join(" · "))
        }
        for (const host of shownHosts)
            if (remote[host] && remote[host].error)
                lines.push(i18n("%1: not reachable", hostLabel(host)))
        return lines.join("\n")
    }
}
