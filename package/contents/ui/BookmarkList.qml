import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "bookmarks.mjs" as Bm
import "icons.mjs" as Icons

// The chat's bookmarks (Ctrl+Shift+B, the tab row's ribbon: BookmarkPill.qml): a card over the
// conversation's top right, under the find bar while it's open, so nothing moves (ChatPane.qml's
// Loader: read and made only while it's open). Each in the chat's order: whose (Claude's dot, your
// bar), its first words, when it was written. A click goes to it, framed a moment (one further back
// than what's shown is read first: Going there…; one too far back is copied; one no longer in the
// chat says so); × on the one under the pointer takes its bookmark away. It closes once you're there,
// unless the chat is wide enough that it covers little (bookmarks.mjs staysOpen); Esc closes it.
// VS Code BookmarkList.tsx: the same words and rules
Rectangle {
    id: card

    readonly property Item logic: bookmarkLogic.item   // (Bookmarks.qml: settled, going, current; made on a click)
    // (the keys read now: a bookmark's message is here, else further back)
    readonly property var loaded: {
        const keys = new Set()
        for (const it of pane.shownList)
            keys.add(String(it.key))
        return keys
    }
    readonly property bool capped: pane.more && pane.limit >= pane.limitMax

    width: Math.min(Kirigami.Units.gridUnit * 16, scroll.width - Kirigami.Units.gridUnit * 4)
    height: Math.min(column.implicitHeight + Kirigami.Units.smallSpacing * 2,
                     scroll.height - Kirigami.Units.gridUnit * 2 - bookmarkList.anchors.topMargin)
    radius: Kirigami.Units.cornerRadius
    color: Kirigami.Theme.backgroundColor
    border.width: 1
    border.color: pane.borderColor

    function close() {
        pane.bookmarksOn = false
        replyBox.forceActiveFocus()
    }
    // A click: to it (here: there now; earlier: read first), else copied (too far back), else why not
    function go(mark, where) {
        const logic = pane.bookmarksNow()
        if (where === "here")
            logic.jump(mark.key, true)
        else if (where === "earlier")
            logic.reach(mark.key, true)
        else if (where === "far")
            pane.copyWhole(mark.key, true)
        else {
            pane.info = i18n("That message isn't in the chat any more")
            pane.infoBad = true
            infoTimer.restart()
        }
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Layout.preferredWidth
                Layout.leftMargin: Kirigami.Units.smallSpacing
                source: Icons.plasma.bookmarked
                isMask: true
                color: pane.textColor
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                text: i18n("Bookmarks")
                font.weight: Font.Bold
            }
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: pane.bookmarks.length
                color: pane.mutedColor
            }
            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.close
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Close (Ctrl+Shift+B, Esc)")
                onClicked: card.close()
                PlasmaComponents3.ToolTip.text: text
                PlasmaComponents3.ToolTip.visible: hovered
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: pane.borderColor
        }
        Text {
            visible: pane.bookmarks.length === 0
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            textFormat: Text.PlainText
            text: i18n("No bookmarks in this chat yet. Hover a message and click its bookmark, or press Ctrl+D.")
            wrapMode: Text.Wrap
            color: pane.mutedColor
            font.pointSize: pane.pt * 0.9
        }
        ListView {
            id: entries
            visible: count > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: contentHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: pane.bookmarks
            PlasmaComponents3.ScrollBar.vertical: PlasmaComponents3.ScrollBar {
                id: entriesBar
            }

            delegate: MouseArea {
                id: entry

                required property var modelData
                readonly property var mark: modelData
                readonly property string where: Bm.stateOf(mark, card.loaded, pane.more, card.capped, card.logic ? card.logic.settled : null)
                readonly property bool going: !!card.logic && card.logic.going === mark.key
                readonly property bool dim: where === "far" || where === "gone"
                readonly property bool hovered: hover.hovered

                width: entries.width - (entriesBar.visible ? entriesBar.width : 0)   // (clear of its scroll bar)
                height: Math.max(snippet.implicitHeight, side.height) + Kirigami.Units.smallSpacing * 2
                onClicked: card.go(mark, where)

                HoverShade {
                    target: entry
                    shown: entry.hovered
                }
                HoverHandler {
                    id: hover
                    cursorShape: Qt.PointingHandCursor
                }
                // the one gone to last: framed thin, no fill
                Rectangle {
                    anchors.fill: parent
                    visible: !!card.logic && card.logic.current === entry.mark.key
                    radius: Kirigami.Units.cornerRadius
                    color: "transparent"
                    border.width: 1
                    border.color: pane.youColor
                }
                // whose: Claude's dot, your bar (as the conversation marks them)
                Rectangle {
                    readonly property bool yours: entry.mark.kind === "you"
                    readonly property real line: snippetLine.height
                    x: Kirigami.Units.smallSpacing * 1.5
                    y: Kirigami.Units.smallSpacing + (yours ? 0 : Math.round((line - height) / 2))
                    width: yours ? 3 : Math.round(line * 0.42)
                    height: yours ? Math.min(snippet.height, line * 2) : width
                    radius: yours ? 1.5 : width / 2
                    color: yours ? pane.youColor : pane.claudeColor
                    opacity: entry.dim ? 0.5 : 1
                }
                TextMetrics {
                    id: snippetLine
                    font: snippet.font
                    text: "M"
                }
                Text {
                    id: snippet
                    x: Kirigami.Units.smallSpacing * 2 + Math.round(snippetLine.height * 0.42) + Kirigami.Units.smallSpacing
                    y: Kirigami.Units.smallSpacing
                    width: side.x - x - Kirigami.Units.smallSpacing
                    textFormat: Text.PlainText
                    text: entry.mark.text
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    font.family: pane.chatFamily
                    font.pointSize: pane.pt * 0.9
                    color: pane.textColor
                    opacity: entry.dim ? 0.55 : 1
                }
                // when it was written, or where it is now; × in the same place on hover, so nothing moves
                Item {
                    id: side
                    x: entry.width - width - Kirigami.Units.smallSpacing
                    y: Kirigami.Units.smallSpacing
                    width: Math.max(sideRow.implicitWidth, Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing)
                    height: Math.max(sideRow.implicitHeight, Kirigami.Units.iconSizes.small)

                    Row {
                        id: sideRow
                        anchors.right: parent.right
                        visible: !entry.hovered
                        spacing: Kirigami.Units.smallSpacing / 2
                        Loader {
                            active: entry.where === "earlier" && !entry.going
                            visible: active
                            y: Math.round((sideLine.height - height) / 2)   // (beside its first line)
                            sourceComponent: Kirigami.Icon {
                                width: Math.round(snippetLine.height * 0.9)
                                height: width
                                source: Icons.plasma.earlier
                                color: pane.mutedColor
                            }
                        }
                        TextMetrics {
                            id: sideLine
                            font: sideText.font
                            text: "0"
                        }
                        Text {
                            id: sideText
                            // (at most a third of the line, on two lines if it must: the words keep their room)
                            width: Math.min(implicitWidth, Math.round(entry.width * 0.34))
                            textFormat: Text.PlainText
                            text: entry.going ? i18n("Going there…") : entry.where === "far" ? i18n("Too far back")
                                  : entry.where === "gone" ? i18n("Not in the chat any more") : pane.timeText(entry.mark.at)
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            horizontalAlignment: Text.AlignRight
                            color: pane.mutedColor
                            font.family: pane.chatFamily
                            font.pointSize: pane.pt * 0.8
                        }
                    }
                    Loader {
                        id: remove
                        active: entry.hovered
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        sourceComponent: MouseArea {
                            width: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            height: width
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: pane.bookmarksNow().unmark(entry.mark.key)
                            Kirigami.Icon {
                                anchors.centerIn: parent
                                width: Kirigami.Units.iconSizes.small
                                height: width
                                source: Icons.plasma.cancel
                                color: Icons.color("cancel", Kirigami.Theme)
                                opacity: parent.containsMouse ? 1 : 0.8
                            }
                            PlasmaComponents3.ToolTip.text: i18n("Remove this bookmark")
                            PlasmaComponents3.ToolTip.visible: containsMouse
                            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                        }
                    }
                }

                PlasmaComponents3.ToolTip.text: !entry.hovered ? ""
                    : entry.where === "here" ? entry.mark.text + "\n" + i18n("Go to it (Alt+↑ / Alt+↓: the one before / after)")
                    : entry.where === "earlier" ? i18n("Further back than what's shown: a click reads more of the chat and goes there")
                    : entry.where === "far" ? i18n("Further back than the last 2000 steps Talpy Chat shows: a click copies it")
                    : i18n("Not in this chat any more: × removes the bookmark")
                PlasmaComponents3.ToolTip.visible: entry.hovered && !(remove.item && remove.item.containsMouse)
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }
}
