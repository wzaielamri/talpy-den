import QtQuick
import org.kde.plasma.plasmoid
import "sides.mjs" as Sides

// What Talpy Chat's side questions do (ChatPane.qml's sideLogic: read and made only once you ask one,
// remove one or the panel shows, so a window whose side questions stay closed runs none of this). The
// rules and words are sides.mjs's, VS Code's the same.
// - Asking shows the question at once, Answering… under it (one of this window's own), while pane.py
//   --side-question puts it to a copy of the chat Claude doesn't keep and waits for the answer (2-30 s,
//   up to 4 min); several can be on their way, each its own run. pane.py keeps it in the chat's list as on
//   its way at once, so a read of the chat meanwhile lists it: that one takes this window's place (its row
//   stays, SidePanel.qml). Its answer comes with the chat's whole list: newer than what's shown, taken.
// - Remove (×) and Remove all hide them at once, then pane.py --side-question --remove takes them out of
//   the list it keeps; one that fails comes back, and the panel says why (note). One removed while
//   it's on its way is taken out of pane.py's list once its answer is in.
// - Ask again (one with no answer): that one goes, and its question is asked again on the model picked now.
// - The model picked (sideQuestionModel: "" the chat's own, sonnet or haiku) is every window's.
Item {
    id: logic
    objectName: "sideLogic"
    visible: false

    // [{id: "local-N", q, pick, at, pending | error, dropped}]: this window's, not in pane.py's list yet
    // (dropped: removed while on its way)
    property var asking: []
    property int count: 0
    property var gone: ({})      // id -> true: removed, pane.py's answer on its way
    property real goneBefore: 0  // (Remove all: the ones asked by then are gone, till pane.py's answer)
    property string note: ""     // (one that couldn't be removed: why, in the panel a moment)
    Timer {
        id: noteTimer
        interval: 12000
        onTriggered: logic.note = ""
    }

    readonly property string pick: {
        const p = String(Plasmoid.configuration.sideQuestionModel || "").toLowerCase()
        return Sides.SIDE_PICKS.some(s => s.value === p) ? p : ""
    }
    function setPick(value) {
        Plasmoid.configuration.sideQuestionModel = value
    }

    // What the panel lists: pane.py's list (oldest first) without those removed, then this window's that it
    // doesn't list yet; handoff: {pane.py's id: the id of this window's one it takes the place of}
    readonly property var view: {
        const list = pane.sides.filter(s => s && !gone[s.id] && !(goneBefore > 0 && (s.at || 0) <= goneBefore))
        const handoff = {}, claimed = {}, hidden = {}, mine = []
        for (const a of asking) {
            const found = a.pending ? list.find(s => !claimed[s.id] && s.q === a.q && (s.pick || "") === a.pick && (s.at || 0) >= a.at - 5000) : null
            if (found) {
                claimed[found.id] = true
                if (a.dropped)
                    hidden[found.id] = true   // (removed while on its way: pane.py's copy of it isn't shown either)
                else
                    handoff[found.id] = a.id
            } else if (!a.dropped)
                mine.push(a)
        }
        return { list: list.filter(s => !hidden[s.id]).concat(mine), handoff: handoff }
    }
    readonly property var shown: view.list
    readonly property var handoff: view.handoff

    // A question about the chat shown, on the model picked: false when there's none to ask (or no chat)
    function ask(text) {
        const q = String(text || "").trim()
        if (q === "" || !pane.chatId || pane.fresh)
            return false
        const id = "local-" + (++count)
        const at = Date.now()
        asking = asking.concat([{ id: id, q: q, pick: pick, at: at, model: "", pending: true }])
        pane.start("--side-question " + root.shellQuote(pane.chatId) + " --text " + root.shellQuote(q)
                   + (pick ? " --model " + pick : "") + pane.paneArgs() + " # " + at + "." + id,
                   { kind: "side", chat: pane.chatId, host: pane.host, local: id, q: q, pick: pick, at: at })
        return true
    }
    // Explain this: what you selected, quoted, asked in the panel (opened if it's closed)
    function explain(selected) {
        const q = Sides.explainQuestion(selected)
        if (q === "")
            return
        pane.showSides(true, true)
        ask(q)
    }
    // One of them ("all": every one of the chat's) out of the list at once, then out of pane.py's
    function remove(id) {
        if (asking.some(a => a.id === id)) {   // (this window's: one on its way is dropped, else nothing to write)
            asking = asking.filter(a => a.id !== id || a.pending).map(a => a.id === id ? Object.assign({}, a, { dropped: true }) : a)
            return
        }
        if (id === "all") {
            goneBefore = Date.now()
            asking = asking.filter(a => a.pending).map(a => Object.assign({}, a, { dropped: true }))
        } else {
            const next = Object.assign({}, gone)
            next[id] = true
            gone = next
        }
        removeOf(pane.chatId, pane.host, id)
    }
    function removeOf(chat, host, id) {
        pane.start("--side-question " + root.shellQuote(chat) + " --remove " + root.shellQuote(id)
                   + (host ? " --host " + root.shellQuote(host) : "") + " # " + Date.now(),
                   { kind: "side", chat: chat, host: host, remove: id })
    }
    function askAgain(s) {
        remove(String(s.id))
        ask(s.q)
    }

    // (its answer, ChatPane handle: an answer and the chat's list as pane.py keeps it, or why not)
    function took(result, asked) {
        const here = asked.chat === pane.chatId && asked.host === pane.host
        if (asked.remove !== undefined) {
            if (here && Sides.newerSides(result.sides, result.sidesV, pane.sidesV)) {
                pane.sides = result.sides
                pane.sidesV = result.sidesV
            }
            if (here && asked.remove === "all")
                goneBefore = 0
            else if (here && gone[asked.remove]) {
                const next = Object.assign({}, gone)
                delete next[asked.remove]
                gone = next
            }
            if (here && !result.ok) {
                note = result.message || i18n("That didn't work")
                noteTimer.restart()
            }
            return
        }
        const was = asking.find(a => a.id === asked.local) || null
        asking = asking.filter(a => a.id !== asked.local)
        if (was && was.dropped && result.side && result.side.id) {   // (removed while on its way: from pane.py's list too)
            if (here) {
                const next = Object.assign({}, gone)
                next[result.side.id] = true
                gone = next
            }
            removeOf(asked.chat, asked.host, result.side.id)
        }
        if (!here)
            return   // (the chat before's: its list shows its answer once it's opened again)
        if (Sides.newerSides(result.sides, result.sidesV, pane.sidesV)) {
            pane.sides = result.sides
            pane.sidesV = result.sidesV
        }
        // (one that couldn't even be asked, too long say: why, in its place, to ask again or remove)
        if (!result.ok && !result.side && !(was && was.dropped))
            asking = asking.concat([{ id: asked.local, q: asked.q, pick: asked.pick, at: asked.at, model: "",
                                      error: result.message || i18n("That didn't work"), done: Date.now() }])
    }

    // Another chat shown: none of this one's (the answers still on their way are left out when they come)
    function clear() {
        asking = []
        gone = {}
        goneBefore = 0
        note = ""
    }
}
