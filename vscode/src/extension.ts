// Talpy Den for VS Code. Runs on this computer only ("extensionKind":
// ["ui"]), also in Remote-SSH windows: it reads this computer's Claude Code
// files and reaches SSH hosts with this computer's ssh, so one view shows them
// all, whichever machine the window is connected to.

import * as path from "node:path";
import * as vscode from "vscode";
import { Accounts } from "./accounts";
import { AccountSwitch } from "./accountSwitch";
import { Actions } from "./actions";
import { Backend } from "./backend";
import { configDirArgs } from "./config";
import { openChangesLink } from "./changes";
import { ChatPanes } from "./chatPane";
import { dictationModels } from "./dictation";
import { answerPermissionsHere, liveModeHere } from "./relay";
import { extraConfigDirs, settings } from "./config";
import { markdownLinkFile, openAgentRunFile } from "./agentRun";
import { Dashboard } from "./dashboard";
import { carryOverSettings, settingNames } from "./legacySettings";
import { Notifier } from "./notify";
import { PlanReview, planFileOf } from "./planReview";
import { allGroups, countStates, duration, hiddenCount, type HiddenKind } from "./shared/model";
import { StatusBar } from "./statusBar";
import { registerPreview, setUpUsageBars } from "./statusline";
import { terminalLinkOf, Terminals } from "./terminals";
import { ViewHost } from "./view";

/** Once: the settings of the first name (claudeStatus.*) become talpyDen.* */
async function carryOverOldSettings(context: vscode.ExtensionContext, log: vscode.LogOutputChannel): Promise<void> {
  const flag = "settingsCarriedOver";
  try {
    if (context.globalState?.get(flag)) return;
    const old = vscode.workspace.getConfiguration("claudeStatus");
    if (typeof old.inspect !== "function") return;
    const copied = await carryOverSettings(old, vscode.workspace.getConfiguration("talpyDen"), settingNames(context.extension.packageJSON), {
      global: vscode.ConfigurationTarget.Global,
      workspace: vscode.ConfigurationTarget.Workspace,
    });
    if (copied > 0) log.info(`Took over ${copied} setting(s) of Claude Status (claudeStatus.*)`);
    await context.globalState.update(flag, true);
  } catch (e) {
    log.warn(`Couldn't take over the old settings: ${(e as Error).message}`);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("Talpy Den", { log: true });
  void carryOverOldSettings(context, log);
  const backend = new Backend(context.extensionPath, settings.python);
  // Notifications open chats through the actions, which need the dashboard
  let actions: Actions | undefined;
  const notifier = new Notifier(backend, (chat) => void actions?.open(chat));
  const dash = new Dashboard(backend, notifier, log);
  const terminals = new Terminals((host, since) => dash.hostCheckedSince(host, since));
  const statusBar = new StatusBar(); // (first: the main status bar item)
  const account = new AccountSwitch(dash, backend);
  const answerOldest = async (decision: "allow" | "deny"): Promise<void> => {
    const r = await backend.pane(["--oldest", decision], 20000);
    const message = String(r.message ?? "");
    if (r.ok) void vscode.window.setStatusBarMessage(`$(check) ${message}`, 5000);
    else void vscode.window.showInformationMessage(`Talpy Den: ${message || "Couldn't answer"}`);
    dash.refreshAll();
  };
  actions = new Actions(backend, dash, terminals, log, account);
  const accounts = new Accounts(backend, dash, terminals, account, log);
  const view = new ViewHost(context.extensionUri, dash, actions);
  // The Monday recap: once a week, the last 7 days in a few words; Open the
  // Recap shows the view on its Recap tab (week.py marks the week: the widget
  // and other windows don't show it again)
  const mondayRecap = async (): Promise<void> => {
    if (!notifier.isLeader() || !vscode.workspace.getConfiguration("talpyDen").get<boolean>("mondayRecap", true)) return;
    // (with the SSH hosts the Recap counts, so its numbers match the Recap it opens)
    const r = await backend.mondayRecap([...dash.answeringHosts().flatMap((h) => ["--host", h]), ...configDirArgs()]);
    if (!r?.ok || !r.due) return;
    const n = (k: number, one: string) => `${k} ${one}${k === 1 ? "" : "s"}`;
    const parts = [`Claude worked ${duration(r.workedMs)} over ${n(r.chats, "chat")}; you, ${duration(r.youMs)} and ${n(r.prompts, "prompt")}.`];
    if (r.project) parts.push(`Most of it in ${r.project}.`);
    if (r.workedBefore > 0) {
      const change = Math.round(((r.workedMs - r.workedBefore) / r.workedBefore) * 100);
      parts.push(change >= 0 ? `${change}% more than the week before.` : `${-change}% less than the week before.`);
    }
    const choice = await vscode.window.showInformationMessage(`Your week with Claude: ${parts.join(" ")}`, "Open the Recap");
    if (choice === "Open the Recap") {
      view.showTab("week");
      await vscode.commands.executeCommand("talpyDen.view.focus");
    }
  };
  const mondayTimer = setInterval(() => void mondayRecap(), 30 * 60000);
  const mondayFirst = setTimeout(() => void mondayRecap(), 60000);
  context.subscriptions.push({ dispose: () => (clearInterval(mondayTimer), clearTimeout(mondayFirst)) });
  const a = actions;
  const hiddenShown = new Map<HiddenKind, number>(); // (what the context keys say)
  let needsYouShown = false;
  const review = new PlanReview(extraConfigDirs);
  a.planReview = review;
  // (Send Feedback's button: plans in ~/.claude* and in talpyDen.extraConfigDirs' folders)
  const planFolders = () => void vscode.commands.executeCommand("setContext", "talpyDen.planFolders", extraConfigDirs().map((d) => path.join(d, "plans")));
  planFolders();
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => e.affectsConfiguration("talpyDen.extraConfigDirs") && planFolders()));
  // each chat's tab: its conversation, a reply box, what it asks, its review
  const panes = new ChatPanes(context.extensionUri, backend, dash, actions, terminals, log);
  view.panes = panes;
  notifier.panes = panes;

  // Send Feedback to Claude, for a plan's file (the editor's, or the active one)
  const sendFeedback = (uri?: vscode.Uri) => {
    const target = uri instanceof vscode.Uri ? uri : vscode.window.activeTextEditor?.document.uri;
    const file = target ? planFileOf(target, extraConfigDirs()) : null;
    if (!file) return void vscode.window.showInformationMessage("Talpy Den: open a plan's file first (✎ next to a plan).");
    const state = dash.state();
    const groups = state.status?.groups ?? [];
    // (the status lists the starred plans; the Projects tab, as last read, every one)
    const listed = [...groups.flatMap((g) => [...(g.plans ?? []), ...(g.starredPlans ?? [])]), ...(dash.projectsRead()?.projects ?? []).flatMap((p) => p.plans)]
      .find((p) => p.path === file.file);
    const row = groups.flatMap((g) => g.sessions).find((s) => s.plan?.path === file.file);
    void a.sendPlanFeedback(
      listed ?? {
        slug: file.slug,
        path: file.file,
        profileDir: row?.profileDir ?? path.dirname(path.dirname(file.file)),
        chatId: row ? row.chatId : null,
        title: row?.plan?.title,
      },
    );
  };

  context.subscriptions.push(
    log,
    terminals,
    notifier,
    dash,
    view,
    statusBar,
    account,
    registerPreview(),
    vscode.window.registerWebviewViewProvider(ViewHost.viewId, view, { webviewOptions: { retainContextWhenHidden: true } }),
    dash.onState((state) => {
      statusBar.update(state);
      account.update(state);
      const waiting = countStates(allGroups(state.status, state.hosts)).waiting;
      view.setBadge(waiting, dash.unseenCount());
      // (Go to the Chat That Needs You shows in the view's ⋯ menu only while one does)
      if ((waiting > 0) !== needsYouShown) {
        needsYouShown = waiting > 0;
        void vscode.commands.executeCommand("setContext", "talpyDen.needsYou", needsYouShown);
      }
      // (Show Hidden … Again shows only when something of that kind is hidden here or on a host shown)
      for (const kind of ["chats", "plans", "memories", "projects"] as HiddenKind[]) {
        const n = hiddenCount(state.status, kind) + state.hosts.reduce((sum, h) => sum + hiddenCount(h.result, kind), 0);
        if (n !== hiddenShown.get(kind)) void vscode.commands.executeCommand("setContext", `talpyDen.hidden.${kind}`, n > 0);
        hiddenShown.set(kind, n);
      }
    }),
    dash.onUnseen(() => {
      const state = dash.state();
      view.setBadge(countStates(allGroups(state.status, state.hosts)).waiting, dash.unseenCount());
    }),
    review,
    vscode.commands.registerCommand("talpyDen.planComment.add", (reply: vscode.CommentReply) => review.add(reply)),
    vscode.commands.registerCommand("talpyDen.planComment.delete", (thread: vscode.CommentThread) => review.remove(thread)),
    vscode.commands.registerCommand("talpyDen.sendPlanFeedback", sendFeedback),
    vscode.commands.registerCommand("talpyDen.switchAccount", () => account.switch()),
    vscode.commands.registerCommand("talpyDen.accounts", () => accounts.manage()),
    vscode.commands.registerCommand("talpyDen.addAccount", () => accounts.add()),
    vscode.commands.registerCommand("talpyDen.nextChat", () => a.nextChat()),
    // Keyboard answers: the chat that has waited longest for a permission (a
    // plan: approve it, or keep planning), through the hook (pane.py --oldest)
    vscode.commands.registerCommand("talpyDen.allowOldest", () => answerOldest("allow")),
    vscode.commands.registerCommand("talpyDen.denyOldest", () => answerOldest("deny")),
    // the Plasma and GNOME widgets hand over what a chat changed (changes.ts)
    // and which terminal a chat runs in (terminals.ts)
    vscode.window.registerUriHandler({
      handleUri: async (uri) => {
        if (uri.path.replace(/\/+$/, "") === "/markdown") {
          // a plan or a subagent's run, in the Markdown preview
          const file = markdownLinkFile(uri, undefined, extraConfigDirs());
          if (!file) {
            log.warn(`Ignored a link that isn't a plan or a run of Talpy Den's: ${uri.toString()}`);
            return;
          }
          const error = await openAgentRunFile(file);
          if (error) void vscode.window.showErrorMessage(`Talpy Den: couldn't show ${file}: ${error}`);
          return;
        }
        const link = terminalLinkOf(uri);
        if (!link) return openChangesLink(uri, log);
        if (await terminals.showLinked(link, dash.currentHost)) return;
        log.warn(`No terminal of this window runs that chat: ${uri.toString()}`);
        void vscode.window.showWarningMessage("Talpy Den: this window has no terminal running that chat.");
      },
    }),
    vscode.commands.registerCommand("talpyDen.refresh", () => {
      dash.refreshAll();
      void dash.fetchUsage();
    }),
    vscode.commands.registerCommand("talpyDen.forgetRecapHistory", () => dash.forgetRecapHistory()),
    vscode.commands.registerCommand("talpyDen.pickHosts", () => a.pickHosts()),
    vscode.commands.registerCommand("talpyDen.openInEditor", () => view.openInEditor()),
    vscode.commands.registerCommand("talpyDen.newChat", () => a.newChat()),
    vscode.commands.registerCommand("talpyDen.findChat", () => a.findChat()),
    vscode.commands.registerCommand("talpyDen.showRemoved", () => a.showHidden("chats")),
    vscode.commands.registerCommand("talpyDen.showHiddenPlans", () => a.showHidden("plans")),
    vscode.commands.registerCommand("talpyDen.showHiddenMemories", () => a.showHidden("memories")),
    vscode.commands.registerCommand("talpyDen.showHiddenProjects", () => a.showHidden("projects")),
    vscode.commands.registerCommand("talpyDen.setupUsageBars", () => setUpUsageBars(context.extensionUri)),
    vscode.commands.registerCommand("talpyDen.removeUsageBars", () => setUpUsageBars(context.extensionUri, true)),
    vscode.commands.registerCommand("talpyDen.playWithTalpy", async () => {
      view.showTab("chats");
      await vscode.commands.executeCommand("talpyDen.view.focus");
      view.playWithTalpy();
    }),
    // Playful Talpy on or off (the view's … menu shows the one that changes it)
    vscode.commands.registerCommand("talpyDen.playfulOn", () =>
      vscode.workspace.getConfiguration("talpyDen").update("playfulTalpy", true, vscode.ConfigurationTarget.Global)),
    vscode.commands.registerCommand("talpyDen.playfulOff", () =>
      vscode.workspace.getConfiguration("talpyDen").update("playfulTalpy", false, vscode.ConfigurationTarget.Global)),
    vscode.commands.registerCommand("talpyDen.openUsagePage", () =>
      vscode.env.openExternal(vscode.Uri.parse("https://claude.ai/settings/usage")),
    ),
    vscode.commands.registerCommand("talpyDen.openSettings", () =>
      vscode.commands.executeCommand("workbench.action.openSettings", `@ext:${context.extension.id}`),
    ),
    vscode.commands.registerCommand("talpyDen.toggleDemo", () => {
      const on = dash.toggleDemo();
      void vscode.window.showInformationMessage(on ? "Talpy Den shows made-up demo chats now." : "Talpy Den shows your chats again.");
    }),
    vscode.commands.registerCommand("talpyDen.showLog", () => log.show()),
    vscode.commands.registerCommand("talpyDen.answerPermissions", () => answerPermissionsHere(backend, dash)),
    vscode.commands.registerCommand("talpyDen.liveMode", () => liveModeHere(backend, dash)),
    vscode.commands.registerCommand("talpyDen.dictationModels", () => dictationModels(backend)),
    panes,
  );
  statusBar.update(dash.state());
  void dash.start();
}

export function deactivate(): void {
  // everything is in context.subscriptions
}
