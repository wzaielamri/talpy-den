import QtQuick
import org.kde.plasma.configuration
import "../ui/icons.mjs" as Icons

// The settings' pages: the same categories, in the same order, as in VS Code's
// Settings editor and GNOME's settings window, then the Accounts page
ConfigModel {
    ConfigCategory {
        name: i18n("General")
        icon: Icons.plasma.settings
        source: "configGeneral.qml"
    }
    ConfigCategory {
        name: i18n("Chats")
        icon: Icons.plasma.chats
        source: "configChats.qml"
    }
    ConfigCategory {
        name: i18n("Notifications")
        icon: Icons.plasma.notifications
        source: "configNotifications.qml"
    }
    ConfigCategory {
        name: i18n("Usage & limits")
        icon: Icons.plasma.usageLimits
        source: "configUsage.qml"
    }
    ConfigCategory {
        name: i18n("Talpy")
        icon: Qt.resolvedUrl("../icons/" + Icons.plasma.pet)   // (his own picture)
        source: "configTalpy.qml"
    }
    ConfigCategory {
        name: i18n("Recap")
        icon: Icons.plasma.recap
        source: "configRecap.qml"
    }
    ConfigCategory {
        name: i18n("Hosts")
        icon: Icons.plasma.host
        source: "configHosts.qml"
    }
    ConfigCategory {
        name: i18n("Advanced")
        icon: Icons.plasma.advanced
        source: "configAdvanced.qml"
    }
    ConfigCategory {
        name: i18n("Accounts")
        icon: Icons.plasma.accounts
        source: "configAccounts.qml"
    }
}
