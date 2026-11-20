// Another program's request that a chat be brought up (jump.py --job: Talpy Den Display's tap). The widget takes
// one at once; a VS Code window only when none did, and only for a chat it lists. Only a fresh request naming a
// jobs file id, a file of its own in a private folder, is taken, once; nothing in it is ever run.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import "./useHost";
import { findJobRef, jobIdOk, JOB_ID, openDir, OpenWatch, pendingOpens, takeOpen } from "../src/openRequests";
import { demoState } from "../../core/src/shared/demo";

const JOB = ".claude-work/0b1c2d3e-aaaa-bbbb-cccc-1234567890ab/live";

function tempRun(): { run: string; env: NodeJS.ProcessEnv; done: () => void } {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-open-"));
  const run = path.join(base, "run");
  fs.mkdirSync(run, { mode: 0o700 });
  return { run, env: { XDG_RUNTIME_DIR: run }, done: () => fs.rmSync(base, { recursive: true, force: true }) };
}

function put(folder: string, data: unknown, raw?: string): string {
  const name = `req-${crypto.randomBytes(8).toString("hex")}.json`;
  const tmp = path.join(folder, "tmp-test.json");
  fs.writeFileSync(tmp, raw ?? JSON.stringify(data), { mode: 0o600 });
  fs.renameSync(tmp, path.join(folder, name));
  return name;
}

test("a jobs file id's shape, and nothing else", () => {
  for (const ok of [JOB, "lab:.claude/0b1c/job", "podman:web:.claude/a/live", "docker:api@lab:.claude-x/a/chat/shared"])
    assert.equal(jobIdOk(ok), true, ok);
  for (const bad of [5, "", "a;b/c/live", ".claude-work/$(id)/live", ".claude-work/`id`/live", ".claude-work/a b/live",
                     '.claude-work/"x/live', ".claude-work/x'/live", ".claude-work/x\n/live", "../x/y/live", "-x/y/live",
                     "x".repeat(301), ".claude-work/*/live", ".claude-work/?/live", ".claude-work/[ab]/live",
                     ".claude-work/a{b,c}/live", ".claude-work/~x/live", "lab*:.claude/a/live", "only/two",
                     ".claude-work/a/recent", ".claude-work/Grüße/live"])
    assert.equal(jobIdOk(bad), false, String(bad).slice(0, 40));
});

test("the id rule is the backend's (live.py's JOB_ID)", () => {
  const py = fs.readFileSync(path.join(__dirname, "../../../package/contents/code/live.py"), "utf8");
  const m = /^JOB_ID = re\.compile\(r"(.*)"\)$/m.exec(py);
  assert.ok(m, "live.py's JOB_ID");
  assert.equal(JOB_ID.source.replace(/^\^/, "").replace(/\$$/, "").replace(/\\\//g, "/"), m![1]);
});

test("the requests' folder is in the runtime folder and yours alone, or there are none", () => {
  const t = tempRun();
  try {
    const folder = openDir(t.env)!;
    assert.equal(folder, path.join(t.run, "talpy-den/opens"));
    assert.equal(fs.statSync(folder).mode & 0o777, 0o700);
    fs.chmodSync(folder, 0o777);
    assert.equal(openDir(t.env), null);
    fs.chmodSync(folder, 0o700);
    fs.chmodSync(path.dirname(folder), 0o755);
    assert.equal(openDir(t.env), null);
    assert.equal(openDir({}), null);
    assert.equal(openDir({ XDG_RUNTIME_DIR: "relative" }), null);
  } finally {
    t.done();
  }
});

test("a fresh request is offered as it is, taken once; anything else is dropped", () => {
  const t = tempRun();
  try {
    const folder = openDir(t.env)!;
    const now = Date.now();
    const name = put(folder, { id: JOB, at: now });
    assert.deepEqual(pendingOpens(folder, now).map((r) => [r.name, r.id]), [[name, JOB]]);
    assert.equal(fs.existsSync(path.join(folder, name)), true, "offered, not taken");
    assert.deepEqual(takeOpen(folder, name, now), { taken: true, id: JOB });
    assert.deepEqual(takeOpen(folder, name, now), { taken: false, id: null }, "once");
    assert.deepEqual(fs.readdirSync(folder), []);
    for (const bad of [{ id: JOB, at: now - 11000 }, { id: JOB }, { id: 5, at: now },
                       { id: ".claude-work/*/live", at: now }, { id: JOB, at: true }, { id: JOB, at: now + 0.5 }, [JOB]]) {
      put(folder, bad);
      assert.deepEqual(pendingOpens(folder, now), [], JSON.stringify(bad));
      assert.deepEqual(fs.readdirSync(folder), []);
    }
    for (const raw of ["not json", JSON.stringify({ id: JOB, at: now, pad: "x".repeat(2000) })]) {
      put(folder, null, raw);
      assert.deepEqual(pendingOpens(folder, now), []);
      assert.deepEqual(fs.readdirSync(folder), []);
    }
    for (const name of ["../x.json", "request.json", "req-zz.json"]) assert.deepEqual(takeOpen(folder, name, now), { taken: false, id: null });
  } finally {
    t.done();
  }
});

test("a request that's a link is dropped, its target untouched; leftovers are swept", () => {
  const t = tempRun();
  try {
    const folder = openDir(t.env)!;
    const target = path.join(t.run, "elsewhere.json");
    fs.writeFileSync(target, JSON.stringify({ id: JOB, at: Date.now() }));
    fs.symlinkSync(target, path.join(folder, `req-${"a".repeat(16)}.json`));
    assert.deepEqual(pendingOpens(folder, Date.now()), []);
    assert.equal(fs.existsSync(target), true);
    fs.writeFileSync(path.join(folder, "tmp-1-aa.json"), "{}");
    const old = (Date.now() - 120000) / 1000;
    fs.utimesSync(path.join(folder, "tmp-1-aa.json"), old, old);
    fs.writeFileSync(path.join(folder, "taken-2-bb.json"), "{}");
    openDir(t.env);
    assert.deepEqual(fs.readdirSync(folder), ["taken-2-bb.json"]);
  } finally {
    t.done();
  }
});

test("the chat of a jobs file id is a listed session row, here or on a shown host", () => {
  const state = demoState(1_800_000_000_000);
  const local = state.status!.groups[0].sessions[0];
  const host = state.hosts[0];
  const there = host.result!.groups[0].sessions[0];
  local.key = ".claude-work/0b1c2d3e-aaaa-bbbb-cccc-1234567890ab/live"; // (as the backend makes them: the demo's are made up)
  there.key = ".claude/1c2d3e4f-aaaa-bbbb-cccc-1234567890ab/job";
  assert.equal(findJobRef(state.status, state.hosts, local.key)?.sessionId, local.sessionId);
  const ref = findJobRef(state.status, state.hosts, `${host.name}:${there.key}`);
  assert.equal(ref?.host, host.name);
  assert.equal(ref?.sessionId, there.sessionId);
  assert.equal(findJobRef(state.status, state.hosts, `elsewhere:${there.key}`), null, "a host it doesn't show");
  assert.equal(findJobRef(state.status, state.hosts, ".claude/made-up/live"), null);
  assert.equal(findJobRef(state.status, state.hosts, "a;b/c/live"), null);
});

test("a window takes a request only after the widget's turn, only the leading one, only for a chat it lists", async () => {
  const t = tempRun();
  const opened: string[] = [];
  let leads = false;
  let lists = false;
  const watch = new OpenWatch(() => lists, (id) => opened.push(id), () => leads, t.env, 150);
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  try {
    watch.start();
    const folder = openDir(t.env)!;
    const name = put(folder, { id: JOB, at: Date.now() });
    await wait(60);
    assert.deepEqual(opened, [], "the widget's turn first");
    await wait(300);
    assert.deepEqual(opened, [], "not the leading window: left for it");
    leads = true;
    fs.utimesSync(path.join(folder, name), new Date(), new Date()); // (a change: it looks again)
    await wait(400);
    assert.deepEqual(opened, [], "not a chat it lists: left for jump.py");
    assert.equal(fs.existsSync(path.join(folder, name)), true);
    lists = true;
    fs.utimesSync(path.join(folder, name), new Date(), new Date());
    await wait(400);
    assert.deepEqual(opened, [JOB]);
    assert.equal(fs.existsSync(path.join(folder, name)), false);
  } finally {
    watch.dispose();
    t.done();
  }
});

test("the folder holds while requests come and go (a take's and a write's files)", async () => {
  const t = tempRun();
  try {
    const folder = openDir(t.env)!;
    // (another process takes and writes meanwhile: its files there for a moment)
    const churn = spawn(process.execPath, ["-e", `const fs = require("fs"), p = require("path"); const end = Date.now() + 1500;
      let i = 0; while (Date.now() < end) { for (const pre of ["taken-", "tmp-"]) { const f = p.join(${JSON.stringify(folder)}, pre + i + "-x.json");
      fs.writeFileSync(f, "{}"); fs.unlinkSync(f); } i++; }`]);
    await new Promise((r) => setTimeout(r, 100));
    let misses = 0;
    for (let i = 0; i < 3000; i++) if (openDir(t.env) === null) misses++;
    await new Promise((r) => churn.on("exit", r));
    assert.equal(misses, 0);
  } finally {
    t.done();
  }
});

test("a request ahead of the clock is left for its writer, not dropped", () => {
  const t = tempRun();
  try {
    const folder = openDir(t.env)!;
    const name = put(folder, { id: JOB, at: Date.now() + 5000 });
    assert.deepEqual(pendingOpens(folder, Date.now()), []);
    assert.equal(fs.existsSync(path.join(folder, name)), true);
  } finally {
    t.done();
  }
});

test("the watcher comes back when its folder is removed and made again", async () => {
  const t = tempRun();
  const opened: string[] = [];
  const watch = new OpenWatch(() => true, (id) => opened.push(id), () => true, t.env, 100, 150);
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  try {
    watch.start();
    const folder = openDir(t.env)!;
    fs.rmSync(folder, { recursive: true });
    await wait(400); // (a rescan or two: gone)
    const again = openDir(t.env)!;
    put(again, { id: JOB, at: Date.now() });
    await wait(700);
    assert.deepEqual(opened, [JOB]);
  } finally {
    watch.dispose();
    t.done();
  }
});
