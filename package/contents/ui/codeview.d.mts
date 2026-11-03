// Types for codeview.mjs, for the VS Code extension's webview (TypeScript)

export interface DiffRow {
    readonly kind: "hunk" | "same" | "del" | "add" | "note";
    readonly old: number | null;
    readonly new: number | null;
    readonly text: string;
}

export type Run = [kind: "" | "kw" | "lit" | "str" | "com" | "num" | "fn" | "key", text: string];

export function diffRows(lines: readonly string[]): DiffRow[];
export function splitRows(rows: readonly DiffRow[]): { left: DiffRow | null; right: DiffRow | null }[];
export function pairs(rows: readonly DiffRow[]): Record<number, number>;
export function changed(a: string, b: string): [start: number, endA: number, endB: number] | null;
export function readLines(output: string): { no: number | null; text: string }[] | null;
export function language(path: string): string;
export function fenceLanguage(name: string): string;
export function highlight(text: string, lang: string, state?: { block?: boolean }): Run[];
