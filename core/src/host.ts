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
// onRemote: the window's remote file system (Remote-SSH), not this computer's; localOnly: keep only this
// computer's files (a Remote window's dialog can also pick the remote's)
export interface ChooseOptions {
  kind: "folder" | "file"; many?: boolean; title?: string; openLabel?: string; defaultPath?: string; onRemote?: boolean; localOnly?: boolean;
  filters?: Record<string, string[]>;
}

// Where a setting is written (a caller keeps a value in the scope it is already set in)
export type SettingScope = "global" | "workspace" | "workspaceFolder";

// The talpyDen.* settings
export interface HostSettings {
  get<T>(key: string, fallback: T): T;
  update(key: string, value: unknown, scope?: SettingScope): Promise<void>; // scope: global by default
  inspect(key: string): { global?: unknown; workspace?: unknown; workspaceFolder?: unknown } | undefined;
  other<T>(section: string, key: string, fallback: T): T; // another extension's or VS Code's setting
  updateOther(section: string, key: string, value: unknown): Promise<void>; // another section's key, globally
  // Tells which of these full keys ("editor.fontFamily") a settings change touched; silent when none
  watchOther(keys: readonly string[]): Event<string[]>;
  readonly onDidChange: Event<string[]>; // the talpyDen keys that changed
}

export interface HostServices {
  // Resolves to the action clicked, or undefined when dismissed; an action is its text or an item with a
  // title, and the caller's own one comes back (the same object), so buttons of one title stay apart
  message<A extends string | { title: string }>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined>;
  // The caller's own item comes back (the same object), or undefined on Escape
  pick<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T | undefined>;
  pickMany<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T[] | undefined>;
  input(options?: InputOptions): Promise<string | undefined>;
  choose(options: ChooseOptions): Promise<string[] | undefined>;
  progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R>;
  statusMessage(text: string, ms: number): void;
  readonly settings: HostSettings;
  // inUse: interacted with recently, else focused (VS Code's window `active`, else `focused`); it can change
  // without the focus doing so, hence onDidChangeUse (away's AwayWatch)
  readonly focus: {
    readonly focused: boolean; readonly onDidChange: Event<boolean>;
    readonly inUse: boolean; readonly onDidChangeUse: Event<boolean>;
  };
  readonly clipboard: { read(): Promise<string>; write(text: string): Promise<void> };
  openExternal(url: string): Promise<boolean>;
  openFile(path: string): Promise<void>; // VS Code: "vscode.open"
  revealFile(path: string): Promise<void>; // VS Code: "revealFileInOS"
  openSettings(query: string): Promise<void>; // VS Code: "workbench.action.openSettings"
  showView(): Promise<void>; // VS Code: "talpyDen.view.focus"
  setContext(key: string, value: unknown): void; // VS Code: "setContext"
  workspaceFolders(): readonly { name: string; path: string }[];
  readonly onDidChangeWorkspaceFolders: Event<void>;
  // remoteAuthority: the remote the window has open ("ssh-remote+lab", "dev-container+…"), as it is at
  // each read (dashboard: which host or container the window is on); sessionId: this window's own id, new
  // each time it starts (VS Code's env.sessionId; dashboard: the name its host watchers go by, watchName)
  readonly environment: { readonly remoteName?: string; readonly remoteAuthority?: string; readonly web: boolean; readonly sessionId: string };
  readonly log: { info(m: string): void; warn(m: string): void; error(m: string): void };
}
