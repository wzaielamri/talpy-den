// The webview: in the Activity Bar view, and optionally as an editor tab.
// Both get the same page and the same state; the page only talks to the
// extension through messages (src/shared/types.ts), never to the network.

import * as crypto from "node:crypto";
import * as vscode from "vscode";
import type { Actions } from "./actions";
import { AGENT_ID } from "./agentRun";
import type { ChatPanes } from "./chatPane";
import { setReopenIn, settings } from "./config";
import type { Dashboard } from "./dashboard";
import { badgeOf, findChatRef, findMemory, findPlan, findProjectMemory, findProjectPlan, goOnAt, keptChat, machineStatus, shareAccounts } from "./shared/model";
import { answersOf, askShownOf } from "./shared/pane";
import { permsHost, weekAsked, weekRevokeAsked, weekRuleAsked } from "./shared/week";
import type { ChatRef, Group, HostMessage, Memory, PlanItem, ProjectsData, WebviewMessage } from "./shared/types";
import { isDecision } from "./shared/types";

const CHAT_ID = /^[A-Za-z0-9_-]{1,80}$/;
const PROFILE_DIR = /^[A-Za-z0-9._-]{1,100}$/;
const TIP_COMMAND = /^\/[a-z][a-z-]{0,30}( [a-z0-9-]{1,30})?$/; // what a Recap tab tip suggests, e.g. "/effort xhigh"
// (a permission change the page asked for that isn't one: "Nothing changed: …")
const REFUSED = "that isn't something Talpy Den can change";

export class ViewHost implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewId = "talpyDen.view";
  static readonly badgeId = "talpyDen.badge";
  private webviews = new Set<vscode.Webview>();
  private visibleCount = 0;
  private panel: vscode.WebviewPanel | undefined;
  private view: vscode.WebviewView | undefined;
  // The Activity Bar badge's: a tree view nobody sees (package.json: when
  // talpyDen.never) badges the container from startup; a webview view's badge
  // shows only once the view was opened. Once the view is there, the badge is
  // its own (the tree's cleared: a container adds up its views' numbers), so
  // it follows the view wherever you dragged it.
  private badgeTree: vscode.TreeView<never>;
  private badge: vscode.ViewBadge | undefined;
  private disposables: vscode.Disposable[] = [];
  panes?: ChatPanes; // the chats' tabs (set once they're there)

  constructor(
    private extensionUri: vscode.Uri,
    private dash: Dashboard,
    private actions: Actions,
  ) {
    this.badgeTree = vscode.window.createTreeView<never>(ViewHost.badgeId, { treeDataProvider: { getTreeItem: (e) => e, getChildren: () => [] } });
    this.disposables.push(
      this.badgeTree,
      dash.onState((state) => this.broadcast({ type: "state", state })),
      dash.onPetEvent((e) => this.broadcast({ type: "petEvent", kind: e.kind, text: e.text, key: e.key })),
      // (each step between checks: only what the chats do now, not the whole state)
      dash.onLive((e) => this.broadcast({ type: "live", live: e.live })),
      // (the plan usage Refresh fetched came in: the Recap in sight reads again)
      dash.onUsageCameIn(() => this.broadcast({ type: "readAgain", recap: true })),
    );
  }

  dispose(): void {
    this.panel?.dispose();
    for (const d of this.disposables) d.dispose();
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    this.showBadge();
    const webview = view.webview; // (a disposed view's throws: onDidDispose)
    this.setUp(webview, false);
    let visible = view.visible;
    if (visible) this.visibleCount++;
    view.onDidChangeVisibility(() => {
      if (view.visible === visible) return;
      visible = view.visible;
      this.visibleCount += visible ? 1 : -1;
      this.visibilityChanged(view.webview, visible);
    });
    view.onDidDispose(() => {
      if (visible) this.visibleCount--;
      this.webviews.delete(webview);
      this.projectsShown.delete(webview);
      this.view = undefined;
      this.showBadge();
      this.dash.setVisible(this.visibleCount > 0);
    });
    this.dash.setVisible(this.visibleCount > 0);
  }

  openInEditor(): void {
    if (this.panel) {
      this.panel.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel("talpyDen.panel", "Talpy Den", vscode.ViewColumn.Active, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: this.roots(),
    });
    panel.iconPath = vscode.Uri.joinPath(this.extensionUri, "media", "talpy.svg");
    this.panel = panel;
    const webview = panel.webview; // (a closed panel's throws: onDidDispose)
    this.setUp(webview, true);
    let visible = panel.visible;
    if (visible) this.visibleCount++;
    panel.onDidChangeViewState(() => {
      if (panel.visible === visible) return;
      visible = panel.visible;
      this.visibleCount += visible ? 1 : -1;
      this.visibilityChanged(panel.webview, visible);
    });
    panel.onDidDispose(() => {
      if (visible) this.visibleCount--;
      this.webviews.delete(webview);
      this.projectsShown.delete(webview);
      this.panel = undefined;
      this.dash.setVisible(this.visibleCount > 0);
    });
    this.dash.setVisible(this.visibleCount > 0);
  }

  // The count on the Activity Bar icon: chats that need you, else chats that
  // finished since you last looked (model.badgeOf)
  setBadge(waiting: number, finished: number): void {
    const badge = badgeOf(waiting, finished);
    if (badge?.value === this.badge?.value && badge?.tooltip === this.badge?.tooltip) return;
    this.badge = badge;
    this.showBadge();
  }

  private showBadge(): void {
    if (this.view) this.view.badge = this.badge;
    this.badgeTree.badge = this.view ? undefined : this.badge;
  }

  private visibilityChanged(webview: vscode.Webview, visible: boolean): void {
    void webview.postMessage({ type: "visible", visible } satisfies HostMessage);
    this.dash.setVisible(this.visibleCount > 0);
  }

  private roots(): vscode.Uri[] {
    return [vscode.Uri.joinPath(this.extensionUri, "dist"), vscode.Uri.joinPath(this.extensionUri, "vendor", "pets")];
  }

  private setUp(webview: vscode.Webview, editorTab: boolean): void {
    webview.options = { enableScripts: true, localResourceRoots: this.roots() };
    webview.html = this.html(webview, editorTab);
    this.webviews.add(webview);
    webview.onDidReceiveMessage((m: unknown) => this.receive(webview, m));
  }

  // A page that loads while its view is hidden mustn't start its pets
  private isVisible(webview: vscode.Webview): boolean {
    if (this.view?.webview === webview) return this.view.visible;
    if (this.panel?.webview === webview) return this.panel.visible;
    return true;
  }

  // A tab of the view, shown in its loaded pages now; the view's own page
  // that isn't loaded yet (the caller shows it next) asks when it's ready.
  // No page that loads later (Open in Editor, hours on) starts on it.
  private shownTab: "chats" | "week" | "perms" | null = null;
  private ready = new WeakSet<vscode.Webview>(); // the pages that said they're ready
  showTab(tab: "chats" | "week" | "perms"): void {
    this.shownTab = this.view && this.ready.has(this.view.webview) ? null : tab;
    this.broadcast({ type: "showTab", tab });
  }

  // Refresh (the view's title bar, the Command Palette, an editor tab's
  // header): the chats and the plan usage, and in each page the Recap,
  // Permissions or Projects tab in sight reads again (they have no button
  // of their own for it)
  refresh(): void {
    this.dash.refreshAll();
    void this.dash.fetchUsage();
    this.broadcast({ type: "readAgain" });
  }

  // Play with Talpy (the view's ⋯ menu): a game with the big Talpy, in the
  // view's page (shown first) and in an editor tab's
  playWithTalpy(): void {
    this.broadcast({ type: "playWithTalpy" });
  }

  private broadcast(message: HostMessage): void {
    for (const w of this.webviews) void w.postMessage(message);
  }

  // A chat the page names, as the extension knows it: what runs for it (its
  // open or stop command, its process) comes from the extension's own state,
  // never from the page
  private chatOf(m: { chat?: unknown }): ChatRef | null {
    const ref = m.chat && typeof m.chat === "object" ? (m.chat as { host?: unknown; key?: unknown }) : null;
    const state = this.dash.state();
    // (else one of a bigger check's recent chats, or of the Projects tab's)
    return ref ? findChatRef(state.status, state.hosts, ref.host, ref.key) ?? this.dash.moreChat(ref.host, ref.key) : null;
  }

  // One of an account's memories (or its CLAUDE.md), or of the Projects tab's
  // (an SSH host's shown: as read there, on that host's account)
  private memoryOf(m: { groupId?: unknown; host?: unknown; memory?: unknown }): { memory: Memory; group: Group } | null {
    const state = this.dash.state();
    const host = this.projectHost(m.host);
    return findMemory(state.status, state.hosts, m.host, m.groupId, m.memory)
      ?? (host === null ? null : findProjectMemory(this.dash.projectsOn(host), this.statusOn(host), m.memory, host));
  }

  // A machine the page names for the Projects tab: undefined (this computer),
  // an SSH host shown, or null (anything else)
  private projectHost(host: unknown): string | undefined | null {
    if (host === undefined || host === null || host === "") return undefined;
    return typeof host === "string" && this.dash.shownHosts().includes(host) ? host : null;
  }

  // A machine's status as the view has it (a host's: its last answer)
  private statusOn(host: string | undefined) {
    const state = this.dash.state();
    return host ? state.hosts.find((h) => h.name === host)?.result ?? null : state.status;
  }

  // The Projects tab's chats, plans and memories (week.py --projects), to the
  // view that shows it: this computer's, and each SSH host's shown that
  // answered its last check (week.py --projects --on HOST, each on its own,
  // so a slow host holds up no other: what's read goes to the view as it
  // comes, once this computer's is in); read again for the views that show it
  // after a star, a hide, a move or a delete (only the machine it was on:
  // which, "" this computer, else that host; none: every one)
  private projectsShown = new Set<vscode.Webview>();
  private async sendProjects(webview: vscode.Webview, which?: string): Promise<void> {
    let local: { data?: ProjectsData; error?: string } = { data: this.dash.projectsRead() ?? undefined };
    const send = () => void webview.postMessage({ type: "projects", data: local.data ?? null, error: local.error ?? "",
                                                  hosts: this.dash.hostProjectsRead() } satisfies HostMessage);
    if (which) {
      const read = this.dash.readHostProjects(which);
      send();   // (its read on its way)
      await read;
      send();
      return;
    }
    const hosts = which === "" ? [] : this.dash.answeringHosts().map((h) => this.dash.readHostProjects(h));
    const here = this.dash.projects().then((answer) => {
      local = answer;
      send();
    });
    await Promise.all(hosts.map((read) => Promise.all([read, here]).then(send)));
    await here;
  }

  private projectsChanged(host?: string): void {
    for (const w of this.projectsShown) if (this.webviews.has(w)) void this.sendProjects(w, host ?? "");
  }

  // One of an account's plans the page names, as the extension knows it now
  // (else one of the Projects tab's, an SSH host's shown too)
  private planOf(m: { groupId?: unknown; host?: unknown; plan?: unknown }): { plan: PlanItem; group: Group } | null {
    const state = this.dash.state();
    const host = this.projectHost(m.host);
    return findPlan(state.status, state.hosts, m.host, m.groupId, m.plan)
      ?? (host === null ? null : findProjectPlan(this.dash.projectsOn(host), this.statusOn(host), m.plan, host));
  }

  // What a Delete names, as the extension knows it: a chat by its id,
  // profile and machine, an account's plan or memory by its key (an account's
  // CLAUDE.md is never deleted from here)
  private deleteTarget(m: { kind?: unknown; groupId?: unknown; host?: unknown; id?: unknown }, chat: ChatRef | null):
    { kind: "chat" | "plan" | "memory"; id: string; profileDir: string; host?: string } | null {
    if (m.kind === "chat") return chat ? { kind: "chat", id: chat.chatId || chat.sessionId, profileDir: chat.profileDir, host: chat.host } : null;
    if (m.kind === "plan") {
      const found = this.planOf({ groupId: m.groupId, host: m.host, plan: m.id });
      return found ? { kind: "plan", id: found.plan.slug, profileDir: found.plan.profileDir, host: found.group.host } : null;
    }
    if (m.kind === "memory") {
      const found = this.memoryOf({ groupId: m.groupId, host: m.host, memory: m.id });
      return found && found.memory.type !== "account" ? { kind: "memory", id: found.memory.key, profileDir: "", host: found.group.host } : null;
    }
    return null;
  }

  private receive(webview: vscode.Webview, raw: unknown): void {
    if (!raw || typeof raw !== "object" || typeof (raw as { type?: unknown }).type !== "string") return;
    const m = raw as WebviewMessage;
    const text = (v: unknown) => (typeof v === "string" && v ? v : undefined);
    const chat = "chat" in m ? this.chatOf(m) : null;
    switch (m.type) {
      case "ready":
        this.ready.add(webview);
        void webview.postMessage({ type: "state", state: this.dash.state() } satisfies HostMessage);
        void webview.postMessage({ type: "visible", visible: this.isVisible(webview) } satisfies HostMessage);
        if (this.shownTab) void webview.postMessage({ type: "showTab", tab: this.shownTab } satisfies HostMessage);
        this.shownTab = null;
        break;
      case "open":
        // (a click on a chat: its tab, unless clicks open the chat itself; a made-up one: neither)
        if (chat && this.panes && settings.clickOpensPane()) {
          if (!this.actions.demoOnly()) this.panes.open(chat, "chat");
        }
        else if (chat) void this.actions.open(chat);
        break;
      case "openPane":
        if (chat && this.panes && !this.actions.demoOnly()) this.panes.open(chat, m.tab === "review" ? "review" : "chat");
        break;
      case "openWindow":
        if (chat) void this.actions.open(chat);
        break;
      case "answerPermission":
        // (to the prompt the row showed: one the chat asks after it isn't answered)
        if (chat && this.panes && isDecision(m.decision) && !this.actions.demoOnly())
          void this.panes.answer(chat, m.decision, askShownOf(m.shown), typeof m.note === "string" ? m.note : "", answersOf(m.answers) ?? undefined);
        break;
      case "openInClaudeCode":
        if (chat) void this.actions.openInClaudeCode(chat);
        break;
      case "moveToClaudeCode":
        if (chat) void this.actions.moveToClaudeCode(chat);
        break;
      case "setReopenIn":
        if (m.where === "talpyChat" || m.where === "terminal" || m.where === "claudeCode") void setReopenIn(m.where);
        break;
      case "stop":
        if (chat) void this.actions.stop(chat);
        break;
      case "dismiss":
        if (chat) void this.actions.dismiss(chat);
        break;
      case "hide": {
        // (a plan or memory by its key, as the extension knows it; a project by its folder, this computer's or a host's shown)
        const id = m.kind === "plans" ? this.planOf({ groupId: m.groupId, host: m.host, plan: m.id })?.plan.slug
          : m.kind === "memories" ? this.memoryOf({ groupId: m.groupId, host: m.host, memory: m.id })?.memory.key
          : m.kind === "projects" && typeof m.id === "string" && m.id.startsWith("/") ? m.id : undefined;
        const host = this.projectHost(m.host);
        if (!id || (m.kind === "projects" && host === null)) break;
        void this.actions.hide(m.kind, id, m.kind === "projects" ? host ?? undefined : text(m.host)).then((ok) => {
          if (ok && m.kind === "projects") return this.sendProjects(webview, host ?? "");
          if (ok) this.projectsChanged(text(m.host));
        });
        break;
      }
      case "delete": {
        // (the line asked first)
        const what = this.deleteTarget(m, chat);
        if (what) void this.actions.delete(what.kind, what.id, what.profileDir, what.host).then(() => this.projectsChanged(what.host));
        break;
      }
      case "deleteDescribe": {
        // what Delete would do, for the question on the line
        const what = this.deleteTarget(m, chat), key = text(m.key);
        if (!key) break;
        const answer = what ? this.actions.describeDelete(what.kind, what.id, what.profileDir, what.host)
          : Promise.resolve({ ok: false, question: "", message: "It can't be deleted." });
        void answer.then(
          (a) => webview.postMessage({ type: "deleteAsk", key, ...a } satisfies HostMessage),
          () => webview.postMessage({ type: "deleteAsk", key, ok: false, question: "", message: "It can't be deleted." } satisfies HostMessage),
        );
        break;
      }
      case "moveDescribe": {
        // what Move to project… (or a plan dropped on a project) would do, for the question
        const key = text(m.key), found = this.planOf({ groupId: m.groupId, host: m.host, plan: m.id });
        if (!key) break;
        const folder = text(m.folder), back = m.back === true;
        const answer = found && (!folder || folder.startsWith("/"))
          ? this.actions.describeMove(found.plan, found.group.host, folder, back)
          : Promise.resolve({ ok: false, answer: null, message: "That plan isn't listed any more." });
        void answer.then(
          (a) => webview.postMessage({ type: "moveAsk", key, ...a } satisfies HostMessage),
          () => webview.postMessage({ type: "moveAsk", key, ok: false, answer: null, message: "It can't be moved." } satisfies HostMessage),
        );
        break;
      }
      case "movePlan": {
        // (the question was answered)
        const found = this.planOf({ groupId: m.groupId, host: m.host, plan: m.id }), folder = text(m.folder);
        const ifExists = m.ifExists === "keep" || m.ifExists === "replace" ? m.ifExists : undefined;
        if (found && (!folder || folder.startsWith("/")))
          void this.actions.movePlan(found.plan, found.group.host, folder, m.back === true, m.keepThere !== false, ifExists)
            .then(() => this.projectsChanged(found.group.host));
        break;
      }
      case "share":
        if (chat) void this.actions.share(chat);
        break;
      case "compareChanges":
        if (chat) void this.actions.compareChanges(chat, m.turn === true);
        break;
      case "openAgentRun":
        if (chat && typeof m.agentId === "string" && AGENT_ID.test(m.agentId)) void this.actions.openAgentRun(chat, m.agentId);
        break;
      case "dismissDigest":
        this.dash.dismissDigest();
        break;
      case "newChat":
        void this.actions.newChat(text(m.groupId), text(m.host));
        break;
      case "handOver": {
        // only to one of the chat's machine's accounts, as the extension knows them
        const state = this.dash.state();
        const to = shareAccounts(machineStatus(state, chat?.host)).find((g) => g.shareProfile === m.profile);
        if (chat && to?.shareProfile) void this.actions.handOver(chat, to.shareProfile);
        break;
      }
      case "openPlan": {
        if (chat?.plan) void this.actions.openPlan({ ...chat.plan, profileDir: chat.profileDir }, chat.host, m.edit === true);
        else {
          const found = this.planOf(m);
          if (found) void this.actions.openPlan(found.plan, found.group.host, m.edit === true);
        }
        break;
      }
      case "sendPlanFeedback": {
        // (this computer's plans: an SSH host's chat isn't sent feedback from here)
        if (chat?.plan && !chat.host) void this.actions.sendPlanFeedback({ ...chat.plan, profileDir: chat.profileDir, chatId: chat.chatId ?? chat.sessionId });
        else if (!chat) {
          const found = this.planOf(m);
          if (found && !found.group.host) void this.actions.sendPlanFeedback(found.plan);
        }
        break;
      }
      case "openMemory": {
        const found = this.memoryOf(m);
        if (found) void this.actions.openMemory(found.memory, found.group.host, m.edit === true);
        break;
      }
      case "carryOutPlan": {
        const found = this.planOf(m);
        if (found) void this.actions.newChat(found.group.id, found.group.host, found.plan);
        break;
      }
      case "continuePlanChat": {
        const found = this.planOf(m);
        if (found) void this.actions.continuePlanChat(found.plan, found.group);
        break;
      }
      case "sharePlan": {
        const found = this.planOf(m);
        if (found) void this.actions.sharePlan(found.plan, found.group);
        break;
      }
      case "findChat":
        void this.actions.findChat();
        break;
      case "startQueued": {
        // (a task of this computer's queue, as the extension knows it)
        const t = this.dash.state().status?.queue?.find((q) => q.id === m.id);
        if (t && !this.actions.demoOnly()) void this.dash.startQueued(t, m.now === true);
        break;
      }
      case "openOverlap": {
        // (found in the extension's own state: the row, then its first overlap's row)
        const state = this.dash.state();
        const where = chat?.host ? state.hosts.find((h) => h.name === chat.host)?.result : state.status;
        const row = where?.groups.flatMap((g) => g.sessions).find((s) => s.key === chat?.key);
        const other = row?.overlaps?.[0];
        const ref = other ? findChatRef(state.status, state.hosts, chat?.host, other.key) : null;
        if (ref) void this.actions.open(ref);
        break;
      }
      case "unqueue":
        if (this.dash.state().status?.queue?.some((q) => q.id === m.id)) void this.actions.unqueue(m.id);
        break;
      case "star": {
        // (its id from the extension's own state: a chat, or one of an account's plans)
        const found = chat ? null : this.planOf(m);
        const done = () => this.projectsChanged(chat ? chat.host : found?.group.host);
        if (chat) void this.actions.star("chats", chat.chatId || chat.sessionId, chat.host, m.on === true).then(done);
        else if (found) void this.actions.star("plans", found.plan.slug, found.group.host, m.on === true).then(done);
        break;
      }
      case "keepGoing":
        if (chat) void this.actions.keepGoing(chat, m.on === true); // (an SSH host's too: kept here)
        break;
      case "queueContinue": {
        // (found in the extension's own state: the row or recent chat, when it can go on, and its account;
        // or one of the recent chats a bigger check listed, Show N more)
        const state = this.dash.state();
        const where = chat?.host ? state.hosts.find((h) => h.name === chat.host)?.result : state.status;
        let found: { at: number; account: string } | null = null;
        for (const g of where?.groups ?? []) {
          const item = [...(g.sessions ?? []), ...(g.recent ?? []), ...(g.starred ?? [])].find((x) => x.key === chat?.key);
          if (!item) continue;
          found = { at: goOnAt(item), account: g.title };
          break;
        }
        const more = chat && !found ? this.dash.moreRecentChat(chat.host, chat.key) : null;
        const group = more && where?.groups.find((g) => g.id === more.groupId);
        if (more && group) found = { at: goOnAt(more.chat), account: group.title };
        if (chat && found?.at) void this.actions.queueContinue(chat, found.at, found.account, m.keep === true);
        else this.dash.setActionError("Couldn't queue it: that chat isn't listed any more, or no usage limit stops it now.");
        break;
      }
      case "loginHost":
        if (text(m.host) && this.dash.shownHosts().includes(m.host)) void this.actions.loginHost(m.host);
        break;
      case "disconnectHost":
        if (text(m.host) && this.dash.shownHosts().includes(m.host)) void this.actions.disconnectHost(m.host);
        break;
      case "login":
        void this.actions.login(text(m.groupId), text(m.host));
        break;
      case "refresh":
        if (text(m.host)) void this.dash.pollHost(m.host as string);
        else this.refresh();
        break;
      case "showRemoved":
        void this.actions.showHidden("chats", text(m.host) ?? null);
        break;
      case "showHidden":
        if (text(m.host)) void this.actions.showHiddenOn(m.host);
        break;
      case "hideHost":
        if (text(m.host)) void this.actions.hideHost(m.host);
        break;
      case "showHost":
        if (text(m.host)) void this.actions.showHost(m.host);
        break;
      case "keepOff": {
        // (a chat a host that isn't shown keeps going: only one this computer's status lists as kept there)
        const kept = text(m.chatId) && text(m.host) ? keptChat(this.dash.state().status, m.chatId, m.host) : null;
        if (kept) void this.actions.keepOff(kept.chat, m.host as string);
        break;
      }
      case "pickHosts":
        void this.actions.pickHosts();
        break;
      case "startContainer":
        if (text(m.host)) void this.actions.startContainer(m.host);
        break;
      case "setupUsageBars":
        void vscode.commands.executeCommand("talpyDen.setupUsageBars");
        break;
      case "openSettings":
        void vscode.commands.executeCommand("talpyDen.openSettings");
        break;
      case "week": {
        const asked = weekAsked(m.back, m.account, m.span);
        void this.dash.week(asked.back, asked.account, asked.span).then(({ recap, error }) =>
          webview.postMessage({ type: "week", ...asked, recap: recap ?? null, error: error ?? "" } satisfies HostMessage),
        );
        break;
      }
      case "limits": {
        const { account } = weekAsked(0, m.account);
        void this.dash.limits(account).then(({ data, error }) =>
          webview.postMessage({ type: "limits", account, data: data ?? null, error: error ?? "" } satisfies HostMessage),
        );
        break;
      }
      case "weekRule": {
        const ask = weekRuleAsked(m);
        const host = permsHost(m.host);
        if (!ask || host === null) {
          // (refused: the page still hears back, which frees its buttons)
          webview.postMessage({ type: "weekRule", id: ask && !ask.allow ? ask.id : "", host: text(m.host) ?? "", ok: false, message: REFUSED } satisfies HostMessage);
          break;
        }
        const id = ask.allow ? "" : ask.id;
        void this.dash.weekRule(ask, host).then(({ ok, message }) =>
          webview.postMessage({ type: "weekRule", id, host, ok, message } satisfies HostMessage),
        );
        break;
      }
      case "projects":
        if (m.shown === false) this.projectsShown.delete(webview);
        else {
          this.projectsShown.add(webview);
          void this.sendProjects(webview);
        }
        break;
      case "recentMore": {
        // (an account of this computer's or of a host shown; a few pages of it)
        const host = text(m.host);
        const count = typeof m.count === "number" && Number.isInteger(m.count) && m.count > 0 && m.count <= 2000 ? m.count : 0;
        if (!count || !text(m.groupId) || (m.host !== undefined && !(host && this.dash.shownHosts().includes(host)))) break;
        void this.dash.recentMore(m.groupId, host, count).then((more) =>
          webview.postMessage({ type: "recentMore", groupId: m.groupId, ...(host ? { host } : {}), recent: more?.recent ?? [], asked: more?.asked ?? 0 } satisfies HostMessage),
        );
        break;
      }
      case "newChatIn": {
        // (a folder the projects list named, on an account of this computer's, or of the SSH host shown it's on:
        // started there with the command its read sent, never one from the page)
        const host = this.projectHost(m.host);
        if (host === null || typeof m.path !== "string" || !m.path.startsWith("/")) break;
        const status = this.statusOn(host);
        const group = status?.groups.find((g) => (g.profileKeys ?? []).includes(m.profileDir)) ?? status?.groups[0];
        // (its folder as week.py says it, from your home wherever that is)
        const short = typeof m.short === "string" && m.short && m.short.length < 4096 ? m.short : m.path.replace(/^\/home\/[^/]+/, "~");
        const row = host ? this.dash.projectsOn(host)?.projects.find((p) => p.path === m.path) : undefined;
        if (group && (!host || row))
          void this.actions.newChat(group.id, host, undefined, undefined,
                                    { path: m.path, short, ...(row?.newChatCommand ? { newChatCommand: row.newChatCommand } : {}) });
        break;
      }
      case "perms":
        void this.dash.perms().then(({ data, error }) =>
          webview.postMessage({ type: "perms", data: data ?? null, error: error ?? "" } satisfies HostMessage),
        );
        break;
      case "weekRevoke": {
        const id = weekRevokeAsked(m.id);
        const host = permsHost(m.host);
        if (!id || host === null) {
          webview.postMessage({ type: "weekRevoke", id: id ?? "", host: text(m.host) ?? "", ok: false, message: REFUSED } satisfies HostMessage);
          break;
        }
        void this.dash.weekRevoke(id, host).then(({ ok, message }) =>
          webview.postMessage({ type: "weekRevoke", id, host, ok, message } satisfies HostMessage),
        );
        break;
      }
      case "shareCard":
        if ((m.how === "save" || m.how === "copy") && typeof m.png === "string" && m.png.length < 8_000_000
            && typeof m.name === "string" && /^claude-(day|week|all)-[\w-]{1,20}\.png$/.test(m.name))
          void this.actions.shareCard(m.how, m.name, m.png);
        break;
      case "openWeekChat":
        if (typeof m.chatId === "string" && CHAT_ID.test(m.chatId) && typeof m.profileDir === "string" && PROFILE_DIR.test(m.profileDir))
          void this.actions.openWeekChat(m.chatId, m.profileDir, text(m.name) ?? m.chatId.slice(0, 8),
                                         typeof m.cwd === "string" && m.cwd.startsWith("/") ? m.cwd : "");
        break;
      case "copy":
        if (typeof m.text === "string" && TIP_COMMAND.test(m.text)) void vscode.env.clipboard.writeText(m.text);
        break;
      case "openUsagePage":
        void vscode.commands.executeCommand("talpyDen.openUsagePage");
        break;
    }
  }

  private html(webview: vscode.Webview, editorTab: boolean): string {
    const nonce = crypto.randomBytes(16).toString("base64");
    const asset = (...p: string[]) => webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, ...p)).toString();
    const config = JSON.stringify({ editorTab });
    // Scripts run only with the nonce, and nothing loads from outside the
    // extension. Styles may also be set inline (the pets move by element
    // styles).
    const csp = [
      "default-src 'none'",
      "base-uri 'none'",
      "form-action 'none'",
      `img-src ${webview.cspSource} data:`,
      `style-src ${webview.cspSource} 'unsafe-inline'`,
      `font-src ${webview.cspSource}`,
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${asset("dist", "webview-style.css")}">
<title>Talpy Den</title>
</head>
<body>
<script nonce="${nonce}">window.TALPY_DEN = ${config.replace(/</g, "\\u003c")};</script>
<script nonce="${nonce}" src="${asset("dist", "webview.js")}"></script>
</body>
</html>`;
  }
}
