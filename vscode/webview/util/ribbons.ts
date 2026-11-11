// The bookmarked messages' ribbons in Talpy Chat (chat.tsx): in place of the dot before Claude's reply
// and the › before yours, in the same colour, all from one <style> for the list. The gutter itself is
// painted through the ribbon's shape (a mask, styles.css --pane-ribbon: its dot or › is the ribbon's
// colour, so it's gone in it), so nothing moves and no box is added: bookmarking lays out nothing
// again, it's only drawn again. One rule for them all (each row's gutter is matched against it once,
// as rows are drawn), made again only when the bookmarks change; nothing is added to the rows.

import type { Bookmark } from "../../src/shared/pane";

export function ribbonCss(list: readonly Bookmark[]): string {
  if (!list.length) return "";
  const keys = list.map((m) => `[data-key="${CSS.escape(m.key)}"]`).join(",");
  return `.pane-list>:is(${keys})>.pane-gutter{background:var(--pane-mark,var(--pane-claude));`
    + "-webkit-mask:var(--pane-ribbon) center/.7em .9em no-repeat;mask:var(--pane-ribbon) center/.7em .9em no-repeat}";
}
