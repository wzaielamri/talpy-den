import * as vscode from "vscode";
import { Emitter } from "../../core/src/events";
import type {
  ChooseOptions, HostServices, HostSettings, InputOptions, MessageLevel, MessageOptions, PickItem, PickOptions,
} from "../../core/src/host";
import { currentRemoteAuthority } from "./remoteHost";

// HostServices over the VS Code API: the one place paths and vscode.Uri turn into each other
export class VsCodeHost implements HostServices {
  private settingsChanged = new Emitter<string[]>();
  private focusChanged = new Emitter<boolean>();
  private foldersChanged = new Emitter<void>();
  private subscriptions: vscode.Disposable[];

  // settingKeys: the talpyDen.* settings the extension declares (without the prefix). VS Code says only whether
  // a section changed, so these are asked one by one which of them did
  constructor(private readonly output: vscode.LogOutputChannel, private readonly settingKeys: readonly string[]) {
    this.subscriptions = [
      vscode.workspace.onDidChangeConfiguration((e) => {
        const keys = this.settingKeys.filter((k) => e.affectsConfiguration(`talpyDen.${k}`));
        if (keys.length) this.settingsChanged.fire(keys);
      }),
      vscode.window.onDidChangeWindowState((s) => this.focusChanged.fire(s.focused)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.foldersChanged.fire(undefined)),
    ];
  }

  dispose(): void {
    for (const s of this.subscriptions) s.dispose();
    this.settingsChanged.dispose();
    this.focusChanged.dispose();
    this.foldersChanged.dispose();
  }

  async message<A extends string>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined> {
    const show = level === "error" ? vscode.window.showErrorMessage : level === "warning" ? vscode.window.showWarningMessage : vscode.window.showInformationMessage;
    const opts: vscode.MessageOptions = {};
    if (options?.modal !== undefined) opts.modal = options.modal;
    if (options?.detail !== undefined) opts.detail = options.detail;
    return (await show(text, opts, ...actions)) as A | undefined;
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

  input(options?: InputOptions): Promise<string | undefined> {
    return Promise.resolve(vscode.window.showInputBox(options)) as Promise<string | undefined>;
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

  setContext(key: string, value: unknown): void {
    void vscode.commands.executeCommand("setContext", key, value);
  }

  workspaceFolders(): readonly { name: string; path: string }[] {
    return (vscode.workspace.workspaceFolders ?? []).map((f) => ({ name: f.name, path: f.uri.fsPath }));
  }

  readonly onDidChangeWorkspaceFolders = this.foldersChanged.event;

  get environment(): { readonly remoteName?: string; readonly remoteAuthority?: string; readonly web: boolean } {
    return {
      remoteName: vscode.env.remoteName,
      web: vscode.env.uiKind === vscode.UIKind.Web,
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
