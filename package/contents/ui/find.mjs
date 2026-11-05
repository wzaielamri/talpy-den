// Talpy Chat's search (Ctrl+F) and folding (Show more / Show less, Ctrl+O), the same in Plasma
// (ChatPane.qml, FindBar.qml) and VS Code (chat.tsx, shared/pane.ts): what each tab searches of a
// conversation's items, the matches as a list to go through, and where a long text is folded. Pure
// functions on pane.py's items (kind, key, text, line, summary, input, output, diff, command,
// asked): nothing here reads the screen.

// A text longer than FOLD_LINES lines (of about LINE_CHARS characters: a long paragraph counts as
// the lines it wraps to) shows only its first FOLD_SHOWN lines, folded, with Show more
export const FOLD_LINES = 40;
export const FOLD_SHOWN = 24;
const LINE_CHARS = 100;

function lineCost(length) {
    return Math.max(1, Math.ceil(length / LINE_CHARS));
}

// Where a long text is folded: null for one that isn't long, else {shown: its first part (a code
// block cut in two closed again, for Markdown), at: where the rest starts in text, more: about how
// many lines the rest is}. how: "markdown" (Claude's reply), "plain" (yours), "ansi" (a command's
// output: cut only between lines, never inside a colour's code)
export function foldOf(text, how = "markdown") {
    if (!text)
        return null;
    let lines = 1;
    for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1))
        lines++;
    if (lines + text.length / LINE_CHARS <= FOLD_LINES)   // (quick: it can't be long, whatever its lines)
        return null;
    const parts = text.split("\n");
    let total = 0;
    for (const p of parts)
        total += lineCost(p.length);
    if (total <= FOLD_LINES)
        return null;
    let used = 0, at = 0, fence = "", partly = false;
    for (const p of parts) {
        const cost = lineCost(p.length);
        if (used + cost > FOLD_SHOWN) {
            if (used < FOLD_SHOWN && how !== "ansi" && !fence) {   // (a long paragraph: as much of it as fits, to a word's end)
                const room = (FOLD_SHOWN - used) * LINE_CHARS;
                const space = p.lastIndexOf(" ", room);
                const cut = space > room / 2 ? space : room;
                used += lineCost(cut);
                at += cut;
                partly = true;
            }
            break;
        }
        used += cost;
        const mark = how === "markdown" ? /^\s{0,3}(```|~~~)/.exec(p) : null;
        if (mark)
            fence = fence ? "" : mark[1];
        at += p.length + 1;
    }
    at = Math.min(at, text.length);
    const shown = text.slice(0, at).replace(/\s+$/, "") + (partly ? " …" : "") + (fence ? "\n" + fence : "");
    return { shown, at, more: Math.max(1, total - used) };
}

// Claude's Markdown as the text it shows: the marks that draw it (#, **, `, a link's address, a
// list's marks, a table's bars) left out, code as it is
export function plainOf(md) {
    let fence = false;
    return String(md || "").split("\n").map((line) => {
        if (/^\s{0,3}(```|~~~)/.test(line)) {
            fence = !fence;
            return "";
        }
        if (fence)
            return line;
        if (/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line) && line.includes("-"))
            return "";   // (a table's line under its head)
        return line
            .replace(/^\s{0,3}#{1,6}\s+/, "")
            .replace(/^(\s*>\s?)+/, "")
            .replace(/^\s*(?:[-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?/, "")
            .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
            .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
            .replace(/<(https?:[^>\s]+)>/g, "$1")
            .replace(/`([^`]+)`/g, "$1")
            .replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "$2")
            .replace(/~~(?=\S)([\s\S]*?\S)~~/g, "$1")
            .replace(/(^|[^\w*])\*(?=[^\s*])([^*]*?[^\s*])\*(?![\w*])/g, "$1$2")
            .replace(/(^|\W)_(?=[^\s_])([^_]*?[^\s_])_(?!\w)/g, "$1$2")
            .replace(/^\s*\|(.*)\|\s*$/, (_all, row) => row.trim())
            .replace(/\s*\|\s*/g, " ");
    }).join("\n");
}

const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]/g;
function noAnsi(text) {
    return String(text || "").replace(ANSI, "");
}

// Your message as shown: each picture as [Image #1], [Image #2]… (shared/pane.ts numberedPictures,
// ChatPane shownText); a shell command without its !
function yours(it) {
    const text = it.text || "";
    if (it.command && it.command.shell)
        return text.replace(/^!\s*/, "");
    const seen = new Map();
    return text.replace(/\[Image: (\/[^\]\n]+)\]/g, (_all, p) => {
        if (!seen.has(p))
            seen.set(p, seen.size + 1);
        return `[Image #${seen.get(p)}]`;
    });
}

// A question or a plan Claude asked, once you answered it: shown as Claude's on both tabs (shared/pane.ts
// askedShows); a call you denied with a note shows on the Chat tab too
function askedShown(it) {
    const a = it.asked;
    return !!a && (!!a.questions || a.plan !== undefined) && a.state !== "open" && a.state !== "failed" && a.state !== "denied";
}

// What a tab shows of an item, as text: [what shows as it is, what shows only once it's opened or
// unfolded]. Chat leaves out Claude's tool calls (but a question or a plan you answered, and a call
// you denied with a note); Steps has them, a call's line and what came of it, then what it ran and
// got (its change, for an edit), which show once it's opened. A long text: its first part, then the
// rest (foldOf)
export function findParts(it, steps) {
    switch (it.kind) {
    case "you": {
        const text = yours(it);
        const out = it.command && it.command.output ? noAnsi(it.command.output) : "";
        const f = foldOf(text, "plain");
        const fo = out ? foldOf(it.command.output, "ansi") : null;
        const outShown = fo ? noAnsi(fo.shown) : out;
        return f ? [f.shown, text.slice(f.at) + (out ? "\n" + out : "")]
                 : [text + (outShown ? "\n" + outShown : ""), fo ? noAnsi(it.command.output.slice(fo.at)) : ""];
    }
    case "claude": {
        const f = foldOf(it.text || "");
        return f ? [plainOf(f.shown), plainOf((it.text || "").slice(f.at))] : [plainOf(it.text), ""];
    }
    case "note":
        return [it.text || "", ""];
    case "tool": {
        if (askedShown(it)) {
            const a = it.asked;
            if (a.questions)
                return [a.questions.map((q) => (q.header ? q.header + " " : "") + q.question).join("\n"),
                        a.questions.map((q) => q.options.map((o) => o.label + (o.description ? " " + o.description : "")).join("\n")).join("\n")];
            return ["Plan " + (a.title || ""), plainOf(a.plan || "")];
        }
        if (!steps && !(it.asked && it.asked.state === "denied"))
            return ["", ""];
        const name = it.name || "", line = it.line || "";
        const args = name && line.startsWith(name + ": ") ? line.slice(name.length + 2) : "";
        const head = (args ? name + "  " + args : line) + (it.summary ? "\n" + it.summary : "");
        if (!steps)
            return [head, ""];
        const diff = it.diff && it.diff.length && it.status !== "error" ? it.diff.join("\n") : "";
        return [head, diff || [it.input || "", it.output || ""].filter(Boolean).join("\n")];
    }
    }
    return ["", ""];
}

// Each item's text, low case, as last searched (by its key: an item read again is the same text)
const lowered = new Map();
function lowOf(it, steps) {
    const key = String(it.key) + (steps ? "\u0001s" : "\u0001c");
    const was = lowered.get(key);
    if (was && was.it === it)
        return was;
    const [shown, rest] = findParts(it, steps);
    const found = { it, low: (shown + "\u0000" + rest).toLowerCase(), cut: shown.length };
    lowered.delete(key);   // (the newest last: the oldest go first)
    lowered.set(key, found);
    if (lowered.size > 6000)   // (another chat's, long gone)
        lowered.delete(lowered.keys().next().value);
    return found;
}

// The matches of query in what the tab shows of items (case doesn't count), in their order:
// {key, n: the nth in that item, hidden: in what shows only once it's opened or unfolded}. A slice
// at a time: from (the item to go on from), budget (ms, then it stops at an item's end), hits (the
// ones so far); next: where to go on, -1 once all are searched
export function findIn(items, query, steps, from = 0, budget = Infinity, hits = []) {
    const q = String(query || "").toLowerCase();
    if (!q)
        return { hits: [], next: -1 };
    const start = Date.now();
    for (let i = from; i < items.length; i++) {
        if (budget !== Infinity && i > from && (i - from) % 8 === 0 && Date.now() - start >= budget)
            return { hits, next: i };
        const { low, cut } = lowOf(items[i], steps);
        let n = 0;
        for (let at = low.indexOf(q); at >= 0; at = low.indexOf(q, at + q.length))
            hits.push({ key: String(items[i].key), n: n++, hidden: at > cut });
    }
    return { hits, next: -1 };
}

// The count's words in the find bar: "No matches", "12 matches" (before you go to one), "3 of 12";
// searching: what it found so far, "…"
export function findCount(total, at, done) {
    if (!done)
        return total ? `${total}…` : "…";
    if (!total)
        return "No matches";
    return at >= 0 ? `${at + 1} of ${total}` : total === 1 ? "1 match" : `${total} matches`;
}

// The match to go to from where you read: the first one in an item at or below the first item in
// view (Enter, ↓), or the last one in an item at or above the last in view (Shift+Enter, ↑); then
// one after another, round. at: the one gone to (-1: none yet); order: the keys in the list's order
export function findStep(hits, at, back, view) {
    if (!hits.length)
        return -1;
    if (at >= 0 && at < hits.length)
        return (at + (back ? hits.length - 1 : 1)) % hits.length;
    const index = (key) => (view.order.has(key) ? view.order.get(key) : -1);
    if (!back) {
        const i = hits.findIndex((h) => index(h.key) >= view.first);
        return i >= 0 ? i : 0;
    }
    for (let i = hits.length - 1; i >= 0; i--)
        if (index(hits[i].key) <= view.last)
            return i;
    return hits.length - 1;
}

// Where the nth match of query is in a shown text (case doesn't count): [start, end], or null when it
// shows fewer (it's in what's folded, or shown another way)
export function nthIn(text, query, n) {
    const low = String(text || "").toLowerCase(), q = String(query || "").toLowerCase();
    if (!q)
        return null;
    let k = 0;
    for (let at = low.indexOf(q); at >= 0; at = low.indexOf(q, at + q.length), k++)
        if (k === n)
            return [at, at + q.length];
    return null;
}

// Every match of query in a shown text: [[start, end]…] (at most max)
export function allIn(text, query, max = 500) {
    const low = String(text || "").toLowerCase(), q = String(query || "").toLowerCase();
    const out = [];
    if (!q)
        return out;
    for (let at = low.indexOf(q); at >= 0 && out.length < max; at = low.indexOf(q, at + q.length))
        out.push([at, at + q.length]);
    return out;
}
