// The panel button and its popup: polls code/talpy_den.py (and the SSH
// hosts you picked, through code/remote.py), sends notifications, and runs
// what you click through code/jump.py. A port of the Plasma widget's
// main.qml, CompactRepresentation.qml and FullRepresentation.qml.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import * as L from './logic.js';
import {Notifier} from './notifier.js';
import {Runner} from './runner.js';
import {Pets} from './ui/pets.js';
import {buildGroupSection, buildHostSection} from './ui/groupSection.js';
import {TalpyIcon} from './ui/talpyIcon.js';
import {buildPermsView} from './ui/permsView.js';
import {buildWeekView} from './ui/weekView.js';
import {box, column, emptyState, iconButton, label, paragraph, scaleFactor, textButton, Tooltips} from './ui/widgets.js';
import * as Icons from './ui/icons.js';

const USAGE_PAGE = 'https://claude.ai/settings/usage';
const WEEK_REFRESH_S = 600;   // the Recap tab reads again while it's open

export const Indicator = GObject.registerClass(
class TalpyDenIndicator extends PanelMenu.Button {
    // away: {lockedAt, snapshot} when the screen was locked before this
    // (GNOME Shell turns extensions off while it's locked): the summary of
    // what happened meanwhile goes out once the first checks are back.
    // tracker: the one from before the lock (what it saw of each chat), so the
    // first checks tell what changed meanwhile; notifier: its notifications,
    // still in the tray (a chat's "needs your input" included)
    _init(extension, away = null, tracker = null, notifier = null) {
        super._init(0.5, 'Talpy Den', false);
        this._extension = extension;
        this._settings = extension.getSettings();
        this._notificationSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.notifications'});
        this._soundSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.sound'});
        this._runner = new Runner(GLib.build_filenamev([extension.path, 'code']));
        this.petsDir = GLib.build_filenamev([extension.path, 'pets']);
        this.iconsDir = GLib.build_filenamev([extension.path, 'icons']);   // (the widget's own: build.sh)
        this._notifier = notifier || new Notifier(this.petsDir);
        this._notifier.owner = this;
        this._tracker = tracker || new L.Tracker();
        this.tips = new Tooltips();

        this._status = null;          // parsed output of talpy_den.py
        this._errorText = '';
        this._actionError = '';
        this._actionInfo = '';
        this._sshHosts = [];          // ~/.ssh/config's hosts (remote.py --hosts)
        this._containersHere = [];    // this computer's containers (remote.py --hosts)
        this._containerNotes = [];    // an engine here that couldn't list its containers, and why
        this._hostContainers = {};    // SSH host -> {containers, notes, at} or {error} (remote.py --containers)
        this.remote = {};             // host -> {loading, ok, error, result, updatedAt}
        this._remotePolling = new Set();
        this._polling = false;
        this._timers = {};
        // Popup state kept by row key (rows are rebuilt with new data)
        // (morePages: a paged list's key -> how many pages past its first show;
        // recentMore: group key -> {recent, asked}, an account's recent chats as
        // a check that listed more has them)
        this.ui = {expandedAgents: {}, expandedAgent: {}, expandedRecent: {}, expandedStarred: {}, expandedPeek: {}, expandedStats: {},
            morePages: {}, recentMore: {}, stopConfirm: '', shareConfirm: null, deleteAsk: null, openMenu: null, tab: 'chats'};
        this._recentAsked = {};   // group key -> how many recent chats a check was asked for (till it's folded)
        // The Recap tab's days and what week.py said of them (it runs only
        // while that tab is open: setTab, loadWeek)
        // (span: day, week or all; open: the day or project whose chats are unfolded)
        this.week = {span: 'week', back: 0, account: '', recap: null, error: '', busy: false, copied: '', open: ''};
        // The Permissions tab and what week.py --permissions said (it runs only
        // while that tab is open: setTab, loadPerms)
        // (asking: the rule whose Allow asks first; ruleBusy, ruleMessage: one
        // being written, what it did; rules: suggest rules (the recap-rules
        // setting); revoking: the permission you gave whose Revoke asks first;
        // ruleRevoked: the message is a revoke's; ruleFailed: it says why
        // nothing changed (red); allGranted: all those
        // permissions shown, not the first few)
        // (asking, revoking, ruleBusy: host|id; ruleHost: where the last one was; allGranted: by host)
        this.perms = {data: null, error: '', busy: false, asking: '', ruleBusy: '', ruleMessage: '', ruleHost: '',
            rules: this._settings.get_boolean('recap-rules'), revoking: '', ruleRevoked: false, ruleFailed: false, allGranted: {}};
        this._weekAsked = 0;
        this._permsAgain = false;     // read the permissions again once the read on its way is in (a rule changed meanwhile)
        // Turns that ended while the menu was closed (row key -> "done"), for
        // the hotkey; forgotten when the menu opens
        this._unseen = {};
        this._lastHotkey = null;   // {key, at}: where the hotkey went last
        this._digest = null;       // the "while you were away" card, until the popup has shown it
        this._digestSeen = false;
        this._away = away && this._settings.get_boolean('away-digest') ? {...away, heard: new Set()} : null;

        this._buildPanel();
        this._buildMenu();
        this._pets = new Pets(this);
        this._pets.watchScroll(this._list, this._scroll.vadjustment);   // (stages out of sight hold still)

        this._settingsIds = [
            ...['poll-interval', 'idle-poll-interval'].map(key =>
                this._settings.connect(`changed::${key}`, () => this._restartPollTimer())),
            this._settings.connect('changed::remote-poll-seconds', () => this._restartRemoteTimer()),
            this._settings.connect('changed::ssh-hosts', () => this._onHostsChanged()),
            this._settings.connect('changed::show-containers', () => this._onShowContainers()),
            this._settings.connect('changed::container-days', () => this.reloadHosts()),
            ...['extra-config-dirs', 'keep-done-hours', 'recent-chats', 'show-tokens', 'usage-refresh-minutes'].map(key =>
                this._settings.connect(`changed::${key}`, () => this.refreshAll())),
            ...['show-usage-in-panel', 'show-pet', 'chat-pets'].map(key =>
                this._settings.connect(`changed::${key}`, () => this.rerender())),
            this._settings.connect('changed::playful-talpy', () => this._pets.playfulChanged()),
            this._settings.connect('changed::recap-rules', () => {
                this.perms.rules = this._settings.get_boolean('recap-rules');
                this.rerender();
            }),
            this._settings.connect('changed::recap-currency', () => {
                if (this.menu.isOpen && this.ui.tab === 'week')
                    this.loadWeek();
            }),
        ];
        this._restartPollTimer();
        this._restartRemoteTimer();
        this._loadHosts();
        for (const host of this.shownHosts)
            this.pollHost(host);   // (now, not a check interval later)
        if (this._away) {
            // hosts that don't answer soon are left out
            this._later('awayDigest', 20000, () => this._sendAwayDigest());
        }
    }

    // ---------------------------------------------------------------- data

    get groups() {
        return this._status ? this._status.groups : [];
    }

    // Each account's plan usage, shown once with the newest numbers (L.withUsage)
    get usageOwners() {
        return L.usageOwners(this.groups, this.shownHosts.map(h => [h, this.remote[h]?.result?.groups || []]));
    }

    // The SSH hosts and containers you picked (with Show containers off, the
    // containers stay picked but aren't shown, and no engine is asked anything)
    get pickedHosts() {
        return this._settings.get_strv('ssh-hosts').map(h => h.trim()).filter(h => h.length);
    }

    get shownHosts() {
        const containers = this._settings.get_boolean('show-containers');
        return this.pickedHosts.filter(h => containers || !L.containerOf(h));
    }

    // A container as its last listing had it ({engine, name, image, running, activeAt, folderShort, …}), or null
    containerInfo(id) {
        const c = L.containerOf(id);
        if (!c)
            return null;
        const list = c.host ? (this._hostContainers[c.host] || {}).containers || [] : this._containersHere;
        return list.find(x => x.id === id) || null;
    }

    // Everything on the dashboard: this computer's accounts, then the hosts'
    // (a host's copy of an account shown elsewhere too has its plan usage there: L.withUsage)
    get allGroups() {
        return this.groups.concat(L.remoteGroups(this.shownHosts, this.remote, this.usageOwners));
    }

    get now() {
        return this._status ? this._status.generatedAt : Date.now();
    }

    get canShareChats() {
        return this._status !== null && this._status.canShare === true;
    }

    get shareAccounts() {
        return this.groups.filter(g => !!g.shareProfile);
    }

    get petColors() {
        return this._pets.colors;
    }

    get remotePollSeconds() {
        return Math.max(10, this._settings.get_int('remote-poll-seconds'));
    }

    groupOfProfile(profileDir) {
        return this.groups.find(g => g.profileKeys.indexOf(profileDir) >= 0) || null;
    }

    stageFor(groupKey, chats) {
        return this._pets.stageFor(groupKey, chats);
    }

    get _configDirArgs() {
        return this._settings.get_string('extra-config-dirs').split(',').map(d => d.trim())
            .filter(d => d.length).flatMap(d => ['--config-dir', d]);
    }

    get _listArgs() {
        const args = ['--done-hours', String(Math.max(0, this._settings.get_int('keep-done-hours'))),
            ...L.recentArgs(this._settings.get_int('recent-chats'))];
        if (!this._settings.get_boolean('show-tokens'))
            args.push('--no-tokens');
        // (here and on hosts: an account's plan usage this old is fetched while a chat works)
        args.push('--usage-refresh', String(Math.max(0, this._settings.get_int('usage-refresh-minutes'))));
        return args;
    }

    // ---------------------------------------------------------------- polling

    _restartPollTimer(refreshNow = true) {
        this._clearTimer('poll');
        this._pollMs = this._pollInterval();
        this._timers.poll = GLib.timeout_add(GLib.PRIORITY_DEFAULT, this._pollMs, () => {
            this.refresh();
            return GLib.SOURCE_CONTINUE;
        });
        if (refreshNow)
            this.refresh();
    }

    // Less often while nothing runs and the menu is closed (L.pollInterval)
    _pollInterval() {
        const overall = this._status ? L.overall(this.allGroups) : '';
        return L.pollInterval(this._settings.get_int('poll-interval'), this._settings.get_int('idle-poll-interval'),
            overall, this.menu.isOpen);
    }

    _adjustPollTimer() {
        if (this._pollInterval() !== this._pollMs)
            this._restartPollTimer(false);
    }

    _restartRemoteTimer() {
        this._clearTimer('remote');
        this._timers.remote = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, this.remotePollSeconds, () => {
            for (const host of this.shownHosts) {
                // (a container that's stopped, or gone, isn't checked until Start or Refresh)
                if (!this.remote[host]?.stopped && !this.remote[host]?.gone)
                    this.pollHost(host);
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _clearTimer(name) {
        if (this._timers[name]) {
            GLib.source_remove(this._timers[name]);
            delete this._timers[name];
        }
    }

    _later(name, ms, callback) {
        this._clearTimer(name);
        this._timers[name] = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
            delete this._timers[name];
            callback();
            return GLib.SOURCE_REMOVE;
        });
    }

    refreshAll() {
        this.refresh();
        for (const host of this.shownHosts)
            this.pollHost(host);
    }

    // Refresh (its button): the plan usage too, of every account whose numbers
    // are over a minute old (talpy_den.py --fetch-usage); the status says a
    // fetch is on its way
    async fetchUsage() {
        await this._runner.run('talpy_den.py', ['--fetch-usage', ...this._configDirArgs]);
        if (!this._destroyed)
            this.refresh();
    }

    async refresh() {
        // A still-running poll is still coming: don't stack another
        if (this._polling)
            return;
        this._polling = true;
        // (poll.py runs talpy_den.py with its compiled code cached)
        const out = await this._runner.run('poll.py', [...this._configDirArgs, ...this._listArgs], {poll: true});
        this._polling = false;
        if (this._destroyed || out.cancelled)
            return;
        const result = L.statusResult(out.stdout, out.stderr);
        if (result.error) {
            this._errorText = result.error;
        } else {
            // The new status first: a reaction that fails mustn't keep the
            // popup on old data (on Plasma one froze it at a limit reset)
            this._errorText = result.errorText;
            this._status = result.status;
            try {
                this._track('', result.status.groups, result.status.generatedAt, '');
            } catch (e) {
                console.error(`Talpy Den: following the chats failed: ${e.message}\n${e.stack}`);
            }
        }
        this._render();
        this._adjustPollTimer();
    }

    // Notifications, pet reactions and the sound when sessions change state.
    // Each is on its own: one that fails doesn't stop the others.
    _track(source, groups, nowMs, host) {
        const out = this._tracker.track(source, groups, nowMs, host, {
            notifyWaiting: this._settings.get_boolean('notify-waiting'),
            notifyDone: this._settings.get_boolean('notify-done'),
            notifyDoneMinSeconds: this._settings.get_int('notify-done-min-seconds'),
        });
        const notices = [];   // (an account whose chats a usage limit stopped can go on now)
        const resets = [...this._tracker.celebrateResets(source, groups), ...this._tracker.chatEvents(source, groups, host, notices)];
        const noticed = this._settings.get_boolean('notify-done') ? notices : [];
        const pose = this._settings.get_boolean('show-pet');
        this._noteUnseen(source, out);
        // (after a lock as long as the summary asks for, the summary tells
        // what changed meanwhile: the first check of each source keeps quiet)
        const summed = !!this._away && !this._away.heard.has(source)
            && Date.now() - this._away.lockedAt >= this._settings.get_int('away-minutes') * 60000;
        if (this._away) {
            this._away.heard.add(source);
            if (['', ...this.shownHosts.map(h => `ssh:${h}`)].every(s => this._away.heard.has(s)))
                this._sendAwayDigest();
        }
        const guard = (what, fn) => {
            try {
                fn();
            } catch (e) {
                console.error(`Talpy Den: ${what} failed: ${e.message}\n${e.stack}`);
            }
        };
        for (const c of out.close)
            guard('closing a notification', () => this._notifier.close(c.key, c.kind));
        for (const n of summed ? [] : [...out.notify, ...noticed])
            guard('a notification', () => this._notifier.notify(n, pose, ind => ind._openFromNotification(n)));
        guard('closing notifications', () => this._notifier.closeMissing(source, out.present));
        for (const event of [...out.pets, ...resets])
            guard(`the pets' "${event.kind}"`, () => this._pets.event(event));
        const sound = out.sound || (noticed.length ? 'done' : '');
        if (sound && !summed)
            guard('a sound', () => this._playSound(sound));
    }

    // Turns that ended while you weren't looking (as long as the "finished"
    // notifications ask for), for the hotkey
    _noteUnseen(source, out) {
        const min = this._settings.get_int('notify-done-min-seconds') * 1000;
        for (const f of out.finished) {
            if (f.stop)
                delete this._unseen[f.key];   // (a limit stopped it: nothing to look at)
            else if (!this.menu.isOpen && f.took >= min)
                this._unseen[f.key] = 'done';
        }
        for (const key of Object.keys(this._unseen)) {
            if (L.keyOfSource(key, source) && (!out.present.has(key) || out.states[key] === 'working'))
                delete this._unseen[key];
        }
    }

    // ---------------------------------------------------------------- the hotkey and coming back

    // The hotkey (next-chat-shortcut): the chat that needs you (waiting the
    // longest, then a finished turn you haven't seen); pressed again soon
    // after, the next one; with none, the menu opens or closes
    goToNextChat() {
        const list = L.chatsNeedingYou(this.allGroups, this._unseen);
        const now = Date.now();
        const i = L.nextChatIndex(list, this._lastHotkey, now);
        if (i < 0) {
            this._lastHotkey = null;
            this.menu.toggle();
            return;
        }
        const c = list[i];
        this._lastHotkey = {key: c.key, at: now};
        if (this._unseen[c.key]) {
            delete this._unseen[c.key];
            this._updatePanel();
        }
        this._openChat(c);
    }

    dismissDigest() {
        this._digest = null;
        this._notifier.close('away-digest', this._notifier.kindOf('away-digest'));
        this.rerender();
    }

    _buildDigestCard() {
        const d = this._digest;
        const card = column('claude-digest', {x_expand: true});
        const head = box('claude-line', {x_expand: true});
        head.add_child(label(d.title, 'claude-strong', {x_expand: true}));
        head.add_child(this.tips.add(iconButton(Icons.gnome.close, () => this.dismissDigest()), 'Dismiss'));
        card.add_child(head);
        card.add_child(paragraph(d.body, 'claude-small'));
        if (d.first) {
            card.add_child(textButton('Open the chat that needs you', () => {
                this.dismissDigest();
                this._openChat(d.first);
            }, 'claude-text-button claude-confirm-button'));
        }
        return card;
    }

    _openChat(c) {
        if (c.host)
            this.remoteShow(c.host, c.session);
        else
            this.jumpTo(c.session.sessionId, c.session.profileDir);
    }

    // What happened while the screen was locked: a card at the top of the
    // popup until you've seen it, and (with notifications on) one
    // notification, instead of the ones that would have piled up (none were
    // sent meanwhile)
    _sendAwayDigest() {
        const away = this._away;
        this._away = null;
        this._clearTimer('awayDigest');
        if (!away || !this._status || this._destroyed)
            return;
        let digest = null;
        try {
            digest = L.awayDigest(away, this.allGroups, Date.now(), this._settings.get_int('away-minutes'));
        } catch (e) {
            console.error(`Talpy Den: the away summary failed: ${e.message}\n${e.stack}`);
        }
        if (!digest)
            return;
        this._digest = digest;
        this._digestSeen = false;
        this.rerender();
        if (!this._settings.get_boolean('notify-waiting') && !this._settings.get_boolean('notify-done'))
            return;
        const first = digest.first;
        // its own kind: closeMissing() closes 'waiting' notifications of chats that are gone
        this._notifier.notify({key: 'away-digest', kind: 'digest', waiting: !!first, title: digest.title,
            body: digest.body, icon: first ? Icons.gnome.warning : Icons.gnome.done, session: null,
            action: first ? 'Open the chat that needs you' : 'Show chats'},
        this._settings.get_boolean('show-pet'), ind => (first ? ind._openChat(first) : ind.menu.open()));
    }

    // A click on a notification about no chat (an error): the popup, with
    // the error line still there
    showChats() {
        this.setTab('chats');
        this.menu.open();
    }

    // The notifications, kept while the screen is locked (extension.js): the
    // indicator made after it takes them over, so they stay in the tray
    releaseNotifier() {
        const notifier = this._notifier;
        this._notifier = null;
        if (notifier)
            notifier.owner = null;
        return notifier;
    }

    _openFromNotification(n) {
        if (n.host)
            this.remoteShow(n.host, n.session);
        else
            this.jumpTo(n.session.sessionId, n.session.profileDir);
    }

    // One sound per poll at most: the most urgent. Quiet during Do Not Disturb.
    _playSound(kind) {
        if (!this._settings.get_boolean('notify-sound') || !this._notificationSettings.get_boolean('show-banners'))
            return;
        const sound = this._settings.get_string(
            kind === 'waiting' ? 'sound-waiting' : kind === 'failed' ? 'sound-failed' : 'sound-done');
        if (!sound)
            return;
        this._runner.run('notify_sound.py', [sound, '--volume', String(this._settings.get_int('sound-volume')),
            '--theme', this._soundSettings.get_string('theme-name')]);
    }

    // ---------------------------------------------------------------- actions

    async _helper(script, args) {
        const out = await this._runner.run(script, args);
        return L.helperResult(out.stdout, out.stderr);
    }

    _showError(text) {
        this._actionError = text;
        this._later('actionError', 10000, () => {
            this._actionError = '';
            this.rerender();
        });
        this.rerender();
    }

    _showInfo(text) {
        this._actionInfo = text;
        this._later('actionInfo', 12000, () => {
            this._actionInfo = '';
            this.rerender();
        });
        this.rerender();
    }

    _oops() {
        this._pets.event({kind: 'oops', text: "Hmm, that didn't work.", key: ''});
    }

    // A jump's answer: done (close the popup), or say what went wrong
    _jumped(result) {
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            this.menu.close();
            return;
        }
        this._showError(L.fmt("Couldn't open the chat: %1", result.message));
        this._oops();
        if (!this.menu.isOpen) {
            this._notifier.notify({key: 'jump-error', kind: 'error', title: "Couldn't open the chat",
                body: result.message, icon: Icons.gnome.error, session: null},
            this._settings.get_boolean('show-pet'), ind => ind.showChats());
        }
    }

    // profileDir picks the right copy of a chat shared across profiles
    async jumpTo(sessionId, profileDir) {
        const profile = profileDir ? ['--profile', profileDir] : [];
        this._jumped(await this._helper('jump.py', [sessionId, ...profile, ...this._configDirArgs]));
    }

    // A chat by its id (the Recap's): its row if it's listed, else reopened
    // where the Terminal | VS Code switch says, as a recent chat is (Plasma's
    // openChatById)
    openChatById(chatId, profileDir) {
        let row = null, other = null;
        for (const g of this.groups) {
            for (const s of g.sessions) {
                if (s.chatId !== chatId && s.sessionId !== chatId)
                    continue;
                if (!profileDir || g.profileKeys.includes(profileDir))
                    row = row || s;
                else
                    other = other || s;
            }
        }
        row = row || other;
        const group = this.groupOfProfile(profileDir);
        if (row)
            this.jumpTo(row.sessionId, row.profileDir);
        else if (group && this.openInVscode(group, ''))
            this.resumeInVscode(chatId, profileDir);
        else
            this.jumpTo(chatId, profileDir);
    }

    // busy: you were told it's working or waiting (else only an idle one is stopped)
    async stopSession(sessionId, profileDir, busy = false) {
        const profile = profileDir ? ['--profile', profileDir] : [];
        const result = await this._helper('jump.py',
            ['--stop', sessionId, ...profile, ...busy ? ['--busy'] : [], ...this._configDirArgs]);
        if (this._destroyed)
            return;   // turned off meanwhile (e.g. the screen locked)
        if (!result.ok)
            this._showError(L.fmt("Couldn't stop the chat: %1", result.message));
        else if (L.stopSaysMore(result.message))
            this._showInfo(result.message);
        this.refresh();
    }

    // Esc in the tmux pane of a working chat
    async interruptSession(sessionId, profileDir) {
        const profile = profileDir ? ['--profile', profileDir] : [];
        const result = await this._helper('jump.py', ['--interrupt', sessionId, ...profile, ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (!result.ok)
            this._showError(L.fmt("Couldn't interrupt the chat: %1", result.message));
        this.refresh();
    }

    // Small helper actions whose only effect is on the widget's own list
    async runHelper(args) {
        const result = await this._helper('jump.py', [...args, ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (!result.ok)
            this._showError(result.message);
        this.refresh();
    }

    dismissSession(sessionId) {
        this.runHelper(['--dismiss', sessionId]);
    }

    // The menu's Show Hidden Chats Again: its answer says how many
    async showHiddenChats() {
        const result = await this._helper('jump.py', ['--undismiss-all', ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (result.ok)
            this._showInfo(result.message);
        else
            this._showError(result.message);
        this.refresh();
    }

    // Delete… asks first (ui.deleteAsk, shown under the chat's line: {key: the
    // line's key, id, profileDir, host, busy: being looked at, question,
    // message: why it can't}), with what goes to the Trash and on which
    // accounts (jump.py --delete-chat ID --describe; an SSH host's: remote.py
    // --delete-chat HOST ID PROFILE, to that host's Trash)
    _deleteArgs(a) {
        return a.host ? ['--delete-chat', a.host, a.id, ...a.profileDir ? [a.profileDir] : []]
            : ['--delete-chat', a.id, ...a.profileDir ? ['--profile', a.profileDir] : []];
    }

    async askDelete(rowKey, id, profileDir, host = '') {
        if (this.ui.deleteAsk?.key === rowKey) {   // (again: the question goes)
            this.cancelDelete();
            return;
        }
        const a = {key: rowKey, id, profileDir: profileDir || '', host, busy: true, question: '', message: ''};
        this.ui.deleteAsk = a;
        this.rerender();
        const result = await this._helper(host ? 'remote.py' : 'jump.py',
            [...this._deleteArgs(a), '--describe', ...host ? [] : this._configDirArgs]);
        if (this._destroyed || this.ui.deleteAsk !== a)
            return;   // (cancelled, or another one asked meanwhile)
        this.ui.deleteAsk = {...a, busy: false, question: result.ok ? result.question || result.message || '' : '',
            message: result.ok ? '' : result.message || "It can't be deleted."};
        this.rerender();
    }

    cancelDelete() {
        this.ui.deleteAsk = null;
        this.rerender();
    }

    async confirmDelete() {
        const a = this.ui.deleteAsk;
        this.cancelDelete();
        const result = await this._helper(a.host ? 'remote.py' : 'jump.py',
            [...this._deleteArgs(a), ...a.host ? [] : this._configDirArgs]);
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            this._showInfo(result.message);   // (Moved to the Trash)
        } else {
            this._showError(result.message);
        }
        if (a.host)
            this.pollHost(a.host);
        else
            this.refresh();
    }

    // vscode: in VS Code's Claude extension instead of a terminal
    async newChat(profile, folder, vscode = false) {
        this.ui.openMenu = null;
        const cwd = folder ? ['--cwd', folder] : [];
        this._newChatDone(await this._helper('jump.py',
            ['--new-chat', profile, ...cwd, ...vscode ? ['--vscode'] : [], ...this._configDirArgs]));
    }

    // The folder dialog takes over from the popup; cancelling it does nothing
    async newChatChoosingFolder(profile, vscode = false) {
        this.ui.openMenu = null;
        this.menu.close();
        this._newChatDone(await this._helper('jump.py',
            ['--new-chat', profile, '--choose-folder', ...vscode ? ['--vscode'] : [], ...this._configDirArgs]));
    }

    // VS Code connected to an SSH host, with a new chat (in folder there, or home)
    async remoteNewChatVscode(host, folder) {
        this.ui.openMenu = null;
        const cwd = folder ? ['--cwd', folder] : [];
        this._newChatDone(await this._helper('jump.py', ['--remote-new-vscode', host, ...cwd]));
    }

    // Claude's own login for an account that isn't logged in, in a terminal
    // (accounts.py --login; an SSH host's account: its loginCommand over ssh)
    async logIn(group, host) {
        if (host) {
            this.remoteOpen(host, group.loginCommand);
            return;
        }
        const result = await this._helper('accounts.py', ['--login', group.chatProfile, ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (result.ok)
            this.menu.close();
        else
            this._showError(L.fmt("Couldn't log in: %1", result.message));
    }

    // A recent chat, reopened in VS Code's Claude extension (in its folder)
    async resumeInVscode(sessionId, profileDir) {
        const profile = profileDir ? ['--profile', profileDir] : [];
        this._jumped(await this._helper('jump.py', ['--resume', sessionId, ...profile, '--vscode', ...this._configDirArgs]));
    }

    // A recent chat of an SSH host, reopened in VS Code connected to it
    async remoteResumeVscode(host, sessionId, folder) {
        const cwd = folder ? ['--cwd', folder] : [];
        this._jumped(await this._helper('jump.py', ['--remote-resume-vscode', host, sessionId, ...cwd]));
    }

    // VS Code is here (only the account it runs on can use it)
    get vscodeInstalled() {
        return this._status?.vscode?.installed === true;
    }

    // There's a claude command here (host: on that SSH host)
    cliHere(host) {
        return L.cliInstalled(host ? this.remote[host]?.result : this._status);
    }

    // Where this account's chats open (logic.js openInVscode)
    openInVscode(group, host) {
        return L.openInVscode(group, this.vscodeInstalled, this.cliHere(host), this.newChatInVscode);
    }

    // Where chats open, new and recent: the Terminal | VS Code switch
    get newChatInVscode() {
        return this._settings.get_boolean('new-chat-in-vscode');
    }

    setNewChatInVscode(on) {
        this._settings.set_boolean('new-chat-in-vscode', on);
        this.rerender();
    }

    _newChatDone(result) {
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            this.menu.close();
        } else {
            this._showError(L.fmt("Couldn't open a new chat: %1", result.message));
        }
    }

    // ---------------------------------------------------------------- popup state

    rerender() {
        this._render(true);
    }

    togglePeek(rowKey) {
        this.ui.expandedPeek[rowKey] = !this.ui.expandedPeek[rowKey];
        this.rerender();
    }

    // The files a chat changed, before ↔ now (turn: since your last prompt),
    // side by side in VS Code (jump.py --changes)
    async showChanges(chatId, profileDir, turn = false) {
        const profile = profileDir ? ['--profile', profileDir] : [];
        const result = await this._helper('jump.py',
            ['--changes', chatId, ...profile, ...turn ? ['--turn'] : [], ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            this.menu.close();
        } else {
            this._showError(L.fmt("Couldn't compare the changes: %1", result.message));
        }
    }

    toggleAgents(rowKey) {
        this.ui.expandedAgents[rowKey] = !this.ui.expandedAgents[rowKey];
        this.rerender();
    }

    // One subagent unfolded: its task, last steps and report (key: L.agentKey)
    toggleAgent(key) {
        this.ui.expandedAgent[key] = !this.ui.expandedAgent[key];
        this.rerender();
    }

    // A subagent's whole run, saved as Markdown and opened in your app for
    // those (jump.py --agent-run; remote.py fetches it from an SSH host)
    async openAgentRun(session, agent, remoteHost = '') {
        const {script, args} = L.agentRunCommand(session, agent, remoteHost);
        const result = await this._helper(script, remoteHost ? args : [...args, ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            this.menu.close();
        } else {
            this._showError(L.fmt("Couldn't open the subagent's run: %1", result.message));
            this._oops();
        }
    }

    toggleStats(groupKey) {
        this.ui.expandedStats[groupKey] = !this.ui.expandedStats[groupKey];
        this.rerender();
    }

    // Recent chats and ★ Starred chats: a page at a time (L.recentPage);
    // folded again, a list shows its first page
    get pageSize() {
        return L.pageSize(this._settings.get_int('recent-chats'));
    }

    pagesShown(listKey) {
        return 1 + (this.ui.morePages[listKey] || 0);
    }

    showMore(listKey) {
        this.ui.morePages[listKey] = (this.ui.morePages[listKey] || 0) + 1;
        this.rerender();
    }

    toggleRecent(groupKey, wasOpen) {
        this.ui.expandedRecent[groupKey] = !wasOpen;
        if (wasOpen) {
            delete this.ui.morePages[`${groupKey}|recent`];
            delete this.ui.recentMore[groupKey];
            delete this._recentAsked[groupKey];
        }
        this.rerender();
    }

    toggleStarred(groupKey, wasOpen) {
        this.ui.expandedStarred[groupKey] = !wasOpen;
        if (wasOpen)
            delete this.ui.morePages[`${groupKey}|starred`];
        this.rerender();
    }

    // The account's recent chats past the status' (its next pages): a check
    // (this computer's or the host's) that lists count of them, once for each
    // page wanted (one that failed isn't run again till the list is folded)
    async fetchRecent(groupKey, groupId, host, count) {
        if ((this._recentAsked[groupKey] || 0) >= count)
            return;
        this._recentAsked[groupKey] = count;
        const args = [...this._listArgs, '--recent', String(count), '--no-tokens', '--usage-refresh', '0'];
        const out = host ? await this._runner.run('remote.py', ['--status', host, ...args], {poll: true})
            : await this._runner.run('poll.py', [...this._configDirArgs, ...args], {poll: true});
        if (this._destroyed || out.cancelled || this._recentAsked[groupKey] !== count)
            return;   // (folded meanwhile: its first page shows; or a bigger one's on its way)
        let result = null;
        if (host) {
            const answer = L.helperResult(out.stdout, out.stderr);
            if (answer.ok && answer.result)
                result = L.toLocalClock(answer.result, Date.now() - (answer.result.generatedAt || Date.now()));
        } else {
            const status = L.statusResult(out.stdout, out.stderr);
            result = status.error ? null : status.status;
        }
        const g = result && result.groups ? result.groups.find(x => x.id === groupId) : null;
        if (!g)
            return;
        this.ui.recentMore[groupKey] = {recent: g.recent || [], asked: count};
        this.rerender();
    }

    // ☆ on a chat stars it: it stays listed under its account's ★ Starred
    // chats, however old (jump.py --star, kept in Talpy Den's cache; an SSH
    // host's too, kept here); its ★ unstars it
    async setStar(chatId, host, on) {
        const result = await this._helper('jump.py', [on ? '--star' : '--unstar', chatId,
            ...host ? ['--host', host] : [], ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (!result.ok)
            this._showError(L.fmt("Couldn't star it: %1", result.message));
        if (host)
            this.pollHost(host);
        else
            this.refresh();
    }

    setStopConfirm(rowKey) {
        this.ui.stopConfirm = rowKey;
        this.rerender();
    }

    _toggleMenu(type, key, extra = {}) {
        const open = this.ui.openMenu;
        this.ui.openMenu = open && open.type === type && open.key === key ? null : {type, key, ...extra};
        this.rerender();
    }

    toggleNewChat(groupKey) {
        this._toggleMenu('newchat', groupKey);
    }

    toggleShareMenu(rowKey, chat) {
        this._toggleMenu('share', rowKey, {chat});
    }

    // ---------------------------------------------------------------- SSH hosts

    // --container-days, --picked: the containers listed (the picked ones always), or no containers at all
    get _containerArgs() {
        if (!this._settings.get_boolean('show-containers'))
            return ['--no-containers'];
        const picked = this.pickedHosts.filter(h => L.containerOf(h));
        return ['--container-days', String(Math.max(0, this._settings.get_int('container-days'))),
            ...picked.length ? ['--picked', picked.join(',')] : []];
    }

    // ~/.ssh/config's hosts and this computer's containers (at start, when
    // the picker opens, on Reload), with the SSH hosts' container lists as
    // they were last fetched (shown until they're fetched again)
    async _loadHosts() {
        const result = await this._helper('remote.py', ['--hosts', ...this._containerArgs]);
        if (!this._destroyed && result.ok) {
            this._sshHosts = result.hosts || [];
            this._containersHere = result.containers || [];
            this._containerNotes = result.notes || [];
            const kept = result.hostContainers || {};
            for (const host of Object.keys(kept)) {
                if (!(host in this._hostContainers))
                    this._hostContainers[host] = kept[host];
            }
            this._render();
        }
    }

    // An SSH host's containers (remote.py --containers there): fetched once
    // it's connected (its first check that works after start or after
    // failing) and on Reload, never on a timer
    async loadHostContainers(host) {
        if (!this._settings.get_boolean('show-containers') || L.containerOf(host))
            return;
        const result = await this._helper('remote.py', ['--containers', host, ...this._containerArgs]);
        if (this._destroyed)
            return;
        this._hostContainers = Object.assign({}, this._hostContainers, {
            [host]: result.ok ? {containers: result.containers || [], notes: result.notes || [], at: result.at || Date.now()}
                : Object.assign({}, this._hostContainers[host] || {}, {error: result.error || result.message || ''}),
        });
        this._render();
    }

    // The SSH hosts shown whose last check worked: their containers are in the picker
    get connectedHosts() {
        return this.shownHosts.filter(h => !L.containerOf(h) && this.remote[h] && this.remote[h].ok);
    }

    // Reload in the picker: ~/.ssh/config, this computer's containers and every connected host's
    reloadHosts() {
        this._loadHosts();
        for (const host of this.connectedHosts)
            this.loadHostContainers(host);
    }

    _onShowContainers() {
        if (this._settings.get_boolean('show-containers')) {
            this.reloadHosts();
        } else {
            this._containersHere = [];
            this._containerNotes = [];
            this._hostContainers = {};
        }
        this._onHostsChanged();
    }

    // A stopped container started (remote.py --start); it's checked once that's done
    startContainer(host) {
        this._setRemote(host, {loading: true});
        this._remoteAction('start', host, ['--start', host]);
    }

    toggleHost(host) {
        const list = this.pickedHosts;
        const i = list.indexOf(host);
        if (i >= 0)
            list.splice(i, 1);
        else
            list.push(host);
        this._settings.set_strv('ssh-hosts', list);
    }

    _onHostsChanged() {
        const next = {};
        for (const host of Object.keys(this.remote)) {
            if (!this.shownHosts.includes(host))
                this._forgetSource(`ssh:${host}`);   // shown again later, it starts afresh
        }
        for (const host of this.shownHosts) {
            if (host in this.remote)
                next[host] = this.remote[host];
            else
                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {   // just picked: load it now
                    if (!this._destroyed)
                        this.pollHost(host);
                    return GLib.SOURCE_REMOVE;
                });
        }
        this.remote = next;
        this.rerender();
    }

    async pollHost(host) {
        if (this._remotePolling.has(host))
            return;   // still waiting for the last answer
        this._remotePolling.add(host);
        this._setRemote(host, {loading: true});
        const out = await this._runner.run('remote.py', ['--status', host, ...this._listArgs], {poll: true});
        this._remotePolling.delete(host);
        if (this._destroyed || out.cancelled || !this.shownHosts.includes(host))
            return;   // unpicked while its check was running
        const answer = L.helperResult(out.stdout, out.stderr);
        if (answer.ok && answer.result && !this.remote[host]?.ok && !L.containerOf(host))
            this.loadHostContainers(host);   // (it's connected: its containers go in the picker)
        if (answer.ok && answer.result) {
            // on this computer's clock: the host's may be off
            const result = L.toLocalClock(answer.result, Date.now() - (answer.result.generatedAt || Date.now()));
            this._setRemote(host, {loading: false, ok: true, error: '', result, updatedAt: Date.now(),
                stopped: false, gone: false});
            try {
                this._track(`ssh:${host}`, result.groups, result.generatedAt, host);
            } catch (e) {
                console.error(`Talpy Den: following ${host}'s chats failed: ${e.message}\n${e.stack}`);
            }
        } else {
            // keep the last answer to show (dimmed) with the error
            this._setRemote(host, {loading: false, ok: false, error: answer.error || answer.message || 'no answer',
                stopped: !!answer.stopped, gone: !!answer.gone});
        }
    }

    // What a source's chats were (and their notifications): gone with the source
    _forgetSource(source) {
        this._tracker.forget(source);
        this._notifier.closeSource(source);
        for (const key of Object.keys(this._unseen)) {
            if (L.keyOfSource(key, source))
                delete this._unseen[key];
        }
    }

    _setRemote(host, patch) {
        if (!this.shownHosts.includes(host))
            return;
        const old = this.remote[host] || {loading: false, ok: false, error: '', result: null, updatedAt: 0};
        this.remote = Object.assign({}, this.remote, {[host]: Object.assign({}, old, patch)});
        this._render();
    }

    async _remoteAction(kind, host, args) {
        const result = await this._helper('remote.py', args);
        if (this._destroyed)
            return;
        if (result.ok) {
            this._actionError = '';
            if (kind === 'open')
                this.menu.close();
            else if (kind === 'show' || (kind === 'stop' && L.stopSaysMore(result.message)))
                this._showInfo(result.message);   // (Showing 2 hidden chats again; it was killed)
        } else {
            this._showError(kind === 'open' ? L.fmt("Couldn't open the chat: %1", result.message)
                : kind === 'stop' ? L.fmt("Couldn't stop the chat: %1", result.message) : result.message);
            this._oops();
            if (!this.menu.isOpen) {   // e.g. from a notification or the hotkey: say so
                this._notifier.notify({key: 'remote-error', kind: 'error', title: L.fmt("That didn't work on %1", L.hostLabel(host)),
                    body: this._actionError, icon: Icons.gnome.error, session: null},
                this._settings.get_boolean('show-pet'), ind => ind.showChats());
            }
        }
        if (kind !== 'open')
            this.pollHost(host);
    }

    // Bring up a session of an SSH host: background sessions and finished
    // chats open in a terminal (ssh); one running there shows where it runs
    // here (its VS Code window, the terminal of one, or the terminal with the
    // ssh connection)
    async remoteShow(host, session) {
        const cwd = session.cwd ? ['--cwd', session.cwd] : [];
        if (session.openCommand) {
            this.remoteOpen(host, session.openCommand);
        } else if (session.entrypoint === 'claude-vscode') {
            this._jumped(await this._helper('jump.py', ['--remote-vscode', host, session.sessionId, ...cwd]));
        } else {
            const vscode = session.vscodeTerminal ? ['--vscode-terminal', String(Math.trunc(session.vscodeTerminal)), ...cwd] : [];
            this._jumped(await this._helper('jump.py', ['--remote-terminal', host, '--name', session.name || '', ...vscode]));
        }
    }

    remoteOpen(host, command) {
        this.ui.openMenu = null;
        if (!command) {
            this._showError(L.fmt("This chat runs in a terminal on %1; Talpy Den can't bring it here.", L.hostLabel(host)));
            return;
        }
        this._remoteAction('open', host, ['--open', host, command]);
    }

    remoteStop(host, command) {
        this._remoteAction('stop', host, ['--run', host, command]);
    }

    // A chat with a process on the host (talpy_den.py --end there; busy:
    // you were told it's working or waiting), or one in tmux interrupted
    remoteEnd(host, sessionId, profileDir, busy = false) {
        this._remoteAction('stop', host, ['--end', host, sessionId, ...profileDir ? [profileDir] : [], ...busy ? ['--busy'] : []]);
    }

    remoteInterrupt(host, sessionId, profileDir) {
        this._remoteAction('stop', host, ['--interrupt', host, sessionId, ...profileDir ? [profileDir] : []]);
    }

    remoteDismiss(host, sessionId) {
        this._remoteAction('dismiss', host, ['--dismiss', host, sessionId]);
    }

    remoteUndismissAll(host) {
        this._remoteAction('show', host, ['--undismiss-all', host]);
    }

    // ---------------------------------------------------------------- shared chats
    // Share a chat with your other accounts, continue it on one of them, or
    // keep it on one only: jump.py does it (sharing.py).

    askKeepOnly(rowKey, chat, account) {
        this.ui.openMenu = null;
        this.ui.shareConfirm = {
            key: rowKey, chatId: chat.chatId, name: chat.name, profileKey: account.shareProfile,
            account: account.title,
            others: this.shareAccounts.filter(g => g !== account).map(g => g.title).join(', '),
        };
        this.rerender();
    }

    confirmKeepOnly() {
        const c = this.ui.shareConfirm;
        this.ui.shareConfirm = null;
        this.shareAction('keeponly', c.chatId, c.profileKey);
    }

    cancelKeepOnly() {
        this.ui.shareConfirm = null;
        this.rerender();
    }

    async shareAction(kind, chatId, profileKey) {
        this.ui.openMenu = null;
        this.rerender();
        const flag = {continue: '--continue', share: '--share', keeponly: '--unshare'}[kind];
        const profile = profileKey ? ['--profile', profileKey] : [];
        const result = await this._helper('jump.py', [flag, chatId, ...profile, ...this._configDirArgs]);
        if (this._destroyed)
            return;
        if (!result.ok) {
            this._showError(result.message);
            this._oops();
        } else if (kind === 'continue') {
            this._actionError = '';
            this.menu.close();
        } else {
            this._actionError = '';
            this._showInfo(result.message);
        }
        this.refresh();
    }

    // ---------------------------------------------------------------- panel

    _buildPanel() {
        const panelBox = box('panel-status-indicators-box claude-panel');
        const iconBin = new St.Widget({layout_manager: new Clutter.BinLayout(), y_align: Clutter.ActorAlign.CENTER});
        this._spark = new TalpyIcon('claude-spark');
        // the count of chats that need you (else of finished turns you haven't seen), on the spark's corner
        this._badge = new St.Label({style_class: 'claude-badge', visible: false,
            x_align: Clutter.ActorAlign.END, y_align: Clutter.ActorAlign.START,
            translation_x: 6, translation_y: -4});
        iconBin.add_child(this._spark);
        iconBin.add_child(this._badge);
        this._usage = new St.Label({style_class: 'claude-panel-usage', y_align: Clutter.ActorAlign.CENTER, visible: false});
        panelBox.add_child(iconBin);
        panelBox.add_child(this._usage);
        this.add_child(panelBox);
    }

    // Middle-click refreshes; any other click opens the popup
    vfunc_event(event) {
        if (event.type() === Clutter.EventType.BUTTON_PRESS && event.get_button() === Clutter.BUTTON_MIDDLE) {
            this.refreshAll();
            return Clutter.EVENT_STOP;
        }
        return super.vfunc_event(event);
    }

    _updatePanel() {
        const groups = this.allGroups;
        const c = L.counts(groups);
        const overall = L.overall(groups, c);
        this._spark.setState(L.stateClass(overall), overall);
        // One count at a time, the most urgent: chats that need you (red),
        // else turns that finished since you last opened the popup (green)
        const done = Object.keys(this._unseen).length;
        this._badge.text = String(c.waiting || done);
        this._badge.visible = c.waiting > 0 || done > 0;
        if (c.waiting > 0)
            this._badge.remove_style_class_name('claude-badge-done');
        else
            this._badge.add_style_class_name('claude-badge-done');
        const w = this._settings.get_boolean('show-usage-in-panel') ? L.panelWindow(groups) : null;
        this._usage.visible = w !== null;
        if (w) {
            this._usage.text = `${Math.round(w.pct)}%`;
            if (w.pct >= 90)
                this._usage.add_style_class_name('claude-fg-bad');
            else
                this._usage.remove_style_class_name('claude-fg-bad');
        }
    }

    // ---------------------------------------------------------------- popup

    _buildMenu() {
        this.menu.box.add_style_class_name('claude-menu');
        const popup = column('claude-popup', {x_expand: true});
        this.menu.box.add_child(popup);

        // Header: the tabs, the summary, SSH hosts, refresh, settings
        const header = box('claude-header', {x_expand: true});
        this._headerSpark = new TalpyIcon('claude-spark claude-spark-small');
        this._headerSpark.setMoving(false);   // (moves while the popup shows)
        header.add_child(this._headerSpark);
        // (the title and the tabs keep their whole names: the summary gives way)
        const whole = actor => {
            actor.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
            return actor;
        };
        // The app's name is the first tab: your chats now. The others: the
        // permissions you gave (ui/permsView.js), your last 7 days with Claude
        // (ui/weekView.js), in the order of Plasma's and VS Code's tabs
        this._tabs = {};
        for (const [tab, text] of [['chats', 'Talpy Den'], ['perms', 'Permissions'], ['week', 'Recap']]) {
            const b = new St.Button({style_class: 'claude-tab', can_focus: true, child: whole(new St.Label({text})),
                y_align: Clutter.ActorAlign.CENTER});
            b.connect('clicked', () => this.setTab(tab));
            this._tabs[tab] = b;
            header.add_child(b);
        }
        this._summary = label('', 'claude-summary', {x_expand: true, x_align: Clutter.ActorAlign.END});
        header.add_child(this._summary);
        const hostsContent = box('claude-button-box');
        hostsContent.add_child(new St.Icon({icon_name: Icons.gnome.host, style_class: 'claude-button-icon'}));
        this._hostsCount = label('', '');
        hostsContent.add_child(this._hostsCount);
        const hostsButton = new St.Button({style_class: 'claude-icon-button', can_focus: true, child: hostsContent});
        hostsButton.connect('clicked', () => {
            this._loadHosts();   // in case ~/.ssh/config changed
            this._toggleMenu('hosts', '');
        });
        this.tips.add(hostsButton, () => {
            const containers = this._settings.get_boolean('show-containers');
            const shown = this.shownHosts;
            return [containers ? 'Show Claude on SSH hosts and in containers' : 'Show Claude on SSH hosts', shown.length > 0
                ? containers ? L.fmt('Showing Claude on %1. Click to pick hosts from ~/.ssh/config and containers.', shown.map(h => L.hostLabel(h)).join(', '))
                    : L.fmt('Showing Claude on %1. Click to pick hosts from ~/.ssh/config.', shown.join(', '))
                : containers ? 'Show the Claude chats of your SSH hosts (from ~/.ssh/config) and of your Docker, Podman or nerdctl containers here too.'
                    : 'Show the Claude chats of your SSH hosts (from ~/.ssh/config) here too.'];
        });
        header.add_child(hostsButton);
        header.add_child(this.tips.add(iconButton(Icons.gnome.refresh, () => {
            this.refreshAll();
            this._loadTab();
            this.fetchUsage();
        }), 'Refresh'));
        header.add_child(this.tips.add(iconButton(Icons.gnome.settings, () => {
            this.menu.close();
            this._extension.openPreferences();
        }), 'Settings'));
        popup.add_child(header);

        // The big Talpy (pets.js) stays put while the list scrolls
        this._heroBin = new St.Bin({x_expand: true});
        popup.add_child(this._heroBin);

        this._messages = column('claude-messages', {x_expand: true});
        popup.add_child(this._messages);
        this._hostsPicker = new St.Bin({x_expand: true});
        popup.add_child(this._hostsPicker);

        this._scroll = new St.ScrollView({
            style_class: 'claude-scroll', x_expand: true,
            hscrollbar_policy: St.PolicyType.NEVER, vscrollbar_policy: St.PolicyType.AUTOMATIC,
        });
        this._list = column('claude-list', {x_expand: true});
        this._scroll.set_child(this._list);
        popup.add_child(this._scroll);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._undismissItem = this.menu.addAction('Show Hidden Chats Again',
            () => this.showHiddenChats(), Icons.gnome.showHidden);
        this.menu.addAction('Open Usage Page on claude.ai', () => {
            Gio.AppInfo.launch_default_for_uri(USAGE_PAGE, global.create_app_launch_context(0, -1));
        }, Icons.gnome.web);

        this.menu.connect('open-state-changed', (menu, open) => {
            if (open) {
                this._unseen = {};   // seen now
                const area = Main.layoutManager.getWorkAreaForMonitor(Main.layoutManager.primaryIndex);
                // (CSS pixels, which the display's scale multiplies, as panelMenu.js does)
                this._scroll.style = `max-height: ${Math.round(area.height * 0.62 / scaleFactor())}px;`;
                this._loadHosts();
                this.rerender();
                this.refresh();  // it may have been checked a while ago (see _pollInterval)
                this._loadTab();
            } else {
                this.tips.hide();
                if (this._digestSeen)
                    this._digest = null;   // you've seen it
                this.ui.openMenu = null;
                this.ui.stopConfirm = '';
                this.ui.deleteAsk = null;
            }
            this._headerSpark.setMoving(open);
            this._pets.setActive(open && this.ui.tab === 'chats');
            this._weekTimer();
            this._adjustPollTimer();
        });
    }

    // ---------------------------------------------------------------- the week

    setTab(tab) {
        if (this.ui.tab === tab)
            return;
        this.ui.tab = tab;
        this._pets.setActive(this.menu.isOpen && tab === 'chats');   // (not drawn while another tab shows)
        this._weekTimer();
        this._loadTab();
        this._render(true);
    }

    // What the Recap or Permissions tab shows, read again: as it shows, as the
    // popup opens, at the top row's Refresh (the tabs have none of their own)
    // and every 10 minutes
    _loadTab() {
        if (this.ui.tab === 'week')
            this.loadWeek();
        else if (this.ui.tab === 'perms')
            this.loadPerms();
    }

    setWeek({back = this.week.back, account = this.week.account, span = this.week.span}) {
        if (span !== this.week.span)
            back = 0;   // (a new span starts at today's)
        this.week.span = span;
        this.week.back = Math.max(0, back);
        this.week.account = account;
        this.loadWeek();
        this._render(true);
    }

    // Asks week.py for the days shown: it reads only what the chats'
    // transcripts added since it last ran
    async loadWeek() {
        const asked = ++this._weekAsked;
        const {back, account, span} = this.week;
        this.week.busy = true;
        this._render(true);
        const out = await this._runner.run('week.py',
            L.weekArgs(back, account, this.shownHosts, this.remote, this._configDirArgs, this._settings.get_string('recap-currency'), span),
            {poll: true});
        if (this._destroyed || out.cancelled || asked !== this._weekAsked)
            return;   // (other days were asked for since)
        const result = L.helperResult(out.stdout, out.stderr);
        this.week.busy = false;
        if (result.ok) {
            this.week.recap = result;
            this.week.error = '';
        } else {
            this.week.error = result.message || result.error || 'no answer';
        }
        this._render(true);
    }

    // Every 10 minutes while the popup shows the Recap or Permissions tab
    _weekTimer() {
        this._clearTimer('week');
        if (!this.menu.isOpen || this.ui.tab === 'chats')
            return;
        this._timers.week = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, WEEK_REFRESH_S, () => {
            this._loadTab();
            return GLib.SOURCE_CONTINUE;
        });
    }

    // Unfolds a day's or a project's chats (or folds them)
    weekUnfold(key) {
        this.week.open = this.week.open === key ? '' : key;
        this._render(true);
    }

    // ---------------------------------------------------------------- permissions

    // Asks week.py --permissions for the permissions you gave and the
    // prompts of the last 7 days
    async loadPerms() {
        if (this.perms.busy)
            return;
        this.perms.busy = true;
        this._permsAgain = false;
        this._render(true);
        const out = await this._runner.run('week.py', L.permsArgs(this._configDirArgs, this.shownHosts, this.remote), {poll: true});
        if (this._destroyed || out.cancelled)
            return;
        const result = L.helperResult(out.stdout, out.stderr);
        this.perms.busy = false;
        if (result.ok) {
            this.perms.data = result;
            this.perms.error = '';
        } else {
            this.perms.error = result.message || result.error || 'no answer';
        }
        this._render(true);
        if (this._permsAgain)
            this.loadPerms();
    }

    permsAsk(id) {
        this.perms.asking = id;
        this._render(true);
    }

    // Allows a rule the tab offers for the permission prompts you answered
    // (into the chats' folder's .claude/settings.local.json), or takes one it
    // added back; then reads them again
    async changeRule(rule, allow, host = '') {
        this.perms.asking = '';
        this.perms.ruleBusy = L.permsKey(host, rule.id);
        this.perms.ruleHost = host;
        this.perms.ruleMessage = '';
        this.perms.ruleRevoked = false;
        this._render(true);
        const result = await this._helper('week.py', L.weekRuleArgs(rule, allow, host));
        if (this._destroyed)
            return;
        this.perms.ruleBusy = '';
        this.perms.ruleFailed = !result.ok;
        this.perms.ruleMessage = result.ok ? result.message || '' : L.fmt('Nothing changed: %1', result.message || 'no answer');
        this._permsAgain = true;   // (a read on its way may have read the file before)
        this.loadPerms();
    }

    permsRevokeAsk(id) {
        this.perms.revoking = id;
        this._render(true);
    }

    permsShowAllGranted(host = '') {
        this.perms.allGranted = {...this.perms.allGranted, [host]: true};
        this._render(true);
    }

    // Takes one of the permissions you gave (what lets chats go without
    // asking) out of its file; then reads them again
    async revokeGrant(grant, host = '') {
        this.perms.revoking = '';
        this.perms.ruleBusy = L.permsKey(host, grant.id);
        this.perms.ruleHost = host;
        this.perms.ruleMessage = '';
        this.perms.ruleRevoked = true;
        this._render(true);
        const result = await this._helper('week.py', L.weekRevokeArgs(grant, this._configDirArgs, host));
        if (this._destroyed)
            return;
        this.perms.ruleBusy = '';
        this.perms.ruleFailed = !result.ok;
        this.perms.ruleMessage = result.ok ? result.message || '' : L.fmt('Nothing changed: %1', result.message || 'no answer');
        this._permsAgain = true;   // (a read on its way may have read the file before)
        this.loadPerms();
    }

    copyText(text) {
        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
        this.week.copied = text;
        this._render(true);
        this._later('copied', 2000, () => {
            this.week.copied = '';
            this._render(true);
        });
    }

    // Rebuilds the popup's contents when what they show has changed (and
    // always when asked to: something was clicked)
    _render(force = false) {
        if (this._destroyed)
            return;
        this._updatePanel();
        this._pets.update();
        if (!this.menu.isOpen)
            return;
        // (a host that answered before looks the same while it's checked again)
        const remote = Object.fromEntries(Object.entries(this.remote).map(([host, r]) =>
            [host, {...r, loading: r.loading && !r.result, result: r.result ? {...r.result, generatedAt: 0} : null,
                updatedAt: Math.floor(r.updatedAt / 60000)}]));
        // A forecast moves a little with every check (fullAt in ms): only
        // what the bar shows (its warning, whole percents) rebuilds the popup
        const now = this.now;
        // and so do the stats: an account's (what its box draws) and a chat's (its recap line)
        const coarse = function (key, value) {
            if (key === 'forecast' && value)
                return [L.forecastWarning(this, now), Math.round(value.evenPct), Math.round(Math.min(100, value.atReset))];
            if (key === 'stats' && value)
                return Array.isArray(value.days) ? L.statsSignature(value) : L.chatRecapText(value);
            return value;
        };
        // The Recap and Permissions tabs show none of the chats, only the
        // header's counts: a check that changed a chat leaves them (and the
        // tooltip you're reading) as they are
        const chats = this.ui.tab === 'chats';
        const c = L.counts(this.allGroups);
        const overall = L.overall(this.allGroups, c);
        const shown = chats ? [this._status ? {...this._status, generatedAt: 0} : null, remote]
            : [c, overall, this._status?.dismissed || 0];
        const signature = JSON.stringify([shown, this._errorText,
            this._sshHosts, this._containersHere, this._containerNotes, this._hostContainers, this.ui, this._actionError, this._actionInfo, Math.floor(this.now / 60000),
            this.ui.tab === 'week' ? [this.week.span, this.week.back, this.week.account, this.week.busy, this.week.error, this.week.copied,
                this.week.open, this.week.recap ? this.week.recap.generatedAt : 0] : null,
            this.ui.tab === 'perms' ? {...this.perms, data: this.perms.data ? this.perms.data.generatedAt : 0} : null,
            this._digest ? this._digest.body : null,
            this.petColors, this._settings.get_boolean('show-pet')], coarse);
        if (!force && signature === this._signature)
            return;
        this._signature = signature;
        this.tips.hide();

        this._headerSpark.setState(L.stateClass(overall), overall);
        for (const [tab, b] of Object.entries(this._tabs))
            b.checked = tab === this.ui.tab;   // (St.Button's :checked)
        this._heroBin.visible = chats;
        this._summary.text = this._pets.heroShown && chats ? '' : L.summaryText(c);   // the big Talpy's headline says it
        const hosts = this.shownHosts;
        this._hostsCount.text = hosts.length > 0 ? String(hosts.length) : '';
        this._undismissItem.label.text = L.fmt('Show Hidden Chats Again (%1)', this._status?.dismissed || 0);
        this._undismissItem.visible = (this._status?.dismissed || 0) > 0;

        this._messages.destroy_all_children();
        if (this._actionError)
            this._messages.add_child(paragraph(this._actionError, 'claude-fg-bad claude-message'));
        if (this._actionInfo)
            this._messages.add_child(paragraph(this._actionInfo, 'claude-fg-ok claude-message'));
        if (this._errorText)
            this._messages.add_child(paragraph(this._errorText, 'claude-fg-bad claude-message'));
        if (this._digest) {
            this._messages.add_child(this._buildDigestCard());
            this._digestSeen = true;
        }

        this._hostsPicker.child?.destroy();
        this._hostsPicker.child = this.ui.openMenu?.type === 'hosts' ? this._buildHostsPicker() : null;

        // Rebuild the list where it was scrolled to
        const adjustment = this._scroll.vadjustment;
        const scrolled = adjustment.value;
        this._pets.detachStages();
        this._list.destroy_all_children();
        if (!chats) {
            // (the pets' stages wait, detached, for the Chats tab)
            this._list.add_child(this.ui.tab === 'week' ? buildWeekView(this) : buildPermsView(this));
            return;
        }
        const owners = this.usageOwners;
        this.groups.forEach((g, i) => {
            this._list.add_child(buildGroupSection(this, L.withUsage(g, '', owners), {last: i === this.groups.length - 1, accounts: this.groups.length}));
        });
        // No account here, but SSH hosts shown: one quiet line where this
        // computer's accounts go (a computer that only watches its hosts is fine)
        if (this._status !== null && this.groups.length === 0 && hosts.length > 0)
            this._list.add_child(label('No Claude Code config on this computer', 'claude-dim claude-indent'));
        for (const host of hosts)
            this._list.add_child(buildHostSection(this, host));
        if (this._status !== null && this.groups.length === 0 && hosts.length === 0) {
            this._list.add_child(emptyState('chats', 'No Claude Code chats yet',   // (the tab's icon, as the Recap's has its own)
                "Your Claude Code chats show up here once you start claude in a terminal or open Claude in VS Code. Talpy Den looks in ~/.claude and ~/.claude-*; other folders go in its settings (Extra config folders)."));
        }
        this._pets.pruneStages();
        if (scrolled > 0) {
            this._clearTimer('scroll');
            this._timers.scroll = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                delete this._timers.scroll;
                adjustment.value = Math.min(scrolled, adjustment.upper - adjustment.page_size);
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    // The hosts picker: ~/.ssh/config's hosts, this computer's containers
    // and each connected SSH host's (L.containerPlaces). It shows the last
    // lists at once; this computer's is read again as it opens.
    _buildHostsPicker() {
        const menu = column('claude-inline-menu', {x_expand: true});
        const containers = this._settings.get_boolean('show-containers');
        menu.add_child(label('SSH hosts', 'claude-menu-title'));
        const picked = this.pickedHosts;
        const hosts = picked.filter(h => !L.containerOf(h));
        for (const h of this._sshHosts) {
            const target = (h.user ? `${h.user}@` : '') + (h.hostname || h.name) + (h.jump ? ` via ${h.jump}` : '');
            const on = picked.includes(h.name);
            menu.add_child(textButton(target !== h.name ? `${h.name}  (${target})` : h.name,
                () => this.toggleHost(h.name), 'claude-menu-item',
                on ? Icons.gnome.ticked : Icons.gnome.host));
        }
        // picked hosts that aren't in ~/.ssh/config (any more)
        for (const host of hosts) {
            if (!this._sshHosts.some(h => h.name === host))
                menu.add_child(textButton(host, () => this.toggleHost(host), 'claude-menu-item', Icons.gnome.ticked));
        }
        if (this._sshHosts.length === 0 && hosts.length === 0)
            menu.add_child(label('No hosts in ~/.ssh/config', 'claude-dim claude-indent'));
        if (containers) {
            const places = L.containerPlaces(this._containersHere, this._containerNotes, this._hostContainers,
                this.connectedHosts, picked, Math.max(0, this._settings.get_int('container-days')), Date.now());
            for (const place of places) {
                menu.add_child(label(place.title, 'claude-menu-title'));
                for (const item of place.items) {
                    menu.add_child(textButton(item.text, () => this.toggleHost(item.id), 'claude-menu-item',
                        item.checked ? Icons.gnome.ticked : Icons.gnome.container));
                }
                for (const note of place.notes.concat(place.empty ? [place.empty] : []))
                    menu.add_child(label(note, 'claude-dim claude-indent'));
            }
        }
        menu.add_child(textButton('Reload', () => this.reloadHosts(), 'claude-menu-item', Icons.gnome.refresh));
        return menu;
    }

    _onDestroy() {
        this._destroyed = true;
        for (const id of this._settingsIds)
            this._settings.disconnect(id);
        for (const name of Object.keys(this._timers))
            this._clearTimer(name);
        this._runner.destroy();
        this._notifier?.destroy();
        this._pets.destroy();
        this.tips.destroy();
        super._onDestroy();
    }
});
