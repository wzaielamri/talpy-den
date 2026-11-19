// Types for games.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";
import type { CookieStage } from "./cookie.mjs";

export type GameWords = "got" | "fun" | "bump" | "best";
export type ScoredName = "run" | "dig";
export type GameName = "peekaboo" | ScoredName;

export interface GameStage extends CookieStage {
    height?: number;   // the stage's height, px (the run's: grown)
}

export interface GameHost {
    stage(): GameStage;
    px(): number;
    moveTo(x: number): void;
    say(what: GameWords): void;
    changed(): void;
    // a scored game's (Talpy's Run, Deep Dig; scored.mjs): its best so far
    // (metres), a new best, the stage taller for it (game.stageGu grid units,
    // its status faded) or back, and where they aren't offered
    best?(name: ScoredName): number;
    saveBest?(name: ScoredName, meters: number): void;
    grow?(on: boolean): void;
    runOk?(): boolean;
    face?(left: boolean): void;   // he turns (the run: towards what comes)
}

export interface GameHole {
    x: number;      // its middle, stage px
    open: number;   // 0 (shut) to 1
}

export type RunThingKind = "pebble" | "stone" | "pot" | "pebbles" | "hedgehog" | "stump" | "log" | "crow" | "crowHigh"
    | "tuft" | "cloud" | "cookie" | "plus" | "dust";

// What's on Talpy's way in a run (DECOR, a tuft of grass and a cloud, never hits)
export interface RunThing {
    kind: RunThingKind;
    x: number;        // its left, stage px
    y: number;        // its top, stage px
    w: number;
    h: number;
    frame: number;    // its picture, 0 to FRAMES[kind] - 1 (talpy.mjs: a bird's wings, a landing's puff)
    alpha?: number;   // drawn at that opacity (a "+10" fading), 1 when none
    air?: boolean;    // a cookie up where his jump takes him
    variant: number;  // its look: 0 to VARIANTS[kind] - 1
    slot: number;     // its own while it's there (0 to the game's slots - 1)
}

// [w, h, how high its bottom is] by his body's height
export const KINDS: Record<RunThingKind, [number, number, number]>;
export const VARIANTS: Partial<Record<RunThingKind, number>>;
export const DECOR: RunThingKind[];
export const GRAB: RunThingKind[];
export const SCORED: string[];   // the games with a score (scored.mjs): "run", "dig"

export interface Game {
    readonly name: GameName;
    readonly on: boolean;
    readonly holes: GameHole[];
    readonly state: string;
    start(now: number, wake?: boolean): void;
    tick(now: number): void;
    hit(): boolean;
    stop(): void;
    // a scored game's (Talpy's Run, Deep Dig; Peekaboo has none of these)
    readonly stageGu?: number;    // the stage's whole height while it's on, grid units
    readonly turn?: number;       // degrees he's turned (0 upright)
    readonly things?: RunThing[];
    readonly slots?: number;      // the things' slots used so far this game
    readonly lift?: number;       // px he's above the floor
    readonly digging?: boolean;
    readonly meters?: number;
    readonly best?: number;
    readonly newBest?: boolean;
    readonly hint?: "" | "start" | "dig";
    press?(what: "jump" | "dig"): void;
    release?(what: "dig"): void;
}

export const GAMES: GameName[];
export function pickGame(talpy: Talpy, host: GameHost, name?: GameName | ""): Game;
