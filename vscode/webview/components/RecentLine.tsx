import {
  ago,
  goOnAt,
  claudeCodeHere,
  claudeCodeReopenHint,
  cliInstalled,
  folderIn,
  keptChat,
  keptTitle,
  machineStatus,
  queuedChat,
  reopensInClaudeCode,
  startText,
  stopText,
  terminalReopenHint,
} from "../../src/shared/model";
import { reviewPending, testsText } from "../../src/shared/pane";
import type { Group, RecentChat, ViewState } from "../../src/shared/types";
import { post } from "../env";
import { canShareRecent, deleteHint, recentRef, shareTitle } from "../util/chat";
import { useWoken } from "../util/lazy";
import { useView } from "./context";
import { Elided } from "./Elided";
import { IconButton } from "./IconButton";
import { Tag, TestsTag } from "./Tag";
import { I, Icon, T } from "../util/icons";

// Where an account's chats that no Claude has open reopen: in a terminal,
// or in a Claude Code panel (the switch above Recent chats, kept in
// talpyDen.reopenIn), and whether they can at all (no claude command on the
// chat's machine, Claude Code not here or on another account); what its
// reopen button says, and whether a chat of it can move to another account
export interface Reopen {
  cliHere: boolean;
  codeHere: boolean;
  inCode: boolean;
  canOpen: boolean;
  terminalHint: string;
  codeHint: string;
  reopen: string;
  share: boolean;
}

export function reopenOf(view: ViewState, group: Group): Reopen {
  const status = machineStatus(view, group.host);
  const cliHere = cliInstalled(status);
  const codeHere = claudeCodeHere(group, view.claudeCode);
  const inCode = reopensInClaudeCode(view.settings.reopenIn, cliHere, codeHere);
  const terminalHint = terminalReopenHint(group.host, cliHere);
  const codeHint = claudeCodeReopenHint(group, view.claudeCode, view.status?.groups ?? []);
  const canOpen = inCode || cliHere;
  const reopen = !canOpen ? `${terminalHint}\n${codeHint}` : inCode ? codeHint : terminalHint;
  return { cliHere, codeHere, inCode, canOpen, terminalHint, codeHint, reopen, share: canShareRecent(status) };
}

// One of an account's chats that no Claude has open (Recent chats, ★ Starred
// chats, a project's chats): a click opens its tab (else the chat itself);
// on hover, reopen it, star it, continue it on another account, delete it.
// In a project (project: its folder) the folder says only the part below the
// project's, and accountTag the account it's on when the project is on several.
export function RecentLine({ chat: c, group, how, project, accountTag }:
    { chat: RecentChat; group: Group; how: Reopen; project?: string; accountTag?: string }) {
  const view = useView();
  const [woken, wake] = useWoken(); // (its buttons: made the first time they show)
  const chat = recentRef(c, group.host);
  const { canOpen, inCode, reopen, share } = how;
  const goOn = goOnAt(c);
  const goingOn = queuedChat(view.status, c.sessionId, group.host);
  const kept = group.host ? null : keptChat(view.status, c.sessionId);
  const later = group.host ? "" : " Once: Keep going beside it goes on after later limits too, until it's done.";
  const canKeep = !group.host && !kept && !goingOn && goOn > 0;
  // a click opens its tab (else the chat itself, as the switch above says)
  const paneFirst = view.settings.clickOpensPane !== false;
  const reopenIt = () => post(inCode ? { type: "openInClaudeCode", chat } : { type: "openWindow", chat });
  const toReview = reviewPending({ ...c, chatId: c.sessionId, state: "done" }, view.status, group.host);
  const tests = testsText(c.review);
  // (in a project: only the part of its folder below the project's)
  const folder = project !== undefined ? folderIn(c.cwd, project, c.cwdShort || "~") : c.cwdShort || "~";
  return (
    <li class={"recent-item" + (canOpen || paneFirst ? "" : " unavailable")} {...wake}>
      <button
        type="button"
        class="link recent-name"
        aria-disabled={!canOpen && !paneFirst}
        title={
          `${c.name}\n` +
          (paneFirst
            ? "Click to open it in a tab: its conversation, a box to reply, and what it changed." + (canOpen ? `\nThe reopen button (on hover): ${reopen}` : "")
            : reopen) +
          (c.cwd ? `\nFolder: ${group.host ? `${group.host}:` : ""}${c.cwd}` : "") +
          (c.shared ? `\nShared between accounts; last used on ${c.profile}.` : "") +
          (c.stopped ? `\n\n${stopText(c.stopped)}` : "") +
          (c.recap?.text ? `\n\nRecap: ${c.recap.text}` : "")
        }
        onClick={() => (paneFirst ? post({ type: "openPane", chat }) : canOpen && reopenIt())}
      >
        {c.name}
      </button>
      {c.shared ? (
        <span class="shared-mark" title="Shared between accounts">
          <Icon name={I.share} />
        </span>
      ) : null}
      {goingOn ? (
        <Tag
          icon={I.goOnAt}
          text={startText(goingOn.startAt, view.now)}
          active
          title={`Goes on by itself at ${startText(goingOn.startAt, view.now)}, in the background, in the permission mode it had, telling Claude that the limit has reset (if it didn't go on before then).\n\nClick to cancel it.`}
          onClick={() => post({ type: "unqueue", id: goingOn.id })}
        />
      ) : c.stopped?.kind === "limit" && !c.stopped.over ? (
        <Tag
          text="Limit"
          warning
          title={`A usage limit stopped it\n${c.stopped.text}` + (goOn ? `\n\nClick to have it go on by itself in the background at ${startText(goOn, view.now)}, a minute after the limit resets.${later}` : "")}
          onClick={goOn ? () => post({ type: "queueContinue", chat }) : undefined}
        />
      ) : null}
      {kept ? (
        <Tag
          icon={I.keepGoing}
          text=""
          active={!kept.error}
          warning={!!kept.error || !!kept.note}
          title={keptTitle(kept)}
          onClick={() => post({ type: "keepGoing", chat, on: false })}
        />
      ) : canKeep ? (
        <Tag
          icon={I.keepGoing}
          text=""
          title={`Keep going until it's done\nClick to have it go on by itself in the background at ${startText(goOn, view.now)}, a minute after the limit resets, in the permission mode it had, and again after each later limit that stops it, until a turn of it ends by itself.`}
          onClick={() => post({ type: "queueContinue", chat, keep: true })}
        />
      ) : null}
      {toReview ? (
        <Tag
          text="To review"
          active
          title="It changed files. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed."
          onClick={() => post({ type: "openPane", chat, tab: "review" })}
        />
      ) : null}
      {toReview && tests ? <TestsTag tests={tests} /> : null}
      {accountTag ? <Tag text={accountTag} /> : null}
      {c.starred ? (
        <button type="button" class="star-mark" title="A starred chat stays listed under its account's ★ Starred chats, however old it is. Click to unstar it." onClick={() => post({ type: "star", chat, on: false })}>
          <Icon name={I.starred} tone={T.starred} />
        </button>
      ) : null}
      {folder ? <Elided text={folder} class="recent-folder small muted" title={c.cwd} /> : <span class="recent-folder" title={c.cwd} />}
      <span class="recent-ago small muted nowrap">{ago(view.now - c.lastActive)}</span>
      {woken ? (
        <div class="row-actions">
          {paneFirst && canOpen ? (
            <IconButton icon={I.openWindow} label="Reopen this chat" title={reopen} onClick={reopenIt} />
          ) : null}
          {c.starred ? null : (
            <IconButton
              icon={I.star}
              label="Star"
              title="Star this chat: it stays listed under its account's ★ Starred chats, however old it is."
              onClick={() => post({ type: "star", chat, on: true })}
            />
          )}
          {share ? (
            <IconButton
              icon={I.share}
              label="Continue on another account…"
              title={shareTitle(group.host)}
              onClick={() => post({ type: "share", chat })}
            />
          ) : null}
          <IconButton icon={I.delete} tone={T.delete} label="Delete this chat…" title={`Delete this chat…\n${deleteHint("chat")}`}
            onClick={() => post({ type: "delete", kind: "chat", chat })} />
        </div>
      ) : null}
    </li>
  );
}
