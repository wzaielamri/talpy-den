import * as vscode from "vscode";
import { Emitter, type Event } from "../../core/src/events";
import type {
  ChooseOptions, HostServices, HostSettings, InputOptions, MessageLevel, MessageOptions, PickButton, PickItem, PickOptions, QuickPick,
  QuickPickOptions, WindowFolder,
} from "../../core/src/host";
import { currentRemoteAuthority } from "./remoteHost";

// In use: interacted with recently (VS Code's `active`, newer than the typings), else focused
function inUse(state: vscode.WindowState): boolean {
  return (state as { active?: boolean }).active ?? state.focused;
}

// HostServices over the VS Code API: the one place paths and vscode.Uri turn into each other
export class VsCodeHost implements HostServices {
  private settingsChanged = new Emitter<string[]>();
  private focusChanged = new Emitter<boolean>();
  private useChanged = new Emitter<boolean>();
  private foldersChanged = new Emitter<void>();
  private subscriptions: vscode.Disposable[];

  // settingKeys: the talpyDen.* settings the extension declares (without the prefix). VS Code says only whether
  // a section changed, so these are asked one by one which of them did. kept: where state is kept (the
  // extension's globalState); none (a test's): nothing is, each value reads as its fallback
  constructor(private readonly output: vscode.LogOutputChannel, private readonly settingKeys: readonly string[], private readonly kept?: vscode.Memento) {
    this.subscriptions = [
      vscode.workspace.onDidChangeConfiguration((e) => {
        const keys = this.settingKeys.filter((k) => e.affectsConfiguration(`talpyDen.${k}`));
        if (keys.length) this.settingsChanged.fire(keys);
      }),
      // (the focus before the use: the window claims the lead before coming back asks who leads, host.ts)
      vscode.window.onDidChangeWindowState((s) => {
        this.focusChanged.fire(s.focused);
        this.useChanged.fire(inUse(s));
      }),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.foldersChanged.fire(undefined)),
    ];
  }

  dispose(): void {
    for (const s of this.subscriptions) s.dispose();
    this.settingsChanged.dispose();
    this.focusChanged.dispose();
    this.useChanged.dispose();
    this.foldersChanged.dispose();
  }

  async message<A extends string | { title: string }>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined> {
    const show = level === "error" ? vscode.window.showErrorMessage : level === "warning" ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
    const opts: vscode.MessageOptions = {};
    if (options?.modal !== undefined) opts.modal = options.modal;
    if (options?.detail !== undefined) opts.detail = options.detail;
    return (await show(text, opts, ...(actions as vscode.MessageItem[]))) as A | undefined; // (strings and items both)
  }

  async pick<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T | undefined> {
    const rows = quickItems(items);
    const chosen = await vscode.window.showQuickPick(rows.map((r) => r.item), options);
    return rows.find((r) => r.item === chosen)?.source;
  }

  async pickMany<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T[] | undefined> {
    const rows = quickItems(items);
    const chosen = await vscode.window.showQuickPick(rows.map((r) => r.item), { ...options, canPickMany: true });
    return chosen && rows.filter((r) => chosen.includes(r.item)).map((r) => r.source);
  }

  quickPick<T extends PickItem>(options: QuickPickOptions): QuickPick<T> {
    const qp = vscode.window.createQuickPick<vscode.QuickPickItem>();
    if (options.title !== undefined) qp.title = options.title;
    if (options.placeHolder !== undefined) qp.placeholder = options.placeHolder;
    if (options.many !== undefined) qp.canSelectMany = options.many;
    if (options.matchOnDescription !== undefined) qp.matchOnDescription = options.matchOnDescription;
    if (options.matchOnDetail !== undefined) qp.matchOnDetail = options.matchOnDetail;
    // (settable, though not in the 1.90 types)
    if (options.sortByLabel !== undefined) (qp as vscode.QuickPick<vscode.QuickPickItem> & { sortByLabel: boolean }).sortByLabel = options.sortByLabel;
    return new VsCodeQuickPick<T>(qp);
  }

  input(options?: InputOptions): Promise<string | undefined> {
    return Promise.resolve(vscode.window.showInputBox(options));
  }

  async choose(options: ChooseOptions): Promise<string[] | undefined> {
    // (on the remote: the open folder's scheme and authority carry the dialog there, as a remote default does)
    const base = vscode.workspace.workspaceFolders?.[0];
    const defaultUri = !options.defaultPath
      ? undefined
      : options.onRemote
        ? base?.uri.with({ path: options.defaultPath })
        : vscode.Uri.file(options.defaultPath);
    const picked = await vscode.window.showOpenDialog({
      canSelectFolders: options.kind === "folder",
      canSelectFiles: options.kind === "file",
      canSelectMany: options.many ?? false,
      ...(defaultUri ? { defaultUri } : {}),
      ...(options.openLabel ? { openLabel: options.openLabel } : {}),
      ...(options.title ? { title: options.title } : {}),
      ...(options.filters ? { filters: options.filters } : {}),
    });
    if (!picked?.length) return undefined;
    const kept = options.localOnly ? picked.filter((u) => u.scheme === "file") : picked;
    if (!kept.length) return undefined;
    return kept.map((u) => (options.onRemote ? u.path : u.fsPath));
  }

  progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R> {
    const location = options.where === "window" ? vscode.ProgressLocation.Window : vscode.ProgressLocation.Notification;
    return Promise.resolve(vscode.window.withProgress({ location, title: options.title }, task));
  }

  statusMessage(text: string, ms: number): void {
    vscode.window.setStatusBarMessage(text, ms);
  }

  readonly settings: HostSettings = {
    get: <T>(key: string, fallback: T) => vscode.workspace.getConfiguration("talpyDen").get<T>(key, fallback),
    update: async (key, value, scope = "global") => {
      const target = scope === "workspace" ? vscode.ConfigurationTarget.Workspace : scope === "workspaceFolder" ? vscode.ConfigurationTarget.WorkspaceFolder : vscode.ConfigurationTarget.Global;
      await vscode.workspace.getConfiguration("talpyDen").update(key, value, target);
    },
    updateOther: async (section, key, value) => {
      await vscode.workspace.getConfiguration(section).update(key, value, vscode.ConfigurationTarget.Global);
    },
    watchOther: (keys) => (listener) =>
      vscode.workspace.onDidChangeConfiguration((e) => {
        const touched = keys.filter((k) => e.affectsConfiguration(k));
        if (touched.length) listener(touched);
      }),
    inspect: (key) => {
      const found = vscode.workspace.getConfiguration("talpyDen").inspect(key);
      return found && { global: found.globalValue, workspace: found.workspaceValue, workspaceFolder: found.workspaceFolderValue };
    },
    other: <T>(section: string, key: string, fallback: T) => vscode.workspace.getConfiguration(section).get<T>(key, fallback),
    onDidChange: this.settingsChanged.event,
  };

  readonly focus = {
    get focused() { return vscode.window.state.focused; },
    onDidChange: this.focusChanged.event,
    get inUse() { return inUse(vscode.window.state); },
    onDidChangeUse: this.useChanged.event,
  };

  readonly clipboard = {
    read: async () => vscode.env.clipboard.readText(),
    write: async (text: string) => vscode.env.clipboard.writeText(text),
  };

  async openExternal(url: string): Promise<boolean> {
    return vscode.env.openExternal(vscode.Uri.parse(url));
  }

  async openFile(path: string): Promise<void> {
    await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(path));
  }

  async revealFile(path: string): Promise<void> {
    await vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(path));
  }

  async openSettings(query: string): Promise<void> {
    await vscode.commands.executeCommand("workbench.action.openSettings", query);
  }

  async showView(): Promise<void> {
    await vscode.commands.executeCommand("talpyDen.view.focus");
  }

  async reloadWindow(): Promise<void> {
    await vscode.commands.executeCommand("workbench.action.reloadWindow");
  }

  // (a folder of the window's host: its URI's path there; this computer's: a file: URI's fsPath)
  workspaceFolders(): readonly WindowFolder[] {
    return (vscode.workspace.workspaceFolders ?? []).map((f) => {
      const remote = f.uri.scheme !== "file";
      return { name: f.name, path: remote ? f.uri.path : f.uri.fsPath, remote, uri: f.uri.toString() };
    });
  }

  readonly onDidChangeWorkspaceFolders = this.foldersChanged.event;

  readonly state = {
    get: <T>(key: string, fallback: T): T => (this.kept ? this.kept.get<T>(key, fallback) : fallback),
    update: async (key: string, value: unknown): Promise<void> => {
      await this.kept?.update(key, value);
    },
  };

  get environment(): { readonly remoteName?: string; readonly remoteAuthority?: string; readonly web: boolean; readonly sessionId: string } {
    return {
      remoteName: vscode.env.remoteName,
      web: vscode.env.uiKind === vscode.UIKind.Web,
      sessionId: vscode.env.sessionId ?? "",
      // (looked up only when asked: it walks the open folders and editors)
      get remoteAuthority() { return currentRemoteAuthority(vscode); },
    };
  }

  readonly log = {
    info: (m: string) => this.output.info(m),
    warn: (m: string) => this.output.warn(m),
    error: (m: string) => this.output.error(m),
  };
}

// A VS Code QuickPick showing a caller's items and buttons: each one set turns into VS Code's, and what VS Code
// hands back (the selection, the active item, a button pressed) turns back into the caller's own, also one of
// an earlier set (as the caller's own objects came back when they went to VS Code themselves)
class VsCodeQuickPick<T extends PickItem> implements QuickPick<T> {
  private shownItems: readonly T[] = [];
  private rowOf = new Map<T, vscode.QuickPickItem>(); // (the rows now shown)
  private sourceOf = new WeakMap<vscode.QuickPickItem, T>(); // (every row shown)
  private shownButtons: readonly PickButton[] = [];
  private buttonOf = new Map<PickButton, vscode.QuickInputButton>(); // (the same VS Code button for a caller's, each time)
  private buttonSource = new Map<vscode.QuickInputButton, PickButton>();

  constructor(private readonly qp: vscode.QuickPick<vscode.QuickPickItem>) {}

  get items(): readonly T[] {
    return this.shownItems;
  }
  set items(items: readonly T[]) {
    const rows = quickItems(items);
    this.shownItems = rows.map((r) => r.source);
    this.rowOf = new Map(rows.map((r) => [r.source, r.item]));
    for (const r of rows) this.sourceOf.set(r.item, r.source);
    this.qp.items = rows.map((r) => r.item);
  }
  get activeItems(): readonly T[] {
    return this.sources(this.qp.activeItems);
  }
  set activeItems(items: readonly T[]) {
    this.qp.activeItems = this.shown(items);
  }
  get selectedItems(): readonly T[] {
    return this.sources(this.qp.selectedItems);
  }
  set selectedItems(items: readonly T[]) {
    this.qp.selectedItems = this.shown(items);
  }
  get buttons(): readonly PickButton[] {
    return this.shownButtons;
  }
  set buttons(buttons: readonly PickButton[]) {
    this.shownButtons = buttons.slice();
    this.qp.buttons = buttons.map((source) => {
      let button = this.buttonOf.get(source);
      if (!button) {
        button = { iconPath: new vscode.ThemeIcon(source.icon), tooltip: source.tooltip };
        this.buttonOf.set(source, button);
        this.buttonSource.set(button, source);
      }
      return button;
    });
  }
  get busy(): boolean {
    return this.qp.busy;
  }
  set busy(busy: boolean) {
    this.qp.busy = busy;
  }
  get keepScrollPosition(): boolean {
    return !!this.qp.keepScrollPosition;
  }
  set keepScrollPosition(keep: boolean) {
    this.qp.keepScrollPosition = keep;
  }

  readonly onDidChangeValue: Event<string> = (listener) => this.qp.onDidChangeValue(listener);
  readonly onDidChangeSelection: Event<readonly T[]> = (listener) => this.qp.onDidChangeSelection((items) => listener(this.sources(items)));
  readonly onDidTriggerButton: Event<PickButton> = (listener) =>
    this.qp.onDidTriggerButton((button) => {
      const source = this.buttonSource.get(button);
      if (source) listener(source);
    });
  readonly onDidAccept: Event<void> = (listener) => this.qp.onDidAccept(() => listener(undefined));
  readonly onDidHide: Event<void> = (listener) => this.qp.onDidHide(() => listener(undefined));

  show(): void {
    this.qp.show();
  }
  hide(): void {
    this.qp.hide();
  }
  dispose(): void {
    this.qp.dispose();
  }

  // VS Code's rows back to the caller's items, and the caller's (of those now shown) to VS Code's
  private sources(items: readonly vscode.QuickPickItem[]): T[] {
    return items.flatMap((item) => {
      const source = this.sourceOf.get(item);
      return source ? [source] : [];
    });
  }
  private shown(items: readonly T[]): vscode.QuickPickItem[] {
    return items.flatMap((source) => {
      const item = this.rowOf.get(source);
      return item ? [item] : [];
    });
  }
}

// The rows VS Code shows for a caller's items, each with the item it stands for
function quickItems<T extends PickItem>(items: readonly T[]): { item: vscode.QuickPickItem; source: T }[] {
  return items.map((source) => {
    const { label, description, detail, picked, alwaysShow } = source;
    const item: vscode.QuickPickItem = { label, description, detail, picked, alwaysShow };
    if (source.separator) item.kind = vscode.QuickPickItemKind.Separator;
    if (source.icon) item.iconPath = new vscode.ThemeIcon(source.icon);
    return { item, source };
  });
}
