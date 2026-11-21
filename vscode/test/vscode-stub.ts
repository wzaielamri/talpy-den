// Just enough of the vscode module to run the extension outside VS Code:
// settings read as their defaults, no remote window, and a record of what
// the extension registers (commands, the view, the status bar item).

import * as nodePath from "node:path";

const disposable = () => ({ dispose() {} });

export const recorded = {
  commands: new Map<string, (...args: unknown[]) => unknown>(),
  viewProviders: new Map<string, unknown>(),
  treeViews: new Map<string, { badge: unknown }>(),
  uriHandlers: [] as unknown[],
  statusBarItems: [] as { text: string; tooltip: unknown; backgroundColor: unknown; show(): void; dispose(): void }[],
  messages: [] as string[],
  panels: [] as { sent: unknown[]; receive(m: unknown): void; show(visible: boolean): void; activate(on: boolean): void; dispose(): void; readonly disposed: boolean }[],
  quickPicks: [] as StubQuickPick[],
};

// Listeners of a kind of event, each with a disposable that takes it off
function listeners<T>() {
  const list = new Set<(e: T) => void>();
  return {
    on: (l: (e: T) => void) => (list.add(l), { dispose: () => void list.delete(l) }),
    fire: (e: T) => [...list].forEach((l) => l(e)),
  };
}

// A change of settings, as VS Code tells it: keys like "talpyDen.chatTextScale"
const configChanges = listeners<{ affectsConfiguration(section: string): boolean }>();
export function changeSettings(...keys: string[]): void {
  configChanges.fire({ affectsConfiguration: (section) => keys.some((k) => k === section || k.startsWith(section + ".")) });
}

// settings a test sets (key -> value); the rest read as their defaults
export const overrides = new Map<string, unknown>();
// another section's settings, by "section.key" (a section other than talpyDen reads these first)
export const sectionValues = new Map<string, unknown>();

// The calls the window, command and env APIs got, in order (VsCodeHost's tests read them), and the answer a
// method gives (answers, by method name: a value, or a function of the call's arguments; none: undefined,
// as when Escape is pressed)
export const calls: { method: string; args: unknown[] }[] = [];
export const answers = new Map<string, unknown>();
function call(method: string, args: unknown[], fallback?: unknown): unknown {
  calls.push({ method, args });
  if (!answers.has(method)) return fallback;
  const answer = answers.get(method);
  return typeof answer === "function" ? answer(...args) : answer;
}

const folderChanges = listeners<void>();

export const workspace = {
  getConfiguration: (section?: string): { get<T>(key: string, fallback: T): T; update(...args: unknown[]): Promise<unknown>; inspect?(key: string): unknown } => ({
    get: <T>(key: string, fallback: T) => {
      const qualified = `${section}.${key}`;
      if (section !== "talpyDen" && sectionValues.has(qualified)) return sectionValues.get(qualified) as T;
      return overrides.has(key) ? (overrides.get(key) as T) : fallback;
    },
    update: async (key: string, value: unknown, target?: unknown) => void call("config.update", [section, key, value, target]),
    inspect: (key: string) => call("config.inspect", [section, key]),
  }),
  // the folders a test opens (setWorkspaceFolders)
  workspaceFolders: undefined as { name: string; uri: Uri }[] | undefined,
  workspaceFile: undefined,
  // the documents open in editors (a test's)
  textDocuments: [] as { uri: Uri; isDirty: boolean; save(): Promise<boolean> }[],
  onDidChangeConfiguration: configChanges.on,
  onDidChangeWorkspaceFolders: folderChanges.on,
  registerTextDocumentContentProvider: disposable,
  // a file of a test's own (stubFiles) as a document: its lines, and the text of a range of them
  openTextDocument: async (u: { path: string }) => {
    if (!stubFiles.has(u.path)) throw new Error(`no file ${u.path}`);
    const lines = stubFiles.get(u.path)!.split("\n");
    return {
      uri: u,
      lineCount: lines.length,
      lineAt: (i: number) => ({ text: lines[i] }),
      getText: (r: Range) => {
        const part = lines.slice(r.start.line, r.end.line + 1);
        part[part.length - 1] = part[part.length - 1].slice(0, r.end.character);
        part[0] = part[0].slice(r.start.character);
        return part.join("\n");
      },
    };
  },
  // files: a test's own (stubFiles, by path)
  fs: { readFile: async (u: { path: string }) => {
    if (!stubFiles.has(u.path)) throw new Error(`no file ${u.path}`);
    return new TextEncoder().encode(stubFiles.get(u.path));
  } },
  // a watcher: changeFile fires its change
  createFileSystemWatcher: (p: { base: { path: string }; pattern: string }) => {
    const changed = listeners<unknown>();
    const off = fileChanges.on((file) => file === nodePath.posix.join(p.base.path, p.pattern) && changed.fire(undefined));
    return { onDidChange: changed.on, onDidCreate: changed.on, onDidDelete: disposable, dispose: () => off.dispose() };
  },
};

export function setWorkspaceFolders(folders: { name: string; uri: Uri }[] | undefined): void {
  workspace.workspaceFolders = folders;
  folderChanges.fire(undefined);
}

export const stubFiles = new Map<string, string>();
const fileChanges = listeners<string>();
export function changeFile(file: string, text: string): void {
  stubFiles.set(file, text);
  fileChanges.fire(file);
}

export class RelativePattern {
  constructor(public base: { path: string }, public pattern: string) {}
}

const logChannel = () => ({
  info() {},
  warn() {},
  error() {},
  debug() {},
  trace() {},
  show() {},
  appendLine() {},
  dispose() {},
});

// A pick list that stays open (createQuickPick): what the extension set on it, kept as set, and what a user does
// to it (type, press a title bar button, tick items, accept); hide() closes it as VS Code's does (onDidHide)
type QuickRow = { label: string; kind?: number; iconPath?: unknown; description?: string; detail?: string; alwaysShow?: boolean; picked?: boolean };
type QuickButton = { iconPath: unknown; tooltip?: string };
export class StubQuickPick {
  title: string | undefined;
  placeholder: string | undefined;
  canSelectMany = false;
  matchOnDescription = false;
  matchOnDetail = false;
  sortByLabel = true;
  keepScrollPosition = false;
  busy = false;
  items: readonly QuickRow[] = [];
  activeItems: readonly QuickRow[] = [];
  selectedItems: readonly QuickRow[] = [];
  buttons: readonly QuickButton[] = [];
  visible = false;
  disposed = false;
  private changedValue = listeners<string>();
  private changedSelection = listeners<readonly QuickRow[]>();
  private pressed = listeners<QuickButton>();
  private accepted = listeners<void>();
  private hidden = listeners<void>();
  onDidChangeValue = this.changedValue.on;
  onDidChangeSelection = this.changedSelection.on;
  onDidTriggerButton = this.pressed.on;
  onDidAccept = this.accepted.on;
  onDidHide = this.hidden.on;
  show() {
    this.visible = true;
  }
  hide() {
    if (!this.visible) return;
    this.visible = false;
    this.hidden.fire(undefined);
  }
  dispose() {
    this.hide();
    this.disposed = true;
  }
  type(value: string) {
    this.changedValue.fire(value);
  }
  press(button: QuickButton) {
    this.pressed.fire(button);
  }
  select(items: readonly QuickRow[]) {
    this.selectedItems = items;
    this.changedSelection.fire(items);
  }
  accept() {
    this.accepted.fire(undefined);
  }
}

const windowStates = listeners<{ focused: boolean }>();
// The window gains or loses the focus
export function setWindowFocused(focused: boolean): void {
  window.state.focused = focused;
  windowStates.fire({ focused });
}

export const window = {
  terminals: [],
  visibleTextEditors: [],
  state: { focused: false },
  onDidCloseTerminal: disposable,
  onDidChangeWindowState: windowStates.on,
  createOutputChannel: logChannel,
  createStatusBarItem: () => {
    const item = { text: "", tooltip: undefined as unknown, backgroundColor: undefined as unknown, show() {}, hide() {}, dispose() {} };
    recorded.statusBarItems.push(item);
    return item;
  },
  // a tree view: its badge is kept (recorded.treeViews, by id)
  createTreeView: (id: string) => {
    const tree = { badge: undefined as unknown, dispose() {} };
    recorded.treeViews.set(id, tree);
    return tree;
  },
  registerWebviewViewProvider: (id: string, provider: unknown) => {
    recorded.viewProviders.set(id, provider);
    return disposable();
  },
  registerUriHandler: (handler: unknown) => {
    recorded.uriHandlers.push(handler);
    return disposable();
  },
  // an editor tab with a page: what the page is sent, and a way to send it
  // what a page would (panel.receive), to show or hide it (panel.show) and to
  // close it (panel.dispose). As VS Code's, once it's closed its webview,
  // title and visible throw.
  createWebviewPanel: (_viewType?: string, initialTitle = "") => {
    const sent: unknown[] = [];
    const messages = listeners<unknown>(); // (each listener hears what the page says, as VS Code's)
    const viewState = listeners<unknown>();
    const closed = listeners<void>();
    let disposed = false;
    let title = initialTitle;
    let visible = false;
    let active = false;
    const alive = () => {
      if (disposed) throw new Error("Webview is disposed");
    };
    const webview = {
      html: "",
      cspSource: "vscode-webview:",
      asWebviewUri: (u: unknown) => u,
      postMessage: async (m: unknown) => (disposed ? false : (sent.push(m), true)),
      onDidReceiveMessage: messages.on,
    };
    const panel = {
      get title() {
        alive();
        return title;
      },
      set title(t: string) {
        alive();
        title = t;
      },
      iconPath: undefined as unknown,
      get visible() {
        alive();
        return visible;
      },
      get active() {
        alive();
        return active;
      },
      get disposed() {
        return disposed;
      },
      get webview() {
        alive();
        return webview;
      },
      sent,
      receive: (m: unknown) => messages.fire(m),
      show(v: boolean) {
        visible = v;
        viewState.fire(undefined);
      },
      // (in front, with the focus: its keys go to it)
      activate(v: boolean) {
        active = v;
        visible = visible || v;
        viewState.fire(undefined);
      },
      onDidChangeViewState: viewState.on,
      onDidDispose: closed.on,
      reveal() {},
      dispose() {
        if (disposed) return;
        disposed = true;
        closed.fire();
      },
    };
    recorded.panels.push(panel);
    return panel;
  },
  showTextDocument: async () => undefined,
  showInformationMessage: async (m: string, ...rest: unknown[]) => (recorded.messages.push(m), call("showInformationMessage", [m, ...rest])),
  showWarningMessage: async (m: string, ...rest: unknown[]) => (recorded.messages.push(m), call("showWarningMessage", [m, ...rest])),
  showErrorMessage: async (m: string, ...rest: unknown[]) => (recorded.messages.push(m), call("showErrorMessage", [m, ...rest])),
  showQuickPick: async (...args: unknown[]) => call("showQuickPick", args),
  createQuickPick: () => {
    const qp = new StubQuickPick();
    recorded.quickPicks.push(qp);
    return qp;
  },
  showInputBox: async (...args: unknown[]) => call("showInputBox", args),
  showOpenDialog: async (...args: unknown[]) => call("showOpenDialog", args),
  setStatusBarMessage: (m: string, ms?: number) => (recorded.messages.push(m), call("setStatusBarMessage", [m, ms]), disposable()),
  withProgress: async <T>(o: unknown, task: (p: { report(): void }) => Promise<T>) => (call("withProgress", [o]), task({ report() {} })),
};

export enum ProgressLocation {
  Window = 10,
  Notification = 15,
}

export const commands = {
  registerCommand: (id: string, fn: (...args: unknown[]) => unknown) => {
    recorded.commands.set(id, fn);
    return disposable();
  },
  executeCommand: async (...args: unknown[]) => call("executeCommand", args),
  getCommands: async () => [] as string[],
};

// The extensions installed (by id: a test's; none by default); installed, removed or enabled:
// changeExtensions tells the listeners
export const installedExtensions = new Set<string>();
const extensionChanges = listeners<void>();
export const extensions = {
  onDidChange: extensionChanges.on,
  getExtension: (id: string) => (installedExtensions.has(id) ? { id } : undefined),
};
export function changeExtensions(): void {
  extensionChanges.fire(undefined);
}

export const comments = {
  createCommentController: (id: string, label: string) => ({ id, label, options: undefined, commentingRangeProvider: undefined, dispose: () => undefined }),
};

export enum QuickPickItemKind {
  Separator = -1,
  Default = 0,
}

export enum CommentMode {
  Editing = 0,
  Preview = 1,
}

export const clipboardWrites: string[] = [];
export enum UIKind {
  Desktop = 1,
  Web = 2,
}

export const env = {
  remoteName: undefined as string | undefined,
  sessionId: undefined as string | undefined, // (none unless a test sets one)
  uiKind: UIKind.Desktop,
  openExternal: async (uri: unknown) => call("openExternal", [uri], true),
  clipboard: { writeText: async (text: string) => void clipboardWrites.push(text), readText: async () => clipboardWrites.at(-1) ?? "" },
};

export enum ViewColumn {
  Active = -1,
}

// The oldest VS Code the extension runs in, which has no secondary side bar for extensions' views: a chat
// opens in a tab of its own, as every test of a chat's tab has it. setVersion: a later one (the side bar's
// view: chatSurface.ts sideBarSupported)
export let version = "1.90.0";
export function setVersion(v: string): void {
  version = v;
}

export enum ConfigurationTarget {
  Global = 1,
  Workspace = 2,
  WorkspaceFolder = 3,
}

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export class ThemeIcon {
  constructor(public id: string) {}
}

export class Position {
  constructor(public line: number, public character: number) {}
}

export class Range {
  start: Position;
  end: Position;
  constructor(startLine: number, startCharacter: number, endLine: number, endCharacter: number) {
    this.start = new Position(startLine, startCharacter);
    this.end = new Position(endLine, endCharacter);
  }
}

export class ThemeColor {
  constructor(public id: string) {}
}

export class MarkdownString {
  value = "";
  constructor(value?: string, public supportThemeIcons?: boolean) {
    this.value = value ?? "";
  }
  appendMarkdown(s: string) {
    this.value += s;
    return this;
  }
  appendText(s: string) {
    this.value += s;
    return this;
  }
}

export class Uri {
  private constructor(public scheme: string, public path: string, public authority = "") {}
  static file(p: string) {
    return new Uri("file", p);
  }
  static from(c: { scheme: string; authority?: string; path: string }) {
    return new Uri(c.scheme, c.path, c.authority ?? "");
  }
  static parse(s: string) {
    return new Uri(s.split(":")[0], s);
  }
  with(c: { path?: string }) {
    return new Uri(this.scheme, c.path ?? this.path, this.authority);
  }
  static joinPath(base: Uri, ...parts: string[]) {
    return new Uri(base.scheme, [base.path, ...parts].join("/"));
  }
  get fsPath() {
    return this.path;
  }
  toString() {
    return `${this.scheme}://${this.path}`;
  }
}

export class EventEmitter<T> {
  private listeners: ((e: T) => void)[] = [];
  event = (l: (e: T) => void) => {
    this.listeners.push(l);
    return { dispose: () => undefined };
  };
  fire(e: T) {
    for (const l of this.listeners) l(e);
  }
  dispose() {}
}
