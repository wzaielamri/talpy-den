// What a command printed in Claude's terminal (pane.py's commands.py keeps
// its ANSI colours), as Talpy Chat shows it under the command, for both
// front ends (Plasma's CommandOutput.qml makes Qt rich text of it; the VS
// Code extension's webview draws the runs itself): its colour codes (SGR:
// the 16 colours, 256 and true colour, bold, dim, italic, underline,
// inverse) as runs of text with one look each; every other escape (a cursor
// move, a title) left out.
// Plain ES2017 (it runs in Qt's JavaScript too): no ?. or ??, no lookbehind.

const ESCAPE = /\x1b(?:\[([0-9;:?]*)([A-Za-z])|\[[0-9;:?]*$|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_]?)/g;
const CUBE = [0, 95, 135, 175, 215, 255];

// The 16 colours, as a terminal draws them on a dark and on a light background
export const DARK = ["#3b3b3b", "#f0726a", "#6bcf7f", "#e5c07b", "#6eaaf2", "#c895e8", "#5fc9d6", "#c8c8c8",
                     "#7a7a7a", "#ff8f87", "#8fe39f", "#f2d58f", "#94c2f7", "#dbb2f2", "#86dbe6", "#ffffff"];
export const LIGHT = ["#2b2b2b", "#c4372c", "#2e8a3e", "#9a6d00", "#2563c9", "#8a3fb3", "#1b8394", "#6b6b6b",
                      "#5c5c5c", "#de4a3f", "#3aa14d", "#b38300", "#3a7ae0", "#a352cc", "#239fb3", "#3b3b3b"];

function hex2(n) {
    const s = Math.max(0, Math.min(255, n | 0)).toString(16);
    return s.length < 2 ? "0" + s : s;
}

// The colour of 256-colour number n (0–15: the 16, from palette)
export function color256(n, palette) {
    if (n < 16)
        return (palette || DARK)[n];
    if (n < 232) {
        const i = n - 16;
        return "#" + hex2(CUBE[Math.floor(i / 36)]) + hex2(CUBE[Math.floor(i / 6) % 6]) + hex2(CUBE[i % 6]);
    }
    const g = 8 + (n - 232) * 10;
    return "#" + hex2(g) + hex2(g) + hex2(g);
}

// The look SGR codes give (a copy of style, changed)
function apply(style, codes, palette) {
    const s = Object.assign({}, style);
    for (let i = 0; i < codes.length; i++) {
        const c = codes[i];
        if (c === 0) {
            s.fg = s.bg = "";
            s.bold = s.dim = s.italic = s.underline = s.inverse = false;
        } else if (c === 1) s.bold = true;
        else if (c === 2) s.dim = true;
        else if (c === 3) s.italic = true;
        else if (c === 4) s.underline = true;
        else if (c === 7) s.inverse = true;
        else if (c === 22) s.bold = s.dim = false;
        else if (c === 23) s.italic = false;
        else if (c === 24) s.underline = false;
        else if (c === 27) s.inverse = false;
        else if (c >= 30 && c <= 37) s.fg = palette[c - 30];
        else if (c >= 90 && c <= 97) s.fg = palette[c - 90 + 8];
        else if (c >= 40 && c <= 47) s.bg = palette[c - 40];
        else if (c >= 100 && c <= 107) s.bg = palette[c - 100 + 8];
        else if (c === 39) s.fg = "";
        else if (c === 49) s.bg = "";
        else if (c === 38 || c === 48) {
            let color = "";
            if (codes[i + 1] === 5 && i + 2 < codes.length) {
                color = color256(codes[i + 2], palette);
                i += 2;
            } else if (codes[i + 1] === 2 && i + 4 < codes.length) {
                color = "#" + hex2(codes[i + 2]) + hex2(codes[i + 3]) + hex2(codes[i + 4]);
                i += 4;
            } else {
                break;   // (malformed: the rest of it is left out)
            }
            if (c === 38) s.fg = color;
            else s.bg = color;
        }
    }
    return s;
}

// [{text, fg, bg (#rrggbb, "": the text's own), bold, dim, italic,
// underline, inverse}], new lines kept in the text
export function runs(text, palette) {
    const pal = palette || DARK;
    const out = [];
    let style = { fg: "", bg: "", bold: false, dim: false, italic: false, underline: false, inverse: false };
    let at = 0;
    const push = (t) => {
        if (!t)
            return;
        const last = out.length ? out[out.length - 1] : null;
        if (last && last.fg === style.fg && last.bg === style.bg && last.bold === style.bold && last.dim === style.dim
                && last.italic === style.italic && last.underline === style.underline && last.inverse === style.inverse)
            last.text += t;
        else
            out.push(Object.assign({ text: t }, style));
    };
    const s = String(text || "");
    ESCAPE.lastIndex = 0;
    let m;
    while ((m = ESCAPE.exec(s)) !== null) {
        push(s.slice(at, m.index).replace(/[\x00-\x08\x0b-\x1f\x7f]/g, ""));
        at = ESCAPE.lastIndex;
        if (m[2] === "m")
            style = apply(style, (m[1] || "0").split(/[;:]/).map(x => x === "" ? 0 : Number(x)), pal);
    }
    push(s.slice(at).replace(/[\x00-\x08\x0b-\x1f\x7f]/g, ""));
    return out;
}

// The text without its escapes
export function plain(text) {
    return runs(text).map(r => r.text).join("");
}

function escapeHtml(t) {
    return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function mix(a, b, part) {   // (#rrggbb: part of a over b)
    const n = (h, i) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16);
    return "#" + [0, 1, 2].map(i => hex2(n(a, i) * part + n(b, i) * (1 - part))).join("");
}

// Qt rich text of it: {fg, bg (#rrggbb: the text's and its background's),
// dark}; dim is the colour half over the background (Qt's rich text has no
// opacity), inverse swaps the two
export function html(text, look) {
    const fg = look.fg, bg = look.bg;
    const out = [];
    for (const r of runs(text, look.dark ? DARK : LIGHT)) {
        let f = r.fg || fg, b = r.bg || "";
        if (r.inverse) {
            const was = f;
            f = b || bg;
            b = was;
        }
        if (r.dim)
            f = mix(f, b || bg, 0.55);
        const css = [];
        if (f !== fg)
            css.push("color:" + f);
        if (b)
            css.push("background-color:" + b);
        if (r.bold)
            css.push("font-weight:600");
        if (r.italic)
            css.push("font-style:italic");
        if (r.underline)
            css.push("text-decoration:underline");
        const t = escapeHtml(r.text).replace(/\n/g, "<br>");
        out.push(css.length ? '<span style="' + css.join(";") + '">' + t + "</span>" : t);
    }
    return '<p style="white-space:pre-wrap;margin:0">' + out.join("") + "</p>";
}
