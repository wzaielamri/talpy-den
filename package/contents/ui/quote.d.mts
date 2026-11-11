// Types for quote.mjs, for the VS Code extension (TypeScript)

export declare const QUOTE_BUTTON: string;
export declare const QUOTE_MENU: string;
export declare const QUOTE_CHARS: number;
export declare function quoteOf(selected: string): string;
export declare function withQuote(box: string, selected: string): { text: string; cursor: number };
