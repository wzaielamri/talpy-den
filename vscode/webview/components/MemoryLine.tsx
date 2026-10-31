import { ago, folderIn } from "../../src/shared/model";
import type { Group, Memory } from "../../src/shared/types";
import { post } from "../env";
import { deleteHint, hideHint } from "../util/chat";
import { I, Icon, T, memoryIcon } from "../util/icons";
import { useWoken } from "../util/lazy";
import { useView } from "./context";
import { Elided } from "./Elided";
import { IconButton } from "./IconButton";
import { Tag } from "./Tag";

// One of Claude's memories (<config>/projects/<folder>/memory, a project's),
// or an account's CLAUDE.md (type "account": your instructions for every
// chat on it, its own line under the account): it opens in the Markdown
// preview, the edit button opens its file; a memory can be deleted or
// hidden, CLAUDE.md not. An SSH host's opens only in a window connected to
// that host. In a project (project: its folder) the folder says only the
// part below the project's, and accountTag the account it's on when the
// project is on several.
export function MemoryLine({ memory: m, group, project, accountTag }: { memory: Memory; group: Group; project?: string; accountTag?: string }) {
  const view = useView();
  const [woken, wake] = useWoken(); // (its buttons: made the first time they show)
  const host = group.host;
  const elsewhere = !!host && host !== view.hosts.find((h) => h.current)?.name;
  const account = m.type === "account";
  const ref = (edit?: boolean) => ({ type: "openMemory" as const, groupId: group.id, memory: m.key, ...(host ? { host } : {}), ...(edit ? { edit } : {}) });
  // (in a project: only the part of its folder below the project's)
  const folder = account ? "every folder" : project !== undefined ? folderIn(m.folder, project, m.folderShort) : m.folderShort || m.folder;
  return (
    <li class={"recent-item" + (elsewhere ? " unavailable" : "")} {...wake}>
      <Icon name={memoryIcon(m.type)} class="line-icon" />
      <button
        type="button"
        class="link recent-name"
        aria-disabled={elsewhere}
        title={
          `${m.name}\n` +
          (m.description ? `${m.description}\n` : "") +
          (m.type ? `\nKind: ${m.type}` : "") +
          (m.folder ? `\nFolder: ${host ? `${host}:` : ""}${m.folder}${m.folderGone ? " (not there any more)" : ""}` : "") +
          (elsewhere ? `\n\nOpen it from a VS Code window connected to ${host}.` : "\n\nClick to read it.")
        }
        onClick={() => !elsewhere && post(ref())}
      >
        {m.description || m.name}
      </button>
      {accountTag ? <Tag text={accountTag} /> : null}
      {folder ? (
        <Elided text={folder} class="recent-folder small muted" title={m.folderGone ? `${m.folder} (not there any more)` : m.folder} />
      ) : (
        <span class="recent-folder" title={m.folder || undefined} />
      )}
      <span class="recent-ago small muted nowrap">{ago(view.now - m.updatedAt)}</span>
      {woken ? (
        <div class="row-actions">
          {elsewhere ? null : account ? (
            <IconButton
              icon={I.edit}
              label="Edit your instructions"
              title="Edit your instructions: its CLAUDE.md opens in an editor tab. Claude reads it in every new chat on this account."
              onClick={() => post(ref(true))}
            />
          ) : (
            <IconButton
              icon={I.edit}
              label="Edit this memory"
              title="Edit this memory: its file opens in an editor tab. What you change there is what Claude remembers; it reads it in new chats in that folder."
              onClick={() => post(ref(true))}
            />
          )}
          {account ? null : (
            <IconButton icon={I.delete} tone={T.delete} label="Delete this memory…" title={`Delete this memory…\n${deleteHint("memory")}`}
              onClick={() => post({ type: "delete", kind: "memory", groupId: group.id, ...(host ? { host } : {}), id: m.key })} />
          )}
          {account ? null : (
            <IconButton icon={I.hide} label="Hide this memory" title={`Hide this memory\n${hideHint("memories", host)}`}
              onClick={() => post({ type: "hide", kind: "memories", groupId: group.id, ...(host ? { host } : {}), id: m.key })} />
          )}
        </div>
      ) : null}
    </li>
  );
}
