import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "newsince.mjs" as NewSince

// ───── New since 14:32: a thin line in Talpy Chat's conversation above the first item that came in while
// you were away (pane.newSince: Since you last looked's point, where its click goes; newsince.mjs), in the
// accent colour, as your band and a bookmark's ribbon are. ChatPane makes one only while there's a line, and
// says when it goes (its one timer). It's put where SideFromLine.qml puts its own: in the room the list
// already leaves above that row (its gap), so no row changes its height and nothing you read moves; above
// the list's first row, last in the list's head. Only where that item is in the list: nothing more is read
// for it (the bar's click reads further back, as a bookmark's); a row not made yet is looked for again as
// frames are drawn, only then. Nothing in it moves. VS Code chat.tsx .pane-new-since: the same words.
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
    readonly property bool first: row !== null && row.gap <= 0
    property bool keepTop: false  // (put in the head while the list is at its top: the top stays in view)

    function place() {
        if (row && row.listed && row.key === key) {
            missing = false
            return
        }
        let found = null, listed = false
        if (key !== "") {
            const shown = pane.shownList
            for (let i = 0; i < shown.length; i++)
                if (String(shown[i].key) === key) {
                    listed = true
                    const r = list.itemAtIndex(i)
                    found = r && r.listed ? r : null
                    break
                }
        }
        missing = listed && found === null
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
    Connections {
        target: pane
        enabled: mark.missing
        function onFrameSwapped() { mark.place() }
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

    FontMetrics {
        id: lineFm
        font.family: pane.chatFamily
        font.pointSize: pane.pt * 0.8
    }
    Component {
        id: rule

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: pane.youColor
            }
            Text {
                textFormat: Text.PlainText
                text: mark.label
                color: pane.youColor
                font: lineFm.font

                HoverHandler {
                    id: tipHover
                }
                PlasmaComponents3.ToolTip.text: NewSince.NEW_SINCE_TIP
                PlasmaComponents3.ToolTip.visible: tipHover.hovered
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            Rectangle {
                Layout.preferredWidth: Kirigami.Units.largeSpacing
                implicitHeight: 1
                color: pane.youColor
            }
        }
    }

    // In the room above the item (its row's gap), the line in its middle: where there's little (a step right
    // after a step), its words reach a little above and below, at the window's right, where a row's text
    // seldom is; the line itself never crosses a row's text
    Loader {
        parent: mark.row && !mark.first ? mark.row : mark
        active: mark.row !== null && !mark.first
        visible: active && mark.row.shows
        width: parent ? parent.width : 0
        y: mark.row ? Math.round((mark.row.gap - height) / 2) : 0
        sourceComponent: rule
    }
    // Above the list's first row: the last thing in its head
    Loader {
        readonly property Item head: mark.first ? mark.headOf(list.headerItem) : null
        parent: head || mark
        active: head !== null
        visible: active
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        sourceComponent: rule
    }
}
