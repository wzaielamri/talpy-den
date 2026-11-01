// What Talpy does: each action is a few steps (a pose held for t ms, with
// things that fly off), picked at random within a mood so it never does the
// same thing twice. Depth is how far out of the burrow it is:
// gone < hidden (only the lamp shows) < peek < low < half < high < out.
//
// Plain ES2017 (see paths.mjs).

const rnd = (a, b) => a + Math.random() * (b - a);
const int = (a, b) => Math.floor(rnd(a, b + 1));
const pick = list => list[Math.floor(Math.random() * list.length)];
const chance = p => Math.random() < p;
const repeat = (n, fn) => {
    const out = [];
    for (let i = 0; i < n; i++)
        out.push(...[].concat(fn(i)));
    return out;
};

// Dirt thrown out of the burrow
export const dirt = (n, spread) => repeat(n || 6, () => [['clod', rnd(20, 44), rnd(53, 56),
    { dx: rnd(-(spread || 14), spread || 14), dur: rnd(0.6, 1), delay: rnd(0, 0.25), r: rnd(0.8, 1.5),
      color: pick(['#8a6a4f', '#a07a55', '#6e523a']) }]]);
const zzz = (x, y) => [['z', x, y, { dx: 6, dy: -14, dur: 2.2 }], ['z', x + 2, y - 2, { dx: 8, dy: -16, dur: 2.2, delay: 0.9, scale: 0.8 }],
    ['z', x + 1, y - 1, { dx: 5, dy: -15, dur: 2.2, delay: 1.8, scale: 0.65 }]];
const confetti = n => repeat(n, () => [['confetti', rnd(10, 54), rnd(0, 14), {
    color: pick(['#3daee9', '#27ae60', '#f2c94c', '#f28dbb', '#8e9af5']), dx: rnd(-6, 6), dy: rnd(30, 44),
    rot: rnd(-360, 360), dur: rnd(1.2, 1.9), delay: rnd(0, 0.4), s0: 1, s1: 1, ease: 'in' }]]);
const notes = () => [['note', 50, 26, { dx: 6, dy: -14, dur: 1.8 }], ['note', 12, 28, { dx: -6, dy: -12, dur: 1.8, delay: 0.6 }],
    ['note', 48, 22, { dx: 4, dy: -16, dur: 1.8, delay: 1.2 }]];
const sparkles = n => repeat(n, i => [['sparkle', rnd(14, 50), rnd(10, 26), { dy: rnd(-12, -6), dx: rnd(-4, 4), delay: i * 0.15 }]]);
const crumbs = () => repeat(int(2, 4), () => [['crumb', rnd(27, 37), rnd(44, 48), { dx: rnd(-5, 5), dy: rnd(8, 12), dur: rnd(0.5, 0.8),
    s0: 1, s1: 1, ease: 'in' }]]);
const bubbles = () => repeat(int(4, 6), i => [['bubble', rnd(33, 38), rnd(44, 46), { path: 'rise', r: rnd(1.4, 2.6), dx: rnd(-6, 16),
    dy: rnd(-28, -18), dur: rnd(1.8, 2.6), delay: i * 0.3 }]]);

// steps(w): w translates the few words it says (achoo!, boo!)
export const ACTIONS = {
    lookaround: { steps: () => [
        ...repeat(int(3, 5), () => ({ look: [rnd(-1.8, 1.8), rnd(-1.3, 0.6)], eyes: chance(0.15) ? 'wide' : 'open', t: rnd(450, 1000) })),
        { look: [0, 0], t: 300 }] },
    duck: { steps: () => [
        { eyes: 'wide', mouth: 'o', plume: 'up', t: 300 },
        { depth: 'hidden', eyes: 'closed', t: rnd(900, 1500) },
        { depth: 'peek', eyes: 'open', look: [-1.8, 0], t: 700 },
        { depth: 'peek', look: [1.8, 0], t: 700 },
        { eyes: 'happy', t: 500 }] },
    popup: { steps: () => repeat(int(1, 3), () => [{ depth: 'high', eyes: 'happy', mouth: 'open', plume: 'flick', t: 380 }, { t: 360 }]) },
    twirl: { steps: () => {
        const n = int(1, 3);
        return [{ plume: 'twirl', it: n, eyes: 'wide', mouth: 'o', t: 800 * n }, { eyes: 'happy', t: 500 }];
    } },
    sneeze: { steps: w => [
        ...repeat(int(1, 2), () => [{ eyes: 'squint', mouth: 'o', body: 'inhale', plume: 'up', t: rnd(380, 600) },
            { eyes: 'tiny', mouth: 'small', t: rnd(120, 260) }]),
        { depth: 'out', eyes: 'closed', mouth: 'open', body: 'jolt', plume: 'wild',
          fx: [['cloud', 18, 40, { dx: -12, dy: -4, s0: 0.4, s1: 1.4, dur: 1.2 }], ['text', 14, 26, { text: w('achoo!'), size: 6.5, dx: -4, dy: -8, dur: 1.4 }]], t: 520 },
        { eyes: 'tiny', mouth: 'small', fx: dirt(6), t: 600 },
        { eyes: 'happy', blush: 1, t: 700 }] },
    hiccups: { steps: w => [
        ...repeat(int(3, 5), () => [{ depth: 'high', eyes: 'wide', mouth: 'o', plume: 'flick',
            fx: [['text', 48, 26, { text: w('hic!'), size: 5.5, dy: -8, dx: rnd(-2, 4) }]], t: rnd(380, 520) },
            { eyes: 'open', mouth: 'flat', t: rnd(500, 1200) }]),
        { eyes: 'happy', t: 500 }] },
    gum: { steps: () => {
        const d = rnd(1600, 2600);
        return [{ prop: 'gum', gum: d, eyes: 'wide', look: [0, 1], mouth: 'none', t: d },
            { eyes: 'tiny', mouth: 'o', body: 'jolt', fx: [['splat', 32, 52, { dur: 0.5 }]], t: 500 },
            { eyes: 'closed', mouth: 'wavy', blush: 1, t: 800 }];
    } },
    coffee: { keep: { prop: 'mug', arms: 'hold', depth: 'high' }, steps: () => [
        { look: [1, 0.6], t: rnd(600, 1100) },
        ...repeat(int(1, 3), () => [{ arms: 'sip', sip: 1, eyes: 'closed', mouth: 'small', t: rnd(700, 1100) },
            { sip: 0, eyes: 'happy', fx: chance(0.4) ? [['heart', 46, 28, { dy: -10 }]] : [], t: rnd(700, 1200) }])] },
    music: { keep: { prop: 'headphones', body: 'bob' }, steps: () => [
        { eyes: 'closed', plume: 'bob', fx: notes(), t: rnd(2400, 3400) }] },
    butterfly: { steps: () => [
        { fx: [['butterfly', 8, 20, { dur: 3.2, color: pick(['#ffb347', '#7fd1ff', '#ff8fbf']), path: 'fly' }]], look: [-1.8, -1.4], eyes: 'wide', t: 700 },
        { look: [-0.6, -2], t: 600 }, { look: [1.6, -0.6], mouth: 'o', t: 600 },
        { depth: 'high', arms: 'up', eyes: 'happy', mouth: 'open', t: 600 },
        { look: [-1, -2], t: 700 }] },
    balloon: { keep: { prop: 'balloon', arms: 'balloon' }, steps: w => [
        { eyes: 'wide', mouth: 'o', t: 500 },
        { depth: 'out', body: 'float', eyes: 'happy', mouth: 'open', t: rnd(1800, 2600) },
        ...(chance(0.45)
            ? [{ prop: '', arms: 'flail', depth: 'out', eyes: 'tiny', mouth: 'o',
                 fx: [['splat', 6, 4, { dur: 0.5, path: 'pop' }], ['text', 10, 0, { text: w('pop!'), size: 6 }]], t: 450 },
               { prop: '', arms: 'rest', eyes: 'closed', mouth: 'wavy', fx: dirt(8), t: 900 }]
            : [{ eyes: 'happy', fx: dirt(4, 8), t: 600 }])] },
    plane: { steps: () => [
        { arms: 'throw', look: [1.6, -0.8], mouth: 'small', t: 300 },
        { arms: 'throw', fx: [['plane', 54, 30, { dur: 2.2, path: 'plane' }]], t: 250 },
        { look: [2, -1.6], eyes: 'wide', mouth: 'o', t: 900 },
        { depth: 'high', eyes: 'happy', mouth: 'open', arms: 'up', t: 700 }] },
    flip: { steps: () => [
        { body: 'inhale', eyes: 'squint', t: 350 },
        { depth: 'out', body: 'tumble', eyes: 'closed', mouth: 'open', plume: 'wild', t: 1000 },
        { body: 'land', eyes: 'star', mouth: 'grin', arms: 'up', fx: dirt(8), t: 900 }] },
    spin: { steps: () => [
        { body: 'spin', eyes: 'happy', mouth: 'open', fx: dirt(4, 10), t: 1100 },
        { eyes: 'spiral', mouth: 'wavy', t: rnd(500, 900) }, { eyes: 'happy', t: 300 }] },
    wave: { steps: () => [{ depth: 'high', arms: 'wave', eyes: 'happy', mouth: 'open', t: rnd(1200, 1800) }] },
    shake: { steps: () => [
        { body: 'shake', eyes: 'squint', mouth: 'wavy', plume: 'wild',
          fx: [...dirt(5, 16), ...repeat(4, () => [['clod', rnd(16, 48), rnd(28, 42), { dx: rnd(-14, 14), dur: rnd(0.6, 1), r: rnd(0.6, 1) }]])], t: 900 },
        { eyes: 'happy', t: 500 }] },
    tidy: { steps: () => [
        ...repeat(int(2, 4), () => [{ depth: 'low', arms: 'type', eyes: 'squint', mouth: 'flat', t: 260 },
            { arms: pick(['up', 'hold']), eyes: 'squint', fx: dirt(4, 18), t: 360 }]),
        { eyes: 'happy', t: 400 }] },
    sprout: { steps: w => [
        { depth: 'hidden', eyes: 'closed', t: 700 },
        { depth: 'hidden', eyes: 'closed', plume: 'bob', t: rnd(1400, 2200) },
        { depth: 'high', plume: 'up', arms: 'up', eyes: 'star', mouth: 'grin', fx: [['text', 32, 10, { text: w('ta-da!'), size: 7, dy: -6 }], ...dirt(6)], t: 900 }] },
    peekaboo: { steps: w => [
        { arms: 'cover', eyes: 'closed', t: rnd(700, 1100) },
        { depth: 'hidden', eyes: 'closed', t: rnd(700, 1200) },
        { depth: 'high', arms: 'up', eyes: 'wide', mouth: 'open', plume: 'up', fx: [['text', 32, 12, { text: w('boo!'), size: 8, dy: -6 }]], t: 800 },
        { eyes: 'squint', mouth: 'grin', body: 'shake', t: 700 }] },
    telescope: { keep: { prop: 'telescope', arms: 'scope', eyes: 'wink' }, steps: w => [
        { mouth: 'small', t: rnd(1200, 2000) },
        { mouth: 'o', fx: [['sparkle', 60, 14, { dy: 0, s0: 0.2, s1: 1.4, dur: 1 }], ['text', 50, 8, { text: w('a bug!'), size: 5, dy: -4 }]], t: 1100 },
        { prop: '', arms: 'rest', eyes: 'wide', mouth: 'open', depth: 'high', t: 500 }] },
    nap: { steps: () => [
        { eyes: 'tired', mouth: 'small', body: 'nod', t: rnd(1600, 2400) },
        { depth: 'low', eyes: 'closed', plume: 'droop', fx: zzz(44, 34), t: rnd(2600, 3600) },
        { depth: 'high', eyes: 'tiny', mouth: 'o', plume: 'up', t: 450 },
        { eyes: 'open', mouth: 'flat', t: 400 }] },
    shiver: { steps: () => [
        { depth: 'low', body: 'shiver', eyes: 'squint', mouth: 'none', arms: 'both',
          fx: repeat(7, () => [['snow', rnd(4, 60), rnd(-8, 6), { dx: rnd(-4, 4), dy: rnd(50, 62), dur: rnd(1.8, 2.6), delay: rnd(0, 1.2), s0: 1, s1: 1, ease: 'linear' }]]),
          t: rnd(1800, 2600) },
        { eyes: 'open', mouth: 'small', t: 300 }] },
    // to a new spot: the host moves it while it tunnels (travel)
    dig: { steps: () => [
        { body: 'wiggle', eyes: 'squint', mouth: 'flat', fx: dirt(8), t: 450 },
        { depth: 'hidden', eyes: 'closed', fx: dirt(6), t: 500 },
        { depth: 'hidden', tunnel: 1, travel: true, t: rnd(1300, 1900) },
        { depth: 'high', eyes: 'wide', mouth: 'o', fx: dirt(8), t: 450 },
        { body: 'shake', eyes: 'happy', t: 600 }] },
    // Making room in the row (its spot moved): the same dig, quicker
    scoot: { steps: () => [
        { depth: 'hidden', eyes: 'closed', fx: dirt(6), t: 450 },
        { depth: 'hidden', tunnel: 1, travel: true, t: 700 },
        { depth: 'high', eyes: 'wide', mouth: 'o', fx: dirt(6), t: 350 },
        { eyes: 'happy', t: 300 }] },

    typing: { keep: { prop: 'laptop', depth: 'high', look: [0, 1.6], mouth: 'none' }, steps: () => [
        ...repeat(int(2, 4), () => [{ arms: 'type', body: 'fast', t: rnd(900, 1800) }, { arms: 'rest', t: rnd(250, 600) }]),
        ...(chance(0.25) ? [{ eyes: 'wide', fx: [['exclaim', 50, 20, { dy: -4, dur: 1 }]], t: 700 }] : [])] },
    thinking: { steps: () => [
        { arms: 'chin', look: [1.4, -1.6], mouth: 'small', think: 1, plume: 'bob', t: rnd(2200, 3400) },
        { look: [0, 0], t: 300 }] },
    idea: { steps: () => [
        { arms: 'chin', look: [1.4, -1.6], mouth: 'small', think: 1, t: rnd(1500, 2500) },
        { depth: 'high', eyes: 'star', mouth: 'open', plume: 'up', arms: 'up', fx: [['bulb', 32, 4, { dur: 1.8, path: 'bulb' }]], t: 1200 }] },
    debug: { keep: { prop: 'magnifier', arms: 'hold', mouth: 'small' }, steps: w => [
        { fx: [['bug', 44, 55, { dur: 3, path: 'crawl' }]], look: [1, 1.8], t: 900 },
        { look: [-0.6, 1.8], t: 900 }, { eyes: 'wide', mouth: 'o', t: 500 },
        { prop: '', arms: 'up', depth: 'high', eyes: 'happy', mouth: 'grin', fx: [['text', 32, 12, { text: w('got it!'), size: 6 }]], t: 900 }] },
    tests: { steps: () => {
        const fail = chance(0.3) ? 1 : 0, k = { prop: 'clipboard', arms: 'both', depth: 'high', fail: fail, mouth: 'none' };
        return [Object.assign({ look: [-0.6, 1.6], t: 900 }, k), Object.assign({ look: [0, 1.6], t: 900 }, k), Object.assign({ look: [0.6, 1.6], t: 800 }, k),
            fail ? Object.assign({ eyes: 'tiny', fx: [['drop', 48, 28, { dy: 6, s0: 1 }]], t: 900 }, k)
                 : Object.assign({ eyes: 'happy', fx: [['sparkle', 48, 26, { dy: -8 }]], t: 800 }, k)];
    } },
    read: { keep: { prop: 'book', arms: 'both', depth: 'high', mouth: 'none' }, steps: () => [
        ...repeat(int(2, 4), () => [{ look: [-1.5, 1.2], t: 220 }, { look: [1.5, 1.2], t: rnd(700, 1100) }]),
        ...(chance(0.35) ? [{ eyes: 'wide', plume: 'up', fx: [['bulb', 32, 6, { dur: 1.6, path: 'bulb' }]], t: 1000 }] : [])] },
    juggle: { keep: { prop: 'juggle', arms: 'juggle', look: [0, -1.8] }, steps: () => [
        { eyes: 'open', mouth: 'open', t: rnd(2600, 3600) }, { eyes: 'happy', mouth: 'open', t: 500 }] },

    alert: { steps: () => [
        { depth: 'high', body: 'bounce', arms: 'waveboth', eyes: 'wide', mouth: 'open', plume: 'wild',
          fx: [['exclaim', 32, 6, { dy: -6, dur: 1.2, s0: 0.4, s1: 1.1 }]], t: rnd(1800, 2600) }] },
    sign: { keep: { prop: 'sign', arms: 'sign', depth: 'high' }, steps: () => [{ eyes: 'wide', mouth: 'open', t: rnd(1800, 2800) }] },
    phone: { keep: { prop: 'phone', arms: 'ear', depth: 'high' }, steps: () => [
        { eyes: 'wide', mouth: 'o', fx: [0, 0.4, 0.8].map(d => ['ring', 50, 24, { dur: 0.6, delay: d, path: 'pop' }]), t: 1300 },
        { mouth: 'open', eyes: 'happy', t: rnd(1000, 1500) }] },
    letter: { keep: { prop: 'letter', arms: 'both', depth: 'high' }, steps: () => [
        { eyes: 'wide', mouth: 'none', plume: 'up', fx: [['heart', 46, 28, { dy: -10 }]], t: 1300 }, { eyes: 'happy', mouth: 'none', t: 800 }] },

    celebrate: { steps: () => [
        { depth: 'out', body: 'jump', it: int(1, 2), arms: 'up', eyes: 'happy', mouth: 'grin', plume: 'wild', fx: confetti(12), t: 1300 },
        { depth: 'high', eyes: 'star', mouth: 'open', arms: 'dance', body: 'sway', t: rnd(900, 1400) },
        { depth: 'half', fx: dirt(5), t: 400 }] },
    sleep: { steps: () => [
        { depth: 'low', eyes: 'closed', mouth: 'small', body: 'slump', plume: 'droop', fx: zzz(44, 34), t: rnd(3400, 5000) }] },
    sad: { steps: w => [
        { depth: 'low', eyes: 'sad', mouth: 'frown', plume: 'droop', fx: [['drop', 22, 50, { dy: 5, s0: 1, s1: 0.8, dur: 1.4, ease: 'in' }]], t: rnd(2000, 3000) },
        ...(chance(0.5) ? [{ depth: 'peek', eyes: 'closed', plume: 'droop', fx: [['text', 46, 34, { text: w('sigh'), size: 5, dy: -6 }]], t: 1300 }] : [])] },
    battery: { keep: { prop: 'battery' }, steps: () => [
        { depth: 'low', eyes: 'tired', mouth: 'flat', body: 'slump', plume: 'droop', t: rnd(1800, 2600) },
        { depth: 'half', eyes: 'closed', mouth: 'yawn', body: 'stretch', t: 1300 },
        { depth: 'low', eyes: 'tired', mouth: 'small', plume: 'droop', t: 800 }] },

    // reactions to you and to events
    pet: { steps: () => [
        { depth: 'high', eyes: 'happy', mouth: 'open', blush: 1, body: 'wiggle',
          fx: repeat(int(1, 3), i => [['heart', rnd(20, 46), rnd(14, 24), { dy: -12, dx: rnd(-4, 4), delay: i * 0.25 }]]), t: 1100 }] },
    shy: { steps: () => [{ depth: 'low', eyes: 'closed', mouth: 'wavy', blush: 1, arms: 'cover', fx: [['heart', 40, 22, { dy: -10 }]], t: 1300 }] },
    laugh: { steps: w => [
        { depth: 'high', eyes: 'squint', mouth: 'grin', body: 'shake', blush: 1, plume: 'wild',
          fx: [['text', 50, 22, { text: w('haha'), size: 6 }], ['text', 14, 20, { text: w('hihi'), size: 5, delay: 0.4 }]], t: 1500 }] },
    dance: { steps: () => [
        { depth: 'high', arms: 'dance', body: 'sway', eyes: 'happy', mouth: 'open', plume: 'bob', fx: notes(), t: rnd(2200, 3000) }] },
    grumpy: { steps: () => [{ depth: 'low', eyes: 'tired', mouth: 'frown', plume: 'droop', fx: zzz(44, 34), t: 1600 }] },
    angry: { steps: () => [{ depth: 'high', eyes: 'squint', mouth: 'frown', body: 'shake', plume: 'wild',
        fx: [['exclaim', 44, 14, { dy: -4, dur: 1 }]], t: 1300 }] },
    yawn: { steps: () => [{ eyes: 'closed', mouth: 'yawn', body: 'stretch', t: 1300 }, { eyes: 'tired', mouth: 'small', t: 500 }] },
    finished: { steps: () => [
        { depth: 'out', body: 'jump', arms: 'up', eyes: 'happy', mouth: 'grin', plume: 'wild', fx: [...confetti(10), ...sparkles(3)], t: 1100 },
        { depth: 'high', eyes: 'star', mouth: 'open', t: 700 }] },
    failed: { steps: () => [
        { depth: 'low', eyes: 'sad', mouth: 'frown', plume: 'droop', body: 'slump', fx: [['drop', 22, 50, { dy: 5, s0: 1, dur: 1.4, ease: 'in' }]], t: 2200 }] },
    shrug: { steps: () => [{ arms: 'up', eyes: 'closed', mouth: 'flat', t: 900 }, { eyes: 'open', t: 400 }] },
    confused: { steps: w => [
        { arms: 'scratch', eyes: 'squint', mouth: 'wavy', fx: [['text', 50, 22, { text: '?', size: 9, dy: -6 }]], t: rnd(1200, 1800) },
        { eyes: 'open', t: 300 }] },
    charged: { steps: () => [
        { depth: 'high', eyes: 'star', mouth: 'grin', arms: 'up', plume: 'up', fx: sparkles(4), t: 1100 }, { eyes: 'happy', t: 400 }] },
    mindblown: { steps: w => [
        { depth: 'high', eyes: 'spiral', mouth: 'o', orbit: 1, plume: 'wild', body: 'shake',
          fx: [['cloud', 22, 18, { dy: -10, s0: 0.4, s1: 1.2, dur: 1.4 }], ['cloud', 42, 16, { dy: -12, s0: 0.4, s1: 1.2, dur: 1.4, delay: 0.3 }],
               ['text', 50, 10, { text: '!!', size: 7, dy: -4 }]], t: 1600 },
        { orbit: 0, eyes: 'tired', t: 600 }] },
    contextFull: { steps: () => [
        { depth: 'high', eyes: 'tiny', mouth: 'wavy', body: 'shiver', fx: [['drop', 47, 26, { dy: 6, s0: 1 }], ['drop', 17, 28, { dy: 6, s0: 1, delay: 0.4 }]], t: 1500 },
        { eyes: 'open', t: 300 }] },

    // little joys
    bubbles: { steps: () => [
        { mouth: 'kiss', eyes: 'happy', look: [0.6, -0.6], t: 400 },
        { mouth: 'kiss', eyes: 'closed', blush: 1, fx: bubbles(), t: rnd(1800, 2400) },
        { mouth: 'smile', eyes: 'happy', look: [0.8, -1.6], t: 1000 }] },
    flower: { steps: w => {
        const color = pick(['#ff8fbf', '#ffd166', '#b8a1ff', '#ff9a76']);
        return [
            { depth: 'low', arms: 'type', eyes: 'squint', mouth: 'flat', look: [1.6, 1], fx: dirt(3, 6), t: 600 },
            { depth: 'half', arms: 'rest', eyes: 'wide', mouth: 'o', look: [1.8, 0.6],
              fx: [['flower', 64, 57.5, { path: 'grow', dur: 5.2, color: color }]], t: 1000 },
            { depth: 'high', eyes: 'closed', mouth: 'small', blush: 1, look: [1.6, 0], body: 'inhale',
              fx: [['text', 50, 22, { text: w('mmm…'), size: 5.5, dy: -6 }], ['heart', 52, 30, { dy: -10, delay: 0.5 }]], t: 1400 },
            { eyes: 'happy', mouth: 'smile', blush: 1, look: [1.4, 0.4], t: 1000 }];
    } },
    // (a cookie of its own, of any flavour: FLAVOURS below)
    snack: { steps: w => {
        const k = { prop: 'cookie', arms: 'both', depth: 'out', treat: pickFlavour() };
        return [
            Object.assign({ eyes: 'wide', mouth: 'o', look: [0, 1.4], t: 700 }, k),
            ...repeat(3, i => [Object.assign({ eyes: 'closed', mouth: 'open', bite: i + 1, fx: crumbs(), t: 380 }, k),
                Object.assign({ eyes: 'happy', mouth: 'small', bite: i + 1, t: rnd(380, 560) }, k)]),
            { depth: 'out', eyes: 'happy', mouth: 'grin', blush: 1, fx: [['text', 50, 22, { text: w('yum!'), size: 6, dy: -6 }]], t: 1000 }];
    } },
    selfie: { steps: w => [
        { depth: 'high', arms: 'selfie', eyes: 'open', mouth: 'smile', look: [1.2, -1.4], t: 700 },
        { arms: 'selfie', eyes: 'wink', mouth: 'grin', blush: 1, fx: [['text', 46, 4, { text: w('cheese!'), size: 6, dy: -4 }]], t: 800 },
        { arms: 'selfie', eyes: 'happy', mouth: 'grin', fx: [['flash', 56, 12, { path: 'pop', dur: 0.45 }], ...sparkles(2)], t: 700 },
        { arms: 'rest', eyes: 'happy', mouth: 'smile', t: 500 }] },
    love: { steps: () => [
        { depth: 'high', eyes: 'heart', mouth: 'open', blush: 1, body: 'wiggle', plume: 'bob',
          fx: repeat(int(3, 5), i => [['heart', rnd(16, 48), rnd(16, 28), { dy: rnd(-16, -10), dx: rnd(-6, 6), delay: i * 0.22, scale: rnd(0.8, 1.3) }]]),
          t: 1400 },
        { eyes: 'happy', mouth: 'smile', blush: 1, t: 600 }] },
    wink: { steps: () => [
        { depth: 'high', eyes: 'wink', mouth: 'kiss', blush: 1, plume: 'flick', fx: [['sparkle', 46, 30, { dy: -6, dur: 0.9 }]], t: 900 },
        { eyes: 'happy', mouth: 'smile', t: 400 }] },
    blowkiss: { steps: () => [
        { depth: 'high', arms: 'chin', eyes: 'closed', mouth: 'kiss', t: 550 },
        { arms: 'wave', eyes: 'happy', mouth: 'kiss', blush: 1, fx: [['heart', 42, 40, { path: 'plane', dur: 1.9, scale: 0.9 }]], t: 1300 }] },
    bunnyhop: { steps: () => [
        { depth: 'out', body: 'hop', it: 3, arms: 'up', eyes: 'happy', mouth: 'open', plume: 'bob', fx: sparkles(3), t: 1650 },
        { depth: 'half', eyes: 'happy', mouth: 'smile', fx: dirt(4, 8), t: 450 }] },
    boogie: { steps: () => [
        { depth: 'high', arms: 'dance', body: 'wiggle', eyes: 'happy', mouth: 'grin', plume: 'bob', fx: notes(), t: rnd(1800, 2400) },
        { arms: 'up', eyes: 'star', mouth: 'open', body: 'bounce', fx: sparkles(3), t: 700 }] },
    yay: { steps: w => [
        { depth: 'out', body: 'hop', it: 2, arms: 'up', eyes: 'star', mouth: 'grin', plume: 'wild',
          fx: [...confetti(8), ['text', 32, 4, { text: w('yay!'), size: 7, dy: -6 }]], t: 1100 },
        { depth: 'high', arms: 'waveboth', eyes: 'happy', mouth: 'open', t: 900 }] },
    // a quiet night
    stargaze: { steps: w => [
        { depth: 'half', eyes: 'tired', mouth: 'small', look: [-1, -2], t: rnd(1200, 1800) },
        { eyes: 'wide', mouth: 'o', look: [1.4, -2], fx: [['shoot', -6, 4, { path: 'shoot', dur: 1.1 }]], t: 1000 },
        { eyes: 'star', mouth: 'smile', blush: 1, fx: [...sparkles(2), ['text', 32, 6, { text: w('a star!'), size: 5.5, dy: -4 }]], t: 1200 },
        { eyes: 'closed', mouth: 'small', t: 600 }] },
    firefly: { steps: () => [
        { eyes: 'open', mouth: 'small', look: [-1.6, -1], fx: [['firefly', 8, 30, { path: 'fly', dur: 3.8, scale: 1.2 }]], t: 900 },
        { look: [-0.4, -2], t: 700 }, { look: [1.4, -0.4], eyes: 'wide', mouth: 'o', t: 700 },
        { look: [-0.8, -1.8], eyes: 'happy', mouth: 'smile', blush: 1, t: 1300 }] },
    dream: { steps: () => [
        { depth: 'low', eyes: 'closed', mouth: 'small', body: 'slump', plume: 'droop',
          fx: [['bubble', 35.2, 44.4, { path: 'breathe', r: 2.4, dur: 4.2 }], ...zzz(44, 34)], t: 4100 },
        { depth: 'low', eyes: 'tiny', mouth: 'o', plume: 'flick', fx: [['flash', 35.2, 44.4, { path: 'pop', dur: 0.35, scale: 0.45, color: '#9fd0f0' }]], t: 700 },
        { depth: 'low', eyes: 'closed', mouth: 'small', body: 'slump', plume: 'droop', t: 900 }] },

    arrive: { steps: () => [
        { depth: 'gone', hole: 0, snap: 1, t: 300 },   // (no sinking first: it isn't there yet)
        { depth: 'gone', hole: 1, fx: dirt(8), t: 450 },
        { depth: 'peek', hole: 1, look: [-1.6, 0], t: 600 },
        { depth: 'peek', hole: 1, look: [1.6, 0], t: 500 },
        { depth: 'high', hole: 1, arms: 'wave', eyes: 'happy', mouth: 'open', t: 1000 }] },
    leave: { steps: () => [
        { depth: 'high', hole: 1, arms: 'wave', eyes: 'happy', t: 1100 },
        { depth: 'hidden', hole: 1, eyes: 'closed', fx: dirt(8), t: 600 },
        { depth: 'gone', hole: 1, t: 450 },                     // all of it down, then
        { depth: 'gone', hole: 0, fx: dirt(4, 8), t: 450 }] }   // the hole closes
};

// A cookie you give it (cookie.mjs): it sees it, goes after it out of its
// burrow on its feet (the host moves it: chase poses), eats it, says thanks
// its way now and then, and digs in where it is. Not picked by any mood:
// only the cookie's game plays these.
//
// Flavours, and how often each comes up (cookie.mjs picks one as a cookie
// pops up; art.mjs draws them): mostly chocolate chip, now and then another
export const FLAVOURS = { choc: 4, double: 1, sprinkles: 1, ginger: 1, mint: 1, jam: 1, oat: 1, white: 1 };
export function pickFlavour() {
    const names = Object.keys(FLAVOURS);
    let r = Math.random() * names.reduce((sum, n) => sum + FLAVOURS[n], 0);
    for (const n of names) {
        r -= FLAVOURS[n];
        if (r < 0)
            return n;
    }
    return names[0];
}
const hearts = n => repeat(n, i => [['heart', rnd(16, 48), rnd(16, 28), { dy: rnd(-16, -10), dx: rnd(-6, 6), delay: i * 0.2 }]]);
const bites = (keep, flavour) => repeat(3, i => [
    Object.assign({ prop: 'cookie', treat: flavour, arms: 'both', bite: i + 1, eyes: 'closed', mouth: 'open', fx: crumbs(), t: 360 }, keep),
    Object.assign({ prop: 'cookie', treat: flavour, arms: 'both', bite: i + 1, eyes: 'happy', mouth: 'small', t: rnd(340, 480) }, keep)]);
const OUT = { depth: 'out', hole: 0 };
const out = steps => steps.map(s => Object.assign({}, s, OUT));
// How each one tastes, once it's eaten
const TASTE = {
    choc: w => [{ eyes: 'happy', mouth: 'grin', blush: 1, fx: [['text', 50, 22, { text: w('yum!'), size: 6, dy: -6 }], ...hearts(3)], t: 1000 }],
    double: () => [{ eyes: 'heart', mouth: 'open', blush: 1, body: 'wiggle', plume: 'bob', fx: hearts(5), t: 1300 }],
    sprinkles: () => [{ arms: 'dance', body: 'sway', eyes: 'happy', mouth: 'open', plume: 'bob', fx: notes(), t: 1600 }],
    ginger: w => [
        { eyes: 'squint', mouth: 'o', body: 'inhale', plume: 'up', t: 450 },
        { eyes: 'closed', mouth: 'open', body: 'jolt', plume: 'wild',
          fx: [['cloud', 18, 40, { dx: -12, dy: -4, s0: 0.4, s1: 1.4, dur: 1.2 }], ['text', 14, 26, { text: w('achoo!'), size: 6.5, dx: -4, dy: -8, dur: 1.4 }]],
          t: 520 },
        { eyes: 'happy', mouth: 'smile', blush: 1, t: 600 }],
    mint: () => [{ arms: 'both', body: 'shiver', eyes: 'squint', mouth: 'grin', plume: 'up',
        fx: repeat(6, () => [['snow', rnd(8, 56), rnd(-6, 8), { dx: rnd(-4, 4), dy: rnd(46, 58), dur: rnd(1.4, 2), delay: rnd(0, 0.6), s0: 1, s1: 1, ease: 'linear' }]]),
        t: 1400 }],
    jam: w => [{ eyes: 'closed', mouth: 'kiss', blush: 1, look: [0.8, -1.2], body: 'inhale',
        fx: [['text', 50, 22, { text: w('mmm…'), size: 5.5, dy: -6 }], ['heart', 46, 30, { dy: -10, delay: 0.4 }]], t: 1300 }],
    oat: () => [
        { eyes: 'squint', mouth: 'wavy', look: [0, 1.6], fx: [['text', 48, 22, { text: '?', size: 8, dy: -6 }]], t: 900 },
        { eyes: 'happy', mouth: 'smile', blush: 1, t: 700 }],
    white: () => [{ eyes: 'closed', mouth: 'kiss', blush: 1, look: [0.6, -0.6], fx: bubbles(), t: 1600 }]
};
// Thanks now and then, its own way, picked at random (never for how many
// it had: it doesn't count them)
const THANKS = {
    bow: () => [{ body: 'bow', arms: 'both', eyes: 'closed', mouth: 'smile', blush: 1, look: [0, 1.4], t: 1200 }, { eyes: 'happy', t: 300 }],
    fanfare: w => [
        { prop: 'trumpet', arms: 'horn', eyes: 'closed', mouth: 'small', blush: 1, body: 'inhale', t: 450 },
        { prop: 'trumpet', arms: 'horn', eyes: 'happy', mouth: 'small', blush: 1, plume: 'wild',
          fx: [['note', 52, 30, { dx: 8, dy: -12, dur: 1.2 }], ['note', 54, 34, { dx: 10, dy: -8, dur: 1.2, delay: 0.3 }],
               ['note', 50, 28, { dx: 6, dy: -16, dur: 1.2, delay: 0.6 }], ['text', 32, 6, { text: w('ta-da!'), size: 7, dy: -6, delay: 0.3 }]],
          t: 1300 }],
    confetti: w => [{ body: 'hop', it: 2, arms: 'up', eyes: 'star', mouth: 'grin', plume: 'wild',
        fx: [...confetti(12), ['text', 32, 4, { text: w('yay!'), size: 7, dy: -6 }]], t: 1100 }],
    twirl: () => [{ plume: 'twirl', it: 2, arms: 'up', eyes: 'wide', mouth: 'o', fx: sparkles(3), t: 1600 }, { eyes: 'happy', mouth: 'grin', t: 300 }],
    kiss: () => [
        { arms: 'chin', eyes: 'closed', mouth: 'kiss', t: 550 },
        { arms: 'wave', eyes: 'happy', mouth: 'kiss', blush: 1, fx: [['heart', 42, 40, { path: 'plane', dur: 1.9, scale: 0.9 }]], t: 1300 }],
    hops: () => [{ body: 'hop', it: 3, arms: 'up', eyes: 'happy', mouth: 'open', plume: 'bob', fx: sparkles(3), t: 1650 }]
};
const THANKS_OFTEN = 0.6;
// (its hole opens under it, it spins round and digs in: the end of a fall too)
const digIn = () => [
    { depth: 'out', hole: 1, eyes: 'happy', mouth: 'smile', t: 500 },
    { body: 'spin', eyes: 'squint', fx: dirt(10), t: 700 },
    { eyes: 'happy', t: 400 }];
export const COOKIE = {
    // Gone (Playful Talpy turned off as it's after it or eats it): a blink
    // where it was, and it digs in where it is
    gone: () => [
        { depth: 'out', hole: 1, eyes: 'wide', mouth: 'o', plume: '', t: 350 },
        { body: 'spin', eyes: 'squint', fx: dirt(10), t: 700 },
        { t: 300 }],
    // It sees it (look: towards it); asleep, it sniffs and wakes up first
    spot: (look, sleepy) => w => [
        ...(sleepy ? [{ depth: 'low', eyes: 'closed', mouth: 'small', plume: 'flick',
                        fx: [['text', 46, 24, { text: w('sniff sniff'), size: 5, dy: -5, dur: 1.2 }]], t: 900 }] : []),
        { depth: 'high', eyes: 'wide', mouth: 'o', plume: 'up', look: look,
          fx: [['exclaim', 32, 6, { dy: -6, dur: 1.2, s0: 0.4, s1: 1.1 }]], t: 600 },
        { depth: 'high', eyes: 'star', mouth: 'open', plume: 'wild', look: look, fx: sparkles(2), t: 450 }],
    // After it: out of its burrow at a jump, then running, begging under it
    // (out of reach), jumping for it (and trying to, out of reach), or cross
    // that you keep it away
    chase: {
        out: () => Object.assign({ body: 'jump', arms: 'up', eyes: 'wide', mouth: 'open', plume: 'up', tail: 'wag', fx: dirt(8, 16) }, OUT),
        run: () => Object.assign({ walk: 1, arms: 'flail', eyes: 'wide', mouth: 'open', plume: 'bob', tail: 'wag' }, OUT),
        stand: () => Object.assign({ arms: 'both', eyes: 'wide', mouth: 'open', plume: 'up', tail: 'wag' }, OUT),
        beg: () => Object.assign({ body: 'bounce', arms: 'up', eyes: 'wide', mouth: 'open', plume: 'up', tail: 'wag' }, OUT),
        leap: () => Object.assign({ body: 'jump', arms: 'up', eyes: 'wide', mouth: 'o', plume: 'up', tail: 'up' }, OUT),
        reach: () => Object.assign({ body: 'jump', arms: 'up', eyes: 'squint', mouth: 'open', plume: 'wild', tail: 'up' }, OUT),
        pout: () => Object.assign({ body: 'shake', eyes: 'squint', mouth: 'frown', plume: 'wild', tail: 'droop' }, OUT)
    },
    // Got it (caught: out of the air): eats it, tastes it (TASTE), says
    // thanks now and then (THANKS), and digs in. thanks: which, '' none,
    // undefined: at random
    eat: (flavour, caught, thanks) => w => {
        const taste = TASTE[flavour] || TASTE.choc;
        if (thanks === undefined)
            thanks = chance(THANKS_OFTEN) ? pick(Object.keys(THANKS)) : '';
        return [
            Object.assign({ prop: 'cookie', treat: flavour, arms: 'both', eyes: 'star', mouth: 'o', look: [0, 1.4],
                            fx: [...sparkles(2), ...(caught ? [['text', 32, 4, { text: w('got it!'), size: 6, dy: -6 }]] : [])], t: 650 }, OUT),
            ...bites(OUT, flavour),
            ...out(taste(w)),
            ...out(THANKS[thanks] ? THANKS[thanks](w) : []),
            ...digIn()];
    }
};
export const THANKS_NAMES = Object.keys(THANKS);

// Pulled at in its burrow (Talpy.tug): it hangs on to the rim, stretched
// and trembling, for TUG_MS until it lets go (the host has it then), or you
// let go first and it drops back in
export const TUG_MS = 1000;
export const TUG = {
    hold: () => [{ depth: 'high', body: 'tug', arms: 'rim', eyes: 'squint', mouth: 'wavy', plume: 'wild',
                   fx: [...dirt(4, 10), ['drop', 47, 26, { dy: 6, s0: 1, delay: 0.45 }]], t: TUG_MS }],
    back: () => [
        { depth: 'low', body: 'jolt', eyes: 'closed', mouth: 'wavy', plume: 'droop', fx: dirt(4, 8), t: 450 },
        { depth: 'half', eyes: 'happy', mouth: 'smile', t: 500 }]
};

// Pushed down into its burrow (Talpy.push): it squashes (body 'push'), grabs
// the rim and pushes back, with a dirt puff (start); pushed on, it gives in
// and ducks all the way (give). Let go: given in, it stays down a moment,
// then peeks out, hey! or a giggle, and is back to its mood (back); not yet,
// it springs back up past where it was, boing, and settles (boing); with a
// chat that needs you it pops straight back up (needs)
export const PUSH = {
    start: () => ({ eyes: 'squint', mouth: 'wavy', arms: 'rim', plume: 'wild', body: 'push', fx: dirt(6, 12) }),
    give: () => ({ eyes: 'closed', mouth: 'o', plume: 'droop', body: 'push', fx: dirt(4, 8) }),
    back: w => [
        { depth: 'hidden', eyes: 'closed', mouth: 'small', body: '', plume: '', t: rnd(1000, 1600) },
        { depth: 'peek', eyes: 'open', mouth: 'small', look: [-1.6, 0], t: 650 },
        { depth: 'peek', look: [1.6, 0], t: 550 },
        { depth: 'half', eyes: 'happy', mouth: 'open', plume: 'flick',
          fx: [['text', 15, 24, { text: w(chance(0.5) ? 'hey!' : 'hihi'), size: 6.5, dx: -3, dy: -8, dur: 1.4 }]], t: 900 }],
    boing: () => [
        { depth: 'high', body: 'jolt', eyes: 'wide', mouth: 'open', plume: 'flick', fx: dirt(3, 6), t: 420 },
        { eyes: 'squint', mouth: 'smile', plume: 'bob', t: 650 }],
    needs: () => [
        { depth: 'hidden', body: '', t: 120 },
        { depth: 'high', body: 'jolt', eyes: 'wide', mouth: 'open', plume: 'up', fx: dirt(6), t: 450 }]
};

// Moods: how it looks between actions (base) and what it picks (pool); with
// Playful Talpy off (Talpy.setPlayful), only what shows what the chats do and
// quiet moves (calm): no props, no tricks, no jokes
export const MOODS = {
    idle: { base: { eyes: 'open', mouth: 'smile', depth: 'half', lamp: 'idle' }, pause: [700, 2000],
        pool: { lookaround: 3, duck: 1, popup: 1.2, twirl: 1, sneeze: 0.8, hiccups: 0.6, gum: 0.8, coffee: 1, music: 1, butterfly: 1,
                balloon: 0.7, plane: 0.8, flip: 0.7, spin: 0.8, wave: 0.7, shake: 0.6, tidy: 0.7, sprout: 0.8, peekaboo: 0.8,
                telescope: 0.6, nap: 0.6, shiver: 0.3, dig: 2.4, bubbles: 0.8, flower: 0.7, snack: 0.6, selfie: 0.5, wink: 0.5,
                boogie: 0.5, bunnyhop: 0.5, blowkiss: 0.3, firefly: 0.3 },
        calm: { lookaround: 3, duck: 0.6, nap: 0.6, dig: 1.2 } },
    working: { base: { eyes: 'open', mouth: 'flat', depth: 'half', lamp: 'working' }, pause: [500, 1500],
        pool: { typing: 4, thinking: 2, idea: 1.2, debug: 1.2, tests: 1.2, read: 0.8, coffee: 0.6, telescope: 0.5, dig: 0.8, snack: 0.3 },
        calm: { typing: 4, thinking: 2, read: 0.8 } },
    agents: { base: { eyes: 'open', mouth: 'flat', depth: 'half', lamp: 'agents' }, pause: [500, 1500],
        pool: { juggle: 4, typing: 1.2, thinking: 1, idea: 0.6, dig: 0.5 },
        calm: { typing: 1.2, thinking: 1 } },
    needs: { base: { eyes: 'wide', mouth: 'open', depth: 'high', plume: 'up', body: 'bounce', lamp: 'needs' }, pause: [300, 900],
        pool: { alert: 2.5, sign: 2, phone: 1.5, letter: 1.2, wave: 0.8 },
        calm: { alert: 2.5, sign: 2, wave: 0.8 } },
    done: { base: { eyes: 'closed', mouth: 'small', depth: 'low', plume: 'droop', lamp: 'done' }, pause: [1500, 3500],
        pool: { sleep: 3, nap: 0.6, dream: 1.4, stargaze: 0.5, firefly: 0.4 },
        calm: { sleep: 3, nap: 0.6 } },
    failed: { base: { eyes: 'sad', mouth: 'frown', depth: 'low', plume: 'droop', lamp: 'failed' }, pause: [1500, 3500],
        pool: { sad: 3, duck: 0.5 } },
    limit: { base: { eyes: 'tired', mouth: 'flat', depth: 'low', plume: 'droop', prop: 'battery', lamp: 'limit' }, pause: [1500, 3500],
        pool: { battery: 3, nap: 0.8 } },
    error: { base: { eyes: 'sad', mouth: 'wavy', depth: 'peek', plume: 'droop', lamp: 'error' }, pause: [2000, 4000],
        pool: { confused: 1, duck: 1 } },
    loading: { base: { eyes: 'open', mouth: 'small', depth: 'peek', lamp: 'idle' }, pause: [800, 2000],
        pool: { lookaround: 1 } }
};

export const random = { rnd: rnd, int: int, pick: pick, chance: chance };
