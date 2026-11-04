import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Stop on Talpy Chat's working line (ChatPane.qml, a Loader: read and made only
// while a chat it can stop works, so every window opens as quickly; VS Code
// chat.tsx the same). What Claude does now stops, as Esc in its terminal:
// Ctrl+C in its tmux pane, or Esc into a background chat through Claude's
// background service (pane.py --interrupt). The chat stays where it runs and
// takes your next message. "Stopping…" at once, till its turn ends.
IconTextButton {
    Layout.preferredHeight: pane.queueButtonHeight
    enabled: !pane.stopping
    icon.name: Icons.plasma.stopTurn
    text: pane.stopping ? i18n("Stopping…") : i18n("Stop")
    onClicked: pane.stop()
    PlasmaComponents3.ToolTip.text: pane.where === "tmux"
        ? i18n("Stop what Claude is doing now, as Ctrl+C in its tmux pane: the chat stays open there and takes your next message.")
        : i18n("Stop what Claude is doing now, as Esc in its terminal: the background chat stays and takes your next message.")
    PlasmaComponents3.ToolTip.visible: hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
