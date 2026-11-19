// Types for scored.mjs, for the VS Code extension's webview (TypeScript)

import type { Talpy } from "./talpy.mjs";
import type { GameHost, RunThing, RunThingKind, ScoredName } from "./games.mjs";

export const RUN_END_MS: number;
export const RUN_AGAIN_MS: number;
export const BONUS: number;
export const SCORED: string[];
export const DECOR: RunThingKind[];
export const GRAB: RunThingKind[];

export class Scored {
    constructor(talpy: Talpy, host: GameHost, name: ScoredName, stageGu: number);
    readonly name: ScoredName;
    readonly on: boolean;
    readonly things: RunThing[];
    readonly slots: number;
    readonly state: string;
    readonly stageGu: number;
    readonly lift: number;
    readonly turn: number;
    readonly meters: number;
    readonly best: number;
    readonly newBest: boolean;
    start(now: number): void;
    tick(now: number): void;
    hit(): boolean;
    stop(): void;
}
