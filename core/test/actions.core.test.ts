// The actions on their host alone (no vscode): what a Delete asks before anything goes, the terminal a chat
// opens in, and which file system a new chat's folder dialog browses.

import assert from "node:assert/strict";
import * as os from "node:os";
import { test } from "node:test";
import { Actions } from "../src/actions";
import type { Answer, Backend } from "../src/agents/claudeCode/backend";
import type { Dashboard } from "../src/dashboard";
import type { AccountSwitch, EditorPort, Place, TerminalHandle, TerminalPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import type { ChatRef, Group } from "../src/shared/types";
import { FakeHost } from "./fakeHost";

// The terminals a click starts, in order (none is found running a chat)
class FakeTerminals implements TerminalPort {
  runs: { key: string; name: string; command: string; place: Place; opts?: { private?: boolean; chatOn?: string } }[] = [];
  async find(): Promise<TerminalHandle | undefined> {
    return undefined;
  }
  async run(key: string, name: string, command: string, place: Place, opts?: { private?: boolean; chatOn?: string }): Promise<TerminalHandle> {
    this.runs.push({ key, name, command, place, opts });
    return { show() {}, sendText() {} };
  }
}

const work = (host?: string) => ({
  id: "w", title: "work", name: "work", chatProfile: ".claude-work", profileKeys: [".claude-work"], sessions: [], projects: [],
  homeChatCommand: "cd /home/me 2>/dev/null; claude", ...(host ? { host } : {}),
}) as unknown as Group;

// Actions over a FakeHost, with what they ran: the backend's helpers (without the --config-dir of the machine
// the tests run on) and the terminals. currentHost: the host a Remote-SSH window is connected to; groups: this
// computer's accounts (work alone, by default), canShare: they can share chats
const setup = (opts: { currentHost?: string; answers?: Partial<Answer>[]; groups?: Group[]; canShare?: boolean } = {}) => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  const terminals = new FakeTerminals();
  const helpers: [string, string[]][] = [];
  const backend = {
    action: async (script: string, args: string[]) => {
      helpers.push([script, args.filter((a, i) => a !== "--config-dir" && args[i - 1] !== "--config-dir")]);
      return { ok: true, message: "", ...opts.answers?.shift() };
    },
  } as unknown as Backend;
  const editor = { claudePanelAvailable: async () => false } as unknown as EditorPort;
  const hosts = opts.currentHost ? [{ name: opts.currentHost, current: true, ok: true, result: { groups: [work(opts.currentHost)], cli: { installed: true } } }] : [];
  const errors: string[] = [];
  const dash = {
    demo: false, currentHost: opts.currentHost, opened() {}, isVisible: () => true, setActionError: (m: string) => void errors.push(m), setActionInfo() {},
    refresh: async () => undefined, pollHost: async () => undefined, claudeCodeInfo: () => ({ available: false, profileKey: null }),
    state: () => ({ status: { groups: opts.groups ?? [work()], cli: { installed: true }, canShare: opts.canShare }, hosts }),
  } as unknown as Dashboard;
  const actions = new Actions(fake, terminals, editor, backend, dash, {} as AccountSwitch);
  return { fake, terminals, helpers, errors, actions };
};

// A Delete is asked on its line, in the view: describeDelete gives it the question (the backend's
// --describe, which deletes nothing), and only an answer there runs delete. Removing a shared chat from
// the other accounts (Keep only on …) asks here, with a modal warning: no answer, no helper run.
test("delete with no answer deletes nothing", async () => {
  const question = "Delete “Fix the parser”? It goes to the Trash.";
  const { fake, helpers, actions } = setup({ answers: [{ question }] });
  assert.deepEqual(await actions.describeDelete("chat", "c1", ".claude-work"), { ok: true, question, message: "" });
  assert.deepEqual(helpers, [["jump.py", ["--delete-chat", "c1", "--profile", ".claude-work", "--describe"]]], "only what it would delete");
  assert.equal(fake.recorded.messages.length, 0, "the question is the view's, not a dialog of its own");

  const chat = { key: "k", sessionId: "c1", chatId: "c1", profileDir: ".claude-work", name: "Fix the parser", kind: "chat", pid: null, shared: true } as ChatRef;
  const personal = { ...work(), id: "p", title: "personal", profileKeys: [".claude-personal"], shareProfile: "personal" };
  const sharing = setup({ groups: [{ ...work(), shareProfile: "work" }, personal], canShare: true });
  sharing.fake.answer.pick = (items) => items.find((i) => i.label === "Keep only on personal…");
  await sharing.actions.share(chat);
  assert.deepEqual(sharing.fake.recorded.messages.map((m) => [m.level, m.text, m.options?.modal, m.actions]),
    [["warning", "Keep “Fix the parser” only on personal?", true, ["Keep Only on personal"]]]);
  assert.deepEqual(sharing.helpers, [], "no answer: nothing unshared");
});

// The call that reopens a chat with its own command (actions.ts: open, "A command opens it"): a terminal of
// its own, found again by the chat's key on its machine
test("opening a terminal chat on this machine runs its open command in a terminal keyed host|chat", async () => {
  const chat = {
    key: ".claude-work/c1/recent", sessionId: "c1", chatId: "c1", profileDir: ".claude-work", name: "Fix the parser", cwd: "/w/app",
    kind: "chat", pid: null, openCommand: "cd /w/app 2>/dev/null; claude --resume c1",
  } as ChatRef;
  const { terminals, helpers, errors, actions } = setup();
  await actions.open(chat);
  assert.deepEqual(terminals.runs, [{ key: "|.claude-work/c1/recent", name: "Fix the parser", command: chat.openCommand, place: { kind: "local" }, opts: { chatOn: undefined } }]);
  assert.deepEqual([helpers, errors], [[], []]);
  // an SSH host's: keyed by the host, in a terminal running ssh there
  await actions.open({ ...chat, host: "lab" });
  assert.deepEqual(terminals.runs[1], { key: "lab|.claude-work/c1/recent", name: "Fix the parser", command: chat.openCommand, place: { kind: "ssh", host: "lab" }, opts: { chatOn: "lab" } });
});

// New Chat…'s Choose folder…: a Remote-SSH window's dialog browses the host it's connected to, starting in
// the host's home folder, and the chat starts in the folder picked there; this computer's starts in its home
test("a new chat's folder dialog on a Remote-SSH window asks the remote file system", async () => {
  const { fake, terminals, actions } = setup({ currentHost: "lab" });
  const chooseFolder = (start: string) => (items: readonly { label: string }[]) =>
    items.find((i) => (i as { start?: string; choose?: string }).start === start && (i as { choose?: string }).choose === "dialog");
  fake.answer.pick = chooseFolder("terminal");
  fake.answer.choose = () => ["/home/me/proj"];
  await actions.newChat("w", "lab");
  assert.deepEqual(fake.recorded.choices, [{ kind: "folder", onRemote: true, defaultPath: "/home/me", openLabel: "Start Chat Here" }]);
  assert.equal(terminals.runs.length, 1);
  assert.match(terminals.runs[0].command, /^cd \/home\/me\/proj 2>\/dev\/null; claude( |$)/);
  assert.deepEqual(terminals.runs[0].place, { kind: "windowHost" }, "in a terminal on the window's host");
  // this computer's
  await actions.newChat("w");
  assert.deepEqual(fake.recorded.choices[1], { kind: "folder", onRemote: false, defaultPath: os.homedir(), openLabel: "Start Chat Here" });
  assert.deepEqual(terminals.runs[1].place, { kind: "local" });
});
