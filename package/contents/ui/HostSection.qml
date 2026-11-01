import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// An SSH host or a container you picked: its Claude accounts, sessions and
// recent chats, fetched by remote.py (ssh, or the container engine's exec).
// The host's own answer is kept when a poll fails: it's shown dimmed, under
// the error. A stopped container says so, with Start (it isn't checked
// until you press Start or Refresh).
ColumnLayout {
    id: hostSection

    property string host
    readonly property var info: root.remote[host] || ({ loading: true, ok: false, error: "", result: null, updatedAt: 0 })
    readonly property var hostGroups: info.result ? info.result.groups.map(g => root.withUsage(g, host)) : []
    // (its last answer: after a check that failed, or kept from before this start until the first check answers)
    readonly property bool stale: (!!info.error || !!info.cached) && info.result !== null
    readonly property var container: root.containerOf(host)
    readonly property string label: root.hostLabel(host)
    // (a container on an SSH host logs in and disconnects through its host)
    readonly property string sshHost: container ? container.host : host
    readonly property bool stopped: !!info.stopped && !info.loading

    spacing: Kirigami.Units.smallSpacing

    // (set off from this computer's accounts, and from the host before)
    Kirigami.Separator {
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.gridUnit
        Layout.bottomMargin: Kirigami.Units.smallSpacing
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: root.hostIcon(hostSection.host)
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
        }
        Kirigami.Heading {
            textFormat: Text.PlainText
            level: 1   // (above its accounts' titles)
            font.weight: Font.Bold
            text: hostSection.container ? hostSection.container.name : hostSection.host
            elide: Text.ElideRight
            Layout.maximumWidth: hostSection.width / 2
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            // the machine's own name, when the ssh alias differs; a container's engine and image (· on its host)
            visible: text !== ""
            text: hostSection.container ? root.containerDetail(hostSection.host, true)
                  : hostSection.info.result && hostSection.info.result.host
                  && hostSection.info.result.host.split(".")[0] !== hostSection.host ? hostSection.info.result.host : ""
            opacity: 0.6
            font: Kirigami.Theme.smallFont
            elide: Text.ElideRight
            Layout.maximumWidth: Kirigami.Units.gridUnit * (hostSection.container ? 9 : 6)
        }
        Item {
            Layout.fillWidth: true
        }
        PlasmaComponents3.BusyIndicator {
            visible: hostSection.info.loading
            running: visible
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: hostSection.info.loading && !hostSection.info.result ? i18n("connecting…")
                  : !hostSection.info.updatedAt ? ""
                  : root.now - hostSection.info.updatedAt < 60000 ? i18n("updated just now")
                  : i18n("updated %1 ago", root.duration(root.now - hostSection.info.updatedAt))
            opacity: 0.6
            font: Kirigami.Theme.smallFont
        }
        // what you hid on the host (its chats, plans, memories): a menu to show a kind again
        PlasmaComponents3.ToolButton {
            id: hiddenButton
            readonly property var kinds: hostSection.info.result ? root.hiddenKinds.filter(k => root.hiddenCount(k, hostSection.host) > 0) : []
            icon.name: Icons.plasma.showHidden
            visible: kinds.length > 0
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Show hidden ones again…")
            onClicked: root.openHiddenMenu(hiddenButton, hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Show hidden ones again")
                subText: hiddenButton.kinds.map(k => root.showHiddenText(k, root.hiddenCount(k, hostSection.host))).join("\n")
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.signOut
            visible: !!hostSection.info.loggedIn
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Disconnect from %1", hostSection.sshHost)
            onClicked: root.disconnectHost(hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Disconnect from %1", hostSection.sshHost)
                subText: i18n("Closes the connection you logged in with: to check %1 again, Talpy Den asks you to log in.", hostSection.label)
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.refresh
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Refresh %1", hostSection.label)
            onClicked: root.pollHost(hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Refresh %1", hostSection.label)
                subText: hostSection.stopped ? i18n("Not checked while it's stopped: Refresh checks it once.")
                       : i18n("Checked every %1 seconds while it's shown.", Math.max(10, Plasmoid.configuration.remotePollSeconds))
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.hide
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Stop showing %1", hostSection.label)
            onClicked: root.toggleHost(hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Stop showing %1", hostSection.label)
                subText: i18n("Pick it again with the hosts button at the top.")
            }
        }
    }

    // The host wants a password (or a passphrase, a code, its host key):
    // you log in in a terminal, where ssh asks (root.loginHost)
    RowLayout {
        visible: !!hostSection.info.error && !!hostSection.info.login
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: (hostSection.host in root.loginWaits ? i18n("Log in to %1 in the terminal that opened.", hostSection.sshHost)
                   : i18n("%1 wants you to log in: a password, a passphrase or a code, or its host key confirmed.", hostSection.sshHost))
                  + (hostSection.stale ? " " + i18n("Showing what it said %1 ago.", root.duration(root.now - hostSection.info.updatedAt)) : "")
            color: Kirigami.Theme.negativeTextColor
            wrapMode: Text.Wrap
        }
        PlasmaComponents3.Button {
            icon.name: Icons.plasma.password
            text: i18n("Log in…")
            onClicked: root.loginHost(hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Log in to %1", hostSection.sshHost)
                subText: i18n("Opens a terminal where ssh asks for what it needs. It goes to ssh only: Talpy Den never sees it and keeps nothing. The checks then use that connection until 30 minutes after they stop, until you log out, or until you disconnect.")
            }
        }
    }

    // A stopped container: Start (remote.py --start), then it's checked
    RowLayout {
        visible: hostSection.stopped
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: i18n("%1 is stopped.", hostSection.label)
                  + (hostSection.stale ? " " + i18n("Showing what it said %1 ago.", root.duration(root.now - hostSection.info.updatedAt)) : "")
            wrapMode: Text.Wrap
        }
        PlasmaComponents3.Button {
            icon.name: Icons.plasma.startNow
            text: i18n("Start")
            onClicked: root.startContainer(hostSection.host)
            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: i18n("Start %1", hostSection.label)
                subText: i18n("Starts the container (%1 start), then shows its chats.", hostSection.container ? hostSection.container.engine : "")
            }
        }
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: !!hostSection.info.error && !hostSection.info.login && !hostSection.stopped
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.rightMargin: Kirigami.Units.smallSpacing
        // (an error may end without a full stop: "…Connection timed out Showing what it said…")
        text: hostSection.stale ? i18n("%1 Showing what it said %2 ago.",
                                       /[.!?]$/.test(hostSection.info.error) ? hostSection.info.error : hostSection.info.error + ".",
                                       root.duration(root.now - hostSection.info.updatedAt))
                                : hostSection.info.error
        color: Kirigami.Theme.negativeTextColor
        wrapMode: Text.Wrap
    }

    Repeater {
        model: hostSection.hostGroups.length
        delegate: GroupSection {
            required property int index
            Layout.fillWidth: true
            opacity: hostSection.stale ? 0.5 : 1
            group: hostSection.hostGroups[index] || root.emptyGroup
            accounts: hostSection.hostGroups.length
            remoteHost: hostSection.host
            last: true
        }
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: hostSection.info.ok && hostSection.hostGroups.length === 0
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        text: hostSection.container ? i18n("No Claude Code config in this container (~/.claude, ~/.claude-*)")
                                    : i18n("No Claude Code config on this host (~/.claude, ~/.claude-*)")
        opacity: 0.6
        wrapMode: Text.Wrap
    }
}
