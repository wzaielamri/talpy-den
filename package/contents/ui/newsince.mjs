// New since …: a thin line in Talpy Chat's conversation above the first item that came in while you were
// away, the same in Plasma (ChatPane.qml, NewSinceLine.qml) and VS Code (chat.tsx). Its point is Since you
// last looked's (pane.py --away: turns.Away), where that bar's click goes (shared/pane.ts awayTarget): it
// shows when the bar does, stays where the click takes you, and moves when you come back to more. It goes
// once you've been at the chat's newest part for NEW_SINCE_READ_MS with the window shown (one timer, only
// then), when you send a message, and with the window. Pure functions: nothing here reads the screen or
// keeps time.
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

export const NEW_SINCE_READ_MS = 10000;   // (at the newest part this long, the window shown: read, it goes)
export const NEW_SINCE_TIP = "What came in since you last looked starts here. This line goes once you've been at the newest part for a few seconds, or when you send a message.";

// Its words (when: the time you left, as a message's time shows it: "14:32", "Yesterday 9:15")
export function newSinceText(when) {
    return "New since " + when;
}

// Where it is once Since you last looked answers (away: pane.py --away's answer, null when there's nothing
// new): {key (Claude's first reply since: the Chat tab's), stepKey (the first item since: Steps'), since};
// with nothing to point at, where it was (back with nothing new: the line you hadn't read yet stays)
export function newSinceOf(away, was) {
    if (away && (away.key || away.stepKey))
        return { key: String(away.key || ""), stepKey: String(away.stepKey || ""), since: Number(away.since) || 0 };
    return was || null;
}

// The item it's above on a tab (steps: the Steps tab), as Since you last looked's click goes; "": none there
export function newSinceKey(at, steps) {
    if (!at)
        return "";
    return steps ? at.stepKey || at.key : at.key;
}

// Whether its one timer runs: there's a line, the window shows the chat and is at its newest part
export function newSinceReading(at, shown, atEnd) {
    return !!at && !!shown && !!atEnd;
}

// What a message you send leaves of it: nothing, but Since you last looked's Recap (/recap: still catching up)
export function newSinceAfterSend(at, text) {
    return String(text || "").trim() === "/recap" ? at : null;
}
