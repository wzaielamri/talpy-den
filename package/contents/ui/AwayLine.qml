import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// "Since you last looked: 12 steps · 2 files changed · tests passed", a line under Talpy Chat's
// conversation when its window shows a chat that went on without you (ChatPane.qml: made only
// then; pane.away is pane.py's --away answer, turns.Away). A click goes to where you left (Claude's
// first reply since; on Steps, the first step); scrolling, sending or × closes it. VS Code chat.tsx
// .pane-away: the same words and rules (shared/pane.ts awayHead, awayParts, awayTip).
Rectangle {
    id: line
    readonly property var away: pane.away
    readonly property string head: away.from === "seen" ? i18n("Since you last looked") : i18n("Since your last message")
    readonly property string parts: {
        const out = []
        const more = away.partial   // (read from after then: "12+ steps", at least)
        if (away.steps)
            out.push(more ? i18n("%1+ steps", away.steps) : i18np("%1 step", "%1 steps", away.steps))
        else if (away.replies)
            out.push(more ? i18n("%1+ replies", away.replies) : i18np("%1 reply", "%1 replies", away.replies))
        if (away.fileCount)
            out.push(more ? i18n("%1+ files changed", away.fileCount) : i18np("%1 file changed", "%1 files changed", away.fileCount))
        if (away.test)
            out.push(away.test.ok ? i18n("tests passed") : i18n("tests failed"))
        if (pane.permission !== null)   // (it waits on a prompt now, as its row says: the ask box shows)
            out.push(i18n("it waits for your answer"))
        else if (away.asks === "question")
            out.push(i18n("it asks you something"))
        return out.join(" · ")
    }
    readonly property string tip: {
        const when = pane.timeText(away.since)
        const out = [away.from === "seen" ? i18n("Since a Talpy Chat window last showed this chat, at %1", when)
                                          : i18n("Since your last message, at %1", when)]
        if (away.fileCount) {
            out.push("", i18n("Files changed:"))
            for (const f of away.files)
                out.push("  " + f)
            if (away.fileCount > away.files.length)
                out.push("  " + i18n("and %1 more", away.fileCount - away.files.length))
        }
        if (away.test)
            out.push("", (away.test.ok ? i18n("Tests passed: %1", away.test.command) : i18n("Tests failed: %1", away.test.command)))
        out.push("", i18n("Click to go to where you left. Scrolling or × closes it."))
        return out.join("\n")
    }

    implicitHeight: row.implicitHeight + Kirigami.Units.smallSpacing
    radius: Kirigami.Units.cornerRadius
    color: Qt.rgba(Kirigami.Theme.focusColor.r, Kirigami.Theme.focusColor.g, Kirigami.Theme.focusColor.b, 0.08)
    border.width: 1
    border.color: Kirigami.Theme.focusColor

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: Kirigami.Units.largeSpacing
        anchors.rightMargin: Kirigami.Units.smallSpacing * 0.5
        spacing: Kirigami.Units.smallSpacing
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            textFormat: Text.StyledText
            text: "<b>" + line.head.replace(/&/g, "&amp;").replace(/</g, "&lt;") + ":</b> "
                  + line.parts.replace(/&/g, "&amp;").replace(/</g, "&lt;")
            elide: Text.ElideRight
            maximumLineCount: 1
            font.pointSize: pane.pt * 0.9
            font.underline: hover.hovered
            HoverHandler {
                id: hover
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                gesturePolicy: TapHandler.ReleaseWithinBounds
                onTapped: pane.goAway()
            }
            PlasmaComponents3.ToolTip.text: line.tip
            PlasmaComponents3.ToolTip.visible: hover.hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.close
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Close")
            Accessible.name: i18n("Close")
            implicitWidth: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
            implicitHeight: implicitWidth
            onClicked: pane.away = null
            PlasmaComponents3.ToolTip.text: text
            PlasmaComponents3.ToolTip.visible: hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }
}
