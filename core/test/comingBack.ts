// Coming back to a window after a while, on a host (VsCodeHost over the stub, vscodeHost.test.ts): what a real
// Notifier and Dashboard (with its AwayWatch) do on that one change of the window's state, in order. The window claims
// the lead on the focus (Notifier: focus.onDidChange); away's onBack then sums up the absence and shows it only
// in the window that leads (Dashboard.cameBack -> Notifier.digest -> isLeader); then the dashboard clears what
// finished while you weren't looking (its focus.onDidChangeUse, after away's). The host must fire onDidChange
// before onDidChangeUse (host.ts, focus): the other way round, another window still leads when the digest is
// asked for, and "While you were away" is dropped.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { mock } from "node:test";
import type { Backend } from "../src/agents/claudeCode/backend";
import type { Changes } from "../src/transitions";
import { Dashboard } from "../src/dashboard";
import type { HostServices } from "../src/host";
import { Notifier } from "../src/notify";
import type { EditorPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import { petKeyOf } from "../src/shared/model";
import type { Session, Status } from "../src/shared/types";

const AWAY_MS = 10 * 60_000; // (longer than talpyDen.awayMinutes, 5 by default)

// order: "claim" (this window took the lead), "back" (away's onBack), "digest" (While you were away, shown),
// "unseen cleared" (the dashboard's reaction); digest: its text; unseen: the chats finished unseen, before
// coming back and after
export function comingBack(host: HostServices, setFocused: (focused: boolean) => void): { order: string[]; digest: string; unseen: number[] } {
  const saved = process.env.XDG_CACHE_HOME;
  const cache = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-coming-back-"));
  process.env.XDG_CACHE_HOME = cache; // (the lead's file and away's mark: the test's own)
  let clock = Date.now();
  const now = mock.method(Date, "now", () => clock);
  mock.timers.enable({ apis: ["setTimeout", "setInterval"] }); // (no check runs, no mark is written by itself)
  const message = host.message;
  setFocused(false);
  useSettingsHost(host);
  const notifier = new Notifier(host, {} as Backend, () => undefined);
  const editor = { claudePanelAvailable: async () => false, onDidChangeClaudePanel: () => ({ dispose() {} }), localPanelProfileKey: () => "" } as unknown as EditorPort;
  const dash = new Dashboard(host, editor, {} as Backend, notifier);
  const order: string[] = [];
  let digest = "";
  try {
    const lead = notifier as unknown as { claim(): void; leaderFile: string };
    const claim = lead.claim.bind(notifier);
    lead.claim = () => {
      order.push("claim");
      claim();
    };
    const priv = dash as unknown as { status: Status; noteUnseen(c: Pick<Changes, "finished">): void; cameBack(now: number, lastUse: number): void };
    const cameBack = priv.cameBack.bind(dash);
    priv.cameBack = (at, lastUse) => {
      order.push("back");
      cameBack(at, lastUse);
    };
    host.message = ((level, text, ...rest) => {
      if (text.startsWith("While you were away")) {
        order.push("digest");
        digest = text;
      }
      return message.call(host, level, text, ...rest);
    }) as HostServices["message"];

    // the demo's chats (one of them waits for you: something to sum up), and one whose turn ends while you're away
    const status = structuredClone(demoState(clock).status!);
    const done: Session = { ...status.groups[0].sessions[0], key: "came-back", chatId: "came-back", sessionId: "came-back", state: "idle", stopped: null };
    status.groups[0].sessions.push(done);
    priv.status = status;
    dash.setVisible(true);
    setFocused(true); // (this window's first use: nothing to sum up)
    setFocused(false); // away
    priv.noteUnseen({ finished: [{ id: petKeyOf(done), session: done, took: 600_000, at: clock, stop: "" }] });
    const before = dash.unseenCount();
    clock += AWAY_MS;
    // meanwhile another window led (a live process that isn't this one)
    fs.writeFileSync(lead.leaderFile, JSON.stringify({ pid: process.ppid, at: clock }));
    order.length = 0;
    const heard = dash.onUnseen(() => order.push("unseen cleared"));
    setFocused(true); // back
    heard.dispose();
    return { order, digest, unseen: [before, dash.unseenCount()] };
  } finally {
    dash.dispose();
    notifier.dispose();
    host.message = message;
    mock.timers.reset();
    now.mock.restore();
    if (saved === undefined) delete process.env.XDG_CACHE_HOME;
    else process.env.XDG_CACHE_HOME = saved;
    fs.rmSync(cache, { recursive: true, force: true });
  }
}
