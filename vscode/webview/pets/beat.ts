// One clock for what keeps moving on a page (the widget's hub/Beat.qml): the
// pets' stages, the big Talpy's light and stars (stage.ts), Talpy's glyph
// (TalpyIcon) and Talpy Chat's blinking dot. It beats BEAT_MS apart, on the
// screen's frame nearest each beat (every other frame of a 60 Hz screen), only
// while something waits for a beat, and not while nobody sees the page
// (hidden, or its host says so: beatShown). Each frame the page draws costs
// about the same whatever changed in it (measured in Electron 45, compositing
// on the GPU through ANGLE and Mesa: a 16 px canvas drawn 60 times a second
// used about 27% of a core, 30 times 13%, a CSS animation of one dot's opacity
// 14%), so whatever moves on a page moves on the same beats, one frame for all
// of it. A wish can be quick (a pet in your hand, a game): then it comes true
// the next frame.

export const BEAT_MS = 1000 / 30;
export const FRAME_MS = 1000 / 60;

// When the timer wakes the page to ask for the beat's frame. Chromium hands a
// page that starts asking for frames after a while without any the frame of
// the screen's last refresh, at once; one that drew a frame or two ago, the
// next refresh's. So a beat that comes after a while (a glyph's, every third)
// wakes the page just after it's due and gets its frame at once; the next of
// beats that follow each other wakes it half a frame early and gets the next
// one (a frame handed over before it is let go: a frame for nothing, as cheap
// as frames get). Woken just after it, the frame of the beats that followed
// each other came a frame late; woken early, a glyph's came after a frame for
// nothing, each time.
const LATE = 4;
const AWHILE = 3 * FRAME_MS;

type Wish = { fn: (now: number) => void; due: number; quick: boolean };

const wishes = new Map<number, Wish>();
let lastId = 0;
let last = -1e9; // when it last beat (a frame's time, as performance.now())
let lastFrame = -1e9; // (the page's last frame)
let frame = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let timerAt = Infinity;
let ticking = false; // (the wishes of a beat come true: what they wish next is scheduled after)
let hostShown = true; // (beatShown)
let pageShown = typeof document === "undefined" || document.visibilityState !== "hidden";
// How far apart the screen's frames come (frames one after the other), and
// the beats (one after the other): the last few, measured
const frameGaps: number[] = [];
const beatGaps: number[] = [];

function median(list: number[], otherwise: number): number {
  if (!list.length) return otherwise;
  const sorted = [...list].sort((a, b) => a - b);
  return sorted[sorted.length >> 1];
}

function keep(list: number[], gap: number): void {
  list.push(gap);
  if (list.length > 9) list.shift();
}

// The screen's frame: 16.7 ms on a 60 Hz screen, 6.9 on a 144 Hz one
export function screenFrame(): number {
  return median(frameGaps, FRAME_MS);
}

// How far apart the beats come here: BEAT_MS on a 60 or 120 Hz screen; on
// others the frame nearest each beat (40 ms on a 75 Hz screen, 34.7 on a
// 144 Hz one), which is what moves on the beat should count with (the pets'
// films: stage.ts)
export function beatInterval(): number {
  return median(beatGaps, BEAT_MS);
}

// (a frame up to half a frame early is the beat's: the frame nearest it, the
// later of two as near)
function slack(): number {
  return screenFrame() / 2 - 0.1;
}

// fn(now) on the next beat (quick: the next frame; count: the beat that many
// beats after the last one, in step with the rest), as requestAnimationFrame
// for what moves on the beat. A wish to a beat that's idle comes true the next
// frame.
export function nextBeat(fn: (now: number) => void, quick = false, count = 1): number {
  const id = ++lastId;
  wishes.set(id, { fn, quick, due: Math.max(last + count * BEAT_MS, performance.now() - FRAME_MS) });
  schedule();
  return id;
}

// fn(now) on the next beat that comes anyway (a glyph's, the pets'), else on
// one of its own: for a change that can wait a moment (a clock's next second),
// so it takes no frame of its own
export function withNextBeat(fn: (now: number) => void): number {
  const due = nextDue();
  if (due === Infinity) return nextBeat(fn);
  const id = ++lastId;
  wishes.set(id, { fn, quick: false, due });
  schedule();
  return id;
}

export function cancelBeat(id: number): void {
  if (wishes.delete(id) && !wishes.size) unschedule(); // (nothing waits for a beat any more)
}

// The page's host says whether anyone sees it (a webview with another view or
// tab in front of it): while nobody does, no beat comes and the wishes wait
export function beatShown(shown: boolean): void {
  hostShown = shown;
  if (shown) schedule();
  else unschedule();
}

if (typeof document !== "undefined")
  document.addEventListener("visibilitychange", () => {
    pageShown = document.visibilityState !== "hidden";
    if (pageShown) schedule();
    else unschedule();
  });

// (no timer, no frame)
function unschedule(): void {
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
  timerAt = Infinity;
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
}

// When the next beat is due (Infinity: no wish waits for one)
function nextDue(): number {
  let due = Infinity;
  for (const w of wishes.values()) if (!w.quick) due = Math.min(due, w.due);
  return due;
}

function schedule(): void {
  if (frame || ticking || !wishes.size || !hostShown || !pageShown) return;
  const quick = [...wishes.values()].some((w) => w.quick);
  const due = nextDue();
  const at = quick ? -Infinity : due - last >= AWHILE - 1 ? due + LATE : due - screenFrame() / 2;
  const wait = at - performance.now();
  if (wait <= 0) {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    timerAt = Infinity;
    frame = requestAnimationFrame(tick);
  } else if (at < timerAt) {
    if (timer !== undefined) clearTimeout(timer);
    timerAt = at;
    timer = setTimeout(() => {
      timer = undefined;
      timerAt = Infinity;
      if (!frame && wishes.size && hostShown && pageShown) frame = requestAnimationFrame(tick);
    }, wait);
  }
}

// What a follower threw goes to the page's error handling, after: the others
// on this beat still move, and take their next beats
function report(e: unknown): void {
  if (typeof reportError === "function") reportError(e);
  else
    setTimeout(() => {
      throw e;
    }, 0);
}

// A frame: the beat if it's due (the frame nearest a beat after the last one,
// and a wish waits for it), then the wishes due by now come true; and every
// quick wish
export function tick(now: number): void {
  frame = 0;
  const gap = now - lastFrame;
  if (gap > 3 && gap < 21) keep(frameGaps, gap); // (frames one after the other)
  lastFrame = now;
  const next = nextDue();
  const beat = now >= Math.max(last + BEAT_MS, next < Infinity ? next : 0) - slack();
  if (beat) {
    if (now - last < 1.5 * BEAT_MS) keep(beatGaps, now - last); // (beats one after the other)
    last = now;
  }
  const due: Wish[] = [];
  for (const [id, w] of wishes) {
    if (!w.quick && !(beat && w.due <= now + slack())) continue;
    wishes.delete(id);
    due.push(w);
  }
  ticking = true;
  for (const w of due) {
    try {
      w.fn(now);
    } catch (e) {
      report(e);
    }
  }
  ticking = false;
  schedule();
}
