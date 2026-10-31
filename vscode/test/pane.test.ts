// The chat tab and what rows and notifications do with it: a click on a
// chat opens its tab; answers and replies go to pane.py with what the
// extension's own state says (the chat's request, its process), never with
// what the page claims; to-review and the tests badge; Claude's Markdown made
// into elements only (no link that runs anything).

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { ChatPanes } from "../src/chatPane";
import { demoState } from "../src/shared/demo";
import { chatRefOf } from "../src/shared/model";
import { answersOf, chatWhere, oneChoice, picturesIn, queuedReply, reviewPending, reviewSeen, routeHint, shownAsk, testsText, textScale, TEXT_SCALES, whereTag, withoutPicture } from "../src/shared/pane";
import type { ViewState } from "../src/shared/types";
import { ViewHost } from "../src/view";
import { clipboardWrites, overrides, recorded } from "./vscode-stub";
import { inline, Markdown } from "../webview/util/markdown";

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
  assert.deepEqual(await typed.p.send(chatRefOf(row), "hi", "enter", false), { ok: true, message: "Sent" });
  assert.equal(typed.opened.length, 0);
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

test("Show earlier goes up to the most a tab shows, then the tab says only the last steps are shown", async () => {
  const row = demoState(NOW).status!.groups.flatMap((g) => g.sessions)[0];
  const limits: string[] = [];
  const backend = { pane: async (args: string[]) => (limits.push(args[args.indexOf("--limit") + 1]), { ok: true, items: [], more: true, stamp: `s${limits.length}` }) };
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
  const copied: string[] = [];
  const tree = Markdown({ text: "1. Run:\n   ```python\n   if x:\n       go()\n   ```", onCopy: (code) => copied.push(code) });
  assert.ok(asHtml(tree).includes("<code>if x:\n    go()</code>"), asHtml(tree));
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

test("one message to a chat at a time: one sent while the last is on its way isn't sent; the tab always hears back", async () => {
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
  const busy = { ok: false, message: "Your last message to it is still being sent: try again in a moment" };
  const first = p.send(chatRefOf(row), "fix the parser", "auto", false);
  const second = p.send(chatRefOf(row), "fix the parser", "enter", false); // (a second Enter)
  const later = p.send(chatRefOf(row), "and the docs", "background", true);
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(calls.length, 1, "sent once");
  assert.deepEqual(await second, busy);
  assert.deepEqual(await later, busy);
  release({ ok: true, message: "Sent" });
  assert.deepEqual(await first, { ok: true, message: "Sent" });
  const next = p.send(chatRefOf(row), "and the docs", "auto", false); // (once it's sent, the next one goes)
  await new Promise((r) => setTimeout(r, 10));
  release({ ok: true, message: "Sent" });
  assert.equal((await next).ok, true);
  assert.equal(calls.length, 2);
  // the tab hears back about every send, even one that failed on the way (its Send button comes back)
  fail = true;
  p.open(chatRefOf(row));
  const panel = recorded.panels.at(-1)!;
  panel.receive({ type: "send", text: "hello", how: "auto", afterTurn: false });
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(panel.sent.filter((m) => (m as { type: string }).type === "result"),
                   [{ type: "result", kind: "send", ok: false, message: "Couldn't send it: the helper fell over" }]);
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
