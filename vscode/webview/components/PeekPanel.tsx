import { hostLabel, plural, recapText, recapTitle, taskMark } from "../../src/shared/model";
import type { ChatRef, Session } from "../../src/shared/types";
import { post } from "../env";
import { useView } from "./context";

// Unfolded under a chat (click its peek line): your last prompt, Claude's
// last reply, its task list, its changed files to compare side by side, and
// its numbers (prompts, time worked, tool calls, tokens)
export function PeekPanel({ session: s, host, chat }: { session: Session; host?: string; chat: ChatRef }) {
  const peek = s.peek;
  const tasks = s.tasks;
  const changes = s.changes;
  const stats = s.stats;
  const now = useView().now;
  const elsewhere = host ? `Its files are on ${hostLabel(host)}: compare them there.` : "";
  return (
    <div class="peek small">
      {peek?.recap?.text ? (
        <div class="peek-msg" title="Claude's recap of the chat, written when you came back to it">
          <span class="peek-who">Recap</span>
          <div class="peek-text">{peek.recap.text}</div>
        </div>
      ) : null}
      {peek?.prompt ? (
        <div class="peek-msg">
          <span class="peek-who">You</span>
          <div class="peek-text">{peek.prompt}</div>
        </div>
      ) : null}
      {peek?.reply ? (
        <div class="peek-msg">
          <span class="peek-who">Claude</span>
          <div class="peek-text peek-reply">{peek.reply}</div>
        </div>
      ) : null}
      {tasks?.items.length ? (
        <ul class="peek-tasks" aria-label="Tasks">
          {tasks.items.map((t, i) => (
            <li key={i} class={`task task-${t.status}`}>
              <span class="task-mark" aria-hidden="true">
                {taskMark(t.status)}
              </span>
              <span class="task-subject" title={t.subject}>
                {t.subject}
              </span>
            </li>
          ))}
          {tasks.total > tasks.items.length ? <li class="task muted">+{tasks.total - tasks.items.length} more</li> : null}
        </ul>
      ) : null}
      {changes ? (
        <div class="peek-actions">
          <button
            type="button"
            class="link"
            disabled={!!host}
            title={elsewhere || "Each file as it was before the chat and now, side by side in VS Code's changes view"}
            onClick={() => post({ type: "compareChanges", chat, turn: false })}
          >
            Compare changes ({plural(changes.count, "%1 file", "%1 files")})
          </button>
          <button
            type="button"
            class="link"
            disabled={!!host}
            title={elsewhere || "Only what changed since your last prompt"}
            onClick={() => post({ type: "compareChanges", chat, turn: true })}
          >
            Last turn
          </button>
        </div>
      ) : null}
      {stats ? (
        <div class="peek-recap muted" title={recapTitle(stats, now)}>
          {recapText(stats, s.costUsd)}
        </div>
      ) : null}
    </div>
  );
}
