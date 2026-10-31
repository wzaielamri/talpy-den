import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// An account's last days (talpy_den.py: token_stats): tokens per day as
// bars (today's in the accent color), the totals, its busiest folders and
// its models, in a box as the VS Code extension shows them.
Rectangle {
    id: panel

    property var stats: null
    readonly property var days: stats ? stats.days : []
    readonly property var projects: stats ? stats.projects.slice(0, 5) : []
    readonly property real maxDay: Math.max(1, ...days.map(d => d.total))
    readonly property real maxProject: Math.max(1, ...projects.map(p => p.total))
    // (the folders' numbers in one column as wide as the widest, so every bar's track is as long)
    readonly property real numbersWidth: Math.ceil(Math.max(0, ...projects.map(p => numbersMetrics.advanceWidth(numbersOf(p)))))
    readonly property color muted: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.35)
    readonly property color track: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

    implicitHeight: column.implicitHeight + Kirigami.Units.smallSpacing * 3

    function numbersOf(project) {
        return root.formatTokens(project.total) + (project.prompts ? " · " + i18np("%1 prompt", "%1 prompts", project.prompts) : "")
    }

    FontMetrics {
        id: numbersMetrics
        font: Kirigami.Theme.smallFont
    }
    radius: Kirigami.Units.cornerRadius
    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.topMargin: Kirigami.Units.smallSpacing * 1.5
        anchors.bottomMargin: Kirigami.Units.smallSpacing * 1.5
        anchors.leftMargin: Kirigami.Units.smallSpacing * 2
        anchors.rightMargin: Kirigami.Units.smallSpacing * 2
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: 2

            Repeater {
                model: panel.days.length
                delegate: ColumnLayout {
                    id: dayColumn
                    required property int index
                    readonly property var day: panel.days[index] || root.emptyDay
                    readonly property bool today: index === panel.days.length - 1
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    spacing: 1

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.5

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: Math.max(1, Math.round(parent.height * dayColumn.day.total / panel.maxDay))
                            radius: Math.min(2, width / 2)
                            color: dayColumn.today ? Kirigami.Theme.focusColor : panel.muted
                        }
                        // the baseline
                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.rightMargin: -2
                            height: 1
                            color: panel.track
                        }

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: root.dayName(dayColumn.day.day, true)
                            subText: i18n("%1 tokens (%2 out)", root.formatTokens(dayColumn.day.total), root.formatTokens(dayColumn.day.output))
                                     + "\n" + i18np("%1 chat", "%1 chats", dayColumn.day.chats)
                                     + " · " + i18np("%1 prompt", "%1 prompts", dayColumn.day.prompts)
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: root.dayName(dayColumn.day.day, false)
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        font.bold: dayColumn.today
                        opacity: dayColumn.today ? 0.9 : 0.6
                    }
                }
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: panel.stats !== null
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.8
            text: !panel.stats ? ""
                  : i18np("%1 day: ", "%1 days: ", panel.days.length)
                    + i18n("%1 tokens (%2 out)", root.formatTokens(panel.stats.sum.total), root.formatTokens(panel.stats.sum.output))
                    + " · " + i18np("%1 chat", "%1 chats", panel.stats.sum.chats)
                    + " · " + i18np("%1 prompt", "%1 prompts", panel.stats.sum.prompts)
                    + " · " + i18np("%1 active day", "%1 active days", panel.stats.sum.activeDays)
        }

        // Its busiest folders, by tokens
        Repeater {
            model: panel.projects.length
            delegate: RowLayout {
                id: projectRow
                required property int index
                readonly property var project: panel.projects[index] || root.emptyProject
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                    text: projectRow.project.name
                    elide: Text.ElideMiddle
                    font: Kirigami.Theme.smallFont

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: projectRow.project.path
                        subText: i18n("%1 tokens (%2 out) · %3", root.formatTokens(projectRow.project.total),
                                      root.formatTokens(projectRow.project.output),
                                      i18np("%1 prompt", "%1 prompts", projectRow.project.prompts))
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 5
                    radius: height / 2
                    color: panel.track

                    Rectangle {
                        width: Math.max(1, parent.width * projectRow.project.total / panel.maxProject)
                        height: parent.height
                        radius: height / 2
                        color: Kirigami.Theme.focusColor
                    }
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.preferredWidth: panel.numbersWidth + 1
                    horizontalAlignment: Text.AlignRight
                    text: panel.numbersOf(projectRow.project)
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                }
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: !!panel.stats && panel.stats.models.length > 0
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: !panel.stats ? "" : panel.stats.models.map(m => {
                const share = 100 * m.total / Math.max(1, panel.stats.sum.total)
                return m.model + " " + (share < 1 ? "<1%" : share > 99 && share < 100 ? ">99%" : Math.round(share) + "%")
            }).join(" · ")
        }
    }
}
