// VS Code's Claude, the Claude Code extension's panel: which account it runs
// on (named in Talpy Den's status bar item, vscode/src/statusBar.ts, with a
// link in its hover to switch) and switching it, through VS Code's own setting
// (vscodeAccount.ts), read and written through the host, the window reloaded
// by it. In a Remote-SSH window the panel runs on the host: the
// setting is a machine setting, which VS Code keeps per host (its Remote
// Settings, written from a window connected to it), so the host's accounts
// are listed and switched there, and this computer's setting stays as it is.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Backend } from "./agents/claudeCode/backend";
import { panelConfigDir, profileKey } from "./agents/claudeCode/claudePanel";
import { profileDirs } from "./agents/claudeCode/profiles";
import { configDirFor, withConfigDir } from "./agents/claudeCode/vscodeAccount";
import type { Dashboard } from "./dashboard";
import type { HostServices, PickItem } from "./host";
import { noLinks } from "./notify";
import type { EditorPort } from "./ports";
import { configDirArgs } from "./settings";
import { hostLabel, machineStatus } from "./shared/model";
import type { Group, ViewState } from "./shared/types";

function tildify(p: string): string {
  const home = os.homedir();
  return p === home || p.startsWith(home + "/") ? "~" + p.slice(home.length) : p;
}

function realOr(p: string): string {
  try {
    return fs.realpathSync(p);
  } catch {
    return p;
  }
}

// The account the status bar item names (null: one account, nothing to
// tell apart): its short name, its group (so the usage next to it is known
// to be its own), what its hover says, and what the hover's link does
export interface AccountShown {
  name: string;
  group?: Group;
  tip: string;
  link: string;
}

// Claude Accounts (accounts.ts), as the switch opens it: Add Account… and the accounts list. The accounts are
// made after the switch (they take it), so these find them when called
export interface AccountsOpener {
  add(): Promise<void>;
  manage(): Promise<void>;
}

export class AccountSwitch {
  private startedOn: string; // the folder this window's panel started on
  private switching = false;
  private told = "";

  constructor(
    private host: HostServices,
    private editor: EditorPort,
    private dash: Dashboard,
    private accounts: AccountsOpener,
    private backend?: Backend, // for pointing ~/.claude at the default account too (accounts.py)
  ) {
    this.startedOn = realOr(this.panelDir());
  }

  // claudeCode.environmentVariables: the Claude Code extension's setting (in a Remote-SSH window, the host's)
  private panelVars(): unknown {
    return this.host.settings.other<unknown>("claudeCode", "environmentVariables", undefined);
  }

  private panelDir(): string {
    return panelConfigDir(this.panelVars());
  }

  // Which account VS Code's Claude runs on, for the status bar item; and a
  // window whose panel's account was switched elsewhere offers to reload
  update(state: ViewState): AccountShown | null {
    if (this.host.environment.remoteName) return this.updateOnHost(state);
    const groups = state.status?.groups ?? [];
    if (state.demo || groups.length < 2) return null;
    const key = this.editor.localPanelProfileKey();
    const group = groups.find((g) => g.profileKeys.includes(key));
    const dir = this.panelDir();
    const plain = groups.find((g) => g.plainHere);
    const shown: AccountShown = {
      name: group ? group.name : key,
      group,
      tip:
        `VS Code's Claude runs on ${group ? group.title : key} (${tildify(dir)})` +
        (group?.defaultHere ? ", the default account" : "") +
        (plain && plain !== group ? `; plain claude on ${plain.title}` : "") +
        ".",
      link: "Change the default account…",
    };
    // Switched elsewhere (another window, or by hand): this window's panel
    // runs on the old account until the window reloads
    const now = realOr(dir);
    if (now !== this.startedOn && !this.switching && this.told !== now) {
      this.told = now;
      void this.host
        .message(
          "info",
          noLinks(`VS Code's Claude runs on ${group ? group.name : path.basename(now)} now. Reload this window so its Claude Code panel does too.`),
          undefined,
          "Reload Window",
        )
        .then((c) => c && this.host.reloadWindow());
    }
    return shown;
  }

  // A Remote-SSH window: the host's accounts, and which one Claude Code there
  // runs on (its backend reads the VS Code server's settings)
  private updateOnHost(state: ViewState): AccountShown | null {
    const host = this.dash.currentHost;
    const groups = host ? (machineStatus(state, host)?.groups ?? []) : [];
    if (!host || state.demo || groups.length < 2) return null;
    const on = groups.find((g) => g.vscodeHere);
    return {
      name: on ? on.name : "?",
      group: on,
      tip: `Claude Code on ${hostLabel(host)} runs on ${on ? on.title : "an account Talpy Den can't tell"}.`,
      link: `Change ${hostLabel(host)}'s default account…`,
    };
  }

  async switch(): Promise<void> {
    if (this.host.environment.remoteName) return this.switchOnHost();
    if (!this.editor.claudeCodeInstalled()) {
      void this.host.message("info", "The Claude Code extension isn't installed, so there's no VS Code Claude to switch.");
      return;
    }
    const groups = this.dash.state().status?.groups ?? [];
    const hidden = this.dash.state().status?.hiddenGroups ?? [];
    if (groups.length < 2 && hidden.length) {
      const names = hidden.map((g) => g.name).join(", ");
      const show = await this.host.message("info",
        noLinks(`The other Claude account${hidden.length === 1 ? ` on this computer, ${names}, is` : `s on this computer, ${names}, are`} hidden. Show ${hidden.length === 1 ? "it" : "them"} again to pick ${hidden.length === 1 ? "it" : "one"} (Claude Accounts → Show), or make ${hidden.length === 1 ? "it" : "one"} the default there.`),
        undefined,
        "Claude Accounts…",
      );
      if (show) await this.accounts.manage();
      return;
    }
    if (groups.length < 2) {
      const add = await this.host.message("info",
        "There's one Claude account on this computer. Add another one (a ~/.claude-NAME folder, logged in with Claude's own login) to switch between them.",
        undefined,
        "Add Account…",
      );
      if (add) await this.accounts.add();
      return;
    }
    const key = this.editor.localPanelProfileKey();
    const pick = await this.host.pick<PickItem & { group?: Group }>(
      [
        ...groups.map((g) => ({
          label: g.title,
          description: [
            g.defaultHere ? "$(star-full) default" : "",
            g.profileKeys.includes(key) ? "VS Code's Claude" : "",
            g.plainHere ? "plain claude" : "",
            g.loggedOut ? "not logged in" : "",
          ]
            .filter((d) => d)
            .join(" · "),
          group: g,
        })),
        { label: "", separator: true },
        { label: "$(person-add) Add Account…" },
      ],
      {
        title: "Default Claude account",
        placeHolder: "Listed first, its usage in the status bar; VS Code's Claude and plain claude (~/.claude, where it's a link) run on it",
      },
    );
    if (pick && !pick.group) await this.accounts.add();
    else if (pick?.group) await this.switchTo(pick.group);
  }

  // group becomes the default account (the widget's accounts.py --default):
  // VS Code's Claude runs on it (this setting; the window reloads) and plain
  // claude too where ~/.claude is a link. Not while that would cut a chat
  // off: one working in VS Code's Claude Code panel (the reload), or any chat
  // running through ~/.claude (accounts.py refuses: it would go on on the
  // other account).
  async switchTo(group: Group): Promise<void> {
    const onIt = group.profileKeys.includes(this.editor.localPanelProfileKey());
    const link = path.join(os.homedir(), ".claude");
    // ~/.claude a link: plain claude can follow the default (one is only
    // re-pointed, never made: without CLAUDE_CONFIG_DIR, plain claude reads
    // ~/.claude.json whatever the link says)
    let linked = false;
    try {
      linked = fs.lstatSync(link).isSymbolicLink();
    } catch {
      // no ~/.claude
    }
    const moveLink = linked && !group.plainHere && !!this.backend;
    if (onIt && !moveLink) {
      void this.host.message("info", noLinks(`${group.name} is the default account already.`));
      return;
    }
    const dir = profileDirs().find((d) => profileKey(d) === group.chatProfile);
    if (!dir) return this.fail(`Can't find the Claude folder of ${group.name}.`);
    if (!onIt) {
      const working = (this.dash.state().status?.groups ?? [])
        .flatMap((g) => g.sessions)
        .filter((s) => s.entrypoint === "claude-vscode" && s.pid !== null && (s.state === "working" || s.state === "waiting"));
      if (working.length)
        return this.fail(
          `${working.length === 1 ? `“${working[0].name}” is` : `${working.length} chats are`} working in VS Code's Claude: ` +
            "making another account the default reloads this window, which would stop it. Try again once it's done.",
        );
    }
    const ok = await this.host.message("warning",
      `Make ${group.name} the default account?`,
      {
        modal: true,
        detail:
          "It's listed first and its usage shows in the status bar. " +
          (onIt ? "" : "VS Code's Claude runs on it: this window reloads (other windows when they reload). ") +
          (moveLink
            ? "Plain `claude` in a terminal runs on it too (~/.claude is pointed at it); refused while a chat runs through ~/.claude."
            : linked
              ? ""
              : "Plain `claude` stays on ~/.claude, a folder.") +
          (onIt
            ? ""
            : "\n\nRemote-SSH windows read this setting too: on a host that doesn't have this folder, set \"claudeCode.environmentVariables\": [] in its Remote Settings."),
      },
      "Make Default",
    );
    if (ok !== "Make Default") return;
    if (moveLink && this.backend) {
      const r = await this.backend.accounts(["--default", group.chatProfile, "--no-vscode", ...configDirArgs()]);
      if (!r.ok) return this.fail(String(r.message ?? "Couldn't make it the default"));
      this.dash.refreshAll();
    }
    // (after ~/.claude moved: the account it links to is named by the link)
    const value = configDirFor(dir);
    if (value === null && process.env.CLAUDE_CONFIG_DIR) {
      // A plain ~/.claude runs without the variable, but VS Code itself has
      // one: its Claude would stay on that
      return this.fail(
        `VS Code was started with CLAUDE_CONFIG_DIR=${process.env.CLAUDE_CONFIG_DIR}, so its Claude keeps using that. ` +
          `Start VS Code without it to use ${group.name}.`,
      );
    }
    const next = withConfigDir(this.panelVars(), value);
    if (onIt) {
      // the same account, maybe under the link's name now: no reload needed
      if (realOr(this.panelDir()) === realOr(dir) && this.panelDir() !== (value ?? link)) {
        try {
          await this.host.settings.updateOther("claudeCode", "environmentVariables", next.length ? next : undefined);
        } catch {
          // it still runs on the account
        }
      }
      void this.host.message("info", noLinks(`${group.name} is the default account: plain claude runs on it too now.`));
      return;
    }
    this.switching = true;
    try {
      await this.host.settings.updateOther("claudeCode", "environmentVariables", next.length ? next : undefined);
    } catch (err) {
      this.switching = false;
      return this.fail(`Couldn't change VS Code's Claude settings: ${(err as Error).message}`);
    }
    setTimeout(() => void this.host.reloadWindow(), 300);
    // the reload can be declined (unsaved files): then other switches count again
    setTimeout(() => (this.switching = false), 15000);
  }

  private async switchOnHost(): Promise<void> {
    const host = this.dash.currentHost;
    if (!host) {
      void this.host.message("info",
        "This window isn't connected to an SSH host (Remote-SSH), so there's no Claude account here to switch.",
      );
      return;
    }
    const groups = machineStatus(this.dash.state(), host)?.groups ?? [];
    if (groups.length < 2) {
      const hidden = machineStatus(this.dash.state(), host)?.hiddenGroups?.length ?? 0;
      void this.host.message("info",
        noLinks(
          hidden
            ? `The other Claude account${hidden === 1 ? " is" : "s are"} hidden on ${hostLabel(host)}: Claude Accounts → Show lists ${hidden === 1 ? "it" : "them"} again.`
            : `There's one Claude account on ${hostLabel(host)}, so there's nothing to switch to.`,
        ),
      );
      return;
    }
    const pick = await this.host.pick(
      groups.map((g) => ({
        label: g.title,
        description: [
          g.defaultHere ? "$(star-full) default" : "",
          g.vscodeHere ? `Claude Code on ${hostLabel(host)}` : "",
          g.plainHere ? "plain claude" : "",
        ]
          .filter((d) => d)
          .join(" · "),
        group: g,
      })),
      {
        title: `Default Claude account on ${hostLabel(host)}`,
        placeHolder: "Claude Code there (its new chats, in its other windows too) and plain claude there (~/.claude, where it's a link) run on it",
      },
    );
    if (!pick) return;
    if (pick.group.vscodeHere && pick.group.plainHere !== false) {
      void this.host.message("info", noLinks(`${pick.group.name} is the default account on ${hostLabel(host)} already.`));
      return;
    }
    if (await this.switchHost(pick.group, true))
      void this.host.message("info",
        noLinks(`${pick.group.name} is the default account on ${hostLabel(host)} now: new chats start there. Chats already open keep their account.`),
      );
  }

  // Claude Code on this window's SSH host runs on group's account from now
  // on (its new chats, its other windows there too). Written as a user
  // setting from a window connected to the host, VS Code puts this machine
  // setting into the host's Remote Settings; the Claude extension follows it.
  // asDefault: plain claude there too (the host's ~/.claude, where it's a
  // link, through accounts.py there; refused while a chat runs through it).
  async switchHost(group: Group, asDefault = false): Promise<boolean> {
    if (group.configDir === undefined) {
      this.fail(`Can't tell which folder ${group.name} has on ${hostLabel(group.host ?? "")}: that host's status comes from an older Talpy Den.`);
      return false;
    }
    let value = group.configDir;
    if (asDefault && this.backend && group.host) {
      const r = await this.backend.accounts(["--default", group.chatProfile, "--no-vscode"], group.host);
      if (!r.ok) {
        this.fail(String(r.message || `Couldn't make ${group.name} the default on ${hostLabel(group.host)}`));
        return false;
      }
      // (~/.claude may lead there now: the name terminals there use)
      if (typeof r.configDir === "string" || r.configDir === null) value = r.configDir;
    }
    const next = withConfigDir(this.panelVars(), value);
    try {
      await this.host.settings.updateOther("claudeCode", "environmentVariables", next.length ? next : undefined);
    } catch (err) {
      this.fail(`Couldn't change Claude Code's settings on ${hostLabel(group.host ?? "")}: ${(err as Error).message}`);
      return false;
    }
    void this.dash.refreshAll(); // the host's accounts and the status bar item follow
    return true;
  }

  private fail(message: string): void {
    void this.host.message("error", noLinks(message));
  }
}
