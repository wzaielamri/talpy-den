import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// The hero's ticker: one line with what the chats do right now, e.g.
// "fix parser ▸ Edit: parser.py +12 −3". A chat's new step shows as it
// comes (at once with live mode, else at each check); with several chats at
// work, one that did something new goes first, and with nothing new they
// take turns. A click opens that chat's pane.
Item {
    id: ticker

    // [{key, name, text, host, session}] of the working chats (root.tickerItems)
    property var items: []
    property var shown: null       // the item on show
    property var queue: []         // keys of chats with a step not shown yet
    property var noted: ({})       // key -> its text when last noted
    property real shownAt: 0
    readonly property int dwellMs: 1500   // another chat's step waits this long behind the one on show
    readonly property int turnMs: 4000    // with nothing new, the next chat after this

    implicitHeight: row.implicitHeight
    visible: shown !== null
    // (a closed popup, or a desktop a window covers, still has it "visible")
    readonly property bool seen: visible && root.dashboardShown && !root.coveredByWindow && !root.underWindows(ticker)
    onSeenChanged: if (seen) shownAt = Date.now()   // (the one on show gets its turn)

    function byKey(key) {
        return items.find(it => it.key === key) || null
    }

    function show(item) {
        const another = !shown || shown.key !== item.key
        shown = item
        if (another) {
            shownAt = Date.now()
            if (seen)
                fadeIn.restart()
        }
    }

    // the next chat: the first with a step not shown yet, else the one after this
    function advance() {
        while (queue.length) {
            const next = byKey(queue[0])
            queue = queue.slice(1)
            if (next) {
                show(next)
                return
            }
        }
        if (items.length === 0) {
            shown = null
            return
        }
        const at = shown ? items.findIndex(it => it.key === shown.key) : -1
        show(items[(at + 1) % items.length])
    }

    onItemsChanged: {
        const wanted = {}
        let waiting = queue.filter(k => items.some(it => it.key === k))
        for (const it of items) {
            wanted[it.key] = true
            if (noted[it.key] !== it.text) {
                noted[it.key] = it.text
                if ((!shown || shown.key !== it.key) && waiting.indexOf(it.key) < 0)
                    waiting.push(it.key)
            }
        }
        for (const key in noted)
            if (!wanted[key])
                delete noted[key]
        queue = waiting
        const mine = shown ? byKey(shown.key) : null
        if (mine)
            show(mine)   // (its own new step: at once)
        else if (shown || items.length)
            advance()
        else
            shown = null
    }

    Timer {
        interval: 500
        repeat: true
        running: ticker.seen && ticker.items.length > 1
        onTriggered: {
            const on = Date.now() - ticker.shownAt
            if ((ticker.queue.length && on >= ticker.dwellMs) || on >= ticker.turnMs)
                ticker.advance()
        }
    }

    NumberAnimation {
        id: fadeIn
        target: row
        property: "opacity"
        from: 0.15
        to: 1
        duration: 220
        easing.type: Easing.OutCubic
    }

    RowLayout {
        id: row
        width: parent.width
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.maximumWidth: ticker.width * 0.4
            visible: ticker.items.length > 1 || (ticker.shown !== null && ticker.shown.host !== "")
            text: ticker.shown ? (ticker.shown.host ? root.hostLabel(ticker.shown.host) + ": " : "") + ticker.shown.name : ""
            font: Kirigami.Theme.smallFont
            elide: Text.ElideRight
            opacity: 0.65
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: ticker.shown ? "▸ " + ticker.shown.text : ""
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            font.underline: tickerMouse.containsMouse
            color: Kirigami.Theme.focusColor
            elide: Text.ElideRight
        }
    }

    MouseArea {
        id: tickerMouse
        anchors.fill: row
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (ticker.shown)
                root.openPane(ticker.shown.session, ticker.shown.host, "chat")
        }
        PlasmaCore.ToolTipArea {
            anchors.fill: parent
            textFormat: Text.PlainText
            active: ticker.shown !== null
            mainText: ticker.shown ? i18n("Open %1 in Talpy Chat", ticker.shown.name) : ""
            subText: ticker.shown ? ticker.shown.text : ""
        }
    }
}
