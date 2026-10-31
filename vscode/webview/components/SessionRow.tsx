import {
  canEndChat,
  canMoveToClaudeCode,
  changesTag,
  changesTitle,
  claudeCodeHere,
  cliInstalled,
  goOnAt,
  handoverTarget,
  hasPeek,
  hasTurn,
  keptChat,
  keptTitle,
  machineStatus,
  modeHint,
  modeText,
  overlapText,
  liveMatch,
  peekLine,
  petKeyOf,
  queuedChat,
  reopensInClaudeCode,
  resetAtText,
  shareAccounts,
  startText,
  stateText,
  tasksTitle,
  usageLevel,
} from "../../src/shared/model";
import { attachedTag, chatWhere, reviewPending, shownAsk, testsText, whereTag } from "../../src/shared/pane";
import type { Group, Session } from "../../src/shared/types";
import { post } from "../env";
import { pets } from "../pets";
import { canRemove, canShare, canStop, chatRefOf, deleteHint, hideHint, isBackground, openHint, rowKeyOf, sharedTagTitle, shareTitle } from "../util/chat";
import { useStore } from "../util/store";
import { useLiveView } from "../util/stores";
import { toggleAgents, togglePeek, uiState } from "../util/ui";
import { AgentTree } from "./AgentTree";
import { AskBox, askKey } from "./AskBox";
import { useView } from "./context";
import { I, Icon, T } from "../util/icons";
import { Elided } from "./Elided";
import { IconButton } from "./IconButton";
import { PeekPanel } from "./PeekPanel";
import { Tag, TestsTag } from "./Tag";

// The color class of a chat's state; a failed chat stands out from done ones
export function stateClass(state: string, reason: string): string {
  return reason === "failed" ? "st-failed" : `st-${state}`;
}

function lineTitle(kind: string): string {
  return kind === "needs"
    ? "What it needs: "
    : kind === "result"
      ? "Result: "
      : kind === "activity"
        ? "Doing: "
        : kind === "stopped"
          ? "What stopped it: "
          : kind === "recap"
            ? "Claude's recap of the chat, written when you came back to it:\n"
            : "";
}

// One chat: state, name (click to open), tags, folder, model, context fill,
// what it's doing or needs or said last (click it for more), and its
// subagents. With `host`, the chat is on that SSH host.
export function SessionRow({ session: s, group, host, showProfile }: { session: Session; group: Group; host?: string; showProfile: boolean }) {
  const view = useView();
  const ui = useStore(uiState);
  const now = view.now;
  const rowKey = rowKeyOf(s, host);
  const chat = chatRefOf(s, host);
  const petColor = pets.petColor(petKeyOf(s, host));
  const agents = s.agents;
  const showAgents = !!agents && !!ui.agents[rowKey];
  // where it runs, in the chat tab's words (whereTag)
  const where = whereTag(chatWhere(s, false), s.terminalApp ?? "");
  const line = peekLine(s, liveMatch(s, useLiveView(s.sessionId, !host && !!s.pid)));
  const canPeek = hasPeek(s);
  const showPeek = canPeek && !!ui.peek[rowKey];
  const tasks = s.tasks;
  const changes = s.changes;

  const share = canShare(s, machineStatus(view, host));
  const remove = canRemove(s);
  const stop = canStop(s, host);
  const codeHere = claudeCodeHere({ ...group, host }, view.claudeCode);
  const move = canMoveToClaudeCode(s, codeHere);
  const reopenInCode = s.kind === "chat" && reopensInClaudeCode(view.settings.reopenIn, cliInstalled(machineStatus(view, host)), codeHere);
  const mode = modeText(s.peek?.mode);
  const ultracode = s.peek?.ultracode === true;
  // A usage limit stopped it: it can go on on another account with room left
  const handover = handoverTarget(s, shareAccounts(machineStatus(view, host)));
  // or by itself once the limit resets (queued; again: cancelled)
  const goOn = goOnAt(s);
  const goingOn = goOn || s.stopped ? queuedChat(view.status, s.chatId || s.sessionId, host) : null;
  // it keeps going until it's done (after each usage limit, on by itself); one at work here can
  const kept = host ? null : keptChat(view.status, s.chatId || s.sessionId);
  const canKeep = !host && !kept && s.state === "working" && s.entrypoint !== "claude-vscode";
  const ending =
    (s.pid === null ? "" : s.kind === "bg" ? " This background chat is stopped first (claude stop)." : " Claude here quits first (its terminal stays open).") +
    " It goes on in the permission mode it had.";
  const resetsAt = s.stopped?.kind === "limit" && !s.stopped.over && s.stopped.resetsAt ? s.stopped.resetsAt : 0;
  // a click on its name opens its tab (else the chat itself)
  const paneFirst = view.settings.clickOpensPane !== false;
  // it changed files and is done: to review until you mark it reviewed
  const toReview = reviewPending(s, view.status, host);
  const tests = testsText(s.review);
  const stopped = s.stopped && !s.stopped.over ? " stopped" : s.stopped ? " freed" : "";

  return (
    <div class={`session ${stateClass(s.state, s.reason)}${stopped}`} data-flip={rowKey}>
      {/* A bar in the color of the chat's pet, to spot which pet is which */}
      <span class="pet-bar" style={{ background: petColor || "transparent" }} aria-hidden="true" />
      <span class="state-dot" aria-hidden="true" />
      <div class="session-main">
        <div class="session-line">
          <button
            type="button"
            class="link session-name"
            title={paneFirst ? "Open this chat in a tab: its conversation as it goes, a box to reply, and what it changed" : openHint(s, host, reopenInCode)}
            onClick={() => post({ type: "open", chat })}
          >
            {s.name}
          </button>
          {s.starred ? (
            <button
              type="button"
              class="star-mark"
              title="Starred: once it isn't listed here any more, it stays under Recent chats → Starred. Click to unstar it."
              onClick={() => post({ type: "star", chat, on: false })}
            >
              <Icon name={I.starred} tone={T.starred} />
            </button>
          ) : null}
          {showProfile && s.profile ? <Tag text={s.profile} title="The Claude profile (config folder) this chat runs in" /> : null}
          <Tag text={where.tag} title={where.title} />
          {isBackground(s) && attachedTag(s.attached) ? (
            <Tag text={attachedTag(s.attached)!.tag} title={attachedTag(s.attached)!.title} />
          ) : null}
          {s.shared ? <Tag icon={I.share} text={s.shared.forkOf ? "Shared copy" : "Shared"} title={sharedTagTitle(s)} /> : null}
          {agents ? (
            <Tag
              text={`Agents ${agents.done}/${agents.total}`}
              active={agents.running > 0}
              pressed={showAgents}
              title={`Subagents: ${agents.done} done, ${agents.running} running, ${agents.stopped} stopped${agents.failed ? `, ${agents.failed} failed` : ""}. Click to ${showAgents ? "hide" : "show"} what each one is doing.`}
              onClick={() => toggleAgents(rowKey)}
            />
          ) : null}
          {tasks ? (
            <Tag
              text={`${tasks.done}/${tasks.total}`}
              fill={tasks.total ? tasks.done / tasks.total : 0}
              active={!!tasks.current}
              pressed={showPeek}
              title={`${tasksTitle(tasks)}\n\nClick to ${showPeek ? "hide" : "show"} the chat's tasks and last exchange.`}
              onClick={() => togglePeek(rowKey)}
            />
          ) : null}
          {s.overlaps?.length ? (
            <Tag
              icon={I.warning}
              text="Same files"
              warning
              title={`${overlapText(s.overlaps)}\n\nTwo chats changing the same files can overwrite each other's work. Click to go to the other chat.`}
              onClick={() => post({ type: "openOverlap", chat })}
            />
          ) : null}
          {mode ? (
            <Tag text={mode} warning={s.peek?.mode === "bypassPermissions"} title={`Permission mode: ${mode}\n${modeHint(s.peek?.mode)}`} />
          ) : null}
          {s.plan ? (
            <Tag
              icon={I.plan}
              text="Plan"
              title={`${s.plan.title}\nThe plan this chat made. Click to read it in the Markdown preview${host && host !== view.hosts.find((h) => h.current)?.name ? ` (a copy, fetched from ${host})` : " (its Open Source button edits it)"}.`}
              onClick={() => post({ type: "openPlan", chat })}
            />
          ) : null}
          {s.plan && (!host || host === view.hosts.find((h) => h.current)?.name) ? (
            <Tag
              icon={I.edit}
              text=""
              title={`Edit the plan: its Markdown file opens in an editor tab. What you change there is the plan.`}
              onClick={() => post({ type: "openPlan", chat, edit: true })}
            />
          ) : null}
          {s.plan?.edited && !host ? (
            <Tag
              icon={I.send}
              text="Send to Claude"
              active
              title={
                "You changed this plan since Claude wrote it. Click to send what you changed (and your comments on it) to this chat: Claude revises the plan, in plan mode.\n\n" +
                "In one of this window's terminals, or in tmux, it's typed in for you. Else it goes to the clipboard and the chat comes up, to paste it there (if Claude asks whether to go ahead with the plan, choose to keep planning first). A chat that isn't open reopens in plan mode with it."
              }
              onClick={() => post({ type: "sendPlanFeedback", chat })}
            />
          ) : null}
          {changes ? (
            <Tag
              text={changesTag(changes)}
              title={changesTitle(changes, host)}
              onClick={host ? undefined : () => post({ type: "compareChanges", chat, turn: false })}
            />
          ) : null}
          {toReview ? (
            <Tag
              text="To review"
              active
              title="It changed files and its turn is over. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed."
              onClick={() => post({ type: "openPane", chat, tab: "review" })}
            />
          ) : null}
          {toReview && tests ? <TestsTag tests={tests} /> : null}
          <span class="state-text" title={stateText(s, now) + (resetsAt ? `\n${resetAtText(resetsAt, now)}` : "")}>
            {stateText(s, now)}
          </span>
        </div>

        <div class="session-line small">
          <Elided text={s.cwdShort || s.cwd || "~"} class="folder muted" title={s.cwd || s.cwdShort} />
          {s.model || ultracode ? (
            // the model, how hard it thinks (Claude's /effort) and whether ultracode is on
            <span class="muted nowrap" title={[s.model ?? "", s.effort ? `Effort: ${s.effort} (how hard it thinks; /effort changes it)` : "",
              ultracode ? "Ultracode: Claude runs workflows of agents for every substantial task (/ultracode off turns it off)" : ""]
              .filter((t) => t).join("\n")}>
              {[s.model ?? "", s.effort ?? "", ultracode ? "ultracode" : ""].filter((t) => t).join(" · ")}
            </span>
          ) : null}
          {s.context != null ? (
            <>
              {/* Context window fill */}
              <span
                class={`meter ctx-meter lvl-${usageLevel(s.context)}`}
                role="meter"
                aria-label="Context window"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(s.context)}
              >
                <span style={{ width: `${Math.min(100, Math.max(0, s.context))}%` }} />
              </span>
              <span class="muted nowrap" title="How full the chat's context window is">
                ctx {Math.round(s.context)}%
              </span>
            </>
          ) : null}
        </div>

        {line ? (
          canPeek ? (
            <button
              type="button"
              class={`session-detail small peek-line pk-${line.kind}`}
              aria-expanded={showPeek}
              title={`${lineTitle(line.kind)}${line.text}\n\nClick to ${showPeek ? "hide" : "show"} your last prompt and Claude's reply${tasks ? ", the tasks" : ""}${changes ? " and the changed files" : ""}.`}
              onClick={() => togglePeek(rowKey)}
            >
              {line.text}
            </button>
          ) : (
            <div class={`session-detail small pk-${line.kind}`} title={lineTitle(line.kind) + line.text}>
              {line.text}
            </div>
          )
        ) : null}

        {handover || goOn || goingOn || kept ? (
          <div class="handover small">
            {handover ? (
            <button
              type="button"
              class="link"
              title={
                (handover.pct !== null
                  ? `${handover.title} has used ${Math.round(handover.pct)}% of its ${handover.label} limit.`
                  : `${handover.title}'s plan usage isn't known here.`) +
                (s.pid !== null
                  ? s.kind === "bg"
                    ? ` This background chat is stopped first (claude stop); then the chat is shared with ${handover.title} and reopens there in a terminal.`
                    : ` Claude here quits first (its terminal stays open); then the chat is shared with ${handover.title} and reopens there in a terminal.`
                  : ` The chat is shared with ${handover.title} and reopens there in a terminal.`)
              }
              onClick={() => post({ type: "handOver", chat, profile: handover.shareProfile })}
            >
              Continue on {handover.title}
            </button>
            ) : null}
            {goingOn ? (
              <IconButton
                icon={I.goOnAt}
                class="text-btn"
                pressed
                label={`Goes on at ${startText(goingOn.startAt, now)}`}
                title={`Goes on by itself at ${startText(goingOn.startAt, now)}, in the background, telling Claude that the limit has reset.${ending} If it went on before then, nothing happens.\n\nClick to cancel it${kept ? ": then it doesn't keep going either" : ""}.`}
                onClick={() => post({ type: "unqueue", id: goingOn.id })}
              >
                Goes on at {startText(goingOn.startAt, now)}
              </IconButton>
            ) : goOn ? (
              <IconButton
                icon={I.goOnAt}
                class="text-btn"
                label={`Go on at ${startText(goOn, now)}`}
                title={`At ${startText(goOn, now)}, a minute after the limit resets, the chat goes on in the background, telling Claude that the limit has reset.${ending} If it went on before then, nothing happens.\n\nThis happens once${host ? "" : ": to have it go on after later limits too, choose Keep going"}.`}
                onClick={() => post({ type: "queueContinue", chat })}
              >
                Go on at {startText(goOn, now)}
              </IconButton>
            ) : null}
            {goOn && !goingOn && !kept && !host ? (
              <IconButton
                icon={I.keepGoing}
                class="text-btn"
                label="Keep going"
                title={`Keep going until it's done: at ${startText(goOn, now)}, a minute after the limit resets, the chat goes on in the background, and again after each later limit that stops it, until a turn of it ends by itself.${ending}`}
                onClick={() => post({ type: "queueContinue", chat, keep: true })}
              >
                Keep going
              </IconButton>
            ) : null}
            {kept ? (
              <Tag
                icon={I.keepGoing}
                text={"Keeps going" + (kept.error ? " (gave up)" : kept.note ? " (can't go on now)" : "")}
                active={!kept.error}
                warning={!!kept.error || !!kept.note}
                title={keptTitle(kept)}
                onClick={() => post({ type: "keepGoing", chat, on: false })}
              />
            ) : null}
          </div>
        ) : null}

        {s.state === "waiting" && s.permission ? (
          <AskBox key={askKey(s.permission)} ask={s.permission} max={6} compact
            onAnswer={(decision, note, answers) => post({ type: "answerPermission", chat, decision, note, answers, shown: shownAsk(s.permission) })}
            onWholePlan={() => post({ type: "openPane", chat, tab: "chat" })} />
        ) : null}

        {showPeek ? <PeekPanel session={s} host={host} chat={chat} /> : null}

        {showAgents && agents ? <AgentTree tree={agents.tree} now={now} rowKey={rowKey} chat={chat} host={host} /> : null}
      </div>

      {
        <div class="row-actions">
          {/* the other way to open it than a click on its name: its window, or its tab */}
          <IconButton
            icon={paneFirst ? I.openWindow : I.openPane}
            label={paneFirst ? "Open its window" : "Open in a tab"}
            title={paneFirst ? openHint(s, host, reopenInCode) : "Open this chat in a tab: its conversation as it goes, a box to reply, and what it changed."}
            onClick={() => post(paneFirst ? { type: "openWindow", chat } : { type: "openPane", chat })}
          />
          {move ? (
            <IconButton
              icon={I.moveTo}
              label="Move to a Claude Code panel…"
              title="Go on with this chat in a Claude Code panel: Claude quits in its terminal (the terminal stays open) and the chat reopens in a Claude Code panel. Asks first; a chat that's working or waiting for you is stopped only once you say so."
              onClick={() => post({ type: "moveToClaudeCode", chat })}
            />
          ) : null}
          {s.starred ? null : (
            <IconButton
              icon={I.star}
              label="Star"
              title="Star this chat: once it isn't listed here any more, it stays under Recent chats → Starred, however old it is."
              onClick={() => post({ type: "star", chat, on: true })}
            />
          )}
          {canKeep ? (
            <IconButton
              icon={I.keepGoing}
              label="Keep going after usage limits"
              title="Keep going until it's done: when a usage limit stops this chat, it goes on by itself in the background a minute after the limit resets, in the permission mode it had, and again after each later one, until a turn of it ends by itself. Claude here quits first then (its terminal stays open)."
              onClick={() => post({ type: "keepGoing", chat, on: true })}
            />
          ) : null}
          {share ? (
            <IconButton
              icon={I.share}
              label="Continue on another account…"
              title={shareTitle(host)}
              onClick={() => post({ type: "share", chat })}
            />
          ) : null}
          {remove ? (
            <IconButton icon={I.delete} tone={T.delete} label="Delete this chat…" title={`Delete this chat…\n${deleteHint("chat")}`}
              onClick={() => post({ type: "delete", kind: "chat", chat })} />
          ) : null}
          {remove ? (
            <IconButton icon={I.hide} label="Hide this chat" title={`Hide this chat\n${hideHint("chats", host)}`}
              onClick={() => post({ type: "dismiss", chat })} />
          ) : null}
          {stop ? (
            canEndChat(s) ? (
              <IconButton
                icon={I.stop}
                label={hasTurn(s) ? "Interrupt or stop this chat…" : "Stop this chat…"}
                title={
                  s.entrypoint === "claude-vscode"
                    ? "Stop this chat. Asks first; its Claude Code panel shows it as interrupted and goes on with your next message."
                    : hasTurn(s)
                      ? "Interrupt or stop this chat. Asks first. Interrupting is like Ctrl+C or the stop button of a Claude Code panel (where it runs in a terminal of this window, or in tmux): its subagents stop too and the chat stays open. Stopping cuts off the current step, Claude quits and its terminal stays open."
                      : "Stop this chat. Asks first; Claude quits and its terminal stays open. The chat is kept and shows under Recent chats."
                }
                onClick={() => post({ type: "stop", chat })}
              />
            ) : (
              <IconButton
                icon={I.stop}
                label="Stop this background chat…"
                title="Stop this background chat. Asks first; the conversation is kept and claude attach resumes it."
                onClick={() => post({ type: "stop", chat })}
              />
            )
          ) : null}
        </div>
      }
    </div>
  );
}
