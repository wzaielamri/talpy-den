// The status bar item: the panel icon of the widget, one item. A status bar
// can only show text and icons, so the count of chats that need you goes in
// the text (with the warning background), then, with two or more accounts,
// the one VS Code's Claude runs on (accountSwitch.ts), then the 5-hour usage:
// of that account, when it has numbers. Clicking it opens Talpy Den; its
// hover has a link to change the default account. The icon is Talpy, held
// still in the panel icon's pose for the state (the extension's icon font,
// media/talpy-glyphs.woff, made by tools/talpy_font.py): a spinner had VS
// Code redraw its window 60 times a second while a chat worked, about 8% of
// a core, under other windows too.

import * as vscode from "vscode";
import type { AccountShown } from "./accountSwitch";
import { settings } from "./config";
import { allGroups, claudeCodeGroup, countStates, overallState, panelWindow, tooltipLines } from "./shared/model";
import type { ViewState } from "./shared/types";

export class StatusBar implements vscode.Disposable {
  private item = vscode.window.createStatusBarItem("talpyDen.status", vscode.StatusBarAlignment.Right, 100);

  constructor() {
    this.item.name = "Talpy Den";
    this.item.command = "talpyDen.view.focus";
    this.item.text = "$(talpy-den-none)";
    this.item.show();
  }

  dispose(): void {
    this.item.dispose();
  }

  update(state: ViewState, account: AccountShown | null = null): void {
    const groups = allGroups(state.status, state.hosts);
    const counts = countStates(groups);
    const overall = overallState(groups, counts);
    const count = overall === "waiting" ? counts.waiting : overall === "working" ? counts.working : 0;
    // (the account VS Code's Claude runs on first: its chats are the ones here)
    const usage = settings.showUsageInStatusBar() ? panelWindow(groups, claudeCodeGroup(groups, state.hosts, state.claudeCode)?.id) : null;
    let tail = account ? account.name : ""; // "work 42%"
    if (usage) {
      const pct = `${Math.round(usage.window.pct)}%`;
      // (another account's usage, when VS Code's has no numbers, says whose it is: "work · personal 42%")
      const own = !account || usage.group.id === account.group?.id;
      tail = own ? `${tail} ${pct}`.trim() : `${tail} · ${usage.group.name} ${pct}`;
    }
    this.item.text = `$(talpy-den-${overall})` + (count ? ` ${count}` : "") + (tail ? (count ? " · " : " ") + tail : "");
    this.item.backgroundColor = overall === "waiting" ? new vscode.ThemeColor("statusBarItem.warningBackground") : undefined;
    this.item.color =
      overall !== "waiting" && usage && usage.window.pct >= 90 ? new vscode.ThemeColor("errorForeground") : undefined;
    const tip = new vscode.MarkdownString(undefined, true);
    tip.appendMarkdown("**Talpy Den**" + (state.demo ? " (demo data)" : "") + "\n\n");
    const lines = !state.status && state.errorText ? [state.errorText] : tooltipLines(groups, counts, state.hosts);
    for (const line of lines) tip.appendText(line + "\n\n");
    if (account) {
      // (the one link the hover can follow: switching accounts)
      tip.isTrusted = { enabledCommands: ["talpyDen.switchAccount"] };
      tip.appendMarkdown("---\n\n");
      tip.appendText(account.tip + " ");
      tip.appendMarkdown(`[$(account) ${account.link}](command:talpyDen.switchAccount)`);
    }
    this.item.tooltip = tip;
    this.item.accessibilityInformation = {
      label: `Talpy Den: ${lines[0] ?? ""}` + (account ? `. ${account.tip}` : ""),
    };
  }
}
