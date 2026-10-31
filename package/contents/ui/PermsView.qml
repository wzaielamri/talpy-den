import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The Permissions tab (main.qml: loadPerms, week.py --permissions): the
// permissions you gave, every rule and mode that lets chats on this computer
// go without asking (each to revoke), and the permission prompts you answered
// in the last 7 days with the rules that would have let the most of them
// through (the settings can leave those out). Read from your settings and the
// chat transcripts: no tokens, nothing sent.
PlasmaComponents3.ScrollView {
    id: view

    readonly property var perms: root.permsData
    // this computer's, then each SSH host's: [{host, ok, error, prompts, granted}]
    readonly property var sources: !perms ? [] : [{ host: "", ok: true, prompts: perms.prompts, granted: perms.granted }].concat(perms.hosts || [])
    readonly property real gu: Kirigami.Units.gridUnit
    property string confirmRule: ""   // the rule whose Allow asks first: its id
    property string confirmGrant: ""  // the permission whose Revoke asks first: its id
    // the hosts ("" this computer) whose permissions you gave are all shown, not the first few
    // (kept here: a revoke reloads the tab)
    property var allGranted: ({})
    readonly property int grantedFew: 8

    readonly property var emptyRule: ({ kind: "", value: "", project: "", count: 0, waitMs: 0, example: "", id: "",
                                        state: "", title: "", change: "" })
    readonly property var emptyGrant: ({ id: "", kind: "", value: "", title: "", place: "", where: "", shared: false,
                                         added: false, change: "" })

    // Fixed implicit size, as the other tabs: deriving it from the content
    // would loop through the popup's width
    implicitWidth: gu * 28
    implicitHeight: gu * 26
    contentWidth: availableWidth
    contentHeight: sheet.implicitHeight
    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

    // A permission you gave: a trusted folder, an MCP server, a loosened
    // check, a folder to read, a mode, a command, the web
    function grantIcon(g) {
        if (g.kind === "trust")
            return Icons.plasma.trusted
        if (g.kind === "mcp")
            return Icons.plasma.mcp
        if (g.kind === "flag")
            return Icons.plasma.warning
        if (g.kind === "dir")
            return Icons.plasma.folder
        if (g.kind === "mode")
            return g.value === "acceptEdits" ? Icons.plasma.edit : Icons.plasma.warning
        if (g.value.indexOf("WebFetch") === 0 || g.value === "WebSearch")
            return Icons.plasma.webAccess
        return g.value.indexOf("Bash") === 0 ? Icons.plasma.terminal : Icons.plasma.allowed
    }

    // 3h 05m, 45m
    function hours(ms) {
        const m = Math.round(Math.max(0, ms) / 60000)
        return m < 60 ? i18nc("duration in minutes", "%1m", m)
                      : i18nc("duration in hours and minutes", "%1h %2m", Math.floor(m / 60), m % 60)
    }

    Item {
        id: sheet
        width: view.availableWidth
        implicitHeight: page.implicitHeight + Kirigami.Units.largeSpacing

    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Kirigami.Units.smallSpacing
        anchors.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.largeSpacing
        // (while it reads again: what it said before, dimmed, no jump)
        opacity: root.permsBusy && view.perms ? 0.6 : 1

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            visible: root.permsBusy && !view.perms
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.BusyIndicator {
                implicitWidth: Kirigami.Units.iconSizes.medium
                implicitHeight: Kirigami.Units.iconSizes.medium
                running: parent.visible
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: i18n("Reading your settings and the chats of the last 7 days.")
                opacity: 0.8
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            visible: root.permsError !== ""
            wrapMode: Text.Wrap
            color: Kirigami.Theme.negativeTextColor
            text: i18n("Couldn't read your permissions: %1", root.permsError)
        }

        // This computer's, then each SSH host's shown (as listed there); by
        // count, so a reload refreshes them in place
        Repeater {
            model: view.sources.length
            delegate: ColumnLayout {
                id: origin
                required property int index
                readonly property var src: view.sources[index] || ({ host: "", ok: true, prompts: null, granted: [] })
                readonly property string host: src.host || ""
                readonly property var granted: src.granted || []
                readonly property var prompts: src.prompts || null
                readonly property bool allGranted: view.allGranted[origin.host] === true
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing

                // (what asks first or is busy: a host's rule and this computer's may share an id)
                function key(id) {
                    return host + "|" + id
                }

                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: origin.src.ok === false
                    wrapMode: Text.Wrap
                    color: Kirigami.Theme.negativeTextColor
                    text: i18n("Couldn't read the permissions on %1: %2", origin.host, origin.src.error || i18n("no answer"))
                }

            // The permissions you gave: every rule and mode that lets chats on
            // this computer go without asking, each to revoke (it asks first)
            ColumnLayout {
                Layout.fillWidth: true
                visible: origin.src.ok !== false
                spacing: Math.round(view.gu * 0.2)

                SectionTitle {
                    text: origin.host ? i18n("Permissions you gave on %1", origin.host) : i18n("Permissions you gave")
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                    text: origin.granted.length
                          ? (origin.host ? i18n("What lets chats on %1 go without asking you, as listed there: its settings, its trusted folders, and the .claude settings of the folders Claude ran in. Revoke takes one out of its file on %1.", origin.host)
                         : i18n("What lets chats on this computer go without asking you: your settings and your administrator's, the folders you trusted, the .claude settings of the folders Claude ran in, and what you approved in them. Revoke takes one out of its file."))
                          : origin.host ? i18n("Nothing lets chats on %1 skip a permission prompt: they ask you each time.", origin.host)
                      : i18n("Nothing lets chats on this computer skip a permission prompt: they ask you each time.")
                }
                Repeater {
                    model: origin.allGranted ? origin.granted.length : Math.min(origin.granted.length, view.grantedFew)
                    delegate: ColumnLayout {
                        id: grantRow
                        required property int index
                        readonly property var grant: origin.granted[index] || view.emptyGrant
                        readonly property bool asking: view.confirmGrant !== "" && view.confirmGrant === origin.key(grant.id)
                        Layout.fillWidth: true
                        spacing: Math.round(view.gu * 0.2)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                source: view.grantIcon(grantRow.grant)
                                opacity: 0.8
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    text: grantRow.grant.title
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    text: grantRow.grant.place + " · " + grantRow.grant.where
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.alignment: Qt.AlignTop
                                visible: grantRow.grant.shared
                                text: grantRow.grant.managed ? i18n("Administrator's") : i18n("In git")
                                font: Kirigami.Theme.smallFont
                                opacity: 0.7

                                PlasmaCore.ToolTipArea {
                                    textFormat: Text.PlainText
                                    anchors.fill: parent
                                    mainText: grantRow.grant.managed ? i18n("Set by your administrator") : i18n("Shared through git")
                                    subText: grantRow.grant.managed ? i18n("It's in /etc/claude-code: it can't be changed here.")
                                             : i18n("This folder's .claude/settings.json is shared with whoever uses its repository: change it there.")
                                }
                            }
                            PlasmaComponents3.Button {
                                Layout.alignment: Qt.AlignTop
                                visible: !grantRow.grant.shared && !grantRow.asking && root.ruleBusy !== origin.key(grantRow.grant.id)
                                enabled: root.ruleBusy === ""
                                text: i18n("Revoke…")
                                onClicked: view.confirmGrant = origin.key(grantRow.grant.id)
                            }
                            PlasmaComponents3.BusyIndicator {
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                visible: root.ruleBusy !== "" && root.ruleBusy === origin.key(grantRow.grant.id)
                                running: visible
                            }
                        }
                        // Revoke asks first, saying what changes where
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            visible: grantRow.asking
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                font: Kirigami.Theme.smallFont
                                text: i18n("This %1.", grantRow.grant.change)
                            }
                            RowLayout {
                                spacing: Kirigami.Units.smallSpacing

                                PlasmaComponents3.Button {
                                    icon.name: Icons.plasma.cancel
                                    icon.color: Icons.color("cancel", Kirigami.Theme)
                                    text: i18n("Revoke")
                                    enabled: root.ruleBusy === ""   // (one settings write at a time)
                                    onClicked: {
                                        view.confirmGrant = ""
                                        root.revokeGrant(grantRow.grant, origin.host)
                                    }
                                }
                                PlasmaComponents3.Button {
                                    text: i18n("Cancel")
                                    onClicked: view.confirmGrant = ""
                                }
                            }
                        }
                    }
                }
                PlasmaComponents3.ToolButton {
                    visible: !origin.allGranted && origin.granted.length > view.grantedFew
                    text: i18np("Show %1 more", "Show %1 more", origin.granted.length - view.grantedFew)
                    onClicked: view.allGranted = Object.assign({}, view.allGranted, { [origin.host]: true })
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: root.ruleMessage !== "" && root.ruleRevoked && root.ruleHost === origin.host
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    text: root.ruleMessage
                }
            }

            // The permission prompts you answered, and the rules that would have
            // let the most of them through (written only when you allow one)
            ColumnLayout {
                Layout.fillWidth: true
                visible: !!origin.prompts
                spacing: Math.round(view.gu * 0.2)

                SectionTitle {
                    text: origin.host ? i18n("Permission prompts on %1, last 7 days", origin.host) : i18n("Permission prompts, last 7 days")
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: {
                        const p = origin.prompts
                        if (!p)
                            return ""
                        if (!p.answered)
                            return origin.host ? i18n("You answered no permission prompts on %1 in the last 7 days.", origin.host)
                                      : i18n("You answered no permission prompts on this computer in the last 7 days.")
                        let text = p.refused ? i18np("You answered %1 permission prompt and refused %2 of them.", "You answered %1 permission prompts and refused %2 of them.", p.answered, p.refused)
                                             : i18np("You answered %1 permission prompt.", "You answered %1 permission prompts.", p.answered)
                        if (p.waitMs >= 60000)
                            text += " " + i18n("They waited for your answer %1 in all.", view.hours(p.waitMs))
                        return text
                    }
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: !!origin.prompts && origin.prompts.byTool.length > 0
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                    text: !origin.prompts ? "" : i18n("For: %1", origin.prompts.byTool.map(t => t[0] + " " + t[1]).join(" · "))
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: root.suggestRules && !!origin.prompts && origin.prompts.rules.length > 0
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                    text: i18n("These rules would have let the most of them through. One you allow goes into the .claude/settings.local.json of the folder the chats started in (not shared through git), and only chats started there follow it.")
                }
                Repeater {
                    model: root.suggestRules && origin.prompts ? origin.prompts.rules.length : 0   // (the settings can leave them out)
                    delegate: ColumnLayout {
                        id: ruleRow
                        required property int index
                        readonly property var rule: origin.prompts.rules[index] || view.emptyRule
                        readonly property bool asking: view.confirmRule !== "" && view.confirmRule === origin.key(rule.id)
                        readonly property bool busy: root.ruleBusy !== "" && root.ruleBusy === origin.key(rule.id)
                        Layout.fillWidth: true
                        spacing: Math.round(view.gu * 0.2)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                source: ruleRow.rule.kind === "dir" ? Icons.plasma.folder : ruleRow.rule.kind === "edits" ? Icons.plasma.edit
                                      : ruleRow.rule.value.indexOf("WebFetch") === 0 ? Icons.plasma.webAccess : Icons.plasma.terminal
                                opacity: 0.8
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    text: ruleRow.rule.title
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    text: i18np("%1 prompt", "%1 prompts", ruleRow.rule.count)
                                          + (ruleRow.rule.waitMs >= 60000 ? " · " + i18n("waited %1 for you", view.hours(ruleRow.rule.waitMs)) : "")
                                          + " · " + i18n("e.g. %1", ruleRow.rule.example)
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.alignment: Qt.AlignTop
                                visible: ruleRow.rule.state === "allowed"
                                text: i18n("Allowed now")
                                font: Kirigami.Theme.smallFont
                                opacity: 0.7
                            }
                            PlasmaComponents3.Button {
                                Layout.alignment: Qt.AlignTop
                                visible: ruleRow.rule.state === "new" && !ruleRow.asking
                                enabled: root.ruleBusy === ""
                                text: i18n("Allow…")
                                onClicked: view.confirmRule = origin.key(ruleRow.rule.id)
                            }
                            PlasmaComponents3.Button {
                                Layout.alignment: Qt.AlignTop
                                visible: ruleRow.rule.state === "added"
                                enabled: root.ruleBusy === ""
                                icon.name: Icons.plasma.undo
                                text: i18n("Undo")
                                onClicked: root.changeRule(ruleRow.rule, false, origin.host)

                                PlasmaCore.ToolTipArea {
                                    textFormat: Text.PlainText
                                    anchors.fill: parent
                                    mainText: i18n("Take this rule back")
                                    subText: i18n("You allowed it here: Undo removes it from the file it went into, as it was before.")
                                }
                            }
                            PlasmaComponents3.BusyIndicator {
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                visible: ruleRow.busy
                                running: visible
                            }
                        }
                        // Allow asks first, saying what changes where
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            visible: ruleRow.asking
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                font: Kirigami.Theme.smallFont
                                text: i18n("This %1.", ruleRow.rule.change)
                            }
                            RowLayout {
                                spacing: Kirigami.Units.smallSpacing

                                PlasmaComponents3.Button {
                                    icon.name: Icons.plasma.allow
                                    icon.color: Icons.color("allow", Kirigami.Theme)
                                    text: i18n("Allow")
                                    enabled: root.ruleBusy === ""   // (one settings write at a time)
                                    onClicked: {
                                        view.confirmRule = ""
                                        root.changeRule(ruleRow.rule, true, origin.host)
                                    }
                                }
                                PlasmaComponents3.Button {
                                    text: i18n("Cancel")
                                    onClicked: view.confirmRule = ""
                                }
                            }
                        }
                    }
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: root.ruleMessage !== "" && !root.ruleRevoked && root.ruleHost === origin.host
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    text: root.ruleMessage
                }
            }
            }
        }

        // Where it all comes from
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: !!view.perms
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.55
            text: view.sources.length > 1 ? i18n("Read from your settings and the chats on this computer and on the SSH hosts shown, without using any tokens.")
                                          : i18n("Read from your settings and the chats on this computer, without using any tokens.")
        }
    }
    }
}
