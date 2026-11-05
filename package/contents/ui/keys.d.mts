// Types for keys.mjs, for the VS Code extension (TypeScript)

export type KeyWhere = "plasma" | "vscode";
export interface PaneKey {
    id: string;
    group: string;
    plasma: string;
    vscode: string;
    what: string;
    commands?: [string, string][]; // [command, its default keybinding]
}
export type EscTarget = "" | "menu" | "big" | "list" | "find" | "help" | "ghost" | "stop";

export const KEY_GROUPS: readonly string[];
export const KEYS: readonly PaneKey[];
export const ESC_ORDER: readonly Exclude<EscTarget, "">[];
export function keyOf(id: string): PaneKey | null;
export function keyText(id: string, where: KeyWhere, mac?: boolean): string;
export function withKey(title: string, id: string, where: KeyWhere, mac?: boolean): string;
export function escTarget(open: Partial<Record<Exclude<EscTarget, "">, unknown>>): EscTarget;
