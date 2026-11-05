import QtQuick

// The model of a list whose rows are kept by key (an account's chats, the
// accounts, the SSH hosts): sync() with the list as it is now moves, adds
// and removes only the rows whose item came, went or moved, and gives a row
// a new rev only when its item changed. A Repeater given a number made all
// its rows anew whenever the number changed (a chat starting or hidden: every
// row of the account, seconds in a long list), and a new array every check
// ran every row's bindings again. A row reads its item here (item(key)) when
// its rev changes:
//
//     Repeater {
//         model: rows.model   // (rows: a KeyedRows)
//         delegate: Row {
//             required property string key
//             required property string rev
//             thing: { rev; return rows.item(key) || empty }
//         }
//     }
//
// Many new rows at once (the list's first fill, the popup made anew) come a
// few at a time, from the top, each frame's worth within budgetMs, so the
// popup draws meanwhile; a row or two (a chat that starts) come at once.
QtObject {
    id: rows

    readonly property ListModel model: ListModel {}

    // how long one go may spend making rows before the rest wait for the next frame (0: all at once)
    property int budgetMs: 20
    // (rows still to make: sync goes on by itself, a go each frame, until they're all there)
    readonly property bool filling: more.running
    // the list as it is, by key (the model's rows, in order, and what each shows)
    property var keys: []
    property var items: ({})
    property var revs: ({})
    // what the last sync was given, for the rows still to make
    property var wanted: null

    function item(key) {
        return items[key]
    }

    // list: the items in order; keyOf(item): its key (unique; a repeated
    // one gets "#2", "#3"…); revOf(item): a string that changes when it
    // changes (missing: worked out from the item); renamed(item): the key a
    // row of it had before, when it should keep that row (a chat moved to
    // another id), else ""
    function sync(list, keyOf, revOf, renamed) {
        const t0 = Date.now()
        const want = [], seen = {}, nextItems = {}, nextRevs = {}
        for (const it of list || []) {
            let key = String(keyOf(it))
            if (key in seen) {
                let n = 2
                while ((key + "#" + n) in seen)
                    n += 1
                key = key + "#" + n
            }
            seen[key] = true
            want.push(key)
            nextItems[key] = it
            const r = revOf ? revOf(it) : undefined
            nextRevs[key] = r !== undefined && r !== null && r !== "" ? String(r) : JSON.stringify(it)
        }
        // a row whose item moved to another key keeps its row (renamed in place)
        if (renamed) {
            for (const key of want) {
                if (keys.indexOf(key) >= 0)
                    continue
                const from = renamed(nextItems[key]) || ""
                const at = from ? keys.indexOf(from) : -1
                if (at >= 0 && !(from in seen)) {
                    items[key] = nextItems[key]   // (before its row reads it)
                    revs[key] = nextRevs[key]
                    keys[at] = key
                    model.setProperty(at, "key", key)
                    model.setProperty(at, "rev", nextRevs[key])
                }
            }
        }
        // the rows that went (from the end, so the ones before stay where they are)
        for (let i = keys.length - 1; i >= 0; i--) {
            if (!(keys[i] in seen)) {
                model.remove(i, 1)
                keys.splice(i, 1)
            }
        }
        // then in order: each row moved into its place, or made (within the budget)
        let at = 0, made = 0, waiting = false
        for (const key of want) {
            const was = keys.indexOf(key, at)
            if (was >= 0) {
                if (was !== at) {
                    model.move(was, at, 1)
                    keys.splice(was, 1)
                    keys.splice(at, 0, key)
                }
                at += 1
            } else if (budgetMs <= 0 || made === 0 || Date.now() - t0 < budgetMs) {
                items[key] = nextItems[key]   // (before the row is made: it reads it)
                model.insert(at, { key: key, rev: nextRevs[key] })
                keys.splice(at, 0, key)
                revs[key] = nextRevs[key]
                at += 1
                made += 1
            } else {
                waiting = true
            }
        }
        // what changed in the rows that stay
        for (let i = 0; i < keys.length; i++) {
            const key = keys[i]
            items[key] = nextItems[key]
            if (revs[key] !== nextRevs[key]) {
                revs[key] = nextRevs[key]
                model.setProperty(i, "rev", nextRevs[key])
            }
        }
        // (and the items of the rows that went: gone)
        for (const key in items)
            if (!(key in seen))
                delete items[key]
        for (const key in revs)
            if (keys.indexOf(key) < 0)
                delete revs[key]
        wanted = waiting ? { list: list, keyOf: keyOf, revOf: revOf, renamed: renamed } : null
        more.running = waiting
    }

    function clearRows() {
        more.running = false
        wanted = null
        model.clear()
        keys = []
        items = {}
        revs = {}
    }

    // (the next frame's rows, once this one is drawn; while the list's
    // window isn't drawn, nobody sees them: they wait)
    property FrameAnimation more: FrameAnimation {
        onTriggered: {
            const w = rows.wanted
            if (w)
                rows.sync(w.list, w.keyOf, w.revOf, w.renamed)
            else
                running = false
        }
    }
}
