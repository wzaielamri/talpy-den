import QtQuick
import QtQuick.Shapes

// A bookmarked message's ribbon, in place of its mark (Claude's dot, your › or $), in the same colour
// and on the same spot: over the mark, on its own ground, so nothing moves and no text is covered.
// Bookmarks.qml makes one on each bookmarked row only (a child of the row's rowMark), at most 100.
// Drawn here (Breeze's bookmarks-bookmarked, the filled ribbon: the list's and the hover bar's icon),
// not a themed icon: a window making 100 at once stays as quick.
Item {
    id: flag
    objectName: "bookmarkFlag"

    property Item row: null
    property string kind: "claude"
    readonly property bool yours: kind === "you"

    anchors.fill: parent
    z: 2

    // (over the mark only, not your band's bar beside it: your band's colour, or the window's)
    Rectangle {
        x: ribbon.x - 1
        width: ribbon.width + 2
        height: parent.height
        color: flag.yours ? pane.youGround : surface.color
    }
    Shape {
        id: ribbon
        width: Math.round(fm.height * 0.8)
        height: width
        // (where the mark is: Claude's dot a little left of the middle, as Dot draws it; yours in the middle)
        readonly property real dot: Math.round(flag.height * 0.42)
        x: flag.yours ? Math.round((flag.width - width) / 2) : Math.round((flag.width - dot) * 0.4 + dot / 2 - width / 2)
        anchors.verticalCenter: parent.verticalCenter
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: flag.yours ? pane.youColor : pane.claudeColor
            strokeWidth: -1
            scale: Qt.size(ribbon.width / 16, ribbon.height / 16)
            PathPolyline {   // (16 by 16: m4 2v12l4-1.594 4 1.594v-12z)
                path: [Qt.point(4, 2), Qt.point(12, 2), Qt.point(12, 14), Qt.point(8, 12.406), Qt.point(4, 14), Qt.point(4, 2)]
            }
        }
    }
}
