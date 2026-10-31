// Types for games.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";
import type { CookieStage } from "./cookie.mjs";

export type GameWords = "got" | "fun";

export interface GameHost {
    stage(): CookieStage;
    px(): number;
    moveTo(x: number): void;
    say(what: GameWords): void;
    changed(): void;
}

export interface GameHole {
    x: number;      // its middle, stage px
    open: number;   // 0 (shut) to 1
}

export interface Game {
    readonly name: string;
    readonly on: boolean;
    readonly holes: GameHole[];
    readonly state: string;
    start(now: number, wake?: boolean): void;
    tick(now: number): void;
    hit(): boolean;
    stop(): void;
}

export const GAMES: string[];
export function pickGame(talpy: Talpy, host: GameHost): Game;
