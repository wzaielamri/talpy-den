// New since …: a thin line in Talpy Chat's conversation above the first item that came in while you were
// away, the same in Plasma (ChatPane.qml, NewSinceLine.qml) and VS Code (chat.tsx). Its point is Since you
// last looked's (pane.py --away: turns.Away), where that bar's click goes (shared/pane.ts awayTarget): it
// shows when the bar does, stays where the click takes you, and moves when you come back to more. Once it
// has been in view with the window shown (seen: coming back, you're at the end with it out of view above),
// it goes when you've been at the chat's newest part for NEW_SINCE_READ_MS with the window shown (one timer,
// only then); unseen, it stays. It goes at once when you send a message, and with the window. Pure
// functions: nothing here reads the screen or keeps time.
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

export const NEW_SINCE_READ_MS = 10000;   // (at the newest part this long, the window shown: read, it goes)
export const NEW_SINCE_TIP = "What came in since you last looked starts here. This line goes once you've been at the newest part for a few seconds, or when you send a message.";

// Its words (when: the time you left, as a message's time shows it: "14:32", "Yesterday 9:15")
export function newSinceText(when) {
    return "New since " + when;
}

// Where it is once Since you last looked answers (away: pane.py --away's answer, null when there's nothing
// new): {key (Claude's first reply since: the Chat tab's), stepKey (the first item since: Steps'), since,
// seen (it has been in view: not yet)}; with nothing to point at, where it was (back with nothing new: the
// line you hadn't read yet stays)
export function newSinceOf(away, was) {
    if (away && (away.key || away.stepKey))
        return { key: String(away.key || ""), stepKey: String(away.stepKey || ""), since: Number(away.since) || 0, seen: false };
    return was || null;
}

// Seen once it's been in view (inView: newSinceInView) with the window shown; else as it was (the same
// object: nothing changes, nothing is drawn again)
export function newSinceLooked(at, shown, inView) {
    if (!at || at.seen || !shown || !inView)
        return at || null;
    return { key: at.key, stepKey: at.stepKey, since: at.since, seen: true };
}

// In view: all of it (top and height, px from the view's top) between the view's top and bottom (view: its height)
export function newSinceInView(top, height, view) {
    return height > 0 && top >= -0.5 && top + height <= view + 0.5;
}

// The item it's above on a tab (steps: the Steps tab), as Since you last looked's click goes; "": none there
export function newSinceKey(at, steps) {
    if (!at)
        return "";
    return steps ? at.stepKey || at.key : at.key;
}

// Whether its one timer runs: there's a line you've seen, the window shows the chat and is at its newest part
export function newSinceReading(at, shown, atEnd) {
    return !!at && !!at.seen && !!shown && !!atEnd;
}

// What a message you send leaves of it: nothing, but Since you last looked's Recap (/recap: still catching up)
export function newSinceAfterSend(at, text) {
    return String(text || "").trim() === "/recap" ? at : null;
}
