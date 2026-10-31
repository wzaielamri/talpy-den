import { useRef } from "preact/hooks";
import { formatTokens, planUsageText, stateText, tokensText } from "../../src/shared/model";
import type { Group, TokenTotals, Tokens } from "../../src/shared/types";
import { post } from "../env";
import { fiveHourOf, groupKeyOf, sharedRef, stageChats } from "../util/chat";
import { I, Icon } from "../util/icons";
import { useStore } from "../util/store";
import { toggleStats, uiState } from "../util/ui";
import { AccountStage } from "./AccountStage";
import { useView } from "./context";
import { IconButton } from "./IconButton";
import { MemoryLine } from "./MemoryLine";
import { QueuedTasks } from "./QueuedTasks";
import { RecentChats } from "./RecentChats";
import { SessionRow, stateClass } from "./SessionRow";
import { StarredPlans } from "./StarredPlans";
import { useFlip } from "../util/motion";
import { StatsPanel } from "./StatsPanel";
import { Tag } from "./Tag";
import { UsageBar } from "./UsageBar";

function modelName(model: string): string {
  return model.replace(/^claude-/, "");
}

function tokenTitle(t: Tokens): string {
  const fmt = (b: TokenTotals) =>
    `input ${formatTokens(b.input)} · output ${formatTokens(b.output)} · cache read ${formatTokens(b.cacheRead)} · cache write ${formatTokens(b.cacheWrite)} · ${b.messages} replies`;
  const models = (t.models ?? []).map((m) => `${modelName(m.model)}: ${formatTokens(m.total)}`);
  return (
    "Tokens (this machine's transcripts only)\n" +
    `Today: ${fmt(t.today)}\nLast 7 days: ${fmt(t.week)}` +
    (models.length ? `\nBy model (7 days): ${models.join(", ")}` : "") +
    (t.week.shared > 0
      ? `\nIncludes ${formatTokens(t.today.shared)} today (${formatTokens(t.week.shared)} in 7 days) from chats shared with another profile. A transcript doesn't say which account paid, so shared chats count on both.`
      : "")
  );
}

function TokenLine({ tokens }: { tokens: Tokens }) {
  return <span class="token-line">{tokensText(tokens)}</span>;
}

// One Claude account: its pets, plan limits, token totals, chats (from every
// config folder logged into it), then your shortlists: Recent chats, ★ Starred
// chats and ★ Starred plans, and its CLAUDE.md. Its plans and memories are
// in their projects (the Projects tab). With group.host set, the account is
// on that SSH host and its actions run there.
// accounts: how many its machine has (with two or more, the default one is marked)
export function GroupSection({ group: g, accounts = 1 }: { group: Group; accounts?: number }) {
  const rowsRef = useRef<HTMLDivElement>(null);
  useFlip(rowsRef); // (a chat that moves slides there)
  const view = useView();
  const now = view.now;
  const host = g.host;
  const key = groupKeyOf(g);
  const settings = view.settings;
  const multiProfile = g.profiles.length > 1;
  const limits = g.limits;
  const usageAge = limits ? planUsageText(limits, g.limitsFrom ?? "", now, g.usageFetchAt) : ""; // (limitsFrom: the newer numbers of the account's copy there, shareUsage)
  const tokens = settings.showTokens ? g.tokens : null;
  const ui = useStore(uiState);
  const stats = tokens && g.stats ? g.stats : null;
  const statsOpen = !!stats && !!ui.stats[key];

  return (
    <section class="group" aria-label={(host ? host + ": " : "") + g.title}>
      <div class="group-head">
        <h3 class="group-title" title={(host ? host + ": " : "") + g.title}>
          {host ? <span class="group-host muted">{host}: </span> : null}
          {g.title}
        </h3>
        {g.defaultHere && accounts > 1 ? (
          <Tag
            text="Default"
            title={
              (host
                ? `The default account on ${host}: listed first; Claude Code there (its VS Code server) and plain claude there run on it.`
                : "The default account: listed first, its usage is in the status bar, and VS Code's Claude and plain claude run on it.") +
              " Change it with Claude Accounts → Make Default, or the account item in the status bar."
            }
          />
        ) : null}
        <IconButton
          icon={I.newChat}
          label={`New chat on ${g.title}`}
          title={
            (host
              ? `New chat on ${g.title}: opens a terminal with a new Claude chat on this account on ${host} (over ssh), in the folder you pick.`
              : `New chat on ${g.title}: opens a terminal with a new Claude chat on this account, in the folder you pick.`) +
            " Type a task first and the chat starts with it, also in the background."
          }
          onClick={() => post(host ? { type: "newChat", groupId: g.id, host } : { type: "newChat", groupId: g.id })}
        />
        <span class="spacer" />
        {multiProfile ? <span class="small muted nowrap">{(g.profiles ?? []).join(" + ")}</span> : null}
      </div>

      {settings.showPet ? (
        <AccountStage
          stageKey={key}
          input={{ chats: stageChats(g), maxPets: settings.showPet ? settings.chatPets : 0, fiveHour: fiveHourOf(g) }}
        />
      ) : null}

      {/* Not logged in to an account (a new one, or logged out): Claude's own login, in a terminal */}
      {g.loggedOut ? (
        <div class="logged-out small">
          <span class="muted">Not logged in.</span>
          {g.loginCommand ? (
            <>
              {" "}
              <button
                type="button"
                class="link"
                title={
                  host
                    ? `Opens a terminal with Claude's own login on ${host} (over ssh): open the address it shows in your browser, sign in, and paste the code you get back.`
                    : "Opens a terminal with Claude's own login (claude auth login): sign in in your browser with the account for this folder. The extension never sees the login."
                }
                onClick={() => post(host ? { type: "login", groupId: g.id, host } : { type: "login", groupId: g.id })}
              >
                Log in…
              </button>
            </>
          ) : null}
        </div>
      ) : null}

      {/* Plan limits (from the status line); not where they show elsewhere (shareUsage) */}
      {g.limitsHidden || g.loggedOut ? null : limits && limits.windows.length ? (
        <>
          <div class="usage">
            {limits.windows.map((w) => (
              <UsageBar key={w.key} window={w} now={now} />
            ))}
          </div>
          {usageAge ? <div class="usage-age small muted">{usageAge}</div> : null}
        </>
      ) : (
        <div class="no-usage small muted">
          <span title="Plan limits come from Claude Code's status line. They update whenever a chat of this account gets a reply.">
            No plan usage yet: shows after this account's next reply.
          </span>
          {!host ? (
            <>
              {" "}
              <button
                type="button"
                class="link"
                title="Adds the snippet that reports plan usage to Claude Code's status line"
                onClick={() => post({ type: "setupUsageBars" })}
              >
                Set up…
              </button>
            </>
          ) : null}
        </div>
      )}

      {/* Token totals (from local transcripts) */}
      {tokens ? (
        stats ? (
          <button
            type="button"
            class="tokens small stats-toggle"
            aria-expanded={statsOpen}
            title={`${tokenTitle(tokens)}\n\nClick to ${statsOpen ? "hide" : "show"} the last ${stats.days.length} days.`}
            onClick={() => toggleStats(key)}
          >
            <Icon name={I.folded} class={statsOpen ? "open" : ""} />
            <TokenLine tokens={tokens} />
          </button>
        ) : (
          <div class="tokens small" title={tokenTitle(tokens)}>
            <TokenLine tokens={tokens} />
          </div>
        )
      ) : null}
      {statsOpen && stats ? <StatsPanel stats={stats} /> : null}

      <div class="sessions" ref={rowsRef}>
        {g.sessions.map((s) => (
          <SessionRow key={s.key} session={s} group={g} host={host} showProfile={multiProfile} />
        ))}
        {g.sessions.length === 0 ? <div class="no-sessions muted">No running chats</div> : null}
      </div>

      <QueuedTasks group={g} />

      {/* Chats shared with this account that are in use on another one:
          they're listed there, once, so here only a line points to them */}
      {(g.sharedHere ?? []).map((p) => (
        <div key={p.key} class="shared-line">
          <span class={`shared-glyph ${stateClass(p.state, p.reason)}`} aria-hidden="true">
            <Icon name={I.share} />
          </span>
          <button
            type="button"
            class="link shared-name"
            title={
              (p.copy
                ? `Shared chat, continued on ${p.profile} as a copy.\nNew messages are only in that copy. Click to go to it.`
                : p.state === "done"
                  ? `Shared chat, last used on ${p.profile}.\nIt's listed once, under the account it's used on. Click to go to it.`
                  : `Shared chat, open on ${p.profile}.\nIt's listed once, under the account it's used on. Click to go to it.`) +
              (p.stoppedHere ? "\nIts background chat on this account was stopped." : "")
            }
            onClick={() => post({ type: "open", chat: sharedRef(p, host) })}
          >
            {p.name}
          </button>
          <span class="shared-where small muted">
            {p.copy ? `copy on ${p.profile}` : `on ${p.profile}`} · {stateText(p, now)}
          </span>
        </div>
      ))}

      <RecentChats group={g} />
      <StarredPlans group={g} />
      {/* its CLAUDE.md: your instructions for every chat on it (read it, or edit it) */}
      {g.instructions?.length ? (
        <ul class="recent-list instructions">
          {g.instructions.map((m) => <MemoryLine key={m.key} memory={m} group={g} />)}
        </ul>
      ) : null}
    </section>
  );
}
