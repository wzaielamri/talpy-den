import { duration, hiddenCount } from "../../src/shared/model";
import type { Group, HostState } from "../../src/shared/types";
import { post } from "../env";
import { groupKeyOf } from "../util/chat";
import { I, Icon } from "../util/icons";
import { useView } from "./context";
import { GroupSection } from "./GroupSection";
import { IconButton } from "./IconButton";
import { Tag } from "./Tag";

// An SSH host you picked: its accounts, chats and recent chats. Its last good
// answer is kept when a check fails: shown dimmed, under the error.
export function HostSection({ host: h, groups }: { host: HostState; groups: Group[] }) {
  const view = useView();
  const now = view.now;
  const result = h.result;
  const stale = !h.ok && result !== null;
  // the machine's own name, when the ssh alias differs
  const machine = result?.host && result.host.split(".")[0] !== h.name ? result.host : "";
  const updated =
    h.loading && !result
      ? "connecting…"
      : !h.updatedAt
        ? ""
        : now - h.updatedAt < 60000
          ? "updated just now"
          : `updated ${duration(now - h.updatedAt)} ago`;
  const hidden = (["chats", "plans", "memories", "projects"] as const).reduce((n, kind) => n + hiddenCount(result, kind), 0);

  return (
    <section class={"host" + (stale ? " stale" : "")} aria-label={`SSH host ${h.name}`}>
      <div class="host-head">
        <Icon name={I.host} class="host-icon" />
        <h2 class="host-name" title={h.name + (machine ? ` (${machine})` : "")}>
          {h.name}
        </h2>
        {machine ? <span class="host-machine small muted">{machine}</span> : null}
        {h.current ? (
          <Tag text="this window" title="The host this VS Code window is connected to" />
        ) : null}
        <span class="spacer" />
        {h.loading ? <span class="spinner" role="status" aria-label={`Checking ${h.name}…`} /> : null}
        {updated ? <span class="host-updated small muted">{updated}</span> : null}
        {hidden > 0 ? (
          <IconButton
            icon={I.showHidden}
            label="Show hidden ones again…"
            title={`Show hidden ones again: the chats, plans or memories of ${h.name} you hid (${hidden})`}
            onClick={() => post({ type: "showHidden", host: h.name })}
          />
        ) : null}
        {h.loggedIn ? (
          <IconButton
            icon={I.signOut}
            label={`Disconnect from ${h.name}`}
            title={`Disconnect from ${h.name}: closes the connection you logged in with. To check ${h.name} again, log in again.`}
            onClick={() => post({ type: "disconnectHost", host: h.name })}
          />
        ) : null}
        <IconButton
          icon={I.refresh}
          label={`Refresh ${h.name}`}
          title={`Refresh ${h.name}` + (updated ? ` (${updated})` : "")}
          onClick={() => post({ type: "refresh", host: h.name })}
        />
        {!h.current ? (
          <IconButton
            icon={I.hide}
            label={`Stop showing ${h.name}`}
            title={`Stop showing ${h.name}. Pick it again with the SSH hosts button.`}
            onClick={() => post({ type: "hideHost", host: h.name })}
          />
        ) : null}
      </div>

      {h.error ? (
        <div class="msg error">
          {stale && h.updatedAt
            ? `${h.error}${/[.!?]$/.test(h.error) ? "" : "."} Showing what it said ${duration(now - h.updatedAt)} ago.`
            : h.error}
          {h.login ? (
            <>
              {" "}
              <button
                type="button"
                class="link"
                title={`Opens a terminal where ssh asks for ${h.name}'s password (or passphrase, one-time code, new host key): the extension never sees it. The checks then go through the connection that login opened, until 30 minutes after their last check, until you log out, or until you disconnect.`}
                onClick={() => post({ type: "loginHost", host: h.name })}
              >
                Log in…
              </button>
            </>
          ) : null}
        </div>
      ) : null}

      <div class="host-groups">
        {groups.map((g) => (
          <GroupSection key={groupKeyOf(g)} group={g} accounts={groups.length} />
        ))}
      </div>

      {h.ok && result && groups.length === 0 ? (
        <div class="muted host-empty">No Claude Code config on this host (~/.claude, ~/.claude-*)</div>
      ) : null}
    </section>
  );
}
