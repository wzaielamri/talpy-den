import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// Claude's turn so far, at the end of Talpy Chat's working line, before Stop:
// "8m 12s · 58 steps", the time since your message that started it and its
// steps (tool calls) since (pane.py --conversation "turn": talpy_den.TurnSoFar).
// ChatPane.qml's Loader reads and makes it only while a chat works and its
// turn is known, so every window opens as quickly. Its one clock ticks each
// second, only while the window shows that tab; nothing ticks otherwise.
// VS Code chat.tsx TurnMeta: the same words and rule (shared/pane.ts turnText,
// turnTickIn).
PlasmaComponents3.Label {
    id: meta

    property real now: Date.now()
    readonly property var turn: pane.turnNow || ({ startedAt: now, steps: 0 })
    readonly property real ms: Math.max(0, now - turn.startedAt)
    readonly property string time: {
        const s = Math.floor(ms / 1000)
        if (s < 60)
            return i18nc("Claude's turn so far: seconds", "%1s", s)
        const m = Math.floor(s / 60)
        return m < 60 ? i18nc("Claude's turn so far: minutes and seconds", "%1m %2s", m, s % 60)
                      : i18nc("Claude's turn so far: hours, minutes and seconds", "%1h %2m %3s", Math.floor(m / 60), m % 60, s % 60)
    }

    textFormat: Text.PlainText
    text: turn.steps > 0 ? i18np("%2 · %1 step", "%2 · %1 steps", turn.steps, time) : time
    color: root.stateColor("working")
    opacity: 0.75
    font.family: pane.chatFamily
    font.pointSize: pane.pt

    Timer {
        running: meta.visible && pane.shown && pane.conversationTab
        repeat: true
        interval: 1000 - meta.ms % 1000 + 20
        onTriggered: meta.now = Date.now()
        onRunningChanged: if (running) meta.now = Date.now()
    }

    HoverHandler {
        id: hover
    }
    PlasmaComponents3.ToolTip.text: i18np("Claude's turn so far: %2 since your message, %1 step (its tool calls, in the Steps tab).",
                                          "Claude's turn so far: %2 since your message, %1 steps (its tool calls, in the Steps tab).",
                                          turn.steps, time)
    PlasmaComponents3.ToolTip.visible: hover.hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
