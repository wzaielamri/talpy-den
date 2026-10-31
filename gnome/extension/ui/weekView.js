// The popup's Recap tab: your last 7 days with Claude (week.py, which the
// indicator runs only while this tab is open), as a story: how long you were
// at it and how long Claude worked, what it did, a day per row on a timeline
// (drawn with Cairo), your plan's limits, where it worked and on which chats,
// what the same work would cost at API prices, and what would use less of
// your plan (the rules of Claude Code's own /usage). No tokens used: it's
// all read from the chats' transcripts.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as L from '../logic.js';
import {box, column, iconButton, label, meter, paragraph, scaleFactor, textButton} from './widgets.js';
import * as Icons from './icons.js';

// (in the display's units: the Cairo drawings are scaled, see scaled())
const ROW_PX = 18;
const FILL_PX = 18;
// The colors of the timeline: mid tones, as the rest of the popup, so they
// read on the dark and the light shell theme
const YOU = [154 / 255, 153 / 255, 150 / 255, 0.85];
const WORK = [53 / 255, 132 / 255, 228 / 255];
const WAIT = [245 / 255, 121 / 255, 0, 0.85];
const LIMIT = [224 / 255, 27 / 255, 36 / 255];
const GRID = [0.5, 0.5, 0.5, 0.25];
const MARK = [0.5, 0.5, 0.5, 0.9];

// A section's title: big and bold, under a line that sets the section off
// from the one before
export function heading(text) {
    const title = column('claude-week-title', {x_expand: true});
    title.add_child(new St.Widget({style_class: 'claude-week-rule', x_expand: true}));
    title.add_child(label(text, 'claude-week-heading'));
    return title;
}

export function buildWeekView(ctx) {
    const week = ctx.week;
    const recap = week.recap;
    const view = column('claude-week', {x_expand: true});
    if (week.busy && recap)
        view.opacity = 160;   // what it said before, while it reads again

    // A day, 7 days or everything kept
    const spans = box('claude-week-accounts', {x_align: Clutter.ActorAlign.CENTER});
    for (const [span, text] of [['day', 'Day'], ['week', 'Week'], ['all', 'Overall']])
        spans.add_child(textButton(text, () => ctx.setWeek({span}), `claude-chip${week.span === span ? ' claude-chip-on' : ''}`));
    view.add_child(spans);

    // The days shown, one back or on, and whose chats
    const shown = recap && recap.span === week.span;
    const period = box('claude-week-period', {x_expand: true});
    const day = week.span === 'day';
    const before = iconButton(Icons.gnome.previous, () => ctx.setWeek({back: week.back + 1}));
    ctx.tips.add(before, day ? 'The day before' : 'The week before');
    // (after its tooltip, which makes it reactive: greyed out, it does nothing)
    before.reactive = before.can_focus = shown && week.back < recap.backMax;
    before.opacity = before.reactive ? 255 : 90;
    before.visible = week.span !== 'all';
    period.add_child(before);
    period.add_child(label(shown ? L.weekPeriodText({...recap, back: week.back}) : L.weekPeriodWaiting(week.span, week.back),
        'claude-week-span', {x_expand: true, x_align: Clutter.ActorAlign.CENTER}));
    const after = iconButton(Icons.gnome.next, () => ctx.setWeek({back: week.back - 1}));
    ctx.tips.add(after, day ? 'The day after' : 'The week after');
    after.reactive = after.can_focus = week.back > 0;
    after.opacity = after.reactive ? 255 : 90;
    after.visible = week.span !== 'all';
    period.add_child(after);
    const again = iconButton(Icons.gnome.refresh, () => ctx.loadWeek());
    ctx.tips.add(again, ['Read again', 'These days read again from your chats now.']);
    again.reactive = again.can_focus = !week.busy;   // (after its tooltip: greyed out while it reads)
    again.opacity = again.reactive ? 255 : 90;
    period.add_child(again);
    view.add_child(period);

    if (recap && recap.accounts.length > 1) {
        const chips = box('claude-week-accounts', {x_expand: true});
        for (const a of [{id: '', name: 'All accounts', plan: null}, ...recap.accounts]) {
            const chip = textButton(a.name + (a.plan ? ` · ${a.plan}` : ''), () => ctx.setWeek({account: a.id}),
                `claude-chip${week.account === a.id ? ' claude-chip-on' : ''}`);
            chips.add_child(chip);
        }
        view.add_child(chips);
    }

    if (week.busy && !recap && !week.error)
        view.add_child(paragraph("Reading your chats of these days. The first time takes a few seconds; after that only what's new is read.",
            'claude-dim claude-week-note'));
    if (week.error)
        view.add_child(paragraph(L.fmt("Couldn't read your week: %1", week.error), 'claude-fg-bad'));
    const s = recap ? recap.sum : null;
    const hasData = !!s && (s.workedMs > 0 || s.prompts > 0 || s.cost > 0);
    if (recap && !hasData) {
        const empty = column('claude-week-note', {x_expand: true});
        empty.add_child(paragraph(recap.span === 'day' ? 'No Claude on this day' : recap.span === 'all' ? 'No Claude yet' : 'No Claude in these days',
            'claude-strong'));
        empty.add_child(paragraph(recap.span === 'day' ? 'None of your chats here (or on the SSH hosts shown) has a prompt or a reply on this day.'
            : recap.span === 'all' ? 'None of your chats here (or on the SSH hosts shown) has a prompt or a reply yet.'
                : 'None of your chats here (or on the SSH hosts shown) has a prompt or a reply in these 7 days.', 'claude-dim'));
        view.add_child(empty);
    }
    if (!hasData)
        return view;
    const cur = L.weekCurrency(recap);

    const tiles = box('claude-week-tiles', {x_expand: true});
    for (const t of L.weekTiles(recap)) {
        const tile = column('claude-week-tile', {x_expand: true});
        tile.add_child(label(t.label, 'claude-small claude-dim'));
        tile.add_child(label(t.value, 'claude-week-value'));
        if (t.delta)
            tile.add_child(label(t.delta, 'claude-small claude-dim'));
        if (t.trend.length > 1)
            tile.add_child(trendBars(t.trend));
        ctx.tips.add(tile, [t.label, t.tip]);
        tiles.add_child(tile);
    }
    view.add_child(tiles);
    const facts = L.weekFactsText(s);
    if (facts)
        view.add_child(paragraph(facts, 'claude-small claude-dim'));

    // Then as a story: what Claude did, when (the days, your plan's limits),
    // where, the chats, the money and what could use less of your plan
    const did = L.weekWorkText(recap.work);
    if (did) {
        const work = column('claude-week-section', {x_expand: true});
        work.add_child(heading('What Claude did'));
        work.add_child(paragraph(did, ''));
        if (L.weekToolsText(recap.work))
            work.add_child(paragraph(L.weekToolsText(recap.work), 'claude-small claude-dim'));
        view.add_child(work);
    }
    view.add_child(buildTimeline(ctx, recap, cur));
    view.add_child(buildPlan(ctx, recap));
    view.add_child(buildProjects(ctx, recap, cur));
    if (recap.chats.length) {
        const chats = column('claude-week-section', {x_expand: true});
        chats.add_child(heading('Chats it worked on most'));
        for (const c of recap.chats)
            chats.add_child(chatLine(ctx, c, cur));
        view.add_child(chats);
    }
    const models = buildBars(ctx, 'At API prices', recap.models.map(m => ({
        name: m.model, share: m.share, value: `${L.moneyText(m.cost, cur)} · ${L.weekShareText(m.share)}`, color: 'none',
        tip: `${m.model}: ${L.moneyText(m.cost, cur)} · ${L.plural(m.requests, '%1 request', '%1 requests')}`,
    })));
    const cache = L.weekCacheText(recap);
    if (cache)
        models.add_child(paragraph(cache, 'claude-small claude-dim'));
    view.add_child(models);
    view.add_child(buildTips(ctx, recap));
    view.add_child(paragraph(L.weekFootText(recap), 'claude-small claude-dim claude-week-foot'));
    return view;
}

// The same number over the 5 weeks up to these days, these last (a week
// the widget no longer has: a dot)
function trendBars(values) {
    const bars = box('claude-week-trend', {y_align: Clutter.ActorAlign.END});
    const top = Math.max(1e-9, ...values.filter(v => v !== null));
    values.forEach((v, i) => {
        const height = v === null ? 3 : Math.max(1, Math.round(12 * v / top));
        bars.add_child(new St.Widget({
            style_class: `claude-week-trend-bar${i === values.length - 1 ? ' claude-week-trend-now' : ''}`,
            style: `height: ${height}px;${v === null ? ' opacity: 0.3;' : ''}`, y_align: Clutter.ActorAlign.END,
        }));
    });
    return bars;
}

// A chat in the tab's lists: click one of this computer's to bring it up
function chatLine(ctx, c, cur, where = null, sub = false) {
    const line = box('claude-week-chat', {x_expand: true});
    line.add_child(label(c.name, sub ? 'claude-small' : '', {x_expand: true}));
    // (its folder and numbers: right-aligned columns of one width in every list, as Plasma's)
    const place = where !== null ? where : (c.host ? `${c.host}: ` : '') + c.folder;
    if (place) {
        const folder = label(place, 'claude-small claude-dim claude-week-folder');
        folder.clutter_text.ellipsize = 2;   // Pango.EllipsizeMode.MIDDLE
        line.add_child(folder);
    }
    line.add_child(label(`${L.hoursText(c.workedMs)} · ${L.moneyText(c.cost, cur)}`, 'claude-small claude-dim claude-week-chat-numbers'));
    const opens = !c.host && !!c.chatId;
    const button = new St.Button({style_class: `${opens ? 'claude-row-button' : ''}${sub ? ' claude-week-sub' : ''}`, child: line,
        x_expand: true, can_focus: opens, reactive: opens});
    button.connect('clicked', () => {
        if (opens)   // (its tooltip makes every row reactive)
            ctx.openChatById(c.chatId, c.profileDir);
    });
    ctx.tips.add(button, c.host ? `${c.name} on ${c.host}: its row under ${c.host} opens it` : `Open “${c.name}”`);
    return button;
}

// A day per row: when you were at it, when Claude worked (darker where
// several chats worked at once), when it waited for your answer, where a
// usage limit stopped a chat. Click a day for its chats.
function buildTimeline(ctx, recap, cur) {
    const section = column('claude-week-section', {x_expand: true});
    const weeks = recap.span === 'all';   // (a row per 7 days, with their numbers)
    section.add_child(heading(weeks ? 'Week by week' : recap.span === 'day' ? 'Through the day' : 'Day by day'));
    const legend = box('claude-week-head', {x_expand: true});
    const keys = weeks ? [['claude-week-swatch-you', 'You'], ['claude-bg-working', 'Claude worked']]
        : [['claude-week-swatch-you', 'You'], ['claude-bg-working', 'Claude working'], ['claude-bg-waiting', 'Waiting for you']];
    if (!weeks && recap.days.some(d => d.limits && d.limits.length))
        keys.push(['claude-week-swatch-limit', 'A usage limit stopped a chat']);
    for (const [cls, text] of keys) {
        legend.add_child(new St.Widget({style_class: `claude-week-swatch ${cls}`, y_align: Clutter.ActorAlign.CENTER}));
        legend.add_child(label(text, 'claude-small claude-dim'));
    }
    section.add_child(legend);

    const axis = box('claude-week-row', {x_expand: true});
    axis.add_child(label('', 'claude-week-day'));
    const hours = box('claude-week-hours', {x_expand: true});
    (weeks ? [] : [0, 6, 12, 18, 24]).forEach((h, i) => {
        hours.add_child(label(String(h), 'claude-small claude-dim', {x_expand: i < 4}));
    });
    axis.add_child(hours);
    axis.add_child(label('You', 'claude-small claude-dim claude-week-num'));
    axis.add_child(label('Claude', 'claude-small claude-dim claude-week-num'));
    section.add_child(axis);

    const hint = weeks ? 'Click a week for its chats.' : 'Point at a day to see what went on then; click it for its chats.';
    const readout = label(hint, 'claude-small claude-dim claude-week-readout', {x_expand: true});
    const areas = [];
    const last = weeks ? 0 : recap.days.length - 1;
    const most = Math.max(1, ...recap.days.map(d => Math.max(d.youMs, d.workedMs)));
    recap.days.forEach((d, i) => {
        const today = i === last && recap.back === 0;
        const open = ctx.week.open === `day:${d.day}` && d.chats && d.chats.length > 0;
        const row = box('claude-week-row', {x_expand: true});
        const dayLabel = label(L.weekRowDay(d.day, weeks), `claude-small claude-week-day${today || open ? ' claude-strong' : ''}`);
        row.add_child(dayLabel);
        const area = new St.DrawingArea({x_expand: true, height: ROW_PX * scaleFactor(), reactive: true, track_hover: true});
        area._week = {day: d, today, hoverX: -1, most};
        area.connect('repaint', a => (weeks ? paintWeek(a) : paintDay(a, recap.generatedAt)));
        area.connect('motion-event', (a, event) => {
            if (weeks)
                return Clutter.EVENT_PROPAGATE;
            const [x, y] = event.get_coords();
            const [ok, lx] = a.transform_stage_point(x, y);
            if (!ok)
                return Clutter.EVENT_PROPAGATE;
            const width = Math.max(1, a.get_width());
            const span = d.end - d.start;
            for (const other of areas) {
                if (other !== a && other._week.hoverX >= 0) {
                    other._week.hoverX = -1;
                    other.queue_repaint();
                }
            }
            a._week.hoverX = lx;
            a.queue_repaint();
            readout.text = L.weekHoverText(d, L.weekDayMoment(d, lx / width), recap.generatedAt, span / width);
            readout.remove_style_class_name('claude-dim');
            return Clutter.EVENT_PROPAGATE;
        });
        area.connect('leave-event', a => {
            a._week.hoverX = -1;
            a.queue_repaint();
            readout.text = hint;
            readout.add_style_class_name('claude-dim');
            return Clutter.EVENT_PROPAGATE;
        });
        if (d.chats && d.chats.length) {
            area.connect('button-release-event', () => {
                ctx.weekUnfold(`day:${d.day}`);
                return Clutter.EVENT_STOP;
            });
        }
        areas.push(area);
        row.add_child(area);
        row.add_child(label(d.youMs >= 60000 ? L.hoursText(d.youMs) : '–', 'claude-small claude-dim claude-week-num'));
        const worked = label(d.workedMs >= 60000 ? L.hoursText(d.workedMs) : '–', 'claude-small claude-week-num');
        ctx.tips.add(worked, L.weekDayTip(d, cur));
        row.add_child(worked);
        section.add_child(row);
        if (open) {
            for (const c of d.chats)
                section.add_child(chatLine(ctx, c, cur, null, true));
        }
    });
    section.add_child(readout);
    return section;
}

// Overall's row: the 7 days' time, yours and Claude's, against the busiest 7 days
function paintWeek(area) {
    const {day: d, most} = area._week;
    const [cr, w, h] = scaled(area);
    cr.setSourceRGBA(...GRID);
    cr.rectangle(0, h - 1, w, 1);
    cr.fill();
    cr.setSourceRGBA(...YOU);
    if (d.youMs > 0)
        cr.rectangle(0, 1, Math.max(1, w * d.youMs / most), 4);
    cr.fill();
    cr.setSourceRGBA(...WORK, 1);
    if (d.workedMs > 0)
        cr.rectangle(0, 7, Math.max(1, w * d.workedMs / most), 9);
    cr.fill();
    cr.$dispose();
}

// A drawing area's Cairo context, drawing in the display's units, and its size in them
function scaled(area) {
    const cr = area.get_context();
    const scale = scaleFactor();
    const [w, h] = area.get_surface_size();
    cr.scale(scale, scale);
    return [cr, w / scale, h / scale, scale];
}

function paintDay(area, now) {
    const {day: d, today} = area._week;
    const [cr, w, h, scale] = scaled(area);
    const hoverX = area._week.hoverX / scale;   // (in real pixels: where the pointer is on the actor)
    const x = ms => w * L.weekDayPlace(d, ms);   // (by the day's own clock: under the hours over the rows)
    const bar = (a, b, top, height) => {
        cr.rectangle(x(a), top, Math.max(1, x(b) - x(a)), height);
        cr.fill();
    };
    cr.setSourceRGBA(...GRID);
    for (const q of [0.25, 0.5, 0.75]) {   // (6, 12 and 18 o'clock)
        cr.rectangle(Math.round(w * q), 0, 1, h);
        cr.fill();
    }
    cr.rectangle(0, h - 1, w, 1);
    cr.fill();
    cr.setSourceRGBA(...YOU);
    for (const [a, b] of d.you)
        bar(a, b, 1, 4);
    cr.setSourceRGBA(...WAIT);
    for (const [a, b] of d.wait)
        bar(a, b, 7, 9);
    for (const [a, b, n] of d.work) {
        cr.setSourceRGBA(...WORK, n >= 3 ? 1 : n === 2 ? 0.8 : 0.55);
        bar(a, b, 7, 9);
    }
    cr.setSourceRGBA(...LIMIT, 1);
    for (const t of d.limits || []) {
        cr.rectangle(Math.round(x(t)) - 1, 0, 2, h);
        cr.fill();
    }
    cr.setSourceRGBA(...MARK);
    if (today) {
        cr.rectangle(Math.round(x(now)), 0, 1, h);
        cr.fill();
    }
    if (hoverX >= 0) {
        cr.rectangle(Math.round(hoverX), 0, 1, h);
        cr.fill();
    }
    cr.$dispose();
}

// How full your plan's windows are now, and how they filled up (this
// computer's accounts, from the widget's usage history)
function buildPlan(ctx, recap) {
    const section = column('claude-week-section', {x_expand: true});
    const plans = recap.plan || [];
    if (!plans.length)
        return section;
    section.add_child(heading("Your plan's limits now"));
    for (const p of plans) {
        for (const w of p.windows) {
            const line = box('claude-stats-project', {x_expand: true});
            line.add_child(label((plans.length > 1 ? `${p.name} · ` : '') + w.label, 'claude-small claude-week-name'));
            const area = new St.DrawingArea({x_expand: true, height: FILL_PX * scaleFactor(), y_align: Clutter.ActorAlign.CENTER});
            area.connect('repaint', a => paintFill(a, w, recap.generatedAt));
            line.add_child(area);
            line.add_child(label(L.weekPlanText(w, recap.generatedAt),
                `claude-small claude-stats-numbers claude-week-plan-numbers ${w.pct >= 90 ? 'claude-fg-bad' : 'claude-dim'}`));
            ctx.tips.add(line, [L.fmt('%1: %2% used', w.label, Math.round(w.pct)),
                'How this window of your plan filled up, from its start (on the left) to when it resets (on the right), as Talpy Den saw it.']);
            section.add_child(line);
        }
    }
    return section;
}

function paintFill(area, win, now) {
    const [cr, w, h] = scaled(area);
    const [from, until] = L.weekWindowSpan(win);
    const x = ms => Math.max(0, Math.min(w, (ms - from) / (until - from) * w));
    const y = pct => h - 0.5 - Math.max(0, Math.min(100, pct)) / 100 * (h - 1);
    cr.setSourceRGBA(...GRID);
    cr.rectangle(0, 0, w, h);
    cr.fill();
    const points = win.points.filter(p => p[0] >= from);
    if (points.length) {
        const color = win.pct >= 90 ? LIMIT : win.pct >= 70 ? WAIT.slice(0, 3) : WORK;
        const end = Math.min(now, until);
        const lastPct = points[points.length - 1][1];
        cr.moveTo(x(points[0][0]), h);
        for (const [t, pct] of points)
            cr.lineTo(x(t), y(pct));
        cr.lineTo(x(end), y(lastPct));
        cr.lineTo(x(end), h);
        cr.closePath();
        cr.setSourceRGBA(...color, 0.3);
        cr.fill();
        cr.moveTo(x(points[0][0]), y(points[0][1]));
        for (const [t, pct] of points)
            cr.lineTo(x(t), y(pct));
        cr.lineTo(x(end), y(lastPct));
        cr.setSourceRGBA(...color, 1);
        cr.setLineWidth(1.5);
        cr.stroke();
    }
    cr.$dispose();
}

// The project folders Claude worked in most (a chat started in a subfolder
// of a repository counts for the repository): click one for its chats
function buildProjects(ctx, recap, cur) {
    const section = column('claude-week-section', {x_expand: true});
    if (!recap.projects.length)
        return section;
    section.add_child(heading('Where Claude worked'));
    const most = Math.max(1, ...recap.projects.map(q => q.workedMs));
    for (const p of recap.projects) {
        const key = `project:${p.host}|${p.path}`;
        const open = ctx.week.open === key;
        const chats = Array.isArray(p.chats) ? p.chats : [];
        const line = box('claude-stats-project', {x_expand: true});
        line.add_child(new St.Icon({icon_name: open ? Icons.gnome.unfolded : Icons.gnome.folded, style_class: 'claude-week-fold'}));
        line.add_child(label((p.host ? `${p.host}: ` : '') + p.name, `claude-small claude-week-name${open ? ' claude-strong' : ''}`));
        line.add_child(meter(100 * p.workedMs / most, 'working', 'claude-meter claude-stats-meter'));
        line.add_child(label(`${L.hoursText(p.workedMs)} · ${L.moneyText(p.cost, cur)}`, 'claude-small claude-dim claude-stats-numbers'));
        const button = new St.Button({style_class: 'claude-row-button', child: line, x_expand: true, can_focus: true, reactive: true});
        button.connect('clicked', () => ctx.weekUnfold(key));
        ctx.tips.add(button, [(p.host ? `${p.host}: ` : '') + p.path,
            `Claude worked ${L.hoursText(p.workedMs)} · ${L.moneyText(p.cost, cur)} at API prices\n` +
            `${L.plural(p.prompts, '%1 prompt', '%1 prompts')} · ${L.plural(p.chatCount !== undefined ? p.chatCount : chats.length, '%1 chat', '%1 chats')}` +
            '\n\nClick for its chats.']);
        section.add_child(button);
        if (open) {
            for (const c of chats)
                section.add_child(chatLine(ctx, c, cur, '', true));
            const more = (p.chatCount || 0) - chats.length;
            if (more > 0)
                section.add_child(label(more === 1 ? 'and 1 more chat' : `and ${more} more chats`, 'claude-small claude-dim claude-week-more'));
        }
    }
    return section;
}

function buildBars(ctx, title, rows) {
    const section = column('claude-week-section', {x_expand: true});
    if (!rows.length)
        return section;
    section.add_child(heading(title));
    for (const r of rows) {
        const line = box('claude-stats-project', {x_expand: true});
        line.add_child(label(r.name, 'claude-small claude-week-name'));
        line.add_child(meter(100 * r.share, r.color, 'claude-meter claude-stats-meter'));
        line.add_child(label(r.value, 'claude-small claude-dim claude-stats-numbers'));
        ctx.tips.add(line, r.tip);
        section.add_child(line);
    }
    return section;
}

// What would use less of your plan (Claude Code's /usage rules), and what
// coming back to chats whose cache had expired cost
function buildTips(ctx, recap) {
    const section = column('claude-week-section', {x_expand: true});
    section.add_child(heading('What could use less of your plan'));
    const cold = L.weekColdText(recap);
    if (!recap.tips.length && !cold)
        section.add_child(paragraph('Nothing stands out: no habit takes a tenth of the usage shown.', 'claude-dim'));
    for (const t of recap.tips) {
        const line = box('claude-week-tip', {x_expand: true});
        line.add_child(new St.Icon({icon_name: Icons.gnome[L.weekTipMeaning(t.key)], style_class: 'claude-button-icon claude-dim',
            y_align: Clutter.ActorAlign.START}));
        const text = column('', {x_expand: true});
        text.add_child(paragraph(t.title, ''));
        if (t.detail)
            text.add_child(paragraph(t.detail, 'claude-small claude-dim'));
        line.add_child(text);
        // (its share and command in columns of one width, empty where it has
        // none, so the shares line up, as Plasma's)
        const hasPct = t.pct !== null && t.pct !== undefined;
        const pct = label(hasPct ? `${t.pct}%` : '', 'claude-small claude-week-tip-pct', {y_align: Clutter.ActorAlign.START});
        if (hasPct) {
            ctx.tips.add(pct, [`${t.pct}% of the usage shown`, "Of the usage of these days, as Claude Code's /usage weighs it " +
                "toward your plan's limits. A request can count for several of these."]);
        }
        line.add_child(pct);
        if (t.command) {
            const copy = textButton(ctx.week.copied === t.command ? 'Copied' : t.command, () => ctx.copyText(t.command),
                'claude-chip claude-chip-code claude-week-tip-command');
            copy.y_align = Clutter.ActorAlign.START;
            ctx.tips.add(copy, [`Copy ${t.command}`, 'Type it in a chat of yours.']);
            line.add_child(copy);
        } else if (recap.tips.some(o => o.command)) {
            line.add_child(new St.Widget({style_class: 'claude-week-tip-command'}));
        }
        section.add_child(line);
    }
    if (cold)
        section.add_child(paragraph(cold, 'claude-small claude-dim'));
    return section;
}
