// The Projects tab: each project (a chat's git repository, else its folder),
// newest first, folded: its name, when Claude last worked there, a dot for
// each of its open chats, a button for a new chat there and one to hide it. Opened (its
// lines are made then): its open chats now, Claude's last recap of it, its
// chats, plans and memories, each a page at a time (as Recent chats), each
// line as under an account, with the account it's on when the project is on
// several. Everything of it comes from week.py --projects (asked when the tab
// is in sight, again every 10 minutes, at the view's Refresh, and after a
// star, a hide or a delete); what goes on now from the status (the view's
// state). No time or money here: the Recap has them, by project.

import { useEffect, useRef } from "preact/hooks";
import type { Group, ProjectRow, Session } from "../../src/shared/types";
import { duration, folderIn, groupOfProfile, listedChats, openChatsByProject, pagedTitle, pageSizeOf, projectLists, stateText } from "../../src/shared/model";
import { post } from "../env";
import { hideHint } from "../util/chat";
import { I, Icon } from "../util/icons";
import { useAfterFrame } from "../util/lazy";
import { useViewVisible } from "../util/petStage";
import { useStore } from "../util/store";
import { projectsAnswer, useReadAgain } from "../util/stores";
import { pages, pagesShown, projectListKey, projectToShow, showMore, toggleProject, uiState } from "../util/ui";
import { useView } from "./context";
import { FocusLine } from "./FocusView";
import { MemoryLine } from "./MemoryLine";
import { MoreButton } from "./MoreButton";
import { PlanLine } from "./PlanLine";
import { Reading } from "./Reading";
import { RecentLine, reopenOf, type Reopen } from "./RecentLine";
import { dotClass } from "./SessionRow";

export function ProjectsView() {
  const answer = useStore(projectsAnswer);
  const view = useView();
  const ui = useStore(uiState);
  // Asked when the tab is in sight, again every 10 minutes and at the view's
  // Refresh; gone, not read again after a star, a hide or a delete
  const visible = useViewVisible();
  useEffect(() => {
    if (!visible) return undefined;
    post({ type: "projects" });
    const t = setInterval(() => post({ type: "projects" }), 600000);
    return () => clearInterval(t);
  }, [visible]);
  useReadAgain(visible, () => post({ type: "projects" }));
  useEffect(() => () => post({ type: "projects", shown: false }), []);
  // Shown again (Show Hidden Projects, Plans or Memories Again): read again,
  // as a hide from here is (Plasma reads again after either)
  const hidden = (view.status?.hiddenProjects ?? 0) + (view.status?.hiddenPlans ?? 0) + (view.status?.hiddenMemories ?? 0);
  const hiddenBefore = useRef(hidden);
  useEffect(() => {
    if (visible && hidden < hiddenBefore.current) post({ type: "projects" });
    hiddenBefore.current = hidden;
  }, [hidden]);
  if (!answer) return <Reading text="Reading your chats by project…" />;
  const projects = answer.data?.projects ?? [];
  // (a read that failed says why, above the projects read before it, as Plasma's)
  const error = answer.error ? <div class="msg error" role="alert">Couldn't read your projects: {answer.error}</div> : null;
  if (!projects.length) {
    return error ?? (
      <div class="empty">
        <p class="empty-title">No projects yet</p>
        <p class="muted">A project is a folder (or the git repository it's in) where you chatted with Claude.</p>
      </div>
    );
  }
  const groups = view.status?.groups ?? [];
  const now = Date.now();
  // (each open chat in its closest project only; one you hid counts, so its chats show in no other)
  const open = openChatsByProject([...projects, ...(answer.data?.hiddenPaths ?? []).map((path) => ({ path }))],
    groups.flatMap((g) => g.sessions));
  return (
    <div class="projects">
      {error}
      {projects.map((p) => (
        <Project key={p.path} p={p} open={!!ui.projects[p.path]} now={now} here={(p.path && open.get(p.path)) || []} />
      ))}
    </div>
  );
}

// One project: its line, and opened, what's in it
function Project({ p, open, here, now }: { p: ProjectRow; open: boolean; here: Session[]; now: number }) {
  const card = useRef<HTMLElement>(null);
  // (opened from the Recap: brought into view)
  const toShow = useStore(projectToShow);
  useEffect(() => {
    if (toShow && toShow === p.path && card.current) {
      card.current.scrollIntoView({ block: "start" });
      projectToShow.set("");
    }
  }, [toShow]);
  // (a plan whose chat is gone: its folder isn't known)
  const unfiled = !p.path;
  const profileDir = p.chats[0]?.profileDir ?? p.plans[0]?.profileDir ?? p.memories[0]?.profileDir ?? "";
  return (
    <section class="project" ref={card}>
      <div class="project-head">
        <button type="button" class="project-name" aria-expanded={open} onClick={() => toggleProject(p.path)}>
          <span class={"chevron" + (open ? " open" : "")} aria-hidden="true"><Icon name={I.folded} /></span>
          <span class="project-title">
            <strong>{unfiled ? "Plans whose chat is gone" : p.name}</strong>
            <span class="small muted project-meta" title={p.path || undefined}>
              {unfiled ? "Their folder isn't known any more"
                : `${p.gone ? `${p.short} (not there any more)` : p.short} · last at work ${duration(Math.max(60000, now - p.lastAt))} ago`}
            </span>
          </span>
        </button>
        {/* a dot for each of its open chats, in its state's color, at the top right */}
        {here.length ? (
          <span class="project-dots" title={`${here.length} open ${here.length === 1 ? "chat" : "chats"}\n` + here.map((s) => `${s.name}: ${stateText(s, now)}`).join("\n")}>
            {here.map((s) => <span key={s.key} class={`focus-dot ${dotClass(s)}`} aria-hidden="true" />)}
          </span>
        ) : null}
        {/* on hover (or Tab), over the end of its folder's line: the dots stay in sight, and nothing moves */}
        {unfiled ? null : (
          <span class="project-actions">
            <button type="button" class="icon-btn" title={`New chat here\n${p.short}`} aria-label="New chat here"
              onClick={() => post({ type: "newChatIn", path: p.path, short: p.short, profileDir })}>
              <Icon name={I.newChat} />
            </button>
            <button type="button" class="icon-btn" title={`Hide this project\n${hideHint("projects")}`} aria-label="Hide this project"
              onClick={() => post({ type: "hide", kind: "projects", id: p.path })}>
              <Icon name={I.hide} />
            </button>
          </span>
        )}
      </div>
      {open ? <ProjectDetails p={p} here={here} /> : null}
    </section>
  );
}

// An opened project: its open chats now, Claude's last recap of it, then its
// chats (not the ones listed as running chats), plans and memories
function ProjectDetails({ p, here }: { p: ProjectRow; here: Session[] }) {
  const view = useView();
  const shownPages = useStore(pages);
  const size = pageSizeOf(view.settings.recentChats);
  const groups = view.status?.groups ?? [];
  const lists = projectLists(p, listedChats(groups), {
    chats: pagesShown(shownPages, projectListKey(p.path, "chats")),
    plans: pagesShown(shownPages, projectListKey(p.path, "plans")),
    memories: pagesShown(shownPages, projectListKey(p.path, "memories")),
  }, size);
  // (each line on its account here: how its chats reopen, once for each)
  const hows = new Map<string, Reopen>();
  const groupOf = (profileDir: string): Group | undefined => groupOfProfile(view.status, profileDir) ?? groups[0];
  const howOf = (g: Group): Reopen => hows.get(g.id) ?? hows.set(g.id, reopenOf(view, g)).get(g.id)!;
  const tag = (account: string) => (lists.tagged ? account : undefined);
  // (its plans and memories a frame after its chats: the project opens at once)
  const rest = useAfterFrame();
  // (the folder column takes room only while a line shown is in a folder
  // below the project's, one for the three lists so their times line up, as Plasma's)
  const belowProject = [
    ...lists.chats.slice(0, lists.chatsShown).map((c) => folderIn(c.cwd, p.path, c.cwdShort || "~")),
    ...(rest ? lists.plans.slice(0, lists.plansShown).map((x) => folderIn(x.cwd, p.path, x.cwdShort)) : []),
    ...(rest ? lists.memories.slice(0, lists.memoriesShown).map((m) => (m.type === "account" ? "every folder" : folderIn(m.folder, p.path, m.folderShort))) : []),
  ].some((f) => !!f);
  const listClass = "recent-list" + (belowProject ? "" : " no-folders");
  return (
    <div class="project-details">
      {/* what goes on there now: the focus view's lines (as Plasma's) */}
      {here.map((s) => {
        const g = groups.find((x) => x.sessions.includes(s));
        return g ? <FocusLine key={s.key} item={{ key: s.key, session: s, group: g }} /> : null;
      })}
      {p.recap?.text ? <p class="project-recap">“{p.recap.text}”</p> : null}
      {lists.chats.length ? (
        <>
          <div class="project-list small">{pagedTitle("Chats", lists.chatsShown, lists.chats.length)}</div>
          <ul class={listClass}>
            {lists.chats.slice(0, lists.chatsShown).map((c) => {
              const g = groupOf(c.profileDir);
              return g ? <RecentLine key={c.key} chat={c} group={g} how={howOf(g)} project={p.path} accountTag={tag(c.account)} /> : null;
            })}
          </ul>
          <MoreButton shown={lists.chatsShown} count={lists.chats.length} size={size} onClick={() => showMore(projectListKey(p.path, "chats"))} />
        </>
      ) : null}
      {rest && lists.plans.length ? (
        <>
          <div class="project-list small">{pagedTitle("Plans", lists.plansShown, lists.plans.length)}</div>
          <ul class={listClass}>
            {lists.plans.slice(0, lists.plansShown).map((x) => {
              const g = groupOf(x.profileDir);
              return g ? <PlanLine key={x.key} plan={x} group={g} project={p.path} accountTag={tag(x.account)} /> : null;
            })}
          </ul>
          <MoreButton shown={lists.plansShown} count={lists.plans.length} size={size} onClick={() => showMore(projectListKey(p.path, "plans"))} />
        </>
      ) : null}
      {rest && lists.memories.length ? (
        <>
          <div class="project-list small">{pagedTitle("Memories", lists.memoriesShown, lists.memories.length)}</div>
          <ul class={listClass}>
            {lists.memories.slice(0, lists.memoriesShown).map((m) => {
              const g = groupOf(m.profileDir);
              return g ? <MemoryLine key={m.key} memory={m} group={g} project={p.path} accountTag={tag(m.account)} /> : null;
            })}
          </ul>
          <MoreButton shown={lists.memoriesShown} count={lists.memories.length} size={size} onClick={() => showMore(projectListKey(p.path, "memories"))} />
        </>
      ) : null}
    </div>
  );
}
