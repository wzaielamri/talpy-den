// Code and changes as Qt rich text, for the chat pane and the asks
// (DiffView.qml, ChatPane.qml): a diff with line numbers, + and −, tinted
// lines, the changed words marked and syntax colors, one line after the
// other (paragraphs, quick to lay out) or side by side (a table, made only
// when asked for); a tool call's details: a command and what it printed,
// the lines a file read gave back, numbered, or what it was asked. Every
// bit of text is escaped. The parsing is codeview.mjs (shared with the VS
// Code extension). Plain ES2017 (see markdown.mjs).
//
// p (a palette): {mono, pt, text, muted, faint (line numbers), bg, addBg,
// addWord, delBg, delWord, add, del (the + and − marks), hunkBg, bad,
// syntax: {kw, lit, str, com, num, fn, key}}: colors as "#rrggbb".

import { diffRows, splitRows, pairs, changed, highlight, language, readLines } from "./codeview.mjs";

// ---------------------------------------------------------------- colors

function rgb(hex) {
    const n = parseInt(String(hex).replace("#", "").slice(-6), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// k of color b over color a, as "#rrggbb"
function mix(a, b, k) {
    const x = rgb(a), y = rgb(b);
    return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * k).toString(16).padStart(2, "0")).join("");
}

// The palette for a theme: text and bg (what the code sits on) as
// "#rrggbb"; green and red tints over bg, syntax colors as GitHub's.
// advance: a mono character's width at the code's size (pt × 0.88), in px,
// as FontMetrics measures it (else about that, at 96 dpi)
export function palette(dark, text, bg, mono, pt, advance) {
    const green = dark ? "#2ea043" : "#2da44e", red = dark ? "#f85149" : "#cf222e";
    return {
        mono: mono, pt: pt, text: text, bg: bg, advance: advance || pt * 0.88 * 1.333 * 0.6,
        muted: mix(bg, text, 0.62), faint: mix(bg, text, 0.38), hunkBg: mix(bg, text, dark ? 0.07 : 0.05),
        addBg: mix(bg, green, dark ? 0.2 : 0.12), addWord: mix(bg, green, dark ? 0.45 : 0.32),
        delBg: mix(bg, red, dark ? 0.2 : 0.1), delWord: mix(bg, red, dark ? 0.45 : 0.27),
        add: dark ? "#56d364" : "#1a7f37", del: dark ? "#f47067" : "#cf222e", bad: dark ? "#f47067" : "#cf222e",
        syntax: syntaxColors(dark)
    };
}

// The syntax colors, as GitHub's (also a reply's code blocks: markdown.mjs)
export function syntaxColors(dark) {
    return dark ? { kw: "#ff7b72", lit: "#79c0ff", str: "#a5d6ff", com: "#8b949e", num: "#79c0ff", fn: "#d2a8ff", key: "#7ee787" }
                : { kw: "#cf222e", lit: "#0550ae", str: "#0a3069", com: "#6e7781", num: "#0550ae", fn: "#8250df", key: "#116329" };
}

// ---------------------------------------------------------------- html

function escape(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function family(name) {
    return /^[\w-]+$/.test(name) ? name : `'${name.replace(/'/g, "")}'`;
}

const TAB = "    ";

// A line of code as colored spans; mark [start, end) gets the background markBg
function codeSpans(text, lang, state, p, mark, markBg) {
    text = text.replace(/\t/g, TAB);
    const runs = highlight(text, lang, state);
    let out = "", at = 0;
    for (const run of runs) {
        const color = run[0] ? p.syntax[run[0]] : "";
        const open = color ? `<span style="color:${color}">` : "";
        const close = color ? "</span>" : "";
        let s = run[1];
        const end = at + s.length;
        if (mark && mark[0] < end && mark[1] > at) {   // (the marked part of this run)
            const a = Math.max(0, mark[0] - at), b = Math.min(s.length, mark[1] - at);
            out += open + escape(s.slice(0, a)) + `<span style="background-color:${markBg}">${escape(s.slice(a, b))}</span>`
                + escape(s.slice(b)) + close;
        } else {
            out += open + escape(s) + close;
        }
        at = end;
    }
    return out || "&nbsp;";
}

function number(n, width) {
    const s = n === null || n === undefined ? "" : String(n);
    return "&nbsp;".repeat(Math.max(0, width - s.length)) + s;
}

function widthOf(rows) {
    let most = 1;
    for (const r of rows)
        most = Math.max(most, String(r.old === null ? "" : r.old).length, String(r.new === null ? "" : r.new).length);
    return most;
}

// The marks of changed words: {row index: [start, end)}
function marksOf(rows) {
    const pair = pairs(rows), out = {};
    for (const k in pair) {
        const i = Number(k), j = pair[k];
        const r = rows[i], o = rows[j];
        const c = r.kind === "del" ? changed(r.text.replace(/\t/g, TAB), o.text.replace(/\t/g, TAB))
                                   : changed(o.text.replace(/\t/g, TAB), r.text.replace(/\t/g, TAB));
        if (c)
            out[i] = r.kind === "del" ? [c[0], c[1]] : [c[0], c[2]];
    }
    return out;
}

// The rows a folded diff shows: max of them from just before its first change
function shown(rows, max) {
    if (!max || rows.length <= max)
        return { rows: rows, more: 0 };
    const first = rows.findIndex(r => r.kind === "add" || r.kind === "del");
    const start = Math.max(0, Math.min(first - 1, rows.length - max));
    const kept = rows.slice(start, start + max);
    return { rows: kept, more: rows.slice(start + max).filter(r => r.kind !== "hunk").length };
}

// A diff's lines (unified, as pane.py and the asks give them), one after the
// other: number, mark, code, wrapped lines under the code. max: rows shown
// (0: all), the rest counted
export function diffHtml(lines, path, p, max) {
    const all = diffRows(lines);
    const marks = marksOf(all);
    const lang = language(path);
    const cut = shown(all, max);
    const w = widthOf(cut.rows);
    const numbered = cut.rows.some(r => r.old !== null || r.new !== null);
    const em = p.advance;
    const lead = numbered ? w + 3 : 2;   // characters before the code (number, space, mark, space)
    const state = {};
    let html = "";
    cut.rows.forEach((r, i) => {
        if (r.kind === "hunk") {
            if (i > 0 || r.text)
                html += `<p style="margin:0px; background-color:${p.hunkBg}; color:${p.muted}; white-space:pre-wrap">${"&nbsp;".repeat(lead)}`
                    + `${i > 0 ? "⋯ " : ""}${escape(r.text)}</p>`;
            return;
        }
        if (r.kind === "note") {
            html += `<p style="margin:0px; color:${p.muted}; white-space:pre-wrap">${"&nbsp;".repeat(lead)}<i>${escape(r.text)}</i></p>`;
            return;
        }
        const bg = r.kind === "add" ? p.addBg : r.kind === "del" ? p.delBg : "";
        const mark = r.kind === "add" ? `<span style="color:${p.add}">+</span>` : r.kind === "del" ? `<span style="color:${p.del}">−</span>` : "&nbsp;";
        const n = numbered ? `<span style="color:${p.faint}">${number(r.kind === "del" ? r.old : r.new, w)}</span>&nbsp;` : "";
        html += `<p style="margin:0px; margin-left:${Math.round(lead * em)}px; text-indent:-${Math.round(lead * em)}px; white-space:pre-wrap${bg ? "; background-color:" + bg : ""}">`
            + n + mark + "&nbsp;" + codeSpans(r.text, lang, state, p, marks[i], r.kind === "add" ? p.addWord : p.delWord) + "</p>";
    });
    if (cut.more)
        html += `<p style="margin:0px; color:${p.muted}">${"&nbsp;".repeat(lead)}<i>… ${cut.more} more</i></p>`;
    return `<div style="font-family:${family(p.mono)}; font-size:${(p.pt * 0.88).toFixed(1)}pt; color:${p.text}">${html}</div>`;
}

// The same, before | after, in a table (made when asked for)
export function splitHtml(lines, path, p, max) {
    const all = diffRows(lines);
    const marks = marksOf(all);
    const index = new Map(all.map((r, i) => [r, i]));
    const lang = language(path);
    const cut = shown(all, max);
    const w = widthOf(cut.rows);
    const left = {}, right = {};
    const numPx = Math.round((w + 1.5) * p.pt * 1.333 * 0.88 * 0.62);   // (the numbers' column: digits never wrap)
    const side = (r, st, which) => {
        if (!r)
            return `<td bgcolor="${p.hunkBg}" width="${numPx}"></td><td bgcolor="${p.hunkBg}" width="50%"></td>`;
        const bg = r.kind === "add" ? p.addBg : r.kind === "del" ? p.delBg : p.bg;
        const no = which === "left" ? r.old : r.new;
        return `<td bgcolor="${bg}" width="${numPx}" style="color:${p.faint}; white-space:nowrap">${number(no, w)}&nbsp;</td>`
            + `<td bgcolor="${bg}" width="50%" style="white-space:pre-wrap">${codeSpans(r.text, lang, st, p, marks[index.get(r)],
                                                                                        r.kind === "add" ? p.addWord : p.delWord)}</td>`;
    };
    let html = "";
    splitRows(cut.rows).forEach((pair, i) => {
        const r = pair.left || pair.right;
        if (r.kind === "hunk") {
            if (i > 0 || r.text)
                html += `<tr><td colspan="5" bgcolor="${p.hunkBg}" style="color:${p.muted}">&nbsp;${i > 0 ? "⋯ " : ""}${escape(r.text)}</td></tr>`;
            return;
        }
        if (r.kind === "note") {
            html += `<tr><td></td><td colspan="4" style="color:${p.muted}"><i>${escape(r.text)}</i></td></tr>`;
            return;
        }
        html += "<tr>" + side(pair.left, left, "left") + `<td bgcolor="${p.faint}" width="1"></td>` + side(pair.right, right, "right") + "</tr>";
    });
    if (cut.more)
        html += `<tr><td></td><td colspan="4" style="color:${p.muted}"><i>… ${cut.more} more</i></td></tr>`;
    return `<table width="100%" cellspacing="0" cellpadding="0" style="font-family:${family(p.mono)}; font-size:${(p.pt * 0.88).toFixed(1)}pt; color:${p.text}">${html}</table>`;
}

// Numbered lines of code ([{no, text}], no null: a note)
function listingLines(lines, path, p) {
    const w = Math.max(1, ...lines.map(l => String(l.no === null ? "" : l.no).length));
    const lang = language(path), st = {};
    const em = p.advance;   // (before the code: number and two spaces)
    return lines.map(l => `<p style="margin:0px; margin-left:${Math.round((w + 2) * em)}px; text-indent:-${Math.round((w + 2) * em)}px; white-space:pre-wrap">`
        + `<span style="color:${p.faint}">${number(l.no, w)}</span>&nbsp;&nbsp;${l.no === null ? `<i style="color:${p.muted}">${escape(l.text)}</i>`
                                                                                     : codeSpans(l.text, lang, st, p, null, "")}</p>`).join("");
}

// A file's lines as they are (no earlier version to compare with), numbered
// from 1; one starting with "… (" is the note of how many more there are
export function listingHtml(lines, path, p, max) {
    let rows = lines.map((l, i) => /^… \(\d+ more lines\)$/.test(l) ? { no: null, text: l } : { no: i + 1, text: l });
    if (max && rows.length > max)
        rows = rows.slice(0, max).concat([{ no: null, text: `… ${rows.length - max} more` }]);
    return `<div style="font-family:${family(p.mono)}; font-size:${(p.pt * 0.88).toFixed(1)}pt; color:${p.text}">${listingLines(rows, path, p)}</div>`;
}

// Lines of output, as they came (an error's in red)
function outputHtml(text, p, color) {
    return text.split("\n").map(l => `<p style="margin:0px; white-space:pre-wrap; color:${color}">${escape(l.replace(/\t/g, TAB)) || "&nbsp;"}</p>`).join("");
}

// A tool call's details, unfolded: a command and what it printed, the
// numbered lines a file read gave back (in the file's colors), else what it
// was asked (name: value) and what came back
export function toolHtml(item, path, p) {
    const name = item.name || "", input = item.input || "", output = item.output || "";
    const bad = item.status === "error";
    const gap = `<p style="margin:0px; font-size:4pt">&nbsp;</p>`;
    let html = "";
    if (name === "Bash" && input.indexOf("$ ") === 0) {
        const st = {};
        html += input.slice(2).split("\n").map((l, k) => `<p style="margin:0px; white-space:pre-wrap"><span style="color:${p.muted}">${k ? "&nbsp;&nbsp;" : "$&nbsp;"}</span>`
            + codeSpans(l, "sh", st, p, null, "") + "</p>").join("");
        if (output)
            html += gap + outputHtml(output, p, bad ? p.bad : p.muted);
    } else if (name === "Read" && !bad && readLines(output)) {
        html += listingLines(readLines(output), path, p);
    } else {
        const fields = input.split("\n").map(l => {
            const k = /^([\w-]{1,40}): (.*)$/.exec(l);
            return `<p style="margin:0px; white-space:pre-wrap">` + (k ? `<span style="color:${p.muted}">${escape(k[1])}</span>&nbsp;&nbsp;${escape(k[2])}` : escape(l)) + "</p>";
        });
        html += input ? fields.join("") : "";
        if (output)
            html += (input ? gap : "") + outputHtml(output, p, bad ? p.bad : p.muted);
    }
    return `<div style="font-family:${family(p.mono)}; font-size:${(p.pt * 0.88).toFixed(1)}pt; color:${p.text}">${html}</div>`;
}
