// The pets on their own, fed with the made-up demo data (src/shared/demo.ts):
// the hero, one stage per account, a list with each chat's pet color, and
// buttons that fire pet events. See dev/pets.html for how to run it.
//
// Query: ?theme=light|dark, ?mood=done (the hero's mood), ?pets=N (pets
// per account), ?phase=N (the demo's story), ?still (no scheduled events),
// ?cookie=X,Y (a double-click there on the hero's stage after a second: a
// cookie).

import "../webview/styles.css";
import { pets } from "../webview/pets";
import type { AccountInput, HeroInput, PetStage, StageChat } from "../webview/pets/api";
import { demoState } from "../src/shared/demo";
import {
  agentsRunning,
  allGroups,
  countStates,
  firstWaiting,
  headlineText,
  heroMood,
  highUsageText,
  maxFiveHour,
  overallState,
  petKeyOf,
  stateText,
} from "../src/shared/model";
import type { ChatRef, Group, Session, ViewState } from "../src/shared/types";

const query = new URLSearchParams(location.search);
const forcedMood = query.get("mood") ?? "";
let maxPets = query.has("pets") ? Number(query.get("pets")) : 5;
let phase = Number(query.get("phase") ?? 0);
let live = true;

const app = document.getElementById("app")!;
const callbacks = { open: (chat: ChatRef) => console.log("open", chat) };

function ref(s: Session, host?: string): ChatRef {
  return { host, key: s.key, sessionId: s.sessionId, chatId: s.chatId, profileDir: s.profileDir, name: s.name };
}

const order = { waiting: 0, working: 1, idle: 2, done: 3 };

function chatsOf(g: Group): StageChat[] {
  return g.sessions
    .map((s, i) => ({ s, i }))
    .sort((a, b) => order[a.s.state] - order[b.s.state] || a.i - b.i)
    .map(({ s, i }) => ({ key: petKeyOf(s, g.host), session: s, host: g.host, order: i }));
}

function heroInput(state: ViewState, groups: Group[]): HeroInput {
  const counts = countStates(groups);
  const waiting = firstWaiting(groups);
  let contextFullText = "";
  for (const g of groups)
    for (const s of g.sessions)
      if (!contextFullText && s.state === "working" && s.context !== null && s.context >= 85 && !pets.petColor(petKeyOf(s, g.host)))
        contextFullText = `${s.name}: context ${Math.round(s.context)}% full`;
  return {
    mood: forcedMood || heroMood(state, overallState(groups, counts), groups),
    headline: headlineText(state, counts),
    counts,
    highUsageText: highUsageText(groups),
    contextFullText,
    maxFiveHour: maxFiveHour(groups),
    agentsRunning: agentsRunning(groups),
    waiting: waiting ? ref(waiting.session, waiting.group.host) : null,
  };
}

function box(className: string, parent: HTMLElement = app): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  parent.append(el);
  return el;
}

const hero = pets.createHeroStage(box("dev-hero"), callbacks);
const cookieAt = query.get("cookie");
if (cookieAt) {
  setTimeout(() => {
    const [x, y] = cookieAt.split(",").map(Number);
    const stage = document.querySelector(".td-stage--hero")!;
    const r = stage.getBoundingClientRect();
    stage.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: r.left + x, clientY: r.top + y }));
  }, 1000);
}
const accounts = new Map<string, { stage: PetStage; title: HTMLDivElement }>();
const list = box("dev-list");

function render(): void {
  const state = demoState(Date.now(), phase);
  const groups = allGroups(state.status, state.hosts);
  for (const g of groups) {
    const key = (g.host ? g.host + "|" : "") + g.id;
    let account = accounts.get(key);
    if (!account) {
      const title = box("dev-title", app);
      account = { title, stage: pets.createAccountStage(box("dev-account"), key, callbacks) };
      accounts.set(key, account);
    }
    account.title.textContent = (g.host ? g.host + ": " : "") + g.title;
    const input: AccountInput = { chats: chatsOf(g), maxPets, fiveHour: g.limits?.windows[0]?.pct ?? 0 };
    account.stage.update(input);
    account.stage.setLive(live);
  }
  hero.update(heroInput(state, groups));
  hero.setLive(live);
  app.append(list);
  list.replaceChildren();
  const title = box("dev-title", list);
  title.textContent = `Chats (demo phase ${phase})`;
  for (const g of groups)
    for (const s of g.sessions) {
      const row = box("dev-row", list);
      box("dev-bar", row).style.background = pets.petColor(petKeyOf(s, g.host)) || "transparent";
      row.append(s.name + " ");
      const small = document.createElement("small");
      small.textContent = stateText(s, Date.now());
      row.append(small);
    }
  app.append(buttons);
}

pets.onColorsChanged(render);

// Buttons: events for the hero (key "") and for a chat's pet
const buttons = box("dev-buttons");
function button(label: string, fn: () => void): void {
  const b = document.createElement("button");
  b.textContent = label;
  b.addEventListener("click", fn);
  buttons.append(b);
}
const parser = "demo-1",
  notes = "demo-2",
  ranking = "ssh:build-server|demo-4";
button("hero: done", () => pets.dispatchPetEvent("done", "Something is done!", ""));
button("hero: failed", () => pets.dispatchPetEvent("failed", "Something failed…", ""));
button("hero: reset", () => pets.dispatchPetEvent("reset", "5h limit reset!", ""));
button("hero: oops", () => pets.dispatchPetEvent("oops", "Couldn't open that chat.", ""));
button("parser: done", () => pets.dispatchPetEvent("done", "Fix the date parser is done!", parser));
button("notes: waiting", () => pets.dispatchPetEvent("waiting", "Release notes for 2.0 needs you!", notes));
button("ranking: failed", () => pets.dispatchPetEvent("failed", "Train the ranking model failed…", ranking));
button("ranking: stopped", () => pets.dispatchPetEvent("stopped", "Train the ranking model was stopped.", ranking));
button("next phase", () => {
  phase += 1;
  render();
});
button("pets −", () => {
  maxPets = Math.max(0, maxPets - 1);
  render();
});
button("pets +", () => {
  maxPets += 1;
  render();
});
button("toggle live", () => {
  live = !live;
  render();
});
button("theme", () => {
  const dark = document.body.classList.contains("vscode-dark");
  document.body.className = dark ? "vscode-light" : "vscode-dark";
  pets.setDark(!dark);
});

pets.setDark(document.body.classList.contains("vscode-dark"));
render();

// A little story: a chat calls, one finishes, a limit resets…
if (!query.has("still")) {
  const story: [number, () => void][] = [
    [2500, () => pets.dispatchPetEvent("waiting", "Release notes for 2.0 needs you!", notes)],
    [7000, () => {
      phase += 1;
      render();
      pets.dispatchPetEvent("done", "Train the ranking model is done!", ranking);
    }],
    [12000, () => pets.dispatchPetEvent("reset", "5h limit reset!", "")],
    [17000, () => {
      phase += 1;
      render();
      pets.dispatchPetEvent("done", "Fix the date parser is done!", parser);
    }],
  ];
  const run = (): void => {
    for (const [at, fn] of story) setTimeout(fn, at);
  };
  run();
  setInterval(run, 20000);
}
