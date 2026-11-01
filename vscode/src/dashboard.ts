// What the view and the status bar show: this computer's status and the SSH
// hosts', polled with the widget's backend. This computer is checked the
// moment a chat changes (LiveWatch: its session file), and in between every
// pollInterval while the view is open and a chat works (every 10 s while
// it's hidden: the status bar and notifications still need it); with live
// mode, whose hook hands on each step as it happens, every 6 s at most
// often; while no chat works, every idlePollInterval (20 s). Without the
// watching: every pollInterval (10 s hidden). Hosts every remotePollSeconds.

import * as vscode from "vscode";
import { AwayWatch } from "./away";
import type { Backend } from "./backend";
import { claudePanelAvailable, localPanelProfileKey } from "./claudePanel";
import { cacheDir, extraConfigDirs, settings, statusArgs, configDirArgs, viewSettings } from "./config";
import { LiveWatch } from "./live";
import type { Notifier } from "./notify";
import { currentRemoteAuthority, hostFromAuthority, portFromAuthority, sshPort } from "./remoteHost";
import { demoPerms, demoProjects, demoState, demoWeek } from "./shared/demo";
import { allGroups, chatsNeedingYou, findProjectChat, keptChat, limitReset, liveFromRows, queuedWhat, recentRef, shareUsage, toLocalClock, trackKey, withLive, type ChatSpot, type RecentMore } from "./shared/model";
import { chatRef } from "./notify";
import type { ChatRef, ClaudeCodeInfo, DigestCard, Group, HostState, LiveView, PermsData, PetEventKind, ProjectsData, QueuedTask, Status, ViewState, WeekRecap, WeekSpan } from "./shared/types";
import type { WeekRuleAsk } from "./shared/week";
import { mergeChanges, TransitionTracker, type Changes, type PetEvent } from "./transitions";

const HIDDEN_POLL_MS = 10000;
const LIVE_WORKING_MS = 6000; // watched, a chat works, live mode (or the window isn't focused)
const VIEW_ID = "talpyDen.view";
const DIGEST_SHOWN_MS = 60 * 60000; // the away card stays this long, unless closed
const DEMO_STEP_MS = 8000;
const MESSAGE_MS = { error: 10000, info: 12000 };

export class Dashboard implements vscode.Disposable {
  private status: Status | null = null;
  private errorText = "";
  private hosts = new Map<string, HostState>();
  private actionError = "";
  private actionInfo = "";
  private messageTimers: { error?: NodeJS.Timeout; info?: NodeJS.Timeout } = {};
  private visible = false;
  private localBusy = false;
  private hostBusy = new Set<string>();
  private hostAgain = new Set<string>(); // an action there while its check ran: checked again after it
  private hostAnswered = new Map<string, number>(); // host -> when its last check that answered started
  private localTimer?: NodeJS.Timeout;
  private hostTimer?: NodeJS.Timeout;
  private retryTimer?: NodeJS.Timeout; // Python didn't work: try again (its own timer: polls mustn't cancel it)
  private demoTimer?: NodeJS.Timeout;
  private demoPhase: number | null = null;
  private projectsData: ProjectsData | null = null; // the Projects tab's, as last read
  private moreRecent = new Map<string, RecentMore>(); // "host|account id": its recent chats as a bigger check listed them
  private tracker = new TransitionTracker();
  private disposables: vscode.Disposable[] = [];
  private disposed = false;
  private windowHost: string | undefined;
  private claudeCodeAvailable = false;
  private claudeCodeCheckedAt = 0;
  // Chats that finished a turn while you weren't looking (trackKey -> when)
  private unseen = new Map<string, number>();
  // Chats that finished a turn you haven't looked at yet (the focus view's
  // Finished lines, as in the widget): trackKey -> when, until you open that
  // chat (its tab, or the chat itself). Unlike unseen, showing the view leaves them.
  private finishedUnopened = new Map<string, number>();
  lookingAt: (id: string) => boolean = () => false; // (a chat's tab shows it: ChatPanes)
  private away: AwayWatch;
  private digest: DigestCard | null = null;
  private readonly onStateEmitter = new vscode.EventEmitter<ViewState>();
  private readonly onUnseenEmitter = new vscode.EventEmitter<void>();
  // (what finished unseen changed: the Activity Bar badge's count)
  readonly onUnseen = this.onUnseenEmitter.event;
  private readonly onPetEventEmitter = new vscode.EventEmitter<PetEvent>();
  private readonly onLiveEmitter = new vscode.EventEmitter<{ live: Record<string, LiveView>; changed: string[] }>();
  readonly onState = this.onStateEmitter.event;
  readonly onPetEvent = this.onPetEventEmitter.event;
  // What this computer's running chats do now, between checks (live mode);
  // changed: the session ids whose view is new
  readonly onLive = this.onLiveEmitter.event;
  private live: LiveWatch;
  private liveViews: Record<string, LiveView> = {};
  private again = false; // a chat changed while a check ran: check again once it's done

  constructor(
    private backend: Backend,
    private notifier: Notifier,
    private log: vscode.LogOutputChannel,
  ) {
    this.windowHost = this.windowHostNow();
    this.polledWith = this.pollSettings();
    this.away = new AwayWatch((now, lastUse) => this.cameBack(now, lastUse));
    this.live = new LiveWatch(
      ({ urgent, views }) => {
        if (views.length) this.noteLive(views);
        // (a window nobody looks at that doesn't notify: its next check is soon enough)
        if (urgent && (this.visible || vscode.window.state.focused || this.notifier.isLeader()))
          void this.refresh(true).then(() => this.scheduleLocal()); // (the next check counts from this one)
      },
      () => extraConfigDirs(),
      cacheDir(),
    );
    this.disposables.push(
      this.away,
      this.live,
      this.onLiveEmitter,
      // looking at the view: what finished is seen
      vscode.window.onDidChangeWindowState((s) => {
        if (s.focused && this.visible) this.clearUnseen();
      }),
      this.onStateEmitter,
      this.onUnseenEmitter,
      this.onPetEventEmitter,
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (!e.affectsConfiguration("talpyDen")) return;
        if (e.affectsConfiguration("talpyDen.recapHistory")) void this.setRecapHistory(settings.recapHistory());
        this.settingsChanged();
      }),
      // the Claude Code extension installed, removed or (in a new folder) enabled
      vscode.extensions.onDidChange(() => void this.checkClaudeCode()),
      vscode.workspace.onDidChangeWorkspaceFolders(() => {
        void this.checkClaudeCode();
        const host = this.windowHostNow();
        if (host !== this.windowHost) {
          this.windowHost = host;
          this.polledWith = { ...this.polledWith, hosts: this.pollSettings().hosts };
          this.syncHosts();
          this.scheduleHosts(0);
        }
      }),
    );
  }

  // The host this window is connected to (Remote-SSH), if any
  get currentHost(): string | undefined {
    return this.windowHost;
  }

  // ... and whether its checks would reach it: a window that got there on a
  // port ssh <host> doesn't use (user@host:2222 typed into Remote-SSH) would
  // check another sshd, so its host isn't added by itself; that's said once
  private windowHostOff = false;
  private windowHostNow(): string | undefined {
    const authority = currentRemoteAuthority(vscode);
    const host = hostFromAuthority(authority);
    const port = portFromAuthority(authority);
    const sshTo = host && port ? sshPort(host) : undefined;
    const off = !!host && !!port && sshTo !== port;
    if (off && (!this.windowHostOff || host !== this.windowHost)) {
      const why = `this window reached ${host} on port ${port}, and ssh ${host} goes to ${sshTo ? `port ${sshTo}` : "another port"}, so Talpy Den doesn't list its chats. A Host entry for it with Port ${port} in ~/.ssh/config lets it.`;
      this.log.warn(why);
      void vscode.window.showInformationMessage(`Talpy Den: ${why}`);
    }
    this.windowHostOff = off;
    return host;
  }

  get demo(): boolean {
    return this.demoPhase !== null;
  }

  async start(): Promise<void> {
    if (this.disposed) return;
    void this.checkClaudeCode();
    void this.syncRecapHistory();
    const problem = await this.backend.checkPython();
    if (this.disposed) return;
    if (problem) {
      this.errorText = problem;
      this.log.error(problem);
      this.emit();
      // try again later: the setting may get fixed
      clearTimeout(this.retryTimer);
      this.retryTimer = setTimeout(() => void this.start(), 30000);
      return;
    }
    this.syncHosts();
    this.live.start();
    this.scheduleLocal(0);
    this.scheduleHosts(0);
  }

  // Whether chats are followed as they change (their session files): the checks in between are rarer then
  get watching(): boolean {
    return this.live.healthy && !this.demo;
  }

  // With live mode's hook on, each step comes as it happens
  get liveHook(): boolean {
    return this.watching && !!this.status?.liveHook;
  }

  private noteLive(views: LiveView[]): void {
    const next = withLive(this.liveViews, views);
    if (!next || this.demo || this.disposed) return;
    this.liveViews = next;
    this.onLiveEmitter.fire({ live: next, changed: views.map((v) => v.sessionId ?? "") });
  }

  // How long until the next check of this computer (see the top)
  private paceMs(): number {
    const poll = settings.pollInterval();
    if (!this.watching) return this.visible ? poll : Math.max(HIDDEN_POLL_MS, poll);
    // (with live mode, a working chat's steps come as they happen: pollInterval doesn't count then)
    if (!this.status || !this.status.counts.working) return this.liveHook ? settings.idlePollInterval() : Math.max(poll, settings.idlePollInterval());
    if (this.liveHook) return this.visible ? LIVE_WORKING_MS : HIDDEN_POLL_MS;
    if (!this.visible) return Math.max(HIDDEN_POLL_MS, poll);
    if (!vscode.window.state.focused) return Math.max(poll, LIVE_WORKING_MS);
    return poll;
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.localTimer);
    clearTimeout(this.hostTimer);
    clearTimeout(this.retryTimer);
    clearInterval(this.demoTimer);
    clearTimeout(this.messageTimers.error);
    clearTimeout(this.messageTimers.info);
    for (const d of this.disposables) d.dispose();
  }

  // Whether the Claude Code extension can open chats in this window (its
  // commands are registered wherever it runs)
  private async checkClaudeCode(): Promise<void> {
    this.claudeCodeCheckedAt = Date.now();
    const available = await claudePanelAvailable();
    if (available === this.claudeCodeAvailable || this.disposed) return;
    this.claudeCodeAvailable = available;
    this.emit();
  }

  // The Claude Code extension here, and the account it runs this computer's chats on
  claudeCodeInfo(): ClaudeCodeInfo {
    return { available: this.claudeCodeAvailable, profileKey: this.claudeCodeAvailable ? localPanelProfileKey() : null };
  }

  setVisible(visible: boolean): void {
    if (visible === this.visible) return;
    this.visible = visible;
    // Just opened: show fresh numbers now, then poll at the faster pace
    if (visible) this.scheduleLocal(0);
    if (visible && vscode.window.state.focused) this.clearUnseen();
  }

  isVisible(): boolean {
    return this.visible;
  }

  // What the checks run with: this computer's (Python, its config dirs, the
  // status's arguments, the usage cap), the hosts' (Python, the arguments,
  // which hosts), and their pace. A setting that changes none of them (the
  // chat tab's text size, a sound, …) only redraws.
  private pollSettings() {
    const status = statusArgs();
    return {
      local: JSON.stringify([settings.python(), configDirArgs(), status, settings.usageCap()]),
      hosts: JSON.stringify([settings.python(), status, this.shownHosts()]),
      localPace: JSON.stringify([settings.pollInterval(), settings.idlePollInterval()]),
      hostPace: String(settings.remotePollSeconds()),
    };
  }

  private polledWith: ReturnType<Dashboard["pollSettings"]>; // (what the last checks ran with)

  private settingsChanged(): void {
    const now = this.pollSettings();
    const was = this.polledWith;
    this.polledWith = now;
    this.syncHosts(); // (also redraws: the view's settings, the status bar's)
    if (now.local !== was.local) this.scheduleLocal(0);
    else if (now.localPace !== was.localPace) this.scheduleLocal(); // (the next check at the new pace)
    if (now.hosts !== was.hosts) this.scheduleHosts(0);
    else if (now.hostPace !== was.hostPace) this.scheduleHosts();
  }

  // The hosts to check: the window's own host first, then the picked ones
  // The SSH hosts shown whose last check answered (the Recap and the Monday
  // recap count these: one out of reach would hold them up)
  answeringHosts(): string[] {
    return this.shownHosts().filter((name) => {
      const h = this.hosts.get(name);
      return !!h && h.ok && !!h.result;
    });
  }

  shownHosts(): string[] {
    const list = settings.sshHosts();
    if (this.windowHost && !this.windowHostOff && settings.includeCurrentRemote() && !list.includes(this.windowHost)) list.unshift(this.windowHost);
    return list;
  }

  private syncHosts(): void {
    const shown = this.shownHosts();
    for (const name of [...this.hosts.keys()]) {
      if (!shown.includes(name)) {
        this.hosts.delete(name);
        this.tracker.forget("ssh:" + name); // a host that comes back starts over
      }
    }
    for (const name of shown) {
      const h = this.hosts.get(name);
      if (h) h.current = name === this.windowHost;
      else
        this.hosts.set(name, { name, loading: false, ok: false, error: "", result: null, updatedAt: 0, current: name === this.windowHost });
    }
    this.emit();
  }

  private scheduleLocal(delay?: number): void {
    if (this.disposed) return;
    clearTimeout(this.localTimer);
    const wait = delay ?? this.paceMs();
    this.localTimer = setTimeout(() => void this.refresh().finally(() => this.scheduleLocal()), wait);
  }

  private scheduleHosts(delay?: number): void {
    if (this.disposed) return;
    clearTimeout(this.hostTimer);
    const wait = delay ?? settings.remotePollSeconds() * 1000;
    this.hostTimer = setTimeout(() => {
      for (const host of this.shownHosts()) void this.pollHost(host);
      this.scheduleHosts();
    }, wait);
  }

  // This computer's check only: the usage cap, and (in the window that
  // notifies) looking after the chats that keep going
  private localArgs(): string[] {
    const cap = settings.usageCap();
    return [...(cap > 0 ? ["--usage-cap", String(Math.round(cap))] : []), ...(this.notifier.isLeader() ? ["--keep-going"] : [])];
  }

  // Check this computer now (a check still running isn't doubled; changed:
  // a chat changed, so one that's running then runs again once it's done)
  async refresh(changed = false): Promise<void> {
    if (this.localBusy && changed) this.again = true;
    if (this.localBusy || this.demo || this.disposed) return;
    // Claude Code starts alongside this extension and can register its commands
    // after the first check, with no event for it: look again until it's there
    if (!this.claudeCodeAvailable && Date.now() - this.claudeCodeCheckedAt >= HIDDEN_POLL_MS) void this.checkClaudeCode();
    this.localBusy = true;
    try {
      const { status, error } = await this.backend.status([...configDirArgs(), ...statusArgs(), ...this.localArgs()]);
      if (status) {
        this.errorText = status.errors.length ? status.errors.join("\n") : "";
        const opts = { ...this.notifyOptions(), kept: (chat: string) => !!keptChat(status, chat) };
        const changes = mergeChanges(
          mergeChanges(
            this.tracker.track("", status.groups, status.generatedAt, undefined, opts),
            this.tracker.limitResets("", status.groups, undefined, opts),
          ),
          this.tracker.overlaps("", status.groups, undefined, opts),
        );
        const resets = this.tracker.resets("", status.groups);
        this.status = status;
        this.liveViews = liveFromRows(status.groups, this.liveViews);
        this.react(changes, resets);
        this.startDueTasks(status);
      } else {
        this.errorText = error ?? "Status unavailable";
        this.log.warn(this.errorText);
      }
    } finally {
      this.localBusy = false;
    }
    this.emit();
    if (this.again) {
      this.again = false;
      void this.refresh();
    }
  }

  refreshAll(): void {
    void this.refresh();
    for (const host of this.shownHosts()) void this.pollHost(host);
  }

  // Refresh (its button, its command): the plan usage too, of every account
  // whose numbers are over a minute old; the status says a fetch is on its way
  async fetchUsage(): Promise<void> {
    if (this.demo || this.disposed) return;
    await this.backend.fetchUsage(configDirArgs());
    void this.refresh();
  }

  // Whether a check of host that started at since or later has answered:
  // what runs there since then is in its rows (Terminals)
  hostCheckedSince(host: string, since: number): boolean {
    const asked = this.hostAnswered.get(host);
    return asked !== undefined && asked >= since;
  }

  // (changed: something was done there while a check ran, which may have
  // read it before: it checks again once that's done)
  async pollHost(host: string, changed = false): Promise<void> {
    if (this.hostBusy.has(host) && changed) this.hostAgain.add(host);
    if (this.hostBusy.has(host) || this.demo || this.disposed) return;
    const h = this.hosts.get(host);
    if (!h) return;
    this.hostBusy.add(host);
    h.loading = true;
    this.emit();
    const asked = Date.now();
    try {
      const answer = await this.backend.hostStatus(host, statusArgs());
      const now = this.hosts.get(host);
      if (!now) return; // unpicked while it was being checked
      if (answer.ok && answer.result) {
        // on this computer's clock: the host's may be off
        const result = toLocalClock(answer.result, Date.now() - (answer.result.generatedAt || Date.now()));
        const opts = this.notifyOptions();
        const changes = mergeChanges(
          mergeChanges(
            this.tracker.track("ssh:" + host, result.groups, result.generatedAt, host, opts),
            this.tracker.limitResets("ssh:" + host, result.groups, host, opts),
          ),
          this.tracker.overlaps("ssh:" + host, result.groups, host, opts),
        );
        const resets = this.tracker.resets("ssh:" + host, result.groups);
        Object.assign(now, { loading: false, ok: true, error: "", result, updatedAt: Date.now(), login: false, loggedIn: !!answer.loggedIn });
        this.hostAnswered.set(host, asked);
        this.react(changes, resets);
      } else {
        // keep the last answer to show (dimmed) with the error
        Object.assign(now, { loading: false, ok: false, error: answer.error || "no answer", login: !!answer.login, loggedIn: false });
        this.log.warn(`${host}: ${now.error}`);
      }
    } finally {
      this.hostBusy.delete(host);
      const h2 = this.hosts.get(host);
      if (h2) h2.loading = false;
      this.emit();
      if (this.hostAgain.delete(host) && h2) void this.pollHost(host);
    }
  }

  // Queued tasks whose usage limit has reset start now: from the window
  // that notifies (of several windows, and the Plasma widget, only one
  // starts each: jump.py --start-queued takes it out of the queue first)
  // (a task whose account is at its usage limit right now waits on until
  // that resets: jump.py --requeue)
  private startDueTasks(status: Status): void {
    if (this.demo || !this.notifier.isLeader()) return;
    // (a host's accounts as it last said them, also when its last check
    // failed: allGroups leaves those out, and its chats aren't gone then)
    const groupsOf = (host: string): Group[] => (host ? (this.hosts.get(host)?.result?.groups ?? []) : status.groups);
    for (const t of status.queue ?? []) {
      if (t.afterTurn) {
        // a reply for when the chat's turn ends: now it has (or the chat isn't
        // listed); a host not heard from yet, or whose last check failed, waits
        const h = t.host ? this.hosts.get(t.host) : undefined;
        if (t.host && (!h?.result || h.error)) continue;
        // (the chat's row on the task's account first, as the widget's listedRow)
        const rows = groupsOf(t.host || "").flatMap((g) =>
          g.sessions.filter((s) => s.chatId === t.chat || s.sessionId === t.chat).map((s) => ({ s, own: (g.profileKeys ?? []).includes(t.profile) })));
        const row = (rows.find((r) => r.own) ?? rows[0])?.s;
        if (t.error || this.starting.has(t.id) || (row && (row.state === "working" || row.state === "waiting"))) continue;
        if (t.startAt > Date.now()) continue; // (it waits for a usage limit to reset, as below)
      } else if (!t.due || this.starting.has(t.id)) continue;
      // (a reply too: on an account at its usage limit it would stop at once)
      const group = groupsOf(t.host || "").find((g) => (g.profileKeys ?? []).includes(t.profile));
      const reset = group ? limitReset(group, Date.now()) : null;
      if (!reset) {
        void this.startQueued(t);
        continue;
      }
      this.starting.add(t.id);
      void this.backend
        .action("jump.py", ["--requeue", t.id, "--at", String(Math.round(reset.at + 60_000)), ...configDirArgs()])
        .then((a) => {
          if (t.afterTurn && a.ok && a.message) this.setActionInfo(a.message); // (It waits for the usage limit: it starts at 14:31)
        })
        .finally(() => {
          this.starting.delete(t.id);
          void this.refresh();
        });
    }
  }

  private starting = new Set<string>();

  async startQueued(t: QueuedTask): Promise<void> {
    if (this.starting.has(t.id)) return;
    this.starting.add(t.id);
    this.emit();
    try {
      const answer = await this.backend.action("jump.py", ["--start-queued", t.id, ...configDirArgs()], 120000);
      const what = queuedWhat(t).split("\n")[0];
      if (t.afterTurn) {
        // your reply, sent as the chat's turn ended
        if (answer.ok && answer.message && settings.notifyDone() && this.notifier.isLeader() && !this.visible)
          void vscode.window.showInformationMessage(`Sent to ${t.name || "the chat"}: ${t.prompt} — ${answer.message}`);
        else if (!answer.ok) this.setActionError(`Couldn't send your reply to ${t.name || "the chat"}: ${answer.message}`);
      } else if (answer.waits !== undefined) {
        // a chat's go-on waits for its background commands (the queue says
        // so): told once, as it starts waiting, as the widget does
        if (answer.notify) {
          this.setActionInfo(answer.message);
          if (this.notifier.isLeader() && !this.visible) void vscode.window.showWarningMessage(answer.message);
        }
      } else if (answer.ok && answer.message) {
        // ("": another window, or the widget, started it)
        this.petEvent("reset", `Started: ${what}`);
        if (answer.ended !== undefined) {
          // (it ended the background commands it waited for: told whatever the settings, as it began to wait)
          this.setActionInfo(answer.message);
          if (this.notifier.isLeader() && !this.visible) void vscode.window.showInformationMessage(answer.message);
        } else if (settings.notifyDone() && this.notifier.isLeader())
          void vscode.window.showInformationMessage(`Started on ${t.account}: ${what} — ${answer.message}${t.host ? ` · ${t.host}` : ""}`);
      } else if (!answer.ok) {
        this.setActionError(`Couldn't start the queued task: ${answer.message}`);
        if (!this.visible) void vscode.window.showErrorMessage(`Talpy Den: couldn't start the queued task “${what}”: ${answer.message}`);
      }
    } finally {
      this.starting.delete(t.id);
      void this.refresh();
      if (t.host) void this.pollHost(t.host);
    }
  }

  isStarting(id: string): boolean {
    return this.starting.has(id);
  }

  // After Log in… (a host that wants a password): check it every few seconds
  // until it answers, for up to three minutes
  watchLogin(host: string): void {
    const until = Date.now() + 180000;
    const tick = () => {
      const h = this.hosts.get(host);
      if (this.disposed || !h || h.ok || Date.now() > until) return;
      void this.pollHost(host);
      setTimeout(tick, 3000);
    };
    setTimeout(tick, 3000);
  }

  private notifyOptions() {
    return {
      notifyWaiting: settings.notifyWaiting(),
      notifyDone: settings.notifyDone(),
      notifyDoneMinSeconds: settings.notifyDoneMinSeconds(),
    };
  }

  // Pets and notifications, once the new status is stored: a reaction that
  // fails can't hold the dashboard back (the widget froze that way once, at
  // every plan-limit reset).
  private react(changes: Changes, resets: PetEvent[]): void {
    if (this.disposed) return; // a poll that finished after the window closed: no toasts or sounds
    try {
      this.petEvents([...changes.petEvents, ...resets]);
      const now = Date.now();
      this.away.tracker.note(changes, resets, now);
      this.noteUnseen(changes);
      const holdDone = settings.awayDigest() && this.away.holding(now, settings.awayMinutes() * 60000);
      if (!this.demo) this.notifier.handle(changes, { holdDone });
    } catch (e) {
      this.log.error(`A reaction to the new status failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // A turn that finished while you weren't looking at the view (and that was
  // long enough to notify about) waits for you: the shortcut to the chat that
  // needs you goes there too
  private noteUnseen(changes: Changes): void {
    const min = settings.notifyDoneMinSeconds() * 1000;
    for (const f of changes.finished) {
      if (f.stop) this.unseen.delete(f.id); // (a limit broke it off: nothing to look at)
      if (f.stop) this.finishedUnopened.delete(f.id);
      else if (f.took >= min && !this.lookingAt(f.id)) this.finishedUnopened.set(f.id, f.at);
    }
    if (!(this.visible && vscode.window.state.focused))
      for (const f of changes.finished) if (!f.stop && f.took >= min) this.unseen.set(f.id, f.at);
    if (changes.finished.length) this.onUnseenEmitter.fire();
  }

  private clearUnseen(): void {
    if (!this.unseen.size) return;
    this.unseen.clear();
    this.onUnseenEmitter.fire();
  }

  // How many chats finished since you last looked (and still sit finished):
  // the badge's count when none needs you
  unseenCount(): number {
    const st = this.state();
    const states = new Map<string, string>();
    for (const g of allGroups(st.status, st.hosts)) for (const s of g.sessions) states.set(trackKey(s, g.host), s.state);
    let n = 0;
    for (const id of this.unseen.keys()) {
      const state = states.get(id);
      if (state === "idle" || state === "done") n++;
    }
    return n;
  }

  // You opened a chat: it's looked at
  opened(chat: ChatRef): void {
    if (this.finishedUnopened.delete(trackKey(chat, chat.host))) this.emit();
  }

  // The finished chats you haven't opened (newest first); one that works
  // again, or that its machine no longer lists, is let go
  private finishedNow(status: Status | null, hosts: HostState[]): string[] {
    const states = new Map<string, string>();
    for (const g of allGroups(status, hosts)) for (const s of g.sessions) states.set(trackKey(s, g.host), s.state);
    const checked = (id: string) => (id.startsWith("ssh:") ? hosts.some((h) => id.startsWith(`ssh:${h.name}|`) && h.result && !h.error) : !!status);
    for (const id of [...this.finishedUnopened.keys()]) {
      const state = states.get(id);
      if (state === "working" || state === "waiting" || (state === undefined && checked(id))) this.finishedUnopened.delete(id);
    }
    return [...this.finishedUnopened.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
  }

  // The chats that need you, most urgent first (model.chatsNeedingYou)
  needingYou(): ChatSpot[] {
    const st = this.state();
    const groups = allGroups(st.status, st.hosts);
    // a finished chat that works again, or is gone, no longer waits for you
    const states = new Map<string, string>();
    for (const g of groups) for (const s of g.sessions) states.set(trackKey(s, g.host), s.state);
    for (const id of [...this.unseen.keys()]) {
      const state = states.get(id);
      if (state !== "idle" && state !== "done") this.unseen.delete(id);
    }
    return chatsNeedingYou(groups, this.unseen);
  }

  seen(id: string): void {
    if (this.unseen.delete(id)) this.onUnseenEmitter.fire();
  }

  // Back at VS Code after a while: what happened, in one notification
  private cameBack(now: number, lastUse: number): void {
    const st = this.state();
    const digest = this.away.tracker.back(now, lastUse, allGroups(st.status, st.hosts), settings.awayMinutes() * 60000);
    if (!digest || this.demo || !settings.awayDigest()) return;
    // a card in the view; a notification too, unless notifications are off
    this.digest = { title: digest.title, lines: digest.lines, at: now, first: digest.first ? chatRef(digest.first.session, digest.first.host) : null };
    if (settings.notifyWaiting() || settings.notifyDone())
      this.notifier.digest(digest, () => void vscode.commands.executeCommand(`${VIEW_ID}.focus`));
    this.emit();
  }

  dismissDigest(): void {
    this.digest = null;
    this.emit();
  }

  private petEvents(events: PetEvent[]): void {
    for (const e of events) this.onPetEventEmitter.fire(e);
  }

  petEvent(kind: PetEventKind, text: string, key = ""): void {
    this.onPetEventEmitter.fire({ kind, text, key });
  }

  setActionError(message: string): void {
    this.actionError = message;
    clearTimeout(this.messageTimers.error);
    this.messageTimers.error = setTimeout(() => {
      this.actionError = "";
      this.emit();
    }, MESSAGE_MS.error);
    if (message) this.petEvent("oops", "Hmm, that didn't work.");
    this.emit();
  }

  setActionInfo(message: string): void {
    this.actionInfo = message;
    clearTimeout(this.messageTimers.info);
    this.messageTimers.info = setTimeout(() => {
      this.actionInfo = "";
      this.emit();
    }, MESSAGE_MS.info);
    this.emit();
  }

  // Demo mode: made-up chats whose story moves on every few seconds, for
  // screenshots and for trying the view without Claude Code.
  toggleDemo(): boolean {
    if (this.demo) {
      clearInterval(this.demoTimer);
      this.demoPhase = null;
      this.tracker.forget("demo");
      this.scheduleLocal(0);
      this.scheduleHosts(0);
    } else {
      this.demoPhase = 0;
      const step = () => {
        const state = demoState(Date.now(), this.demoPhase ?? 0);
        const groups = [...(state.status?.groups ?? []), ...state.hosts.flatMap((h) => h.result?.groups ?? [])];
        this.petEvents(this.tracker.track("demo", groups, Date.now(), undefined, this.notifyOptions()).petEvents);
      };
      step();
      this.demoTimer = setInterval(() => {
        this.demoPhase = (this.demoPhase ?? 0) + 1;
        step();
        this.emit();
      }, DEMO_STEP_MS);
    }
    this.emit();
    return this.demo;
  }

  // The Recap tab's recap of these days, with the SSH hosts shown whose last
  // check answered (one out of reach would hold it up)
  async week(back: number, account: string, span: WeekSpan = "week"): Promise<{ recap?: WeekRecap; error?: string }> {
    if (this.demoPhase !== null) return { recap: demoWeek(Date.now(), back, account, span) };
    void this.syncRecapHistory();
    const hosts = this.answeringHosts();
    const currency = settings.recapCurrency();
    return this.backend.week([
      "--span", span,
      "--back", String(back),
      ...(account ? ["--account", account] : []),
      ...(currency !== "USD" ? ["--currency", currency] : []),
      ...hosts.flatMap((h) => ["--host", h]),
      ...configDirArgs(),
    ]);
  }

  // A rule the Recap tab offers for permission prompts you answered: into
  // the chats' folder's .claude/settings.local.json, or taken back
  async weekRule(ask: WeekRuleAsk, host = ""): Promise<{ ok: boolean; message: string }> {
    if (this.demoPhase !== null) return { ok: false, message: "Not in the demo: nothing was changed" };
    if (host && !this.shownHosts().includes(host)) return { ok: false, message: `${host} isn't one of the SSH hosts shown` };
    return this.backend.action("week.py", [...(ask.allow ? ["--allow", ask.kind, ask.value, ask.project] : ["--undo", ask.id]),
      ...(host ? ["--on", host] : [])]);
  }

  // The Recap's history: kept past Claude's own cleanup or not (one choice
  // for every copy of the widget's week.py: a file next to their cache), or
  // deleted (it starts again from the transcripts Claude still has)
  async setRecapHistory(keep: boolean): Promise<void> {
    // (the window it was changed in: every window hears of the change)
    if (this.demoPhase !== null || !vscode.window.state.focused) return;
    const now = await this.backend.historyStatus();
    if (now && now.keep === keep) return; // (the setting caught up with week.py's choice: syncRecapHistory)
    // off forgets the numbers of the chats Claude has deleted: asked first, as Delete Saved History… does
    if (!keep && now && now.deletedChats > 0) {
      const n = now.deletedChats;
      const pick = await vscode.window.showWarningMessage("Stop keeping the history?", {
        modal: true,
        detail: `The Recap forgets the numbers of the ${n} ${n === 1 ? "chat" : "chats"} Claude has deleted, for good.`,
      }, "Stop Keeping It");
      if (pick !== "Stop Keeping It") {
        await vscode.workspace.getConfiguration("talpyDen").update("recapHistory", true, vscode.ConfigurationTarget.Global);
        return;
      }
    }
    const { ok, message } = await this.backend.action("week.py", ["--history", keep ? "on" : "off"]);
    if (ok) void vscode.window.showInformationMessage(`Talpy Den: ${message}.`);
    else void vscode.window.showWarningMessage(`Talpy Den: the Recap's history didn't change: ${message}`);
  }

  // The setting shows the choice week.py keeps (Talpy Den's settings on
  // Plasma or GNOME may have changed it)
  async syncRecapHistory(): Promise<void> {
    if (this.demoPhase !== null) return;
    try {
      const now = await this.backend.historyStatus();
      if (now && now.keep !== settings.recapHistory())
        await vscode.workspace.getConfiguration("talpyDen").update("recapHistory", now.keep, vscode.ConfigurationTarget.Global);
    } catch {
      // (no answer: the setting stays as it is)
    }
  }

  async forgetRecapHistory(): Promise<void> {
    const pick = await vscode.window.showWarningMessage("Delete the Recap's saved history?", {
      modal: true,
      detail: "It starts again from the chats Claude still has (Claude Code keeps them 30 days by default).",
    }, "Delete");
    if (pick !== "Delete" || this.demoPhase !== null) return;
    const { ok, message } = await this.backend.action("week.py", ["--forget"]);
    if (ok) void vscode.window.showInformationMessage(`Talpy Den: ${message}.`);
    else void vscode.window.showWarningMessage(`Talpy Den: nothing was deleted: ${message}`);
  }

  // The Projects tab's projects (kept: a click on one of its chats, plans
  // or memories is found in it); a read that failed says why, with the ones
  // read last (as Plasma keeps them)
  async projects(): Promise<{ data?: ProjectsData; error?: string }> {
    const answer = this.demoPhase !== null ? { data: demoProjects(Date.now()) } : await this.backend.projects(configDirArgs());
    if (answer.data) this.projectsData = answer.data;
    return answer.data ? answer : { data: this.projectsData ?? undefined, error: answer.error };
  }

  projectsRead(): ProjectsData | null {
    return this.projectsData;
  }

  // An account's first count recent chats, past what the status lists
  // ("Show N more"): the status run once more, listing that many (a host's
  // there), without the tokens or a usage fetch. Kept, so a click on one is
  // found (moreChat).
  async recentMore(groupId: string, host: string | undefined, count: number): Promise<RecentMore | null> {
    if (this.demo || this.disposed) return null;
    const more = ["--recent", String(count), "--no-tokens", "--usage-refresh", "0"];
    let result: Status | undefined;
    if (host) {
      const answer = await this.backend.hostStatus(host, [...statusArgs(), ...more]);
      if (answer.ok && answer.result) result = toLocalClock(answer.result, Date.now() - (answer.result.generatedAt || Date.now()));
    } else result = (await this.backend.status([...configDirArgs(), ...statusArgs(), ...more])).status;
    const g = result?.groups.find((x) => x.id === groupId);
    if (!g) return null;
    const found = { recent: g.recent ?? [], asked: count };
    this.moreRecent.set(`${host ?? ""}|${groupId}`, found);
    return found;
  }

  // A chat a click names that the status doesn't list: one of an account's
  // recent chats a bigger check listed, or one of the Projects tab's (this computer's)
  moreChat(host: unknown, key: unknown): ChatRef | null {
    if (typeof key !== "string" || !key || (host !== undefined && host !== null && typeof host !== "string")) return null;
    for (const [where, more] of this.moreRecent)
      if (where.startsWith(`${host ?? ""}|`)) {
        const c = more.recent.find((x) => x.key === key);
        if (c) return recentRef(c, (host as string) || undefined);
      }
    return host ? null : findProjectChat(this.projectsData, key);
  }

  async perms(): Promise<{ data?: PermsData; error?: string }> {
    if (this.demoPhase !== null) return { data: demoPerms(Date.now()) };
    const hosts = this.shownHosts().filter((name) => {
      const h = this.hosts.get(name);
      return !!h && h.ok && !!h.result; // (one out of reach would hold it up)
    });
    return this.backend.perms([...hosts.flatMap((h) => ["--host", h]), ...configDirArgs()]);
  }

  // Takes one of the permissions you gave (what lets chats go without
  // asking) out of its file
  async weekRevoke(id: string, host = ""): Promise<{ ok: boolean; message: string }> {
    if (this.demoPhase !== null) return { ok: false, message: "Not in the demo: nothing was changed" };
    if (host && !this.shownHosts().includes(host)) return { ok: false, message: `${host} isn't one of the SSH hosts shown` };
    return this.backend.action("week.py", ["--revoke", id, ...(host ? ["--on", host] : configDirArgs())]);
  }

  state(): ViewState {
    const now = Date.now();
    if (this.demoPhase !== null) {
      const demo = demoState(now, this.demoPhase);
      return { ...demo, ...shareUsage(demo.status, demo.hosts, settings.sshUsage()), settings: viewSettings(), actionError: this.actionError, actionInfo: this.actionInfo };
    }
    // (an account's plan usage once: shareUsage; the notifications see each machine's own)
    const hosts = this.shownHosts().map((name) => this.hosts.get(name)).filter((h): h is HostState => !!h);
    return {
      ...shareUsage(this.status, hosts, settings.sshUsage()),
      errorText: this.errorText,
      settings: viewSettings(),
      demo: false,
      platformNote:
        process.platform === "linux"
          ? ""
          : process.platform === "win32"
            ? "Talpy Den needs Linux or macOS: its status script doesn't run on Windows, so nothing shows here."
            : "Running chats on this computer are only detected on Linux for now; SSH hosts still work.",
      claudeCode: this.claudeCodeInfo(),
      actionError: this.actionError,
      actionInfo: this.actionInfo,
      digest: this.digest && now - this.digest.at < DIGEST_SHOWN_MS ? this.digest : null,
      now,
      live: this.liveViews,
      finished: this.finishedNow(this.status, hosts),
    };
  }

  emit(): void {
    if (!this.disposed) this.onStateEmitter.fire(this.state());
  }
}
