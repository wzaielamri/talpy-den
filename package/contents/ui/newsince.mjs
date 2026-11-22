// New since …: a thin line in Talpy Chat's conversation above the first item that came in while you were
// away, the same in Plasma (ChatPane.qml, NewSinceLine.qml) and VS Code (chat.tsx). Its point is Since you
// last looked's (pane.py --away: turns.Away), where that bar's click goes (shared/pane.ts awayTarget): it
// shows when the bar does, stays where the click takes you, and moves when you come back to more.
//
// When it goes. Coming back you're usually at the end, the line out of view above, so it waits till you've
// seen it: all of it in the view for NEW_SINCE_SEEN_MS with the list at rest, the window shown and the list
// done going where it goes (the end as the window opens, a jump), on the tab you're on (seen on Chat isn't
// seen on Steps). A glimpse as the list moves past it doesn't count. Once seen there, it goes when you've
// been at the chat's newest part for NEW_SINCE_READ_MS with the window shown; scrolling up or hiding it
// stops that. It goes at once when you send a message. Hidden, it goes: back with new items, Since you last
// looked puts it at the new point; back with nothing new, there's none. Each front end runs two timers for
// it, each only while these say so: nothing ticks otherwise. Pure functions: nothing here reads the screen
// or keeps time.
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

export const NEW_SINCE_READ_MS = 10000;   // (seen, at the newest part this long, the window shown: read, it goes)
export const NEW_SINCE_SEEN_MS = 400;     // (in view this long, the list at rest: seen)
export const NEW_SINCE_TIP = "What came in since you last looked starts here. Once you've seen it, this line goes when you've been at the newest part for a few seconds, or when you send a message.";

// Its words (when: the time you left, as a message's time shows it: "14:32", "Yesterday 9:15")
export function newSinceText(when) {
    return "New since " + when;
}

// Where it is once Since you last looked answers (away: pane.py --away's answer, null when there's nothing
// new): {key (Claude's first reply since: the Chat tab's), stepKey (the first item since: Steps'), since,
// seen ({chat, steps}: seen on that tab, not yet)}; with nothing to point at, where it was
export function newSinceOf(away, was) {
    if (away && (away.key || away.stepKey))
        return { key: String(away.key || ""), stepKey: String(away.stepKey || ""), since: Number(away.since) || 0,
                 seen: { chat: false, steps: false } };
    return was || null;
}

// The item it's above on a tab (steps: the Steps tab), as Since you last looked's click goes; "": none there
export function newSinceKey(at, steps) {
    if (!at)
        return "";
    return steps ? at.stepKey || at.key : at.key;
}

// Whether you've seen it on that tab
export function newSinceSeenOn(at, steps) {
    return !!at && !!at.seen && at.seen[steps ? "steps" : "chat"] === true;
}

// Whether its seen timer (NEW_SINCE_SEEN_MS) runs: a line not seen on this tab, there, all of it in view
// (newSinceInView), the window shown, the list at rest and done going where it goes (placed). Every move
// of the list starts it again; when this turns false it stops
export function newSinceLooking(at, steps, shown, inView, still, placed) {
    return !!at && !newSinceSeenOn(at, steps) && newSinceKey(at, steps) !== "" && !!shown && !!inView && !!still && !!placed;
}

// Seen on that tab (its seen timer ended): a new object; already seen there, the same one
export function newSinceSeen(at, steps) {
    if (!at || newSinceSeenOn(at, steps))
        return at || null;
    const seen = { chat: !!(at.seen && at.seen.chat), steps: !!(at.seen && at.seen.steps) };
    seen[steps ? "steps" : "chat"] = true;
    return { key: at.key, stepKey: at.stepKey, since: at.since, seen: seen };
}

// In view: all of it (top and height, px from the view's top) between the view's top and bottom (view: its height)
export function newSinceInView(top, height, view) {
    return height > 0 && top >= -0.5 && top + height <= view + 0.5;
}

// Whether its read timer (NEW_SINCE_READ_MS) runs: seen on this tab, the window shows the chat and is at its
// newest part
export function newSinceReading(at, steps, shown, atEnd) {
    return newSinceSeenOn(at, steps) && !!shown && !!atEnd;
}

// What a message you send leaves of it: nothing, but Since you last looked's Recap (/recap: still catching up)
export function newSinceAfterSend(at, text) {
    return String(text || "").trim() === "/recap" ? at : null;
}

// What hiding the window (another tab in front) leaves of it: nothing. Back with new items, Since you last
// looked's answer puts it at the new point (newSinceOf); back with nothing new, there's none
export function newSinceAfterHide(at) {
    return null;
}
