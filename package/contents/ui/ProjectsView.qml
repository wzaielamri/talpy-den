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
// the Recap has them, by project.
PlasmaComponents3.ScrollView {
    id: view

    readonly property var projects: root.projectsData ? root.projectsData.projects || [] : []
    readonly property real folderWidth: Kirigami.Units.gridUnit * 8
    // a project's buttons, as a row's (HoverButtons.qml): 22 px high, 16 px icons, packed close
    readonly property real buttonSize: Math.round(Kirigami.Units.iconSizes.small * 1.375)
    readonly property real buttonWidth: Kirigami.Units.iconSizes.small + 4
    // the chats listed now (open, or kept for the record): not again under Chats
    readonly property var listed: {
        const ids = {}
        for (const g of root.groups)
            for (const s of g.sessions)
                for (const id of [s.chatId, s.sessionId, s.jobSessionId])
                    if (id)
                        ids[id] = true
        return ids
    }
    contentWidth: availableWidth
    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

    function under(folder, path) {
        return !!folder && !!path && (folder === path || folder.startsWith(path + "/"))
    }
    // What goes on in each project now (the status' open chats), by its path: each
    // chat in one project only, the closest one whose folder holds the chat's (one
    // in ~/repos/app is app's, not also ~/repos's and ~'s when chats once ran
    // there too); a project you hid counts, so its chats show in no other
    readonly property var openByProject: {
        const paths = projects.map(p => p.path).concat((root.projectsData && root.projectsData.hiddenPaths) || [])
        const out = {}
        for (const g of root.groups)
            for (const s of g.sessions) {
                let best = ""
                for (const p of paths)
                    if (p && p.length > best.length && under(s.cwd, p))
                        best = p
                if (best)
                    (out[best] = out[best] || []).push({ key: root.petKeyOf(s, ""), session: s, host: "", account: g.title })
            }
        return out
    }
    function openChats(project) {
        return openByProject[project.path] || []
    }
    function isOpen(project) {
        return !!root.openProjects[project.path]
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

    // the title of an opened project's chats, plans, memories: small, as the folds of an account's lists
    component SubTitle: PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        font.weight: Font.DemiBold
        opacity: 0.75
        elide: Text.ElideRight
    }

    ColumnLayout {
        id: list
        width: view.availableWidth
        spacing: Kirigami.Units.largeSpacing

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
            visible: !root.projectsBusy && root.projectsData !== null && view.projects.length === 0
            iconName: Icons.plasma.project
            text: i18n("No projects yet")
            explanation: i18n("A project is a folder (or the git repository it's in) where you chatted with Claude.")
        }

        Repeater {
            model: view.projects.length
            delegate: ColumnLayout {
                id: card
                required property int index
                readonly property var project: view.projects[index]
                                               || ({ name: "", path: "", short: "", gone: false, lastAt: 0, accounts: [], chats: [],
                                                     chatCount: 0, plans: [], memories: [], recap: null })
                // (a plan whose chat is gone: its folder isn't known)
                readonly property bool unfiled: project.path === ""
                readonly property bool unfolded: view.isOpen(project)
                readonly property var here: unfiled ? [] : view.openChats(project)
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
                    root.toggleProject(project.path, unfolded)
                }
                // (opened from the Recap: brought into view, once the list is laid out)
                function bringUp() {
                    if (root.projectToShow !== "" && root.projectToShow === project.path) {
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
                    visible: card.index > 0
                }
                RowLayout {
                    Layout.fillWidth: true
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
                            Kirigami.Heading {
                                id: projectName
                                level: 4
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
                                        subText: card.here.map(c => c.session.name + ": " + root.stateText(c.session)).join("\n")
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
                                            + " · " + i18n("last at work %1 ago", root.duration(Math.max(60000, root.now - card.project.lastAt)))
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

                                    PlasmaComponents3.ToolButton {
                                        id: newHere
                                        Layout.preferredWidth: view.buttonWidth
                                        Layout.preferredHeight: view.buttonSize
                                        icon.source: root.iconDir + Icons.plasma.newChat   // (as an account's: at 16 px)
                                        icon.width: Kirigami.Units.iconSizes.small
                                        icon.height: Kirigami.Units.iconSizes.small
                                        display: PlasmaComponents3.AbstractButton.IconOnly
                                        text: i18n("New chat here")
                                        onClicked: root.newChatInProject(card.project)

                                        PlasmaCore.ToolTipArea {
                                            textFormat: Text.PlainText
                                            anchors.fill: parent
                                            mainText: i18n("New chat here")
                                            subText: card.project.short
                                        }
                                    }
                                    PlasmaComponents3.ToolButton {
                                        id: hideHere
                                        Layout.preferredWidth: view.buttonWidth
                                        Layout.preferredHeight: view.buttonSize
                                        icon.name: Icons.plasma.hide
                                        icon.width: Kirigami.Units.iconSizes.small
                                        icon.height: Kirigami.Units.iconSizes.small
                                        display: PlasmaComponents3.AbstractButton.IconOnly
                                        text: i18n("Hide this project")
                                        onClicked: root.hideItem("projects", card.project.path, "")

                                        PlasmaCore.ToolTipArea {
                                            textFormat: Text.PlainText
                                            anchors.fill: parent
                                            mainText: i18n("Hide this project")
                                            subText: root.hideHint("projects", "")
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

                // Opened: what's in it (made only then)
                Loader {
                    active: card.unfolded
                    visible: active
                    Layout.fillWidth: true
                    sourceComponent: ColumnLayout {
                        id: inside
                        readonly property var project: card.project
                        readonly property bool tagged: (project.accounts || []).length > 1
                        readonly property var chats: (project.chats || []).filter(c => !view.listed[c.sessionId])
                        readonly property string pageKey: "project|" + project.path
                        readonly property int chatsShown: Math.min(chats.length, root.pageSize * root.pagesShown(pageKey))
                        readonly property var plans: project.plans || []
                        readonly property int plansShown: Math.min(plans.length, root.pageSize * root.pagesShown(pageKey + "|plans"))
                        readonly property var memories: project.memories || []
                        readonly property int memoriesShown: Math.min(memories.length, root.pageSize * root.pagesShown(pageKey + "|memories"))
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
                        Repeater {
                            model: card.here.length
                            delegate: FocusLine {
                                required property int index
                                Layout.fillWidth: true
                                item: card.here[index] || null
                            }
                        }
                        // Claude's last recap of it (its own, in the chat)
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
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
                            Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            text: inside.chatsShown < inside.chats.length
                                  ? i18nc("a project's chats: how many show, of how many", "Chats (%1 of %2)", inside.chatsShown, inside.chats.length)
                                  : i18n("Chats (%1)", inside.chats.length)
                        }
                        Repeater {
                            model: PageRows { size: inside.chatsShown }
                            delegate: RecentLine {
                                required property int index
                                Layout.leftMargin: Kirigami.Units.gridUnit
                                chat: inside.chats[index] || root.emptyRecent
                                group: root.groupOfProfile(chat.profileDir)
                                accountTag: inside.tagged ? chat.account || "" : ""
                                project: inside.project.path
                                folderWidth: inside.folderWidth
                            }
                        }
                        MoreButton {
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
                                    Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                                    text: inside.plansShown < inside.plans.length
                                          ? i18nc("a project's plans: how many show, of how many", "Plans (%1 of %2)", inside.plansShown, inside.plans.length)
                                          : i18n("Plans (%1)", inside.plans.length)
                                }
                                Repeater {
                                    model: PageRows { size: inside.plansShown }
                                    delegate: PlanLine {
                                        required property int index
                                        Layout.leftMargin: Kirigami.Units.gridUnit
                                        plan: inside.plans[index] || root.emptyPlan
                                        group: root.groupOfProfile(plan.profileDir)
                                        accountTag: inside.tagged ? plan.account || "" : ""
                                        project: inside.project.path
                                        folderWidth: inside.folderWidth
                                    }
                                }
                                MoreButton {
                                    open: true
                                    listKey: inside.pageKey + "|plans"
                                    shown: inside.plansShown
                                    count: inside.plans.length
                                }
                                SubTitle {
                                    visible: inside.memories.length > 0
                                    Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                                    text: inside.memoriesShown < inside.memories.length
                                          ? i18nc("a project's memories: how many show, of how many", "Memories (%1 of %2)", inside.memoriesShown, inside.memories.length)
                                          : i18n("Memories (%1)", inside.memories.length)
                                }
                                Repeater {
                                    model: PageRows { size: inside.memoriesShown }
                                    delegate: MemoryLine {
                                        required property int index
                                        Layout.leftMargin: Kirigami.Units.gridUnit
                                        memory: inside.memories[index] || root.emptyMemory
                                        accountTag: inside.tagged ? memory.account || "" : ""
                                        project: inside.project.path
                                        folderWidth: inside.folderWidth
                                    }
                                }
                                MoreButton {
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
