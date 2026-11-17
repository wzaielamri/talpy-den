// Side questions (Talpy Chat's side panel, Claude's /btw beside the chat), the same in Plasma
// (ChatPane.qml) and VS Code (chat.tsx): asked about a chat without adding to it, answered by a copy of
// it Claude doesn't keep (pane.py --side-question, side.py), kept per chat to read again. Words, the
// question an "Explain this" asks, which of a chat's lists is newer, and what a question costs. Pure
// functions: nothing here reads the screen.
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

import { quoteOf } from "./quote.mjs";

export const SIDE_TITLE = "Side questions";
export const SIDE_BUTTON = "Side questions";   // (the header's toggle; its tip: SIDE_TIP)
export const SIDE_TIP = "Side questions: ask about this chat without adding to it";
export const SIDE_EMPTY = "Ask about this chat without adding to it. Claude answers from what the chat has so far, with no tools, and goes on with its work.";
export const SIDE_PLACEHOLDER = "Ask about this chat…";
export const EXPLAIN_BUTTON = "Explain this";
export const EXPLAIN_TIP = "Explain this: what you selected, asked as a side question (nothing is added to the chat)";
export const SIDE_PENDING = "Answering…";
export const SIDE_REMOVE = "Remove";
export const SIDE_CLEAR = "Remove all";
export const SIDE_COPY = "Copy answer";
export const SIDE_QUOTE = "Quote in reply";   // (an answer, quoted in the chat's reply box)
export const SIDE_AGAIN = "Ask again";        // (one with no answer: the same question again)
export const SIDE_CLEAR_ASK = "Remove all side questions of this chat?";
export const SIDE_CLOSE = "Close";
export const SIDE_PICK_TIP = "The model your next side question goes to: the chat's own, or a smaller one (less of your usage limit)";
// An answer's actions on hover, in this order in both front ends
export const SIDE_ACTIONS = ["copy", "quote", "whole", "remove"];   // ("whole": Ask with the whole chat, on one asked about a part)

// The model a side question was (or is being) answered on, for its meta line ("14:02 · Haiku"): the pick,
// else the chat's model as Claude names it ("claude-opus-5-5" → "Opus 5.5"), else the first pick's label
export function sideModelLabel(s) {
    if (s && s.pick)
        return pickLabel(s.pick);
    const m = /^claude-([a-z]+)-(\d+)-(\d+)/.exec(String((s && s.model) || ""));
    if (m)
        return m[1].charAt(0).toUpperCase() + m[1].slice(1) + " " + m[2] + "." + m[3];
    return "";
}

// The models a side question can be answered on: the chat's own, or a smaller one (less of your usage)
export const SIDE_PICKS = [
    { value: "", label: "Same model as the chat" },
    { value: "sonnet", label: "Sonnet" },
    { value: "haiku", label: "Haiku" },
];

export function pickLabel(pick) {
    for (const p of SIDE_PICKS)
        if (p.value === (pick || ""))
            return p.label;
    return SIDE_PICKS[0].label;
}

// The question an "Explain this" asks about what you selected (quoted as Quote in reply quotes it)
export function explainQuestion(selected) {
    const q = quoteOf(selected);
    return q ? "Explain this part of the chat:\n\n" + q : "";
}

// Whether a list of a chat's side questions (sides, v: pane.py's) is newer than the one shown (shownV)
export function newerSides(sides, v, shownV) {
    return Array.isArray(sides) && typeof v === "number" && v > (shownV || 0);
}

// "pending" (on its way), "error" (none came: its error) or "answered" (its a)
export function sideState(s) {
    if (!s || s.pending)
        return "pending";
    return typeof s.a === "string" && s.a ? "answered" : "error";
}

// Claude keeps a chat's prompt cache for about an hour (Claude Code asks for an hour): a side question
// after one answered on the same pick within WARM_MS reads the chat from the cache.
export const WARM_MS = 55 * 60 * 1000;

// fromKey: the part asked about (a part's key, "": the whole chat), which has a cache of its own
export function sideWarm(sides, pick, now, fromKey) {
    for (const s of sides || [])
        if ((s.pick || "") === (pick || "") && sideState(s) === "answered" && now - (s.done || 0) < WARM_MS
                && ((s.from && s.from.key) || "") === (fromKey || ""))
            return true;
    return false;
}

export function tokensText(n) {
    if (!(n > 0))
        return "";
    if (n >= 999500)
        return (Math.round(n / 100000) / 10) + "M";
    if (n >= 1000)
        return Math.round(n / 1000) + "k";
    return String(Math.round(n));
}

// The line under the ask box: what the next question costs. used: the chat's context in tokens (its
// --conversation "context".used), warm: sideWarm's. "" when there's nothing to say.
export const SIDE_COST_TIP = "A side question goes to a copy of this chat that Claude doesn't keep. "
    + "The first one in an hour sends the whole chat to Claude again; the ones after it, on the same model, "
    + "reuse it from the prompt cache. Sonnet or Haiku use less of your usage limit than the chat's own model.";

// Ask from here (a message's right-click menu, Explain this): side questions see the chat from the start
// of that message's turn on, not all of it (pane.py --side-question --from KEY; --part KEY says where it
// starts and what it costs). The chat shows where with a line; the panel says it under the box.
export const SIDE_FROM_MENU = "Ask from here";
export const SIDE_FROM_TIP = "Side questions see the chat from this message's turn on: less to send than all of it";
export const SIDE_FROM_LINE = "Side questions see from here";
export const SIDE_WHOLE = "Whole chat";   // (the x on the panel's from line: back to all of it)
export const SIDE_WHOLE_TIP = "Ask about the whole chat again";
export const SIDE_ASK_WHOLE = "Ask with the whole chat";
// (Ask from here on a message no part can start at: --part's null, else its "missing")
export const SIDE_FROM_COMPACTED = "That message is before the chat was compacted: side questions see all of it";
export const SIDE_FROM_GONE = "That message isn't in the chat any more: side questions see all of it";   // (an answer asked about a part: the same question, all of it)

function quoted(text) {
    return "\u201c" + String(text || "").replace(/\s+/g, " ").trim() + "\u201d";
}

// The panel's line when a part is picked (part: pane.py's {key, text, at, tokens, of}): where it starts and
// what it costs; warm: sideWarm's for that part
export function fromNote(part, warm) {
    if (!part)
        return "";
    const size = tokensText(part.tokens);
    const whole = tokensText(part.of);
    const head = "From " + quoted(part.text);
    if (warm)
        return head + ": follow-ups reuse it from the cache";
    return size ? head + ": " + size + (whole ? " of the chat's " + whole : "") + " tokens" : head;
}

// An answer's word on what it saw, for its meta line: the part ("from" and its first words), "whole chat"
// when it was asked from a message but got all of it, else nothing (all of it, as asked)
export function sideSaw(s) {
    if (s && s.from)
        return "from " + quoted(s.from.text);
    return s && s.since && sideState(s) === "answered" ? "whole chat" : "";
}

export function costNote(used, warm) {
    const t = tokensText(used);
    if (!t)
        return "";
    return warm ? "Follow-ups reuse the chat from the cache" : "The first question re-reads the chat: " + t + " tokens";
}
