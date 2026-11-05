// Settings window (port of the Plasma widget's configGeneral.qml and
// SoundChooser.qml): same settings, same defaults (schemas/*.gschema.xml).

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import * as Icons from './ui/icons.js';
import {containerOf, hostLabel} from './logic.js';

// The Recap tab's currencies (those of the European Central Bank's reference rates)
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const CURRENCIES = [['USD', 'US dollars'], ['EUR', 'Euros'], ['GBP', 'Pounds sterling'], ['CHF', 'Swiss francs'], ['JPY', 'Japanese yen'],
    ['CNY', 'Chinese yuan'], ['INR', 'Indian rupees'], ['CAD', 'Canadian dollars'], ['AUD', 'Australian dollars'],
    ['NZD', 'New Zealand dollars'], ['SEK', 'Swedish kronor'], ['NOK', 'Norwegian kroner'], ['DKK', 'Danish kroner'],
    ['PLN', 'Polish złoty'], ['CZK', 'Czech koruny'], ['HUF', 'Hungarian forints'], ['RON', 'Romanian lei'],
    ['ISK', 'Icelandic krónur'], ['TRY', 'Turkish lira'], ['BRL', 'Brazilian reais'], ['MXN', 'Mexican pesos'],
    ['ZAR', 'South African rand'], ['KRW', 'South Korean won'], ['SGD', 'Singapore dollars'], ['HKD', 'Hong Kong dollars'],
    ['ILS', 'Israeli shekels'], ['IDR', 'Indonesian rupiah'], ['MYR', 'Malaysian ringgit'], ['PHP', 'Philippine pesos'],
    ['THB', 'Thai baht']];

// A question's color: the popup's orange (stylesheet.css claude-fg-waiting)
const QUESTION = '#f57900';

// A button with its icon (a meaning of the icon table, icons.mjs) before its
// words, plain: the icon red or green where the color says something (TONES),
// never the button
function iconTextButton(label, meaning, onClick, tip = '') {
    const content = new Gtk.Box({spacing: 6, halign: Gtk.Align.CENTER});
    const tone = Icons.TONES[meaning];
    content.append(new Gtk.Image({icon_name: Icons.gnome[meaning],
        css_classes: tone === 'negative' ? ['error'] : tone === 'positive' ? ['success'] : []}));
    content.append(new Gtk.Label({label, use_underline: false}));
    const b = new Gtk.Button({child: content, valign: Gtk.Align.CENTER});
    if (tip)
        b.tooltip_text = tip;
    b.connect('clicked', onClick);
    return b;
}

// Sounds from the sound theme (comma separated: the first one found plays)
const SOUNDS = [
    ['Message', 'message-new-instant'],
    ['Success', 'outcome-success,complete'],
    ['Complete', 'complete'],
    ['Bell', 'bell'],
    ['Attention', 'window-attention'],
    ['Question', 'dialog-question,dialog-information'],
    ['Information', 'dialog-information'],
    ['Warning', 'dialog-warning'],
    ['Error', 'dialog-error'],
    ['No sound', ''],
];

export default class TalpyDenPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        window._claudeSettings = settings;   // lives as long as the window
        window.set_default_size(880, 760);   // (wide enough for the nine pages' names in its switcher)
        // One page per category, as Plasma's settings pages and VS Code's
        // Settings editor (Talpy Den › General, › Chats…), then Accounts
        const category = (title, meaning) => {
            const page = new Adw.PreferencesPage({title, icon_name: Icons.gnome[meaning]});
            window.add(page);
            return page;
        };
        const group = (page, title = '', description = '') => {
            const g = new Adw.PreferencesGroup({title, description});
            page.add(g);
            return g;
        };

        const spin = (key, title, subtitle, min, max, step) => {
            const row = Adw.SpinRow.new_with_range(min, max, step);
            row.set({title, subtitle});
            settings.bind(key, row, 'value', Gio.SettingsBindFlags.DEFAULT);
            return row;
        };
        const toggle = (key, title, subtitle = '') => {
            const row = new Adw.SwitchRow({title, subtitle});
            settings.bind(key, row, 'active', Gio.SettingsBindFlags.DEFAULT);
            return row;
        };
        const needs = (row, key) => {
            settings.bind(key, row, 'sensitive', Gio.SettingsBindFlags.GET);
            return row;
        };

        // ---- General: the chat list, the top bar
        const general = category('General', 'settings');
        const list = group(general, 'Chat list');
        list.add(spin('recent-chats', 'Recent chats per account',
            'How many show at a time (Show N more for the next ones), also under ★ Starred chats; 0 hides Recent chats', 0, 20, 1));
        list.add(spin('keep-done-hours', 'Keep finished background chats', 'hours; 0 hides them right away', 0, 168, 1));
        list.add(toggle('show-tokens', 'Show token totals', 'from local transcripts'));
        group(general, 'Top bar').add(toggle('show-usage-in-panel', 'Show 5-hour usage next to the icon'));

        // ---- Chats (where they open is the popup's Terminal | VS Code switch)
        const chats = category('Chats', 'chats');
        group(chats, 'Open in',
            'New and recent chats open in a terminal or in VS Code: the Terminal | VS Code switch at the top of their lists picks it.');
        chats.add(this._cleanupGroup(window, settings));

        // ---- Notifications: when, sounds, while you're away, the shortcut
        const notifications = category('Notifications', 'notifications');
        const when = group(notifications, 'When to notify');
        when.add(toggle('notify-waiting', 'When a chat needs input', 'a permission prompt or a question'));
        when.add(toggle('notify-done', 'When a chat finishes its turn'));
        when.add(spin('notify-done-min-seconds', '…if the turn took at least',
            'seconds; also picks which finished turns the shortcut goes to, notifications on or off', 0, 3600, 10));
        const sounds = group(notifications, 'Sounds', 'Sounds come from your sound theme. They stay quiet while Do Not Disturb is on.');
        sounds.add(toggle('notify-sound', 'Play a sound with these notifications'));
        sounds.add(needs(spin('sound-volume', 'Volume', 'percent', 0, 100, 5), 'notify-sound'));
        sounds.add(needs(this._soundRow(window, settings, 'sound-waiting', 'Needs input'), 'notify-sound'));
        sounds.add(needs(this._soundRow(window, settings, 'sound-done', 'Finished'), 'notify-sound'));
        sounds.add(needs(this._soundRow(window, settings, 'sound-failed', 'Failed or stopped'), 'notify-sound'));
        const away = group(notifications, "While you're away");
        away.add(toggle('away-digest', 'A summary when you come back',
            'after the screen was locked: what finished, failed or needs you, at the top of the popup, and as one notification while the ones above are on'));
        away.add(needs(spin('away-minutes', '…if you were away at least', 'minutes', 1, 240, 1), 'away-digest'));
        // (a group's description is Pango markup: < is &lt;)
        group(notifications, 'Keyboard shortcut',
            "Goes to the chat that needs you: the one waiting longest, then a finished turn you haven't seen. Press it again soon after for the next one. With none, it opens the popup. E.g. &lt;Super&gt;&lt;Shift&gt;c; empty for none.")
            .add(this._shortcutRow(settings, 'next-chat-shortcut', 'Go to the chat that needs you'));

        // ---- Usage & limits
        group(category('Usage & limits', 'usageLimits')).add(spin('usage-refresh-minutes', 'Fetch plan usage older than',
            "minutes; VS Code's Claude Code panel runs no status line, so while one of an account's chats works, Claude Code fetches its usage this old (as /usage does: no tokens, no chat saved), at most this often; 0 never",
            0, 60, 1));

        // ---- Talpy
        const pet = group(category('Talpy', 'pet'));
        pet.add(toggle('show-pet', 'Show Talpy, the pet', 'in the popup and in notifications'));
        pet.add(needs(toggle('playful-talpy', 'Playful Talpy',
            'his tricks and props and jokes; off, he only shows what your chats do (moods, lamp, quiet moves)'), 'show-pet'));
        pet.add(needs(spin('chat-pets', 'Chat pets per account, at most', '0 keeps only the big Talpy', 0, 8, 1),
            'show-pet'));

        // ---- Recap: its currency, its kept history, the suggested rules
        const recap = category('Recap', 'recap');
        group(recap).add(this._currencyRow(settings));
        recap.add(this._historyGroup(window));
        group(recap, 'Suggested rules').add(toggle('recap-rules', 'Suggest rules for the permission prompts you answered',
            "The Permissions tab offers rules that would have let them go without asking, each with an Allow button. Off, it only counts the prompts, and there's nothing to allow by mistake. Either way it lists the permissions you gave, to revoke them."));

        // ---- Hosts
        const hostsPage = category('Hosts', 'host');
        group(hostsPage, 'SSH hosts',
            "Pick SSH hosts and containers with the hosts button at the top of the popup. They need key-based login (Talpy Den can't type a password) and python3 on the host; nothing gets installed there.")
            .add(spin('remote-poll-seconds', 'Check SSH hosts every', 'seconds', 10, 600, 10));
        const containers = group(hostsPage, 'Containers',
            "Docker, Podman and nerdctl containers, here and on the SSH hosts shown, are in the hosts picker. One you pick shows like a host; Talpy Den works in it with the engine's exec, and it needs python3 there. Off, Talpy Den never runs docker, podman or nerdctl.");
        containers.add(toggle('show-containers', 'Show containers'));
        containers.add(needs(spin('container-days', 'List containers active in the last', 'days (0: only the running ones)', 0, 365, 1),
            'show-containers'));

        // ---- Advanced: how often Talpy Den checks, extra Claude folders
        const advanced = category('Advanced', 'advanced');
        const checks = group(advanced, 'Checks');
        checks.add(spin('poll-interval', 'Check every', 'milliseconds', 1000, 60000, 500));
        checks.add(spin('idle-poll-interval', '…while nothing runs',
            'milliseconds, while no chat runs and the popup is closed', 1000, 300000, 1000));
        const dirs = new Adw.EntryRow({title: 'Extra config folders (comma separated)', show_apply_button: true,
            text: settings.get_string('extra-config-dirs')});
        dirs.connect('apply', () => settings.set_string('extra-config-dirs', dirs.text));
        group(advanced, 'Claude folders', '~/.claude and ~/.claude-* are found automatically.').add(dirs);

        window.add(this._accountsPage(window, settings));
    }

    // The Claude accounts on this computer or an SSH host (code/accounts.py; a
    // host's through remote.py --accounts; port of the Plasma widget's
    // configAccounts.qml): add one, log in or out, remove one, the default one
    _accountsPage(window, settings) {
        const page = new Adw.PreferencesPage({title: 'Accounts', icon_name: Icons.gnome.accounts});
        const esc = text => GLib.markup_escape_text(text, -1);
        const state = {accounts: [], loaded: false, canCheck: true, linked: false, busy: '', confirm: '', rows: [], closed: false,
            host: '', loadedAt: 0};
        // whose accounts: this computer's, or an SSH host's picked in the popup
        // (the picked containers too, unless Show containers is off)
        const hosts = settings.get_strv('ssh-hosts').map(h => h.trim())
            .filter(h => h && (settings.get_boolean('show-containers') || !containerOf(h)));
        // (a container's accounts go through its engine on this computer or its host, not ssh)
        const whereText = host => (!host ? '' : esc(containerOf(host)
            ? `In ${hostLabel(host)}: nothing is installed there, and its logins open in a terminal here, where you paste the code Claude gives you.`
            : `On ${host}, over ssh: nothing is installed there, and its logins open in a terminal here, where you paste the code Claude gives you.`));
        const where = new Adw.ComboRow({title: 'On', model: Gtk.StringList.new(['This computer', ...hosts.map(h => hostLabel(h))])});
        if (hosts.length) {
            const on = new Adw.PreferencesGroup();
            on.add(where);
            page.add(on);
        }

        const about = 'Each account is a Claude folder (~/.claude, ~/.claude-NAME) with a login, history and chats of its own. The default account is listed first and its usage is in the top bar: VS Code\'s Claude runs on it, and plain claude too where ~/.claude is a link. A chat started with the + next to an account runs on that account.';
        const list = new Adw.PreferencesGroup({title: 'Accounts on this computer', description: about});
        page.add(list);

        const add = new Adw.PreferencesGroup({title: 'Add an account',
            description: "A terminal opens with Claude's own login: sign in in your browser with the other account. Claude keeps the login in the new folder; Talpy Den never sees it."});
        const nameRow = new Adw.EntryRow({title: 'Name, e.g. work (its folder: ~/.claude-NAME)'});
        add.add(nameRow);
        const shareRow = new Adw.ComboRow({title: 'Settings',
            subtitle: 'Shared: settings.json (your status line), CLAUDE.md, keybindings and your own skills, agents and commands are linked to that account\'s. The login, MCP servers, plugins and claude.ai\'s skills stay per account.'});
        add.add(shareRow);
        const commandRow = new Adw.ActionRow({title: 'Add a claude-NAME command', subtitle: 'In ~/.local/bin: runs Claude on the new account in any terminal'});
        const commandSwitch = new Gtk.Switch({active: true, valign: Gtk.Align.CENTER});
        commandRow.add_suffix(commandSwitch);
        commandRow.activatable_widget = commandSwitch;
        add.add(commandRow);
        const addRow = new Adw.ActionRow({title: ''});
        const addButton = iconTextButton('Add and Log In…', 'addAccount', () => {
            const share = shareKeys[shareRow.selected];
            act(['--add', nameRow.text.trim(), ...share ? ['--share-from', share] : [],
                ...commandSwitch.active ? ['--command'] : []], 'add');
        });
        addRow.add_suffix(addButton);
        add.add(addRow);
        page.add(add);

        const toast = (text, ok) => {
            if (text)
                window.add_toast(new Adw.Toast({title: esc(text), timeout: ok ? 5 : 10}));
        };
        const run = args => new Promise(resolve => {
            const dirs = settings.get_string('extra-config-dirs').split(',').map(d => d.trim()).filter(d => d)
                .flatMap(d => ['--config-dir', d]);
            const code = name => GLib.build_filenamev([this.path, 'code', name]);
            const argv = state.host
                ? ['python3', '-I', code('remote.py'), '--accounts', state.host, ...args]
                : ['python3', '-I', code('accounts.py'), ...args, ...dirs];
            try {
                const proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
                proc.communicate_utf8_async(null, null, (pr, res) => {
                    try {
                        const [, out, err] = pr.communicate_utf8_finish(res);
                        try {
                            resolve(JSON.parse(out));
                        } catch {
                            resolve({ok: false, message: (err || '').trim().split('\n').pop() || 'the helper gave no answer'});
                        }
                    } catch (e) {
                        resolve({ok: false, message: e.message});
                    }
                });
            } catch (e) {
                resolve({ok: false, message: e.message});
            }
        });

        const nameProblem = () => {
            const name = nameRow.text.trim();
            if (!name)
                return 'empty';
            if (name === 'default' || name === 'main')
                return `${name} is taken: main is what ~/.claude is called, default marks the default account`;
            if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(name))
                return 'Up to 32 letters, digits, - and _, starting with a letter';
            if (state.accounts.some(a => a.folder === `~/.claude-${name}`))
                return `There's an account called ${name} already`;
            return '';
        };
        const syncAdd = () => {
            const problem = nameProblem();
            const name = nameRow.text.trim();
            addRow.title = problem && problem !== 'empty' ? esc(problem) : name ? esc(`Folder: ~/.claude-${name}`) : '';
            commandRow.title = esc(`Add a claude-${!problem ? name : 'NAME'} command`);
            addButton.sensitive = !problem && !state.busy && state.canCheck;
        };
        nameRow.connect('changed', () => {
            nameRow.remove_css_class('error');
            syncAdd();
        });

        let shareKeys = [];
        const render = () => {
            for (const row of state.rows)
                list.remove(row);
            state.rows = state.accounts.map(a => this._accountRow(a, state, esc, act));
            for (const row of state.rows)
                list.add(row);
            if (!state.loaded) {
                const row = new Adw.ActionRow({title: 'Looking…'});
                state.rows.push(row);
                list.add(row);
            }
            // VS Code's Claude and plain claude on two accounts: say so
            const def = state.accounts.find(a => a.default), plain = state.accounts.find(a => a.main);
            list.description = esc(state.linked && def && plain && def.key !== plain.key
                ? `${about}\n\nVS Code's Claude runs on ${def.label}, the default account, but plain claude on ${plain.label} (~/.claude links there). Make Default on ${def.label} points plain claude there too.`
                : about);
            const keys = state.accounts.map(a => a.key);
            if (keys.join('\n') !== shareKeys.join('\n')) {
                shareKeys = keys;
                shareRow.model = Gtk.StringList.new([...state.accounts.map(a => `Shared with ${a.label}`), "Claude's defaults, nothing shared"]);
                shareRow.selected = 0;
            }
            syncAdd();
        };

        const load = async check => {
            const host = state.host;
            state.loadedAt = Date.now();
            const result = await run(check ? ['--list', '--check'] : ['--list']);
            if (state.closed || host !== state.host)
                return;   // (an answer for the machine shown before)
            if (!result.ok) {
                state.loaded = true;
                toast(result.message, false);
                render();
                return;
            }
            const before = Object.fromEntries(state.accounts.map(a => [a.key, a]));
            // A quick look keeps what Claude said last while the folder says the
            // same (quick); when that changes, Claude is asked again
            const changed = result.accounts.some(a => !before[a.key] || before[a.key].quick !== a.quick);
            state.accounts = result.accounts.map(a => {
                const old = before[a.key];
                return check || !old || !old.checked || old.quick !== a.quick ? a
                    : {...a, checked: true, method: old.method, email: old.email, loggedIn: old.loggedIn};
            });
            state.canCheck = result.canCheck;
            state.linked = !!result.linked;
            state.canDefault = !!result.canDefault;
            const first = !state.loaded;
            state.loaded = true;
            render();
            if (!check && (first || changed))
                load(true);
        };

        const act = async (args, key) => {
            state.busy = key;
            state.confirm = '';
            render();
            const result = await run(args);
            if (state.closed)
                return;
            state.busy = '';
            toast(result.message, result.ok);
            if (result.ok && args[0] === '--add')
                nameRow.text = '';
            await load(true);
        };
        state.render = render;

        where.connect('notify::selected', () => {
            state.host = where.selected > 0 ? hosts[where.selected - 1] : '';
            list.title = state.host ? esc(`Accounts on ${hostLabel(state.host)}`) : 'Accounts on this computer';
            where.subtitle = whereText(state.host);
            state.accounts = [];
            state.loaded = false;
            state.confirm = '';
            render();
            load(true);
        });

        load(true);
        // A login happens in a terminal: look again every few seconds (a
        // host's over ssh, less often)
        const timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, () => {
            if (state.closed)
                return GLib.SOURCE_REMOVE;
            if (state.loaded && !state.busy && window.is_active && Date.now() - state.loadedAt >= (state.host ? 10000 : 3500))
                load(false);
            return GLib.SOURCE_CONTINUE;
        });
        window.connect('close-request', () => {
            state.closed = true;
            GLib.source_remove(timer);
            return false;
        });
        return page;
    }

    // One account: what it is, and its buttons (log in or out, remove, its
    // claude-NAME command); logging out and removing ask first
    _accountRow(a, state, esc, act) {
        const parts = [a.folder];
        if (a.default)
            parts.push('default');
        if (a.main)
            parts.push('plain claude');
        if (a.vscode)
            parts.push("VS Code's Claude");
        if (!a.loggedIn)
            parts.push('not logged in');
        else if (a.method && a.method !== 'claude.ai')
            parts.push(`logged in (${a.method})`);
        else
            parts.push(...[a.email || a.account || 'logged in', a.plan].filter(t => t));
        if (a.chats > 0)
            parts.push(a.chats === 1 ? '1 chat running' : `${a.chats} chats running`);
        const row = new Adw.ActionRow({title: esc(a.label), subtitle: esc(parts.join(' · '))});
        // (each with its icon, as Plasma's; a question's do-it button with the asking one's)
        const button = (label, meaning, onClick, tip = '') => {
            const b = meaning ? iconTextButton(label, meaning, onClick, tip)
                : new Gtk.Button({label, valign: Gtk.Align.CENTER, tooltip_text: tip});
            if (!meaning)
                b.connect('clicked', onClick);
            b.sensitive = !state.busy;
            row.add_suffix(b);
            return b;
        };
        const rerender = () => state.render();
        if (state.confirm === `remove:${a.key}` || state.confirm === `logout:${a.key}`) {
            const removing = state.confirm.startsWith('remove:');
            // (an SSH host's folder goes to that host's Trash; in orange, its
            // buttons beside it, as every question)
            row.subtitle = `<span foreground="${QUESTION}">${esc(removing && state.host
                ? `Remove ${a.label} on ${hostLabel(state.host)}? It logs out, then moves ${a.folder} to the Trash of ${hostLabel(state.host)} with its chats, history and settings (restore it from there if you change your mind). Chats shared with your other accounts stay on them.`
                : removing
                    ? `Remove ${a.label}? It logs out, then moves ${a.folder} to the Trash with its chats, history and settings (restore it from there if you change your mind). Chats shared with your other accounts stay on them.`
                    : `Log out of ${a.label}? Claude deletes its login; its chats and history stay, and Log in… signs it in again (also with another account).`)
                // (what other accounts link to in it moves to them first: accounts.py hand_over)
                + (removing && a.handOver ? esc(` ${a.handOver}`) : '')}</span>`;
            row.add_css_class('property');   // (the question at full strength, the account's name over it)
            button(removing ? 'Remove' : 'Log out', removing ? 'delete' : 'signOut', () => act([removing ? '--remove' : '--logout', a.key], a.key));
            button('Cancel', '', () => {
                state.confirm = '';
                rerender();
            });
            return row;
        }
        if (state.canDefault && state.accounts.length > 1 && a.loggedIn && (!a.default || (state.linked && !a.main))) {
            button('Make Default', 'makeDefault', () => act(['--default', a.key], a.key), state.linked
                ? "Lists it first and shows its usage in the top bar; VS Code's Claude and plain claude (~/.claude) run on it. Not while a chat runs through ~/.claude: it would go on on this account."
                : "Lists it first and shows its usage in the top bar; VS Code's Claude runs on it. Plain claude stays on ~/.claude, a folder.");
        }
        if (!a.loggedIn) {
            button('Log in…', 'signIn', () => act(['--login', a.key], a.key),
                "Opens a terminal with Claude's own login (claude auth login): sign in in your browser with the account for this folder.");
        } else {
            const out = button('Log out…', 'signOut', () => {
                state.confirm = `logout:${a.key}`;
                rerender();
            }, a.chats > 0 ? "Close its chats first: they'd lose the login." : "Claude deletes this account's login (claude auth logout).");
            out.sensitive = !state.busy && a.chats === 0;
        }
        const remove = button('Remove…', 'delete', () => {
            state.confirm = `remove:${a.key}`;
            rerender();
        }, a.notRemovable || 'Logs out and moves the folder to the Trash.');
        remove.sensitive = !state.busy && !a.notRemovable;
        if (a.commandName) {
            const check = new Gtk.CheckButton({label: a.commandName, active: !!a.command, valign: Gtk.Align.CENTER,
                tooltip_text: `~/.local/bin/${a.commandName} runs Claude on this account in any terminal.`});
            check.sensitive = !state.busy;
            check.connect('toggled', () => act([check.active ? '--command' : '--no-command', a.key], a.key));
            row.add_suffix(check);
        }
        return row;
    }

    // An accelerator like <Super><Shift>c, checked before it's kept
    _shortcutRow(settings, key, title) {
        const row = new Adw.EntryRow({title, show_apply_button: true, text: settings.get_strv(key)[0] || ''});
        row.connect('apply', () => {
            const text = row.text.trim();
            const [ok, keyval, mods] = text ? Gtk.accelerator_parse(text) : [true, 0, 0];
            // a key with no modifier (plain "c") would take that key from every app
            if (text && (!ok || !keyval || !mods)) {
                row.add_css_class('error');
                return;
            }
            row.remove_css_class('error');
            settings.set_strv(key, text ? [text] : []);
        });
        row.connect('changed', () => row.remove_css_class('error'));
        return row;
    }

    // Old chats (cleanup.py --status [--days N], --set claude | --set talpy
    // DAYS): who deletes them, Claude Code's own cleanup or Talpy Den's, which
    // keeps what you starred. One choice for every copy of the widget and the
    // VS Code extension, in Talpy Den's state folder: it changes at once, and
    // Talpy Den's, or fewer days, only once you saw what its first run deletes
    _cleanupGroup(window, settings) {
        const group = new Adw.PreferencesGroup({title: 'Old chats'});
        const run = args => new Promise(resolve => {
            try {
                const dirs = settings.get_string('extra-config-dirs').split(',').map(d => d.trim()).filter(d => d)
                    .flatMap(d => ['--config-dir', d]);
                const proc = Gio.Subprocess.new(['python3', '-I', GLib.build_filenamev([this.path, 'code', 'cleanup.py']), ...args, ...dirs],
                    Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
                proc.communicate_utf8_async(null, null, (pr, res) => {
                    try {
                        resolve(JSON.parse(pr.communicate_utf8_finish(res)[1]));
                    } catch (e) {
                        resolve({ok: false, message: e.message});
                    }
                });
            } catch (e) {
                resolve({ok: false, message: e.message});
            }
        });
        const who = new Adw.ComboRow({title: 'Deleted by', sensitive: false,
            model: Gtk.StringList.new(["Claude Code's own cleanup", 'Talpy Den, keeping what you starred'])});
        const days = Adw.SpinRow.new_with_range(1, 3649, 1);
        days.set({title: 'Not used for', subtitle: 'days', visible: false});
        const about = new Adw.ActionRow({title: '', subtitle_lines: 0});
        about.add_css_class('property');
        const ask = new Adw.ActionRow({visible: false});
        const use = iconTextButton('Use It', 'erase', async () => {
            ask.visible = false;
            said(await run(['--set', 'talpy', String(asked)]));
            asked = 0;
            sync();
        });
        const cancel = new Gtk.Button({label: 'Cancel', valign: Gtk.Align.CENTER});
        cancel.connect('clicked', () => {
            asked = 0;
            ask.visible = false;
            show();
        });
        ask.add_suffix(use);
        ask.add_suffix(cancel);
        // Claude Code's own cleanup again: what it would delete of what Talpy Den keeps, asked first
        const back = new Adw.ActionRow({visible: false});
        const letClaude = iconTextButton('Let Claude Code Delete', 'erase', async () => {
            back.visible = false;
            said(await run(['--set', 'claude']));
            sync();
        });
        const keep = new Gtk.Button({label: 'Cancel', valign: Gtk.Align.CENTER});
        keep.connect('clicked', () => {
            back.visible = false;
            show();
        });
        back.add_suffix(letClaude);
        back.add_suffix(keep);
        const said = result => window.add_toast(new Adw.Toast({title: GLib.markup_escape_text(result.message || '', -1), timeout: 5}));
        let st = null, asked = 0, syncing = false, applyId = 0;
        // (more days delete nothing more: applied after the last change, not asked)
        const applyLater = n => {
            if (applyId)
                GLib.source_remove(applyId);
            applyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 800, () => {
                applyId = 0;
                if (st && st.mode === 'talpy' && n > st.days)
                    run(['--set', 'talpy', String(n)]).then(r => {
                        said(r);
                        asked = 0;
                        sync();
                    });
                return GLib.SOURCE_REMOVE;
            });
        };
        group.connect('destroy', () => {
            if (applyId)
                GLib.source_remove(applyId);
            applyId = 0;
        });
        const size = bytes => GLib.format_size(bytes || 0);
        const what = r => {   // ("3 chats, 1 background chat, 12 other files (412 MB), 1 plan to the Trash", as Plasma's)
            const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;
            const parts = [r.chats && n(r.chats, 'chat', 'chats'), r.backgroundChats && n(r.backgroundChats, 'background chat', 'background chats'),
                r.files && n(r.files, 'other file', 'other files')].filter(x => x);
            let text = parts.length ? `${parts.join(', ')} (${size(r.bytes)})` : '';
            if (r.plans)
                text += `${text ? ', ' : ''}${n(r.plans, 'plan', 'plans')} to the Trash`;
            return text || 'nothing';
        };
        const kept = r => {
            const k = (r.keptChats || 0) + (r.keptPlans || 0);
            return k ? `${k} old starred, open or queued ${k === 1 ? 'one stays' : 'ones stay'}` : '';
        };
        const show = () => {
            if (!st)
                return;
            syncing = true;
            const talpy = asked > 0 || (st.mode === 'talpy' && !back.visible);
            who.selected = talpy ? 1 : 0;
            days.visible = talpy;
            days.value = asked > 0 ? asked : st.days;
            syncing = false;
            // (Talpy Den's, or fewer days: what its first run deletes is asked first)
            ask.visible = asked > 0 && (st.mode !== 'talpy' || asked < st.days);
            const risk = st.claudeRisk;
            if (back.visible && risk) {
                const counts = [risk.chats ? `${risk.chats} ${risk.chats === 1 ? 'chat' : 'chats'} you keep` : '',
                    risk.plans ? `${risk.plans} ${risk.plans === 1 ? 'plan' : 'plans'} you keep` : ''].filter(x => x).join(' and ');
                back.title = `<span foreground="${QUESTION}">${GLib.markup_escape_text(
                    `Let Claude Code delete old chats again? When it next starts, it deletes what's older than ${risk.days} ` +
                    `${risk.days === 1 ? 'day' : 'days'}, starred or not: here that's ${counts}.`, -1)}</span>`;
            }
            if (ask.visible)
                ask.title = `<span foreground="${QUESTION}">${GLib.markup_escape_text(st.previewDays !== asked ? 'Looking at what it would delete…'
                    : `Delete chats you haven't used for ${asked} ${asked === 1 ? 'day' : 'days'}? Its first run deletes ${what(st.preview)} here.`, -1)}</span>`;
            use.sensitive = st.previewDays === asked;
            const lines = [st.mode !== 'talpy' && !ask.visible   // (asked: what Talpy Den's does, read first)
                ? `When it starts, Claude Code deletes every chat, and every plan of an account's plans folder, older than its cleanupPeriodDays (${
                    st.claudeDays.map(a => `${a.account}: ${a.days} days`).join(', ')}): starred or not, for good.`
                : 'Once a day Talpy Den deletes the chats you haven\'t used for that long, with their undo history and files, and finished background chats; old plans go to the Trash. What you starred stays, and so do chats that are open, queued or keep going, and a plan while its chat stays. Meanwhile Claude Code\'s own cleanup is off on every account, here and on the SSH hosts and containers shown (cleanupPeriodDays 3650); choosing it again puts it back.'];
            const overrides = list => (list || []).map(o => `${o.path} (${o.days} days)`).join(', ');
            if ((st.mode === 'talpy' || ask.visible) && (st.overrides || []).length)
                lines.push('', `These settings still have Claude Code delete old chats, starred or not, when it runs there: ${overrides(st.overrides)}. ` +
                    "Talpy Den doesn't change them: set their cleanupPeriodDays higher, or take it out, to keep what you starred.");
            if (st.mode === 'talpy' && !ask.visible)
                lines.push('', `Its next run would delete ${what(st.preview)} here.${kept(st.preview) ? ` ${kept(st.preview)}.` : ''}`);
            const places = Object.keys(st.runs || {}).sort();
            if (places.length)
                lines.push('');
            for (const place of places) {
                const r = st.runs[place];
                let text = !r.ok && r.message ? r.message   // (out of reach, or it failed there)
                    : r.mode === 'talpy' ? what(r) + (kept(r) ? `; ${kept(r)}` : '')
                    : r.raised ? "Claude Code's cleanup isn't back yet" : "Claude Code's cleanup is back";
                const errors = r.errors && r.errors.length ? r.errors.join('; ') : '';
                if (r.ok && (r.message || errors))
                    text += ` · ${r.message || errors}`;
                else if (!r.ok && !r.message && errors)
                    text += ` · ${errors}`;
                if (place && r.overrides && r.overrides.length)   // (this computer's: said above)
                    text += ` · Claude Code still cleans up by ${overrides(r.overrides)}`;
                lines.push(`${place || 'This computer'}, ${r.at ? new Date(r.at).toLocaleString() : ''}: ${text}`);
            }
            about.subtitle = GLib.markup_escape_text(lines.join('\n'), -1);
        };
        const sync = async (asking = 0) => {
            const result = await run(asking ? ['--status', '--days', String(asking)] : ['--status']);
            if (result.preview === undefined) {
                about.subtitle = GLib.markup_escape_text(result.message || "Couldn't ask about old chats", -1);
                return;
            }
            st = result;
            who.sensitive = true;
            show();
        };
        let previewId = 0;
        const askFor = n => {   // (Talpy Den's at n days: what its first run deletes, read first)
            asked = n;
            back.visible = false;
            show();
            if (previewId)
                GLib.source_remove(previewId);
            previewId = 0;
            if (ask.visible) {   // (read once the days stop changing, not at each step)
                previewId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                    previewId = 0;
                    if (asked === n)
                        sync(n);
                    return GLib.SOURCE_REMOVE;
                });
            } else if (st.mode === 'talpy' && n > st.days) {
                applyLater(n);
            }
        };
        group.connect('destroy', () => {
            if (previewId)
                GLib.source_remove(previewId);
            previewId = 0;
        });
        who.connect('notify::selected', async () => {
            if (syncing || !st)
                return;
            if (who.selected === 1 && st.mode !== 'talpy') {
                askFor(st.days);
            } else if (who.selected === 1) {
                back.visible = false;
                show();
            } else if (st.mode === 'talpy') {
                asked = 0;
                const risk = st.claudeRisk;
                if (risk && risk.chats + risk.plans > 0) {   // (it would delete what Talpy Den keeps: asked first)
                    back.visible = true;
                    show();
                } else {
                    said(await run(['--set', 'claude']));
                    sync();
                }
            } else {
                asked = 0;
                show();
            }
        });
        days.connect('notify::value', () => {
            if (!syncing && st)
                askFor(Math.round(days.value));
        });
        group.add(who);
        group.add(days);
        group.add(ask);
        group.add(back);
        group.add(about);
        sync();
        return group;
    }

    // The Recap's history (week.py --history-status, --history on|off,
    // --forget): one choice for every copy of the widget and the VS Code
    // extension, kept next to their cache, so it changes at once
    _historyGroup(window) {
        const group = new Adw.PreferencesGroup({title: 'History',
            description: "Claude Code deletes chats after 30 days (its cleanupPeriodDays setting). The Recap's Overall keeps their numbers past that, in ~/.cache/talpy-den: times, tokens, costs, folders and chat names; and your plan's windows that ended, for 90 days. Off, it keeps only what Claude still has. This changes at once, for the VS Code extension too."});
        const week = args => new Promise(resolve => {
            try {
                const proc = Gio.Subprocess.new(['python3', '-I', GLib.build_filenamev([this.path, 'code', 'week.py']), ...args],
                    Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
                proc.communicate_utf8_async(null, null, (pr, res) => {
                    try {
                        resolve(JSON.parse(pr.communicate_utf8_finish(res)[1]));
                    } catch (e) {
                        resolve({ok: false, message: e.message});
                    }
                });
            } catch (e) {
                resolve({ok: false, message: e.message});
            }
        });
        const keep = new Adw.SwitchRow({title: "Keep a history beyond Claude's 30 days", sensitive: false});
        const forget = iconTextButton('Delete…', 'erase', () => forgetAsk.show(true));
        forget.sensitive = false;
        const saved = new Adw.ActionRow({title: 'Saved history'});
        saved.add_suffix(forget);
        // A question under the setting that asked (as every question: in
        // orange, its buttons beside it; the one that does it with the eraser)
        const question = (confirm, onYes, onNo = () => {}) => {
            const row = new Adw.ActionRow({visible: false});
            const yes = iconTextButton(confirm, 'erase', () => {
                row.visible = false;
                onYes();
            });
            const no = new Gtk.Button({label: 'Cancel', valign: Gtk.Align.CENTER});
            no.connect('clicked', () => {
                row.visible = false;
                onNo();
            });
            row.add_suffix(yes);
            row.add_suffix(no);
            return {row, show(on, text = '') {
                if (text)
                    row.title = `<span foreground="${QUESTION}">${GLib.markup_escape_text(text, -1)}</span>`;
                row.visible = on;
            }};
        };
        let syncing = false;
        let deletedChats = 0, planWindows = 0;   // (in the history: off forgets them, so it asks first)
        const setKeep = on => {
            syncing = true;
            keep.active = on;
            syncing = false;
        };
        const sync = async () => {
            const st = await week(['--history-status']);
            if (st.keep === undefined)
                return;
            setKeep(st.keep);
            keep.sensitive = true;
            deletedChats = st.deletedChats || 0;
            planWindows = st.planWindows || 0;
            // ("Kept since 1 Sep 2026, with 1 chat Claude has deleted · 12 KB", as Plasma's)
            const since = st.since ? new Date(`${st.since}T00:00`) : null;
            const n = st.deletedChats || 0;
            saved.subtitle = since ? `Kept since ${since.getDate()} ${MONTHS[since.getMonth()]} ${since.getFullYear()}, with ${n} ${n === 1 ? 'chat' : 'chats'} ` +
                `Claude has deleted · ${st.sizeKB} KB` : 'Nothing kept yet.';
            forget.sensitive = !!st.since || planWindows > 0;
        };
        const said = result => window.add_toast(new Adw.Toast({title: GLib.markup_escape_text(result.message || '', -1), timeout: 5}));
        // the numbers of the chats Claude has deleted and the plan's windows go for good: asked first
        const offAsk = question('Stop Keeping It', async () => {
            said(await week(['--history', 'off']));
            sync();
        }, () => setKeep(true));   // (kept on)
        const forgetAsk = question('Delete', async () => {
            said(await week(['--forget']));
            sync();
        });
        forgetAsk.show(false, "Delete the Recap's saved history and your plan's windows that ended? It starts again from the chats Claude still has.");
        keep.connect('notify::active', async () => {
            if (syncing)
                return;
            if (keep.active && offAsk.row.visible) {   // (switched back on while it asked: nothing changes)
                offAsk.show(false);
                return;
            }
            if (!keep.active && (deletedChats > 0 || planWindows > 0)) {
                const windows = planWindows > 0 ? "your plan's windows that ended" : '';
                const chats = deletedChats === 0 ? ''
                    : `the numbers of the ${deletedChats} ${deletedChats === 1 ? 'chat' : 'chats'} Claude has deleted`;
                offAsk.show(true, `Stop keeping the history? The Recap forgets ${chats && windows ? `${chats}, and ${windows}` : chats || windows}, for good.`);
                return;
            }
            offAsk.show(false);
            said(await week(['--history', keep.active ? 'on' : 'off']));
            sync();
        });
        group.add(keep);
        group.add(offAsk.row);
        group.add(saved);
        group.add(forgetAsk.row);
        sync();
        return group;
    }

    // The Recap tab's currency: Claude's API prices are in US dollars; another
    // currency is at the European Central Bank's reference rate of the day
    _currencyRow(settings) {
        const row = new Adw.ComboRow({title: 'Recap amounts in',
            subtitle: "Other than US dollars: at the European Central Bank's rate of the day, downloaded from ecb.europa.eu at most every 6 hours while the Recap tab is open. Nothing about your chats is sent.",
            model: Gtk.StringList.new(CURRENCIES.map(([code, name]) => `${name} (${code})`))});
        const sync = () => {
            const i = CURRENCIES.findIndex(([code]) => code === settings.get_string('recap-currency'));
            row.selected = Math.max(0, i);
        };
        sync();
        row.connect('notify::selected', () => {
            const code = CURRENCIES[row.selected] ? CURRENCIES[row.selected][0] : 'USD';
            if (settings.get_string('recap-currency') !== code)
                settings.set_string('recap-currency', code);
        });
        const id = settings.connect('changed::recap-currency', sync);
        row.connect('destroy', () => settings.disconnect(id));
        return row;
    }

    // A sound: one of the theme's, none, or a file; with a button to hear it
    _soundRow(window, settings, key, title) {
        const labels = [...SOUNDS.map(([label]) => label), 'Sound file…'];
        const row = new Adw.ComboRow({title, model: Gtk.StringList.new(labels)});
        let syncing = false;
        const sync = () => {
            syncing = true;
            const value = settings.get_string(key);
            const preset = SOUNDS.findIndex(([, v]) => v === value);
            row.selected = preset >= 0 ? preset : SOUNDS.length;
            row.subtitle = preset >= 0 ? '' : GLib.markup_escape_text(GLib.path_get_basename(value), -1);   // shown as markup
            syncing = false;
        };
        const choose = () => {
            const filter = new Gtk.FileFilter({name: 'Sound files'});
            for (const ext of ['oga', 'ogg', 'wav', 'flac', 'mp3'])
                filter.add_suffix(ext);
            const dialog = new Gtk.FileDialog({title: 'Choose a sound file', default_filter: filter});
            dialog.open(window, null, (d, result) => {
                try {
                    settings.set_string(key, d.open_finish(result).get_path());
                } catch {
                    sync();   // cancelled
                }
            });
        };
        row.connect('notify::selected', () => {
            if (syncing)
                return;
            if (row.selected < SOUNDS.length)
                settings.set_string(key, SOUNDS[row.selected][1]);
            else
                choose();
        });
        const changed = settings.connect(`changed::${key}`, sync);
        row.connect('destroy', () => settings.disconnect(changed));
        sync();

        const play = new Gtk.Button({icon_name: Icons.gnome.startNow, valign: Gtk.Align.CENTER,
            tooltip_text: 'Play this sound', css_classes: ['flat']});
        play.connect('clicked', () => this._preview(settings, settings.get_string(key)));
        row.add_suffix(play);
        // (picking "Sound file…" again, with a file set, changes nothing in the list)
        const file = new Gtk.Button({icon_name: Icons.gnome.chooseFile, valign: Gtk.Align.CENTER,
            tooltip_text: 'Choose a sound file', css_classes: ['flat']});
        file.connect('clicked', choose);
        row.add_suffix(file);
        return row;
    }

    // Plays even with Do Not Disturb on
    _preview(settings, sound) {
        if (!sound)
            return;
        const theme = new Gio.Settings({schema_id: 'org.gnome.desktop.sound'}).get_string('theme-name');
        try {
            Gio.Subprocess.new(['python3', '-I', GLib.build_filenamev([this.path, 'code', 'notify_sound.py']), sound,
                '--volume', String(settings.get_int('sound-volume')), '--force', '--theme', theme],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (e) {
            console.warn(`Talpy Den: couldn't play ${sound}: ${e.message}`);
        }
    }
}
