import QtQuick
import org.kde.kirigami as Kirigami

// The matches of Talpy Chat's search in one of a row's texts (box: a TextEdit), marked over its
// letters (see-through: a code block's own background would hide a mark under them), the one gone
// to framed; without a text (a step's line, a card, a note: box null), a light tint over the whole
// row. FindBar.qml makes these on the rows near what you read only, and takes them away again (as
// you scroll, search for something else, or close it): no row has anything of the search otherwise
Item {
    id: marks

    property Item box: null
    property var places: []      // [[start, end]…] in box's text (getText)
    property int now: -1         // which of them is the one gone to (-1: none here)
    property bool current: false // (a tint: its row has the one gone to)
    readonly property color tone: Kirigami.Theme.neutralTextColor

    x: 0
    y: box ? 0 : parent.gap || 0
    width: parent.width
    height: parent.height - y
    z: 1

    Rectangle {
        visible: marks.box === null
        anchors.fill: parent
        radius: Kirigami.Units.cornerRadius
        color: Qt.rgba(marks.tone.r, marks.tone.g, marks.tone.b, marks.current ? 0.22 : 0.1)
        border.width: marks.current ? 2 : 0
        border.color: marks.tone
    }
    Repeater {
        model: marks.box ? marks.places : []
        delegate: Rectangle {
            required property var modelData
            required property int index
            readonly property rect from: marks.box.positionToRectangle(modelData[0])
            readonly property rect to: marks.box.positionToRectangle(modelData[1])
            x: from.x
            y: from.y
            width: Math.max(2, (to.y === from.y ? to.x : marks.box.width) - from.x)
            height: from.height
            radius: 2
            color: Qt.rgba(marks.tone.r, marks.tone.g, marks.tone.b, index === marks.now ? 0.45 : 0.28)
            border.width: index === marks.now ? 2 : 0
            border.color: marks.tone
        }
    }
}
