// Types for bookmarks.mjs, for the VS Code extension (TypeScript)

import type { FindItem } from "./find.mjs";

export interface Bookmark {
    key: string;
    kind: "you" | "claude";
    at: number;      // when its message was written (ms)
    text: string;    // its first 140 characters, on one line
    made: number;    // when it was bookmarked (ms)
}
export type BookmarkState = "here" | "earlier" | "far" | "gone";
export type BookmarkStep = { key: string } | { reach: string } | { end: true } | null;
export interface Markable extends FindItem {
    at?: number | null;
    thinking?: boolean;
    queued?: boolean;
    until?: number;
    sending?: boolean;
}

export const BOOKMARKS_MAX: number;
export const SNIPPET_CHARS: number;
export function canBookmark(it: Markable | null | undefined): boolean;
export function oneLine(text: string | undefined | null): string;
export function snippetOf(it: Markable): string;
export function entryOf(it: Markable, now: number): Bookmark;
export function withBookmark(list: readonly Bookmark[] | null | undefined, entry: Bookmark): Bookmark[] | null;
export function withoutBookmark(list: readonly Bookmark[] | null | undefined, key: string): Bookmark[];
export function keysOf(list: readonly Bookmark[] | null | undefined): Record<string, true>;
export function stateOf(mark: Bookmark, loaded: ReadonlyMap<string, unknown> | ReadonlySet<string> | Record<string, unknown> | null,
                        more: boolean, capped: boolean, settled?: Record<string, "far" | "gone"> | null): BookmarkState;
export function step(list: readonly Bookmark[], states: Record<string, BookmarkState> | null, tops: Record<string, number>,
                     viewTop: number, back: boolean): BookmarkStep;
export function adoptable(localV: number, busy: boolean, answerV: number | undefined | null): boolean;
export function staysOpen(listWidth: number, cardWidth: number, beside: boolean): boolean;
