// Claude's replies as Qt rich text, for the chat pane (ChatPane.qml): the
// Markdown it writes (headings, lists, code blocks, tables, quotes, rules,
// bold, italics, strikethrough, inline code, links) made into the HTML a
// RichText TextEdit draws, in the pane's colors and sizes. Every bit of the
// reply is escaped, so nothing in it becomes a tag of its own (no images,
// nothing loaded); links are only http(s) and mailto. A code block's "Copy"
// is a copy:N link (N: its index in codeBlocks()). What isn't understood
// shows as written. Plain ES2017 for Qt's JavaScript: no ?. or ??, no
// lookbehind.
//
// style: {pt (the text's point size), mono (a monospace family), text,
// muted, accent (bullets, quote bars), heading, strong (bold, small headings
// and a table's head, as Claude's terminal draws bold: the theme's highlight;
// none: the text's), code (inline code), codeBg, blockBg (code blocks),
// border, link}: colors as "#rrggbb"; syntax (codehtml.mjs syntaxColors: a
// code block's colors, by the language after its ```; none: as written).

import { fenceLanguage, highlight } from "./codeview.mjs";

const FENCE = /^(\s*)(```+|~~~+)\s*([^\s`]*)/;
const HEADING = /^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;   // (a closing run of # only after a space: C# stays)
const BULLET = /^(\s*)([-*+])\s+(.*)$/;
const NUMBERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const SAFE_LINK = /^(https?:|mailto:)/i;
// A link's address as it's opened: a mailto: one to its addresses only (its
// ?attach=… would put a file of yours in the mail, ?body=… write it)
function linkHref(url) {
    return /^mailto:/i.test(url) ? url.split("?")[0] : url;
}
const INLINE = /`([^`]+)`|\*\*(\S(?:(?:(?!\*\*).)*?\S)?)\*\*|__(\S(?:(?:(?!__).)*?\S)?)__|\*([^*\s](?:[^*]*?[^*\s])?)\*|_([^_\s](?:[^_]*?[^_\s])?)_|~~(\S(?:(?:(?!~~).)*?\S)?)~~|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)|(https?:\/\/(?:[^\s<>()]|\([^\s<>()]*\))*(?:[^\s<>().,;:!?'"]|\([^\s<>()]*\)))|\\([\\`*_{}\[\]()#+\-.!|~<>])/g;
const WORD = /\w/;
const MARK = /[^\w\s]/;

// Whether the marks around m (a **, __, *, _ or ~~ match ending at end) make
// emphasis, as in CommonMark: a closing mark comes after text and isn't
// written \*, no mark sits between punctuation and a word (f(*args, **kw)
// stays as written), and _ or __ only at words' edges (snake_case_names)
function emphasis(text, m, end) {
    const d = m[2] !== undefined || m[3] !== undefined || m[6] !== undefined ? 2 : 1;
    const before = m.index > 0 ? text[m.index - 1] : " ";
    const after = end < text.length ? text[end] : " ";
    const last = text[end - d - 1];
    if (last === "\\" || (MARK.test(text[m.index + d]) && WORD.test(before)) || (MARK.test(last) && WORD.test(after)))
        return false;
    return (m[3] === undefined && m[5] === undefined) || !(WORD.test(before) || WORD.test(after));
}

export function escape(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function px(n) {
    return Math.round(n) + "px";
}

// The room above a table: Qt Quick paints a table's background over its own
// margin, so a table's gap is a nearly empty line before it
function spacer(h) {
    return h > 0 ? `<p style="margin-top:${px(h - 1)}; margin-bottom:0px; font-size:1px">&nbsp;</p>` : "";
}

function family(name) {
    return /^[\w-]+$/.test(name) ? name : `'${name.replace(/'/g, "")}'`;
}

// Inline Markdown in a line: `code`, **bold**, *italics*, ~~struck~~, links
export function inline(text, s) {
    let out = "";
    let last = 0;
    const pattern = new RegExp(INLINE.source, "g");
    for (let m = pattern.exec(text); m; m = pattern.exec(text)) {
        const end = pattern.lastIndex;
        if (m[1] === undefined && m[7] === undefined && m[9] === undefined && m[10] === undefined && !emphasis(text, m, end)) {
            pattern.lastIndex = m.index + 1;
            continue;
        }
        out += escape(text.slice(last, m.index));
        if (m[1] !== undefined)   // (its ground ends with its last character: no margin that reads as a space)
            out += `<span style="font-family:${family(s.mono)}; font-size:${(s.pt * 0.92).toFixed(1)}pt; color:${s.code}; background-color:${s.codeBg}">${escape(m[1])}</span>`;
        else if (m[2] !== undefined || m[3] !== undefined)
            out += `<b style="color:${s.strong || s.text}">${inline(m[2] !== undefined ? m[2] : m[3], s)}</b>`;
        else if (m[4] !== undefined || m[5] !== undefined)
            out += `<i>${inline(m[4] !== undefined ? m[4] : m[5], s)}</i>`;
        else if (m[6] !== undefined)
            out += `<s>${inline(m[6], s)}</s>`;
        else if (m[7] !== undefined)
            out += SAFE_LINK.test(m[8]) ? `<a href="${escape(linkHref(m[8]))}" style="color:${s.link}">${inline(m[7], s)}</a>` : inline(m[7], s);
        else if (m[9] !== undefined)
            out += `<a href="${escape(m[9])}" style="color:${s.link}">${escape(m[9])}</a>`;
        else
            out += escape(m[10]);   // (\*, \_, \| …: the mark itself)
        last = end;
    }
    return out + escape(text.slice(last));
}

// A table line's cells: split at each | but one written \|, a | in its cell
function cells(line) {
    const out = [""];
    const t = line.trim().replace(/^\|/, "");
    for (let i = 0; i < t.length; i++) {
        if (t[i] === "\\" && t[i + 1] === "|")
            out[out.length - 1] += t[++i];
        else if (t[i] === "|")
            out.push("");
        else
            out[out.length - 1] += t[i];
    }
    if (out.length > 1 && !out[out.length - 1].trim())
        out.pop();   // (the line's closing |)
    return out.map(c => c.trim());
}

// The reply's blocks: {kind: "para"|"heading"|"list"|"code"|"quote"|"rule"|"table", …}
export function blocks(text) {
    const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let para = [];
    let list = null;
    const flushPara = () => {
        if (para.length)
            out.push({ kind: "para", text: para.join(" ") });
        para = [];
    };
    const flushList = () => {
        if (list)
            out.push(list);
        list = null;
    };
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const fence = FENCE.exec(line);
        if (fence) {
            flushPara();
            flushList();
            // (a block in a list item: its lines without the fence's indent)
            const body = [];
            for (i++; i < lines.length && !(lines[i].trim().indexOf(fence[2]) === 0 && lines[i].trim().replace(/[`~]/g, "") === ""); i++)
                body.push(lines[i].replace(/^[ \t]*/, w => w.slice(fence[1].length)));
            out.push({ kind: "code", lang: fence[3], text: body.join("\n") });
            continue;
        }
        if (!line.trim()) {
            flushPara();
            flushList();
            continue;
        }
        const heading = HEADING.exec(line);
        if (heading) {
            flushPara();
            flushList();
            out.push({ kind: "heading", level: heading[1].length, text: heading[2] });
            continue;
        }
        if (RULE.test(line) && !para.length) {
            flushList();
            out.push({ kind: "rule" });
            continue;
        }
        if (line.indexOf("|") >= 0 && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1]) && lines[i + 1].indexOf("-") >= 0) {
            flushPara();
            flushList();
            const head = cells(line);
            const rows = [];
            for (i += 2; i < lines.length && lines[i].indexOf("|") >= 0 && lines[i].trim(); i++)
                rows.push(cells(lines[i]));
            i--;
            out.push({ kind: "table", head: head, rows: rows });
            continue;
        }
        const quote = QUOTE.exec(line);
        if (quote) {
            flushPara();
            flushList();
            const body = [quote[1]];
            while (i + 1 < lines.length && QUOTE.test(lines[i + 1]))
                body.push(QUOTE.exec(lines[++i])[1]);
            out.push({ kind: "quote", text: body.join(" ") });
            continue;
        }
        const bullet = BULLET.exec(line);
        const numbered = bullet ? null : NUMBERED.exec(line);
        if (bullet || numbered) {
            flushPara();
            const m = bullet || numbered;
            const depth = Math.floor(m[1].replace(/\t/g, "  ").length / 2);
            if (list && depth === 0 && list.items[0].ordered !== !!numbered)
                flushList();
            if (!list)
                list = { kind: "list", items: [] };
            list.items.push({ depth: depth, ordered: !!numbered, n: numbered ? Number(numbered[2]) : 0, text: m[3] });
            continue;
        }
        if (list && /^\s{2,}\S/.test(line)) {   // (a list item that goes on on the next line)
            list.items[list.items.length - 1].text += " " + line.trim();
            continue;
        }
        flushList();
        para.push(line.trim());
    }
    flushPara();
    flushList();
    return out;
}

// The text of each code block, by its copy:N index
export function codeBlocks(text) {
    return blocks(text).filter(b => b.kind === "code").map(b => b.text);
}

// What a code block's Copy puts on the clipboard: its text, without the "! "
// of a command Claude means for its prompt in a terminal (where a line that
// starts with ! runs in the chat's shell) when each of its lines has one. The
// pane shows it as written; pasted in a shell, ! is "not" (the command runs,
// its exit status turned round, and a && after it goes the other way).
export function clipboardCode(code) {
    const lines = code.split("\n");
    const filled = lines.filter(line => line.trim() !== "");
    if (filled.length === 0 || !filled.every(line => /^!\s+\S/.test(line)))
        return code;
    return lines.map(line => line.replace(/^!\s+/, "")).join("\n");
}

const HEADING_SIZE = [1.5, 1.3, 1.15, 1.05, 1, 1];

// A code block's text in its language's colors (codeview.mjs highlight), as escaped HTML
function colored(text, lang, s) {
    const kind = s.syntax ? fenceLanguage(lang) : "";
    if (!kind || text.length > 200000)
        return escape(text);
    const state = {};
    return text.split("\n").map(line => highlight(line, kind, state).map(run => {
        const color = run[0] ? s.syntax[run[0]] : "";
        return color ? `<span style="color:${color}">${escape(run[1])}</span>` : escape(run[1]);
    }).join("")).join("\n");
}

function listHtml(items, s, top, bottom) {
    // Nested <ul>/<ol>: Qt draws the markers, in the item's color (the accent)
    let out = "";
    const open = [];
    const em = s.pt * 1.333;
    items.forEach((it, k) => {
        const tag = it.ordered ? "ol" : "ul";
        while (open.length > it.depth + 1 || (open.length === it.depth + 1 && open[open.length - 1] !== tag))
            out += `</${open.pop()}>`;
        while (open.length < it.depth + 1) {
            const first = open.length === 0;
            out += `<${tag}${it.ordered ? ` start="${it.n || 1}"` : ""} style="margin-top:${first ? px(top) : "0px"}; margin-bottom:0px; -qt-list-indent:${open.length + 1}">`;
            open.push(tag);
        }
        const last = k === items.length - 1;
        out += `<li style="color:${s.accent}; margin-top:${px(em * 0.15)}; margin-bottom:${last ? px(bottom) : px(em * 0.15)}"><span style="color:${s.text}">${inline(it.text, s)}</span></li>`;
    });
    while (open.length)
        out += `</${open.pop()}>`;
    return out;
}

// Claude's reply as Qt rich text; copied: the code block whose Copy reads Copied (its index), if one
export function toHtml(text, s, copied) {
    const em = s.pt * 1.333;   // (in px)
    const gap = em * 0.7;
    const list = blocks(text);
    let code = 0;
    const html = list.map((b, k) => {
        const top = k === 0 ? 0 : gap;
        const bottom = 0;   // (the next block's top is the gap)
        if (b.kind === "heading") {
            const size = HEADING_SIZE[b.level - 1] * s.pt;
            return `<p style="margin-top:${k === 0 ? "0px" : px(em * 1.1)}; margin-bottom:${px(em * 0.1)}; font-size:${size.toFixed(1)}pt; font-weight:700; color:${b.level <= 3 ? s.heading : s.strong || s.text}">${inline(b.text, s)}</p>`;
        }
        if (b.kind === "list")
            return listHtml(b.items, s, top, bottom);
        if (b.kind === "code") {
            const n = code++;
            const small = `font-size:${(s.pt * 0.8).toFixed(1)}pt`;
            // (its Copy reads Copied a moment after a click: copied, that block's index;
            // the pane frames it while the pointer is on it, copyFrame)
            const head = `<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:${px(em * 0.3)}"><tr><td style="${small}; color:${s.muted}">${escape(b.lang)}</td>`
                + `<td align="right" style="${small}"><a href="copy:${n}" style="color:${n === copied ? s.text : s.muted}; text-decoration:none">${n === copied ? "Copied" : "Copy"}</a></td></tr></table>`;
            return spacer(top) + `<table width="100%" cellspacing="0" cellpadding="${Math.round(em * 0.5)}" style="background-color:${s.blockBg}; border-color:${s.border}; border-style:solid; border-width:1px"><tr><td>`
                + head + `<pre style="font-family:${family(s.mono)}; font-size:${(s.pt * 0.92).toFixed(1)}pt; white-space:pre-wrap; margin:0px">${colored(b.text, b.lang, s)}</pre></td></tr></table>`;
        }
        if (b.kind === "quote")
            return spacer(top) + `<table cellspacing="0" cellpadding="0"><tr><td width="3" style="background-color:${s.accent}"></td>`
                + `<td style="padding-left:${px(em * 0.7)}; color:${s.muted}">${inline(b.text, s)}</td></tr></table>`;
        if (b.kind === "rule")
            return spacer(top + em * 0.3) + `<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:${px(em * 0.3)}"><tr><td style="background-color:${s.border}; font-size:1pt">&nbsp;</td></tr></table>`;
        if (b.kind === "table") {
            const pad = Math.round(em * 0.35);
            const head = b.head.map(c => `<th align="left" style="color:${s.strong || s.text}">${inline(c, s)}</th>`).join("");
            const rows = b.rows.map(r => "<tr>" + r.map(c => `<td>${inline(c, s)}</td>`).join("") + "</tr>").join("");
            return spacer(top) + `<table cellspacing="0" cellpadding="${pad}" style="border-collapse:collapse; border-color:${s.border}; border-style:solid; border-width:1px"><tr>${head}</tr>${rows}</table>`;
        }
        return `<p style="margin-top:${px(top)}; margin-bottom:${px(bottom)}">${inline(b.text, s)}</p>`;
    });
    return `<div style="color:${s.text}">${html.join("")}</div>`;
}
