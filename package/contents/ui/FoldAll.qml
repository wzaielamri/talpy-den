import QtQuick

// Ctrl+O in Talpy Chat: every long text unfolded (a message, a reply, a command's output), a few
// at a time, the ones nearest what you read first, a little of it each frame, so the window keeps
// drawing while they're drawn whole again. ChatPane.qml makes it at the first Ctrl+O; a row gets its
// turn when its late is set to allGen; rows made after (scrolled to, come in) at once
Timer {
    property var rows: []
    interval: 16

    function unfoldAll() {
        const n = items.count
        const top = Math.max(0, list.indexAt(list.width / 2, list.contentY + 2))
        const order = []
        for (let d = 0; top + d < n || top - d - 1 >= 0; d++) {   // (from what you read, outward: the long ones)
            if (top + d < n && items.get(top + d).fold !== "")
                order.push(top + d)
            if (top - d - 1 >= 0 && items.get(top - d - 1).fold !== "")
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
