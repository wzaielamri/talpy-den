import QtQuick
import org.kde.kirigami as Kirigami
import "bookmarks.mjs" as Bm

// What Talpy Chat's bookmarks do (ChatPane.qml's bookmarkLogic: read and made only once the chat has a
// bookmark, after its read, or once you bookmark one, so a chat without any runs none of this). The
// rules are bookmarks.mjs's, VS Code's the same.
// - A click, the right-click menu or Ctrl+D changes the list at once (the ribbon, the hover bar's icon,
//   the count and the side list, in the same frame), then pane.py --bookmark keeps it: one write at a
//   time, in the order you clicked; one that fails is undone, and the line under the tabs says why.
// - Each bookmarked message's dot (Claude's) or › (yours) is a ribbon (BookmarkFlag.qml, made on those
//   rows only, a child of the row's rowMark: nothing in each row, nothing moves).
// - Alt+↑ / Alt+↓ and a click in the list go to one, framed a moment; one further back than what's
//   shown is read first (pane.py --conversation --reach: as Show earlier reads more).
Item {
    id: logic
    objectName: "bookmarkLogic"
    visible: false

    // ---------------------------------------------------------------- the list, and its writes

    property var queue: []         // [{args, chat, host, key, on, entry}]: the head is on its way
    property bool writing: false
    readonly property bool busy: queue.length > 0   // (an answer's list isn't taken meanwhile: ChatPane takeConversation)

    // (the item pane.py read, for a row: when it was written, what it says)
    function itemOf(key) {
        const shown = pane.shownList
        for (let i = 0; i < shown.length; i++)
            if (String(shown[i].key) === key)
                return shown[i]
        return null
    }
    function set(list) {
        pane.bookmarks = list
        pane.bookmarked = Bm.keysOf(list)
    }
    // A message bookmarked, or its bookmark taken away (it: a row, or pane.py's item)
    function toggle(it) {
        if (!it || !Bm.canBookmark(it))
            return
        const key = String(it.key)
        const item = itemOf(key) || it
        if (!Bm.canBookmark(item))
            return
        if (pane.bookmarked[key] === true)
            return unmark(key)
        const entry = Bm.entryOf(item, Date.now())
        const next = Bm.withBookmark(pane.bookmarks, entry)
        if (next === null) {
            pane.info = i18n("A chat keeps up to 100 bookmarks: remove one first")
            pane.infoBad = true
            infoTimer.restart()
            return
        }
        set(next)
        write({ on: true, key: key, entry: entry })
    }
    function unmark(key) {
        const was = pane.bookmarks.find(m => m.key === key)
        if (!was)
            return
        set(Bm.withoutBookmark(pane.bookmarks, key))
        write({ on: false, key: key, entry: was })
    }
    function write(op) {
        op.chat = pane.chatId
        op.host = pane.host
        op.args = "--bookmark " + root.shellQuote(op.chat) + " --key " + root.shellQuote(op.key)
                  + (op.on ? " --kind " + op.entry.kind + " --at " + Math.max(0, Math.floor(op.entry.at || 0))
                             + " --text " + root.shellQuote(op.entry.text) : " --off") + pane.paneArgs()
        queue = queue.concat([op])
        pump()
    }
    function pump() {
        if (writing || !queue.length)
            return
        writing = true
        const op = queue[0]
        pane.start(op.args + " # " + Date.now(), { kind: "bookmark", chat: op.chat, host: op.host, op: op })
    }
    // (its answer, ChatPane handle: kept, or why not; the chat's whole list as pane.py keeps it)
    function took(result, asked) {
        writing = false
        const op = asked.op || queue[0]
        queue = queue.filter(o => o !== op)
        const here = !!op && op.chat === pane.chatId && op.host === pane.host
        if (here && !result.ok) {
            set(op.on ? Bm.withoutBookmark(pane.bookmarks, op.key) : Bm.withBookmark(pane.bookmarks, op.entry) || pane.bookmarks)
            pane.info = i18n("Couldn't keep the bookmark: %1", result.message || i18n("That didn't work"))
            pane.infoBad = true
            infoTimer.restart()
        }
        if (here && !queue.length && Array.isArray(result.bookmarks) && (result.bookmarksV || 0) >= pane.bookmarksV) {
            set(result.bookmarks)
            pane.bookmarksV = result.bookmarksV || 0
        }
        pump()
    }

    // Ctrl+D: the message under the pointer, else (at the end) Claude's last reply, else the first one
    // at the top of what you read
    function target() {
        const hovered = list.hoverRow
        if (hovered && Bm.canBookmark(hovered))
            return hovered
        if (pane.nearEnd()) {
            const last = pane.lastItems
            for (let i = last.length - 1; i >= 0; i--)
                if (last[i].kind === "claude" && !last[i].thinking)
                    return Bm.canBookmark(last[i]) ? last[i] : null
        }
        const top = list.contentY
        let i = list.indexAt(list.width / 2, top)
        if (i < 0)
            i = list.indexAt(list.width / 2, top + fm.height)
        for (i = Math.max(0, i); i < items.count; i++) {
            const row = list.itemAtIndex(i)
            if (row && row.listed && row.shows && !row.card && row.y + row.height > top + 4 && Bm.canBookmark(row))
                return row
        }
        return null
    }
    function toggleHere() {
        toggle(target())
    }

    // ---------------------------------------------------------------- the ribbons

    property var flags: new Map()   // key -> [BookmarkFlag]
    property var flagMaker: null
    property int missing: 0         // (bookmarked rows not made yet: further than the list makes ahead)
    property int tries: 0
    property real placedY: 0
    function placeSoon() {
        Qt.callLater(place)
    }
    // Each bookmarked row's mark: its ribbon (made where there's none, kept where it is, taken away where
    // it's no longer bookmarked)
    function place() {
        const want = pane.bookmarked, shown = pane.shownList
        const rows = new Map()   // key -> its indices (a message of two parts: both)
        if (pane.bookmarks.length) {
            list.forceLayout()   // (rows just put in: made now, not after this frame)
            for (let i = 0; i < shown.length; i++) {
                const k = String(shown[i].key)
                if (want[k] === true) {
                    const at = rows.get(k)
                    if (at)
                        at.push(i)
                    else
                        rows.set(k, [i])
                }
            }
        }
        const next = new Map(), kept = new Set()
        let lost = 0
        rows.forEach((at, k) => {
            const had = flags.get(k) || [], now = []
            for (const i of at) {
                const row = list.itemAtIndex(i)
                if (!row || !row.listed) {
                    lost++
                    continue
                }
                let flag = had.find(f => f.row === row && !!f.parent)
                if (!flag) {
                    const mark = markOf(row, 0)
                    if (!mark) {
                        lost++
                        continue
                    }
                    if (!flagMaker)
                        flagMaker = Qt.createComponent("BookmarkFlag.qml")
                    flag = flagMaker.createObject(mark, { row: row, kind: shown[i].kind })
                }
                now.push(flag)
                kept.add(flag)
            }
            if (now.length)
                next.set(k, now)
        })
        flags.forEach(had => {
            for (const f of had)
                if (!kept.has(f) && f.parent) {   // (a row gone takes its own along)
                    f.visible = false
                    f.destroy()
                }
        })
        flags = next
        missing = lost
        placedY = list.contentY
        tries = lost ? tries + 1 : 0
    }
    function markOf(item, depth) {
        for (const k of item.children) {
            if (k.objectName === "rowMark")
                return k
            if (depth < 6) {
                const found = markOf(k, depth + 1)
                if (found)
                    return found
            }
        }
        return null
    }
    function clear() {
        flags.forEach(had => {
            for (const f of had)
                if (f.parent) {
                    f.visible = false
                    f.destroy()
                }
        })
        flags = new Map()
        missing = 0
        tries = 0
        settled = {}
        going = ""
        current = ""
        jumpKey = ""
        jumpRetry.stop()
        if (flashing) {
            flashing.end()
            flashing.destroy()
        }
        flashing = null
    }
    Connections {
        target: pane
        function onBookmarksChanged() { logic.placeSoon() }
        function onShownListChanged() {
            if (pane.bookmarks.length || logic.flags.size)
                logic.placeSoon()
        }
    }
    // (a row not made yet: once the next frame is drawn, and again as you go far from where it was looked for)
    Connections {
        target: pane
        enabled: logic.missing > 0 && logic.tries < 3
        function onFrameSwapped() { logic.placeSoon() }
    }
    Connections {
        target: list
        enabled: logic.missing > 0
        function onContentYChanged() {
            if (Math.abs(list.contentY - logic.placedY) > list.height)
                logic.placeSoon()
        }
    }
    Component.onCompleted: placeSoon()
    Component.onDestruction: clear()

    // ---------------------------------------------------------------- going to one

    property string current: ""   // (the one gone to last: framed in the list)
    property string going: ""     // (one further back being read: Going there…)
    property var settled: ({})    // key -> "far" | "gone", as a read for it found
    property bool closeAfter: false   // (gone to from the list: it closes, unless it covers little)
    property string jumpKey: ""
    property int jumpTries: 0

    readonly property bool capped: pane.more && pane.limit >= pane.limitMax   // (the most Talpy Chat shows)
    function loadedKeys() {   // key -> its first row
        const keys = new Map(), shown = pane.shownList
        for (let i = 0; i < shown.length; i++) {
            const k = String(shown[i].key)
            if (!keys.has(k))
                keys.set(k, i)
        }
        return keys
    }
    function stateOf(mark, loaded) {
        return Bm.stateOf(mark, loaded, pane.more, capped, settled)
    }
    function topOf(row) {   // (where the list goes to show it at the top, as Ctrl+↑ does)
        return Math.max(list.originY, Math.min(list.originY + list.contentHeight - list.height, row.y + row.gap - fm.height * 0.5))
    }

    // To the message with that key, once it's drawn (fromList: a click in the list)
    function jump(key, fromList) {
        jumpKey = key
        jumpTries = 15
        closeAfter = !!fromList
        jumpRetry.stop()
        jumpNow()
    }
    Timer {
        id: jumpRetry
        interval: 30
        onTriggered: logic.jumpNow()
    }
    function jumpNow() {
        const loaded = loadedKeys()
        const i = loaded.has(jumpKey) ? loaded.get(jumpKey) : -1
        if (i < 0)
            return
        list.forceLayout()
        const row = list.itemAtIndex(i)
        if (!row || !row.listed || !row.shows) {
            if (--jumpTries > 0) {
                list.positionViewAtIndex(i, ListView.Beginning)
                jumpRetry.restart()
            }
            return
        }
        settle.stop()
        holdTop.stop()
        list.contentY = topOf(row)
        // (rows above it still getting their height: it stays at the top meanwhile, till you scroll)
        pane.chatTop = [row.key, row.y - list.contentY, i]
        holdTop.restart()
        flash(row)
        current = jumpKey
        const card = bookmarkList.item
        if (closeAfter && card && !Bm.staysOpen(scroll.width, card.width, false)) {
            pane.bookmarksOn = false
            replyBox.forceActiveFocus()
        }
        closeAfter = false
    }

    // Alt+↑ (back) / Alt+↓: the bookmark before / after what you read (past the last: the end; before
    // the first, the newest one further back, read first)
    function step(back) {
        const loaded = loadedKeys(), states = {}, tops = {}
        for (const m of pane.bookmarks) {
            states[m.key] = stateOf(m, loaded)
            if (states[m.key] !== "here")
                continue
            const row = list.itemAtIndex(loaded.get(m.key))
            if (row && row.listed && row.shows)
                tops[m.key] = topOf(row)
        }
        const r = Bm.step(pane.bookmarks, states, tops, list.contentY, back)
        if (!r)
            return
        if (r.key)
            jump(r.key, false)
        else if (r.reach)
            reach(r.reach, false)
        else if (r.end)
            pane.toEnd()
    }

    // One further back than what's shown: the chat read as far back as it (as Show earlier reads more),
    // then gone to
    function reach(key, fromList) {
        going = key
        closeAfter = !!fromList
        pane.reachKey = key
        pane.stamp = ""
        pane.load()
    }
    // (that read's answer, ChatPane takeConversation: there, too far back or gone; or it failed)
    function reached(result) {
        const key = result.reach || going
        const mine = key === going
        if (mine)
            going = ""
        if (!result.ok || !key)
            return
        if (result.reached === "here") {
            if (mine)
                Qt.callLater(() => logic.jump(key, logic.closeAfter))
        } else if (result.reached === "far" || result.reached === "gone") {
            const next = Object.assign({}, settled)
            next[key] = result.reached
            settled = next
            if (result.reached === "gone" && mine) {
                pane.info = i18n("That message isn't in the chat any more")
                pane.infoBad = true
                infoTimer.restart()
            }
        }
    }

    // The one gone to, framed a moment: one frame, moved to the row gone to (made the first time; gone
    // with its row); with animations off, framed as long, no fade
    property Item flashing: null
    function flash(row) {
        if (!flashing)
            flashing = flashFrame.createObject(row)
        else
            flashing.parent = row
        flashing.start()
    }
    Component {
        id: flashFrame

        Rectangle {
            id: frame
            visible: false
            y: parent ? parent.gap : 0
            width: parent ? parent.width : 0
            height: parent ? parent.height - parent.gap : 0
            z: 3
            color: "transparent"
            radius: Kirigami.Units.cornerRadius
            border.width: 2
            border.color: pane.youColor   // (the theme's focus colour)

            function start() {
                visible = true
                fade.restart()
            }
            function end() {
                fade.stop()
                visible = false
            }
            SequentialAnimation {
                id: fade
                OpacityAnimator {
                    target: frame
                    from: 1
                    to: Kirigami.Units.longDuration > 0 ? 0 : 1
                    duration: 900
                    easing.type: Easing.InQuad
                }
                ScriptAction {
                    script: frame.visible = false
                }
            }
        }
    }
}
