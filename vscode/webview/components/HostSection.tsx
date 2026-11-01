import { containerOf, duration, hiddenCount, hostLabel } from "../../src/shared/model";
import type { Group, HostState } from "../../src/shared/types";
import { post } from "../env";
import { groupKeyOf } from "../util/chat";
import { I, Icon } from "../util/icons";
import { useView } from "./context";
import { GroupSection } from "./GroupSection";
import { IconButton } from "./IconButton";
import { Tag } from "./Tag";

// An SSH host or a container you picked: its accounts, chats and recent
// chats. Its last good answer is kept when a check fails: shown dimmed, under
// the error. A stopped container says so, with Start (it isn't checked until
// Start or Refresh).
export function HostSection({ host: h, groups }: { host: HostState; groups: Group[] }) {
  const view = useView();
  const now = view.now;
  const result = h.result;
  const stale = !h.ok && result !== null;
  const container = containerOf(h.name);
  const name = hostLabel(h.name);
  const stopped = !!h.stopped && !h.loading;
  // the machine's own name, when the ssh alias differs; a container's engine and image (· on its host)
  const machine = container ? h.detail ?? container.engine : result?.host && result.host.split(".")[0] !== h.name ? result.host : "";
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
    <section class={"host" + (stale ? " stale" : "")} aria-label={container ? `Container ${name}` : `SSH host ${h.name}`}>
      <div class="host-head">
        <Icon name={container ? I.container : I.host} class="host-icon" />
        <h2 class="host-name" title={name + (machine ? ` (${machine})` : "")}>
          {container ? container.name : h.name}
        </h2>
        {machine ? <span class="host-machine small muted">{machine}</span> : null}
        {h.current ? (
          <Tag text="this window" title={container ? "The container this VS Code window is connected to" : "The host this VS Code window is connected to"} />
        ) : null}
        <span class="spacer" />
        {h.loading ? <span class="spinner" role="status" aria-label={`Checking ${name}…`} /> : null}
        {updated ? <span class="host-updated small muted">{updated}</span> : null}
        {hidden > 0 ? (
          <IconButton
            icon={I.showHidden}
            label="Show hidden ones again…"
            title={`Show hidden ones again…\nThe chats, plans or memories of ${name} you hid (${hidden})`}
            onClick={() => post({ type: "showHidden", host: h.name })}
          />
        ) : null}
        {h.loggedIn ? (
          <IconButton
            icon={I.signOut}
            label={`Disconnect from ${container?.host || h.name}`}
            title={`Disconnect from ${container?.host || h.name}\nCloses the connection you logged in with. To check ${name} again, log in again.`}
            onClick={() => post({ type: "disconnectHost", host: h.name })}
          />
        ) : null}
        <IconButton
          icon={I.refresh}
          label={`Refresh ${name}`}
          title={`Refresh ${name}` + (stopped ? "\nNot checked while it's stopped: Refresh checks it once." : updated ? `\n${updated[0].toUpperCase() + updated.slice(1)}.` : "")}
          onClick={() => post({ type: "refresh", host: h.name })}
        />
        {!h.current ? (
          <IconButton
            icon={I.hide}
            label={`Stop showing ${name}`}
            title={`Stop showing ${name}\nPick it again with the hosts button.`}
            onClick={() => post({ type: "hideHost", host: h.name })}
          />
        ) : null}
      </div>

      {stopped ? (
        <div class="msg host-stopped">
          {`${name} is stopped.`}
          {stale && h.updatedAt ? ` Showing what it said ${duration(now - h.updatedAt)} ago.` : ""}{" "}
          <button
            type="button"
            class="link"
            title={`Start ${name}\nStarts the container (${container?.engine ?? "docker"} start), then shows its chats.`}
            onClick={() => post({ type: "startContainer", host: h.name })}
          >
            <Icon name={I.startNow} /> Start
          </button>
        </div>
      ) : h.error ? (
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
                title={`Opens a terminal where ssh asks for ${container?.host || h.name}'s password (or passphrase, one-time code, new host key): Talpy Den never sees it. The checks then go through the connection that login opened, until 30 minutes after their last check, until you log out, or until you disconnect.`}
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
        <div class="muted host-empty">{container ? "No Claude Code config in this container (~/.claude, ~/.claude-*)" : "No Claude Code config on this host (~/.claude, ~/.claude-*)"}</div>
      ) : null}
    </section>
  );
}
