# Deep Dig: a second high-score game for the big Talpy (design)

Date: 2026-11-19. Size: a project (full design).

## Intent

The owner wants more than one game with a score, so a moment of play while
Claude works isn't always the same game ("so people don't get bored"). Talpy's
Run (2026-11-18, `docs/superpowers/specs/2026-11-18-talpy-run-design.md`) is
the first; Deep Dig is the second. It's built for what Talpa is: a burrowing
creature with a lamp on his head. He digs straight down through the ground,
what's buried comes up at him, and you steer him around it. Where the Run is
timing (jump, dig), Deep Dig is steering and planning a way through.

The owner's words for the bar: **"make sure the physics are correct, not
weird movements, and also nice design."** Movement that feels physical and a
polished look are the point, not extras.

## Goals

- A dig on the big Talpy's stage, in the Plasma widget's popup and VS Code's
  main view, from one shared piece of game logic, next to the Run.
- He follows the mouse across the stage (or ←/→, or a drag on touch), with
  smooth, physical movement: he speeds up and slows down, has a top speed,
  leans into turns and swings back upright.
- What's buried changes with depth (soil layers, new kinds of things), so a
  long dig keeps showing something new.
- One score: metres dug, plus 10 m for each cookie he grabs. The first touch
  with anything ends the dig with how deep he got and your best.
- The same end as the Run: "212 m · best 340 m" or "New best! 340 m"; a
  click digs again; with none in 5 s his stage is back to your chats.

## Non-goals

- Scores anywhere but the game's end (as the Run): no counters, badges,
  leaderboard or sharing; the best only at the end.
- Sound.
- GNOME (not at parity: kept from breaking only), the desktop pets, the small
  Talpys on rows, Talpy Chat's window.
- A window or view of its own.
- Changing the Run's controls, its obstacles or its fairness rules (it gets
  cookies and better physics, below; the rest stays as it plays now).

## Anti-goals (a failure even if it works)

- **Weird movement:** teleporting to the mouse, sliding at a constant speed,
  jitter, snapping, a lean that flips, a tunnel that doesn't follow the path
  he took, a picture a frame behind his position.
- Anything slower when nobody plays: nothing ticks, draws or listens unless a
  game is on; during a game, no stage-sized canvas painted every frame (the
  Run's lesson: each thing a picture drawn once and moved).
- An unfair dig: a row of things with no way through, or a way through he
  can't reach in time at his top speed.
- A buried thing that looks like something to grab when it ends the game, or
  the other way round (the owner caught this for the Run: mushrooms read as
  power-ups). Only cookies are grabbed; everything that hurts looks hard,
  sharp or solid.
- A dig that hides a chat that needs you: such a chat ends it at once.

## How it fits what exists

- `package/contents/ui/talpy/games.mjs`: `GAMES`, `pickGame`, `Peekaboo`,
  `Run`. Run's contract: `start(now)`, `tick(now)`, `hit()`, `stop()`,
  `press(what)`, `release(what)`, and for the host `on`, `state` ('ready',
  'run', 'over'), `things` (kind, x, y, w, h, frame, variant, slot), `slots`,
  `lift`, `meters`, `best`, `newBest`, `hint`. Host: `stage()`, `px()`,
  `moveTo(x)`, `say(what)`, `changed()`, `face(left)`, `best()`,
  `saveBest(m)`, `grow(on)`, `runOk()`.
- Things are drawn by `drawThing` in `talpy.mjs` (ink outlines, shading, a
  floor shadow; `vscode/dev/things.html` shows them all). Plasma (`Pet.qml`)
  keeps one Canvas per slot, painted once per look and moved by bindings;
  VS Code (`pet.ts` `runSprite`) caches one canvas per look and `drawImage`s
  it each frame.
- The stage grows for the Run: Plasma `PetStrip.qml` `running` (+5 grid
  units), VS Code `stage.ts` `setRunning` (`.td-running`, `pets.css` 11 grid
  units). The status fades, the press overlay and keys are the game's
  (Plasma `runPresses`/`runKeys`; VS Code `listenToRun`).
- Talpy's position: the host draws him at the floor minus `lift` (Plasma
  `runLift`, VS Code `runLift()`), at `px`; both hosts can already rotate
  him (Plasma's `Rotation` on `TalpyView`, VS Code's `rotate()` on his
  sheets).
- The best: Plasma `runBest` (`main.xml`, `sharedKeys`, `saveRunBest` keeps
  the larger), VS Code memento `talpyDen.runBest` via `runBest` messages and
  `nextBest`.
- Menus: Plasma `main.qml` ("Play Peekaboo with Talpy", "Run with Talpy",
  `runOk`), VS Code's view ⋯ menu (`talpyDen.playPeekaboo`,
  `talpyDen.runWithTalpy`).
- Tests: `tests/test_games.py` drives the game module in node (a seeded
  player plays whole runs) and reads the hosts' wiring.

## Approaches

1. **Picked by the owner: a third game in `games.mjs`, sharing the Run's
   machinery.** What the Run built becomes shared by both games rather than
   copied: the slots and their pictures, the end screen and its 5 s wait,
   the kept best, the stage growing (to a height each game says). One logic
   and one set of tests for both apps. Costs a careful refactor of the Run's
   hosting, guarded by the Run's tests.
2. A separate game file with its own host code: no risk to the Run, but a
   second copy of slots, pictures, end screen and best in each app; fixes
   made twice, the games drift apart.
3. (Dropped) one generic scroller engine both games configure: their inputs
   (jump/dig vs steer) have too little in common; it would make the Run's
   code harder to follow.

## What gets built

### The stage during a dig (the owner's choice: B)

- It grows to about **16 grid units** (the Run: 11): about 290 px in Plasma,
  260 px in VS Code. The chat list moves down meanwhile (in a ~560 px popup
  about a third of it still shows). The headline, counts and ticker fade out
  as for the Run; every press on the stage is the game's.
- It's underground: the stage is filled with the soil's colour (below) while
  the dig is on, back to the stage's own look as it ends.
- Talpa stays in the **top quarter**, so he sees about 220 px ahead (about
  2.5 s at the starting speed).

### Moving (the owner: "correct physics, not weird movements")

- **Aim:** the mouse's x over the stage (kept where it left when it leaves
  the stage); ←/→ held move the aim at a steady rate; on touch, the drag's x.
- **Motion:** his x follows the aim with a critically damped spring (no
  overshoot), clamped to a top sideways speed and a top acceleration, all
  advanced per frame with the same time step the Run uses (whole host
  frames). So: he eases off as he arrives, never teleports, never slides at
  a constant speed into a stop.
- **Lean:** he tilts with his sideways speed (towards where he's going, up
  to about 20°), eased so it never flips or snaps, and swings back upright
  as he stops (a little settle, no wobble that keeps going).
- **Facing (the owner, after the gallery: head-down "doesn't look good"):**
  he's upright, digging down with his paws scooping below him (Talpy's
  `scoop` arms), his lamp glowing on his head; going right his paws lead
  right and his head tilts back left (`turn` = −lean).
- **Digging feel:** small clods of earth fly off his paws, more when he
  turns; a slight bob as he digs.
- **The tunnel:** behind him (above, scrolling up with the ground), along the
  exact path he took: a darker, smooth-edged band his width, made of pieces
  laid as he goes (decoration, never in the way).
- **Walls:** the stage's sides; the aim is clamped so he never leaves it, and
  he slows into a wall, never bounces.

### What's buried, by depth (the owner: approved)

- **0–100 m, topsoil:** brown earth; roots (curving, from a side or across
  part of the way), pebbles and stones.
- **100–300 m, clay:** reddish earth; buried pipes (long, across part of the
  stage, with a gap), old bottles, roots still.
- **300 m on, deep rock:** dark earth; big boulders; glowing crystals as
  decoration (faint and still, in the wall: the owner, so they're taken for
  neither a treasure nor an obstacle); now and then a **beetle** crawling sideways (it moves: dodge
  it). Beetles only in rows of their own (nothing else to dodge at that
  moment), so a way past always exists.
- The soil's colour shifts smoothly from one layer to the next as he gets
  there (no hard cut).
- **Decoration** (never in the way, faint or small, clearly not solid):
  worms wriggling, small specks and stones in the earth, the crystals' glow.
- **Cookies:** the one thing that shines (the owner: so nobody takes them
  for a bug or an obstacle): a warm glow and little stars twinkling round
  them, a slight bob, in both games. Buried in the ways through (always reachable); grabbed, it
  pops with a little "+10" floating up and 10 m are added to the score (the
  owner's choice: 1, bonus depth). They're the only things to grab, drawn as
  Talpy's cookies (`drawCookie`, its flavours).

### Fair and getting harder

- What comes, comes in **rows** from below. Each row leaves at least one
  gap at least about 1.6 of his body's widths, and the gap he can reach
  from the last one in the time the ground takes to bring the row up, at his
  top speed with a margin. New kinds come in by depth, as above.
- Speeds up a little every 100 m, up to twice the start (as the Run); rows
  come closer with it, never closer than the reach rule allows.
- Hit boxes a little inside the drawings (forgiving), his too.
- The first 2 s: the hint ("Move the mouse to steer"; with keys: "← → to
  steer"), nothing buried in that time.

### The score and the end (shared with the Run)

- Metres dug (from the speed, as the Run counts) plus 10 m a cookie; shown
  small top right while digging, one right-aligned figure.
- The first touch ends it: the world stops, Talpa looks dizzy, "212 m · best
  340 m" or "New best! 340 m"; a click (or Space) digs again (not in the
  first 450 ms, as the Run); with none in 5 s his stage is back to your
  chats. Esc, a click outside the stage, the stage out of sight or a chat
  that needs you end it at once; what he dug still counts for the best.
- **The best:** its own, apart from the Run's: Plasma `digBest` (a
  `main.xml` entry, shared by every widget, the larger value winning), VS
  Code memento `talpyDen.digBest`. Only shown at the end.

### Starting it

- **"Dig with Talpy"** in Plasma's menu and VS Code's view ⋯ menu (command
  `talpyDen.digWithTalpy`), next to Peekaboo and the Run; four quick clicks
  may pick it too.
- Offered where the Run is: not in a widget on the desktop, not with less
  motion (Plasma's animation speed Instant, VS Code's reduced motion).

### The Run gets what Deep Dig brings (the owner, 2026-11-19: "if also the run can be nicer based on the findings of this game, like physics and cookies")

- **Cookies:** now and then a cookie on his way, worth 10 m with the same
  "+10" floating up (one score, as Deep Dig). Some sit on the ground in a gap
  between two things (run through it); some float over a ground thing at the
  top of his jump (a well-timed jump over it grabs it). Never one that lures
  him into a bump: only in a gap, or on the arc of a jump that clears.
- **Physics:**
  - Bumped in the air, he falls with the same gravity his jump has
    (speeding up as he falls), not at a constant speed.
  - He stretches a little as he takes off and squashes as he lands, quickly
    eased back (Talpy's own squash and stretch).
  - A small puff of dust where he lands.
  - His steps keep pace with the ground: the faster it goes, the quicker
    his feet, so they never slide over it.

### What becomes shared with the Run (approach 1)

- In `games.mjs`: the slots (`freeSlot`), the end and its waits
  (`RUN_END_MS`, `RUN_AGAIN_MS`), the best handling, the whole-frame time
  step, the stage-grow request with its height, as one small shared base the
  Run and Dig both use. The Run's behaviour stays as it is (its tests pass
  unchanged, but for names that move).
- In the hosts: "a scored game is on" in place of "a run is on" for the
  stage growing (by the game's height), the status fading, the things
  layer (slots and pictures), the words (distance, hint, end) and the
  press/keys overlay, which hands the game what it takes: the Run press and
  release (jump, dig), Deep Dig the aim (pointer x, ←/→ held).
- Talpy's offset and turn from the game (`lift` today; a turn in degrees
  added for the dig).

## Constraints

- Plain ES2017 in `talpy/` (it runs in Qt's JS engine and in the webview).
- English words through i18n in Plasma.
- Light: 60 fps while on, nothing while off; no per-frame stage-sized canvas;
  measured with the offscreen Plasma benchmark the Run used (before/after,
  interleaved runs).
- Fits a narrow popup (380 px): the gap rule and the speeds are by his body's
  size and the stage's width.
- The build is done without helper agents (the owner's wish), step by step.

## Decided by the owner

- Deep Dig, a high-score game (approach 1: a third game sharing the Run's
  machinery).
- A taller stage (B, about 16 grid units).
- A cookie is worth 10 m of score (one number).
- The playthrough as played back on 2026-11-19 (steering with mouse, keys or
  a drag at a top speed; layers by depth with their things; beetles from 300
  m; decoration never in the way; fair rows; the Run's end and best rules).
- Physics that look right and a nice design are the bar.
- The Run gets cookies and the physics too.
- Built without agents.

## Calls I made (the owner may change them)

- (Head-down was my call; the owner turned it down after the gallery: upright, paws scooping.)
- The spring-and-limits movement model; lean up to about 20°.
- The tunnel as a darker band along his path.
- Rows from below; the gap rule's numbers (1.6 body widths, the reach with a
  margin).
- Beetles only in rows of their own.
- The hint words; Space also digs again on the end screen.
- The Run's cookies: on the ground in gaps, or over a ground thing at his
  jump's top; its physics: gravity for the fall, squash and stretch, a dust
  puff, steps in pace with the ground.
- A gallery page (like `vscode/dev/things.html`) with every buried thing,
  the layers and Talpa head-down, approved by the owner before the hosts are
  built.

## Left to the builder

- The numbers: start speed, speed-up, row spacing, spring stiffness, top
  speed and acceleration, lean factor, hit-box margins (tuned by playing; the
  rules above are fixed).
- The drawings, within Talpy's lines and colours and the anti-goal on things
  that hurt vs cookies.
- How the shared base is cut inside `games.mjs` and the hosts, as long as the
  Run keeps playing as it does.
- How the soil colour is shown (a stage background colour per host is
  enough).
