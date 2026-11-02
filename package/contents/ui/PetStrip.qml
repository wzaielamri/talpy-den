import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// A stage where pets (Pet.qml) live. Two kinds:
//
// hero: the big Talpy at the top of the popup, on a little stage whose light
// follows the whole dashboard (warm when a chat needs you, blue while chats
// work, green when they wait for your next message, a starry night once
// everything is done), with a headline and the session counts beside him.
// Double-click his stage a little away from him and there's a cookie for him
// (Pet.qml).
//
// an account's stage (in GroupSection): one pet per chat of that account in
// the sessions list, up to a few. A pet wears the chat's name on a tag in the
// chat's color (the chat's row gets a bar in the same color), stands in the
// row in the list's order, acts the chat out, opens it when clicked, and stays
// the same pet until the chat leaves the list; then it waves and digs away.
//
// Everything stops while the popup is closed.
Item {
    id: strip

    property bool hero: false
    // An account's chats, as [{key, session, host, order}] (order: in the list), the ones that get a pet first
    property var chats: []
    // Names this stage's colors in root.petColors (an account's group key)
    property string stageKey: hero ? "hero" : ""

    // Each Talpy is drawn in a 64-unit box (TalpyView.qml): its body is 38
    // units wide and stands about 31 units out of its burrow
    readonly property real gu: Kirigami.Units.gridUnit
    readonly property real boxSize: hero ? gu * 5.6 : gu * 3.8
    readonly property real bodyWidth: boxSize * 38 / 64
    readonly property real bodyHeight: boxSize * 31 / 64
    readonly property real tagHeight: gu * 1.05
    readonly property real margin: bodyWidth * 0.8
    // Pets stand in a row from the left, spaced so their tags fit
    property int placed: 0   // pets the spots were made for (sync): their tags fit there
    readonly property real slotSpacing: spacingFor(placed)
    readonly property real tagWidth: Math.max(gu * 3.5, slotSpacing - Kirigami.Units.smallSpacing * 2)
    // (the name tag goes under the burrow's mound)
    readonly property real chatGround: height - tagHeight - boxSize * 6 / 64 - Kirigami.Units.smallSpacing
    readonly property real loneGround: height - gu * 0.55
    readonly property bool live: visible && root.dashboardShown
    readonly property bool playing: live && !root.coveredByWindow && inView   // can be seen: things move
    // Scrolled out of sight in the list: its pets hold still (every picture
    // costs). The list (a Flickable) is found up the parents; the hero has none.
    property bool inView: true
    property Item list: null
    function checkInView() {
        if (!list || !live)
            return
        const top = strip.mapToItem(list, 0, 0).y
        const seen = top + strip.height > 0 && top < list.height
        if (seen !== inView)
            inView = seen
    }
    Connections {
        target: strip.list
        function onContentYChanged() { strip.checkInView() }
        function onHeightChanged() { strip.checkInView() }
        function onContentHeightChanged() { Qt.callLater(strip.checkInView) }   // (rows above it came or went)
    }
    onLiveChanged: checkInView()
    onHeightChanged: checkInView()
    property real cursorX: -1        // mouse x while it hovers the stage
    property bool firstShown: false  // once shown, a new pet digs its way up
    readonly property int maxPets: Math.max(0, Plasmoid.configuration.chatPets)
    // Colors that stay apart from each other on light and dark themes
    readonly property var petPalette: ["#e5534b", "#e8913a", "#c9a227", "#4caf50", "#26a69a", "#42a5f5", "#7e57c2", "#ec407a"]
    readonly property bool darkTheme: Kirigami.Theme.backgroundColor.hslLightness < 0.5

    readonly property var shownChats: hero || !Plasmoid.configuration.showPet ? [] : chats.slice(0, maxPets)
    readonly property int hiddenChats: hero ? 0 : Math.max(0, chats.length - shownChats.length)
    readonly property int petCount: petModel.count
    property var chatByKey: ({})
    property var slots: ({})    // pet key → where it stands; a leaving pet keeps its spot

    // The hero's light: what the whole dashboard is up to
    readonly property string mood: root.petMood
    readonly property color moodColor: mood === "needs" ? Kirigami.Theme.neutralTextColor
                                     : mood === "working" || mood === "agents" ? Kirigami.Theme.focusColor
                                     : mood === "idle" ? Kirigami.Theme.positiveTextColor
                                     : mood === "error" ? Kirigami.Theme.negativeTextColor
                                     : darkTheme ? "#6f7fd0" : "#5363b8"   // night
    // The light pulses while a chat needs you, the stars twinkle once all is
    // done: in steps with the pets' clock, 10 a second (each step redraws the
    // whole window, which a smooth animation would do 60 times a second);
    // with less motion (root.lessMotion) they keep still
    property real stageClock: 0
    readonly property bool pulsing: hero && playing && !root.lessMotion
    readonly property real glow: pulsing && mood === "needs" ? 1.3 - 0.3 * Math.cos(stageClock / 1800 * 2 * Math.PI) : 1
    Connections {
        target: root
        enabled: strip.pulsing && (strip.mood === "needs" || strip.mood === "done")
        function onPetFrame(now) {
            if (now - strip.stageClock >= 95)
                strip.stageClock = now
        }
    }
    // a star's light: up in 900 + 260·i ms, down in 1100 + 190·i
    function twinkle(i, now) {
        const up = 900 + 260 * i, down = 1100 + 190 * i
        const p = (now + 400 * i) % (up + down)
        const ease = x => 0.5 - 0.5 * Math.cos(Math.PI * x)
        return p < up ? 0.15 + 0.75 * ease(p / up) : 0.9 - 0.75 * ease((p - up) / down)
    }

    // Room for what the pets hold over their heads (signs, bubbles: up to
    // half the image above the floor)
    implicitHeight: hero ? gu * 6 : gu * 4.5
    clip: true

    ListModel {
        id: petModel  // {petKey, colorIndex, leaving, label, host}; petKey "" is the hero
    }

    onShownChatsChanged: sync()
    onWidthChanged: sync()
    onVisibleChanged: if (visible) laidOut.restart()
    Timer {
        id: laidOut   // (shown again: once its scroll bar is back, see spotsWidth)
        interval: 150
        onTriggered: strip.sync()
    }
    Component.onCompleted: {
        for (let p = parent; p; p = p.parent) {
            if (p.contentY !== undefined && p.flicking !== undefined) {
                list = p
                break
            }
        }
        sync()
    }
    Component.onDestruction: if (root) root.dropPetColors(stageKey)   // (root may be gone at shutdown)

    // Shown and laid out: from now on a new pet digs its way up
    Timer {
        running: strip.live && !strip.firstShown
        interval: 500
        onTriggered: strip.firstShown = true
    }

    function indexOfPet(key) {
        for (let i = 0; i < petModel.count; i++)
            if (petModel.get(i).petKey === key)
                return i
        return -1
    }

    // The width the spots are made for: the stage's while it shows. Hidden
    // (under another tab, or the focus view) the list loses its scroll bar
    // and the stage gets a little wider: the pets keep their spots, which
    // are right again once it shows
    property real spotsWidth: 0

    function spacingFor(n) {
        return Math.max(0, Math.min(gu * 7.5, (spotsWidth - 2 * margin) / Math.max(1, n)))
    }

    // Where a pet stands: the hero on the right of his stage (under the
    // stars), a chat's pet on its spot in the row
    function slotX(key) {
        if (key === "")
            return width * 0.76
        return key in slots ? slots[key] : width / 2
    }

    // A color for a chat: its own (from its key) unless another pet wears it,
    // here or, while there are colors left, on another account's stage
    function freeColor(key) {
        let h = 0
        for (let i = 0; i < key.length; i++)
            h = (h * 31 + key.charCodeAt(i)) >>> 0
        const here = new Set(), anywhere = new Set()
        for (let i = 0; i < petModel.count; i++) {
            const p = petModel.get(i)
            if (!p.leaving && p.colorIndex >= 0)
                here.add(p.colorIndex)
        }
        for (const k in root.petColors)
            anywhere.add(petPalette.indexOf(root.petColors[k]))
        for (const used of [new Set([...here, ...anywhere]), here]) {
            let c = h % petPalette.length
            for (let n = 0; n < petPalette.length; n++, c = (c + 1) % petPalette.length)
                if (!used.has(c))
                    return c
        }
        return h % petPalette.length
    }

    // What the pets showed at the last sync: most checks change nothing for
    // them (the same chats in the same states), and then there's nothing to do
    property string syncedAs: ""

    function sync() {
        if (hero) {
            if (indexOfPet("") < 0)
                petModel.append({ petKey: "", colorIndex: -1, leaving: false, label: "", host: "" })
            return
        }
        if (visible || spotsWidth <= 0)
            spotsWidth = width
        const seen = JSON.stringify([spotsWidth, shownChats.map(c => {
            const s = c.session   // what a pet shows of its chat (Pet.qml)
            return [c.key, s.state, s.reason, s.name, s.since, s.context, s.agents ? s.agents.running : 0,
                    s.stopped ? [s.stopped.kind, s.stopped.over, s.stopped.resetsAt] : null, c.host || ""]
        })])
        if (seen === syncedAs)
            return
        syncedAs = seen
        const byKey = {}
        for (const c of shownChats)
            byKey[c.key] = c
        chatByKey = byKey
        for (let i = 0; i < petModel.count; i++) {
            const p = petModel.get(i)
            const leave = !(p.petKey in byKey)
            if (p.leaving !== leave)
                petModel.setProperty(i, "leaving", leave)
            const label = leave ? p.label : (byKey[p.petKey].session.name || "").trim()
            if (p.label !== label)
                petModel.setProperty(i, "label", label)
        }
        // While a pet digs away the others stay where they are and a new
        // chat's pet waits: none tunnels over it or digs up where it still
        // stands (removePet comes back here once it's gone)
        for (let i = 0; i < petModel.count; i++)
            if (petModel.get(i).leaving) {
                publishColors()
                return
            }
        for (const c of shownChats)
            if (indexOfPet(c.key) < 0)
                petModel.append({ petKey: c.key, colorIndex: freeColor(c.key), leaving: false,
                                  label: (c.session.name || "").trim(), host: c.host })
        // Spots: in the order of the chats in the list, left to right (the
        // colors tie pets to rows)
        const keys = shownChats.slice().sort((a, b) => a.order - b.order).map(c => c.key)
        const spacing = spacingFor(keys.length)
        placed = keys.length
        const spots = {}
        for (let i = 0; i < petModel.count; i++) {
            const k = petModel.get(i).petKey
            spots[k] = margin + (keys.indexOf(k) + 0.5) * spacing
        }
        if (JSON.stringify(spots) !== JSON.stringify(slots))
            slots = spots
        publishColors()
    }

    function removePet(key) {
        const i = indexOfPet(key)
        if (i >= 0 && petModel.get(i).leaving)
            petModel.remove(i)
        publishColors()
        // (the last one gone: the others move up, a new chat's pet comes)
        syncedAs = ""
        sync()
    }

    // The list shows a bar in each pet's color next to its chat
    function publishColors() {
        const colors = {}
        for (let i = 0; i < petModel.count; i++) {
            const p = petModel.get(i)
            if (p.petKey !== "" && !p.leaving && p.colorIndex >= 0)
                colors[p.petKey] = petPalette[p.colorIndex]
        }
        root.setPetColors(stageKey, colors)
    }

    function petFor(key) {
        for (let i = 0; i < pets.count; i++) {
            const p = pets.itemAt(i)
            if (p && p.petKey === key)
                return p
        }
        return null
    }

    // The chat the hero's headline is about: the first one that needs you
    readonly property var callingChat: {
        if (!hero)
            return null
        for (const g of root.allGroups)
            for (const s of g.sessions)
                if (s.state === "waiting")
                    return { session: s, host: g.host || "" }
        return null
    }

    // ------------------------------------------------------------ the stage

    // Hero: a soft card lit in the dashboard's mood
    Rectangle {
        visible: strip.hero
        anchors.fill: parent
        radius: strip.gu * 0.7
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(strip.moodColor.r, strip.moodColor.g, strip.moodColor.b, 0.24 * strip.glow) }
            GradientStop { position: 1; color: Qt.rgba(strip.moodColor.r, strip.moodColor.g, strip.moodColor.b, 0.06) }
        }
        border.width: 1
        border.color: Qt.rgba(strip.moodColor.r, strip.moodColor.g, strip.moodColor.b, 0.35 * strip.glow)
    }

    // An account's stage: barely there, just a place to stand
    Rectangle {
        visible: !strip.hero
        anchors.fill: parent
        radius: strip.gu * 0.5
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.035)
    }

    // An account's floor
    Rectangle {
        visible: !strip.hero
        x: strip.gu * 0.6
        width: strip.width - 2 * x
        height: 1
        y: strip.chatGround
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.10)
    }

    // A starry night once everything is done
    Repeater {
        model: strip.hero ? 9 : 0
        delegate: PlasmaComponents3.Label {
            required property int index
            readonly property var spots: [[0.55, 0.14], [0.64, 0.36], [0.71, 0.10], [0.80, 0.30], [0.88, 0.12],
                                          [0.94, 0.40], [0.60, 0.56], [0.97, 0.66], [0.50, 0.42]]
            visible: strip.mood === "done"
            x: strip.width * spots[index][0]
            y: strip.height * spots[index][1]
            text: index % 3 === 0 ? "✦" : "·"
            font.pixelSize: strip.gu * (index % 3 === 0 ? 0.6 : 1)
            color: strip.darkTheme ? "#d4dbff" : "#5363b8"
            opacity: strip.stageClock > 0 && !root.lessMotion ? strip.twinkle(index, strip.stageClock) : 0.5
        }
    }

    // The hero's headline (what needs you, what works) and the session counts,
    // left of where he stands
    ColumnLayout {
        visible: strip.hero
        x: strip.gu * 0.8
        y: strip.gu * 0.55
        width: Math.max(strip.gu * 8, strip.slotX("") - strip.bodyWidth / 2 - strip.gu - x)
        spacing: Kirigami.Units.smallSpacing
        z: 1

        PlasmaComponents3.Label {
            id: headline
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: root.headlineText()
            font.pixelSize: Math.round(strip.gu * 1.0)
            font.weight: Font.DemiBold
            font.underline: headlineMouse.containsMouse
            color: strip.mood === "needs" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
            elide: Text.ElideRight

            // "1 chat needs you": click to go there
            MouseArea {
                id: headlineMouse
                // the words only: Talpy may stand under the rest of the line, and it's grabbed there
                width: Math.min(parent.width, parent.paintedWidth)
                height: parent.height
                enabled: strip.callingChat !== null
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    const c = strip.callingChat
                    if (c && c.host)
                        root.remoteShow(c.host, c.session)
                    else if (c)
                        root.jumpTo(c.session.sessionId, c.session.profileDir)
                }
                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    active: strip.callingChat !== null
                    mainText: strip.callingChat ? i18n("Open %1", strip.callingChat.session.name) : ""
                    subText: strip.callingChat ? (strip.callingChat.host ? root.hostLabel(strip.callingChat.host) + " · " : "")
                                                 + root.stateText(strip.callingChat.session) : ""
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            visible: strip.hero && root.status !== null

            // (a fixed model: a poll changes the counts' text, not the rows)
            Repeater {
                model: strip.hero ? ["waiting", "working", "idle", "limit", "done"] : []
                delegate: Row {
                    required property string modelData
                    readonly property int n: root.counts[modelData] || 0
                    visible: n > 0
                    spacing: Kirigami.Units.smallSpacing
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(strip.gu * 0.45)
                        height: width
                        radius: width / 2
                        color: root.stateColor(modelData)
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        text: modelData === "waiting" ? i18np("%1 needs input", "%1 need input", n)
                            : modelData === "working" ? i18n("%1 working", n)
                            : modelData === "idle" ? i18n("%1 idle", n)
                            : modelData === "limit" ? i18n("%1 at the usage limit", n)
                            : i18n("%1 done", n)
                        font: Kirigami.Theme.smallFont
                        opacity: 0.85
                    }
                }
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                visible: root.counts.waiting + root.counts.working + root.counts.idle + root.counts.done + root.counts.limit === 0
                text: i18n("No chats running")
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
        }

        // What the working chats do right now, one at a time
        Ticker {
            Layout.fillWidth: true
            items: strip.hero ? root.tickerItems : []
        }
    }

    // A cookie for the hero where you double-click (Pet.qml says if that's
    // too close to him). Under everything else: the headline and the ticker
    // keep their clicks
    MouseArea {
        anchors.fill: parent
        enabled: strip.hero
        acceptedButtons: Qt.LeftButton
        onDoubleClicked: mouse => {
            const hero = strip.petFor("")
            if (hero)
                hero.placeCookie(mouse.x, mouse.y)
        }
    }

    // ------------------------------------------------------------ the pets

    Repeater {
        id: pets
        model: petModel
        // (Pet has properties named like the roles: read them through model,
        // and reach the stage as pets.parent)
        delegate: Pet {
            required property var model
            strip: pets.parent
            petKey: model.petKey
            leaving: model.leaving
            label: model.label
            host: model.host
            tint: model.colorIndex >= 0 ? pets.parent.petPalette[model.colorIndex] : "transparent"
            chat: pets.parent.chatByKey[model.petKey] ? pets.parent.chatByKey[model.petKey].session : null
            homeX: pets.parent.slotX(model.petKey)
            isMain: pets.parent.hero
            z: pets.parent.hero ? 2 : 0   // the hero walks in front of the headline
            onGone: pets.parent.removePet(model.petKey)
        }
    }

    // More chats than pets: say how many
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: strip.hiddenChats > 0
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Kirigami.Units.smallSpacing
        text: i18nc("more chats than pets", "+%1", strip.hiddenChats)
        opacity: 0.7
        font: Kirigami.Theme.smallFont
        z: 2

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18np("%1 more chat", "%1 more chats", strip.hiddenChats)
            subText: i18n("Up to %1 pets per account, the chats that need you or work first; the list shows them all.", strip.maxPets)
        }
    }

    // ------------------------------------------------------------ shared by the pets

    function say(pet, text) {
        bubbleBox.owner = pet
        bubble.text = text
        bubbleTimer.restart()
    }

    Timer {
        id: bubbleTimer
        interval: 4500
        onTriggered: bubble.text = ""
    }

    // Speech bubble above whoever speaks, or beside him when there's no room above
    Rectangle {
        id: bubbleBox
        property Item owner: null
        readonly property real ownerX: owner ? owner.px : strip.width / 2
        readonly property real headTop: owner ? owner.ground - owner.lift - strip.bodyHeight : strip.height
        readonly property bool roomAbove: headTop - height - Kirigami.Units.smallSpacing >= 0
        readonly property bool rightSide: ownerX + strip.bodyWidth / 2 + width + Kirigami.Units.smallSpacing <= strip.width
        visible: bubble.text !== "" && owner !== null
        z: 3
        width: Math.min(bubble.implicitWidth + Kirigami.Units.largeSpacing, strip.width)
        height: bubble.implicitHeight + Kirigami.Units.smallSpacing
        x: roomAbove ? Math.max(0, Math.min(strip.width - width, ownerX - width / 2))
                     : rightSide ? ownerX + strip.bodyWidth / 2 + Kirigami.Units.smallSpacing
                                 : Math.max(0, ownerX - strip.bodyWidth / 2 - width - Kirigami.Units.smallSpacing)
        y: roomAbove ? headTop - height - Kirigami.Units.smallSpacing : Math.max(0, headTop)
        radius: height / 2
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)

        PlasmaComponents3.Label {
            id: bubble
            textFormat: Text.PlainText   // (chat names in it: as typed)
            anchors.centerIn: parent
            width: Math.min(implicitWidth, strip.width - Kirigami.Units.largeSpacing)
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
        }
    }

    HoverHandler {
        onPointChanged: strip.cursorX = hovered ? point.position.x : -1
        onHoveredChanged: if (!hovered) strip.cursorX = -1
    }

    // Events go to the chat's own pet; the hero takes the ones about everything
    // (and the ones for a chat that has no pet)
    Connections {
        target: root
        function onPetEvent(kind, text, key) {
            let pet = null
            if (strip.hero)
                pet = !key || !(key in root.petColors) ? strip.petFor("") : null
            else if (key)
                pet = strip.petFor(key)
            if (pet)
                pet.event(kind, text)
        }
    }
}
