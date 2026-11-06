import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "markdown.mjs" as Md
import "icons.mjs" as Icons

// What Claude made, in Talpy Chat (pane.py made.py; VS Code MadeLine.tsx: the same words and rules):
// a line under the step that made it or the reply that names it, on both tabs, folded: "icon.svg ·
// 2 KB". Unfolded: a picture at the window's width (never wider than it is), a plan rendered, a
// page never drawn here (Open in browser, Show source), another file Open. A file of its own, read
// and made only for such a line (ChatPane.qml's madeItem); what it shows is asked for only once
// it's unfolded, again at each unfold (pane.madeAsk: pane.py --made, off this thread; a picture
// is a file Qt's image reader loads asynchronously, scaled down: this computer's once pane.py
// says it's a plain file, what Claude saw or an SSH host's a copy here)
ColumnLayout {
    id: madeBox
    spacing: 0

    required property Item row   // (its row in the list: key, text and, as JSON in input, what was made: pane.py made.py)
    readonly property var m: row.input ? JSON.parse(row.input) : ({ path: "", type: "file", name: "", size: null })
    readonly property bool unfolded: pane.openTools[row.key] === true
    readonly property bool local: pane.host === ""
    readonly property bool canOpen: local && !m.gone
    // what it asks pane.py for, unfolded (none for a file gone, a PDF, or a page whose source isn't shown)
    readonly property bool wanted: unfolded && !m.gone && m.type !== "file" && (m.type !== "page" || source)
    readonly property var shown: pane.madeShown[row.key] || null
    property bool source: false   // (a page: its source shown)

    onWantedChanged: if (wanted) pane.madeAsk(row.key, m.path, m.step || "", m.type === "picture")
    Component.onCompleted: if (wanted) pane.madeAsk(row.key, m.path, m.step || "", m.type === "picture")

    // "2 KB" (VS Code shared/pane.ts madeSize: the same rule)
    function sizeText(bytes) {
        if (bytes === null || bytes === undefined || bytes < 0)
            return ""
        if (bytes < 1024)
            return i18n("%1 B", bytes)
        if (bytes < 1024 * 1024)
            return i18n("%1 KB", Math.max(1, Math.round(bytes / 1024)))
        return i18n("%1 MB", (bytes / 1024 / 1024).toFixed(1))
    }
    function open(file) {
        Qt.openUrlExternally("file://" + encodeURI(file))
    }

    // The line: ▸ an icon of what it is, its name and size
    Rectangle {
        Layout.leftMargin: pane.gutter - Kirigami.Units.smallSpacing
        Layout.maximumWidth: madeBox.width - Layout.leftMargin
        implicitWidth: lineRow.implicitWidth + Kirigami.Units.smallSpacing * 2
        implicitHeight: lineRow.implicitHeight + 2
        radius: Kirigami.Units.cornerRadius
        color: lineHover.hovered ? pane.mix(pane.textColor, 0.06) : "transparent"

        RowLayout {
            id: lineRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: Kirigami.Units.smallSpacing / 2
            anchors.verticalCenter: parent.verticalCenter
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: madeBox.unfolded ? Icons.plasma.unfolded : Icons.plasma.folded
                Layout.preferredWidth: Math.round(fm.height * 0.7)
                Layout.preferredHeight: Layout.preferredWidth
                color: pane.mutedColor
            }
            Kirigami.Icon {
                readonly property string meaning: ({ picture: Icons.plasma.madePicture, plan: Icons.plasma.plan, page: Icons.plasma.madePage })[madeBox.m.type]
                                                  || Icons.plasma.madeFile
                source: meaning
                Layout.preferredWidth: Math.round(fm.height * 0.85)
                Layout.preferredHeight: Layout.preferredWidth
                color: pane.mutedColor
            }
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: [row.text || madeBox.m.name, madeBox.m.gone ? i18n("not there any more") : madeBox.sizeText(madeBox.m.size)]
                      .filter(s => !!s).join(" · ")
                elide: Text.ElideMiddle
                color: lineHover.hovered ? pane.textColor : pane.mix(pane.textColor, 0.85)
                font.family: pane.chatFamily
                font.pointSize: pane.pt * 0.92
            }
        }
        HoverHandler {
            id: lineHover
            cursorShape: Qt.PointingHandCursor
        }
        TapHandler {
            onTapped: {
                const next = Object.assign({}, pane.openTools)
                next[row.key] = !madeBox.unfolded
                pane.openTools = next
            }
        }
        PlasmaComponents3.ToolTip.text: madeBox.m.path + "\n" + (madeBox.m.gone ? i18n("It isn't there any more")
                                                                 : madeBox.unfolded ? i18n("Fold it") : i18n("Click to see it"))
        PlasmaComponents3.ToolTip.visible: lineHover.hovered
        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
    }

    // Unfolded: made only then
    Loader {
        active: madeBox.unfolded
        visible: active
        Layout.fillWidth: true
        Layout.leftMargin: pane.gutter + Kirigami.Units.gridUnit
        Layout.topMargin: active ? Kirigami.Units.smallSpacing / 2 : 0
        sourceComponent: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            // A picture: at the window's width at most (as it is, when smaller), and at most most of its height.
            // Read once at a size of its own (decode: the screen's width at most), never again as the window
            // changes: shown smaller than that, it's only drawn smaller
            Item {
                id: picBox
                readonly property string file: madeBox.m.type === "picture" && madeBox.shown && madeBox.shown.ok && madeBox.shown.file
                                                ? madeBox.shown.file : ""
                readonly property real most: Math.max(Kirigami.Units.gridUnit * 6, pane.height * 0.6)
                readonly property int decode: Math.round(Math.min(1600, Screen.width || 1600) * Screen.devicePixelRatio)
                readonly property real k: pic.implicitWidth > 0 && pic.implicitHeight > 0
                                          ? Math.min(1, width / pic.implicitWidth, most / pic.implicitHeight) : 0
                visible: file !== ""
                Layout.fillWidth: true
                implicitHeight: pic.status === Image.Ready ? Math.round(pic.implicitHeight * k) + 2 : (file ? Kirigami.Units.gridUnit * 2 : 0)

                Rectangle {
                    width: pic.width + 2
                    height: pic.height + 2
                    color: pane.mdStyle.blockBg
                    border.width: 1
                    border.color: pane.borderColor
                    radius: 2
                    visible: pic.status === Image.Ready
                }
                Image {
                    id: pic
                    x: 1
                    y: 1
                    width: Math.round(implicitWidth * picBox.k)
                    height: Math.round(implicitHeight * picBox.k)
                    source: picBox.file ? "file://" + encodeURI(picBox.file) : ""
                    // (a raster picture: scaled down to fit decode × decode, never up; an SVG drawn decode wide)
                    sourceSize.width: picBox.decode
                    sourceSize.height: /\.svg$/i.test(picBox.file) ? 0 : picBox.decode
                    fillMode: Image.Stretch   // (width and height keep its shape)
                    asynchronous: true
                    cache: false   // (again at each unfold: the file as it is now)
                    smooth: true
                }
                PlasmaComponents3.Label {
                    visible: pic.status === Image.Error
                    textFormat: Text.PlainText
                    text: i18n("It couldn't be shown")
                    color: pane.mutedColor
                    font.pointSize: pane.pt * 0.92
                }
                MouseArea {   // (a click: big, BigPicture.qml)
                    anchors.fill: pic
                    cursorShape: Qt.PointingHandCursor
                    onClicked: pane.bigPicture = picBox.file
                }
            }
            // A plan, rendered; a page's source, as text (at most most of the window's height, scrolling)
            Loader {
                readonly property bool texts: !!madeBox.shown && madeBox.shown.ok && typeof madeBox.shown.text === "string"
                                              && (madeBox.m.type === "plan" || (madeBox.m.type === "page" && madeBox.source))
                active: texts
                visible: active
                Layout.fillWidth: true
                Layout.preferredHeight: item ? Math.min(item.textHeight + 2, Math.max(Kirigami.Units.gridUnit * 8, pane.height * 0.55)) : 0
                sourceComponent: PlasmaComponents3.ScrollView {
                    id: textScroll
                    readonly property real textHeight: madeText.implicitHeight + Kirigami.Units.largeSpacing * 1.5
                    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff
                    background: Rectangle {
                        color: pane.mdStyle.blockBg
                        border.width: 1
                        border.color: pane.borderColor
                        radius: Kirigami.Units.cornerRadius
                    }
                    TextEdit {
                        id: madeText
                        width: textScroll.availableWidth
                        leftPadding: Kirigami.Units.largeSpacing
                        rightPadding: Kirigami.Units.largeSpacing
                        topPadding: Kirigami.Units.largeSpacing * 0.75
                        bottomPadding: Kirigami.Units.largeSpacing * 0.75
                        readonly property string said: madeBox.shown.text + (madeBox.shown.cut ? "\n…" : "")
                        text: madeBox.m.type === "plan" ? Md.toHtml(said, pane.mdStyle, -1) : said
                        textFormat: madeBox.m.type === "plan" ? TextEdit.RichText : TextEdit.PlainText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: madeBox.m.type === "plan" ? TextEdit.Wrap : TextEdit.WrapAnywhere
                        color: pane.textColor
                        selectionColor: Kirigami.Theme.focusColor
                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                        font.family: madeBox.m.type === "plan" ? pane.chatFamily : pane.monoFamily
                        font.pointSize: madeBox.m.type === "plan" ? pane.pt : pane.pt * 0.88
                        onLinkActivated: link => {
                            if (link.indexOf("copy:") === 0)
                                pane.copyText(Md.clipboardCode(Md.codeBlocks(madeBox.shown.text)[Number(link.slice(5))] || ""), true)
                            else
                                Qt.openUrlExternally(link)
                        }
                    }
                }
            }
            // What it can't show: reading it, gone, too big, on an SSH host
            PlasmaComponents3.Label {
                readonly property string said: madeBox.m.gone ? i18n("It isn't there any more")
                    : madeBox.wanted && !madeBox.shown ? i18n("Reading it…")
                    : madeBox.shown && !madeBox.shown.ok ? (madeBox.shown.message || i18n("It couldn't be read"))
                    : !madeBox.local && (madeBox.m.type === "page" || madeBox.m.type === "file") ? i18n("On %1: %2", root.hostLabel(pane.host), madeBox.m.path)
                    : ""
                visible: said !== ""
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: said
                wrapMode: Text.Wrap
                color: pane.mutedColor
                font.family: pane.chatFamily
                font.pointSize: pane.pt * 0.92
            }
            RowLayout {
                spacing: Kirigami.Units.smallSpacing
                // (from what each shows for, not their visible: hidden, the row would hide them for good)
                readonly property bool pageOpens: madeBox.m.type === "page" && madeBox.canOpen
                readonly property bool sourceShows: madeBox.m.type === "page" && !madeBox.m.gone
                readonly property bool opens: madeBox.m.type !== "page" && (madeBox.canOpen || (!madeBox.local && picBox.file !== ""))
                visible: pageOpens || sourceShows || opens

                PlasmaComponents3.Button {
                    id: openPage
                    visible: parent.pageOpens
                    icon.name: Icons.plasma.web
                    text: i18n("Open in browser")
                    onClicked: madeBox.open(madeBox.m.path)
                    PlasmaComponents3.ToolTip.text: i18n("Pages aren't drawn in Talpy Chat: in your browser")
                    PlasmaComponents3.ToolTip.visible: hovered
                    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
                PlasmaComponents3.Button {
                    id: sourceButton
                    visible: parent.sourceShows
                    icon.name: Icons.plasma.showSource
                    text: madeBox.source ? i18n("Hide source") : i18n("Show source")
                    checkable: true
                    checked: madeBox.source
                    onClicked: madeBox.source = !madeBox.source
                    PlasmaComponents3.ToolTip.text: madeBox.source ? i18n("Hide its HTML") : i18n("Its HTML, as text (its first lines)")
                    PlasmaComponents3.ToolTip.visible: hovered
                    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
                PlasmaComponents3.Button {
                    id: openButton
                    // (a picture Claude saw: the copy of it here, what it saw; else the file as it is now)
                    readonly property string file: picBox.file || madeBox.m.path
                    visible: parent.opens
                    icon.name: Icons.plasma.openRun
                    text: i18n("Open")
                    onClicked: madeBox.open(file)
                    PlasmaComponents3.ToolTip.text: madeBox.m.type === "picture" ? i18n("In your picture viewer") : i18n("In the app for it")
                    PlasmaComponents3.ToolTip.visible: hovered
                    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
            }
        }
    }
}
