// Types for newsince.mjs, for the VS Code extension (TypeScript)

export interface NewSince {
  key: string;      // (Claude's first reply since: the Chat tab's)
  stepKey: string;  // (the first item since: Steps')
  since: number;    // (ms: when you left, on the clock of the computer the chat runs on)
  seen?: boolean;   // (it has been in view with the window shown: only then can its timer take it)
}
export declare const NEW_SINCE_READ_MS: number;
export declare const NEW_SINCE_TIP: string;
export declare function newSinceText(when: string): string;
export declare function newSinceOf(away: { key: string; stepKey: string; since: number } | null | undefined, was: NewSince | null): NewSince | null;
export declare function newSinceKey(at: NewSince | null, steps: boolean): string;
export declare function newSinceLooked(at: NewSince | null, shown: boolean, inView: boolean): NewSince | null;
export declare function newSinceInView(top: number, height: number, view: number): boolean;
export declare function newSinceReading(at: NewSince | null, shown: boolean, atEnd: boolean): boolean;
export declare function newSinceAfterSend(at: NewSince | null, text: string): NewSince | null;
