// Claude's replies, rendered: the Markdown it writes (headings, lists, code
// blocks, tables, quotes, bold, italics, strikethrough, inline code, links),
// made into elements here, never into HTML text, so nothing in a reply can
// run or load anything in the page. What isn't understood shows as written.
// A code block has its language, its colors (codeview.mjs, as the widget's)
// and a Copy button (onCopy).

import type { ComponentChildren, JSX } from "preact";
import { fenceLanguage, highlight } from "../../vendor/codeview.mjs";

// A code block's text in its language's colors (.cv-kw…; as written for one without)
function colored(text: string, lang: string): ComponentChildren {
  const kind = fenceLanguage(lang);
  if (!kind || text.length > 200000) return text;
  const state = {};
  return text.split("\n").map((line, n) => [
    n ? "\n" : "",
    ...highlight(line, kind, state).map(([k, t], i) => (k ? <span key={`${n}.${i}`} class={`cv-${k}`}>{t}</span> : t)),
  ]);
}

const FENCE = /^(\s*)(```+|~~~+)\s*([^\s`]*)/;
const HEADING = /^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/; // (a closing run of # only after a space: C# stays)
const BULLET = /^(\s*)([-*+])\s+(.*)$/;
const NUMBERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const SAFE_LINK = /^(https?:|mailto:)/i;
const WORD = /\w/;
const MARK = /[^\w\s]/;

// Whether the marks around m (a **, __, *, _ or ~~ match ending at end) make
// emphasis, as in CommonMark: a closing mark comes after text and isn't
// written \*, no mark sits between punctuation and a word (f(*args, **kw)
// stays as written), and _ or __ only at words' edges (snake_case_names)
function emphasis(text: string, m: RegExpExecArray, end: number): boolean {
  const d = m[2] !== undefined || m[3] !== undefined || m[8] !== undefined ? 2 : 1;
  const before = m.index > 0 ? text[m.index - 1] : " ";
  const after = end < text.length ? text[end] : " ";
  const last = text[end - d - 1];
  if (last === "\\" || (MARK.test(text[m.index + d]) && WORD.test(before)) || (MARK.test(last) && WORD.test(after))) return false;
  return (m[3] === undefined && m[5] === undefined) || !(WORD.test(before) || WORD.test(after));
}

// Inline Markdown: `code`, **bold**, *italics* / _italics_, ~~struck~~, [links](url), bare web addresses
export function inline(text: string, key = "i"): ComponentChildren[] {
  const out: ComponentChildren[] = [];
  const pattern =
    /`([^`]+)`|\*\*(\S(?:.*?\S)?)\*\*|__(\S(?:.*?\S)?)__|\*([^*\s](?:[^*]*?[^*\s])?)\*|_([^_\s](?:[^_]*?[^_\s])?)_|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)|~~(\S(?:.*?\S)?)~~|(https?:\/\/(?:[^\s<>()]|\([^\s<>()]*\))*(?:[^\s<>().,;:!?'"]|\([^\s<>()]*\)))|\\([\\`*_{}\[\]()#+\-.!|~<>])/g;
  let last = 0;
  let n = 0;
  for (let m = pattern.exec(text); m; m = pattern.exec(text)) {
    if (m[1] === undefined && m[6] === undefined && m[9] === undefined && m[10] === undefined && !emphasis(text, m, pattern.lastIndex)) {
      pattern.lastIndex = m.index + 1; // (snake_case_names, *.py and *.js stay as they are)
      continue;
    }
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}-${n++}`;
    if (m[1] !== undefined) out.push(<code key={k}>{m[1]}</code>);
    else if (m[2] !== undefined || m[3] !== undefined) out.push(<strong key={k}>{inline(m[2] ?? m[3], k)}</strong>);
    else if (m[4] !== undefined || m[5] !== undefined) out.push(<em key={k}>{inline(m[4] ?? m[5], k)}</em>);
    else if (m[6] !== undefined) {
      const href = m[7];
      out.push(SAFE_LINK.test(href) ? <a key={k} href={href} title={href}>{inline(m[6], k)}</a> : <span key={k}>{inline(m[6], k)}</span>);
    } else if (m[8] !== undefined) out.push(<s key={k}>{inline(m[8], k)}</s>);
    else if (m[9] !== undefined) out.push(<a key={k} href={m[9]} title={m[9]}>{m[9]}</a>);
    else out.push(m[10]); // (\*, \_, \| …: the mark itself)
    last = pattern.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// A table line's cells: split at each | but one written \|, a | in its cell
function cells(line: string): string[] {
  const out = [""];
  const t = line.trim().replace(/^\|/, "");
  for (let i = 0; i < t.length; i++) {
    if (t[i] === "\\" && t[i + 1] === "|") out[out.length - 1] += t[++i];
    else if (t[i] === "|") out.push("");
    else out[out.length - 1] += t[i];
  }
  if (out.length > 1 && !out[out.length - 1].trim()) out.pop(); // (the line's closing |)
  return out.map((c) => c.trim());
}

type Item = { depth: number; ordered: boolean; start: number; text: string };

// List items as nested lists, as the Plasma pane shows them: a run of items
// at one depth (and of one kind) is an <ol>/<ul>, deeper items under an item
// a list of their own inside it
function lists(items: Item[], key: string): JSX.Element[] {
  const out: JSX.Element[] = [];
  for (let i = 0; i < items.length; ) {
    const { depth, ordered, start } = items[i];
    const lis: JSX.Element[] = [];
    while (i < items.length && items[i].depth === depth && items[i].ordered === ordered) {
      const k = `${key}-${i}`;
      let j = i + 1;
      while (j < items.length && items[j].depth > depth) j++;
      lis.push(
        <li key={k}>
          {inline(items[i].text, k)}
          {j > i + 1 ? lists(items.slice(i + 1, j), k) : null}
        </li>,
      );
      i = j;
    }
    const l = `${key}.${out.length}`;
    out.push(ordered ? <ol key={l} start={start}>{lis}</ol> : <ul key={l}>{lis}</ul>);
  }
  return out;
}

// Block Markdown: the reply as paragraphs, headings, lists, code blocks, …
export function Markdown({ text, onCopy }: { text: string; onCopy?: (code: string) => void }) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: JSX.Element[] = [];
  let para: string[] = [];
  let list: Item[] | null = null;
  const flushPara = () => {
    if (para.length) blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "), `p${blocks.length}`)}</p>);
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(...lists(list, `l${blocks.length}`));
    list = null;
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = FENCE.exec(line);
    if (fence) {
      flushPara();
      flushList();
      // (a block in a list item: its lines without the fence's indent)
      const body: string[] = [];
      for (i++; i < lines.length && !(lines[i].trim().startsWith(fence[2]) && !lines[i].trim().replace(/[`~]/g, "")); i++)
        body.push(lines[i].replace(/^[ \t]*/, (w) => w.slice(fence[1].length)));
      const code = body.join("\n");
      blocks.push(
        <div key={`c${blocks.length}`} class="md-codeblock">
          <div class="md-code-head">
            <span>{fence[3]}</span>
            {onCopy ? (
              <button type="button" class="md-copy" title="Copy this code" onClick={() => onCopy(code)}>
                Copy
              </button>
            ) : null}
          </div>
          <pre class="md-code cv">
            <code>{colored(code, fence[3])}</code>
          </pre>
        </div>,
      );
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
      const level = Math.min(6, heading[1].length + 2); // (smaller than the tab's own heading)
      const H = `h${level}` as "h3";
      blocks.push(<H key={`h${blocks.length}`} class={`md-heading md-h${heading[1].length}`}>{inline(heading[2], `h${blocks.length}`)}</H>);
      continue;
    }
    if (RULE.test(line) && !para.length) {
      flushList();
      blocks.push(<hr key={`r${blocks.length}`} />);
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      flushPara();
      flushList();
      const head = cells(line);
      const rows: string[][] = [];
      for (i += 2; i < lines.length && lines[i].includes("|") && lines[i].trim(); i++) rows.push(cells(lines[i]));
      i--;
      const t = blocks.length;
      blocks.push(
        <div key={`t${t}`} class="md-table">
          <table>
            <thead>
              <tr>{head.map((c, j) => <th key={j}>{inline(c, `t${t}h${j}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, k) => (
                <tr key={k}>{r.map((c, j) => <td key={j}>{inline(c, `t${t}r${k}c${j}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const quote = QUOTE.exec(line);
    if (quote) {
      flushPara();
      flushList();
      const body = [quote[1]];
      while (i + 1 < lines.length && QUOTE.test(lines[i + 1])) body.push(QUOTE.exec(lines[++i])![1]);
      blocks.push(<blockquote key={`q${blocks.length}`}>{inline(body.join(" "), `q${blocks.length}`)}</blockquote>);
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    if (bullet || numbered) {
      flushPara();
      const m = (bullet ?? numbered)!;
      const ordered = !!numbered;
      const depth = Math.floor(m[1].replace(/\t/g, "  ").length / 2);
      if (list && list[0].ordered !== ordered && depth === 0) flushList();
      (list ??= []).push({ depth, ordered, start: numbered ? Number(numbered[2]) : 1, text: m[3] });
      continue;
    }
    if (list && /^\s{2,}\S/.test(line)) {
      // (a list item that goes on on the next line)
      list[list.length - 1].text += " " + line.trim();
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushPara();
  flushList();
  return <div class="md">{blocks}</div>;
}
