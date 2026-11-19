// Talpy: the pet that lives in a burrow. One creature for the Plasma widget,
// the GNOME extension and the VS Code extension: each host calls tick(now)
// and draw(ctx) on its own 2D canvas (QML Canvas, Cairo through an adapter,
// an HTML canvas) and moves it around its stage.
//
//   const t = new Talpy({ colors, words: s => i18n(s), travels: true });
//   t.setMood('working');          // idle working agents needs done failed limit error loading
//   t.react('pet');                // an action now (see actions.mjs)
//   t.tug(ok => ...);              // you pull at it: it holds on to its burrow, then comes out
//   t.push(still, givesIn); t.pushTo(down); t.pushed(needs, done)  // you push it down: it pushes back, then gives in
//   t.onTravel = ms => { ... };    // it dug in: move it to its new spot within ms
//   t.onTravelStop = () => { ... }; // (optional) cut short under way: it stops where it is
//   every frame: t.tick(Date.now()); then draw(ctx) in a 64 × 64 box, floor at y = 57
//
// Pulled at in its burrow (tug), it hangs on to the rim for a moment first;
// while you hold it (setHeld) nothing else moves it; land() drops it, and it
// digs back in where it landed.
//
// Plain ES2017 (see paths.mjs).

import * as art from './art.mjs';
import { traceEllipse, traceRoundRect } from './paths.mjs';
import { ACTIONS, COOKIE, FLAVOURS, MOODS, PUSH, TUG, TUG_MS, dirt, random } from './actions.mjs';

export const BOX = 64;
export const FLOOR = 57;     // where the stage's floor is, in the box
export const TOP = 2;        // the lamp's top (highest pose), for room above
export const LILAC = art.LILAC;
export const calmColors = art.calmColors;

const KEYS = ['eyes', 'mouth', 'arms', 'plume', 'body', 'prop', 'tail', 'blush', 'think', 'orbit', 'walk', 'held', 'sip',
              'fail', 'depth', 'tunnel', 'hole', 'lamp', 'gum', 'bite', 'treat'];
const DEPTH = { out: -0.5, high: 6, half: 10, low: 13, peek: 19, hidden: 42, gone: 74 };
const ARMS = { rest: [16, -16], up: [150, -150], hold: [16, 35], sip: [16, 62], both: [-50, 50], chin: [16, 60], scratch: [16, -165],
               ear: [16, 153], scope: [16, -164], sign: [16, -150], balloon: [150, -16], cover: [-101, 101], juggle: [-20, 20],
               type: [-38, 38], held: [60, -60], wave: [16, -145], waveboth: [145, -145], dance: [90, -90], flail: [70, -70], throw: [16, -140],
               selfie: [16, -152], rim: [44, -44], horn: [16, 75], scoop: [10, -10] };
const BLINKING = { open: 1, wide: 1, sad: 1, tired: 1, wink: 1 };
// How often a picture is worth drawing (frameMs): quick moves want 25 a
// second, slow ones 12; at rest (breathing, the lamp's glow) 5 show it all.
// What's eased towards where it's going, and how much it moves in a tick
// (40 ms) to count as a quick move (a twentieth of it: a slow one). Sleepy
// z's float up slowly enough for 5, and a sleepy slump too.
const EASED = { depth: 0.3, hole: 0.02, armL: 1.5, armR: 1.5, armLy: 0.1, armRy: 0.1, plume: 3, lx: 0.08, ly: 0.08, sip: 0.05 };
// Pushed down (push), it hangs on and pushes back: it sinks less the further
// you push (PUSH_SOFT box units of your hand take it about two thirds of the
// way to PUSH_MOST of the way down), shoving up against your hand every
// PUSH_HEAVE_MS, and follows your hand on a spring (PUSH_HZ, PUSH_DAMP: a
// little bouncy). As a tug takes TUG_MS, it gives in and ducks all the way
// once your hand has held it at least PUSH_HOLD units down for TUG_MS (back
// above that, the time starts again), or at once when your hand has gone
// PUSH_GIVE units
const PUSH_GIVE = 40;
const PUSH_HOLD = 6;
const PUSH_SOFT = 22;
const PUSH_MOST = 0.25;   // (its eyes still show, mostly)
const PUSH_HEAVE_MS = 760;
const PUSH_HZ = 2.6;
const PUSH_DAMP = 0.38;
const QUICK_BODY = { hop: 1, jump: 1, bounce: 1, wiggle: 1, shake: 1, spin: 1, jolt: 1, shiver: 1, tumble: 1, land: 1, bob: 1, tug: 1 };
const RESTING_BODY = { slump: 1 };   // (as slow as breathing)
const QUICK_PROPS = { phone: 1, juggle: 1 };
const SLOW_PROPS = { gum: 1, magnifier: 1 };

// ---------------------------------------------------------------- easing

const clamp01 = x => Math.max(0, Math.min(1, x));
const lerp = (a, b, p) => a + (b - a) * p;
const sine = p => 0.5 - 0.5 * Math.cos(Math.PI * p);           // ease in-out
const alt = (ms, period) => sine((ms / period) % 2 > 1 ? 2 - (ms / period) % 2 : (ms / period) % 2);
const outBack = p => {
    const c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
};
// value at p along [[pos, value], ...] (eased between frames)
function kf(p, frames) {
    if (p <= frames[0][0])
        return frames[0][1];
    for (let i = 1; i < frames.length; i++) {
        if (p <= frames[i][0]) {
            const a = frames[i - 1], b = frames[i];
            return lerp(a[1], b[1], sine((p - a[0]) / Math.max(1e-6, b[0] - a[0])));
        }
    }
    return frames[frames.length - 1][1];
}
const ease = (kind, p) => kind === 'in' ? p * p : kind === 'linear' ? p : 1 - (1 - p) * (1 - p);

// ---------------------------------------------------------------- body moves

// What a body move does at ms into it: whole (x, y, rotation about an
// origin) and torso (scale, rotation about its base). null: it's over.
function bodyMove(name, ms, it) {
    const once = (T, n) => ms < T * (n || 1) ? (ms % T) / T : null;
    const m = { wx: 0, wy: 0, wr: 0, ox: 32, oy: 57, sx: 1, sy: 1, tr: 0, ty: 0, torso: false };
    let p;
    switch (name) {
    case 'hop': case 'jump':
        p = once(name === 'hop' ? 550 : 800, it);
        if (p === null)
            return null;
        m.wy = kf(p, [[0, 0], [0.45, name === 'hop' ? -8 : -14], [0.8, 0], [1, 0]]);
        m.sx = kf(p, [[0, 1.06], [0.2, 0.95], [0.7, 1], [0.85, 1.07], [1, 1]]);
        m.sy = kf(p, [[0, 0.94], [0.2, 1.06], [0.7, 1], [0.85, 0.93], [1, 1]]);
        m.torso = true;
        return m;
    case 'bounce': m.wy = kf((ms % 420) / 420, [[0, 0], [0.5, -4], [1, 0]]); return m;
    case 'wiggle': m.wr = lerp(-6, 6, alt(ms, 180)); return m;
    case 'shake': m.wr = lerp(-6, 6, alt(ms, 90)); return m;
    case 'sway': m.wr = lerp(-10, 10, alt(ms, 500)); return m;
    case 'spin':
        p = once(1100);
        if (p === null)
            return null;
        if (ms < 700)
            m.wy = kf(ms / 700, [[0, 0], [0.45, -8], [0.8, 0], [1, 0]]);
        m.sx = kf(p, [[0, 1], [0.3, 1.04], [0.6, 0.98], [1, 1]]);
        m.sy = kf(p, [[0, 1], [0.3, 0.97], [0.6, 1.03], [1, 1]]);
        m.torso = true;
        m.turn = p;
        return m;
    case 'stretch':
        p = Math.min(1, ms / 1300);
        m.sx = kf(p, [[0, 1], [0.35, 0.92], [0.8, 0.92], [1, 1]]);
        m.sy = kf(p, [[0, 1], [0.35, 1.13], [0.8, 1.13], [1, 1]]);
        m.torso = true;
        return m;
    case 'bow':          // a little bow, hands together: down, a beat, up
        p = Math.min(1, ms / 1200);
        m.sx = kf(p, [[0, 1], [0.3, 1.05], [0.7, 1.05], [1, 1]]);
        m.sy = kf(p, [[0, 1], [0.3, 0.86], [0.7, 0.86], [1, 1]]);
        m.tr = kf(p, [[0, 0], [0.3, 6], [0.7, 6], [1, 0]]);
        m.ty = kf(p, [[0, 0], [0.3, 2.6], [0.7, 2.6], [1, 0]]);
        m.torso = true;
        return m;
    case 'tug':          // pulled at, hanging on: trembling (drawn out of its burrow: Talpy.stretch, see draw)
        p = sine(Math.min(1, ms / TUG_MS));
        m.wx = lerp(-0.6, 0.6, alt(ms, 60)) * p;
        m.torso = true;
        return m;
    case 'inhale':
        p = sine(Math.min(1, ms / 450));
        m.sx = lerp(1, 0.95, p);
        m.sy = lerp(1, 1.08, p);
        m.torso = true;
        return m;
    case 'jolt':
        p = once(400);
        if (p === null)
            return null;
        m.sx = kf(p, [[0, 0.95], [0.25, 1.14], [1, 1]]);
        m.sy = kf(p, [[0, 1.08], [0.25, 0.85], [1, 1]]);
        m.wx = kf(p, [[0, 0], [0.25, -3], [1, 0]]);
        m.torso = true;
        return m;
    case 'shiver': m.wx = lerp(-0.7, 0.7, alt(ms, 70)); return m;
    case 'nod':
        p = (ms % 1700) / 1700;
        m.tr = kf(p, [[0, 0], [0.45, 0], [0.72, 7], [0.8, 1], [1, 0]]);
        m.ty = kf(p, [[0, 0], [0.45, 0], [0.72, 1], [0.8, 0], [1, 0]]);
        m.torso = true;
        return m;
    case 'slump':
        p = (ms % 3600) / 3600;
        m.sx = kf(p, [[0, 1.05], [0.5, 1.07], [1, 1.05]]);
        m.sy = kf(p, [[0, 0.92], [0.5, 0.9], [1, 0.92]]);
        m.wy = 1;
        m.torso = true;
        return m;
    case 'tumble':
        p = once(1000);
        if (p === null)
            return null;
        m.oy = 40;
        m.wy = kf(p, [[0, 0], [0.25, -12], [0.75, -6], [1, 0]]);
        m.wr = kf(p, [[0, 0], [0.25, 0], [0.75, 340], [1, 360]]);
        return m;
    case 'float':
        m.wy = lerp(-6, -12, alt(ms, 1400));
        m.wr = lerp(-3, 3, alt(ms, 1400));
        m.shadow = 0.6;
        return m;
    case 'trip':
        p = Math.min(1, ms / 1500);
        m.ox = 47;
        m.wr = kf(p, [[0, 0], [0.12, -8], [0.32, 82], [0.7, 82], [1, 0]]);
        return m;
    case 'land':
        p = once(400);
        if (p === null)
            return null;
        m.sx = lerp(1.14, 1, sine(p));
        m.sy = lerp(0.84, 1, sine(p));
        m.torso = true;
        return m;
    case 'bob':
        p = (ms % 460) / 460;
        m.wr = kf(p, [[0, -2.5], [0.5, 2.5], [1, -2.5]]);
        m.wy = kf(p, [[0, 0], [0.5, -1.8], [1, 0]]);
        return m;
    default:
        return null;
    }
}

// The arms' angles for poses that move by themselves (null: a still pose)
function armMove(name, ms) {
    switch (name) {
    case 'wave': return [16, lerp(-120, -170, alt(ms, 380)), 0, 0];
    case 'waveboth': return [lerp(120, 170, alt(ms + 170, 340)), lerp(-120, -170, alt(ms, 340)), 0, 0];
    case 'sign': return [16, lerp(-138, -160, alt(ms, 500)), 0, 0];
    case 'type': {
        const l = alt(ms, 130), r = alt(ms + 130, 130);
        return [lerp(-38, -31, l), lerp(38, 31, r), -1.4 * l, -1.4 * r];
    }
    case 'juggle': return [lerp(-20, -6, alt(ms, 375)), lerp(20, 6, alt(ms + 190, 375)), -2 * alt(ms, 375), -2 * alt(ms + 190, 375)];
    case 'dance': return [lerp(30, 145, alt(ms, 500)), lerp(-145, -30, alt(ms, 500)), 0, 0];
    case 'flail': return [lerp(50, 95, alt(ms, 180)), lerp(-50, -95, alt(ms, 180)), 0, 0];
    case 'scoop': {   // (digging down: each paw from under him out to the side, one out as the other comes in)
        const l = alt(ms, 170), r = alt(ms + 170, 170);
        return [lerp(-20, 40, l), lerp(20, -40, r), -1.2 * l, -1.2 * r];
    }
    case 'scratch': return [16, lerp(-158, -172, alt(ms, 160)), 0, 0];
    case 'throw': return [16, kf(Math.min(1, ms / 550), [[0, -16], [0.35, 30], [0.75, -175], [1, -140]]), 0, 0];
    default: return null;
    }
}

function plumeAngle(name, ms, it) {
    switch (name) {
    case 'up': return -22;
    case 'droop': return 66;
    case 'bob': return kf((ms % 1100) / 1100, [[0, -9], [0.5, 11], [1, -9]]);
    case 'twirl': return ms < 800 * (it || 1) ? ((ms % 800) / 800) * 360 : 0;
    case 'flick': return ms < 400 ? kf(ms / 400, [[0, 0], [0.4, -45], [1, 0]]) : 0;
    case 'wild': return lerp(-24, 14, alt(ms, 160));
    default: return 0;
    }
}

// ---------------------------------------------------------------- stills

// A host may show a pet as pictures instead of drawing it every frame (each
// drawing costs; the widget does it for the chats' pets, the big one moves
// all the time; see pictures.mjs): stillKey() says what a picture of it shows
// now, drawStill() draws that picture, settled. A quick move goes round four
// pictures, a beat each: one end of its swing, halfway, the other end,
// halfway back (the beats below: ms from one end to the other). A beat is a
// quarter of the quickest move's round, in whole steps of BEAT_MS, so all
// pets change pictures on the same ticks (each costs a window). A big move
// has no picture: one that happens once (a jump, a spin), a long way in or out
// of the burrow, its hole opening or closing; stillKey() is '' until it's over
// and what flew off meanwhile has landed, and the host draws it live.
const BEAT_MS = 140;
const ARM_BEATS = { wave: 380, waveboth: 340, sign: 500, type: 130, juggle: 375, dance: 500, flail: 180, scratch: 160, scoop: 170 };
const BODY_BEATS = { bounce: 210, bob: 230, wiggle: 180, shake: 90, sway: 500, shiver: 70, nod: 1200, float: 1400 };
const PLUME_BEATS = { bob: 550, wild: 160 };
const PROP_BEATS = { phone: 78, juggle: 250 };   // (its prop's own motion)
const TUNNEL_BEAT = 260;
const ONE_WAY = { waveboth: 1, juggle: 1, nod: 1, phone: 1 };   // (halfway back doesn't look like halfway there)
const ONCE = { hop: 550, jump: 800, spin: 1100, jolt: 400, tumble: 1000, land: 400 };   // (ms; a hop or a jump × it)
const BIG_DEPTH = 8;   // (from low to high is no big move, from half to peeking out is)
// A film (films.mjs) plays a quick move as it is, round after round: each of
// its pictures drawn once. What's eased between poses settles within
// SETTLE_MS (the arms in about four of their 70 ms); TWEENED is what moves
// between two pictures of a film when a pose changes.
// A move that happens once and isn't big (a stretch, a throw, a twirl of the
// lamp) has no pictures either: a film draws it live (ms it takes, × it).
const SETTLE_MS = 280;
const TWEENED = ['depth', 'armL', 'armR', 'armLy', 'armRy', 'plume', 'lx', 'ly', 'sip'];
const ONE_SHOT = { body: { stretch: 1300, inhale: 450, trip: 1500, bow: 1200, tug: TUG_MS }, arms: { throw: 550 }, plume: { flick: 400, twirl: 800 } };

// ---------------------------------------------------------------- the hole

// The hole as it opens or closes (hole 0 to 1.1, a little over at the end of
// opening), the back of it or the front: the creature is drawn between them
function holePart(ctx, hole, part) {
    const size = Math.min(1.1, hole);
    ctx.save();
    art.about(ctx, 32, 56, 0, lerp(0.05, 1, size), lerp(0.2, 1, size));
    ctx.globalAlpha = clamp01(hole);
    part(ctx);
    ctx.restore();
}

// An empty hole in the 64 × 64 box (hole as above), for what a host keeps
// where a creature you hold was pulled out of it (setHeld)
export function drawHole(ctx, hole) {
    holePart(ctx, hole, art.holeBack);
    holePart(ctx, hole, art.holeFront);
}

// The open hole's back or front ('back', 'front'), turned left or not, in
// the 64 × 64 box: a host may draw these once on sheets of their own and
// give them to Talpy (holeImage): half of what drawing it costs is its hole
export function drawHoleSide(ctx, part, left) {
    ctx.save();
    if (left) {
        ctx.translate(BOX, 0);
        ctx.scale(-1, 1);
    }
    holePart(ctx, 1, part === 'front' ? art.holeFront : art.holeBack);
    ctx.restore();
}

// A cookie (the one it eats) of that flavour (actions.mjs FLAVOURS), 5.6
// units round, centred at the context's origin: a host draws the one it goes
// after with this (cookie.mjs)
export function drawCookie(ctx, flavour) {
    ctx.save();
    ctx.translate(-32, -47.4);
    art.propFront(ctx, 'cookie', 0, 0, { bite: 0, treat: flavour || '' });
    ctx.restore();
}

// The cookie vanishing where it is (CookieGame.stop), p from 0 to 1: it
// shrinks away into a puff of dust that swells and fades, a few crumbs
// flying off; drawn as drawCookie (its middle at the origin, 5.6 its radius),
// reaching about three times as far
const PUFF_DUST = ['#b5a48b', '#9e8c72', '#c7b8a2'];
export function drawPuff(ctx, p, flavour) {
    p = clamp01(p);
    const s = 1 - p / 0.3;
    if (s > 0) {
        ctx.save();
        ctx.scale(s, s);
        drawCookie(ctx, flavour);
        ctx.restore();
    }
    const out = 1 - (1 - p) * (1 - p), dust = 0.8 * (1 - p) * Math.min(1, p / 0.12);
    for (let i = 0; i < 7; i++) {
        const a = 0.4 + i * 2 * Math.PI / 7, d = 1.5 + 8 * out, r = (2.4 + 0.8 * (i % 3)) * (0.5 + 0.9 * out);
        art.ellipse(ctx, Math.cos(a) * d, Math.sin(a) * d * 0.75 - 3 * out, r, r * 0.9, PUFF_DUST[i % 3], dust);
    }
    for (let i = 0; i < 5; i++) {
        const a = 1.1 + i * 2 * Math.PI / 5, d = 3 + 11 * out;
        art.ellipse(ctx, Math.cos(a) * d, Math.sin(a) * d * 0.7 + 6 * p * p, 0.9, 0.7, '#8a6a4f', 1 - p);
    }
}

// What's on Talpy's way in a run (games.mjs Run's things), in its own w × h
// box, top left at the context's origin, in px (no transforms): a rock, a
// boulder, a flower pot (variant: its flower's colours), a hedgehog (its
// quills'), a heap of rocks, a tree stump, a log, a bird (which: a crow, a
// bluebird, a robin; frame: where its wings are in a flap, 0 to FLAP_FRAMES -
// 1; crowHigh the same birds higher up), a tuft of grass (its blades, one with
// a daisy), a cloud. What's in the way has ink outlines and shading, as
// Talpy's own things; the grass and the clouds go by behind, thin or faint
// and see-through, never taken for something to jump. Each is drawn once, as
// a picture the host moves (Pet.qml, pet.ts).
export const FLAP_FRAMES = 8;
// how many pictures a kind has (its frame: 0 to that − 1; a host keeps them all)
export const FRAMES = { crow: FLAP_FRAMES, crowHigh: FLAP_FRAMES, dust: 4, beetle: 4, worm: 4, cookie: 4 };
const COOKIE_FLAVOURS = Object.keys(FLAVOURS).map(f => f === 'choc' ? '' : f);   // (a cookie's variant: its flavour)
const CLAIM = '#f2c84b';   // a cookie's glow and its "+10": you get it
const ROCK = { base: '#a29b92', lit: '#cbc4ba', shade: '#7f7870', speck: '#6c665f' };
const POT = { body: '#c96f48', shade: '#a65a3a', rim: '#de8c63', rimLit: '#eba37f' };
const LEAF = { leaf: '#77a65c', vein: '#557f40', stem: '#5f8f48' };
const FLOWERS = [['#f08db0', '#f7d154'], ['#f6c945', '#c8742f'], ['#a9b6f2', '#f7d154'], ['#f6f2ea', '#f2c84b']];
// a crow, a bluebird, a robin: body, near wing, far wing, beak, breast ('' none)
const BIRDS = [['#2d2a3a', '#4a4560', '#1d1a28', '#f0a83a', ''], ['#4f7fd6', '#3a63b3', '#2c4c8c', '#f0a83a', '#f2efe6'],
               ['#7a6152', '#5e4a3e', '#45362d', '#f0c03a', '#ee7d45']];
const HEDGEHOGS = [['#6f5242', '#8d6c58'], ['#76737f', '#94919d']];   // quills, their lit top
const HEDGEHOG = { face: '#ead2ad', blush: '#f2a0a8' };
const WOOD = { bark: '#8a5e3c', shade: '#6b472c', line: '#5a3c25', cut: '#e4c28e', ring: '#b98f5a' };
const GRASS = { light: '#6f9a5a', dark: '#7fae63', daisy: '#ffffff', heart: '#f2c84b' };
const CLOUD = { light: '#ffffff', lightRim: '#aab6d6', dark: '#cdd3ec' };
// Deep Dig's buried things: a root (pale wood on the earth), a pipe, a bottle, a beetle; and what's
// only in the earth: specks, worms, crystals, clods
const ROOT = { wood: '#c39a6b', shade: '#9b7449', line: '#8a6a45', grain: '#dcbb8f' };
const PIPE = { steel: '#7f8c94', lit: '#a9b6bd', shade: '#5f6b72', ring: '#909ca3', rust: '#b0643a', inside: '#26221f' };
const BOTTLE = { glass: '#4f9a66', shine: '#cdeed6', shade: '#2f6b44', cork: '#c9a06b' };
const BEETLE = { shell: '#2f6a5a', lit: '#5ea58f', head: '#22302c' };
const SPECK = { stone: '#cfc6b8', shell: '#e6d7b8' };
const WORM = { skin: '#e8909f', band: '#cc6c7e' };
const CRYSTALS = [['#8ee0ef', '#3d97a8'], ['#c4a0f2', '#7a55b0']];
const CLOD = { earth: '#5b402b', lit: '#80603f' };
// Deep Dig's earth by depth: topsoil, clay from 100 m, rock from 300 m, each blended into over SOIL_BLEND m
export const SOIL = { topsoil: '#7a5634', clay: '#9a5a3c', rock: '#3c3443' };
const SOIL_AT = [[0, 'topsoil'], [100, 'clay'], [300, 'rock']];
const SOIL_BLEND = 30;
export function soilAt(m) {
    let i = 0;
    while (i + 1 < SOIL_AT.length && m >= SOIL_AT[i + 1][0])
        i++;
    const to = SOIL[SOIL_AT[i][1]];
    if (i === 0 || m >= SOIL_AT[i][0] + SOIL_BLEND)
        return to;
    const from = SOIL[SOIL_AT[i - 1][1]], p = 0.5 - 0.5 * Math.cos(Math.PI * (m - SOIL_AT[i][0]) / SOIL_BLEND);
    let out = '#';
    for (let c = 1; c < 7; c += 2) {
        const a = parseInt(from.slice(c, c + 2), 16), b = parseInt(to.slice(c, c + 2), 16);
        out += ('0' + Math.round(a + (b - a) * p).toString(16)).slice(-2);
    }
    return out;
}
const SHADOW = '#000000';
const DARK_RIM = '#d9d4ec';   // a dark thing's outline on a dark stage (a crow: ink on ink vanished)
function blob(ctx, cx, cy, rx, ry, color, lw, ink) {
    ctx.beginPath();
    traceEllipse(ctx, cx, cy, rx, ry);
    art.fill(ctx, color);
    art.stroke(ctx, ink || art.INK, lw);
}
// A cookie's shine: a soft glow round it and four
// little stars about it, twinkling by frame (0 to 3): one bright, one fading
function shine(ctx, w, h, f, color) {
    const r = Math.min(w, h) / 2;
    art.circle(ctx, w / 2, h / 2, r * 0.74, color, 0.26 + 0.08 * (f % 2));
    art.circle(ctx, w / 2, h / 2, r * 0.5, '#ffffff', 0.14);
    const spots = [[0.14, 0.2], [0.86, 0.3], [0.8, 0.86], [0.18, 0.78]];
    for (let i = 0; i < spots.length; i++) {
        const k = [1, 0.45, 0, 0.45][(i + f) % 4];   // (each in turn bright)
        if (k <= 0)
            continue;
        const sx = w * spots[i][0], sy = h * spots[i][1], sr = r * 0.2 * (0.6 + 0.4 * k);
        ctx.beginPath();
        ctx.moveTo(sx, sy - sr);
        ctx.lineTo(sx + sr * 0.28, sy - sr * 0.28);
        ctx.lineTo(sx + sr, sy);
        ctx.lineTo(sx + sr * 0.28, sy + sr * 0.28);
        ctx.lineTo(sx, sy + sr);
        ctx.lineTo(sx - sr * 0.28, sy + sr * 0.28);
        ctx.lineTo(sx - sr, sy);
        ctx.lineTo(sx - sr * 0.28, sy - sr * 0.28);
        ctx.closePath();
        art.fill(ctx, '#fff6cf', 0.55 + 0.45 * k);
    }
}
// a rounded box filled (alpha: its opacity)
function patch(ctx, x, y, w, h, r, color, alpha) {
    ctx.beginPath();
    traceRoundRect(ctx, x, y, w, h, r);
    art.fill(ctx, color, alpha);
}
// its shadow on the floor, along the box's bottom
function shadow(ctx, cx, w, h, alpha) {
    art.ellipse(ctx, cx, h - Math.max(1, h * 0.05), w / 2, Math.max(1, h * 0.05), SHADOW, alpha);
}
// A rock in (x, y, w, h): flat underneath, a lumpy top, lit from the top
// left, its right side in shade; crack: a crack down its face
function rock(ctx, x, y, w, h, lw, crack) {
    const X = f => x + f * w, Y = f => y + f * h;
    const outline = () => {
        ctx.beginPath();
        ctx.moveTo(X(0.05), Y(1));
        ctx.bezierCurveTo(X(0.0), Y(0.9), X(0.0), Y(0.7), X(0.03), Y(0.52));
        ctx.bezierCurveTo(X(0.06), Y(0.25), X(0.15), Y(0.06), X(0.36), Y(0.04));
        ctx.bezierCurveTo(X(0.5), Y(0.02), X(0.6), Y(0.0), X(0.74), Y(0.09));
        ctx.bezierCurveTo(X(0.9), Y(0.18), X(1.0), Y(0.4), X(0.99), Y(0.62));
        ctx.bezierCurveTo(X(0.99), Y(0.8), X(0.98), Y(0.94), X(0.95), Y(1));
        ctx.closePath();
    };
    outline();
    art.fill(ctx, ROCK.base);
    ctx.save();
    outline();
    ctx.clip();
    art.ellipse(ctx, X(0.95), Y(0.95), w * 0.5, h * 0.62, ROCK.shade);
    art.ellipse(ctx, X(0.32), Y(0.2), w * 0.3, h * 0.2, ROCK.lit);
    art.ellipse(ctx, X(0.62), Y(0.55), w * 0.04, h * 0.05, ROCK.speck);
    art.ellipse(ctx, X(0.38), Y(0.7), w * 0.035, h * 0.04, ROCK.speck);
    ctx.restore();
    outline();
    art.stroke(ctx, art.INK, lw);
    if (crack) {
        ctx.beginPath();
        ctx.moveTo(X(0.6), Y(0.08));
        ctx.lineTo(X(0.66), Y(0.3));
        ctx.lineTo(X(0.58), Y(0.45));
        ctx.lineTo(X(0.65), Y(0.62));
        art.stroke(ctx, art.INK, lw * 0.7);
    }
}
// A leaf from its stalk (bx, by) to its tip (tx, ty), bulging towards (c1)
// on one side and (c2) on the other
function leaf(ctx, bx, by, tx, ty, c1x, c1y, c2x, c2y, lw) {
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.quadraticCurveTo(c1x, c1y, tx, ty);
    ctx.quadraticCurveTo(c2x, c2y, bx, by);
    art.fill(ctx, LEAF.leaf);
    art.stroke(ctx, art.INK, lw * 0.7);
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx + (tx - bx) * 0.65, by + (ty - by) * 0.65);
    art.stroke(ctx, LEAF.vein, lw * 0.5);
}
// An ellipse turned by an angle (radians) about its centre, as four curves
// (no transforms: a thing draws in its box's own px)
function traceTurned(ctx, cx, cy, rx, ry, an) {
    const c = Math.cos(an), s = Math.sin(an), k = 0.5523;
    const at = (x, y) => [cx + x * c - y * s, cy + x * s + y * c];
    const p = [at(rx, 0), at(0, ry), at(-rx, 0), at(0, -ry)];
    const q = [[at(rx, ry * k), at(rx * k, ry)], [at(-rx * k, ry), at(-rx, ry * k)],
               [at(-rx, -ry * k), at(-rx * k, -ry)], [at(rx * k, -ry), at(rx, -ry * k)]];
    ctx.moveTo(p[0][0], p[0][1]);
    for (let i = 0; i < 4; i++) {
        const to = p[(i + 1) % 4];
        ctx.bezierCurveTo(q[i][0][0], q[i][0][1], q[i][1][0], q[i][1][1], to[0], to[1]);
    }
    ctx.closePath();
}
// A bird's wing from its shoulder (sx, sy), up (a = 1) to down (a = -1): a
// rounded wing, length long, with two feathers drawn on it
function wing(ctx, sx, sy, a, long, color, lw, ink) {
    const an = a >= 0 ? -a * 1.25 : -a * 0.95;   // (radians from straight back; up is further than down)
    const c = Math.cos(an), s = Math.sin(an), rx = long / 2, ry = long * 0.24;
    const cx = sx + c * rx * 0.9, cy = sy + s * rx * 0.9;
    ctx.beginPath();
    traceTurned(ctx, cx, cy, rx, ry, an);
    art.fill(ctx, color);
    art.stroke(ctx, ink, lw);
    ctx.beginPath();
    for (const f of [0.25, -0.3]) {   // (its feathers: lines along it)
        const ox = -s * ry * f, oy = c * ry * f;
        ctx.moveTo(cx + ox - c * rx * 0.1, cy + oy - s * rx * 0.1);
        ctx.lineTo(cx + ox + c * rx * 0.65, cy + oy + s * rx * 0.65);
    }
    art.stroke(ctx, ink, lw * 0.5, 0.6);
}
// dark: the stage is a dark theme's (the crow gets a light outline there)
export function drawThing(ctx, thing, dark) {
    const w = thing.w, h = thing.h, m = Math.min(w, h), lw = Math.max(0.8, m * 0.06), e = lw / 2;
    switch (thing.kind) {
    case 'pebble':
        shadow(ctx, w / 2, w, h, 0.16);
        rock(ctx, e + w * 0.03, e, w * 0.94 - lw, h - lw, lw, false);
        break;
    case 'stone':
        shadow(ctx, w / 2, w, h, 0.16);
        rock(ctx, e + w * 0.02, e, w * 0.96 - lw, h - lw, lw, true);
        break;
    case 'pebbles':
        shadow(ctx, w / 2, w, h, 0.16);
        rock(ctx, w * 0.4, e, w * 0.6 - e, h - lw, lw, false);
        rock(ctx, e, h * 0.3, w * 0.5, h * 0.7 - e, lw, false);
        rock(ctx, w * 0.3, h * 0.05, w * 0.24, h * 0.4, lw * 0.9, false);
        break;
    case 'pot': {
        const colors = FLOWERS[(thing.variant || 0) % FLOWERS.length];
        const rimY = h * 0.56, rimH = h * 0.11, cx = w * 0.5, fy = h * 0.22;
        shadow(ctx, cx, w * 0.8, h, 0.16);
        ctx.beginPath();   // its stalk
        ctx.moveTo(cx, rimY + rimH * 0.5);
        ctx.bezierCurveTo(w * 0.42, h * 0.45, w * 0.58, h * 0.34, cx, fy);
        art.stroke(ctx, LEAF.stem, Math.max(1.2, w * 0.07));
        leaf(ctx, w * 0.47, h * 0.5, w * 0.06 + e, h * 0.36, w * 0.2, h * 0.53, w * 0.3, h * 0.33, lw);
        leaf(ctx, w * 0.53, h * 0.43, w * 0.94 - e, h * 0.3, w * 0.8, h * 0.47, w * 0.68, h * 0.26, lw);
        // its flower: five round petals and a heart
        const d = w * 0.15, pr = w * 0.13;
        for (let i = 0; i < 5; i++) {
            const an = -Math.PI / 2 + i * 2 * Math.PI / 5;
            blob(ctx, cx + Math.cos(an) * d, fy + Math.sin(an) * d, pr, pr, colors[0], lw * 0.6);
        }
        blob(ctx, cx, fy, w * 0.1, w * 0.1, colors[1], lw * 0.6);
        // the pot: wider at the top, its right side in shade, a rim
        const body = () => {
            ctx.beginPath();
            ctx.moveTo(w * 0.12, rimY + rimH);
            ctx.lineTo(w * 0.88, rimY + rimH);
            ctx.lineTo(w * 0.77, h - e);
            ctx.lineTo(w * 0.23, h - e);
            ctx.closePath();
        };
        body();
        art.fill(ctx, POT.body);
        ctx.save();
        body();
        ctx.clip();
        art.ellipse(ctx, w * 0.95, h * 0.85, w * 0.28, h * 0.3, POT.shade);
        ctx.restore();
        body();
        art.stroke(ctx, art.INK, lw);
        ctx.beginPath();
        traceRoundRect(ctx, w * 0.05 + e, rimY, w * 0.9 - lw, rimH, m * 0.05);
        art.fill(ctx, POT.rim);
        art.stroke(ctx, art.INK, lw);
        ctx.beginPath();
        ctx.moveTo(w * 0.14, rimY + rimH * 0.38);
        ctx.lineTo(w * 0.5, rimY + rimH * 0.38);
        art.stroke(ctx, POT.rimLit, lw * 0.8);
        break;
    }
    case 'crow':
    case 'crowHigh': {
        // (facing what it flies to: Talpy; plump, a big head, its wings flapping)
        const ink = dark ? DARK_RIM : art.INK, bird = BIRDS[(thing.variant || 0) % BIRDS.length];
        const p = ((thing.frame || 0) % FLAP_FRAMES) / FLAP_FRAMES, a = Math.cos(2 * Math.PI * p);
        const dy = h * 0.06 * Math.sin(2 * Math.PI * p);   // (lifted by each downstroke)
        const by = h * 0.56 + dy, long = Math.min(w * 0.4, h * 0.46);
        wing(ctx, w * 0.56, by - h * 0.12, a * 0.8, long * 0.85, bird[2], lw * 0.8, ink);   // its far wing
        ctx.beginPath();   // its tail: three feathers fanned
        ctx.moveTo(w * 0.7, by - h * 0.06);
        ctx.quadraticCurveTo(w * 0.86, by - h * 0.26, w - e, by - h * 0.2);
        ctx.quadraticCurveTo(w * 0.92, by - h * 0.06, w - e, by);
        ctx.quadraticCurveTo(w * 0.92, by + h * 0.06, w * 0.97, by + h * 0.18);
        ctx.quadraticCurveTo(w * 0.84, by + h * 0.18, w * 0.7, by + h * 0.1);
        ctx.closePath();
        art.fill(ctx, bird[0]);
        art.stroke(ctx, ink, lw);
        const body = () => {
            ctx.beginPath();
            traceEllipse(ctx, w * 0.5, by, w * 0.26, h * 0.26);
        };
        body();
        art.fill(ctx, bird[0]);
        ctx.save();
        body();
        ctx.clip();
        if (bird[4])   // (its breast)
            art.ellipse(ctx, w * 0.36, by + h * 0.14, w * 0.2, h * 0.2, bird[4]);
        art.ellipse(ctx, w * 0.6, by + h * 0.34, w * 0.3, h * 0.14, '#000000', 0.18);   // (its belly in shade)
        ctx.restore();
        body();
        art.stroke(ctx, ink, lw);
        const hx = w * 0.27, hy = by - h * 0.2, hr = Math.min(w * 0.15, h * 0.24);
        ctx.beginPath();   // its beak
        ctx.moveTo(hx - hr * 0.7, hy - hr * 0.3);
        ctx.quadraticCurveTo(hx - hr * 1.3, hy - hr * 0.1, Math.max(e, hx - hr * 1.75), hy + hr * 0.25);
        ctx.quadraticCurveTo(hx - hr * 1.2, hy + hr * 0.45, hx - hr * 0.7, hy + hr * 0.4);
        ctx.closePath();
        art.fill(ctx, bird[3]);
        art.stroke(ctx, ink, lw * 0.7);
        blob(ctx, hx, hy, hr, hr, bird[0], lw, ink);   // its head
        art.circle(ctx, hx - hr * 0.25, hy - hr * 0.15, hr * 0.42, '#ffffff');
        art.circle(ctx, hx - hr * 0.38, hy - hr * 0.1, hr * 0.24, art.INK);
        art.circle(ctx, hx - hr * 0.32, hy - hr * 0.24, hr * 0.09, '#ffffff');
        wing(ctx, w * 0.5, by - h * 0.06, a, long, bird[1], lw, ink);   // its near wing
        break;
    }
    case 'hedgehog': {
        // (spikes say "don't touch": facing Talpy, its snout and nose to the left)
        const quills = HEDGEHOGS[(thing.variant || 0) % HEDGEHOGS.length];
        const cx = w * 0.56, cy = h * 0.66, rx = w * 0.36, ry = h * 0.5, n = 9;
        shadow(ctx, w / 2, w, h, 0.16);
        const back = () => {   // a dome of quills, pointed all over
            ctx.beginPath();
            ctx.moveTo(w * 0.22, h * 0.9);
            for (let i = 0; i <= 2 * n; i++) {
                const an = Math.PI + Math.PI * i / (2 * n), r = i % 2 ? 1.17 : 1;
                ctx.lineTo(cx + Math.cos(an) * rx * r, cy + Math.sin(an) * ry * r);
            }
            ctx.lineTo(w * 0.94, h * 0.9);
            ctx.closePath();
        };
        back();
        art.fill(ctx, quills[0]);
        ctx.save();
        back();
        ctx.clip();
        art.ellipse(ctx, cx - rx * 0.15, cy - ry * 0.35, rx * 0.6, ry * 0.42, quills[1]);   // (lit on top)
        ctx.restore();
        back();
        art.stroke(ctx, art.INK, lw);
        for (const fx of [0.36, 0.76])   // its feet
            blob(ctx, w * fx, h * 0.9, w * 0.07, h * 0.07, HEDGEHOG.face, lw * 0.7);
        ctx.beginPath();   // its face: a snout to the left
        ctx.moveTo(w * 0.4, h * 0.42);
        ctx.quadraticCurveTo(w * 0.2, h * 0.46, w * 0.05 + e, h * 0.68);
        ctx.quadraticCurveTo(w * 0.2, h * 0.9, w * 0.44, h * 0.88);
        ctx.quadraticCurveTo(w * 0.5, h * 0.62, w * 0.4, h * 0.42);
        ctx.closePath();
        art.fill(ctx, HEDGEHOG.face);
        art.stroke(ctx, art.INK, lw);
        art.circle(ctx, w * 0.06 + e, h * 0.67, Math.max(1, w * 0.045), art.INK);   // its nose
        art.circle(ctx, w * 0.25, h * 0.58, Math.max(0.9, w * 0.038), art.INK);   // its eye
        art.circle(ctx, w * 0.24, h * 0.565, Math.max(0.4, w * 0.014), '#ffffff');
        art.ellipse(ctx, w * 0.31, h * 0.73, w * 0.05, h * 0.04, HEDGEHOG.blush, 0.8);
        break;
    }
    case 'stump': {
        const cutY = h * 0.22, cutR = h * 0.13;
        shadow(ctx, w / 2, w, h, 0.16);
        const side = () => {   // its bark, roots spread at the foot
            ctx.beginPath();
            ctx.moveTo(w * 0.13, cutY);
            ctx.lineTo(w * 0.14, h * 0.78);
            ctx.quadraticCurveTo(w * 0.12, h * 0.94, e, h - e);
            ctx.lineTo(w - e, h - e);
            ctx.quadraticCurveTo(w * 0.88, h * 0.94, w * 0.86, h * 0.78);
            ctx.lineTo(w * 0.87, cutY);
            ctx.closePath();
        };
        side();
        art.fill(ctx, WOOD.bark);
        ctx.save();
        side();
        ctx.clip();
        art.ellipse(ctx, w * 0.95, h * 0.7, w * 0.3, h * 0.6, WOOD.shade);
        ctx.restore();
        ctx.beginPath();   // the bark's lines
        ctx.moveTo(w * 0.32, cutY + cutR);
        ctx.lineTo(w * 0.3, h * 0.82);
        ctx.moveTo(w * 0.52, cutY + cutR * 1.2);
        ctx.lineTo(w * 0.54, h * 0.7);
        ctx.moveTo(w * 0.7, cutY + cutR);
        ctx.lineTo(w * 0.72, h * 0.86);
        art.stroke(ctx, WOOD.line, lw * 0.6);
        side();
        art.stroke(ctx, art.INK, lw);
        blob(ctx, w / 2, cutY, w * 0.37, cutR, WOOD.cut, lw);   // its top, cut: rings
        ctx.beginPath();
        traceEllipse(ctx, w / 2, cutY, w * 0.24, cutR * 0.6);
        art.stroke(ctx, WOOD.ring, lw * 0.6);
        ctx.beginPath();
        traceEllipse(ctx, w / 2, cutY, w * 0.1, cutR * 0.25);
        art.stroke(ctx, WOOD.ring, lw * 0.6);
        // (a sprout on its top)
        ctx.beginPath();
        ctx.moveTo(w * 0.3, cutY);
        ctx.quadraticCurveTo(w * 0.27, cutY * 0.6, w * 0.3, cutY * 0.35);
        art.stroke(ctx, LEAF.stem, lw * 0.8);
        leaf(ctx, w * 0.3, cutY * 0.4, w * 0.12, e + h * 0.01, w * 0.14, cutY * 0.5, w * 0.28, e, lw * 0.8);
        break;
    }
    case 'log': {
        const r = h / 2 - e, endX = w * 0.16;
        shadow(ctx, w / 2, w, h, 0.16);
        const side = () => {   // lying down, its round end to the left, the far one rounded off
            ctx.beginPath();
            ctx.moveTo(endX, e);
            ctx.lineTo(w - e - r * 0.6, e);
            ctx.quadraticCurveTo(w - e, e, w - e, h / 2);
            ctx.quadraticCurveTo(w - e, h - e, w - e - r * 0.6, h - e);
            ctx.lineTo(endX, h - e);
            ctx.closePath();
        };
        side();
        art.fill(ctx, WOOD.bark);
        ctx.save();
        side();
        ctx.clip();
        art.ellipse(ctx, w * 0.6, h, w * 0.5, h * 0.35, WOOD.shade);
        ctx.restore();
        ctx.beginPath();   // the bark's lines
        ctx.moveTo(w * 0.3, h * 0.3);
        ctx.lineTo(w * 0.62, h * 0.28);
        ctx.moveTo(w * 0.45, h * 0.55);
        ctx.lineTo(w * 0.85, h * 0.52);
        ctx.moveTo(w * 0.3, h * 0.75);
        ctx.lineTo(w * 0.55, h * 0.78);
        art.stroke(ctx, WOOD.line, lw * 0.6);
        side();
        art.stroke(ctx, art.INK, lw);
        const er = Math.min(endX - e, r * 0.55);
        blob(ctx, endX, h / 2, er, r, WOOD.cut, lw);   // its cut end: rings
        ctx.beginPath();
        traceEllipse(ctx, endX, h / 2, er * 0.55, r * 0.55);
        art.stroke(ctx, WOOD.ring, lw * 0.6);
        break;
    }
    case 'tuft': {
        // (the ground's: no outline, see-through, thin blades; one has a daisy)
        const v = (thing.variant || 0) % 3, green = dark ? GRASS.dark : GRASS.light, blade = Math.max(0.8, lw * 0.75);
        ctx.beginPath();
        if (v === 1) {
            ctx.moveTo(w * 0.3, h);
            ctx.quadraticCurveTo(w * 0.26, h * 0.5, w * 0.1 + e, h * 0.3 + e);
            ctx.moveTo(w * 0.5, h);
            ctx.quadraticCurveTo(w * 0.52, h * 0.4, w * 0.6, e);
            ctx.moveTo(w * 0.66, h);
            ctx.quadraticCurveTo(w * 0.74, h * 0.55, w * 0.92 - e, h * 0.3);
        } else {
            ctx.moveTo(w * 0.22, h);
            ctx.quadraticCurveTo(w * 0.2, h * 0.55, w * 0.04 + e, h * 0.2 + e);
            ctx.moveTo(w * 0.42, h);
            ctx.quadraticCurveTo(w * 0.4, h * 0.45, w * 0.36, e);
            ctx.moveTo(w * 0.58, h);
            ctx.quadraticCurveTo(w * 0.62, h * 0.4, w * 0.7, h * 0.1 + e);
            ctx.moveTo(w * 0.76, h);
            ctx.quadraticCurveTo(w * 0.82, h * 0.6, w * 0.96 - e, h * 0.4);
        }
        art.stroke(ctx, green, blade, 0.55);
        if (v === 2) {   // (a daisy among the blades)
            const fx = w * 0.5, fy = h * 0.32, fr = Math.min(w, h) * 0.16;
            for (let i = 0; i < 5; i++) {
                const an = -Math.PI / 2 + i * 2 * Math.PI / 5;
                art.circle(ctx, fx + Math.cos(an) * fr, fy + Math.sin(an) * fr, fr * 0.75, GRASS.daisy, 0.6);
            }
            art.circle(ctx, fx, fy, fr * 0.6, GRASS.heart, 0.7);
        }
        break;
    }
    case 'cookie': {
        // (the one thing to take: Talpy's own cookie, bobbing a little in a warm glow, twinkling)
        const f = (thing.frame || 0) % FRAMES.cookie, bob = Math.sin(f / FRAMES.cookie * Math.PI * 2) * h * 0.03;
        shine(ctx, w, h, f, CLAIM);
        const sc = (Math.min(w, h) * 0.56) / 11.2;   // (drawCookie: 5.6 box units round)
        ctx.save();
        ctx.translate(w / 2, h / 2 + bob);
        ctx.scale(sc, sc);
        drawCookie(ctx, COOKIE_FLAVOURS[(thing.variant || 0) % COOKIE_FLAVOURS.length]);
        ctx.restore();
        break;
    }
    case 'plus': {
        // ("+10" rising from a cookie taken: the plus drawn, the figures written)
        const cy = h / 2, arm = h * 0.28, px = h * 0.38;
        ctx.beginPath();
        ctx.moveTo(px - arm, cy);
        ctx.lineTo(px + arm, cy);
        ctx.moveTo(px, cy - arm);
        ctx.lineTo(px, cy + arm);
        art.stroke(ctx, dark ? DARK_RIM : art.INK, lw * 2.6);
        art.stroke(ctx, CLAIM, lw * 1.4);
        ctx.font = 'bold ' + Math.max(6, Math.round(h * 0.9)) + 'px sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.lineWidth = lw * 1.6;
        ctx.strokeStyle = dark ? DARK_RIM : art.INK;
        ctx.strokeText('10', px + arm + h * 0.08, cy);
        ctx.fillStyle = CLAIM;
        ctx.fillText('10', px + arm + h * 0.08, cy);
        break;
    }
    case 'dust': {
        // (a puff where he landed: frame 0 to 3, swelling and fading)
        const f = (thing.frame || 0) % FRAMES.dust, grow = 0.55 + 0.15 * f, fade = 0.55 * (1 - f / FRAMES.dust);
        for (const pf of [[0.25, 0.7, 0.18], [0.5, 0.6, 0.24], [0.75, 0.7, 0.18]]) {
            const r = Math.min(w * pf[2], h * 0.45) * grow;
            art.ellipse(ctx, w * pf[0], Math.min(h - r * 0.7, h * pf[1]), r, r * 0.7, PUFF_DUST[0], fade);
        }
        break;
    }
    case 'root': {
        // (a root across the way: a wavy woody tube, thick where it comes from,
        // tapering, knobbly, rootlets curling off; variant: its curl, 0 to 2
        // from the left, 3 to 5 the same from the right)
        const v = (thing.variant || 0) % 3, flip = ((thing.variant || 0) % 6) >= 3, side = flip ? -1 : 1;
        const n = 18, amp = h * [0.16, 0.22, 0.12][v], lam = [1.1, 0.8, 1.4][v];
        const t0 = h * 0.62, top = [], bot = [];
        for (let i = 0; i <= n; i++) {
            const p = i / n, x = flip ? w - e - (w - lw) * p : e + (w - lw) * p;
            const knob = 1 + 0.12 * Math.sin(p * Math.PI * 7 + v);
            const t = Math.max(h * 0.1, t0 * (1 - 0.82 * p) * knob) / 2;
            const y = h / 2 + amp * Math.sin(p * Math.PI * 2 / lam + v) * (0.4 + 0.6 * p);
            top.push([x, Math.max(e, y - t)]);
            bot.push([x, Math.min(h - e, y + t)]);
        }
        const rootPath = () => {   // (smooth: through the midpoints)
            const pts = top.concat(bot.slice().reverse());
            ctx.beginPath();
            ctx.moveTo((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2);
            for (let i = 1; i < pts.length; i++) {
                const a = pts[i], b = pts[(i + 1) % pts.length];
                ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
            }
            ctx.closePath();
        };
        // its rootlets first (under it), thin and curling
        ctx.beginPath();
        const lets = v === 1 ? [0.28, 0.62] : v === 2 ? [0.4, 0.78] : [0.2, 0.48, 0.72];
        for (let i = 0; i < lets.length; i++) {
            const j = Math.round(lets[i] * n), up = i % 2 === 1, from = up ? top[j] : bot[j];
            const reach = Math.min(h * 0.45, up ? from[1] - e : h - e - from[1]);
            ctx.moveTo(from[0], from[1]);
            ctx.quadraticCurveTo(from[0] + side * h * 0.25, from[1] + (up ? -reach : reach), from[0] + side * h * 0.6,
                                 from[1] + (up ? -reach * 0.7 : reach * 0.7));
        }
        art.stroke(ctx, ROOT.line, Math.max(0.8, lw * 0.8));
        rootPath();
        art.fill(ctx, ROOT.wood);
        ctx.save();
        rootPath();
        ctx.clip();
        ctx.beginPath();   // (its underside in shade)
        for (let i = 0; i <= n; i++)
            ctx[i ? 'lineTo' : 'moveTo'](bot[i][0], bot[i][1] - (bot[i][1] - top[i][1]) * 0.35);
        for (let i = n; i >= 0; i--)
            ctx.lineTo(bot[i][0], h);
        ctx.closePath();
        art.fill(ctx, ROOT.shade);
        ctx.restore();
        rootPath();
        art.stroke(ctx, art.INK, lw);
        ctx.beginPath();   // (its grain, along the top)
        for (let i = 1; i < n * 0.7; i++) {
            const y = top[i][1] + (bot[i][1] - top[i][1]) * 0.3;
            ctx[i > 1 ? 'lineTo' : 'moveTo'](top[i][0], y);
        }
        art.stroke(ctx, ROOT.grain, lw * 0.5, 0.8);
        break;
    }
    case 'pipe': {
        // (an old pipe buried across the way: steel, rings along it, rust; its
        // open end towards the middle, variant 0 to the right, 1 to the left)
        const right = ((thing.variant || 0) % 2) === 0, bodyH = h * 0.78, top = (h - bodyH) / 2, endR = bodyH / 2;
        const tube = () => {
            ctx.beginPath();
            traceRoundRect(ctx, e, top, w - lw, bodyH, Math.min(endR, w / 4));
        };
        tube();
        art.fill(ctx, PIPE.steel);
        ctx.save();
        tube();
        ctx.clip();
        art.rrect(ctx, e, top, w - lw, bodyH * 0.32, endR * 0.5, PIPE.lit);
        art.rrect(ctx, e, top + bodyH * 0.7, w - lw, bodyH * 0.3, 0, PIPE.shade);
        for (let x = w * 0.18; x < w - h; x += h * 1.7)   // (rust)
            art.ellipse(ctx, x + h * 0.6, top + bodyH * 0.6, h * 0.22, bodyH * 0.16, PIPE.rust, 0.85);
        ctx.restore();
        tube();
        art.stroke(ctx, art.INK, lw);
        const ring = x => {   // (a ring round it, a little proud of it)
            ctx.beginPath();
            traceRoundRect(ctx, x, e, Math.max(lw * 2, h * 0.22), h - lw, h * 0.06);
            art.fill(ctx, PIPE.ring);
            art.stroke(ctx, art.INK, lw);
        };
        for (let x = h * 0.6; x < w - h * 0.8; x += h * 2.6)
            ring(right ? x : w - x - h * 0.22);
        // its open end: dark inside
        const ex = right ? w - e - endR * 0.55 : e + endR * 0.55;
        blob(ctx, ex, h / 2, endR * 0.5, endR - lw, PIPE.ring, lw);
        art.ellipse(ctx, ex, h / 2, endR * 0.3, endR * 0.62, PIPE.inside);
        break;
    }
    case 'bottle': {
        // (an old glass bottle stuck in the earth: green, a cork, a shine)
        const neckW = w * 0.36, neckTop = h * 0.08, shoulder = h * 0.38;
        const glass = () => {
            ctx.beginPath();
            ctx.moveTo(w / 2 - neckW / 2, neckTop + h * 0.06);
            ctx.lineTo(w / 2 - neckW / 2, shoulder - h * 0.06);
            ctx.quadraticCurveTo(e, shoulder, e, shoulder + h * 0.12);
            ctx.lineTo(e, h - h * 0.06 - e);
            ctx.quadraticCurveTo(e, h - e, w * 0.2, h - e);
            ctx.lineTo(w * 0.8, h - e);
            ctx.quadraticCurveTo(w - e, h - e, w - e, h - h * 0.06 - e);
            ctx.lineTo(w - e, shoulder + h * 0.12);
            ctx.quadraticCurveTo(w - e, shoulder, w / 2 + neckW / 2, shoulder - h * 0.06);
            ctx.lineTo(w / 2 + neckW / 2, neckTop + h * 0.06);
            ctx.closePath();
        };
        glass();
        art.fill(ctx, BOTTLE.glass, 0.92);
        ctx.save();
        glass();
        ctx.clip();
        patch(ctx, w * 0.2, shoulder, w * 0.14, h * 0.5, w * 0.07, BOTTLE.shine, 0.75);
        patch(ctx, w * 0.62, shoulder, w * 0.4, h, 0, BOTTLE.shade, 0.5);
        ctx.restore();
        glass();
        art.stroke(ctx, art.INK, lw);
        ctx.beginPath();   // its cork
        traceRoundRect(ctx, w / 2 - neckW * 0.6, e, neckW * 1.2, h * 0.13, w * 0.06);
        art.fill(ctx, BOTTLE.cork);
        art.stroke(ctx, art.INK, lw * 0.8);
        break;
    }
    case 'boulder':
        shadow(ctx, w / 2, w, h, 0.16);
        rock(ctx, e + w * 0.02, e, w * 0.96 - lw, h - lw, lw, true);
        art.ellipse(ctx, w * 0.7, h * 0.28, w * 0.06, h * 0.05, ROCK.speck);
        break;
    case 'beetle': {
        // (it crawls sideways: its shell, its head the way it goes, six legs
        // stepping by frame; variant 0 to the left, 1 to the right)
        const ink = dark ? DARK_RIM : art.INK, left = ((thing.variant || 0) % 2) === 0, f = (thing.frame || 0) % FRAMES.beetle;
        const X = x => left ? x : w - x;
        const sx = w * 0.55, sy = h * 0.46, rx = w * 0.32, ry = h * 0.36;
        ctx.beginPath();   // its legs, under it
        for (let i = 0; i < 3; i++) {
            const lx = w * (0.38 + i * 0.16), swing = ((i + f) % 2 ? 1 : -1) * w * 0.05;
            ctx.moveTo(X(lx), sy + ry * 0.6);
            ctx.lineTo(X(lx + swing - w * 0.04), h * 0.8);
            ctx.lineTo(X(lx + swing - w * 0.08), h - e);
        }
        art.stroke(ctx, ink, Math.max(0.8, lw * 0.9));
        ctx.beginPath();   // its antennae
        ctx.moveTo(X(w * 0.18), sy - h * 0.05);
        ctx.quadraticCurveTo(X(w * 0.08), h * 0.12, X(e + w * 0.02), h * 0.1 + e);
        ctx.moveTo(X(w * 0.2), sy - h * 0.08);
        ctx.quadraticCurveTo(X(w * 0.14), h * 0.02 + e, X(w * 0.06), e);
        art.stroke(ctx, ink, Math.max(0.7, lw * 0.6));
        blob(ctx, X(w * 0.22), sy + h * 0.04, w * 0.11, h * 0.2, BEETLE.head, lw, ink);   // its head
        const shell = () => {
            ctx.beginPath();
            traceEllipse(ctx, X(sx), sy, rx, ry);
        };
        shell();
        art.fill(ctx, BEETLE.shell);
        ctx.save();
        shell();
        ctx.clip();
        art.ellipse(ctx, X(sx - rx * 0.3), sy - ry * 0.45, rx * 0.5, ry * 0.32, BEETLE.lit);
        ctx.restore();
        shell();
        art.stroke(ctx, ink, lw);
        ctx.beginPath();   // where its wing cases meet
        ctx.moveTo(X(sx - rx * 0.92), sy);
        ctx.lineTo(X(sx + rx * 0.92), sy);
        art.stroke(ctx, ink, lw * 0.6);
        art.circle(ctx, X(w * 0.16), sy, Math.max(0.6, h * 0.05), '#ffffff');   // its eye
        break;
    }
    case 'speck': {
        // (in the earth, faint: a few small stones, or an old shell)
        if (((thing.variant || 0) % 2) === 0) {
            art.ellipse(ctx, w * 0.25, h * 0.6, w * 0.16, h * 0.3, SPECK.stone, 0.5);
            art.ellipse(ctx, w * 0.62, h * 0.45, w * 0.12, h * 0.24, SPECK.stone, 0.45);
            art.ellipse(ctx, w * 0.82, h * 0.72, w * 0.08, h * 0.18, SPECK.stone, 0.4);
        } else {
            ctx.beginPath();   // (a spiral shell)
            const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - e;
            ctx.moveTo(cx + r, cy);
            for (let i = 1; i <= 24; i++) {
                const a = i / 24 * Math.PI * 3.6, rr = r * (1 - i / 30);
                ctx.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * 0.9);
            }
            art.stroke(ctx, SPECK.shell, Math.max(0.8, lw * 0.7), 0.55);
        }
        break;
    }
    case 'worm': {
        // (a worm wriggling by, faint (only in the earth: never in his way): frame its wave)
        const f = (thing.frame || 0) % FRAMES.worm, ph = f / FRAMES.worm * Math.PI * 2, thick = h * 0.5;
        ctx.beginPath();
        for (let i = 0; i <= 16; i++) {
            const x = thick / 2 + (w - thick) * i / 16, y = h / 2 + Math.sin(i / 16 * Math.PI * 2 + ph) * (h / 2 - thick / 2);
            if (i === 0)
                ctx.moveTo(x, y);
            else
                ctx.lineTo(x, y);
        }
        art.stroke(ctx, WORM.skin, thick, 0.45);
        const bx = w * 0.3, by = h / 2 + Math.sin(0.3 * Math.PI * 2 + ph) * (h / 2 - thick / 2);
        art.circle(ctx, bx, by, thick * 0.45, WORM.band, 0.45);
        break;
    }
    case 'crystal': {
        // (in the deep rock's wall, faint and still: three points of crystal, no
        // shine, no outline: neither a treasure nor something in the way)
        const c = CRYSTALS[(thing.variant || 0) % CRYSTALS.length];
        const point = (x, wd, top) => {
            ctx.beginPath();
            ctx.moveTo(x - wd / 2, h - e);
            ctx.lineTo(x - wd / 2, top + wd * 0.6);
            ctx.lineTo(x, top);
            ctx.lineTo(x + wd / 2, top + wd * 0.6);
            ctx.lineTo(x + wd / 2, h - e);
            ctx.closePath();
            art.fill(ctx, c[0], 0.32);
            art.stroke(ctx, c[1], lw * 0.6, 0.35);
        };
        point(w * 0.3, w * 0.22, h * 0.3);
        point(w * 0.72, w * 0.2, h * 0.42);
        point(w * 0.5, w * 0.26, e);
        break;
    }
    case 'tunnel':
        // (a piece of his tunnel: the earth he dug through, darker; drawn faint, the pieces overlap)
        art.ellipse(ctx, w / 2, h / 2, w / 2, h / 2, '#000000', 0.12);
        art.ellipse(ctx, w / 2, h / 2, w * 0.42, h * 0.36, '#000000', 0.12);
        break;
    case 'clod': {
        // (a crumb of earth flung off his paws)
        const v = (thing.variant || 0) % 3;
        art.ellipse(ctx, w / 2, h / 2, w / 2 - (v === 1 ? w * 0.1 : 0), h / 2 - (v === 2 ? h * 0.12 : 0), CLOD.earth);
        art.ellipse(ctx, w * 0.42, h * 0.38, w * 0.22, h * 0.18, CLOD.lit);
        break;
    }
    case 'glow': {
        // (his lamp's light ahead of him, soft, fading out)
        const r = Math.min(w, h) / 2;
        const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, r);
        g.addColorStop(0, 'rgba(255, 228, 150, 0.36)');
        g.addColorStop(0.55, 'rgba(255, 220, 140, 0.14)');
        g.addColorStop(1, 'rgba(255, 220, 140, 0)');
        ctx.beginPath();
        traceEllipse(ctx, w / 2, h / 2, r, r);
        ctx.fillStyle = g;
        ctx.fill();
        break;
    }
    case 'cloud': {
        // (far off, behind: puffs on a flat bottom, faint)
        const puffs = (thing.variant || 0) % 2 ? [[0.3, 0.62, 0.24, 0.36], [0.52, 0.48, 0.24, 0.46], [0.74, 0.64, 0.2, 0.34]]
                                                : [[0.2, 0.66, 0.16, 0.32], [0.4, 0.46, 0.2, 0.44], [0.62, 0.42, 0.2, 0.4],
                                                   [0.82, 0.66, 0.15, 0.3]];
        const cloud = () => {
            ctx.beginPath();
            for (const pf of puffs)
                traceEllipse(ctx, w * pf[0], h * pf[1], w * pf[2], h * pf[3]);
        };
        if (!dark) {
            cloud();
            art.stroke(ctx, CLOUD.lightRim, lw * 1.4, 0.45);
        }
        cloud();
        art.fill(ctx, dark ? CLOUD.dark : CLOUD.light, dark ? 0.14 : 0.9);
        break;
    }
    }
}

// ---------------------------------------------------------------- the creature

export class Talpy {
    constructor(opts) {
        opts = opts || {};
        this.colors = opts.colors || art.LILAC;
        this.theme = opts.theme || { fx: '#7d87a3', text: '#161a24' };
        this.words = opts.words || (s => s);
        this.travels = !!opts.travels;    // may dig over to another spot (the host moves it: onTravel)
        this.onTravel = null;
        this.onTravelStop = null;         // (a run cut short while it tunnels: the move stops too)
        this.facingLeft = false;
        // (part, left) => the open hole's side drawn by drawHoleSide on a sheet the
        // size of the canvas Talpy's drawn on, at the same transform; null: drawn
        this.holeImage = null;
        this.mood = 'idle';
        this.base = Object.assign({}, MOODS.idle.base);
        this.st = {};
        this.since = {};          // when each part last changed (ms)
        this.now = 0;
        this.last = 0;
        this.run = null;          // the action under way: {name, steps, i, until, done, auto}
        this.lastAuto = '';
        this.nextBrain = 0;
        this.brainOn = opts.brain !== false;
        this.playful = opts.playful !== false;   // its tricks and props (setPlayful)
        this.held = false;
        this.heldAt = 0;
        this.tugging = false;     // you pull at it, it hangs on to its burrow (tug)
        this.tugAim = 0;          // and leans towards your hand (degrees, + to the right: tugToward),
        this.tugLean = 0;         // eased there
        this.pushing = false;     // you push it down into its burrow (push): it hangs on and pushes back,
        this.pushFrom = 0;        // from that depth (box units),
        this.pushTarget = 0;      // sinking towards this one (pushTo),
        this.pushDepth = 0;       // on a spring: where it is now,
        this.pushVel = 0;         // and how quickly it goes (units a second)
        this.pushAt = 0;          // (when you began: its shoves up keep time from then)
        this.pushHeldAt = 0;      // since when your hand has held it PUSH_HOLD down (0: not now)
        this.pushGives = null;    // (the host's word when it gives in: push)
        this.gaveIn = false;      // you pushed on: it gave in and ducked all the way
        this.pushStill = false;   // (less motion: down at once, no spring, no shoves)
        this.squash = 0;          // how squashed it's drawn (0 to 1), eased: as you push, and a moment after
        this.stretch = 0;         // how drawn out (0 to 1), eased: as you pull (tug), and a moment after
        this.chasing = false;     // after a cookie (chase): on its feet, the host moves it
        this.chased = '';         // how (chaseAs)
        this.frameMs = 40;        // see tick()
        this.walkMs = 500;        // a step's length, both feet (a game's: as quick as the ground goes)
        this.walkT = -1;          // (a film's picture: its time in the step, placeMoves)
        this.stepAt = 0;          // when the pose shown began
        this.big = false;         // a big move is under way (see stills), since bigAt
        this.bigAt = 0;
        this.landsAt = 0;         // what flew off during it has landed by then
        this.away = false;        // it left (leave): it stays down there until it arrives again
        this.settled = false;     // what's eased between poses is where it's going (see films)
        this.easeAt = 0;          // when that last changed
        this.fx = [];
        this.v = { depth: DEPTH.half, depthFrom: DEPTH.half, depthTo: DEPTH.half, depthAt: -1e9, hole: 1, holeFrom: 1, holeTo: 1,
                   holeAt: -1e9, armL: 16, armR: -16, plume: 0, lx: 0, ly: 0, sip: 0 };
        this.blinkUntil = 0;
        this.nextBlink = 0;
        this.glance = [0, 0];
        this.nextGlance = 0;
        this.apply({}, true);
    }

    // ------------------------------------------------------------ what the host calls

    setColors(colors) {
        this.colors = colors || art.LILAC;
    }

    setTheme(theme) {
        this.theme = theme;
    }

    setMood(mood) {
        if (!MOODS[mood] || mood === this.mood)
            return;
        this.mood = mood;
        this.base = Object.assign({}, MOODS[mood].base);
        this.lastAuto = '';
        if (this.held)
            return;
        if (this.chasing || this.pushing)
            return;   // (it looks so once it's back: pushed() ends on its base)
        if (!this.run || this.run.auto)
            this.cancel();
        if (!this.run)
            this.apply({});
        this.nextBrain = this.now + random.rnd(200, 700);
    }

    // Playful Talpy (a setting): off, it picks only from its mood's calm moves
    // (what the chats do, and quiet ones); a trick under way it picked itself stops
    setPlayful(on) {
        on = on !== false;
        if (on === this.playful)
            return;
        this.playful = on;
        if (on || !this.run || !this.run.auto)
            return;
        const calm = (MOODS[this.mood] || MOODS.idle).calm;
        if (calm && !calm[this.run.name]) {
            this.cancel();
            this.apply({});
        }
    }

    // An action now: a reaction to you or to an event (done(true) when it ran
    // to the end); not while you have it (held, pulled at, pushed down)
    react(name, done) {
        if (this.held || this.tugging || this.pushing || this.chasing || !ACTIONS[name]) {
            if (done)
                done(false);
            return;
        }
        this.play(name, done, false);
    }

    get busy() {
        return this.run !== null || this.held || this.tugging || this.pushing || this.chasing;
    }

    // Its burrow is open or opening under it (a host swinging it puts it
    // upright then, so the burrow never swings)
    get holeOpen() {
        return this.v.holeTo > 0;
    }

    // Out of its burrow on the floor, as it's drawn now (what a pose that
    // just ended goes back to hasn't moved it yet)
    get onFloor() {
        return !this.held && this.st.tunnel !== '1' && this.v.depth <= 0 && this.v.hole <= 0.02;
    }

    // You pull at it (a drag on it): in its burrow it hangs on to the rim,
    // stretched and trembling, for TUG_MS, then done(true): it lets go and
    // the host takes it (setHeld); done(false): you let go first (letGo) or
    // took it anyway. Pushed down (push), it comes up from there into it;
    // pushed down again before it came out (push), the tug ends (done(false)).
    // False if it isn't in its burrow (out on the floor, tunnelling, held):
    // the host takes it at once
    tug(done) {
        if (this.held || this.chasing || this.tugging || this.st.tunnel === '1' || this.v.holeTo <= 0 || this.st.depth === 'out')
            return false;
        this.pushing = false;   // (pushed down, then pulled: it comes up from there into the tug, its squash easing off)
        this.pushHeldAt = 0;
        this.pushGives = null;
        this.tugging = true;
        this.play({ steps: TUG.hold }, ok => {
            this.tugging = false;
            if (done)
                done(ok);
        }, false);
        return true;
    }

    // You push it down (a drag that starts downward while it's in its burrow):
    // it squashes, grabs the rim and pushes back, with a dirt puff, sinking a
    // little as your hand goes (pushTo); still (less motion): it's down at
    // once. givesIn(): it gives in now (held down long enough, or pushed far:
    // the host has it say so). Pulled at (tug) and pushed back down before it
    // came out, the tug ends (its done(false)) and it's pushed from where it
    // is, drawn out easing into squashed. False if it isn't in its burrow (out
    // on the floor, tunnelling, held, gone): the host does what it did
    push(still, givesIn) {
        if (this.held || this.chasing || this.pushing || this.away || this.st.tunnel === '1' || this.v.holeTo <= 0
            || this.st.depth === 'out')
            return false;
        this.cancel();
        this.tugging = false;
        this.pushing = true;
        this.gaveIn = this.pushStill = !!still;
        this.pushFrom = this.pushDepth = this.pushTarget = this.v.depth;
        this.pushVel = 0;
        this.pushAt = this.now;
        this.pushHeldAt = 0;
        this.pushGives = givesIn || null;
        this.apply(still ? PUSH.give() : PUSH.start());
        if (still)
            this.pushTarget = DEPTH.hidden;
        return true;
    }

    // How far down your hand went since the drag began (box units): it sinks
    // less the further you push; held PUSH_HOLD down for TUG_MS, or pushed
    // PUSH_GIVE down, it gives in and ducks all the way. True when it gives in
    // now
    pushTo(down) {
        if (!this.pushing || this.gaveIn)
            return false;
        down = Math.max(0, down);
        if (down >= PUSH_GIVE)
            return this.giveIn();
        if (down < PUSH_HOLD)
            this.pushHeldAt = 0;
        else if (!this.pushHeldAt)
            this.pushHeldAt = this.now || 1;
        this.pushTarget = this.pushFrom + (DEPTH.hidden - this.pushFrom) * PUSH_MOST * (1 - Math.exp(-down / PUSH_SOFT));
        return false;
    }

    // (it gives in: ducks all the way, and the host has it say so)
    giveIn() {
        this.gaveIn = true;
        this.pushHeldAt = 0;
        this.pushTarget = DEPTH.hidden;
        this.apply(PUSH.give());
        if (this.pushGives)
            this.pushGives();
        return true;
    }

    // You let go: given in, it stays down a moment, then peeks out and is back
    // to its mood ('down'); else it springs back up past where it was, boing,
    // and settles ('boing'); needs (a chat needs you): it pops straight back
    // up ('up': the host has it show its sign then). done(true) once it's back.
    // '' when it wasn't pushed
    pushed(needs, done) {
        if (!this.pushing) {
            if (done)
                done(false);
            return '';
        }
        this.pushing = false;
        this.pushHeldAt = 0;
        this.pushGives = null;
        const how = needs ? 'up' : this.gaveIn ? 'down' : 'boing';
        this.play({ steps: how === 'up' ? PUSH.needs : how === 'down' ? PUSH.back : PUSH.boing }, done, false);
        return how;
    }

    // (while pushed, each tick: towards where your hand has it on a spring,
    // shoving up now and then until it gives in, as it does once your hand
    // has held it down for TUG_MS)
    pushStep(dt) {
        if (!this.gaveIn && this.pushHeldAt && this.now - this.pushHeldAt >= TUG_MS)
            this.giveIn();
        let target = this.pushTarget;
        if (this.pushStill) {
            this.pushDepth = target;
            this.pushVel = 0;
        } else {
            if (!this.gaveIn) {
                const f = clamp01((target - this.pushFrom) / Math.max(1, (DEPTH.hidden - this.pushFrom) * PUSH_MOST));
                const ph = ((this.now - this.pushAt) % PUSH_HEAVE_MS) / PUSH_HEAVE_MS;
                if (this.now - this.pushAt > 250 && ph < 0.28)
                    target -= (1 + 3.5 * f) * Math.sin(Math.PI * ph / 0.28);
            }
            const w = 2 * Math.PI * PUSH_HZ;
            for (let left = dt; left > 0; left -= 8) {
                const h = Math.min(8, left) / 1000;
                this.pushVel += (w * w * (target - this.pushDepth) - 2 * PUSH_DAMP * w * this.pushVel) * h;
                this.pushDepth += this.pushVel * h;
            }
            this.pushDepth = Math.max(DEPTH.out, Math.min(DEPTH.hidden + 4, this.pushDepth));
        }
        const v = this.v;
        v.depth = v.depthFrom = v.depthTo = this.pushDepth;
        v.depthAt = this.now - 1000;
    }

    // Where your hand is as you pull, from its middle (box units: right +,
    // down +): it leans that way as it hangs on, more as it stretches
    tugToward(dx, dy) {
        this.tugAim = Math.max(-40, Math.min(40, Math.atan2(dx, Math.max(6, -dy)) * 180 / Math.PI));
    }

    // You let go before it came out: it drops back in, phew
    letGo(done) {
        if (!this.tugging) {
            if (done)
                done(false);
            return;
        }
        this.play({ steps: TUG.back }, done, false);
    }

    // Grabbed: out of the burrow, flailing; nothing else moves it until land()
    // Returns how much of its hole it leaves behind (0: none, it was tunnelling
    // or down; 1: the whole hole): the host keeps drawing that where it was
    // (drawHole), since the hole doesn't come along
    setHeld(held) {
        if (!held)
            return 0;
        const left = this.st.tunnel === '1' ? 0 : clamp01(this.v.hole);
        this.cancel();
        this.chasing = false;
        this.tugging = false;
        this.pushing = false;
        this.held = true;
        this.heldAt = this.now;
        this.apply({ depth: 'out', hole: 0, held: 1, arms: 'flail', eyes: 'wide', mouth: 'o', body: '', fx: dirt(8, 16) });
        // out at once, its hole gone from under it (a creature half in a hole that
        // closes while it moves would show where there's no hole)
        const v = this.v;
        v.depth = v.depthFrom = v.depthTo = DEPTH.out;
        v.hole = v.holeFrom = v.holeTo = 0;
        return left > 0.02 ? left : 0;
    }

    // Dropped from `height` box units: lands, maybe dizzy, then digs in right
    // there (stayOut: not yet, a cookie is out and it's off after it, see
    // cookie.mjs). Returns how it feels, for the words the host has it say:
    // 'sick' (from high up), 'dizzy' or 'fine'
    land(height, done, stayOut) {
        this.held = false;
        const feel = height > 28 ? 'sick' : height > 16 ? 'dizzy' : 'fine';
        const first = feel === 'sick' ? { eyes: 'spiral', mouth: 'wavy', plume: 'droop', orbit: 1, t: 1800 }
                    : feel === 'dizzy' ? { eyes: 'spiral', mouth: 'o', orbit: 1, t: 1200 }
                    : { eyes: 'happy', mouth: 'smile', t: 700 };
        this.play({ steps: () => [Object.assign({ depth: 'out', hole: 0, body: 'land' }, first)].concat(stayOut ? [] : [
            { depth: 'out', hole: 1, eyes: feel === 'sick' ? 'tired' : 'open', mouth: feel === 'sick' ? 'wavy' : 'flat', look: [-1.5, 0.5],
              t: 500 },   // the hole opens under it first
            { body: 'spin', eyes: 'squint', fx: dirt(10), t: 700 },
            { eyes: 'happy', t: 500 }]) }, done, false);
        return feel;
    }

    // Shown at rest in a pose right away, no motion in between (icons, previews)
    pose(step) {
        this.cancel();
        this.apply(step || {}, true);
        this.nextBlink = this.now + 1e9;   // eyes open for a still picture
        this.nextGlance = this.now + 1e9;
        this.glance = [0, 0];
        const look = this.st.look || [0, 0];
        this.v.lx = look[0];
        this.v.ly = look[1];
    }

    // ------------------------------------------------------------ a cookie (cookie.mjs)

    // It sees a cookie (look: where it is, from its eyes, ahead); asleep, it
    // wakes up first. done(true): it has seen it
    seeCookie(look, done) {
        if (this.held) {
            if (done)
                done(false);
            return;
        }
        this.chasing = false;
        this.play({ steps: COOKIE.spot(look, this.mood === 'done') }, done, false);
    }

    // Off after it: out of its burrow at a jump (or, out already, on its
    // feet at once). No action or mood moves it until it has it (eat) or you
    // pick it up. Returns how much of its hole it leaves behind, as setHeld
    chase() {
        const left = this.st.tunnel === '1' || this.held ? 0 : clamp01(this.v.hole);
        const out = this.onFloor;
        this.cancel();
        this.held = false;
        this.chasing = true;
        this.chased = out ? 'stand' : 'out';
        this.apply(COOKIE.chase[this.chased]());
        const v = this.v;
        v.hole = v.holeFrom = v.holeTo = 0;
        return left > 0.02 ? left : 0;
    }

    // How it goes after it: 'run', 'stand', 'beg' (out of reach), 'leap',
    // 'reach' (a jump for one out of reach), 'pout'; look: where it is, as for seeCookie (eased, as its glances)
    chaseAs(pose, look) {
        if (!this.chasing)
            return;
        if (pose !== this.chased && COOKIE.chase[pose]) {
            this.chased = pose;
            this.apply(COOKIE.chase[pose]());
        }
        if (look)
            this.st.look = look;
    }

    // The cookie it's after or eating is gone (CookieGame.stop): it digs in
    // where it is
    cookieGone(done) {
        this.chasing = false;
        this.play({ steps: COOKIE.gone }, done, false);
    }

    // It has it: eats it (flavour: see FLAVOURS in actions.mjs; caught: out
    // of the air), says thanks its way now and then, and digs in where it is
    eat(flavour, caught, done) {
        this.chasing = false;
        this.play({ steps: COOKIE.eat(flavour, caught) }, done, false);
    }

    // ------------------------------------------------------------ steps

    play(nameOrDef, done, auto) {
        const def = typeof nameOrDef === 'string' ? ACTIONS[nameOrDef] : nameOrDef;
        this.cancel();
        if (nameOrDef === 'arrive')
            this.away = false;
        if (!def) {
            if (done)
                done(false);
            return;
        }
        const keep = def.keep || {};
        const steps = def.steps(this.words).map(s => Object.assign({}, keep, s));
        this.run = { name: typeof nameOrDef === 'string' ? nameOrDef : '', steps: steps, i: -1, until: 0, done: done || null, auto: !!auto };
        this.next();
    }

    cancel() {
        const r = this.run;
        this.run = null;
        // (it pops up where it is, not gliding on to where the tunnel went)
        if (r && r.i >= 0 && r.i < r.steps.length && r.steps[r.i].travel && this.onTravelStop)
            this.onTravelStop();
        if (r && r.done)
            r.done(false);
    }

    next() {
        const r = this.run;
        r.i += 1;
        if (r.i >= r.steps.length) {
            this.run = null;
            if (r.name === 'leave')
                this.away = true;
            this.apply({});
            const p = (MOODS[this.mood] || MOODS.idle).pause;
            this.nextBrain = this.now + random.rnd(p[0], p[1]);
            if (r.done)
                r.done(true);
            return;
        }
        const step = r.steps[r.i];
        r.until = this.now + (step.t || 600);
        this.apply(step, step.snap === 1);
        if (step.travel && this.onTravel)
            this.onTravel(step.t || 1500);
    }

    apply(step, snap) {
        this.stepAt = this.now;
        const prev = this.st, st = {};
        for (const k of KEYS) {
            const v = step[k] !== undefined ? step[k] : this.base[k];
            st[k] = v === undefined || v === null ? '' : String(v);
            if (st[k] !== prev[k] || (step[k] !== undefined && (k === 'body' || k === 'plume' || k === 'arms')))
                this.since[k] = this.now;
        }
        if (this.away && step.depth === undefined) {
            st.depth = 'gone';   // (left: not back up by itself)
            st.hole = '0';
        }
        st.it = step.it || 1;
        st.look = step.look || this.base.look || null;
        if (st.depth !== prev.depth || st.arms !== prev.arms || st.plume !== prev.plume || st.sip !== prev.sip
            || String(st.look) !== String(prev.look))
            this.easeAt = this.now;
        if (step.gum)
            st.gum = String(step.gum);
        this.st = st;
        const depth = DEPTH[st.depth] !== undefined ? DEPTH[st.depth] : DEPTH.half;
        // (out for a moment, a jump or a sneeze, its hole stays: only held or
        // tunnelling it has none)
        const hole = st.hole === '0' ? 0 : 1;
        const v = this.v;
        if (snap) {
            v.depth = v.depthFrom = v.depthTo = depth;
            v.hole = v.holeFrom = v.holeTo = hole;
            const a = ARMS[st.arms] || ARMS.rest;
            v.armL = a[0];
            v.armR = a[1];
            v.plume = plumeAngle(st.plume, 0, 1);
        } else {
            if (depth !== v.depthTo) {
                v.depthFrom = v.depth;
                v.depthTo = depth;
                v.depthAt = this.now;
            }
            if (hole !== v.holeTo) {
                v.holeFrom = v.hole;
                v.holeTo = hole;
                v.holeAt = this.now;
            }
        }
        for (const f of (step.fx || [])) {
            const o = f[3] || {};
            this.fx.push({ kind: f[0], x: f[1], y: f[2], o: o, born: this.now + (o.delay || 0) * 1000 });
        }
    }

    // ------------------------------------------------------------ time

    tick(now) {
        const dt = this.last ? Math.min(100, Math.max(0, now - this.last)) : 0;
        this.last = now;
        this.now = now;
        if (this.run && now >= this.run.until)
            this.next();
        if (!this.run && !this.held && !this.chasing && !this.pushing && this.brainOn && now >= this.nextBrain)
            this.think();
        if (this.held && now - this.heldAt > 2200 && this.st.eyes !== 'tiny') {
            this.st.eyes = 'tiny';     // held up for long: scared
            this.st.mouth = 'wavy';
        }
        const v = this.v, st = this.st;
        const before = {};
        for (const key in EASED)
            before[key] = v[key] || 0;
        if (this.pushing)
            this.pushStep(dt);
        // the burrow depth: pops up with a little overshoot, sinks smoothly
        const dp = clamp01((now - v.depthAt) / 450);
        v.depth = lerp(v.depthFrom, v.depthTo, v.depthTo > v.depthFrom && v.depthTo >= DEPTH.hidden ? dp * dp : outBack(dp));
        const hp = clamp01((now - v.holeAt) / 350);
        v.hole = lerp(v.holeFrom, v.holeTo, v.holeTo > v.holeFrom ? outBack(hp) : hp);
        // arms, lamp stalk, eyes: eased towards where they're going
        const k = tau => 1 - Math.exp(-dt / tau);
        const moving = armMove(st.arms, now - (this.since.arms || 0));
        const target = moving || ARMS[st.arms] || ARMS.rest;
        v.armL += (target[0] - v.armL) * k(moving ? 40 : 70);
        v.armR += (target[1] - v.armR) * k(moving ? 40 : 70);
        v.armLy = moving ? moving[2] : 0;
        v.armRy = moving ? moving[3] : 0;
        const plumeTarget = st.tunnel === '1' ? plumeAngle('wild', now, 1) : plumeAngle(st.plume, now - (this.since.plume || 0), Number(st.it));
        v.plume = st.plume === 'twirl' || st.plume === 'wild' || st.tunnel === '1' ? plumeTarget : v.plume + (plumeTarget - v.plume) * k(70);
        v.sip += ((st.sip === '1' ? 1 : 0) - v.sip) * k(90);
        this.tugLean += ((st.body === 'tug' ? this.tugAim : 0) - this.tugLean) * k(110);
        if (st.body !== 'tug' && Math.abs(this.tugLean) < 0.05)
            this.tugLean = 0;
        // (drawn out as the tug goes on; let go, popped out or pushed back down, easing off)
        const stretch = st.body === 'tug' ? sine(Math.min(1, (now - (this.since.body || 0)) / TUG_MS)) : 0;
        this.stretch = stretch >= this.stretch ? stretch : this.stretch + (stretch - this.stretch) * k(80);
        if (Math.abs(this.stretch - stretch) < 0.002)
            this.stretch = stretch;
        const squash = this.pushing && !this.pushStill
            ? sine(Math.min(1, clamp01((this.pushDepth - this.pushFrom) / Math.max(1, (DEPTH.hidden - this.pushFrom) * PUSH_MOST)))) : 0;
        this.squash += (squash - this.squash) * k(this.pushing ? 45 : 80);
        if (Math.abs(this.squash - squash) < 0.002)
            this.squash = squash;
        // glances and blinks of its own
        if (now >= this.nextGlance) {
            this.glance = st.prop || Math.random() < 0.4 ? [0, 0] : [random.rnd(-1.6, 1.6), random.rnd(-1, 0.8)];
            this.nextGlance = now + random.rnd(900, 3200);
        }
        const look = st.look || this.glance;
        v.lx += (look[0] - v.lx) * k(90);
        v.ly += (look[1] - v.ly) * k(90);
        if (!this.nextBlink)
            this.nextBlink = now + random.rnd(1200, 4000);   // not straight away
        if (now >= this.nextBlink && BLINKING[st.eyes]) {
            this.blinkUntil = now + 110;
            this.nextBlink = now + (Math.random() < 0.22 ? 250 : random.rnd(1800, 5200));
        }
        this.fx = this.fx.filter(p => now - p.born < (p.o.dur || 1.6) * 1000);
        // How often the host should draw it now (each picture costs)
        let quick = false, slow = false;
        for (const key in EASED) {
            const moved = Math.abs((v[key] || 0) - before[key]) * 40 / Math.max(dt, 1);
            quick = quick || moved > EASED[key];
            slow = slow || moved > EASED[key] / 20;
        }
        const body = st.body === '' ? null : st.body === 'fast' ? true : bodyMove(st.body, now - (this.since.body || 0), Number(st.it));
        quick = quick || this.held || this.pushing || this.squash > 0 || this.stretch > 0 || this.tugLean !== 0 || st.walk === '1' || QUICK_PROPS[st.prop] === 1 || (body !== null && QUICK_BODY[st.body] === 1)
            || (BLINKING[st.eyes] === 1 && now >= this.nextBlink - 45) || now < this.blinkUntil + 45;
        slow = slow || (body !== null && RESTING_BODY[st.body] !== 1) || this.fx.some(p => p.kind !== 'z') || st.tunnel === '1' || st.orbit === '1'
            || st.think === '1' || SLOW_PROPS[st.prop] === 1;
        this.frameMs = quick ? 40 : slow ? 80 : 200;
        // A big move (no picture shows it, see stills), and when what it threw meanwhile lands
        const once = ONCE[st.body];
        const big = (once !== undefined && now - (this.since.body || 0) < once * (st.body === 'hop' || st.body === 'jump' ? Number(st.it) : 1))
            || (Math.abs(v.depthTo - v.depthFrom) >= BIG_DEPTH && dp < 1) || (v.holeTo !== v.holeFrom && hp < 1) || this.pushing;
        if (big && !this.big)
            this.bigAt = this.stepAt;   // (the step that started it: maybe a reaction since the last tick)
        this.big = big;
        if (big)
            this.landsAt = this.fx.reduce((t, p) => p.born >= this.bigAt ? Math.max(t, p.born + (p.o.dur || 1.6) * 1000) : t, now);
        // The new pose has settled (a film shows it from its pictures again)
        this.settled = !big && dp >= 1 && hp >= 1 && now - this.easeAt >= SETTLE_MS && !this.oneShot();
    }

    // A move that happens once and has no pictures is under way (see films)
    oneShot() {
        if (this.squash > 0 || this.stretch > 0 || this.tugLean !== 0)
            return true;   // (no picture is squashed, drawn out or leaning)
        for (const key in ONE_SHOT) {
            const ms = ONE_SHOT[key][this.st[key]];
            if (ms !== undefined && this.now - (this.since[key] || 0) < ms * (key === 'plume' ? Number(this.st.it) : 1))
                return true;
        }
        return false;
    }

    think() {
        if (this.away) {
            this.nextBrain = this.now + 2000;
            return;
        }
        const mood = MOODS[this.mood] || MOODS.idle;
        const pool = Object.assign({}, this.playful || !mood.calm ? mood.pool : mood.calm);
        if (!this.travels || !this.onTravel)
            delete pool.dig;
        delete pool[this.lastAuto];
        const names = Object.keys(pool);
        if (!names.length) {
            this.nextBrain = this.now + 2000;
            return;
        }
        let r = Math.random() * names.reduce((s, n) => s + pool[n], 0);
        let name = names[0];
        for (const n of names) {
            r -= pool[n];
            if (r < 0) {
                name = n;
                break;
            }
        }
        this.lastAuto = name;
        this.play(name, null, true);
    }

    // ------------------------------------------------------------ stills (see above)

    beat() {
        const st = this.st;
        const beats = [ARM_BEATS[st.arms], BODY_BEATS[st.body], PLUME_BEATS[st.plume], PROP_BEATS[st.prop], st.tunnel === '1' ? TUNNEL_BEAT : undefined]
            .filter(b => b !== undefined);
        if (!beats.length)
            return -1;
        const step = BEAT_MS * Math.max(1, Math.round(Math.min.apply(null, beats) / 2 / BEAT_MS));
        const beat = Math.floor(this.now / step) % 4;
        return beat === 3 && !ONE_WAY[st.arms] && !ONE_WAY[st.body] && !ONE_WAY[st.prop] && st.tunnel !== '1' ? 1 : beat;
    }

    // (busy with a quick move, it looks ahead: each glance would take four new pictures)
    stillLook() {
        const look = this.st.look || (this.beat() >= 0 ? [0, 0] : this.glance);
        return [Math.round(look[0] * 2) / 2, Math.round(look[1] * 2) / 2];
    }

    // What a picture of it shows now, as "pose#details": the host fades over
    // to a new pose, and just changes the picture for new details (a blink, a
    // glance, a beat); '' during a big move
    stillKey() {
        if (this.big || this.now < this.landsAt)
            return '';
        const st = this.st;
        const blink = this.now < this.blinkUntil && BLINKING[st.eyes] === 1;
        return KEYS.map(k => st[k]).join(',') + ',' + st.it + ',' + (st.gum || '') + (this.facingLeft ? ',L' : ',R')
            + '#' + this.stillLook().join(',') + (blink ? ',blink' : '') + ',' + this.beat();
    }

    drawStill(ctx) {
        let s = this.stillOne;
        if (!s)
            s = this.stillOne = new Talpy({ brain: false });
        s.colors = this.colors;
        s.theme = this.theme;
        s.facingLeft = this.facingLeft;
        const st = this.st, step = { it: st.it, look: this.stillLook() };
        for (const k of KEYS) {
            if (st[k] !== '')
                step[k] = st[k];
        }
        if (st.gum)
            step.gum = st.gum;
        if (this.now < this.blinkUntil && BLINKING[st.eyes] === 1)
            step.eyes = 'closed';
        // a quick move where this beat has it (ms into it)
        const beat = Math.max(0, this.beat());
        const at = beats => beat * beats / 2;
        s.now = 1e6 + at(PROP_BEATS[st.prop] || (st.tunnel === '1' ? TUNNEL_BEAT : 0));
        s.pose(step);
        this.placeMoves(s, st, at);
        s.draw(ctx);
    }

    // (the still one's quick moves where at(beats) has them)
    placeMoves(s, st, at) {
        const arms = ARM_BEATS[st.arms] !== undefined ? armMove(st.arms, at(ARM_BEATS[st.arms])) : null;
        s.v.armLy = arms ? arms[2] : 0;
        s.v.armRy = arms ? arms[3] : 0;
        if (arms) {
            s.v.armL = arms[0];
            s.v.armR = arms[1];
        }
        if (st.tunnel === '1')
            s.v.plume = plumeAngle('wild', at(PLUME_BEATS.wild), 1);
        else if (PLUME_BEATS[st.plume] !== undefined)
            s.v.plume = plumeAngle(st.plume, at(PLUME_BEATS[st.plume]), 1);
        // (a move that happens once shows as done)
        s.since.body = s.now - (BODY_BEATS[st.body] !== undefined ? at(BODY_BEATS[st.body]) : 1e7);
        s.walkMs = this.walkMs;
        s.walkT = st.walk === '1' ? at(this.walkMs / 2) : -1;
    }

    // ------------------------------------------------------------ films (see films.mjs)

    // The quick moves under way: [what moves, its beat] (beats as above)
    moves() {
        const st = this.st, out = [];
        if (ARM_BEATS[st.arms] !== undefined)
            out.push(['arms', ARM_BEATS[st.arms]]);
        if (BODY_BEATS[st.body] !== undefined)
            out.push(['body', BODY_BEATS[st.body]]);
        if (PLUME_BEATS[st.plume] !== undefined)
            out.push(['plume', PLUME_BEATS[st.plume]]);
        if (PROP_BEATS[st.prop] !== undefined)
            out.push(['prop', PROP_BEATS[st.prop]]);
        if (st.tunnel === '1')
            out.push(['tunnel', TUNNEL_BEAT]);
        if (st.walk === '1')   // (a step each half: his feet in its pictures as they go)
            out.push(['walk', this.walkMs / 2]);
        return out;
    }

    // What a film's picture of it shows now: its pose and details (as for
    // stillKey) and where it is in a quick move's round, pictures at least
    // frameMs apart and at most maxFrames a round (a move that swings back
    // shows the same ones on the way back); null during a big move. rest: no
    // quick move under way; every: ms from one picture to the next, a whole
    // number of the host's ticks (clockMs apart). ticksSince(id, ms), from
    // the film: the ticks since the move (id) began, ms ago; a picture then
    // shows for exactly its ticks, 2 each, not 2, 2, 3 (by time, a picture
    // due right at a tick showed for 1 tick or 3 as the ticks jittered).
    still(frameMs, maxFrames, clockMs, ticksSince) {
        if (this.big || this.now < this.landsAt || this.oneShot())
            return null;
        const st = this.st, moves = this.moves();
        let frames = 1, frame = 0, round = 0, every = Infinity;
        if (moves.length) {
            let quick = moves[0];
            for (const m of moves) {
                if (m[1] < quick[1])
                    quick = m;
            }
            round = 2 * quick[1];
            const oneWay = ONE_WAY[st.arms] === 1 || ONE_WAY[st.body] === 1 || ONE_WAY[st.prop] === 1 || st.tunnel === '1';
            const tick = Math.max(1, frameMs);
            const clock = clockMs > 0 ? clockMs : tick;
            const ticks = Math.ceil(round / (tick * (maxFrames || 12)));   // frameMs a picture shows
            const q = Math.max(1, Math.round(ticks * tick / clock));        // the host's ticks a picture shows
            every = q * clock;
            frames = Math.max(4, Math.round(round / (ticks * tick)));
            if (!oneWay)
                frames += frames % 2;
            // (counted from when that move began, as it's drawn live)
            const ms = Math.max(0, this.now - (this.since[quick[0]] || 0));
            frame = ticksSince ? Math.floor(ticksSince(quick[0] + '@' + (this.since[quick[0]] || 0), ms) / q) % frames
                               : Math.floor((ms + clock / 2) / every) % frames;
            if (!oneWay && frame > frames / 2)
                frame = frames - frame;
        }
        const blink = this.now < this.blinkUntil && BLINKING[st.eyes] === 1;
        const look = this.stillLook();
        const pose = KEYS.map(k => st[k]).join(',') + ',' + st.it + ',' + (st.gum || '') + (this.facingLeft ? ',L' : ',R');
        return { key: pose + '#' + look.join(',') + (blink ? ',blink' : '') + ',' + frame + '/' + frames, pose: pose, st: st,
                 look: look, blink: blink, phase: frame / frames, rest: !moves.length, left: this.facingLeft,
                 every: every };
    }

    // Draws film picture d (still()), or one on its way there from picture
    // `from` (p: 0 there, 1 arrived), without what flies about
    drawFilm(ctx, d, from, p) {
        let was = null;
        if (from && p < 1) {
            const v = this.posed(from).v;
            was = TWEENED.map(k => v[k] || 0);
        }
        const s = this.posed(d);
        if (was) {
            const e = sine(clamp01(p));
            TWEENED.forEach((k, i) => {
                s.v[k] = lerp(was[i], s.v[k] || 0, e);
            });
        }
        s.draw(ctx, true);
    }

    // (the still one, posed as film picture d)
    posed(d) {
        let s = this.stillOne;
        if (!s)
            s = this.stillOne = new Talpy({ brain: false });
        s.colors = this.colors;
        s.theme = this.theme;
        s.holeImage = this.holeImage;
        s.facingLeft = d.left;
        const st = d.st, step = { it: st.it, look: d.look };
        for (const k of KEYS) {
            if (st[k] !== '')
                step[k] = st[k];
        }
        if (st.gum)
            step.gum = st.gum;
        if (d.blink)
            step.eyes = 'closed';
        const at = beats => d.phase * 2 * beats;
        s.now = 1e6 + at(PROP_BEATS[st.prop] || (st.tunnel === '1' ? TUNNEL_BEAT : 0));
        s.pose(step);
        this.placeMoves(s, st, at);
        return s;
    }

    // ------------------------------------------------------------ drawing

    // Draws the 64 × 64 box at the context's current transform (without what
    // flies about: a host that draws that on its own, see films.mjs)
    draw(ctx, withoutParticles) {
        const now = this.now, st = this.st, v = this.v, pal = this.colors;
        const ms = key => now - (this.since[key] || 0);
        const move = bodyMove(st.body, ms('body'), Number(st.it)) || {};
        // drawn out as you pull it (tug), easing off as it comes out, drops
        // back in or is pushed back down (a still one: as far as the tug goes)
        const stretch = st.body === 'tug' ? Math.max(this.stretch, sine(Math.min(1, ms('body') / TUG_MS))) : this.stretch;
        if (stretch > 0) {
            move.torso = true;
            move.wy = (move.wy || 0) - 3.5 * stretch;
            move.sx = (move.sx || 1) * (1 - 0.1 * stretch);
            move.sy = (move.sy || 1) * (1 + 0.2 * stretch);
        }
        if (this.squash > 0) {   // (squashed as you push it down, easing off as it comes back up or into a tug)
            move.torso = true;
            move.sx = (move.sx || 1) * (1 + 0.13 * this.squash);
            move.sy = (move.sy || 1) * (1 - 0.12 * this.squash);
        }
        if (st.body === 'push' && this.pushing && !this.gaveIn)   // (trembling as it pushes back)
            move.wx = (move.wx || 0) + lerp(-0.5, 0.5, alt(ms('body'), 60)) * Math.min(1, ms('body') / 300);
        if (this.tugLean !== 0)   // (leaning towards your hand, about its burrow: tugToward; easing back after)
            move.wr = (move.wr || 0) + this.tugLean * (0.4 + 0.6 * stretch) * (this.facingLeft ? -1 : 1);
        ctx.save();
        if (this.facingLeft) {
            ctx.translate(BOX, 0);
            ctx.scale(-1, 1);
        }
        // its shadow when it's out on the floor
        if (st.depth === 'out' && v.depth < 3) {
            ctx.save();
            art.about(ctx, 32, 57.6, 0, st.held === '1' ? 0.5 : move.shadow || 1, 1);
            art.ellipse(ctx, 32, 57.6, 15, 2.1, 'rgba(20,25,45,0.16)');
            ctx.restore();
        }
        const tunneling = st.tunnel === '1';
        if (!tunneling && v.hole > 0.02)
            this.drawHolePart(ctx, 'back');
        // the creature, cut along the burrow (art.traceCut) while it's in it or
        // its hole is there (out for a moment, its feet would hang in the hole)
        ctx.save();
        const holed = !tunneling && v.hole > 0.02;
        if (st.depth !== 'out' || v.depth > 0 || holed) {
            const h = holed ? Math.min(1.1, v.hole) : 1;
            ctx.beginPath();
            art.traceCut(ctx, lerp(0.05, 1, h), lerp(0.2, 1, h));
            ctx.clip();
        }
        ctx.translate(0, v.depth);
        this.drawCreature(ctx, now, st, v, pal, move, ms);
        ctx.restore();
        if (tunneling) {
            ctx.save();
            const p = alt(now, 260);
            art.about(ctx, 32, 61.4, 0, lerp(1, 1.08, p), lerp(0.9, 1.1, p));
            art.tunnel(ctx);
            ctx.restore();
        } else if (v.hole > 0.02) {
            this.drawHolePart(ctx, 'front');
        }
        ctx.restore();
        if (!withoutParticles)
            this.drawParticles(ctx, now);
    }

    // Whether anything flies about now (drawParticles draws it), and whether
    // it's quick: z's float up slowly
    particles(now) {
        let any = false;
        for (const p of this.fx) {
            if (now < p.born)
                continue;
            if (p.kind !== 'z')
                return 2;
            any = true;
        }
        return any ? 1 : 0;
    }

    // (the open hole from the host's sheet when it has one: pixel for pixel,
    // since it was drawn at this transform)
    drawHolePart(ctx, part) {
        const image = this.holeImage && Math.abs(this.v.hole - 1) < 0.001 ? this.holeImage(part, this.facingLeft) : null;
        if (!image) {
            holePart(ctx, this.v.hole, part === 'front' ? art.holeFront : art.holeBack);
            return;
        }
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(image, 0, 0);
        ctx.restore();
    }

    drawCreature(ctx, now, st, v, pal, move, ms) {
        // the whole creature: hops, sways, tumbles
        ctx.save();
        ctx.translate(move.wx || 0, move.wy || 0);
        const W = this.walkMs, wt = this.walkT >= 0 ? this.walkT : now;   // (a picture's own time in its step: posed)
        if (st.walk === '1')
            ctx.translate(0, -1.3 * alt(wt, W / 2));
        if (move.wr)
            art.about(ctx, move.ox || 32, move.oy || 57, move.wr);
        if (st.depth === 'out')
            this.drawTail(ctx, now, st, pal, ms);
        let feet = null;
        if (st.held === '1')
            feet = [lerp(-18, 18, alt(now, 450)), lerp(-18, 18, alt(now + 225, 450)), 0, 0];
        else if (st.walk === '1')
            feet = [0, 0, kf((wt % W) / W, [[0, 0], [0.25, -2.4], [0.5, 0], [1, 0]]), kf(((wt + W / 2) % W) / W, [[0, 0], [0.25, -2.4], [0.5, 0], [1, 0]])];
        // feet stand on the ground: over its hole they'd hang in it (unless it jumps clear)
        if (st.tunnel === '1' || v.hole <= 0.02 || (move.wy || 0) < -3)
            art.feet(ctx, pal, feet);
        // the torso: breathing, squash and stretch
        ctx.save();
        if (move.torso) {
            ctx.translate(0, move.ty || 0);
            art.about(ctx, 32, 55, move.tr || 0, move.sx, move.sy);
        } else {
            const p = (now % (st.body === 'fast' ? 600 : 2800)) / (st.body === 'fast' ? 600 : 2800);
            art.about(ctx, 32, 55, 0, kf(p, [[0, 1], [0.5, 1.022], [1, 1]]), kf(p, [[0, 1], [0.5, 0.978], [1, 1]]));
        }
        this.drawLamp(ctx, now, st, v, pal, move);
        art.body(ctx, pal);
        if (st.prop === 'headphones') {
            ctx.save();
            ctx.translate(0, art.PLUME_Y);
            art.headphones(ctx);
            ctx.restore();
        }
        this.drawFace(ctx, now, st, v, pal, move, ms);
        art.propBack(ctx, st.prop, now, this.theme.fx, v.sip, art.FACE_Y);
        this.drawArm(ctx, 14.5, v.armL, v.armLy || 0, pal, st.prop === 'balloon' ? 'balloon' : '', now);
        this.drawArm(ctx, 49.5, v.armR, v.armRy || 0, pal, st.prop === 'sign' ? 'sign' : st.arms === 'selfie' ? 'selfie' : '', now);
        art.propFront(ctx, st.prop, now, ms('prop'), { fail: st.fail === '1', gum: Number(st.gum) || 2000, bite: Number(st.bite) || 0, skin: pal.skin,
                                                       treat: st.treat });
        if (st.think === '1')
            art.think(ctx, now, this.theme.fx);
        ctx.restore();
        if (st.prop === 'juggle')
            art.juggle(ctx, now);
        if (st.prop === 'battery')
            art.battery(ctx, now, this.theme.fx);
        if (st.orbit === '1') {
            ctx.save();
            ctx.translate(0, art.PLUME_Y);
            art.orbit(ctx, now);
            ctx.restore();
        }
        ctx.restore();
    }

    drawTail(ctx, now, st, pal, ms) {
        let a = lerp(-6, 9, alt(now, 2400));
        if (st.tail === 'wag')
            a = lerp(-16, 22, alt(now, 200));
        else if (st.tail === 'droop')
            a = 38;
        else if (st.tail === 'up')
            a = -30;
        ctx.save();
        art.about(ctx, 48.5, 50.5, a);
        art.tail(ctx, pal);
        ctx.restore();
    }

    drawLamp(ctx, now, st, v, pal, move) {
        const lamp = art.LAMP[st.lamp] || art.LAMP.idle;
        let glow = alt(now, st.lamp === 'needs' ? 700 : 2400), flicker = 1;
        if (st.lamp === 'limit') {
            glow = 0;
            const p = (now % 1600) / 1600;
            flicker = p < 0.75 ? 1 : p < 0.85 ? 0.3 : p < 0.9 ? 0.9 : 0.2;
        }
        ctx.save();
        ctx.translate(0, art.PLUME_Y);
        art.about(ctx, 31.4, 25.6, v.plume);
        if (move.turn !== undefined)
            art.about(ctx, 31.4, 25.6, 0, kf(move.turn, [[0, 1], [0.32, -1], [0.46, -1], [0.8, 1], [1, 1]]), 1);
        art.plume(ctx, pal, lamp, glow, flicker);
        ctx.restore();
    }

    // (no clip of its own: Qt's canvas puts the cut back in the wrong place
    // after a clip inside it, and hands showed under the burrow)
    drawFace(ctx, now, st, v, pal, move, ms) {
        ctx.save();
        ctx.translate(0, art.FACE_Y);
        if (move.turn !== undefined) {
            const p = move.turn;
            const tx = p < 0.22 ? lerp(0, 13, p / 0.22) : p < 0.32 ? lerp(13, 27, (p - 0.22) / 0.1)
                     : p < 0.46 ? -27 : p < 0.58 ? lerp(-27, -13, (p - 0.46) / 0.12) : p < 0.8 ? lerp(-13, 0, sine((p - 0.58) / 0.22)) : 0;
            const sx = p < 0.22 ? lerp(1, 0.55, p / 0.22) : p < 0.32 ? lerp(0.55, 0.3, (p - 0.22) / 0.1)
                     : p < 0.46 ? 0.3 : p < 0.58 ? lerp(0.3, 0.55, (p - 0.46) / 0.12) : p < 0.8 ? lerp(0.55, 1, sine((p - 0.58) / 0.22)) : 1;
            // it fades as it slides round the body's edge
            const fade = clamp01((24 - Math.abs(tx)) / 8);
            if (fade <= 0) {
                ctx.restore();
                return;
            }
            ctx.globalAlpha = ctx.globalAlpha * fade;
            ctx.translate(tx, 0);
            art.about(ctx, 32, 40, 0, sx, 1);
        }
        if (st.blush === '1')
            art.blush(ctx);
        const blink = now < this.blinkUntil ? 0.08 : 1;
        // a magnifier or telescope covers the right eye with its own
        art.eyes(ctx, pal, st.eyes || 'open', [v.lx, v.ly], blink, now);
        art.mouth(ctx, st.mouth);
        ctx.restore();
    }

    drawArm(ctx, x, angle, dy, pal, holds, now) {
        ctx.save();
        ctx.translate(x, 41 + dy);
        ctx.rotate(angle * Math.PI / 180);
        art.arm(ctx, pal);
        if (holds === 'balloon')
            art.balloon(ctx, lerp(-6, 6, alt(now, 1600)));
        else if (holds === 'sign')
            art.sign(ctx);
        else if (holds === 'selfie')
            art.selfie(ctx);
        ctx.restore();
    }

    drawParticles(ctx, now) {
        for (const p of this.fx) {
            const o = p.o, life = (o.dur || 1.6) * 1000, q = (now - p.born) / life;
            if (q < 0 || q > 1)
                continue;
            let x = p.x, y = p.y, s = 1, rot = 0, a = 1;
            if (o.path === 'fly') {
                const pts = [[0, 0], [-14, -9], [-4, -19], [9, -7], [1, -15], [-8, -26]];
                const seg = Math.min(4.999, q * 5), i = Math.floor(seg), f = sine(seg - i);
                x += lerp(pts[i][0], pts[i + 1][0], f);
                y += lerp(pts[i][1], pts[i + 1][1], f);
                a = q < 0.08 ? q / 0.08 : q > 0.85 ? (1 - q) / 0.15 : 1;
            } else if (o.path === 'plane') {
                const pts = [[0, 0, 0, 0], [0.4, 28, -14, -10], [0.7, 50, -5, 14], [1, 78, -20, -6]];
                let i = 1;
                while (i < 3 && q > pts[i][0])
                    i++;
                const f = sine((q - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]));
                x += lerp(pts[i - 1][1], pts[i][1], f);
                y += lerp(pts[i - 1][2], pts[i][2], f);
                rot = lerp(pts[i - 1][3], pts[i][3], f);
                a = q > 0.7 ? (1 - q) / 0.3 : 1;
            } else if (o.path === 'crawl') {
                x -= 14 * q;
                y -= q < 0.5 ? 2 * q : 2 * (1 - q);
                a = q < 0.15 ? q / 0.15 : q > 0.85 ? (1 - q) / 0.15 : 1;
            } else if (o.path === 'pop') {
                s = lerp(0.4, 1.5, q);
                a = 1 - q;
            } else if (o.path === 'rise') {        // a soap bubble: wobbles up, then pops
                const e = ease('out', q);
                x += (o.dx || 0) * e + Math.sin(q * 9) * 1.4;
                y += (o.dy === undefined ? -20 : o.dy) * e;
                s = q > 0.88 ? lerp(1, 1.5, (q - 0.88) / 0.12) : lerp(0.5, 1, Math.min(1, q * 4));
                a = q > 0.88 ? (1 - q) / 0.12 : q < 0.1 ? q / 0.1 : 1;
            } else if (o.path === 'grow') {        // a flower: grows up, sways, fades away
                s = q < 0.2 ? outBack(q / 0.2) : 1;
                rot = q > 0.2 ? Math.sin((q - 0.2) * 12) * 4 : 0;
                a = q > 0.85 ? (1 - q) / 0.15 : 1;
            } else if (o.path === 'breathe') {     // a bubble at its nose as it sleeps: in, out, bigger
                s = (0.4 + 0.8 * (0.5 - 0.5 * Math.cos(q * 3 * 2 * Math.PI))) * Math.min(1, 0.5 + q);
            } else if (o.path === 'shoot') {       // a shooting star across the sky
                const e = ease('in', q);
                x += 76 * e;
                y += 12 * e;
                a = q < 0.1 ? q / 0.1 : 1 - e;
            } else if (o.path === 'bulb') {
                s = q < 0.25 ? lerp(0, 1.25, q / 0.25) : q < 0.4 ? lerp(1.25, 1, (q - 0.25) / 0.15) : 1;
                a = q > 0.85 ? (1 - q) / 0.15 : 1;
            } else if (p.kind === 'clod') {
                const dx = o.dx || 0;
                x += q < 0.45 ? dx * 0.55 * (q / 0.45) : lerp(dx * 0.55, dx, (q - 0.45) / 0.55);
                y += q < 0.45 ? -9 * (1 - (1 - q / 0.45) * (1 - q / 0.45)) : lerp(-9, 3, ((q - 0.45) / 0.55) * ((q - 0.45) / 0.55));
                a = 1 - q;
            } else {
                const e = ease(o.ease, q);
                x += (o.dx || 0) * e;
                y += (o.dy === undefined ? -12 : o.dy) * e;
                s = lerp(o.s0 === undefined ? 0.6 : o.s0, o.s1 === undefined ? 1 : o.s1, e);
                rot = (o.rot || 0) * e;
                a = q < 0.15 ? q / 0.15 : q > 0.7 ? (1 - q) / 0.3 : 1;
            }
            ctx.save();
            ctx.globalAlpha = ctx.globalAlpha * clamp01(a);
            ctx.translate(this.facingLeft ? BOX - x : x, y);
            if (rot)
                ctx.rotate((this.facingLeft ? -rot : rot) * Math.PI / 180);
            const k = s * (o.scale || 1);
            ctx.scale(this.facingLeft && p.kind !== 'text' && p.kind !== 'z' ? -k : k, k);
            art.particle(ctx, p.kind, o, now, this.theme);
            ctx.restore();
        }
    }
}
