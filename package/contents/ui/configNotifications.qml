import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import "hub"
import "icons.mjs" as Icons

// Settings, Notifications: when a chat notifies, its sounds, what happens
// while you're away (one summary, your phone), and the keyboard shortcut.
ConfigPage {
    id: page

    property alias cfg_notifyWaiting: notifyWaiting.checked
    property alias cfg_notifyDone: notifyDone.checked
    property alias cfg_notifyDoneMinSeconds: notifyDoneMinSeconds.value
    property alias cfg_notifySound: notifySound.checked
    property alias cfg_soundVolume: soundVolume.value
    property alias cfg_soundWaiting: soundWaiting.value
    property alias cfg_soundDone: soundDone.value
    property alias cfg_soundFailed: soundFailed.value
    property alias cfg_awayDigest: awayDigest.checked
    property alias cfg_awayMinutes: awayMinutes.value
    property alias cfg_phoneWhileAway: phoneWhileAway.checked
    property alias cfg_phoneFinished: phoneFinished.checked
    property string cfg_phoneDevice
    property alias cfg_shortcutGoesToChat: shortcutGoesToChat.checked
    property alias cfg_shortcutTalpyChat: shortcutTalpyChat.checked

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property bool cfg_notifyWaitingDefault
    property bool cfg_notifyDoneDefault
    property int cfg_notifyDoneMinSecondsDefault
    property bool cfg_notifySoundDefault
    property int cfg_soundVolumeDefault
    property string cfg_soundWaitingDefault
    property string cfg_soundDoneDefault
    property string cfg_soundFailedDefault
    property bool cfg_awayDigestDefault
    property int cfg_awayMinutesDefault
    property bool cfg_phoneWhileAwayDefault
    property bool cfg_phoneFinishedDefault
    property string cfg_phoneDeviceDefault
    property bool cfg_shortcutGoesToChatDefault
    property bool cfg_shortcutTalpyChatDefault

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))

    // Preview a sound (plays even with Do Not Disturb on)
    Exec {
        id: player
        onNewData: source => disconnectSource(source)
    }

    // KDE Connect: the paired phones (jump.py --phone-devices), and a test message
    property var phones: []
    property string phoneStatus: ""
    property bool kdeConnect: true

    Exec {
        id: phoneHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.phoneStatus = i18n("Couldn't ask KDE Connect")
                return
            }
            if (result.devices !== undefined) {
                page.kdeConnect = result.ok
                page.phones = result.devices
                if (!result.ok)
                    page.phoneStatus = result.message
            } else {
                page.phoneStatus = result.message
            }
        }
    }

    function jumpCommand(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        return "python3 -I " + q(codeDir + "jump.py") + " " + args.map(q).join(" ") + " # " + Date.now()
    }

    Component.onCompleted: phoneHelper.connectSource(jumpCommand(["--phone-devices"]))

    function play(sound) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        player.connectSource("python3 -I " + q(codeDir + "notify_sound.py") + " " + q(sound)
                             + " --volume " + soundVolume.value + " --force # " + Date.now())
    }

    Kirigami.FormLayout {
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("When to notify")
        }

        QQC2.CheckBox {
            id: notifyWaiting
            Kirigami.FormData.label: i18n("Notify:")
            text: i18n("When a chat needs input (permission, question)")
        }

        QQC2.CheckBox {
            id: notifyDone
            text: i18n("When a chat finishes its turn")
        }

        QQC2.SpinBox {
            id: notifyDoneMinSeconds
            Kirigami.FormData.label: i18n("…if the turn took at least (s):")
            from: 0
            to: 3600
            stepSize: 10
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Also picks which finished turns the keyboard shortcut goes to, notifications on or off.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Sounds")
        }

        QQC2.CheckBox {
            id: notifySound
            text: i18n("Play a sound with these notifications")
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Volume:")
            enabled: notifySound.checked
            QQC2.Slider {
                id: soundVolume
                from: 0
                to: 100
                stepSize: 5
                snapMode: QQC2.Slider.SnapAlways   // whole steps, not 47.82%
                Layout.preferredWidth: Kirigami.Units.gridUnit * 10
            }
            QQC2.Label {
                text: i18nc("volume in percent", "%1%", soundVolume.value)
            }
        }

        SoundChooser {
            id: soundWaiting
            Kirigami.FormData.label: i18n("Needs input:")
            enabled: notifySound.checked && notifyWaiting.checked
            onPreview: sound => page.play(sound)
        }

        SoundChooser {
            id: soundDone
            Kirigami.FormData.label: i18n("Finished:")
            enabled: notifySound.checked && notifyDone.checked
            onPreview: sound => page.play(sound)
        }

        SoundChooser {
            id: soundFailed
            Kirigami.FormData.label: i18n("Failed or stopped:")
            enabled: notifySound.checked && notifyDone.checked
            onPreview: sound => page.play(sound)
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Sounds use your sound theme and the system's notification volume. They stay quiet while Do Not Disturb is on.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("While you're away")
        }

        QQC2.CheckBox {
            id: awayDigest
            text: i18n("Sum it all up in one notification when you're back")
        }

        QQC2.SpinBox {
            id: awayMinutes
            Kirigami.FormData.label: i18n("…once the screen was locked for (min):")
            enabled: awayDigest.checked || phoneWhileAway.checked   // the phone waits as long too
            from: 1
            to: 240
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("After this long, chats that finish or need you don't notify one by one: when you unlock the screen, one notification says what happened meanwhile.")
        }

        QQC2.CheckBox {
            id: phoneWhileAway
            Kirigami.FormData.label: i18n("Phone:")
            enabled: page.kdeConnect
            text: i18n("Meanwhile, send chats that need you to my phone")
        }

        QQC2.CheckBox {
            id: phoneFinished
            enabled: page.kdeConnect && phoneWhileAway.checked
            text: i18n("…and chats that finish a turn")
        }

        RowLayout {
            Kirigami.FormData.label: i18n("…to:")
            enabled: page.kdeConnect

            QQC2.ComboBox {
                id: phoneDevice
                textRole: "text"
                valueRole: "value"
                model: [{ text: i18n("Every paired phone that's reachable"), value: "" }].concat(
                    page.phones.map(d => ({ text: d.name + (d.reachable ? "" : " " + i18n("(not reachable now)")), value: d.id })),
                    page.cfg_phoneDevice && !page.phones.some(d => d.id === page.cfg_phoneDevice)
                        ? [{ text: i18n("A phone no longer paired"), value: page.cfg_phoneDevice }] : [])
                // again once the phones are listed (the list comes after the page)
                currentIndex: { model; return Math.max(0, indexOfValue(page.cfg_phoneDevice)) }
                onModelChanged: Qt.callLater(() => currentIndex = Math.max(0, indexOfValue(page.cfg_phoneDevice)))
                onActivated: page.cfg_phoneDevice = currentValue
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            }
            QQC2.Button {
                text: i18n("Send a test")
                icon.name: Icons.plasma.phone
                onClicked: {
                    page.phoneStatus = i18n("Sending…")
                    phoneHelper.connectSource(page.jumpCommand(["--phone", i18n("Talpy Den: this is how chats that need you will show up here."),
                                                                ...(page.cfg_phoneDevice ? ["--device", page.cfg_phoneDevice] : [])]))
                }
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            textFormat: Text.PlainText   // (a helper's or a host's words, shown as written)
            text: (page.phoneStatus ? page.phoneStatus + "\n" : "")
                  + (page.kdeConnect
                     ? i18n("Through KDE Connect, once the screen was locked as long as set above: the phone gets them while it's on the same network as this computer (pair it in System Settings → KDE Connect).")
                     : i18n("Needs KDE Connect (kdeconnect-cli), paired with your phone."))
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Keyboard shortcut")
        }

        QQC2.CheckBox {
            id: shortcutGoesToChat
            text: i18n("Goes to the chat that needs you")
        }
        QQC2.CheckBox {
            id: shortcutTalpyChat
            Layout.leftMargin: Kirigami.Units.gridUnit
            enabled: shortcutGoesToChat.checked
            text: i18n("In Talpy Chat, wherever it runs")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Set the key on the Keyboard Shortcuts page of these settings. It brings up the chat that has waited longest for you, then one that finished while you weren't looking; press it again for the next one: in its own window (its terminal, its VS Code tab), or in Talpy Chat. With none, it opens the popup. In the system tray, the shortcut opens the popup.")
        }
    }
}
