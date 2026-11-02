import QtQuick
import QtQuick.Layouts

// What stands at a line's end (a chat's state; a folder and how long ago):
// the row's HoverButtons cover its end while they show, so it's cut there,
// in place. Its child takes the whole width (width: <this>.width). While they
// show it's at least as wide as they are, so what stands before it (the
// name) is cut where they start, not run under them (a starred plan's end,
// with no folder, is narrower than its eight buttons).
Item {
    id: end

    property real covered: 0                // HoverButtons.covering
    default property alias content: window.data

    Layout.minimumWidth: covered

    Item {
        id: window
        width: Math.max(0, end.width - end.covered)
        height: end.height
        clip: true
    }
}
