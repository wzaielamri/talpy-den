// Plasma Talpy Chat's conversation moved by the wheel and the touchpad (package/contents/ui/wheel.mjs,
// WheelScroll.qml), frame by frame on a screen's clock (60.03 Hz, the owner's): a notch eases out, a spin
// keeps its pace, a touchpad's stream is followed evenly however its moves come, and its glide starts at
// the speed it had. Kirigami's WheelHandler (Plasma's scroll views; kirigami 6.32 wheelhandler.cpp,
// written out below as it does it) fails the same checks: that's the fault this fixes.
import test from "node:test";
import assert from "node:assert/strict";
import * as W from "../../package/contents/ui/wheel.mjs";

const F = 1000 / 60.03;   // (a frame, ms)
const STEP = 60;          // (a notch: 3 lines × 20 px, the desktop's default)
const LONG = 200;         // (Kirigami.Units.longDuration)

interface Ev { t: number; kind: "notch" | "begin" | "move" | "end"; dist: number }

const notches = (n: number, gap: number): Ev[] => Array.from({ length: n }, (_, i) => ({ t: i * gap, kind: "notch" as const, dist: -STEP }));
// (Wayland's touchpad: a move a report, its angle 12 eighths of a degree a pixel, Kirigami's distance for it)
function touchpad(hz: number, speed: number, ms: number, late = 0, seed = 1): Ev[] {
  let r = seed;
  const rnd = () => { r = (r * 16807) % 2147483647; return r / 2147483647; };
  const out: Ev[] = [{ t: 5.3, kind: "begin", dist: 0 }];
  for (let t = 5.3; t <= 5.3 + ms + 1e-9; t += 1000 / hz)
    out.push({ t: t + rnd() * late, kind: "move", dist: -Math.round(12 * speed / hz) / 120 * STEP });
  for (let i = 1; i < out.length; i++) out[i].t = Math.max(out[i].t, out[i - 1].t);   // (late ones come bunched, in order)
  out.push({ t: out[out.length - 1].t + 1000 / hz, kind: "end", dist: 0 });
  return out;
}

// wheel.mjs as WheelScroll.qml drives it: each frame the events that came since, the first step at once
// when it was still, then a step a frame; whole pixels. The steps, from the first that moved to the last
function play(events: Ev[], lo = -1e9, hi = 1e9, y0 = 0): { steps: number[]; ys: number[]; still: boolean; late: number } {
  const s = W.create(y0);
  const ys = [y0];
  let i = 0;
  let running = false;
  let first = -1;
  for (let k = 1; k < 400; k++) {
    let fresh = false;
    while (i < events.length && events[i].t <= k * F) {
      const e = events[i++];
      if (first < 0 && (e.kind === "notch" || e.kind === "move")) first = k;
      if (e.kind === "notch") W.notch(s, e.dist, LONG, STEP);
      else if (e.kind === "begin") W.padBegin(s);
      else if (e.kind === "end") W.padEnd(s);
      else W.padMove(s, e.dist);
      if (!running && W.moving(s)) { W.frame(s, F, lo, hi); running = true; fresh = true; }
      else if (!W.moving(s)) W.frame(s, 0, lo, hi);
    }
    if (running && !fresh) { W.frame(s, F, lo, hi); running = W.moving(s); }
    ys.push(Math.round(s.y));
  }
  const moved = ys.findIndex((y, k) => k > 0 && y !== ys[k - 1]);
  return { steps: stepsOf(ys), ys, still: !W.moving(s), late: moved - first };   // (late: frames from the input to its first move)
}
function stepsOf(ys: number[]): number[] {
  const st = ys.slice(1).map((y, k) => ys[k] - y);
  const moving = st.map((x, k) => (x !== 0 ? k : -1)).filter((k) => k >= 0);
  return moving.length ? st.slice(moving[0], moving[moving.length - 1] + 1) : [];
}
// How often the steps go from growing to shrinking or back by more than whole-pixel rounding: an ease
// turns once at most (it speeds up, then slows down); every turn more is judder
function turns(steps: number[], tol = 1.5): number {
  let n = 0, trend = 0, extreme = steps[0];
  for (const s of steps.slice(1)) {
    if (trend >= 0 && s < extreme - tol) { n += trend > 0 ? 1 : 0; trend = -1; extreme = s; }
    else if (trend <= 0 && s > extreme + tol) { n += trend < 0 ? 1 : 0; trend = 1; extreme = s; }
    else if ((trend >= 0 && s > extreme) || (trend <= 0 && s < extreme)) extreme = s;
  }
  return n;
}
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

// Kirigami 6.32's WheelHandler, as wheelhandler.cpp does it: each event stops its ease and starts one
// from where the list is to where it was going plus the event's distance (OutCubic, |Δ| × 200/60 ms,
// 50 ms at least), and as the fingers lift a glide from the pixels' speed × 2.5 (OutQuad, 10000 px/s²)
function kirigami(events: Ev[]): number[] {
  let y = 0, anim: { a: number; b: number; d: number; t: number; quad: boolean } | null = null;
  const queue: [number, number][] = [];
  const ys = [0];
  let i = 0;
  for (let k = 1; k < 400; k++) {
    if (anim) {
      anim.t += Math.floor(k * F) - Math.floor((k - 1) * F);
      const u = Math.min(1, anim.t / anim.d);
      y = anim.a + (anim.b - anim.a) * (anim.quad ? 1 - (1 - u) ** 2 : 1 - (1 - u) ** 3);
      if (u >= 1) anim = null;
    }
    while (i < events.length && events[i].t <= k * F) {
      const e = events[i++];
      if (e.kind === "end" && queue.length > 2) {
        const px = sum(queue.map((q) => q[1])), el = Math.max(1, queue[queue.length - 1][0] - queue[0][0]);
        const v = px / el * 2.5, time = Math.abs(v) / 0.01;   // (px/ms; 4000 × 2.5 px/s²: 0.01 px/ms²)
        queue.length = 0;
        anim = { a: y, b: y + time * v / 2, d: time, t: 0, quad: true };
        continue;
      }
      if (queue.length > 6) queue.shift();
      queue.push([Math.floor(e.t), e.kind === "move" ? e.dist / 6 : 0]);   // (its pixels: a sixth of the angle's distance)
      if (e.kind !== "notch" && e.kind !== "move") continue;
      const target = Math.round((anim && !anim.quad ? anim.b : y) + e.dist);
      const d = Math.abs(target - y);
      anim = null;
      if (d > 2) anim = { a: y, b: target, d: Math.max(50, Math.min(Math.round(d * 200 / 60), 200)), t: 0, quad: false };
      else y = target;
    }
    ys.push(Math.round(y));
  }
  return stepsOf(ys);
}

test("a notch eases out over Kirigami's 200 ms: the desktop's lines × 20 px, its steps only fall, the first frame moves", () => {
  const { steps, still, late } = play(notches(1, 0));
  assert.equal(late, 0);   // (it moves in the frame that comes next: Kirigami's ease began a frame later)
  assert.equal(sum(steps), STEP);
  assert.ok(steps[0] >= 12, String(steps));   // (as Kirigami's first: 23% of the way)
  for (let k = 1; k < steps.length; k++) assert.ok(steps[k] <= steps[k - 1] + 1, String(steps));
  assert.deepEqual(steps, kirigami(notches(1, 0)));   // (one notch alone: the same ease)
  assert.ok(still);
});

test("a spin keeps its pace: the steps go up once and down once, every notch's distance kept (Kirigami's go up and down)", () => {
  for (const [n, gap] of [[6, 50], [8, 25], [10, 40], [4, 80]]) {
    const { steps, still } = play(notches(n, gap));
    assert.equal(sum(steps), n * STEP, `${n}×${gap}: ${steps}`);
    // (the first notch's ease slows till the next ones speed it up, then it slows to a stop: twice at most)
    assert.ok(turns(steps) <= 2, `${n}×${gap}: ${turns(steps)} turns ${steps}`);
    assert.ok(steps.every((s) => s > 0), `${n}×${gap}: a frame that didn't move ${steps}`);
    assert.ok(still);
  }
  const old = kirigami(notches(6, 50));
  assert.ok(turns(old) >= 6, `Kirigami's: ${turns(old)} turns ${old}`);   // (each notch threw it forward again)
});

test("a notch the other way turns it back to where it began, and a notch on a moving list adds to where it goes", () => {
  assert.equal(sum(play([{ t: 0, kind: "notch", dist: -STEP }, { t: 30, kind: "notch", dist: STEP }]).steps), 0);
  assert.equal(sum(play([...notches(3, 30), { t: 100, kind: "notch", dist: STEP / 2 }]).steps), 2.5 * STEP);
});

test("the desktop's animations off: a notch is there at once", () => {
  const s = W.create(100);
  W.notch(s, -STEP, 0, STEP);
  assert.equal(W.frame(s, 0, -1e9, 1e9), 40);
  assert.equal(W.moving(s), false);
});

for (const hz of [60, 90, 125]) {
  test(`a touchpad's stream at ${hz} a second is followed evenly, its moves on time or late and bunched`, () => {
    for (const late of [0, 4, 8, 12]) {
      for (const seed of [1, 2, 3]) {
        const { steps, still, late: wait } = play(touchpad(hz, 200, 600, late, seed));
        assert.equal(wait, 0, `${hz} Hz: the first frame moves`);
        // (after its start, till the fingers lift: each frame's step within a tenth and rounding of the pace)
        const mid = steps.slice(12, 34);
        const pace = mid.slice().sort((a, b) => a - b)[mid.length >> 1];
        const off = mid.filter((s) => Math.abs(s - pace) > 0.1 * pace + 1);
        assert.ok(off.length <= (late ? 2 : 0), `${hz} Hz, ${late} ms late: ${off.length} uneven of ${mid} (pace ${pace})`);
        assert.ok(steps.every((s) => s > 0), `${hz} Hz, ${late} ms late: a frame that didn't move ${steps}`);
        assert.ok(still);
      }
    }
  });
}

test("each move applied as it comes, the moves of a frame at once (what the follower smooths), beats with the frames", () => {
  // (90 moves a second on 60 frames: one, two, one, two… a frame; what the follower above smooths)
  const raw: number[] = [];
  const ev = touchpad(90, 200, 600);
  let y = 0, i = 0;
  for (let k = 1; k < 40; k++) {
    while (i < ev.length && ev[i].t <= k * F) y += ev[i++].dist;
    raw.push(-y);
  }
  const st = raw.slice(1).map((v, k) => v - raw[k]).slice(5, 30);
  assert.ok(Math.max(...st) >= 1.8 * Math.min(...st), String(st));
});

test("as the fingers lift it glides on at the speed it had, slowing evenly (Kirigami's glide began at less than half)", () => {
  // (from the pace it had down to rest, no frame slows by more than a sixth of it)
  const slows = (steps: number[]) => Math.max(...steps.slice(30).map((s, k) => s - steps[30 + k + 1]).filter((d) => !Number.isNaN(d)));
  for (const hz of [60, 90, 125]) {
    for (const liftLate of [0, 0.5, 1]) {   // (the lift a move after the last, or a little later)
      const ev = touchpad(hz, 200, 600);
      ev[ev.length - 1].t += liftLate * 1000 / hz;
      const { steps } = play(ev);
      const pace = steps.slice(12, 34).sort((a, b) => a - b)[11];
      assert.ok(slows(steps) <= pace / 6 + 1, `${hz} Hz, lift ${liftLate} late: ${steps.slice(30)}`);
    }
  }
  const old = kirigami(touchpad(60, 200, 600));
  assert.ok(slows(old) >= 0.4 * 20, `Kirigami's: ${old.slice(30)}`);
});

test("fingers that stopped before they lifted don't glide; no lift seen (X11), it ends where they took it", () => {
  const stopped = touchpad(125, 200, 300);
  stopped[stopped.length - 1].t += 200;   // (the lift 200 ms after the last move)
  const a = play(stopped);
  const moves = stopped.filter((e) => e.kind === "move");
  assert.equal(sum(a.steps), -sum(moves.map((e) => e.dist)));
  assert.ok(a.still);
  const b = play(touchpad(125, 200, 300).filter((e) => e.kind === "move"));
  assert.equal(sum(b.steps), -sum(moves.map((e) => e.dist)));
  assert.ok(b.still);
});

test("it stops at an end; a touch held there goes back the other way at once", () => {
  const { ys } = play(notches(8, 25), -100, 1e9, 0);
  assert.equal(Math.min(...ys), -100);   // (up from 0, its top 100 px up: no further)
  const up = play(notches(3, 30), 0, 1e9, 50).ys;
  assert.equal(up[up.length - 1], 0);
  const s = W.create(10);
  W.padBegin(s);
  for (let k = 0; k < 20; k++) { W.padMove(s, -10); W.frame(s, F, 0, 1e9); }
  assert.equal(s.y, 0);
  W.padMove(s, 10);
  W.padMove(s, 10);
  W.padMove(s, 10);
  let y = s.y;
  for (let k = 0; k < 6 && y === 0; k++) y = W.frame(s, F, 0, 1e9);
  assert.ok(y > 0, "back the other way");
});

test("moved by anything else, it stops there", () => {
  const s = W.create(0);
  W.notch(s, -STEP, LONG, STEP);
  W.frame(s, F, -1e9, 1e9);
  W.stop(s, 500);
  assert.equal(W.moving(s), false);
  assert.equal(W.frame(s, F, -1e9, 1e9), 500);
});
