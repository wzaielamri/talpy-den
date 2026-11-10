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
//         id: reply
//         WholeRedraw { edit: reply; base: Kirigami.Theme.focusColor }
//     }
//
// It sets the TextEdit's selectionColor itself (base, the color it would
// have), and looks whether the text has a table only when a selection first
// changes (reading a rich text back is work: a reply nobody selects in costs
// nothing).
Item {
    id: redraw

    required property TextEdit edit
    property color base              // the selection's color
    property bool flip: false
    property int tables: -1          // 1: the text has tables, 0: none, -1: not looked yet
    visible: false
    width: 0
    height: 0

    function again() {
        if (tables < 0)
            tables = edit.text.indexOf("<table") >= 0 ? 1 : 0
        if (tables > 0)
            flip = !flip
    }

    Binding {
        target: redraw.edit
        property: "selectionColor"
        value: redraw.flip ? Qt.rgba(redraw.base.r, redraw.base.g, redraw.base.b, redraw.base.a * 0.996) : redraw.base
    }
    Connections {
        target: redraw.edit
        function onSelectionStartChanged() {
            redraw.again()
        }
        function onSelectionEndChanged() {
            redraw.again()
        }
        function onTextChanged() {
            redraw.tables = -1
        }
    }
}
