// Deep Dig: Talpy digs straight down through the ground, what's buried comes
// up at him, and you steer him round it (see the design, 2026-11-19).
//
// Plain ES2017 (see paths.mjs).

// a thing's size by his body's height (w × h; a root's and a pipe's w is the row's)
export const DIG_KINDS = {
    root: [1.6, 0.34], pebble: [0.6, 0.4], stone: [0.6, 0.62], pipe: [2.2, 0.42], bottle: [0.32, 0.72],
    boulder: [1.25, 0.85], beetle: [0.8, 0.46], cookie: [0.6, 0.6], plus: [0.7, 0.35],
    speck: [0.32, 0.2], worm: [0.62, 0.2], crystal: [0.5, 0.46], tunnel: [1, 0.34], clod: [0.13, 0.11], glow: [1.8, 1.8]
};
// how many looks a kind has (drawThing's variant: a root's curl, which way a pipe's open end or a
// beetle faces, a speck's, a crystal's colour, a clod's, a cookie's flavour)
export const DIG_VARIANTS = { root: 3, pipe: 2, beetle: 2, speck: 2, crystal: 2, clod: 3, cookie: 8 };
