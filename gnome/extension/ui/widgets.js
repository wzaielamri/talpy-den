// Small building blocks for the popup (St widgets), and hover tooltips
// (GNOME Shell has none of its own for popup contents).

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// The display's scale: CSS lengths follow it, sizes given in code (an actor's
// height, Cairo's units) are in real pixels and must be multiplied by it
export function scaleFactor() {
    return St.ThemeContext.get_for_stage(global.stage).scale_factor;
}

export function box(styleClass = '', props = {}) {
    return new St.BoxLayout({style_class: styleClass, ...props});
}

export function column(styleClass = '', props = {}) {
    return new St.BoxLayout({style_class: styleClass, orientation: Clutter.Orientation.VERTICAL, ...props});
}

// One line of text, cut off with … when there's no room
export function label(text, styleClass = '', props = {}) {
    const l = new St.Label({text: text ?? '', style_class: styleClass, y_align: Clutter.ActorAlign.CENTER, ...props});
    l.clutter_text.ellipsize = props.ellipsize ?? Pango.EllipsizeMode.END;
    return l;
}

// Text that wraps onto more lines
export function paragraph(text, styleClass = '', props = {}) {
    const l = new St.Label({text: text ?? '', style_class: styleClass, x_expand: true, ...props});
    l.clutter_text.line_wrap = true;
    l.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    l.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return l;
}

// icon: an icon name, or a Gio.Icon (one of the extension's own)
export function iconButton(icon, onClick, styleClass = 'claude-icon-button') {
    const b = new St.Button({
        style_class: styleClass,
        can_focus: true,
        y_align: Clutter.ActorAlign.CENTER,
        child: new St.Icon({...(typeof icon === 'string' ? {icon_name: icon} : {gicon: icon}), style_class: 'claude-button-icon'}),
    });
    b.connect('clicked', () => onClick(b));
    return b;
}

// Buttons shown only while the pointer is over their line (they keep their
// place, so nothing moves), or while the line has the keyboard focus (its
// name, in focus: the line's other actors that take Tab) or one of them has;
// hidden, they don't take Tab, so it never lands on a button you can't see
export function showOnHover(line, buttons, focus = []) {
    const sync = () => {
        const shown = line.hover || [...focus, ...buttons].some(a => a.has_key_focus());
        for (const b of buttons) {
            b.opacity = shown ? 255 : 0;
            b.can_focus = shown;
        }
    };
    line.connect('notify::hover', sync);
    for (const a of [...focus, ...buttons]) {
        a.connect('key-focus-in', sync);
        a.connect('key-focus-out', sync);
    }
    sync();
}

export function textButton(text, onClick, styleClass = 'claude-text-button', iconName = '') {
    const content = box('claude-button-box');
    if (iconName)
        content.add_child(new St.Icon({icon_name: iconName, style_class: 'claude-button-icon'}));
    content.add_child(label(text));
    const b = new St.Button({style_class: styleClass, can_focus: true, child: content, x_align: Clutter.ActorAlign.START});
    b.connect('clicked', () => onClick(b));
    return b;
}

// Clickable text (a session's name, a recent chat): underlined on hover
export function link(text, onClick, styleClass = '') {
    const l = label(text);
    const b = new St.Button({
        style_class: `claude-link ${styleClass}`, can_focus: true, child: l,
        x_align: Clutter.ActorAlign.START, x_expand: false,
    });
    b.connect('clicked', () => onClick(b));
    return b;
}

// Small outlined label, e.g. the profile or "VS Code" next to a session name
export function tag(text, active = false, icon = '') {
    if (!icon) {
        return new St.Label({
            text, style_class: `claude-tag${active ? ' claude-tag-active' : ''}`,
            y_align: Clutter.ActorAlign.CENTER, reactive: true, track_hover: true,
        });
    }
    // (an icon before its words, as Plasma's and VS Code's tags have)
    const t = new St.BoxLayout({
        style_class: `claude-tag claude-tag-with-icon${active ? ' claude-tag-active' : ''}`,
        y_align: Clutter.ActorAlign.CENTER, reactive: true, track_hover: true,
    });
    t.add_child(new St.Icon({icon_name: icon, style_class: 'claude-tag-icon'}));
    t.add_child(new St.Label({text, y_align: Clutter.ActorAlign.CENTER}));
    return t;
}

// A chat's first line: its name, its tags and, at the end of the line, its
// state and buttons. The tags go beside the name while the whole name and all
// of them fit there, else under it (on more lines if need be), so the tags
// never cut the name short (as in the Plasma widget's SessionRow.qml; the VS
// Code extension wraps them too). Spacing: the line's style (claude-line).
const NameLineLayout = GObject.registerClass(
class ClaudeNameLineLayout extends Clutter.LayoutManager {
    _init(name, end) {
        super._init();
        this._name = name;
        this._end = end;
    }

    _gap(container) {
        const node = container.peek_theme_node();
        return node ? node.get_length('spacing') : 0;
    }

    // Where each shown child goes in a line `width` wide ([actor, x, y, w, h]),
    // and the height of it all; each line's parts are centered on it
    _place(container, width) {
        const gap = this._gap(container);
        const sized = (actor, max) => {
            const w = Math.max(0, Math.min(actor.get_preferred_width(-1)[1], max));
            return [actor, w, actor.get_preferred_height(w)[1]];
        };
        const end = this._end.visible ? sized(this._end, width) : null;
        const room = end ? Math.max(0, width - end[1] - gap) : width;
        const lines = [[sized(this._name, room)]];
        const tags = container.get_children()
            .filter(c => c.visible && c !== this._name && c !== this._end)
            .map(c => sized(c, room));
        const beside = tags.reduce((x, [, w]) => x + gap + w, lines[0][0][1]) <= room;
        let x = 0;
        for (const t of tags) {
            if (!beside && (lines.length === 1 || x + gap + t[1] > room)) {
                lines.push([]);
                x = -gap;
            }
            lines[lines.length - 1].push(t);
            x += gap + t[1];
        }
        const placed = [];
        let y = 0;
        lines.forEach((line, i) => {
            const height = Math.max(...line.map(([, , h]) => h), i === 0 && end ? end[2] : 0);
            const at = ([actor, w, h], left) => placed.push([actor, left, y + Math.round((height - h) / 2), w, h]);
            let left = 0;
            for (const part of line) {
                at(part, left);
                left += part[1] + gap;
            }
            if (i === 0 && end)
                at(end, width - end[1]);
            y += height + Math.round(gap / 2);
        });
        return [placed, Math.max(0, y - Math.round(gap / 2))];
    }

    vfunc_get_preferred_width(container, _forHeight) {
        const gap = this._gap(container);
        let min = 0, nat = -gap;
        for (const c of container.get_children().filter(a => a.visible)) {
            const [m, n] = c.get_preferred_width(-1);
            if (c !== this._end)
                min = Math.max(min, m);
            nat += gap + n;
        }
        if (this._end.visible)
            min += gap + this._end.get_preferred_width(-1)[1];
        return [min, Math.max(0, nat)];
    }

    vfunc_get_preferred_height(container, forWidth) {
        const [, height] = this._place(container, forWidth >= 0 ? forWidth : this.vfunc_get_preferred_width(container, -1)[1]);
        return [height, height];
    }

    vfunc_allocate(container, box) {
        const [placed] = this._place(container, box.get_width());
        for (const [actor, x, y, w, h] of placed) {
            const childBox = new Clutter.ActorBox();
            childBox.set_origin(box.x1 + x, box.y1 + y);
            childBox.set_size(w, h);
            actor.allocate(childBox);
        }
    }
});

export function nameLine(name, tags, end) {
    const line = new St.Widget({style_class: 'claude-line', x_expand: true, layout_manager: new NameLineLayout(name, end)});
    for (const actor of [name, ...tags, end])
        line.add_child(actor);
    return line;
}

// A bar's parts, placed as the bar is allocated: place(width, height) gives
// [actor, x, y, w, h] for each of them. (Sizing them on notify::width
// instead laid them out again in the middle of a layout pass: GNOME 43 then
// logged "Can't update stage views actor … needs an allocation" for each
// bar, at every refresh.) Its size comes from the bar's style and expand.
const BarLayout = GObject.registerClass(
class ClaudeBarLayout extends Clutter.LayoutManager {
    _init(place) {
        super._init();
        this._place = place;
    }

    vfunc_get_preferred_width(_container, _forHeight) {
        return [0, 0];
    }

    vfunc_get_preferred_height(_container, _forWidth) {
        return [0, 0];
    }

    vfunc_allocate(container, box) {
        for (const [actor, x, y, w, h] of this._place(box.get_width(), box.get_height())) {
            const childBox = new Clutter.ActorBox();
            childBox.set_origin(box.x1 + x, box.y1 + y);
            childBox.set_size(Math.max(0, w), Math.max(0, h));
            actor.allocate(childBox);
        }
    }
});

// A bar filled to pct% in the color class (working, waiting, bad)
export function meter(pct, colorClass, styleClass = 'claude-meter') {
    const share = Math.min(100, Math.max(0, pct)) / 100;
    const fill = new St.Widget({style_class: `claude-meter-fill claude-bg-${colorClass}`});
    const trough = new St.Widget({style_class: styleClass, x_expand: true, y_align: Clutter.ActorAlign.CENTER,
        layout_manager: new BarLayout((w, h) => [[fill, 0, 0, Math.round(w * share), h]])});
    trough.add_child(fill);
    return trough;
}

// A plan usage bar: filled to pct%, then, lighter, to where it would be when
// the window resets at your pace (projected, e.g. talpy_den.py's
// forecast.atReset), and a thin tick where an even pace would be by now
export function usageMeter(pct, colorClass, projected = pct, projectedClass = colorClass, evenPct = null) {
    const share = v => Math.min(100, Math.max(0, v)) / 100;
    const s = scaleFactor();
    const ahead = projected > pct
        ? new St.Widget({style_class: `claude-meter-fill claude-bg-${projectedClass}`, opacity: 90}) : null;
    const fill = new St.Widget({style_class: `claude-meter-fill claude-bg-${colorClass}`});
    const tick = evenPct !== null && evenPct !== undefined ? new St.Widget({style_class: 'claude-meter-tick'}) : null;
    const place = (w, h) => {
        const filled = Math.round(w * share(pct));
        const parts = [];
        if (ahead) {
            // under the fill's rounded end, so there's no gap between them
            const from = Math.max(0, filled - h);
            parts.push([ahead, from, 0, Math.round(w * share(projected)) - from, h]);
        }
        parts.push([fill, 0, 0, filled, h]);
        if (tick)   // sticks out above and below, so it shows over the fill too
            parts.push([tick, Math.max(0, Math.round(w * share(evenPct)) - s), -3 * s, 2 * s, h + 6 * s]);
        return parts;
    };
    const trough = new St.Widget({style_class: 'claude-meter', x_expand: true, y_align: Clutter.ActorAlign.CENTER,
        layout_manager: new BarLayout(place)});
    for (const part of [ahead, fill, tick]) {
        if (part)
            trough.add_child(part);
    }
    return trough;
}

export function dot(colorClass, styleClass = 'claude-dot') {
    return new St.Widget({style_class: `${styleClass} claude-bg-${colorClass}`, y_align: Clutter.ActorAlign.CENTER});
}

export function separator() {
    return new St.Widget({style_class: 'claude-separator', x_expand: true});
}

// Shows a little box of text under whatever the pointer rests on
export class Tooltips {
    constructor() {
        this._label = new St.Label({style_class: 'dash-label claude-tooltip', visible: false, reactive: false});
        this._label.clutter_text.line_wrap = true;
        this._label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        this._label.connect('destroy', () => {
            this._label = null;   // gone with the shell's UI (shutting down)
        });
        Main.layoutManager.uiGroup.add_child(this._label);
        this._timeout = 0;
        this._owner = null;
    }

    // text: a string, or a function giving one ([title, text] for a bold title)
    add(actor, text) {
        actor.reactive = true;
        actor.track_hover = true;
        actor.connect('notify::hover', () => {
            if (actor.hover)
                this._schedule(actor, text);
            else if (this._owner === actor || this._pending === actor)
                this.hide();
        });
        actor.connect('destroy', () => {
            if (this._owner === actor || this._pending === actor)
                this.hide();
        });
        return actor;
    }

    _schedule(actor, text) {
        this.hide();
        this._pending = actor;
        this._timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._timeout = 0;
            this._pending = null;
            this._show(actor, typeof text === 'function' ? text() : text);
            return GLib.SOURCE_REMOVE;
        });
    }

    _show(actor, text) {
        const [title, body] = Array.isArray(text) ? text : ['', text];
        if (!title && !body)
            return;
        const esc = s => GLib.markup_escape_text(s, -1);
        this._label.clutter_text.set_markup(
            title && body ? `<b>${esc(title)}</b>\n${esc(body)}` : title ? `<b>${esc(title)}</b>` : esc(body));
        this._owner = actor;
        const [x, y] = actor.get_transformed_position();
        const [, height] = actor.get_transformed_size();
        const monitor = Main.layoutManager.findMonitorForActor(actor) || Main.layoutManager.primaryMonitor;
        const [, natWidth] = this._label.get_preferred_width(-1);
        const [, natHeight] = this._label.get_preferred_height(natWidth);
        let left = Math.min(x, monitor.x + monitor.width - natWidth - 8);
        let top = y + height + 6;
        if (top + natHeight > monitor.y + monitor.height)
            top = y - natHeight - 6;
        this._label.set_position(Math.max(monitor.x + 8, Math.round(left)), Math.round(top));
        Main.layoutManager.uiGroup.set_child_above_sibling(this._label, null);
        this._label.show();
    }

    hide() {
        if (this._timeout) {
            GLib.source_remove(this._timeout);
            this._timeout = 0;
        }
        this._pending = null;
        this._owner = null;
        this._label?.hide();
    }

    destroy() {
        this.hide();
        this._label?.destroy();
    }
}
