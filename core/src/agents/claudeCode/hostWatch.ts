// Talpy Chat's watcher of an SSH host or a container (Plasma's hub/Hub.qml
// does the same): remote.py --watch, live.py there over the shared ssh
// connection, answers the moment a chat's session file or a permission
// request there changes (within 50 s anyway), and runs again at once while
// it's wanted: a Talpy Chat tab of a chat there shows (or starts one), or,
// in the window that notifies, a chat there whose prompts Talpy Den's hook
// answers works or waits. It also watches the chats of the tabs that show
// there (setChats: --chats), and says which were written ("wrote"): a tab
// reads its conversation then, not every few seconds in case, each read
// sending the script there (2026-11-22). Other chats, or unwanted: the run
// on its way ends (its ssh too), and with other chats it runs again at once.

import * as crypto from "node:crypto";
import * as os from "node:os";

export interface WatchAnswer {
  ok: boolean;
  sessions?: boolean;
  requests?: boolean;
  changed?: string[];
  wrote?: string[]; // (the chats of the tabs there that were written: --chats)
  timeout?: boolean;
  reached?: boolean;
  error?: string;
  message?: string;
}

export const WATCH_TIMEOUT_MS = 70000; // (live.py waits 50 s at the most, then ssh's own time)
const RETRY_MS = 5000;
const RETRY_LONG_MS = 60000; // after 3 failures in a row
const AGAIN_MS = 250; // (an answer at once, again and again: a host whose watcher can't wait, say)

// The name a watcher goes by on the host (live.py --as: what it told this
// window's last run is kept there under it): a hash, as it shows in the
// host's process list; a window's own, so two windows don't share what was told
export function watchName(sessionId: string): string {
  return crypto.createHash("sha1").update(`talpy-den vscode ${os.hostname()} ${sessionId}`).digest("hex").slice(0, 12);
}

export class HostWatch {
  private stopped = false;
  private failures = 0;
  private pause?: { timer: NodeJS.Timeout; done: () => void };
  private chats: string[] = []; // (sorted)
  private inFlight?: { chats: string[]; end: AbortController }; // the run on its way, and the chats it watches
  // why it can't watch now ("" when it can); "check": the host couldn't be reached, so not until its next check
  trouble = "";

  constructor(
    readonly host: string,
    private readonly run: (args: string[], timeoutMs: number, signal?: AbortSignal) => Promise<WatchAnswer>,
    private readonly name: string,
    private readonly onChange: (host: string, answer: WatchAnswer) => void,
    private readonly onTrouble: (host: string, trouble: string) => void = () => undefined,
    private readonly delays = { retry: RETRY_MS, retryLong: RETRY_LONG_MS, again: AGAIN_MS },
  ) {}

  get running(): boolean {
    return !this.stopped && this.trouble !== "check";
  }

  start(): void {
    void this.loop();
  }

  stop(): void {
    this.stopped = true;
    this.inFlight?.end.abort();
    if (this.pause) {
      clearTimeout(this.pause.timer);
      this.pause.done();
    }
  }

  // The chats of the tabs that show there: the run on its way, for others, ends, and it runs again with these
  setChats(chats: Iterable<string>): void {
    const next = [...new Set(chats)].sort();
    if (next.join(",") === this.chats.join(",")) return;
    this.chats = next;
    if (this.inFlight && this.inFlight.chats.join(",") !== next.join(",")) this.inFlight.end.abort();
  }

  // Whether it says when chat is written there (one of the tabs' chats)
  watches(chat: string): boolean {
    return !this.stopped && this.chats.includes(chat);
  }

  // The host answered its check: a watcher that couldn't reach it runs again
  checked(): void {
    if (this.trouble !== "check" || this.stopped) return;
    this.setTrouble("");
    this.failures = 0;
    void this.loop();
  }

  private setTrouble(trouble: string): void {
    if (trouble === this.trouble) return;
    this.trouble = trouble;
    this.onTrouble(this.host, trouble);
  }

  private wait(ms: number): Promise<void> {
    return new Promise((done) => {
      this.pause = { timer: setTimeout(() => ((this.pause = undefined), done()), ms), done };
    });
  }

  private async loop(): Promise<void> {
    while (!this.stopped) {
      const asked = Date.now();
      const chats = this.chats;
      const end = new AbortController();
      this.inFlight = { chats, end };
      let answer: WatchAnswer;
      try {
        answer = await this.run(["remote.py", "--watch", this.host, "--as", this.name, ...(chats.length ? ["--chats", chats.join(",")] : [])],
                                WATCH_TIMEOUT_MS, end.signal);
      } catch (e) {
        answer = { ok: false, error: e instanceof Error ? e.message : String(e) };
      }
      this.inFlight = undefined;
      if (this.stopped) return;
      if (end.signal.aborted && !answer.ok) continue; // (ended for other chats: again at once with them, not a failure)
      if (!answer.ok) {
        this.failures += 1;
        if (answer.reached === false) return this.setTrouble("check"); // (till its next check answers: checked)
        if (this.failures >= 3) this.setTrouble(String(answer.error ?? answer.message ?? "it didn't answer"));
        await this.wait(this.failures >= 3 ? this.delays.retryLong : this.delays.retry);
        continue;
      }
      this.failures = 0;
      this.setTrouble("");
      if (answer.sessions || answer.requests || answer.wrote?.length) this.onChange(this.host, answer);
      if (Date.now() - asked < this.delays.again) await this.wait(this.delays.again);
    }
  }
}
