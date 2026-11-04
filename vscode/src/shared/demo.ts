// Made-up data for the demo mode (README screenshots, trying the view without
// Claude Code) and for the webview's dev harness. Nothing here is real: the
// accounts, folders, hosts and chats are invented, times are relative to now.

import type { LimitAccount, LimitHistory, LimitPeriod, ProjectsData, WeekLane, Agent, ChatStats, Group, HostState, PermsData, Session, Status, UsageStats, ViewState, WeekChat, WeekDay, WeekRecap, WeekSpan } from "./types";

const MIN = 60000;
const HOUR = 60 * MIN;

function session(now: number, partial: Partial<Session> & Pick<Session, "key" | "name" | "state">): Session {
  return {
    profileDir: ".claude",
    sessionId: partial.key,
    chatId: partial.key,
    pid: 4242,
    cwd: "/home/alice/projects/webapp",
    cwdShort: "~/projects/webapp",
    profile: "personal",
    kind: "interactive",
    entrypoint: "cli",
    reason: "",
    waitingFor: "",
    detail: "",
    since: now - 5 * MIN,
    startedAt: now - HOUR,
    context: 34,
    model: "Opus",
    costUsd: 1.42,
    agents: null,
    shared: null,
    jobId: null,
    jobSessionId: null,
    openCommand: "echo 'Demo mode: nothing to open'",
    stopCommand: null,
    ...partial,
  };
}

function agents(now: number): Session["agents"] {
  const tree: Agent[] = [
    {
      id: "a1", parent: null, depth: 0, type: "Explore", description: "Find the date parsing code", status: "done",
      activity: "parseIsoWeek() in src/date/week.ts", started: now - 9 * MIN, updated: now - 6 * MIN, model: "Haiku 4.5",
      task: "Find where ISO week dates are parsed and why week 53 can land in the wrong year. Read only; list the files and functions involved.",
      steps: ["Grep: isoWeek", "Read: parse.ts", "Read: week.ts", "Grep: getFullYear"],
      report: "parseIsoWeek() in src/date/week.ts\n\n• It takes the year from the week's Monday, so week 53 of 2026 lands in 2027.\n• parse.ts calls it for every \"YYYY-Www\" string.\n• Tests: test/date.test.ts covers weeks 1–52 only.",
      toolCalls: 7, tokens: 182_400,
    },
    {
      id: "a2", parent: null, depth: 0, type: "general-purpose", description: "Write tests for the parser", status: "running",
      activity: "Bash: npm test -- date", started: now - 4 * MIN, updated: now - 10000, model: "Sonnet 4.5",
      task: "Add tests for ISO week 53 (2020, 2026) and the years around it to test/date.test.ts, then run them.",
      steps: ["Read: date.test.ts", "Agent: Look for existing fixtures", "Edit: date.test.ts", "Bash: npm test -- date"],
      report: "", toolCalls: 5, tokens: 96_300,
    },
    {
      id: "a3", parent: "a2", depth: 1, type: "Explore", description: "Look for existing fixtures", status: "running",
      activity: "Read: weeks.json", started: now - 2 * MIN, updated: now - 5000,
      task: "Are there fixtures with ISO week dates under test/fixtures?", steps: ["Glob: test/fixtures/**", "Read: weeks.json"],
      report: "", toolCalls: 2, tokens: null,
    },
  ];
  return { running: 2, done: 1, stopped: 0, total: 3, tree };
}

function totals(scale: number) {
  return {
    input: 120000 * scale,
    output: 340000 * scale,
    cacheRead: 9800000 * scale,
    cacheWrite: 410000 * scale,
    total: 10670000 * scale,
    messages: Math.round(180 * scale),
    shared: 0,
  };
}

// The last 14 days of an account: a busy week, a quiet weekend, today
function usageStats(now: number, scale: number, folders: [string, string][]): UsageStats {
  const shape = [0, 0.2, 0.9, 1.6, 2.4, 1.1, 0, 0, 0.7, 1.9, 3.1, 2.2, 1.4, 1];
  const days = shape.map((f, i) => {
    const d = new Date(now - (shape.length - 1 - i) * 24 * HOUR);
    const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const total = Math.round(f * 21_000_000 * scale);
    return { day, total, output: Math.round(total / 31), messages: Math.round(f * 160 * scale), chats: f ? Math.max(1, Math.round(f * 2.4)) : 0, prompts: Math.round(f * 18 * scale) };
  });
  const total = days.reduce((n, d) => n + d.total, 0);
  const prompts = days.reduce((n, d) => n + d.prompts, 0);
  const shares = [0.58, 0.27, 0.1, 0.05];
  return {
    days,
    projects: folders.map(([name, path], i) => ({
      name,
      path,
      total: Math.round(total * shares[i]),
      output: Math.round((total * shares[i]) / 31),
      prompts: Math.round(prompts * shares[i]),
    })),
    models: [
      { model: "Opus 5.5", total: Math.round(total * 0.86) },
      { model: "Sonnet 5.5", total: Math.round(total * 0.13) },
      { model: "Haiku 5.5", total: Math.round(total * 0.01) },
    ],
    sum: { total, output: Math.round(total / 31), chats: 23, prompts, activeDays: days.filter((d) => d.total).length },
  };
}

function chatStats(now: number, prompts: number, minutes: number, tools: [string, number][], total: number): ChatStats {
  return {
    prompts,
    toolCalls: tools.reduce((n, [, c]) => n + c, 0),
    tools,
    tokens: { input: Math.round(total * 0.004), output: Math.round(total / 30), cacheRead: Math.round(total * 0.9), cacheWrite: Math.round(total * 0.06), total },
    workedMs: minutes * MIN,
    startedAt: now - 3 * HOUR,
    lastAt: now - 20000,
  };
}

function personal(now: number, phase: number): Group {
  const parserState = phase % 3 === 2 ? "idle" : "working";
  return {
    id: "demo-personal",
    name: "personal",
    plan: "Max",
    title: "personal · Max",
    profiles: ["personal"],
    profileKeys: [".claude"],
    sessions: [
      session(now, {
        key: "demo-1",
        name: "Fix the date parser",
        state: parserState,
        since: now - (parserState === "working" ? 7 : 1) * MIN,
        agents: parserState === "working" ? agents(now) : null,
        context: 62,
        peek:
          parserState === "working"
            ? { activity: "Bash: npm test -- parser", prompt: "The date parser breaks on ISO weeks; fix it and add tests.", reply: "Found it: week 53 wraps to the next year. Fixing the year rollover now.", replyLine: "Found it: week 53 wraps to the next year. Fixing the year rollover now.", at: now - 20000, mode: "auto" }
            : {
                activity: "", prompt: "The date parser breaks on ISO weeks; fix it and add tests.", reply: "Fixed: ISO week 53 no longer rolls over into the next year.\n\n• parseIsoWeek() takes the year from the week's Thursday\n• 12 new tests in date.test.ts, all passing\n\nWant me to open a pull request?", replyLine: "Fixed: ISO week 53 no longer rolls over into the next year.", at: now - 60000, mode: "auto",
                recap: { text: "You asked me to fix ISO week parsing; it's fixed, with 12 new tests that pass. Next step: tell me whether to open a pull request.", at: now - 30000 },
              },
        changes: { count: 3, files: ["src/date/parse.ts", "src/date/week.ts", "test/date.test.ts"] },
        stats: chatStats(now, 4, 38, [["Bash", 41], ["Read", 18], ["Edit", 9], ["Grep", 6], ["Agent", 3]], 18_400_000),
        tasks: {
          done: parserState === "working" ? 2 : 4,
          total: 4,
          current: parserState === "working" ? "Writing tests for week 53" : "",
          items: [
            { subject: "Reproduce the week-53 bug", status: "completed" },
            { subject: "Fix the year rollover", status: "completed" },
            { subject: "Write tests for week 53", status: parserState === "working" ? "in_progress" : "completed" },
            { subject: "Run the whole test suite", status: parserState === "working" ? "pending" : "completed" },
          ],
        },
      }),
      session(now, {
        key: "demo-2",
        name: "Release notes for 2.0",
        state: "waiting",
        reason: "permission",
        waitingFor: "permission prompt",
        detail: "Wants to run: git tag v2.0.0",
        cwd: "/home/alice/projects/api-server",
        cwdShort: "~/projects/api-server",
        since: now - 2 * MIN,
        context: 18,
        model: "Sonnet",
        peek: { activity: "Bash: git tag v2.0.0", prompt: "Write the release notes for 2.0 and tag it.", reply: "The notes are in CHANGELOG.md. Tagging v2.0.0 next.", replyLine: "The notes are in CHANGELOG.md. Tagging v2.0.0 next.", at: now - 2 * MIN, mode: "acceptEdits" },
        plan: { slug: "brave-green-otter", title: "Release 2.0", path: "/home/alice/.claude/plans/brave-green-otter.md", updatedAt: now - 2 * HOUR, edited: true },
        changes: { count: 1, files: ["CHANGELOG.md"] },
        stats: chatStats(now, 2, 6, [["Bash", 7], ["Read", 4], ["Write", 1]], 2_100_000),
        reply: "tmux",
        permission: { tool: "Bash", line: "Bash: git tag v2.0.0", command: "git tag v2.0.0", file: "", diff: [],
                      always: "Bash(git tag v2.0.0)", request: "demo-request", answer: "hook" },
      }),
      session(now, {
        key: "demo-3",
        name: "Nightly dependency check",
        state: "done",
        kind: "bg",
        pid: null,
        jobId: "demo-job",
        cwd: "/home/alice/notes",
        cwdShort: "~/notes",
        since: now - 3 * HOUR,
        context: 9,
        detail: "All dependencies are up to date",
        changes: { count: 2, files: ["package.json", "package-lock.json"] },
        review: { editedAt: now - 3 * HOUR - 5 * MIN, tests: { command: "npm test", ok: true, at: now - 3 * HOUR - 2 * MIN } },
      }),
    ],
    limits: {
      updatedAt: now - 3 * MIN,
      windows: [
        {
          key: "five_hour",
          label: "5h",
          pct: 63,
          resetsAt: now + 2 * HOUR + 14 * MIN,
          reset: false,
          forecast: { evenPct: 55, rate: 24, atReset: 116, fullAt: now + HOUR + 32 * MIN, basis: "hour" },
        },
        {
          key: "seven_day",
          label: "7d",
          pct: 41,
          resetsAt: now + 3 * 24 * HOUR,
          reset: false,
          forecast: { evenPct: 57, rate: 0.4, atReset: 70, fullAt: null, basis: "window" },
        },
      ],
    },
    tokens: { today: totals(1), week: totals(5.3), models: [{ model: "Opus", total: 8100000 }, { model: "Sonnet", total: 2570000 }] },
    stats: usageStats(now, 1, [
      ["webapp", "~/projects/webapp"],
      ["api-server", "~/projects/api-server"],
      ["notes", "~/notes"],
      ["~", "~"],
    ]),
    chatProfile: ".claude",
    shareProfile: null,
    projects: [
      { path: "/home/alice/projects/webapp", short: "~/projects/webapp", newChatCommand: "echo 'Demo mode'" },
      { path: "/home/alice/projects/api-server", short: "~/projects/api-server", newChatCommand: "echo 'Demo mode'" },
      { path: "/home/alice", short: "~", newChatCommand: "echo 'Demo mode'" },
    ],
    sharedHere: [],
    recentCount: 2,
    recent: [
      { key: "demo-r1", sessionId: "demo-r1", name: "Explain the build pipeline", cwd: "/home/alice/projects/webapp", cwdShort: "~/projects/webapp", lastActive: now - 5 * HOUR, profile: "personal", profileDir: ".claude", shared: false, openCommand: "echo 'Demo mode'" },
      { key: "demo-r2", sessionId: "demo-r2", name: "Rename the config module", cwd: "/home/alice/projects/api-server", cwdShort: "~/projects/api-server", lastActive: now - 26 * HOUR, profile: "personal", profileDir: ".claude", shared: false, openCommand: "echo 'Demo mode'" },
    ],
    plans: [
      {
        key: "demo-plan-1", slug: "brave-green-otter", title: "Release 2.0", path: "/home/alice/.claude/plans/brave-green-otter.md",
        profileDir: ".claude", profile: "personal", updatedAt: now - 2 * HOUR, shared: false, chatId: "demo-2", chatProfileDir: ".claude",
        cwd: "/home/alice/projects/api-server", cwdShort: "~/projects/api-server", openCommand: "echo 'Demo mode'",
      },
      {
        key: "demo-plan-2", slug: "quiet-amber-heron", title: "Move the settings page to the new router", path: "/home/alice/.claude/plans/quiet-amber-heron.md",
        profileDir: ".claude", profile: "personal", updatedAt: now - 3 * 24 * HOUR, shared: false, chatId: null, chatProfileDir: null,
        cwd: "", cwdShort: "",
      },
    ],
    memories: [
      {
        key: "demo-mem-1", name: "test-command", description: "Run the tests with npm test -- --runInBand: the parallel run is flaky on this machine",
        type: "project", path: "/home/alice/.claude/projects/-home-alice-projects-webapp/memory/test-command.md",
        folder: "/home/alice/projects/webapp", folderShort: "~/projects/webapp", folderGone: false, profileDir: ".claude", profile: "personal", updatedAt: now - 4 * HOUR,
      },
      {
        key: "demo-mem-2", name: "short-commit-messages", description: "Commit messages: one short line in the present tense, no body",
        type: "feedback", path: "/home/alice/.claude/projects/-home-alice-projects-api-server/memory/short-commit-messages.md",
        folder: "/home/alice/projects/api-server", folderShort: "~/projects/api-server", folderGone: false, profileDir: ".claude", profile: "personal", updatedAt: now - 2 * 24 * HOUR,
      },
    ],
    instructions: [
      {
        key: ".claude/CLAUDE.md/memory", name: "CLAUDE.md", description: "Your instructions for every chat on this account", type: "account",
        path: "/home/alice/.claude/CLAUDE.md", folder: "", folderShort: "", folderGone: false, profileDir: ".claude", profile: "personal", updatedAt: now - 9 * 24 * HOUR,
      },
    ],
    homeChatCommand: "echo 'Demo mode'",
  };
}

function buildServer(now: number, phase: number): Status {
  const state = phase % 2 === 0 ? "working" : "idle";
  return {
    ok: true,
    generatedAt: now,
    overall: state,
    counts: { waiting: 0, working: state === "working" ? 1 : 0, idle: state === "idle" ? 1 : 0, done: 0, limit: 0 },
    dismissed: 0,
    canShare: false,
    errors: [],
    host: "build-server",
    groups: [
      {
        id: "demo-team",
        name: "team",
        plan: "Team",
        title: "team · Team",
        profiles: ["team"],
        profileKeys: [".claude"],
        sessions: [
          session(now, {
            key: "demo-4",
            name: "Train the ranking model",
            state,
            cwd: "/home/alice/experiments/ranking",
            cwdShort: "~/experiments/ranking",
            since: now - (state === "working" ? 24 : 2) * MIN,
            context: 87,
            model: "Opus",
            peek: {
              activity: state === "working" ? "Bash: python train.py --epochs 20" : "",
              prompt: "Train the ranking model on the new click data.",
              reply: state === "working" ? "Epoch 7/20: validation NDCG 0.412." : "Done: NDCG 0.431 on validation, up from 0.398.",
              replyLine: state === "working" ? "Epoch 7/20: validation NDCG 0.412." : "Done: NDCG 0.431 on validation, up from 0.398.",
              at: now - MIN,
            },
            changes: { count: 2, files: ["configs/ranking.yaml", "train.py"] },
            stats: chatStats(now, 3, 24, [["Bash", 22], ["Read", 9], ["Edit", 4]], 9_700_000),
            overlaps: [{ key: "demo-5", name: "Evaluate on the holdout set", sessionId: "demo-5", profileDir: ".claude", count: 1, files: ["train.py"] }],
          }),
          session(now, {
            overlaps: [{ key: "demo-4", name: "Train the ranking model", sessionId: "demo-4", profileDir: ".claude", count: 1, files: ["train.py"] }],
            key: "demo-5",
            name: "Evaluate on the holdout set",
            state: "idle",
            cwd: "/home/alice/experiments/ranking",
            cwdShort: "~/experiments/ranking",
            since: now - 18 * MIN,
            context: 41,
            model: "Opus",
            peek: { activity: "", prompt: "Evaluate the new model on the holdout set.", reply: "", replyLine: "", at: now - 18 * MIN },
            stopped: { kind: "limit", window: "five_hour", text: "You've hit your session limit · resets 4:10pm", at: now - 18 * MIN, resetsAt: now + 41 * MIN, over: false },
          }),
        ],
        limits: {
          updatedAt: now - 9 * MIN,
          windows: [
            {
              key: "five_hour",
              label: "5h",
              pct: 92,
              resetsAt: now + 41 * MIN,
              reset: false,
              forecast: { evenPct: 86, rate: 11, atReset: 99.5, fullAt: null, basis: "hour" },
            },
            { key: "seven_day", label: "7d", pct: 55, resetsAt: now + 5 * 24 * HOUR, reset: false },
          ],
        },
        tokens: { today: totals(0.6), week: totals(2.2), models: [{ model: "Opus", total: 6400000 }] },
        stats: usageStats(now, 0.6, [["ranking", "~/experiments/ranking"]]),
        chatProfile: ".claude",
        shareProfile: null,
        projects: [{ path: "/home/alice/experiments/ranking", short: "~/experiments/ranking", newChatCommand: "echo 'Demo mode'" }],
        sharedHere: [],
        recent: [],
        homeChatCommand: "echo 'Demo mode'",
      },
    ],
  };
}

// As the backend lists an account's chats: the ones that need you first
// (asking longest first), the others in the order they started
function listed<G extends { sessions: Session[] }>(g: G): G {
  const order = (s: Session): [number, number] => (s.state === "waiting" ? [0, s.since ?? 0] : [1, s.startedAt ?? s.since ?? 0]);
  g.sessions.sort((a, b) => order(a)[0] - order(b)[0] || order(a)[1] - order(b)[1] || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return g;
}

// phase moves the story on (a chat finishes, the host's chat starts again…)
export function demoState(now: number, phase = 0): ViewState {
  const groups = [listed(personal(now, phase))];
  const status: Status = {
    ok: true,
    generatedAt: now,
    overall: "waiting",
    counts: { waiting: 1, working: 1, idle: 0, done: 1, limit: 0 },
    groups,
    dismissed: 0,
    canShare: false,
    errors: [],
    reviewed: {},
    reviewedSince: now - 24 * HOUR,
    queue: [
      {
        id: "demo-q1", host: "", profile: ".claude", account: "personal · Max", folder: "/home/alice/projects/webapp",
        folderShort: "~/projects/webapp", prompt: "Update the dependencies and run the tests", plan: null, planProfile: null,
        planTitle: "", startAt: now + 2 * HOUR + 15 * MIN, createdAt: now - 5 * MIN, error: "", due: false,
      },
    ],
  };
  const hosts: HostState[] = [
    { name: "build-server", loading: false, ok: true, error: "", result: buildServer(now, phase), updatedAt: now - 12000, current: true },
    { name: "gpu-box", loading: false, ok: false, error: "Can't reach gpu-box: Connection timed out", result: null, updatedAt: 0, current: false },
  ];
  return {
    status,
    errorText: "",
    hosts,
    settings: { showPet: true, chatPets: 5, showTokens: true, recentChats: 5, reopenIn: "terminal" },
    demo: true,
    platformNote: "",
    claudeCode: { available: true, profileKey: ".claude" },
    actionError: "",
    actionInfo: "",
    now,
  };
}

const DEMO_CHATS: WeekChat[] = [
  { name: "Port the date parser", chatId: "demo-1", host: "", profileDir: ".claude", folder: "~/projects/date-parser", cwd: "/home/alice/projects/date-parser", workedMs: 3.2 * HOUR, cost: 41.2, prompts: 14 },
  { name: "Release notes for 2.0", chatId: "demo-2", host: "", profileDir: ".claude", folder: "~/projects/webapp", cwd: "/home/alice/projects/webapp", workedMs: 2.4 * HOUR, cost: 29.9, prompts: 11 },
  { name: "Nightly dependency check", chatId: "demo-3", host: "build-server", profileDir: ".claude", folder: "/srv/pipeline", workedMs: 1.6 * HOUR, cost: 17.3, prompts: 6 },
];

// The Recap tab's recap of made-up days: mornings and afternoons of work, a
// second chat at once now and then, one long wait for your answer, two
// usage limits, the rules the permission prompts you answered ask for
const TOKENS_PER_DOLLAR = 1_853_000; // (a made-up week's tokens, about the breakdown below)

// The Day view's lanes: a few made-up chats through the day (starts: its midnight)
function demoLanes(start: number): WeekLane[] {
  const h = 3_600_000;
  const at = (hours: number) => start + Math.round(hours * h);
  const lane = (id: string, name: string, project: string, parts: [number, number, "w" | "y" | "p"][], host = ""): WeekLane => ({
    key: host + "|" + id, id, host, name, project, profileDir: ".claude",
    parts: parts.map(([a, b, k]) => [at(a), at(b), k] as [number, number, "w" | "y" | "p"]),
    workedMs: parts.filter((p) => p[2] === "w").reduce((n, p) => n + (p[1] - p[0]) * h, 0),
    waitedMs: parts.filter((p) => p[2] === "y").reduce((n, p) => n + (p[1] - p[0]) * h, 0),
  });
  return [
    lane("demo-1", "Fix the date parser", "webapp", [[9, 9.6, "w"], [9.6, 10.4, "y"], [10.4, 11.2, "w"], [14, 15.1, "w"]]),
    lane("demo-2", "Release notes for 2.0", "api-server", [[9.5, 9.8, "w"], [9.8, 9.9, "y"], [9.9, 10.5, "w"], [16, 16.3, "y"]]),
    lane("demo-3", "Train the ranking model", "ranker", [[10, 12.5, "w"], [12.5, 13.5, "p"], [13.5, 17, "w"]], "build-server"),
    lane("demo-4", "Nightly dependency check", "webapp", [[11, 11.3, "w"]]),
  ];
}

export function demoWeek(now: number, back = 0, account = "", span: WeekSpan = "week"): WeekRecap {
  if (span !== "week") {
    // a day: today's (or the one back days before) out of the made-up week;
    // everything: that week and the one before, a row each
    const week = demoWeek(now, span === "day" ? Math.floor(back / 7) : 0, account);
    if (span === "day") {
      const d = week.days[Math.max(0, week.days.length - 1 - (back % 7))];
      return { ...week, span, back, backMax: 13, first: week.days[0].day, from: d.day, to: d.day, days: [d], trend: week.trend.slice(-5),
               lanes: demoLanes(d.start) };
    }
    const before = demoWeek(now, 1, account);
    const row = (w: WeekRecap): WeekDay => ({
      ...w.days[0], to: w.to, you: [], work: [], wait: [], limits: [], end: w.days[w.days.length - 1].end,
      youMs: w.sum.youMs, workedMs: w.sum.workedMs, busyMs: w.sum.busyMs, waitMs: w.sum.waitMs, prompts: w.sum.prompts, cost: w.sum.cost,
      tokenTotal: w.sum.tokenTotal,
      chats: w.chats.slice(0, 3),
    });
    const sum = { ...week.sum, youMs: week.sum.youMs + before.sum.youMs, workedMs: week.sum.workedMs + before.sum.workedMs,
      prompts: week.sum.prompts + before.sum.prompts, cost: week.sum.cost + before.sum.cost,
      tokenTotal: week.sum.tokenTotal + before.sum.tokenTotal };
    return { ...week, span, back: 0, backMax: 0, first: before.from, from: before.from, previous: null, trend: [],
      days: [row(week), row(before)], sum };
  }
  const today = new Date(now);
  const midnight = (offset: number) =>
    new Date(today.getFullYear(), today.getMonth(), today.getDate() - 7 * back - offset).getTime();
  const isoDay = (t: number) => {
    const d = new Date(t);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const scale = account ? 0.6 : 1;
  const days: WeekDay[] = [];
  for (let i = 6; i >= 0; i--) {
    const start = midnight(i);
    const end = midnight(i - 1);
    const weekend = [0, 6].includes(new Date(start).getDay());
    const h = (x: number) => start + x * HOUR;
    const blocks: [number, number, number][] = weekend
      ? [[10.5, 11.2, 1]]
      : [[9.1, 9.9, 1], [10.2, 11.6, 1], [11.6, 12.1, 2], [14, 15.3, 1], [15.3, 15.8, 2], [16.4, 17.5, 1]];
    const work = blocks.map(([a, b, n]) => [h(a), h(b), n] as [number, number, number]).filter((w) => w[0] < now);
    const you: [number, number][] = (weekend ? [[10.4, 11.3]] : [[8.9, 10.4], [11.3, 12.4], [13.8, 14.6], [15.1, 16.1], [17.2, 17.6]])
      .map(([a, b]) => [h(a), h(b)] as [number, number]).filter((y) => y[0] < now);
    const wait: [number, number][] = !weekend && i === 2 ? [[h(18.2), h(21.5)]] : [];
    const limits = !weekend && i === 3 ? [h(11.4), h(15.6)].filter((t) => t < now) : [];
    const workedMs = work.reduce((sum, [a, b, n]) => sum + (Math.min(b, now) - a) * n, 0) * scale;
    days.push({
      day: isoDay(start), start, end, you, work: work.map(([a, b, n]) => [a, Math.min(b, now), n]), wait, limits,
      youMs: you.reduce((sum, [a, b]) => sum + Math.min(b, now) - a, 0) * scale, workedMs,
      busyMs: workedMs * 0.85, waitMs: wait.reduce((sum, [a, b]) => sum + b - a, 0),
      prompts: weekend ? 4 : Math.round(31 * scale), cost: Math.round((weekend ? 9 : 64) * scale * 100) / 100,
      tokenTotal: Math.round((weekend ? 9 : 64) * scale * TOKENS_PER_DOLLAR),
      chats: work.length ? DEMO_CHATS.slice(0, weekend ? 1 : 3).map((c, k) => ({ ...c, workedMs: workedMs / (k + 2), cost: c.cost / 5 })) : [],
    });
  }
  const total = (key: "youMs" | "workedMs" | "busyMs" | "waitMs" | "prompts" | "cost" | "tokenTotal") => days.reduce((sum, d) => sum + d[key], 0);
  const cost = total("cost");
  const week = (k: number) => ({
    youMs: total("youMs") * k, workedMs: total("workedMs") * k, busyMs: total("busyMs") * k, waitMs: total("waitMs") * k,
    prompts: Math.round(total("prompts") * k), cost: cost * k, tokenTotal: total("tokenTotal") * k, start: days[0].start - 7 * 86400000 * Math.round(1 / k),
  });
  const fill = (from: number, until: number, top: number): [number, number][] =>
    Array.from({ length: 13 }, (_, k) => [from + ((Math.min(now, until) - from) * k) / 12, Math.round((top * k) / 12)] as [number, number]);
  return {
    ok: true,
    generatedAt: now,
    back,
    backMax: 4,
    account,
    accounts: [
      { id: "0123456789ab", name: "personal", plan: "Max", hosts: [""] },
      { id: "ba9876543210", name: "work", plan: "Team", hosts: ["", "build-server"] },
    ],
    from: days[0].day,
    to: days[6].day,
    days,
    sum: {
      youMs: total("youMs"), workedMs: total("workedMs"), busyMs: total("busyMs"), waitMs: total("waitMs"),
      prompts: total("prompts"), cost, tokenTotal: total("tokenTotal"), turns: 212, limits: 2, chats: 23, peakAtOnce: 2, busiestDay: days[3].day,
      longestTurn: { workedMs: 48 * MIN, startedAt: days[3].start + 10 * HOUR, name: "Port the date parser", host: "" },
      tokens: { input: 41_200, output: 2_310_000, cacheRead: 612_000_000, cacheWrite5m: 2_100_000, cacheWrite1h: 9_800_000, webSearches: 3 },
    },
    previous: { youMs: total("youMs") * 0.8, workedMs: total("workedMs") * 0.7, busyMs: 0, waitMs: 0, prompts: total("prompts") - 18, cost: cost * 0.75,
      tokenTotal: total("tokenTotal") * 0.75 },
    projects: [
      { name: "webapp", path: "~/projects/webapp", host: "", workedMs: total("workedMs") * 0.55, cost: cost * 0.55, prompts: 92, chats: [DEMO_CHATS[1]], chatCount: 11 },
      { name: "date-parser", path: "~/projects/date-parser", host: "", workedMs: total("workedMs") * 0.25, cost: cost * 0.27, prompts: 41, chats: [DEMO_CHATS[0]], chatCount: 6 },
      { name: "pipeline", path: "/srv/pipeline", host: "build-server", workedMs: total("workedMs") * 0.15, cost: cost * 0.14, prompts: 17, chats: [DEMO_CHATS[2]], chatCount: 4 },
      { name: "~", path: "~", host: "", workedMs: total("workedMs") * 0.05, cost: cost * 0.04, prompts: 9, chats: [], chatCount: 2 },
    ],
    chats: DEMO_CHATS,
    models: [
      { model: "Opus 5.5", cost: cost * 0.93, tokens: 590_000_000, requests: 2900, share: 0.93 },
      { model: "Sonnet 5.5", cost: cost * 0.07, tokens: 35_000_000, requests: 410, share: 0.07 },
    ],
    cacheSaved: 2290,
    trend: back >= 3 ? [null, null, week(0.5), week(0.75), week(1)] : [week(0.4), week(0.55), week(0.6), week(0.75), week(1)],
    spend: {
      cold: { count: 5, cost: 11.4, chats: [{ ...DEMO_CHATS[1], resumes: 3, cost: 7.1 }] },
    },
    work: {
      toolCalls: 3184, tools: [["Bash", 1410], ["Read", 902], ["Edit", 611], ["Write", 88], ["Agent", 21], ["WebFetch", 9]],
      commands: 1410, edits: 699, files: 143, linesAdded: 9412, linesRemoved: 2210, subagents: 21, compactions: 3, webSearches: 6, webFetches: 9,
    },
    plan: back ? [] : [
      { account: "0123456789ab", name: "personal", windows: [
        { key: "seven_day", label: "7d", resetsAt: now + 2.5 * 86400000, pct: 58, points: fill(now - 4.5 * 86400000, now + 2.5 * 86400000, 58) },
      ] },
      { account: "ba9876543210", name: "work", windows: [
        { key: "five_hour", label: "5h", resetsAt: now + 2 * HOUR, pct: 91, points: fill(now - 3 * HOUR, now + 2 * HOUR, 91) },
      ] },
    ],
    prompts: {
      answered: 148, refused: 2, waitMs: 3.3 * HOUR, byTool: [["Bash", 81], ["Edit", 39], ["Read", 24], ["WebFetch", 4]],
      rules: [
        { kind: "dir", value: "/home/alice/projects/shared-ui", project: "/home/alice/projects/webapp", count: 24, waitMs: 2.1 * HOUR,
          example: "~/projects/shared-ui/src/button.tsx", id: "a1b2c3d4e5f6", state: "new", title: "Let chats in webapp read ~/projects/shared-ui",
          change: "adds ~/projects/shared-ui to permissions.additionalDirectories in ~/projects/webapp/.claude/settings.local.json" },
        { kind: "allow", value: "Bash(git status *)", project: "/home/alice/projects/date-parser", count: 11, waitMs: 14 * MIN,
          example: "git status --short", id: "0f1e2d3c4b5a", state: "added", title: "Allow “git status” in date-parser",
          change: "adds Bash(git status *) to permissions.allow in ~/projects/date-parser/.claude/settings.local.json" },
      ],
    },
    tips: [
      { key: "long_context", pct: 41, title: "Start fresh when you switch tasks", detail: "812 requests carried over 150k tokens of context", command: "/clear" },
      { key: "max_effort", pct: 22, title: "Save max effort for hard tasks", detail: "22% of your usage ran at max effort", command: "/effort xhigh" },
      { key: "cache_miss", pct: 12, title: "Compact before you step away", detail: "37 requests sent over 100k tokens the cache had let go", command: "/compact" },
      { key: "waits", pct: null, title: "Let Claude go on without asking", detail: "it waited 3h 18m for your answers, 9 times · auto mode, or allow what you always allow", command: "/permissions" },
    ],
    prices: { asOf: "2026-10-24", guessed: [] },
    sources: [{ host: "", ok: true, error: "" }, { host: "build-server", ok: true, error: "" }],
  };
}

// The Permissions tab of made-up settings: the week's prompts, and a rule in
// the user settings, two in folders' local settings, one shared through git
export function demoPerms(now: number): PermsData {
  const week = demoWeek(now);
  return {
    ok: true, generatedAt: now, from: week.from, to: week.to, prompts: week.prompts,
    granted: [
      { id: "1a2b3c4d5e6f", kind: "allow", value: "Bash(npm test *)", title: "Run “npm test *”", place: "every chat of personal, work",
        where: "~/.claude-shared/settings.json", shared: false, added: false,
        change: "takes Bash(npm test *) out of permissions.allow in ~/.claude-shared/settings.json" },
      { id: "0f1e2d3c4b5a", kind: "allow", value: "Bash(git status *)", title: "Run “git status *”", place: "chats started in date-parser",
        where: "~/projects/date-parser/.claude/settings.local.json", shared: false, added: true,
        change: "takes Bash(git status *) out of permissions.allow in ~/projects/date-parser/.claude/settings.local.json" },
      { id: "6f5e4d3c2b1a", kind: "mode", value: "acceptEdits", title: "Accept file edits without asking", place: "chats started in webapp",
        where: "~/projects/webapp/.claude/settings.local.json", shared: false, added: false,
        change: "takes permissions.defaultMode (acceptEdits) out of ~/projects/webapp/.claude/settings.local.json" },
      { id: "a9b8c7d6e5f4", kind: "allow", value: "WebSearch", title: "WebSearch", place: "chats started in webapp (shared through git)",
        where: "~/projects/webapp/.claude/settings.json", shared: true, added: false,
        change: "takes WebSearch out of permissions.allow in ~/projects/webapp/.claude/settings.json" },
      { id: "7a6b5c4d3e2f", kind: "trust", value: "/home/alice/projects/webapp", folder: "/home/alice/projects/webapp",
        title: "Trusted folder: ~/projects/webapp", place: "for personal", where: "~/.claude-personal/.claude.json", shared: false,
        added: false, change: "marks ~/projects/webapp untrusted in ~/.claude-personal/.claude.json: Claude asks again before it works there" },
    ],
    hosts: [
      { host: "build-server", ok: true, error: "", prompts: { answered: 0, refused: 0, waitMs: 0, byTool: [], rules: [] },
        granted: [{ id: "1b2c3d4e5f6a", kind: "flag", value: "skipDangerousModePermissionPrompt", folder: "",
          title: "Bypass permissions mode starts without its warning", place: "every chat of team", where: "~/.claude/settings.json",
          shared: false, added: false, change: "sets skipDangerousModePermissionPrompt to false in ~/.claude/settings.json" }] },
    ],
  };
}


// The Projects tab: the demo's chats by project
export function demoProjects(now: number): ProjectsData {
  const h = 3_600_000;
  const home = "/home/alice";
  const chat = (id: string, name: string, cwd: string, ago: number) =>
    ({ key: `.claude/${id}/project`, sessionId: id, name, cwd, cwdShort: cwd.replace(home, "~"), lastActive: now - ago, profile: "personal",
       profileDir: ".claude", account: "personal", shared: false, starred: false });
  const local = personal(now, 0);
  const plans = (local.plans ?? []).map((p) => ({ ...p, account: "personal" }));
  const memories = (local.memories ?? []).map((m) => ({ ...m, account: "personal" }));
  const project = (name: string, path: string, ago: number, chats: ReturnType<typeof chat>[], recap: string | null) => ({
    name, path, short: path.replace(home, "~"), gone: false, lastAt: now - ago, accounts: ["personal"], chatCount: chats.length, chats,
    plans: plans.filter((p) => p.cwd === path), memories: memories.filter((m) => m.folder === path), recap: recap ? { text: recap, at: now - ago } : null,
  });
  return {
    ok: true, generatedAt: now,
    projects: [
      project("webapp", `${home}/projects/webapp`, 0.2 * h, [
        chat("demo-1", "Fix the date parser", `${home}/projects/webapp`, 0.2 * h),
        chat("demo-r1", "Explain the build pipeline", `${home}/projects/webapp/build`, 5 * h),
        chat("demo-6", "Nightly dependency check", `${home}/projects/webapp`, 30 * h),
      ], "Fixed the date parser for ISO weeks; the tests pass. Next: the release notes."),
      project("api-server", `${home}/projects/api-server`, 0.5 * h, [
        chat("demo-2", "Release notes for 2.0", `${home}/projects/api-server`, 0.5 * h),
        chat("demo-r2", "Rename the config module", `${home}/projects/api-server/config`, 26 * h),
      ], null),
      project("notes", `${home}/notes`, 50 * h, [chat("demo-9", "Sort the meeting notes", `${home}/notes`, 50 * h)], null),
      { ...project("", "", 72 * h, [], null), name: "", short: "", plans: plans.filter((p) => !p.cwd) },
    ],
  };
}

// The Recap's How your limits changed in the demo: six weeks of each account,
// the Max one's 5-hour window a little smaller in the newest week, the Team
// one with a weekly limit from its fourth week
export function demoLimits(now: number, account = ""): LimitHistory {
  const day = 86400000;
  const reset = now + 2 * day;
  // (changed: the week its limits changed in, from the plan before, which had a fifth of them)
  const make = (id: string, name: string, plan: string, five: number[], week: (number | null)[], opus: boolean,
    changed = -1, before = ""): LimitAccount => {
    const periods: (LimitPeriod & { era: number })[] = five.map((size, i) => {
      const from = reset - (five.length - i) * 7 * day;
      const old = i < changed;
      const cost = old ? size / 5 : size;
      const w = week[i] && old ? week[i]! / 5 : week[i];
      return {
        from, until: from + 7 * day, plan: old ? before : plan, era: old ? 0 : changed >= 0 ? 1 : 0,
        fiveHour: { cost, n: 4 + (i % 3), lo: cost * 0.92, hi: cost * 1.07 },
        weeks: w ? { seven_day: { cost: w, pct: i === five.length - 1 ? 46 : 88 }, ...(opus ? { seven_day_opus: { cost: w * 0.8, pct: 51 } } : {}) } : {},
        share: w ? { pct: (cost / w) * 100, how: "sizes", measured: null } : null,
        fill: { wallMs: (2.2 + (i % 2) * 0.4) * 3600000, workMs: (3.5 + (i % 3) * 0.3) * 3600000 },
        tokens: { fresh: cost * 52000, output: cost * 10500, cacheRead: cost * 2.6e6 },
      };
    });
    const windows = periods.flatMap((p, i) => [0.5, 1.6, 2.7, 3.9, 5.2].slice(0, 3 + (i % 3)).map((d, k) => {
      const start = p.from + d * day;
      const full = (p.fiveHour?.cost ?? 0) * [0.94, 1.05, 1, 0.97, 1.03][k];
      return { start, at: start + 2 * 3600000, pct: 60 + k * 9, full, plan: p.plan, era: p.era };
    })).filter((w) => w.at < now);
    const last = periods[periods.length - 1];
    const prev = periods[periods.length - 2];
    const pct = Math.round((last.fiveHour!.cost / prev.fiveHour!.cost - 1) * 100);
    return {
      id, name, plan, periods, windows,
      events: changed >= 0 ? [{ at: periods[changed].from + 9 * 3600000, factors: { five_hour: 5.1, seven_day: 4.9 }, from: before, to: plan }] : [],
      changes: {
        fiveHour: { kind: Math.abs(pct) >= 10 ? "change" : "same", pct, against: prev.from },
        share: { kind: "same", pct: -2, against: prev.from },
        seven_day: week.filter(Boolean).length > 1 ? { kind: "same", pct: -3, against: prev.from } : { kind: "new", against: prev.from },
        ...(opus ? { seven_day_opus: { kind: "same", pct: 1, against: prev.from } } : {}),
      },
      now: { fiveHour: last.fiveHour, share: last.share, fill: last.fill, tokens: last.tokens,
        weeks: { seven_day: last.weeks.seven_day ?? null, ...(opus ? { seven_day_opus: last.weeks.seven_day_opus ?? null } : {}) } },
      equivalents: { model: "Opus 5.5", fiveHour: { output: (last.fiveHour!.cost / 20) * 1e6, input: (last.fiveHour!.cost / 4) * 1e6, cacheRead: (last.fiveHour!.cost / 0.2) * 1e6 },
        week: last.weeks.seven_day ? { output: (last.weeks.seven_day.cost / 20) * 1e6, input: (last.weeks.seven_day.cost / 4) * 1e6, cacheRead: (last.weeks.seven_day.cost / 0.2) * 1e6 } : null },
    };
  };
  const accounts = [
    make("0123456789ab", "personal", "Max 5×", [176, 181, 178, 183, 179, 158], [1250, 1240, 1262, 1255, 1248, 1236], true, 2, "Pro"),
    make("ba9876543210", "work", "Team · standard seat", [51, 50, 52, 49, 50, 49], [null, null, null, 297, 291, 288], false),
  ];
  return { ok: true, generatedAt: now, since: reset - 6 * 7 * day, accounts: accounts.filter((a) => !account || a.id === account) };
}
