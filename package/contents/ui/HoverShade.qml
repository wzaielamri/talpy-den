import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// The faint shade over a whole line while the pointer is on it, as a row in
// VS Code's list and a step in the chat pane (a tint of the text color):
// under a chat's row, a recent chat's, a plan's, a memory's, a queued task's.
// It covers `target`, `side` past its left and right (the list's gutter) and
// `pad` above and below, from wherever it is in it, drawn under what's after
// it. A layout has no background, and lays out every item in it, so put it
// first in a line whose layout has no spacing (empty, it takes no room
// there; a layout adds its spacing after even an empty item, and a negative
// margin doesn't take that back), or in the line's first item that isn't a
// layout, with z -1 (under that item too); in a plain item, anywhere first.
Item {
    id: shade

    required property Item target
    property bool shown: false
    property real side: 0
    property real pad: 0
    // in a list's row: the row's colors (ListPalette.qml), else the theme's
    property var colors: null
    Layout.preferredWidth: 0
    Layout.preferredHeight: 0

    property bool made: false   // (shown once: kept)
    Loader {   // (made the first time the line is hovered: most never are)
        active: shade.shown || shade.made
        onLoaded: shade.made = true
        sourceComponent: Rectangle {
            // where it is in target (bound to every item's place on the way)
            readonly property point offset: {
                let x = 0, y = 0
                for (let item = shade; item && item !== shade.target; item = item.parent) {
                    x += item.x
                    y += item.y
                }
                return Qt.point(x, y)
            }
            x: -offset.x - shade.side
            y: -offset.y - shade.pad
            width: shade.target.width + 2 * shade.side
            height: shade.target.height + 2 * shade.pad
            radius: Kirigami.Units.cornerRadius
            color: shade.colors ? shade.colors.shade : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)
            // (made on a hover: from nothing, as every later one)
            property bool ready: false
            Component.onCompleted: ready = true
            opacity: shade.shown && ready ? 1 : 0
            visible: opacity > 0
            Behavior on opacity {
                NumberAnimation { duration: Kirigami.Units.shortDuration }
            }
        }
    }
}
