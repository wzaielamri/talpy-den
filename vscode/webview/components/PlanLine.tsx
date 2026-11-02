import { ago, folderIn, machineStatus, shareAccounts } from "../../src/shared/model";
import type { Group, PlanItem } from "../../src/shared/types";
import { post } from "../env";
import { deleteHint, hideHint } from "../util/chat";
import { I, Icon, T } from "../util/icons";
import { useWoken } from "../util/lazy";
import { useView } from "./context";
import { askDelete, DeleteAsk } from "./DeleteAsk";
import { askMove, MoveAsk } from "./MoveAsk";
import { moveAsk, planDrag } from "../util/stores";
import { useStore } from "../util/store";
import { Elided } from "./Elided";
import { IconButton } from "./IconButton";
import { Tag } from "./Tag";

// One of an account's plans (<config>/plans, what its chats wrote in plan
// mode, or its project's own plans folder: p.inProject; ★ Starred plans, a
// project's plans): it opens in the Markdown preview (an SSH host's: a
// copy, unless this window is connected to it); on hover, star it, edit it,
// send your feedback, carry it out in a new chat (▶), go back to the chat
// that made it (◀), share it with the machine's other accounts (not one in
// a project's folder: every account has it), delete it, hide it. In a
// project (project: its folder) the folder says only the part below the
// project's, and accountTag the account it's on when the project is on
// several. One whose project isn't known says "chat gone" there, as the
// Projects tab's card of plans whose chat is gone (chatGoneCard: in it).
// Move to project… puts its file into a project's own plans folder (one
// there has Move back), after a question under the line (MoveAsk); in the
// Projects tab (project set) its name drags onto another project's card,
// which asks the same.
export function PlanLine({ plan: p, group, project, accountTag, chatGoneCard }:
  { plan: PlanItem; group: Group; project?: string; accountTag?: string; chatGoneCard?: boolean }) {
  const view = useView();
  const [woken, wake] = useWoken(); // (its buttons: made the first time they show)
  const host = group.host;
  const share = shareAccounts(machineStatus(view, host)).length >= 2 && !p.inProject;
  const copy = !!host && host !== view.hosts.find((h) => h.current)?.name;
  const ref = (plan: string) => (host ? { groupId: group.id, host, plan } : { groupId: group.id, plan });
  // (in a project: only the part of its folder below the project's)
  const folder = project !== undefined ? folderIn(p.cwd, project, p.cwdShort) : p.cwdShort;
  const askKey = `plan|${host ?? ""}|${group.id}|${p.key}`; // (Delete?'s line, and Move?'s)
  const account = group.name || p.profile;
  const draggable = project !== undefined && !host;
  const asking = useStore(moveAsk)?.key === askKey;
  return (
    <>
    <li class="recent-item" {...wake}>
      <Icon name={I.plan} class="line-icon" />
      <button
        type="button"
        class={"link recent-name" + (draggable ? " plan-drag" : "")}
        draggable={draggable}
        onDragStart={draggable ? (e) => {
          e.dataTransfer?.setData("text/plain", p.title);
          if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
          moveAsk.set(null);
          planDrag.set({ id: p.key, groupId: group.id, from: project ?? "" });
        } : undefined}
        onDragEnd={draggable ? () => planDrag.set(null) : undefined}
        title={
          `${p.title}\n` +
          (copy
            ? `Click to read it: a copy, fetched from ${host}.`
            : "Click to read it in the Markdown preview. Its Open Source button edits it: what you change there is the plan.") +
          (p.cwd ? `\nFolder: ${host ? `${host}:` : ""}${p.cwd}` : "") +
          (p.shared ? "\nShared with your other accounts." : "") +
          (p.inProject ? "\nIn its project's plans folder: every account has it." : "") +
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
      {folder ? <Elided text={folder} class="recent-folder small muted" title={p.cwd} />
        : !p.cwd && !chatGoneCard ? (
          <span class="recent-folder small muted" title={"Its chat is gone\nThe chat that made it went before Talpy Den saw it, so its project isn't known. The Projects tab lists it under Plans whose chat is gone."}>
            chat gone
          </span>
        ) : <span class="recent-folder" title={p.cwd || undefined} />}
      {/* starred: its ★ right before the time (every line keeps its room, so the times line up); hidden while its buttons show */}
      {p.starred ? (
        <button type="button" class="star-mark" tabIndex={-1} title="A starred plan stays listed under its account's ★ Starred plans, however old it is. Click to unstar it." onClick={() => post({ type: "star", ...ref(p.key), on: false })}>
          <Icon name={I.starred} tone={T.starred} />
        </button>
      ) : <span class="star-mark" aria-hidden="true" />}
      <span class="recent-ago small muted nowrap">{ago(view.now - p.updatedAt)}</span>
      {woken ? (
        <div class="row-actions">
          {/* (a starred one's yellow ★ unstars it: the line's own ★ hides while these show) */}
          <IconButton
            icon={p.starred ? I.starred : I.star}
            tone={p.starred ? T.starred : undefined}
            label={p.starred ? "Unstar this plan" : "Star this plan"}
            title={p.starred ? "Unstar this plan\nA starred plan stays listed under its account's ★ Starred plans, however old it is. Click to unstar it."
              : "Star this plan\nIt stays listed under its account's ★ Starred plans, however old it is."}
            onClick={() => post({ type: "star", ...ref(p.key), on: !p.starred })}
          />
          {copy ? null : (
            <IconButton
              icon={I.edit}
              label="Edit the plan"
              title={"Edit the plan\nIts Markdown file opens in an editor tab. What you change there is the plan."}
              onClick={() => post({ type: "openPlan", ...ref(p.key), edit: true })}
            />
          )}
          {copy || host ? null : (
            <IconButton
              icon={I.send}
              label="Send your feedback to Claude"
              disabled={!p.chatId}
              title={
                "Send your feedback to Claude\n" + (!p.chatId ? "The chat that made it isn't here any more, so there's no chat to send your feedback to."
                  : (p.edited ? "You changed this plan since Claude wrote it. " : "") +
                    "Send what you changed in it, and your comments on its lines (the + next to a line, in its file), to the chat that made it: Claude revises the plan, in plan mode.")
              }
              onClick={() => post({ type: "sendPlanFeedback", ...ref(p.key) })}
            />
          )}
          <IconButton
            icon={I.startNow}
            label="Carry it out…"
            title={"Carry it out…\nIn a new chat: the plan is the chat's first message, with what you add; in a terminal, in the background or in a Claude Code panel, in the plan's folder or another one."}
            onClick={() => post({ type: "carryOutPlan", ...ref(p.key) })}
          />
          <IconButton
            icon={I.origin}
            label="Continue the chat that made it"
            disabled={!p.chatId}
            title={p.chatId
              ? "Continue the chat that made it\nTo change the plan with Claude: it comes up, or reopens (in a terminal or a Claude Code panel, as the switch of Recent chats says)."
              : "Continue the chat that made it\nThe chat that made it isn't here any more."}
            onClick={() => post({ type: "continuePlanChat", ...ref(p.key) })}
          />
          <IconButton
            icon={p.inProject ? I.moveBack : I.moveToProject}
            label={p.inProject ? `Move back to ${account}…` : "Move to project…"}
            askFor={askKey}
            pressed={asking}
            title={p.inProject
              ? `Move back to ${account}…\nMoves its file from its project's plans folder into ${account}'s own plans. It asks first.`
              : "Move to project…\nMoves its file into a project's own plans folder (the one its plansDirectory setting names, else .claude/plans), so it's with the project and every account has it. It asks first." +
                (draggable ? " You can also drag it by its name onto another project." : "")}
            onClick={() => askMove(askKey, { groupId: group.id, ...(host ? { host } : {}), id: p.key, ...(p.inProject ? { back: true } : {}) }, !p.inProject)}
          />
          {share ? (
            <IconButton
              icon={I.share}
              label="Share this plan…"
              title={"Share this plan…\nWith your other accounts: one file on each of them, so a change shows on all of them. Sharing a chat shares its plan too."}
              onClick={() => post({ type: "sharePlan", ...ref(p.key) })}
            />
          ) : null}
          <IconButton icon={I.delete} tone={T.delete} label="Delete this plan…" title={`Delete this plan…\n${deleteHint("plan")}`}
            onClick={() => askDelete(askKey, { kind: "plan", groupId: group.id, ...(host ? { host } : {}), id: p.key })} />
          <IconButton icon={I.hide} label="Hide this plan" title={`Hide this plan\n${hideHint("plans", host)}`}
            onClick={() => post({ type: "hide", kind: "plans", groupId: group.id, ...(host ? { host } : {}), id: p.key })} />
        </div>
      ) : null}
    </li>
    {woken ? <DeleteAsk itemKey={askKey} li /> : null}
    {woken ? <MoveAsk itemKey={askKey} li /> : null}
    </>
  );
}
