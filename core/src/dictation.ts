// Dictation Models…: what writes dictated replies down (dictate.py --status),
// dictation set up from here (faster-whisper in its own Python environment in
// ~/.local/share/talpy-den/whisper, no sudo), and the speech models to
// download, delete or use: one choice for the extension and the Plasma widget.

import type { Backend } from "./agents/claudeCode/backend";
import type { HostServices, PickItem } from "./host";
import { noLinks } from "./notify";

type Model = { name: string; mb: number; note: string; installed: boolean; deletable: boolean; used: boolean };
type Item = PickItem & { run?: string[]; busy?: string; model?: Model; ask?: string };

export async function dictationModels(host: HostServices, backend: Backend): Promise<void> {
  if (host.environment.web) {
    void host.message("info", "Dictating works in VS Code on your computer, not in a browser");
    return;
  }
  const st = await backend.dictate(["--status"]);
  if (!Array.isArray(st.models)) {
    void host.message("error", noLinks(`Talpy Den: dictation can't be asked now (${String(st.message ?? "no answer")})`));
    return;
  }
  const missing = (Array.isArray(st.missing) ? st.missing : []).join(" and ");
  if (!st.engine && !st.canSetup) {
    void host.message("warning", noLinks(`To dictate, install ${missing}.`));
    return;
  }
  const items: Item[] = [];
  let title: string;
  if (!st.engine) {
    title = "Dictation isn't set up";
    items.push({
      label: "$(cloud-download) Set up dictation",
      description: `about ${Number(st.setupMb) || 612} MB`,
      detail: "Installs faster-whisper, speech to text that runs on this computer, from pypi.org into its own Python environment, and downloads the base speech model from huggingface.co, all in ~/.local/share/talpy-den/whisper; no sudo needed. What you say never leaves the computer.",
      run: ["--setup"],
      busy: "Setting up dictation (a few minutes)…",
    });
  } else {
    const by = st.engine === "whisper.cpp" ? `whisper.cpp (${String(st.tool)})` : "faster-whisper";
    title = `Dictation: ${by}, ${st.modelName ? (st.chosen === "auto" ? `the ${st.modelName} model (the best one downloaded)` : `the ${st.modelName} model`) : "no speech model yet"}`;
    for (const m of st.models as Model[])
      items.push({
        label: `${m.used ? "$(check) " : ""}${m.name}`,
        description: `${m.mb} MB · ${m.used ? "used" : m.installed ? "downloaded" : "not downloaded"}`,
        detail: m.note,
        model: m,
      });
    if (st.chosen !== "auto" && st.modelName)
      items.push({ label: "Use the best one downloaded", detail: "The best model downloaded is used, whichever that is", run: ["--use-model", "auto"] });
    if (st.setUp)
      items.push({
        label: "$(trash) Remove faster-whisper…",
        detail: "Deletes faster-whisper's environment and its speech models; dictating needs setting up again then",
        run: ["--remove-setup"],
        ask: "Delete faster-whisper and its speech models? Dictating needs setting up again then.",
      });
  }
  if (!st.recorder && missing) title += ` · to record, install ${missing}`;
  const pick = await host.pick(items, { title, placeHolder: "A speech model, to download, use or delete it" });
  if (!pick) return;
  const action = pick.model ? await modelAction(host, pick.model) : pick;
  if (!action?.run) return;
  if (action.ask && (await host.message("warning", action.ask, { modal: true }, "Delete")) !== "Delete") return;
  const r = action.busy
    ? await host.progress({ where: "notification", title: action.busy }, () => backend.dictate(action.run!, 3600000))
    : await backend.dictate(action.run);
  const message = String(r.message ?? "");
  if (r.ok) void host.message("info", noLinks(message));
  else void host.message("error", noLinks(message) || "Talpy Den: that didn't work");
}

// What to do with one model: download it (and use it), use it, delete it
async function modelAction(host: HostServices, m: Model): Promise<Item | undefined> {
  const items: Item[] = [];
  if (!m.installed)
    items.push({ label: "$(cloud-download) Download and use it", description: `${m.mb} MB from huggingface.co`, run: ["--get-model", m.name],
                 busy: `Downloading the ${m.name} speech model…` });
  if (m.installed && !m.used) items.push({ label: "$(check) Use it", run: ["--use-model", m.name] });
  if (m.installed && m.deletable) items.push({ label: "$(trash) Delete it", description: "download it again any time", run: ["--delete-model", m.name] });
  if (m.installed && !m.deletable) items.push({ label: "whisper.cpp's own model", description: "in whisper.cpp's folder: not Talpy Den's to delete" });
  return host.pick(items, { title: `The ${m.name} model · ${m.mb} MB`, placeHolder: m.note });
}
