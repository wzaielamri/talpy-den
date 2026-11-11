import QtQuick

// For a rich-text TextEdit whose text has tables (a reply's code blocks, its
// tables and quotes, a plan's). When a selection in it is drawn again, Qt
// draws only that part, and with it the text of every table before that part
// once more, over what's there already (Qt 6.11,
// QQuickTextEdit::updatePaintNode: a table's text starts at the text's start
// again, whatever was kept): a table looked bold, until a selection in it
// drew it anew. Here the whole text is drawn once instead: a change of the
// selection's color does that, so it's a hair's breadth another each time
// (not one you can see).
//
//     TextEdit {
//         id: reply
//         WholeRedraw { edit: reply; base: Kirigami.Theme.focusColor }
//     }
//
// Qt draws a selection again not only when it changes: every move of the
// mouse while its button is down, and its release, do too (QQuickTextControl
// says the selection changed on each, changed or not), and so does a cursor
// that moved. selectedTextChanged and cursorPositionChanged are the two that
// come each time, where selectionStart and selectionEnd come only for a
// selection that isn't the same: with those alone a table got bolder with
// every move of a drag that left the selection as it was.
//
// It sets the TextEdit's selectionColor itself (base, the color it would
// have). A text nobody selected in is left alone (Qt draws nothing again
// there), and whether the text has a table is looked at only then (reading a
// rich text back is work: a reply nobody selects in costs nothing).
Item {
    id: redraw

    required property TextEdit edit
    property color base              // the selection's color
    property bool flip: false
    property bool selected: false    // a selection was in it, now or before
    property int tables: -1          // 1: the text has tables, 0: none, -1: not looked yet
    visible: false
    width: 0
    height: 0

    function again() {
        if (!selected && edit.selectionStart === edit.selectionEnd)
            return
        selected = true
        if (tables < 0)   // (a plain text has none, whatever it says: a page's source)
            tables = edit.textFormat !== TextEdit.PlainText && edit.text.indexOf("<table") >= 0 ? 1 : 0
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
        function onSelectedTextChanged() {
            redraw.again()
        }
        function onCursorPositionChanged() {
            redraw.again()
        }
        function onTextChanged() {
            redraw.tables = -1
        }
    }
}
