import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid
import "hub"
import "icons.mjs" as Icons

// The Claude accounts on this computer or an SSH host (code/accounts.py; a
// host's through remote.py --accounts): add one (a ~/.claude-NAME folder that
// Claude's own login, in a terminal, signs in), log in or out, remove one,
// make one the default, and its claude-NAME command. Nothing here is a
// setting, so there's nothing to apply.
KCM.SimpleKCM {
    id: page

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))
    readonly property var configDirArgs: Plasmoid.configuration.extraConfigDirs.split(",")
        .map(d => d.trim()).filter(d => d.length).reduce((args, d) => args.concat(["--config-dir", d]), [])

    // whose accounts: this computer's (""), or an SSH host's picked in the popup
    property string host: ""
    readonly property var hosts: Plasmoid.configuration.sshHosts.split(",").map(h => h.trim()).filter(h => h.length)
    property var pending: ({})        // command -> the machine it's for

    property var accounts: []
    property bool loaded: false
    property bool canCheck: true
    property bool linked: false       // ~/.claude is a link: plain claude can follow the default
    property bool canDefault: false   // Make Default can point VS Code's Claude or plain claude somewhere
    readonly property var defaultAccount: accounts.find(a => a.default) || null
    readonly property var plainAccount: accounts.find(a => a.main) || null
    property string message: ""
    property bool messageOk: true
    property bool listFailed: false   // the message is what a failed list said: it goes once a list works
    property string dismissed: ""     // the message the user closed (a failed list says it again every few seconds)
    property string busy: ""          // the account (or "add") an action runs for
    property string confirm: ""       // "remove:<key>" or "logout:<key>": asks first

    readonly property string name: nameField.text.trim()
    readonly property string nameProblem: {
        if (!name)
            return ""
        if (name === "default" || name === "main")
            return i18n("%1 is taken: main is what ~/.claude is called, default marks the default account", name)
        if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(name))
            return i18n("Up to 32 letters, digits, - and _, starting with a letter")
        if (accounts.some(a => a.folder === "~/.claude-" + name))
            return i18n("There's an account called %1 already", name)
        return ""
    }

    // The message box's close button sets its visible, which ends a binding
    // (visible: message !== ""): the next message would never show. So it's
    // shown and hidden from here.
    onMessageChanged: messageBox.visible = message !== ""

    function command(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        const line = host
            ? "python3 -I " + q(codeDir + "remote.py") + " " + ["--accounts", host].concat(args).map(q).join(" ")
            : "python3 -I " + q(codeDir + "accounts.py") + " " + args.concat(configDirArgs).map(q).join(" ")
        const source = line + " # " + Date.now() + Math.random()
        pending[source] = host
        return source
    }

    function pick(machine) {
        host = machine
        accounts = []
        loaded = false
        message = ""
        dismissed = ""
        listFailed = false
        confirm = ""
        load(true)
    }

    // check: ask Claude which accounts are logged in (and as whom); without,
    // the list says what the folders say (cheap, every few seconds)
    function load(check) {
        helper.connectSource(command(check ? ["--list", "--check"] : ["--list"]))
    }

    function act(args, forKey) {
        busy = forKey
        confirm = ""
        helper.connectSource(command(args))
    }

    Exec {
        id: helper
        onNewData: (source, data) => {
            disconnectSource(source)
            const machine = page.pending[source]
            delete page.pending[source]
            if (machine !== page.host && source.indexOf("'--list'") >= 0)
                return   // an answer for the machine shown before
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                const lines = (data["stderr"] || "").trim().split("\n")
                result = { ok: false, message: lines[lines.length - 1] || i18n("the helper gave no answer") }
            }
            if (source.indexOf("'--list'") >= 0 && !result.ok) {
                const said = result.message || i18n("the helper gave no answer")
                if (said !== page.dismissed) {
                    page.message = said
                    page.messageOk = false
                    page.listFailed = true
                }
                page.loaded = true
                return
            }
            if (source.indexOf("'--list'") >= 0) {
                const checked = source.indexOf("'--check'") >= 0
                const before = {}
                for (const a of page.accounts)
                    before[a.key] = a
                // A quick look keeps what Claude said last while the folder
                // says the same (quick); when that changes, Claude is asked again
                const changed = result.accounts.some(a => !before[a.key] || before[a.key].quick !== a.quick)
                page.accounts = result.accounts.map(a => {
                    const old = before[a.key]
                    return checked || !old || !old.checked || old.quick !== a.quick ? a
                        : Object.assign({}, a, { checked: true, method: old.method, email: old.email, loggedIn: old.loggedIn })
                })
                page.canCheck = result.canCheck
                page.linked = !!result.linked
                page.canDefault = !!result.canDefault
                if (!checked && (!page.loaded || changed))
                    page.load(true)
                page.loaded = true
                page.dismissed = ""
                if (page.listFailed) {   // (what a failed list said is over)
                    page.listFailed = false
                    page.message = ""
                }
                return
            }
            page.message = result.message || ""
            page.messageOk = result.ok
            page.listFailed = false
            page.busy = ""
            if (result.ok && source.indexOf("'--add'") >= 0)
                nameField.text = ""
            page.load(true)
        }
    }

    Component.onCompleted: load(true)

    // A login happens in a terminal: look again every few seconds (a host's over ssh, less often)
    Timer {
        interval: page.host ? 10000 : 4000
        repeat: true
        running: page.visible && page.loaded
        onTriggered: page.load(false)
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            id: messageBox
            Layout.fillWidth: true
            type: page.messageOk ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            text: page.message
            showCloseButton: true
            onVisibleChanged: {
                if (!visible) {
                    page.dismissed = page.message
                    page.message = ""
                }
            }
        }

        RowLayout {
            Kirigami.Heading {
                level: 3
                textFormat: Text.PlainText
                text: page.host ? i18n("Accounts on %1", page.host) : i18n("Accounts on this computer")
            }
            Item { Layout.fillWidth: true }
            QQC2.Label {
                visible: page.hosts.length > 0
                text: i18n("On:")
            }
            QQC2.ComboBox {
                visible: page.hosts.length > 0
                model: [i18n("This computer")].concat(page.hosts)
                onActivated: page.pick(currentIndex === 0 ? "" : page.hosts[currentIndex - 1])
            }
        }

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: (page.host ? i18n("On %1, over ssh: nothing is installed there, and its logins open in a terminal here, where you paste the code Claude gives you.", page.host) + " " : "")
                  + i18n("Each account is a Claude folder (~/.claude, ~/.claude-NAME) with a login, history and chats of its own. The default account is listed first and its usage is in the panel: VS Code's Claude runs on it, and plain claude too where ~/.claude is a link. A chat started with the + next to an account in the popup runs on that account.")
        }

        QQC2.Label {
            visible: !page.loaded
            text: i18n("Looking…")
            opacity: 0.7
        }

        // The default account is listed first everywhere and its usage is in
        // the panel; VS Code's Claude and plain claude run on it
        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: page.linked && !!page.defaultAccount && !!page.plainAccount && page.defaultAccount.key !== page.plainAccount.key
            type: Kirigami.MessageType.Information
            text: visible ? i18n("VS Code's Claude runs on %1, the default account, but plain claude on %2 (~/.claude links there). Make Default on %1 points plain claude there too.",
                                 page.defaultAccount.label, page.plainAccount.label) : ""
        }

        Repeater {
            model: page.accounts.length
            delegate: Rectangle {
                id: card
                required property int index
                readonly property var account: page.accounts[index] || ({ key: "", label: "", folder: "" })
                readonly property bool asking: page.confirm === "remove:" + account.key || page.confirm === "logout:" + account.key
                Layout.fillWidth: true
                implicitHeight: cardColumn.implicitHeight + Kirigami.Units.largeSpacing * 2
                radius: Kirigami.Units.cornerRadius
                color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.04)
                border.width: 1
                border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.12)

                ColumnLayout {
                    id: cardColumn
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        Kirigami.Icon {
                            source: card.account.loggedIn ? Icons.plasma.account : Icons.plasma.accountOut
                            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                            Layout.preferredHeight: Layout.preferredWidth
                        }
                        QQC2.Label {
                            textFormat: Text.PlainText
                            text: card.account.label
                            font.bold: true
                        }
                        QQC2.Label {
                            textFormat: Text.PlainText
                            visible: card.account.default
                            text: i18n("default")
                            font.bold: true
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            color: Kirigami.Theme.positiveTextColor
                        }
                        QQC2.Label {
                            textFormat: Text.PlainText
                            visible: card.account.main || card.account.vscode
                            text: [card.account.main ? i18n("plain claude") : "", card.account.vscode ? i18n("VS Code's Claude") : ""]
                                  .filter(t => t).join(" · ")
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                        }
                        Item { Layout.fillWidth: true }
                        QQC2.Label {
                            textFormat: Text.PlainText
                            text: card.account.folder
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: {
                            const a = card.account
                            const parts = []
                            if (!a.loggedIn)
                                parts.push(a.checked ? i18n("Not logged in") : i18n("Not logged in to a Claude account"))
                            else if (a.method && a.method !== "claude.ai")
                                parts.push(i18n("Logged in (%1)", a.method))
                            else
                                parts.push([a.email || a.account || i18n("Logged in"), a.plan].filter(t => t).join(" · "))
                            if (a.chats > 0)
                                parts.push(i18np("1 chat running", "%1 chats running", a.chats))
                            return parts.join(" · ")
                        }
                        opacity: card.account.loggedIn ? 1 : 0.8
                    }

                    // Asks first: logging out, removing
                    Kirigami.InlineMessage {
                        Layout.fillWidth: true
                        visible: card.asking
                        type: page.confirm.startsWith("remove:") ? Kirigami.MessageType.Warning : Kirigami.MessageType.Information
                        text: page.confirm.startsWith("remove:")
                              ? (page.host ? i18n("Remove %1 on %3? It logs out, then moves %2 to the Trash of %3 with its chats, history and settings (restore it from there if you change your mind). Chats shared with your other accounts stay on them.", card.account.label, card.account.folder, page.host)
                                           : i18n("Remove %1? It logs out, then moves %2 to the Trash with its chats, history and settings (restore it from there if you change your mind). Chats shared with your other accounts stay on them.", card.account.label, card.account.folder))
                              : i18n("Log out of %1? Claude deletes its login; its chats and history stay, and Log in… signs it in again (also with another account).", card.account.label)
                        actions: [
                            Kirigami.Action {
                                text: page.confirm.startsWith("remove:") ? i18n("Remove") : i18n("Log out")
                                icon.name: page.confirm.startsWith("remove:") ? Icons.plasma.delete : Icons.plasma.signOut
                                icon.color: page.confirm.startsWith("remove:") ? Icons.color("delete", Kirigami.Theme) : "transparent"
                                onTriggered: page.act([page.confirm.startsWith("remove:") ? "--remove" : "--logout", card.account.key], card.account.key)
                            },
                            Kirigami.Action {
                                text: i18n("Cancel")
                                icon.name: Icons.plasma.cancel
                                icon.color: Icons.color("cancel", Kirigami.Theme)
                                onTriggered: page.confirm = ""
                            }
                        ]
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        visible: !card.asking

                        QQC2.Button {
                            visible: page.canDefault && page.accounts.length > 1 && card.account.loggedIn
                                     && (!card.account.default || (page.linked && !card.account.main))
                            text: i18n("Make Default")
                            icon.name: Icons.plasma.starred
                            enabled: page.busy === ""
                            onClicked: page.act(["--default", card.account.key], card.account.key)
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: page.linked
                                ? i18n("Lists it first and shows its usage in the panel; VS Code's Claude (new chats, and a window's Claude Code panel once it reloads) and plain claude (~/.claude) run on it. Not while a chat runs through ~/.claude: it would go on on this account.")
                                : i18n("Lists it first and shows its usage in the panel; VS Code's Claude runs on it (new chats, and a window's Claude Code panel once it reloads). Plain claude stays on ~/.claude, a folder.")
                        }
                        QQC2.Button {
                            visible: !card.account.loggedIn
                            text: i18n("Log in…")
                            icon.name: Icons.plasma.signIn
                            enabled: page.busy === "" && page.canCheck
                            onClicked: page.act(["--login", card.account.key], card.account.key)
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: i18n("Opens a terminal with Claude's own login (claude auth login): sign in in your browser with the account for this folder.")
                        }
                        QQC2.Button {
                            visible: card.account.loggedIn
                            text: i18n("Log out…")
                            icon.name: Icons.plasma.signOut
                            enabled: page.busy === "" && card.account.chats === 0
                            onClicked: page.confirm = "logout:" + card.account.key
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: card.account.chats > 0 ? i18n("Close its chats first: they'd lose the login.")
                                                                      : i18n("Claude deletes this account's login (claude auth logout).")
                        }
                        QQC2.Button {
                            text: i18n("Remove…")
                            icon.name: Icons.plasma.delete
                            icon.color: Icons.color("delete", Kirigami.Theme)
                            enabled: page.busy === "" && !card.account.notRemovable
                            onClicked: page.confirm = "remove:" + card.account.key
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: card.account.notRemovable || i18n("Logs out and moves the folder to the Trash.")
                        }
                        QQC2.CheckBox {
                            visible: !!card.account.commandName
                            text: i18n("%1 command", card.account.commandName || "")
                            checked: !!card.account.command
                            enabled: page.busy === ""
                            onToggled: {
                                const want = checked
                                checked = Qt.binding(() => !!card.account.command)   // the list says when it's done
                                page.act([want ? "--command" : "--no-command", card.account.key], card.account.key)
                            }
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: i18n("~/.local/bin/%1 runs Claude on this account in any terminal.", card.account.commandName || "")
                        }
                        QQC2.BusyIndicator {
                            visible: page.busy === card.account.key
                            running: visible
                            implicitHeight: Kirigami.Units.iconSizes.smallMedium
                            implicitWidth: implicitHeight
                        }
                    }
                }
            }
        }

        Kirigami.Heading {
            level: 3
            textFormat: Text.PlainText
            text: i18n("Add an account")
            Layout.topMargin: Kirigami.Units.largeSpacing
        }

        Kirigami.FormLayout {
            Layout.fillWidth: true

            QQC2.TextField {
                id: nameField
                Kirigami.FormData.label: i18n("Name:")
                placeholderText: i18n("e.g. work")
                maximumLength: 32
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            }

            QQC2.Label {
                textFormat: Text.PlainText
                text: page.nameProblem || (page.name ? i18n("Folder: ~/.claude-%1", page.name) : i18n("Its folder will be ~/.claude-NAME"))
                color: page.nameProblem ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                font: Kirigami.Theme.smallFont
                opacity: page.nameProblem ? 1 : 0.7
            }

            QQC2.ComboBox {
                id: shareFrom
                Kirigami.FormData.label: i18n("Settings:")
                textRole: "text"
                valueRole: "value"
                model: page.accounts.map(a => ({ text: i18n("Shared with %1", a.label), value: a.key }))
                       .concat([{ text: i18n("Claude's defaults, nothing shared"), value: "" }])
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            }

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 22
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: shareFrom.currentValue
                      ? i18n("Links settings.json (your status line, so the plan usage bars work), CLAUDE.md, keybindings and your own skills, agents and commands to that account's: a change on one is a change on both. The login, MCP servers, plugins and the skills claude.ai syncs stay per account.")
                      : i18n("A fresh folder: Claude starts with its defaults. Plan usage shows once Claude fetched it (/usage), or after you give the account a status line and run install.sh again.")
            }

            QQC2.CheckBox {
                id: withCommand
                text: page.name && !page.nameProblem ? i18n("Add a claude-%1 command", page.name) : i18n("Add a claude-NAME command")
                checked: true
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.text: i18n("In ~/.local/bin: runs Claude on the new account in any terminal.")
            }

            RowLayout {
                QQC2.Button {
                    text: i18n("Add and Log In…")
                    icon.name: Icons.plasma.addAccount
                    enabled: page.name !== "" && page.nameProblem === "" && page.busy === "" && page.canCheck
                    onClicked: page.act(["--add", page.name].concat(shareFrom.currentValue ? ["--share-from", shareFrom.currentValue] : [],
                                                                    withCommand.checked ? ["--command"] : []), "add")
                }
                QQC2.BusyIndicator {
                    visible: page.busy === "add"
                    running: visible
                    implicitHeight: Kirigami.Units.iconSizes.smallMedium
                    implicitWidth: implicitHeight
                }
            }

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 22
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: page.canCheck
                      ? i18n("A terminal opens with Claude's own login: sign in in your browser with the other account. Claude keeps the login in the new folder; Talpy Den never sees it. The account shows up in the popup right away.")
                      : i18n("Needs the claude command, which isn't found (on PATH, in ~/.local/bin, npm's or nvm's folders).")
            }
        }
    }
}
