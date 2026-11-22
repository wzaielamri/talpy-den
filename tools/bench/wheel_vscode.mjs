// tools/bench/wheel_vscode.py's driver: VS Code's chat tab (the harness, vscode/dev/chat.html) in a
// headless Chromium, given a made-up conversation, scrolled by the same inputs as bench.py wheel, driven
// over the devtools protocol; every frame's scrollTop (requestAnimationFrame) is printed as a
// "motion {json}" line, and what a frame costs as "pace {json}".
//   node wheel_vscode.mjs REPO DATA.json CHROME
//
// - a wheel notch: a mouse wheel's event (emulateTouchFromMouseEvent's wheel: not precise, so Chromium
//   animates it, as it does a notch), 100 px; quick spins of several;
// - a touchpad's stream at 60, 90 and 125 events a second: precise pixel deltas (dispatchMouseEvent's
//   wheel), applied as they come, at the pace of bench.py's (1200 px a second, a slow one 300);
// - the scroll bar dragged: its thumb pressed, moved 1 px at a time at 125 a second, released;
// - 12 px a frame for 240 frames, the pointer away and over the list: rAF's intervals and the page's work.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";

const [repo, dataPath, chrome] = process.argv.slice(2);
const data = fs.readFileSync(dataPath);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
  ".png": "image/png", ".woff2": "font/woff2", ".ttf": "font/ttf", ".map": "application/json" };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  if (u.pathname === "/data.json") { res.writeHead(200, { "content-type": "application/json" }); res.end(data); return; }
  const f = path.join(repo, decodeURIComponent(u.pathname));
  if (!f.startsWith(repo) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-wheel-chrome-"));
const proc = spawn(chrome, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run",
  "--no-default-browser-check", "--window-size=760,900", "--enable-smooth-scrolling", "--hide-scrollbars=false", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws = null;
try {
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = "";
    proc.stderr.on("data", (d) => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) resolve(m[1]); });
    setTimeout(() => reject(new Error("no devtools url: " + buf.slice(0, 500))), 20000);
  });
  const list = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json/list`)).json();
  ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const waiting = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && waiting.has(m.id)) { const w = waiting.get(m.id); waiting.delete(m.id); m.error ? w.reject(new Error(JSON.stringify(m.error))) : w.resolve(m.result); }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => { const i = ++id; waiting.set(i, { resolve, reject }); ws.send(JSON.stringify({ id: i, method, params })); });
  const fire = (method, params = {}) => { const i = ++id; waiting.set(i, { resolve() {}, reject() {} }); ws.send(JSON.stringify({ id: i, method, params })); };
  const evaluate = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 800));
    return r.result.value;
  };
  const log = (what, v) => console.log(what, JSON.stringify(v));

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Performance.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 760, height: 900, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: `http://127.0.0.1:${port}/vscode/dev/chat.html?theme=dark&width=700&agents=0&tasks=0` });
  await sleep(2500);
  await evaluate(`fetch("/data.json").then(r => r.json()).then(a => { window.postMessage({ type: "conversation", answer: { ...a, stamp: "wheel" + Math.random() } }, "*"); return true; })`);
  await sleep(3000);
  const box = await evaluate(`(() => { const r = document.querySelector(".pane-list").getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; })()`);
  const cx = Math.round(box.x + box.width / 2), cy = Math.round(box.y + box.height / 2);
  const place = () => evaluate(`(() => { const el = document.querySelector(".pane-list"); el.scrollTop = el.scrollHeight - el.clientHeight - 6000; return el.scrollTop; })()`);
  // (every frame's scrollTop; and how often the message under the pointer changed meanwhile: mouseover)
  const record = () => evaluate(`(() => { window.__ys = []; window.__ts = []; window.__on = true; window.__over = 0; const el = document.querySelector(".pane-list");
    if (!window.__hooked) { window.__hooked = true; el.addEventListener("mouseover", () => { if (window.__on) window.__over++; }); }
    const f = (t) => { window.__ys.push(el.scrollTop); window.__ts.push(t); if (window.__on) requestAnimationFrame(f); }; requestAnimationFrame(f); return true; })()`);
  const stop = () => evaluate(`(() => { window.__on = false; return { ys: window.__ys, hoverChanges: window.__over, ts: window.__ts.map((t) => Math.round((t - window.__ts[0]) * 10) / 10) }; })()`);
  // events [[ms, fn]] at their times from now (sent without waiting for Chromium's answer: they come as they're due)
  const play = async (events) => {
    const t0 = performance.now();
    for (const [t, fn] of events) {
      const wait = t0 + t - performance.now();
      if (wait > 1) await sleep(wait - 1);
      while (performance.now() < t0 + t) { /* the last ms */ }
      fn();
    }
  };
  const motion = async (label, events, frames) => {
    await place();
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: cx, y: cy });
    await sleep(600);
    await record();
    await sleep(100);
    await play(events);
    await sleep(frames);
    const r = await stop();
    log("motion", { label, ...r });
  };
  const notch = (t) => [t, () => fire("Input.emulateTouchFromMouseEvent", { type: "mouseWheel", x: cx, y: cy, button: "none", deltaX: 0, deltaY: 100 })];
  const pad = (hz, speed, ms) => {
    const out = [];
    for (let t = 0; t <= ms; t += 1000 / hz)
      out.push([t, () => fire("Input.dispatchMouseEvent", { type: "mouseWheel", x: cx, y: cy, deltaX: 0, deltaY: -speed / hz })]);
    return out;
  };
  await motion("one notch", [notch(0)], 900);
  await motion("spin, 6 notches 50 ms apart", [0, 1, 2, 3, 4, 5].map((i) => notch(i * 50)), 1200);
  await motion("spin, 8 notches 25 ms apart", [0, 1, 2, 3, 4, 5, 6, 7].map((i) => notch(i * 25)), 1200);
  for (const hz of [60, 90, 125]) await motion(`touchpad ${hz} Hz`, pad(hz, 1200, 600), 700);
  await motion("touchpad 125 Hz, slow", pad(125, 300, 800), 700);
  {
    await place();
    await sleep(400);
    const bar = await evaluate(`(() => { const el = document.querySelector(".pane-list"); const r = el.getBoundingClientRect();
      const w = el.offsetWidth - el.clientWidth, track = el.clientHeight, thumb = Math.max(20, track * el.clientHeight / el.scrollHeight);
      return { x: r.right - Math.max(w, 6) / 2, y: r.top + el.scrollTop / (el.scrollHeight - el.clientHeight) * (track - thumb) + thumb / 2, w, thumb }; })()`);
    const x = Math.round(bar.x), y = Math.round(bar.y);
    const events = [[0, () => fire("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 })]];
    for (let i = 1; i <= 62; i++)
      events.push([4 + i * 8, () => fire("Input.dispatchMouseEvent", { type: "mouseMoved", x, y: y - i, button: "left", buttons: 1 })]);
    events.push([4 + 63 * 8, () => fire("Input.dispatchMouseEvent", { type: "mouseReleased", x, y: y - 62, button: "left", buttons: 1, clickCount: 1 })]);
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await sleep(300);
    await record();
    await sleep(100);
    await play(events);
    await sleep(600);
    log("motion", { label: "scroll bar dragged", scrollbar: bar, ...(await stop()) });
  }
  // what a frame costs: 12 px a frame for 240 frames, the pointer away, then over the list
  const metric = async () => Object.fromEntries((await send("Performance.getMetrics")).metrics.map((m) => [m.name, m.value]));
  for (const over of [false, true]) {
    await place();
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: over ? cx : cx, y: over ? cy : 2 });
    await sleep(800);
    const m0 = await metric();
    const r = await evaluate(`new Promise((done) => { const el = document.querySelector(".pane-list"); const ts = []; let n = 0;
      const f = (t) => { ts.push(t); if (n++ >= 240) { const d = []; for (let i = 1; i < ts.length; i++) d.push(ts[i] - ts[i - 1]); done(d); return; }
        el.scrollTop -= 12; requestAnimationFrame(f); }; requestAnimationFrame(f); })`);
    const m1 = await metric();
    const per = (k) => Math.round((m1[k] - m0[k]) * 1000 / r.length * 100) / 100;
    const s = r.slice().sort((a, b) => a - b);
    log("pace", { label: over ? "pointer over the list" : "pointer away", frames: r.length, p50: Math.round(s[s.length >> 1] * 10) / 10,
      p95: Math.round(s[Math.floor(s.length * 0.95)] * 10) / 10, max: Math.round(s[s.length - 1] * 10) / 10,
      scriptMsPerFrame: per("ScriptDuration"), layoutMsPerFrame: per("LayoutDuration"), styleMsPerFrame: per("RecalcStyleDuration"),
      taskMsPerFrame: per("TaskDuration") });
  }
} catch (e) {
  console.log("error", String((e && e.stack) || e));
} finally {
  try { ws && ws.close(); } catch { /* */ }
  proc.kill("SIGTERM");
  await sleep(500);
  if (proc.exitCode === null) proc.kill("SIGKILL");
  server.close();
  fs.rmSync(profile, { recursive: true, force: true });
}
