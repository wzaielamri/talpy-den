import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Suggested replies above Talpy Chat's reply box (ChatPane.qml, a Loader: read and made
// only while there are chips, so every window opens as quickly; VS Code chat.tsx the same,
// with shared/pane.ts's rules and words): small framed chips once Claude's turn is over,
// the answers to its question first, in your accent (the option it recommends in bold),
// then your usual replies, plain. A click sends one as if you typed it; Shift+click puts it
// in the box first; Alt+1…4 in the box; right-click: Edit before sending, and Don't suggest
// this for one of your usual replies.
Flow {
    id: row
    objectName: "replyChips"   // (tools/bench: the frame they're drawn in)
    spacing: Kirigami.Units.smallSpacing
    Accessible.role: Accessible.ToolBar
    Accessible.name: i18n("Suggested replies")

    readonly property int chipsMax: 4
    function endedAfter(ended) {
        return ({ asked: i18n("Claude's questions"), finished: i18n("a finished turn"), limit: i18n("a usage limit"),
                  interrupted: i18n("an interruption"), failed: i18n("an error"), stopped: i18n("a chat that stopped") })[ended] || ended
    }
    // The chips (VS Code's shared/pane.ts chipsOf, the same rule and words): Claude's question's
    // (more options than fit: the ones it recommends, then the first ones, in their order), then
    // your usual replies after a turn that ended so, each once and none you hid; at most chipsMax
    function chipsOf(asked, ended, yours, hidden) {
        let choices = asked && asked.choices ? asked.choices : []
        if (choices.length > chipsMax) {
            const marked = choices.filter(c => c.recommended).slice(0, chipsMax)
            const rest = choices.filter(c => !c.recommended).slice(0, chipsMax - marked.length)
            choices = choices.filter(c => marked.indexOf(c) >= 0 || rest.indexOf(c) >= 0)
        }
        const out = [], seen = {}
        const add = (label, send, recommended, mine) => {
            const n = out.length + 1
            out.push({ label: label, send: send, recommended: recommended, usual: mine,
                       title: mine ? i18n("Your usual reply after %1: sends “%2” (Alt+%3). Shift+click: put it in the box first, to add to it. Right-click: don't suggest it again.", endedAfter(ended), send, n)
                                   : i18n("Answers Claude's question with “%1” (Alt+%2).", send, n) + (recommended ? " " + i18n("Claude recommends this one.") : "")
                                     + " " + i18n("Shift+click: put it in the box first, to add to it.") })
            seen[pane.replyKey(send)] = true
        }
        for (const c of choices)
            add(c.label, c.send, !!c.recommended, false)
        for (const t of (ended && yours && yours.chips && yours.chips[ended]) || []) {
            if (out.length >= chipsMax)
                break
            const key = pane.replyKey(t)
            if (!seen[key] && !hidden[key])
                add(t, t, false, true)
        }
        return out
    }
    readonly property var chips: chipsOf(pane.asks, pane.turnEnded, pane.usual, pane.hiddenReplies)
    // (as shown: the same list while they're the same, so no chip is made again; the window's
    // Alt+1…4 and its backing off go by it)
    property var shown: []
    onChipsChanged: {
        if (JSON.stringify(chips) === JSON.stringify(shown))
            return
        shown = chips
        if (chips.length)
            pane.chipsSeen = chips
    }
    Component.onCompleted: chipsChanged()

    Repeater {
        model: row.shown
        delegate: Rectangle {
            id: chip
            required property var modelData
            readonly property color tone: modelData.usual ? pane.textColor : pane.youColor
            height: pane.queueButtonHeight
            width: Math.min(row.width, label.implicitWidth + Kirigami.Units.smallSpacing * 3)
            radius: Kirigami.Units.cornerRadius
            // (framed thin, as a held message's buttons; tinted while pressed or under the pointer)
            color: mouse.pressed ? Qt.rgba(tone.r, tone.g, tone.b, 0.16) : mouse.containsMouse ? Qt.rgba(tone.r, tone.g, tone.b, 0.08) : "transparent"
            border.width: 1
            border.color: mouse.containsMouse ? Kirigami.Theme.focusColor : Qt.rgba(tone.r, tone.g, tone.b, modelData.usual ? 0.3 : 0.55)
            Accessible.role: Accessible.Button
            Accessible.name: (modelData.usual ? i18n("Your usual reply") : i18n("Answer")) + ": " + modelData.send
            Accessible.description: modelData.title
            Accessible.onPressAction: pane.takeChip(modelData, false)

            // Its right-click menu, made only now (and gone once closed)
            function openMenu() {
                const menu = menuMaker.createObject(row, { chip: modelData })
                menu.closed.connect(() => menu.destroy())
                menu.popup()
            }

            PlasmaComponents3.Label {
                id: label
                anchors.fill: parent
                anchors.leftMargin: Kirigami.Units.smallSpacing * 1.5
                anchors.rightMargin: Kirigami.Units.smallSpacing * 1.5
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                text: chip.modelData.label
                color: chip.tone
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.bold: chip.modelData.recommended
                elide: Text.ElideRight
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: event => {
                    if (event.button === Qt.RightButton)
                        chip.openMenu()
                    else
                        pane.takeChip(chip.modelData, (event.modifiers & Qt.ShiftModifier) !== 0)
                }
            }
            PlasmaComponents3.ToolTip.text: modelData.title
            PlasmaComponents3.ToolTip.visible: mouse.containsMouse && mouse.pressedButtons === Qt.NoButton
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Component {
        id: menuMaker
        PlasmaComponents3.Menu {
            id: menu
            property var chip: null
            PlasmaComponents3.MenuItem {
                icon.name: Icons.plasma.edit
                text: i18n("Edit before sending")
                onTriggered: pane.takeChip(menu.chip, true)
            }
            PlasmaComponents3.MenuItem {
                visible: !!menu.chip && menu.chip.usual
                height: visible ? implicitHeight : 0
                icon.name: Icons.plasma.hide
                text: i18n("Don't suggest this")
                onTriggered: pane.hideChip(menu.chip)
            }
        }
    }
}
