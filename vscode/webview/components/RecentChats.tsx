import { useEffect } from "preact/hooks";
import { pagedTitle, pageSizeOf, recentPage } from "../../src/shared/model";
import type { Group, ReopenIn } from "../../src/shared/types";
import { post } from "../env";
import { groupKeyOf } from "../util/chat";
import { I, Icon, type IconName } from "../util/icons";
import { useStore } from "../util/store";
import { askRecentMore, pages, pagesShown, recentMore, showMore, toggleRecent, toggleStarred, uiState } from "../util/ui";
import { useView } from "./context";
import { MoreButton } from "./MoreButton";
import { RecentLine, reopenOf, type Reopen } from "./RecentLine";

// The account's latest other chats, to pick one up again (Recent chats),
// and the ones you starred, however old (★ Starred chats): each folded by
// default (the running chats come first), flat, newest first, a page at a
// time (as many as the Recent chats setting; "Show N more" the next page,
// folded again the first one). The status lists a page more recent chats
// than show, and how many there are; past those the extension runs a check
// that lists more, once. A switch at the top says where they reopen: in a
// terminal, or in a Claude Code panel (kept in talpyDen.reopenIn); a half is
// greyed out where it can't work.
export function RecentChats({ group }: { group: Group }) {
  const view = useView();
  const ui = useStore(uiState);
  const shownPages = useStore(pages);
  const more = useStore(recentMore);
  const key = groupKeyOf(group);
  const size = pageSizeOf(view.settings.recentChats);
  const open = !!ui.recent[key];
  const recent = recentPage(group, open ? more[key] : null, pagesShown(shownPages, key + "|recent"), size);
  // (the next page: asked for as the one before it shows)
  useEffect(() => {
    if (open && recent.fetch) askRecentMore(group, recent.fetch);
  }, [open, recent.fetch, key]);
  const starred = group.starred ?? [];
  const starredOpen = !!ui.starred[`${key}|chats`];
  const starredShown = Math.min(starred.length, size * pagesShown(shownPages, key + "|chats"));
  if (!recent.count && !starred.length) return null;
  const how = open || starredOpen ? reopenOf(view, group) : null;
  const paneFirst = view.settings.clickOpensPane !== false;

  return (
    <>
      {recent.count ? (
        <div class="recent">
          <button
            type="button"
            class="recent-toggle small"
            aria-expanded={open}
            title={(paneFirst
              ? "This account's latest chats that aren't listed above, newest first. Click one to open it in a tab; its reopen button (on hover) reopens it in a terminal or in a Claude Code panel (the switch at the top of the list)."
              : "This account's latest chats that aren't listed above, newest first. Click one to reopen it, in a terminal or in a Claude Code panel (the switch at the top of the list).") +
              " Show more lists more of them; folded again, it lists the first ones again. Every chat of a project is in the Projects tab."}
            onClick={() => toggleRecent(key)}
          >
            <Icon name={I.folded} class={open ? "open" : ""} />
            {pagedTitle("Recent chats", recent.shown, recent.count)}
          </button>
          {open && how ? (
            <>
              <OpenIn how={how} />
              <ul class="recent-list">
                {recent.all.slice(0, recent.shown).map((c) => <RecentLine key={c.key} chat={c} group={group} how={how} />)}
              </ul>
              <MoreButton shown={recent.shown} count={recent.count} size={size} onClick={() => showMore(key + "|recent")} />
            </>
          ) : null}
        </div>
      ) : null}
      {starred.length ? (
        <div class="recent">
          <button
            type="button"
            class="recent-toggle small"
            aria-expanded={starredOpen}
            title="The chats of this account you starred (☆ next to a chat), newest first, however old they are; not the ones listed above. Click a chat's ★ to unstar it."
            onClick={() => toggleStarred(`${key}|chats`)}
          >
            <Icon name={I.folded} class={starredOpen ? "open" : ""} />
            {pagedTitle("★ Starred chats", starredShown, starred.length)}
          </button>
          {starredOpen && how ? (
            <>
              {/* (the switch here too while Recent chats is folded) */}
              {open ? null : <OpenIn how={how} />}
              <ul class="recent-list">
                {starred.slice(0, starredShown).map((c) => <RecentLine key={c.key} chat={c} group={group} how={how} />)}
              </ul>
              <MoreButton shown={starredShown} count={starred.length} size={size} onClick={() => showMore(`${key}|chats`)} />
            </>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

// Where an account's chats reopen: Terminal | Claude Code panel
function OpenIn({ how }: { how: Reopen }) {
  const half = (where: ReopenIn, icon: IconName, text: string, available: boolean, checked: boolean, title: string) => (
    <button
      type="button"
      class={"tag with-icon open-in-half" + (available ? " clickable" : " unavailable")}
      aria-pressed={checked}
      aria-disabled={!available}
      title={title}
      onClick={() => available && post({ type: "setReopenIn", where })}
    >
      <Icon name={icon} />
      {text}
    </button>
  );
  const { cliHere, codeHere, inCode, terminalHint, codeHint } = how;
  return (
    <>
      <div class="open-in small" role="group" aria-label="Where recent chats reopen">
        <span class="muted">Open in:</span>
        {half("terminal", I.terminal, "Terminal", cliHere, cliHere && !inCode, (cliHere ? "Reopen chats in a terminal\n" : "No claude command\n") + terminalHint)}
        {half("claudeCode", I.openPane, "Claude Code panel", codeHere, inCode, (codeHere ? "Reopen chats in a Claude Code panel\n" : "Not here\n") + codeHint)}
      </div>
      {!cliHere && !codeHere ? <div class="open-in-why small muted">{`${terminalHint} ${codeHint}`}</div> : null}
    </>
  );
}
