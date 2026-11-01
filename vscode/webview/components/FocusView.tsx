import { chatRefOf, doingText, duration, focusLists, liveMatch, petKeyOf, stateText } from "../../src/shared/model";
import type { Group } from "../../src/shared/types";
import { post } from "../env";
import { pets } from "../pets";
import { rowKeyOf } from "../util/chat";
import { useLiveView } from "../util/stores";
import { setFocus } from "../util/ui";
import { I, Icon } from "../util/icons";
import { useView } from "./context";
import { dotClass, SessionRow } from "./SessionRow";
import type { FocusItem } from "../../src/shared/model";

// The focus view (the header's filter button): only what needs you, as full
// rows (their questions, Allow / Deny), the chats that finished a turn you
// haven't opened yet, one line for each chat at work with what it does now,
// and how the rest stands; Show everything goes back to the whole dashboard.
export function FocusView({ groups }: { groups: Group[] }) {
  const view = useView();
  const lists = focusLists(groups, view.finished);
  const rest = [
    lists.rest.idle ? `${lists.rest.idle} idle` : "",
    lists.rest.limit ? `${lists.rest.limit} at the usage limit` : "",
    lists.rest.done ? `${lists.rest.done} done` : "",
  ].filter(Boolean);
  return (
    <section class="focus">
      <h2 class={"focus-title" + (lists.needs.length ? " needs" : " calm")}>
        {lists.needs.length === 0 ? "Nothing needs you" : lists.needs.length === 1 ? "Needs you" : `${lists.needs.length} need you`}
      </h2>
      <div class="sessions">
        {lists.needs.map((i) => (
          <SessionRow key={i.session.key} session={i.session} group={i.group} host={i.group.host}
            showProfile={(i.group.profiles ?? []).length > 1} />
        ))}
      </div>
      {lists.finished.map((i) => <FocusLine key={i.key} item={i} finished />)}
      {lists.working.length ? <h2 class="focus-title">{lists.working.length === 1 ? "Working" : `${lists.working.length} working`}</h2> : null}
      {lists.working.map((i) => <FocusLine key={i.key} item={i} />)}
      <div class="focus-rest muted">
        {rest.length ? <div>Also: {rest.join(" · ")}</div> : null}
        {lists.usage.length ? <div class="small">5-hour usage: {lists.usage.map((u) => `${u.name} ${Math.round(u.pct)}%`).join(" · ")}</div> : null}
        <button type="button" class="btn secondary focus-all" onClick={() => setFocus(false)}>
          <Icon name={I.showAll} />
          Show everything
        </button>
      </div>
    </section>
  );
}

// One chat: its pet's color, a dot, its name, what it does now (or that it
// finished), how long; a click opens it (as a click on its name does)
// (also an opened project's open chats: ProjectsView, as Plasma's FocusLine)
export function FocusLine({ item, finished = false }: { item: FocusItem; finished?: boolean }) {
  const view = useView();
  const s = item.session,
    host = item.group.host;
  const live = useLiveView(s.sessionId, !finished && !host && !!s.pid);
  const doing = finished ? "" : doingText(s, liveMatch(s, live));
  const what = finished
    ? s.reason === "failed" ? "Failed: look at what happened" : "Finished: results to look at"
    : doing || stateText(s, view.now);
  const color = pets.petColor(petKeyOf(s, host));
  return (
    <button type="button" class={"focus-line" + (finished ? " finished" : "")} data-row={rowKeyOf(s, host)}
      title={`${s.name}\n${what}\nClick to open this chat`} onClick={() => post({ type: "open", chat: chatRefOf(s, host) })}>
      <span class="pet-bar" style={{ background: color || "transparent" }} aria-hidden="true" />
      <span class={"focus-dot" + (finished ? "" : " " + dotClass(s))} aria-hidden="true" />
      <span class="focus-name">{(host ? host + ": " : "") + s.name}</span>
      <span class="focus-what">{what}</span>
      {/* (with no step known, the state's text says how long itself) */}
      {doing && s.since ? <span class="focus-time small muted">{duration(view.now - s.since)}</span> : null}
    </button>
  );
}
