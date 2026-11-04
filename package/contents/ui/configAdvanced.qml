import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import "hub"

// Settings, Advanced: how often Talpy Den checks and live mode, extra
// Claude folders, and where plans and subagent runs open.
ConfigPage {
    id: page

    property alias cfg_pollInterval: pollInterval.value
    property alias cfg_idlePollInterval: idlePollInterval.value
    property alias cfg_extraConfigDirs: extraDirs.text
    property string cfg_markdownApp

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property int cfg_pollIntervalDefault
    property int cfg_idlePollIntervalDefault
    property string cfg_extraConfigDirsDefault
    property string cfg_markdownAppDefault

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))

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

    // The extra config dirs (as this page has them): this computer's hooks go in their settings too
    function withConfigDirs(args) {
        return args.indexOf("--host") >= 0 ? args
               : args.concat(...cfg_extraConfigDirs.split(",").map(d => d.trim()).filter(d => d).map(d => ["--config-dir", d]))
    }

    function runLive(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        liveHelper.connectSource("python3 -I " + q(codeDir + "pane.py") + " --live " + withConfigDirs(args).map(q).join(" ") + " # " + Date.now())
    }

    Component.onCompleted: runLive(["status"])

    Kirigami.FormLayout {
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Checks")
        }

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
            textFormat: Text.PlainText   // (a helper's or a host's words, shown as written)
            text: (page.liveMessage ? page.liveMessage + "\n" : "")
                  + i18n("Adds a hook to each Claude profile's settings.json that notes each step of each chat as it happens (Claude doesn't wait for it): rows, the chat pane and the line under the big Talpy follow every tool call at once, and Talpy Den checks the rest less often. Without it, a chat that starts, waits or finishes still shows at once; its steps show at each check. Applies at once.")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Claude folders")
        }

        QQC2.TextField {
            id: extraDirs
            Kirigami.FormData.label: i18n("Extra config dirs:")
            placeholderText: i18n("comma separated; ~/.claude and ~/.claude-* are automatic")
        }

        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Plans and runs")
        }

        QQC2.ComboBox {
            id: markdownApp
            readonly property var values: ["auto", "okular", "browser", "vscode", "default"]
            Kirigami.FormData.label: i18n("Open plans and runs in:")
            model: [i18n("Okular if installed, else your browser"), i18n("Okular"), i18n("Your web browser"),
                    i18n("VS Code"), i18n("Your app for Markdown files")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_markdownApp))
            onActivated: page.cfg_markdownApp = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Plans and subagent runs are Markdown. Okular shows it rendered; in your browser Talpy Den shows it as a page of its own (it loads nothing from the internet). VS Code shows it in a tab of the Talpy Den extension (1.13 or newer; it loads nothing from the internet either), else the file opens in its editor. Your app for Markdown files is often a text editor: a change you make there to a plan is the plan's. Whatever you pick that isn't installed, your browser shows it.")
        }
    }
}
