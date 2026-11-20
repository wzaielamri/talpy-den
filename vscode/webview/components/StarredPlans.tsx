import { pagedTitle, pageSizeOf } from "../../../core/src/shared/model";
import type { Group } from "../../../core/src/shared/types";
import { groupKeyOf } from "../util/chat";
import { I, Icon } from "../util/icons";
import { useStore } from "../util/store";
import { pages, pagesShown, showMore, toggleStarred, uiState } from "../util/ui";
import { useView } from "./context";
import { MoreButton } from "./MoreButton";
import { PlanLine } from "./PlanLine";

// The plans of this account you starred (☆ next to a plan), however old:
// folded by default, flat, newest first, a page at a time. Every plan is in
// its project, in the Projects tab.
export function StarredPlans({ group }: { group: Group }) {
  const view = useView();
  const ui = useStore(uiState);
  const shownPages = useStore(pages);
  const starred = group.starredPlans ?? [];
  if (!starred.length) return null;
  const key = `${groupKeyOf(group)}|plans`;
  const open = !!ui.starred[key];
  const size = pageSizeOf(view.settings.recentChats);
  const shown = Math.min(starred.length, size * pagesShown(shownPages, key));
  return (
    <div class="recent plans">
      <button
        type="button"
        class="recent-toggle small"
        aria-expanded={open}
        title="The plans of this account you starred (☆ next to a plan), newest first, however old they are. Click one to read it; carry it out in a new chat, go back to the chat that made it, or share it with your other accounts. Click a plan's ★ to unstar it. Every plan is in its project, in the Projects tab."
        onClick={() => toggleStarred(key)}
      >
        <Icon name={I.folded} class={open ? "open" : ""} />
        {pagedTitle("★ Starred plans", shown, starred.length)}
      </button>
      {open ? (
        <>
          <ul class="recent-list">
            {starred.slice(0, shown).map((p) => <PlanLine key={p.key} plan={p} group={group} />)}
          </ul>
          <MoreButton shown={shown} count={starred.length} size={size} onClick={() => showMore(key)} />
        </>
      ) : null}
    </div>
  );
}
