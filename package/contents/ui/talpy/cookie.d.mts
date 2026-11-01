// Types for cookie.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";

export interface CookieStage {
    width: number;
    ground: number;      // the floor, from the stage's top
    unit: number;        // px a box unit
    bodyWidth: number;
    bodyHeight: number;
    minX: number;        // where Talpy may be (its centre)
    maxX: number;
}

export type CookieWords = "spot" | "wake" | "gimme" | "cross" | "aww" | "yum";

export interface CookieHost {
    stage(): CookieStage;
    px(): number;
    moveTo(x: number): void;
    face(left: boolean): void;
    say(what: CookieWords, flavour: string): void;
    leaveHole(open: number): void;
    fillHole(): void;
    changed(): void;
    instant(): boolean;
}

export interface Cookie {
    x: number;        // its middle, stage px
    y: number;
    r: number;        // its radius, px
    scale: number;    // popping up: 0 to 1 (a little over on the way)
    angle: number;    // degrees, as it swings (and rocks as it lands)
    sx: number;       // squashed as it lands (1: round): draw it scaled so, its bottom where it is
    sy: number;
    held: boolean;    // in your hand
    flavour: string;  // choc double sprinkles ginger mint jam oat white (actions.mjs FLAVOURS)
}

// the cookie vanishing in a puff where it was (stop): draw drawPuff(ctx, p, flavour) there, at its size
export interface CookiePuff {
    x: number;        // its middle, stage px
    y: number;
    r: number;        // its radius, px
    flavour: string;
    p: number;        // 0 to 1
}

export class CookieGame {
    constructor(talpy: Talpy, host: CookieHost);
    readonly cookie: Cookie | null;
    readonly puff: CookiePuff | null;
    readonly on: boolean;        // something goes on: tick it
    readonly chasing: boolean;   // Talpy is on its feet after it: draw it live
    place(x: number, y: number): boolean;
    grab(x: number, y: number): boolean;
    drag(x: number, y: number): void;
    drop(): void;
    picked(): void;
    landed(): void;
    stop(): void;   // Playful Talpy turned off: the cookie vanishes in a puff (puff), Talpy digs in where he is
    tick(now: number): void;
}
