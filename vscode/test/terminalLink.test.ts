// The widgets' link to a chat's terminal: VS Code can't bring one up from
// outside (nor the panel back once closed), so the window gets it from them.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import "./useHost";
import { terminalLinkOf, Terminals } from "../src/terminals";

const stub = vscode as unknown as typeof import("./vscode-stub");

test("a terminal link names a process, and the host for a Remote-SSH window", () => {
  const link = (query: string, path = "/terminal") => terminalLinkOf({ path, query });
  assert.deepEqual(link("pid=4321"), { pid: 4321 });
  assert.deepEqual(link("pid=4321&host=lab"), { pid: 4321, host: "lab" });
  assert.deepEqual(link("pid=4321", "/terminal/"), { pid: 4321 });
  for (const q of ["", "pid=", "pid=1", "pid=0", "pid=-5", "pid=4.5", "pid=12abc", "pid=99999999999999999999"]) assert.equal(link(q), null, q);
  assert.equal(link("pid=4321", "/changes"), null);
});

function terminal(pid: number, shown: number[]) {
  return { processId: Promise.resolve(pid), exitStatus: undefined, show: () => void shown.push(pid) };
}

test("the link brings up the terminal of this window that runs the chat", async (t) => {
  const shown: number[] = [];
  const window = stub.window as unknown as { terminals: unknown[] };
  t.after(() => {
    window.terminals = [];
    stub.env.remoteName = undefined;
  });
  window.terminals = [terminal(400, shown), terminal(650, shown)];
  const terminals = new Terminals();
  // a window on this computer
  assert.equal(await terminals.showLinked({ pid: 650 }, undefined), true);
  assert.equal(await terminals.showLinked({ pid: 999 }, undefined), false);
  assert.equal(await terminals.showLinked({ pid: 400, host: "lab" }, undefined), false); // none of its terminals is on lab
  assert.deepEqual(shown, [650]);
  // a window connected to lab: its terminals run there
  stub.env.remoteName = "ssh-remote";
  shown.length = 0;
  assert.equal(await terminals.showLinked({ pid: 400, host: "lab" }, "lab"), true);
  assert.equal(await terminals.showLinked({ pid: 400, host: "lab" }, undefined), true); // no folder open: the host isn't known
  assert.equal(await terminals.showLinked({ pid: 400, host: "other" }, "lab"), false); // the same pid on another machine
  assert.equal(await terminals.showLinked({ pid: 400 }, "lab"), false); // a chat on this computer
  assert.deepEqual(shown, [400, 400]);
  terminals.dispose();
});
