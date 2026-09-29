# CHEERIVY — Game Flow & Design Guideline

> **"For three minutes, a lab table becomes a stadium — and you are the star."**

This is the reference for the redesign: how the game should feel, what happens in which order,
who controls what, and what has to be built. When in doubt, ask:
*"Does this make the player feel more like they are in a stadium final?"* If not, cut it.

---

## 1. Feelings we design for

| Moment | The player should feel | How |
|---|---|---|
| Walking past | Curiosity | Home screen is alive: crowd murmur, best goals replaying, "PRESS ⬤" pulsing |
| Starting a match | *"Oh, this is serious."* | Cinematic intro: crowd swells, commentator introduces the battle, 3-2-1, loud buzzer |
| Choosing | Confident, zero confusion | One question per screen, big choices, joystick + button only |
| Playing | In control, focused | Calm screen: board, clock, score, buzzer panel. Nothing else. |
| Goal | Explosion (joy or pain) | Crowd roar, commentator screams, scorer's colour flash, then a clear, calm restart |
| Buzzer race | Drama, reflexes | Random BUZZ!, first press freezes the other: "Player one hits the buzzer first!" … "And they're live again!" |
| Last 10 s | Panic | Red clock, heartbeat, countdown voice |
| Full time | Pride / "one more!" | Loud outro that grabs the room, then a real highlight story |
| After | Wanting a rematch | Highlights end → home, rematch is one button away |

### Design principles
1. **The ball is the hero, the screen is the stadium.** During play show only: board (AI view), clock, score, freeze status.
2. **Zero learning curve.** A stranger plays within 5 seconds. One joystick, one button. No text to read during play.
3. **Earn the big moments.** Loud only for kick-off, goals, freeze, golden goal, full time. Calm otherwise.
4. **Every input gets an answer within 100 ms** (sound + visual). Silence after a press feels broken.
5. **It's a TV broadcast, not an app.** Scoreboard bar, lower-thirds, replays, commentator. No windows, cursors, debug text.
6. **Two clear identities.** Player 1 = warm colour (red/orange). Player 2 / AI = cool colour (cyan/blue). AI has a cold, digital personality. Gold = victory / awards only. Same colours everywhere (screen, LCD text, carriage tape).
7. **Losing still feels good.** Everyone gets a moment in the highlights/awards.
8. **Readable from 3 metres.** Huge numbers, high contrast.
9. **Nobody gets rushed.** The game never restarts until the restarting player says so (button).
10. **The commentator is a guide, not a radio host.** Every line tells the players something:
    the **score**, the **game flow** (whose restart, what happens next), the **rules** (freeze, golden goal,
    pause), the **clock**, or **what just happened** (goal, save, freeze). **No random filler lines.**
    Silence is fine; the crowd carries the atmosphere.

---

## 2. Decisions (fixed)

| Topic | Decision |
|---|---|
| Modes | **PLAYER 1 vs AI**, **PLAYER 1 vs PLAYER 2**, and **AI vs AI** (demo: the camera AI drives both carriages; blue tape on player 1's carriage; firmware game 3, laptop key `b`) |
| Names | No typing. Fixed: **PLAYER ONE**, **PLAYER TWO**, **CHEERIVY AI** (recorded clips exist) |
| Match end | **Timer** (chosen before each match) + **golden goal** if level at time-up |
| Restart after goal / kick-off | **The restarting player presses their button** when the ball is placed → 3-2-1 → buzzer → GO |
| Menu control | **Both joysticks equal**: either moves the cursor, either button confirms |
| Pause | **Both players hold their buttons 3 s** → game pauses → pause menu (Resume / Restart / Home) |
| Freeze = **buzzer race** | At a **random moment** the buzzer beeps; the **first player to press** freezes the other for 3 s. Pressing without a buzzer does nothing. **VS MACHINE: the AI wins ~60 %** of races (it then presses in 0.12–0.3 s; otherwise it doesn't press, so any human press within 3 s wins) |
| Highlights | **Every goal, ~60–90 s total**, story commentary written from the goal's data, then **auto → Home** |
| Commentator's job | **Guide only:** score, game flow, rules, clock, what just happened. **No random fillers.** |
| Clock calls | **Half time** reminder · **"Only thirty seconds remaining"** · **"Only ten seconds remaining"** · then **5 · 4 · 3 · 2 · 1** |
| Settings | Sound · Gameplay · Servo tuning · Camera & AI |
| Gameplay view | **Only the AI view** (top-down board with prediction). The raw camera is not shown (still recorded for replays). |
| LCD 16×2 | Shows mode / score / clock / state (see §8). Wired as the old diagram: RS PB2, EN PB3, D4–D7 PB4–PB7 |

---

## 3. Screen / state map

```
BOOT ─► HOME ─┬─► MODE SELECT ─► (AI) DIFFICULTY ─► MATCH LENGTH ─► PRE-MATCH ─► LIVE ◄──┐
              │                  (2P) P2 JOIN ─────┘                                       │
              ├─► SETTINGS                                        GOAL ─► RESTART WAIT ────┘
              └─► (idle 60 s) ATTRACT                             PAUSE (both hold 3 s)
                                                                  TIME UP ─► (level) GOLDEN GOAL ─► LIVE
                                                                  FULL TIME ─► OUTRO ─► HIGHLIGHTS ─► HOME
```

### 3.1 HOME
- Big title, two options + settings: **VS MACHINE · 2 PLAYERS · SETTINGS**. Joystick left/right (or up/down), button = OK.
- Background: crowd murmur, slow replay of the best goal of the day, leaderboard strip.
- Idle 60 s → ATTRACT (a louder "PRESS ⬤ TO PLAY" loop). Any button → HOME.
- LCD: `CHEERIVY` / `Select mode <>`

### 3.2 MODE SELECT → setup
- **VS MACHINE:** choose **difficulty** (EASY / MEDIUM / HARD), then **match length**.
- **2 PLAYERS:** "PLAYER TWO, press ⬤ to join" → then **match length**.
- **Match length:** 1 · 2 · 3 · 5 min (default from Settings). Joystick picks, button confirms.
- Every screen has **BACK** as the last option (and holding down on a joystick = back).

### 3.3 PRE-MATCH (the cinematic intro) — robot is locked
1. Lights dim (screen darkens), crowd **swells** (volume ramps up over ~3 s).
2. Commentator intro for the mode (VS MACHINE / 2 PLAYERS lines).
3. **"We are about to witness a battle between PLAYER ONE and CHEERIVY AI!"**
   Then the rules, once: the clock (*"Three minutes on the clock. And if it's level at the end, a golden goal will settle it."*)
   and the **buzzer** (*"And listen for the buzzer! At any moment it will sound, and whoever hits their button first freezes
   their opponent for three seconds. Press too early, and nothing happens."*). All lines: `cheerivy_ai/ui/commentary.py`.
4. Kick-off instruction: **"Player one, you have the privilege to start. Place the ball just in front of your carriage, and push your joystick forward when you're ready."**
5. Player 1 pushes the joystick forward → **"Three… two… one…"** → **buzzer: loud beep-beep-beep-BEEEP** (robot buzzer + speaker) → **GO**, clock starts.
- LCD: `P1 vs AI  3:00` / `Get ready...` → `3` `2` `1` `GO!`

### 3.4 LIVE
- Screen: **left ~70%: AI view** (board, ball, predicted path, carriages). **Right panel:** clock (big), score card, buzzer panel (race state + who is frozen), mode + difficulty.
- Sound: crowd bed (ducked under commentary). The commentator only speaks when something happens that the
  players should know: a save, a freeze, the clock calls below, or a goal (§3.5). **No fillers.**
- **Clock calls:**
  - **Half time:** *"That's half the time gone. Player one leads, two–one."* (always with the score)
  - **30 s left:** *"Only thirty seconds remaining!"*
  - **10 s left:** *"Only ten seconds remaining!"*
  - **Last 5 s:** *"Five… four… three… two… one…"*, then the whistle
- **Buzzer race (freeze):** every 12–25 s of live play (setting: often / normal / rare) the buzzer beeps and **BUZZ!** fills the board for 3 s.
  The first button press wins: the other side's carriage/servo is locked 3 s. Commentary: *"Player one hits the buzzer first! The machine is frozen for three seconds!"* … *"And they're live again!"*
  Nobody pressed in 3 s: *"Nobody on the buzzer!"*. No buzzer in the last 4 s of the clock or while someone is frozen.
  First-timers react in ~0.5–1 s, so against the AI it is not a speed test: 60 % the AI takes it instantly, 40 % the AI doesn't press at all.
- Screen: clock turns amber at 30 s, red + heartbeat sound at 10 s, big numbers for 5-4-3-2-1.
- LCD: `P1  2 - 1  AI` / `2:15   LIVE`

### 3.5 GOAL (everything stops until the restart)
1. Laser (or camera) detects the goal → robot **locks both carriages and servos** and **stops the clock** instantly.
2. **Crowd roar + commentator scream** (goal call with the scorer's name), scorer's colour flashes, instant replay (short PIP).
3. **Score announcement with goal difference:** *"Two–one. Player one leads by one."* / *"Level! Two–two!"* / *"Three–nil. A three-goal cushion."*
4. **Restart instruction for the player who CONCEDED:** *"Player two, place the ball in front of your carriage, and push your joystick forward when ready."*
   - **VS MACHINE, the AI conceded:** *"Player one, please place the ball in front of the machine's carriage, and push your joystick forward when ready."* (Player 1 pushes forward for the AI.)
5. Joystick forward → 3-2-1 → buzzer → GO → clock resumes.
- No movement works and no time counts from the goal until GO.
- LCD: `GOAL! PLAYER 1` / `P1 2 - 1 AI` → `Place ball: P2` / `Push fwd`

### 3.6 PAUSE
- **Both players hold their buttons 3 s** (a progress ring on screen fills while holding; releasing early cancels, a short tap is just a normal press).
- Everything locks, clock stops, crowd murmurs quietly. Menu: **RESUME · RESTART MATCH · HOME** (joysticks, button).
- RESUME → the same "place ball / press button / 3-2-1" restart as after a goal (the player whose side the ball is on).
- LCD: `PAUSED` / `Resume  Home`

### 3.7 TIME UP → GOLDEN GOAL (only if level)
- Whistle, *"It's level! Golden goal. The next goal wins it all!"*, clock shows **GOLDEN GOAL** (no time limit, or a safety cap e.g. 2 min then draw).
- Kick-off like a normal restart.

### 3.8 FULL TIME → OUTRO
- Final whistle, **loud** crowd, result call (*"It is over! Player one beats the machine, three–one!"*).
- **Outro, loud and theatrical**, to grab the whole room's attention.
- Result card: score, winner (gold), 2–3 awards (Rocket = fastest shot, The Wall = most saves, Comeback, …).
- LCD: `FULL TIME` / `P1 3 - 1 AI`

### 3.9 HIGHLIGHTS (§6) → auto HOME
- Every goal, ~60–90 s total, then awards recap → **automatically back to HOME**.
- Any time: both hold 3 s → skip to HOME.

---

## 4. Input map (joysticks only)

| Input | Menus | Live | Pre-match / restart | Paused |
|---|---|---|---|---|
| Either joystick left/right/up/down | move cursor | move own carriage | — | move cursor |
| Either joystick push-up | — | fire own servo | **restarting player: ready → 3-2-1** | — |
| Tap own button | confirm | **buzzer race** (only while BUZZ! is on) | — (the button never means "ready") | confirm |
| Both hold buttons 3 s | — | **pause** | pause | — |
| Hold down on a joystick 1 s | back | — | — | back |

Keyboard (organisers only, hidden): F1 settings, F5 force restart, Esc home, debug keys as today.

---

### Board tilt
A thin 4 × 50 cm sheet under the board tilts it, so play is less predictable: a weak push can fail to climb,
stop and **roll back to the side that pushed it**, even into its own goal (**own goal**, counted for the other side).
- The AI **learns the slope from the ball** (each half separately) and predicts curved runs, balls that turn back,
  and balls in its own half rolling down to it (`predictor.py`, `config.SLOPE_*`).
- Commentary: *"It's rolling back!"* when a ball turns back mid-board; own goals get their own call
  (*"It couldn't make the climb, and it's rolled back in! Own goal, Player One!"*).
- The simulator uses `config.SIM_SLOPE`.

## 5. Audio design

- **Always a crowd bed.** Ducked (quieter) while the commentator speaks.
- **Big moments are loud:** pre-match swell, 3-2-1 + buzzer, goal roar, golden goal, full time, outro.
- **Silence on purpose:** 1 s of near-silence right before "Three…" builds tension.
- **The commentator only guides:** score, game flow, rules, clock, what just happened. Never talks over a goal call.
  **No filler lines** (remove the current random fillers / colour lines from the live game).
- What he does say during play: goal calls + score/difference, restart instructions, freeze calls, save calls,
  clock calls (half time with score, 30 s, 10 s, 5-4-3-2-1), golden goal, pause/resume.
- **Robot buzzer** doubles the 3-2-1-GO beeps and goal jingle, loud (run the passive buzzer near its resonant frequency ~2.7–4 kHz).

### During play: never late, never robotic
- **The crowd carries the play.** Ambience always on; it swells when the AI predicts a goal is coming (tension),
  "ooh" on a last-moment save, gasp when a goal looks certain, applause at 6 / 10 / 15 / 20-hit rallies.
- **Short calls (< ~1 s), fired the instant it happens, never queued:** saves ("Denied!", "Not today!"),
  close saves ("Ohhh! Inches!"), rockets ("A rocket!"), walls ("Off the wall!"), danger ("Here it comes!").
  At most one every 4 s, and only if nothing else is being said.
- **Guiding lines only in safe gaps:** after 2.5 s of quiet, at most one per 9 s, and only while the AI sees no
  goal coming on this attack: rally counts, "still unbeaten", the score situation, "needs a goal, time running out".
- **A goal always cuts in:** whatever is playing fades out in 80 ms under the roar; the goal call starts at once.
- **Only the F5 voice (Tahmid's).** Recorded clips from `show/voice_bank` are used wherever they fit; new lines are
  rendered by `ui/render_lines.py` with the same references. A line with no clip is shown as a subtitle only.

### New voice lines to record/render (F5-TTS, same voice)
- Mode intros (VS MACHINE / 2 PLAYERS), "We are about to witness a battle between … and …"
- Kick-off privilege line for P1; placement lines for P1 / P2 / "in front of the machine's carriage"
- "Push your joystick forward when you're ready." · "Three… two… one… Go!"
- Goal difference: "leads by one / two / three", "level", "a three-goal cushion", "pulls one back"
- Buzzer: "Player one / Player two / The machine hits the buzzer first!" · "… is frozen for three seconds!" · "Nobody on the buzzer!" · "And they're live again!"
- Pause: "The match is paused." · "We're back!"
- Clock: "That's half the time gone." (+ score clip) · "Only thirty seconds remaining!" · "Only ten seconds remaining!" · "Five… four… three… two… one…"
- Golden goal: "Golden goal! The next goal wins it all!" · golden-goal winner call
- Outro (loud, several versions)
- Highlight story pieces (§6.3)

---

## 6. Highlights system (rebuild — the current one is not good enough)

### 6.1 Record per goal (the "goal file")
For every goal keep a data record + video:
- **Video:** raw camera + AI view, from ~6 s before to ~3 s after the goal (ring buffer).
- **Ball track:** positions + timestamps for the last ~6 s (from the tracker), shot speed (peak & at goal), shot angle, **wall bounces** (count, which wall), where it crossed the goal line (x), distance travelled.
- **Keeper situation:** defending carriage position at the shot, distance from the ball's line, whether the AI's predicted intercept was reachable (= "unstoppable" vs "keeper error"), whether the defender was **frozen**.
- **Match context:** score before/after, clock, time since the previous goal (quick reply?), rally length before the goal, saves made before it, who was leading, was it an **equaliser / go-ahead / winner / golden goal / comeback** (was the scorer 2+ behind earlier?), goal number of the match.

### 6.2 Classify the goal (story type)
Examples: **Worldie** (very fast from far), **Bank shot** (off a wall), **Rebound** (straight after a save), **Instant reply** (< 10 s after conceding), **Sneaky** (slow ball, keeper out of position), **Unstoppable** (keeper couldn't physically reach), **While frozen**, **Equaliser**, **Winner / Golden goal**, **Comeback completed**.

### 6.3 Write the commentary from the data (not the live clips)
- A highlight gets its **own narration**, calmer and more storytelling than the live call:
  *"Minute two. Player one, a goal behind… watch the angle… off the left wall… eighty centimetres a second… and the machine never had a chance. Level."*
- Built from **pre-rendered modular pieces** (the Windows PC can't run F5-TTS live): time phrases, situation phrases, shot-description phrases, speed numbers, emotion phrases, score/impact phrases, comeback lines. Assemble per goal from the data, with fillers and breaths.
- Tone follows the story: tension on the build-up, peak on the goal frame, whisper on the slow-mo, satisfaction on the impact line.

### 6.4 Sync narration to video
- Timeline per goal (~12–18 s): build-up at normal speed with narration → **peak phrase lands exactly on the goal frame** → slow-motion replay (0.4×) with a whispered line → impact line (score, story).
- Crowd bed follows: builds during the build-up, roar on the goal, murmur under the slow-mo.
- Between goals: short title card ("GOAL 2 · 1:47 · PLAYER ONE").
- End: awards recap (5–10 s) → HOME.

---

## 7. Settings page (joystick-driven)

| Group | Settings |
|---|---|
| **Sound** | Commentary volume · Crowd volume · Commentary on/off · Output test |
| **Gameplay** | Default match length · Golden goal on/off · Buzzer freeze on/off · Buzzer how often · Freeze length · AI wins the buzzer (%) · Default AI difficulty |
| **Servo tuning** | P1 / P2: rest angle, swing, test strike (the current `[ ] - = /` tool, joystick version). Saved on the robot **and** the laptop |
| **Camera & AI** | Recalibrate board · Re-teach ball / carriage colour · Swap L/R · Show AI debug overlay |

Settings persist on the laptop (JSON) and are pushed to the robot on connect.

---

## 8. LCD 16×2 (for show: "we used proper equipment")

| State | Line 1 | Line 2 |
|---|---|---|
| Boot | `CHEERIVY v5` | `Connecting...` |
| Home | `CHEERIVY` | `Select mode <>` |
| Setup | `VS MACHINE` / `2 PLAYERS` | `MEDIUM  3:00` |
| Pre-match | `P1 vs AI  3:00` | `Get ready...` → `3` `2` `1` `GO!` |
| Live | `P1  2 - 1  AI` | `2:15    LIVE` |
| Goal | `GOAL! PLAYER 1` | `Place ball: P2` |
| Paused | `PAUSED` | `Resume  Home` |
| Golden goal | `GOLDEN GOAL` | `P1  2 - 2  P2` |
| Full time | `FULL TIME` | `P1  3 - 1  AI` |

Wiring (old diagram): RS PB2 (pin 3), EN PB3 (pin 4), D4–D7 PB4–PB7 (pins 5–8), RW → GND, contrast pot on V0.
⚠️ PB5–PB7 are shared with the USBasp: burning works with the LCD attached, the LCD just shows garbage until reset.
The laptop sends the text; the ATmega only writes it (keeps the firmware simple).

---

## 9. Architecture (what to build)

```
ROBOT (ATmega32)                    LAPTOP (Python)                         SCREEN (browser, fullscreen)
- motors, servos, buzzer, LCD  ◄──► - game state machine (this document)  ─► HTML + CSS + JS
- joystick/button events  BT        - camera AI, goal detection               - all screens above
- locks / unlocks play              - sound (pygame mixer, crowd + voice)     - animations, replays
- laser goals                       - highlights builder                      - reads state via WebSocket
                                    - small web server + WebSocket
```

### Firmware changes needed
- **Report inputs always** (lobby, menus, pause): joystick directions (edge events), button taps, "both held 3 s".
- **Lock / unlock play** on laptop command (goal, pause, pre-match): carriages + servos off, clock stopped.
- **Robot does not decide the flow any more** — the laptop does (the robot keeps a safe fallback for Mirror-AI play without a laptop).
- LCD driver + "write line 1/2" command.
- Buzzer race: `buzz` command beeps the buzzer; the robot reports which button was pressed first (fair timing on the MCU), laptop sends `freeze <side> <s>`. The old free freeze + cooldown is removed.
- 3-2-1 + loud GO beeps on command.

### Laptop changes needed
- New state machine (§3), web server + WebSocket, browser UI (§3, §7), new highlight system (§6), settings persistence, new voice lines (§5).
- Commentary: **remove fillers / colour lines** from live play; add half-time + 30 s + 10 s + 5-4-3-2-1 calls; keep only guiding lines.

---

## 10. Open questions (decide later)
- Golden goal safety cap (end as a draw after X min?) — default proposal: 2 min.
- Leaderboard: keep for VS MACHINE only (by difficulty)?
- Attract mode content once there are no goals of the day yet.
- Visual identity: final colours, font, logo.
