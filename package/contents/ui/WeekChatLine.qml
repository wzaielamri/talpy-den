import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// A chat in the Recap tab's lists (WeekView.qml): its name, where (or when;
// in What got done: what it got done), and its numbers, the last two
// right-aligned in columns as wide as the list's widest (whereWidth,
// numbersWidth; -1: its own). Click it to bring the chat up; one a click
// can't open (an SSH host's) is as bright as the others, only no link: its
// name's tooltip says why. In What got done, a chat whose changes you haven't
// reviewed says so, with its tests after its last edit, as its row in the
// chat list does (main.qml reviewPending, TestsBadge.qml).
PlasmaComponents3.ItemDelegate {
    id: line

    property var chat: ({ name: "", chatId: "", host: "", profileDir: "", folder: "", cwd: "" })
    property string where: (chat.host ? root.hostLabel(chat.host) + ": " : "") + (chat.folder || "")
    property string numbers: ""
    property string tip: ""   // (What got done: its share of your week; its tooltip is made only with one)
    property real indent: 0
    property real whereWidth: -1
    property real numbersWidth: -1
    // (its review now: week.py chat_done; on this computer's clock, also an SSH host's chat's)
    readonly property var review: chat.review || null
    readonly property bool toReview: {
        if (!review)
            return false
        const live = root.listedRow(chat.chatId, chat.profileDir || "", chat.host || "")
        return root.reviewPending({ review: review, chatId: chat.chatId, state: live ? live.state : "" }, chat.host || "", true)
    }

    // (an SSH host's chat: its row in the Chats tab opens it)
    readonly property bool canOpen: !chat.host && !!chat.chatId

    Layout.fillWidth: true
    leftPadding: Kirigami.Units.smallSpacing + indent
    topPadding: Math.round(Kirigami.Units.smallSpacing / 2)
    bottomPadding: Math.round(Kirigami.Units.smallSpacing / 2)
    hoverEnabled: canOpen
    down: canOpen && pressed
    focusPolicy: canOpen ? Qt.StrongFocus : Qt.NoFocus
    onClicked: {
        if (canOpen)
            root.openChatById(chat.chatId, chat.profileDir, chat.cwd || "", "", "", "")
    }

    contentItem: RowLayout {
        spacing: Kirigami.Units.smallSpacing

        // (its name and where in lines of their font's height, whatever their
        // characters: one a fallback font draws, with taller metrics, made the
        // line taller, or set its text higher than its numbers)
        FontMetrics {
            id: nameMetrics
            font: line.indent > 0 ? Kirigami.Theme.smallFont : Kirigami.Theme.defaultFont
        }
        FontMetrics {
            id: smallLine
            font: Kirigami.Theme.smallFont
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: line.chat.name
            elide: Text.ElideRight
            font: nameMetrics.font
            lineHeightMode: Text.FixedHeight
            lineHeight: Math.ceil(nameMetrics.height)

            Loader {   // (why a click does nothing; made only then)
                anchors.fill: parent
                active: !line.canOpen
                sourceComponent: PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    mainText: line.chat.name
                    subText: line.chat.host ? i18n("On %1: its row under %1 opens it", root.hostLabel(line.chat.host))
                                            : i18n("Not found: there's nothing to open")
                }
            }
        }
        Loader {   // (made only when it shows)
            active: line.toReview
            visible: active
            sourceComponent: Tag {
                text: i18nc("a finished chat's changes, not reviewed yet", "To review")
                active: true
                clickable: true
                onClicked: root.openPane({ chatId: line.chat.chatId, sessionId: line.chat.chatId,
                                           profileDir: line.chat.profileDir, cwd: line.chat.cwd || "", name: line.chat.name },
                                         line.chat.host || "", "review")
                tooltipTitle: i18n("Not reviewed yet")
                tooltip: i18n("It changed files. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed.")
            }
        }
        Loader {
            active: line.toReview
            visible: active
            sourceComponent: TestsBadge {
                review: line.review
            }
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.preferredWidth: line.whereWidth
            Layout.maximumWidth: Kirigami.Units.gridUnit * 7
            visible: text !== "" || line.whereWidth > 1
            horizontalAlignment: Text.AlignRight
            text: line.where
            elide: Text.ElideMiddle
            font: smallLine.font
            lineHeightMode: Text.FixedHeight
            lineHeight: Math.ceil(smallLine.height)
            opacity: 0.6
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.preferredWidth: line.numbersWidth
            horizontalAlignment: Text.AlignRight
            text: line.numbers
            font: Kirigami.Theme.smallFont
            opacity: 0.8

            Loader {
                anchors.fill: parent
                active: line.tip !== ""
                sourceComponent: PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    mainText: line.chat.name
                    subText: line.tip
                }
            }
        }
    }
}
