import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "find.mjs" as Find
import "icons.mjs" as Icons

// Search in Talpy Chat (Ctrl+F): a bar over the list's top right, so nothing moves (ChatPane.qml's
// Loader: read and made only while it's open, so a window opens as quickly). What you type is
// looked for in what the tab shows (find.mjs findIn: VS Code's the same), a slice at a time (about
// 4 ms, then the window draws), and again as the chat is read again (Show earlier: more to search).
// The list stays where you read till you go to a match: Enter or F3 the next one from what you
// read, Shift+Enter or Shift+F3 the one before, then one after another, round; one in what's folded
// unfolds it first. The matches in the rows near what you read are marked under their letters
// (FindMarks.qml, made on those rows only, again as you scroll), the one gone to in its own colour.
// Esc closes it (PaneKeys.qml). VS Code chat.tsx FindBar: the same words
Rectangle {
    id: bar

    property var hits: []
    property int at: -1            // the one gone to (-1: none yet)
    property var hit: null         // (that one: found again as the chat is read again)
    property int next: -1          // (a search going on: the item to go on from)
    property var found: []         // (its matches so far)
    property int partly: -1        // (a long search: how many so far, shown after a moment)
    property real began: 0
    property bool stepAfter: false // (Enter while it searched: a step once it's done)
    property bool searched: false  // (it has a count: "…" till then)
    property bool stepBack: false
    property var order: new Map()  // key -> its row
    property var marks: []
    property var markComponent: null
    property int goTries: 0
    readonly property bool steps: pane.listTab === "steps"
    readonly property string count: pane.findQuery === "" ? ""
                                   : partly >= 0 || !searched ? Find.findCount(Math.max(0, partly), -1, false) : Find.findCount(hits.length, at, true)

    width: Math.min(row.implicitWidth + Kirigami.Units.smallSpacing * 2, scroll.width - Kirigami.Units.gridUnit * 2)
    height: row.implicitHeight + Kirigami.Units.smallSpacing
    radius: Kirigami.Units.cornerRadius
    color: Kirigami.Theme.backgroundColor
    border.width: 1
    border.color: pane.borderColor

    function focusField() {
        field.forceActiveFocus()
        field.selectAll()
    }
    function search() {
        slicer.stop()
        next = 0
        found = []
        began = Date.now()
        order = new Map(pane.shownList.map((it, i) => [String(it.key), i]))
        if (pane.findQuery === "") {
            hits = []
            at = -1
            partly = -1
            remark()
            return
        }
        slicer.restart()
    }
    Timer {
        id: slicer
        interval: 1
        onTriggered: {
            const r = Find.findIn(pane.shownList, pane.findQuery, bar.steps, bar.next, 4, bar.found)
            if (r.next >= 0) {
                bar.next = r.next
                if (Date.now() - bar.began > 150)
                    bar.partly = r.hits.length
                restart()
                return
            }
            bar.next = -1
            bar.partly = -1
            const was = bar.hit
            bar.at = was ? r.hits.findIndex(h => h.key === was.key && h.n === was.n) : -1
            if (bar.at < 0)
                bar.hit = null
            bar.hits = r.hits
            bar.searched = true
            bar.remark()
            if (bar.stepAfter) {
                bar.stepAfter = false
                bar.step(bar.stepBack)
            }
        }
    }
    Connections {
        target: pane
        function onShownListChanged() { bar.search() }
        function onListTabChanged() { bar.search() }
        function onFindQueryChanged() {
            bar.hit = null
            bar.at = -1
            bar.search()
        }
    }

    // A step: from what you read (the rows in view), then one after another, round
    function step(back) {
        if (pane.findQuery === "")
            return
        if (next >= 0 || slicer.running) {   // (still looking: once it's done)
            stepAfter = true
            stepBack = back
            return
        }
        if (!hits.length)
            return
        const top = list.indexAt(list.width / 2, list.contentY + 2)
        const bottom = list.indexAt(list.width / 2, list.contentY + list.height - 2)
        let i = Find.findStep(hits, at, back, { first: top >= 0 ? top : 0, last: bottom >= 0 ? bottom : items.count - 1, order: order })
        if (at < 0)
            i = fromView(i, back)
        at = i
        hit = hits[at]
        if (hit.hidden) {   // (in what's folded: unfolded first, as a click would)
            const open = Object.assign({}, pane.openTools)
            open[hit.key] = true
            open[hit.key + "/out"] = true
            pane.openTools = open
        }
        goTries = 15
        go.restart()
    }
    // (the first step, in a long item at the view's edge: from the first match below its top, or
    // going back, the last one above its end; one folded away counts as below)
    function fromView(i, back) {
        const key = hits[i].key, edge = back ? list.contentY + list.height : list.contentY
        let k = i
        for (; k >= 0 && k < hits.length && hits[k].key === key; k += back ? -1 : 1) {
            const p = placeOf(hits[k])
            const y = p ? p.item.mapToItem(list.contentItem, p.rect.x, p.rect.y).y : Infinity
            if (back ? y <= edge : y >= edge)
                return k
        }
        return (k + hits.length) % hits.length
    }
    Timer {
        id: go
        interval: 30
        onTriggered: bar.goTo()
    }
    // To the one gone to, once it's drawn (unfolded, its details made): a third down the list if
    // it isn't in view
    function goTo() {
        const place = placeOf(hit)
        if (!place && --goTries > 0) {
            go.restart()
            return
        }
        if (place) {
            const p = place.item.mapToItem(list.contentItem, place.rect.x, place.rect.y)
            if (p.y < list.contentY + 4 || p.y + place.rect.height > list.contentY + list.height - 4) {
                settle.stop()
                holdTop.stop()
                list.contentY = Math.max(list.originY, Math.min(list.originY + list.contentHeight - list.height, p.y - list.height / 3))
            }
        }
        remark()
    }

    // A row's texts with matches marked (its message, a reply, a command's output, a step's
    // details), in order; [] for a step's line, a card or a note (tinted whole)
    function rowOf(key) {
        const i = order.has(key) ? order.get(key) : -1
        const r = i >= 0 ? list.itemAtIndex(i) : null
        return r && r.listed && r.shows ? r : null
    }
    function boxesIn(item, out) {
        for (const k of item.children) {
            if (!k.visible)
                continue
            if (k.objectName === "findText")
                out.push(k)
            else
                boxesIn(k, out)
        }
        return out
    }
    function placesIn(box) {
        const out = []
        const rich = box.textFormat === TextEdit.RichText
        for (const m of Find.allIn(box.getText(0, box.length), pane.findQuery, 300)) {
            if (rich) {   // (not a code block's Copy)
                const r = box.positionToRectangle(m[0])
                if (box.linkAt(r.x + 1, r.y + r.height / 2).indexOf("copy:") === 0)
                    continue
            }
            out.push(m)
        }
        return out
    }
    // (how many of a step's matches are in its line and what came of it: tinted, not marked)
    function headOf(row) {
        if (row.kind !== "tool")
            return 0
        const it = pane.shownList[order.get(row.key)]
        return it ? Find.allIn(Find.findParts(it, steps)[0], pane.findQuery, 1000).length : 0
    }
    // Where the one gone to is: {item, rect} (its letters, or its row), null while it isn't drawn yet
    function placeOf(h) {
        const row = h ? rowOf(h.key) : null
        if (!row)
            return null
        if (h.hidden && (!row.whole || !row.outWhole || (row.kind === "tool" && !row.card && !row.unfolded)))
            return null
        let n = h.n - headOf(row)
        if (n < 0 || row.card || row.kind === "note")
            return { item: row, rect: Qt.rect(0, row.gap, row.width, row.height - row.gap) }
        const boxes = boxesIn(row, [])
        if (h.hidden && row.kind === "tool" && !boxes.length)
            return null   // (its details are being made)
        for (const box of boxes) {
            const places = placesIn(box)
            if (n < places.length) {
                const r = box.positionToRectangle(places[n][0])
                return { item: box, rect: r }
            }
            n -= places.length
        }
        return { item: row, rect: Qt.rect(0, row.gap, row.width, Math.min(row.height - row.gap, fm.height * 2)) }
    }

    // The marks on the rows with matches within half a screen of what you read (and the one gone to;
    // at most 600: a one-letter search marks only so many at once, again as you scroll)
    function unmark() {
        for (const m of marks)
            if (m)
                m.destroy()
        marks = []
    }
    function remark() {
        unmark()
        if (!hits.length || pane.findQuery === "")
            return
        if (!markComponent)
            markComponent = Qt.createComponent("FindMarks.qml")
        const made = [], keys = []
        for (const h of hits)
            if (keys[keys.length - 1] !== h.key)
                keys.push(h.key)
        let many = 0
        for (const key of keys) {
            const row = rowOf(key)
            if (!row || row.y + row.height < list.contentY - list.height / 2 || row.y > list.contentY + list.height * 1.5)
                continue
            const now = hit && hit.key === key ? hit.n : -1
            const head = headOf(row)
            const boxes = row.card || row.kind === "note" ? [] : boxesIn(row, [])
            if (!boxes.length || head > 0)
                made.push(markComponent.createObject(row, { current: now >= 0 && (now < head || !boxes.length) }))
            let n = now - head
            for (const box of boxes) {
                const places = placesIn(box)
                if (places.length)
                    made.push(markComponent.createObject(box, { box: box, places: places, now: n >= 0 && n < places.length ? n : -1 }))
                n -= places.length
                many += places.length
            }
            if (many > 600)
                break
        }
        marks = made
    }
    Timer {
        id: remarkSoon
        interval: 120
        onTriggered: bar.remark()
    }
    Connections {
        target: list
        function onContentYChanged() { remarkSoon.restart() }
    }
    Component.onCompleted: {
        field.text = pane.findQuery
        focusField()
        search()
    }
    Component.onDestruction: unmark()

    RowLayout {
        id: row
        anchors.centerIn: parent
        width: parent.width - Kirigami.Units.smallSpacing * 2
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            Layout.leftMargin: Kirigami.Units.smallSpacing
            source: Icons.plasma.search
            color: pane.mutedColor
        }
        PlasmaComponents3.TextField {
            id: field
            Layout.fillWidth: true
            Layout.preferredWidth: Kirigami.Units.gridUnit * 11
            Layout.minimumWidth: Kirigami.Units.gridUnit * 4
            placeholderText: i18n("Find in the chat")
            onTextChanged: if (pane.findQuery !== text) pane.findQuery = text
            Keys.onReturnPressed: event => bar.step(!!(event.modifiers & Qt.ShiftModifier))
            Keys.onEnterPressed: event => bar.step(!!(event.modifiers & Qt.ShiftModifier))
        }
        PlasmaComponents3.Label {
            Layout.preferredWidth: countWidth.advanceWidth
            textFormat: Text.PlainText
            text: bar.count
            color: pane.mutedColor
            font.pointSize: pane.pt * 0.85
            TextMetrics {
                id: countWidth
                font.pointSize: pane.pt * 0.85
                text: "888 of 888…"
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.findPrevious
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Previous match (Shift+Enter, Shift+F3)")
            onClicked: bar.step(true)
            PlasmaComponents3.ToolTip.text: text
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.findNext
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Next match (Enter, F3)")
            onClicked: bar.step(false)
            PlasmaComponents3.ToolTip.text: text
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.close
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Close (Esc)")
            onClicked: pane.closeFind()
            PlasmaComponents3.ToolTip.text: text
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }
}
