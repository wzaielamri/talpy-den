import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "sides.mjs" as Sides

// ── Side questions see from here ──: a line in Talpy Chat's conversation above the message the side
// questions' part starts at (Ask from here, Explain this: Sides.qml part), drawn as the day lines are
// (DayLine.qml). SidePanel.qml makes one for the window, only while it's open with a part. It sits in the
// room the list already leaves above that message (a new turn's gap: ChatPane's row gap), so no row
// changes its height and nothing you read moves. Above the list's first row (no gap there) it goes in the
// list's head, which grows upward: the rows stay where they are (at the top, the top stays in view). Only
// where that message is in the list: nothing more is read for it (pane.shownList); a row not made yet is
// looked for again as frames are drawn, only then. Plain items, no theme of their own. VS Code chat.tsx:
// the same words.
Item {
    id: from
    visible: false   // (a holder: its line is put in the conversation)

    readonly property string key: panel.part ? String(panel.part.key) : ""
    property Item row: null       // (the message's row, once it's made)
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
        function onShownListChanged() { from.place() }
    }
    Connections {
        target: pane
        enabled: from.missing
        function onFrameSwapped() { from.place() }
    }
    Connections {   // (the head grew: the top in view again, once)
        target: list
        enabled: from.keepTop
        function onOriginYChanged() {
            from.keepTop = false
            list.contentY = list.originY
        }
    }
    Timer {
        running: from.keepTop
        interval: 500
        onTriggered: from.keepTop = false
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
        font.weight: Font.DemiBold
    }
    Component {
        id: rule

        RowLayout {
            spacing: Kirigami.Units.largeSpacing

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: pane.borderColor
            }
            Text {
                textFormat: Text.PlainText
                text: Sides.SIDE_FROM_LINE
                color: pane.mutedColor
                font: lineFm.font
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: pane.borderColor
            }
        }
    }

    // In the room above the message (a new turn's gap), in its middle
    Loader {
        parent: from.row && !from.first ? from.row : from
        active: from.row !== null && !from.first
        visible: active && from.row.shows
        width: parent ? parent.width : 0
        y: from.row ? Math.max(0, Math.round((from.row.gap - height) / 2)) : 0
        sourceComponent: rule
    }
    // Above the list's first row: the last thing in its head
    Loader {
        readonly property Item head: from.first ? from.headOf(list.headerItem) : null
        parent: head || from
        active: head !== null
        visible: active
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        sourceComponent: rule
    }
}
