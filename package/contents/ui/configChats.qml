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
    // (cfg_openChatsIn, cfg_newChatModel, cfg_newChatEffort, cfg_newChatMode, set in the
    // popup's new-chat box, and cfg_diffSideBySide, cfg_paneTextPercent, set in the chat pane:
    // ConfigPage's, which puts them back as they are now on Apply)
    property alias cfg_dictateLanguage: dictateLanguage.text
    property alias cfg_suggestReplies: suggestReplies.checked
    property string cfg_paneFont
    // (cfg_paneTerminalFont: found by the pane, pane.py --terminal-font; ConfigPage's)

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property bool cfg_clickOpensPaneDefault
    property string cfg_dictateLanguageDefault
    property bool cfg_suggestRepliesDefault
    property string cfg_paneFontDefault

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

    // keepCopy: off for every chat, but the chats Talpy Chat started keep theirs (pane.py --keep-copy)
    function setRelay(on, keepCopy) {
        runRelay([on ? "on" : "off"].concat(!on && keepCopy ? ["--keep-copy"] : []))
        for (const host of Plasmoid.configuration.sshHosts.split(",").map(h => h.trim()).filter(h => h))
            runRelay([on ? "on" : "off", "--host", host])
    }
    // Turned off while chats Talpy Chat started answer their prompts here with a hook of
    // their own (relay.hooked): asked first whether they keep it
    property bool askingHookOff: false

    // The replies hidden with a chip's Don't suggest this (pane.py --hide-reply - --off): suggested
    // again, here and on each SSH host (each keeps its own), at once (not with Apply)
    property string hiddenMessage: ""
    Exec {
        id: hiddenHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                result = null
            }
            if (source.indexOf("--host") < 0)
                page.hiddenMessage = result && result.ok ? i18n("The replies you hid are suggested again.") : i18n("That didn't work")
        }
    }
    function unhideReplies() {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        const line = "python3 -I " + q(codeDir + "pane.py") + " --hide-reply - --off"
        hiddenHelper.connectSource(line + " # " + Date.now())
        for (const host of Plasmoid.configuration.sshHosts.split(",").map(h => h.trim()).filter(h => h))
            hiddenHelper.connectSource(line + " --host " + q(host) + " # " + Date.now())
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

    // Old chats (cleanup.py --status [--days N], --set claude | --set talpy DAYS): who deletes them,
    // Claude Code's own cleanup or Talpy Den's, which keeps what you starred or bookmarked. One choice for every copy
    // of the widget and the VS Code extension, in Talpy Den's state folder: it changes at once (not with
    // Apply), and Talpy Den's, or fewer days, only once you saw what its first run deletes
    property var cleanup: null           // cleanup.py --status
    property string cleanupMessage: ""
    property int cleanupDays: 0          // the days picked, not applied yet (0: none)
    property bool cleanupToClaude: false // Claude Code's own cleanup again, asked first: it would delete what Talpy Den keeps
    // (Talpy Den's, or fewer days: what its first run deletes is asked first; more days delete nothing more)
    readonly property bool cleanupAsking: cleanup !== null && cleanupDays > 0
                                          && (cleanup.mode !== "talpy" || cleanupDays < cleanup.days)
    readonly property int cleanupRisk: cleanup && cleanup.claudeRisk ? cleanup.claudeRisk.chats + cleanup.claudeRisk.plans : 0

    Exec {
        id: cleanupHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.cleanupMessage = i18n("Couldn't ask about old chats")
                return
            }
            if (result.preview !== undefined) {
                page.cleanup = result
            } else if (source.indexOf("--status") >= 0) {
                page.cleanupMessage = result.message || i18n("Couldn't ask about old chats")   // (not asked again: it'd fail again)
            } else {
                page.cleanupMessage = result.message || ""
                page.cleanupDays = 0
                page.cleanupToClaude = false
                page.runCleanup(["--status"])
            }
        }
    }

    Timer {   // (more days: applied after the last click)
        id: cleanupApply
        interval: 800
        onTriggered: if (page.cleanup && page.cleanupDays > 0 && !page.cleanupAsking && page.cleanupDays !== page.cleanup.days)
                         page.runCleanup(["--set", "talpy", String(page.cleanupDays)])
    }

    function runCleanup(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        cleanupHelper.connectSource("python3 -I " + q(codeDir + "cleanup.py") + " " + withConfigDirs(args).map(q).join(" ") + " # " + Date.now())
    }

    // Talpy Den's cleanup at days: what its first run deletes is read first (the question shows it)
    function askCleanup(days) {
        cleanupDays = days
        cleanupToClaude = false
        if (cleanupAsking)
            cleanupPreview.restart()   // (what it deletes: read once the days stop changing, not at each step)
        else
            cleanupApply.restart()
    }

    Timer {
        id: cleanupPreview
        interval: 500
        onTriggered: if (page.cleanupAsking)
                         page.runCleanup(["--status", "--days", String(page.cleanupDays)])
    }

    // Settings besides the accounts' own that still have Claude Code clean up there: "~/repo/.claude/settings.json (7 days)"
    function overridesText(list) {
        return (list || []).map(o => i18nc("a settings file and the days it sets", "%1 (%2 days)", o.path, o.days)).join(", ")
    }

    // Claude Code's own cleanup again: at once, unless it would delete what Talpy Den keeps (asked first)
    function backToClaude() {
        cleanupDays = 0
        if (cleanupRisk > 0)
            cleanupToClaude = true
        else
            runCleanup(["--set", "claude"])
    }

    function sizeText(bytes) {
        return Qt.locale().formattedDataSize(bytes || 0, 1)
    }

    // What a run deleted (or would delete): "3 chats, 1 background chat, 12 files (412 MB), 1 plan to the Trash"
    function cleanupText(r) {
        const parts = []
        if (r.chats)
            parts.push(i18np("%1 chat", "%1 chats", r.chats))
        if (r.backgroundChats)
            parts.push(i18np("%1 background chat", "%1 background chats", r.backgroundChats))
        if (r.files)
            parts.push(i18np("%1 other file", "%1 other files", r.files))
        let text = parts.length ? parts.join(", ") + " (" + sizeText(r.bytes) + ")" : ""
        if (r.plans)
            text += (text ? ", " : "") + i18np("%1 plan to the Trash", "%1 plans to the Trash", r.plans)
        return text || i18n("nothing")
    }

    function keptText(r) {
        const kept = (r.keptChats || 0) + (r.keptPlans || 0)
        return kept ? i18np("%1 old starred, bookmarked, open or queued one stays", "%1 old starred, bookmarked, open or queued ones stay", kept) : ""
    }

    // Each place's last run: "This computer, today 14:02: …", then each SSH host and container
    function runsText() {
        if (!cleanup || !cleanup.runs)
            return ""
        const lines = []
        for (const place of Object.keys(cleanup.runs).sort()) {
            const r = cleanup.runs[place]
            const when = r.at ? Qt.formatDateTime(new Date(r.at), Qt.locale().dateTimeFormat(Locale.ShortFormat)) : ""
            const where = place || i18n("This computer")
            let what = !r.ok && r.message ? r.message   // (out of reach, or it failed there)
                     : r.mode === "talpy" ? cleanupText(r) + (keptText(r) ? "; " + keptText(r) : "")
                     : r.raised ? i18n("Claude Code's cleanup isn't back yet") : i18n("Claude Code's cleanup is back")
            if (r.ok && (r.message || (r.errors && r.errors.length)))
                what += " · " + (r.message || r.errors.join("; "))
            else if (!r.ok && !r.message && r.errors && r.errors.length)
                what += " · " + r.errors.join("; ")
            if (place && r.overrides && r.overrides.length)   // (this computer's: said above)
                what += " · " + i18n("Claude Code still cleans up by %1", overridesText(r.overrides))
            lines.push(i18nc("a place's last cleanup: where, when: what", "%1, %2: %3", where, when, what))
        }
        return lines.join("\n")
    }

    Component.onCompleted: {
        runRelay(["status"])
        runKeys(["status"])
        runDictate(["--status"])
        runCleanup(["--status"])
    }

    Kirigami.FormLayout {
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Open in")
        }

        QQC2.CheckBox {
            id: clickOpensPane
            text: i18n("A click on a chat opens it in Talpy Chat")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Talpy Chat: its conversation as it goes, a box to reply, what it asks for, and what it changed. Off: a click goes to the chat's terminal or VS Code tab (Talpy Chat is then a button beside it).")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("New and recent chats open in a terminal or in VS Code: the Terminal | VS Code switch at the top of their lists picks it.")
        }

        QQC2.ComboBox {
            id: paneFont
            readonly property var values: ["terminal", "desktop"]
            Kirigami.FormData.label: i18n("Talpy Chat text:")
            model: [Plasmoid.configuration.paneTerminalFont
                        ? i18n("In your terminal's font (%1)", Plasmoid.configuration.paneTerminalFont)
                        : i18n("In your terminal's font"),
                    i18n("In the desktop's font")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_paneFont))
            onActivated: page.cfg_paneFont = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("The conversation and your reply, as Claude's terminal shows them: in the font of the terminal Talpy Den opens chats in (System Settings > Default Applications, else Konsole), or a fixed-width one. The size: A− / A+ in the pane.")
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
            enabled: page.relay !== null && !page.askingHookOff
            onToggled: {
                if (!checked && page.relay && page.relay.hooked > 0) {
                    checked = true   // (till you've answered)
                    page.askingHookOff = true
                } else {
                    page.setRelay(checked, false)
                }
            }
        }
        Kirigami.InlineMessage {
            visible: page.askingHookOff
            Layout.preferredWidth: Kirigami.Units.gridUnit * 20
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            type: Kirigami.MessageType.Information
            text: i18np("1 chat started from Talpy Chat answers its prompts here with it. Turn it off for it too?",
                        "%1 chats started from Talpy Chat answer their prompts here with it. Turn it off for them too?",
                        page.relay ? page.relay.hooked : 0)
            actions: [
                Kirigami.Action {
                    text: i18n("Yes, for them too")
                    tooltip: i18n("They ask in their own prompt: Talpy Chat shows Answer it in a terminal.")
                    onTriggered: { page.askingHookOff = false; relayBox.checked = false; page.setRelay(false, false) }
                },
                Kirigami.Action {
                    text: i18n("No, keep it for them")
                    tooltip: i18n("Off for every other chat; the chats started from Talpy Chat still answer their prompts there.")
                    onTriggered: { page.askingHookOff = false; relayBox.checked = false; page.setRelay(false, true) }
                },
                Kirigami.Action {
                    text: i18n("Cancel")
                    onTriggered: { page.askingHookOff = false; relayBox.checked = true }
                }
            ]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            textFormat: Text.PlainText   // (a helper's or a host's words, shown as written)
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
            textFormat: Text.PlainText
            text: (page.keysMessage ? page.keysMessage + "\n" : "")
                  + i18n("Two global shortcuts answer the chat that has waited longest for a permission, from anywhere: Allow once (a plan: Approve) or Deny (a plan: Keep planning); a note on screen says what was answered. They take \"Answer permission prompts from Talpy Den\"; Claude's questions are answered in the panel. Pick other keys in System Settings → Shortcuts → Talpy Den. Applies at once.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Old chats")
        }

        QQC2.ComboBox {
            id: cleanupWho
            Kirigami.FormData.label: i18n("Deleted by:")
            enabled: page.cleanup !== null
            model: [i18n("Claude Code's own cleanup"), i18n("Talpy Den, keeping what you starred")]
            readonly property int shown: page.cleanupAsking
                                         || (page.cleanup !== null && page.cleanup.mode === "talpy" && !page.cleanupToClaude) ? 1 : 0
            currentIndex: shown
            onActivated: index => {
                if (index === 1 && page.cleanup.mode !== "talpy")
                    page.askCleanup(page.cleanup.days)   // (asked first: what its first run deletes)
                else if (index === 1)
                    page.cleanupToClaude = false
                else if (page.cleanup.mode === "talpy")
                    page.backToClaude()
                else
                    page.cleanupDays = 0
                currentIndex = Qt.binding(() => shown)
            }
        }

        RowLayout {
            visible: cleanupWho.currentIndex === 1
            Kirigami.FormData.label: i18n("Not used for:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.SpinBox {
                id: cleanupDaysBox
                from: 1
                to: page.cleanup ? page.cleanup.maxDays : 3649
                editable: true
                value: page.cleanupDays > 0 ? page.cleanupDays : page.cleanup ? page.cleanup.days : 30
                onValueModified: page.askCleanup(value)
            }
            QQC2.Label {
                text: i18ncp("after the number of days", "day", "days", cleanupDaysBox.value)
            }
        }

        // Talpy Den's cleanup, or fewer days: what its first run deletes, asked first
        RowLayout {
            visible: page.cleanupAsking
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                color: Kirigami.Theme.neutralTextColor   // (a question: as every one, ConfirmLine)
                text: !page.cleanup || page.cleanup.previewDays !== page.cleanupDays
                      ? i18n("Looking at what it would delete…")
                      : i18np("Delete chats you haven't used for %1 day? Its first run deletes %2 here.",
                              "Delete chats you haven't used for %1 days? Its first run deletes %2 here.",
                              page.cleanupDays, page.cleanupText(page.cleanup.preview))
            }
            QQC2.Button {
                enabled: !!page.cleanup && page.cleanup.previewDays === page.cleanupDays
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Use It")
                onClicked: page.runCleanup(["--set", "talpy", String(page.cleanupDays)])
            }
            QQC2.Button {
                text: i18n("Cancel")
                onClicked: {
                    page.cleanupDays = 0
                    page.runCleanup(["--status"])
                }
            }
        }

        // Claude Code's own cleanup again: what it would delete of what Talpy Den keeps, asked first
        RowLayout {
            visible: page.cleanupToClaude
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                color: Kirigami.Theme.neutralTextColor
                text: !page.cleanup || !page.cleanup.claudeRisk ? ""
                      : i18np("Let Claude Code delete old chats again? When it next starts, it deletes what's older than %1 day, starred or not: here that's %2.",
                              "Let Claude Code delete old chats again? When it next starts, it deletes what's older than %1 days, starred or not: here that's %2.",
                              page.cleanup.claudeRisk.days,
                              [page.cleanup.claudeRisk.chats ? i18np("%1 chat you keep", "%1 chats you keep", page.cleanup.claudeRisk.chats) : "",
                               page.cleanup.claudeRisk.plans ? i18np("%1 plan you keep", "%1 plans you keep", page.cleanup.claudeRisk.plans) : ""]
                              .filter(s => s).join(i18nc("joins two counts", " and ")))
            }
            QQC2.Button {
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Let Claude Code Delete")
                onClicked: page.runCleanup(["--set", "claude"])
            }
            QQC2.Button {
                text: i18n("Cancel")
                onClicked: page.cleanupToClaude = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            textFormat: Text.PlainText   // (a helper's or a host's words, shown as written)
            text: (page.cleanupMessage ? page.cleanupMessage + "\n" : "")
                  + (!page.cleanup ? ""
                     : page.cleanup.mode !== "talpy" && !page.cleanupAsking   // (asked: what Talpy Den's does, read first)
                     ? i18n("When it starts, Claude Code deletes every chat, and every plan of an account's plans folder, older than its cleanupPeriodDays (%1): starred or not, for good.",
                            page.cleanup.claudeDays.map(a => i18nc("an account: its days", "%1: %2 days", a.account, a.days)).join(", "))
                     : i18n("Once a day Talpy Den deletes the chats you haven't used for that long, with their undo history and files, and finished background chats; old plans go to the Trash. What you starred or bookmarked stays, and so do chats that are open, queued or keep going, and a plan while its chat stays. Meanwhile Claude Code's own cleanup is off on every account, here and on the SSH hosts and containers shown (cleanupPeriodDays 3650); choosing it again puts it back."))
                  + (page.cleanup && (page.cleanup.mode === "talpy" || page.cleanupAsking) && (page.cleanup.overrides || []).length
                     ? "\n\n" + i18n("These settings still have Claude Code delete old chats, starred or not, when it runs there: %1. Talpy Den doesn't change them: set their cleanupPeriodDays higher, or take it out, to keep what you starred.",
                                    page.overridesText(page.cleanup.overrides))
                     : "")
                  + (page.cleanup && page.cleanup.mode === "talpy" && !page.cleanupAsking
                     ? "\n\n" + i18n("Its next run would delete %1 here.", page.cleanupText(page.cleanup.preview))
                       + (page.keptText(page.cleanup.preview) ? " " + page.keptText(page.cleanup.preview) + "." : "")
                     : "")
                  + (page.runsText() ? "\n\n" + page.runsText() : "")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Talpy Chat")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Side by side changes and the text size are set in Talpy Chat itself: its side-by-side button, and A− / A+ or Ctrl+wheel.")
        }

        QQC2.CheckBox {
            id: suggestReplies
            text: i18n("Suggest replies")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Nothing is sent without a click. Off: nothing is read or worked out for it.")
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            textFormat: Text.PlainText
            text: (page.hiddenMessage ? page.hiddenMessage + "\n" : "")
                  + i18n("Once Claude's turn is over, small chips above the box answer the question it ended with (its options, Yes or No…) or offer what you usually reply after a turn that ended the same way (a usage limit, a chat that stopped…), and what you type is completed in grey (Tab or → takes it). Worked out on this computer, from your own chats on the chat's account. A chip's right-click menu hides one of your usual replies for good.")
        }
        QQC2.Button {
            text: i18n("Suggest Hidden Replies Again")
            icon.name: Icons.plasma.showHidden
            onClicked: page.unhideReplies()
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("The usual replies you hid with a chip's Don't suggest this are suggested again. Applies at once.")
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
            textFormat: Text.PlainText
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
                        textFormat: Text.PlainText
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
            textFormat: Text.PlainText
            text: page.dictationMessage
        }
    }
}
