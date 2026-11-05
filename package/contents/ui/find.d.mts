// Types for find.mjs, for the VS Code extension (TypeScript)

export interface FindItem {
    kind: string;
    key: string;
    text?: string;
    line?: string;
    name?: string;
    summary?: string;
    status?: string;
    input?: string;
    output?: string;
    diff?: string[];
    command?: { shell?: boolean; output?: string; error?: boolean };
    asked?: { state: string; questions?: { header: string; question: string; options: { label: string; description?: string }[] }[]; plan?: string; title?: string };
}
export interface Fold {
    shown: string;
    at: number;
    more: number;
}
export interface FindHit {
    key: string;
    n: number;
    hidden: boolean;
}

export const FOLD_LINES: number;
export const FOLD_SHOWN: number;
export function foldOf(text: string | undefined | null, how?: "markdown" | "plain" | "ansi"): Fold | null;
export function plainOf(md: string | undefined | null): string;
export function findParts(it: FindItem, steps: boolean): [string, string];
export function findIn(items: readonly FindItem[], query: string, steps: boolean, from?: number, budget?: number, hits?: FindHit[]): { hits: FindHit[]; next: number };
export function findCount(total: number, at: number, done: boolean): string;
export function findStep(hits: readonly FindHit[], at: number, back: boolean, view: { first: number; last: number; order: ReadonlyMap<string, number> }): number;
export function nthIn(text: string, query: string, n: number): [number, number] | null;
export function allIn(text: string, query: string, max?: number): [number, number][];
