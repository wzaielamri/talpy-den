import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid
import "hub"
import "icons.mjs" as Icons

KCM.SimpleKCM {
    id: page

    // Plasma writes back every cfg_ property on Apply. These are set in the
    // popup, not here: take what they are now, so applying this page doesn't
    // put back what they were when it opened.
    function saveConfig() {
        cfg_newChatInVscode = Plasmoid.configuration.newChatInVscode
        cfg_newChatModel = Plasmoid.configuration.newChatModel
        cfg_newChatEffort = Plasmoid.configuration.newChatEffort
        cfg_newChatMode = Plasmoid.configuration.newChatMode
        cfg_sshHosts = Plasmoid.configuration.sshHosts
        cfg_focusView = Plasmoid.configuration.focusView
        cfg_paneTextPercent = Plasmoid.configuration.paneTextPercent
        cfg_diffSideBySide = Plasmoid.configuration.diffSideBySide
    }

    property alias cfg_pollInterval: pollInterval.value
    property alias cfg_idlePollInterval: idlePollInterval.value
    property alias cfg_extraConfigDirs: extraDirs.text
    property alias cfg_notifyWaiting: notifyWaiting.checked
    property alias cfg_notifyDone: notifyDone.checked
    property alias cfg_notifyDoneMinSeconds: notifyDoneMinSeconds.value
    property alias cfg_clickOpensPane: clickOpensPane.checked
    property alias cfg_dictateLanguage: dictateLanguage.text
    property alias cfg_mondayRecap: mondayRecap.checked
    property alias cfg_awayDigest: awayDigest.checked
    property alias cfg_awayMinutes: awayMinutes.value
    property alias cfg_shortcutGoesToChat: shortcutGoesToChat.checked
    property alias cfg_phoneWhileAway: phoneWhileAway.checked
    property alias cfg_phoneFinished: phoneFinished.checked
    property string cfg_phoneDevice
    property alias cfg_keepDoneHours: keepDoneHours.value
    property alias cfg_showUsageInPanel: showUsage.checked
    property alias cfg_iconBlink: iconBlink.checked
    property bool cfg_newChatInVscode   // set with the Terminal | VS Code switch in the popup
    property bool cfg_focusView         // set with the filter button in the popup's header
    property int cfg_paneTextPercent    // set with A− / A+ in the chat pane
    property bool cfg_diffSideBySide    // set with the chat pane's side-by-side button
    property string cfg_newChatModel    // these three in the popup's new-chat box
    property string cfg_newChatEffort
    property string cfg_newChatMode
    property int cfg_usageCap
    property alias cfg_usageRefreshMinutes: usageRefreshMinutes.value
    property alias cfg_showTokens: showTokens.checked
    property alias cfg_showPet: showPet.checked
    property alias cfg_playful: playful.checked
    property alias cfg_chatPets: chatPets.value
    property alias cfg_recentChats: recentChats.value
    property alias cfg_remotePollSeconds: remotePollSeconds.value
    property string cfg_sshHosts
    property string cfg_sshUsage
    property string cfg_markdownApp
    property string cfg_recapCurrency
    property alias cfg_recapRules: recapRules.checked
    property alias cfg_notifySound: notifySound.checked
    property alias cfg_soundVolume: soundVolume.value
    property alias cfg_soundWaiting: soundWaiting.value
    property alias cfg_soundDone: soundDone.value
    property alias cfg_soundFailed: soundFailed.value

    // Plasma passes the defaults in too; declaring them avoids
    // "SimpleKCM does not have a property called cfg_…Default" warnings.
    property int cfg_pollIntervalDefault
    property int cfg_idlePollIntervalDefault
    property string cfg_extraConfigDirsDefault
    property bool cfg_notifyWaitingDefault
    property bool cfg_notifyDoneDefault
    property int cfg_notifyDoneMinSecondsDefault
    property bool cfg_clickOpensPaneDefault
    property string cfg_dictateLanguageDefault
    property bool cfg_mondayRecapDefault
    property bool cfg_awayDigestDefault
    property int cfg_awayMinutesDefault
    property bool cfg_shortcutGoesToChatDefault
    property bool cfg_phoneWhileAwayDefault
    property bool cfg_phoneFinishedDefault
    property string cfg_phoneDeviceDefault
    property int cfg_keepDoneHoursDefault
    property bool cfg_showUsageInPanelDefault
    property bool cfg_iconBlinkDefault
    property bool cfg_newChatInVscodeDefault
    property bool cfg_focusViewDefault
    property int cfg_paneTextPercentDefault
    property bool cfg_diffSideBySideDefault
    property string cfg_newChatModelDefault
    property string cfg_newChatEffortDefault
    property string cfg_newChatModeDefault
    property int cfg_usageCapDefault
    property int cfg_usageRefreshMinutesDefault
    property bool cfg_showTokensDefault
    property bool cfg_showPetDefault
    property bool cfg_playfulDefault
    property int cfg_chatPetsDefault
    property int cfg_recentChatsDefault
    property int cfg_remotePollSecondsDefault
    property string cfg_sshHostsDefault
    property string cfg_sshUsageDefault
    property string cfg_markdownAppDefault
    property string cfg_recapCurrencyDefault
    property bool cfg_recapRulesDefault
    property bool cfg_notifySoundDefault
    property int cfg_soundVolumeDefault
    property string cfg_soundWaitingDefault
    property string cfg_soundDoneDefault
    property string cfg_soundFailedDefault

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

    // The Recap's history (week.py --history-status, --history on|off,
    // --forget): one choice for every copy of the widget and the VS Code
    // extension, kept next to their cache, so it changes at once (not with Apply)
    property var history: null        // {keep, since, deletedChats, sizeKB}
    property string historyMessage: ""
    property bool forgetAsking: false
    property bool historyOffAsking: false   // (off forgets the chats Claude deleted: asked first)

    Exec {
        id: historyHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.historyMessage = i18n("Couldn't ask the Recap about its history")
                return
            }
            if (result.keep !== undefined) {
                page.history = result
            } else {
                page.historyMessage = result.message || ""
                page.runHistory(["--history-status"])
            }
        }
    }

    // The permission hook (pane.py --relay status|on|off): in Claude's own
    // settings, so it changes at once (not with Apply)
    property var relay: null          // {on, some, settings}
    property string relayMessage: ""

    Exec {
        id: relayHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.relayMessage = i18n("Couldn't ask about the permission hook")
                return
            }
            if (result.on !== undefined) {
                page.relay = result
            } else if (source.indexOf("--host") < 0) {
                page.relayMessage = result.message || ""
                page.runRelay(["status"])
            } else if (!result.ok) {
                page.relayMessage = result.message || ""
            }
        }
    }

    // The extra config dirs (as this page has them): this computer's hooks go in their settings too
    function withConfigDirs(args) {
        return args.indexOf("--host") >= 0 ? args
               : args.concat(...cfg_extraConfigDirs.split(",").map(d => d.trim()).filter(d => d).map(d => ["--config-dir", d]))
    }

    function runRelay(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        relayHelper.connectSource("python3 -I " + q(codeDir + "pane.py") + " --relay " + withConfigDirs(args).map(q).join(" ") + " # " + Date.now())
    }

    function setRelay(on) {
        runRelay([on ? "on" : "off"])
        for (const host of Plasmoid.configuration.sshHosts.split(",").map(h => h.trim()).filter(h => h))
            runRelay([on ? "on" : "off", "--host", host])
    }

    // Live mode (pane.py --live status|on|off): the live hook in Claude's
    // own settings, so it changes at once (not with Apply)
    property var liveHook: null       // {on, some, settings}
    readonly property bool liveOn: liveHook !== null && liveHook.on === true
    property string liveMessage: ""

    Exec {
        id: liveHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.liveMessage = i18n("Couldn't ask about live mode")
                return
            }
            if (result.on !== undefined) {
                page.liveHook = result
            } else {
                page.liveMessage = result.message || ""
                page.runLive(["status"])
            }
        }
    }

    // Keyboard answers (pane.py --shortcuts status|on|off): global shortcuts
    // for the oldest prompt, registered with Plasma at once (not with Apply)
    property var keysState: null      // {on}
    property string keysMessage: ""

    Exec {
        id: keysHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.keysMessage = i18n("Couldn't ask about keyboard answers")
                return
            }
            if (result.on !== undefined) {
                page.keysState = result
            } else {
                page.keysMessage = result.message || ""
                page.runKeys(["status"])
            }
        }
    }

    // Dictation (dictate.py --status, --setup, --get-model, --use-model,
    // --delete-model, --remove-setup): faster-whisper and the speech models
    // in ~/.local/share/talpy-den/whisper, one choice for every copy of the
    // widget and the VS Code extension, so it changes at once (not with Apply)
    property var dictation: null      // its --status
    property string dictationBusy: "" // what runs: "setup", "get", "delete", "use", "remove"
    property string dictationModel: ""   // (the model that's downloaded or deleted)
    property string dictationMessage: ""
    property bool removeAsking: false

    Exec {
        id: dictateHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.dictationBusy = ""
                page.dictationMessage = i18n("Couldn't ask about dictation")
                return
            }
            if (result.models !== undefined) {
                page.dictation = result
            } else {
                page.dictationBusy = ""
                page.dictationMessage = result.message || ""
                page.runDictate(["--status"])
            }
        }
    }

    function runDictate(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        if (args[0] !== "--status") {
            dictationBusy = {"--setup": "setup", "--get-model": "get", "--delete-model": "delete", "--use-model": "use",
                             "--remove-setup": "remove"}[args[0]] || ""
            dictationModel = args[1] || ""
            dictationMessage = ""
        }
        dictateHelper.connectSource("python3 -I " + q(codeDir + "dictate.py") + " " + args.map(q).join(" ") + " # " + Date.now())
    }

    function runKeys(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        keysHelper.connectSource("python3 -I " + q(codeDir + "pane.py") + " --shortcuts " + args.map(q).join(" ") + " # " + Date.now())
    }

    function runLive(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        liveHelper.connectSource("python3 -I " + q(codeDir + "pane.py") + " --live " + withConfigDirs(args).map(q).join(" ") + " # " + Date.now())
    }

    function runHistory(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        historyHelper.connectSource("python3 -I " + q(codeDir + "week.py") + " " + args.map(q).join(" ") + " # " + Date.now())
    }

    function jumpCommand(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        return "python3 -I " + q(codeDir + "jump.py") + " " + args.map(q).join(" ") + " # " + Date.now()
    }

    Component.onCompleted: {
        phoneHelper.connectSource(jumpCommand(["--phone-devices"]))
        runHistory(["--history-status"])
        runRelay(["status"])
        runLive(["status"])
        runKeys(["status"])
        runDictate(["--status"])
    }

    function play(sound) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        player.connectSource("python3 -I " + q(codeDir + "notify_sound.py") + " " + q(sound)
                             + " --volume " + soundVolume.value + " --force # " + Date.now())
    }

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: pollInterval
            Kirigami.FormData.label: i18n("While a chat works, check every (ms):")
            from: 1000
            to: 60000
            stepSize: 500
            // (with live mode its steps come as they happen: then this only counts
            // if the watching fails, which the widget then falls back to)
            enabled: !page.liveOn
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("How often a working chat's line (what it's doing) is brought up to date.")
        }

        QQC2.SpinBox {
            id: idlePollInterval
            Kirigami.FormData.label: i18n("While no chat works, check every (ms):")
            from: 1000
            to: 300000
            stepSize: 1000
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("For what changes while no chat does anything: plan usage and its forecast, a usage limit resetting, a queued task coming due, a Claude that crashed. Never more often than above.")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: (page.liveOn ? i18n("Live mode is on: a working chat's steps show as they happen, and it's checked every 6 s, so the first one doesn't apply. ") : "")
                  + i18n("A chat that starts, ends, starts working, asks for something or finishes its turn shows at once either way: Talpy Den watches the files Claude keeps for its chats.")
        }

        QQC2.TextField {
            id: extraDirs
            Kirigami.FormData.label: i18n("Extra config dirs:")
            placeholderText: i18n("comma separated; ~/.claude and ~/.claude-* are automatic")
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

        QQC2.CheckBox {
            id: clickOpensPane
            Kirigami.FormData.label: i18n("Chats:")
            text: i18n("A click on a chat opens it beside the popup")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("The chat pane: its conversation as it goes, a box to reply, what it asks for, and what it changed. Off: a click goes to the chat's terminal or VS Code tab (the pane is then a button beside it).")
        }

        QQC2.CheckBox {
            id: relayBox
            text: i18n("Answer permission prompts from Talpy Den")
            checked: page.relay !== null && page.relay.on
            enabled: page.relay !== null
            onToggled: page.setRelay(checked)
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: (page.relayMessage ? page.relayMessage + "\n" : "")
                  + i18n("Adds a hook to each Claude profile's settings.json (and on the SSH hosts shown): a chat that asks for a permission shows Allow once, Always allow and Deny in its row, its pane and its notification, and Claude's questions show their choices there to answer. Claude still asks in the chat too; the first answer counts. Permission prompts of chats in tmux can be answered without it. Applies at once.")
        }

        QQC2.CheckBox {
            id: liveBox
            text: i18n("Live mode: show each step as it happens")
            checked: page.liveHook !== null && page.liveHook.on
            enabled: page.liveHook !== null
            onToggled: page.runLive([checked ? "on" : "off"])
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: (page.liveMessage ? page.liveMessage + "\n" : "")
                  + i18n("Adds a hook to each Claude profile's settings.json that notes each step of each chat as it happens (Claude doesn't wait for it): rows, the chat pane and the line under the big Talpy follow every tool call at once, and Talpy Den checks the rest less often. Without it, a chat that starts, waits or finishes still shows at once; its steps show at each check. Applies at once.")
        }

        QQC2.CheckBox {
            id: keysBox
            text: i18n("Keyboard answers: Meta+Alt+Y allows the oldest prompt, Meta+Alt+N denies it")
            checked: page.keysState !== null && page.keysState.on
            enabled: page.keysState !== null
            onToggled: page.runKeys([checked ? "on" : "off"])
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: (page.keysMessage ? page.keysMessage + "\n" : "")
                  + i18n("Two global shortcuts answer the chat that has waited longest for a permission, from anywhere: Allow once (a plan: Approve) or Deny (a plan: Keep planning); a note on screen says what was answered. They take \"Answer permission prompts from Talpy Den\"; Claude's questions are answered in the panel. Pick other keys in System Settings → Shortcuts → Talpy Den. Applies at once.")
        }

        QQC2.TextField {
            id: dictateLanguage
            Kirigami.FormData.label: i18n("Dictation language:")
            placeholderText: "auto"
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("The language you dictate replies in, as a code (en, de, fr…), or auto to let whisper tell. Dictating runs on this computer only.")
        }

        // Dictation: what writes it down, set up here, and its speech models
        QQC2.Label {
            Kirigami.FormData.label: i18n("Dictation:")
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            text: {
                const d = page.dictation
                if (page.dictationBusy === "setup")
                    return i18n("Setting up dictation (a few minutes)…")
                if (page.dictationBusy === "get")
                    return i18n("Downloading the %1 model…", page.dictationModel)
                if (page.dictationBusy === "remove")
                    return i18n("Deleting faster-whisper…")
                if (!d)
                    return i18n("Asking…")
                if (!d.engine)
                    return d.canSetup ? i18n("Not set up. Dictating needs faster-whisper, speech to text that runs on this computer; set up here, no sudo needed.")
                                      : i18n("To dictate, install %1.", d.missing.join(i18n(" and ")))
                let line = d.engine === "whisper.cpp" ? i18n("Written down by whisper.cpp (%1).", d.tool)
                                                      : i18n("Written down by faster-whisper, set up in ~/.local/share/talpy-den/whisper.")
                line += " " + (!d.modelName ? i18n("No speech model yet: download one below.")
                               : d.chosen === "auto" ? i18n("It uses the %1 model (the best one downloaded).", d.modelName)
                               : i18n("It uses the %1 model.", d.modelName))
                if (!d.recorder)
                    line += " " + i18n("To record, install %1.", d.missing.join(i18n(" and ")))
                return line
            }
        }

        QQC2.Button {
            visible: page.dictation !== null && page.dictation.canSetup
            enabled: page.dictationBusy === ""
            icon.name: Icons.plasma.download
            text: i18n("Set Up Dictation (about %1 MB)", page.dictation ? page.dictation.setupMb : 0)
            onClicked: page.runDictate(["--setup"])
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Installs faster-whisper from pypi.org into its own Python environment and downloads the base speech model from huggingface.co, all in ~/.local/share/talpy-den/whisper. What you say never leaves the computer.")
        }

        // The speech models: pick the one used, download or delete them
        ColumnLayout {
            visible: page.dictation !== null && !!page.dictation.engine
            spacing: 0

            QQC2.ButtonGroup {
                id: modelGroup
            }
            Repeater {
                model: page.dictation && page.dictation.engine ? page.dictation.models : []

                RowLayout {
                    required property var modelData
                    spacing: Kirigami.Units.smallSpacing

                    QQC2.RadioButton {
                        QQC2.ButtonGroup.group: modelGroup
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 10
                        text: modelData.name + " · " + i18n("%1 MB", modelData.mb)
                        checked: modelData.used
                        enabled: modelData.installed && page.dictationBusy === ""
                        onToggled: page.runDictate(["--use-model", modelData.name])
                    }
                    QQC2.Label {
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                        wrapMode: Text.Wrap
                        font: Kirigami.Theme.smallFont
                        opacity: 0.7
                        text: modelData.note
                    }
                    QQC2.Button {
                        visible: !modelData.installed || modelData.deletable
                        enabled: page.dictationBusy === ""
                        icon.name: modelData.installed ? Icons.plasma.erase : Icons.plasma.download
                        icon.color: modelData.installed ? Icons.color("erase", Kirigami.Theme) : "transparent"
                        text: modelData.installed ? i18n("Delete") : i18n("Download")
                        onClicked: page.runDictate([modelData.installed ? "--delete-model" : "--get-model", modelData.name])
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.text: modelData.installed ? i18n("Delete the %1 model; download it again any time", modelData.name)
                                                               : i18n("Download the %1 model (%2 MB, from huggingface.co) and use it", modelData.name, modelData.mb)
                    }
                    QQC2.Label {
                        visible: modelData.installed && !modelData.deletable
                        font: Kirigami.Theme.smallFont
                        opacity: 0.7
                        text: i18n("whisper.cpp's own")
                    }
                }
            }
        }

        QQC2.Button {
            visible: page.dictation !== null && !!page.dictation.engine && page.dictation.chosen !== "auto"
            enabled: page.dictationBusy === ""
            flat: true
            text: i18n("Use the Best One Downloaded")
            onClicked: page.runDictate(["--use-model", "auto"])
        }

        RowLayout {
            visible: page.dictation !== null && page.dictation.setUp
            spacing: Kirigami.Units.smallSpacing

            QQC2.Button {
                visible: !page.removeAsking
                enabled: page.dictationBusy === ""
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Remove faster-whisper…")
                onClicked: page.removeAsking = true
            }
            QQC2.Label {
                visible: page.removeAsking
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                text: i18n("Delete faster-whisper and its speech models? Dictating needs setting up again then.")
            }
            QQC2.Button {
                visible: page.removeAsking
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Delete")
                onClicked: {
                    page.removeAsking = false
                    page.runDictate(["--remove-setup"])
                }
            }
            QQC2.Button {
                visible: page.removeAsking
                text: i18n("Cancel")
                onClicked: page.removeAsking = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            visible: page.dictationMessage !== ""
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            text: page.dictationMessage
        }

        QQC2.CheckBox {
            id: mondayRecap
            Kirigami.FormData.label: i18n("Every week:")
            text: i18n("On Mondays, sum up the last 7 days in a notification (it opens the Recap)")
        }

        QQC2.CheckBox {
            id: awayDigest
            Kirigami.FormData.label: i18n("While you're away:")
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
            text: (page.phoneStatus ? page.phoneStatus + "\n" : "")
                  + (page.kdeConnect
                     ? i18n("Through KDE Connect, once the screen was locked as long as set above: the phone gets them while it's on the same network as this computer (pair it in System Settings → KDE Connect).")
                     : i18n("Needs KDE Connect (kdeconnect-cli), paired with your phone."))
        }

        QQC2.CheckBox {
            id: notifySound
            Kirigami.FormData.label: i18n("Sound:")
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

        // The usage cap: stop what an account has at work at N% of a plan window
        RowLayout {
            Kirigami.FormData.label: i18n("Usage cap:")
            QQC2.CheckBox {
                id: capOn
                text: i18n("Stop an account's chats at work when a plan limit reaches")
                checked: page.cfg_usageCap > 0
                onToggled: page.cfg_usageCap = checked ? capPct.value : 0
            }
            QQC2.SpinBox {
                id: capPct
                from: 10
                to: 100
                stepSize: 5
                value: page.cfg_usageCap > 0 ? page.cfg_usageCap : 90
                enabled: capOn.checked
                onValueModified: if (capOn.checked) page.cfg_usageCap = value
            }
            QQC2.Label {
                text: i18nc("percent sign after the usage cap", "%")
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Once an account's 5-hour or weekly window reaches it, the chats of that account that are at work on this computer are stopped, once in that window (in tmux and VS Code's Claude the turn is interrupted, the chat stays open). Queued tasks wait until the window resets, and chats that keep going go on then. Chats you start or answer yourself afterwards aren't stopped again.")
        }

        QQC2.SpinBox {
            id: usageRefreshMinutes
            Kirigami.FormData.label: i18n("Fetch plan usage older than (min):")
            from: 0
            to: 60
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("VS Code's Claude Code panel runs no status line, so its chats don't bring an account's plan usage up to date. While one of the account's chats works and its numbers are this old, Claude Code fetches them, as its /usage does (no tokens, no chat saved), at most this often. 0: never.")
        }

        QQC2.SpinBox {
            id: keepDoneHours
            Kirigami.FormData.label: i18n("Keep finished background jobs (h):")
            from: 0
            to: 168
        }

        QQC2.SpinBox {
            id: recentChats
            Kirigami.FormData.label: i18n("Recent chats per account:")
            from: 0
            to: 20
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

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Pick SSH hosts with the SSH hosts button at the top of the popup. A host that wants a password (or a passphrase, a code, its host key confirmed) shows Log in…, which opens a terminal where ssh asks for it: Talpy Den never sees it. With your key in the agent (ssh-add) that isn't needed. The host needs python3; nothing gets installed there.")
        }

        QQC2.CheckBox {
            id: showUsage
            Kirigami.FormData.label: i18n("Panel:")
            text: i18n("Show 5-hour usage next to the icon")
        }

        QQC2.CheckBox {
            id: shortcutGoesToChat
            Kirigami.FormData.label: i18n("Keyboard shortcut:")
            text: i18n("Goes to the chat that needs you")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Set the key on the Keyboard Shortcuts page of these settings. It brings up the chat that has waited longest for you, then one that finished while you weren't looking; press it again for the next one. With none, it opens the popup. In the system tray, the shortcut opens the popup.")
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

        QQC2.CheckBox {
            id: showPet
            Kirigami.FormData.label: i18n("Pet:")
            text: i18n("Show Talpy, the pet, in the popup and in notifications")
        }

        QQC2.CheckBox {
            id: playful
            enabled: showPet.checked
            text: i18n("Playful Talpy: tricks and props, jokes, cookies and games")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Off, Talpy only shows what your chats do: his moods, his lamp and quiet moves (looking around, typing, thinking, sleeping). Notifications and badges stay as they are.")
        }

        QQC2.SpinBox {
            id: chatPets
            Kirigami.FormData.label: i18n("Chat pets per account, at most:")
            enabled: showPet.checked
            from: 0
            to: 8
        }

        QQC2.CheckBox {
            id: showTokens
            Kirigami.FormData.label: i18n("Popup:")
            text: i18n("Show token totals from local transcripts")
        }

        QQC2.ComboBox {
            id: recapCurrency
            // (the currencies of the European Central Bank's reference rates)
            readonly property var values: ["USD", "EUR", "GBP", "CHF", "JPY", "CNY", "INR", "CAD", "AUD", "NZD", "SEK", "NOK",
                                           "DKK", "PLN", "CZK", "HUF", "RON", "ISK", "TRY", "BRL", "MXN", "ZAR", "KRW", "SGD",
                                           "HKD", "ILS", "IDR", "MYR", "PHP", "THB"]
            Kirigami.FormData.label: i18n("Recap amounts in:")
            model: [i18n("US dollars (USD)"), i18n("Euros (EUR)"), i18n("Pounds sterling (GBP)"), i18n("Swiss francs (CHF)"),
                    i18n("Japanese yen (JPY)"), i18n("Chinese yuan (CNY)"), i18n("Indian rupees (INR)"),
                    i18n("Canadian dollars (CAD)"), i18n("Australian dollars (AUD)"), i18n("New Zealand dollars (NZD)"),
                    i18n("Swedish kronor (SEK)"), i18n("Norwegian kroner (NOK)"), i18n("Danish kroner (DKK)"),
                    i18n("Polish złoty (PLN)"), i18n("Czech koruny (CZK)"), i18n("Hungarian forints (HUF)"),
                    i18n("Romanian lei (RON)"), i18n("Icelandic krónur (ISK)"), i18n("Turkish lira (TRY)"),
                    i18n("Brazilian reais (BRL)"), i18n("Mexican pesos (MXN)"), i18n("South African rand (ZAR)"),
                    i18n("South Korean won (KRW)"), i18n("Singapore dollars (SGD)"), i18n("Hong Kong dollars (HKD)"),
                    i18n("Israeli shekels (ILS)"), i18n("Indonesian rupiah (IDR)"), i18n("Malaysian ringgit (MYR)"),
                    i18n("Philippine pesos (PHP)"), i18n("Thai baht (THB)")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_recapCurrency))
            onActivated: page.cfg_recapCurrency = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Claude's API prices are in US dollars. For another currency, the Recap tab downloads the European Central Bank's reference rates of the day from ecb.europa.eu, at most every 6 hours and only while the tab is open; offline, it uses the last rates it has. Nothing about your chats is sent.")
        }

        QQC2.CheckBox {
            id: recapHistory
            text: i18n("Keep a history beyond Claude's 30 days")
            enabled: page.history !== null
            checked: page.history ? page.history.keep : true
            onToggled: {
                if (!checked && page.history && page.history.deletedChats > 0)
                    page.historyOffAsking = true   // (the numbers of chats Claude deleted go: asked first)
                else
                    page.runHistory(["--history", checked ? "on" : "off"])
                checked = Qt.binding(() => page.history ? page.history.keep : true)   // (it shows what the Recap keeps)
            }
        }

        RowLayout {
            visible: page.historyOffAsking
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                text: i18np("Stop keeping the history? The Recap forgets the numbers of the %1 chat Claude has deleted, for good.",
                            "Stop keeping the history? The Recap forgets the numbers of the %1 chats Claude has deleted, for good.",
                            page.history ? page.history.deletedChats : 0)
            }
            QQC2.Button {
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Stop Keeping It")
                onClicked: {
                    page.historyOffAsking = false
                    page.runHistory(["--history", "off"])
                }
            }
            QQC2.Button {
                text: i18n("Cancel")
                onClicked: page.historyOffAsking = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Claude Code deletes chats after 30 days (its cleanupPeriodDays setting). The Recap's Overall keeps their numbers past that, in ~/.cache/talpy-den: times, tokens, costs, folders and chat names. Off, it keeps only what Claude still has. This changes at once, for the VS Code extension too.")
                  + (!page.history ? "" : "\n" + (page.history.since
                         ? i18np("Kept since %2, with %1 chat Claude has deleted · %3 KB", "Kept since %2, with %1 chats Claude has deleted · %3 KB",
                                 page.history.deletedChats, Qt.locale().toString(new Date(page.history.since + "T00:00"), "d MMM yyyy"),
                                 page.history.sizeKB)
                         : i18n("Nothing kept yet.")))
        }

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Button {
                visible: !page.forgetAsking
                enabled: page.history !== null && !!page.history.since
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Delete Saved History…")
                onClicked: page.forgetAsking = true
            }
            QQC2.Label {
                visible: page.forgetAsking
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                text: i18n("Delete the Recap's saved history? It starts again from the chats Claude still has.")
            }
            QQC2.Button {
                visible: page.forgetAsking
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Delete")
                onClicked: {
                    page.forgetAsking = false
                    page.runHistory(["--forget"])
                }
            }
            QQC2.Button {
                visible: page.forgetAsking
                text: i18n("Cancel")
                onClicked: page.forgetAsking = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            visible: page.historyMessage !== ""
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            text: page.historyMessage
        }

        QQC2.CheckBox {
            id: recapRules
            text: i18n("Suggest rules for the permission prompts you answered")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("The Permissions tab offers rules that would have let those prompts go without asking, each with an Allow… button. Off, it only counts the prompts, and there's nothing to allow by mistake. Either way it lists the permissions you gave, to revoke them.")
        }

        QQC2.ComboBox {
            id: markdownApp
            readonly property var values: ["auto", "okular", "browser", "vscode", "default"]
            Kirigami.FormData.label: i18n("Open plans and runs in:")
            model: [i18n("Okular if installed, else your browser"), i18n("Okular"), i18n("Your web browser"),
                    i18n("VS Code (Markdown preview)"), i18n("Your app for Markdown files")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_markdownApp))
            onActivated: page.cfg_markdownApp = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Plans and subagent runs are Markdown. Okular shows it rendered; in your browser Talpy Den shows it as a page of its own (it loads nothing from the internet). VS Code's preview needs the Talpy Den extension for VS Code 1.13 or newer, else the file opens in its editor. Your app for Markdown files is often a text editor: a change you make there to a plan is the plan's. Whatever you pick that isn't installed, your browser shows it.")
        }
    }
}
