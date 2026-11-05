import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// "3 new ↓" over the bottom of Talpy Chat's conversation, while you're
// scrolled up and something came in below (ChatPane.qml: made only then, over
// the list, so it moves nothing; pane.unseen counts what the tab shows). A
// click goes to the end; it's gone once you're there. VS Code chat.tsx
// .pane-below: the same words and rule (shared/pane.ts newBelow).
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
        text: i18np("%1 new ↓", "%1 new ↓", pane.unseen)
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
    PlasmaComponents3.ToolTip.text: i18np("One new item below, since you scrolled up. Click to go to the end.",
                                          "%1 new items below, since you scrolled up. Click to go to the end.", pane.unseen)
    PlasmaComponents3.ToolTip.visible: hover.hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
