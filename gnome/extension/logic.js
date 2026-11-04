// What the dashboard says, worked out from the status script's JSON
// (package/contents/code/talpy_den.py, see its collect()). No GNOME Shell
// imports here, so `gjs -m gnome/tests/test_logic.js` can test it.
//
// A port of the logic in the Plasma widget's main.qml: keep the two in step.

// "%1 of %2" style placeholders, as in the Plasma widget's i18n()
export function fmt(text, ...args) {
    return text.replace(/%(\d)/g, (m, i) => (args[i - 1] !== undefined ? String(args[i - 1]) : m));
}

export function plural(n, one, many) {
    return fmt(n === 1 ? one : many, n);
}

// ---- containers: docker:NAME, podman:NAME, nerdctl:NAME (this computer's),
// ENGINE:NAME@HOST (on the SSH host HOST), picked and shown like SSH hosts
// (remote.py's ids)

// {engine, name, host} of a container's id ('' host: this computer's), or null for an SSH host
export function containerOf(id) {
    const m = /^(docker|podman|nerdctl):([A-Za-z0-9][A-Za-z0-9_.-]*)(?:@(.+))?$/.exec(id || '');
    return m ? {engine: m[1], name: m[2], host: m[3] || ''} : null;
}

// How an SSH host or a container is named: lab, web, or web on lab
export function hostLabel(id) {
    const c = containerOf(id);
    return !c ? id : c.host ? fmt('%1 on %2', c.name, c.host) : c.name;
}

// "stopped 3 days ago", "stopped 5h 10m ago", "stopped"
export function containerStopped(c, now) {
    const age = c && c.activeAt ? Math.max(0, now - c.activeAt) : -1;
    return age < 0 ? 'stopped' : age >= 2 * 86400000 ? plural(Math.floor(age / 86400000), 'stopped %1 day ago', 'stopped %1 days ago')
        : fmt('stopped %1 ago', duration(age));
}

// A container's line in the hosts picker: "web  (podman · ubuntu:22.04 · stopped 3 days ago)"
export function containerLine(c, now) {
    const parts = [c.folderShort ? c.folderShort : c.engine + (c.image ? ` · ${c.image}` : '')];
    if (!c.running)
        parts.push(containerStopped(c, now));
    if (c.sharesHome)
        parts.push('shares your home folder');
    return `${c.name}  (${parts.join(' · ')})`;
}

// A picked container's header line: "podman · ubuntu:22.04", or its dev container's folder (· on lab)
export function containerDetail(id, info) {
    const c = containerOf(id);
    const parts = [info && info.folderShort ? info.folderShort : c.engine + (info && info.image ? ` · ${info.image}` : '')];
    if (c.host)
        parts.push(fmt('on %1', c.host));
    return parts.join(' · ');
}

// The hosts picker's container sections: this computer's, then each
// connected SSH host's (and a host's whose container you picked); a picked
// container that isn't listed is still there, to unpick it.
// [{host, title, items: [{text, id, checked}], notes: [text], empty: text|''}]
export function containerPlaces(here, notes, hostContainers, connected, picked, days, now) {
    const none = days > 0 ? plural(days, 'No containers active in the last day', 'No containers active in the last %1 days')
        : 'No running containers';
    const pickedOf = host => picked.filter(id => (containerOf(id) || {host: null}).host === host);
    const hosts = connected.concat(picked.map(id => (containerOf(id) || {}).host || '')
        .filter((h, i, all) => h && all.indexOf(h) === i && !connected.includes(h)));
    const places = [{host: '', title: 'Containers on this computer', list: here, notes}];
    for (const host of hosts) {
        const kept = connected.includes(host) ? hostContainers[host] || {} : {};
        places.push({host, title: fmt('Containers on %1', host), list: kept.containers || [],
            notes: (kept.notes || []).concat(kept.error ? [{message: kept.error}] : [])});
    }
    return places.map(place => {
        const listed = place.list.filter(c => c && c.id);
        const items = listed.map(c => ({text: containerLine(c, now), id: c.id, checked: picked.includes(c.id)}));
        for (const id of pickedOf(place.host)) {
            if (!listed.some(c => c.id === id))
                items.push({text: containerOf(id).name, id, checked: true});
        }
        const messages = place.notes.map(n => n.message);
        return {host: place.host, title: place.title, items, notes: messages,
            empty: items.length || messages.length ? '' : none};
    });
}

// What stopped a chat's turn before it was through, while that holds:
// "limit" (a usage limit, until it resets) or "login" (it expired), else ""
export function stopOf(s) {
    return (s.state === 'idle' || s.state === 'done') && s.stopped && !s.stopped.over ? s.stopped.kind : '';
}

// (a chat a usage limit stopped waits for the limit, not for you: "limit",
// whether a process still has it open or not)
export function counts(groups) {
    const c = {waiting: 0, working: 0, idle: 0, done: 0, limit: 0};
    for (const g of groups) {
        for (const s of g.sessions) {
            const state = stopOf(s) === 'limit' ? 'limit' : s.state;
            c[state] = (c[state] || 0) + 1;
        }
    }
    return c;
}

export function overall(groups, c = counts(groups)) {
    if (c.waiting)
        return 'waiting';
    if (c.working)
        return 'working';
    // finished jobs kept for the record don't count as running
    return groups.some(g => g.sessions.some(s => (s.state === 'idle' || s.state === 'done') && s.pid !== null))
        ? 'idle' : 'none';
}

// Milliseconds between status checks: poll-interval while a chat runs (here
// or on a host) or the menu is open; with nothing running, idle-poll-interval
// (never more often). An idle panel then costs less, and a chat that starts
// still shows within seconds (the menu opening checks at once).
export function pollInterval(settingMs, idleMs, overallState, menuOpen) {
    const ms = Math.max(1000, settingMs);
    return overallState === 'none' && !menuOpen ? Math.max(ms, idleMs) : ms;
}

// The accounts of the hosts that answered, each marked with its host. A
// host whose last check failed still shows what it said before (dimmed), but
// that doesn't count here: no badge or shortcut for a chat you can't reach.
// owners (usageOwners): an account's plan usage counts once, where it's
// shown (withUsage), as in Plasma
export function remoteGroups(shownHosts, remote, owners = null) {
    const out = [];
    for (const host of shownHosts) {
        const r = remote[host];
        if (r && r.result && !r.error && !r.cached) {   // (its answer kept from before this start: shown, not counted)
            for (const g of r.result.groups)
                out.push(Object.assign({}, owners ? withUsage(g, host, owners) : g, {host}));
        }
    }
    return out;
}

// Plan usage is the account's, whichever machine it's used on. An account on
// several (this computer and SSH hosts: the same id) shows it once, where it's
// listed first, with the newest numbers of them all (as Plasma's and VS Code's
// default). hostGroups: [[host, groups], ...] in the hosts' order
export function usageOwners(groups, hostGroups) {
    const out = {};
    const note = (g, host) => {
        const o = out[g.id] || (out[g.id] = {host, limits: null, from: ''});
        if (g.limits && (!o.limits || g.limits.updatedAt > o.limits.updatedAt)) {
            o.limits = g.limits;
            o.from = host;
        }
    };
    for (const g of groups)
        note(g, '');
    for (const [host, gs] of hostGroups) {
        for (const g of gs)
            note(g, host);
    }
    return out;
}

// group as shown in host's section ('' here): limitsHidden when its usage
// shows elsewhere, limitsFrom when the numbers come from another machine
export function withUsage(group, host, owners) {
    const owner = owners[group.id];
    if (!owner)
        return group;
    if (host && owner.host !== host)
        return Object.assign({}, group, {limits: null, limitsHidden: true});
    if (owner.from === host)
        return group;
    return Object.assign({}, group, {limits: owner.limits, limitsFrom: owner.from});
}

// The hero's headline: the most important thing on the dashboard
export function headline(status, errorText, c) {
    if (!status && errorText)
        return 'Status unavailable';
    if (!status)
        return 'Looking for your chats…';
    if (c.waiting)
        return plural(c.waiting, '%1 chat needs you', '%1 chats need you');
    if (c.working)
        return plural(c.working, '%1 chat working', '%1 chats working');
    if (c.idle)
        return plural(c.idle, 'Your turn in %1 chat', 'Your turn in %1 chats');   // Claude finished its reply
    if (c.limit)
        return plural(c.limit, '%1 chat waits for its usage limit', '%1 chats wait for their usage limit');
    if (c.done)
        return plural(c.done, '%1 finished chat to look at', '%1 finished chats to look at');
    return 'All quiet';
}

export function summaryText(c) {
    const parts = [];
    if (c.waiting)
        parts.push(plural(c.waiting, '%1 needs input', '%1 need input'));
    if (c.working)
        parts.push(fmt('%1 working', c.working));
    if (c.idle)
        parts.push(fmt('%1 idle', c.idle));
    if (c.limit)
        parts.push(fmt('%1 at the usage limit', c.limit));
    if (c.done)
        parts.push(fmt('%1 done', c.done));
    return parts.length ? parts.join(' · ') : 'No chats running';
}

// A chat's key: its account and conversation, so its pet, its notifications
// and whether you've seen it stay the same while its row changes (e.g. a
// background session's row from running to finished, …/live to …/job). A
// chat shared with two accounts is two chats here.
export function petKeyOf(session, host) {
    return `${host ? `ssh:${host}|` : ''}${session.profileDir || ''}/${session.chatId || session.sessionId || session.key}`;
}

// What a waiting chat asks, to tell one prompt from the next: the hook's
// request, else the tool call it's about; '' when there's nothing to tell
// them apart by (main.qml: askId)
export function askId(s) {
    const p = s ? s.permission : null;
    if (!p)
        return '';
    if (p.answer === 'hook')
        return p.request ? `request:${p.request}` : '';
    return p.toolUse ? `tool:${p.toolUse}` : '';
}

// What a waiting chat asks, for its notification: [title, text] (s.permission
// set; main.qml: askText): a plan ready, Claude's questions, or a permission
// with its command or the file it changes
export function askText(s) {
    const p = s.permission;
    if (p.plan)
        return [fmt('%1 has a plan ready', s.name), p.plan.title || 'Approve it to start, or keep planning.'];
    if (p.questions && p.questions.length)
        return [fmt('%1 asks you', s.name), p.questions.map(q => q.question).join('\n')];
    return [fmt('%1 asks for a permission', s.name), p.command || (p.file ? fmt('Change %1', p.file) : p.line || '')];
}

// The 5-hour usage that goes next to the panel icon: this computer's default
// account (listed first; VS Code's Claude and plain claude run on it), else
// the account with an active session, else the one with the freshest numbers.
export function panelWindow(groups) {
    const own = groups.find(g => !g.host && g.defaultHere && g.limits && g.limits.windows.length);
    if (own)
        return own.limits.windows[0];
    let best = null, bestScore = -1;
    for (const g of groups) {
        if (!g.limits || !g.limits.windows.length)
            continue;
        const active = g.sessions.some(s => s.state === 'working' || s.state === 'waiting');
        const score = (active ? 1e15 : 0) + g.limits.updatedAt;
        if (score > bestScore) {
            bestScore = score;
            best = g.limits.windows[0];
        }
    }
    return best;
}

// "work · Team", or "lab: work · Team" for an SSH host's account
export function groupLabel(g) {
    return g.host ? fmt('%1: %2', hostLabel(g.host), g.name) : g.name;
}

export function tooltipText(status, errorText, groups, shownHosts, remote) {
    if (errorText && !status)
        return errorText;
    const lines = [summaryText(counts(groups))];
    for (const g of groups) {
        if (!g.limits)
            continue;
        lines.push(`${g.host ? `${hostLabel(g.host)}: ` : ''}${g.title}: ${
            g.limits.windows.map(w => `${w.label} ${Math.round(w.pct)}%`).join(' · ')}`);
    }
    for (const host of shownHosts) {
        if (remote[host] && remote[host].error)
            lines.push(fmt('%1: not reachable', hostLabel(host)));
    }
    return lines.join('\n');
}

export function reasonText(reason) {
    switch (reason) {
    case 'permission': return 'Asks for permission';
    case 'question': return 'Has a question for you';
    case 'network access': return 'Asks for network access';
    case 'goal approval': return 'Proposes a goal';
    case '': return 'Waiting for you';
    default: return reason;
    }
}

export function duration(ms) {
    const m = Math.max(0, Math.round(ms / 60000));
    if (m < 60)
        return fmt('%1m', m);
    const h = Math.floor(m / 60);
    if (h < 24)
        return fmt('%1h %2m', h, m % 60);
    return fmt('%1d %2h', Math.floor(h / 24), h % 24);
}

// How long ago, for the lists' ages: "just now" under a minute, not "0m ago"
export function ago(ms) {
    return ms < 60000 ? 'just now' : fmt('%1 ago', duration(ms));
}

export function resetText(window, now) {
    if (window.reset)
        return 'reset';
    if (!window.resetsAt)
        return '';
    // The last minute reads "<1m": a rounded "0m" looked stuck
    return fmt('resets in %1', window.resetsAt - now < 60000 ? '<1m' : duration(window.resetsAt - now));
}

export function stateText(s, now) {
    const since = s.since ? ` · ${duration(now - s.since)}` : '';
    const reason = s.reason ? ` · ${s.reason}` : '';
    if (s.stopped && (s.state === 'idle' || s.state === 'done')) {
        if (s.stopped.kind === 'login')
            return 'Login expired';
        if (s.stopped.over)
            return 'Limit reset · go on';
        return s.stopped.resetsAt
            ? `Limit · resets in ${s.stopped.resetsAt - now < 60000 ? '<1m' : duration(s.stopped.resetsAt - now)}`
            : 'Hit a usage limit';
    }
    switch (s.state) {
    case 'waiting': return `Needs input${reason}`;
    case 'working': return `Working${reason}${since}`;
    case 'done':
        return (s.reason === 'failed' ? 'Failed' : s.reason === 'stopped' ? 'Stopped' : 'Done') + since;
    default: return `Idle${since}`;
    }
}

// (the unit goes by the rounded value, so 999,999 reads 1.0M, not 1000.0k)
export function formatTokens(n) {
    if (n >= 999.95e6)
        return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 999.95e3)
        return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3)
        return `${(n / 1e3).toFixed(1)}k`;
    return String(n);
}

// The color of a state, as a style class suffix (claude-fg-*, claude-bg-*
// in stylesheet.css)
export function stateClass(state) {
    switch (state) {
    case 'waiting': return 'waiting';
    case 'working': return 'working';
    case 'idle':
    case 'done': return 'ok';
    default: return 'none';
    }
}

export function usageClass(pct) {
    if (pct >= 90)
        return 'bad';
    if (pct >= 70)
        return 'waiting';
    return 'working';
}

// from: the SSH host the numbers come from, when another machine's are newer
// (withUsage); a fetch on its way (Refresh's, or while a chat works: fetchAt) says so
export function planUsageText(limits, now, from = '', fetchAt = null) {
    if (fetchAt && now - fetchAt < 70000 && (!limits || limits.updatedAt < fetchAt))
        return 'Fetching the plan usage…';
    if (!limits)
        return "No plan usage yet: shows after this account's next reply";
    if (from) {
        return now - limits.updatedAt < 60000 ? fmt('Plan usage updated just now, on %1', from)
            : fmt('Plan usage as of %1 ago, on %2', duration(now - limits.updatedAt), from);
    }
    if (now - limits.updatedAt < 60000)
        return 'Plan usage updated just now';
    return fmt('Plan usage as of %1 ago', duration(now - limits.updatedAt));
}

export function tokensText(t) {
    return fmt('Tokens today %1 (%2 out) · 7 days %3 (%4 out)',
        formatTokens(t.today.total), formatTokens(t.today.output),
        formatTokens(t.week.total), formatTokens(t.week.output));
}

export function tokensTooltip(t) {
    const line = b => fmt('input %1 · output %2 · cache read %3 · cache write %4 · %5 replies',
        formatTokens(b.input), formatTokens(b.output), formatTokens(b.cacheRead),
        formatTokens(b.cacheWrite), b.messages);
    const models = t.models.map(m => `${m.model.replace(/^claude-/, '')}: ${formatTokens(m.total)}`);
    let text = `Today: ${line(t.today)}\nLast 7 days: ${line(t.week)}`;
    if (models.length)
        text += `\nBy model (7 days): ${models.join(', ')}`;
    if (t.week.shared > 0) {
        text += `\n${fmt("Includes %1 today (%2 in 7 days) from chats shared with another profile. A transcript doesn't say which account paid, so shared chats count on both.",
            formatTokens(t.today.shared), formatTokens(t.week.shared))}`;
    }
    return text;
}

// The hint on a session's name: what clicking it does
export function openHint(session, remoteHost) {
    if (containerOf(remoteHost)) {
        const name = hostLabel(remoteHost);
        if (session.entrypoint === 'claude-vscode' && !session.openCommand)
            return fmt('Show this conversation in VS Code (connected to %1)', name);
        if (!session.openCommand)
            return fmt('Switch to the terminal open in %1', name);
        if (session.kind === 'chat')
            return fmt('Reopen this chat in %1 in a terminal', name);
        return fmt('Open this background chat in %1 in a terminal', name);
    }
    if (remoteHost) {
        if (session.entrypoint === 'claude-vscode' && !session.openCommand)
            return fmt('Show this conversation in VS Code (connected to %1)', remoteHost);
        if (!session.openCommand)
            return fmt('Switch to the terminal with the ssh connection to %1', remoteHost);
        if (session.kind === 'chat')
            return fmt('Reopen this chat on %1 in a terminal (ssh)', remoteHost);
        return fmt('Open this background chat on %1 in a terminal (ssh)', remoteHost);
    }
    if (session.entrypoint === 'claude-vscode')
        return 'Open this conversation in VS Code';
    if (session.kind === 'chat')
        return 'Reopen this chat in a terminal (claude --resume)';
    if (session.kind === 'bg' && session.pid === null)
        return 'Reopen this background chat in a terminal';
    if (session.kind === 'bg')
        return 'Show this background chat in a terminal';
    return 'Switch to the terminal running this chat';
}

// The tooltips of a finished chat's × (Hide this chat: where it comes back)
// and its Delete… (Plasma's words)
export function hideHint(host) {
    return `Only hides it here; nothing is deleted. It comes back if the chat runs again. ${host
        ? fmt("The eye button next to %1's name brings it back.", hostLabel(host))
        : 'Show Hidden Chats Again, at the bottom of this menu, brings it back.'}`;
}

export const DELETE_HINT = "Moves it to the Trash, on every account it's shared with, with its subagents and checkpoints; the Recap keeps its numbers. It asks first.";

// A chat with a process of its own can be stopped, whatever it's doing: in a
// terminal its claude quits (the chat is kept), in VS Code its tab shows it as
// interrupted and goes on with the next message (talpy_den.py: stopping
// and interrupting chats). One in tmux that's working can be interrupted
// instead: Ctrl+C in its pane, like VS Code's stop button.
export function canEnd(session) {
    return session.kind === 'interactive' && session.pid !== null;
}

// (not when only a background command runs: its turn is over, Ctrl+C would land at its prompt)
export function canInterrupt(session) {
    return canEnd(session) && !!session.tmux && (session.state === 'working' || session.state === 'waiting')
        && session.reason !== 'background shell';
}

// A stop's answer that says more happened than you asked for (it hadn't quit
// after a few seconds, so it was killed; the commands it was running ended):
// shown, as Plasma does
export function stopSaysMore(message) {
    return /killed|ended/.test(message || '');
}

// The stop button's tooltip
export function stopTip(session) {
    if (canInterrupt(session)) {
        return ['Interrupt or stop this chat',
            'Asks first. Interrupting is like Ctrl+C in its tmux pane, or the stop button in VS Code: the current step and its subagents stop, and the chat stays open there.'];
    }
    if (canEnd(session) && session.entrypoint === 'claude-vscode')
        return ['Stop this chat', 'Asks first. Its tab in VS Code shows it as interrupted, keeps the chat and goes on with your next message.'];
    if (canEnd(session) && session.state === 'idle')
        return ['Stop this chat', 'Asks first. Claude quits and its terminal stays open; the chat is kept and shows under Recent chats.'];
    if (canEnd(session)) {
        return ['Stop this chat',
            'Asks first. The current step is cut off, Claude quits and its terminal stays open; the chat is kept and shows under Recent chats.'];
    }
    return ['Stop this background chat', 'Asks first. The conversation is kept; claude attach resumes it.'];
}

export function stopQuestion(session) {
    const n = session.name;
    if (canInterrupt(session))
        return fmt("Interrupt “%1”? Like Ctrl+C in its tmux pane, or the stop button in VS Code: the current step and its subagents stop, and the chat stays open there. Or stop it: Claude quits and its terminal stays open.", n);
    if (canEnd(session) && session.entrypoint === 'claude-vscode') {
        if (session.state === 'working')
            return fmt("Stop “%1”? It's working right now: the current step is interrupted, as with VS Code's stop button, and anything it was running stops. Its tab keeps the chat and goes on with your next message.", n);
        if (session.state === 'waiting')
            return fmt("Stop “%1”? It's waiting for you: what it asks is refused, as with VS Code's stop button. Its tab keeps the chat and goes on with your next message.", n);
        return fmt("Stop “%1”? It's idle, so nothing is interrupted: its Claude process in VS Code quits. Its tab keeps the chat and goes on with your next message.", n);
    }
    if (canEnd(session) && session.state === 'working')
        return fmt("Stop “%1”? It's working right now: the current step is cut off and anything it was running stops. Claude quits and its terminal stays open; the chat is kept (Recent chats reopens it).", n);
    if (canEnd(session) && session.state === 'waiting')
        return fmt("Stop “%1”? It's waiting for you: Claude quits without your answer and its terminal stays open. The chat is kept (Recent chats reopens it).", n);
    if (canEnd(session))
        return fmt("Stop “%1”? It's idle, so nothing is interrupted: Claude quits and its terminal stays open. The chat is kept; reopen it from Recent chats.", n);
    if (session.state === 'working') {
        return fmt("Stop “%1”? It's working right now: the current step is interrupted and anything it started in the background stops too. The conversation is kept; claude attach resumes it.",
            session.name);
    }
    if (session.state === 'waiting')
        return fmt("Stop “%1”? It's waiting for you. The conversation is kept; claude attach resumes it.", session.name);
    return fmt("Stop “%1”? It's finished, so this only shuts down its idle process. The conversation is kept.", session.name);
}

// The pets' mood for the whole dashboard (the big Talpy)
export function petMood(status, errorText, overallState, agentsRunning) {
    if (!status && errorText)
        return 'error';
    if (!status)
        return 'loading';
    if (overallState === 'waiting')
        return 'needs';
    if (overallState === 'working')
        return agentsRunning > 0 ? 'agents' : 'working';
    if (overallState === 'idle')
        return 'idle';
    return 'done';
}

export function agentsRunning(groups) {
    let n = 0;
    for (const g of groups) {
        for (const s of g.sessions) {
            if (s.agents && s.state !== 'done')
                n += s.agents.running;
        }
    }
    return n;
}

const SOUND_RANK = {'': 0, done: 1, failed: 2, waiting: 3};

// Remembers each session's state across polls and says what to tell you
// when one changes: notifications to send or close, pet reactions, and the
// one sound for the poll (the most urgent). Each source ("" for this
// computer, "ssh:<host>" for an SSH host) keeps its own memory, so one
// poll can't close another's notifications.
export class Tracker {
    constructor() {
        this.lastStates = {};
        this.turnStarts = {};
        this.lastEnded = {};   // the turns that ended lately (a minute, while idle or done), told as finished: {key: {took, at}}
        this.primed = {};
        this.lastWaitingAlert = {};   // key -> {at, ask}: its last "needs input" alert, and what it asked (askId)
        this.lastWindows = {};
        this.lastStops = {};      // source -> {pet key: whether the limit that stopped it has reset}
        this.lastOverlaps = {};   // source -> {pair of chats changing the same files: true}
    }

    // settings: {notifyWaiting, notifyDone, notifyDoneMinSeconds}
    // Returns {notify: [...], close: [...], pets: [...], sound: "" | "waiting" | "done" | "failed",
    // present: Set, states: {key: state}, finished: [{key, took, stop}] (every turn that ended;
    // stop: what broke it off, see stopOf)}
    track(source, groupList, nowMs, host, settings) {
        const out = {notify: [], close: [], pets: [], sound: '', present: new Set(), states: {}, finished: []};
        const next = {}, starts = {}, ends = {};
        const before = this.lastStates[source] || {};
        const startedAt = this.turnStarts[source] || {};
        const ended = this.lastEnded[source] || {};
        const primed = !!this.primed[source];
        const where = host ? ` · ${host}` : '';
        const sound = kind => {
            if (SOUND_RANK[kind] > SOUND_RANK[out.sound])
                out.sound = kind;
        };
        for (const g of groupList) {
            for (const s of g.sessions) {
                const sid = petKeyOf(s, host);   // starts with source + "|" for a host's
                if (sid in next)
                    continue;   // a chat listed twice: its most urgent row (they come first) counts
                const prev = before[sid];
                const active = s.state === 'working' || s.state === 'waiting';
                next[sid] = s.state;
                out.states[sid] = s.state;
                out.present.add(sid);
                // A turn runs from leaving idle/done until returning to it.
                if (active)
                    starts[sid] = sid in startedAt ? startedAt[sid] : s.since || nowMs;
                if (prev === 'waiting' && s.state !== 'waiting')
                    out.close.push({key: sid, kind: 'waiting'});   // answered: drop the stale prompt
                if (!primed)
                    continue;
                const stop = stopOf(s);
                if (stop && sid in ended && nowMs - ended[sid].at < 60000) {
                    // Claude writes its transcript a moment after the turn ends, so
                    // the usage limit that ended it can show a poll later: it
                    // didn't finish after all
                    this._turnEnded(out, sid, s, host, ended[sid].took, settings, sound);
                    continue;
                }
                // (a check or two later too, with checks coming quickly: for a
                // minute, while it stays idle or done)
                if (sid in ended && (s.state === 'idle' || s.state === 'done') && nowMs - ended[sid].at < 60000)
                    ends[sid] = ended[sid];
                const alerted = this.lastWaitingAlert[sid];
                const alert = () => {
                    this.lastWaitingAlert[sid] = {at: nowMs, ask: askId(s)};
                    out.pets.push({kind: 'waiting', text: fmt('%1 needs you!', s.name), key: petKeyOf(s, host)});
                    if (settings.notifyWaiting) {
                        const asks = s.permission ? askText(s) : [fmt('%1 needs your input', s.name), s.detail || reasonText(s.reason)];
                        out.notify.push({
                            key: sid, session: s, kind: 'waiting', host,
                            title: asks[0],
                            body: `${asks[1]}\n${s.cwdShort}${where}`,
                            icon: 'warning',   // (a meaning of ui/icons.js: notifier.js)
                        });
                        sound('waiting');
                    }
                };
                // a new prompt the minute's quiet held back (nothing told it
                // apart from the last one then: the hook's request came a poll later)
                if (prev === 'waiting' && s.state === 'waiting' && alerted && alerted.held && askId(s) && askId(s) !== alerted.ask)
                    alert();
                if (prev === s.state)
                    continue;
                if (s.state === 'waiting') {
                    // At most one "needs input" alert per session per minute, unless
                    // it asks something new (the next command after you allowed one)
                    if (!alerted || nowMs - alerted.at >= 60000 || (askId(s) && askId(s) !== alerted.ask))
                        alert();
                    else
                        alerted.held = true;
                } else if ((prev === 'working' || (stop && prev === 'waiting')) && (s.state === 'idle' || s.state === 'done')) {
                    // (a background session a limit stops can say it waits for a moment first)
                    const took = (s.since || nowMs) - (sid in startedAt ? startedAt[sid] : nowMs);
                    this._turnEnded(out, sid, s, host, took, settings, sound);
                    if (!stop)
                        ends[sid] = {took, at: nowMs};
                }
            }
        }
        for (const key of Object.keys(this.lastWaitingAlert)) {
            if (keyOfSource(key, source) && !(key in next))
                delete this.lastWaitingAlert[key];
        }
        this.lastStates[source] = next;
        this.turnStarts[source] = starts;
        this.lastEnded[source] = ends;
        this.primed[source] = true;
        return out;
    }

    // A chat's turn ended (it was working, it's idle or done now) after took ms:
    // its pet reacts and a notification says how. A turn a usage limit or an
    // expired login broke off didn't finish (its notification replaces a
    // "finished" one sent a poll before).
    _turnEnded(out, sid, s, host, took, settings, sound) {
        const where = host ? ` · ${host}` : '';
        const stop = stopOf(s);
        const pk = petKeyOf(s, host);
        if (stop === 'limit')
            out.pets.push({kind: 'limit', text: fmt('%1 hit the usage limit.', s.name), key: pk});
        else if (stop === 'login')
            out.pets.push({kind: 'stopped', text: fmt('%1: the login expired.', s.name), key: pk});
        else if (s.reason === 'failed')
            out.pets.push({kind: 'failed', text: fmt('%1 failed…', s.name), key: pk});
        else if (s.reason === 'stopped')
            out.pets.push({kind: 'stopped', text: fmt('%1 was stopped.', s.name), key: pk});
        else
            out.pets.push({kind: 'done', text: fmt('%1 is done!', s.name), key: pk});
        out.finished.push({key: sid, took, stop});
        if (!settings.notifyDone || took < settings.notifyDoneMinSeconds * 1000)
            return;
        if (stop) {
            out.notify.push({
                key: sid, session: s, kind: stop, host,
                title: stop === 'limit' ? fmt('%1 hit the usage limit', s.name) : fmt('%1 stopped: the login expired', s.name),
                body: `${s.stopped.text}\n${fmt('Took %1 · %2', duration(took), s.cwdShort)}${where}`,
                icon: stop === 'limit' ? 'goOnAt' : 'error',
            });
            sound('failed');
        } else {
            const title = s.reason === 'failed' ? fmt('%1 failed', s.name)
                : s.reason === 'stopped' ? fmt('%1 was stopped', s.name)
                    : fmt('%1 finished', s.name);
            out.notify.push({
                key: sid, session: s, kind: 'done', host, title,
                body: `${s.detail ? `${s.detail}\n` : ''}${fmt('Took %1 · %2', duration(took), s.cwdShort)}${where}`,
                icon: 'done',
            });
            sound(s.reason === 'failed' ? 'failed' : 'done');
        }
    }

    // A source you stopped showing (an unticked host): picked again later, it starts afresh
    forget(source) {
        delete this.lastStates[source];
        delete this.turnStarts[source];
        delete this.lastEnded[source];
        delete this.primed[source];
        for (const key of Object.keys(this.lastWaitingAlert)) {
            if (keyOfSource(key, source))
                delete this.lastWaitingAlert[key];
        }
        for (const key of Object.keys(this.lastWindows)) {
            if (key.startsWith(`${source}|`))
                delete this.lastWindows[key];
        }
        delete this.lastStops[source];
        delete this.lastOverlaps[source];
    }

    // A chat's own news, for its pet: the usage limit that stopped it reset
    // (it can go on), or it and another chat began changing the same files
    // (the first check only learns). notices: an array that gets one
    // notification per account whose stopped chats can go on now
    chatEvents(source, groupList, host, notices = null) {
        const events = [];
        const stopsBefore = this.lastStops[source], overlapsBefore = this.lastOverlaps[source];
        const stops = {}, overlaps = {};
        for (const g of groupList) {
            const freed = [];
            for (const s of g.sessions) {
                const pk = petKeyOf(s, host);
                if (s.stopped && s.stopped.kind === 'limit' && !(pk in stops)) {
                    stops[pk] = !!s.stopped.over;
                    if (stopsBefore && stopsBefore[pk] === false && s.stopped.over) {
                        events.push({kind: 'reset', text: fmt('%1 can go on!', s.name), key: pk});
                        freed.push(s);
                    }
                }
                for (const o of s.overlaps || []) {
                    // (by chat: one listed twice, open on two accounts, is one chat)
                    const pair = [s.chatId || s.sessionId, o.chatId || o.sessionId].sort().join('|');
                    if (pair in overlaps)
                        continue;
                    overlaps[pair] = true;
                    if (overlapsBefore && !(pair in overlapsBefore))
                        events.push({kind: 'waiting', text: fmt('%1 and %2 change the same files!', s.name, o.name), key: pk});
                }
            }
            if (freed.length && notices)
                notices.push(limitResetNotice(source, g, freed, host));
        }
        this.lastStops[source] = stops;
        this.lastOverlaps[source] = overlaps;
        return events;
    }

    // A limit that dropped a lot since the last poll was reset: the pets cheer
    celebrateResets(source, groupList) {
        const events = [];
        const next = Object.assign({}, this.lastWindows);
        for (const g of groupList) {
            for (const w of g.limits ? g.limits.windows : []) {
                const key = `${source}|${g.id}/${w.key}`;
                if (key in this.lastWindows && this.lastWindows[key] >= 25 && w.pct < this.lastWindows[key] - 20)
                    events.push({kind: 'reset', text: fmt('%1 limit reset!', w.label), key: ''});
                next[key] = w.pct;
            }
        }
        this.lastWindows = next;
        return events;
    }
}

// "work: the usage limit reset / fix-parser can go on", for the chats of an
// account a usage limit stopped (Plasma's trackLimitStops)
function limitResetNotice(source, g, freed, host) {
    const names = freed.slice(0, 4).map(s => s.name).join(', ') + (freed.length > 4 ? ` +${freed.length - 4}` : '');
    return {
        key: `${source ? `${source}|` : ''}limit-reset:${g.id}`, session: freed[0], kind: 'reset', host,
        title: fmt('%1: the usage limit reset', host ? fmt('%1: %2', hostLabel(host), g.name) : g.name),
        body: freed.length === 1 ? fmt('%1 can go on.', names) : fmt('%1 chats can go on: %2', freed.length, names),
        icon: 'done',
    };
}

// Which notification keys belong to a source: "" (this computer) has no
// "|" in its keys, "ssh:<host>" prefixes them
export function keyOfSource(key, source) {
    return source ? key.startsWith(`${source}|`) : key.indexOf('|') < 0;
}

// The helpers print one JSON line; anything else becomes an error message
export function helperResult(stdout, stderr) {
    try {
        return JSON.parse(stdout);
    } catch {
        const lines = (stderr || '').trim().split('\n');
        return {ok: false, message: lines[lines.length - 1] || 'the helper gave no answer'};
    }
}

// The status script's answer: {status} or {error}
export function statusResult(stdout, stderr) {
    let parsed;
    try {
        parsed = JSON.parse(stdout);
    } catch {
        const lines = (stderr || '').trim().split('\n');
        return {error: fmt('Status script failed: %1', lines[lines.length - 1] || 'no output')};
    }
    if (!parsed || typeof parsed !== 'object')
        return {error: fmt('Status script failed: %1', 'no answer')};
    if (!parsed.ok)
        return {error: fmt('Status unavailable: %1', parsed.error)};
    if (!Array.isArray(parsed.groups))
        return {error: fmt('Status unavailable: %1', 'an answer without accounts')};
    const errors = Array.isArray(parsed.errors) ? parsed.errors : [];
    return {status: parsed, errorText: errors.join('\n')};
}

// A host's answer on this computer's clock: its times ("since", "last
// active", resets) are its own clock's, which may be off from ours
export function toLocalClock(result, offset) {
    if (!result || Math.abs(offset) < 5000)
        return result;   // network delay, or close enough
    const at = t => (typeof t === 'number' ? t + offset : t);
    const shift = (o, keys) => {
        if (o) {
            for (const k of keys)
                o[k] = at(o[k]);
        }
    };
    result = JSON.parse(JSON.stringify(result));
    result.generatedAt = at(result.generatedAt);
    for (const g of result.groups || []) {
        for (const s of g.sessions || []) {
            shift(s, ['since', 'startedAt']);
            shift(s.peek, ['at']);
            shift(s.peek && s.peek.recap, ['at']);
            shift(s.stopped, ['at', 'resetsAt']);
            shift(s.movedFrom, ['at']);
            shift(s.plan, ['updatedAt']);
            shift(s.stats, ['startedAt', 'lastAt']);
            for (const a of (s.agents && s.agents.tree) || [])
                shift(a, ['started', 'updated']);
        }
        for (const c of (g.recent || []).concat(g.sharedHere || [], g.starred || [])) {
            shift(c, ['lastActive', 'since']);
            shift(c.recap, ['at']);
            shift(c.stopped, ['at', 'resetsAt']);
        }
        for (const plan of (g.plans || []).concat(g.starredPlans || []))
            shift(plan, ['updatedAt']);
        if (g.limits) {
            shift(g.limits, ['updatedAt']);
            for (const w of g.limits.windows || []) {
                shift(w, ['resetsAt']);
                shift(w.forecast, ['fullAt']);
            }
        }
    }
    return result;
}

// The new-chat choices of an account: its recent folders (here without the
// home folder, which "Choose folder…" covers; an SSH host's can't be browsed
// from here, so its home folder stays in the list)
export function newChatFolders(group, host) {
    const folders = host ? group.projects.slice() : group.projects.filter(f => f.short !== '~');
    if (host && !folders.some(f => f.short === '~'))
        folders.push({path: '', short: '~', newChatCommand: group.homeChatCommand || ''});
    return folders;
}

// Recent chats and ★ Starred chats show a page at a time (the Recent chats
// setting; 5 when it's 0), "Show N more" the next page; folded again, a list
// shows its first page. The status lists a page more recent chats than show
// (so the next one is there at once) and counts them all (recentCount); only
// the starred plans and CLAUDE.md of the plans and memories (Plasma lists the
// rest in its Projects tab).
export function pageSize(recentChats) {
    return recentChats > 0 ? recentChats : 5;
}

export function recentArgs(recentChats) {
    return ['--recent', String(recentChats > 0 ? 2 * recentChats : 0), '--plans', '0', '--memories', '0'];
}

// An account's Recent chats as they show, pages of size: the status' and,
// past those, the ones a check that listed more has (more: {recent, asked};
// fewer than it asked for: that's all of them). all: the chats there are,
// count: of how many, shown: how many show; fetch: how many a check should
// list now (unfolded and a page more than show wanted but not there), else 0.
export function recentPage(group, more, size, pages, open) {
    const recent = group.recent || [];
    let all = recent;
    if (more) {
        const listed = new Set(recent.map(c => c.sessionId));
        all = recent.concat(more.recent.filter(c => !listed.has(c.sessionId)));
    }
    const count = more && more.recent.length < more.asked ? all.length : Math.max(group.recentCount || 0, recent.length);
    const shown = Math.min(all.length, size * pages);
    const wanted = open ? Math.min(count, size * (pages + 1)) : 0;
    return {all, count, shown, fetch: all.length < wanted ? wanted : 0};
}

// A paged list's title: "Recent chats (5 of 23)", all shown "Recent chats (23)"
export function pagedTitle(title, shown, count) {
    return shown < count ? fmt('%1 (%2 of %3)', title, shown, count) : fmt('%1 (%2)', title, count);
}

// "Show N more" under a list, and its tooltip
export function showMoreText(size, shown, count) {
    return fmt('Show %1 more', Math.min(size, count - shown));
}

export function showMoreTip(size, shown, count) {
    return [showMoreText(size, shown, count), fmt('%1 of %2 show. Folded again, the list shows its first ones again.', shown, count)];
}

// What a chat's ☆ / ★ says
export function starHint(starred) {
    return starred ? "A starred chat stays listed under its account's ★ Starred chats, however old it is. Click to unstar it."
        : "A starred chat stays listed under its account's ★ Starred chats, however old it is.";
}

// The pets of an account's stage: one per chat, the ones that need you or
// work first
export function stageChats(group, host) {
    const rank = {waiting: 0, working: 1, idle: 2, done: 3};
    const out = [], seen = {};
    for (const s of group.sessions) {
        const key = petKeyOf(s, host);
        if (key in seen)
            continue;
        seen[key] = true;
        out.push({key, session: s, host, order: out.length});
    }
    return out.sort((a, b) => rank[a.session.state] - rank[b.session.state] || a.order - b.order);
}

// Accounts close to their 5-hour limit, e.g. "work: 100% of the 5-hour limit!"
export function highUsageText(groups) {
    const parts = [];
    for (const g of groups) {
        for (const w of g.limits ? g.limits.windows : []) {
            if (w.key === 'five_hour' && w.pct >= 90)
                parts.push(fmt('%1: %2% of the 5-hour limit!', groupLabel(g), Math.round(w.pct)));
        }
    }
    return parts.join(' ');
}

export function maxFiveHour(groups) {
    let m = 0;
    for (const g of groups) {
        for (const w of g.limits ? g.limits.windows : []) {
            if (w.key === 'five_hour')
                m = Math.max(m, w.pct);
        }
    }
    return m;
}

// A working session whose context window is nearly full and that has no
// pet of its own to show it, e.g. "fix parser: context 91% full"
export function contextFullText(groups, petColors) {
    for (const g of groups) {
        for (const s of g.sessions) {
            if (s.state === 'working' && s.context !== null && s.context >= 85 && !(petKeyOf(s, g.host) in petColors))
                return fmt('%1: context %2% full', s.name, Math.round(s.context));
        }
    }
    return '';
}

export function firstWaitingName(groups) {
    for (const g of groups) {
        for (const s of g.sessions) {
            if (s.state === 'waiting')
                return s.name;
        }
    }
    return '';
}

// Which window jump.py wants raised (raiser.js; on Plasma its KWIN_SCRIPT).
// want: {pids, caption, require, prefer}. The window owned by the nearest of
// pids wins (pids go from the process up to its ancestors); a title with
// caption first (only those if require), then one with prefer.
export function pickWindow(windows, want) {
    // pid 0: a window whose process isn't known (it would match anything's)
    const pids = Array.isArray(want.pids) ? want.pids.filter(p => Number.isInteger(p) && p > 0).slice(0, 64) : [];
    const caption = typeof want.caption === 'string' ? want.caption : '';
    const prefer = typeof want.prefer === 'string' ? want.prefer : '';
    let best = null, bestScore = -1;
    for (const w of windows) {
        const rank = pids.indexOf(w.pid);
        if (rank < 0)
            continue;
        const title = w.title || '';
        const hit = caption !== '' && title.includes(caption);
        if (want.require && !hit)
            continue;
        let score = 100 - rank;   // the nearest ancestor owning a window wins
        if (hit)
            score += 1000;
        if (prefer && title.includes(prefer))
            score += 500;
        if (score > bestScore) {
            best = w;
            bestScore = score;
        }
    }
    return best;
}

// Chats open in a terminal or in VS Code (port of main.qml's cliHere,
// openInVscode, terminalHint and vscodeHint): one choice for new and recent
// chats. A status says whether there's a claude command (result.cli); when
// unsure (no answer yet, or an error looking), it counts as there.
export function cliInstalled(result) {
    return !result || !result.cli || result.cli.installed !== false;
}

// VS Code when you picked it, or when there's no claude command but VS
// Code's Claude runs on this account
export function openInVscode(group, vscodeInstalled, cliHere, preferVscode) {
    if (!vscodeInstalled || !group.vscodeHere)
        return false;
    return preferVscode || !cliHere;
}

// resuming: for the recent chats' switch (they reopen) instead of new chats'
export function terminalHint(host, cliHere, resuming = false) {
    if (!cliHere) {
        return containerOf(host) ? fmt("Claude Code's claude command isn't installed in %1: it isn't on PATH there, in ~/.local/bin, npm's or nvm's folders, nor on the login shell's PATH.", hostLabel(host))
            : host ? fmt("Claude Code's claude command isn't installed on %1: it isn't on PATH there, in ~/.local/bin, npm's or nvm's folders, nor on the login shell's PATH.", host)
            : "Claude Code's claude command isn't installed here: it isn't on PATH, in ~/.local/bin, npm's or nvm's folders, nor on your login shell's PATH.";
    }
    if (resuming) {
        return containerOf(host) ? fmt('Reopens the chat in %1 in a terminal (claude --resume, in the container).', hostLabel(host))
            : host ? fmt('Reopens the chat on %1 in a terminal (ssh, claude --resume).', host)
            : 'Reopens the chat in a terminal (claude --resume).';
    }
    return containerOf(host) ? fmt('A terminal opens with Claude in %1 in the folder you click.', hostLabel(host))
        : host ? fmt('A terminal opens with Claude on %1 (ssh) in the folder you click.', host)
        : 'A terminal opens with Claude in the folder you click.';
}

// VS Code's Claude extension runs on one account (status.vscode.on; an SSH
// host's: its ~/.claude), so its button only works there
export function vscodeHint(group, host, status, resuming = false) {
    const how = containerOf(host) ? 'Dev Containers' : 'Remote-SSH';
    const name = hostLabel(host);
    if (!(status && status.vscode && status.vscode.installed === true)) {
        return host ? fmt("VS Code would connect to %1 (%2), but it isn't installed on this computer.", name, how)
            : "VS Code isn't installed on this computer.";
    }
    if (group.vscodeHere && resuming) {
        return host ? fmt("Opens VS Code connected to %1 (%2) in the chat's folder, and the chat in its Claude Code panel.", name, how)
            : "Opens the chat's folder in VS Code, and the chat in its Claude Code panel.";
    }
    if (group.vscodeHere) {
        return host ? fmt('Opens VS Code connected to %1 (%2) with a new chat in its Claude Code panel.', name, how)
            : 'Opens the folder in VS Code with a new chat in its Claude Code panel.';
    }
    if (host)
        return fmt("VS Code's Claude on %1 runs on another account (the host's ~/.claude).", name);
    const on = status.vscode.on;
    return on ? fmt("VS Code's Claude runs on %1, not %2: switch its profile to use this account there.", on, group.title)
        : "VS Code's Claude doesn't run on this account.";
}


// ---------------------------------------------------------------- what a chat is doing

// The line under a chat's folder: what it needs, what it's doing, or what
// Claude said last ({text, title, full}), or null. A finished background
// session keeps its result (detail).
export function peekLine(s) {
    const peek = s.peek || null;
    const activity = (peek && peek.activity) || (s.tasks && s.tasks.current) || '';
    const reply = peek && peek.replyLine ? fmt('Claude: %1', peek.replyLine) : '';
    // (kind: its color, as Plasma's: working the working color, waiting
    // orange, what stopped it red, the rest dim)
    if (s.state === 'waiting') {
        if (s.detail)
            return {text: s.detail, title: 'What it needs', full: s.detail, kind: 'needs'};
        return activity ? {text: activity, title: 'What it needs', full: activity, kind: 'needs'} : null;
    }
    if (s.state === 'working')
        return activity ? {text: `▸ ${activity}`, title: 'Working on', full: activity, kind: 'activity'} : null;
    if (s.stopped) {
        const text = stopText(s.stopped);
        return {text, title: 'What stopped it', full: text, kind: s.stopped.over ? 'reply' : 'stopped'};
    }
    if (s.state === 'done' && s.detail)
        return {text: s.detail, title: 'Result', full: s.detail, kind: 'result'};
    return reply ? {text: reply, title: "Claude's last reply", full: peek.reply || peek.replyLine, kind: 'reply'} : null;
}

// The line under a chat that a usage limit or an expired login stopped: what to do
export function stopText(stopped) {
    if (stopped.kind === 'login')
        return "Claude's login expired. Log in again (/login), then tell it to go on.";
    if (stopped.over)
        return 'The limit it hit has reset: open it and tell Claude to go on.';
    return stopped.text || '';
}

// Is there more to show when the peek line is clicked?
export function canPeek(s, remoteHost) {
    const peek = s.peek || null;
    return !!((peek && (peek.prompt || peek.reply)) || (s.tasks && s.tasks.total) || (s.changes && !remoteHost)
        || (s.stats && chatRecapText(s.stats)));
}

// At most maxLines lines and maxChars characters, with … when cut
export function clampText(text, maxLines = 12, maxChars = 900) {
    let lines = (text || '').split('\n');
    let cut = false;
    if (lines.length > maxLines) {
        lines = lines.slice(0, maxLines);
        cut = true;
    }
    let out = lines.join('\n');
    if (out.length > maxChars) {
        out = out.slice(0, maxChars);
        cut = true;
    }
    return cut ? `${out.trimEnd()}…` : out;
}

export function taskMark(status) {
    return status === 'completed' ? '✓' : status === 'in_progress' ? '▸' : '○';
}

export function tasksTooltip(tasks, open) {
    const lines = [];
    if (tasks.current)
        lines.push(fmt('Now: %1', tasks.current));
    for (const t of tasks.items)
        lines.push(`${taskMark(t.status)} ${t.subject}`);
    if (tasks.total > tasks.items.length)
        lines.push(fmt('… and %1 more', tasks.total - tasks.items.length));
    lines.push(fmt('Click to %1 the list.', open ? 'hide' : 'show'));
    return [fmt('Tasks: %1 of %2 done', tasks.done, tasks.total), lines.join('\n')];
}

export function changesTag(changes) {
    return fmt('±%1', changes.count);
}

// (vscodeInstalled: VS Code shows them side by side, so without it they
// can't be compared: Plasma's canCompare)
export function changesTooltip(changes, remoteHost, vscodeInstalled = true) {
    const lines = changes.files.slice();
    if (changes.count > changes.files.length)
        lines.push(fmt('… and %1 more', changes.count - changes.files.length));
    lines.push('');
    lines.push(remoteHost
        ? fmt('On %1: comparing them works for chats on this computer.', hostLabel(remoteHost))
        : !vscodeInstalled ? 'Install VS Code to compare them side by side.'
            : 'Click to compare them with how they were before the chat, side by side in VS Code.');
    return [plural(changes.count, '%1 file changed', '%1 files changed'), lines.join('\n')];
}

// ---------------------------------------------------------------- subagents

// A row's popup state (details, subagents, stop asked) is kept by its chat,
// not its key: a background session that ends goes from live to job
export function rowKey(s, remoteHost) {
    return `${remoteHost ? `${remoteHost}|` : ''}${s.profileDir}/${s.chatId || s.sessionId}`;
}

// Popup state of one subagent (unfolded or not): by its row's key and its id
export function agentKey(rowKey, agent) {
    return `${rowKey}|${agent.id}`;
}

// "12 tool calls · 45.2k tokens": what's known of it so far
export function agentSummaryText(a) {
    const parts = [];
    if (a.toolCalls !== null && a.toolCalls !== undefined)
        parts.push(plural(a.toolCalls, '%1 tool call', '%1 tool calls'));
    if (a.tokens)
        parts.push(fmt('%1 tokens', formatTokens(a.tokens)));
    return parts.join(' · ');
}

// Its last steps, oldest first ({text, current}); a running one is on the newest
export function agentStepLines(a) {
    const steps = a.steps || [];
    return steps.map((step, i) => ({text: `▸ ${step}`, current: a.status === 'running' && i === steps.length - 1}));
}

// The tooltip of its line, which unfolds it
export function agentTooltip(a, open) {
    const what = a.activity ? `${a.activity}\n\n` : '';
    return [a.description || a.type, what + fmt('Click to %1 its task, its last steps and its report.', open ? 'hide' : 'show')];
}

export function agentRunTooltip(remoteHost) {
    const text = "Its task, every step with the start of each result, and its report, as a Markdown file in your app for those. Claude Code itself can't open a subagent from outside.";
    return ['Open the whole run', remoteHost ? `${text}\n${containerOf(remoteHost) ? fmt('Fetched from %1.', hostLabel(remoteHost))
        : fmt('Fetched from %1 over ssh.', remoteHost)}` : text];
}

// The helper that saves a subagent's whole run as Markdown and opens it
// ({script, args}): jump.py here, remote.py for a chat on an SSH host
export function agentRunCommand(s, a, remoteHost = '') {
    const chat = s.chatId || s.sessionId;
    if (remoteHost)
        return {script: 'remote.py', args: ['--agent-run', remoteHost, chat, a.id, ...s.profileDir ? [s.profileDir] : []]};
    return {script: 'jump.py', args: ['--agent-run', a.id, '--chat', chat, ...s.profileDir ? ['--profile', s.profileDir] : []]};
}

// ---------------------------------------------------------------- usage forecast

// Where the bar's lighter part ends: the usage when the window resets, at your pace
export function projectedPct(w) {
    const f = w.forecast;
    if (!f || typeof f.atReset !== 'number')
        return w.pct;
    return Math.max(w.pct, Math.min(100, f.atReset));
}

// The line under a bar when the window would run out before it resets
export function forecastWarning(w, now) {
    const f = w.forecast;
    if (!f || !f.fullAt || !w.resetsAt)
        return '';
    return fmt('At this pace: full in %1, %2 before it resets', duration(f.fullAt - now), duration(w.resetsAt - f.fullAt));
}

// (Plasma's forecastText)
export function forecastTooltip(w, now) {
    const f = w.forecast;
    if (!f)
        return null;
    const when = ms => (ms - now > 20 * 3600000 ? `${WEEKDAYS[new Date(ms).getDay()]} ${clock(ms)}` : clock(ms));
    const lines = [f.basis === 'hour' ? fmt('Your pace over the last hour: %1% an hour.', f.rate.toFixed(1))
        : fmt('Your pace in this window so far: %1% an hour.', f.rate.toFixed(1))];
    if (f.fullAt && w.resetsAt)
        lines.push(fmt('At this pace it runs out at %1, %2 before it resets.', when(f.fullAt), duration(w.resetsAt - f.fullAt)));
    else if (w.pct < 100)
        lines.push(fmt('At this pace: about %1% when it resets (the faded part of the bar).', Math.round(f.atReset)));
    lines.push(fmt('An even pace through the window would be at %1% by now (the mark).', Math.round(f.evenPct)));
    return [fmt('%1 limit: %2% used', w.label, Math.round(w.pct)), lines.join('\n')];
}

// ---------------------------------------------------------------- the chat that needs you

// The key of a session on the dashboard, as Tracker.track names it
export function sessionKey(s, host) {
    return petKeyOf(s, host);
}

// The chats the hotkey goes to, in order: the ones waiting for you (the one
// waiting longest first), then the ones that finished a turn you haven't
// seen (newest first). groups: this computer's and the hosts' (with .host).
export function chatsNeedingYou(groups, unseen = {}) {
    const waiting = [], done = [], seen = new Set();
    for (const g of groups) {
        for (const s of g.sessions) {
            const key = sessionKey(s, g.host);
            if (seen.has(key))
                continue;   // the chat's most urgent row came first
            seen.add(key);
            const entry = {key, session: s, host: g.host || ''};
            if (s.state === 'waiting')
                waiting.push(entry);
            else if (unseen[key] === 'done' && s.state !== 'working')
                done.push(entry);
        }
    }
    waiting.sort((a, b) => (a.session.since || 0) - (b.session.since || 0));
    done.sort((a, b) => (b.session.since || 0) - (a.session.since || 0));
    return waiting.concat(done);
}

// Which of them the hotkey goes to now: the first, or the one after the
// last one it went to if that was less than windowMs ago; -1 for none
export function nextChatIndex(list, last, now, windowMs = 30000) {
    if (!list.length)
        return -1;
    if (last && now - last.at < windowMs) {
        const i = list.findIndex(c => c.key === last.key);
        if (i >= 0)
            return (i + 1) % list.length;
    }
    return 0;
}

// ---------------------------------------------------------------- while you were away

// What the dashboard looked like when the screen locked: {sessions: {key:
// {state, name}}, windows: {key: {resetsAt}}}. groups: this computer's and the hosts'.
export function awaySnapshot(groups) {
    const sessions = {}, windows = {};
    for (const g of groups) {
        for (const s of g.sessions)
            sessions[sessionKey(s, g.host)] = {state: s.state, name: s.name};
        for (const w of g.limits ? g.limits.windows : [])
            windows[`${g.host || ''}|${g.id}/${w.key}`] = {resetsAt: w.resetsAt || null};
    }
    return {sessions, windows};
}

function nameList(names, max = 4) {
    const shown = names.slice(0, max).join(', ');
    return names.length > max ? fmt('%1 +%2', shown, names.length - max) : shown;
}

// One summary for when you come back: {title, body, first: the chat that
// waited longest (chatsNeedingYou entry) or null}, or null when you were away
// less than minMinutes or nothing happened. away: {lockedAt, snapshot}.
export function awayDigest(away, groups, now, minMinutes) {
    const awayMs = now - away.lockedAt;
    if (!(awayMs >= minMinutes * 60000))
        return null;
    const before = away.snapshot.sessions;
    const named = (s, host) => (host ? fmt('%1 (%2)', s.name, hostLabel(host)) : s.name);
    const finished = [], failed = [], stopped = [], limited = [], loggedOut = [], resets = [];
    for (const g of groups) {
        for (const s of g.sessions) {
            const prev = before[sessionKey(s, g.host)];
            const ended = s.state === 'idle' || s.state === 'done';
            const ran = prev ? prev.state === 'working' || prev.state === 'waiting'
                : (s.since || 0) >= away.lockedAt;   // a chat that came and finished meanwhile
            const stop = stopOf(s);
            if (!ended || !ran)
                continue;
            (stop === 'limit' ? limited : stop === 'login' ? loggedOut : s.reason === 'failed' ? failed
                : s.reason === 'stopped' ? stopped : finished).push(named(s, g.host));
        }
        for (const w of g.limits ? g.limits.windows : []) {
            const prev = away.snapshot.windows[`${g.host || ''}|${g.id}/${w.key}`];
            if (prev && prev.resetsAt && prev.resetsAt > away.lockedAt && prev.resetsAt <= now)
                resets.push(fmt('%1 limit reset (%2)', w.label, groupLabel(g)));
        }
    }
    const waiting = chatsNeedingYou(groups);
    if (!waiting.length && !finished.length && !failed.length && !stopped.length && !limited.length && !loggedOut.length)
        return null;
    const lines = waiting.slice(0, 3).map(c => fmt('Needs you: %1 (waiting %2)', named(c.session, c.host),
        duration(now - (c.session.since || now))));
    if (waiting.length > 3)
        lines.push(plural(waiting.length - 3, '+%1 more needs you', '+%1 more need you'));
    if (finished.length)
        lines.push(fmt('Finished: %1', nameList(finished)));
    if (failed.length)
        lines.push(fmt('Failed: %1', nameList(failed)));
    if (stopped.length)
        lines.push(fmt('Stopped: %1', nameList(stopped)));
    if (limited.length)
        lines.push(fmt('Hit the usage limit: %1', nameList(limited)));
    if (loggedOut.length)
        lines.push(fmt('Login expired: %1', nameList(loggedOut)));
    lines.push(...resets);
    return {title: fmt('While you were away (%1)', duration(awayMs)), body: lines.join('\n'), first: waiting[0] || null};
}

// ---------------------------------------------------------------- stats

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "2026-10-15" -> a local Date (no time zone shift)
function dayDate(day) {
    const [y, m, d] = String(day).split('-').map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
}

// The letter under a day's bar: M, T, W, …
export function statsDayLetter(day) {
    return WEEKDAYS[dayDate(day).getDay()][0];
}

// A day's bar, on hover: "Tue 15 Oct: 446.8M tokens (1.7M out) · 6 chats · 73 prompts"
export function statsDayText(d) {
    const date = dayDate(d.day);
    const parts = [fmt('%1 tokens (%2 out)', formatTokens(d.total), formatTokens(d.output)),
        plural(d.chats, '%1 chat', '%1 chats'), plural(d.prompts, '%1 prompt', '%1 prompts')];
    return `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}: ${parts.join(' · ')}`;
}

// "14 days: 997.4M tokens (3.2M out) · 15 chats · 253 prompts · 5 active days"
export function statsSummaryText(stats) {
    const s = stats.sum;
    return [fmt('%1 days: %2 tokens (%3 out)', stats.days.length, formatTokens(s.total), formatTokens(s.output)),
        plural(s.chats, '%1 chat', '%1 chats'), plural(s.prompts, '%1 prompt', '%1 prompts'),
        plural(s.activeDays, '%1 active day', '%1 active days')].join(' · ');
}

// The bars' heights in px, out of maxPx for the busiest day; 0 for a day without tokens
export function statsBarHeights(stats, maxPx) {
    const top = Math.max(0, ...stats.days.map(d => d.total));
    return stats.days.map(d => (d.total > 0 && top > 0 ? Math.max(2, Math.round(maxPx * d.total / top)) : 0));
}

// A busy folder's numbers: "669.8M · 146 prompts"
export function statsProjectText(p) {
    const parts = [];
    if (p.total > 0)
        parts.push(formatTokens(p.total));
    if (p.prompts > 0)
        parts.push(plural(p.prompts, '%1 prompt', '%1 prompts'));
    return parts.join(' · ');
}

// "Opus 5.5 >99% · Sonnet 5.5 <1%": under one percent "<1%", between 99 and
// 100 ">99%" (not a rounded "100%" beside another's "<1%"), as Plasma's
export function statsModelsText(stats) {
    const all = stats.models.reduce((n, m) => n + m.total, 0);
    if (!all)
        return '';
    return stats.models.map(m => {
        const pct = 100 * m.total / all;
        return `${m.model} ${pct <= 0 ? '0%' : pct < 1 ? '<1%' : pct > 99 && pct < 100 ? '>99%' : `${Math.round(pct)}%`}`;
    }).join(' · ');
}

// A chat's recap, at the bottom of its peek box: "3 prompts · worked 51m ·
// 278 tool calls (Bash 236, Read 23, Write 5) · 85.3M tokens (249.7k out)",
// with what it would cost at API prices when the status line says
export function chatRecapText(stats, costUsd = null) {
    const parts = [];
    if (stats.prompts)
        parts.push(plural(stats.prompts, '%1 prompt', '%1 prompts'));
    if (stats.workedMs > 0)
        parts.push(fmt('worked %1', stats.workedMs < 60000 ? '<1m' : duration(stats.workedMs)));
    if (stats.toolCalls) {
        const top = stats.tools.slice(0, 3).map(([name, n]) => `${name} ${n}`).join(', ');
        parts.push(plural(stats.toolCalls, '%1 tool call', '%1 tool calls') + (top ? ` (${top})` : ''));
    }
    if (stats.tokens && stats.tokens.total)
        parts.push(fmt('%1 tokens (%2 out)', formatTokens(stats.tokens.total), formatTokens(stats.tokens.output)));
    if (typeof costUsd === 'number' && costUsd > 0)
        parts.push(fmt('$%1 at API prices', costUsd.toFixed(2)));
    return parts.join(' · ');
}

// What of an account's stats the popup draws (for its render signature):
// moving numbers only rebuild it where the text or a bar changes
export function statsSignature(stats) {
    return [statsSummaryText(stats), statsBarHeights(stats, 48), stats.days.map(statsDayText),
        stats.projects.map(p => [p.name, statsProjectText(p)]), statsModelsText(stats)];
}

// The recap's tooltip: its tokens in full, when it started and was last busy,
// and every tool it used
export function chatRecapTooltip(stats, costUsd, now) {
    const t = stats.tokens || {};
    const lines = [fmt('Tokens: %1 in · %2 out · %3 cache read · %4 cache write (subagents included)',
        formatTokens(t.input || 0), formatTokens(t.output || 0), formatTokens(t.cacheRead || 0), formatTokens(t.cacheWrite || 0))];
    if (stats.tools.length)
        lines.push(fmt('Tools: %1', stats.tools.map(([name, n]) => `${name} ${n}`).join(', ')));
    if (stats.workedMs > 0)
        lines.push(fmt('Claude worked %1: from each of your prompts to its last step.', duration(stats.workedMs)));
    if (stats.startedAt)
        lines.push(fmt('Started %1 ago, last busy %2 ago.', duration(now - stats.startedAt), duration(now - (stats.lastAt || now))));
    if (typeof costUsd === 'number' && costUsd > 0)
        lines.push(fmt('At API prices this chat would cost $%1 (from the status line; a plan pays differently).', costUsd.toFixed(2)));
    return lines.join('\n');
}

// ---------------------------------------------------------------- the week
// The Recap tab (ui/weekView.js), from the recap of week.py; as the Plasma
// widget's WeekView.qml and the VS Code extension's src/shared/week.ts say it.

const WEEKDAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
    'November', 'December'];

function clock(ms) {
    const d = new Date(ms);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// A chat Claude moved to the background under a new id (its row's movedFrom), in a line, or ''
export function movedText(s) {
    const m = s && s.movedFrom;
    if (!m)
        return '';
    return (m.at ? `Moved to the background at ${clock(m.at)}: Claude goes on with it under a new id.`
        : 'Moved to the background: Claude goes on with it under a new id.') + '\n\n';
}

// 3h 5m, 45m: a week of work reads better in hours than in days
export function hoursText(ms) {
    const m = Math.round(Math.max(0, ms) / 60000);
    return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function grouped(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// The amounts are API prices in US dollars; in another currency (the
// recap-currency setting) week.py sends the European Central Bank's rate of the day
const USD = {code: 'USD', rate: 1};
const SYMBOLS = {USD: '$', EUR: '€', GBP: '£', JPY: '¥', CNY: '¥', INR: '₹', KRW: '₩', ILS: '₪', TRY: '₺', PHP: '₱', THB: '฿'};
const WHOLE_UNITS = ['JPY', 'KRW', 'HUF', 'ISK', 'IDR'];

export function weekCurrency(recap) {
    const c = recap ? recap.currency : null;
    return c && !c.error && c.rate > 0 && /^[A-Z]{3}$/.test(c.code) ? c : USD;
}

export function moneyText(usd, cur = USD) {
    const amount = (usd || 0) * cur.rate;
    const symbol = SYMBOLS[cur.code];
    const put = text => (symbol ? symbol + text : `${text} ${cur.code}`);
    if (!amount)
        return put('0');
    const whole = amount >= 100 || WHOLE_UNITS.includes(cur.code);
    if (amount < (whole ? 1 : 0.01))
        return `<${put(whole ? '1' : '0.01')}`;
    const [units, cents] = amount.toFixed(whole ? 0 : 2).split('.');
    return put(`${grouped(units)}${cents ? `.${cents}` : ''}`);
}

// "Sat 24 Oct"
export function weekDayLabel(day) {
    const d = dayDate(day);
    return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// Where a moment is on its day's row (start to end: its local midnights),
// 0 to 1, by that day's own wall clock, as Plasma's and VS Code's: on a day
// the clocks change (23 or 25 hours) 18:00 is still at 3/4, under the 18 over
// the rows (the hour that comes twice drawn twice in one place, the one it
// skips not at all)
export function weekDayPlace(d, ms) {
    if (ms <= d.start)
        return 0;
    if (ms >= d.end)
        return 1;
    const t = new Date(ms);
    return (t.getHours() + (t.getMinutes() + (t.getSeconds() + t.getMilliseconds() / 1000) / 60) / 60) / 24;
}

// and back: the moment at a place of its row
export function weekDayMoment(d, place) {
    const s = new Date(d.start);
    const ms = new Date(s.getFullYear(), s.getMonth(), s.getDate(), 0, 0, 0, Math.round(Math.max(0, Math.min(1, place)) * 86400000)).getTime();
    return Math.max(d.start, Math.min(d.end, ms));
}

// "Sat 24": a timeline row's day
export function weekRowDay(day, weeks = false) {
    const d = dayDate(day);
    return weeks ? shortDay(day) : `${WEEKDAYS[d.getDay()]} ${d.getDate()}`;
}

// "Wed 14:05": when a turn started
export function weekWhenText(ms) {
    return `${WEEKDAYS[new Date(ms).getDay()]} ${clock(ms)}`;
}

function shortDay(day) {
    const d = dayDate(day);
    return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// "24 Oct 2026" (Plasma's "d MMM yyyy")
function dateText(day) {
    const d = dayDate(day);
    return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function weekPeriodText(recap) {
    if (recap.span === 'day') {
        const day = `${WEEKDAYS[dayDate(recap.from).getDay()]} ${shortDay(recap.from)}`;
        return recap.back === 0 ? `Today · ${day}` : recap.back === 1 ? `Yesterday · ${day}` : day;
    }
    if (recap.span === 'all')
        return recap.first ? `Everything since ${dateText(recap.first)}` : 'Everything';
    const span = `${shortDay(recap.from)} – ${shortDay(recap.to)}`;
    return recap.back === 0 ? `Last 7 days · ${span}` : span;
}

// What the period line says before the answer for a span comes
export function weekPeriodWaiting(span, back) {
    return back !== 0 ? '' : span === 'day' ? 'Today' : span === 'all' ? 'Everything' : 'Last 7 days';
}

// The 7 days before, when there was anything in them
function previousOf(recap) {
    const p = recap.previous;
    return p && (p.workedMs || p.prompts || p.cost) ? p : null;
}

// The change against the 7 days before: "+4h 44m", "−$12"
export function weekDeltaText(now, before, kind, cur = USD) {
    if (before === null || before === undefined)
        return '';
    const d = now - before;
    const abs = Math.abs(d);
    if (kind === 'time' ? abs < 60000 : kind === 'money' ? abs < 0.01 : d === 0)
        return 'same as before';
    return (d > 0 ? '+' : '−') + (kind === 'time' ? hoursText(abs) : kind === 'money' ? moneyText(abs, cur) : grouped(abs));
}

// One number over the 5 weeks up to these days, these last (null: older than what's kept)
export function weekTrend(recap, key) {
    return (recap.trend || []).map(w => (w ? w[key] || 0 : null));
}

export function weekTiles(recap) {
    const s = recap.sum;
    const p = previousOf(recap);
    const cur = weekCurrency(recap);
    const shown = (v, kind) => (kind === 'time' ? hoursText(v) : kind === 'money' ? moneyText(v, cur) : grouped(v));
    const day = recap.span === 'day';
    const before = (v, kind) => (p ? `\n${day ? 'The day before' : 'The 7 days before'}: ${shown(v, kind)}` : '');
    const weeks = (key, kind) => {
        const values = weekTrend(recap, key);
        return values.length > 1 ? `\n${day ? 'Day by day, this day last' : 'Week by week, these 7 days last'}: ` +
            `${values.map(v => (v === null ? '?' : shown(v, kind))).join(' · ')}` : '';
    };
    return [
        {label: 'You', value: hoursText(s.youMs), delta: weekDeltaText(s.youMs, p ? p.youMs : null, 'time'), trend: weekTrend(recap, 'youMs'),
            tip: 'The time you spent writing to Claude, reading its replies and answering its questions, in all your chats and ' +
                "accounts: the time between your prompts and its replies counts when it's under 15 minutes." + before(p ? p.youMs : 0, 'time') +
                weeks('youMs', 'time')},
        {label: 'Claude worked', value: hoursText(s.workedMs), delta: weekDeltaText(s.workedMs, p ? p.workedMs : null, 'time'),
            trend: weekTrend(recap, 'workedMs'),
            tip: "Claude's own count of its turns (its “Worked for …”), all chats added up: chats working at the same time each " +
                `count. On the clock it worked ${hoursText(s.busyMs)}, and it waited ${hoursText(s.waitMs)} for your answers.` +
                before(p ? p.workedMs : 0, 'time') + weeks('workedMs', 'time')},
        {label: 'Prompts', value: grouped(s.prompts), delta: weekDeltaText(s.prompts, p ? p.prompts : null, 'count'),
            trend: weekTrend(recap, 'prompts'),
            tip: `${plural(s.chats, 'In %1 chat', 'In %1 chats')} · ${plural(s.turns, "%1 turn of Claude's", "%1 turns of Claude's")}` +
                before(p ? p.prompts : 0, 'count') + weeks('prompts', 'count')},
        {label: 'At API prices', value: moneyText(s.cost, cur), delta: weekDeltaText(s.cost, p ? p.cost : null, 'money', cur),
            trend: weekTrend(recap, 'cost'),
            tip: `What the same tokens would cost on Claude's API, at its list prices of ${dateText(recap.prices.asOf)}. ` +
                "Your plan isn't billed this way: this is the value of what you used." + before(p ? p.cost : 0, 'money') + weeks('cost', 'money')},
    ];
}

export function weekFactsText(s) {
    const parts = [];
    if (s.longestTurn && s.longestTurn.workedMs >= 60000)
        parts.push(`longest turn ${hoursText(s.longestTurn.workedMs)} (${s.longestTurn.name || '?'})`);
    if (s.peakAtOnce > 1)
        parts.push(`up to ${s.peakAtOnce} chats at once`);
    if (s.busiestDay)
        parts.push(`busiest day ${WEEKDAYS_LONG[dayDate(s.busiestDay).getDay()]}`);
    if (s.limits)
        parts.push(s.limits === 1 ? 'a usage limit stopped you once' : `usage limits stopped you ${s.limits} times`);
    return parts.join(' · ');
}

// What went on at ms, on its day's row. px: a pixel's ms, so a mark a pixel
// or two wide can be hit
export function weekHoverText(d, ms, now, px) {
    const when = `${weekDayLabel(d.day)}, ${clock(ms)}: `;
    if (ms > now)
        return `${when}still to come`;
    const at = list => list.find(s => s[0] <= ms && ms < s[1]) ||
        list.find(s => s[1] - s[0] < 3 * px && s[0] - 2 * px <= ms && ms < s[1] + 2 * px);
    const span = s => `${clock(s[0])}–${clock(s[1])}`;
    const work = at(d.work), wait = at(d.wait), you = at(d.you);
    const parts = [];
    const limit = (d.limits || []).find(t => Math.abs(t - ms) <= 3 * px);
    if (limit !== undefined)
        parts.push(`a usage limit stopped a chat at ${clock(limit)}`);
    if (work)
        parts.push(work[2] > 1 ? `Claude worked ${span(work)}, ${work[2]} chats at once` : `Claude worked ${span(work)}`);
    else if (wait)
        parts.push(`Claude waited for your answer ${span(wait)}`);
    if (you)
        parts.push(`you were at it ${span(you)}`);
    return when + (parts.length ? parts.join(' · ') : 'nothing went on');
}

export function weekDayTip(d, cur = USD) {
    const date = dayDate(d.day);
    const to = d.to ? dayDate(d.to) : null;   // (Overall: a row per 7 days)
    return [to ? `${date.getDate()} ${MONTHS_LONG[date.getMonth()]} – ${to.getDate()} ${MONTHS_LONG[to.getMonth()]}`
        : `${WEEKDAYS_LONG[date.getDay()]} ${date.getDate()} ${MONTHS_LONG[date.getMonth()]}`,
        `You: ${hoursText(d.youMs)} · Claude worked ${hoursText(d.workedMs)} (on the clock ${hoursText(d.busyMs)}) · ` +
        `it waited ${hoursText(d.waitMs)} for you\n${plural(d.prompts, '%1 prompt', '%1 prompts')} · ${formatTokens(d.tokenTotal || 0)} tokens · ` +
        `${moneyText(d.cost, cur)} at API prices` +
        (d.chats && d.chats.length ? '\nClick for its chats' : '')];
}

export function weekCacheText(recap) {
    const t = recap.sum.tokens;
    const input = t.input + t.cacheRead + t.cacheWrite5m + t.cacheWrite1h;
    if (!t.cacheRead)
        return '';
    return `${Math.round(100 * t.cacheRead / Math.max(1, input))}% of the ${formatTokens(input)} input tokens came from the cache: ` +
        `it saved ${moneyText(recap.cacheSaved, weekCurrency(recap))}. Claude wrote ${formatTokens(t.output)} tokens.`;
}

// A model's part of the whole: "<1%", ">99%" (not a rounded "100%" beside
// another's "<1%"), as statsModelsText
export function weekShareText(share) {
    return share <= 0 ? '0%' : share < 0.01 ? '<1%' : share > 0.99 && share < 1 ? '>99%' : `${Math.round(share * 100)}%`;
}

// A tip's icon (icons.mjs meanings, as Plasma's): the time chats waited for
// you, usage limits, else a tip of Claude Code's /usage
export function weekTipMeaning(key) {
    return key === 'waits' ? 'tipWaits' : key === 'limits' ? 'tipLimits' : 'tip';
}

// What Claude did, in a line: its tool calls, commands, edits, subagents
export function weekWorkText(w) {
    if (!w || !w.toolCalls)
        return '';
    const n = (v, one, many) => (v === 1 ? one : many).replace('%1', grouped(v));
    const parts = [n(w.toolCalls, '%1 tool call', '%1 tool calls')];
    if (w.commands)
        parts.push(n(w.commands, '%1 command run', '%1 commands run'));
    if (w.edits)
        parts.push(`${n(w.edits, '%1 edit', '%1 edits')} ${n(w.files, 'in %1 file', 'in %1 files')} (+${grouped(w.linesAdded)} −${grouped(w.linesRemoved)})`);
    if (w.subagents)
        parts.push(n(w.subagents, '%1 subagent started', '%1 subagents started'));
    if (w.webSearches)
        parts.push(n(w.webSearches, '%1 web search', '%1 web searches'));
    if (w.webFetches)
        parts.push(n(w.webFetches, '%1 page fetched', '%1 pages fetched'));
    if (w.compactions)
        parts.push(n(w.compactions, '%1 compaction', '%1 compactions'));
    return parts.join(' · ');
}

export function weekToolsText(w) {
    return w && w.tools && w.tools.length ? `Its tools: ${w.tools.map(([name, n]) => `${name} ${grouped(n)}`).join(' · ')}` : '';
}

// A plan window, from its start (its reset less its length) to its reset
const WINDOW_MS = {five_hour: 5 * 3600000, seven_day: 7 * 86400000, seven_day_opus: 7 * 86400000, seven_day_sonnet: 7 * 86400000};

export function weekWindowSpan(w) {
    const from = w.resetsAt && WINDOW_MS[w.key] ? w.resetsAt - WINDOW_MS[w.key] : w.points.length ? w.points[0][0] : 0;
    return [from, Math.max(w.resetsAt || 0, from + 1)];
}

export function weekResetText(ms, now) {
    if (!ms)
        return '';
    return `resets ${ms - now < 86400000 ? clock(ms) : weekWhenText(ms)}`;
}

// What a plan window's line says beside its fill: "60% · resets 14:00", "0% · reset"
export function weekPlanText(w, now) {
    const reset = w.reset ? 'reset' : weekResetText(w.resetsAt, now);
    return `${Math.round(w.pct)}%${reset ? ` · ${reset}` : ''}`;
}

export function weekPromptsText(p) {
    if (!p || !p.answered)
        return '';
    const answered = plural(p.answered, '%1 permission prompt', '%1 permission prompts');
    return (p.refused ? `You answered ${answered} and refused ${p.refused} of them.` : `You answered ${answered}.`) +
        (p.waitMs >= 60000 ? ` They waited for your answer ${hoursText(p.waitMs)} in all.` : '');
}

export function weekRuleMeta(r) {
    return [plural(r.count, '%1 prompt', '%1 prompts'), r.waitMs >= 60000 ? `waited ${hoursText(r.waitMs)} for you` : '', `e.g. ${r.example}`]
        .filter(Boolean).join(' · ');
}

export function weekColdText(recap) {
    const cold = recap.spend ? recap.spend.cold : null;
    if (!cold || !cold.count)
        return '';
    const cur = weekCurrency(recap);
    const most = cold.chats.map(c => `${c.name} (${c.resumes || 0}×, ${moneyText(c.cost, cur)})`).join(', ');
    return (cold.count === 1
        ? 'You came back to a chat after its cache had expired (an hour without a reply) once: writing its context again cost ' +
          `${moneyText(cold.cost, cur)} more than reading it from the cache.`
        : `You came back to chats after their cache had expired (an hour without a reply) ${cold.count} times: writing their ` +
          `context again cost ${moneyText(cold.cost, cur)} more than reading it from the cache.`) + (most ? ` Most in: ${most}.` : '');
}

export function weekFootText(recap) {
    const hosts = recap.sources.filter(s => s.host && s.ok).map(s => s.host);
    const guessed = recap.prices.guessed.length ? ` (${recap.prices.guessed.join(', ')} at the price of its family's newest model)` : '';
    const lines = [`Read from the chats on this computer${hosts.length ? ` and on ${hosts.join(', ')}` : ''}, without using any tokens. ` +
        `Prices: Claude's API list prices of ${dateText(recap.prices.asOf)}${guessed}.`];
    const c = recap.currency;
    if (c && c.error)
        lines.push(`Amounts in US dollars: ${c.error}.`);
    else if (c && c.code !== 'USD' && c.date)
        lines.push(`Amounts in ${c.code} at the European Central Bank's rate of ${dateText(c.date)}: 1 USD = ${c.rate.toFixed(4)} ${c.code}.`);
    for (const s of recap.sources) {
        if (!s.ok)
            lines.push(`${s.host} couldn't be read: ${s.error}`);
    }
    return lines.join('\n');
}

// The arguments of week.py for those days: the SSH hosts shown whose last
// check answered (one out of reach would hold it up), the currency picked
export function weekArgs(back, account, shownHosts, remote, configDirArgs, currency = 'USD', span = 'week') {
    const hosts = shownHosts.filter(h => remote[h] && remote[h].ok && remote[h].result);
    return ['--span', ['day', 'week', 'all'].includes(span) ? span : 'week', '--back', String(back), ...(account ? ['--account', account] : []),
        ...(/^[A-Z]{3}$/.test(currency) && currency !== 'USD' ? ['--currency', currency] : []),
        ...hosts.flatMap(h => ['--host', h]), ...configDirArgs];
}

// ---------------------------------------------------------------- advanced analyses: how your limits changed
// (the Recap's folded section, week.py --limits; the same words as VS Code's
// src/shared/week.ts and Plasma's WeekView.qml)

// week.py --limits' arguments: an account's or all, in the Recap's currency
export function limitsArgs(account, configDirArgs, currency = 'USD') {
    return ['--limits', ...(/^[0-9a-f]{12}$/.test(account) ? ['--account', account] : []),
        ...(/^[A-Z]{3}$/.test(currency) && currency !== 'USD' ? ['--currency', currency] : []), ...configDirArgs];
}

const FAMILIES = ['fable', 'mythos', 'opus', 'sonnet', 'haiku'];

// "5-hour window", "Week", "Week · Opus" (a plan's weekly window of one model)
export function limitLabel(key) {
    if (key === 'five_hour')
        return '5-hour window';
    if (key === 'seven_day')
        return 'Week';
    const family = FAMILIES.find(f => key.includes(f));
    return family ? `Week · ${family.charAt(0).toUpperCase()}${family.slice(1)}` : key.replace(/_/g, ' ');
}

// "24 Oct": when a week began
export function limitDay(ms) {
    const d = new Date(ms);
    return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// "about 5×", "▲ 20%", "▼ 80%", "about the same": how many times what a window held it holds now
function factorText(f) {
    if (f >= 1.5)
        return `about ${Number(f.toFixed(1))}×`;
    const pct = Math.round(Math.abs(f - 1) * 100);
    return pct < 10 ? 'about the same' : `${f > 1 ? '▲' : '▼'} ${pct}%`;
}

// "▼ 14% vs the week before", "about the same as the week before", "new this week", "about 5× since 4 Nov", …
export function limitChangeText(c) {
    if (!c)
        return '';
    if (c.kind === 'change')
        return `${(c.pct || 0) < 0 ? '▼' : '▲'} ${Math.abs(c.pct || 0)}% vs the week before`;
    if (c.kind === 'same')
        return 'about the same as the week before';
    if (c.kind === 'new')
        return 'new this week';
    if (c.kind === 'limits') {
        const day = c.at ? limitDay(c.at) : '';
        return c.factor ? `${factorText(c.factor)} since ${day}` : `your plan changed on ${day}`;
    }
    return 'too few readings to compare yet';
}

// Is a change one to show as bad (the window holds less)?
export function limitChangeBad(c) {
    return !!c && ((c.kind === 'change' && (c.pct || 0) < 0) || (c.kind === 'limits' && (c.factor || 1) < 0.9));
}

// A change of the plan's limits, in a line: "4 Nov 18:52 · your limits grew about 5× · Pro → Max 5×"
export function limitEventText(e) {
    const fs = Object.values(e.factors || {}).sort((p, q) => p - q);
    const f = fs.length ? fs[Math.floor((fs.length - 1) / 2)] : null;
    const what = f === null ? 'your plan changed'
        : f >= 1.5 ? `your limits grew about ${Number(f.toFixed(1))}×`
            : Math.abs(f - 1) < 0.1 ? 'your limits stayed about the same'
                : `your limits ${f > 1 ? 'grew' : 'shrank'} ${Math.round(Math.abs(f - 1) * 100)}%`;
    const plans = e.from && e.to && e.from !== e.to ? ` · ${e.from} → ${e.to}` : !e.from && e.to ? ` · now ${e.to}` : '';
    return `${limitDay(e.at)} ${clock(e.at)} · ${what}${plans}`;
}

export function limitEventTip(e) {
    const keys = Object.keys(e.factors || {});
    return keys.length
        ? `${keys.map(k => `${limitLabel(k)}: ${Number(e.factors[k].toFixed(2))}× what it held`).join('\n')
        }\nFrom your readings at that moment: the same usage read as a different share of the window.`
        : 'Your windows\' plan changed between two of them: what they held before and after tells by how much.';
}

// "17% of the week · about 6 full windows a week"
export function limitShareText(pct) {
    return pct > 0 ? `${Math.round(pct)}% of the week · about ${Math.max(1, Math.round(100 / pct))} full windows a week` : '';
}

// How long a full 5-hour window lasted at your pace
export function limitFillText(fill) {
    if (!fill)
        return '';
    const work = fill.workMs >= 60000 ? ` · Claude worked ${hoursText(fill.workMs)} in it, across chats` : '';
    return (fill.wallMs <= 5 * 3600000 ? `Full after about ${hoursText(fill.wallMs)} at your pace`
        : "At your pace a 5-hour window doesn't fill in its 5 hours") + work;
}

// What a full window is worth in tokens, at the API price of the model used most
export function limitTokensText(a) {
    const e = a.equivalents;
    const five = e ? e.fiveHour : null, week = e ? e.week : null;
    if (!e || !(five || week))
        return '';
    const first = five || week;
    return `${formatTokens(first.output)} output tokens of ${e.model} (or ${formatTokens(first.cacheRead)} cache reads) fill ` +
        `${five ? 'a 5-hour window' : 'a week'}${five && week ? `; ${formatTokens(week.output)} a week` : ''}, at API prices`;
}

// What filled a window: its parts (shares of all its tokens) and the line for them
export function limitMix(t) {
    const total = t ? t.cacheRead + t.fresh + t.output : 0;
    if (!t || total <= 0)
        return {parts: [], text: ''};
    const parts = ['cacheRead', 'fresh', 'output'].map(kind => ({kind, share: t[kind] / total}));
    return {
        parts,
        text: `${formatTokens(Math.round(total))} tokens filled one: ${weekShareText(parts[0].share)} cache reads, ` +
            `${weekShareText(parts[1].share)} new input and cache writes, ${weekShareText(parts[2].share)} output`,
    };
}

// A window's size: whole amounts from 10 up ("$48", "€1,180")
export function limitMoney(usd, cur = USD) {
    const amount = (usd || 0) * cur.rate;
    if (amount < 10)
        return moneyText(usd, cur);
    const symbol = SYMBOLS[cur.code];
    const text = grouped(Math.round(amount));
    return symbol ? symbol + text : `${text} ${cur.code}`;
}

// The dots of the 5-hour windows (x, y: 0 to 1), each week's median and each
// change of the limits, over the weeks kept; from a little under the
// smallest to a little over the largest
export function limitDots(a, now) {
    const from = a.periods.length ? a.periods[0].from : now;
    const span = Math.max(1, now - from);
    const sizes = [...a.windows.map(w => w.full), ...a.periods.map(p => (p.fiveHour ? p.fiveHour.cost : NaN))].filter(v => v > 0);
    const most = sizes.length ? Math.max(...sizes) : 1;
    const least = sizes.length ? Math.min(...sizes) : 0;
    const pad = Math.max((most - least) * 0.15, most * 0.05);
    const lo = Math.max(0, least - pad);
    const top = most + pad;
    const x = ms => Math.max(0, Math.min(1, (ms - from) / span));
    const y = v => (v - lo) / (top - lo);
    return {
        dots: a.windows.map(w => ({x: x(w.at), y: y(w.full), full: w.full,
            tip: `${weekWhenText(w.start)}: ${Math.round(w.pct)}% used by ${clock(w.at)}`})),
        medians: a.periods.filter(p => p.fiveHour).map(p => ({x1: x(p.from), x2: x(Math.min(p.until, now)), y: y(p.fiveHour.cost)})),
        marks: (a.events || []).filter(e => e.at > from && e.at <= now).map(e => x(e.at)),
        lo,
        top,
    };
}

// The weeks' bars (the main weekly window): height 0 to 1
export function limitWeekBars(a) {
    const weeks = a.periods.filter(p => p.weeks.seven_day);
    const top = Math.max(1e-9, ...weeks.map(p => p.weeks.seven_day.cost));
    return weeks.map(p => ({from: p.from, cost: p.weeks.seven_day.cost, h: p.weeks.seven_day.cost / top, partial: !!p.weeks.seven_day.partial}));
}

// The window keys an account has, in the order the Chats tab lists them
export function limitKeys(a) {
    const order = ['five_hour', 'seven_day', 'seven_day_opus', 'seven_day_sonnet'];
    const keys = ['five_hour', ...Object.keys(a.now.weeks)].filter(k => (k === 'five_hour' ? a.now.fiveHour : a.now.weeks[k]));
    return keys.sort((p, q) => (order.indexOf(p) + 1 || 99) - (order.indexOf(q) + 1 || 99));
}

// A window's size now ({cost, scaled}), its change
export function limitNow(a, key) {
    return {value: key === 'five_hour' ? a.now.fiveHour : a.now.weeks[key], change: a.changes[key === 'five_hour' ? 'fiveHour' : key]};
}

export function limitFootText(h) {
    return `Estimated from this computer's chats and the limit readings Talpy Den kept${h.since ? ` since ${limitDay(h.since)}` : ''}. ` +
        "Use on claude.ai, your phone, other computers or SSH hosts counts toward your limits but isn't seen here, so a limit can look smaller than it is.";
}

export const LIMIT_EMPTY = 'Not enough readings yet: a few 5-hour windows used past half tell how much one holds.';

// A size's tooltip: how it's worked out
export function limitSizeTip(key, a, cur) {
    const v = key === 'five_hour' ? a.now.fiveHour : a.now.weeks[key];
    const since = v && v.scaled ? `\nNone measured since your limits changed yet: what it held before, times ${Number(v.scaled.toFixed(2))}.` : '';
    if (key === 'five_hour') {
        const f = a.now.fiveHour;
        return f ? 'What a full 5-hour window held: the API price of what your chats used by a reading, over the share of the window ' +
            `it said was used. The middle of ${plural(f.n, '%1 window', '%1 windows')} in the newest week` +
            `${f.n > 1 ? ` (${moneyText(f.lo, cur)} to ${moneyText(f.hi, cur)})` : ''}.${since}` : '';
    }
    return `What a full ${limitLabel(key).toLowerCase()} held: the API price of what your chats used by its readings, over the ` +
        `share of it they said was used${key === 'seven_day' ? '.' : ' (only that model\'s usage counts).'}${since}`;
}

// week.py's arguments to allow a rule the tab offers, or take one it added back
// (on an SSH host: week.py runs there)
export function weekRuleArgs(rule, allow, host = '') {
    return [...(allow ? ['--allow', rule.kind, rule.value, rule.project] : ['--undo', rule.id]), ...(host ? ['--on', host] : [])];
}

// The permissions you gave (week.py's granted list): the first few, until
// you ask for all
export const WEEK_GRANTED_FEW = 8;

export function weekGrantedShown(granted, all) {
    return all ? granted : granted.slice(0, WEEK_GRANTED_FEW);
}

export function weekGrantedIntro(granted, host = '') {
    if (!granted.length)
        return `Nothing lets chats on ${host || 'this computer'} skip a permission prompt: they ask you each time.`;
    return host
        ? `What lets chats on ${host} go without asking you, as listed there: its settings, its trusted folders, and the .claude ` +
          `settings of the folders Claude ran in. Revoke takes one out of its file on ${host}.`
        : "What lets chats on this computer go without asking you: your settings and your administrator's, the folders you " +
          'trusted, the .claude settings of the folders Claude ran in, and what you approved in them. Revoke takes one out of its file.';
}

// What asks first or is busy in the Permissions tab: host|id (a host's
// rule and this computer's may share an id)
export function permsKey(host, id) {
    return `${host || ''}|${id}`;
}

export function weekGrantMeta(g) {
    return `${g.place} · ${g.where}`;
}

// A permission you gave, as an icon's meaning (icons.mjs; as Plasma's
// PermsView): a trusted folder, an MCP server, a loosened check, a folder to
// read, a mode, the web, a command, else a check
export function permsGrantMeaning(g) {
    if (g.kind === 'trust')
        return 'trusted';
    if (g.kind === 'mcp')
        return 'mcp';
    if (g.kind === 'flag')
        return 'warning';
    if (g.kind === 'dir')
        return 'folder';
    if (g.kind === 'mode')
        return g.value === 'acceptEdits' ? 'edit' : 'warning';
    if (g.value.startsWith('WebFetch') || g.value === 'WebSearch')
        return 'webAccess';
    return g.value.startsWith('Bash') ? 'terminal' : 'allowed';
}

// A rule it suggests: a folder to read, edits, the web, a command
export function permsRuleMeaning(r) {
    return r.kind === 'dir' ? 'folder' : r.kind === 'edits' ? 'edit' : r.value.startsWith('WebFetch') ? 'webAccess' : 'terminal';
}

// week.py's arguments for the Permissions tab (with the extra Claude
// folders, as the others)
export function permsArgs(configDirArgs, shownHosts = [], remote = {}) {
    const hosts = shownHosts.filter(h => remote[h] && remote[h].ok && remote[h].result);   // (one out of reach would hold it up)
    return ['--permissions', ...hosts.flatMap(h => ['--host', h]), ...configDirArgs];
}

// week.py's arguments to take one of them out of its file (with the extra
// Claude folders, so it finds the same list)
export function weekRevokeArgs(grant, configDirArgs, host = '') {
    return ['--revoke', grant.id, ...(host ? ['--on', host] : configDirArgs)];
}
