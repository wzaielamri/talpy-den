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
// A button in a pick list's title bar; icon: a codicon id
export interface PickButton { icon: string; tooltip: string }
// many: several can be picked; sortByLabel false: the items keep the order given while you type, headings
// too (VS Code otherwise sorts them by how well they match, and drops the separators)
export interface QuickPickOptions {
  title?: string; placeHolder?: string; many?: boolean; matchOnDescription?: boolean; matchOnDetail?: boolean; sortByLabel?: boolean;
}
// A pick list that stays open while its caller changes it (VS Code's QuickPick: actions' findChat searches as
// you type and folds headings, pickHosts reloads its hosts). Its items and buttons are the caller's own, and
// the same objects come back; activeItems: the one the cursor is on; hide(): closed as Escape closes it
// (onDidHide fires); dispose(): gone
export interface QuickPick<T extends PickItem> {
  items: readonly T[];
  activeItems: readonly T[];
  selectedItems: readonly T[];
  buttons: readonly PickButton[];
  busy: boolean;
  keepScrollPosition: boolean;
  readonly onDidChangeValue: Event<string>;
  readonly onDidChangeSelection: Event<readonly T[]>;
  readonly onDidTriggerButton: Event<PickButton>;
  readonly onDidAccept: Event<void>;
  readonly onDidHide: Event<void>;
  show(): void;
  hide(): void;
  dispose(): void;
}

// A folder the window has open. path: where it is on its machine; remote: that machine is the host the window
// is connected to (Remote-SSH, Dev Containers), not this computer; uri: the host's own name for the folder
// (VS Code: its URI, which Talpy Chat's empty view hands back for "New chat in <folder>")
export interface WindowFolder { name: string; path: string; remote: boolean; uri: string }

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
  quickPick<T extends PickItem>(options: QuickPickOptions): QuickPick<T>; // (shown once show() is called)
  input(options?: InputOptions): Promise<string | undefined>;
  choose(options: ChooseOptions): Promise<string[] | undefined>;
  progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R>;
  statusMessage(text: string, ms: number): void;
  readonly settings: HostSettings;
  // inUse: interacted with recently, else focused (VS Code's window `active`, else `focused`); it can change
  // without the focus doing so, hence onDidChangeUse (away's AwayWatch). An implementation must fire
  // onDidChangeUse on every change of the window's focus too, not only when inUse changes: the dashboard's
  // reaction to the focus (clearing what was seen) listens on it, not on onDidChange. For one change of the
  // window's state, onDidChange fires before onDidChangeUse: the window claims the lead on the focus (Notifier),
  // and coming back (AwayWatch -> Dashboard.cameBack -> Notifier.digest) shows "While you were away" only in
  // the window that leads.
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
  // The window starts again, Claude Code's panel with it, on the account it was switched to (accountSwitch);
  // VS Code: "workbench.action.reloadWindow", which can be declined (unsaved files)
  reloadWindow(): Promise<void>;
  workspaceFolders(): readonly WindowFolder[];
  readonly onDidChangeWorkspaceFolders: Event<void>;
  // Values kept for every window, over restarts, by key (VS Code: the extension's globalState); chatPanes keeps
  // the side questions panel's pick and whether it's open. get: the value kept, else fallback
  readonly state: { get<T>(key: string, fallback: T): T; update(key: string, value: unknown): Promise<void> };
  // remoteAuthority: the remote the window has open ("ssh-remote+lab", "dev-container+…"), as it is at
  // each read (dashboard: which host or container the window is on); sessionId: this window's own id, new
  // each time it starts (VS Code's env.sessionId; dashboard: the name its host watchers go by, watchName)
  readonly environment: { readonly remoteName?: string; readonly remoteAuthority?: string; readonly web: boolean; readonly sessionId: string };
  readonly log: { info(m: string): void; warn(m: string): void; error(m: string): void };
}
