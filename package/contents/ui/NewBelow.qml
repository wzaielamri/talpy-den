import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// "↓ Latest" over the bottom of Talpy Chat's conversation whenever it isn't at its newest (a
// bookmark gone to, a search's match, scrolled up), "↓ 3 new" once something came in below
// meanwhile (ChatPane.qml: made only then, over the list, so it moves nothing; pane.unseen counts
// what the tab shows). A click goes back to the newest, as the chat is read at first (pane.toEnd);
// it's gone once you're there. Nothing in it moves. VS Code chat.tsx .pane-below: the same words
// and rule (shared/pane.ts newText, newHint, newBelow).
Rectangle {
    implicitWidth: label.implicitWidth + Kirigami.Units.gridUnit
    implicitHeight: label.implicitHeight + Kirigami.Units.smallSpacing * 2
    radius: height / 2
    color: Kirigami.Theme.focusColor   // (the accent: highlightColor is a pale tint in a Plasma 6 window)
    border.width: 1
    border.color: hover.hovered ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.focusColor

    PlasmaComponents3.Label {
        id: label
        anchors.centerIn: parent
        textFormat: Text.PlainText
        text: pane.unseen > 0 ? i18np("↓ %1 new", "↓ %1 new", pane.unseen) : i18n("↓ Latest")
        color: Kirigami.Theme.highlightedTextColor
        font.pointSize: pane.pt * 0.85
    }
    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: pane.toEnd()
    }
    PlasmaComponents3.ToolTip.text: pane.unseen > 0
        ? i18np("One new item below, since you scrolled up. Click to go back to the latest.",
                "%1 new items below, since you scrolled up. Click to go back to the latest.", pane.unseen)
        : i18n("Back to the latest point of the chat")
    PlasmaComponents3.ToolTip.visible: hover.hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
