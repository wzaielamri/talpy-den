import QtQuick
import QtQuick.Layouts

// What stands at a line's end (a chat's state; a folder and how long ago):
// the row's HoverButtons cover its end while they show, so it's cut there,
// in place. Its child takes the whole width (width: <this>.width). While they
// show it's at least as wide as they are, so what stands before it (the
// name) is cut where they start, not run under them (a starred plan's end,
// with no folder, is narrower than its eight buttons). Put it right before
// them in the line's RowLayout: it takes back the spacing the layout puts
// before them (a negative right margin here does; their left margin
// didn't), so it ends where a line without buttons ends.
Item {
    id: end

    property real covered: 0                // HoverButtons.covering
    default property alias content: window.data

    Layout.minimumWidth: covered
    Layout.rightMargin: parent && parent.spacing !== undefined ? -parent.spacing : 0

    Item {
        id: window
        width: Math.max(0, end.width - end.covered)
        height: end.height
        clip: true
    }
}
