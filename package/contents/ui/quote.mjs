// Quote in reply (Talpy Chat: the "Reply to this" button by a selection, the right-click menu's Quote in
// reply), the same in Plasma (ChatPane.qml) and VS Code (chat.tsx): what you selected, as a Markdown
// quote at the top of the reply box, the cursor under it. Pure functions: nothing here reads the screen.
//
// ES2017, no `?.` or `??`: QML (Qt V4) and browsers import it as it is.

export const QUOTE_BUTTON = "Reply to this";
export const QUOTE_MENU = "Quote in reply";
export const QUOTE_CHARS = 4000;   // (a selection longer than this is cut, with …: a quote, not a copy of the chat)

// The selection as a quote: each line after "> ", blank lines at its ends gone and runs of them one
export function quoteOf(selected) {
    let text = String(selected || "").replace(/\r\n?/g, "\n").replace(/[\u2028\u2029]/g, "\n");
    if (text.length > QUOTE_CHARS)
        text = text.slice(0, QUOTE_CHARS - 1).replace(/\s+$/, "") + "…";
    const lines = text.split("\n").map(function (l) { return l.replace(/\s+$/, ""); });
    while (lines.length && !lines[0].trim())
        lines.shift();
    while (lines.length && !lines[lines.length - 1].trim())
        lines.pop();
    const out = [];
    for (const l of lines) {
        if (!l.trim() && out.length && out[out.length - 1] === ">")
            continue;
        out.push(l.trim() ? "> " + l : ">");
    }
    return out.join("\n");
}

// The box with the quote put at its top: {text, cursor} (the cursor on the line after the quote, before
// what you had written)
export function withQuote(box, selected) {
    const q = quoteOf(selected);
    const rest = String(box || "").replace(/^\s+/, "");
    if (!q)
        return { text: String(box || ""), cursor: String(box || "").length };
    const head = q + "\n\n";
    return { text: head + rest, cursor: head.length };
}
