// Types for sides.mjs, for the VS Code extension (TypeScript)

export interface Side {
    id: string;
    q: string;
    at: number;
    pick: "" | "sonnet" | "haiku";
    model: string;
    a?: string;
    done?: number;
    error?: string;
    synthetic?: boolean;
    pending?: boolean;
    since?: string;
    folded?: boolean;
    from?: { key: string; text: string; at: number; tokens: number; of: number };
}

export declare const SIDE_TITLE: string;
export declare const SIDE_BUTTON: string;
export declare const SIDE_TIP: string;
export declare const SIDE_EMPTY: string;
export declare const SIDE_PLACEHOLDER: string;
export declare const EXPLAIN_BUTTON: string;
export declare const EXPLAIN_TIP: string;
export declare const SIDE_PENDING: string;
export declare const SIDE_REMOVE: string;
export declare const SIDE_CLEAR: string;
export declare const SIDE_COPY: string;
export declare const SIDE_QUOTE: string;
export declare const SIDE_AGAIN: string;
export declare const SIDE_CLEAR_ASK: string;
export declare const SIDE_CLOSE: string;
export declare const SIDE_FOLD_TIP: string;
export declare const SIDE_UNFOLD_TIP: string;
export declare function foldedLine(q: string): string;
export declare const SIDE_PICK_TIP: string;
export declare const SIDE_ACTIONS: ("copy" | "quote" | "whole" | "remove")[];
export declare function sideModelLabel(s: Side | null | undefined): string;
export declare const SIDE_PICKS: { value: "" | "sonnet" | "haiku"; label: string }[];
export declare function pickLabel(pick: string): string;
export declare function explainQuestion(selected: string): string;
export declare function newerSides(sides: unknown, v: unknown, shownV: number): boolean;
export declare function sideState(s: Side | null | undefined): "pending" | "error" | "answered";
export declare const WARM_MS: number;
export declare function sideWarm(sides: Side[], pick: string, now: number, fromKey?: string): boolean;
export interface SidePart { key: string; text: string; at: number; tokens: number; of: number; }
export declare const SIDE_FROM_MENU: string;
export declare const SIDE_FROM_TIP: string;
export declare const SIDE_FROM_LINE: string;
export declare const SIDE_FROM_SHOW: string;
export declare const SIDE_WHOLE: string;
export declare const SIDE_WHOLE_TIP: string;
export declare const SIDE_ASK_WHOLE: string;
export declare const SIDE_FROM_COMPACTED: string;
export declare const SIDE_FROM_GONE: string;
export declare function fromNote(part: SidePart | null | undefined, warm: boolean): string;
export declare function sideSaw(s: Side | null | undefined): string;
export declare function tokensText(n: number): string;
export declare const SIDE_COST_TIP: string;
export declare function costNote(used: number, warm: boolean): string;
