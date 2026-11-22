// Types for newsince.mjs, for the VS Code extension (TypeScript)

export interface NewSince {
  key: string;      // (Claude's first reply since: the Chat tab's)
  stepKey: string;  // (the first item since: Steps')
  since: number;    // (ms: when you left, on the clock of the computer the chat runs on)
  seen?: { chat: boolean; steps: boolean };   // (seen on that tab: only then can its read timer take it)
}
export declare const NEW_SINCE_READ_MS: number;
export declare const NEW_SINCE_SEEN_MS: number;
export declare const NEW_SINCE_TIP: string;
export declare function newSinceText(when: string): string;
export declare function newSinceOf(away: { key: string; stepKey: string; since: number } | null | undefined, was: NewSince | null): NewSince | null;
export declare function newSinceKey(at: NewSince | null, steps: boolean): string;
export declare function newSinceSeenOn(at: NewSince | null, steps: boolean): boolean;
export declare function newSinceLooking(at: NewSince | null, steps: boolean, shown: boolean, inView: boolean, still: boolean, placed: boolean): boolean;
export declare function newSinceSeen(at: NewSince | null, steps: boolean): NewSince | null;
export declare function newSinceInView(top: number, height: number, view: number): boolean;
export declare function newSinceReading(at: NewSince | null, steps: boolean, shown: boolean, atEnd: boolean): boolean;
export declare function newSinceAfterSend(at: NewSince | null, text: string): NewSince | null;
export declare function newSinceAfterHide(at: NewSince | null): NewSince | null;
