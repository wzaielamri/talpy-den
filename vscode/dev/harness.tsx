// Feeds the webview demo data, the way the extension would: a state after
// "ready", then a new one every few seconds with the story moved on.

import "../webview/main";
import { demoPerms, demoProjects, demoState, demoWeek } from "../src/shared/demo";
import type { HostMessage } from "../src/shared/types";
import { setFocus, setTab, toggleProject, toggleRecent, toggleStarred, uiState } from "../webview/util/ui";
import { askMove } from "../webview/components/MoveAsk";

const params = new URLSearchParams(location.search);
let phase = Number(params.get("phase")) || 0;

function send(message: HostMessage): void {
  window.postMessage(message, "*");
}

function sendState(): void {
  const state = demoState(Date.now(), phase);
  // ?digest=1: the card that sums up what happened while you were away
  if (params.get("digest") === "1")
    state.digest = {
      title: "While you were away (1h 12m)",
      lines: ["Needs you: Release notes for 2.0 (waiting 22m)", "Finished: Fix the date parser, Nightly dependency check", "5h limit reset"],
      at: Date.now(),
      first: { key: "demo-2", sessionId: "demo-2", profileDir: ".claude", name: "Release notes for 2.0" },
    };
  // ?rules=0: the Recap tab's rule suggestions left out (the recapRules setting)
  if (params.get("rules") === "0") state.settings.recapRules = false;
  // ?loggedOut=1: the last account isn't logged in (Log in…)
  const groups = state.status?.groups ?? [];
  if (params.get("loggedOut") === "1" && groups.length)
    groups[groups.length - 1] = { ...groups[groups.length - 1], loggedOut: true, loginCommand: "claude auth login", limits: null };
  // ?default=1: a second account here, and the first one marked the default
  if (params.get("default") === "1" && groups.length)
    groups.splice(1, 0, { ...groups[0], id: "demo-second", name: "work", title: "work · Team", plan: "Team", defaultHere: false, sessions: [] }),
      (groups[0] = { ...groups[0], defaultHere: true });
  // ?stopped=1: two chats here a usage limit stopped, one queued to go on that keeps going
  const hostStopped = state.hosts.flatMap((h) => h.result?.groups ?? []).flatMap((g) => g.sessions).find((s) => s.stopped);
  if (params.get("stopped") === "1" && hostStopped && groups.length && state.status) {
    const copy = (id: string, name: string) => ({ ...hostStopped, key: id, sessionId: id, chatId: id, name, overlaps: [] });
    const later = copy("demo-stopped-2", "Port the importer");
    groups[0].sessions.push(copy("demo-stopped-1", "Migrate the schema"), later);
    state.status.keep = [{ chat: later.chatId, profile: ".claude", name: later.name, since: Date.now(), wentOnAt: null, tries: 0, note: "", error: "" }];
    state.status.queue = [...(state.status.queue ?? []), {
      id: "q-later", host: "", profile: ".claude", account: groups[0].title, folder: later.cwd, folderShort: later.cwdShort, prompt: "",
      plan: null, planProfile: null, planTitle: "", startAt: (later.stopped?.resetsAt ?? Date.now()) + 60000, createdAt: Date.now(),
      error: "", due: false, chat: later.chatId, name: later.name, scheduled: false,
    }];
  }
  // ?unseen=1: a chat that keeps going on an SSH host that isn't shown, its go-on queued, and a go-on
  // in a container on it that couldn't reach it (UnseenLines)
  if (params.get("unseen") === "1" && state.status) {
    const kept = { chat: "demo-unseen-1", profile: ".claude", host: "gpu-lab", name: "Train the ranker", since: Date.now(), wentOnAt: null, tries: 0, note: "", error: "" };
    state.status.keep = [...(state.status.keep ?? []), kept];
    const task = { profile: ".claude", account: "gpu-lab · Max", folder: "/srv/app", folderShort: "/srv/app", prompt: "", plan: null,
      planProfile: null, planTitle: "", createdAt: Date.now(), due: false, scheduled: false };
    state.status.queue = [...(state.status.queue ?? []),
      { ...task, id: "q-unseen-1", host: "gpu-lab", startAt: Date.now() + 50 * 60_000, error: "", chat: kept.chat, name: kept.name },
      { ...task, id: "q-unseen-2", host: "docker:web@gpu-lab", startAt: Date.now() - 60_000, chat: "demo-unseen-2", name: "Fix the parser",
        error: "Can't reach gpu-lab: Connection timed out. It starts once web on gpu-lab answers again" }];
  }
  // ?stars=1: a chat at work, a recent chat and a plan starred, and an old chat and plan under Starred
  const first = groups[0];
  if (params.get("stars") === "1" && first) {
    const DAY = 86400_000;
    if (first.sessions[0]) first.sessions[0].starred = true;
    const recent = first.recent?.[0];
    if (recent) {
      recent.starred = true;
      first.starred = [
        { ...recent, key: recent.key + "|starred" },
        { ...recent, key: "demo-old|starred", sessionId: "demo-old", name: "Rate limiter design", lastActive: Date.now() - 9 * DAY, stopped: null, recap: null },
      ];
    }
    const plan = first.plans?.[0];
    if (plan) {
      plan.starred = true;
      first.starredPlans = [
        { ...plan, key: plan.key + "|starred" },
        { ...plan, key: "demo-old-plan|starred", slug: "old-plan", title: "Cache the API answers", updatedAt: Date.now() - 9 * DAY, chatId: null },
      ];
    }
  }
  // ?many=1: lists shown a page at a time: 10 of 23 recent chats here, 7 starred ones
  if (params.get("many") === "1" && first?.recent?.[0]) {
    const r = first.recent[0];
    const names = ["Bump the lockfile", "Why is CI slow", "Draft the 2.1 roadmap", "Split the parser module", "Port the importer", "Add retries to the client",
                   "Fix the flaky upload test", "Rename the settings keys", "Tidy the README", "Profile the startup"];
    first.recent = names.map((name, i) => ({ ...r, key: `many-${i}`, sessionId: `many-${i}`, name, lastActive: Date.now() - (i + 1) * 3_600_000 }));
    first.recentCount = 23;
    first.starred = names.slice(0, 7).map((name, i) => ({ ...r, key: `many-${i}|starred`, sessionId: `many-s${i}`, name, starred: true,
                                                          lastActive: Date.now() - (i + 9) * 86_400_000 }));
  }
  // (?open=1: Recent chats unfolded; with ?stars=1 the starred lists too)
  if (params.get("open") === "1" && first && !uiState.get().recent[first.id]) toggleRecent(first.id);
  if (params.get("stars") === "1" && params.get("open") === "1" && first)
    for (const fold of ["|chats", "|plans"]) if (!uiState.get().starred[first.id + fold]) toggleStarred(first.id + fold);
  // ?question=1: the chat that waits asks Claude's questions instead of a permission
  const waiting = groups.flatMap((g) => g.sessions).find((s) => s.state === "waiting" && s.permission);
  if (params.get("question") === "1" && waiting?.permission)
    waiting.permission = { ...waiting.permission, tool: "AskUserQuestion", line: "Which changelog style?", command: "", file: "", diff: [], always: "",
      questions: [{ question: "Which changelog style should the 2.0 notes use?", header: "Style", multiSelect: false,
                    options: [{ label: "Keep a Changelog (Recommended)", description: "Added / Changed / Fixed sections" },
                              { label: "One paragraph per feature", description: "As the 1.x notes" }] }] };
  // ?banner=0: without the "Demo data" line, for the README's screenshots
  if (params.get("banner") === "0") state.demo = false;
  // ?keep=1: the first chat at work keeps going (after each usage limit), and one gave up
  if (params.get("keep") === "1" && state.status) {
    const chats = groups.flatMap((g) => g.sessions);
    const working = chats.find((s) => s.state === "working");
    const other = chats.find((s) => s !== working && s.state !== "working");
    const kept = (chat: string, error = "") => ({ chat, profile: ".claude", name: "", since: Date.now(), wentOnAt: null, tries: 0, note: "", error });
    state.status.keep = [
      ...(working ? [kept(working.chatId || working.sessionId)] : []),
      ...(other ? [kept(other.chatId || other.sessionId, "Gave up after 5 tries: it didn't go on")] : []),
    ];
  }
  // ?live=1: live mode: the first chat at work does a step (an edit, with its lines)
  if (params.get("live") === "1") {
    const working = groups.flatMap((g) => g.sessions).find((s) => s.state === "working" && s.pid);
    const at = Date.now() + 60000;
    if (working)
      state.live = { [working.sessionId]: { sessionId: working.sessionId, pid: working.pid, state: "working", doing: "Edit: parser.py", at,
        steps: [{ id: "t1", tool: "Edit", text: "Edit: parser.py", at, end: at, ok: true, add: 12, del: 3 }], agents: [] } };
  }
  send({ type: "state", state });
}

setTimeout(() => {
  sendState();
  send({ type: "visible", visible: true });
  // ?week=1: the Week tab, its days there from the start (a screenshot doesn't wait)
  // (?span=day or all: the Recap tab starts on it)
  const span = params.get("span") === "day" || params.get("span") === "all" ? (params.get("span") as "day" | "all") : "week";
  if (params.get("week") === "1") send({ type: "week", back: 0, account: "", span, recap: demoWeek(Date.now(), 0, "", span), error: "" });
  if (params.get("perms") === "1") send({ type: "perms", data: demoPerms(Date.now()), error: "" });
  // ?tab=projects: that tab (&project=webapp: that project opened)
  if (params.get("tab") === "projects") {
    setTab("projects");
    send({ type: "projects", data: demoProjects(Date.now()), error: "" });   // (at once: a screenshot doesn't wait)
  }
  const project = demoProjects(Date.now()).projects.find((p) => p.name === params.get("project"));
  if (project && !uiState.get().projects[project.path]) toggleProject(project.path);
  // ?drop=webapp: a plan of the plans whose chat is gone dropped on that project: its question
  const dropOn = demoProjects(Date.now()).projects.find((p) => p.name === params.get("drop"));
  const gone = demoProjects(Date.now()).projects.find((p) => !p.path)?.plans[0];
  if (dropOn && gone) setTimeout(() => askMove("drop|" + dropOn.path, { groupId: "", id: gone.key, folder: dropOn.path }, false), 0);
  // ?focus=1: the focus view
  if (params.get("focus") === "1") setFocus(true);
  // ?scroll=N: to see the top stay put over the list
  const scroll = Number(params.get("scroll"));
  if (scroll) setTimeout(() => window.scrollTo(0, scroll), 300);
}, 0);

setInterval(() => {
  phase += 1;
  sendState();
}, 4000);

setTimeout(() => send({ type: "petEvent", kind: "done", text: "Fix the date parser is done!", key: "demo-1" }), 2000);

// The Recap tab asks for its days, the Permissions tab for what it shows: the made-up ones
window.addEventListener("harness-post", (event) => {
  const m = (event as CustomEvent).detail as { type: string; back?: number; account?: string; span?: "day" | "week" | "all" };
  if (m.type === "perms") send({ type: "perms", data: demoPerms(Date.now()), error: "" });
  if (m.type === "projects") send({ type: "projects", data: demoProjects(Date.now()), error: "" });
  // (Move to project…: a made-up answer, as jump.py --move-plan --describe gives one)
  if (m.type === "moveDescribe") {
    const d = m as unknown as { key: string; folder?: string; back?: boolean };
    const folder = d.folder || "/home/alice/projects/webapp";
    const short = folder.replace(/^\/home\/[^/]+/, "~");
    send({ type: "moveAsk", key: d.key, ok: true, message: "", answer: {
      title: "Date parser rewrite", slug: "brave-green-otter", back: !!d.back, project: folder, projectShort: short,
      target: folder + "/.claude/plans/brave-green-otter.md", targetShort: short + "/.claude/plans/brave-green-otter.md",
      setting: "", settingsFile: short + "/.claude/settings.local.json", git: true, exists: false, free: "", account: "work",
      lost: false, choices: [{ path: folder, short }, { path: "/home/alice/projects/api", short: "~/projects/api" }], default: folder } });
  }
  if (m.type !== "week") return;
  const back = m.back ?? 0;
  const account = m.account ?? "";
  const span = m.span ?? "week";
  send({ type: "week", back, account, span, recap: demoWeek(Date.now(), back, account, span), error: "" });
});
