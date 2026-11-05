// UI state kept across reloads of the webview (VS Code drops a hidden view's
// page): which subagent trees (and subagents), peeks, recent-chat lists,
// projects and stats are open. Kept by row and account key, since every poll
// brings new objects.

import { allGroups, type RecentMore } from "../../src/shared/model";
import type { Group, RecentChat, ViewState } from "../../src/shared/types";
import { post, savedState, saveState } from "../env";
import { groupKeyOf, rowKeyOf } from "./chat";
import { createStore } from "./store";

export type Tab = "chats" | "week" | "perms" | "projects";
// (in the order they stand: your chats now, then the rest of your work by
// project, the permissions you gave, and the Recap of your days)
export const TAB_ORDER: readonly Tab[] = ["chats", "projects", "perms", "week"];

interface UiState {
  tab: Tab; // the view's tab: your chats now, your last 7 days, or the permissions you gave
  focus: boolean; // the Chats tab shows only what needs you and what works (FocusView.tsx)
  agents: Record<string, true>;
  agentDetail: Record<string, true>; // by agentDetailKey(): row key + "|" + agent id
  peek: Record<string, true>;
  recent: Record<string, true>;
  starred: Record<string, true>; // an account's starred chats or plans unfolded: its key + "|chats" or "|plans"
  projects: Record<string, true>; // the Projects tab's projects unfolded, by folder
  stats: Record<string, true>;
}

// Our part of the webview's saved state; other parts (the pets) keep theirs
const KEY = "ui";
// Keys of chats long gone would pile up otherwise
const MAX_KEYS = 100;

function load(): UiState {
  const saved = savedState<Record<string, unknown>>()[KEY] as Partial<UiState> | undefined;
  return {
    tab: saved?.tab === "week" || saved?.tab === "perms" || saved?.tab === "projects" ? saved.tab : "chats",
    focus: saved?.focus === true,
    agents: { ...(saved?.agents ?? {}) },
    agentDetail: { ...(saved?.agentDetail ?? {}) },
    peek: { ...(saved?.peek ?? {}) },
    recent: { ...(saved?.recent ?? {}) },
    starred: { ...(saved?.starred ?? {}) },
    projects: { ...(saved?.projects ?? {}) },
    stats: { ...(saved?.stats ?? {}) },
  };
}

export const uiState = createStore<UiState>(load());

function toggled(map: Record<string, true>, key: string): Record<string, true> {
  const next = { ...map };
  if (next[key]) delete next[key];
  else next[key] = true;
  const keys = Object.keys(next);
  for (const old of keys.slice(0, Math.max(0, keys.length - MAX_KEYS))) delete next[old];
  return next;
}

function persist(next: UiState): void {
  uiState.set(next);
  saveState({ ...savedState<Record<string, unknown>>(), [KEY]: next });
}

export function setTab(tab: Tab): void {
  const s = uiState.get();
  if (s.tab !== tab) persist({ ...s, tab });
}

export function setFocus(focus: boolean): void {
  const s = uiState.get();
  if (s.focus !== focus) persist({ ...s, focus });
}

export function toggleAgents(rowKey: string): void {
  const s = uiState.get();
  persist({ ...s, agents: toggled(s.agents, rowKey) });
}

export function toggleAgentDetail(key: string): void {
  const s = uiState.get();
  persist({ ...s, agentDetail: toggled(s.agentDetail, key) });
}

// A chat Claude moved to the background under a new id (its row's movedFrom)
// keeps its subagents, theirs and its peek open, as it keeps its pet
// (pets/stage.ts sync): what was open under the id it had goes over to the new
// one, as each state comes. Only for a moved row with something open under
// its old key, unless the old id is still listed (both run).
export function followMovedRows(state: ViewState): void {
  let s = uiState.get();
  let changed = false;
  for (const g of allGroups(state.status, state.hosts)) {
    for (const r of g.sessions) {
      const old = r.movedFrom?.id;
      if (!old) continue;
      const from = rowKeyOf({ ...r, chatId: old }, g.host), to = rowKeyOf(r, g.host);
      const runs = Object.keys(s.agentDetail).filter((k) => k.startsWith(from + "|"));
      if (from === to || !(s.agents[from] || s.peek[from] || runs.length)) continue;
      if (g.sessions.some((o) => (o.chatId || o.sessionId) === old)) continue;
      const moved = (map: Record<string, true>, keys: string[]): Record<string, true> => {
        const next = { ...map };
        for (const k of keys) {
          next[to + k.slice(from.length)] = true;
          delete next[k];
        }
        return next;
      };
      s = { ...s, agents: moved(s.agents, s.agents[from] ? [from] : []), peek: moved(s.peek, s.peek[from] ? [from] : []), agentDetail: moved(s.agentDetail, runs) };
      changed = true;
    }
  }
  if (changed) persist(s);
}

export function togglePeek(rowKey: string): void {
  const s = uiState.get();
  persist({ ...s, peek: toggled(s.peek, rowKey) });
}

// (folded: its first page again, without the chats a bigger check listed)
export function toggleRecent(groupKey: string): void {
  const s = uiState.get();
  if (s.recent[groupKey]) {
    firstPage(groupKey + "|recent");
    dropRecentMore(groupKey);
  }
  persist({ ...s, recent: toggled(s.recent, groupKey) });
}

export function toggleStarred(key: string): void {
  const s = uiState.get();
  if (s.starred[key]) firstPage(key);
  persist({ ...s, starred: toggled(s.starred, key) });
}

// A project of the Projects tab, unfolded or folded (then its lists show their first page again)
// A project's key in the view: its folder, an SSH host's after the host's
// name (the same folder there is another project)
export function projectKey(path: string, host?: string): string {
  return host ? `${host}|${path}` : path;
}

export function toggleProject(path: string): void {
  const s = uiState.get();
  if (s.projects[path]) firstPage(...PROJECT_LISTS.map((l) => projectListKey(path, l)));
  persist({ ...s, projects: toggled(s.projects, path) });
}

// The Recap's project row: the Projects tab, that project unfolded and brought into view
export function showProject(path: string): void {
  const s = uiState.get();
  projectToShow.set(path);
  persist({ ...s, tab: "projects", projects: s.projects[path] ? s.projects : toggled(s.projects, path) });
}
export const projectToShow = createStore("");

// ---------------------------------------------------------------- lists a page at a time
// How many pages past its first a list shows (by its key: an account's key
// + "|recent", "|chats" or "|plans", a project's projectListKey), while the
// view is open (src/shared/model.ts: recentPage, projectLists)
export const pages = createStore<Record<string, number>>({});

export const PROJECT_LISTS = ["chats", "plans", "memories"] as const;
export function projectListKey(path: string, list: (typeof PROJECT_LISTS)[number]): string {
  return `project|${path}|${list}`;
}

export function pagesShown(all: Record<string, number>, key: string): number {
  return 1 + (all[key] ?? 0);
}

export function showMore(key: string): void {
  const all = pages.get();
  pages.set({ ...all, [key]: (all[key] ?? 0) + 1 });
}

function firstPage(...keys: string[]): void {
  const all = pages.get();
  if (!keys.some((k) => k in all)) return;
  const next = { ...all };
  for (const k of keys) delete next[k];
  pages.set(next);
}

// An account's recent chats past what the status lists, as a bigger check
// listed them (the extension runs it: "recentMore"), by its key; asked once
// for each count while its list is open
export const recentMore = createStore<Record<string, RecentMore>>({});
const recentAsked = new Map<string, number>();

export function askRecentMore(group: Group, count: number): void {
  const key = groupKeyOf(group);
  if (recentAsked.get(key) === count) return;
  recentAsked.set(key, count);
  post({ type: "recentMore", groupId: group.id, ...(group.host ? { host: group.host } : {}), count });
}

// Its answer, while the list is still open (folded, its first page shows)
export function gotRecentMore(m: { groupId: string; host?: string; recent: RecentChat[]; asked: number }): void {
  const key = (m.host ? m.host + "/" : "") + m.groupId;
  if (!m.asked || !uiState.get().recent[key]) return;
  recentMore.set({ ...recentMore.get(), [key]: { recent: m.recent, asked: m.asked } });
}

function dropRecentMore(key: string): void {
  recentAsked.delete(key);
  const all = recentMore.get();
  if (!(key in all)) return;
  const next = { ...all };
  delete next[key];
  recentMore.set(next);
}

export function toggleStats(groupKey: string): void {
  const s = uiState.get();
  persist({ ...s, stats: toggled(s.stats, groupKey) });
}
