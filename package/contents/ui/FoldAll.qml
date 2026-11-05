import QtQuick

// Ctrl+O in Talpy Chat: every row unfolded (each step's details, its whole change, a long text), a
// few at a time, the ones nearest what you read first, about 6 ms of it at once, so the window keeps
// drawing while they're made (an edit's whole change is drawn again at once, all of them together
// held the window up for a second and more). ChatPane.qml makes it at the first Ctrl+O; a row gets
// its turn when its late is set to allGen; rows made after (scrolled to, come in) at once
Timer {
    property var rows: []
    interval: 16

    function unfoldAll() {
        const n = items.count
        const top = Math.max(0, list.indexAt(list.width / 2, list.contentY + 2))
        const order = []
        for (let d = 0; top + d < n || top - d - 1 >= 0; d++) {   // (from what you read, outward)
            if (top + d < n)
                order.push(top + d)
            if (top - d - 1 >= 0)
                order.push(top - d - 1)
        }
        rows = order
        restart()
    }
    onTriggered: {
        const start = Date.now(), gen = pane.allGen
        if (!pane.allOpen) {
            rows = []
            return
        }
        while (rows.length && Date.now() - start < 2) {
            const row = list.itemAtIndex(rows.shift())
            if (row)
                row.late = gen
        }
        if (rows.length)
            restart()
        else
            pane.lateDefault = gen
    }
}
