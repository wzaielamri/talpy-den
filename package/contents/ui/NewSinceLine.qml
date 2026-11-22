import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "newsince.mjs" as NewSince

// ───── New since 14:32: a thin line in Talpy Chat's conversation above the first item that came in while
// you were away (pane.newSince: Since you last looked's point, where its click goes; newsince.mjs), in the
// accent colour, as your band and a bookmark's ribbon are. ChatPane makes one only while there's a line, and
// says when it goes (its read timer, which runs only once the line has been seen on this tab: here, once all
// of it has been in the view for a moment with the list at rest, the window shown and the list done going
// where it goes; looked at only till then, as the list moves). It's put where SideFromLine.qml puts its own:
// in the room the list already leaves above that row (its gap, at least the line's height there: ChatPane
// roomAbove, lineRoom), so it takes no room of its own; above the list's first row, last in the list's head. Only
// where that item is in the list: nothing more is read for it (the bar's click reads further back, as a
// bookmark's); a row not made yet is looked for again as the list makes rows, only then. Nothing in it
// moves. VS Code chat.tsx .pane-new-since: the same words.
Item {
    id: mark
    visible: false   // (a holder: its line is put in the conversation)

    readonly property string key: pane.newSinceAt
    readonly property string label: {
        void pane.today   // (past midnight: "Yesterday 14:32")
        return pane.newSince ? NewSince.newSinceText(pane.timeText(pane.newSince.since)) : ""
    }
    property Item row: null       // (the item's row, once it's made)
    property bool missing: false  // (listed, its row not made yet)
    property int missingAt: -1    // (where it's listed then)
    readonly property bool first: row !== null && row.gap <= 0
    property bool keepTop: false  // (put in the head while the list is at its top: the top stays in view)
    // Seen on this tab (newsince.mjs newSinceLooking, newSinceSeen) once all of it has been in the view for
    // NEW_SINCE_SEEN_MS with the list at rest, the window shown and the list done going where it goes
    // (pane.listSettling): a glimpse as the list moves past doesn't count. Looked at only till then, as the list
    // moves, grows or is resized, the line is placed or the window shown again; each move starts the wait again
    readonly property bool steps: pane.listTab === "steps"
    readonly property bool unseen: pane.newSince !== null && !NewSince.newSinceSeenOn(pane.newSince, mark.steps) && pane.shown
    function looking() {
        const it = inGap.item && inGap.visible ? inGap.item : inHead.item && inHead.visible ? inHead.item : null
        if (!unseen || !it)
            return false
        const p = it.mapToItem(list, 0, 0)
        return NewSince.newSinceLooking(pane.newSince, mark.steps, pane.shown, NewSince.newSinceInView(p.y, it.height, list.height),
                                         !pane.scrolling(), !pane.listSettling)
    }
    function look(moved) {
        if (!looking())
            seenWait.stop()
        else if (moved || !seenWait.running)
            seenWait.restart()
    }
    function moved() { look(true) }
    function glance() { look(false) }
    Timer {
        id: seenWait
        interval: NewSince.NEW_SINCE_SEEN_MS
        onTriggered: if (mark.looking())
            pane.newSince = NewSince.newSinceSeen(pane.newSince, mark.steps)
    }
    onUnseenChanged: Qt.callLater(glance)
    onStepsChanged: Qt.callLater(moved)
    onRowChanged: Qt.callLater(moved)
    Connections {
        target: list
        enabled: mark.unseen
        function onContentYChanged() { Qt.callLater(mark.moved) }
        function onContentHeightChanged() { Qt.callLater(mark.moved) }
        function onHeightChanged() { Qt.callLater(mark.moved) }
        function onMovingChanged() { Qt.callLater(mark.moved) }
    }
    Connections {
        target: pane
        enabled: mark.unseen
        function onListSettlingChanged() { Qt.callLater(mark.glance) }
    }

    function place() {
        if (row && row.listed && row.key === key) {
            missing = false
            return
        }
        let found = null, listed = false, at = -1
        if (key !== "") {
            const shown = pane.shownList
            for (let i = 0; i < shown.length; i++)
                if (String(shown[i].key) === key) {
                    listed = true
                    at = i
                    const r = list.itemAtIndex(i)
                    found = r && r.listed ? r : null
                    break
                }
        }
        missing = listed && found === null
        missingAt = missing ? at : -1
        if (found !== row) {
            keepTop = found !== null && found.gap <= 0 && list.contentY <= list.originY + 1
            row = found
        }
    }
    onKeyChanged: place()
    Component.onCompleted: place()
    Connections {
        target: pane
        function onShownListChanged() { mark.place() }
    }
    // (its row not made yet: looked at again as the list makes rows (they're its content's children), that
    // one index only; the list changed meanwhile: place() runs for that anyway)
    function placeMissing() {
        if (!missing)
            return
        const shown = pane.shownList, i = missingAt
        if (i < 0 || i >= shown.length || String(shown[i].key) !== key)
            return
        const r = list.itemAtIndex(i)
        if (r && r.listed) {
            missing = false
            missingAt = -1
            keepTop = r.gap <= 0 && list.contentY <= list.originY + 1
            row = r
        }
    }
    Connections {
        target: list.contentItem
        enabled: mark.missing
        function onChildrenChanged() { Qt.callLater(mark.placeMissing) }
    }
    Connections {   // (the head grew: the top in view again, once)
        target: list
        enabled: mark.keepTop
        function onOriginYChanged() {
            mark.keepTop = false
            list.contentY = list.originY
        }
    }
    Timer {
        running: mark.keepTop
        interval: 500
        onTriggered: mark.keepTop = false
    }
    function headOf(item) {   // (the column in the list's head: ChatPane's listHead)
        for (const k of item ? item.children : [])
            if (k.objectName === "listHead")
                return k
        return null
    }

    Component {
        id: rule

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            // (its tooltip on the whole line)
            HoverHandler {
                id: tipHover
            }
            PlasmaComponents3.ToolTip.text: NewSince.NEW_SINCE_TIP
            PlasmaComponents3.ToolTip.visible: tipHover.hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: pane.youColor
            }
            Text {
                textFormat: Text.PlainText
                text: mark.label
                color: pane.youColor
                font: pane.newSinceFont
            }
            Rectangle {
                Layout.preferredWidth: Kirigami.Units.largeSpacing
                implicitHeight: 1
                color: pane.youColor
            }
        }
    }

    // In the room above the item (its row's gap, at least the line's height: ChatPane lineRoom), in its middle
    Loader {
        id: inGap
        parent: mark.row && !mark.first ? mark.row : mark
        active: mark.row !== null && !mark.first
        visible: active && mark.row.shows
        width: parent ? parent.width : 0
        y: mark.row ? Math.round((mark.row.gap - height) / 2) : 0
        sourceComponent: rule
        onLoaded: Qt.callLater(mark.look)
    }
    // Above the list's first row: the last thing in its head
    Loader {
        id: inHead
        readonly property Item head: mark.first ? mark.headOf(list.headerItem) : null
        parent: head || mark
        active: head !== null
        visible: active
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        sourceComponent: rule
        onLoaded: Qt.callLater(mark.look)
    }
}
