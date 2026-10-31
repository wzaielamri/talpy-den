// Types for talpy.mjs, for the VS Code extension's webview (TypeScript)

export interface TalpyColors {
    skin: string;
    shade: string;
}

export interface TalpyTheme {
    fx: string;    // particles, z's, notes
    text: string;  // the words it says
}

export const BOX: number;
export const FLOOR: number;
export const TOP: number;
export const LILAC: TalpyColors;
export function calmColors(tint: string): TalpyColors;
export function drawHole(ctx: unknown, hole: number): void;   // an empty hole in the 64 × 64 box (hole: 0 to 1.1, as it opens or closes)
// the open hole's back or front, turned left or not, in the 64 × 64 box (for Talpy.holeImage)
export function drawHoleSide(ctx: unknown, part: "back" | "front", left: boolean): void;
// a cookie (the one it eats) of a flavour (cookie.mjs: Cookie.flavour), 5.6 box units round, centred at the context's origin
export function drawCookie(ctx: unknown, flavour?: string): void;

// A film's picture of it (Talpy.still), see films.mjs
export interface Still {
    readonly key: string;
    readonly pose: string;
    readonly phase: number;
    readonly rest: boolean;
    readonly left: boolean;
    readonly every: number;   // ms from one picture of its move to the next (Infinity at rest)
}

export class Talpy {
    constructor(opts?: { colors?: TalpyColors; theme?: TalpyTheme; words?: (s: string) => string; travels?: boolean; brain?: boolean; playful?: boolean });
    onTravel: ((ms: number) => void) | null;
    onTravelStop: (() => void) | null;   // a move cut short while it tunnels: it stops where it is
    facingLeft: boolean;
    travels: boolean;
    readonly busy: boolean;
    readonly holeOpen: boolean;   // its burrow is open or opening under it
    readonly onFloor: boolean;    // out of its burrow on the floor, as drawn now
    readonly frameMs: number;   // how often a picture is worth drawing now: 40 (quick moves), 80 (slow) or 200 (at rest)
    readonly run: unknown;
    readonly mood: string;
    readonly held: boolean;
    readonly tugging: boolean;   // you pull at it, it hangs on to its burrow (tug)
    readonly chasing: boolean;   // after a cookie (cookie.mjs): on its feet, the host moves it
    readonly now: number;
    readonly settled: boolean;   // what's eased between poses is where it's going
    // the open hole's back or front drawn by drawHoleSide on a sheet the size of the canvas, at the
    // canvas's transform: copied in (half of a picture's cost); null: drawn
    holeImage: ((part: "back" | "front", left: boolean) => CanvasImageSource) | null;
    setColors(colors: TalpyColors): void;
    setTheme(theme: TalpyTheme): void;
    setMood(mood: string): void;
    playful: boolean;
    setPlayful(on: boolean): void;
    // pushed down into its burrow (a drag that starts downward): false if it isn't in it;
    // still (less motion): down at once. It pushes back, and gives in when you push on
    // (pushTo: true then); let go: 'down' (it had given in), 'boing' (it springs back up), 'up' (needs)
    pushing: boolean;
    readonly gaveIn: boolean;
    push(still?: boolean): boolean;
    pushTo(down: number): boolean;
    pushed(needs: boolean, done?: (ok: boolean) => void): "" | "down" | "boing" | "up";
    react(name: string, done?: ((ok: boolean) => void) | null): void;
    // you pull at it: in its burrow it hangs on for a moment, then done(true) (take it: setHeld);
    // false: it isn't in its burrow, take it at once
    tug(done?: ((ok: boolean) => void) | null): boolean;
    tugToward(dx: number, dy: number): void;   // where your hand is from its middle (box units, right +, down +): it leans that way
    letGo(done?: ((ok: boolean) => void) | null): void;   // you let go before it came out: back in it drops
    setHeld(held: boolean): number;   // how much of its hole it leaves behind (0 to 1): draw that where it was, drawHole
    // height in box units; stayOut: it doesn't dig in (a cookie is out: it goes after it)
    land(height: number, done?: ((ok: boolean) => void) | null, stayOut?: boolean): "sick" | "dizzy" | "fine";
    pose(step?: Record<string, unknown>): void;
    // a cookie (cookie.mjs drives these)
    seeCookie(look: [number, number], done?: ((ok: boolean) => void) | null): void;
    chase(): number;   // how much of its hole it leaves behind, as setHeld
    chaseAs(pose: "out" | "run" | "stand" | "beg" | "leap" | "reach" | "pout", look?: [number, number]): void;
    eat(flavour: string, caught: boolean, done?: ((ok: boolean) => void) | null): void;
    tick(now: number): void;
    draw(ctx: unknown, withoutParticles?: boolean): void;
    drawParticles(ctx: unknown, now: number): void;
    particles(now: number): 0 | 1 | 2;   // nothing flies about, only z's, quicker things
    still(frameMs: number, maxFrames: number, clockMs?: number): Still | null;
    drawFilm(ctx: unknown, d: Still, from: Still | null, p: number): void;
    // a picture instead of every frame: what it shows ("pose#details": fade over to a new pose), and the picture
    stillKey(): string;
    drawStill(ctx: unknown): void;
}
