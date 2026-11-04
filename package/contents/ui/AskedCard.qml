import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "markdown.mjs" as Md
import "icons.mjs" as Icons

// What Claude asked, once you answered it, as Claude's in Talpy Chat (ChatPane.qml; VS Code
// chat.tsx AskedCard): ● and the question, its header in a small tag before it; its options
// folded (the ones you picked ✓ and bold, the others muted); a plan's title, the plan folded.
// Your answer comes under it, as yours; a question you declined, or chose to chat about, says
// so here. A file of its own, made the first time a card shows (a chat's window opens as
// quickly as before); its options and plan are made only once unfolded.
RowLayout {
    id: askedBox
    spacing: 0
    property var pane: null     // the window it's in (ChatPane.qml): its colours, fonts and openTools
    property var asked: null    // what was asked (pane.py asked_of)
    property string key: ""     // its call's (its options unfolded: the window's openTools[key])
    readonly property bool unfolded: !!pane && pane.openTools[key] === true
    readonly property var a: asked || ({ state: "", questions: [] })

    FontMetrics {
        id: fm
        font.family: askedBox.pane ? askedBox.pane.chatFamily : ""
        font.pointSize: askedBox.pane ? askedBox.pane.pt : 10
    }

    // ● in Claude's orange, on its first line (as ChatPane's Dot)
    Item {
        Layout.preferredWidth: askedBox.pane.gutter
        Layout.preferredHeight: fm.height
        Layout.alignment: Qt.AlignTop

        Rectangle {
            width: Math.round(fm.height * 0.42)
            height: width
            radius: width / 2
            x: Math.round((askedBox.pane.gutter - width) * 0.4)
            anchors.verticalCenter: parent.verticalCenter
            color: askedBox.pane.claudeColor
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0

        Repeater {
            model: askedBox.a.questions ? askedBox.a.questions
                 : [{ header: i18nc("a tag before the plan's title", "Plan"),
                      question: askedBox.a.title || i18n("A plan, ready to start"), options: [], picked: [] }]
            delegate: ColumnLayout {
                id: questionBox
                required property var modelData
                required property int index
                Layout.fillWidth: true
                Layout.topMargin: index > 0 ? Kirigami.Units.smallSpacing : 0
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Rectangle {
                        visible: questionBox.modelData.header !== ""
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: Math.max(0, (fm.height - implicitHeight) / 2)
                        implicitWidth: headerText.implicitWidth + Kirigami.Units.smallSpacing * 2
                        implicitHeight: headerText.implicitHeight + 2
                        radius: Kirigami.Units.cornerRadius
                        color: "transparent"
                        border.width: 1
                        border.color: askedBox.pane.mix(askedBox.pane.textColor, 0.3)

                        PlasmaComponents3.Label {
                            id: headerText
                            anchors.centerIn: parent
                            textFormat: Text.PlainText
                            text: questionBox.modelData.header
                            color: askedBox.pane.claudeColor
                            font.family: askedBox.pane.chatFamily
                            font.pointSize: askedBox.pane.pt * 0.8
                        }
                    }
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: questionBox.modelData.question
                        wrapMode: Text.Wrap
                        color: askedBox.pane.textColor
                        font.family: askedBox.pane.chatFamily
                        font.pointSize: askedBox.pane.pt
                    }
                }
                Loader {
                    active: askedBox.unfolded && questionBox.modelData.options.length > 0
                    visible: active
                    Layout.fillWidth: true
                    Layout.topMargin: active ? Kirigami.Units.smallSpacing / 2 : 0
                    sourceComponent: ColumnLayout {
                        spacing: 0

                        Repeater {
                            model: questionBox.modelData.options
                            delegate: RowLayout {
                                id: optionRow
                                required property var modelData
                                readonly property bool picked: questionBox.modelData.picked.indexOf(modelData.label) >= 0
                                Layout.fillWidth: true
                                spacing: 0

                                Item {
                                    Layout.preferredWidth: Math.round(fm.height * 1.15)
                                    Layout.preferredHeight: fm.height
                                    Layout.alignment: Qt.AlignTop

                                    Kirigami.Icon {
                                        visible: optionRow.picked
                                        source: Icons.plasma.picked
                                        width: Math.round(fm.height * 0.75)
                                        height: width
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: askedBox.pane.textColor
                                    }
                                }
                                PlasmaComponents3.Label {
                                    Layout.fillWidth: true
                                    textFormat: Text.StyledText
                                    text: (optionRow.picked ? "<b>" + Md.escape(optionRow.modelData.label) + "</b>" : Md.escape(optionRow.modelData.label))
                                          + (optionRow.modelData.description ? "&nbsp;&nbsp;<font color=\"" + askedBox.pane.hex(askedBox.pane.mutedColor) + "\">"
                                                                               + Md.escape(optionRow.modelData.description) + "</font>" : "")
                                    wrapMode: Text.Wrap
                                    color: optionRow.picked ? askedBox.pane.textColor : askedBox.pane.mutedColor
                                    font.family: askedBox.pane.chatFamily
                                    font.pointSize: askedBox.pane.pt
                                }
                            }
                        }
                    }
                }
            }
        }
        // Show the options / the plan (Hide, unfolded)
        Rectangle {
            visible: askedBox.a.questions ? askedBox.a.questions.some(q => q.options.length > 0) : !!askedBox.a.plan
            Layout.topMargin: Kirigami.Units.smallSpacing / 2
            implicitWidth: toggleRow.implicitWidth + Kirigami.Units.smallSpacing
            implicitHeight: toggleRow.implicitHeight
            radius: Kirigami.Units.cornerRadius
            color: toggleHover.hovered ? askedBox.pane.mix(askedBox.pane.textColor, 0.06) : "transparent"

            RowLayout {
                id: toggleRow
                spacing: Kirigami.Units.smallSpacing / 2

                Kirigami.Icon {
                    source: askedBox.unfolded ? Icons.plasma.unfolded : Icons.plasma.folded
                    Layout.preferredWidth: Math.round(fm.height * 0.7)
                    Layout.preferredHeight: Layout.preferredWidth
                    color: toggleHover.hovered ? askedBox.pane.textColor : askedBox.pane.mutedColor
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    text: askedBox.a.questions ? (askedBox.unfolded ? i18n("Hide the options") : i18n("Show the options"))
                        : askedBox.unfolded ? i18n("Hide the plan") : i18n("Show the plan")
                    color: toggleHover.hovered ? askedBox.pane.textColor : askedBox.pane.mutedColor
                    font.family: askedBox.pane.chatFamily
                    font.pointSize: askedBox.pane.pt * 0.92
                }
            }
            HoverHandler {
                id: toggleHover
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                onTapped: {
                    const next = Object.assign({}, askedBox.pane.openTools)
                    next[askedBox.key] = !askedBox.unfolded
                    askedBox.pane.openTools = next
                }
            }
        }
        // The plan, unfolded
        Loader {
            active: askedBox.unfolded && !!askedBox.a.plan
            visible: active
            Layout.fillWidth: true
            Layout.topMargin: active ? Kirigami.Units.smallSpacing : 0
            sourceComponent: Rectangle {
                implicitHeight: planText.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                radius: Kirigami.Units.cornerRadius
                color: askedBox.pane.mdStyle.blockBg
                border.width: 1
                border.color: askedBox.pane.borderColor

                TextEdit {
                    id: planText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Kirigami.Units.largeSpacing
                    anchors.rightMargin: Kirigami.Units.largeSpacing
                    text: Md.toHtml(askedBox.a.plan, askedBox.pane.mdStyle, -1)
                    textFormat: TextEdit.RichText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: askedBox.pane.textColor
                    selectionColor: Kirigami.Theme.focusColor
                    selectedTextColor: Kirigami.Theme.highlightedTextColor
                    font.family: askedBox.pane.chatFamily
                    font.pointSize: askedBox.pane.pt
                    onLinkActivated: link => {
                        if (link.indexOf("copy:") === 0)
                            askedBox.pane.copyText(Md.clipboardCode(Md.codeBlocks(askedBox.a.plan)[Number(link.slice(5))] || ""), true)
                        else
                            Qt.openUrlExternally(link)
                    }
                }
            }
        }
        PlasmaComponents3.Label {
            visible: askedBox.a.state === "declined" || askedBox.a.state === "chat"
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: "⎿  " + (askedBox.a.state === "chat" ? i18n("Chat about this") : i18n("Declined"))
            elide: Text.ElideRight
            color: askedBox.pane.mutedColor
            font.family: askedBox.pane.chatFamily
            font.pointSize: askedBox.pane.pt * 0.92
        }
    }
}
