// A HostServices a core test scripts: what it was asked is in `recorded`, what it answers in `answer`
// (none: undefined, as when Escape is pressed), its settings in `values` and `others`.

import { Emitter } from "../src/events";
import type {
  ChooseOptions, HostServices, HostSettings, InputOptions, MessageLevel, MessageOptions, PickButton, PickItem, PickOptions, QuickPick,
  QuickPickOptions, SettingScope, WindowFolder,
} from "../src/host";

// A pick list a test drives as a user would: types in it, presses a title bar button, ticks items, accepts or
// closes it; what the caller set on it stays readable (items, buttons, busy…)
export class FakeQuickPick<T extends PickItem> implements QuickPick<T> {
  items: readonly T[] = [];
  activeItems: readonly T[] = [];
  selectedItems: readonly T[] = [];
  buttons: readonly PickButton[] = [];
  busy = false;
  keepScrollPosition = false;
  shown = false;
  disposed = false;
  private valueChanged = new Emitter<string>();
  private selectionChanged = new Emitter<readonly T[]>();
  private buttonPressed = new Emitter<PickButton>();
  private accepted = new Emitter<void>();
  private hidden = new Emitter<void>();
  readonly onDidChangeValue = this.valueChanged.event;
  readonly onDidChangeSelection = this.selectionChanged.event;
  readonly onDidTriggerButton = this.buttonPressed.event;
  readonly onDidAccept = this.accepted.event;
  readonly onDidHide = this.hidden.event;

  constructor(readonly options: QuickPickOptions) {}

  show(): void {
    this.shown = true;
  }

  hide(): void {
    if (!this.shown) return;
    this.shown = false;
    this.hidden.fire(undefined);
  }

  dispose(): void {
    this.hide();
    this.disposed = true;
  }

  type(value: string): void {
    this.valueChanged.fire(value);
  }

  press(button: PickButton): void {
    this.buttonPressed.fire(button);
  }

  select(items: readonly T[]): void {
    this.selectedItems = items;
    this.selectionChanged.fire(items);
  }

  // Enter, on item when given (picked: the selection)
  accept(item?: T): void {
    if (item) this.selectedItems = [item];
    this.accepted.fire(undefined);
  }
}

export class FakeHost implements HostServices {
  recorded = {
    messages: [] as { level: MessageLevel; text: string; options?: MessageOptions; actions: string[] }[],
    picks: [] as { items: readonly PickItem[]; options?: PickOptions }[],
    inputs: [] as InputOptions[],
    choices: [] as ChooseOptions[],
    progress: [] as { where: "window" | "notification"; title: string }[],
    quickPicks: [] as FakeQuickPick<PickItem>[],
    external: [] as string[],
    files: [] as string[],
    revealed: [] as string[],
    settingsOpened: [] as string[],
    views: 0,
    reloads: 0,
    updates: [] as { section: string; key: string; value: unknown; scope: SettingScope }[], // section "talpyDen" or another
    status: [] as string[],
    logs: [] as string[],
  };

  answer: {
    // the action to click: its index among the buttons, or its title (the first of that title)
    message?: (text: string, actions: string[]) => string | number | undefined;
    pick?: (items: readonly PickItem[]) => PickItem | undefined;
    pickMany?: (items: readonly PickItem[]) => PickItem[] | undefined;
    input?: (o: InputOptions) => string | undefined;
    choose?: (o: ChooseOptions) => string[] | undefined;
  } = {};

  values = new Map<string, unknown>(); // talpyDen.<key> -> value
  others = new Map<string, unknown>(); // "section.key" -> value
  clip = "";
  folders: WindowFolder[] = [];
  kept = new Map<string, unknown>(); // what state keeps, by key
  environment: { remoteName?: string; remoteAuthority?: string; web: boolean; sessionId: string } = { web: false, sessionId: "fake-window" };

  private settingsChanged = new Emitter<string[]>();
  private focusChanged = new Emitter<boolean>();
  private useChanged = new Emitter<boolean>();
  private foldersChanged = new Emitter<void>();
  private watchers: { keys: readonly string[]; changed: Emitter<string[]> }[] = [];
  private isFocused = false;
  private isActive: boolean | undefined; // set: the window is in use whatever its focus (VS Code's `active`)

  // Sets a talpyDen setting, as the user would, and tells the listeners
  set(key: string, value: unknown): void {
    this.values.set(key, value);
    this.settingsChanged.fire([key]);
  }

  // Sets another section's setting ("editor.fontFamily"), as the user would, and tells its watchers
  setOther(fullKey: string, value: unknown): void {
    this.others.set(fullKey, value);
    for (const w of this.watchers) {
      const touched = w.keys.filter((k) => k === fullKey);
      if (touched.length) w.changed.fire(touched);
    }
  }

  // (the focus told before the use, as VS Code's host tells them: host.ts)
  setFocused(focused: boolean): void {
    this.isFocused = focused;
    this.focusChanged.fire(focused);
    this.useChanged.fire(this.isActive ?? focused);
  }

  // The window is in use or not, as VS Code's `active` says (the focus unchanged)
  setActive(active: boolean): void {
    this.isActive = active;
    this.useChanged.fire(active);
  }

  // Changes the open folders and tells the listeners
  setFolders(folders: WindowFolder[]): void {
    this.folders = folders;
    this.foldersChanged.fire(undefined);
  }

  async message<A extends string | { title: string }>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined> {
    const titles = actions.map((a) => (typeof a === "string" ? a : a.title));
    this.recorded.messages.push({ level, text, options, actions: titles });
    const chosen = this.answer.message?.(text, titles);
    return (typeof chosen === "number" ? actions[chosen] : actions.find((_, i) => titles[i] === chosen)) as A | undefined;
  }

  async pick<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T | undefined> {
    this.recorded.picks.push({ items, options });
    return this.answer.pick?.(items) as T | undefined;
  }

  async pickMany<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T[] | undefined> {
    this.recorded.picks.push({ items, options });
    return this.answer.pickMany?.(items) as T[] | undefined;
  }

  quickPick<T extends PickItem>(options: QuickPickOptions): QuickPick<T> {
    const qp = new FakeQuickPick<T>(options);
    this.recorded.quickPicks.push(qp as unknown as FakeQuickPick<PickItem>);
    return qp;
  }

  async input(options: InputOptions = {}): Promise<string | undefined> {
    this.recorded.inputs.push(options);
    return this.answer.input?.(options);
  }

  async choose(options: ChooseOptions): Promise<string[] | undefined> {
    this.recorded.choices.push(options);
    return this.answer.choose?.(options);
  }

  progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R> {
    this.recorded.progress.push({ where: options.where, title: options.title });
    return task();
  }

  statusMessage(text: string, _ms: number): void {
    this.recorded.status.push(text);
  }

  readonly settings: HostSettings = {
    get: <T>(key: string, fallback: T) => (this.values.has(key) ? (this.values.get(key) as T) : fallback),
    update: async (key, value, scope = "global") => {
      this.recorded.updates.push({ section: "talpyDen", key, value, scope });
      this.set(key, value);
    },
    updateOther: async (section, key, value) => {
      this.recorded.updates.push({ section, key, value, scope: "global" });
      this.setOther(`${section}.${key}`, value);
    },
    watchOther: (keys) => {
      const watcher = { keys, changed: new Emitter<string[]>() };
      this.watchers.push(watcher);
      return watcher.changed.event;
    },
    inspect: (key) => (this.values.has(key) ? { global: this.values.get(key) } : undefined),
    other: <T>(section: string, key: string, fallback: T) => (this.others.has(`${section}.${key}`) ? (this.others.get(`${section}.${key}`) as T) : fallback),
    onDidChange: this.settingsChanged.event,
  };

  readonly focus = ((self: FakeHost) => ({
    get focused() { return self.isFocused; },
    onDidChange: self.focusChanged.event,
    get inUse() { return self.isActive ?? self.isFocused; },
    onDidChangeUse: self.useChanged.event,
  }))(this);

  readonly clipboard = {
    read: async () => this.clip,
    write: async (text: string) => { this.clip = text; },
  };

  async openExternal(url: string): Promise<boolean> {
    this.recorded.external.push(url);
    return true;
  }

  async openFile(path: string): Promise<void> {
    this.recorded.files.push(path);
  }

  async revealFile(path: string): Promise<void> {
    this.recorded.revealed.push(path);
  }

  async openSettings(query: string): Promise<void> {
    this.recorded.settingsOpened.push(query);
  }

  async showView(): Promise<void> {
    this.recorded.views++;
  }

  async reloadWindow(): Promise<void> {
    this.recorded.reloads++;
  }

  workspaceFolders(): readonly WindowFolder[] {
    return this.folders;
  }

  readonly onDidChangeWorkspaceFolders = this.foldersChanged.event;

  readonly state = {
    get: <T>(key: string, fallback: T) => (this.kept.has(key) ? (this.kept.get(key) as T) : fallback),
    update: async (key: string, value: unknown) => void this.kept.set(key, value),
  };

  readonly log = {
    info: (m: string) => void this.recorded.logs.push(`info ${m}`),
    warn: (m: string) => void this.recorded.logs.push(`warn ${m}`),
    error: (m: string) => void this.recorded.logs.push(`error ${m}`),
  };
}
