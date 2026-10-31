import { useState } from "preact/hooks";
import { duration, keptChat, queuedFor, queuedWhat, startText } from "../../src/shared/model";
import type { Group, QueuedTask } from "../../src/shared/types";
import { post } from "../env";
import { Icon, I, T } from "../util/icons";
import { useWoken } from "../util/lazy";
import { useView } from "./context";
import { IconButton } from "./IconButton";

// Tasks waiting for this account's usage limit to reset (the queue is
// this computer's, an SSH host's tasks included): when each starts, or why
// it didn't; start one now, or cancel it
export function QueuedTasks({ group }: { group: Group }) {
  const view = useView();
  const [asking, setAsking] = useState(""); // the task whose Cancel it asks first
  const tasks = queuedFor(view.status, group);
  if (!tasks.length) return null;
  return (
    <ul class="queued">
      {tasks.map((t) => (
        <QueuedLine key={t.id} task={t} asking={asking === t.id} ask={(on) => setAsking(on ? t.id : "")} />
      ))}
    </ul>
  );
}

// One queued task, a line as a recent chat's: its mark, what it is, and at its
// end its folder and when it starts; Start now and Cancel show on hover (or
// Tab, or a finger's hold), over that end. A failed one says why under it.
function QueuedLine({ task: t, asking, ask }: { task: QueuedTask; asking: boolean; ask: (on: boolean) => void }) {
  const view = useView();
  const [woken, wake] = useWoken(); // (its buttons: made the first time they show)
  const what = queuedWhat(t);
  // (what you wrote for it is asked about first: it's gone with it; a kept chat's go-on stops it keeping going)
  const wrote = !t.chat || !!t.afterTurn;
  const kept = !!t.chat && !t.afterTurn && !t.host && keptChat(view.status, t.chat) !== null;
  const folder = (t.host ? `${t.host}:` : "") + (t.folder || "~");
  const how = t.chat
    ? `The chat goes on in the background in ${folder}, at ${startText(t.startAt, view.now)}, telling Claude that the limit has reset. A Claude that still has it open (in a terminal, or in the background) quits first; if it went on before then, nothing happens.`
    : t.scheduled
      ? `Starts in the background in ${folder}, at ${startText(t.startAt, view.now)}: the time you picked.`
      : `Waits for the usage limit, then starts in the background in ${folder}, at ${startText(t.startAt, view.now)}.`;
  const when = t.error
    ? "didn't start"
    : t.due || t.startAt <= view.now
      ? "starting…"
      : t.startAt - view.now > 12 * 3600_000
        ? `starts ${startText(t.startAt, view.now)}`
        : `starts in ${duration(t.startAt - view.now)}`;
  return (
    <li class={"queued-item" + (t.error ? " failed" : "")}>
      <div class="recent-item queued-line" {...wake}>
        <Icon name={t.error ? I.warning : I.goOnAt} class="queued-mark" />
        <span class="queued-what" tabIndex={0} title={`${what}\n\n${how}`}>
          {what.split("\n")[0]}
        </span>
        <span class="queued-when small nowrap" title={t.error || undefined}>
          {t.folderShort || "~"} · {when}
        </span>
        {woken || asking ? (
          <div class={"row-actions" + (asking ? " shown" : "")}>
            <IconButton
              icon={I.startNow}
              label="Start it now"
              title={
                t.scheduled
                  ? "Start it now, in the background, without waiting for its time."
                  : "Start it now, in the background, without waiting for the limit to reset. While the limit lasts, Claude stops again at once."
              }
              onClick={() => post({ type: "startQueued", id: t.id })}
            />
            <IconButton icon={I.cancel} tone={T.cancel} label="Cancel it"
              title={"Cancel it\nIt doesn't start." + (kept ? " It stops keeping going after usage limits too." : "")
                + (wrote ? " It asks first: what you wrote for it is gone with it." : "")}
              onClick={() => (wrote ? ask(!asking) : post({ type: "unqueue", id: t.id }))} />
          </div>
        ) : null}
      </div>
      {t.error ? <div class="queued-error small">{t.error}</div> : null}
      {asking ? (
        <div class="confirm queued-ask">
          <span>{t.afterTurn ? `Cancel your message to “${t.name || "the chat"}”? It isn't sent, and its text is gone.`
            : "Cancel this task? It doesn't start, and what you wrote for it is gone."}</span>
          <button type="button" class="btn small" onClick={() => { ask(false); post({ type: "unqueue", id: t.id }); }}>Cancel it</button>
          <button type="button" class="btn secondary small" onClick={() => ask(false)}>Keep it</button>
        </div>
      ) : null}
    </li>
  );
}
