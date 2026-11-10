import QtQuick
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A bookmarked message's ribbon, in place of its mark (Claude's dot, your › or $), in the same colour
// and on the same spot: over the mark, on its own ground, so nothing moves and no text is covered.
// Bookmarks.qml makes one on each bookmarked row only (a child of the row's rowMark), at most 100.
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
    Kirigami.Icon {
        id: ribbon
        width: Math.round(fm.height * 0.8)
        height: width
        // (where the mark is: Claude's dot a little left of the middle, as Dot draws it; yours in the middle)
        readonly property real dot: Math.round(flag.height * 0.42)
        x: flag.yours ? Math.round((flag.width - width) / 2) : Math.round((flag.width - dot) * 0.4 + dot / 2 - width / 2)
        anchors.verticalCenter: parent.verticalCenter
        source: Icons.plasma.bookmarked
        isMask: true
        color: flag.yours ? pane.youColor : pane.claudeColor
    }
}
