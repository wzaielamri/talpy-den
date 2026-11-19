// Types for dig.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";
import type { GameHost } from "./games.mjs";
import { Scored } from "./scored.mjs";

export const DIG_KINDS: Record<string, [number, number]>;
export const DIG_VARIANTS: Record<string, number>;
export const MOVE: { omega: number; top: number; accel: number; lean: number; leanOmega: number; keys: number };
export const LAYERS: [number, string][];

export interface DigRow {
    readonly id: number;
    readonly top: number;
    readonly bottom: number;
    readonly gapL: number;
    readonly gapR: number;
    readonly beetle: boolean;
}

export class Dig extends Scored {
    constructor(talpy: Talpy, host: GameHost);
    readonly x: number;     // his middle, stage px
    readonly vx: number;    // px a second
    readonly cy: number;    // his body's middle, stage px from the top
    readonly soil: string;  // the earth's colour here, '#rrggbb'
    readonly layer: "topsoil" | "clay" | "rock";
    readonly rows: DigRow[];
    aim(x: number): void;
    press(what: "left" | "right" | "jump"): void;
    release(what: "left" | "right"): void;
}
