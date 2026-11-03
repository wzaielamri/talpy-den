// Code and changes as the chat pane shows them, for both front ends (Plasma's
// codehtml.mjs makes Qt rich text of them; the VS Code extension's webview
// draws them itself): a unified diff's lines as numbered rows, those rows
// side by side (before | after), the part of a changed line that changed,
// the lines Claude's Read tool gave back, and light syntax colors (keywords,
// strings, comments, numbers, calls) by the file's extension.
// Plain ES2017 (it runs in Qt's JavaScript too): no ?. or ??, no lookbehind.

// ---------------------------------------------------------------- diffs

const HUNK = /^@@(?: -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)?)? @@ ?(.*)$/;

// A unified diff's lines ("@@ -a,b +c,d @@", " same", "-old", "+new", and
// notes such as "… (12 more lines)") as rows: {kind: 'hunk' | 'same' | 'del'
// | 'add' | 'note', old, new (line numbers, null where there is none, or all
// null when the @@ lines carry none: "@@ @@"), text}. A hunk's text is what
// follows its @@ (a function's name).
export function diffRows(lines) {
    const rows = [];
    let a = 0, b = 0, numbered = false;
    for (const l of lines || []) {
        const h = HUNK.exec(l);
        if (h) {
            numbered = h[1] !== undefined;
            a = numbered ? Number(h[1]) : 0;
            b = numbered ? Number(h[2]) : 0;
            // (a hunk that adds to an empty file starts at 0,0: its first line is 1)
            if (numbered && a === 0)
                a = 1;
            if (numbered && b === 0)
                b = 1;
            rows.push({ kind: 'hunk', old: null, new: null, text: h[3] || '' });
            continue;
        }
        const c = l.charAt(0);
        if (c === '+')
            rows.push({ kind: 'add', old: null, new: numbered ? b++ : null, text: l.slice(1) });
        else if (c === '-')
            rows.push({ kind: 'del', old: numbered ? a++ : null, new: null, text: l.slice(1) });
        else if (c === ' ')
            rows.push({ kind: 'same', old: numbered ? a++ : null, new: numbered ? b++ : null, text: l.slice(1) });
        else
            rows.push({ kind: 'note', old: null, new: null, text: l });
    }
    return rows;
}

// Rows side by side: [{left, right}] (a row or null each), a run of removed
// lines next to the run of added ones that follows it, a hunk or a note
// across both (as left and right)
export function splitRows(rows) {
    const out = [];
    let dels = [], adds = [];
    const flush = () => {
        for (let i = 0; i < Math.max(dels.length, adds.length); i++)
            out.push({ left: dels[i] || null, right: adds[i] || null });
        dels = [];
        adds = [];
    };
    for (const r of rows) {
        if (r.kind === 'del') {
            if (adds.length)
                flush();
            dels.push(r);
        } else if (r.kind === 'add') {
            adds.push(r);
        } else {
            flush();
            out.push({ left: r, right: r });
        }
    }
    flush();
    return out;
}

// Pairs of a removed and an added line (index in rows → index of the other),
// the k-th line of a run of removed ones with the k-th of the added ones
// right after it, for changed(): only lines that look alike
export function pairs(rows) {
    const out = {};
    let i = 0;
    while (i < rows.length) {
        if (rows[i].kind !== 'del') {
            i++;
            continue;
        }
        let d = i;
        while (d < rows.length && rows[d].kind === 'del')
            d++;
        let e = d;
        while (e < rows.length && rows[e].kind === 'add')
            e++;
        for (let k = 0; k < Math.min(d - i, e - d); k++) {
            if (changed(rows[i + k].text, rows[d + k].text)) {
                out[i + k] = d + k;
                out[d + k] = i + k;
            }
        }
        i = e;
    }
    return out;
}

// What changed between two versions of a line: [start, end in a, end in b]
// (the same start and ends on both sides), or null when they share too
// little for it to be the same line changed
export function changed(a, b) {
    let s = 0;
    while (s < a.length && s < b.length && a.charAt(s) === b.charAt(s))
        s++;
    let ea = a.length, eb = b.length;
    while (ea > s && eb > s && a.charAt(ea - 1) === b.charAt(eb - 1)) {
        ea--;
        eb--;
    }
    // (out to whole words: half a word marked reads badly)
    while (s > 0 && /\w/.test(a.charAt(s - 1)) && /\w/.test(a.charAt(s)))
        s--;
    while (ea < a.length && /\w/.test(a.charAt(ea)) && ea > 0 && /\w/.test(a.charAt(ea - 1)))
        ea++;
    while (eb < b.length && /\w/.test(b.charAt(eb)) && eb > 0 && /\w/.test(b.charAt(eb - 1)))
        eb++;
    const kept = s + (a.length - ea);
    const longer = Math.max(a.trim().length, b.trim().length);
    if (longer === 0 || kept < longer * 0.35 || (ea === s && eb === s))
        return null;
    return [s, ea, eb];
}

// ---------------------------------------------------------------- Read's lines

const READ_LINE = /^\s*(\d+)(?:\t|→)(.*)$/;

// The lines Read gave back ("    12\tcode" or "12→code") as [{no, text}],
// or null when they aren't numbered (an image, a PDF, an error)
export function readLines(output) {
    const lines = (output || '').split('\n');
    const out = [];
    for (const l of lines) {
        const m = READ_LINE.exec(l);
        if (m)
            out.push({ no: Number(m[1]), text: m[2] });
        else if (l === '…' && out.length)
            out.push({ no: null, text: '…' });
        else if (l.trim() !== '' && !out.length)
            return null;
    }
    return out.length ? out : null;
}

// ---------------------------------------------------------------- syntax colors

const EXT = {
    js: 'js', mjs: 'js', cjs: 'js', jsx: 'js', ts: 'js', tsx: 'js', mts: 'js', cts: 'js', qml: 'js', vue: 'js', svelte: 'js',
    json: 'json', jsonl: 'json', py: 'py', pyi: 'py', sh: 'sh', bash: 'sh', zsh: 'sh', fish: 'sh',
    c: 'c', h: 'c', cc: 'c', cpp: 'c', cxx: 'c', hpp: 'c', hh: 'c', m: 'c', java: 'c', kt: 'c', kts: 'c', scala: 'c',
    cs: 'c', swift: 'c', dart: 'c', php: 'c', go: 'c', rs: 'c', zig: 'c',
    css: 'css', scss: 'css', less: 'css', html: 'html', htm: 'html', xml: 'html', svg: 'html', ui: 'html',
    yml: 'yaml', yaml: 'yaml', toml: 'yaml', ini: 'yaml', cfg: 'yaml', conf: 'sh', rb: 'rb', lua: 'lua', sql: 'sql',
    md: 'md', markdown: 'md'
};
const NAMES = { Makefile: 'sh', Dockerfile: 'sh', CMakeLists: 'sh', '.bashrc': 'sh', '.zshrc': 'sh', '.profile': 'sh' };

// A code block's language, by the name after its ``` (python, bash, ts…), as language()
const FENCES = {
    python: 'py', python3: 'py', py3: 'py', shell: 'sh', console: 'sh', shellsession: 'sh', zsh: 'sh', bash: 'sh', sh: 'sh',
    javascript: 'js', typescript: 'js', node: 'js', golang: 'c', rust: 'c', kotlin: 'c', csharp: 'c', 'c++': 'c', objc: 'c',
    ruby: 'rb', jsonc: 'json', json5: 'json', yml: 'yaml', dockerfile: 'sh', makefile: 'sh', diff: '', text: '', plain: ''
};
export function fenceLanguage(name) {
    const n = String(name || '').toLowerCase();
    return FENCES[n] !== undefined ? FENCES[n] : EXT[n] || '';
}

// The language of a file (by its extension), '' for one without colors
export function language(path) {
    const name = String(path || '').split('/').pop();
    if (NAMES[name] !== undefined)
        return NAMES[name];
    const dot = name.lastIndexOf('.');
    return dot > 0 ? EXT[name.slice(dot + 1).toLowerCase()] || '' : '';
}

const words = s => {
    const out = {};
    for (const w of s.split(' '))
        out[w] = 1;
    return out;
};
const JS = 'break case catch class const continue debugger default delete do else export extends finally for function if import in '
    + 'instanceof let new return super switch this throw try typeof var void while with yield async await of from as get set static '
    + 'interface type enum implements readonly private public protected declare namespace abstract keyof '
    + 'property signal required alias component pragma';
const C = 'auto break case char const continue default do double else enum extern float for goto if int long register return short '
    + 'signed sizeof static struct switch typedef union unsigned void volatile while class public private protected new delete this '
    + 'namespace using template typename virtual override final bool string import package func var type interface map chan go defer '
    + 'select range fn let mut pub impl use mod match trait where crate self Self val fun when object throws throw try catch finally '
    + 'extends implements super instanceof async await';
const SPEC = {
    js: { kw: words(JS), lit: words('true false null undefined NaN Infinity'), line: '//', block: ['/*', '*/'], quotes: '\'"`' },
    c: { kw: words(C), lit: words('true false null nullptr nil NULL None'), line: '//', block: ['/*', '*/'], quotes: '\'"`' },
    json: { kw: {}, lit: words('true false null'), line: '', block: null, quotes: '"', keys: true },
    py: { kw: words('and as assert async await break class continue def del elif else except finally for from global if import in is '
                    + 'lambda nonlocal not or pass raise return try while with yield match case print'),
          lit: words('True False None self cls'), line: '#', block: null, quotes: '\'"' },
    sh: { kw: words('if then else elif fi for while until do done case esac function in return local export set unset exit '
                    + 'source alias echo cd shift trap readonly declare eval exec'),
          lit: words('true false'), line: '#', block: null, quotes: '\'"', vars: true },
    rb: { kw: words('alias and begin break case class def do else elsif end ensure for if in module next not or redo rescue retry '
                    + 'return self super then unless until when while yield require'),
          lit: words('true false nil'), line: '#', block: null, quotes: '\'"' },
    lua: { kw: words('and break do else elseif end for function goto if in local not or repeat return then until while'),
           lit: words('true false nil'), line: '--', block: null, quotes: '\'"' },
    sql: { kw: words('select from where insert into update delete join left right inner outer on group by order limit as and or '
                     + 'not is create table index values set primary key references drop alter add distinct having union all '
                     + 'SELECT FROM WHERE INSERT INTO UPDATE DELETE JOIN LEFT RIGHT INNER OUTER ON GROUP BY ORDER LIMIT AS AND OR '
                     + 'NOT IS CREATE TABLE INDEX VALUES SET PRIMARY KEY REFERENCES DROP ALTER ADD DISTINCT HAVING UNION ALL'),
           lit: words('null true false NULL TRUE FALSE'), line: '--', block: ['/*', '*/'], quotes: '\'"' },
    css: { kw: words('important media import from to and not only'), lit: {}, line: '', block: ['/*', '*/'], quotes: '\'"' },
    yaml: { kw: {}, lit: words('true false null yes no on off True False'), line: '#', block: null, quotes: '\'"', keys: true },
    html: { kw: {}, lit: {}, line: '', block: ['<!--', '-->'], quotes: '"\'', tags: true },
    md: { kw: {}, lit: {}, line: '', block: null, quotes: '`', md: true }
};

const IDENT = /[A-Za-z_$][\w$]*/g;
const NUMBER = /(?:0[xX][\da-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)[a-zA-Z]*/g;

function at(re, text, i) {
    re.lastIndex = i;
    const m = re.exec(text);
    return m && m.index === i ? m[0] : '';
}

// A line as colored runs: [[kind, text], ...], kind '' (as is), 'kw'
// (keyword), 'lit' (true, null, self…), 'str', 'com' (comment), 'num',
// 'fn' (a name called or defined), 'key' (a JSON or YAML key, an HTML tag).
// state ({}), kept from line to line, carries a comment over lines.
export function highlight(text, lang, state) {
    const spec = SPEC[lang];
    if (!spec || text.length > 2000)
        return [['', text]];
    state = state || {};
    const out = [];
    const push = (kind, s) => {
        if (!s)
            return;
        const last = out[out.length - 1];
        if (last && last[0] === kind)
            last[1] += s;
        else
            out.push([kind, s]);
    };
    let i = 0;
    if (spec.md) {
        if (/^\s{0,3}#{1,6}\s/.test(text))
            return [['kw', text]];
        if (/^\s*([-*+]|\d+[.)])\s/.test(text)) {
            const m = /^\s*([-*+]|\d+[.)])/.exec(text);
            push('lit', m[0]);
            i = m[0].length;
        }
    }
    if (state.block) {
        const end = text.indexOf(spec.block[1]);
        if (end < 0)
            return [['com', text]];
        push('com', text.slice(0, end + spec.block[1].length));
        i = end + spec.block[1].length;
        state.block = false;
    }
    if (spec.keys) {   // (a key: its name colored, up to its colon)
        const m = /^(\s*-?\s*)("(?:[^"\\]|\\.)*"|[\w.$-]+)(\s*:)/.exec(text.slice(i));
        if (m && (lang === 'yaml' || m[2].charAt(0) === '"')) {
            push('', m[1]);
            push('key', m[2]);
            push('', m[3]);
            i += m[0].length;
        }
    }
    while (i < text.length) {
        const ch = text.charAt(i);
        const rest = text.slice(i);
        if (spec.line && rest.indexOf(spec.line) === 0 && (spec.line !== '#' || i === 0 || /\s/.test(text.charAt(i - 1)))) {
            push('com', rest);
            break;
        }
        if (spec.block && rest.indexOf(spec.block[0]) === 0) {
            const end = text.indexOf(spec.block[1], i + spec.block[0].length);
            if (end < 0) {
                push('com', rest);
                state.block = true;
                break;
            }
            push('com', text.slice(i, end + spec.block[1].length));
            i = end + spec.block[1].length;
            continue;
        }
        if (spec.quotes.indexOf(ch) >= 0) {
            let j = i + 1;
            while (j < text.length && text.charAt(j) !== ch)
                j += text.charAt(j) === '\\' ? 2 : 1;
            j = Math.min(text.length, j + 1);
            // (a JSON key, followed by its colon)
            const key = spec.keys && /^\s*:/.test(text.slice(j));
            push(key ? 'key' : 'str', text.slice(i, j));
            i = j;
            continue;
        }
        if (spec.tags && ch === '<') {
            const m = /^<\/?[\w:.-]+/.exec(rest);
            if (m) {
                push('key', m[0]);
                i += m[0].length;
                continue;
            }
        }
        if (spec.vars && ch === '$') {
            const m = /^\$(\{[^}]*\}|\w+|[@#?*!$-])/.exec(rest);
            if (m) {
                push('lit', m[0]);
                i += m[0].length;
                continue;
            }
        }
        if (/\d/.test(ch) && (i === 0 || !/[\w$]/.test(text.charAt(i - 1)))) {
            const n = at(NUMBER, text, i);
            if (n) {
                push('num', n);
                i += n.length;
                continue;
            }
        }
        const word = /[A-Za-z_$]/.test(ch) ? at(IDENT, text, i) : '';
        if (word) {
            const after = text.slice(i + word.length);
            const kind = spec.kw[word] === 1 ? 'kw' : spec.lit[word] === 1 ? 'lit'
                : /^\s*\(/.test(after) && !spec.keys && !spec.md ? 'fn' : '';
            push(kind, word);
            i += word.length;
            continue;
        }
        push('', ch);
        i++;
    }
    return out;
}
