// Feedback on a plan, as in a review: comment on its lines (the + next to a
// line of a plan's file, in the editor), change the file itself, then Send
// Feedback to Claude (the send button of the editor's title bar, or ↩ next
// to the chat's plan): what you changed and your comments go to the chat
// that made the plan, which revises it in plan mode (jump.py --plan-feedback,
// Actions.sendPlanFeedback). The comments are kept until they're sent.
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";

export const CONTROLLER_ID = "talpyDen.planFeedback";
const SLUG = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/; // talpy_den.py: PLAN_SLUG

// A comment of yours on the plan
class Note implements vscode.Comment {
  mode = vscode.CommentMode.Preview;
  author = { name: "You" };
  contextValue = "planNote";
  constructor(public body: string) {}
}

export interface PlanComment {
  from: number; // its lines, from 1
  to: number;
  quote: string;
  text: string;
}

// {slug, file} of a plan of this computer, <config>/plans/<slug>.md (a Claude
// config folder: ~/.claude*, or one of configDirs), or null
export function planFileOf(uri: vscode.Uri, configDirs: string[] = [], home = os.homedir(),
  listed: ReadonlySet<string> = new Set()): { slug: string; file: string } | null {
  // (file: in a Remote-SSH window too: this extension runs on this computer)
  if (uri.scheme !== "file") return null;
  return planPath(uri.path, configDirs, home, listed);
}

// listed: the files of the plans in projects' own plans folders the view
// lists (Claude's plansDirectory there names any folder)
export function planPath(file: string, configDirs: string[] = [], home = os.homedir(),
  listed: ReadonlySet<string> = new Set()): { slug: string; file: string } | null {
  const slug = path.basename(file, ".md");
  if (listed.has(file) && file.endsWith(".md") && SLUG.test(slug)) return { slug, file };
  if (!file.endsWith(".md") || path.basename(path.dirname(file)) !== "plans") return null;
  const config = path.dirname(path.dirname(file));
  const own = path.dirname(config) === home && /^\.claude(-[^/]+)?$/.test(path.basename(config));
  return SLUG.test(slug) && (own || configDirs.includes(config)) ? { slug, file } : null;
}

export class PlanReview implements vscode.Disposable {
  private readonly controller: vscode.CommentController;
  private readonly threads = new Map<string, Set<vscode.CommentThread>>(); // plan file -> its comment threads

  constructor(private readonly configDirs: () => string[], private readonly listed: () => ReadonlySet<string> = () => new Set()) {
    this.controller = vscode.comments.createCommentController(CONTROLLER_ID, "Feedback for Claude");
    this.controller.options = { prompt: "Comment for Claude…", placeHolder: "What Claude should change here" };
    this.controller.commentingRangeProvider = {
      provideCommentingRanges: (doc) => (planFileOf(doc.uri, this.configDirs(), undefined, this.listed()) ? [new vscode.Range(0, 0, Math.max(0, doc.lineCount - 1), 0)] : []),
    };
  }

  // The comment typed into a thread (its Add Comment button)
  add(reply: vscode.CommentReply): void {
    const thread = reply.thread;
    if (!reply.text.trim()) return;
    thread.comments = [...thread.comments, new Note(reply.text)];
    thread.label = "Feedback for Claude";
    thread.canReply = true;
    const key = thread.uri.path;
    if (!this.threads.has(key)) this.threads.set(key, new Set());
    this.threads.get(key)!.add(thread);
  }

  remove(thread: vscode.CommentThread): void {
    this.threads.get(thread.uri.path)?.delete(thread);
    thread.dispose();
  }

  // The comments on a plan file, top to bottom (with the lines they're on)
  async comments(file: string): Promise<PlanComment[]> {
    const threads = [...(this.threads.get(file) ?? [])].filter((t) => t.comments.length);
    if (!threads.length) return [];
    const doc = await vscode.workspace.openTextDocument(threads[0].uri);
    return threads
      .map((t) => {
        const range = t.range ?? new vscode.Range(0, 0, 0, 0);
        const last = Math.min(range.end.line, doc.lineCount - 1);
        return {
          from: range.start.line + 1,
          to: last + 1,
          quote: doc.getText(new vscode.Range(range.start.line, 0, last, doc.lineAt(last).text.length)),
          text: t.comments.map((c) => (typeof c.body === "string" ? c.body : c.body.value)).join("\n\n"),
        };
      })
      .sort((a, b) => a.from - b.from);
  }

  // Sent: they're done
  clear(file: string): void {
    for (const t of this.threads.get(file) ?? []) t.dispose();
    this.threads.delete(file);
  }

  dispose(): void {
    for (const set of this.threads.values()) for (const t of set) t.dispose();
    this.threads.clear();
    this.controller.dispose();
  }
}
