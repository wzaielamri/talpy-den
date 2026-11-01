import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid

// Settings, General: the chat list (how many recent chats, how long finished
// background chats stay, the token line) and the panel icon.
KCM.SimpleKCM {
    id: page

    // Plasma writes back every cfg_ property of the page on Apply. This one is
    // set in the popup, not here: take what it is now, so applying this page
    // doesn't put back what it was when it opened.
    function saveConfig() {
        cfg_focusView = Plasmoid.configuration.focusView
    }

    property alias cfg_recentChats: recentChats.value
    property alias cfg_keepDoneHours: keepDoneHours.value
    property alias cfg_showTokens: showTokens.checked
    property bool cfg_focusView   // set with the Focus button in the popup's header
    property alias cfg_showUsageInPanel: showUsage.checked
    property alias cfg_iconBlink: iconBlink.checked

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property int cfg_recentChatsDefault
    property int cfg_keepDoneHoursDefault
    property bool cfg_showTokensDefault
    property bool cfg_focusViewDefault
    property bool cfg_showUsageInPanelDefault
    property bool cfg_iconBlinkDefault

    Kirigami.FormLayout {
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Chat list")
        }

        QQC2.SpinBox {
            id: recentChats
            Kirigami.FormData.label: i18n("Recent chats per account:")
            from: 0
            to: 20
        }

        QQC2.SpinBox {
            id: keepDoneHours
            Kirigami.FormData.label: i18n("Keep finished background chats (h):")
            from: 0
            to: 168
        }

        QQC2.CheckBox {
            id: showTokens
            Kirigami.FormData.label: i18n("Tokens:")
            text: i18n("Show token totals from local transcripts")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Panel")
        }

        QQC2.CheckBox {
            id: showUsage
            Kirigami.FormData.label: i18n("Usage:")
            text: i18n("Show 5-hour usage next to the icon")
        }

        QQC2.CheckBox {
            id: iconBlink
            Kirigami.FormData.label: i18n("Icon:")
            text: i18n("Blink while a chat needs you, pulse when one finishes")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Its number: red, chats that need you; green, chats that finished since you last opened the popup (turns at least as long as the \"finished\" notifications ask for). Opening the popup counts as seen.")
        }

        QQC2.Label {
            Kirigami.FormData.label: i18n("System tray:")
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Talpy Den can sit in the system tray too: right-click the tray's arrow → Configure System Tray… → Entries → Talpy Den. \"Shown when relevant\" shows it while a chat runs. Several Talpy Den widgets share these settings, and only one of them notifies.")
        }
    }
}
