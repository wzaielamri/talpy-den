// Feeds the chat tab's page made-up data, the way src/chatPane.ts would: the
// chat, its conversation, and its review when the page asks for it.

import "../webview/chat";
import type { PaneChat, PaneHostMessage, PaneItem, ReviewAnswer } from "../src/shared/pane";

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
  chatId: "demo-chat",
  sessionId: "demo-chat",
  profileDir: ".claude",
  name: "Fix the date parser",
  cwd: "/home/alice/projects/webapp",
  state: ask ? "waiting" : "working",
  stateText: ask ? "Needs input · 1m" : "Working · 6m",
  route: params.get("route") === "terminal" ? "terminal" : "tmux",
  canMove: params.get("route") === "terminal",
  busy: true,
  atWork: !ask,
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

// what the page sends, answered as the extension would
// ?type=TEXT: typed into the reply box (to see what it offers)
const typed = params.get("type");
if (typed)
  setTimeout(() => {
    const box = document.querySelector<HTMLTextAreaElement>(".pane-reply");
    if (!box) return;
    box.focus();
    box.value = typed;
    box.setSelectionRange(typed.length, typed.length);
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }, 300);

window.addEventListener("harness-post", (e: Event) => {
  const m = (e as CustomEvent).detail as { type: string };
  if (m.type === "ready") {
    send({ type: "chat", chat });
    send({ type: "conversation", answer: { ok: true, items, more: true, stamp: "1" } });
    const tab = params.get("tab");   // ?tab=steps
    if (tab) send({ type: "result", kind: "tab:" + tab, ok: true, message: "" });
  } else if (m.type === "picture") {
    const id = (m as unknown as { id: string }).id;
    setTimeout(() => send({ type: "picture", id, path: `/home/alice/.cache/talpy-den/images/20261026-1015${id.slice(-2)}.png`, error: "" }), 200);
  } else if (m.type === "review") {
    send({ type: "review", answer: review, error: "" });
  } else if (m.type === "complete") {
    send({ type: "offers", offers: {
      commands: [{ name: "/compact", about: "Free up context by summarizing the conversation so far", kind: "Claude" },
                 { name: "/context", about: "Show how full the context is", kind: "Claude" },
                 { name: "/release", about: "Cut a release", kind: "project" }],
      files: ["src/parser.ts", "src/parse_date.ts", "tests/parser.test.ts", "README.md"],
      history: ["Fix the date parser", "Run the tests again"],
    } });
  }
});

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
