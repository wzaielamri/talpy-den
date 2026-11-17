import QtQuick
import QtQuick.Layouts
import QtQml.Models
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "markdown.mjs" as Md
import "sides.mjs" as Sides
import "icons.mjs" as Icons

// The chat's side questions (the tab row's toggle, SideToggle.qml; Explain this): beside the chat, top to
// bottom at the window's right, where the window is wide enough (ChatPane.qml sideBeside: the chat's column
// made room), else over the chat under the tab row (ChatPane.qml's Loader places it; read and made only
// while it's open, after the window's first frame). Its head: the title, Remove all (asked first) and ×.
// Then each question, oldest first, kept to the newest while you're at the end: yours as your messages are
// (› and a band in your accent; Markdown, a quote as a quote), its answer as Claude's replies (● and
// Markdown; Claude's stand-in for one, muted), Talpy thinking and Answering… while it's on its way, or why
// none came with Ask again; when it was asked, on which model and what of the chat it saw (from “…”, or
// whole chat). On hover, over its top right: Copy (Copied a moment, as a message's Copy), Quote in reply,
// Ask with the whole chat (one asked about a part), Remove (×). At its foot, the box (Enter asks,
// Shift+Enter: a new line; Esc anywhere in the panel closes it), the model a question goes to (every
// window's) and what the next one costs, or, with a part (Ask from here, Explain this), where it starts and
// its cost, with × back to the whole chat; the chat shows where with a line (SideFromLine.qml, made only
// then). What asks and takes the answers: Sides.qml. VS Code components/SidePanel.tsx: the same parts,
// words and clicks.
Rectangle {
    id: panel

    readonly property Item logic: sideLogic.item
    readonly property var shown: logic ? logic.shown : []
    readonly property string pick: logic ? logic.pick : ""
    readonly property var part: logic ? logic.part : null   // (the part side questions see; null: all of the chat)
    readonly property bool beside: pane.sideBeside
    readonly property real pt: pane.pt * 0.92
    readonly property real gutter: Math.round(lineFm.height * 1.3)
    readonly property var answerStyle: Object.assign({}, pane.mdStyle, { pt: pt })
    readonly property var standInStyle: Object.assign({}, pane.thoughtStyle, { pt: pt })   // (Claude's stand-in for an answer)
    readonly property var askStyle: Object.assign({}, pane.mdStyle, { pt: pt, accent: pane.hex(pane.youColor) })   // (a quote in yours: your colour's bar)
    // what the next question costs: "" when the chat's context isn't known; with a part, where it starts and
    // what it costs (a part has a cache of its own)
    property real now: Date.now()
    readonly property string cost: part ? Sides.fromNote(part, Sides.sideWarm(shown, pick, now, part.key))
                                        : Sides.costNote(pane.contextLeft ? pane.contextLeft.used || 0 : 0, Sides.sideWarm(shown, pick, now, ""))
    property bool clearAsk: false   // (Remove all clicked: asked first)
    // (the theme's colours, read here once for every row: a row that reads Kirigami.Theme gets a theme of its own)
    readonly property color selection: Kirigami.Theme.focusColor
    readonly property color selectedText: Kirigami.Theme.highlightedTextColor
    readonly property color negative: Kirigami.Theme.negativeTextColor
    property string copied: ""      // (the one whose Copy reads Copied a moment)

    color: Kirigami.Theme.backgroundColor

    property bool opened: false   // (its rows are made from its first frame on: as it's made, none yet)
    Component.onCompleted: {
        pane.sidesNow()
        hold = Math.max(0, shown.length - perFrame)
        opened = true
        sync()
        keepEnd()
        if (hold > 0)
            filling.start()
        if (pane.sideFocus) {   // (opened by you, not by a window opening with it open)
            pane.sideFocus = false
            box.forceActiveFocus()
        }
    }
    onShownChanged: {
        now = Date.now()
        if (shown.length === 0)
            clearAsk = false   // (none left, or another chat: Remove all isn't asked any more)
        if (opened)
            sync()
    }
    Timer {   // (an hour after the last answer, the next one reads the chat again: the cost line says so)
        interval: 60000
        repeat: true
        running: pane.shown
        onTriggered: panel.now = Date.now()
    }
    Timer {
        id: copiedTimer
        interval: 1500
        onTriggered: panel.copied = ""
    }
    // Esc anywhere in it (its box, an answer you clicked in) closes it; the model's menu closes itself first
    Keys.onShortcutOverride: event => {
        if (event.key === Qt.Key_Escape && (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier)
            event.accepted = true
    }
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Escape && (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier) {
            event.accepted = true
            panel.close()
        }
    }

    function focusBox() {
        box.forceActiveFocus()
    }
    function close() {
        pane.showSides(false)
    }
    function ask() {
        if (!logic || box.text.trim() === "")
            return
        if (logic.ask(box.text)) {
            box.text = ""
            keepEnd()
        }
    }
    function openPick() {   // (the model's menu, under its button)
        pickMenu.active = true
        pickMenu.item.popup(pickButton, 0, pickButton.height)
    }
    function act(what, entry) {   // (an answer's actions: Sides.SIDE_ACTIONS)
        if (what === "copy") {
            pane.copyText(entry.a, true)
            copied = entry.sid
            copiedTimer.restart()
        } else if (what === "quote") {
            pane.sideAway()   // (over the chat: out of the way of your reply)
            pane.quoteIn(entry.a)
        } else if (what === "whole") {
            logic.askWhole({ q: entry.q })
            keepEnd()
        } else
            logic.remove(entry.sid)
    }

    // The rows, by id: each keeps its place and state as the list changes (an answer coming in changes its
    // row, not the list); one asked here that pane.py now lists keeps its row under pane.py's id
    ListModel {
        id: rows
    }
    function flatOf(s) {
        const phase = Sides.sideState(s)
        return { sid: String(s.id), q: String(s.q || ""), a: phase === "answered" ? String(s.a) : "",
                 err: phase === "error" ? String(s.error || "") : "", at: Number(s.at) || 0,
                 mname: Sides.sideModelLabel(s), synthetic: s.synthetic === true, phase: phase,
                 saw: Sides.sideSaw(s), parted: phase === "answered" && !!s.from,   // (what it saw; asked about a part)
                 since: String(s.since || "") }   // (the message it was asked from: Ask again asks from it again)
    }
    function rowOf(sid) {
        for (let i = 0; i < rows.count; i++)
            if (rows.get(i).sid === sid)
                return i
        return -1
    }
    // (as it opens: the newest perFrame rows in its first frame, the ones before them perFrame a frame after,
    // so a chat with many doesn't hold the window up; the list stays at its newest meanwhile)
    readonly property int perFrame: 4
    property int hold: 0   // (the oldest ones not made yet)
    Timer {
        id: filling
        interval: 16
        repeat: true
        onTriggered: {
            panel.hold = Math.max(0, panel.hold - panel.perFrame)
            panel.sync()
            if (panel.hold === 0)
                stop()
        }
    }
    function sync() {
        const list = hold > 0 ? shown.slice(Math.min(hold, shown.length)) : shown, handoff = logic ? logic.handoff : {}
        const wanted = {}
        for (const s of list)
            wanted[String(s.id)] = true
        for (const id in handoff) {
            const at = rowOf(handoff[id])
            if (at >= 0 && wanted[id] && rowOf(id) < 0)
                rows.setProperty(at, "sid", id)
        }
        for (let i = rows.count - 1; i >= 0; i--)
            if (!wanted[rows.get(i).sid])
                rows.remove(i)
        for (let i = 0; i < list.length; i++) {
            const flat = flatOf(list[i])
            if (i < rows.count && rows.get(i).sid === flat.sid) {
                const old = rows.get(i)
                if (old.q !== flat.q || old.a !== flat.a || old.err !== flat.err || old.at !== flat.at
                        || old.mname !== flat.mname || old.synthetic !== flat.synthetic || old.phase !== flat.phase
                        || old.saw !== flat.saw || old.parted !== flat.parted || old.since !== flat.since)
                    rows.set(i, flat)
            } else if (i < rows.count)
                rows.insert(i, flat)
            else
                rows.append(flat)
        }
        while (rows.count > list.length)
            rows.remove(rows.count - 1)
    }

    // The newest in view while you're there (stuck): a question asked, an answer coming in or a row getting
    // its height as it's laid out keeps it there; scrolled up, it stays where you read
    property bool stuck: true
    property bool following: false
    function atEnd() {
        return entries.contentY + entries.height >= entries.originY + entries.contentHeight - Kirigami.Units.gridUnit
    }
    function followEnd() {
        following = true
        entries.contentY = Math.max(entries.originY, entries.originY + entries.contentHeight - entries.height)
        following = false
    }
    function keepEnd() {
        stuck = true
        followEnd()
    }

    FontMetrics {
        id: lineFm
        font.family: pane.chatFamily
        font.pointSize: panel.pt
    }

    // A drawn button (plain items, light), framed thin while the pointer is on it (framed: always, as a
    // button with words): a meaning's icon (Icons.plasma; coloured where the colour says something), or words
    component FlatButton: MouseArea {
        id: flat
        property string meaning: ""
        property string label: ""
        property string tip: ""
        property bool framed: false
        property bool lit: false   // (Copied: framed and plain while it says so)
        implicitWidth: label !== "" ? labelText.implicitWidth + Kirigami.Units.largeSpacing
                                    : Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
        implicitHeight: Math.max(labelText.implicitHeight, Kirigami.Units.iconSizes.small) + Kirigami.Units.smallSpacing
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        Accessible.role: Accessible.Button
        Accessible.name: label || tip

        Rectangle {
            anchors.fill: parent
            radius: Kirigami.Units.cornerRadius
            color: "transparent"
            border.width: 1
            border.color: flat.containsMouse || flat.lit ? pane.youColor : flat.framed ? pane.mix(pane.textColor, 0.3) : "transparent"
        }
        Text {
            id: labelText
            anchors.centerIn: parent
            visible: flat.label !== ""
            textFormat: Text.PlainText
            text: flat.label
            font.pointSize: pane.pt * 0.85
            color: flat.containsMouse || flat.lit || flat.framed ? pane.textColor : pane.mutedColor
        }
        Loader {
            anchors.centerIn: parent
            active: flat.meaning !== ""
            sourceComponent: Kirigami.Icon {
                width: Kirigami.Units.iconSizes.small
                height: width
                source: Icons.plasma[flat.meaning]
                color: Icons.TONES[flat.meaning] ? Icons.color(flat.meaning, Kirigami.Theme)
                       : flat.containsMouse ? pane.textColor : pane.mutedColor
            }
        }
        PlasmaComponents3.ToolTip.text: flat.tip
        PlasmaComponents3.ToolTip.visible: flat.containsMouse && flat.tip !== ""
        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
    }

    MouseArea {   // (a press, a wheel or a right-click on it is its own, not what's under it)
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        onWheel: wheel => wheel.accepted = true
    }
    // (beside the chat: a line between them)
    Rectangle {
        visible: panel.beside
        width: 1
        height: parent.height
        color: pane.borderColor
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: Kirigami.Units.largeSpacing
        anchors.rightMargin: Kirigami.Units.largeSpacing
        anchors.topMargin: panel.beside ? Kirigami.Units.largeSpacing : Kirigami.Units.smallSpacing
        anchors.bottomMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Layout.preferredWidth
                source: root.iconDir + Icons.plasma.sideQuestions
                isMask: true
                color: pane.textColor
            }
            Text {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: Sides.SIDE_TITLE
                font.weight: Font.Bold
                color: pane.textColor
                elide: Text.ElideRight
            }
            FlatButton {
                visible: panel.shown.length > 0
                label: Sides.SIDE_CLEAR
                framed: true
                onClicked: panel.clearAsk = !panel.clearAsk
            }
            FlatButton {
                meaning: "close"
                tip: Sides.SIDE_CLOSE + " (Esc)"
                onClicked: panel.close()
            }
        }
        // Remove all: asked first (made only then)
        Loader {
            Layout.fillWidth: true
            active: panel.clearAsk && panel.shown.length > 0
            visible: active
            sourceComponent: ConfirmLine {
                text: Sides.SIDE_CLEAR_ASK
                confirmText: Sides.SIDE_CLEAR
                confirmIcon: "cancel"
                cancelText: i18n("Cancel")
                onConfirmed: {
                    panel.clearAsk = false
                    panel.logic.remove("all")
                }
                onCancelled: panel.clearAsk = false
            }
        }
        // (one that couldn't be removed: why, in the negative colour; a part there's none of: why, muted)
        Text {
            visible: !!panel.logic && panel.logic.note !== ""
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: panel.logic ? panel.logic.note : ""
            wrapMode: Text.Wrap
            color: panel.logic && !panel.logic.noteBad ? pane.mutedColor : panel.negative
            font.pointSize: pane.pt * 0.85
        }

        ListView {
            id: entries
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: rows
            spacing: Math.round(lineFm.height * 1.2)
            cacheBuffer: 100000   // (each made and laid out once, so the list doesn't jump as you scroll: a chat keeps 50 at most)
            // (only you leave the end: a drag, the wheel or the scroll bar; the list moving itself as rows
            // come, go or get their height doesn't)
            onMovementStarted: panel.stuck = false
            onMovementEnded: panel.stuck = panel.atEnd()
            onContentYChanged: if (panel.stuck && !panel.following && !moving && !entriesBar.pressed && !panel.atEnd()) Qt.callLater(panel.followEnd)
            onContentHeightChanged: if (panel.stuck) panel.followEnd()
            onHeightChanged: if (panel.stuck) panel.followEnd()
            PlasmaComponents3.ScrollBar.vertical: PlasmaComponents3.ScrollBar {
                id: entriesBar
                onPressedChanged: panel.stuck = !pressed && panel.atEnd()
            }

            delegate: Item {
                id: entry

                required property int index
                required property string sid
                required property string q
                required property string a
                required property string err
                required property real at
                required property string mname
                required property bool synthetic
                required property string phase
                required property string saw
                required property bool parted
                required property string since
                readonly property bool listed: index >= 0   // (Qt's ListView can leave a removed row drawn: none of it)

                width: entries.width - (entriesBar.visible ? entriesBar.width : 0)
                height: listed ? body.implicitHeight : 0
                visible: listed

                HoverHandler {
                    id: entryHover
                }

                ColumnLayout {
                    id: body
                    width: parent.width
                    spacing: Kirigami.Units.smallSpacing

                    // Yours, as your messages: › in a band in your accent (Markdown: an Explain this' quote as a quote)
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: question.implicitHeight + Kirigami.Units.smallSpacing * 2
                        radius: Kirigami.Units.cornerRadius
                        color: pane.youGround

                        Rectangle {
                            width: 3
                            height: parent.height
                            radius: 1.5
                            color: pane.youColor
                        }
                        Text {
                            y: Kirigami.Units.smallSpacing
                            width: panel.gutter
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                            text: "›"
                            color: pane.youColor
                            font.pointSize: panel.pt
                            font.weight: Font.Bold
                        }
                        TextEdit {
                            id: question
                            x: panel.gutter
                            y: Kirigami.Units.smallSpacing
                            width: parent.width - x - Kirigami.Units.smallSpacing
                            text: Md.toHtml(entry.q, panel.askStyle)
                            textFormat: TextEdit.RichText
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            color: pane.textColor
                            selectionColor: panel.selection
                            selectedTextColor: panel.selectedText
                            font.family: pane.chatFamily
                            font.pointSize: panel.pt
                            WholeRedraw {
                                edit: question
                                base: panel.selection
                            }
                        }
                    }
                    // Its answer, as Claude's replies: ● and its Markdown; on its way, Talpy thinking and
                    // Answering…; none came: why, and Ask again
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Item {
                            Layout.preferredWidth: panel.gutter
                            Layout.preferredHeight: lineFm.height
                            Layout.alignment: Qt.AlignTop

                            Rectangle {
                                visible: entry.phase === "answered"
                                width: Math.round(lineFm.height * 0.42)
                                height: width
                                radius: width / 2
                                x: Math.round((panel.gutter - width) * 0.4)
                                anchors.verticalCenter: parent.verticalCenter
                                color: pane.claudeColor
                            }
                            Loader {
                                anchors.fill: parent
                                active: entry.phase !== "answered"
                                sourceComponent: entry.phase === "pending" ? thinking : failed
                            }
                            Component {
                                id: thinking

                                TalpyIcon {
                                    mode: "thinking"
                                    color: root.stateColor("working")
                                    moving: pane.shown
                                }
                            }
                            Component {
                                id: failed

                                Item {
                                    Kirigami.Icon {
                                        anchors.centerIn: parent
                                        width: Math.min(Kirigami.Units.iconSizes.small, Math.round(lineFm.height))
                                        height: width
                                        source: Icons.plasma.error
                                    }
                                }
                            }
                        }
                        Loader {
                            Layout.fillWidth: true
                            sourceComponent: entry.phase === "answered" ? answerItem : entry.phase === "error" ? errorItem : pendingItem
                        }
                    }
                    // When it was asked, on which model, and what of the chat it saw (from “…”, whole chat)
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: panel.gutter
                        textFormat: Text.PlainText
                        text: pane.timeText(entry.at) + (entry.mname !== "" ? " · " + entry.mname : "") + (entry.saw !== "" ? " · " + entry.saw : "")
                        elide: Text.ElideRight
                        color: pane.mutedColor
                        font.family: pane.chatFamily
                        font.pointSize: pane.pt * 0.8
                    }
                }

                Component {
                    id: answerItem

                    TextEdit {
                        id: answer
                        property int copied: -1   // (a code block's Copy just clicked: it reads Copied a moment)
                        text: Md.toHtml(entry.a, entry.synthetic ? panel.standInStyle : panel.answerStyle, copied)
                        textFormat: TextEdit.RichText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        color: entry.synthetic ? pane.mutedColor : pane.textColor
                        selectionColor: panel.selection
                        selectedTextColor: panel.selectedText
                        font.family: pane.chatFamily
                        font.pointSize: panel.pt
                        onLinkActivated: link => {
                            if (link.indexOf("copy:") === 0) {
                                copied = Number(link.slice(5))
                                pane.copyText(Md.clipboardCode(Md.codeBlocks(entry.a)[copied] || ""), true)
                                codeCopiedTimer.restart()
                            } else
                                Qt.openUrlExternally(link)
                        }
                        onLinkHovered: link => pane.linkHovered(answer, link, linkHover.point.position)   // (where it goes, under the pointer)
                        Timer {
                            id: codeCopiedTimer
                            interval: 1500
                            onTriggered: answer.copied = -1
                        }
                        HoverHandler {
                            id: linkHover
                            cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor
                        }
                        WholeRedraw {
                            edit: answer
                            base: panel.selection
                        }
                    }
                }
                Component {
                    id: pendingItem

                    Text {
                        textFormat: Text.PlainText
                        text: Sides.SIDE_PENDING
                        color: pane.mutedColor
                        font.family: pane.chatFamily
                        font.pointSize: panel.pt
                    }
                }
                Component {
                    id: errorItem

                    RowLayout {
                        spacing: Kirigami.Units.smallSpacing

                        Text {
                            Layout.fillWidth: true
                            textFormat: Text.PlainText
                            text: entry.err
                            wrapMode: Text.Wrap
                            color: panel.negative
                            font.family: pane.chatFamily
                            font.pointSize: panel.pt
                        }
                        PlasmaComponents3.Button {
                            Layout.alignment: Qt.AlignTop
                            icon.name: Icons.plasma.refresh
                            text: Sides.SIDE_AGAIN
                            onClicked: panel.logic.askAgain({ id: entry.sid, q: entry.q, since: entry.since })
                        }
                    }
                }

                // Its actions while the pointer is on it, over its top right (made only then), in SIDE_ACTIONS'
                // order: Copy (Copied a moment, as a message's) and Quote in reply once it has an answer, Ask with
                // the whole chat on an answer about a part, Remove (×)
                Loader {
                    active: (entryHover.hovered || panel.copied === entry.sid) && entry.listed
                    z: 5
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: Kirigami.Units.smallSpacing * 0.5
                    anchors.rightMargin: Kirigami.Units.smallSpacing * 0.5
                    sourceComponent: Rectangle {
                        width: actions.implicitWidth + 2
                        height: actions.implicitHeight + 2
                        radius: Kirigami.Units.cornerRadius
                        color: Kirigami.Theme.backgroundColor
                        border.width: 1
                        border.color: pane.borderColor

                        TextMetrics {
                            id: copyWord
                            font.pointSize: pane.pt * 0.85
                            text: i18n("Copy")
                        }
                        TextMetrics {
                            id: copiedWord
                            font.pointSize: pane.pt * 0.85
                            text: i18n("Copied")
                        }
                        Row {
                            id: actions
                            anchors.centerIn: parent

                            Repeater {
                                model: Sides.SIDE_ACTIONS.filter(w => w === "remove" || (entry.phase === "answered" && (w !== "whole" || entry.parted)))
                                delegate: FlatButton {
                                    required property string modelData
                                    readonly property bool isCopy: modelData === "copy"
                                    // (Ask with the whole chat: asked again, as VS Code's)
                                    meaning: isCopy ? "" : modelData === "remove" ? "cancel" : modelData === "whole" ? "refresh" : modelData
                                    label: !isCopy ? "" : panel.copied === entry.sid ? copiedWord.text : copyWord.text
                                    lit: isCopy && panel.copied === entry.sid
                                    // (as wide with Copied as with Copy)
                                    implicitWidth: isCopy ? Math.max(copyWord.advanceWidth, copiedWord.advanceWidth) + Kirigami.Units.largeSpacing
                                                          : Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
                                    tip: isCopy ? Sides.SIDE_COPY : modelData === "quote" ? Sides.SIDE_QUOTE
                                         : modelData === "whole" ? Sides.SIDE_ASK_WHOLE : Sides.SIDE_REMOVE
                                    onClicked: panel.act(modelData, entry)
                                }
                            }
                        }
                    }
                }
            }
        }
        // (none yet, once the chat is read: what they are, just above the box)
        Text {
            visible: rows.count === 0 && pane.loaded
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            textFormat: Text.PlainText
            text: Sides.SIDE_EMPTY
            wrapMode: Text.Wrap
            color: pane.mutedColor
            font.pointSize: pane.pt * 0.9
        }

        // The box, as the reply box: › and what you type, framed (your accent while you type)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(lineFm.height * 7, Math.max(lineFm.height * 2.4, box.implicitHeight + Kirigami.Units.smallSpacing * 2))
            radius: Kirigami.Units.cornerRadius * 1.5
            color: pane.mix(pane.textColor, 0.035)
            border.width: box.activeFocus ? 2 : 1
            border.color: box.activeFocus ? pane.youColor : pane.borderColor

            Text {
                y: Kirigami.Units.smallSpacing + box.topPadding
                width: panel.gutter
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
                text: "›"
                color: box.activeFocus ? pane.youColor : pane.mutedColor
                font.pointSize: panel.pt
                font.weight: Font.Bold
            }
            PlasmaComponents3.ScrollView {
                id: boxScroll
                anchors.fill: parent
                anchors.leftMargin: panel.gutter - box.leftPadding
                anchors.topMargin: Kirigami.Units.smallSpacing
                anchors.bottomMargin: Kirigami.Units.smallSpacing
                anchors.rightMargin: Kirigami.Units.smallSpacing
                contentWidth: availableWidth
                PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                PlasmaComponents3.TextArea {
                    id: box
                    background: null
                    placeholderText: Sides.SIDE_PLACEHOLDER
                    wrapMode: TextEdit.Wrap
                    font.family: pane.chatFamily
                    font.pointSize: panel.pt
                    // Enter asks (an empty box: nothing), Shift+Enter: a new line, Ctrl+L empties it: the box's
                    // own, never the reply box's send or clear (Esc: the panel's)
                    Keys.onShortcutOverride: event => {
                        const m = event.modifiers & ~Qt.KeypadModifier
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || (event.key === Qt.Key_L && m === Qt.ControlModifier))
                            event.accepted = true
                    }
                    Keys.onPressed: event => {
                        const m = event.modifiers & ~Qt.KeypadModifier
                        if (event.key === Qt.Key_L && m === Qt.ControlModifier) {
                            remove(0, length)
                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            if (m & Qt.ShiftModifier) {
                                if (selectedText)
                                    remove(selectionStart, selectionEnd)
                                insert(cursorPosition, "\n")
                            } else if (preeditText === "") {   // (not while an input method composes)
                                panel.ask()
                            } else {
                                return
                            }
                        } else {
                            return
                        }
                        event.accepted = true
                    }
                    NoSideScroll {   // (as the reply box: never sideways)
                        view: boxScroll
                    }
                }
            }
        }
        // The model a question goes to (its menu: the three), and what the next one costs; with a part, where
        // it starts and what it costs, and × back to the whole chat
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            MouseArea {
                id: pickButton
                Layout.alignment: Qt.AlignTop
                implicitWidth: pickLine.implicitWidth + Kirigami.Units.smallSpacing * 2
                implicitHeight: pickLine.implicitHeight + Kirigami.Units.smallSpacing
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                Accessible.role: Accessible.ButtonMenu
                Accessible.name: Sides.pickLabel(panel.pick)
                onClicked: panel.openPick()

                Rectangle {
                    anchors.fill: parent
                    radius: Kirigami.Units.cornerRadius
                    color: "transparent"
                    border.width: 1
                    border.color: pickButton.containsMouse || pickMenu.active ? pane.mix(pane.textColor, 0.3) : "transparent"
                }
                Row {
                    id: pickLine
                    anchors.centerIn: parent
                    spacing: Kirigami.Units.smallSpacing / 2

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText
                        text: Sides.pickLabel(panel.pick)
                        font.pointSize: pane.pt * 0.8
                        color: pickButton.containsMouse ? pane.textColor : pane.mutedColor
                    }
                    Kirigami.Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Kirigami.Units.iconSizes.small
                        height: width
                        source: Icons.plasma.unfolded
                        color: pickButton.containsMouse ? pane.textColor : pane.mutedColor
                    }
                }
                PlasmaComponents3.ToolTip.text: Sides.SIDE_PICK_TIP
                PlasmaComponents3.ToolTip.visible: containsMouse && !pickMenu.active
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            Text {
                id: costLine
                visible: panel.cost !== ""
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: panel.cost
                horizontalAlignment: Text.AlignRight
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                color: pane.mutedColor
                font.pointSize: pane.pt * 0.8
                HoverHandler {
                    id: costHover
                }
                PlasmaComponents3.ToolTip.text: panel.part ? Sides.SIDE_FROM_TIP : Sides.SIDE_COST_TIP
                PlasmaComponents3.ToolTip.visible: costHover.hovered
                PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            FlatButton {
                visible: panel.part !== null
                Layout.alignment: Qt.AlignTop
                meaning: "cancel"
                tip: Sides.SIDE_WHOLE_TIP
                Accessible.name: Sides.SIDE_WHOLE
                onClicked: panel.logic.wholeChat()
            }
        }
    }

    // The line in the chat above where the part starts (SideFromLine.qml: made only while there's one)
    Loader {
        active: panel.part !== null
        source: active ? "SideFromLine.qml" : ""
    }

    // The model's menu: the three, the one picked marked (made as it opens, gone once it's closed)
    Loader {
        id: pickMenu
        active: false
        sourceComponent: PlasmaComponents3.Menu {
            id: menu
            onClosed: Qt.callLater(() => pickMenu.active = false)

            Instantiator {
                model: Sides.SIDE_PICKS
                delegate: PlasmaComponents3.MenuItem {
                    required property var modelData
                    text: modelData.label
                    checkable: true
                    autoExclusive: true
                    checked: panel.pick === modelData.value
                    onTriggered: {
                        panel.logic.setPick(modelData.value)
                        box.forceActiveFocus()
                    }
                }
                onObjectAdded: (index, object) => menu.insertItem(index, object)
                onObjectRemoved: (index, object) => menu.removeItem(object)
            }
        }
    }
}
