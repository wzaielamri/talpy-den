import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// A new chat's ⚙ line in Talpy Chat (ChatPane.qml, a Loader: made only in a
// new chat's window, and its QML read only then, so every other window opens
// as quickly): the model, effort and permission mode it starts with, the
// new-chat ones, as the popup's New chat box has them; a change is kept for
// the next new chat.
Flow {
    spacing: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        source: root.iconDir + "settings-symbolic.svg"
        width: Kirigami.Units.iconSizes.small
        height: modelPick.height
        opacity: 0.7
    }
    PlasmaComponents3.ComboBox {
        id: modelPick
        readonly property var values: ["opus", "sonnet", "fable", "haiku", ""]
        model: [i18n("Opus"), i18n("Sonnet"), i18n("Fable"), i18n("Haiku"), i18n("Claude's default model")]
        currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatModel))
        onActivated: Plasmoid.configuration.newChatModel = values[currentIndex]
        TipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Model")
            subText: i18n("The chat starts with it (claude --model); /model changes it in the chat. The next new chat starts with the same.")
        }
    }
    PlasmaComponents3.ComboBox {
        readonly property var values: ["low", "medium", "high", "xhigh", "max", ""]
        model: [i18nc("reasoning effort", "Low"), i18nc("reasoning effort", "Medium"), i18nc("reasoning effort", "High"),
                i18nc("reasoning effort", "Extra high"), i18nc("reasoning effort", "Max"), i18n("Claude's default effort")]
        currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatEffort))
        onActivated: Plasmoid.configuration.newChatEffort = values[currentIndex]
        TipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Reasoning effort")
            subText: i18n("How hard Claude thinks (claude --effort); /effort changes it in the chat. The next new chat starts with the same.")
        }
    }
    PlasmaComponents3.ComboBox {
        id: freshMode
        readonly property var values: ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", ""]
        model: [i18nc("permission mode", "Manual (asks first)"), i18nc("permission mode", "Accept edits"),
                i18nc("permission mode", "Plan"), i18nc("permission mode", "Auto"), i18nc("permission mode", "Don't ask"),
                i18nc("permission mode", "Bypass permissions"), i18n("Claude's default mode")]
        currentIndex: Math.max(0, values.indexOf(Plasmoid.configuration.newChatMode))
        onActivated: Plasmoid.configuration.newChatMode = values[currentIndex]
        TipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Permission mode")
            subText: (freshMode.values[freshMode.currentIndex] === "default"
                      ? i18n("Manual: Claude asks you before it edits files or runs commands, and you answer here.")
                      : freshMode.values[freshMode.currentIndex] === "" ? i18n("The mode your Claude settings start chats in.")
                      : root.modeHint(freshMode.values[freshMode.currentIndex]))
                     + "\n\n" + i18n("The chat starts in it (claude --permission-mode). The next new chat starts in the same.")
                     + " " + i18n("A background chat can start in auto mode or bypass permissions only once you turned that on in a terminal: Claude says so then.")
        }
    }
}
