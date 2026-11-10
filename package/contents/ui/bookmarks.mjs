// Talpy Chat's bookmarks, the same in Plasma (Bookmarks.qml, BookmarkList.qml, MessageTools.qml,
// EditMenu.qml) and VS Code (chat.tsx, BookmarkList.tsx): which messages can be bookmarked, what a
// bookmark keeps of one, a chat's list as a click changes it (before pane.py --bookmark writes it),
// where each one is now, and where Alt+↑ / Alt+↓ go. Pure functions on pane.py's items and a chat's
// bookmarks ({key, kind: "you" | "claude", at, text, made}, in the chat's order): nothing here reads
// the screen. The rules match talpy_den.py's (bookmark_key_ok, bookmark_text, the cap).
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

import { plainOf, yoursShown } from "./find.mjs";

export const BOOKMARKS_MAX = 100;    // (talpy_den.BOOKMARKS_MAX)
export const SNIPPET_CHARS = 140;    // (talpy_den.BOOKMARK_TEXT)
const KEY = /^[A-Za-z0-9_.:@][A-Za-z0-9_.:@-]{0,199}$/;   // (talpy_den.BOOKMARK_KEY, never a flag)

// Can it be bookmarked: Claude's reply or your message, once it's in the chat (not a thinking line,
// a step, a note, your answer to a question, nor a message on its way, held or waiting in the queue)
export function canBookmark(it) {
    if (!it || (it.kind !== "you" && it.kind !== "claude") || it.thinking)
        return false;
    if (typeof it.key !== "string" || !KEY.test(it.key) || it.key.indexOf("pending-") === 0)
        return false;
    if (it.status === "sending" || it.status === "held")
        return false;
    return !it.queued && !it.until && !it.sending;
}

// A text on one line, its first SNIPPET_CHARS characters (… where cut), as talpy_den.bookmark_text
export function oneLine(text) {
    const line = String(text || "").split(/\s+/).filter(Boolean).join(" ");
    return line.length <= SNIPPET_CHARS ? line : line.slice(0, SNIPPET_CHARS - 1).replace(/\s+$/, "") + "…";
}

// What a bookmark shows of its message: Claude's reply as plain text, yours as shown (pictures as
// [Image #1]…, a command without its !)
export function snippetOf(it) {
    return oneLine(it.kind === "claude" ? plainOf(it.text) : yoursShown(it));
}

// A new bookmark of it, made now (ms)
export function entryOf(it, now) {
    return { key: it.key, kind: it.kind, at: it.at > 0 ? Math.floor(it.at) : 0, text: snippetOf(it), made: now };
}

// (in the chat's order: when each message was written, then when it was bookmarked; a stable sort)
function sorted(list) {
    return list.map((m, i) => [m, i])
        .sort((a, b) => (a[0].at - b[0].at) || (a[0].made - b[0].made) || (a[1] - b[1]))
        .map((p) => p[0]);
}

// The list with entry in it (one a key: a key it has stays as it is); null when it's full
export function withBookmark(list, entry) {
    const was = list || [];
    if (was.some((m) => m.key === entry.key))
        return sorted(was.slice());
    if (was.length >= BOOKMARKS_MAX)
        return null;
    return sorted(was.concat([entry]));
}

// The list without key
export function withoutBookmark(list, key) {
    return sorted((list || []).filter((m) => m.key !== key));
}

// {key: true} for each bookmark: is this row bookmarked
export function keysOf(list) {
    const out = {};
    for (const m of list || [])
        out[m.key] = true;
    return out;
}

// Where a bookmark's message is now: "here" (loaded: a Map or an object of the loaded keys);
// else what an earlier reach found (settled: {key: "far" | "gone"}); else "gone" once the whole chat
// is loaded (no more, not capped); "far" when the tab shows the most it shows (capped: further back
// than that); else "earlier" (further back than what's shown: Show earlier, or a reach, reads it)
export function stateOf(mark, loaded, more, capped, settled) {
    const key = mark.key;
    if (loaded && (typeof loaded.has === "function" ? loaded.has(key) : Object.prototype.hasOwnProperty.call(loaded, key)))
        return "here";
    if (settled && settled[key])
        return settled[key];
    if (!more && !capped)
        return "gone";
    return capped ? "far" : "earlier";
}

// Alt+↓ (back false) / Alt+↑ (back true) from what you read (viewTop: the view's top, in the list's
// coordinates; tops: {key: its row's top} for the loaded bookmarked rows): {key} the next / previous
// one; down past the last: {end: true}; up past the first: the newest one further back as {reach: key}
// (states: {key: stateOf}), else null. Those too far back or gone are skipped
export function step(list, states, tops, viewTop, back) {
    let best = null;
    for (const m of list || []) {
        const top = tops ? tops[m.key] : undefined;
        if (typeof top !== "number" || (states && states[m.key] && states[m.key] !== "here"))
            continue;
        if (back ? top < viewTop - 4 && (best === null || top > best.top) : top > viewTop + 4 && (best === null || top < best.top))
            best = { key: m.key, top };
    }
    if (best)
        return { key: best.key };
    if (!back)
        return { end: true };
    const all = list || [];
    for (let i = all.length - 1; i >= 0; i--) {
        if (states && states[all[i].key] === "earlier")
            return { reach: all[i].key };
    }
    return null;
}

// May an answer's list (its v) replace what's shown (localV): not while a change of ours is on its
// way (busy), nor an older one
export function adoptable(localV, busy, answerV) {
    return !busy && (answerV || 0) >= (localV || 0);
}

// Does the list stay open after a click goes to a bookmark: beside the chat (VS Code's wide tab), or
// when the chat is wide enough that the card covers little of it
export function staysOpen(listWidth, cardWidth, beside) {
    return !!beside || listWidth >= 3 * cardWidth;
}
