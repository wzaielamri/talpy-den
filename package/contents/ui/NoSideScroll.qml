import QtQuick

// A box you write in, its text wrapped, in a ScrollView: never scrolled sideways
// (in its TextArea: NoSideScroll { view: the ScrollView }). Qt's TextArea keeps its
// cursor in view by moving the ScrollView's contentX, sideways too, which its
// contentWidth doesn't hold back; and spaces at a line's end hang past the box's edge
// instead of wrapping. Text pasted from a terminal has each line padded with spaces
// to its width: → or End along such a line slid all the text out of view to the
// left, a letter at a time, and it stayed there. Now the text stays where it is (the
// cursor in those spaces goes on past the edge, as the spaces do).
Connections {
    property Item view
    target: view ? view.contentItem : null
    function onContentXChanged() {
        if (target.contentX !== 0)
            target.contentX = 0
    }
}
