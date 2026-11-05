// Old chats (cleanup.py): who deletes them, Claude Code's own cleanup or
// Talpy Den's, which keeps what you starred. One choice for every copy of
// Talpy Den (Plasma, GNOME, VS Code), kept by cleanup.py in Talpy Den's state
// folder; these are its answers and the words the settings and the Old Chats
// command say them with (as Plasma's configChats.qml and GNOME's prefs.js).

// What a run deleted, or would delete (and what stayed of what it would have)
export interface CleanupCounts {
  chats?: number;
  backgroundChats?: number;
  files?: number;
  plans?: number;
  bytes?: number;
  keptChats?: number;
  keptPlans?: number;
  errors?: string[];
}

// A place's last run ("" this computer, else an SSH host or a container)
export interface CleanupRun extends CleanupCounts {
  ok?: boolean;
  at?: number;
  mode?: "claude" | "talpy";
  message?: string;
  raised?: boolean;
}

// The choice alone (cleanup.py --setting)
export interface CleanupSetting {
  mode: "claude" | "talpy";
  days: number;
}

export interface CleanupStatus extends CleanupSetting {
  ok: boolean;
  maxDays: number;
  claudeDays: { account: string; days: number }[];
  runs: Record<string, CleanupRun>;
  preview: CleanupCounts;
  previewDays: number;
  // Talpy Den's: what Claude Code's own cleanup would delete of what it keeps, if chosen again
  claudeRisk: { days: number; chats: number; plans: number } | null;
}

export function cleanupSettingOf(r: Record<string, any> | null): CleanupSetting | null {
  return r && r.ok && (r.mode === "claude" || r.mode === "talpy") ? { mode: r.mode, days: Number(r.days) || 30 } : null;
}

// cleanup.py --status's answer, or null for one that isn't
export function cleanupStatusOf(r: Record<string, any> | null): CleanupStatus | null {
  const setting = cleanupSettingOf(r);
  if (!r || !setting || typeof r.preview !== "object" || !r.preview) return null;
  const risk = r.claudeRisk;
  return {
    ...setting, ok: true, maxDays: Number(r.maxDays) || 3649,
    claudeDays: Array.isArray(r.claudeDays) ? r.claudeDays.filter((a: any) => a && typeof a.account === "string") : [],
    runs: r.runs && typeof r.runs === "object" ? r.runs : {}, preview: r.preview, previewDays: Number(r.previewDays) || 0,
    claudeRisk: risk && typeof risk === "object"
      ? { days: Number(risk.days) || 30, chats: Number(risk.chats) || 0, plans: Number(risk.plans) || 0 } : null,
  };
}

// "2 chats you keep and 1 plan you keep"
export function riskText(risk: { chats: number; plans: number }): string {
  return [risk.chats ? `${n(risk.chats, "chat", "chats")} you keep` : "", risk.plans ? `${n(risk.plans, "plan", "plans")} you keep` : ""]
    .filter((x) => x).join(" and ");
}

// The setting's value for cleanup.py's mode
export const SETTING_OF = { claude: "claude", talpy: "talpyDen" } as const;

export function sizeText(bytes: number | undefined): string {
  const b = bytes || 0;
  if (b < 1024 * 1024) return `${Math.max(0, Math.round(b / 1024))} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;

// "3 chats, 1 background chat, 12 other files (412.0 MB), 1 plan to the Trash", or "nothing"
export function cleanupText(r: CleanupCounts): string {
  const parts = [r.chats && n(r.chats, "chat", "chats"), r.backgroundChats && n(r.backgroundChats, "background chat", "background chats"),
    r.files && n(r.files, "other file", "other files")].filter((x): x is string => !!x);
  let text = parts.length ? `${parts.join(", ")} (${sizeText(r.bytes)})` : "";
  if (r.plans) text += `${text ? ", " : ""}${n(r.plans, "plan", "plans")} to the Trash`;
  return text || "nothing";
}

export function keptText(r: CleanupCounts): string {
  const k = (r.keptChats || 0) + (r.keptPlans || 0);
  return k ? `${k} old starred, open or queued ${k === 1 ? "one stays" : "ones stay"}` : "";
}

// Each place's last run, a line each: "This computer, 5 Nov, 14:02: 3 chats (412.0 MB); 2 old … stay"
export function runsLines(status: CleanupStatus, when: (ms: number) => string): string[] {
  return Object.keys(status.runs).sort().map((place) => {
    const r = status.runs[place];
    const errors = r.errors && r.errors.length ? r.errors.join("; ") : "";
    let what = !r.ok && r.message ? r.message // (out of reach, or it failed there)
      : r.mode === "talpy" ? cleanupText(r) + (keptText(r) ? `; ${keptText(r)}` : "")
      : r.raised ? "Claude Code's cleanup isn't back yet" : "Claude Code's cleanup is back";
    if (r.ok && (r.message || errors)) what += ` · ${r.message || errors}`;
    else if (!r.ok && !r.message && errors) what += ` · ${errors}`;
    return `${place || "This computer"}, ${r.at ? when(r.at) : ""}: ${what}`;
  });
}

// What the Old Chats command says: who deletes them, the next run here, the last runs
export function oldChatsDetail(status: CleanupStatus, when: (ms: number) => string): string {
  const lines = [status.mode === "talpy"
    ? `Talpy Den deletes the chats you haven't used for ${n(status.days, "day", "days")} once a day; old plans go to the Trash, and what you starred stays. ` +
      `Its next run would delete ${cleanupText(status.preview)} here.${keptText(status.preview) ? ` ${keptText(status.preview)}.` : ""}`
    : `Claude Code's own cleanup deletes every chat, and every plan of an account's plans folder, older than its cleanupPeriodDays (${
      status.claudeDays.map((a) => `${a.account}: ${a.days} days`).join(", ") || "30 days"}): starred or not, for good.`];
  const runs = runsLines(status, when);
  if (runs.length) lines.push("", ...runs);
  return lines.join("\n");
}
