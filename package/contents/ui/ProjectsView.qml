import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The Projects tab: each project (a chat's git repository, else its folder),
// newest first, folded: its name, when Claude last worked there, a dot for
// each of its open chats, a button for a new chat there. Opened (its lines
// are made then): its open chats now, Claude's last recap of it, its chats
// (a page at a time, as Recent chats), its plans and its memories, each
// line as under an account, with the account it's on when the project is
// on several. Everything of it comes from week.py --projects (main.qml:
// loadProjects), what goes on now from the status. No time or money here:
// the Recap has them, by project. Then each SSH host's (and container's)
// shown, under its name, as read there (main.qml: hostProjects), with its
// open chats from its status: everything on its lines opens and changes it
// there, as in its section of the Chats tab. A plan dragged by its name onto
// another project's card (of the same machine) asks to move it there (the
// card it would go to lights up, and the list scrolls near its top and
// bottom edges); the question shows at the top of that card (MoveAsk.qml),
// and nothing moves without it.
PlasmaComponents3.ScrollView {
    id: view

    readonly property var projects: root.projectsData ? root.projectsData.projects || [] : []
    // the SSH hosts shown whose projects were read (or are being read the first time), in the Chats tab's order
    readonly property var hosts: root.shownHosts.filter(h => !!root.hostProjects[h] || !!root.hostProjectsBusy[h])
    // the cards, one list: this computer's projects, then each host's under its name ({host, project,
    // first: its host's first card, whose name shows above it}; project null: the host has none to show)
    // (a project you hide leaves at once: root.hidingNow)
    readonly property var entries: {
        const out = projects.filter(p => !root.isHiding("projects", "", p.path)).map(p => ({ host: "", project: p, first: false }))
        for (const host of hosts) {
            const rows = ((root.hostProjects[host] || {}).projects || []).filter(p => !root.isHiding("projects", host, p.path))
            if (!rows.length)
                out.push({ host: host, project: null, first: true })
            rows.forEach((p, i) => out.push({ host: host, project: p, first: i === 0 }))
        }
        return out
    }
    // The cards kept by project (KeyedRows.qml): a new read that says the same
    // leaves them as they are, a project that comes or goes makes or drops its
    // card only, and many at once (the tab's first look) come a few a frame
    readonly property KeyedRows cardRows: KeyedRows {}
    function entryKey(e) {
        return e.project ? root.projectKey(e.project.path, e.host) : "empty|" + e.host
    }
    onEntriesChanged: cardRows.sync(entries, entryKey, null)
    Component.onCompleted: cardRows.sync(entries, entryKey, null)
    readonly property real folderWidth: Kirigami.Units.gridUnit * 8
    // a project's buttons, as a row's (HoverButton.qml): 22 px high, 16 px icons, packed close
    readonly property real buttonSize: Math.round(Kirigami.Units.iconSizes.small * 1.375)
    // the accounts on this computer ("") and on each host, as the Chats tab shows them
    function groupsOn(host) {
        return host ? (((root.remote[host] || {}).result || {}).groups || []) : root.groups
    }
    // the chats listed now (open, or kept for the record), by host: not again under Chats
    readonly property var listed: {
        const out = {}
        for (const host of [""].concat(hosts)) {
            const ids = out[host] = {}
            for (const g of groupsOn(host))
                for (const s of g.sessions)
                    for (const id of [s.chatId, s.sessionId, s.jobSessionId])
                        if (id)
                            ids[id] = true
        }
        return out
    }
    contentWidth: availableWidth
    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

    function under(folder, path) {
        return !!folder && !!path && (folder === path || folder.startsWith(path + "/"))
    }
    // What goes on in each project now (the status' open chats; a host's, its own), by its
    // key (root.projectKey): each chat in one project only, the closest one of its machine
    // whose folder holds the chat's (one in ~/repos/app is app's, not also ~/repos's and
    // ~'s when chats once ran there too); a project you hid counts, so its chats show in no other
    // (a project whose open chats say what they said keeps its list, so its card's bindings don't run again)
    readonly property var openMemo: ({})   // (changed in place: no binding hangs on it)
    readonly property var openByProject: {
        const out = {}
        for (const host of [""].concat(hosts)) {
            const read = host ? root.hostProjects[host] || {} : root.projectsData || {}
            const paths = (read.projects || []).map(p => p.path).concat(read.hiddenPaths || [])
            for (const g of groupsOn(host))
                for (const s of g.sessions) {
                    let best = ""
                    for (const p of paths)
                        if (p && p.length > best.length && under(s.cwd, p))
                            best = p
                    if (best) {
                        const key = root.projectKey(best, host)
                        if (!out[key])
                            out[key] = []
                        out[key].push({ key: root.petKeyOf(s, host), session: s, host: host, account: g.title })
                    }
                }
        }
        const seen = c => c.key + "/" + (c.session.rev || JSON.stringify(c.session)) + "/" + c.account
        for (const key in out) {
            const was = openMemo[key]
            if (was && was.length === out[key].length && was.every((c, i) => seen(c) === seen(out[key][i])))
                out[key] = was
        }
        for (const key in openMemo)
            delete openMemo[key]
        Object.assign(openMemo, out)
        return out
    }
    function openChats(project, host) {
        return openByProject[root.projectKey(project.path, host)] || []
    }

    // A plan dragged onto another project (PlanLine.qml's name: dragMoved,
    // dragEnded): {plan, host: its machine's ("": this computer), from: its
    // card's folder}; dropCard, the card under it that would take it (another
    // project of the same machine, not the card of plans whose chat is gone);
    // a drop there asks (root.askMove), anywhere else does nothing
    property var dragged: null
    property point dragScene: Qt.point(0, 0)
    property Item dropCard: null
    readonly property point dragAt: { view.flickY; return dragged ? view.mapFromItem(null, dragScene.x, dragScene.y) : Qt.point(0, 0) }
    readonly property real flickY: view.contentItem ? view.contentItem.contentY : 0
    readonly property real edge: Kirigami.Units.gridUnit * 2   // (this near the top or bottom, the list scrolls)
    readonly property int edgeScroll: !dragged ? 0 : dragAt.y < edge ? -1 : dragAt.y > height - edge ? 1 : 0
    function dragMove(plan, host, from, scenePosition) {
        if (!dragged) {
            root.cancelMove()
            root.deleteAsk = root.noDeleteAsk
        }
        dragged = { plan: plan, host: host, from: from }
        dragScene = scenePosition
        findDropCard()
    }
    function findDropCard() {
        let found = null
        for (let i = 0; dragged && i < cards.count; i++) {
            const c = cards.itemAt(i)
            if (!c || !c.visible)
                continue
            const q = c.mapFromItem(null, dragScene.x, dragScene.y)
            if (q.x >= 0 && q.y >= 0 && q.x < c.width && q.y < c.height) {
                found = c.project.path && c.host === dragged.host && c.project.path !== dragged.from && !c.project.gone ? c : null
                break
            }
        }
        dropCard = found
    }
    function dragEnd() {
        const card = dropCard, d = dragged
        dragged = null
        dropCard = null
        if (card && d)
            root.askMove("drop|" + card.key, d.plan, card.host, card.project.path, false, false)
    }
    Timer {   // (near an edge: the list scrolls, and what's under the plan is looked at again)
        interval: 30
        repeat: true
        running: view.edgeScroll !== 0
        onTriggered: {
            const flick = view.contentItem
            flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height,
                                                  flick.contentY + view.edgeScroll * Kirigami.Units.gridUnit / 2))
            view.findDropCard()
        }
    }
    // The card it would go to, lit up, and the plan by the pointer: over the
    // list, not in it (a second item in the ScrollView would be content too)
    readonly property Item dragLayer: Item {
        parent: view
        anchors.fill: parent
        z: 100
        clip: true
        visible: view.dragged !== null   // (nothing in it takes the mouse: the drag goes on under it)

        Rectangle {
            readonly property rect at: { view.flickY; view.dragAt; return view.dropCard
                ? view.dropCard.mapToItem(view.dragLayer, 0, 0, view.dropCard.width, view.dropCard.height) : Qt.rect(0, 0, 0, 0) }
            visible: view.dropCard !== null
            x: at.x - Kirigami.Units.smallSpacing / 2
            y: at.y - Kirigami.Units.smallSpacing / 2
            width: at.width + Kirigami.Units.smallSpacing
            height: at.height + Kirigami.Units.smallSpacing
            radius: Kirigami.Units.smallSpacing
            color: Qt.rgba(Kirigami.Theme.focusColor.r, Kirigami.Theme.focusColor.g, Kirigami.Theme.focusColor.b, 0.15)   // (the accent: highlightColor is a pale tint in a popup)
            border.color: Kirigami.Theme.focusColor
            border.width: 1
        }
        Rectangle {
            x: Math.min(view.dragAt.x + Kirigami.Units.largeSpacing, view.width - width)
            y: view.dragAt.y + Kirigami.Units.largeSpacing
            width: Math.min(ghost.implicitWidth + 2 * Kirigami.Units.smallSpacing, view.width * 0.7)
            height: ghost.implicitHeight + Kirigami.Units.smallSpacing
            radius: Kirigami.Units.smallSpacing
            // (as a tooltip: its text and background always go together)
            Kirigami.Theme.colorSet: Kirigami.Theme.Tooltip
            Kirigami.Theme.inherit: false
            color: Kirigami.Theme.backgroundColor
            border.color: Kirigami.Theme.focusColor
            opacity: 0.9

            RowLayout {
                id: ghost
                anchors.fill: parent
                anchors.leftMargin: Kirigami.Units.smallSpacing
                anchors.rightMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Icon {
                    source: Icons.plasma.plan
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Layout.preferredWidth
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: view.dragged ? view.dragged.plan.title : ""
                    elide: Text.ElideRight
                }
            }
        }
    }

    // A project opened from the Recap, scrolled to the top of the view
    property Item scrollTarget: null
    Timer {
        id: scroller
        interval: 100
        onTriggered: {
            if (!view.scrollTarget)
                return
            const flick = view.contentItem
            flick.contentY = Math.max(0, Math.min(view.scrollTarget.y, flick.contentHeight - flick.height))
            view.scrollTarget = null
        }
    }

    // the title of an opened project's active chats, chats, plans, memories: the text's size, bold
    // and dimmed (small, they were hard to spot among the lines)
    component SubTitle: PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        font.weight: Font.DemiBold
        opacity: 0.75
        elide: Text.ElideRight
    }

    ColumnLayout {
        id: list
        width: view.availableWidth
        spacing: Kirigami.Units.largeSpacing

        ListPalette {   // (its lines' colors: RecentLine, PlanLine, MemoryLine)
            id: listColors
        }

        // (read the first time: as the Recap's and the Permissions tab's)
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            visible: root.projectsBusy && view.projects.length === 0
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
                text: i18n("Reading your chats by project…")
                opacity: 0.8
            }
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            visible: root.projectsError !== ""
            text: root.projectsError
            color: Kirigami.Theme.negativeTextColor
            wrapMode: Text.Wrap
        }
        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.gridUnit
            visible: !root.projectsBusy && root.projectsData !== null && view.entries.length === 0
            iconName: Icons.plasma.project
            text: i18n("No projects yet")
            explanation: i18n("A project is a folder (or the git repository it's in) where you chatted with Claude.")
        }

        Repeater {
            id: cards
            model: view.cardRows.model
            delegate: ColumnLayout {
                id: card
                required property int index
                // (its project's key: root.projectKey; "empty|<host>" for a host with none to show)
                required property string key
                required property string rev
                readonly property var entry: { rev; return view.cardRows.item(key) || ({ host: "", project: null, first: false }) }
                readonly property string host: entry.host   // ("": this computer's)
                // (a host with no projects to show: only its name, and why)
                readonly property bool empty: entry.project === null
                readonly property var project: entry.project
                                               || ({ name: "", path: "", short: "", gone: false, lastAt: 0, accounts: [], chats: [],
                                                     chatCount: 0, plans: [], memories: [], recap: null })
                // (a plan whose chat is gone: its folder isn't known)
                readonly property bool unfiled: project.path === ""
                readonly property bool unfolded: !empty && !!root.openProjects[key]
                readonly property var here: unfiled || empty ? [] : view.openChats(project, host)
                // its buttons (new chat here, hide): on hover, while the keyboard is on its line
                // (Tab), or after a press and hold with a finger (TouchHold.qml)
                readonly property bool buttonsShown: cardHover.hovered || projectName.activeFocus
                                                     || (headButtons.item !== null && headButtons.item.focused) || held
                property bool made: false   // (its buttons, once they first showed: kept)
                onButtonsShownChanged: if (buttonsShown) made = true
                property bool held: false
                property bool holding: false
                Connections {
                    target: root
                    enabled: card.held
                    function onDashboardShownChanged() {
                        card.held = false
                    }
                }
                function fold() {
                    root.toggleProject(key, unfolded)
                }
                // (opened from the Recap: brought into view, once the list is laid out)
                function bringUp() {
                    if (root.projectToShow !== "" && !empty && root.projectToShow === key) {
                        root.projectToShow = ""
                        view.scrollTarget = card
                        scroller.restart()
                    }
                }
                Component.onCompleted: bringUp()
                Connections {
                    target: root
                    function onProjectToShowChanged() {
                        card.bringUp()
                    }
                }
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.smallSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Separator {
                    Layout.fillWidth: true
                    visible: card.index > 0 && !(card.host && card.entry.first)
                }
                // A host's name above its first card (made only there): as its section's in the Chats tab,
                // with what was read there: still reading, why it couldn't, or that it has none
                Loader {
                    active: card.host !== "" && card.entry.first
                    visible: active
                    Layout.fillWidth: true
                    sourceComponent: ColumnLayout {
                        id: hostHead
                        readonly property var read: root.hostProjects[card.host] || null
                        readonly property bool busy: !!root.hostProjectsBusy[card.host]
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Separator {
                            Layout.fillWidth: true
                            Layout.topMargin: card.index > 0 ? Kirigami.Units.gridUnit : 0
                            Layout.bottomMargin: Kirigami.Units.smallSpacing
                            visible: card.index > 0
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                source: root.hostIcon(card.host)
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                            }
                            Kirigami.Heading {
                                textFormat: Text.PlainText
                                level: 1   // (above its projects' names)
                                font.weight: Font.Bold
                                text: root.hostLabel(card.host)
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            PlasmaComponents3.BusyIndicator {
                                visible: hostHead.busy
                                running: visible
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                            }
                            // what you hid there (its projects too): a menu to show a kind again, as in its section
                            PlasmaComponents3.ToolButton {
                                id: hostHidden
                                readonly property var kinds: root.hiddenKinds.filter(k => root.hiddenCount(k, card.host) > 0)
                                icon.name: Icons.plasma.showHidden
                                visible: kinds.length > 0
                                display: PlasmaComponents3.AbstractButton.IconOnly
                                text: i18n("Show hidden ones again…")
                                onClicked: root.openHiddenMenu(hostHidden, card.host)
                                PlasmaCore.ToolTipArea {
                                    textFormat: Text.PlainText
                                    anchors.fill: parent
                                    mainText: i18n("Show hidden ones again")
                                    subText: hostHidden.kinds.map(k => root.showHiddenText(k, root.hiddenCount(k, card.host))).join("\n")
                                }
                            }
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: hostHead.read && !hostHead.read.ok
                                  ? i18n("Couldn't read the projects on %1: %2", root.hostLabel(card.host), hostHead.read.error)
                                  : !card.empty ? ""
                                  : hostHead.read ? i18n("No projects on %1 yet", root.hostLabel(card.host))
                                  : i18n("Reading the chats on %1 by project…", root.hostLabel(card.host))
                            color: hostHead.read && !hostHead.read.ok ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                            opacity: hostHead.read && !hostHead.read.ok ? 1 : 0.65
                            wrapMode: Text.Wrap
                        }
                    }
                }
                RowLayout {
                    id: head
                    Layout.fillWidth: true
                    visible: !card.empty
                    spacing: Kirigami.Units.smallSpacing

                    HoverHandler {
                        id: cardHover
                    }
                    TouchHold {
                        buttons: card
                    }
                    Kirigami.Icon {
                        source: card.unfolded ? Icons.plasma.unfolded : Icons.plasma.folded
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Layout.preferredWidth
                        // (on the name's line)
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: Math.max(0, (projectName.implicitHeight - Layout.preferredHeight) / 2)

                        // the line shaded while the pointer is on it, as a chat's row (in the
                        // line's first item, under it: in the line, it would take its spacing)
                        HoverShade {
                            z: -1
                            target: head
                            shown: cardHover.hovered
                            side: Kirigami.Units.smallSpacing
                            pad: Kirigami.Units.smallSpacing / 2
                        }
                    }
                    // Its name, with a dot for each of its open chats at the top right; under it its folder and
                    // when Claude last worked there, a line as high as a row's buttons, whose end they cover on
                    // hover: the dots stay in sight, and nothing moves
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            // (big and bold: a project is spotted among the lines of the one opened above it)
                            Kirigami.Heading {
                                id: projectName
                                level: 2
                                type: Kirigami.Heading.Type.Primary
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: card.unfiled ? i18n("Plans whose chat is gone") : card.project.name
                                elide: Text.ElideRight
                                // (Tab: its hide button shows; Enter: folds it open or shut, as a click)
                                activeFocusOnTab: true
                                font.underline: activeFocus
                                Keys.onReturnPressed: card.fold()
                                Keys.onEnterPressed: card.fold()
                            }
                            // a dot for each of its open chats, in its state's color (made only for a project that has some);
                            // its tooltip over the dots, not one of them: in the Row, sized by the Row, it grew the Row
                            // it was sized by, a polish loop that left the whole tab unlaid out
                            Loader {
                                active: card.here.length > 0
                                visible: active
                                Layout.alignment: Qt.AlignVCenter
                                sourceComponent: Item {
                                    implicitWidth: dots.implicitWidth
                                    implicitHeight: dots.implicitHeight
                                    Row {
                                        id: dots
                                        spacing: Kirigami.Units.smallSpacing / 2
                                        Repeater {
                                            model: card.here.length
                                            delegate: Rectangle {
                                                required property int index
                                                width: Kirigami.Units.smallSpacing * 2
                                                height: width
                                                radius: width / 2
                                                // (as its row's dot: red for a chat that failed or that a usage limit stopped)
                                                color: card.here[index] ? root.rowColor(card.here[index].session) : root.stateColor("idle")
                                            }
                                        }
                                    }
                                    PlasmaCore.ToolTipArea {
                                        textFormat: Text.PlainText
                                        anchors.fill: parent
                                        mainText: i18np("%1 open chat", "%1 open chats", card.here.length)
                                        subText: !containsMouse ? "" : card.here.map(c => c.session.name + ": " + root.stateText(c.session)).join("\n")
                                    }
                                }
                            }
                        }
                        Item {
                            id: metaLine
                            Layout.fillWidth: true
                            implicitHeight: Math.max(projectMeta.implicitHeight, card.unfiled ? 0 : view.buttonSize)
                            // (cut where the buttons start while they show)
                            Item {
                                width: parent.width - (card.buttonsShown && headButtons.item ? headButtons.width + Kirigami.Units.smallSpacing : 0)
                                height: parent.height
                                clip: true
                                PlasmaComponents3.Label {
                                    id: projectMeta
                                    width: metaLine.width
                                    anchors.verticalCenter: parent.verticalCenter
                                    textFormat: Text.PlainText
                                    text: card.unfiled ? i18n("Their folder isn't known any more")
                                          : (card.project.gone ? i18n("%1 (not there any more)", card.project.short) : card.project.short)
                                            + " · " + i18n("last at work %1 ago", root.duration(Math.max(60000, root.minuteNow - card.project.lastAt)))
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.65
                                    elide: Text.ElideMiddle
                                }
                            }
                            // on hover, as a line's buttons (or Tab, or a finger's hold): a new chat here, and hide it
                            // here (nothing is deleted; its chats, plans and memories stay in their lists); made the
                            // first time they show
                            Loader {
                                id: headButtons
                                active: !card.unfiled && card.made
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                sourceComponent: RowLayout {
                                    readonly property bool focused: newHere.visualFocus || hideHere.visualFocus
                                    spacing: 0
                                    opacity: card.buttonsShown ? 1 : 0
                                    enabled: card.buttonsShown

                                    HoverButton {
                                        id: newHere
                                        icon.source: root.iconDir + Icons.plasma.newChat   // (as an account's: at 16 px)
                                        text: i18n("New chat here")
                                        onClicked: root.newChatInProject(card.project, card.host)

                                        PlasmaCore.ToolTipArea {
                                            textFormat: Text.PlainText
                                            anchors.fill: parent
                                            mainText: i18n("New chat here")
                                            subText: (card.host ? root.hostLabel(card.host) + ":" : "") + card.project.short
                                        }
                                    }
                                    HoverButton {
                                        id: hideHere
                                        icon.name: Icons.plasma.hide
                                        text: i18n("Hide this project")
                                        onClicked: root.hideItem("projects", card.project.path, card.host)

                                        PlasmaCore.ToolTipArea {
                                            textFormat: Text.PlainText
                                            anchors.fill: parent
                                            mainText: i18n("Hide this project")
                                            subText: root.hideHint("projects", card.host)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    TapHandler {
                        onTapped: card.fold()
                    }
                }

                // A plan dropped on it: may it move here? (made only then)
                MoveAsk {
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                    itemKey: card.unfiled || card.empty ? "" : "drop|" + card.key
                }
                // Opened: what's in it (made only then)
                Loader {
                    active: card.unfolded
                    visible: active
                    Layout.fillWidth: true
                    sourceComponent: ColumnLayout {
                        id: inside
                        readonly property var project: card.project
                        readonly property bool tagged: (project.accounts || []).length > 1
                        readonly property var chats: (project.chats || []).filter(c => !(view.listed[card.host] || {})[c.sessionId])
                        readonly property string pageKey: "project|" + card.key
                        readonly property int chatsShown: Math.min(chats.length, root.pageSize * root.pagesShown(pageKey))
                        // (one you hide leaves at once: root.hidingNow)
                        readonly property var plans: (project.plans || []).filter(p => !root.isHiding("plans", card.host, p.slug))
                        readonly property int plansShown: Math.min(plans.length, root.pageSize * root.pagesShown(pageKey + "|plans"))
                        readonly property var memories: (project.memories || []).filter(m => !root.isHiding("memories", card.host, m.key))
                        readonly property int memoriesShown: Math.min(memories.length, root.pageSize * root.pagesShown(pageKey + "|memories"))
                        // its titles on the name's line, and each title's lines (with their Show N more) a little
                        // further in, under it: the groups are seen at a glance
                        readonly property real titleIndent: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                        readonly property real lineIndent: titleIndent + Kirigami.Units.largeSpacing + Kirigami.Units.smallSpacing
                        // the lines' folder column (one for its chats, plans and memories, so their
                        // times line up), only when a line that shows is in a folder below the
                        // project's: empty on every line, it took room their names were cut short for
                        readonly property real folderWidth: {
                            const p = project.path
                            const below = chats.slice(0, chatsShown).some(c => root.folderIn(c.cwd, p, c.cwdShort || "~") !== "")
                                          || plans.slice(0, plansShown).some(x => root.folderIn(x.cwd, p, x.cwdShort || "") !== "")
                                          || memories.slice(0, memoriesShown).some(m => m.type === "account" || root.folderIn(m.folder, p, m.folderShort || "") !== "")
                            return below ? view.folderWidth : 0
                        }
                        spacing: Kirigami.Units.smallSpacing

                        // What goes on there now
                        SubTitle {
                            visible: card.here.length > 0
                            Layout.leftMargin: inside.titleIndent
                            text: i18n("Active chats (%1)", card.here.length)
                        }
                        Repeater {
                            model: card.here.length
                            delegate: FocusLine {
                                required property int index
                                Layout.fillWidth: true
                                Layout.leftMargin: inside.lineIndent
                                item: card.here[index] || null
                            }
                        }
                        // Claude's last recap of it (its own, in the chat)
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            Layout.leftMargin: inside.titleIndent
                            visible: !!inside.project.recap && !!inside.project.recap.text
                            text: visible ? "“" + inside.project.recap.text + "”" : ""
                            font.italic: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 4
                            elide: Text.ElideRight
                            opacity: 0.8
                        }

                        // Its chats, newest first, a page at a time
                        SubTitle {
                            visible: inside.chats.length > 0
                            Layout.leftMargin: inside.titleIndent
                            text: inside.chatsShown < inside.chats.length
                                  ? i18nc("a project's chats: how many show, of how many", "Chats (%1 of %2)", inside.chatsShown, inside.chats.length)
                                  : i18n("Chats (%1)", inside.chats.length)
                        }
                        Repeater {
                            model: PageRows { size: inside.chatsShown }
                            delegate: RecentLine {
                                required property int index
                                colors: listColors
                                Layout.leftMargin: inside.lineIndent
                                chat: inside.chats[index] || root.emptyRecent
                                group: root.groupOfProfile(chat.profileDir, card.host)
                                remoteHost: card.host
                                accountTag: inside.tagged ? chat.account || "" : ""
                                project: inside.project.path
                                folderWidth: inside.folderWidth
                            }
                        }
                        MoreButton {
                            Layout.leftMargin: inside.lineIndent
                            open: true
                            listKey: inside.pageKey
                            shown: inside.chatsShown
                            count: inside.chats.length
                        }

                        // Its plans and its memories, newest first, a page at a time too
                        // (made once its chats show, a frame later: the project opens at once)
                        Loader {
                            id: rest
                            property bool due: false
                            Connections {
                                target: rest.Window.window
                                enabled: !rest.due
                                function onFrameSwapped() {
                                    restTimer.start()   // (not in the frame's own signal: after it)
                                }
                            }
                            Timer {
                                id: restTimer
                                interval: 0
                                onTriggered: rest.due = true
                            }
                            active: due
                            visible: active
                            Layout.fillWidth: true
                            sourceComponent: ColumnLayout {
                                spacing: Kirigami.Units.smallSpacing

                                SubTitle {
                                    visible: inside.plans.length > 0
                                    Layout.leftMargin: inside.titleIndent
                                    text: inside.plansShown < inside.plans.length
                                          ? i18nc("a project's plans: how many show, of how many", "Plans (%1 of %2)", inside.plansShown, inside.plans.length)
                                          : i18n("Plans (%1)", inside.plans.length)
                                }
                                Repeater {
                                    model: PageRows { size: inside.plansShown }
                                    delegate: PlanLine {
                                        required property int index
                                        colors: listColors
                                        Layout.leftMargin: inside.lineIndent
                                        plan: inside.plans[index] || root.emptyPlan
                                        group: root.groupOfProfile(plan.profileDir, card.host)
                                        remoteHost: card.host
                                        accountTag: inside.tagged ? plan.account || "" : ""
                                        project: inside.project.path
                                        chatGoneCard: inside.project.path === ""
                                        draggable: true
                                        onDragMoved: at => view.dragMove(plan, card.host, inside.project.path, at)
                                        onDragEnded: view.dragEnd()
                                        folderWidth: inside.folderWidth
                                    }
                                }
                                MoreButton {
                                    Layout.leftMargin: inside.lineIndent
                                    open: true
                                    listKey: inside.pageKey + "|plans"
                                    shown: inside.plansShown
                                    count: inside.plans.length
                                }
                                SubTitle {
                                    visible: inside.memories.length > 0
                                    Layout.leftMargin: inside.titleIndent
                                    text: inside.memoriesShown < inside.memories.length
                                          ? i18nc("a project's memories: how many show, of how many", "Memories (%1 of %2)", inside.memoriesShown, inside.memories.length)
                                          : i18n("Memories (%1)", inside.memories.length)
                                }
                                Repeater {
                                    model: PageRows { size: inside.memoriesShown }
                                    delegate: MemoryLine {
                                        required property int index
                                        colors: listColors
                                        Layout.leftMargin: inside.lineIndent
                                        memory: inside.memories[index] || root.emptyMemory
                                        remoteHost: card.host
                                        accountTag: inside.tagged ? memory.account || "" : ""
                                        project: inside.project.path
                                        folderWidth: inside.folderWidth
                                    }
                                }
                                MoreButton {
                                    Layout.leftMargin: inside.lineIndent
                                    open: true
                                    listKey: inside.pageKey + "|memories"
                                    shown: inside.memoriesShown
                                    count: inside.memories.length
                                }
                            }
                        }
                    }
                }
            }
        }

        Item {
            implicitHeight: Kirigami.Units.smallSpacing
        }
    }
}
