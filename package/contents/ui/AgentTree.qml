import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A chat's subagents as a tree: what each one is doing; click one for its
// task, its last steps and its report, and to open its whole run. Under a
// chat's row (SessionRow.qml: its Agents tag) and in its chat window's strip
// (ChatPane.qml: the header's Agents tag), made only while shown there; its
// tooltips are TipAreas, which show in the chat window too.
ColumnLayout {
    id: tree

    property var agents: []        // in the order shown (each one after the one that started it)
    property string rowKey: ""     // (with an agent's id: whether its details are unfolded, root.expandedAgentRuns)
    property var session: ({})     // the chat (its chatId and profileDir: to open an agent's whole run)
    property string remoteHost: ""
    property real pointSize: Kirigami.Theme.smallFont.pointSize

    spacing: Kirigami.Units.smallSpacing / 2

    Repeater {
        model: tree.agents.length
        delegate: RowLayout {
            id: agentRow
            required property int index
            readonly property var modelData: tree.agents[index] || root.emptyAgent
            readonly property string runKey: tree.rowKey + "|" + modelData.id
            readonly property bool open: root.expandedAgentRuns[runKey] === true
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.gridUnit * 0.9 * modelData.depth
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.alignment: Qt.AlignTop
                text: "└"
                opacity: 0.4
            }
            Rectangle {
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: Math.round(Kirigami.Units.gridUnit * 0.3)
                Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 0.45)
                Layout.preferredHeight: Layout.preferredWidth
                radius: width / 2
                color: agentRow.modelData.status === "running" ? Kirigami.Theme.focusColor
                     : agentRow.modelData.status === "done" ? Kirigami.Theme.positiveTextColor
                     : Kirigami.Theme.disabledTextColor
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                // Its lines: click for its task, its last steps and its report
                Item {
                    id: agentHead
                    Layout.fillWidth: true
                    implicitHeight: agentLines.implicitHeight

                    HoverShade {
                        target: agentHead
                        shown: agentMouse.containsMouse
                        side: Kirigami.Units.smallSpacing / 2
                    }
                    ColumnLayout {
                        id: agentLines
                        anchors.fill: parent
                        spacing: 0
                        RowLayout {
                            id: headRow
                            Layout.fillWidth: true
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: agentRow.modelData.description || agentRow.modelData.type
                                elide: Text.ElideRight
                                font.pointSize: tree.pointSize
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                // its kind, and the model it runs on (at most 40% of the line: its name first, as in VS Code)
                                Layout.maximumWidth: Math.round(headRow.width * 0.4)
                                elide: Text.ElideRight
                                text: agentRow.modelData.type + (agentRow.modelData.model ? " · " + agentRow.modelData.model : "")
                                opacity: 0.6
                                font.pointSize: tree.pointSize
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                // failed: it ended on an API error (e.g. a usage limit)
                                text: agentRow.modelData.status === "running"
                                      ? i18n("running · %1", root.duration(root.now - (agentRow.modelData.started || root.now)))
                                      : agentRow.modelData.status === "done" ? i18n("done")
                                      : agentRow.modelData.status === "failed" ? i18n("failed") : i18n("stopped")
                                color: agentRow.modelData.status === "failed" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                opacity: agentRow.modelData.status === "failed" ? 1 : 0.7
                                font.pointSize: tree.pointSize
                            }
                            Kirigami.Icon {
                                source: agentRow.open ? Icons.plasma.unfolded : Icons.plasma.folded
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Layout.preferredWidth
                                opacity: agentMouse.containsMouse ? 0.9 : 0.4
                            }
                        }
                        // What it does, in words, and its context now at the end, under its state
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 1
                            visible: activityLabel.text !== "" || contextLabel.text !== ""
                            PlasmaComponents3.Label {
                                id: activityLabel
                                // a running one's call apart from its task: in the working
                                // color, as a chat's "▸ what it's doing"
                                readonly property bool doing: agentRow.modelData.status === "running" && agentRow.modelData.activity !== ""
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: doing ? "▸ " + agentRow.modelData.activity : agentRow.modelData.activity
                                color: doing ? root.stateColor("working") : Kirigami.Theme.textColor
                                opacity: doing ? 1 : 0.6
                                elide: Text.ElideRight
                                font.pointSize: tree.pointSize
                            }
                            PlasmaComponents3.Label {
                                id: contextLabel
                                textFormat: Text.PlainText
                                // (as Claude's agent list counts it: its last request, both ways)
                                Layout.rightMargin: Kirigami.Units.iconSizes.small + headRow.spacing
                                visible: text !== ""
                                text: agentRow.modelData.context ? i18n("%1 tokens", root.formatTokens(agentRow.modelData.context)) : ""
                                opacity: 0.6
                                font.pointSize: tree.pointSize
                            }
                        }
                    }

                    TipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: agentRow.modelData.description || agentRow.modelData.type
                        subText: (activityLabel.truncated ? agentRow.modelData.activity + "\n\n" : "")
                                 + (contextLabel.visible ? i18n("Its context now: %1 (what its last request sent and got back, as Claude's agent list counts it).", contextLabel.text) + "\n\n" : "")
                                 + (agentRow.open ? i18n("Click to fold it up again.")
                                                  : i18n("Click for its task, what it runs now, its last steps and its report."))

                        MouseArea {
                            id: agentMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.toggleAgentRun(agentRow.runKey)
                        }
                    }
                }

                // What it was asked, what it did last, and what it handed back
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing / 2
                    visible: agentRow.open
                    implicitHeight: runColumn.implicitHeight + Kirigami.Units.smallSpacing * 2
                    radius: Kirigami.Units.cornerRadius
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)

                    ColumnLayout {
                        id: runColumn
                        anchors.fill: parent
                        anchors.margins: Kirigami.Units.smallSpacing
                        spacing: Kirigami.Units.smallSpacing / 2

                        PlasmaComponents3.Label {
                            id: taskLabel
                            Layout.fillWidth: true
                            visible: !!agentRow.modelData.task
                            text: i18nc("what a subagent was asked to do", "Task: %1", agentRow.modelData.task)
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            maximumLineCount: 4
                            elide: Text.ElideRight
                            opacity: 0.7
                            font.pointSize: tree.pointSize

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                active: taskLabel.truncated
                                mainText: i18n("Its task")
                                subText: agentRow.modelData.task
                            }
                        }
                        // Running now: the calls it's on, exact, each with how long it has run
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            visible: runningRepeater.count > 0
                            text: i18nc("the tool calls a subagent is on", "Running now:")
                            font.pointSize: tree.pointSize
                            font.bold: true
                            opacity: 0.8
                        }
                        Repeater {
                            id: runningRepeater
                            model: agentRow.modelData.status === "running" ? (agentRow.modelData.running || []).length : 0
                            delegate: RowLayout {
                                id: runningCall
                                required property int index
                                readonly property var call: (agentRow.modelData.running || [])[index] || { line: "", since: null }
                                Layout.fillWidth: true
                                PlasmaComponents3.Label {
                                    id: callLabel
                                    Layout.fillWidth: true
                                    text: "▸ " + runningCall.call.line
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    font.pointSize: tree.pointSize
                                    font.bold: true
                                    opacity: 0.9

                                    TipArea {
                                        textFormat: Text.PlainText
                                        anchors.fill: parent
                                        active: callLabel.truncated
                                        mainText: i18n("Running now")
                                        subText: runningCall.call.line
                                    }
                                }
                                PlasmaComponents3.Label {
                                    visible: !!runningCall.call.since
                                    text: runningCall.call.since ? root.ranFor(root.now - runningCall.call.since) : ""
                                    textFormat: Text.PlainText
                                    horizontalAlignment: Text.AlignRight
                                    opacity: 0.6
                                    font.pointSize: tree.pointSize
                                }
                            }
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: root.agentNumbers(agentRow.modelData)
                            opacity: 0.7
                            font.pointSize: tree.pointSize
                        }
                        Repeater {
                            model: (agentRow.modelData.steps || []).length
                            delegate: PlasmaComponents3.Label {
                                required property int index
                                Layout.fillWidth: true
                                text: "▸ " + ((agentRow.modelData.steps || [])[index] || "")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                opacity: 0.8
                                font.pointSize: tree.pointSize
                                font.bold: agentRow.modelData.status === "running" && index === (agentRow.modelData.steps || []).length - 1
                            }
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            visible: !!agentRow.modelData.report
                            text: i18nc("what a subagent handed back", "Report: %1", agentRow.modelData.report)
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            maximumLineCount: 12
                            elide: Text.ElideRight
                            font.pointSize: tree.pointSize
                        }
                        PlasmaComponents3.ToolButton {
                            icon.name: Icons.plasma.openRun
                            text: i18n("Open the whole run")
                            enabled: !!tree.session.chatId
                            onClicked: root.openAgentRun(tree.session, agentRow.modelData.id, tree.remoteHost)

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Everything it did")
                                subText: i18n("Its task, every step with the start of each result, and its report, as a Markdown file in your app for those. Claude Code itself can't open a subagent from outside.")
                                         + (tree.remoteHost ? " " + (root.isContainer(tree.remoteHost) ? i18n("Fetched from %1.", root.hostLabel(tree.remoteHost))
                                                                                       : i18n("Fetched from %1 over ssh.", tree.remoteHost)) : "")
                            }
                        }
                    }
                }
            }
        }
    }
}
