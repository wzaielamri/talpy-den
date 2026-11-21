// Types for fill.mjs, for the tests (TypeScript)

export const FILL_ALL: number;
export const FILL_INTERVAL: number;
export const FILL_STEP_MAX: number;
export const FILL_SLOW: number;
export const FILL_QUICK: number;
export function fillStepMin(lineHeight: number): number;
export function fillStart(viewHeight: number, lineHeight: number): { buffer: number; step: number; interval: number };
export function fillNext(buffer: number, step: number): number;
export function fillPace(step: number, cost: number, lineHeight: number): { step: number; interval: number };
