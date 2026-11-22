// The chat tab and what rows and notifications do with it: a click on a
// chat opens its tab; answers and replies go to pane.py with what the
// extension's own state says (the chat's request, its process), never with
// what the page claims; to-review and the tests badge; Claude's Markdown made
// into elements only (no link that runs anything).

import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, mock, test } from "node:test";
import * as vscode from "vscode";
import { host, manifest } from "./useHost";
import { ChatPanes } from "../../core/src/chatPanes";
import type { HostServices } from "../../core/src/host";
import { ChatSurfaces } from "../src/chatPane";
import { settingNames } from "../src/legacySettings";
import { VsCodeEditor } from "../src/vscodeEditor";
import { VsCodeHost } from "../src/vscodeHost";
import { demoState } from "../../core/src/shared/demo";
import { chatRefOf, clockText } from "../../core/src/shared/model";
import { awayRecap, RECAP_BUTTON, QUOTE_BUTTON, QUOTE_MENU, quoteOf, withQuote, compactCommand, compactLabel, contextNumbers, HANDOFF_PROMPT, handoffDraft, handoffNote, contextLevel, contextUsed, type Away, awayHead, awayParts, awayTarget, awayTip, shownUpTo, type ChatOptions, pickLabel, withPick, answerFor, answerKind, answersOf, answersTaken,answerText, askedShows, chatWhere, chipsAfterSend, chipsOf, chipsWanted, CHIPS_IGNORED, CHIPS_REST_MS, commandHint, commandRun, completionOf, suggestFor, type Offers, joinAnswer, clipboardCode, HOLD_MS, numberedPictures, oneChoice, pendingTaken, picturesIn, promptHistory, queuedReply, replyAnswers, replyKey, reviewPending, reviewSeen, routeHint, shownAsk, stampFresher, stopOf, testsText, contextText, contextHint, turnText, turnHint, turnTickIn, copyText, copyCut, lastReply, findCount, findIn, findParts, findStep, FOLD_LINES, FOLD_SHOWN, foldOf, lowOf, nthIn, allIn, plainOf, adoptable, BOOKMARKS_MAX, bookmarkStep, canBookmark, entryOf, keysOf, snippetOf, stateOf, staysOpen, withBookmark, withoutBookmark, type Bookmark, type PaneItem, dayBreaks, dayLabel, newBelow, newHint, newText, timeText, textScale, TEXT_SCALES, whereTag, withoutPicture, type Asks, type UsualReplies } from "../../core/src/shared/pane";
import { type BackgroundShell, SHELL_FOLD, shellFold, shellLine, shellsMore, shellsWaiting, costNote, explainQuestion, newerSides, SIDE_ACTIONS, sideAnswerOf, sideModelLabel, sideOf, sidePickLabel, sidePickOf, SIDE_PICKS, sidesOf, sidesShown, sideState, sideWarm, WARM_MS, type AskedSide, type Side, fromKeyOk, fromNote, SIDE_COST_TIP, SIDE_FROM_TIP, sideKeyOk, sideLine, sidePartAnswerOf, sidePartOf, sideSaw } from "../../core/src/shared/pane";
import { NEW_SINCE_READ_MS, newSinceAfterSend, newSinceInView, newSinceKey, newSinceLooked, newSinceOf, newSinceReading, newSinceText, type NewSince } from "../../core/src/shared/pane";
import type { ViewState } from "../../core/src/shared/types";
import { ViewHost } from "../src/view";
import { clipboardWrites, overrides, recorded } from "./vscode-stub";
import { inline, Markdown } from "../webview/util/markdown";
import { ribbonCss } from "../webview/util/ribbons";
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

// A cache a test gives itself (XDG_CACHE_HOME, which the tests after it keep), removed once the file's tests are
// done
const caches: string[] = [];
after(() => {
  for (const dir of caches.splice(0)) rmSync(dir, { recursive: true, force: true });
});
function ownCache(prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  caches.push(dir);
  return dir;
}

// Talpy Chat as extension.ts makes it: the core's ChatPanes on VS Code's surfaces (the stub's panels), on a
// VsCodeHost (useHost's: settings from stub.overrides, nothing kept), with no terminal running a chat
function chatPanes(backend: unknown, dash: unknown, actions: unknown = {}, terminals: unknown = { find: async () => undefined }, on: HostServices = host) {
  return new ChatPanes(on, backend as never, dash as never, new ChatSurfaces(vscode.Uri.file("/ext") as never, on, dash as never), actions as never,
                       terminals as never, new VsCodeEditor());
}

function panes(state: ViewState, answers: Record<string, unknown> = {}) {
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(own(args)), { ok: true, message: "Allowed", ...answers }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {} };
  const opened: unknown[] = [];
  const actions = { open: async (c: unknown) => void opened.push(c), unqueue: async () => undefined };
  const terminals = { find: async () => undefined };
  const p = chatPanes(backend, dash, actions, terminals);
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
  const path = await import("node:path");
  process.env.XDG_CACHE_HOME = ownCache("talpy-den-text-");
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
  const p = chatPanes(backend, dash);
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
    { name: "/model", about: "Set the model", kind: "Claude", run: "picker", why: "saves it as your default model for every new chat" },
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
  assert.deepEqual(commandRun("/model fable", null, tmux), { run: "terminal", name: "/model", why: "saves it as your default model for every new chat" });   // couldn't be: never /model as a message)
  assert.deepEqual(commandRun("/compact keep the tests", OFFERS, closed), { run: "here", name: "/compact", why: "" });
  assert.deepEqual(commandRun(" /config ", OFFERS, tmux), { run: "terminal", name: "/config", why: "opens Claude's settings panel" });
  assert.deepEqual(commandRun("/settings", OFFERS, tmux), { run: "terminal", name: "/config", why: "opens Claude's settings panel" });
  // /model never goes as a message (it saves your default for every new chat), with or without a name: Talpy Chat's own
  // list sets it for a background or closed chat alone (pane.py --set-options), a terminal's opens Claude's there
  assert.deepEqual(commandRun("/model fable", OFFERS, closed), { run: "picker", name: "/model", why: "saves it as your default model for every new chat", arg: "fable" });
  assert.equal(commandRun("/model", null, { where: "background", route: "background" })!.arg, "");
  assert.equal(commandRun("/model fable", OFFERS, tmux)!.run, "terminal");
  assert.equal(commandRun("/model fable", OFFERS, { where: "claude", route: "vscode" })!.run, "here");
  assert.deepEqual(commandRun("/model", OFFERS, { where: "new", route: "background" }),
                   { run: "off", name: "/model", why: "Pick its model on the ⚙ line above: it starts with it." });
  assert.equal(commandHint(commandRun("/model fable", OFFERS, closed), "background"),
               "Enter: Fable for this chat alone (in its terminal, Claude's /model would also make it your default for every new chat).");
  assert.equal(commandHint(commandRun("/model", OFFERS, closed), "background"),
               "Enter lists the models: for this chat alone (in its terminal, Claude's /model would also make it your default for every new chat).");
  // (part of a name: the list's pick; one the list doesn't know: as typed, pane.py says if it isn't one)
  assert.match(commandHint(commandRun("/model so", OFFERS, closed), "background")!, /^Enter: the model picked in the list, for this chat alone/);
  assert.match(commandHint(commandRun("/model claude-opus-5-5", OFFERS, closed), "background")!, /^Enter: claude-opus-5-5 for this chat alone/);
  // its list as you type the name: each sets it at once
  assert.deepEqual(suggestFor("/model ", OFFERS, "", closed).items.map((o) => [o.text, o.insert, !!o.run]),
                   [["Opus", "/model opus", true], ["Sonnet", "/model sonnet", true], ["Fable", "/model fable", true], ["Haiku", "/model haiku", true],
                    ["Claude's default model", "/model default", true]]);
  assert.deepEqual(suggestFor("/effort x", null, "", closed).items.map((o) => o.insert), ["/effort xhigh"]);
  assert.deepEqual(suggestFor("/model ", OFFERS, "", tmux).items, []);   // (a terminal's: Claude's own list there)
  // what it uses now, marked (its full name as the list names it); the line under the box says it
  const now: ChatOptions = { model: "claude-sonnet-5-5[1m]", effort: "high", ultracode: false, next: false };
  assert.deepEqual(suggestFor("/model ", OFFERS, "", closed, now).items.filter((o) => o.now).map((o) => [o.text, o.about]),
                   [["Sonnet", "now · for this chat alone"]]);
  assert.match(commandHint(commandRun("/model ", OFFERS, closed), "background", "", now)!, /^Now: Sonnet · High effort\. Enter lists the models/);
  // /effort turns ultracode on or off (Extra high effort, with ultracode: claude --effort ultracode)
  const effort = (o: ChatOptions) => suggestFor("/effort ", null, "", closed, o).items.map((s) => [s.text, s.insert, s.about, !!s.now]);
  assert.deepEqual(effort(now).slice(2, 6), [["High", "/effort high", "now · for this chat alone", true],
    ["Extra high", "/effort xhigh", "for this chat alone", false], ["Max", "/effort max", "for this chat alone", false],
    ["Turn ultracode on", "/effort ultracode", "with Extra high effort · for this chat alone", false]]);
  const on = withPick(now, "effort", "ultracode", "next");
  assert.deepEqual(on, { model: "claude-sonnet-5-5[1m]", effort: "xhigh", ultracode: true, next: true });
  assert.deepEqual(effort(on).slice(3, 6), [["Extra high", "/effort xhigh", "from your next message, with ultracode · for this chat alone", true],
    ["Max", "/effort max", "for this chat alone", false], ["Turn ultracode off", "/effort xhigh", "Extra high effort stays · for this chat alone", false]]);
  assert.match(commandHint(commandRun("/effort ", null, closed), "background", "", on)!,
               /^From your next message: Sonnet · Extra high effort, with ultracode\. Enter lists/);
  assert.deepEqual(withPick(on, "effort", "xhigh", "now"), { ...on, ultracode: false, next: false });
  assert.equal(pickLabel("effort", "ultracode"), "Ultracode, with Extra high effort");
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
  assert.equal(suggestFor("/mo", OFFERS, "", closed).items[0].about, "Set the model · this chat");
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
  const dash = { opened() {}, onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false, state: () => state, setVisible() {}, moreChat: () => null };
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
  const { TransitionTracker } = await import("../../core/src/transitions");
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
  const here = chatPanes({ pane: async () => assert.fail("not pane.py") }, { state: () => state, refresh: async () => undefined, pollHost: async () => undefined }, {},
    { find: async () => ({ sendText: (t: string) => typed.push(t) }) });
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: true };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
                 onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false, setActionError() {}, setActionInfo() {} };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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

// (2026-11-06) A new chat on an SSH host (or in a container) in a Talpy Chat tab: started there (pane.py --start
// --host, never this computer's extra Claude folders), the tab under "host|chat" after, that host checked at once;
// one that started without Talpy Den's permission hook says so on its line
test("a new chat on an SSH host starts there, and its tab goes on with it under the host's key", async () => {
  const NEW = "c0ffee00-0000-4000-8000-000000000002";
  const calls: string[][] = [];
  const polled: string[] = [];
  const backend = { pane: async (args: string[]) => {
    calls.push(args);
    if (args[0] === "--start") return { ok: true, how: "background", chat: NEW, id: NEW.slice(0, 8), profileDir: ".claude", message: "Started",
                                        hooked: false, hookWhy: "Talpy Den couldn't put its permission hook in place: others may write in /x" };
    return { ok: false, missing: true, message: "not yet" };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async (host?: string) => void polled.push(host ?? ""), pollHost: async (host: string) => void polled.push(host),
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false,
                 setActionError() {}, setActionInfo() {} };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
  p.openNew({ id: "lab/g", title: "main", chatProfile: ".claude", host: "lab" } as never, { path: "/srv/app", short: "~/app" });
  const panel = recorded.panels.at(-1)!;
  const keys = () => [...(p as unknown as { panes: Map<string, unknown> }).panes.keys()];
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    assert.ok(keys().some((k) => k.startsWith("lab|new-")), keys().join(" "));
    panel.receive({ type: "send", text: "Build it", how: "auto", afterTurn: false, id: 1 });
    await tick(50);
    const start = calls.find((c) => c[0] === "--start")!;
    assert.deepEqual(start.slice(-2), ["--host", "lab"]);
    assert.ok(!start.includes("--config-dir"), "this computer's extra Claude folders stay here");
    assert.deepEqual(keys(), [`lab|${NEW}`]);
    const result = panel.sent.find((m) => (m as { type: string }).type === "result") as { ok: boolean; went: boolean; warn: boolean; message: string };
    assert.deepEqual([result.ok, result.went, result.warn], [true, true, true]);
    assert.match(result.message, /^It went, but Talpy Chat can't answer what it asks \(Talpy Den couldn't put its permission hook in place/);
    assert.ok(calls.some((c) => c[0] === "--conversation" && c[1] === NEW && c.includes("lab")), "read there");
  } finally {
    p.dispose();
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
                 onState: (l: () => void) => (changed.push(l), { dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: true };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
  const p = chatPanes(backend, dash);
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
  const { droppedPaths, fileMention } = await import("../../core/src/shared/pane");
  assert.equal(fileMention("/home/me/src/app.py"), "@/home/me/src/app.py");
  assert.equal(fileMention("/home/me/My Notes/todo.md"), '@"/home/me/My Notes/todo.md"');
  assert.deepEqual(droppedPaths("file:///home/me/a%20b.txt\r\nhttps://example.com/x\n# a comment\nfile:///tmp/c.png"),
    ["/home/me/a b.txt", "/tmp/c.png"]);
  assert.deepEqual(droppedPaths(""), []);
});

test("the reply box offers commands at the start and files after @, best first", async () => {
  const { suggestFor } = await import("../../core/src/shared/pane");
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
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
  const { askShownOf } = await import("../../core/src/shared/pane");
  assert.deepEqual(askShownOf({ request: "1-a", toolUse: null, line: "Bash: make" }), { request: "1-a", toolUse: null, line: "Bash: make" });
  for (const bad of [null, "x", [], { request: 1, toolUse: null, line: "" }, { request: null, toolUse: "", line: "" },
                     { request: null, toolUse: null }, { request: "x".repeat(201), toolUse: null, line: "" }])
    assert.equal(askShownOf(bad), null);

  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(own(args)), args[0] === "--conversation" ? { ok: true, unchanged: true } : { ok: true, message: "Allowed" }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
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
  const { TransitionTracker } = await import("../../core/src/transitions");
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
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { open: async () => undefined });
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
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
                 onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
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
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
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
  let logged: VsCodeHost | undefined;
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
    const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
    const warnings: string[] = [];
    const log = { info() {}, warn: (m: string) => void warnings.push(m), error() {} } as unknown as vscode.LogOutputChannel;
    logged = new VsCodeHost(log, settingNames(manifest));
    const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false }, terminals, logged);
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
    logged?.dispose();
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
  // Claude's own guess at your reply first (a background chat's), each once, still at most 4
  const guessed = chipsOf(yesno, "asked", usual, new Set(), " yes ");
  assert.deepEqual(guessed.map((c) => [c.send, !!c.predicted, c.usual]),
                   [["yes", true, false], ["No", false, false], ["yes please", false, true], ["go", false, true]]);
  assert.match(guessed[0].title, /^Claude's own guess at your reply: sends “yes” \(Alt\+1\)/);
  assert.equal(chipsOf(null, "asked", usual, new Set(), "keep the old logs").length, 4);
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

test("context used in the header, coloured as the rows' bars, and Claude's turn so far on the working line (Plasma's words)", () => {
  const c = { used: 300000, window: 1000000, compactAt: 967000, left: 69, near: false };
  assert.equal(contextText(c), "Context 31% used");
  assert.equal(contextUsed(c), 31);
  assert.deepEqual([contextLevel(c), contextLevel({ ...c, left: 30 }), contextLevel({ ...c, left: 10 }), contextLevel({ ...c, left: 40, near: true })],
                   ["low", "medium", "high", "high"]);   // (70% and 90% as model.ts usageLevel; Claude Code saying it's close: high)
  assert.equal(contextHint(c), "300.0k of its 1.0M tokens of context are used. Claude compacts the chat on its own at about 967.0k: it sums up the conversation so far and goes on from that.");
  assert.match(contextHint({ ...c, left: 2, near: true }), / That's soon: run \/compact now to say what it keeps, if you'd rather choose\.$/);
  const t = { startedAt: 1_000_000, steps: 12 };
  assert.equal(turnText(t, 1_000_000 + 9_400), "9s · 12 steps");
  assert.equal(turnText({ ...t, steps: 1 }, 1_000_000 + 4 * 60000 + 59_000), "4m 59s · 1 step");
  assert.equal(turnText({ ...t, steps: 58 }, 1_000_000 + 8 * 60000 + 12_700), "8m 12s · 58 steps");
  assert.equal(turnText({ ...t, steps: 0 }, 1_000_000 + 60_000), "1m 0s");
  assert.equal(turnText({ ...t, steps: 0 }, 1_000_000 + 65 * 60000 + 7_000), "1h 5m 7s");
  assert.equal(turnText(t, 1_000_000 - 5000), "0s · 12 steps");   // (a host's clock a little ahead)
  assert.equal(turnHint(t, 1_000_000 + 125_000), "Claude's turn so far: 2m 5s since your message, 12 steps (its tool calls, in the Steps tab).");
  // the next change: the next second, all along
  assert.equal(turnTickIn(t, 1_000_000 + 9_400), 600);
  assert.equal(turnTickIn(t, 1_000_000 + 59_999), 1);
  assert.equal(turnTickIn(t, 1_000_000 + 60_000), 1000);
  assert.equal(turnTickIn(t, 1_000_000 + 4 * 60000 + 59_300), 700);
  assert.equal(turnTickIn(t, 1_000_000 - 5000), 1000);
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
  // (the button says so, after its ↓; with nothing new below, it's there all the same: Latest)
  assert.equal(newText(3), "3 new");
  assert.equal(newText(0), "Latest");
  assert.equal(newHint(1), "One new item below, since you scrolled up. Click to go back to the latest.");
  assert.equal(newHint(4), "4 new items below, since you scrolled up. Click to go back to the latest.");
  assert.equal(newHint(0), "Back to the latest point of the chat");
});

test("back at the newest after a read further back: the chat is read as at first again, a reach on its way is given up", async () => {
  const reads: string[][] = [];
  let release: (() => void) | null = null;
  const answer = (args: string[]) => {
    const limit = args[args.indexOf("--limit") + 1];
    if (args.includes("--reach")) return { ok: true, items: [{ kind: "you", key: "u0", text: "old", at: 1 }], more: true, stamp: "900:5/1920", limit: 1920, reach: args[args.indexOf("--reach") + 1], reached: "here" };
    return { ok: true, items: [], more: true, stamp: `800:4/${limit}` };
  };
  const backend = { pane: async (args: string[]) => {
    if (args.includes("--wait")) return { ok: true, unchanged: true };
    reads.push(own(args));
    if (args.includes("u5")) await new Promise<void>((r) => (release = r));   // (a reach that takes its time)
    return answer(args);
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  p.open({ chatId: "latest-1", sessionId: "latest-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const tick = () => new Promise((r) => setTimeout(r, 10));
  const limits = () => reads.map((a) => a[a.indexOf("--limit") + 1] + (a.includes("--reach") ? ` --reach ${a[a.indexOf("--reach") + 1]}` : ""));
  panel.show(true);
  panel.receive({ type: "ready" });
  await tick();
  panel.receive({ type: "latest" });   // (at the first read's length: nothing to read)
  await tick();
  assert.deepEqual(limits(), ["120"]);
  panel.receive({ type: "reach", key: "u0" });
  await tick();
  panel.receive({ type: "latest" });
  await tick();
  assert.deepEqual(limits(), ["120", "120 --reach u0", "120"]);
  // a reach still on its way when you go back: its length isn't taken, the newest is read after it
  panel.receive({ type: "reach", key: "u5" });
  await tick();
  panel.receive({ type: "latest" });
  await tick();
  release!();
  await tick();
  await tick();
  panel.dispose();
  assert.deepEqual(limits(), ["120", "120 --reach u0", "120", "120 --reach u5", "120"]);
  const conv = panel.sent.filter((m) => (m as { type: string }).type === "conversation").map((m) => (m as { answer: Record<string, unknown> }).answer);
  assert.deepEqual(conv.map((a) => a.stamp), ["800:4/120", "900:5/1920", "800:4/120", "800:4/120"], "the reach given up isn't shown");
});

// Since you last looked (A9): a chat that went on without you, as one line when its window shows it
// again (pane.py --away: turns.Away), Plasma's AwayLine.qml the same words
test("since you last looked: its steps, files, tests and what it waits for, in a line; the rest in its tooltip", () => {
  const a: Away = { from: "seen", since: 1000, key: "m5", stepKey: "t1", steps: 12, replies: 2, files: ["src/a.py", "b.qml"],
                    fileCount: 2, test: { command: "npm test", ok: true }, asks: "question", partial: false };
  assert.equal(awayHead(a), "Since you last looked");
  assert.deepEqual(awayParts(a), ["12 steps", "2 files changed", "tests passed", "it asks you something"]);
  assert.deepEqual(awayParts({ ...a, from: "you", steps: 1, fileCount: 1, files: ["a"], test: { command: "x", ok: false } }, true),
                   ["1 step", "1 file changed", "tests failed", "it waits for your answer"]);   // (waiting on a prompt: its row says)
  assert.equal(awayHead({ ...a, from: "you" }), "Since your last message");
  // (only replies: how many; read from after then: at least)
  assert.deepEqual(awayParts({ ...a, steps: 0, replies: 1, fileCount: 0, files: [], test: null, asks: "" }), ["1 reply"]);
  assert.deepEqual(awayParts({ ...a, partial: true, steps: 1, fileCount: 1, test: null, asks: "" }), ["1+ steps", "1+ files changed"]);
  assert.equal(awayTip({ ...a, fileCount: 11 }, "14:02"), [
    "Since a Talpy Chat window last showed this chat, at 14:02", "", "Files changed:", "  src/a.py", "  b.qml", "  and 9 more", "",
    "Tests passed: npm test", "", "Click to go to where you left. Scrolling or × closes it."].join("\n"));
  assert.equal(awayTip({ ...a, from: "you", fileCount: 0, test: null }, "Yesterday 9:15"),
               "Since your last message, at Yesterday 9:15\n\nClick to go to where you left. Scrolling or × closes it.");
  // where a click goes: Claude's first reply since, on Steps the first step
  assert.equal(awayTarget(a, false), "m5");
  assert.equal(awayTarget(a, true), "t1");
  assert.equal(awayTarget({ ...a, stepKey: "" }, true), "m5");
  // how far a window shows a chat: its newest item's time
  assert.equal(shownUpTo([{ at: 5 }, { at: 9 }, {}, { at: 7 }], 0), 9);
  assert.equal(shownUpTo([{ at: 5 }], 8), 8);
  assert.equal(shownUpTo(undefined, 3), 3);
});

// New since … (newsince.mjs, Plasma's NewSinceLine.qml too): a thin line in the conversation above the first
// item since you last looked, where Since you last looked's click goes; it goes once read (seen, then 10 s at
// the newest part), or with a message
test("new since: the line is where Since you last looked's click goes, stays for it, moves with the next one", () => {
  const a: Away = { from: "seen", since: 1000, key: "m5", stepKey: "t1", steps: 12, replies: 2, files: [], fileCount: 0,
                    test: null, asks: "", partial: false };
  const at = newSinceOf(a, null)!;
  assert.deepEqual(at, { key: "m5", stepKey: "t1", since: 1000, seen: false });
  assert.equal(newSinceKey(at, false), awayTarget(a, false));
  assert.equal(newSinceKey(at, true), awayTarget(a, true));
  assert.equal(newSinceKey({ ...at, stepKey: "" }, true), "m5");
  assert.equal(newSinceKey(null, false), "");
  assert.equal(newSinceText("14:32"), "New since 14:32");
  assert.equal(newSinceText("Yesterday 9:15"), "New since Yesterday 9:15");
  // back with nothing new (no answer, or one with nothing to point at): where it was
  assert.equal(newSinceOf(null, at), at);
  assert.equal(newSinceOf({ ...a, key: "", stepKey: "" }, at), at);
  assert.equal(newSinceOf(null, null), null);
  // back again with more: the new point
  assert.deepEqual(newSinceOf({ ...a, since: 9000, key: "m9", stepKey: "t7" }, at), { key: "m9", stepKey: "t7", since: 9000, seen: false });
  // (a line you'd seen: the new point is one you haven't)
  assert.equal(newSinceOf({ ...a, since: 9000, key: "m9" }, { ...at, seen: true })!.seen, false);
  // only steps since (no reply yet): on Steps only
  const steps = newSinceOf({ ...a, key: "" }, null)!;
  assert.equal(newSinceKey(steps, false), "");
  assert.equal(newSinceKey(steps, true), "t1");
});

test("new since: one timer, only once the line has been seen and while the window shows the chat's newest part; a message takes it", () => {
  const at: NewSince = { key: "m5", stepKey: "t1", since: 1000, seen: true };
  assert.equal(NEW_SINCE_READ_MS, 10000);
  assert.equal(newSinceReading(at, true, true), true);
  assert.equal(newSinceReading({ ...at, seen: false }, true, true), false);   // (never in view yet)
  assert.equal(newSinceReading(at, false, true), false);   // (the window hidden)
  assert.equal(newSinceReading(at, true, false), false);   // (scrolled up)
  assert.equal(newSinceReading(null, true, true), false);   // (no line: nothing runs)
  assert.equal(newSinceAfterSend(at, "fix the lexer"), null);
  assert.equal(newSinceAfterSend(at, " /recap "), at);   // (Since you last looked's Recap: still catching up)
  assert.equal(newSinceAfterSend(null, "go on"), null);
  assert.equal(newSinceAfterSend({ ...at, seen: false }, "go on"), null);   // (seen or not)
});

// Seen: once the line has been in view with the window shown (newSinceLooked); in view: all of it between
// the view's top and bottom (newSinceInView)
test("new since: seen once it's been in view with the window shown, not before", () => {
  const at: NewSince = { key: "m5", stepKey: "t1", since: 1000, seen: false };
  assert.deepEqual(newSinceLooked(at, true, true), { ...at, seen: true });
  assert.equal(newSinceLooked(at, true, false), at);    // (out of view)
  assert.equal(newSinceLooked(at, false, true), at);    // (in view, the window hidden)
  const seen = newSinceLooked(at, true, true)!;
  assert.equal(newSinceLooked(seen, true, false), seen);   // (seen stays seen: no new object)
  assert.equal(newSinceLooked(null, true, true), null);
  assert.equal(newSinceInView(10, 14, 600), true);
  assert.equal(newSinceInView(-5, 14, 600), false);   // (cut at the top)
  assert.equal(newSinceInView(590, 14, 600), false);  // (cut at the bottom)
  assert.equal(newSinceInView(586, 14, 600), true);
  assert.equal(newSinceInView(10, 0, 600), false);    // (not drawn)
});

// Its 10 s, as both front ends run them: one timer, started when newSinceReading turns true, stopped when it
// turns false, taking the line when it ends; each moment says what the window shows from then on
type Moment = { at: number; shown: boolean; atEnd: boolean; inView: boolean };
function lineAfter(at: NewSince | null, moments: Moment[], end: number): NewSince | null {
  let started: number | null = null;
  for (const m of moments) {
    if (started !== null && m.at - started >= NEW_SINCE_READ_MS) return null;   // (it went before this moment)
    at = newSinceLooked(at, m.shown, m.inView);
    started = newSinceReading(at, m.shown, m.atEnd) ? started ?? m.at : null;
  }
  return started !== null && end - started >= NEW_SINCE_READ_MS ? null : at;
}
test("new since: never seen, it stays past 10 s at the end", () => {
  const at = newSinceOf({ key: "m5", stepKey: "t1", since: 1000 }, null);
  // (back at the end, the line out of view above it, the bar showing)
  const back: Moment[] = [{ at: 0, shown: true, atEnd: true, inView: false }];
  assert.notEqual(lineAfter(at, back, 10_000), null);
  assert.notEqual(lineAfter(at, back, 600_000), null);
  // (in view while the window was hidden doesn't count)
  assert.notEqual(lineAfter(at, [{ at: 0, shown: false, atEnd: true, inView: true }, { at: 1000, shown: true, atEnd: true, inView: false }], 60_000), null);
});
test("new since: seen, then 10 s at the end, it goes", () => {
  const at = newSinceOf({ key: "m5", stepKey: "t1", since: 1000 }, null);
  // (Since you last looked's click: the line in view, not at the end; then down to the end)
  const read: Moment[] = [{ at: 0, shown: true, atEnd: false, inView: true }, { at: 3000, shown: true, atEnd: true, inView: false }];
  assert.notEqual(lineAfter(at, read, 12_999), null);
  assert.equal(lineAfter(at, read, 13_000), null);
  // (the new part fits: in view at the end)
  assert.equal(lineAfter(at, [{ at: 0, shown: true, atEnd: true, inView: true }], 10_000), null);
});
test("new since: seen, then scrolled away before the 10 s, it stays", () => {
  const at = newSinceOf({ key: "m5", stepKey: "t1", since: 1000 }, null);
  const away: Moment[] = [{ at: 0, shown: true, atEnd: true, inView: true }, { at: 6000, shown: true, atEnd: false, inView: false }];
  assert.notEqual(lineAfter(at, away, 600_000), null);
  // (hidden before the 10 s: the same)
  assert.notEqual(lineAfter(at, [{ at: 0, shown: true, atEnd: true, inView: true }, { at: 6000, shown: false, atEnd: true, inView: false }], 600_000), null);
  // (back at the end later: 10 s from then)
  const back = [...away, { at: 20_000, shown: true, atEnd: true, inView: false }];
  assert.notEqual(lineAfter(at, back, 29_999), null);
  assert.equal(lineAfter(at, back, 30_000), null);
});

// A chat's tab tells pane.py how far it showed the chat (--seen), and asks what it did since a
// window last showed it once, when it first reads it and again once shown again (--away)
// The context tag's menu (Plasma's CompactMenu.qml: the same words): Compact now with what it must keep,
// and Continue in a new chat (Claude's handoff note, once its turn is over, in a new chat's box)
test("compact now and continue in a new chat: the command, the handoff note once it's written, the new chat's draft", () => {
  assert.equal(compactCommand(""), "/compact");
  assert.equal(compactCommand("  the parser work,\n the open bug "), "/compact the parser work, the open bug");
  assert.equal(compactLabel(false), "Compact now");
  assert.equal(compactLabel(true), "Compact when this turn ends");
  assert.equal(contextNumbers({ used: 300000, window: 1000000, compactAt: 967000, left: 69, near: false }),
               "300.0k of 1.0M tokens used · Claude compacts on its own at about 967.0k");
  const items: PaneItem[] = [
    { kind: "you", key: "u1", text: "fix it", at: 1 },
    { kind: "claude", key: "m1", text: "Done.", at: 2 },
    { kind: "you", key: "u2", text: HANDOFF_PROMPT, at: 3 },
    { kind: "claude", key: "m2/thinking", text: "Summing up the work", thinking: true, at: 4 },
    { kind: "claude", key: "m2", text: "Goal: fix the parser.", at: 5 },
    { kind: "tool", key: "t1", name: "Read", line: "Read a.py", status: "ok", input: "", output: "", summary: "", at: 6 },
    { kind: "claude", key: "m3", text: "Left: the lexer.", at: 7 },
  ];
  assert.equal(handoffNote(items, true), "Goal: fix the parser.\n\nLeft: the lexer.");   // (its replies after it, no thinking line)
  assert.equal(handoffNote(items, false), null);   // (still writing)
  assert.equal(handoffNote(items.slice(0, 3), true), null);   // (asked, nothing written)
  assert.equal(handoffNote(items.slice(0, 2), true), null);   // (never asked)
  assert.equal(handoffDraft("fix parser", "Goal: x."), "Continuing from the chat “fix parser”. Its handoff note:\n\nGoal: x.");
});

// Since you last looked's recap: Claude's own (no request) when written after then, else the /recap you ran
test("since you last looked: Claude's recap, its own after then or the /recap you ran from the line", () => {
  const a: Away = { from: "seen", since: 5000, key: "", stepKey: "", steps: 3, replies: 1, files: [], fileCount: 0, test: null, asks: "", partial: false };
  const items: PaneItem[] = [
    { kind: "you", key: "r1", text: "/recap", command: { output: "An old recap." }, at: 1000 },
    { kind: "claude", key: "m1", text: "Done.", at: 6000 },
  ];
  assert.equal(awayRecap(a, null, items, null), "");   // (nothing asked: an old /recap isn't this one)
  assert.equal(awayRecap(a, { text: "You asked …; next: merge.", at: 7000 }, items, null), "You asked …; next: merge.");
  assert.equal(awayRecap(a, { text: "Before you left.", at: 4000 }, items, null), "");   // (older than then)
  const before = new Set(["r1"]);
  assert.equal(awayRecap(a, null, items, before), "");   // (asked: not in yet)
  const ran = [...items, { kind: "you" as const, key: "r2", text: "/recap", command: { output: "\x1b[1mThe parser is fixed.\x1b[0m " }, at: 8000 }];
  assert.equal(awayRecap(a, null, ran, before), "The parser is fixed.");
  assert.equal(RECAP_BUTTON, "Recap");
});

// Quote in reply (quote.mjs, Plasma's too): a selection as a Markdown quote at the top of the box
test("quote in reply: each line quoted, blank runs one, the cursor under it, what you wrote kept below", () => {
  assert.equal(quoteOf("Use weeksInYear(date)\n\n\n  and a test\n"), "> Use weeksInYear(date)\n>\n>   and a test");
  assert.equal(quoteOf("\n\n  \n"), "");
  assert.equal(quoteOf("a\u2029b"), "> a\n> b");   // (Qt's paragraph separator)
  assert.ok(quoteOf("x".repeat(5000)).endsWith("…"));
  const q = withQuote("", "Should I merge?");
  assert.deepEqual(q, { text: "> Should I merge?\n\n", cursor: 19 });
  const kept = withQuote("  yes, but first", "Should I merge?");
  assert.equal(kept.text, "> Should I merge?\n\nyes, but first");
  assert.equal(kept.text.slice(kept.cursor), "yes, but first");
  assert.deepEqual(withQuote("draft", "  "), { text: "draft", cursor: 5 });   // (nothing selected: as it was)
  assert.equal(QUOTE_BUTTON, "Reply to this");
  assert.equal(QUOTE_MENU, "Quote in reply");
});

test("Continue in a new chat opens a new chat in the same account and folder with the note in its box, not sent", async () => {
  const calls: string[][] = [];
  const backend = { pane: async (args: string[]) => (calls.push(args), args[0] === "--conversation" ? { ok: true, unchanged: true } : { ok: true }) };
  const state = demoState(NOW);
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: true };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  const row = state.status!.groups[0].sessions[0];
  p.open(chatRefOf(row));
  const old = recorded.panels.at(-1)!;
  const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
  try {
    old.show(true);
    old.receive({ type: "ready" });
    await tick();
    old.receive({ type: "handoff", text: "Continuing from the chat “x”. Its handoff note:\n\nGoal: y." });
    await tick();
    const fresh = recorded.panels.at(-1)!;
    assert.notEqual(fresh, old, "a new chat's tab");
    fresh.show(true);
    fresh.receive({ type: "ready" });
    await tick();
    assert.deepEqual(fresh.sent.filter((m) => (m as { type: string }).type === "prefill"),
                     [{ type: "prefill", text: "Continuing from the chat “x”. Its handoff note:\n\nGoal: y." }]);
    assert.ok(!fresh.sent.some((m) => (m as { type: string }).type === "startWith"), "not sent: you read it and send it");
    assert.ok(!calls.some((c) => c[0] === "--start"), "nothing started");
  } finally {
    p.dispose();
  }
});

test("a chat's tab asks what the chat did since you last looked: when it first reads it and once it shows again", async () => {
  const calls: string[][] = [];
  const items = [{ kind: "you", key: "u1", text: "hi", at: 5000 }, { kind: "claude", key: "m1", text: "Done", at: 9000 }];
  const away = { from: "seen", since: 4000, key: "m1", stepKey: "m1", steps: 0, replies: 1, files: [], fileCount: 0, test: null, asks: "", partial: false };
  const backend = { pane: async (args: string[]) => {
    if (args[0] !== "--conversation") return { ok: true };
    calls.push(args);
    if (args.includes("--wait")) return new Promise(() => {});   // (the watcher: nothing new)
    return args.includes("--if-changed") ? { ok: true, unchanged: true }
      : { ok: true, items, more: false, stamp: "10:1/120", ...(args.includes("--away") ? { away } : {}) };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  p.open({ chatId: "looked", sessionId: "looked", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
  try {
    panel.show(true);
    panel.receive({ type: "ready" });
    await tick();
    const reads = calls.filter((c) => !c.includes("--wait"));
    assert.ok(reads[0].includes("--away") && !reads[0].includes("--seen"), "the first read asks, having shown nothing");
    assert.deepEqual(panel.sent.filter((m) => (m as { type: string }).type === "away"), [{ type: "away", away }]);
    const watch = calls.find((c) => c.includes("--wait"))!;
    assert.deepEqual(watch.slice(watch.indexOf("--seen"), watch.indexOf("--seen") + 2), ["--seen", "9000"]);
    assert.ok(!watch.includes("--away"));
    panel.show(false);
    panel.show(true);
    await tick();
    const again = calls.filter((c) => !c.includes("--wait")).at(-1)!;
    assert.ok(again.includes("--away") && again.includes("--if-changed"), "shown again: asked again");
    assert.deepEqual(again.slice(again.indexOf("--seen"), again.indexOf("--seen") + 2), ["--seen", "9000"]);
    assert.equal(panel.sent.filter((m) => (m as { type: string }).type === "away").length, 1, "nothing new: nothing said");
  } finally {
    p.dispose();
  }
});

// Talpy Chat's keys (A10): one table for the ? list and the tooltips (keys.mjs, the
// widget's too); each action is a command whose key applies only while a chat tab has
// the focus (not with it in the terminal or the side bar: editorAreaFocus)
test("bookmarks (bookmarks.mjs, Plasma's too): Claude's replies and your messages once they're in the chat; their first words on a line; the list in the chat's order, 100 at most", () => {
  const you = (key: string, more: Partial<PaneItem> = {}): PaneItem => ({ kind: "you", key, text: "hi", at: 5, ...more });
  assert.equal(canBookmark({ kind: "claude", key: "msg_1", text: "a", at: 1 }), true);
  assert.equal(canBookmark(you("0b1c-uuid")), true);
  assert.equal(canBookmark(you("queued-1762400000000")), true);   // (keyed by its enqueue: it's in the chat)
  for (const not of [{ kind: "claude", key: "msg_1/thinking", thinking: true }, { kind: "tool", key: "toolu_1" }, { kind: "note", key: "n1" },
                     { kind: "you", key: "pending-3" }, { kind: "you", key: "u1", status: "sending" }, { kind: "you", key: "u1", status: "held" },
                     { kind: "you", key: "u1", queued: true }, { kind: "you", key: "u1", until: 99 }, { kind: "you", key: "u1", sending: true },
                     { kind: "you", key: "toolu_1/answer", answered: "question" }, { kind: "you", key: "-rf" }, { kind: "you", key: "" }])
    assert.equal(canBookmark({ at: 1, ...not } as PaneItem), false, JSON.stringify(not));
  assert.equal(canBookmark(null), false);

  assert.equal(snippetOf({ kind: "claude", key: "m", at: 1, text: "## Done\n\n- **all** `tests` pass\n- [docs](https://x.org)" }), "Done all tests pass docs");
  assert.equal(snippetOf(you("u", { text: "look [Image: /tmp/a.png] and [Image: /tmp/b.png] and [Image: /tmp/a.png]" })), "look [Image #1] and [Image #2] and [Image #1]");
  assert.equal(snippetOf(you("u", { text: "!ls -la", command: { shell: true } })), "ls -la");
  const long = snippetOf({ kind: "claude", key: "m", at: 1, text: "word ".repeat(60) });
  assert.equal(long.length, 140);
  assert.ok(long.endsWith("word…"), long);
  assert.equal(snippetOf({ kind: "claude", key: "m", at: 1, text: "x".repeat(140) }), "x".repeat(140));   // (140 fit)
  assert.deepEqual(entryOf(you("u", { at: 7.6, text: "one\ntwo" }), 99), { key: "u", kind: "you", at: 7, text: "one two", made: 99 });
  assert.equal(entryOf(you("u", { at: null }), 99).at, 0);

  const m = (key: string, at: number, made = 1): Bookmark => ({ key, kind: "claude", at, text: key, made });
  const list = withBookmark([m("b", 20), m("a", 10)], m("c", 15))!;
  assert.deepEqual(list.map((x) => x.key), ["a", "c", "b"]);
  assert.deepEqual(withBookmark(list, m("c", 15, 50))!.map((x) => x.made), [1, 1, 1]);   // (one a message: the first stays)
  assert.deepEqual(withBookmark([m("x", 5, 9), m("y", 5, 3)], m("z", 5, 6))!.map((x) => x.key), ["y", "z", "x"]);   // (same time: by when it was bookmarked)
  assert.deepEqual(withoutBookmark(list, "c").map((x) => x.key), ["a", "b"]);
  assert.deepEqual(withoutBookmark(list, "nope").map((x) => x.key), ["a", "c", "b"]);
  const full = Array.from({ length: BOOKMARKS_MAX }, (_, i) => m("k" + i, i));
  assert.equal(withBookmark(full, m("one-more", 1000)), null);
  assert.equal(withBookmark(full, m("k3", 3))!.length, BOOKMARKS_MAX);   // (one it has: no change, not refused)
  assert.deepEqual(keysOf(list), { a: true, c: true, b: true });
});

test("bookmarks: where each one is, Alt+↑ / Alt+↓ from what you read, and which answer's list is taken", () => {
  const m = (key: string): Bookmark => ({ key, kind: "claude", at: 1, text: key, made: 1 });
  const loaded = new Map([["a", 0], ["b", 1]]);
  assert.equal(stateOf(m("a"), loaded, true, false), "here");
  assert.equal(stateOf(m("a"), { a: 0 }, true, false), "here");
  assert.equal(stateOf(m("z"), loaded, true, false), "earlier");   // (Show earlier, or a reach, reads it)
  assert.equal(stateOf(m("z"), loaded, true, true), "far");        // (further back than the most the tab shows)
  assert.equal(stateOf(m("z"), loaded, false, false), "gone");     // (all of the chat is there: it isn't)
  assert.equal(stateOf(m("z"), loaded, true, false, { z: "gone" }), "gone");
  assert.equal(stateOf(m("z"), loaded, true, false, { z: "far" }), "far");
  assert.equal(stateOf(m("toString"), {}, false, false), "gone");   // (an object's own keys only)

  const list = ["e1", "e2", "f", "g", "a", "b", "c"].map(m);
  const states = { e1: "earlier", e2: "earlier", f: "far", g: "gone", a: "here", b: "here", c: "here" } as const;
  const tops = { a: 100, b: 500, c: 900 };
  assert.deepEqual(bookmarkStep(list, states, tops, 0, false), { key: "a" });
  assert.deepEqual(bookmarkStep(list, states, tops, 100, false), { key: "b" });     // (the one at the top is the one you read)
  assert.deepEqual(bookmarkStep(list, states, tops, 98, false), { key: "b" });      // (within 4 px)
  assert.deepEqual(bookmarkStep(list, states, tops, 900, false), { end: true });    // (past the last: the end)
  assert.deepEqual(bookmarkStep(list, states, tops, 900, true), { key: "b" });
  assert.deepEqual(bookmarkStep(list, states, tops, 600, true), { key: "b" });
  assert.deepEqual(bookmarkStep(list, states, tops, 100, true), { reach: "e2" });   // (the newest further back; far and gone skipped)
  assert.equal(bookmarkStep(["f", "g", "a"].map(m), states, tops, 50, true), null);
  assert.deepEqual(bookmarkStep([], {}, {}, 0, false), { end: true });
  // Plasma, its rows made a few at a time: one in the list whose row isn't made yet has no top; by its
  // place in the list (order) against the row at the view's top (viewIndex), it's below or above, not past the end
  const order = { a: 10, b: 50, c: 90 };
  assert.deepEqual(bookmarkStep(list, states, { a: 100 }, 100, false, order, 10), { key: "b" });   // (b and c not made)
  assert.deepEqual(bookmarkStep(list, states, {}, 100, false, order, 60), { key: "c" });
  assert.deepEqual(bookmarkStep(list, states, {}, 100, false, order, 95), { end: true });          // (none later at all: the end)
  assert.deepEqual(bookmarkStep(list, states, { c: 900 }, 900, true, order, 90), { key: "b" });    // (a and b not made)
  assert.deepEqual(bookmarkStep(list, states, {}, 0, true, order, 40), { key: "a" });
  assert.deepEqual(bookmarkStep(list, states, {}, 0, true, order, 5), { reach: "e2" });            // (none loaded above: further back)
  assert.deepEqual(bookmarkStep(list, states, { b: 500 }, 0, false, order, 0), { key: "a" });     // (a not made, before b: a first)

  assert.equal(adoptable(5, false, 5), true);
  assert.equal(adoptable(5, false, 7), true);
  assert.equal(adoptable(5, false, 4), false);     // (an older list)
  assert.equal(adoptable(5, true, 9), false);      // (a change of ours on its way)
  assert.equal(adoptable(0, false, undefined), true);
  assert.equal(adoptable(3, false, undefined), false);
  assert.equal(staysOpen(780, 260, false), true);
  assert.equal(staysOpen(700, 260, false), false);
  assert.equal(staysOpen(300, 260, true), true);
});

test("bookmarks' ribbons: one rule for them all, in place of each one's dot or ›, nothing without bookmarks", () => {
  const g = globalThis as { CSS?: { escape(s: string): string } };
  const had = g.CSS;
  g.CSS = { escape: (s: string) => s.replace(/[^A-Za-z0-9_-]/g, (c) => "\\" + c) };   // (a browser's CSS.escape, for these keys)
  try {
    const m = (key: string) => ({ key, kind: "claude", at: 1, text: "", made: 1 }) as Bookmark;
    assert.equal(ribbonCss([]), "");
    const css = ribbonCss([m("msg_1"), m("u.2")]);
    assert.ok(css.startsWith('.pane-list>:is([data-key="msg_1"],[data-key="u\\.2"])>.pane-gutter{'), css);
    assert.equal(css.split("{").length, 2, "one rule");
    assert.ok(css.includes("background:var(--pane-mark,var(--pane-claude))") && css.includes("mask:var(--pane-ribbon) center/.7em .9em no-repeat"));
    assert.ok(!/content:|position:|::after/.test(css), "no box of its own: nothing to lay out again");
  } finally {
    g.CSS = had;
  }
});

test("a bookmark is written by pane.py --bookmark, a host's chat's with --host (kept here), one write at a time in click order", async () => {
  const calls: string[][] = [];
  const done: string[] = [];
  let v = 10;
  const backend = { pane: async (args: string[]) => {
    if (args[0] !== "--bookmark") return { ok: true, unchanged: true };
    calls.push(own(args));
    // (the first write is the slow one: the second still waits for it)
    await new Promise((r) => setTimeout(r, calls.length === 1 ? 40 : 1));
    done.push(args.includes("--off") ? "off" : "on");
    return args[3] === "bad" ? { ok: false, message: "Which message?", bookmarks: [], bookmarksV: v }
      : { ok: true, message: "", bookmarks: args.includes("--off") ? [] : [{ key: args[3], kind: "claude", at: 5, text: "Done", made: 6 }], bookmarksV: ++v };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
  p.open({ chatId: "mark-1", sessionId: "mark-1", profileDir: ".claude-work", name: "x", host: "lab" } as never);
  const panel = recorded.panels.at(-1)!;
  const answers = () => panel.sent.filter((m) => (m as { type: string }).type === "bookmarks");
  panel.receive({ type: "bookmark", id: 1, key: "m1", on: true, kind: "claude", at: 5, text: "Done\n  and   dusted" });
  panel.receive({ type: "bookmark", id: 2, key: "m1", on: false, kind: "claude", at: 5, text: "" });
  await new Promise((r) => setTimeout(r, 80));
  assert.deepEqual(calls, [
    ["--bookmark", "mark-1", "--key", "m1", "--kind", "claude", "--at", "5", "--text", "Done and dusted", "--profile", ".claude-work", "--host", "lab"],
    ["--bookmark", "mark-1", "--key", "m1", "--off", "--profile", ".claude-work", "--host", "lab"],
  ]);
  assert.deepEqual(done, ["on", "off"], "the second waited for the first");
  assert.deepEqual(answers(), [
    { type: "bookmarks", id: 1, chatId: "mark-1", ok: true, message: "", bookmarks: [{ key: "m1", kind: "claude", at: 5, text: "Done", made: 6 }], bookmarksV: 11 },
    { type: "bookmarks", id: 2, chatId: "mark-1", ok: true, message: "", bookmarks: [], bookmarksV: 12 },
  ]);
  // (a refusal is answered as one, with why; what isn't a message's key, or a kind that isn't yours
  // or Claude's, doesn't go to pane.py at all)
  panel.receive({ type: "bookmark", id: 3, key: "bad", on: false, kind: "you", at: 0, text: "" });
  for (const m of [{ key: "-x" }, { key: "pending-3" }, { key: "t1/answer" }, { kind: "tool" }, { id: "4" }, { text: 7 }])
    panel.receive({ type: "bookmark", id: 4, key: "m2", on: true, kind: "you", at: 1, text: "Hi", ...m });
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(calls.length, 3);
  assert.deepEqual(answers().at(-1), { type: "bookmarks", id: 3, chatId: "mark-1", ok: false, message: "Which message?", bookmarks: [], bookmarksV: 12 });
  // this computer's chat: its config folders, no --host
  p.open({ chatId: "mark-2", sessionId: "mark-2", profileDir: ".claude", name: "y" } as never);
  recorded.panels.at(-1)!.receive({ type: "bookmark", id: 1, key: "u1", on: true, kind: "you", at: 7, text: "Fix it" });
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(calls.at(-1), ["--bookmark", "mark-2", "--key", "u1", "--kind", "you", "--at", "7", "--text", "Fix it", "--profile", ".claude"]);
  p.dispose();
});

test("a bookmark further back than what's shown: the next read has --reach, and its answer's limit is taken before its stamp is compared", async () => {
  const reads: string[][] = [];
  const answer = (args: string[]) => {
    const limit = args[args.indexOf("--limit") + 1];
    if (args.includes("--reach")) return { ok: true, items: [{ kind: "you", key: "u0", text: "old", at: 1 }], more: true, stamp: "900:5/480", limit: 480, reach: "u0", reached: "here" };
    return { ok: true, items: [], more: true, stamp: `800:4/${limit}` };
  };
  const backend = { pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true } : (reads.push(own(args)), answer(args))) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  p.open({ chatId: "reach-1", sessionId: "reach-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const tick = () => new Promise((r) => setTimeout(r, 10));
  panel.show(true);
  panel.receive({ type: "ready" });
  await tick();
  panel.receive({ type: "reach", key: "u0" });
  await tick();
  panel.receive({ type: "reach", key: "--limit" });   // (not a message's key: nothing read)
  panel.receive({ type: "more" });
  await tick();
  panel.dispose();
  const conv = panel.sent.filter((m) => (m as { type: string }).type === "conversation").map((m) => (m as { answer: Record<string, unknown> }).answer);
  assert.deepEqual(reads.map((a) => a.slice(0, 4).concat(a.includes("--reach") ? a.slice(4, 6) : [])), [
    ["--conversation", "reach-1", "--limit", "120"],
    ["--conversation", "reach-1", "--limit", "120", "--reach", "u0"],
    ["--conversation", "reach-1", "--limit", "960"],   // (Show earlier doubles from the reach's 480)
  ]);
  assert.ok(!reads[1].includes("--if-changed"), "a reach reads in any case");
  assert.deepEqual([conv[1].reach, conv[1].reached, conv[1].stamp], ["u0", "here", "900:5/480"], "taken: read for the limit it needed");
  assert.equal(conv.length, 3);
  // (as stampFresher sees it: refused at the old limit, taken at the new one)
  assert.equal(stampFresher("900:5/480", "800:4/120", 120), false);
  assert.equal(stampFresher("900:5/480", "800:4/120", 480), true);
  assert.equal(stampFresher("800:4/480", "900:5/480", 480), false, "and an older one at that limit isn't");
});

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
      // (a chat's tab with the focus, or Talpy Chat's view in the side bar with it: talpyDen.chatPlace)
      if (command.startsWith("talpyDen.chat."))
        assert.equal(b!.when, "(activeWebviewPanelId == 'talpyDen.chat' && editorAreaFocus) || focusedView == 'talpyDen.chatView'", command);
    }
  }
  // (each of the tab's commands is in the table, but Stop and the list itself: Esc and ? are the page's)
  for (const c of commands) if (c.startsWith("talpyDen.chat.")) assert.ok(named.has(c) || ["talpyDen.chat.stop", "talpyDen.chat.keys"].includes(c), c);
  // (in the command palette only where they act)
  const palette: { command: string; when: string }[] = manifest.contributes.menus.commandPalette;
  for (const c of commands)
    if (c.startsWith("talpyDen.chat."))
      assert.equal(palette.find((m) => m.command === c)?.when, "activeWebviewPanelId == 'talpyDen.chat' || view.talpyDen.chatView.visible", c);
  // Talpy Chat's view in the secondary side bar: shown only where the extension says the bar is there
  // (an older VS Code would list a view of a container it doesn't know under Explorer)
  assert.deepEqual(manifest.contributes.viewsContainers.secondarySidebar.map((c: { id: string }) => c.id), ["talpyDenChat"]);
  assert.deepEqual(manifest.contributes.views.talpyDenChat, [{ type: "webview", id: "talpyDen.chatView", name: "Talpy Chat", when: "talpyDen.chatSideBar" }]);
  assert.equal(keyText("sendNow", "vscode"), "Ctrl+Enter");
  assert.equal(keyText("sendNow", "vscode", true), "Cmd+Enter");
  assert.equal(withKey("Send now", "sendNow", "plasma"), "Send now (Ctrl+Enter)");
  assert.equal(withKey("Your other windows", "chats", "vscode"), "Your other windows");   // (none there: VS Code's own)
  assert.equal(withKey("Bookmark this reply", "bookmark", "vscode", true), "Bookmark this reply (Cmd+D)");
  // (each command of the tab goes to the page as the id its onKey takes)
  const { CHAT_KEYS } = await import("../src/chatPane");
  for (const [command, id] of [["toggleBookmark", "bookmark"], ["bookmarks", "bookmarks"], ["previousBookmark", "bookmarkUp"], ["nextBookmark", "bookmarkDown"]])
    assert.equal(CHAT_KEYS["talpyDen.chat." + command], id, command);
});

test("Esc does the nearest thing first, one thing a press: Stop only once nothing is open", () => {
  assert.equal(escTarget({ menu: true, big: true, list: true, help: true, ghost: true, stop: true }), "menu");
  assert.equal(escTarget({ big: true, list: true, stop: true }), "big");
  assert.equal(escTarget({ list: true, help: true, stop: true }), "list");
  assert.equal(escTarget({ find: true, bookmarks: true, help: true }), "find");
  assert.equal(escTarget({ bookmarks: true, help: true, ghost: true, stop: true }), "bookmarks");
  assert.equal(escTarget({ help: true, ghost: true, stop: true }), "help");
  assert.equal(escTarget({ ghost: true, stop: true }), "ghost");
  assert.equal(escTarget({ stop: true }), "stop");
  assert.equal(escTarget({ stop: false }), "");
  assert.equal(escTarget({}), "");
  assert.deepEqual([...ESC_ORDER], ["menu", "big", "list", "find", "bookmarks", "help", "ghost", "stop"]);
});

test("a key's command goes to the chat tab in front, and only to it", async () => {
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes({ pane: async () => ({ ok: true, unchanged: true }) }, dash);
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
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
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
  // (a thinking line isn't Claude's reply)
  assert.equal(lastReply([{ kind: "claude", key: "m3", text: "three", at: 3 },
                          { kind: "claude", key: "m4/thinking", text: "Pushing it.", thinking: true, at: 4 }])?.key, "m3");
  p.dispose();
});

// Search (A3) and folding (A6): find.mjs, the widget's too, so Plasma and VS Code count the same
// matches and fold the same texts. Made-up text only
const lines = (n: number, word = "line") => Array.from({ length: n }, (_, i) => `${word} ${i + 1}`).join("\n");

test("folding: past about 40 lines (a long paragraph counts as the lines it wraps to), its first 24 show", () => {
  assert.equal(foldOf(""), null);
  assert.equal(foldOf(lines(FOLD_LINES)), null);
  assert.equal(foldOf("word ".repeat(700)), null);   // (3500 characters: 35 lines of 100)
  const f = foldOf(lines(FOLD_LINES + 17))!;
  assert.equal(f.shown, lines(FOLD_SHOWN));
  assert.equal(f.more, FOLD_LINES + 17 - FOLD_SHOWN);
  assert.ok(lines(FOLD_LINES + 17).slice(f.at).startsWith("line 25\n"));
  // one long paragraph: as much as fits, to a word's end, then …
  const para = Array.from({ length: 1200 }, (_, i) => `w${i}`).join(" ");
  const p = foldOf(para)!;
  assert.ok(p.shown.endsWith(" …"), p.shown.slice(-20));
  assert.ok(p.shown.length <= FOLD_SHOWN * 100 + 2);
  assert.ok(para.slice(p.at).startsWith(" w"), "cut between words");
  // a code block cut in two is closed again, with its own marks
  const code = "Here it is:\n\n~~~python\n" + lines(60, "x =") + "\n~~~\nDone.";
  assert.ok(foldOf(code)!.shown.endsWith("\n~~~"));
  assert.ok(!foldOf(code, "plain")!.shown.endsWith("~~~"));
  // a command's output: cut between lines only (never in a colour's code)
  const ansi = Array.from({ length: 50 }, (_, i) => `\x1b[3${i % 7}m${"z".repeat(150)}\x1b[0m`).join("\n");
  const a = foldOf(ansi, "ansi")!;
  assert.equal(a.shown.split("\n").length, FOLD_SHOWN / 2);
  assert.ok(a.shown.endsWith("\x1b[0m"));
});

test("search reads Markdown as the text it shows: no marks, a link's words, code as it is", () => {
  assert.equal(plainOf("## The plan\n\n- **Fix** the `parser` in [the docs](https://example.org/x)\n1. _then_ ~~not~~ test"),
               "The plan\n\nFix the parser in the docs\nthen not test");
  assert.equal(plainOf("```js\nconst **a** = `b`;\n```"), "\nconst **a** = `b`;\n");
  assert.equal(plainOf("| Case | Before |\n|---|---|\n| one | 12 ms |"), "Case Before\n\none 12 ms");
  assert.equal(plainOf("keep snake_case_names and 2 * 3 * 4"), "keep snake_case_names and 2 * 3 * 4");
  assert.equal(plainOf("> quoted *word*"), "quoted word");
});

const conversation = (): PaneItem[] => [
  { kind: "you", key: "u1", text: "Fix the Parser, see [Image: /tmp/a.png] and [Image: /tmp/a.png]", at: 1 },
  { kind: "claude", key: "c1", text: "The **parser** reads `dates`.", at: 2 },
  { kind: "tool", key: "t1", name: "Bash", line: "Bash: npm test -- parser", status: "ok", summary: "3 passed", input: "$ npm test -- parser", output: "parser ok\nparser ok", at: 3 },
  { kind: "tool", key: "t2", name: "Edit", line: "Edit: src/parse.ts", status: "ok", input: "old parser", output: "", diff: ["@@ -1 +1 @@", "-old parser", "+new parser"], at: 4 },
  { kind: "you", key: "u2", text: "!grep parser src", command: { shell: true, output: "\x1b[31msrc/parser.ts\x1b[0m: parser" }, at: 5 },
  { kind: "note", key: "n1", text: "Interrupted", at: 6 },
  { kind: "claude", key: "c2", text: lines(50, "parser"), at: 7 },
];

test("search: what each tab shows, in order; what shows only once opened or unfolded is marked so", () => {
  const [u1] = conversation();
  assert.equal(findParts(u1, false)[0], "Fix the Parser, see [Image #1] and [Image #1]");
  assert.deepEqual(findParts(conversation()[2], false), ["", ""]);   // (Chat: no tool calls)
  assert.deepEqual(findParts(conversation()[2], true), ["Bash  npm test -- parser\n3 passed", "$ npm test -- parser\nparser ok\nparser ok"]);
  assert.deepEqual(findParts(conversation()[3], true), ["Edit  src/parse.ts", "@@ -1 +1 @@\n-old parser\n+new parser"]);   // (an edit: its change)
  assert.deepEqual(findParts(conversation()[4], false), ["grep parser src\nsrc/parser.ts: parser", ""]);
  const chat = findIn(conversation(), "PARSER", false).hits;
  assert.deepEqual(chat.slice(0, 5), [{ key: "u1", n: 0, hidden: false }, { key: "c1", n: 0, hidden: false },
                                      { key: "u2", n: 0, hidden: false }, { key: "u2", n: 1, hidden: false }, { key: "u2", n: 2, hidden: false }]);
  const long = chat.filter((h) => h.key === "c2");
  assert.equal(long.length, 50);
  assert.equal(long.filter((h) => !h.hidden).length, FOLD_SHOWN);   // (folded: the rest shows once unfolded)
  const steps = findIn(conversation(), "parser", true).hits;
  assert.deepEqual(steps.filter((h) => h.key === "t1"), [{ key: "t1", n: 0, hidden: false }, { key: "t1", n: 1, hidden: true },
                                                         { key: "t1", n: 2, hidden: true }, { key: "t1", n: 3, hidden: true }]);
  assert.equal(steps.filter((h) => h.key === "t2").length, 2);
  assert.deepEqual(findIn(conversation(), "", true), { hits: [], next: -1 });
  assert.deepEqual(findIn(conversation(), "nowhere", true).hits, []);
  // an answered question shows on both tabs: its options once unfolded
  const asked: PaneItem = { kind: "tool", key: "q1", name: "AskUserQuestion", line: "", at: 8, asked: { state: "answered", questions: [
    { header: "Weeks", question: "Which weeks?", multiSelect: false, options: [{ label: "ISO weeks", description: "" }, { label: "US weeks", description: "Sunday first" }], picked: ["ISO weeks"] }] } };
  assert.deepEqual(findIn([asked], "weeks", false).hits.map((h) => h.hidden), [false, false, true, true]);
});

test("search goes a slice at a time and finds the same; a chat read again is searched again", () => {
  const many: PaneItem[] = [];
  for (let i = 0; i < 400; i++) many.push({ kind: i % 2 ? "claude" : "you", key: `k${i}`, text: `item ${i} with a needle and a Needle`, at: i });
  const whole = findIn(many, "needle", true).hits;
  assert.equal(whole.length, 800);
  let got = findIn(many, "needle", true, 0, 0);
  let slices = 1;
  while (got.next >= 0) {
    got = findIn(many, "needle", true, got.next, 0, got.hits);
    slices++;
  }
  assert.ok(slices >= 400 / 8, `${slices} slices`);
  assert.deepEqual(got.hits, whole);
  const again = many.map((it) => (it.key === "k3" ? { ...it, text: "no longer" } : it));
  assert.equal(findIn(again, "needle", true).hits.length, 798);
});

test("a chat read again isn't made low case again: only the items whose text changed are", () => {
  // (each read brings new objects: a search open while Claude works searched every item anew at each)
  const step: PaneItem = { kind: "tool", key: "t1", name: "Bash", line: "Bash: npm test", status: "ok", summary: "3 passed",
                           input: "npm test", output: "ok", diff: ["+a"], at: 1, asked: undefined };
  const reply: PaneItem = { kind: "claude", key: "m1", text: "The **parser** works", at: 2 };
  const yours: PaneItem = { kind: "you", key: "u1", text: "!ls", command: { shell: true, output: "a.txt" }, at: 3 };
  for (const it of [step, reply, yours])
    for (const steps of [false, true]) {
      const first = lowOf(it, steps);
      assert.equal(lowOf(structuredClone(it), steps), first, `${it.key}: the same text, read again`);
    }
  const was = lowOf(reply, false);
  for (const changed of [{ ...reply, text: "The parser" }, { ...reply, kind: "note" as const }]) assert.notEqual(lowOf(changed, false), was);
  const tool = lowOf(step, true);
  for (const changed of [{ status: "error" }, { summary: "1 failed" }, { output: "no" }, { input: "npm t" }, { line: "Bash: x" },
                         { diff: ["+b"] }, { asked: { state: "answered", plan: "P" } }])
    assert.notEqual(lowOf({ ...step, ...changed }, true), tool, JSON.stringify(changed));
  const mine = lowOf(yours, false);
  assert.notEqual(lowOf({ ...yours, command: { shell: true, output: "b.txt" } }, false), mine);
  assert.equal(lowOf({ ...yours, command: { shell: true, output: "b.txt" } }, false).low.includes("b.txt"), true);
});

test("the find bar's count and its steps: from what you read, then one after another, round", () => {
  assert.equal(findCount(0, -1, false), "…");
  assert.equal(findCount(7, -1, false), "7…");
  assert.equal(findCount(0, -1, true), "No matches");
  assert.equal(findCount(1, -1, true), "1 match");
  assert.equal(findCount(12, -1, true), "12 matches");
  assert.equal(findCount(12, 2, true), "3 of 12");
  const hits = [{ key: "a", n: 0, hidden: false }, { key: "c", n: 0, hidden: false }, { key: "c", n: 1, hidden: false }, { key: "e", n: 0, hidden: false }];
  const order = new Map(["a", "b", "c", "d", "e"].map((k, i) => [k, i]));
  assert.equal(findStep(hits, -1, false, { first: 1, last: 3, order }), 1);   // (the first at or below what you read)
  assert.equal(findStep(hits, -1, true, { first: 1, last: 3, order }), 2);    // (the last at or above its end)
  assert.equal(findStep(hits, -1, false, { first: 4, last: 4, order }), 3);
  assert.equal(findStep(hits, -1, false, { first: 9, last: 9, order }), 0);   // (none below: the first)
  assert.equal(findStep(hits, 3, false, { first: 0, last: 0, order }), 0);    // (round)
  assert.equal(findStep(hits, 0, true, { first: 0, last: 0, order }), 3);
  assert.equal(findStep([], -1, false, { first: 0, last: 0, order }), -1);
  assert.deepEqual(nthIn("A parser, the PARSER", "parser", 1), [14, 20]);
  assert.equal(nthIn("A parser", "parser", 1), null);
  assert.deepEqual(allIn("aXa xa", "A"), [[0, 1], [2, 3], [5, 6]]);
  assert.equal(allIn("aaaa", "a", 2).length, 2);
});

// Side questions (sides.mjs, Plasma's too; the panel: webview/components/SidePanel.tsx): what pane.py
// gives is taken only as what it can be; the panel shows the chat's list, then the questions this tab
// asked till that list has them
test("side questions: pane.py's list taken only as what it can be, the malformed left out", () => {
  const ok = { id: "0123456789ab", q: "Why 52?", at: 5, pick: "haiku", model: "claude-haiku-4-5", a: "Because…", done: 9 };
  assert.deepEqual(sideOf(ok), ok);
  assert.deepEqual(sideOf({ ...ok, pick: "opus", extra: "x", synthetic: true }), { ...ok, pick: "", synthetic: true });   // (not a pick: the chat's own)
  assert.deepEqual(sideOf({ id: "0123456789ab", q: "Q", at: 5, pick: "", model: "", pending: true, a: "x", error: "y" }),
                   { id: "0123456789ab", q: "Q", at: 5, pick: "", model: "", pending: true });   // (on its way: nothing else)
  assert.deepEqual(sideOf({ id: "0123456789ab", q: "Q", at: 5, done: 7, error: "No answer came: ask again" }),
                   { id: "0123456789ab", q: "Q", at: 5, pick: "", model: "", done: 7, error: "No answer came: ask again" });
  assert.equal(sideOf({ id: "0123456789ab", q: "Q", at: 5, done: 7 })!.error, "Claude couldn't answer it");   // (no answer: why, always)
  assert.equal(sideOf({ ...ok, synthetic: "yes" })!.synthetic, undefined);
  assert.deepEqual([sideOf({ ...ok, at: "5", done: -1 })!.at, sideOf({ ...ok, at: "5", done: -1 })!.done], [0, undefined]);
  for (const bad of [null, "x", [], { id: "nope", q: "Q" }, { id: "0123456789ab", q: "  " }, { id: "0123456789ab" }, { id: 7, q: "Q" }, { id: "0123456789AB", q: "Q" }])
    assert.equal(sideOf(bad), null, JSON.stringify(bad));
  assert.deepEqual(sidesOf([ok, { id: "bad" }, 3]).map((s) => s.id), ["0123456789ab"]);
  assert.deepEqual(sidesOf("x"), []);
  assert.deepEqual([sidePickOf(""), sidePickOf("sonnet"), sidePickOf("haiku"), sidePickOf("opus"), sidePickOf(undefined), sidePickOf(0)], ["", "sonnet", "haiku", null, null, null]);
  // the page's answer: the helper's own fields, each only as what it can be
  assert.deepEqual(sideAnswerOf("ask", 3, "c1", { ok: true, message: 1, side: { ...ok, junk: 1 }, sides: [ok, {}], sidesV: 9, extra: "x" }),
                   { type: "side", kind: "ask", id: 3, chatId: "c1", ok: true, message: "", side: ok, sides: [ok], sidesV: 9 });
  assert.deepEqual(sideAnswerOf("remove", 4, "c1", { ok: false, side: "x", sidesV: "9" }),
                   { type: "side", kind: "remove", id: 4, chatId: "c1", ok: false, message: "That didn't work", sides: [], sidesV: 0 });
});

test("side questions: the panel shows the chat's list, then the ones this tab asked till that list has them, several at once", () => {
  const s = (id: string, q: string, at: number, more: Partial<Side> = {}) => ({ id, q, at, pick: "", model: "", ...more }) as Side;
  const a1: AskedSide = { local: 1, q: "Why 52?", pick: "", at: NOW };
  const a2: AskedSide = { local: 2, q: "Why 52?", pick: "haiku", at: NOW + 100 };
  const old = s("aaaaaaaaaaaa", "Earlier", NOW - 3_600_000, { a: "Yes", done: NOW - 3_590_000 });
  // nothing of them in the list yet: on their way, after it, in the order asked
  let shown = sidesShown([old], [a1, a2], new Set());
  assert.deepEqual(shown.map((x) => [x.id, sideState(x), x.local]), [["aaaaaaaaaaaa", "answered", undefined], ["local-1", "pending", 1], ["local-2", "pending", 2]]);
  // pane.py's own item for the first (the same question and pick, a moment later): in its place, once
  const twin = s("bbbbbbbbbbbb", "Why 52?", NOW + 300, { pending: true });
  shown = sidesShown([old, twin], [a1, a2], new Set());
  assert.deepEqual(shown.map((x) => x.id), ["aaaaaaaaaaaa", "bbbbbbbbbbbb", "local-2"]);   // (the Haiku one is another)
  // one being removed is hidden; one removed while it was on its way, and its own item
  assert.deepEqual(sidesShown([old, twin], [{ ...a1, gone: true }, a2], new Set(["aaaaaaaaaaaa"])).map((x) => x.id), ["local-2"]);
  assert.deepEqual(sidesShown([old], [{ ...a1, gone: true }], new Set()).map((x) => x.id), ["aaaaaaaaaaaa"]);
  // Ask again: the same question asked again isn't the failed one, asked before it
  const failed = s("cccccccccccc", "Why 52?", NOW - 10_000, { done: NOW - 5_000, error: "timed out" });
  assert.deepEqual(sidesShown([failed], [a1], new Set(["cccccccccccc"])).map((x) => x.id), ["local-1"]);
  assert.deepEqual(sidesShown([failed], [a1], new Set()).map((x) => x.id), ["cccccccccccc", "local-1"]);
  // one that never got there (the helper said why): why, in its place
  const lost = sidesShown([], [{ ...a1, error: "That's too long for a side question (up to 20000 characters)" }], new Set())[0];
  assert.deepEqual([lost.id, sideState(lost), lost.error, lost.local], ["local-1", "error", "That's too long for a side question (up to 20000 characters)", 1]);
  // the same question twice at once: each its own
  const b1 = s("dddddddddddd", "Why 52?", NOW + 200), b2 = s("eeeeeeeeeeee", "Why 52?", NOW + 250);
  assert.deepEqual(sidesShown([b1, b2], [a1, { ...a1, local: 3, at: NOW + 1 }], new Set()).map((x) => x.id), ["dddddddddddd", "eeeeeeeeeeee"]);
});

test("side questions: which list is newer, what the next one costs, Explain this's question, the meta line's model, the actions' order", () => {
  assert.equal(newerSides([], 5, 4), true);
  assert.equal(newerSides([], 5, 5), false);
  assert.equal(newerSides(undefined, 5, 0), false);
  assert.equal(newerSides([], undefined, 0), false);
  const answered = { id: "aaaaaaaaaaaa", q: "Q", at: NOW - 60_000, pick: "haiku", model: "claude-haiku-4-5", a: "A", done: NOW - 50_000 } as Side;
  assert.equal(sideWarm([answered], "haiku", NOW), true);
  assert.equal(sideWarm([answered], "", NOW), false);   // (another model: its own cache)
  assert.equal(sideWarm([answered], "haiku", NOW - 50_000 + WARM_MS + 1), false);
  assert.equal(sideWarm([{ ...answered, a: undefined, error: "x" }], "haiku", NOW), false);
  assert.equal(costNote(300_000, false), "The first question re-reads the chat: 300k tokens");
  assert.equal(costNote(300_000, true), "Follow-ups reuse the chat from the cache");
  assert.equal(costNote(0, false), "");   // (its context not known: nothing said)
  assert.equal(explainQuestion("isoWeek caps it\n\nat 52"), "Explain this part of the chat:\n\n> isoWeek caps it\n>\n> at 52");
  assert.equal(explainQuestion("  \n "), "");
  assert.equal(sideModelLabel({ ...answered, pick: "", model: "claude-opus-5-5" }), "Opus 5.5");
  assert.equal(sideModelLabel(answered), "Haiku");
  assert.deepEqual(SIDE_ACTIONS, ["copy", "quote", "whole", "remove"]);
  assert.deepEqual(SIDE_PICKS.map((p) => [p.value, sidePickLabel(p.value)]), [["", "Same model as the chat"], ["sonnet", "Sonnet"], ["haiku", "Haiku"]]);
});

// Ask from here (a message's right-click menu; Explain this from the message selected): side questions see the
// chat from that message's turn on (pane.py --part, --from)
const PART = { key: "u-1", text: "fix the parser", at: 5, tokens: 52_000, of: 575_000 };

test("Ask from here: since and from taken only as what they can be; which keys can be asked from", () => {
  const ok = { id: "0123456789ab", q: "Why?", at: 5, pick: "haiku", model: "claude-haiku-4-5", a: "Because", done: 9, since: "msg_01abc", from: PART };
  assert.deepEqual(sideOf(ok), ok);
  // (on its way, pane.py's own keeps the message it was asked from; the part comes with the answer)
  assert.deepEqual(sideOf({ id: "0123456789ab", q: "Q", at: 5, pending: true, since: "toolu_1/answer", from: "x" }),
                   { id: "0123456789ab", q: "Q", at: 5, pick: "", model: "", since: "toolu_1/answer", pending: true });
  for (const since of ["-x", "", "a b", "x".repeat(201), 7, null, ["u-1"]])
    assert.equal(sideOf({ ...ok, since })!.since, undefined, JSON.stringify(since));
  for (const from of [null, "u-1", { key: "-x" }, { text: "no key" }, [], { key: 3 }])
    assert.equal(sideOf({ ...ok, from })!.from, undefined, JSON.stringify(from));
  // (each of the part's fields only as what it can be: whole numbers from 0)
  assert.deepEqual(sideOf({ ...ok, from: { key: "u-1", text: 3, at: -1, tokens: 1.5, of: "9", junk: 1 } })!.from, { key: "u-1", text: "", at: 0, tokens: 0, of: 0 });
  assert.deepEqual(sidePartOf({ ...PART, junk: 1 }), PART);
  assert.equal(sidePartOf(null), null);
  // a message's key (pane.py's: talpy_den.side_since_ok), and of those, one in the chat (not one on its way
  // with this page's key; one sent while Claude worked keeps its queued- key in the chat)
  const keys = ["u-1", "msg_01X", "toolu_1/answer", "a.b:c@d", "-flag", "", "a b", "pending-3", "queued-17", "answer-2", 7];
  assert.deepEqual(keys.map((k) => [sideKeyOk(k), fromKeyOk(k)]),
                   [[true, true], [true, true], [true, true], [true, true], [false, false], [false, false], [false, false],
                    [true, false], [true, true], [true, false], [false, false]]);
  // the page's answer to --part: the part, or none (all of the chat), or why not
  assert.deepEqual(sidePartAnswerOf(4, "c1", { ok: true, part: { ...PART, junk: 1 }, extra: 1 }),
                   { type: "side", kind: "part", id: 4, chatId: "c1", ok: true, message: "", part: PART });
  assert.deepEqual(sidePartAnswerOf(5, "c1", { ok: true, part: null }), { type: "side", kind: "part", id: 5, chatId: "c1", ok: true, message: "", part: null });
  assert.deepEqual(sidePartAnswerOf(6, "c1", { ok: false, missing: true, message: "This chat hasn't started yet, or it isn't there any more" }),
                   { type: "side", kind: "part", id: 6, chatId: "c1", ok: false, message: "This chat hasn't started yet, or it isn't there any more", part: null, missing: true });
  assert.deepEqual(sidePartAnswerOf(7, "c1", { ok: false, part: PART, missing: "yes" }),
                   { type: "side", kind: "part", id: 7, chatId: "c1", ok: false, message: "That didn't work", part: null });
});

test("Ask from here: one asked finds its own (asked from the same message); the panel's line says the part or what the next one costs; the meta line what it saw", () => {
  const s = (id: string, more: Partial<Side> = {}) => ({ id, q: "Why 52?", at: NOW + 300, pick: "", model: "", pending: true, ...more }) as Side;
  const fromHere: AskedSide = { local: 1, q: "Why 52?", pick: "", at: NOW, since: "u-1" };
  const whole: AskedSide = { local: 2, q: "Why 52?", pick: "", at: NOW + 50 };
  // pane.py's own for the one about all of it isn't the one asked from u-1's turn on
  let shown = sidesShown([s("bbbbbbbbbbbb")], [fromHere, whole], new Set());
  assert.deepEqual(shown.map((x) => [x.id, x.since, sideState(x)]), [["bbbbbbbbbbbb", undefined, "pending"], ["local-1", "u-1", "pending"]]);
  shown = sidesShown([s("bbbbbbbbbbbb"), s("cccccccccccc", { since: "u-1" })], [fromHere, whole], new Set());
  assert.deepEqual(shown.map((x) => x.id), ["bbbbbbbbbbbb", "cccccccccccc"]);
  // Ask with the whole chat: the same question again, not the one about the part (which stays)
  const aboutPart = s("dddddddddddd", { at: NOW - 60_000, pending: undefined, a: "A", done: NOW - 50_000, since: "msg_2", from: PART });
  assert.deepEqual(sidesShown([aboutPart], [whole], new Set()).map((x) => x.id), ["dddddddddddd", "local-2"]);
  // the line: no part, the cost (an answer about a part doesn't warm all of it); a part, where it starts and
  // what it costs, its own cache (on the same pick)
  const answered = { id: "aaaaaaaaaaaa", q: "Q", at: NOW - 60_000, pick: "haiku", model: "claude-haiku-4-5", a: "A", done: NOW - 50_000 } as Side;
  const fromU1 = { ...answered, id: "eeeeeeeeeeee", since: "msg_2", from: PART } as Side;
  assert.deepEqual(sideLine(null, [fromU1], "haiku", NOW, 300_000), { text: "The first question re-reads the chat: 300k tokens", tip: SIDE_COST_TIP });
  assert.deepEqual(sideLine(null, [answered], "haiku", NOW, 300_000), { text: "Follow-ups reuse the chat from the cache", tip: SIDE_COST_TIP });
  assert.deepEqual(sideLine(PART, [answered], "haiku", NOW, 300_000), { text: "From “fix the parser”: 52k of the chat's 575k tokens", tip: SIDE_FROM_TIP });
  assert.equal(sideLine(PART, [fromU1], "haiku", NOW, 300_000).text, "From “fix the parser”: follow-ups reuse it from the cache");
  assert.equal(sideLine(PART, [fromU1], "", NOW, 300_000).text, fromNote(PART, false));   // (another pick: its own cache)
  assert.deepEqual(sideLine(null, [], "", NOW, 0), { text: "", tip: SIDE_COST_TIP });   // (its context not known: nothing said)
  // the meta line's word on what it saw: the part, all of it though asked from a message, else nothing
  assert.deepEqual([sideSaw(fromU1), sideSaw({ ...answered, since: "msg_2" }), sideSaw(answered), sideSaw(s("ffffffffffff", { since: "u-1" }))],
                   ["from “fix the parser”", "whole chat", "", ""]);
});

test("Ask from here: --part read where the chat is (a host's with --host), a question with --from; what isn't a message's key isn't run", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  process.env.XDG_CACHE_HOME = ownCache("talpy-den-from-");
  const calls: string[][] = [];
  const texts: string[] = [];
  const answer = { id: "0123456789ab", q: "Why?", at: NOW, pick: "haiku", model: "claude-haiku-4-5", a: "A", done: NOW + 5, since: "msg_2", from: PART };
  const backend = { pane: async (args: string[]) => {
    if (args[0] !== "--side-question") return { ok: true, unchanged: true };
    calls.push(own(args));
    if (args.includes("--text-file")) texts.push(fs.readFileSync(args[args.indexOf("--text-file") + 1], "utf8"));
    if (args.includes("--part")) {
      const key = args[args.indexOf("--part") + 1];
      return key === "old" ? { ok: true, part: null } : key === "gone" ? { ok: false, missing: true, message: "Not there" } : { ok: true, part: { ...PART, junk: 1 } };
    }
    return { ok: true, message: "", side: answer, sides: [answer], sidesV: 3 };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
  p.open({ chatId: "from-1", sessionId: "from-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const sides = () => panel.sent.filter((m) => (m as { type: string }).type === "side") as Record<string, unknown>[];
  panel.receive({ type: "sidePart", id: 1, key: "msg_2" });
  panel.receive({ type: "sidePart", id: 2, key: "old" });
  panel.receive({ type: "sidePart", id: 3, key: "gone" });
  panel.receive({ type: "sideAsk", id: 4, text: "Why?", pick: "haiku", from: "msg_2" });
  for (const bad of [{ key: "-x" }, { key: 7 }, { id: "5" }]) panel.receive({ type: "sidePart", id: 5, key: "u-1", ...bad });
  panel.receive({ type: "sideAsk", id: 6, text: "Q", pick: "", from: "--remove" });
  panel.receive({ type: "sideAsk", id: 7, text: "Q", pick: "", from: 3 });
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(calls, [["--side-question", "from-1", "--part", "msg_2", "--profile", ".claude"],
                           ["--side-question", "from-1", "--part", "old", "--profile", ".claude"],
                           ["--side-question", "from-1", "--part", "gone", "--profile", ".claude"],
                           ["--side-question", "from-1", "--text", "Why?", "--model", "haiku", "--from", "msg_2", "--profile", ".claude"]]);
  const got = sides().sort((x, y) => Number(x.id) - Number(y.id));
  assert.deepEqual(got.slice(0, 3), [{ type: "side", kind: "part", id: 1, chatId: "from-1", ok: true, message: "", part: PART },
                                     { type: "side", kind: "part", id: 2, chatId: "from-1", ok: true, message: "", part: null },
                                     { type: "side", kind: "part", id: 3, chatId: "from-1", ok: false, message: "Not there", part: null, missing: true }]);
  assert.deepEqual(got[3], { type: "side", kind: "ask", id: 4, chatId: "from-1", ok: true, message: "", side: answer, sides: [answer], sidesV: 3 });
  assert.deepEqual(got.slice(4).map((m) => [m.kind, m.id, m.ok, m.message]), [["ask", 6, false, "Which message?"], ["ask", 7, false, "Which message?"]]);
  // an SSH host's chat: read and asked there (--host), the question in a file of its own, gone after
  p.open({ chatId: "from-2", sessionId: "from-2", profileDir: ".claude-work", name: "y", host: "lab" } as never);
  const host = recorded.panels.at(-1)!;
  host.receive({ type: "sidePart", id: 1, key: "u-1" });
  host.receive({ type: "sideAsk", id: 2, text: "On the host?", pick: "", from: "u-1" });
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(calls[4], ["--side-question", "from-2", "--part", "u-1", "--profile", ".claude-work", "--host", "lab"]);
  const asked = calls[5];
  assert.deepEqual([...asked.slice(0, 3), ...asked.slice(4)], ["--side-question", "from-2", "--text-file", "--from", "u-1", "--profile", ".claude-work", "--host", "lab"]);
  assert.equal(texts.at(-1), "On the host?");
  assert.deepEqual(fs.readdirSync(path.join(process.env.XDG_CACHE_HOME, "talpy-den")).filter((f) => f.startsWith("text-")), [], "gone after");
  p.dispose();
});

test("a side question goes to pane.py --side-question (a host's with --host, in a file of its own), several at once; its answer only as what it can be", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  process.env.XDG_CACHE_HOME = ownCache("talpy-den-side-");
  const calls: string[][] = [];
  const texts: string[] = [];
  const item = (q: string) => ({ id: "0123456789ab", q, at: NOW, pick: "", model: "claude-opus-5-5", a: `About ${q}`, done: NOW + 5 });
  let v = 20;
  const backend = { pane: async (args: string[]) => {
    if (args[0] !== "--side-question") return { ok: true, unchanged: true };
    calls.push(own(args));
    if (args.includes("--text-file")) texts.push(fs.readFileSync(args[args.indexOf("--text-file") + 1], "utf8"));
    if (args.includes("--remove")) return { ok: true, message: "", sides: [], sidesV: ++v };
    const q = args.includes("--text") ? args[args.indexOf("--text") + 1] : texts.at(-1)!;
    await new Promise((r) => setTimeout(r, q === "slow" ? 60 : 1));   // (the first is slow: the second doesn't wait for it)
    return { ok: true, message: "", side: { ...item(q), junk: 1 }, sides: [item(q), { bad: 1 }], sidesV: ++v, extra: "x" };
  } };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash);
  p.open({ chatId: "side-1", sessionId: "side-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  const answers = () => panel.sent.filter((m) => (m as { type: string }).type === "side") as { kind: string; id: number; ok: boolean; message: string }[];
  panel.receive({ type: "sideAsk", id: 1, text: "slow", pick: "" });
  panel.receive({ type: "sideAsk", id: 2, text: "  Why 52?  ", pick: "haiku" });
  await new Promise((r) => setTimeout(r, 120));
  assert.deepEqual(calls, [["--side-question", "side-1", "--text", "slow", "--profile", ".claude"],
                           ["--side-question", "side-1", "--text", "Why 52?", "--model", "haiku", "--profile", ".claude"]]);
  assert.deepEqual(answers().map((m) => m.id), [2, 1], "the second didn't wait for the first");
  assert.deepEqual(answers()[0], { type: "side", kind: "ask", id: 2, chatId: "side-1", ok: true, message: "", side: item("Why 52?"), sides: [item("Why 52?")], sidesV: 21 });
  // removed: one, or all; what isn't a side question's id, a pick that isn't one, nothing to ask: not run, said why
  panel.receive({ type: "sideRemove", id: 3, side: "0123456789ab" });
  panel.receive({ type: "sideRemove", id: 4, side: "all" });
  for (const bad of [{ side: "../x" }, { side: 7 }, { id: "5" }]) panel.receive({ type: "sideRemove", id: 5, side: "0123456789ab", ...bad });
  panel.receive({ type: "sideAsk", id: 6, text: "Q", pick: "opus" });
  panel.receive({ type: "sideAsk", id: 7, text: "   ", pick: "" });
  panel.receive({ type: "sideAsk", id: "8", text: "Q", pick: "" });
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(calls.slice(2), [["--side-question", "side-1", "--remove", "0123456789ab"], ["--side-question", "side-1", "--remove", "all"]]);
  assert.deepEqual(answers().slice(2).map((m) => [m.kind, m.id, m.ok, m.message]).sort((x, y) => Number(x[1]) - Number(y[1])),
                   [["remove", 3, true, ""], ["remove", 4, true, ""], ["ask", 6, false, "Not a model side questions can use"], ["ask", 7, false, "Write your question first"]]);
  // an SSH host's chat: asked there (--host; kept here), the question in a file of its own (out of the process list), gone after
  p.open({ chatId: "side-2", sessionId: "side-2", profileDir: ".claude-work", name: "y", host: "lab" } as never);
  recorded.panels.at(-1)!.receive({ type: "sideAsk", id: 1, text: "On the host?", pick: "sonnet" });
  await new Promise((r) => setTimeout(r, 30));
  const last = calls.at(-1)!;
  assert.deepEqual([...last.slice(0, 3), ...last.slice(4)], ["--side-question", "side-2", "--text-file", "--model", "sonnet", "--profile", ".claude-work", "--host", "lab"]);
  assert.equal(texts.at(-1), "On the host?");
  assert.deepEqual(fs.readdirSync(path.join(process.env.XDG_CACHE_HOME, "talpy-den")).filter((f) => f.startsWith("text-")), [], "gone after");
  p.dispose();
});

test("the side questions panel's pick and whether it's open are kept for every Talpy Chat; a chat's list comes with its conversation, only as what it can be", async (t) => {
  const kept = new Map<string, unknown>();
  const memory = { get: (k: string, fallback?: unknown) => (kept.has(k) ? kept.get(k) : fallback), update: async (k: string, v: unknown) => void kept.set(k, v),
                   keys: () => [...kept.keys()] };
  const backend = { pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true }
    : { ok: true, items: [], more: false, stamp: "s1", sides: [{ id: "0123456789ab", q: "Q", at: 5, pending: true, junk: 1 }, "x"], sidesV: 7 }) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  assert.deepEqual(chatPanes(backend, dash).sidePrefs(), { open: false, pick: "" });   // (nowhere to keep them: closed, the chat's own model)
  // (kept in the extension's globalState, as its host's state)
  const quiet = { info() {}, warn() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const keeping = new VsCodeHost(quiet, settingNames(manifest), memory as never);
  t.after(() => keeping.dispose());
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false }, undefined, keeping);
  assert.deepEqual(p.sidePrefs(), { open: false, pick: "" });   // (nothing kept yet)
  p.open({ chatId: "pref-1", sessionId: "pref-1", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  panel.receive({ type: "sidePrefs", open: true });
  panel.receive({ type: "sidePrefs", pick: "haiku" });
  panel.receive({ type: "sidePrefs", open: "yes", pick: "opus" });   // (neither is one: nothing kept)
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(p.sidePrefs(), { open: true, pick: "haiku" });
  assert.deepEqual([...kept], [["talpyDen.sideQuestions.open", true], ["talpyDen.sideQuestions.pick", "haiku"]], "by the keys they always had");
  // the next tab starts with them
  p.open({ chatId: "pref-2", sessionId: "pref-2", profileDir: ".claude", name: "y" } as never);
  const next = recorded.panels.at(-1)! as unknown as { webview: { html: string }; receive(m: unknown): void; sent: unknown[] };
  assert.ok(next.webview.html.includes('"side":{"open":true,"pick":"haiku"},"fresh":false'), next.webview.html);
  next.receive({ type: "ready" });
  await new Promise((r) => setTimeout(r, 30));
  const read = next.sent.find((m) => (m as { type: string }).type === "conversation") as { answer: Record<string, unknown> };
  assert.deepEqual([read.answer.sides, read.answer.sidesV], [[{ id: "0123456789ab", q: "Q", at: 5, pick: "", model: "", pending: true }], 7]);
  p.dispose();
});

test("what a chat runs in the background, under its working line: a line each, the whole command folded on the Steps tab", () => {
  const shell = (command: string, description = ""): BackgroundShell => ({ id: "b1", command, description, started: 1 });
  // (the Chat tab: the command's first line that says something; a nameless one by what Claude called it)
  assert.equal(shellLine(shell("\n  while squeue -h -j 124694 | grep -q .; do\n  sleep 30\ndone")), "while squeue -h -j 124694 | grep -q .; do");
  assert.equal(shellLine(shell("", "Wait for the job")), "Wait for the job");
  assert.equal(shellLine(shell("")), "A background shell");
  // (the Steps tab: whole, unless it's longer than SHELL_FOLD lines and a bit)
  assert.equal(shellFold(Array(SHELL_FOLD + 2).fill("x").join("\n") + "\n\n"), null);
  assert.deepEqual(shellFold(Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n")),
    { shown: Array.from({ length: SHELL_FOLD }, (_, i) => `line ${i}`).join("\n"), more: 20 - SHELL_FOLD });
  assert.equal(shellsWaiting(1), "Waiting on a background shell");
  assert.equal(shellsWaiting(3), "Waiting on 3 background shells");
  assert.equal(shellsMore(2), "and 2 more in the background (the Steps tab lists them)");
});

test("Remote Control: its page only from a claude.ai/code session, and the switch not while a prompt of Claude's is open", async () => {
  const { remoteControlPage, remoteSwitchCan, remoteSwitchTitle } = await import("../../core/src/shared/pane");
  assert.equal(remoteControlPage("https://claude.ai/code/session_01AbC"), "https://claude.ai/code/session_01AbC");
  for (const bad of ["https://claude.ai/code/cse_01AbC", "https://evil.example/code/session_01AbC", "https://claude.ai/code/session_01 x", null, 42])
    assert.equal(remoteControlPage(bad), "");
  // (a chat that waits for your reply has its prompt free; a permission or a question open takes every key)
  assert.equal(remoteSwitchCan({ waitingFor: "" }), true);
  assert.equal(remoteSwitchCan({ waitingFor: "permission prompt" }), false);
  assert.equal(remoteSwitchCan(null), false);
  assert.match(remoteSwitchTitle(false, true), /^Turn on Remote Control\n/);
  assert.match(remoteSwitchTitle(true, false), /^Turn off Remote Control\n[\s\S]*Once its prompt is answered/);
});

test("opening a chat puts the cursor in its reply box, also when its tab is brought up again", async () => {
  const row = demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0];
  const backend = { pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true } : { ok: true, items: [], more: false, stamp: "s1" }) };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  const tick = () => new Promise((r) => setTimeout(r, 10));
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.show(true);
  const focused = () => panel.sent.filter((m) => (m as { type: string }).type === "focusReply").length;
  try {
    assert.equal(focused(), 0, "not before its page is ready");
    panel.receive({ type: "ready" });
    await tick();
    assert.equal(focused(), 1);
    p.open(chatRefOf(row)); // (its tab brought up again: a click, a notification, a request)
    assert.equal(focused(), 2);
    p.open(chatRefOf(row), "review");
    assert.equal(focused(), 2, "its Review tab keeps its own");
  } finally {
    panel.dispose(); // (closed whatever happens: an open tab keeps watching its chat)
  }
});

test("a chat that asks you something opens with the cursor out of its box: typing + Enter would answer it", async () => {
  const state = waitingState("hook");
  const row = state.status!.groups.flatMap((g) => g.sessions).find((x) => x.state === "waiting")!;
  const backend = { pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true } : { ok: true, items: [], more: false, stamp: "s1" }) };
  const dash = { opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = chatPanes(backend, dash, { canMoveToClaudeCode: () => false });
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.show(true);
  try {
    panel.receive({ type: "ready" });
    await new Promise((r) => setTimeout(r, 10));
    const focus = panel.sent.filter((m) => (m as { type: string }).type === "focusReply");
    assert.deepEqual(focus, [{ type: "focusReply", asking: true }]);
  } finally {
    panel.dispose();
  }
});
