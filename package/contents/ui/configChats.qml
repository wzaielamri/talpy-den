import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid
import "hub"
import "icons.mjs" as Icons

// Settings, Chats: where a click opens them, what new chats start with (set
// in the popup), answering permission prompts from Talpy Den, and the chat
// pane's dictation.
ConfigPage {
    id: page

    property alias cfg_clickOpensPane: clickOpensPane.checked
    // (cfg_newChatInVscode, cfg_newChatModel, cfg_newChatEffort, cfg_newChatMode, set in the
    // popup's new-chat box, and cfg_diffSideBySide, cfg_paneTextPercent, set in the chat pane:
    // ConfigPage's, which puts them back as they are now on Apply)
    property alias cfg_dictateLanguage: dictateLanguage.text

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property bool cfg_clickOpensPaneDefault
    property string cfg_dictateLanguageDefault

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))

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

    // The extra config dirs: this computer's hooks go in their settings too
    function withConfigDirs(args) {
        return args.indexOf("--host") >= 0 ? args
               : args.concat(...Plasmoid.configuration.extraConfigDirs.split(",").map(d => d.trim()).filter(d => d).map(d => ["--config-dir", d]))
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

    function runKeys(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        keysHelper.connectSource("python3 -I " + q(codeDir + "pane.py") + " --shortcuts " + args.map(q).join(" ") + " # " + Date.now())
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

    Component.onCompleted: {
        runRelay(["status"])
        runKeys(["status"])
        runDictate(["--status"])
    }

    Kirigami.FormLayout {
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Open in")
        }

        QQC2.CheckBox {
            id: clickOpensPane
            text: i18n("A click on a chat opens it beside the popup")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("The chat pane: its conversation as it goes, a box to reply, what it asks for, and what it changed. Off: a click goes to the chat's terminal or VS Code tab (the pane is then a button beside it).")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("New and recent chats open in a terminal or in VS Code: the Terminal | VS Code switch at the top of their lists picks it.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("New chats")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("The model, effort and permission mode a new chat starts with are picked in the popup's new-chat box; the next new chat starts with the same.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Permission prompts")
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

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Chat window")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Side by side changes and the text size are set in the chat pane: its side-by-side button, and A− / A+ or Ctrl+wheel.")
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
                color: Kirigami.Theme.neutralTextColor   // (a question: as every one, ConfirmLine)
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
    }
}
