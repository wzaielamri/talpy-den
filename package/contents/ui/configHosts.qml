import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid

// Settings, Hosts: the SSH hosts' checks and their accounts' plan usage,
// and the containers in the hosts picker (the hosts and containers
// themselves are picked in the popup).
ConfigPage {
    id: page

    // (cfg_sshHosts: set with the SSH hosts button in the popup, ConfigPage's)
    property alias cfg_remotePollSeconds: remotePollSeconds.value
    property string cfg_sshUsage
    property alias cfg_showContainers: showContainers.checked
    property alias cfg_containerDays: containerDays.value

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property int cfg_remotePollSecondsDefault
    property string cfg_sshUsageDefault
    property bool cfg_showContainersDefault
    property int cfg_containerDaysDefault

    Kirigami.FormLayout {
        QQC2.Label {
            Kirigami.FormData.label: i18n("SSH hosts:")
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Pick SSH hosts and containers with the hosts button at the top of the popup. A host that wants a password (or a passphrase, a code, its host key confirmed) shows Log in…, which opens a terminal where ssh asks for it: Talpy Den never sees it. With your key in the agent (ssh-add) that isn't needed. The host needs python3; nothing gets installed there.")
        }

        QQC2.SpinBox {
            id: remotePollSeconds
            Kirigami.FormData.label: i18n("Check SSH hosts every (s):")
            from: 10
            to: 600
            stepSize: 10
        }

        QQC2.ComboBox {
            id: sshUsage
            readonly property var values: ["once", "all", "none"]
            Kirigami.FormData.label: i18n("Plan usage on SSH hosts:")
            model: [i18n("Once per account"), i18n("On every host"), i18n("Not on hosts")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_sshUsage))
            onActivated: page.cfg_sshUsage = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("An account logged in here and on a host (or on two hosts) has one plan usage. Once per account shows it where the account is listed first, with the newest numbers of them all.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Containers")
        }

        QQC2.CheckBox {
            id: showContainers
            Kirigami.FormData.label: i18n("Containers:")
            text: i18n("Show containers")
        }

        QQC2.SpinBox {
            id: containerDays
            Kirigami.FormData.label: i18n("List containers active in the last (days):")
            enabled: showContainers.checked
            from: 0
            to: 365
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Docker, Podman and nerdctl containers, here and on the SSH hosts shown, are in the hosts picker: the running ones and those started or stopped in these days (0: only the running ones). One you pick shows like a host; Talpy Den works in it with the engine's exec, and it needs python3 there. Off, Talpy Den never runs docker, podman or nerdctl.")
        }
    }
}
