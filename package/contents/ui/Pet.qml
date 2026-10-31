import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "talpy/talpy.mjs" as T
import "talpy/cookie.mjs" as C
import "talpy/games.mjs" as G

// One Talpy on the pet strip (PetStrip.qml). The creature itself (looks,
// moods, what it does) is talpy/talpy.mjs, drawn by TalpyView.qml; this is
// where it lives on the stage and what it does with you.
//
// The lone Talpy (petKey "") mirrors all your sessions and has a life of its
// own: it digs over to wherever your mouse is, has hobbies, naps and reacts to
// you. Click to pet it (many quick clicks tickle), double-click to make it
// dance, drag it out of its burrow (it hangs on to the rim for a moment, then
// pops out into your hand) and drop it. Double-click its stage a little away
// from it and there's a cookie (talpy/cookie.mjs), now and then of another
// flavour: it sees it, runs after it as you drag it about (let go and it
// falls: pick it up again), and eats it.
//
// A chat's pet stands for one chat in the sessions list: it acts that chat out
// (works, calls you, rests while it's idle, sleeps once it's done, looks sad if
// it failed), wears its name and a calm version of its color, pops up out of
// the ground when the chat shows up and digs away when it leaves the list, and
// opens the chat when clicked (drag it for fun: it digs back to its spot).
Item {
    id: pet

    required property Item strip
    property string petKey: ""          // the chat's key ("" for the lone Talpy)
    readonly property bool lone: petKey === ""
    property var chat: null             // the chat's session row, null once it's done
    property var lastChat: null         // the last one seen (opened when clicked)
    property string host: ""            // SSH host of the chat, if any
    property string label: ""           // short name on its tag
    property color tint: "transparent"  // the chat's color
    property real homeX: strip.width / 2
    property bool leaving: false
    property bool isMain: false         // shows the account-wide things (usage limits)
    signal gone()

    onChatChanged: if (chat) lastChat = chat

    // Talpy's moods: idle working agents needs done failed limit (error loading for the lone one)
    readonly property string mood: lone ? root.petMood
                                 : !chat ? "idle"
                                 : chat.state === "waiting" ? "needs"
                                 : chat.state === "working" ? (chat.agents && chat.agents.running > 0 ? "agents" : "working")
                                 : chat.stopped && !chat.stopped.over ? "limit"   // a usage limit (or the login) stopped it
                                 : chat.state === "idle" ? "idle"                // ready for your next message
                                 : chat.reason === "failed" ? "failed"
                                 : "done"                                        // done: results to look at

    readonly property real gu: strip.gu
    readonly property real box: strip.boxSize
    readonly property real unit: box / 64
    readonly property real bodyWidth: strip.bodyWidth
    readonly property real bodyHeight: strip.bodyHeight
    readonly property real ground: lone ? strip.loneGround : strip.chatGround
    // Where it can be: anywhere on the stage, its burrow (wider than its body)
    // staying on it; the lone Talpy walks over the headline
    readonly property real reach: box * 27 / 64 + Kirigami.Units.smallSpacing
    readonly property real minX: reach
    readonly property real maxX: Math.max(minX, strip.width - reach)
    readonly property bool live: strip.live
    readonly property bool playing: strip.playing   // not under a window: it moves

    // Where it is: px = horizontal centre, lift = how high you hold it (its
    // spot moves it by digging over there: no binding to homeX)
    property real px: 0
    Component.onCompleted: px = homeX
    property real lift: 0
    // Where it's drawn: there, but while you hold it it trails your hand on a
    // spring and swings with how fast you move it (and wobbles back after)
    property real shownX: px
    Behavior on shownX {
        enabled: pet.held && !root.lessMotion
        SpringAnimation { spring: 5; damping: 0.32; epsilon: 0.2 }
    }
    readonly property real swing: held ? Math.max(-30, Math.min(30, (px - shownX) * 1.8 / unit)) : 0
    // (on a spring: put down, it wobbles back upright on the ground, and stands
    // upright once talpy.land() opens its burrow, 700 ms or more after it
    // lands, so the burrow never swings; what's left of the wobble then is
    // under a degree)
    property real tilt: root.lessMotion ? 0 : swing
    Behavior on tilt {
        enabled: !root.lessMotion
        SpringAnimation { spring: 3; damping: 0.16; epsilon: 0.3 }
    }
    property bool upright: false
    Connections {
        target: root
        enabled: pet.landing && !pet.held && !pet.upright
        function onPetFrame(now) {
            if (pet.talpy && pet.talpy.holeOpen)
                pet.upright = true
        }
    }
    property bool held: false
    property bool tugging: false        // you pull at it in its burrow: it hangs on (talpy.tug), then pops out
    property bool pushing: false        // you push it down into its burrow (talpy.push): it sinks with your hand
    // A game with the big Talpy (talpy/games.mjs): four quick clicks on him, or
    // Play with Talpy in the menu; ticked and its holes drawn only while it's on
    property var playGame: null
    property bool gameOn: false
    property var gameHoles: []          // [{x, open}]: a copy of the game's, for the holes drawn
    property real pop: 1                // popping out into your hand: 0 in its burrow, 1 where you hold it
    property bool landing: false        // picked up, until it has landed and dug in: drawn live
    property bool arriving: false
    property bool departed: false   // dug away: only waiting to be removed
    property real travelTo: -1      // where the next dig takes it (-1: it picks)
    property int quickClicks: 0
    property int sleepyClicks: 0
    property string lastMood: ""
    property var missed: null       // {kind, text, at}: what happened while it couldn't be seen
    property real actedOutAt: 0     // when it last acted that out
    // The lone Talpy's cookie game (talpy/cookie.mjs): ticked only while a
    // cookie is out or it eats one (cookieOn); chasing: it runs after it,
    // drawn live
    property var game: null
    property bool cookieOn: false
    property bool hadCookie: false      // you gave it one since the widget started (its hint stops)
    property bool chasing: false
    readonly property var talpy: view.talpy

    anchors.fill: parent

    function clampX(x) {
        return Math.max(minX, Math.min(maxX, x))
    }

    function react(name, done) {
        if (talpy)
            talpy.react(name, done || null)
    }

    // Digs over to x (it dives in, tunnels across, pops up there); quick: its
    // spot moved (a new chat makes room), so it hurries
    function digTo(x, quick) {
        if (held || tugging || pushing || leaving || arriving || !talpy)
            return
        travelTo = clampX(x)
        if (Math.abs(travelTo - px) < bodyWidth * 0.3) {
            travelTo = -1
            return
        }
        if (root.lessMotion) {
            px = travelTo   // (less motion: no digging, it's just there)
            travelTo = -1
            return
        }
        react(quick ? "scoot" : "dig")
    }

    function say(text) {
        strip.say(pet, text)
    }

    // Seasons (northern hemisphere, by month) and a few days of the year
    function holidayGreeting() {
        const d = new Date(), m = d.getMonth() + 1, day = d.getDate()
        if ((m === 12 && day === 31) || (m === 1 && day === 1))
            return i18n("Happy New Year!")
        if (m === 12 && day >= 24 && day <= 26)
            return i18n("Merry Christmas!")
        if (m === 10 && day === 31)
            return i18n("Boo! Happy Halloween!")
        if (m === 2 && day === 14)
            return i18n("Happy Valentine's Day!")
        return ""
    }

    function start() {
        talpy.setMood(mood)
        lastMood = mood
        if (lone)
            makeGame()
        if (lone && !strip.firstShown)
            return            // the first time the popup opens it's just there
        arriving = true       // a new chat: it digs up out of the ground
        react("arrive", () => { pet.arriving = false })
    }

    onMoodChanged: {
        if (!talpy)
            return
        talpy.setMood(mood)
        if (gameOn && mood === "needs") {
            stopGame()        // a chat needs you: it's over, and he says so
            react("sign")
        } else if (lastMood === "done" && mood !== "done" && !leaving)
            react("yawn")     // woken up by work
        lastMood = mood
    }
    onHomeXChanged: {
        if (held || leaving)
            return       // in your hand (put down, it digs back), or on its way out
        if (!strip.firstShown || arriving)
            px = homeX   // not seen yet, or still underground: it's just there
        else if (!lone)
            digTo(homeX, true)   // (the big Talpy stays where he wandered to, as in VS Code and GNOME)
    }
    // The strip got narrower: back inside it
    onMaxXChanged: if (!held && px > maxX) digTo(maxX, true)
    onLeavingChanged: {
        if (leaving && !held && !tugging && !pushing)
            goAway()
        else if (!leaving && !held && !tugging && !pushing) {
            departed = false   // its chat came back (also while it dug away): it pops up again
            arriving = true
            react("arrive", () => { pet.arriving = false })
        }
    }
    onLiveChanged: {
        if (!live || !lone || !talpy || cookieOn || gameOn || mood === "done" || mood === "loading" || fresh(missed) || Date.now() - actedOutAt < 1000
                || !root.playful)
            return   // (what it missed meanwhile comes instead, see onPlayingChanged)
        const holiday = holidayGreeting()
        if (holiday) {
            react("celebrate")
            say(holiday)
        } else if (Math.random() < 0.6) {
            react("wave")
            say(i18n("Hi!"))
        }
    }

    // Seen again: it acts out what happened meanwhile, if it's from the last
    // minute (older news is dropped)
    onPlayingChanged: {
        if (!playing)
            stopGame()
        else if (lone && root.playWanted) {
            root.playWanted = false
            wantsToPlay(true)
        }
        if (!playing || !missed)
            return
        const m = missed
        missed = null
        if (fresh(m)) {
            actedOutAt = Date.now()
            event(m.kind, m.text)
        }
    }
    function fresh(m) {
        return m !== null && Date.now() - m.at < 60000
    }

    // (Removed once its frame is over: the leave ends in Talpy's tick, inside
    // its view's frame, and removing it there destroyed the view under it:
    // "attempted to evaluate a function in an invalid context")
    function goAway() {
        react("leave", ok => {
            if (ok && pet.leaving) {
                pet.departed = true
                Qt.callLater(pet.gone)
            }
        })
    }

    // Clicked: the lone Talpy gets petted, a chat's pet opens its chat
    function clicked() {
        if (lone) {
            if (gameOn && playGame.hit())
                return
            petIt()
            return
        }
        const c = lastChat
        if (!c)
            return
        if (host)
            root.remoteShow(host, c)
        else
            root.jumpTo(c.sessionId, c.profileDir)
    }

    function petIt() {
        if (cookieOn) {
            say(i18n("Cookie first!"))
            return
        }
        if (mood === "done") {
            sleepyClicks += 1
            tickleTimer.restart()
            if (sleepyClicks >= 3) {
                sleepyClicks = 0
                react("angry")
                say(i18n("I said let me SLEEP!"))
            } else {
                react("grumpy")
                say(i18n("Zzz… let me sleep."))
            }
            return
        }
        quickClicks += 1
        tickleTimer.restart()
        if (quickClicks >= 4) {
            quickClicks = 0
            if (!wantsToPlay()) {
                react("laugh")
                say(i18n("Hehe, that tickles!"))
            }
        } else if (quickClicks === 3) {
            react("shy")
            say(i18n("Aww, stop it…"))
        } else {
            const r = Math.random()
            react(r < 0.2 ? "love" : r < 0.35 ? "wink" : r < 0.45 ? "blowkiss" : "pet")
            say(petLine())
        }
    }

    // ------------------------------------------------------------ a game

    // Four quick clicks (or Play with Talpy, fromMenu): he laughs, says
    // "Let's play!" and a game starts; false: not now (Playful Talpy off, a
    // cookie out, held…), the clicks only tickle. While a chat needs you he
    // points at it instead; asleep, the menu wakes him (clicks only make him
    // grumpy: petIt)
    function wantsToPlay(fromMenu) {
        if (!lone || !root.playful || !talpy || gameOn || cookieOn || held || tugging || pushing || leaving)
            return false
        if (mood === "needs") {
            react("sign")
            say(petLine())
            return true
        }
        if (mood === "done" && !fromMenu)
            return false
        // (on at once, his laugh its first move: the clicks after this one are the game's)
        say(i18n("Let's play!"))
        startGame(mood === "done")
        return true
    }

    function startGame(wake) {
        if (gameOn || !playing || mood === "needs" || !root.playful || cookieOn || held || tugging || pushing)
            return
        stride.stop()
        travelTo = -1
        playGame = G.pickGame(talpy, {
            stage: () => ({ width: strip.width, ground: pet.ground, unit: pet.unit, bodyWidth: pet.bodyWidth,
                            bodyHeight: pet.bodyHeight, minX: pet.minX, maxX: pet.maxX }),
            px: () => pet.px,
            moveTo: x => { pet.px = x },
            say: what => pet.say(what === "got" ? [i18n("You got me!"), i18n("Hehe, found me!"), i18n("Again!")][Math.floor(Math.random() * 3)]
                                                : i18n("That was fun!")),
            changed: () => pet.gameMoved()
        })
        playGame.start(talpy.now, !!wake)
    }

    // Over at once: Esc, a click outside the stage, a chat that needs you, the stage out of sight
    function stopGame() {
        if (gameOn)
            playGame.stop()
    }

    function gameMoved() {
        gameOn = playGame.on
        gameHoles = playGame.holes.map(h => ({ x: h.x, open: h.open }))
        root.gameStage = gameOn ? strip : null
    }

    Connections {
        target: root
        enabled: pet.gameOn && pet.playing
        function onPetFrame(now) {
            pet.playGame.tick(now)
        }
    }
    // (Play with Talpy, from the menu: once the stage shows; Esc and clicks outside it: over)
    Connections {
        target: root
        enabled: pet.lone
        function onPlayWantedChanged() {
            if (root.playWanted && pet.playing) {
                root.playWanted = false
                pet.wantsToPlay(true)
            }
        }
        function onGameStopWantedChanged() {
            if (root.gameStopWanted) {
                root.gameStopWanted = false
                pet.stopGame()
            }
        }
        function onPlayfulChanged() {
            if (!root.playful)
                pet.stopGame()
        }
    }
    Shortcut {
        sequences: [StandardKey.Cancel]
        enabled: pet.gameOn
        onActivated: pet.stopGame()
    }

    function dance() {
        if (gameOn)
            return   // (the game's: its clicks are)
        if (cookieOn) {
            say(i18n("Cookie first!"))
            return
        }
        if (mood === "done") {
            react("yawn")
            say(i18n("…five more minutes."))
            return
        }
        react(Math.random() < 0.4 ? "boogie" : "dance")
        say("♪ ♫")
    }

    // You start to drag it: in its burrow it hangs on to the rim for a moment
    // (talpy.tug), stretching, then pops out into your hand; let go before
    // that and it drops back in. Out of its burrow (or with less motion) it's
    // yours at once.
    function pull() {
        stopGame()
        if (!root.lessMotion && talpy && talpy.tug(ok => { if (ok && pet.tugging) pet.popOut() })) {
            tugging = true
            tugToward(grab.lastAt)
            stride.stop()
            if (game)
                game.picked()   // (it stops seeing to its cookie meanwhile)
            say(i18n("Hnngh!"))
            return
        }
        pickUp()
        holdAt(grab.lastAt)
    }

    // A drag that starts downward (within 45° of straight down) while it's in
    // its burrow pushes it in (talpy.push): it squashes and sinks as far as
    // your hand goes, with a dirt puff; with less motion it's down at once.
    // False: it isn't in its burrow, and the drag picks it up as before.
    function push() {
        stopGame()
        if (!talpy || !talpy.push())
            return false
        pushing = true
        stride.stop()
        if (game)
            game.picked()   // (it stops seeing to its cookie meanwhile)
        if (root.lessMotion)
            talpy.pushTo(64)
        return true
    }

    // (as far down as your hand, p, went since the drag began)
    function pushToward(p) {
        if (talpy && !root.lessMotion)
            talpy.pushTo((p.y - grab.pressedAt.y) / unit)
    }

    // Let go: it stays down a moment, then peeks out (hey!, or a giggle) and is
    // back to its mood; a chat that needs you: it pops straight up with its sign
    function pushed() {
        pushing = false
        if (!talpy)
            return
        talpy.pushed(mood === "needs", ok => {
            if (!ok)
                return
            if (pet.leaving)
                pet.goAway()      // its chat left meanwhile: now it goes
            else if (pet.mood === "needs")
                pet.react("sign")
            else if (pet.game)
                pet.game.landed()
        })
    }

    // (it leans towards your hand, p, as it hangs on)
    function tugToward(p) {
        if (talpy)
            talpy.tugToward((p.x - px) / unit, (p.y - (ground - bodyHeight * 0.6)) / unit)
    }

    function popOut() {
        tugging = false
        pickUp()
        holdAt(grab.lastAt)
        popping.restart()   // (from its burrow up to your hand)
    }

    // Let go of while it hung on: back down it drops, phew
    function letGo() {
        tugging = false
        if (talpy)
            talpy.letGo(ok => {
                if (!ok)
                    return
                if (pet.leaving)
                    pet.goAway()   // its chat left meanwhile: now it goes
                else if (pet.game)
                    pet.game.landed()
            })
        say(i18n("Phew!"))
    }

    function pickUp() {
        held = true
        upright = false
        landing = true
        fall.stop()   // grabbed again while falling
        stride.stop()
        if (talpy) {
            // (its hole doesn't come along: it stays where it was, until it has landed)
            const open = talpy.setHeld(true)
            if (open > 0)
                leaveHole(open)
        }
        if (game)
            game.picked()   // (put down, it goes after its cookie again)
        say(i18n("Whoa!"))
    }

    // Where you hold it: under your hand (p, in its coordinates)
    function holdAt(p) {
        px = clampX(p.x)
        lift = Math.max(0, Math.min(ground - bodyHeight, ground - p.y - bodyHeight / 2))
    }

    function leaveHole(open) {
        closeHole.stop()
        leftHole.at = px
        leftHole.flip = view.facingLeft
        leftHole.open = open
        leftHole.shown = true
    }

    function drop() {
        if (popping.running) {
            popping.stop()   // (it falls from where it's drawn)
            lift = lift * pop
            pop = 1
        }
        fall.duration = Math.max(160, Math.sqrt(lift / gu) * 230)
        fall.restart()
    }

    // On the floor again: dizzy if it fell from high up, then it digs in where it landed
    function landed(fromHeight) {
        held = false
        if (leftHole.shown)
            closeHole.restart()   // (the one it left is filled in; it digs a new one where it is)
        if (!talpy) {
            landing = false
            return
        }
        // (a cookie out: it stays out of its burrow and goes after it)
        const feel = talpy.land(fromHeight / unit, () => {
            if (pet.held)
                return   // picked up again before it was done (pickUp): nothing of landing happens in your hand
            pet.landing = false
            if (pet.game)
                pet.game.landed()
            if (pet.leaving)
                pet.goAway()      // its chat left while you held it: now it goes
            else if (!pet.lone && Math.abs(pet.px - pet.homeX) > pet.bodyWidth * 0.5)
                pet.digTo(pet.homeX)
        }, game !== null && game.cookie !== null)
        // (in the words for how it looks)
        if (feel === "sick")
            say(i18n("Ugh… I don't feel so good."))
        else if (feel === "dizzy")
            say(i18n("Ouch… the room is spinning."))
    }

    function petLine() {
        if (mood === "needs")
            return i18n("%1 needs you!", root.waitingName)
        if (mood === "agents")
            return i18np("Juggling %1 agent!", "Juggling %1 agents!", root.agentsRunning)
        if (mood === "working")
            return i18n("Busy coding… thanks!")
        if (!root.playful)
            return ""   // (no jokes: only what the chats do)
        if (lone && !hadCookie && Math.random() < 0.25)
            return i18n("Psst… double-click my stage for a cookie!")
        const lines = [i18n("Hi!"), "♥", i18n("Ship it!"), i18n("All quiet here."), i18n("Pet me more!")]
        return lines[Math.floor(Math.random() * lines.length)]
    }

    // Something happened to its chat (or, for the main pet, to an account)
    function event(kind, text) {
        if (held || tugging || pushing || leaving)
            return   // (a reaction now would stop it digging away)
        if (!playing || cookieOn || gameOn) {
            missed = { kind: kind, text: text, at: Date.now() }   // (acted out when it can be seen, has its cookie, or the game's over)
            return
        }
        const action = { done: Math.random() < 0.4 ? "yay" : "finished", failed: "failed", stopped: "shrug", limit: "battery", oops: "confused", reset: "charged" }[kind]
        react(action || "alert")
        say(text)
    }

    // ------------------------------------------------------------ a cookie

    function makeGame() {
        game = new C.CookieGame(talpy, {
            stage: () => ({ width: strip.width, ground: pet.ground, unit: pet.unit, bodyWidth: pet.bodyWidth,
                            bodyHeight: pet.bodyHeight, minX: pet.minX, maxX: pet.maxX }),
            px: () => pet.px,
            moveTo: x => {
                stride.stop()   // (it was digging somewhere else)
                pet.travelTo = -1
                pet.px = x
            },
            face: left => { view.facingLeft = left },
            say: (what, flavour) => pet.say(pet.cookieWords(what, flavour)),
            leaveHole: open => pet.leaveHole(open),
            fillHole: () => { if (leftHole.shown) closeHole.restart() },
            changed: () => pet.cookieChanged(),
            instant: () => root.lessMotion   // (no running about: he just has it)
        })
    }

    // A double-click on the stage at (x, y): false if it's too close to it
    function placeCookie(x, y) {
        if (!root.playful || gameOn || game === null || !playing || !game.place(x, y))
            return false
        hadCookie = true
        return true
    }

    function cookieChanged() {
        cookieOn = game.on
        chasing = game.chasing
        const c = game.cookie
        cookie.shown = c !== null
        if (!c)
            return
        cookie.r = c.r
        cookie.flavour = c.flavour
        cookie.cx = c.x
        cookie.cy = c.y
        cookie.pop = c.scale
        cookie.angle = c.angle
        cookie.sx = c.sx
        cookie.sy = c.sy
    }

    // The game's over: what happened meanwhile
    onGameOnChanged: {
        if (gameOn || !playing || !missed)
            return
        const m = missed
        missed = null
        if (fresh(m))
            event(m.kind, m.text)
    }

    // Done with its cookie: what happened meanwhile
    onCookieOnChanged: {
        if (cookieOn || !playing || !missed)
            return
        const m = missed
        missed = null
        if (fresh(m))
            event(m.kind, m.text)
    }

    // (flavour: the cookie's, see FLAVOURS in talpy/actions.mjs)
    function cookieWords(what, flavour) {
        const any = list => list[Math.floor(Math.random() * list.length)]
        switch (what) {
        case "spot":
            switch (flavour) {
            case "double": return i18n("Double chocolate?!")
            case "sprinkles": return i18n("Sprinkles!!")
            case "ginger": return i18n("Ooh, ginger!")
            case "mint": return i18n("Mint?!")
            case "jam": return i18n("Is that jam?!")
            case "oat": return i18n("Oatmeal… raisin?")
            case "white": return i18n("White chocolate?!")
            }
            return any([i18n("A cookie?!"), i18n("Is that for me?"), i18n("Cookie!!")])
        case "wake": return i18n("Did someone say cookie?")
        case "gimme": return i18n("Gimme!")
        case "cross": return i18n("Hey! No fair!")
        case "aww": return i18n("Aww, so close!")
        case "yum":
            switch (flavour) {
            case "double": return i18n("So chocolatey! ♥")
            case "sprinkles": return i18n("Sprinkles! ♪")
            case "ginger": return i18n("Spicy!")
            case "mint": return i18n("So fresh!")
            case "jam": return i18n("Mmm, jam!")
            case "oat": return i18n("…raisins. Still yum!")
            case "white": return i18n("Fancy!")
            }
            return any([i18n("Yum!"), i18n("Mmm, cookie!"), i18n("Thank you!")])
        }
        return ""
    }

    Connections {
        target: root
        enabled: pet.cookieOn && pet.playing && pet.game !== null
        function onPetFrame(now) {
            pet.game.tick(now)
        }
    }

    // ------------------------------------------------------------ timers

    Timer {
        id: tickleTimer
        interval: 1500
        onTriggered: {
            pet.quickClicks = 0
            pet.sleepyClicks = 0
        }
    }

    // The lone Talpy turns towards the mouse while it hovers the stage
    Timer {
        interval: 350
        repeat: true
        running: pet.playing && pet.lone && pet.strip.cursorX >= 0 && !pet.held && !pet.cookieOn && pet.mood !== "done"
        onTriggered: {
            if (Math.abs(pet.strip.cursorX - pet.px) > pet.bodyWidth * 0.4)
                view.facingLeft = pet.strip.cursorX < pet.px
        }
    }

    // A working session's context window is nearly full: point it out now and
    // then (a chat's pet for its own chat, the hero for chats without a pet)
    readonly property string contextFullText: !lone ? (chat && chat.state === "working" && chat.context !== null && chat.context >= 85
                                                       ? i18n("%1: context %2% full", label, Math.round(chat.context)) : "")
                                                    : root.contextFullText
    Timer {
        interval: 40000
        repeat: true
        running: pet.playing && pet.contextFullText !== "" && (pet.mood === "working" || pet.mood === "agents") && !pet.leaving && !pet.cookieOn
        triggeredOnStart: true
        onTriggered: {
            if (!pet.held && pet.talpy && !pet.talpy.run) {
                pet.react("contextFull")
                pet.say(pet.contextFullText)
            }
        }
    }

    // Close to a usage limit: mind-blown now and then; at the limit out of steam
    Timer {
        interval: 25000
        repeat: true
        running: pet.playing && pet.isMain && root.highUsageText !== "" && pet.mood !== "done" && !pet.leaving && !pet.cookieOn
        triggeredOnStart: true
        onTriggered: {
            if (pet.held || !pet.talpy || pet.talpy.run)
                return
            pet.react(root.maxFiveHour >= 100 ? "battery" : "mindblown")
            pet.say(root.highUsageText)
        }
    }

    // ------------------------------------------------------------ motion

    // Tunnelling across while it digs to a new spot
    NumberAnimation {
        id: stride
        target: pet
        property: "px"
        easing.type: Easing.InOutSine
    }

    NumberAnimation {
        id: fall
        target: pet
        property: "lift"
        to: 0
        easing.type: Easing.InQuad
        property real fromHeight: 0
        onStarted: fromHeight = pet.lift
        onFinished: pet.landed(fromHeight)
    }

    // Out of its burrow up to your hand, with a little overshoot
    NumberAnimation {
        id: popping
        target: pet
        property: "pop"
        from: 0
        to: 1
        duration: 220
        easing.type: Easing.OutBack
    }

    // ------------------------------------------------------------ drawing

    // The hole it was pulled out of, empty where it was while you hold it
    // (under it, so it's drawn first)
    Canvas {
        id: leftHole
        property bool shown: false
        property real at: 0             // its horizontal centre
        property real open: 1           // 0 closed, 1 open
        property bool flip: false       // (the burrow isn't quite the same on both sides)
        visible: shown && !pet.departed
        width: view.width
        height: view.height
        x: at - view.boxX - pet.box / 2
        y: pet.ground - view.floorY
        renderStrategy: Canvas.Cooperative
        onOpenChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.translate(view.boxX, view.boxY)
            ctx.scale(pet.box / T.BOX, pet.box / T.BOX)
            if (flip) {
                ctx.translate(T.BOX, 0)
                ctx.scale(-1, 1)
            }
            T.drawHole(ctx, open)
        }
    }

    // A game's holes (talpy/games.mjs), under him: painted again only as they open or close
    Repeater {
        model: pet.gameOn ? 3 : 0
        delegate: Canvas {
            required property int index
            readonly property var hole: pet.gameHoles[index] || ({ x: 0, open: 0 })
            readonly property real open: hole.open
            visible: open > 0.01 && !pet.departed
            width: view.width
            height: view.height
            x: hole.x - view.boxX - pet.box / 2
            y: pet.ground - view.floorY
            renderStrategy: Canvas.Cooperative
            onOpenChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.translate(view.boxX, view.boxY)
                ctx.scale(pet.box / T.BOX, pet.box / T.BOX)
                T.drawHole(ctx, open)
            }
        }
    }

    NumberAnimation {
        id: closeHole
        target: leftHole
        property: "open"
        to: 0
        duration: 350
        onFinished: leftHole.shown = false
    }

    // The cookie's shadow on the floor (the cookie itself is over it all, see
    // the end)
    Rectangle {
        readonly property real over: Math.min(1, Math.max(0, pet.ground - cookie.cy - cookie.r) / (pet.box * 0.8))
        visible: cookie.visible
        width: cookie.r * 2 * (1 - 0.4 * over) * cookie.pop
        height: width * 0.24
        radius: height / 2
        x: cookie.cx - width / 2
        y: pet.ground - height / 2
        color: Qt.rgba(0.08, 0.1, 0.18, 0.2 * (1 - 0.6 * over))
    }

    TalpyView {
        id: view
        visible: !pet.departed   // (dug away: not even back up for the moment before it's removed)
        box: pet.box
        x: pet.shownX - boxX - pet.box / 2
        y: pet.ground - pet.lift * pet.pop - floorY
        transform: Rotation {
            origin.x: view.boxX + pet.box / 2
            origin.y: view.boxY + pet.box * 30 / 64   // (where you hold it)
            angle: pet.upright ? 0 : pet.tilt
        }
        playing: pet.playing
        travels: pet.lone && !root.lessMotion   // (no digging about with less motion)
        tint: pet.lone ? "transparent" : pet.tint
        // Both are films (TalpyView.qml), drawn live while you hold them and
        // until they've landed, and for a move too slow for a picture every
        // tick (it would step). The big Talpy: a picture every frame of the
        // clock, live until a new pose has settled, breathing at rest. A
        // chat's pet: smaller, so a picture every other tick (30 a second in
        // the popup, 15 on the desktop: even steps, each picture as long),
        // pictures in between poses, still at rest.
        live: pet.landing || pet.chasing || pet.tugging || pet.pushing
        sheets: pet.lone ? 36 : 32
        frameMs: pet.lone ? root.petFrameMs : 2 * root.petFrameMs
        maxFrames: 32
        tweenMs: pet.lone ? 0 : 200
        restMs: pet.lone ? 200 : 0
        smooth: true
        onReady: pet.start()
        onTravelStop: stride.stop()
        onTravel: ms => {
            let to = pet.travelTo
            pet.travelTo = -1
            if (to < 0) {
                // its own idea: towards the mouse if it hovers the stage, else anywhere
                const cursor = pet.strip.cursorX
                to = cursor >= 0 ? cursor + (Math.random() - 0.5) * pet.bodyWidth
                                 : pet.minX + Math.random() * (pet.maxX - pet.minX)
            }
            to = pet.clampX(to)
            view.facingLeft = to < pet.px
            stride.to = to
            stride.duration = Math.max(200, ms - 100)
            stride.restart()
        }
    }

    // Name tag under it, in the chat's color
    Rectangle {
        id: tag
        visible: !pet.lone && pet.label !== "" && !pet.departed
        readonly property bool darkTint: (pet.tint.r * 0.299 + pet.tint.g * 0.587 + pet.tint.b * 0.114) < 0.6
        width: Math.min(tagText.implicitWidth + Kirigami.Units.smallSpacing * 2, pet.strip.tagWidth)
        height: tagText.implicitHeight + 2
        radius: height / 2
        x: pet.px - width / 2   // follows it, also while it tunnels
        y: pet.ground + pet.unit * 6
        color: pet.tint

        PlasmaComponents3.Label {
            id: tagText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, pet.strip.tagWidth - Kirigami.Units.smallSpacing * 2)
            text: pet.label
            elide: Text.ElideRight
            font.pixelSize: Kirigami.Theme.smallFont.pixelSize * 0.95
            color: tag.darkTint ? "white" : "black"
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: pet.clicked()
        }
    }

    // ------------------------------------------------------------ input

    // Grab area around its body (in strip coordinates, so flipping doesn't move it)
    MouseArea {
        id: grab
        property point pressedAt
        property point lastAt           // where your hand is (pull, popOut)
        property bool dragging: false
        x: pet.px - width / 2
        y: pet.ground - pet.lift * pet.pop - height
        width: pet.bodyWidth + Kirigami.Units.largeSpacing
        height: pet.bodyHeight + Kirigami.Units.largeSpacing
        visible: !pet.departed
        cursorShape: pet.held || pet.tugging || pet.pushing ? Qt.ClosedHandCursor : pet.lone ? Qt.OpenHandCursor : Qt.PointingHandCursor
        preventStealing: true
        hoverEnabled: !pet.lone

        onPressed: mouse => {
            pressedAt = mapToItem(pet, mouse.x, mouse.y)
            dragging = false
        }
        onPositionChanged: mouse => {
            if (!pressed)
                return
            const p = mapToItem(pet, mouse.x, mouse.y)
            lastAt = p
            if (!dragging && Math.hypot(p.x - pressedAt.x, p.y - pressedAt.y) > pet.gu * 0.5) {
                dragging = true
                // (down, within 45° of straight down, while it's in its burrow: pushed in; else pulled out)
                if (!(p.y - pressedAt.y > 0 && Math.abs(p.x - pressedAt.x) <= p.y - pressedAt.y && pet.push()))
                    pet.pull()
                else
                    pet.pushToward(p)
            } else if (dragging && pet.pushing) {
                pet.pushToward(p)
            } else if (dragging && pet.held) {
                pet.holdAt(p)
            } else if (dragging && pet.tugging) {
                pet.tugToward(p)
            }
        }
        onReleased: {
            if (dragging && pet.pushing)
                pet.pushed()
            else if (dragging && pet.tugging)
                pet.letGo()
            else if (dragging)
                pet.drop()
        }
        // (a press that ends without a release: the popup closed or the stage folded away under the mouse)
        onCanceled: {
            if (dragging && pet.pushing)
                pet.pushed()
            else if (dragging && pet.tugging)
                pet.letGo()
            else if (dragging && pet.held)
                pet.drop()
        }
        onClicked: {
            if (!dragging)
                pet.clicked()
        }
        onDoubleClicked: {
            if (!dragging && pet.lone)
                pet.dance()
        }

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            active: !pet.lone && !pet.held && pet.lastChat !== null
            mainText: pet.lastChat ? (pet.host ? pet.host + ": " : "") + pet.lastChat.name : ""
            subText: pet.lastChat ? root.stateText(pet.lastChat) + "\n" + i18n("Click to open this chat") : ""
        }
    }

    // The cookie you gave it (talpy/cookie.mjs): painted once and moved
    // about, over Talpy (it shows whole as Talpy gets there) and over its
    // grab area: press it, wherever it is, and it comes along
    Canvas {
        id: cookie
        property bool shown: false
        property real r: pet.unit * 7
        property string flavour: ""
        property real cx: 0
        property real cy: 0
        property real pop: 0
        property real angle: 0
        property real sx: 1
        property real sy: 1
        visible: shown && !pet.departed
        width: Math.ceil(r * 2 + 4)
        height: width
        x: cx - width / 2
        y: cy - height / 2
        scale: pop
        rotation: angle
        // (squashed as it lands, its bottom on the floor: after scale and rotation)
        transform: Scale { origin.x: cookie.width / 2; origin.y: cookie.height / 2 + cookie.r * cookie.pop; xScale: cookie.sx; yScale: cookie.sy }
        renderStrategy: Canvas.Cooperative
        onWidthChanged: requestPaint()
        onFlavourChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.translate(width / 2, height / 2)
            ctx.scale(r / 5.6, r / 5.6)
            T.drawCookie(ctx, flavour)
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            preventStealing: true
            onPressed: mouse => {
                const p = mapToItem(pet, mouse.x, mouse.y)
                if (!pet.game.grab(p.x, p.y))
                    mouse.accepted = false
            }
            onPositionChanged: mouse => {
                const p = mapToItem(pet, mouse.x, mouse.y)
                pet.game.drag(p.x, p.y)
            }
            onReleased: pet.game.drop()
            onCanceled: pet.game.drop()
        }
    }
}
