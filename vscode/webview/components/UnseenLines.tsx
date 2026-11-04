import { useState } from "preact/hooks";
import { containerOf, hostLabel, startText, unseenHostItems, type UnseenItem } from "../../src/shared/model";
import { post } from "../env";
import { Icon, I, T } from "../util/icons";
import { useView } from "./context";
import { IconButton } from "./IconButton";

// Chats that keep going, and tasks queued, on SSH hosts and in containers
// that aren't shown (unseenHostItems): they go on all the same, from here
// over ssh, so they're said where the hosts go, lest you forget them, as
// Plasma's UnseenLine.qml: Show (the host joins the list, with all its
// buttons) and Stop (Keep going off, its queued go-on cancelled) or Cancel.
// A task you wrote is cancelled where it shows, which asks first: Show only.
// Your message to a chat, queued for its turn's end, asks first here too, as
// its queued line does (what you wrote is gone with it).
export function UnseenLines({ shown }: { shown: string[] }) {
  const view = useView();
  const [asking, setAsking] = useState(""); // the message whose Cancel it asks first
  const items = unseenHostItems(view.status, shown);
  if (!items.length) return null;
  return (
    <ul class="queued unseen">
      {items.map((it) => (
        <UnseenLine key={`${it.host}|${it.kept?.chat ?? ""}|${it.task?.id ?? ""}`} item={it}
          asking={!!it.task && asking === it.task.id} ask={(on) => setAsking(on && it.task ? it.task.id : "")} />
      ))}
    </ul>
  );
}

function UnseenLine({ item, asking, ask }: { item: UnseenItem; asking: boolean; ask: (on: boolean) => void }) {
  const view = useView();
  const { host, kept, task: t, name } = item;
  const where = hostLabel(host);
  const what = kept
    ? `“${name}” keeps going on ${where}, which isn't shown`
    : t?.afterTurn
      ? `Your message to “${name}” on ${where}, which isn't shown`
      : t?.chat
        ? `“${name}” goes on by itself on ${where}, which isn't shown`
        : `A task queued on ${where}, which isn't shown`;
  const when = t && !t.error && !t.afterTurn ? ` · ${t.chat ? "goes on" : "starts"} at ${startText(t.startAt, view.now)}` : "";
  const wrote = !!t && !t.chat;
  const message = !!t?.afterTurn;
  return (
    <li class={"queued-item" + (t?.error ? " failed" : "")}>
      <div class="recent-item queued-line unseen-line">
        <Icon name={kept ? I.keepGoing : I.goOnAt} class="queued-mark" />
        <span class="queued-what" tabIndex={0}
          title={`${what}${when}\n\nIt goes on all the same: Talpy Den starts it from here, over ssh. Show ${where} to see it with all its buttons.`
            + (kept ? " Stop: it doesn't keep going any more, and its queued go-on is cancelled." : "")}>
          {what}{when}
        </span>
        <IconButton icon={containerOf(host) ? I.container : I.host} class="text-btn" label={`Show ${where}`}
          title={`Show ${where}\nIt joins the list, with its chats and all their buttons.`}
          onClick={() => post({ type: "showHost", host })}>
          <span class="btn-words">Show {where}</span>
        </IconButton>
        {!wrote ? (
          <IconButton icon={I.cancel} tone={T.cancel} class="text-btn" label={kept ? "Stop" : "Cancel"}
            title={kept ? "Stop keeping it going\nIt doesn't go on by itself after usage limits any more; its queued go-on is cancelled."
              : message ? "Cancel it\nIt isn't sent. It asks first: what you wrote for it is gone with it."
              : "Cancel it\nIt doesn't go on by itself."}
            onClick={() => (message ? ask(!asking) : t ? post({ type: "unqueue", id: t.id }) : kept && post({ type: "keepOff", chatId: kept.chat, host }))}>
            <span class="btn-words">{kept ? "Stop" : "Cancel"}</span>
          </IconButton>
        ) : null}
      </div>
      {t?.error ? <div class="queued-error small">{t.error}</div> : null}
      {t && asking ? (
        <div class="confirm queued-ask">
          <span>{`Cancel your message to “${name}”? It isn't sent, and its text is gone.`}</span>
          <button type="button" class="btn secondary small" onClick={() => { ask(false); post({ type: "unqueue", id: t.id }); }}><Icon name={I.cancel} tone={T.cancel} />Cancel it</button>
          <button type="button" class="btn secondary small" onClick={() => ask(false)}>Keep it</button>
        </div>
      ) : null}
    </li>
  );
}
