// Talpy Chat's rows a few at a time (Plasma, ChatPane.qml fillBuffer). Its list makes every row once
// (a cacheBuffer of FILL_ALL px, so it doesn't jump while you scroll); many that come in at once (a
// read further back for a bookmark, Show earlier: up to 2000) were all made in one go, rich text and
// all, 1,900 of them holding the window up 12 s. Instead the buffer starts at a screen around what you
// read and grows a step at a time, each step sized by what the one before cost, each wait at least
// twice that: it aims to leave plasmashell's main thread, which draws the panel too, half of every
// period while it fills (measured, a second's share still reaches about 70%: some of each step's work
// comes after it, where no step can time it). Pure functions; nothing here reads the screen.

export const FILL_ALL = 100000;     // (the list's cacheBuffer once every row is made)
export const FILL_INTERVAL = 32;    // (ms between steps, at the least)
export const FILL_STEP_MAX = 20000; // (px a step adds, at the most)
export const FILL_SLOW = 24;        // (a step that cost more, ms: the next one half as big)
export const FILL_QUICK = 8;        // (one that cost less: the next one twice as big)

// The smallest step: a few lines (lineHeight: one line's, px)
export function fillStepMin(lineHeight) {
    return Math.max(1, lineHeight * 6);
}

// Where it starts (viewHeight: the list's, px): {buffer, step, interval}
export function fillStart(viewHeight, lineHeight) {
    return { buffer: Math.max(0, Math.round(viewHeight)),
             step: Math.min(FILL_STEP_MAX, Math.max(viewHeight, lineHeight * 12, fillStepMin(lineHeight))),
             interval: FILL_INTERVAL };
}

// The next buffer: grown by step; -1 once it holds every row (the list's own again: it's done)
export function fillNext(buffer, step) {
    const next = buffer + step;
    return next >= FILL_ALL ? -1 : next;
}

// After a step that cost cost ms (rows made then, or as the window was drawn since): the next step
// (half over FILL_SLOW, twice under FILL_QUICK, between fillStepMin and FILL_STEP_MAX) and the wait
// before it (at least twice cost: it aims at half of each period, at most, for making rows)
export function fillPace(step, cost, lineHeight) {
    const c = Math.max(0, cost || 0);
    const next = c > FILL_SLOW ? step / 2 : c < FILL_QUICK ? step * 2 : step;
    return { step: Math.min(FILL_STEP_MAX, Math.max(fillStepMin(lineHeight), next)),
             interval: Math.max(FILL_INTERVAL, Math.ceil(2 * c)) };
}
