# Talpy's Run: an endless-run game for the big Talpy (design)

Date: 2026-11-18. Size: a project (full design).

## Intent

The owner wants a second minigame with the big Talpy (Talpa, the mole) that
plays like the game browsers show offline: the character runs, you jump
over what comes, it gets faster and the obstacles come thicker, and one
bump ends the run. People know that game at once, so it needs no
explaining, and the speed-up only means something because you can lose.
It's for a moment of play while Claude works: started from Talpy, over in
a minute or two, never in the way of the chats.

Picked by the owner: **a real run** (the first bump ends it, the distance
and your best show at the end, click to run again), not a run you can't
lose (judged boring: the speed-up would mean nothing).

## Goals

- An endless run on the big Talpy's stage, in the Plasma widget's popup and
  VS Code's main view, from one shared piece of game logic.
- Click, tap or Space: he jumps. Hold (or ↓): he digs in, under what flies.
- It starts gentle and gets harder: faster, obstacles closer together, new
  kinds of obstacles further on, always possible to clear.
- One bump ends the run: "212 m · best 340 m" ("New best! 340 m" when it
  is); a click runs again.
- Its own look: Talpa in his garden, drawn as Talpy's other things are.

## Non-goals

- Scores anywhere but the run's end: no counters, tallies or badges in the
  rows, the headline, the Recap or a settings page; no leaderboard, no
  sharing.
- Sound.
- GNOME (not at parity: kept from breaking only), the desktop pets, the small
  Talpys on rows, Talpy Chat's window.
- A window or view of its own.

## Anti-goals (a failure even if it works)

- Anything slower when nobody plays: nothing ticks, draws or listens for
  keys unless a run is on (the owner's rule: light, 60 fps).
- Clicks taken when nobody plays: clicking Talpy still pets him, the
  headline and ticker still open chats.
- A run that hides a chat that needs you: such a chat ends the run at once,
  as Peekaboo ends today.
- Looking like the browsers' game: no dinosaur, no cactus, no pterodactyl,
  no grey pixel style. Talpa, a garden, Talpy's own colours and lines.

## How it fits what exists

- `package/contents/ui/talpy/games.mjs` holds the games (Peekaboo today,
  `GAMES = ['peekaboo']`, `pickGame`), plain ES2017, shared: Plasma imports it
  in `Pet.qml`, VS Code's webview vendors it (`vscode/webview/pets/pet.ts`).
  A host ticks a game only while `game.on`, after `talpy.tick(now)`, gives
  clicks to `game.hit()`, and draws what the game says (Peekaboo's holes
  with `drawHole` from `talpy.mjs`). The new game is a second class there,
  `Run`, with the same contract (`start(now, wake)`, `tick(now)`, `hit()`,
  `stop()`, `on`) plus what a run needs (below).
- Talpy's poses for it exist: the cookie game's `chase.run` (on his feet,
  running), `chase.leap` (jumping), and his `depth` (in the ground). The
  game holds a pose as Peekaboo holds his "down" pose (`HOLD`), and turns
  `talpy.brainOn` off while on and back after.
- Starting: today four quick clicks on him or **Play with Talpy** (Plasma's
  menu in `main.qml`; VS Code's view menu, `vscode/src/view.ts`) start
  `pickGame`'s game. Stopping: Esc, a click outside the stage, the stage out
  of sight, a chat that needs you (`Pet.qml`, `pet.ts`).
- Tests: `tests/test_games.py` runs the game module in node (`run_node`)
  and reads the hosts' code for their wiring; the same for the new game.

## What gets built

### Playing

- **Where he is:** Talpa runs in place near the stage's left (about a fifth
  in), on its floor; the ground and everything on it scroll past from the
  right. The stage's own size is the playfield (`host.stage()`).
- **Jump:** a click or tap anywhere on the stage, Space or ↑. One height of
  jump (about 1.6 of his body's height), a smooth arc; no jumping again in
  the air. A press while he's in the air is kept for the moment he lands
  (a little forgiving).
- **Dig:** hold the click, or hold ↓: he dives in up to his eyes (a puff of
  earth), and pops up when you let go, or by himself after about a second.
  Digging passes **under what flies**; what stands on the ground still hits
  him (it's on his ground line). So: jump over things on the ground, dig
  under things in the air.
- **Obstacles** (a garden, Talpy's lines and colours):
  - a pebble (low, short), a stone (taller), a flower pot (tall, narrow),
    later two pebbles together (wide);
  - from about 200 m, a crow flying at head height (dig under it); further
    on, now and then one flying high (run on under it).
- **Getting harder:** it starts slow and speeds up a little every 100 m, up
  to a cap (about twice the start); the gaps between obstacles shrink with
  it, but a gap is never shorter than a jump needs at that speed (and some
  room to land), so every run can always be cleared. New kinds come in by
  distance, not at random from the start.
- **Distance:** in metres, counted from the speed (about 10 m a second at
  the start). Shown small in the stage's top right while running, as one
  right-aligned figure.
- **Hits:** forgiving: an obstacle's hit box is a little smaller than its
  drawing, Talpa's too.
- **The first 2 s:** a hint under him, "Click to jump · hold to dig"; no
  obstacle in that time.

### The end of a run

- **A bump:** the world stops, Talpa tumbles (a dizzy pose, stars or a
  wobble of his own), and the stage says "212 m · best 340 m", or "New
  best! 340 m" when this run beat it. A click (or Space) runs again at
  once; Esc or a click outside the stage ends the game; after about 10 s
  with no click it ends by itself.
- **Ended by the host** (Esc, a click outside, the stage out of sight, a
  chat that needs you): over at once, Talpa back to his own doings as after
  Peekaboo; the distance run so far still counts for the best, without the
  end screen.

### Starting it

- **Play with Talpy** offers the games by name: *Peekaboo* and *Run* (both
  hosts' menus). Four quick clicks on Talpy still pick one at random
  (`pickGame`), so the runner turns up there too.
- Only where Peekaboo plays: the big, lone Talpy on his stage, Playful Talpy
  on, no cookie out.

### Best distance

- Kept per app, as the cookie counts are: Plasma in the widget's config (a
  new key, shared by every Talpy Den widget the way `cookiesEaten` is), VS
  Code in the extension's own storage. Shown only at a run's end. No reset
  button (not needed: nothing else shows it).

### Drawing and speed

- The game keeps its obstacles as plain data (`things`: kind, x, y, size)
  and its state; the hosts draw them with a new shared function in
  `talpy.mjs` (as `drawHole`, `drawCookie`), on the stage canvas they
  already have, and Talpa with his own renderer in the pose the game holds.
- At most a handful of obstacles exist at once; arrays are reused, nothing
  is made per frame. Ticked only while a run is on, then 60 fps; while the
  end screen shows, nothing moves, so nothing ticks but the wait for a
  click.
- Keys (Space, ↑, ↓, Esc) are listened for only while the game is on (VS
  Code: document listeners while on, as pet.ts does for Esc today; Plasma:
  the stage's key handling while on).

## Constraints

- Plain ES2017 in `talpy/` (see `paths.mjs`): it runs in Qt's JS engine and
  in the webview.
- Python 3.7 still runs the test suite (the tests only drive node).
- English words through i18n in Plasma, as the rest of the widget.
- The owner checks UI at 380 px too: the end line and the distance must fit
  a narrow popup (one line; the distance right-aligned).

## Approaches

1. **Picked: a second game in `games.mjs`, drawn by the existing hosts.**
   One piece of logic for Plasma and VS Code, the hosts' existing ticking,
   stopping and drawing paths; light by construction.
2. A bigger game in a window or view of its own: more room, but a new
   window for both apps and more weight for a minute of play.
3. On the desktop pets: they pause under windows, and they aren't where
   you are while Claude works.

## Left to the builder

- The numbers: start speed, speed-up step and cap, gap ranges, jump arc,
  dig time, hit-box margins (tuned by playing; the rules above are fixed).
- The obstacles' drawings, within "Talpy's lines and colours".
- How VS Code stores the best (follow the cookie counts).
- Talpa's tumble pose (from his existing poses if one fits).
- Exact menu wording beyond *Peekaboo* and *Run*.

## Calls I made (the owner may change them)

- Dig only passes under what flies; ground obstacles still hit.
- The distance shows while running (small, top right), the best only at
  the end.
- A run the host ends still counts for the best.
- The end screen waits about 10 s for a click, then the game ends.
- Four quick clicks pick a game at random, the runner included.
