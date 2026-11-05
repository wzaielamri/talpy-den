import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Where chats open: Talpy Chat | Terminal | Claude Code panel, at the top of
// an account's new-chat folders and of its recent chats (GroupSection.qml).
// One choice for both (openChatsIn), kept for next time. A half is greyed
// out where it can't work: Talpy Chat on an SSH host or in a container (it
// can't answer a background chat's prompts there yet), or where managed
// settings let no hook of Talpy Den's run; no claude command (on that SSH
// host), no VS Code, or VS Code's Claude on another account (root.openIn
// picks another one then; a new chat on an SSH host's other account switches
// VS Code's Claude there). When none works, a line under it says why.
ColumnLayout {
    id: openIn

    property var group
    property string remoteHost: ""
    property bool resuming: false   // the recent chats' switch: they reopen

    readonly property string where: root.openIn(group, remoteHost, resuming)
    readonly property bool talpyHere: root.talpyChatHere(remoteHost, resuming)
    readonly property bool terminalHere: root.cliHere(remoteHost)
    // a new chat on an SSH host's other account: VS Code's Claude there switches to it
    readonly property bool switching: !resuming && root.vscodeSwitches(group, remoteHost)
    readonly property bool vscodeHere: root.vscodeInstalled && (!!group.vscodeHere || switching)

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: i18n("Open in:")
            opacity: 0.7
        }
        OpenInButton {
            available: openIn.talpyHere
            checked: openIn.where === "talpyChat"
            iconName: root.iconDir + Icons.plasma.talpyChatLogo   // (Talpa with a speech bubble, in colour)
            text: i18n("Talpy Chat")
            tipTitle: openIn.remoteHost ? i18n("This computer's chats for now")
                      : !openIn.terminalHere ? i18n("No claude command")
                      : !openIn.talpyHere ? i18n("Hooks are off here")
                      : openIn.resuming ? i18n("Reopen chats in Talpy Chat") : i18n("New chats in Talpy Chat")
            tip: root.talpyChatHint(openIn.remoteHost, openIn.resuming)
            onClicked: Plasmoid.configuration.openChatsIn = "talpyChat"
        }
        OpenInButton {
            available: openIn.terminalHere
            checked: openIn.where === "terminal" && openIn.terminalHere
            iconName: Icons.plasma.terminal
            text: i18n("Terminal")
            tipTitle: !openIn.terminalHere ? i18n("No claude command")
                      : openIn.resuming ? i18n("Reopen chats in a terminal") : i18n("New chats in a terminal")
            tip: root.terminalHint(openIn.remoteHost, openIn.resuming)
            onClicked: Plasmoid.configuration.openChatsIn = "terminal"
        }
        OpenInButton {
            available: openIn.vscodeHere
            checked: openIn.where === "vscode"
            iconName: Icons.plasma.vscodeApp
            text: i18n("Claude Code panel")
            tipTitle: !root.vscodeInstalled ? i18n("VS Code isn't installed")
                      : !openIn.vscodeHere ? i18n("Not on this account")
                      : openIn.switching ? i18n("New chats in VS Code, on this account")
                      : openIn.resuming ? i18n("Reopen chats in VS Code") : i18n("New chats in VS Code")
            tip: root.vscodeHint(openIn.group, openIn.remoteHost, openIn.resuming)
            onClicked: Plasmoid.configuration.openChatsIn = "vscode"
        }
        Item {
            Layout.fillWidth: true
        }
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: !openIn.terminalHere && !openIn.vscodeHere
        Layout.fillWidth: true
        text: root.terminalHint(openIn.remoteHost, openIn.resuming) + " "
              + root.vscodeHint(openIn.group, openIn.remoteHost, openIn.resuming)
        wrapMode: Text.Wrap
        opacity: 0.7
        font: Kirigami.Theme.smallFont
    }
}
