import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// What "Find a chat" found (main.qml: runSearch): on this computer, then on
// each SSH host shown, newest first. Click one to bring it up where it runs,
// or to reopen it (in a terminal or VS Code, as the switch of Recent chats says).
// Before the chats: the project folders, plans and memories with those words
// (a folder opens the new-chat box, a plan or a memory opens to read). Each
// source and each kind of thing it found folds under its heading.
ColumnLayout {
    id: found

    readonly property var sources: [""].concat(root.shownHosts)

    spacing: Kirigami.Units.smallSpacing

    Repeater {
        model: found.sources.length
        delegate: ColumnLayout {
            id: block

            required property int index
            readonly property string host: found.sources[index] || ""
            readonly property var answer: root.searchResults[host] || ({ busy: false, results: [], more: false, error: "" })
            readonly property var projects: answer.projects || []
            readonly property var plans: answer.plans || []
            readonly property var memories: answer.memories || []
            // (a host shown since the words were typed is searched as it comes: not "nothing" before its answer)
            readonly property bool nothing: host in root.searchResults
                                            && answer.results.length + projects.length + plans.length + memories.length === 0
            // Folded or not (main.qml: searchShown): the source, and each kind
            // of thing it found. Chats show at first; the rest show too when
            // no chat has the words
            readonly property bool open: root.searchShown(host, "source", true)
            readonly property bool projectsOpen: root.searchShown(host, "projects", answer.results.length === 0)
            readonly property bool plansOpen: root.searchShown(host, "plans", answer.results.length === 0)
            readonly property bool memoriesOpen: root.searchShown(host, "memories", answer.results.length === 0)
            readonly property bool chatsOpen: root.searchShown(host, "chats", true)
            readonly property var kinds: [["projects", projects], ["plans", plans], ["memories", memories], ["chats", answer.results]]
                                         .filter(kind => kind[1].length > 0).map(kind => kind[0])
            readonly property bool allOpen: open && kinds.every(kind => block[kind + "Open"])

            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            Layout.rightMargin: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing / 2

            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                // click to fold or unfold what this source found
                Item {
                    Layout.fillWidth: true
                    implicitHeight: sourceLine.implicitHeight

                    RowLayout {
                        id: sourceLine
                        anchors.fill: parent
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: block.open ? Icons.plasma.unfolded : Icons.plasma.folded
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Layout.preferredWidth
                            opacity: sourceMouse.containsMouse ? 0.9 : 0.6
                        }
                        Kirigami.Icon {
                            source: block.host ? Icons.plasma.host : Icons.plasma.computer
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Layout.preferredWidth
                        }
                        PlasmaComponents3.Label {
                            id: sourceLabel
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: (block.host || i18n("This computer"))
                                  + (block.answer.busy ? "" : " · " + i18np("%1 chat", "%1 chats", block.answer.results.length)
                                                               + (block.answer.more ? "+" : "")
                                                               + (block.projects.length ? ", " + i18np("%1 folder", "%1 folders", block.projects.length) : "")
                                                               + (block.plans.length ? ", " + i18np("%1 plan", "%1 plans", block.plans.length) : "")
                                                               + (block.memories.length ? ", " + i18np("%1 memory", "%1 memories", block.memories.length) : ""))
                            font.bold: true
                            opacity: 0.8
                            elide: Text.ElideRight
                        }
                    }

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: sourceLabel.text
                        subText: block.open ? i18n("Click to fold what was found here.") : i18n("Click to show what was found here.")

                        MouseArea {
                            id: sourceMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.showFound(block.host, ["source"], !block.open)
                        }
                    }
                }
                PlasmaComponents3.BusyIndicator {
                    visible: block.answer.busy
                    running: visible
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                // every kind it found at once (folding them leaves the source open)
                PlasmaComponents3.ToolButton {
                    visible: block.kinds.length > 1
                    icon.name: block.allOpen ? Icons.plasma.collapseAll : Icons.plasma.expandAll
                    text: block.allOpen ? i18n("Fold all") : i18n("Unfold all")
                    font: Kirigami.Theme.smallFont
                    Layout.preferredHeight: sourceLabel.implicitHeight + Kirigami.Units.smallSpacing
                    onClicked: root.showFound(block.host, block.allOpen ? block.kinds : ["source"].concat(block.kinds), !block.allOpen)
                }
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: block.open && block.answer.error !== ""
                text: block.answer.error
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: block.open && !block.answer.busy && block.answer.error === "" && block.nothing
                text: i18n("Nothing with all of these words: no chat (its name, folder or your prompts), project folder, plan or memory.")
                opacity: 0.6
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
            }

            // project folders: click for a new chat there
            PlasmaComponents3.ToolButton {
                visible: block.open && block.projects.length > 0
                flat: true
                icon.name: block.projectsOpen ? Icons.plasma.unfolded : Icons.plasma.folded
                text: i18n("Folders (%1)", block.projects.length)
                font: Kirigami.Theme.smallFont
                onClicked: root.showFound(block.host, ["projects"], !block.projectsOpen)
            }
            Repeater {
                model: block.open && block.projectsOpen ? block.projects.length : 0
                delegate: FoundLine {
                    required property int index
                    readonly property var project: block.projects[index] || ({ folder: "", folderShort: "", chats: 0, lastActive: 0, account: "", groupId: "" })
                    icon: Icons.plasma.project
                    text: project.folderShort || project.folder
                    detail: i18np("%1 chat", "%1 chats", project.chats) + " · " + root.ago(root.now - project.lastActive)
                    account: root.hostGroups(block.host).length > 1 ? project.profile : ""
                    tipTitle: project.folder
                    tip: i18n("Click to start a new chat in this folder on %1: its new-chat box opens with this folder first.", project.account)
                    onActivated: root.openFoundProject(project, block.host)
                }
            }

            // plans: click to read one
            PlasmaComponents3.ToolButton {
                visible: block.open && block.plans.length > 0
                flat: true
                icon.name: block.plansOpen ? Icons.plasma.unfolded : Icons.plasma.folded
                text: i18n("Plans (%1)", block.plans.length)
                font: Kirigami.Theme.smallFont
                onClicked: root.showFound(block.host, ["plans"], !block.plansOpen)
            }
            Repeater {
                model: block.open && block.plansOpen ? block.plans.length : 0
                delegate: FoundLine {
                    required property int index
                    readonly property var plan: block.plans[index] || ({ slug: "", title: "", profileDir: "", updatedAt: 0, account: "" })
                    icon: Icons.plasma.plan
                    text: plan.title
                    detail: root.ago(root.now - plan.updatedAt)
                    account: root.hostGroups(block.host).length > 1 ? plan.profile : ""
                    tipTitle: plan.title
                    tip: i18n("A plan on %1. Click to read it.", plan.account)
                    onActivated: root.openPlan(plan.slug, plan.profileDir, block.host)
                }
            }

            // memories: click to read one
            PlasmaComponents3.ToolButton {
                visible: block.open && block.memories.length > 0
                flat: true
                icon.name: block.memoriesOpen ? Icons.plasma.unfolded : Icons.plasma.folded
                text: i18n("Memories (%1)", block.memories.length)
                font: Kirigami.Theme.smallFont
                onClicked: root.showFound(block.host, ["memories"], !block.memoriesOpen)
            }
            Repeater {
                model: block.open && block.memoriesOpen ? block.memories.length : 0
                delegate: FoundLine {
                    required property int index
                    readonly property var memory: block.memories[index] || ({ name: "", description: "", type: "", path: "", folderShort: "", updatedAt: 0, account: "" })
                    icon: root.memoryIcon(memory.type)
                    text: memory.description || memory.name
                    detail: memory.folderShort || i18n("every folder")
                    account: root.hostGroups(block.host).length > 1 ? memory.profile : ""
                    tipTitle: memory.name
                    tip: !block.host ? i18n("A memory on %1. Click to read it.", memory.account)
                         : root.vscodeInstalled ? i18n("A memory on %1. Click to open its file on %2 in VS Code (Remote - SSH).", memory.account, block.host)
                         : i18n("A memory on %1. Needs VS Code (Remote - SSH) to open a memory on %2.", memory.account, block.host)
                    enabled: !block.host || root.vscodeInstalled
                    onActivated: root.openMemory(memory, block.host, false)
                }
            }

            PlasmaComponents3.ToolButton {
                visible: block.open && block.answer.results.length > 0
                flat: true
                icon.name: block.chatsOpen ? Icons.plasma.unfolded : Icons.plasma.folded
                text: i18n("Chats (%1)", block.answer.results.length + (block.answer.more ? "+" : ""))
                font: Kirigami.Theme.smallFont
                onClicked: root.showFound(block.host, ["chats"], !block.chatsOpen)
            }

            Repeater {
                model: block.open && block.chatsOpen ? block.answer.results.length : 0
                delegate: ColumnLayout {
                    id: hit

                    required property int index
                    readonly property var chat: block.answer.results[index] || root.emptyFound
                    // listed above right now (it runs, or just finished): its row's state
                    readonly property var row: root.listedRow(chat.sessionId, chat.profileDir, block.host)

                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.gridUnit
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Rectangle {
                            visible: hit.row !== null
                            Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 0.5)
                            Layout.preferredHeight: Layout.preferredWidth
                            radius: width / 2
                            // (red as in its row: a chat that failed, or that a usage limit stopped)
                            color: !hit.row ? "transparent"
                                   : hit.row.reason === "failed" || (!!hit.row.stopped && !hit.row.stopped.over) ? Kirigami.Theme.negativeTextColor
                                   : root.stateColor(hit.row.state)
                        }
                        PlasmaComponents3.Label {
                            id: hitName
                            textFormat: Text.PlainText
                            text: hit.chat.name
                            font.underline: hitMouse.containsMouse
                            elide: Text.ElideRight
                            Layout.fillWidth: true

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                width: hitName.contentWidth
                                height: parent.height
                                mainText: hit.chat.name
                                subText: (hit.row ? i18n("Listed above: %1. Click to go to it.", root.stateText(hit.row))
                                                  : i18n("Click to reopen it on %1.", hit.chat.account))
                                         + (hit.chat.shared ? "\n" + i18n("Shared between accounts; last used on %1.", hit.chat.profile) : "")
                                         + (hit.chat.match ? "\n\n" + hit.chat.match : "")

                                MouseArea {
                                    id: hitMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.openFound(hit.chat, block.host)
                                }
                            }
                        }
                        Kirigami.Icon {
                            source: Icons.plasma.share
                            visible: hit.chat.shared
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Layout.preferredWidth
                            Layout.alignment: Qt.AlignVCenter
                            opacity: 0.6
                        }
                        Tag {
                            // its account, where there's more than one
                            visible: root.hostGroups(block.host).length > 1
                            text: hit.chat.profile
                            tooltipTitle: hit.chat.account
                            tooltip: i18n("The account it's on")
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            text: i18nc("found chat: folder · how long ago", "%1 · %2", hit.chat.cwdShort || "~",
                                        root.ago(root.now - hit.chat.lastActive))
                            opacity: 0.6
                            font: Kirigami.Theme.smallFont
                            elide: Text.ElideLeft
                            Layout.maximumWidth: Kirigami.Units.gridUnit * 11
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: hit.chat.match !== ""
                        text: hit.chat.match
                        opacity: 0.7
                        elide: Text.ElideRight
                        font: Kirigami.Theme.smallFont
                    }
                }
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.gridUnit
                visible: block.open && block.chatsOpen && block.answer.more
                text: i18n("More chats have these words: add a word to narrow it down.")
                opacity: 0.6
                font: Kirigami.Theme.smallFont
            }

        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }
}
