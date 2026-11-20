// What the core asks of whatever hosts it (the VS Code extension, the desktop app): dialogs, settings,
// the clipboard, the window's focus. Paths cross as plain strings, never as a host's own types.

import type { Event } from "./events";

export type MessageLevel = "info" | "warning" | "error";
export interface MessageOptions { modal?: boolean; detail?: string }

// A row of a pick list; separator: a heading line, not a choice; icon: a codicon id
export interface PickItem {
  label: string; description?: string; detail?: string; picked?: boolean; alwaysShow?: boolean;
  separator?: boolean; icon?: string;
}
export interface PickOptions { title?: string; placeHolder?: string; matchOnDescription?: boolean; matchOnDetail?: boolean; ignoreFocusOut?: boolean }
export interface InputOptions {
  title?: string; prompt?: string; placeHolder?: string; value?: string; password?: boolean; ignoreFocusOut?: boolean;
  validateInput?: (value: string) => string | undefined | null;
}
// onRemote: the window's remote file system (Remote-SSH), not this computer's
export interface ChooseOptions {
  kind: "folder" | "file"; many?: boolean; title?: string; openLabel?: string; defaultPath?: string; onRemote?: boolean;
  filters?: Record<string, string[]>;
}

// The talpyDen.* settings
export interface HostSettings {
  get<T>(key: string, fallback: T): T;
  update(key: string, value: unknown): Promise<void>; // the user (global) scope
  inspect(key: string): { global?: unknown; workspace?: unknown; workspaceFolder?: unknown } | undefined;
  other<T>(section: string, key: string, fallback: T): T; // another extension's or VS Code's setting
  readonly onDidChange: Event<string[]>; // the talpyDen keys that changed
}

export interface HostServices {
  // Resolves to the action clicked, or undefined when dismissed
  message<A extends string>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined>;
  // The caller's own item comes back (the same object), or undefined on Escape
  pick<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T | undefined>;
  pickMany<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T[] | undefined>;
  input(options?: InputOptions): Promise<string | undefined>;
  choose(options: ChooseOptions): Promise<string[] | undefined>;
  progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R>;
  statusMessage(text: string, ms: number): void;
  readonly settings: HostSettings;
  readonly focus: { readonly focused: boolean; readonly onDidChange: Event<boolean> };
  readonly clipboard: { read(): Promise<string>; write(text: string): Promise<void> };
  openExternal(url: string): Promise<boolean>;
  openFile(path: string): Promise<void>; // VS Code: "vscode.open"
  revealFile(path: string): Promise<void>; // VS Code: "revealFileInOS"
  openSettings(query: string): Promise<void>; // VS Code: "workbench.action.openSettings"
  showView(): Promise<void>; // VS Code: "talpyDen.view.focus"
  setContext(key: string, value: unknown): void; // VS Code: "setContext"
  workspaceFolders(): readonly { name: string; path: string }[];
  readonly onDidChangeWorkspaceFolders: Event<void>;
  readonly environment: { readonly remoteName?: string; readonly web: boolean };
  readonly log: { info(m: string): void; warn(m: string): void; error(m: string): void };
}
