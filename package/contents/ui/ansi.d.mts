// Types for ansi.mjs, for the VS Code extension's webview (TypeScript)

export interface AnsiRun {
    text: string;
    fg: string; // #rrggbb, or "": the text's own
    bg: string;
    bold: boolean;
    dim: boolean;
    italic: boolean;
    underline: boolean;
    inverse: boolean;
}

export const DARK: readonly string[];
export const LIGHT: readonly string[];
export function color256(n: number, palette?: readonly string[]): string;
export function runs(text: string, palette?: readonly string[]): AnsiRun[];
export function plain(text: string): string;
export function html(text: string, look: { fg: string; bg: string; dark: boolean }): string;
