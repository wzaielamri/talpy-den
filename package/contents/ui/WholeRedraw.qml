import QtQuick

// For a rich-text TextEdit whose text has tables (a reply's code blocks, its
// tables and quotes, a plan's). When a selection in it changes, Qt draws only
// the part that changed again, and with it the text of every table before
// that part once more, over what's there already (Qt 6.11,
// QQuickTextEdit::updatePaintNode: a table's text starts at the text's start
// again, whatever was kept): a code block looked bold, until a selection in
// the block itself drew it anew. Here a selection change draws the whole
// text once instead: a change of the selection's color does that, so it's a
// hair's breadth another each time (not one you can see).
//
//     TextEdit {
//         selectionColor: redraw.color
//         onSelectionStartChanged: redraw.again()
//         onSelectionEndChanged: redraw.again()
//         WholeRedraw { id: redraw; base: Kirigami.Theme.focusColor; on: parent.text.indexOf("<table") >= 0 }
//     }
QtObject {
    id: redraw

    property color base              // the selection's color
    property bool on: true           // (a text without tables is drawn right as it is)
    property bool flip: false
    readonly property color color: flip ? Qt.rgba(base.r, base.g, base.b, base.a * 0.996) : base

    function again() {
        if (on)
            flip = !flip
    }
}
