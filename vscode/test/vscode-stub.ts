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
  panels: [] as { sent: unknown[]; receive(m: unknown): void; show(visible: boolean): void; dispose(): void; readonly disposed: boolean }[],
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

export const workspace = {
  getConfiguration: () => ({ get: <T>(key: string, fallback: T) => (overrides.has(key) ? (overrides.get(key) as T) : fallback), update: async () => undefined }),
  workspaceFolders: undefined,
  workspaceFile: undefined,
  onDidChangeConfiguration: configChanges.on,
  onDidChangeWorkspaceFolders: disposable,
  registerTextDocumentContentProvider: disposable,
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

export const window = {
  terminals: [],
  visibleTextEditors: [],
  state: { focused: false },
  onDidCloseTerminal: disposable,
  onDidChangeWindowState: disposable,
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
    let onMessage: (m: unknown) => void = () => undefined;
    const viewState = listeners<unknown>();
    const closed = listeners<void>();
    let disposed = false;
    let title = initialTitle;
    let visible = false;
    const alive = () => {
      if (disposed) throw new Error("Webview is disposed");
    };
    const webview = {
      html: "",
      cspSource: "vscode-webview:",
      asWebviewUri: (u: unknown) => u,
      postMessage: async (m: unknown) => (disposed ? false : (sent.push(m), true)),
      onDidReceiveMessage: (l: (m: unknown) => void) => ((onMessage = l), disposable()),
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
      get disposed() {
        return disposed;
      },
      get webview() {
        alive();
        return webview;
      },
      sent,
      receive: (m: unknown) => onMessage(m),
      show(v: boolean) {
        visible = v;
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
  showInformationMessage: async (m: string) => void recorded.messages.push(m),
  showWarningMessage: async (m: string) => void recorded.messages.push(m),
  showErrorMessage: async (m: string) => void recorded.messages.push(m),
  setStatusBarMessage: (m: string) => (recorded.messages.push(m), disposable()),
  withProgress: async <T>(_o: unknown, task: (p: { report(): void }) => Promise<T>) => task({ report() {} }),
};

export enum ProgressLocation {
  Notification = 15,
}

export const commands = {
  registerCommand: (id: string, fn: (...args: unknown[]) => unknown) => {
    recorded.commands.set(id, fn);
    return disposable();
  },
  executeCommand: async () => undefined,
  getCommands: async () => [] as string[],
};

export const extensions = { onDidChange: disposable };

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
  uiKind: UIKind.Desktop,
  openExternal: async () => true,
  clipboard: { writeText: async (text: string) => void clipboardWrites.push(text), readText: async () => clipboardWrites.at(-1) ?? "" },
};

export enum ViewColumn {
  Active = -1,
}

export enum ConfigurationTarget {
  Global = 1,
}

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export class ThemeIcon {
  constructor(public id: string) {}
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
