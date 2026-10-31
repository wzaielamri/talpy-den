import { ago, folderIn, machineStatus, shareAccounts } from "../../src/shared/model";
import type { Group, PlanItem } from "../../src/shared/types";
import { post } from "../env";
import { deleteHint, hideHint } from "../util/chat";
import { I, Icon, T } from "../util/icons";
import { useWoken } from "../util/lazy";
import { useView } from "./context";
import { Elided } from "./Elided";
import { IconButton } from "./IconButton";
import { Tag } from "./Tag";

// One of an account's plans (<config>/plans, what its chats wrote in plan
// mode; ★ Starred plans, a project's plans): it opens in the Markdown
// preview (an SSH host's: a copy, unless this window is connected to it); on
// hover, star it, edit it, send your feedback, carry it out in a new chat
// (▶), go back to the chat that made it (◀), share it with the machine's
// other accounts, delete it, hide it. In a project (project: its folder) the
// folder says only the part below the project's, and accountTag the account
// it's on when the project is on several.
export function PlanLine({ plan: p, group, project, accountTag }: { plan: PlanItem; group: Group; project?: string; accountTag?: string }) {
  const view = useView();
  const [woken, wake] = useWoken(); // (its buttons: made the first time they show)
  const host = group.host;
  const share = shareAccounts(machineStatus(view, host)).length >= 2;
  const copy = !!host && host !== view.hosts.find((h) => h.current)?.name;
  const ref = (plan: string) => (host ? { groupId: group.id, host, plan } : { groupId: group.id, plan });
  // (in a project: only the part of its folder below the project's)
  const folder = project !== undefined ? folderIn(p.cwd, project, p.cwdShort) : p.cwdShort;
  return (
    <li class="recent-item" {...wake}>
      <Icon name={I.plan} class="line-icon" />
      <button
        type="button"
        class="link recent-name"
        title={
          `${p.title}\n` +
          (copy
            ? `Click to read it: a copy, fetched from ${host}.`
            : "Click to read it in the Markdown preview. Its Open Source button edits it: what you change there is the plan.") +
          (p.cwd ? `\nFolder: ${host ? `${host}:` : ""}${p.cwd}` : "") +
          (p.shared ? "\nShared with your other accounts." : "") +
          (p.chatId ? "" : "\nThe chat that made it isn't here any more.")
        }
        onClick={() => post({ type: "openPlan", ...ref(p.key) })}
      >
        {p.title}
      </button>
      {p.shared ? (
        <span class="shared-mark" title="Shared with your other accounts">
          <Icon name={I.share} />
        </span>
      ) : null}
      {p.edited && p.chatId && !host ? (
        <Tag
          icon={I.send}
          text="Send"
          active
          title="You changed this plan since Claude wrote it. Click to send what you changed (and your comments on it) to the chat that made it: Claude revises the plan, in plan mode."
          onClick={() => post({ type: "sendPlanFeedback", ...ref(p.key) })}
        />
      ) : null}
      {accountTag ? <Tag text={accountTag} /> : null}
      {p.starred ? (
        <button type="button" class="star-mark" title="A starred plan stays listed under its account's ★ Starred plans, however old it is. Click to unstar it." onClick={() => post({ type: "star", ...ref(p.key), on: false })}>
          <Icon name={I.starred} tone={T.starred} />
        </button>
      ) : null}
      {folder ? <Elided text={folder} class="recent-folder small muted" title={p.cwd} /> : <span class="recent-folder" title={p.cwd || undefined} />}
      <span class="recent-ago small muted nowrap">{ago(view.now - p.updatedAt)}</span>
      {woken ? (
        <div class="row-actions">
          {p.starred ? null : (
            <IconButton
              icon={I.star}
              label="Star"
              title="Star this plan: it stays listed under its account's ★ Starred plans, however old it is."
              onClick={() => post({ type: "star", ...ref(p.key), on: true })}
            />
          )}
          {copy ? null : (
            <IconButton
              icon={I.edit}
              label="Edit the plan"
              title="Edit the plan: its Markdown file opens in an editor tab. What you change there is the plan."
              onClick={() => post({ type: "openPlan", ...ref(p.key), edit: true })}
            />
          )}
          {copy || host ? null : (
            <IconButton
              icon={I.send}
              label="Send your feedback to Claude"
              disabled={!p.chatId}
              title={
                !p.chatId ? "The chat that made it isn't here any more, so there's no chat to send your feedback to."
                  : (p.edited ? "You changed this plan since Claude wrote it. " : "") +
                    "Send what you changed in it, and your comments on its lines (the + next to a line, in its file), to the chat that made it: Claude revises the plan, in plan mode."
              }
              onClick={() => post({ type: "sendPlanFeedback", ...ref(p.key) })}
            />
          )}
          <IconButton
            icon={I.startNow}
            label="Carry it out…"
            title="Carry it out in a new chat: the plan is the chat's first message, with what you add; in a terminal, in the background or in a Claude Code panel, in the plan's folder or another one."
            onClick={() => post({ type: "carryOutPlan", ...ref(p.key) })}
          />
          <IconButton
            icon={I.origin}
            label="Continue the chat that made it"
            disabled={!p.chatId}
            title={p.chatId
              ? "Continue the chat that made it, to change the plan with Claude: it comes up, or reopens (in a terminal or a Claude Code panel, as the switch of Recent chats says)."
              : "The chat that made it isn't here any more."}
            onClick={() => post({ type: "continuePlanChat", ...ref(p.key) })}
          />
          {share ? (
            <IconButton
              icon={I.share}
              label="Share this plan…"
              title="Share this plan with your other accounts: one file on each of them, so a change shows on all of them. Sharing a chat shares its plan too."
              onClick={() => post({ type: "sharePlan", ...ref(p.key) })}
            />
          ) : null}
          <IconButton icon={I.delete} tone={T.delete} label="Delete this plan…" title={`Delete this plan…\n${deleteHint("plan")}`}
            onClick={() => post({ type: "delete", kind: "plan", groupId: group.id, ...(host ? { host } : {}), id: p.key })} />
          <IconButton icon={I.hide} label="Hide this plan" title={`Hide this plan\n${hideHint("plans", host)}`}
            onClick={() => post({ type: "hide", kind: "plans", groupId: group.id, ...(host ? { host } : {}), id: p.key })} />
        </div>
      ) : null}
    </li>
  );
}
