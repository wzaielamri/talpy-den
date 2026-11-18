// Types for games.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";
import type { CookieStage } from "./cookie.mjs";

export type GameWords = "got" | "fun" | "bump" | "best";
export type GameName = "peekaboo" | "run";

export interface GameStage extends CookieStage {
    height?: number;   // the stage's height, px (the run's: grown)
}

export interface GameHost {
    stage(): GameStage;
    px(): number;
    moveTo(x: number): void;
    say(what: GameWords): void;
    changed(): void;
    // the run's (Talpy's Run): the best so far (metres), a new best, the
    // stage taller for it (its status faded) or back, and where it isn't offered
    best?(): number;
    saveBest?(meters: number): void;
    grow?(on: boolean): void;
    runOk?(): boolean;
}

export interface GameHole {
    x: number;      // its middle, stage px
    open: number;   // 0 (shut) to 1
}

export type RunThingKind = "pebble" | "stone" | "pot" | "pebbles" | "crow" | "crowHigh" | "tuft";

// What's on Talpy's way in a run (a tuft is only grass: it never hits)
export interface RunThing {
    kind: RunThingKind;
    x: number;      // its left, stage px
    y: number;      // its top, stage px
    w: number;
    h: number;
    frame: number;  // 0 or 1 (a crow's wings)
}

export interface Game {
    readonly name: GameName;
    readonly on: boolean;
    readonly holes: GameHole[];
    readonly state: string;
    start(now: number, wake?: boolean): void;
    tick(now: number): void;
    hit(): boolean;
    stop(): void;
    // the run's (name "run"; Peekaboo has none of these)
    readonly things?: RunThing[];
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
