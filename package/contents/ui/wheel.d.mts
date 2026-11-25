// Types for wheel.mjs, for the tests (TypeScript)

export interface Clock {
  last: number;
  k: number;
  period: number;
  system: boolean;
  rates: number[];
}
export interface Wheel {
  y: number;
  v: number;
  curve: { p0: number; v0: number; p1: number; d: number; t: number } | null;
  pad: object | null;
  fling: number | null;
  written: number;
  clock: Clock;
}
export interface WheelEvent {
  angle: number;
  pixel: number;
  phase: "none" | "begin" | "update" | "end";
}
export const FLING_DECEL: number;
export const PAD_LAG: number;
export const PAD_RATE: number;
export const PAD_IDLE: number;
export const PAD_GLIDE: number;
export const RATES: number[];
export function create(y: number): Wheel;
export function resetFrames(): void;
export function rate(s: Wheel, hz: number, rates: number[]): void;
export function period(s: Wheel): number;
export function input(s: Wheel, ev: WheelEvent, at: number, lo: number, hi: number, step: number, long: number):
  { put: number; starting: boolean; scrolled: boolean };
export function tick(s: Wheel, now: number, at: number, lo: number, hi: number): number;
export function finish(s: Wheel, lo: number, hi: number): number;
export function moving(s: Wheel): boolean;
export function stop(s: Wheel, y: number): void;
export function notch(s: Wheel, dist: number, long: number, step: number, lo: number, hi: number): void;
export function padBegin(s: Wheel): void;
export function padMove(s: Wheel, dist: number, burst?: boolean): void;
export function padEnd(s: Wheel): void;
export function frame(s: Wheel, dt: number, lo: number, hi: number, late?: boolean): number;
