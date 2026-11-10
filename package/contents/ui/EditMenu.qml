import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "bookmarks.mjs" as Bm

// Talpy Chat's right-click menu, each item with its key: on the conversation,
// Copy (what's selected, across messages too), Copy message (the message
// right-clicked, as its Copy button: a reply as Markdown, all of it), Bookmark
// message or Remove bookmark (one that can be: Bookmarks.qml) and Select
// all (every message); on the reply box, Undo, Redo, Cut, Copy, Paste (a picture
// too, as Ctrl+V) and Select all. ChatPane.qml makes one for the window the
// first time it's right-clicked (a Loader) and opens it where it's clicked:
// nothing more per message. VS Code chat.tsx EditMenu: the same items and words.
PlasmaComponents3.Menu {
    id: menu

    property string where: ""   // "list": the conversation, "box": the reply box
    property Item row: null     // the message right-clicked (yours or Claude's reply), or null
    property string chosen: ""  // what's selected in the conversation when it opened

    // p: in selectOver (the conversation), or null (the reply box)
    function openAt(place, p) {
        where = place
        row = null
        chosen = ""
        if (place === "list") {
            const at = selectOver.mapToItem(list.contentItem, p.x, p.y)
            const r = list.itemAt(at.x, at.y)
            row = r && r.listed && r.shows && !r.card && (r.kind === "you" || r.kind === "claude") ? r : null
            chosen = pane.selectionText()
        }
        popup()
    }

    // An item with its key at its right end, dimmed (Plasma's MenuItem shows none); shown: in this
    // menu now (one hidden takes no room, and the menu is as wide as those shown)
    component KeyItem: PlasmaComponents3.MenuItem {
        id: keyItem
        property string keys: ""
        property bool shown: true
        visible: shown
        height: shown ? implicitHeight : 0
        implicitWidth: shown ? contentItem.implicitWidth + leftPadding + rightPadding : 0
        onImplicitWidthChanged: menu.contentItem.contentItem.childrenChanged()   // (as Plasma's own items: the menu's width again)
        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing * 2
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.smallSpacing
                textFormat: Text.PlainText
                text: keyItem.text
                opacity: keyItem.enabled ? 1 : 0.5
            }
            PlasmaComponents3.Label {
                visible: keyItem.keys !== ""
                textFormat: Text.PlainText
                text: keyItem.keys
                opacity: keyItem.enabled ? 0.6 : 0.3
            }
        }
    }

    // ---- the conversation
    KeyItem {
        shown: menu.where === "list"
        enabled: menu.chosen !== ""
        text: i18n("Copy")
        keys: i18nc("a key", "Ctrl+C")
        onTriggered: pane.copyText(menu.chosen)
    }
    KeyItem {
        shown: menu.where === "list" && menu.row !== null
        text: menu.row && menu.row.kind === "claude" ? i18n("Copy message (Markdown)") : i18n("Copy message")
        onTriggered: pane.copyItem(menu.row.key, menu.row.text, true)   // (all of it: Copied once it's on the clipboard)
    }
    KeyItem {
        shown: menu.where === "list" && menu.row !== null && Bm.canBookmark(menu.row)
        text: menu.row && pane.bookmarked[menu.row.key] === true ? i18n("Remove bookmark") : i18n("Bookmark message")
        keys: i18nc("a key", "Ctrl+D")
        onTriggered: pane.bookmarksNow().toggle(menu.row)
    }
    KeyItem {
        shown: menu.where === "list"
        text: i18n("Select all")
        keys: i18nc("a key", "Ctrl+A")
        onTriggered: pane.selectAllMessages()
    }

    // ---- the reply box
    KeyItem {
        shown: menu.where === "box"
        enabled: replyBox.canUndo
        text: i18n("Undo")
        keys: i18nc("a key", "Ctrl+Z")
        onTriggered: replyBox.undo()
    }
    KeyItem {
        shown: menu.where === "box"
        enabled: replyBox.canRedo
        text: i18n("Redo")
        keys: i18nc("a key", "Ctrl+Shift+Z")
        onTriggered: replyBox.redo()
    }
    PlasmaComponents3.MenuSeparator {
        visible: menu.where === "box"
        height: visible ? implicitHeight : 0
    }
    KeyItem {
        shown: menu.where === "box"
        enabled: replyBox.selectedText !== "" && !replyBox.readOnly
        text: i18n("Cut")
        keys: i18nc("a key", "Ctrl+X")
        onTriggered: replyBox.cut()
    }
    KeyItem {
        shown: menu.where === "box"
        enabled: replyBox.selectedText !== ""
        text: i18n("Copy")
        keys: i18nc("a key", "Ctrl+C")
        onTriggered: replyBox.copy()
    }
    KeyItem {
        shown: menu.where === "box"
        enabled: !replyBox.readOnly
        text: i18n("Paste")
        keys: i18nc("a key", "Ctrl+V")
        onTriggered: pane.pasteInBox()   // (a picture too, as Ctrl+V)
    }
    PlasmaComponents3.MenuSeparator {
        visible: menu.where === "box"
        height: visible ? implicitHeight : 0
    }
    KeyItem {
        shown: menu.where === "box"
        text: i18n("Select all")
        keys: i18nc("a key", "Ctrl+A")
        onTriggered: replyBox.selectAll()
    }

    onClosed: if (where === "box") replyBox.forceActiveFocus()
}
