// One Claude account (port of the Plasma widget's GroupSection.qml): plan
// limits, token totals, its sessions (from every config dir logged into it),
// chats shared with it that run elsewhere, recent chats and starred chats. With remoteHost
// set, the account is on that SSH host and its actions run there.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as L from '../logic.js';
import {buildDeleteAsk, buildSessionRow, buildKeepOnly, buildShareMenu} from './sessionRow.js';
import {box, column, iconButton, label, link, meter, paragraph, scaleFactor, separator, showOnHover, tag, textButton, usageMeter} from './widgets.js';
import * as Icons from './icons.js';

// accounts: how many its machine has (with two or more, the default one is marked)
export function buildGroupSection(ctx, group, {last = false, remoteHost = '', accounts = 1} = {}) {
    const tips = ctx.tips;
    const groupKey = (remoteHost ? `${remoteHost}/` : '') + group.id;
    const multiProfile = group.profiles.length > 1;
    const section = column('claude-group', {x_expand: true});

    // Heading: the account, its new-chat button and its profiles
    const head = box('claude-group-head', {x_expand: true});
    head.add_child(label(group.title, 'claude-group-title'));
    // The default account: listed first, VS Code's Claude and plain claude run on it
    if (group.defaultHere && accounts > 1) {
        const mark = tag('Default');
        tips.add(mark, [remoteHost ? L.fmt('The default account on %1', remoteHost) : 'The default account',
            (remoteHost
                ? L.fmt("Listed first; VS Code's Claude on %1 (its VS Code server) and plain claude there run on it.", remoteHost)
                : "Listed first, its 5-hour usage is in the top bar, and VS Code's Claude and plain claude run on it.")
            + ' Change it in the settings: Accounts, Make Default.']);
        head.add_child(mark);
    }
    // (a speech bubble with a plus, the widget's: a + beside the account reads
    // as "add an account"; St colors a -symbolic icon like text)
    const bubble = new Gio.FileIcon({file: Gio.File.new_for_path(GLib.build_filenamev([ctx.iconsDir, 'chat-new-symbolic.svg']))});
    const add = iconButton(bubble, () => ctx.toggleNewChat(groupKey));
    tips.add(add, [L.fmt('New chat on %1', group.title), remoteHost
        ? L.fmt("Lists this account's folders on %1: start a new Claude chat in one, in a terminal (over ssh) or in VS Code.", remoteHost)
        : "Lists this account's recent folders: start a new Claude chat in one, in a terminal or in VS Code."]);
    head.add_child(add);
    head.add_child(new St.Widget({x_expand: true}));
    if (multiProfile)
        head.add_child(label(group.profiles.join(' + '), 'claude-small claude-dim'));
    section.add_child(head);

    if (ctx.ui.openMenu?.type === 'newchat' && ctx.ui.openMenu.key === groupKey)
        section.add_child(buildNewChatMenu(ctx, group, remoteHost));

    // This account's chats as pets (pets.js), when there are any
    const stage = ctx.stageFor(groupKey, L.stageChats(group, remoteHost));
    if (stage)
        section.add_child(stage);

    // Not logged in to an account (a new one, or logged out): Claude's own
    // login, in a terminal (over ssh for a host's)
    if (group.loggedOut) {
        const row = box('claude-login', {x_expand: true});
        row.add_child(new St.Icon({icon_name: Icons.gnome.account, style_class: 'claude-button-icon claude-dim'}));
        row.add_child(label('Not logged in', 'claude-dim', {x_expand: true}));
        if (!remoteHost || group.loginCommand) {
            const login = textButton('Log in…', () => ctx.logIn(group, remoteHost), 'claude-text-button claude-login-button');
            tips.add(login, [L.fmt('Log in to %1', group.title), remoteHost
                ? L.fmt("Opens a terminal with Claude's own login on %1 (over ssh): open the address it shows in your browser, sign in, and paste the code you get back.", remoteHost)
                : "Opens a terminal with Claude's own login (claude auth login): sign in in your browser with the account for this folder. Talpy Den never sees the login."]);
            row.add_child(login);
        }
        section.add_child(row);
    }

    // Plan limits (from the status line)
    const limits = column('claude-limits', {x_expand: true});
    for (const w of group.limits ? group.limits.windows : []) {
        const bar = box('claude-usage', {x_expand: true});
        bar.add_child(label(w.label, 'claude-usage-label'));
        // with a forecast: lighter up to where it'd be at the reset, and a tick for an even pace
        const projected = L.projectedPct(w);
        const m = usageMeter(w.pct, L.usageClass(w.pct), projected, L.usageClass(projected),
            w.forecast ? w.forecast.evenPct : null);
        bar.add_child(m);
        const forecastTip = w.forecast ? () => L.forecastTooltip(w, ctx.now) : null;   // when you hover
        if (forecastTip)
            tips.add(m, forecastTip);
        bar.add_child(label(`${Math.round(w.pct)}%`, 'claude-usage-pct'));
        bar.add_child(label(L.resetText(w, ctx.now), 'claude-usage-detail claude-small claude-dim'));
        limits.add_child(bar);
        const warning = L.forecastWarning(w, ctx.now);
        if (warning) {
            const line = label(warning, `claude-forecast claude-small claude-fg-${L.usageClass(Math.max(70, w.pct))}`, {x_expand: true});
            if (forecastTip)
                tips.add(line, forecastTip);
            limits.add_child(line);
        }
    }
    const asOf = label(L.planUsageText(group.limits, ctx.now, group.limitsFrom, group.usageFetchAt), 'claude-small claude-dim', {x_expand: true});
    if (!group.limits) {
        tips.add(asOf, ['No plan usage yet',
            'Plan limits come from the Claude Code status line (statusline-snippet.sh). They update whenever a chat of this account gets a reply.']);
    }
    limits.add_child(asOf);
    if (!group.loggedOut && !group.limitsHidden)   // (hidden: the account shows it where it's listed first)
        section.add_child(limits);

    // Token totals (from local transcripts); with stats, a toggle for the last days
    if (group.tokens) {
        const statsOpen = !!group.stats && ctx.ui.expandedStats[groupKey] === true;
        const tokens = group.stats
            ? textButton(L.tokensText(group.tokens), () => ctx.toggleStats(groupKey),
                'claude-text-button claude-tokens claude-expander', statsOpen ? Icons.gnome.unfolded : Icons.gnome.folded)
            : label(L.tokensText(group.tokens), 'claude-tokens', {x_expand: true});
        tips.add(tokens, () => ["Tokens (this machine's transcripts only)", L.tokensTooltip(group.tokens)
            + (group.stats ? `\n\n${L.fmt('Click to %1 the last %2 days.', statsOpen ? 'hide' : 'show', group.stats.days.length)}` : '')]);
        section.add_child(tokens);
        if (statsOpen)
            section.add_child(buildStats(ctx, group.stats));
    }

    // Sessions
    for (const s of group.sessions)
        section.add_child(buildSessionRow(ctx, s, {showProfile: multiProfile, remoteHost}));
    if (group.sessions.length === 0)
        section.add_child(label('No running chats', 'claude-dim claude-indent'));

    // Chats shared with this account that are in use on another one (they're
    // listed there, once): a line pointing to them
    for (const chat of group.sharedHere || [])
        section.add_child(buildSharedLine(ctx, chat, remoteHost));

    // Recent chats: this account's latest other chats, to pick one up
    // again, a page at a time ("Show N more"; the status lists one page
    // more than shows, a check for more is asked for past that)
    const size = ctx.pageSize;
    const recentOpen = !!ctx.ui.expandedRecent[groupKey];
    const recent = L.recentPage(group, recentOpen ? ctx.ui.recentMore[groupKey] || null : null, size,
        ctx.pagesShown(`${groupKey}|recent`), recentOpen);
    if (recent.fetch)
        ctx.fetchRecent(groupKey, group.id, remoteHost, recent.fetch);
    if (recent.count > 0) {
        const toggle = textButton(L.pagedTitle('Recent chats', recent.shown, recent.count), () => ctx.toggleRecent(groupKey, recentOpen),
            'claude-text-button claude-small claude-expander', recentOpen ? Icons.gnome.unfolded : Icons.gnome.folded);
        tips.add(toggle, ['Recent chats',
            "This account's latest chats that aren't listed above, newest first. Click one to reopen it, in a terminal or in VS Code (the switch at the top of the list). " +
            'Show more lists more of them; folded again, it lists the first ones again.']);
        section.add_child(toggle);
        if (recentOpen) {
            // Where they reopen: the same Terminal | VS Code choice as for new chats
            const openIn = openInSwitch(ctx, group, remoteHost, true);
            openIn.add_style_class_name('claude-indent');
            section.add_child(openIn);
            for (const chat of recent.all.slice(0, recent.shown))
                section.add_child(buildRecentLine(ctx, group, chat, remoteHost));
            if (recent.shown < recent.count)
                section.add_child(moreButton(ctx, `${groupKey}|recent`, recent.shown, recent.count));
        }
    }

    // ★ Starred chats: the ones you starred (☆ on a chat), however old, a page at a time
    const starred = group.starred || [];
    if (starred.length > 0) {
        const starredOpen = !!ctx.ui.expandedStarred[groupKey];
        const shown = Math.min(starred.length, size * ctx.pagesShown(`${groupKey}|starred`));
        const toggle = textButton(L.pagedTitle('★ Starred chats', shown, starred.length), () => ctx.toggleStarred(groupKey, starredOpen),
            'claude-text-button claude-small claude-expander', starredOpen ? Icons.gnome.unfolded : Icons.gnome.folded);
        tips.add(toggle, ['Starred chats',
            "The chats of this account you starred (☆ next to a chat), newest first, however old they are; not the ones listed above. Click a chat's ★ to unstar it."]);
        section.add_child(toggle);
        if (starredOpen) {
            if (!recentOpen) {   // (the switch is under Recent chats while that's unfolded)
                const openIn = openInSwitch(ctx, group, remoteHost, true);
                openIn.add_style_class_name('claude-indent');
                section.add_child(openIn);
            }
            for (const chat of starred.slice(0, shown))
                section.add_child(buildRecentLine(ctx, group, chat, remoteHost));
            if (shown < starred.length)
                section.add_child(moreButton(ctx, `${groupKey}|starred`, shown, starred.length));
        }
    }

    if (!last)
        section.add_child(separator());
    return section;
}

// "Show N more" under a list that shows a page at a time (Recent chats,
// ★ Starred chats): the next page of it. Folded again, the list shows its first page.
function moreButton(ctx, listKey, shown, count) {
    const size = ctx.pageSize;
    const more = textButton(L.showMoreText(size, shown, count), () => ctx.showMore(listKey),
        'claude-text-button claude-small claude-more', Icons.gnome.more);
    ctx.tips.add(more, L.showMoreTip(size, shown, count));
    return more;
}

// The account's last days: tokens per day as bars (today's in the working
// color), the totals, its busiest folders and its models
const STATS_BAR_PX = 48;

function buildStats(ctx, stats) {
    const wrap = column('claude-stats claude-indent', {x_expand: true});
    wrap.add_child(label(L.fmt('Last %1 days', stats.days.length), 'claude-small claude-strong'));
    const chart = box('claude-stats-chart', {x_expand: true});
    const scale = scaleFactor();
    const heights = L.statsBarHeights(stats, STATS_BAR_PX * scale);
    stats.days.forEach((d, i) => {
        const today = i === stats.days.length - 1;
        const col = column('claude-stats-day', {x_expand: true});
        const area = new St.Widget({layout_manager: new Clutter.BinLayout(), x_expand: true, height: STATS_BAR_PX * scale});
        const bar = new St.Widget({
            style_class: `claude-stats-bar ${heights[i] ? 'claude-bg-working' : 'claude-stats-baseline'}`,
            x_expand: true, y_expand: true, y_align: Clutter.ActorAlign.END,
            height: heights[i] || 2 * scale, opacity: today || !heights[i] ? 255 : 140,
        });
        area.add_child(bar);
        col.add_child(area);
        col.add_child(label(L.statsDayLetter(d.day), `claude-stats-letter claude-small${today ? ' claude-strong' : ' claude-dim'}`,
            {x_align: Clutter.ActorAlign.CENTER}));
        ctx.tips.add(col, L.statsDayText(d));
        chart.add_child(col);
    });
    wrap.add_child(chart);
    wrap.add_child(paragraph(L.statsSummaryText(stats), 'claude-small'));

    const projects = stats.projects.slice(0, 5);
    if (projects.length) {
        wrap.add_child(label('Busiest folders', 'claude-small claude-strong'));
        const top = Math.max(1, ...projects.map(p => p.total));
        for (const p of projects) {
            const line = box('claude-stats-project', {x_expand: true});
            line.add_child(label(p.name, 'claude-small claude-stats-name'));
            line.add_child(meter(100 * p.total / top, 'working', 'claude-meter claude-stats-meter'));
            line.add_child(label(L.statsProjectText(p), 'claude-small claude-dim claude-stats-numbers'));
            ctx.tips.add(line, [p.path, L.fmt('%1 tokens (%2 out) in %3 days', L.formatTokens(p.total),
                L.formatTokens(p.output), stats.days.length)]);
            wrap.add_child(line);
        }
    }
    const models = L.statsModelsText(stats);
    if (models)
        wrap.add_child(label(models, 'claude-small claude-dim', {x_expand: true}));
    return wrap;
}

// New chat on this account: its recent folders, then any folder you pick.
// One switch at the top says where a chat starts (kept between uses): a
// terminal with Claude in the folder you click, or VS Code's Claude extension,
// which runs on one account only (greyed out on the others).
function buildNewChatMenu(ctx, group, host) {
    const menu = column('claude-inline-menu', {x_expand: true});
    menu.add_child(label(L.fmt('New chat on %1 in…', host ? L.fmt('%1 on %2', group.title, host) : group.title),
        'claude-menu-title'));
    const inVscode = ctx.openInVscode(group, host);
    const terminalHere = ctx.cliHere(host);
    menu.add_child(openInSwitch(ctx, group, host, false));
    for (const f of L.newChatFolders(group, host)) {
        const item = textButton(f.short === '~' ? 'Home folder (~)' : f.short, () => {
            if (host && inVscode)
                ctx.remoteNewChatVscode(host, f.path);
            else if (host)
                ctx.remoteOpen(host, f.newChatCommand || '');
            else
                ctx.newChat(group.chatProfile, f.path, inVscode);
        }, 'claude-menu-item', f.short === '~' ? Icons.gnome.home : Icons.gnome.folder);
        item.x_expand = true;
        item.reactive = inVscode || (terminalHere && (!host || !!f.newChatCommand));
        if (!item.reactive)
            item.opacity = 110;
        menu.add_child(item);
    }
    if (!host) {
        const choose = textButton('Choose folder…', () => ctx.newChatChoosingFolder(group.chatProfile, inVscode),
            'claude-menu-item', Icons.gnome.chooseFolder);
        choose.x_expand = true;
        choose.reactive = inVscode || terminalHere;
        if (!choose.reactive)
            choose.opacity = 110;
        menu.add_child(choose);
    }
    return menu;
}

// Terminal | VS Code, for new chats and (resuming) recent ones: one choice
// for both. A half is greyed out where it can't work (no claude command, no
// VS Code, or VS Code's Claude on another account), with a tooltip saying why
// (on a wrapper, so it shows then too); when neither works, a line says why.
function openInSwitch(ctx, group, host, resuming) {
    const inVscode = ctx.openInVscode(group, host);
    const terminalHere = ctx.cliHere(host);
    const vscodeHere = ctx.vscodeInstalled && !!group.vscodeHere;
    const wrap = column('claude-open-in-wrap', {x_expand: true});
    const line = box('claude-menu-row claude-open-in', {x_expand: true});
    wrap.add_child(line);
    line.add_child(label('Open in:', 'claude-small claude-dim', {y_align: Clutter.ActorAlign.CENTER}));
    const half = (icon, fallback, text, checked, enabled, onClick, tip) => {
        const content = box('claude-button-box');
        content.add_child(new St.Icon({icon_name: icon, fallback_icon_name: fallback, style_class: 'claude-button-icon'}));
        content.add_child(label(text));
        const button = new St.Button({style_class: 'claude-text-button claude-switch-button', child: content,
            checked, reactive: enabled, can_focus: enabled, opacity: enabled ? 255 : 110});
        button.connect('clicked', onClick);
        const wrap = new St.Bin({child: button, y_align: Clutter.ActorAlign.CENTER});
        ctx.tips.add(wrap, tip);
        return wrap;
    };
    line.add_child(half(Icons.gnome.terminal, 'utilities-terminal', 'Terminal', terminalHere && !inVscode,
        terminalHere, () => ctx.setNewChatInVscode(false),
        [!terminalHere ? 'No claude command' : resuming ? 'Reopen chats in a terminal' : 'New chats in a terminal',
            L.terminalHint(host, terminalHere, resuming)]));
    line.add_child(half('vscode', Icons.gnome.vscodeApp, 'Claude Code panel', inVscode, vscodeHere,
        () => ctx.setNewChatInVscode(true),
        [!ctx.vscodeInstalled ? "VS Code isn't installed" : !vscodeHere ? 'Not on this account'
            : resuming ? 'Reopen chats in VS Code' : 'New chats in VS Code',
        L.vscodeHint(group, host, ctx._status, resuming)]));
    if (!terminalHere && !vscodeHere) {
        const why = label(`${L.terminalHint(host, terminalHere, resuming)} ${L.vscodeHint(group, host, ctx._status, resuming)}`,
            'claude-small claude-dim claude-open-in', {x_expand: true});
        why.clutter_text.line_wrap = true;
        why.clutter_text.ellipsize = 0;
        wrap.add_child(why);
    }
    return wrap;
}

function buildSharedLine(ctx, chat, remoteHost) {
    const line = box('claude-line claude-indent', {x_expand: true});
    line.add_child(new St.Icon({icon_name: Icons.gnome.share, style_class: `claude-button-icon claude-fg-${L.stateClass(chat.state)}`,
        y_align: Clutter.ActorAlign.CENTER}));
    const name = link(chat.name, () => (remoteHost ? ctx.remoteOpen(remoteHost, chat.openCommand)
        : ctx.jumpTo(chat.sessionId, chat.profileDir)), 'claude-dim');
    name.x_expand = true;
    ctx.tips.add(name, () => {
        const title = chat.copy ? L.fmt('Shared chat, continued on %1 as a copy', chat.profile)
            : chat.state === 'done' ? L.fmt('Shared chat, last used on %1', chat.profile)
                : L.fmt('Shared chat, open on %1', chat.profile);
        let text = chat.copy
            ? L.fmt('This chat is shared with this account too, but it continued on %1 in a copy Claude forked from it. New messages are only in that copy. Click to go to it.', chat.profile)
            : "This chat is shared with this account too. It's listed once, under the account it's used on. Click to go to it.";
        if (chat.stoppedHere)
            text += '\nIts background chat on this account was stopped.';
        return [title, text];
    });
    line.add_child(name);
    line.add_child(label(chat.copy ? L.fmt('copy on %1 · %2', chat.profile, L.stateText(chat, ctx.now))
        : L.fmt('on %1 · %2', chat.profile, L.stateText(chat, ctx.now)), 'claude-small claude-dim claude-side'));
    return line;
}

// A recent chat: click to reopen it where the switch above says
function buildRecentLine(ctx, group, chat, remoteHost) {
    const rowKey = (remoteHost ? `${remoteHost}|` : '') + (chat.key || chat.sessionId);
    const inVscode = ctx.openInVscode(group, remoteHost);
    const terminalHere = ctx.cliHere(remoteHost);
    const canOpen = inVscode || (terminalHere && (!remoteHost || !!chat.openCommand));
    const wrap = column('claude-recent', {x_expand: true});
    const line = box('claude-line', {x_expand: true, reactive: true, track_hover: true});
    const name = link(chat.name, () => {
        if (!canOpen)
            return;
        if (remoteHost && inVscode)
            ctx.remoteResumeVscode(remoteHost, chat.sessionId, chat.cwd);
        else if (remoteHost)
            ctx.remoteOpen(remoteHost, chat.openCommand);
        else if (inVscode)
            ctx.resumeInVscode(chat.sessionId, chat.profileDir);
        else
            ctx.jumpTo(chat.sessionId, chat.profileDir);
    });
    name.x_expand = true;
    if (!canOpen)
        name.opacity = 150;
    const where = !canOpen
        ? `${L.terminalHint(remoteHost, terminalHere, true)}\n${L.vscodeHint(group, remoteHost, ctx._status, true)}`
        : inVscode ? L.vscodeHint(group, remoteHost, ctx._status, true) : L.terminalHint(remoteHost, terminalHere, true);
    ctx.tips.add(name, [chat.name, where +
        (chat.shared ? `\n${L.fmt('Shared between accounts; last used on %1.', chat.profile)}` : '')]);
    line.add_child(name);
    if (chat.shared)
        line.add_child(new St.Icon({icon_name: Icons.gnome.share, style_class: 'claude-button-icon claude-dim', y_align: Clutter.ActorAlign.CENTER}));
    // starred: a ★ (click: unstar it)
    if (chat.starred) {
        const mark = iconButton(Icons.gnome.starred, () => ctx.setStar(chat.sessionId, remoteHost, false), 'claude-icon-button claude-star-mark');
        mark.y_align = Clutter.ActorAlign.CENTER;
        ctx.tips.add(mark, ['Starred', L.starHint(true)]);
        line.add_child(mark);
    }
    const when = label(L.fmt('%1 · %2', chat.cwdShort || '~', L.ago(ctx.now - chat.lastActive)),
        'claude-small claude-dim claude-side');
    when.clutter_text.ellipsize = 1;   // Pango.EllipsizeMode.START
    line.add_child(when);
    const hoverButtons = [];
    // star it: it stays listed under ★ Starred chats (a starred one has its ★)
    if (!chat.starred) {
        const star = iconButton(Icons.gnome.star, () => ctx.setStar(chat.sessionId, remoteHost, true));
        ctx.tips.add(star, ['Star this chat', L.starHint(false)]);
        hoverButtons.push(star);
        line.add_child(star);
    }
    if (ctx.canShareChats && !remoteHost && ctx.shareAccounts.length >= 2) {
        const share = iconButton(Icons.gnome.share, () => ctx.toggleShareMenu(rowKey, {
            chatId: chat.sessionId, name: chat.name, profileDir: chat.profileDir, shared: chat.shared,
        }));
        ctx.tips.add(share, ['Continue on another account',
            'Share this chat with your other accounts and pick it up there, or keep it on one account only.']);
        hoverButtons.push(share);
        line.add_child(share);
    }
    // to the Trash, after a question (under the line)
    const asksDelete = ctx.ui.deleteAsk?.key === rowKey;
    const del = iconButton(Icons.gnome.delete, () => ctx.askDelete(rowKey, chat.sessionId, chat.profileDir, remoteHost),
        'claude-icon-button claude-tone-negative');   // (red, as a cancel's ×: icons.mjs TONES)
    ctx.tips.add(del, ['Delete this chat…', L.DELETE_HINT]);
    if (!asksDelete)
        hoverButtons.push(del);
    line.add_child(del);
    showOnHover(line, hoverButtons, [name]);
    wrap.add_child(line);
    if (ctx.ui.openMenu?.type === 'share' && ctx.ui.openMenu.key === rowKey)
        wrap.add_child(buildShareMenu(ctx, ctx.ui.openMenu.chat, rowKey));
    if (ctx.ui.shareConfirm?.key === rowKey)
        wrap.add_child(buildKeepOnly(ctx));
    if (asksDelete)
        wrap.add_child(buildDeleteAsk(ctx));
    return wrap;
}

// An SSH host you picked (port of HostSection.qml): its accounts, fetched by
// remote.py over ssh. Its last answer stays (dimmed) when a check fails.
export function buildHostSection(ctx, host) {
    const tips = ctx.tips;
    const info = ctx.remote[host] || {loading: true, ok: false, error: '', result: null, updatedAt: 0};
    const owners = ctx.usageOwners;
    const groups = (info.result ? info.result.groups : []).map(g => L.withUsage(g, host, owners));
    const stale = !!info.error && info.result !== null;
    const section = column('claude-host', {x_expand: true});
    const rule = separator();   // (set off from this computer's accounts, and from the host before)
    rule.add_style_class_name('claude-host-rule');
    section.add_child(rule);

    const head = box('claude-group-head', {x_expand: true});
    head.add_child(new St.Icon({icon_name: Icons.gnome.host, style_class: 'claude-button-icon'}));
    head.add_child(label(host, 'claude-host-title'));
    const real = info.result && info.result.host && info.result.host.split('.')[0] !== host ? info.result.host : '';
    if (real)
        head.add_child(label(real, 'claude-small claude-dim'));
    head.add_child(new St.Widget({x_expand: true}));
    head.add_child(label(info.loading && !info.result ? 'connecting…'
        : !info.updatedAt ? ''
            : ctx.now - info.updatedAt < 60000 ? 'updated just now'
                : L.fmt('updated %1 ago', L.duration(ctx.now - info.updatedAt)), 'claude-small claude-dim'));
    if (info.result && (info.result.dismissed || 0) > 0) {
        head.add_child(tips.add(iconButton(Icons.gnome.showHidden, () => ctx.remoteUndismissAll(host)),
            L.fmt('Show Hidden Chats Again (%1)', info.result.dismissed)));
    }
    head.add_child(tips.add(iconButton(Icons.gnome.refresh, () => ctx.pollHost(host)),
        [L.fmt('Refresh %1', host), L.fmt("Checked every %1 seconds while it's shown.", ctx.remotePollSeconds)]));
    head.add_child(tips.add(iconButton(Icons.gnome.hide, () => ctx.toggleHost(host)),
        [L.fmt('Stop showing %1', host), 'Pick it again with the SSH hosts button at the top.']));
    section.add_child(head);

    if (info.error) {
        const err = stale ? L.fmt('%1 Showing what it said %2 ago.', info.error, L.duration(ctx.now - info.updatedAt))
            : info.error;
        const l = label(err, 'claude-fg-bad claude-indent', {x_expand: true});
        l.clutter_text.line_wrap = true;
        l.clutter_text.ellipsize = 0;
        section.add_child(l);
    }
    groups.forEach(g => {
        const s = buildGroupSection(ctx, g, {last: true, remoteHost: host, accounts: groups.length});
        if (stale)
            s.opacity = 128;
        section.add_child(s);
    });
    if (info.ok && groups.length === 0)
        section.add_child(label('No Claude Code config on this host (~/.claude, ~/.claude-*)', 'claude-dim claude-indent'));
    return section;
}
