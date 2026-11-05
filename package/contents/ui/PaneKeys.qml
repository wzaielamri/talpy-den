import QtQuick
import "keys.mjs" as PaneKeys

// What Talpy Chat's keys do (keys.mjs: the same as VS Code's): ChatPane.qml's surface and reply box
// ask keyAction at the ShortcutOverride (the key's id, or "": not Talpy Chat's, or nothing to do
// with it now), then takeKey does it. A file of its own, read and made once the window shows (a
// Loader, asynchronous): every window opens as quickly. Esc does the nearest thing first, one a
// press (keys.mjs escTarget).
QtObject {
    function keyAction(event) {
        const k = event.key, m = event.modifiers & ~Qt.KeypadModifier
        const ctrl = m === Qt.ControlModifier, alt = m === Qt.AltModifier, plain = m === Qt.NoModifier
        const ctrlShift = m === (Qt.ControlModifier | Qt.ShiftModifier)
        if (k === Qt.Key_Escape && plain)
            return escapeTarget() !== "" ? "escape" : ""
        if (ctrl && k >= Qt.Key_1 && k <= Qt.Key_3)
            return k === Qt.Key_3 && pane.fresh ? "" : ["tabChat", "tabSteps", "tabReview"][k - Qt.Key_1]
        if (ctrl && k === Qt.Key_W)
            return "close"
        if ((ctrl && k === Qt.Key_Tab) || (ctrlShift && k === Qt.Key_Backtab))
            return k === Qt.Key_Tab ? "nextWindow" : "previousWindow"
        if (ctrlShift && k === Qt.Key_O)
            return pane.fresh || pane.starting ? "" : "openWindow"
        if (ctrl && k === Qt.Key_T)
            return pane.tasks !== null || pane.agents !== null ? "tasks" : ""
        if (ctrlShift && k === Qt.Key_C)
            return "copyLast"
        if (alt && (k === Qt.Key_Y || k === Qt.Key_A || k === Qt.Key_N))
            return pane.permission && askColumn.canAnswer ? (k === Qt.Key_Y ? "allow" : k === Qt.Key_A ? "always" : "deny") : ""
        if (!pane.conversationTab)
            return ""
        const enter = k === Qt.Key_Return || k === Qt.Key_Enter
        if (enter && (ctrl || alt || ctrlShift))
            return ctrl ? "sendNow" : alt ? "sendLater" : "sendBackground"
        // (Alt+1…: a chip; with Shift, into the box first: the digit by its key, whatever the layout makes of it)
        const digit = k >= Qt.Key_1 && k <= Qt.Key_9 ? k - Qt.Key_0 : event.nativeScanCode >= 10 && event.nativeScanCode <= 18 ? event.nativeScanCode - 9 : 0
        if ((alt || m === (Qt.AltModifier | Qt.ShiftModifier)) && digit > 0)
            return chipsRow.item && chipsRow.item.shown[digit - 1] ? (alt ? "chip" : "edit") + digit : ""
        if (plain && (k === Qt.Key_PageUp || k === Qt.Key_PageDown))
            return k === Qt.Key_PageUp ? "pageUp" : "pageDown"
        if (ctrl && (k === Qt.Key_Up || k === Qt.Key_Down))
            return k === Qt.Key_Up ? "promptUp" : "promptDown"
        if (ctrl && k === Qt.Key_L)
            return replyBox.text !== "" ? "clear" : ""
        if (event.text === "?" && !(m & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) && replyBox.activeFocus && replyBox.text === "")
            return "help"
        return ""
    }
    function takeKey(event) {
        const id = keyAction(event)
        if (id === "")
            return false
        event.accepted = true
        doKey(id)
        return true
    }
    // Esc does the nearest thing first, one a press (keys.mjs escTarget): the big picture, the / and
    // @ list, the keys, the grey completion; only then, in an empty box while Stop shows, it stops
    // Claude (a chip's menu closes itself first)
    function escapeTarget() {
        return PaneKeys.escTarget({ big: pane.bigPicture !== "", list: pane.suggestions.length > 0 && replyBox.activeFocus, help: pane.helpOn,
                                    ghost: !!ghostLine.item && ghostLine.item.rest !== "",
                                    stop: replyBox.activeFocus && replyBox.text === "" && pane.canStop && !pane.stopping })
    }
    function doKey(id) {
        const text = replyBox.text.trim()
        const terminal = pane.route === "terminal" || pane.askHow
        const elsewhere = !pane.replyAnswers && pane.commandNow && pane.commandNow.run !== "here"
        switch (id) {
        case "escape": {
            const what = escapeTarget()
            if (what === "big")
                pane.bigPicture = ""
            else if (what === "list") {
                pane.dismissed = replyBox.text.slice(pane.tokenStart, replyBox.cursorPosition)
                pane.suggestions = []
            } else if (what === "help")
                pane.helpOn = false
            else if (what === "ghost")
                pane.ghostOff = replyBox.text
            else if (what === "stop")
                pane.stop()
            return
        }
        case "sendNow": {   // (no 5 s wait; in an empty box, the message waiting goes now)
            if (text !== "")
                return pane.send("enter", false, true)
            const mine = pane.pendingSent.filter(p => p.state === "held" && p.chat === pane.chatId && p.host === (pane.host || ""))
            if (mine.length)
                pane.release("pending-" + mine[mine.length - 1].id)
            return
        }
        case "sendLater":
            if (pane.busy && text !== "" && !elsewhere)
                pane.send(terminal ? "background" : "auto", true)
            return
        case "sendBackground":
            if (terminal && !pane.busy && text !== "" && !elsewhere)
                pane.send("background", false)
            return
        case "clear":   // (an edit: Ctrl+Z brings it back)
            replyBox.remove(0, replyBox.length)
            replyBox.forceActiveFocus()
            return
        case "allow":
        case "always":
        case "deny":
            askColumn.pressKey(id)
            return
        case "pageUp":
        case "pageDown":
            settle.stop()
            holdTop.stop()
            list.contentY = Math.max(list.originY, Math.min(list.originY + list.contentHeight - list.height,
                                                            list.contentY + (id === "pageUp" ? -1 : 1) * Math.max(fm.height * 2, list.height - fm.height * 2)))
            return
        case "promptUp":
        case "promptDown":
            return jumpPrompt(id === "promptDown")
        case "tabChat":
        case "tabSteps":
        case "tabReview":
            pane.tab = id === "tabChat" ? "chat" : id === "tabSteps" ? "steps" : "review"
            return
        case "tasks":
            return pane.toggleStrip()
        case "copyLast":
            return pane.copyLast()
        case "openWindow":
            return root.openRow(pane.row || pane.chat, pane.host, true)
        case "close":
            return pane.close()
        case "nextWindow":
        case "previousWindow":
            return root.nextPaneWindow(pane, id === "previousWindow")
        case "help":
            pane.helpOn = true
            return
        }
        const chip = /^(chip|edit)([1-9])$/.exec(id)
        if (chip && chipsRow.item && chipsRow.item.shown[Number(chip[2]) - 1])
            pane.takeChip(chipsRow.item.shown[Number(chip[2]) - 1], chip[1] === "edit")
    }
    // Ctrl+↑ / Ctrl+↓: your previous / next message at the list's top (past the last: the end)
    function jumpPrompt(down) {
        settle.stop()
        holdTop.stop()
        const top = list.contentY
        let to = null
        for (let i = 0; i < items.count; i++) {
            if (items.get(i).kind !== "you")
                continue
            const it = list.itemAtIndex(i)
            if (!it || !it.visible || it.height <= 0)
                continue
            const at = it.y + (it.gap || 0) - fm.height * 0.5
            if (down ? at > top + 4 : at < top - 4) {
                to = at
                if (down)
                    break
            }
        }
        if (to !== null)
            list.contentY = Math.max(list.originY, Math.min(list.originY + list.contentHeight - list.height, to))
        else if (down)
            pane.toEnd()
    }
}
