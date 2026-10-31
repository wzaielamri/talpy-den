// Code and changes in a chat's tab, as the widget's pane shows them (the
// parsing is the widget's codeview.mjs, vendored): a diff with line numbers,
// + and −, tinted lines, the changed words marked and syntax colors, one
// line after the other or side by side (before | after) where the tab is
// wide enough; a file's lines as they are; a tool call's details (a command
// and what it printed, a file read's numbered lines, else what it was asked).

import type { ComponentChildren } from "preact";
import { useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { changed, diffRows, highlight, language, pairs, readLines, splitRows, type DiffRow } from "../../vendor/codeview.mjs";
import type { PaneItem } from "../../src/shared/pane";
import { I, Icon } from "../util/icons";

const TAB = "    ";

// A line of code as colored spans, mark [start, end) set off
function Code({ text, lang, state, mark }: { text: string; lang: string; state: { block?: boolean }; mark?: [number, number] | null }) {
  const runs = highlight(text.replace(/\t/g, TAB), lang, state);
  const out: ComponentChildren[] = [];
  let at = 0;
  runs.forEach(([kind, s], i) => {
    const cls = kind ? `cv-${kind}` : undefined;
    const end = at + s.length;
    if (mark && mark[0] < end && mark[1] > at) {
      const a = Math.max(0, mark[0] - at), b = Math.min(s.length, mark[1] - at);
      out.push(<span key={i} class={cls}>{s.slice(0, a)}<mark class="cv-word">{s.slice(a, b)}</mark>{s.slice(b)}</span>);
    } else {
      out.push(cls ? <span key={i} class={cls}>{s}</span> : s);
    }
    at = end;
  });
  return <>{out.length ? out : " "}</>;
}

// The marks of changed words: {row index: [start, end)}
function marksOf(rows: DiffRow[]): Record<number, [number, number]> {
  const pair = pairs(rows);
  const out: Record<number, [number, number]> = {};
  for (const k of Object.keys(pair)) {
    const i = Number(k), r = rows[i], o = rows[pair[i]];
    const del = r.kind === "del";
    const c = del ? changed(r.text.replace(/\t/g, TAB), o.text.replace(/\t/g, TAB)) : changed(o.text.replace(/\t/g, TAB), r.text.replace(/\t/g, TAB));
    if (c) out[i] = del ? [c[0], c[1]] : [c[0], c[2]];
  }
  return out;
}

// The rows a folded diff shows: max of them from just before its first change
function shown(rows: DiffRow[], max: number): { rows: DiffRow[]; more: number } {
  if (!max || rows.length <= max) return { rows, more: 0 };
  const first = rows.findIndex((r) => r.kind === "add" || r.kind === "del");
  const start = Math.max(0, Math.min(first - 1, rows.length - max));
  const kept = rows.slice(start, start + max);
  return { rows: kept, more: rows.slice(start + max).filter((r) => r.kind !== "hunk").length };
}

function useWidth(): [{ current: HTMLDivElement | null }, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    setWidth(el.clientWidth);
    const seen = new ResizeObserver(() => setWidth(el.clientWidth));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  return [ref, width];
}

// A diff (its unified lines). split: side by side where there's room (about
// 2 × 48 characters) and the change has both sides; onSplit: the switch in
// its corner (every diff follows it)
export function Diff({ lines, path = "", max = 0, split = false, onSplit }: {
  lines: string[];
  path?: string;
  max?: number;
  split?: boolean;
  onSplit?: (split: boolean) => void;
}) {
  const [ref, width] = useWidth();
  // (worked out again only for other lines, not when the tab is redrawn)
  const { all, marks, index } = useMemo(() => {
    const rows = diffRows(lines);
    return { all: rows, marks: marksOf(rows), index: new Map(rows.map((r, i) => [r, i])) };
  }, [lines]);
  const lang = language(path);
  const cut = shown(all, max);
  const twoSided = lines.some((l) => l.startsWith("-")) && lines.some((l) => l.startsWith("+"));
  const sideBySide = split && twoSided && width > 2 * 48 * 7.2;
  const left = {}, right = {}, one = {};
  const no = (n: number | null) => <span class="cv-no">{n ?? ""}</span>;
  const more = cut.more ? <div class="cv-note">… {cut.more} more</div> : null;
  return (
    <div class={`cv${sideBySide ? " cv-split" : ""}`} ref={ref}>
      {onSplit && twoSided ? (
        <button type="button" class="cv-switch" aria-label={split ? "One after the other" : "Side by side"}
          title={split ? "One after the other: changes as removed and added lines, one after the other." : "Side by side: changes as before | after, where the tab is wide enough."}
          onClick={(e) => { e.stopPropagation(); onSplit(!split); }}>
          <Icon name={split ? I.aboveBelow : I.sideBySide} />
        </button>
      ) : null}
      {sideBySide
        ? splitRows(cut.rows).map((p, i) => {
            const r = (p.left ?? p.right)!;
            if (r.kind === "hunk") return i > 0 || r.text ? <div key={i} class="cv-hunk cv-wide">{i > 0 ? "⋯ " : ""}{r.text}</div> : null;
            if (r.kind === "note") return <div key={i} class="cv-note cv-wide">{r.text}</div>;
            const side = (s: DiffRow | null, st: object, which: "old" | "new") =>
              s ? (
                <div class={`cv-half ${s.kind}`}>
                  {no(s[which])}
                  <span class="cv-code"><Code text={s.text} lang={lang} state={st} mark={marks[index.get(s) ?? -1]} /></span>
                </div>
              ) : <div class="cv-half cv-empty" />;
            return <div key={i} class="cv-pair">{side(p.left, left, "old")}{side(p.right, right, "new")}</div>;
          })
        : cut.rows.map((r, i) => {
            if (r.kind === "hunk") return i > 0 || r.text ? <div key={i} class="cv-hunk">{i > 0 ? "⋯ " : ""}{r.text}</div> : null;
            if (r.kind === "note") return <div key={i} class="cv-note">{r.text}</div>;
            return (
              <div key={i} class={`cv-row ${r.kind}`}>
                {no(r.kind === "del" ? r.old : r.new)}
                <span class="cv-mark">{r.kind === "add" ? "+" : r.kind === "del" ? "−" : " "}</span>
                <span class="cv-code"><Code text={r.text} lang={lang} state={one} mark={marks[index.get(r) ?? -1]} /></span>
              </div>
            );
          })}
      {more}
    </div>
  );
}

// A file's lines as they are, numbered from 1 (a "… (N more lines)" note last)
export function Listing({ lines, path = "", max = 0 }: { lines: string[]; path?: string; max?: number }) {
  const lang = language(path), st = {};
  const shownLines = max && lines.length > max ? lines.slice(0, max) : lines;
  return (
    <div class="cv">
      {shownLines.map((l, i) =>
        /^… \(\d+ more lines\)$/.test(l) ? <div key={i} class="cv-note">{l}</div> : (
          <div key={i} class="cv-row cv-plain"><span class="cv-no">{i + 1}</span><span class="cv-code"><Code text={l} lang={lang} state={st} /></span></div>
        ))}
      {max && lines.length > max ? <div class="cv-note">… {lines.length - max} more</div> : null}
    </div>
  );
}

// A tool call's details, unfolded
export function ToolDetail({ item, path }: { item: PaneItem; path: string }) {
  const name = item.name ?? "", input = item.input ?? "", output = item.output ?? "";
  const bad = item.status === "error";
  const out = output ? <div class={`cv-out${bad ? " bad" : ""}`}>{output}</div> : null;
  if (name === "Bash" && input.startsWith("$ ")) {
    const st = {};
    return (
      <div class="pane-tool-detail cv-detail">
        {input.slice(2).split("\n").map((l, k) => (
          <div key={k} class="cv-cmd"><span class="cv-prompt">{k ? "  " : "$ "}</span><Code text={l} lang="sh" state={st} /></div>
        ))}
        {out}
      </div>
    );
  }
  const read = name === "Read" && !bad ? readLines(output) : null;
  if (read) {
    const lang = language(path), st = {};
    return (
      <div class="pane-tool-detail cv-detail">
        <div class="cv">
          {read.map((l, i) => (
            <div key={i} class="cv-row cv-plain"><span class="cv-no">{l.no ?? ""}</span>
              <span class="cv-code">{l.no === null ? <span class="cv-note">{l.text}</span> : <Code text={l.text} lang={lang} state={st} />}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div class="pane-tool-detail cv-detail">
      {input.split("\n").filter((l) => l !== "").map((l, i) => {
        const k = /^([\w-]{1,40}): (.*)$/.exec(l);
        return <div key={i} class="cv-field">{k ? <><span class="cv-name">{k[1]}</span>{"  "}{k[2]}</> : l}</div>;
      })}
      {out}
    </div>
  );
}
