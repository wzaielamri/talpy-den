import { summaryText, tooltipLines } from "../../src/shared/model";
import type { Counts, Group, HostState, Overall } from "../../src/shared/types";
import { editorTab, post } from "../env";
import { useViewVisible } from "../util/petStage";
import { useStore } from "../util/store";
import { setFocus, setTab, TAB_ORDER, type Tab, uiState } from "../util/ui";
import { I, Icon, type IconName } from "../util/icons";
import { IconButton } from "./IconButton";
import { TalpyIcon } from "./TalpyIcon";

const TABS: Record<Tab, [string, IconName]> = {
  chats: ["Talpy Den", I.chats],
  projects: ["Projects", I.project],
  perms: ["Permissions", I.permissions],
  week: ["Recap", I.recap],
};

// The icon and the summary. In the sidebar the view's title bar has the
// buttons; opened as an editor tab there's no title bar, so they're here.
// With the big Talpy shown the summary is left out: its headline says it.
export function Header(props: {
  overall: Overall;
  counts: Counts;
  groups: Group[];
  hosts: HostState[];
  answered: boolean; // this computer's status came, or a host's
  unavailable: boolean; // no status, and the reason is known
  heroShown: boolean;
}) {
  const visible = useViewVisible();
  const { tab, focus } = useStore(uiState);
  const { overall, counts, groups, hosts } = props;
  // "No chats running" only once something answered; until then the list
  // says it's looking
  const summary = props.answered ? summaryText(counts) : props.unavailable ? "Status unavailable" : "";

  return (
    <header class="header">
      <TalpyIcon state={overall} moving={visible} />
      {/* The app's name is the first tab: your chats now. The others: your projects (ProjectsView.tsx), the
          permissions you gave (PermsView.tsx), your last 7 days with Claude (WeekView.tsx) */}
      {/* (in a narrow sidebar the tabs not shown are icons, so the Focus button stays in sight) */}
      <div class="tabs" role="tablist">
        {TAB_ORDER.map((t) => [t, ...TABS[t]] as const).map(([t, name, icon]) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} aria-label={name} class={"tab-btn" + (tab === t ? " on" : "")}
            title={t === "chats" ? tooltipLines(groups, counts, hosts).join("\n") : name}
            onClick={() => setTab(t)}>
            <Icon name={icon} class="tab-icon" />
            <span class="tab-name">{name}</span>
          </button>
        ))}
      </div>
      <span class="summary" title={tooltipLines(groups, counts, hosts).join("\n")}>
        {props.heroShown && tab === "chats" ? "" : summary}
      </span>
      {tab === "chats" ? (
        <IconButton
          icon={I.focus}
          label={focus ? "Show everything" : "Focus"}
          title={focus ? "Show everything\nBack to every account, chat, pet and usage bar."
            : "Focus\nOnly what needs you, the chats that finished a turn you haven't looked at yet, and one line for each chat at work."}
          pressed={focus}
          onClick={() => setFocus(!focus)}
        />
      ) : null}
      {editorTab ? (
        <div class="header-actions">
          <IconButton
            icon={I.search}
            label="Find a chat…"
            title={"Find a chat…\nEvery chat with all the words you type in its name, its folder or your prompts, here and on the SSH hosts shown."}
            onClick={() => post({ type: "findChat" })}
          />
          <IconButton
            icon={I.host}
            label="SSH hosts…"
            title={
              hosts.length
                ? `SSH hosts…\nShowing Claude on ${hosts.map((h) => h.name).join(", ")}. Click to pick hosts from ~/.ssh/config.`
                : "SSH hosts…\nShow the Claude chats of your SSH hosts (from ~/.ssh/config) here too."
            }
            class={hosts.length ? "with-count" : ""}
            onClick={() => post({ type: "pickHosts" })}
          >
            {hosts.length ? <span class="count">{hosts.length}</span> : null}
          </IconButton>
          <IconButton icon={I.refresh} label="Refresh" onClick={() => post({ type: "refresh" })} />
          <IconButton icon={I.settings} label="Settings" title={"Settings\nTalpy Den's settings, in VS Code's Settings editor."} onClick={() => post({ type: "openSettings" })} />
        </div>
      ) : null}
    </header>
  );
}
