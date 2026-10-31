// One session in an account's list (port of the Plasma widget's
// SessionRow.qml): state dot, name (click to jump there), tags, state, and
// on hover the share, remove and stop buttons; below it the folder, model,
// context fill, what it needs or is doing or said last (click for the last
// exchange, its tasks and its changes), its subagents and any question to
// confirm.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as L from '../logic.js';
import {box, column, dot, iconButton, label, link, meter, nameLine, paragraph, showOnHover, tag, textButton} from './widgets.js';
import * as Icons from './icons.js';

export function buildSessionRow(ctx, session, {showProfile = false, remoteHost = ''} = {}) {
    const s = session;
    const tips = ctx.tips;
    const rowKey = L.rowKey(s, remoteHost);
    // A background session (claude stop), or a chat with a process of its own
    // (its claude quits; one in tmux can be interrupted instead: logic.js canEnd)
    const canEnd = L.canEnd(s);
    const canInterrupt = L.canInterrupt(s);
    const canStop = canEnd || (s.kind === 'bg' && s.pid !== null && (!remoteHost || !!s.stopCommand));
    const confirmingStop = !!(s.key || s.sessionId) && ctx.ui.stopConfirm === rowKey;
    const canShare = ctx.canShareChats && !remoteHost && s.pid === null && s.state === 'done' &&
        !!s.chatId && ctx.shareAccounts.length >= 2;
    const petColor = ctx.petColors[L.petKeyOf(s, remoteHost)] || '';
    const agents = s.agents || null;
    const showAgents = ctx.ui.expandedAgents[rowKey] === true;
    const tasks = s.tasks && s.tasks.total ? s.tasks : null;
    // its changes, compared side by side in VS Code (not an SSH host's files)
    const canCompare = !!s.changes && !remoteHost && ctx.vscodeInstalled && !!s.chatId;
    const canPeek = L.canPeek(s, remoteHost);
    const showPeek = canPeek && ctx.ui.expandedPeek[rowKey] === true;
    const open = () => (remoteHost ? ctx.remoteShow(remoteHost, s) : ctx.jumpTo(s.sessionId, s.profileDir));

    const row = box('claude-session-row', {x_expand: true, reactive: true, track_hover: true});

    // A bar in the color of the chat's pet, to spot which pet is which
    row.add_child(new St.Widget({
        style_class: 'claude-pet-bar', y_expand: true,
        style: petColor ? `background-color: ${petColor};` : '',
    }));
    // (red while a usage limit or an expired login stops it)
    const stopped = s.stopped || null;
    const stateDot = dot(s.reason === 'failed' || (stopped && !stopped.over) ? 'bad' : L.stateClass(s.state));
    stateDot.y_align = Clutter.ActorAlign.START;
    row.add_child(stateDot);

    const body = column('claude-session-body', {x_expand: true});
    row.add_child(body);

    // First line: name, tags, state, buttons (the tags go under the name when
    // they don't all fit beside it: widgets.js nameLine)
    const name = link(s.name, open, 'claude-session-name');
    tips.add(name, L.openHint(s, remoteHost));
    const tags = [];

    if (showProfile)
        tags.push(tips.add(tag(s.profile), 'The Claude profile (config folder) this chat runs in'));
    // where it runs, in the same words as Plasma's and VS Code's
    const [kindTag, kindTip] = s.pid === null ? ['Not open', 'No terminal or panel has it open: a reply goes on with it in the background.']
        : s.kind === 'bg' ? ['Background', "A background chat: Claude's background service runs it, with no terminal of its own. Click the name to open it in a terminal (claude attach)."]
        : s.entrypoint === 'claude-vscode' ? ['Claude Code panel', "Runs in VS Code's Claude Code panel. Click the name to open the conversation there."]
        : s.tmux ? ['Tmux', 'It runs in a tmux pane.']
        : s.vscodeTerminal || s.terminalApp === 'VS Code' ? ['VS Code terminal', 'It runs in a terminal of VS Code.']
        : ['Terminal', s.terminalApp ? L.fmt('It runs in a terminal (%1).', s.terminalApp) : 'It runs in a terminal.'];
    tags.push(tips.add(tag(kindTag), kindTip));
    // a background session shown in a terminal too (claude attach)
    if (s.kind === 'bg' && s.attached) {
        const where = s.attached.in === 'tmux' ? 'Tmux' : s.attached.in === 'vscode' ? 'VS Code terminal' : 'Terminal';
        tags.push(tips.add(tag(where), s.attached.app ? L.fmt('Shown in a terminal too (%1): claude attach.', s.attached.app)
            : 'Shown in a terminal too: claude attach.'));
    }
    if (s.shared)
        tags.push(tips.add(tag(s.shared.forkOf ? 'Shared copy' : 'Shared', false, Icons.gnome.share), () => sharedTooltip(s)));
    if (agents) {
        const t = tag(L.fmt('Agents %1/%2', agents.done, agents.total), agents.running > 0);
        t.add_style_class_name('claude-clickable');
        t.connect('button-release-event', () => {
            ctx.toggleAgents(rowKey);
            return Clutter.EVENT_STOP;
        });
        tags.push(tips.add(t, () => ['Subagents', L.fmt('%1 done, %2 running, %3 stopped%4. Click to %5 what each one is doing.',
            agents.done, agents.running, agents.stopped, agents.failed ? L.fmt(', %1 failed', agents.failed) : '',
            showAgents ? 'hide' : 'show')]));
    }
    if (tasks) {
        // its task list (TaskCreate), done/total; outlined while it's on one
        const t = tag(L.fmt('Tasks %1/%2', tasks.done, tasks.total), tasks.items.some(i => i.status === 'in_progress'));
        t.add_style_class_name('claude-clickable');
        t.connect('button-release-event', () => {
            ctx.togglePeek(rowKey);
            return Clutter.EVENT_STOP;
        });
        tags.push(tips.add(t, () => L.tasksTooltip(tasks, showPeek)));
    }
    if (s.changes) {
        // the files it changed: compared in VS Code (chats on this computer)
        const t = tag(L.changesTag(s.changes));
        if (canCompare) {
            t.add_style_class_name('claude-clickable');
            t.connect('button-release-event', () => {
                ctx.showChanges(s.chatId || s.sessionId, s.profileDir, false);
                return Clutter.EVENT_STOP;
            });
        }
        tags.push(tips.add(t, () => L.changesTooltip(s.changes, remoteHost, ctx.vscodeInstalled)));
    }
    const end = box('claude-line');
    end.add_child(label(L.stateText(s, ctx.now),
        `claude-state${s.state === 'waiting' ? ' claude-fg-waiting claude-strong'
            : stopped ? ` claude-strong ${stopped.over ? 'claude-fg-ok' : 'claude-fg-bad'}` : ''}`));

    const hoverButtons = [];
    if (canShare) {
        const share = iconButton(Icons.gnome.share, () => ctx.toggleShareMenu(rowKey, {
            chatId: s.chatId, name: s.name, profileDir: s.profileDir,
            shared: !!s.shared && !s.shared.forkOf,
        }));
        tips.add(share, ['Continue on another account',
            'Share this chat with your other accounts and pick it up there, or keep it on one account only.']);
        hoverButtons.push(share);
        end.add_child(share);
    }
    const asksDelete = ctx.ui.deleteAsk?.key === rowKey;
    if (s.state === 'done' && (s.chatId || s.sessionId)) {
        // Delete a finished chat: to the Trash, after a question (under the row)
        const del = iconButton(Icons.gnome.delete,   // (red, as a cancel's ×: icons.mjs TONES)
            () => ctx.askDelete(rowKey, s.chatId || s.sessionId, s.profileDir, remoteHost), 'claude-icon-button claude-tone-negative');
        tips.add(del, ['Delete this chat…', L.DELETE_HINT]);
        if (!asksDelete)
            hoverButtons.push(del);
        end.add_child(del);
    }
    if (s.state === 'done') {
        // Hide a finished chat here (nothing is deleted)
        const hide = iconButton(Icons.gnome.hide,
            () => (remoteHost ? ctx.remoteDismiss(remoteHost, s.sessionId) : ctx.dismissSession(s.sessionId)));
        tips.add(hide, ['Hide this chat', L.hideHint(remoteHost)]);
        hoverButtons.push(hide);
        end.add_child(hide);
    }
    if (canStop) {
        const stop = iconButton(Icons.gnome.stop,
            () => ctx.setStopConfirm(confirmingStop ? '' : rowKey));
        tips.add(stop, L.stopTip(s));
        if (!confirmingStop)
            hoverButtons.push(stop);
        end.add_child(stop);
    }
    showOnHover(row, hoverButtons, [name]);
    body.add_child(nameLine(name, tags, end));

    // Second line: folder, model, context fill
    const line2 = box('claude-line claude-small', {x_expand: true});
    const cwd = label(s.cwdShort, 'claude-dim', {x_expand: true});
    cwd.clutter_text.ellipsize = 2;   // Pango.EllipsizeMode.MIDDLE
    line2.add_child(cwd);
    if (s.model) {
        // the model, and how hard it thinks (Claude's /effort)
        const model = label(s.effort ? `${s.model} · ${s.effort}` : s.model, 'claude-dim');
        if (s.effort)
            tips.add(model, [s.model, L.fmt('Effort: %1 (how hard it thinks; /effort changes it)', s.effort)]);
        line2.add_child(model);
    }
    if (s.context !== null && s.context !== undefined) {
        const m = meter(s.context, L.usageClass(s.context), 'claude-meter claude-context-meter');
        m.x_expand = false;
        line2.add_child(m);
        line2.add_child(label(L.fmt('ctx %1%', Math.round(s.context)), 'claude-dim'));
    }
    body.add_child(line2);

    // What it needs, is doing, or said last; click for more
    const peekLine = L.peekLine(s);
    if (peekLine) {
        const text = label(peekLine.text, 'claude-detail claude-small', {x_expand: true});
        let line = text;
        if (canPeek) {
            line = new St.Button({style_class: 'claude-link claude-peek-line', can_focus: true, child: text,
                x_expand: true, x_align: Clutter.ActorAlign.FILL});
            line.connect('clicked', () => ctx.togglePeek(rowKey));
        }
        tips.add(line, () => [peekLine.title, canPeek
            ? `${L.clampText(peekLine.full, 8, 500)}\n\n${L.fmt('Click to %1 the last exchange.', showPeek ? 'hide' : 'show')}`
            : peekLine.full]);
        body.add_child(line);
    } else if (canPeek) {
        const more = link(showPeek ? 'Hide details' : 'Details', () => ctx.togglePeek(rowKey), 'claude-detail claude-small');
        body.add_child(more);
    }
    if (showPeek)
        body.add_child(buildPeek(ctx, s, remoteHost, canCompare));

    if (showAgents && agents)
        body.add_child(buildAgentsTree(ctx, s, agents, rowKey, remoteHost));

    if (ctx.ui.openMenu?.type === 'share' && ctx.ui.openMenu.key === rowKey)
        body.add_child(buildShareMenu(ctx, ctx.ui.openMenu.chat, rowKey));
    if (s.key !== '' && ctx.ui.shareConfirm?.key === rowKey)
        body.add_child(buildKeepOnly(ctx));
    if (asksDelete)
        body.add_child(buildDeleteAsk(ctx));

    if (confirmingStop && canStop) {
        const buttons = [
            ['Stop', Icons.gnome.stop, () => {
                // stopped only if it's as the question says when you click (it
                // follows the chat): an idle one that got busy since isn't
                const busy = s.state !== 'idle';
                ctx.setStopConfirm('');
                if (remoteHost && canEnd)
                    ctx.remoteEnd(remoteHost, s.sessionId, s.profileDir, busy);
                else if (remoteHost)
                    ctx.remoteStop(remoteHost, s.stopCommand);
                else
                    ctx.stopSession(s.sessionId, s.profileDir, busy);
            }],
            ['Cancel', '', () => ctx.setStopConfirm('')],
        ];
        if (canInterrupt) {
            buttons.unshift(['Interrupt', Icons.gnome.interrupt, () => {
                ctx.setStopConfirm('');
                if (remoteHost)
                    ctx.remoteInterrupt(remoteHost, s.sessionId, s.profileDir);
                else
                    ctx.interruptSession(s.sessionId, s.profileDir);
            }]);
        }
        body.add_child(confirmBox(L.stopQuestion(s), buttons));
    }
    return row;
}

function sharedTooltip(s) {
    const info = s.shared;
    if (info.forkOf) {
        let text = L.fmt('A copy of a chat shared between the %1 profiles: Claude forked it into a chat of its own on %2, so new messages here are only on %2.',
            info.profiles.join(' + '), info.forkOn);
        if (info.movedHere)
            text += "\nThe shared chat continued here, so it isn't listed itself.";
        if (info.stoppedCopies)
            text += `\n${L.fmt('Its background chat on %1 was stopped; %1 shows a link to this copy.', info.stoppedCopies.join(', '))}`;
        return ['Copy of a shared chat', text];
    }
    let text = L.fmt('This chat is shared between the %1 profiles: it continues on whichever account you open it with. Only one Claude can have it open at a time.',
        info.profiles.join(' + '));
    if (s.kind === 'chat')
        text += `\n${L.fmt('Listed here because it was used on %1 last.', s.profile)}`;
    if (info.openIn)
        text += `\n${L.fmt('Open in %1 right now.', info.openIn)}`;
    if (info.stoppedCopies)
        text += `\n${L.fmt('Its background chat on %1 was stopped; %1 shows a link to this chat.', info.stoppedCopies.join(', '))}`;
    return ['Shared chat', text];
}

// The last exchange (your prompt, Claude's reply), its tasks, and buttons
// that compare the files it changed (all of them, or the last turn's)
function buildPeek(ctx, s, remoteHost, canCompare) {
    const peek = s.peek || {};
    const box_ = column('claude-peek', {x_expand: true});
    if (peek.prompt)
        box_.add_child(paragraph(L.fmt('You: %1', L.clampText(peek.prompt, 4, 300)), 'claude-small claude-dim'));
    if (peek.reply)
        box_.add_child(paragraph(L.fmt('Claude: %1', L.clampText(peek.reply)), 'claude-small'));
    else if (s.state === 'working' && peek.activity)
        box_.add_child(paragraph(L.fmt('Claude is on it: %1', peek.activity), 'claude-small claude-dim'));
    if (s.tasks && s.tasks.total) {
        const list = column('claude-tasks', {x_expand: true});
        list.add_child(label(L.fmt('Tasks: %1 of %2 done', s.tasks.done, s.tasks.total), 'claude-small claude-strong'));
        for (const t of s.tasks.items) {
            list.add_child(label(`${L.taskMark(t.status)} ${t.subject}`,
                `claude-small${t.status === 'completed' ? ' claude-dim' : t.status === 'in_progress' ? ' claude-fg-working' : ''}`,
                {x_expand: true}));
        }
        if (s.tasks.total > s.tasks.items.length)
            list.add_child(label(L.fmt('… and %1 more', s.tasks.total - s.tasks.items.length), 'claude-small claude-dim'));
        box_.add_child(list);
    }
    if (canCompare) {
        const buttons = box('claude-confirm-buttons');
        const all = textButton(L.fmt(s.changes.count === 1 ? 'Compare changes (%1 file)' : 'Compare changes (%1 files)', s.changes.count),
            () => ctx.showChanges(s.chatId || s.sessionId, s.profileDir, false), 'claude-text-button claude-confirm-button');
        ctx.tips.add(all, ['Compare changes', 'Every file this chat changed, as it was before the chat and as it is now, side by side in VS Code.']);
        buttons.add_child(all);
        const turn = textButton('Last turn', () => ctx.showChanges(s.chatId || s.sessionId, s.profileDir, true),
            'claude-text-button claude-confirm-button');
        ctx.tips.add(turn, ['Compare the last turn', 'Only what changed since your last prompt.']);
        buttons.add_child(turn);
        box_.add_child(buttons);
    }
    // The chat's numbers so far (subagents included)
    const recap = s.stats ? L.chatRecapText(s.stats, s.costUsd) : '';
    if (recap) {
        const line = paragraph(recap, 'claude-small claude-dim claude-recap');
        ctx.tips.add(line, () => ['This chat so far', L.chatRecapTooltip(s.stats, s.costUsd, ctx.now)]);
        box_.add_child(line);
    }
    return box_;
}

// Subagents as a tree: what each one is doing; click one for its task, its
// last steps and its report, and to open its whole run
function buildAgentsTree(ctx, s, agents, rowKey, remoteHost) {
    const tree = column('claude-agents', {x_expand: true});
    for (const a of agents.tree) {
        const key = L.agentKey(rowKey, a);
        const open = ctx.ui.expandedAgent[key] === true;
        const indent = Math.round(a.depth * 14);
        const line = box('claude-agent', {x_expand: true});
        line.add_child(label('└', 'claude-dim'));
        const d = dot(a.status === 'running' ? 'working' : a.status === 'done' ? 'ok' : a.status === 'failed' ? 'bad' : 'none',
            'claude-dot claude-dot-small');
        d.y_align = Clutter.ActorAlign.START;
        line.add_child(d);
        const col = column('', {x_expand: true});
        const top = box('claude-line', {x_expand: true});
        top.add_child(label(a.description || a.type, 'claude-small', {x_expand: true}));
        top.add_child(label(a.model ? `${a.type} · ${a.model}` : a.type, 'claude-small claude-dim'));
        top.add_child(label(a.status === 'running'
            ? L.fmt('running · %1', L.duration(ctx.now - (a.started || ctx.now)))
            : a.status === 'done' ? 'done' : a.status === 'failed' ? 'failed' : 'stopped',
            a.status === 'failed' ? 'claude-small claude-fg-bad' : 'claude-small claude-dim'));
        top.add_child(new St.Icon({icon_name: open ? Icons.gnome.unfolded : Icons.gnome.folded,
            style_class: 'claude-agent-chevron', y_align: Clutter.ActorAlign.CENTER}));
        col.add_child(top);
        if (a.activity)
            col.add_child(label(a.activity, 'claude-small claude-dim', {x_expand: true}));
        line.add_child(col);
        const button = new St.Button({style_class: 'claude-agent-button', can_focus: true, child: line,
            x_expand: true, x_align: Clutter.ActorAlign.FILL, style: `margin-left: ${indent}px;`});
        button.connect('clicked', () => ctx.toggleAgent(key));
        ctx.tips.add(button, () => L.agentTooltip(a, open));
        tree.add_child(button);
        if (open)
            tree.add_child(buildAgentDetail(ctx, s, a, remoteHost, indent));
    }
    return tree;
}

// An unfolded subagent: the task it was given, how far it got, its last
// steps (the newest in bold while it runs), its report, and its whole run
function buildAgentDetail(ctx, s, a, remoteHost, indent) {
    const detail = column('claude-peek claude-agent-detail', {x_expand: true, style: `margin-left: ${indent + 22}px;`});
    if (a.task)
        detail.add_child(paragraph(L.fmt('Task: %1', L.clampText(a.task, 4, 400)), 'claude-small claude-dim'));
    const summary = L.agentSummaryText(a);
    if (summary)
        detail.add_child(label(summary, 'claude-small claude-dim'));
    const steps = L.agentStepLines(a);
    if (steps.length) {
        const list = column('claude-tasks', {x_expand: true});
        for (const step of steps)
            list.add_child(label(step.text, `claude-small${step.current ? ' claude-strong' : ''}`, {x_expand: true}));
        detail.add_child(list);
    }
    if (a.status === 'done' && a.report)
        detail.add_child(paragraph(L.fmt('Report: %1', L.clampText(a.report, 12, 1500)), 'claude-small'));
    const run = textButton('Open the whole run', () => ctx.openAgentRun(s, a, remoteHost),
        'claude-text-button claude-confirm-button', Icons.gnome.openRun);
    ctx.tips.add(run, L.agentRunTooltip(remoteHost));
    detail.add_child(run);
    return detail;
}

// A question with buttons, e.g. "Stop “fix parser”? …" [Stop] [Cancel]
export function confirmBox(text, buttons) {
    const c = column('claude-confirm', {x_expand: true});
    c.add_child(paragraph(text, 'claude-small'));
    const row = box('claude-confirm-buttons');
    for (const [title, icon, onClick] of buttons)
        row.add_child(textButton(title, onClick, 'claude-text-button claude-confirm-button', icon));
    c.add_child(row);
    return c;
}

// Under a chat's line once its Delete… was clicked (ctx.ui.deleteAsk): what
// goes to the Trash and on which accounts (jump.py --describe), with Delete
// and Cancel; or why it can't be deleted (open in Claude, gone)
export function buildDeleteAsk(ctx) {
    const a = ctx.ui.deleteAsk;
    if (a.busy)
        return label('Looking at what it would delete…', 'claude-small claude-dim');
    if (a.question) {
        return confirmBox(a.question, [
            ['Delete', '', () => ctx.confirmDelete()],
            ['Cancel', '', () => ctx.cancelDelete()],
        ]);
    }
    const c = column('claude-confirm', {x_expand: true});
    c.add_child(paragraph(a.message, 'claude-small claude-fg-bad'));
    const row = box('claude-confirm-buttons');
    row.add_child(textButton('OK', () => ctx.cancelDelete(), 'claude-text-button claude-confirm-button'));
    c.add_child(row);
    return c;
}

// Share a chat with your other accounts, continue it on one of them, or
// keep it on one only (jump.py)
export function buildShareMenu(ctx, chat, rowKey) {
    const menu = column('claude-inline-menu', {x_expand: true});
    menu.add_child(label(chat.name, 'claude-menu-title'));
    const here = ctx.groupOfProfile(chat.profileDir);
    for (const g of ctx.shareAccounts) {
        if (g === here)
            continue;
        menu.add_child(textButton(chat.shared ? L.fmt('Continue on %1', g.title) : L.fmt('Share and continue on %1', g.title),
            () => ctx.shareAction('continue', chat.chatId, g.shareProfile), 'claude-menu-item', Icons.gnome.continueOn));
    }
    if (!chat.shared) {
        menu.add_child(textButton('Share with all accounts', () => ctx.shareAction('share', chat.chatId, ''),
            'claude-menu-item', Icons.gnome.share));
    } else {
        for (const g of ctx.shareAccounts) {
            menu.add_child(textButton(L.fmt('Keep only on %1…', g.title), () => ctx.askKeepOnly(rowKey, chat, g),
                'claude-menu-item', Icons.gnome.moveTo));
        }
    }
    return menu;
}

// Asks before a shared chat is kept on one account only (the others lose it)
export function buildKeepOnly(ctx) {
    const c = ctx.ui.shareConfirm;
    return confirmBox(L.fmt("Keep “%1” only on %2? It leaves the chat lists of %3; the conversation stays on %2. It can't be open in Claude meanwhile.",
        c.name, c.account, c.others), [
        [L.fmt('Keep only on %1', c.account), '', () => ctx.confirmKeepOnly()],   // (no ×: it doesn't close the question)
        ['Cancel', '', () => ctx.cancelKeepOnly()],
    ]);
}
