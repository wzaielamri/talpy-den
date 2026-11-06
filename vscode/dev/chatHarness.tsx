// Feeds the chat tab's page made-up data, the way src/chatPane.ts would: the
// chat, its conversation, and its review when the page asks for it.

import "../webview/chat";
import type { Asks, Conversation, PaneChat, PaneHostMessage, PaneItem, ReviewAnswer, UsualReplies } from "../src/shared/pane";
import { unhookedText } from "../src/shared/pane";

const params = new URLSearchParams(location.search);
const now = Date.now();
const ask = params.get("ask");
// ?ask=question: Claude's questions, answered through the hook
const questions = [
  { question: "Which weeks should the fix cover?", header: "Weeks", multiSelect: false,
    options: [{ label: "ISO weeks only (Recommended)", description: "Week 1 holds the year's first Thursday; 52 or 53 weeks." },
              { label: "US weeks too", description: "Weeks start on Sunday; a setting picks the rule." }] },
  { question: "Which tests should run after the fix?", header: "Tests", multiSelect: true,
    options: [{ label: "Parser tests", description: "npm test -- parser" }, { label: "All unit tests", description: "" },
              { label: "End-to-end", description: "Slow: about 4 minutes" }] },
];

function send(message: PaneHostMessage): void {
  window.postMessage(message, "*");
}

const chat: PaneChat = {
  host: params.get("host") ?? "", // ?host=lab: an SSH host's chat
  // ?host=lab&watch=fail: its host's watcher keeps failing (the host tag in the warning colour, its tooltip says why)
  watchTrouble: params.get("watch") === "fail" ? "lab: Connection closed by remote host" : "",
  chatId: "demo-chat",
  sessionId: "demo-chat",
  profileDir: ".claude",
  name: "Fix the date parser",
  cwd: "/home/alice/projects/webapp",
  state: ask ? "waiting" : "working",
  stateText: ask ? "Needs input · 1m" : "Working · 6m",
  stateShort: ask ? "Needs input" : "Working",
  route: params.get("route") === "terminal" ? "terminal" : "tmux",
  canMove: params.get("route") === "terminal",
  busy: true,
  atWork: !ask,
  bgStop: params.get("bgStop") !== "0", // ?where=background&bgStop=0: a Claude Code version Stop doesn't know
  activity: "Bash: npm test -- parser",
  permission: ask === "question"
    ? { tool: "AskUserQuestion", line: questions[0].question, command: "", file: "", diff: [], always: "", questions,
        request: "1-abcdef02", answer: "hook" }
    : ask
    ? {
        tool: "Edit",
        line: "Edit: src/parse.ts",
        command: "",
        file: "src/parse.ts",
        diff: ["@@ -12,3 +12,3 @@", "   const week = isoWeek(date);", "-  if (week > 52) return 1;", "+  if (week > weeksInYear(date)) return 1;", "   return week;"],
        always: ask === "hook" ? "Edit(src/**)" : "",
        request: ask === "hook" ? "1-abcdef01" : null,
        answer: ask === "none" ? "" : (ask as "hook" | "keys"),
      }
    : null,
  changes: 2,
  reviewPending: false,
  reviewed: true,
  review: { editedAt: now - 60_000, tests: { command: "npm test -- parser", ok: true, at: now - 30_000 } },
  queued: params.get("queued") === "1" ? { id: "q1", prompt: "Then update the changelog.", error: "" } : null,
  // ?where=background|closed|claude|vscode|terminal: where it runs (else tmux)
  where: (params.get("where") as PaneChat["where"] | null) ?? (params.get("route") === "terminal" ? "terminal" : "tmux"),
  terminalApp: params.get("where") === "terminal" || params.get("route") === "terminal" ? "Konsole" : "",
  attached: params.get("where") === "background" ? { in: "terminal", app: "Konsole" } : null,
  profile: "work",
  shared: params.get("shared") === "1" ? { profiles: ["work", "personal"], forkOf: null } as unknown as PaneChat["shared"] : null,
  mode: "auto",
  plan: { title: "Fix the week numbers" },
  // (?agents=0: none)
  agents: params.get("agents") === "0" ? null : {
    running: 2, done: 2, stopped: 0, total: 4,
    tree: [
      { id: "a1", parent: null, depth: 0, type: "Explore", description: "Find where weeks are computed", status: "done", activity: "", started: now - 380_000, updated: now - 330_000 },
      { id: "a2", parent: null, depth: 0, type: "general-purpose", description: "Check the other date helpers", status: "running", activity: "Grep: weeksInYear", started: now - 200_000, updated: now - 5_000,
        model: "Sonnet 5.5", task: "Check whether the other date helpers in src/dates.ts cap weeks at 52 too.", steps: ["Read: dates.ts", "Grep: weeksInYear"], toolCalls: 6, tokens: 41_200 },
      { id: "a4", parent: "a2", depth: 1, type: "Explore", description: "Read the calendar module", status: "running", activity: "Read: calendar.ts", started: now - 60_000, updated: now - 3_000 },
      { id: "a3", parent: null, depth: 0, type: "Explore", description: "Look for week tests", status: "done", activity: "", started: now - 380_000, updated: now - 300_000 },
    ],
  },
  // ?tasks=0: no task list (the strip shows its subagents); ?tasks=open: the strip unfolded
  tasks: params.get("tasks") === "0" ? null : {
    done: 2, total: 4, current: "Running the parser tests",
    items: [
      { subject: "Find why week 53 becomes week 1", status: "completed" },
      { subject: "Fix isoWeek for long years", status: "completed" },
      { subject: "Run the parser tests", status: "in_progress" },
      { subject: "Add a test for 2026-12-31", status: "pending" },
    ],
  },
};

const items: PaneItem[] = [
  { kind: "you", key: "u1", text: "Week 53 dates come out as week 1. Find out why and fix it, with a test.", at: now - 400_000 },
  { kind: "claude", key: "m1", text: "I'll look at how **week numbers** are computed in `src/parse.ts` first.", at: now - 390_000 },
  { kind: "tool", key: "t1", name: "Read", line: "Read: parse.ts", status: "ok", input: "file_path: /home/alice/projects/webapp/src/parse.ts", output: "     1\timport { isoWeek } from './dates';\n     2\t\n     3\texport function parse(text: string) {\n     4\t  const date = new Date(text); // UTC\n     5\t  return { date, week: isoWeek(date) };\n     6\t}", summary: "6 lines", at: now - 380_000 },
  { kind: "tool", key: "t2", name: "Bash", line: "Bash: npm test -- parser", status: "error", input: "$ npm test -- parser", output: "FAIL src/parse.test.ts\n  ✕ week 53 of 2026 (4 ms)", summary: "FAIL src/parse.test.ts … +1 line", at: now - 300_000 },
  { kind: "claude", key: "m2/thinking", thinking: true, text: "The test fails at the year's last week, so `isoWeek` is where to look.", at: now - 210_000 },
  {
    kind: "claude",
    key: "m2",
    text: "Found it: `isoWeek` caps weeks at 52.\n\n## What changes\n\n1. Use `weeksInYear(date)` instead of `52`\n2. Add a test for 2026-12-31\n\n```ts\nif (week > weeksInYear(date)) return 1;\n```\n\nSee [the ISO week rules](https://en.wikipedia.org/wiki/ISO_week_date).",
    at: now - 200_000,
  },
  { kind: "tool", key: "t3", name: "Edit", line: "Edit: parse.ts", status: "ok", input: "/home/alice/projects/webapp/src/parse.ts\n-  if (week > 52) return 1;\n+  if (week > weeksInYear(date)) return 1;", output: "", summary: "2 lines added, 1 removed", at: now - 100_000,
    diff: ["@@ -10,5 +10,6 @@ export function isoWeek(date: Date)", "   const start = startOfIsoYear(date);", "   const week = Math.floor((date - start) / WEEK) + 1;",
           "-  if (week > 52) return 1;", "+  if (week > weeksInYear(date)) return 1;", "+  // (a year has 53 weeks when it starts or ends on a Thursday)", "   return week;", " }"] },
  { kind: "tool", key: "t5", name: "Write", line: "Write: parse.test.ts", status: "ok", input: "", output: "", summary: "5 lines", at: now - 95_000,
    diff: ["@@ -0,0 +1,5 @@", "+import { parse } from './parse';", "+", "+test('week 53 of 2026', () => {", "+  expect(parse('2026-12-31').week).toBe(53);", "+});"] },
  { kind: "note", key: "n1", text: "Interrupted", at: now - 90_000 },
  { kind: "you", key: "u2", text: "Go on, and run the parser tests again.", at: now - 80_000 },
  { kind: "tool", key: "t4", name: "Bash", line: "Bash: npm test -- parser", status: "open", input: "$ npm test -- parser", output: "", at: now - 10_000 },
];

const review: ReviewAnswer = {
  ok: true,
  message: "Fix the date parser\n\nWeek 53 dates came out as week 1: isoWeek capped weeks at 52.",
  files: [
    { label: "src/parse.ts", path: "/home/alice/projects/webapp/src/parse.ts", added: 1, removed: 1, created: false, deleted: false, binary: false, unknown: false,
      diff: ["@@ -12,3 +12,3 @@", "   const week = isoWeek(date);", "-  if (week > 52) return 1;", "+  if (week > weeksInYear(date)) return 1;", "   return week;"] },
    { label: "src/parse.test.ts", path: "/home/alice/projects/webapp/src/parse.test.ts", added: 6, removed: 0, created: true, deleted: false, binary: false, unknown: false,
      diff: ["@@ -0,0 +1,6 @@", "+import { parse } from './parse';", "+", "+test('week 53 of 2026', () => {", "+  expect(parse('2026-12-31').week).toBe(53);", "+});", "+"] },
    { label: "~/notes/dates.md", path: "/home/alice/notes/dates.md", added: null, removed: null, created: false, deleted: false, binary: false, unknown: true,
      diff: [], now: ["# Dates", "", "- ISO weeks: week 1 holds the first Thursday", "- 2026 has 53 weeks"] },
  ],
  tests: { command: "npm test -- parser", ok: true, at: now - 30_000 },
  editedAt: now - 60_000,
  repos: ["/home/alice/projects/webapp"],
};

// ?tasks=open: the strip unfolded (its line clicked); ?agents=open: only its
// subagents (the header's Agents tag clicked), the first running one's details too
const unfold = params.get("tasks") === "open" ? ".pane-tasks-line" : params.get("agents") === "open" ? ".pane-folder button.tag[aria-pressed]" : "";
if (unfold)
  setTimeout(() => {
    document.querySelector<HTMLButtonElement>(unfold)?.click();
    if (params.get("agents") === "open") setTimeout(() => document.querySelector<HTMLButtonElement>(".ag-running .agent-head")?.click(), 100);
  }, 700);

// ?open=1: every tool call unfolded (clicked once the conversation shows)
if (params.get("open") === "1")
  setTimeout(() => document.querySelectorAll<HTMLButtonElement>(".pane-tool-line").forEach((b, i) => setTimeout(() => b.click(), 60 * i)), 900);

// ?pics=1: your last message with two pictures (thumbnails; ?pics=big: the first one opened big)
if (params.get("pics")) {
  const pic = "/home/alice/.cache/talpy-den/images/20261103-162501.png";
  items.push({ kind: "you", key: "p1", text: `[Image: ${pic}] [Image: ${pic.replace("01.png", "14.png")}] the stars show in the pane`, at: now,
               thumbs: [{ path: pic, src: "../media/icon.png" }, { path: pic.replace("01.png", "14.png"), src: "../media/talpy.svg" }] });
  if (params.get("pics") === "big")
    setTimeout(() => document.querySelector<HTMLButtonElement>(".pane-you-pic")?.click(), 900);
}

// ?queue=1: a message in Claude's queue, and one sent while it works (held: Edit / ✕ / Send now)
if (params.get("queue") === "1") {
  items.push({ kind: "you", key: "q1", text: "Also check week 1 of 2027.", queued: true, at: now });
  setTimeout(() => {
    const box = document.querySelector<HTMLTextAreaElement>(".pane-reply");
    if (!box) return;
    box.focus();
    box.value = "And run the whole suite after.";
    box.dispatchEvent(new Event("input", { bubbles: true }));
    setTimeout(() => box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })), 50);
  }, 600);
}

// ?answers=1: your answers in the chat: one question, several (a multi-select, what you typed, a note), a
// plan approved and one kept planning, a Deny with a note, a question declined; ?answers=open: unfolded
if (params.get("answers")) {
  const picked = (q: (typeof questions)[number], labels: string[]) => ({ ...q, picked: labels });
  const plan = "# Fix the week numbers\n\n1. Make `isoWeek` count 53 weeks in a long year.\n2. Add a test for 2026-12-31.";
  items.splice(0, items.length,
    { kind: "you", key: "u1", text: "Week 53 dates come out as week 1. Find out why and fix it, with a test.", at: now - 400_000 },
    { kind: "tool", key: "a1", name: "AskUserQuestion", line: "AskUserQuestion: Which weeks should the fix cover?", status: "ok", summary: "Answered", at: now - 390_000,
      asked: { state: "answered", questions: [picked(questions[0], ["ISO weeks only (Recommended)"])] } },
    { kind: "you", key: "a1/answer", text: "ISO weeks only (Recommended)", answered: "question", at: now - 385_000 },
    { kind: "claude", key: "m1", text: "ISO weeks it is. Two more things before I start:", at: now - 380_000 },
    { kind: "tool", key: "a2", name: "AskUserQuestion", line: "AskUserQuestion: Which tests should run after the fix?", status: "ok", summary: "Answered", at: now - 370_000,
      asked: { state: "answered", questions: [picked(questions[1], ["Parser tests", "All unit tests"]),
                                              { question: "Anything else to keep in mind?", header: "Notes", multiSelect: false, options: [{ label: "No", description: "" }], picked: [] }] } },
    { kind: "you", key: "a2/answer", text: "Tests: Parser tests, All unit tests\nskip the slow ones today\nNotes: keep the old week helper for the reports", answered: "question", at: now - 365_000 },
    { kind: "tool", key: "p1", name: "ExitPlanMode", line: "ExitPlanMode", status: "error", summary: "Keep planning", at: now - 300_000,
      asked: { state: "keep", plan, title: "Fix the week numbers" } },
    { kind: "you", key: "p1/answer", text: "Keep planning\nalso cover week 1 of 2027", answered: "plan", at: now - 295_000 },
    { kind: "tool", key: "p2", name: "ExitPlanMode", line: "ExitPlanMode", status: "ok", summary: "Approved", at: now - 200_000,
      asked: { state: "approved", plan: plan + "\n3. Check week 1 of 2027.", title: "Fix the week numbers" } },
    { kind: "you", key: "p2/answer", text: "Approved the plan", answered: "plan", at: now - 195_000 },
    { kind: "tool", key: "e1", name: "Edit", line: "Edit: dates.ts", status: "error", summary: "Denied", at: now - 120_000, asked: { state: "denied" },
      input: "/home/alice/projects/webapp/src/dates.ts", output: "", diff: ["@@ -3,1 +3,1 @@", "-export const WEEKS = 52;", "+export const WEEKS = 53;"] },
    { kind: "you", key: "e1/answer", text: "Don't change the constant: the reports use it", answered: "permission", at: now - 115_000 },
    { kind: "tool", key: "a3", name: "AskUserQuestion", line: "AskUserQuestion: Should I also fix the US weeks?", status: "error", summary: "Declined", at: now - 60_000,
      asked: { state: "declined", questions: [{ question: "Should I also fix the US weeks?", header: "US weeks", multiSelect: false,
                                                 options: [{ label: "Yes", description: "" }, { label: "No", description: "" }], picked: [] }] } },
    { kind: "claude", key: "m2", text: "All right: only ISO weeks. Running the parser tests now.", at: now - 50_000 },
  );
  if (params.get("answers") === "open")
    setTimeout(() => document.querySelectorAll<HTMLButtonElement>(".pane-asked-toggle").forEach((b) => b.click()), 900);
}

// ?made=1: what Claude made under its steps and its reply (a picture it wrote, one it read, a plan, a
// page, one gone, a PDF); ?made=open: each unfolded (a page's source too); &host=lab: an SSH host's
const madeSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" fill="#2aa198"/>'
  + '<path d="M18 34l9 9 19-21" stroke="#fff" stroke-width="6" fill="none" stroke-linecap="round"/></svg>';
const madeFiles: Record<string, { src?: string; text?: string; cut?: boolean } | { ok: false; message: string }> = {
  "/home/alice/projects/webapp/media/badge.svg": { src: "data:image/svg+xml;base64," + btoa(madeSvg) },
  "/tmp/shots/week53.png": { src: "../media/icon.png" },
  "/home/alice/.claude/plans/brave-otter.md": { text: "# Fix the week numbers\n\n1. Make `isoWeek` count 53 weeks in a long year.\n2. Add a test for **2026-12-31**.\n3. Check week 1 of 2027." },
  "/home/alice/projects/webapp/report/weeks.html": { text: "<!doctype html>\n<title>Weeks</title>\n<table>\n  <tr><td>2026-W53</td><td>ok</td></tr>\n</table>", cut: true },
};
if (params.get("made")) {
  const made = (key: string, path: string, type: "picture" | "plan" | "page" | "file", size: number | null, more: object = {}, text?: string): PaneItem =>
    ({ kind: "made", key, of: key.split("/made/")[0], at: now - 100_000, text: text ?? path.split("/").pop(),
       made: { path, type, name: path.split("/").pop()!, size, ...more } });
  items.splice(0, items.length,
    { kind: "you", key: "u1", text: "Draw a badge for week 53, check how the report looks, and write down the plan.", at: now - 400_000 },
    { kind: "tool", key: "w1", name: "Write", line: "Write: badge.svg", status: "ok", summary: "1 line", at: now - 390_000, diff: [] },
    made("w1/made/0", "/home/alice/projects/webapp/media/badge.svg", "picture", 241),
    { kind: "tool", key: "p1", name: "Write", line: "Write: brave-otter.md", status: "ok", summary: "6 lines", at: now - 380_000, diff: [] },
    made("p1/made/0", "/home/alice/.claude/plans/brave-otter.md", "plan", 3172, {}, "Plan: Fix the week numbers"),
    { kind: "tool", key: "e1", name: "Edit", line: "Edit: weeks.html", status: "ok", summary: "2 lines added, 1 removed", at: now - 370_000, diff: [] },
    made("e1/made/0", "/home/alice/projects/webapp/report/weeks.html", "page", 18_400),
    { kind: "tool", key: "r1", name: "Read", line: "Read: week53.png", status: "ok", summary: "", at: now - 360_000 },
    made("r1/made/0", "/tmp/shots/week53.png", "picture", 41_532, { step: "r1" }),
    { kind: "tool", key: "r2", name: "Read", line: "Read: spec.pdf", status: "ok", summary: "", at: now - 350_000 },
    made("r2/made/0", "/home/alice/projects/webapp/docs/spec.pdf", "file", 242_891),
    { kind: "claude", key: "m1", text: "The badge is in `media/badge.svg`, and the old one, `/tmp/old-badge.png`, is gone now.", at: now - 300_000 },
    made("m1/made/0", "/tmp/old-badge.png", "picture", 3_880, { gone: true }),
  );
  if (params.get("made") === "open")
    setTimeout(() => {
      document.querySelectorAll<HTMLButtonElement>(".pane-made-line").forEach((b) => b.click());
      setTimeout(() => document.querySelectorAll<HTMLButtonElement>(".pane-made-tools button[aria-pressed]").forEach((b) => b.click()), 200);
    }, 900);
}

// ?ask=question&answering=1: your answer shows at once, as yours, under the question, till the conversation has it
if (ask === "question" && params.get("answering") === "1") {
  items.push({ kind: "tool", key: "aq", name: "AskUserQuestion", line: "AskUserQuestion: Which weeks should the fix cover?", status: "open", at: now - 5_000,
               asked: { state: "open", questions: questions.map((q) => ({ ...q, picked: [] })) } });
  setTimeout(() => send({ type: "answering", id: 1, ask: chat.permission!, decision: "answer", note: "",
                          answers: { [questions[0].question]: ["US weeks too"], [questions[1].question]: ["Parser tests", "End-to-end"] } }), 800);
}

// what the page sends, answered as the extension would
// ?type=TEXT: typed into the reply box (to see what it offers)
const typed = params.get("type");
if (typed)
  setTimeout(() => {
    const box = document.querySelector<HTMLTextAreaElement>(".pane-reply");
    if (!box) return;
    box.focus();
    box.dispatchEvent(new FocusEvent("focus"));   // (a headless browser's window never has the focus)
    box.value = typed;
    box.setSelectionRange(typed.length, typed.length);
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }, 300);

// ?new=1: a new chat's tab (New Chat… in a Talpy Chat tab), empty, with its ⚙ line; ?new=task: its task
// sent as its first message at once, Starting… till it's listed
const fresh = params.get("new");
if (fresh)
  Object.assign(chat, { chatId: "new-1", sessionId: "", name: "New chat in ~/repos/app", cwd: "/home/alice/repos/app", state: "done",
                        stateText: "new", route: "background", busy: false, atWork: false, permission: null, changes: 0, where: "new",
                        attached: null, mode: "", plan: null, agents: null, tasks: null, queued: null, canMove: false,
                        fresh: { account: "work · Team", folder: "~/repos/app", plan: "", model: "opus", effort: "xhigh", mode: "default" } });

// ?chips=yesno|options|either|limit: its turn over, with suggested replies (Claude's question's,
// then your usual ones); ?chipmenu=1: a chip's right-click menu; with ?type=co: what you type
// completed in grey
const chipsOf = params.get("chips");
const asks: Record<string, Asks> = {
  yesno: { kind: "yesno", choices: [{ label: "Yes", send: "Yes", recommended: false }, { label: "No", send: "No", recommended: false }] },
  options: { kind: "options", choices: [
    { label: "1 · Run the screening first", send: "1. Run the screening first", recommended: false },
    { label: "2 · Start the rename on a branch", send: "2. Start the rename on a branch", recommended: true },
    { label: "3 · Leave it as it is", send: "3. Leave it as it is", recommended: false }] },
  either: { kind: "either", choices: [{ label: "Fix the parser first", send: "Fix the parser first", recommended: false },
                                      { label: "Update the tests", send: "Update the tests", recommended: false }] },
};
const usual: UsualReplies = { chips: { asked: ["yes please", "go"], limit: ["continue"], stopped: ["go on"] },
                              ranked: ["continue", "commit and push", "go on", "yes please", "go"] };
const turnEnd: Partial<Conversation> = chipsOf === "limit" ? { ended: "limit", over: true, asks: null }
  : chipsOf ? { ended: "asked", over: true, asks: asks[chipsOf] ?? null, predicted: params.get("predicted") } : {};
if (chipsOf)
  Object.assign(chat, { state: "done", stateText: "done 1 min ago", busy: false, atWork: false, permission: null, queued: null, activity: "" });
// how full its context is (?context=near: close to Claude compacting it; ?context=0: not known), and
// Claude's turn so far on the working line (?turn=new: its first seconds; ?turn=0: not known)
const contextOf = params.get("context");
turnEnd.context = contextOf === "0" ? null : contextOf === "near"
  ? { used: 952000, window: 1000000, compactAt: 967000, left: 2, near: true }
  : { used: 300000, window: 1000000, compactAt: 967000, left: 69, near: false };
const turnOf = params.get("turn");
turnEnd.turn = turnOf === "0" ? null : turnOf === "new" ? { startedAt: Date.now() - 7000, steps: 1 } : { startedAt: Date.now() - 252000, steps: 12 };
if (params.get("chipmenu") === "1")
  setTimeout(() => {
    const all = document.querySelectorAll<HTMLButtonElement>(".pane-chip");
    const last = all[all.length - 1];
    if (!last) return;
    const r = last.getBoundingClientRect();
    last.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: r.left + 10, clientY: r.bottom + 2 }));
  }, 400);

window.addEventListener("harness-post", (e: Event) => {
  const m = (e as CustomEvent).detail as { type: string };
  if (m.type === "ready") {
    send({ type: "chat", chat });
    send({ type: "conversation", answer: { ok: true, items: fresh ? [] : items, more: !fresh, stamp: "1", ...turnEnd,
      // (what /model and /effort's lists mark: ?ultracode for a chat with it on)
      options: { model: "claude-opus-5-5", effort: params.has("ultracode") ? "xhigh" : "high", ultracode: params.has("ultracode"), next: false } } });
    if (fresh === "task") setTimeout(() => send({ type: "startWith", text: "Fix the flaky date test in tests/parser.test.ts" }), 100);
    const tab = params.get("tab");   // ?tab=steps
    if (tab) send({ type: "result", kind: "tab:" + tab, ok: true, message: "" });
  } else if (m.type === "made") {   // (pane.py --made: a moment later, as reading it takes)
    const a = m as unknown as { id: number; path: string };
    const f = madeFiles[a.path];
    setTimeout(() => send(f && !("ok" in f) ? { type: "made", id: a.id, ok: true, ...f }
                                           : { type: "made", id: a.id, ok: false, message: "It isn't there any more", gone: true }), 120);
  } else if (m.type === "picture") {
    const id = (m as unknown as { id: string }).id;
    setTimeout(() => send({ type: "picture", id, path: `/home/alice/.cache/talpy-den/images/20261026-1015${id.slice(-2)}.png`, error: "" }), 200);
  } else if (m.type === "review") {
    send({ type: "review", answer: review, error: "" });
  } else if (m.type === "stop") {
    // (?stop=fail: it says why not, and Stop is back)
    setTimeout(() => send({ type: "result", kind: "stop", ok: params.get("stop") !== "fail",
                            message: params.get("stop") === "fail" ? "Claude's background service didn't answer" : "Stopped" }), 1500);
  } else if (m.type === "replies") {
    send({ type: "replies", replies: usual });
  } else if (m.type === "complete") {
    send({ type: "offers", offers: {
      commands: [{ name: "/compact", about: "Free up context by summarizing the conversation so far", kind: "Claude", run: "here" },
                 { name: "/config", about: "Open settings", kind: "Claude", run: "terminal", why: "opens Claude's settings panel" },
                 { name: "/context", about: "Show how full the context is", kind: "Claude", run: "here" },
                 { name: "/copy", about: "Copy Claude's last response", kind: "Claude", run: "terminal", why: "copies where Claude runs" },
                 { name: "/effort", about: "Set the effort level", kind: "Claude", run: "picker", why: "saves it as your default effort for every new chat" },
                 { name: "/model", about: "Set the model", kind: "Claude", run: "picker", why: "saves it as your default model for every new chat" },
                 { name: "/permissions", about: "What Claude may do without asking", kind: "Claude", run: "page" },
                 { name: "/release", about: "Cut a release", kind: "project", run: "here" }],
      files: ["src/parser.ts", "src/parse_date.ts", "tests/parser.test.ts", "README.md"],
      history: ["Fix the date parser", "Run the tests again"],
      typed: { settings: { run: "terminal", of: "/config", why: "opens Claude's settings panel" } },
    } });
  } else if (m.type === "copyItem") {
    // (a reply shown cut is read whole first: a moment; ?copy=fail: it couldn't be)
    const c = m as unknown as { id: number; text: string };
    setTimeout(() => send({ type: "copied", id: c.id, ok: params.get("copy") !== "fail",
                            message: params.get("copy") === "fail" ? "Couldn't copy all of it: That message isn't in the chat any more" : "" }),
               c.text.endsWith("\n…") ? 300 : 0);
  } else if (m.type === "typeIn") {
    setTimeout(() => send({ type: "result", kind: "typein", ok: true, message: "It's in the clipboard. Paste it into its terminal" }), 300);
  } else if (m.type === "send" && params.get("unhooked") === "1") {
    // (?new=task&unhooked=1: a new chat on an SSH host that started without Talpy Den's permission hook there)
    const s = m as unknown as { id?: number };
    setTimeout(() => send({ type: "result", kind: "send", ok: true, went: true, warn: true, id: s.id,
                            message: unhookedText("Talpy Den couldn't put its permission hook in place: others may write in /shared/data/talpy-den") }), 600);
  } else if (m.type === "setOptions") {   // (pane.py --set-options: an idle background chat woken again with them)
    const o = m as unknown as { model?: string; effort?: string };
    setTimeout(() => send({ type: "result", kind: "options", ok: true,
                            message: `${o.model ? o.model[0].toUpperCase() + o.model.slice(1) : `${o.effort} effort`} for this chat from now on` }), 600);
  }
});

// ?commands=1: commands you ran in the conversation, with what they printed (Claude's colours)
if (params.get("commands") === "1") {
  const E = "\x1b";
  const grid = `${E}[1mFill level${E}[22m\n${E}[38;5;244m⛁ ⛁ ${E}[38;2;22;163;74m⛁ ${E}[38;2;215;119;87m⛁ ⛁ ${E}[38;5;246m⛶ ⛶ ⛶ ⛶ ⛶${E}[39m   Made-up model\n`
    + `${E}[38;5;246m⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶${E}[39m   12k/200k tokens (6%)\n\n${E}[38;2;22;163;74m⛁${E}[39m Tools: 8k tokens\n${E}[2mMore: /context all${E}[22m`;
  items.splice(0, items.length,
    { kind: "you", key: "c0", text: "Check the parser's cache and tidy it", at: now - 300_000 },
    { kind: "claude", key: "c1", text: "Done: the cache is tidy now.", at: now - 290_000 },
    { kind: "you", key: "c2", text: "/context", at: now - 280_000, command: { output: grid } },
    { kind: "you", key: "c3", text: "/model fable", at: now - 270_000, command: { output: "Set model to Fable and saved as your default" } },
    { kind: "you", key: "c4", text: "!ls src", at: now - 260_000, command: { shell: true, output: "cache.py\nparse.ts\nroutes" } },
    { kind: "claude", key: "c5", text: "`src` has the cache, the parser and the routes.", at: now - 250_000 },
    { kind: "you", key: "c6", text: "!cat nope.txt", at: now - 240_000, command: { shell: true, output: "cat: nope.txt: No such file or directory", error: true } },
    { kind: "you", key: "c7", text: "/compact", at: now - 230_000, command: {} },
    { kind: "note", key: "c8", text: "The conversation was compacted", at: now - 225_000 });
  Object.assign(chat, { state: "done", stateText: "done 1 min ago", busy: false, atWork: false, permission: null, queued: null, activity: "" });
}

// ?days=1: the conversation over three days: a line before each new day's first item (yesterday's
// before a tool call, which the Chat tab leaves out), none before the first
if (params.get("days") === "1") {
  const d = new Date(now);
  const at = (back: number, h: number, m: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() - back, h, m).getTime();
  const times = [at(9, 10, 2), at(9, 10, 3), at(1, 23, 58), at(1, 23, 59), at(0, 0, 4), at(0, 0, 6), at(0, 0, 7), at(0, 0, 8), at(0, 9, 30), at(0, 9, 31)];
  items.forEach((it, i) => (it.at = times[i] ?? it.at));
}

// ?hover=KEY: the pointer on that message (its time and Copy at its top right); &copy=1: Copy clicked
const hover = params.get("hover");
if (hover)
  setTimeout(() => {
    const row = document.querySelector<HTMLElement>(`[data-key="${CSS.escape(hover)}"]`);
    row?.querySelector(".pane-you-text, .pane-body")?.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    if (params.get("copy") === "1") setTimeout(() => document.querySelector<HTMLButtonElement>(".pane-hoverbar button")?.click(), 1600);
  }, 700);

// ?below=1: scrolled up to the top, then Claude goes on: "N new ↓" at the list's bottom
if (params.get("below") === "1")
  setTimeout(() => {
    const list = document.querySelector<HTMLElement>(".pane-list");
    if (list) list.scrollTop = 0;
    setTimeout(() => send({ type: "conversation", answer: { ok: true, more: true, stamp: "2", items: [...items,
      { kind: "claude", key: "b1", text: "The parser tests pass now: **14 passed**.", at: Date.now() },
      { kind: "tool", key: "b2", name: "Bash", line: "Bash: npm test", status: "ok", summary: "120 passed", at: Date.now() },
      { kind: "claude", key: "b3", text: "And the whole suite too. Shall I commit?", at: Date.now() }] } }), 300);
  }, 700);

// ?stop=1 (or fail): Stop clicked at once ("Stopping…")
if (params.get("stop")) setTimeout(() => document.querySelector<HTMLButtonElement>(".pane-stop")?.click(), 300);

// ?paste=1: a picture pasted into the reply, as Ctrl+V gives one (a browser
// leaves out the clipboard of a paste event a page makes: it's put on the event)
if (params.get("paste") === "1") {
  setTimeout(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 200;
    const g = canvas.getContext("2d")!;
    g.fillStyle = "#3d6fb6";
    g.fillRect(0, 0, 320, 200);
    g.fillStyle = "#d97757";
    g.fillRect(40, 40, 120, 80);
    canvas.toBlob((blob) => {
      const box = document.querySelector<HTMLTextAreaElement>(".pane-reply");
      if (!blob || !box) return;
      const data = new DataTransfer();
      data.items.add(new File([blob], "shot.png", { type: "image/png" }));
      box.focus();
      const event = new Event("paste", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "clipboardData", { value: data });
      box.dispatchEvent(event);
    });
  }, 100);
}

// ?keys=1: the list of keys (? in an empty box); ?key=ID: a key's command, as VS Code sends it (keys.mjs ids:
// sendNow, copyLast, tabSteps, tasks, promptUp, allow, chip1…), 900 ms after the page is up
if (params.get("keys") === "1") setTimeout(() => send({ type: "key", key: "help" }), 600);
const key = params.get("key");
if (key) setTimeout(() => key.split(",").forEach((k, i) => setTimeout(() => send({ type: "key", key: k }), i * 400)), 900);

// ?fold=1: long ones among them (a reply, a pasted log of yours, a command's output, a step's
// output): those read first fold, but Claude's last reply; &more=1: one more long reply comes in
// after (it doesn't fold: you watched it come); ?fold=all: then Ctrl+O (everything unfolded)
const fold = params.get("fold");
if (fold) {
  const lines = (n: number, what: string) => Array.from({ length: n }, (_, i) => `${what} ${i + 1}: the parser reads the week of each date and checks it against the calendar.`).join("\n");
  items.splice(4, 0,
    { kind: "you", key: "f1", text: "Here's the log:\n" + lines(52, "log line"), at: now - 280_000 },
    { kind: "claude", key: "f2", text: "## What the log says\n\n" + lines(30, "- Point") + "\n\n```ts\n" + lines(20, "// step") + "\n```\n\nThat's all of it.", at: now - 270_000 },
    { kind: "you", key: "f3", text: "!cat weeks.txt", command: { shell: true, output: lines(60, "\x1b[32mweek\x1b[0m") }, at: now - 260_000 },
    { kind: "tool", key: "f4", name: "Read", line: "Read: weeks.ts", status: "ok", input: "file_path: /home/alice/projects/webapp/src/weeks.ts",
      output: Array.from({ length: 90 }, (_, i) => `${String(i + 1).padStart(6)}\texport const week${i + 1} = ${i + 1};`).join("\n"), summary: "90 lines", at: now - 250_000 });
  items.push({ kind: "claude", key: "f5", text: "## Done\n\n" + lines(45, "- Fixed"), at: now - 5_000 });
  if (params.get("more") === "1")
    setTimeout(() => send({ type: "conversation", answer: { ok: true, more: true, stamp: "2", items: [...items,
      { kind: "claude", key: "f6", text: "## And one more\n\n" + lines(50, "- Also"), at: Date.now() }] } }), 800);
  if (fold === "all") setTimeout(() => send({ type: "key", key: "fold" }), 900);
}

// ?find=parser: the find bar with that typed in; &step=N: Enter N times (&back=1: Shift+Enter)
const findQuery = params.get("find");
if (findQuery !== null)
  setTimeout(() => {
    send({ type: "key", key: "find" });
    setTimeout(() => {
      const input = document.querySelector<HTMLInputElement>(".pane-find-text");
      if (!input) return;
      input.value = findQuery;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      const steps = Number(params.get("step") ?? 0);
      for (let i = 0; i < steps; i++)
        setTimeout(() => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: params.get("back") === "1", bubbles: true, cancelable: true })),
                   300 + i * 200);
    }, 200);
  }, 700);

// ?scroll=top: the list scrolled to its top once it's drawn (&by=N px down from there)
// ?menu=list|box: the right-click menu, on a reply of Claude's (a word of it selected) or on the reply box
const menuOn = params.get("menu");
if (menuOn)
  setTimeout(() => {
    const at = document.querySelector<HTMLElement>(menuOn === "box" ? ".pane-reply" : ".pane-claude[data-key]:not(.pane-asked) p");
    if (!at) return;
    if (menuOn === "list") {
      const range = document.createRange();
      range.selectNodeContents(at);
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
    }
    const r = at.getBoundingClientRect();
    at.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 8 }));
  }, 1500);

if (params.get("scroll") === "top")
  setTimeout(() => {
    const list = document.querySelector<HTMLElement>(".pane-list");
    if (list) list.scrollTop = Number(params.get("by") ?? 0);
  }, 1200);
