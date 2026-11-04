// Runs the widget's Python helpers (code/*.py, the same ones the Plasma
// widget uses) without blocking GNOME Shell: python3 -I <script> <args>,
// read asynchronously, then handed back as text.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const POLL_TIMEOUT_S = 60;   // a check that takes longer has hung (a stuck network folder, ssh)
const KILL_GRACE_S = 3;      // after SIGTERM, before it's killed

export class Runner {
    constructor(codeDir) {
        this._codeDir = codeDir;
        this._cancellable = new Gio.Cancellable();
        this._polls = new Set();   // read-only status checks: stopped on destroy
        this._timers = new Set();
    }

    // Resolves to {stdout, stderr} (empty when it couldn't start). A poll is
    // only reading, so it's ended when the extension is disabled, or when it
    // hangs (else no other check would start); actions (jump, stop, new chat)
    // are left to finish, and still answer. timeout: a poll's own, in seconds.
    run(script, args, {poll = false, timeout = POLL_TIMEOUT_S} = {}) {
        return new Promise(resolve => {
            let proc;
            try {
                const launcher = new Gio.SubprocessLauncher({
                    flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
                });
                launcher.set_cwd(GLib.get_home_dir());
                proc = launcher.spawnv(['python3', '-I', GLib.build_filenamev([this._codeDir, script]), ...args]);
            } catch (e) {
                resolve({stdout: '', stderr: `Couldn't run python3: ${e.message}`});
                return;
            }
            let timer = 0;
            if (poll) {
                this._polls.add(proc);
                timer = this._after(timeout, () => {
                    timer = 0;
                    this._end(proc);
                });
            }
            proc.communicate_utf8_async(null, poll ? this._cancellable : null, (p, res) => {
                this._polls.delete(proc);
                if (timer)
                    this._clear(timer);
                try {
                    const [, stdout, stderr] = p.communicate_utf8_finish(res);
                    resolve({stdout: stdout || '', stderr: stderr || ''});
                } catch (e) {
                    resolve({stdout: '', stderr: e.message, cancelled: e.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED)});
                }
            });
        });
    }

    // SIGTERM first: remote.py then ends the ssh it runs (a kill would leave
    // that behind); killed if it's still there a little later
    _end(proc) {
        proc.send_signal(15);
        this._after(KILL_GRACE_S, () => proc.force_exit());
    }

    _after(seconds, fn) {
        const id = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => {
            this._timers.delete(id);
            fn();
            return GLib.SOURCE_REMOVE;
        });
        this._timers.add(id);
        return id;
    }

    _clear(id) {
        GLib.source_remove(id);
        this._timers.delete(id);
    }

    get cancelled() {
        return this._cancellable.is_cancelled();
    }

    destroy() {
        this._cancellable.cancel();
        for (const id of this._timers)
            GLib.source_remove(id);
        this._timers.clear();
        for (const proc of this._polls)
            proc.send_signal(15);   // python ends at once (and remote.py its ssh)
        this._polls.clear();
    }
}
