pragma Singleton
import QtQuick

// One status check for every copy of the widget in plasmashell (panel,
// tray, one per desktop…): Plasma runs them all in one QML engine, where a
// singleton is shared, so talpy_den.py runs once per interval instead of
// once per copy, and so does each SSH host's check (remote.py --status). Each
// copy says what it wants (want: a command and how often) and gets every
// answer to it (output). Copies with other settings (a moment while shared
// settings spread) get their own runs.
QtObject {
    id: hub

    // copy id -> {since, popup, wants: {key: {command, interval, named}}}; key
    // is what the command is to the copy ("status", "ssh:<host>"); popup false:
    // shown in place on the desktop, with no popup to open
    property var copies: ({})
    // The copy that sends the notifications and plays the sounds: the one
    // here longest, but one with a popup before one shown in place on the
    // desktop (what a notification opens shows up there, not under your
    // windows); a lone copy whatever it is. Across programs (another
    // plasmashell, a test window), talpy_den.py --instance still picks one
    // (notifier in its answer).
    property string leaderId: ""
    // The name these copies go by in talpy_den.py's election: the first
    // copy's, kept when that copy goes, so the others keep notifying
    property string instanceName: ""
    property var running: ({})       // full command line -> command
    property var lastStart: ({})     // command -> ms
    property var lastOutput: ({})    // command -> {stdout, stderr}
    property var again: ({})         // command -> true: run it again once it's done (something changed meanwhile)
    // A check whose answer never came (plasmashell lost it) is given up after
    // this long and run again; else it would count as still running for good,
    // and the widget would show what it saw last until plasmashell restarts.
    // (live.py waits up to 50 s by itself.)
    readonly property int staleMs: 60000
    readonly property int liveStaleMs: 120000

    signal output(string command, string stdout, string stderr)

    // One parse of an answer for all the copies that take it: each gets the
    // same object, which none of them changes (three copies parsed the same
    // quarter of a megabyte at every check)
    readonly property var parsedMemo: ({ text: "", value: null })   // (changed in place)
    function parse(text) {
        if (parsedMemo.text !== text || parsedMemo.value === null) {
            const value = JSON.parse(text)   // (throws as JSON.parse does)
            parsedMemo.text = text
            parsedMemo.value = value
        }
        return parsedMemo.value
    }
    signal started(string command)   // (an SSH host shows "connecting…" meanwhile)
    // What the chats do right now, between checks (live.py's answer: the live hook's files that changed)
    signal live(var views)

    // named: the status check, which says which copy asks (--instance)
    function want(id, key, command, interval, named) {
        const copy = copies[id] || (copies[id] = { since: Date.now(), wants: {} })
        const known = copy.wants[key]
        copy.wants[key] = { command: command, interval: interval, named: !!named }
        if (!instanceName) {
            instanceName = id
            runLive()
        }
        update()
        if (known && known.command === command)
            return
        // New to this copy: the last answer at once, if there's one
        const last = lastOutput[command]
        if (last)
            Qt.callLater(() => hub.output(command, last.stdout, last.stderr))
        else
            run(command)
    }

    // Whether the copy has a popup (see copies); (a copy that's gone, or not
    // here yet, isn't added: one being destroyed would stay here for good)
    function placed(id, popup) {
        const copy = copies[id]
        if (!copy || copy.popup === popup)
            return
        copy.popup = popup
        update()
    }

    function unwant(id, key) {
        if (copies[id] && key in copies[id].wants) {
            delete copies[id].wants[key]
            update()
        }
    }

    // ---------------------------------------------------------------- the chat pane
    // A chat has one window: each copy has chat windows of its own (the
    // panel's, each desktop's), so a chat open in one copy's window and opened
    // again from another copy brings that window forward (paneRaise), not a second one
    property var panes: ({})   // copy id -> the chats its windows show (["host|chatId", …])
    signal paneRaise(string id, string key, string tab, var then)   // (then: what the pane does, ChatPane act)
    function paneShown(id, keys) {
        if (keys.length)
            panes[id] = keys
        else
            delete panes[id]
    }
    function paneHolder(key, except) {   // (the copy whose window shows that chat, "" for none)
        for (const id in panes)
            if (id !== except && panes[id].indexOf(key) >= 0)
                return id
        return ""
    }

    function drop(id) {
        delete panes[id]
        for (const host in watchWanted)
            dropWatch(id, host)
        if (!(id in copies))
            return
        delete copies[id]
        delete liveWanted[id]
        update()
        pickLive()
    }

    // (Refresh: one running now may have read the chats before you clicked)
    function refresh(command) {
        run(command, true)
    }

    // ---------------------------------------------------------------- live
    // One watcher for all copies (live.py --wait): it answers the moment a
    // chat starts, ends, works, waits or finishes its turn (its session file
    // changes: the status is checked at once) or does a step (the live
    // hook's files), then runs again. While it answers, the copies check the
    // status less often (liveHealthy). Its command line stays the same from
    // run to run (--as: what it told the last run is kept in the live folder).
    property var liveWanted: ({})     // copy id -> its live.py command
    property string liveCommand: ""   // the one that runs: the longest-running copy's
    property bool liveRunning: false
    property string liveLine: ""      // what runs (liveCommand --as …)
    property real liveStartedAt: 0
    property bool liveHealthy: false
    property int liveFailures: 0

    function wantLive(id, command) {
        if (liveWanted[id] === command)
            return
        liveWanted[id] = command
        pickLive()
    }

    function pickLive() {
        let best = "", since = 0
        for (const id in liveWanted) {
            const c = copies[id]
            const at = c ? c.since : Date.now()
            if (!best || at < since) {
                best = liveWanted[id]
                since = at
            }
        }
        liveCommand = best
        if (!best)
            liveHealthy = false
        runLive()
    }

    function runLive() {
        if (!liveCommand || liveRunning || liveRetry.running || !instanceName)
            return
        liveRunning = true
        liveStartedAt = Date.now()
        liveLine = liveCommand + " --as " + shellQuote(instanceName)
        liveRunner.connectSource(liveLine)
    }

    // Each status check of the copies now; one that runs is run again when it's done
    function checkNow() {
        const done = {}
        for (const id in copies) {
            const w = copies[id].wants["status"]
            if (w && !done[w.command]) {
                done[w.command] = true
                run(w.command, true)
            }
        }
    }

    property Exec liveRunner: Exec {
        staleMs: hub.liveStaleMs
        onNewData: (source, data) => {
            disconnectSource(source)
            hub.liveRunning = false
            let answer = null
            try {
                answer = JSON.parse(data["stdout"])
            } catch (e) {
            }
            if (!answer || !answer.ok) {
                // (three in a row: the copies go back to checking as often as before; it tries again in a minute)
                hub.liveFailures += 1
                if (hub.liveFailures >= 3)
                    hub.liveHealthy = false
                liveRetry.interval = hub.liveFailures >= 3 ? 60000 : 5000
                liveRetry.restart()
                return
            }
            hub.liveFailures = 0
            hub.liveHealthy = true
            if (answer.sessions || answer.urgent)
                hub.checkNow()
            if (answer.live && answer.live.length)
                hub.live(answer.live)
            Qt.callLater(hub.runLive)
        }
    }

    property Timer liveRetry: Timer {
        onTriggered: hub.runLive()
    }

    // ---------------------------------------------------------------- SSH hosts' and containers' watchers
    // Talpy Chat's watcher of a host (remote.py --watch: live.py there, over
    // the shared ssh connection): while a copy wants it (a Talpy Chat window
    // of a chat there shows, or, in the copy that notifies, a chat Talpy Chat
    // hooked there works or waits), it answers the moment a chat's session
    // file or a permission request there changes (hostChanged), then runs
    // again; within 50 s anyway. One per host for all copies, its command line
    // the same from run to run (--as: a name of this plasmashell's, hashed).
    property var watchWanted: ({})    // host -> {copy id: its remote.py --watch command, without --as}
    property var watchRuns: ({})      // host -> {line, at}: the one running
    property var watchFailures: ({})  // host -> failures in a row
    property var watchNext: ({})      // host -> when it may run again (after a failure)
    // host -> why Talpy Den can't watch it now ("" or missing: it can); "check": it couldn't be
    // reached, so not until its next check answers (watchChecked)
    property var watchTrouble: ({})
    signal hostChanged(string host, var answer)   // answer: {sessions, requests, changed: [chat ids]}
    readonly property int watchStaleMs: 80000

    function wantWatch(id, host, command) {
        const w = watchWanted[host] || {}
        if (w[id] === command)
            return
        watchWanted = Object.assign({}, watchWanted, { [host]: Object.assign({}, w, { [id]: command }) })
        runWatch(host)
    }

    function dropWatch(id, host) {
        const w = watchWanted[host]
        if (!w || !(id in w))
            return
        const rest = Object.assign({}, w)
        delete rest[id]
        const next = Object.assign({}, watchWanted)
        if (Object.keys(rest).length) {
            next[host] = rest
        } else {
            delete next[host]   // (the run in flight ends by itself within 50 s; its answer is let go)
            // (wanted again later: it starts afresh, no old trouble on its tag nor an old wait)
            delete watchFailures[host]
            delete watchNext[host]
            if (host in watchTrouble) {
                const t = Object.assign({}, watchTrouble)
                delete t[host]
                watchTrouble = t
            }
        }
        watchWanted = next
    }

    // The host answered its check: a watcher that couldn't reach it runs again
    function watchChecked(host) {
        if (watchTrouble[host] === "check") {
            const t = Object.assign({}, watchTrouble)
            delete t[host]
            watchTrouble = t
            watchFailures[host] = 0
            runWatch(host)
        }
    }

    function watching(host) {
        return !!watchWanted[host] && !watchTrouble[host]
    }

    function runWatch(host) {
        const w = watchWanted[host]
        if (!w || watchRuns[host] || watchTrouble[host] === "check" || Date.now() < (watchNext[host] || 0) || !instanceName)
            return
        const command = w[Object.keys(w).sort()[0]]
        const line = command + " --as " + Qt.md5("talpy-den plasma " + instanceName).slice(0, 12)
        watchRuns[host] = { line: line, at: Date.now() }
        watchRunner.connectSource(line)
    }

    function watchFailed(host, why, unreached) {
        const n = (watchFailures[host] || 0) + 1
        watchFailures[host] = n
        watchNext[host] = Date.now() + (n >= 3 ? 60000 : 5000)
        if (unreached || n >= 3)
            watchTrouble = Object.assign({}, watchTrouble, { [host]: unreached ? "check" : why })
    }

    property Timer watchAgain: Timer {
        interval: 260
        onTriggered: {
            for (const host in hub.watchWanted)
                if (!hub.watchRuns[host])
                    hub.runWatch(host)
        }
    }

    property Exec watchRunner: Exec {
        staleMs: hub.watchStaleMs
        onNewData: (source, data) => {
            disconnectSource(source)
            let host = ""
            for (const h in hub.watchRuns)
                if (hub.watchRuns[h].line === source)
                    host = h
            if (!host)
                return
            const startedAt = hub.watchRuns[host].at
            delete hub.watchRuns[host]
            let answer = null
            try {
                answer = JSON.parse(data["stdout"])
            } catch (e) {
            }
            if (!hub.watchWanted[host])
                return   // (not wanted any more: let go)
            if (!answer || !answer.ok) {
                hub.watchFailed(host, answer ? answer.error || answer.message || "" : (data["stderr"] || "").trim().split("\n").pop(),
                                !!answer && answer.reached === false)
                return
            }
            hub.watchFailures[host] = 0
            if (hub.watchTrouble[host]) {
                const t = Object.assign({}, hub.watchTrouble)
                delete t[host]
                hub.watchTrouble = t
            }
            // (again at once, first: a copy's handler that throws doesn't stop it; a function of its own for each
            // host, Qt.callLater runs one function once a pass. One that answered at once runs again a moment
            // later: never again and again)
            if (Date.now() - startedAt < 250) {
                hub.watchNext[host] = startedAt + 250
                watchAgain.restart()
            } else {
                Qt.callLater(() => hub.runWatch(host))
            }
            if (answer.sessions || answer.requests)
                hub.hostChanged(host, answer)
        }
    }

    function wantsOf(command) {
        const out = []
        for (const id in copies)
            for (const key in copies[id].wants)
                if (copies[id].wants[key].command === command)
                    out.push(copies[id].wants[key])
        return out
    }

    // How often a command is checked: as often as its most eager copy wants
    function intervalFor(command) {
        let ms = 0
        for (const w of wantsOf(command))
            if (!ms || w.interval < ms)
                ms = w.interval
        return ms
    }

    // The ticker's step: each interval wanted is a whole number of steps
    // (ticking at the shortest one, a host wanted every 30 s was checked
    // every 40 s next to a status wanted every 20 s)
    function gcd(a, b) {
        return b ? gcd(b, a % b) : a
    }

    function update() {
        let leader = "", since = 0, popup = false, shortest = 0, step = 0
        const wanted = {}
        for (const id in copies) {
            const c = copies[id]
            const p = c.popup !== false   // (not known yet: as one with a popup)
            if (!leader || (p && !popup) || (p === popup && (c.since < since || (c.since === since && id < leader)))) {
                leader = id
                since = c.since
                popup = p
            }
            for (const key in c.wants) {
                wanted[c.wants[key].command] = true
                if (!shortest || c.wants[key].interval < shortest)
                    shortest = c.wants[key].interval
                step = gcd(Math.round(c.wants[key].interval), step)
            }
        }
        leaderId = leader
        ticker.interval = Math.max(1000, step || 2000)
        ticker.running = shortest > 0
        // Forget the answers no copy asks for any more
        for (const command in lastOutput)
            if (!(command in wanted))
                delete lastOutput[command]
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'"
    }

    // urgent: a chat changed meanwhile: a check that's running now may have
    // read it as it was, so it runs again once it's done
    function run(command, urgent) {
        for (const line in running) {
            if (running[line] === command) {
                if (Date.now() - (lastStart[command] || 0) < staleMs && poller.has(line)) {
                    if (urgent)
                        again[command] = true
                    return   // a still-running check: don't stack another
                }
                delete running[line]   // (no answer for too long, or none can come: it's given up)
            }
        }
        const named = wantsOf(command).some(w => w.named)
        const line = named ? command + " --instance " + shellQuote(instanceName) + " --interval-ms " + (intervalFor(command) || 2000)
                           : command
        running[line] = command
        lastStart[command] = Date.now()
        try {
            started(command)
            poller.connectSource(line)
        } catch (e) {
            delete running[line]   // (it never started: not a check to wait for)
            console.warn("Talpy Den: a check didn't start: " + e)
        }
    }

    property Timer ticker: Timer {
        repeat: true
        onTriggered: {
            if (hub.liveRunning && (Date.now() - hub.liveStartedAt > hub.liveStaleMs || !hub.liveRunner.has(hub.liveLine))) {
                hub.liveRunning = false   // (its watcher never answered, or can't: the next one starts)
                hub.runLive()
            }
            // (a host's watcher: one that never answered, or can't, is given up; one that failed runs again when its wait is over)
            for (const host in hub.watchWanted) {
                const r = hub.watchRuns[host]
                if (r && (Date.now() - r.at > hub.watchStaleMs || !hub.watchRunner.has(r.line)))
                    delete hub.watchRuns[host]
                if (!hub.watchRuns[host])
                    hub.runWatch(host)
            }
            const due = {}
            for (const id in hub.copies)
                for (const key in hub.copies[id].wants)
                    due[hub.copies[id].wants[key].command] = true
            // (each command at its own pace; a little early is fine)
            for (const command in due)
                if (Date.now() - (hub.lastStart[command] || 0) >= hub.intervalFor(command) - 250)
                    hub.run(command)
        }
    }

    property Exec poller: Exec {
        staleMs: hub.staleMs
        onNewData: (source, data) => {
            disconnectSource(source)
            const command = hub.running[source]
            delete hub.running[source]
            if (command === undefined)
                return
            const answer = { stdout: data["stdout"] || "", stderr: data["stderr"] || "" }
            if (hub.intervalFor(command))   // still wanted
                hub.lastOutput[command] = answer
            hub.output(command, answer.stdout, answer.stderr)
            if (hub.again[command]) {
                delete hub.again[command]
                if (hub.intervalFor(command))
                    hub.run(command)
            }
        }
    }
}
