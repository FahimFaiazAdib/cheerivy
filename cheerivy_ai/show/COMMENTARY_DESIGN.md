# CHEERIVY — Commentary Design (Drury-inspired style)

All lines are **original**, written in a Drury-*inspired* style. None are real quotes.
The voice is **our own** (a consenting team member recorded live), cloned with F5-TTS.
The render spec for the voice clips is in [VOICE_RENDER_SPEC.md](VOICE_RENDER_SPEC.md).

---

## 1. What makes it sound like Drury

It's a few techniques you can write on purpose:

| Technique | What it means for us |
|---|---|
| **Build-up, then eruption** | Short fragments with silence between ("Fahim… again… still…"), then a shouted payoff. |
| **Saying the name several times** | "Fahim! Fahim Faiaz! From distance!" The name *is* the build-up. |
| **Poetic framing** | Turn a small table game into history: human versus machine, maker versus made. |
| **Lists of three** | "Cold. Calculated. Clinical." |
| **Rhetorical questions** | "Is there time? Is there *belief*?" |
| **Local references** | BUET, Palashi, the Padma, monsoon, "eight megahertz of cold intent". |
| **Silence** | Half of the drama is *not* talking. The crowd fills the gap. |

**Our story:** human against the machine he built. Every line can use it. The AI has no feelings,
so the commentator gives it a personality: "the silicon", "the machine", "thirty-two kilobytes of ambition".

---

## 2. Every scenario we can detect

We already track the ball, the AI carriage, the predicted path, goals, the clock and the link mode.

| # | Scenario | How it's detected | Speed needed |
|---|---|---|---|
| 1 | Kick-off | `START` line from the MCU / `k` key | Relaxed |
| 2 | Human shot | Ball speed spikes and `vy` points at the AI | **Instant** (under 150 ms) |
| 3 | AI shot | Speed spikes, `vy` points at the human, ball near the AI line | Instant |
| 4 | Ball off the wall | Predictor sees a bounce | Instant |
| 5 | AI save | Predicted hit on the AI line, then `vy` flips near it | Instant |
| 6 | Near miss | Ball reaches a goal line near the edges, but no `G` line arrives within ~300 ms | Fast |
| 7 | Human goal | `G H` | Instant |
| 8 | AI goal | `G A` | Instant |
| 9 | Fast shot | Speed over 60 / 80 / 100 cm/s | Adds a tail after the goal |
| 10 | Long rally | Counter of `vy` sign flips reaches 5, 8 or 12 | Relaxed |
| 11 | Lull | Ball slow or still for ~3 s | Relaxed |
| 12 | Ball lost | Tracker loses the ball for more than 1 s | Relaxed |
| 13 | AI blind | `MODE MIRROR` (Bluetooth link dropped) | Relaxed |
| 14 | Link back | `MODE CAMERA` | Relaxed |
| 15 | Freeze used | Needs firmware to report it (planned) | Instant |
| 16 | Score situation | Opener, equaliser, taking the lead, AI extends lead, comeback, rout | Tail after a goal |
| 17 | Clock | 60 s, 30 s, 10…1 countdown, last-gasp goal (under 5 s left) | Scheduled |
| 18 | Full time | Human win, AI win, draw, big win, clean sheet | Relaxed |
| 19 | Records | New fastest shot, new leaderboard top, first player ever to beat the AI | After a goal / full time |
| 20 | Callbacks | "Denied three times… and now at last!" (uses memory of the match) | Tail |

---

## 3. How the clips connect in live play

### 3.1 Split lines into four kinds of clip

Don't render whole sentences. Render **parts** you can glue together:

```
[BUILD]   short, under 0.8 s, played the moment a shot is detected
          "Fahim…"  "Here's Fahim…"  "Off the wall…"  "Oh, this is dangerous…"

[PAYOFF]  the eruption; which one plays depends on the result
          goal: "OH, IT'S IN!"   save: "DENIED!"   miss: "OHHH, INCHES!"

[TAIL]    context about the score, speed or story, played after the crowd roar
          "Two… one. Humanity leads."  "Ninety centimetres a second!"

[COLOUR]  poetic filler for lulls, only in silence
          "The ball rests. The minds do not."
```

**The key trick:** play the BUILD clip the moment the shot is detected, before you know what happens.
The ball takes ~0.5–1 s to cross the arena, so when the result arrives (`G` / save / miss), the PAYOFF
clip follows straight on. It sounds like the commentator *saw it coming*. If nothing happens (a weak
shot), the build-up just ends as an unfinished thought, which Drury does all the time.

### 3.2 Three tone levels

Record 3 reference clips of our real voice, one per tone, and render each line with the right one:
- **calm**: kick-off, lulls, tails, the highlights intro
- **build**: fragments, rising tension
- **erupt**: goals, saves, last-gasp moments

### 3.3 A tension meter picks the tone

A value from 0 to 100, updated every frame:
```
tension = score closeness (0–30)
        + time pressure   (0–30, rises sharply under 30 s)
        + ball danger     (0–25, ball fast and heading for a goal)
        + rally length    (0–15)
```
- Low tension: calm lines, more colour, fewer build-ups.
- High tension: short fragments, no colour, maximum eruption.
- High tension and the ball near a goal: briefly **lower the crowd volume** (the hush), then roar.
  This one trick sells the whole effect.

### 3.4 Rules for the queue (fits the existing `voice.say(priority, max_age, interrupt)`)

| Rule | Why |
|---|---|
| Goal payoffs interrupt everything | A goal can never be late |
| Build-ups expire after ~0.6 s | A stale "Fahim…" after the ball has already landed sounds broken |
| Colour lines only after 3+ s of silence and tension under 40 | Don't talk over play |
| Talk budget of at most ~40% of the time | Silence is part of the style |
| No clip repeats within its cooldown; keep the last 10 used | Repetition kills it fastest |
| Tails wait for the crowd roar to fade (~1.2 s) | That's the pause for effect |

### 3.5 Match memory for callbacks

Keep a small record per match: shots, saves in a row, near misses, fastest shot, lead changes,
time of the last goal. Tail lines can then have conditions:

- `saves_in_a_row ≥ 3` and a human goal: "Three times he knocked… three times the door held… and NOW it breaks!"
- A goal within 10 s of conceding: "The reply! Instant! Defiant!"
- A near miss followed by a goal from the same side: "Denied from there a minute ago… not this time!"

### 3.6 Handling names

F5 is slow, so names can't be rendered live.
- **When the names are typed:** render the name clips in all 3 tones (~10–20 s on the M1, in the background during the intro).
- **Most payoffs don't include the name**, so they are rendered once, forever.
- A few *signature* lines are fully rendered with the name at kick-off, because glued clips can sound choppy.
- Optional **"say it like"** field on the name screen (e.g. "Adib" → "Ah-deeb").
- Write numbers as words, and put pauses in **between clips** as real silence. TTS models often ignore "…".

---

## 4. The script bank (original, Drury-inspired)

Placeholders: `{p}` = player name, `{ai}` = AI name, `{h}`/`{a}` = score, `{v}` = speed.
The full render list with IDs and tones is in [VOICE_RENDER_SPEC.md](VOICE_RENDER_SPEC.md).

**Kick-off (calm → build)**
- "Under the lights of a laboratory in Palashi… one human being. One machine. Sixty centimetres of destiny between them."
- "{p}. Flesh, and nerve, and hope. And across the table… {ai}. Eight megahertz of cold intent."
- "They say the machine cannot be beaten. Tonight… {p} has come to ask it a question."
- "Three minutes. One ball. And a question as old as invention itself… can the maker defeat what he has made?"

**Build-ups (under 0.8 s, all tones)**
- "{p}…" · "{p} again…" · "Here's {p}…" · "Now then…" · "Off the wall…" · "Still alive…" · "Oh, this is dangerous…" · "The machine is moving…" · "Is there… a way through?"

**Human goal (erupt)**
- "OH, IT'S IN! {p}! Poetry in a plywood arena!"
- "{p}… has found a flaw in the code!"
- "The machine calculated everything… except THAT!"
- "IT'S THERE! For every student who ever lost to a computer!"
- "Written in the stars… and now, in the scoresheet!"

**Human goal tails (calm)**
- "The silicon did the maths. The human did the magic."
- "Somewhere, a transistor weeps."
- "Mark it down. Remember where you were."

**AI goal**
- "Cold. Calculated. Clinical."
- "The machine does not celebrate. It does not need to."
- "It saw that… before {p} had even thought it."
- "Oh, cruel. Cruel mathematics."

**AI save**
- "DENIED! The machine stands in the doorway!"
- "Read like a textbook… one it wrote itself."
- "Not today, says the silicon."

**Near miss**
- "OHHH! Inches! Mere inches!"
- "It kissed the line… and ran away."
- "Agony for {p}. Pure agony."

**Wall bounce / fast shot**
- "Off the wall… geometry itself has joined the game!"
- "That left the flipper like a monsoon wind!"
- "{v} centimetres a second! The camera barely believed it!"

**Rally / lull / chaos**
- "This rally has a heartbeat of its own…"
- "Ten touches! Neither will blink!"
- "The ball rests. The minds do not."
- "Where is it? Even the camera has lost it!"
- "The machine has lost its eyes! It plays now… on memory alone!" (`MODE MIRROR`)
- "FROZEN! The machine… cannot… move!" (freeze)

**Score situations (tails)**
- Equaliser: "LEVEL! Everything we thought we knew… is gone!"
- Taking the lead: "{p} LEADS! Humanity is in front!"
- Comeback: "From two behind… this is not a match anymore. This is a story."
- AI extends the lead: "The grip tightens. Slowly. Mechanically."

**Clock**
- 60 s: "One minute. Sixty heartbeats."
- 30 s: "Thirty seconds… and the clock belongs to no one."
- 10…1: separate number clips, getting louder
- Last gasp: "AT THE DEATH! {p}! AT THE VERY DEATH!"

**Full time**
- Human win: "It is over. {p} has beaten the machine. Tell the engineers. Tell the textbooks. Tell everyone."
- AI win: "The machine prevails… but {p} made it sweat. If silicon can sweat."
- Draw: "Level. Human and machine walk away as equals. Tonight… nobody is obsolete."
- Rout by the AI: "A lesson. Delivered in binary."
- New record: "A new name at the top of the leaderboard!"

---

## 5. Commentary in the highlights

Highlights are **offline**, so speed stops being a problem. They can be much richer than live play.

### 5.1 Timeline for one goal replay
The recorder already knows the frame where the goal happens (the clip is 3 s before plus a little after).
```
t = 0.0   normal speed    [context]  "Two minutes in. Nil-nil. The machine had not yet blinked."
t ≈ 1.8   slow motion     [hush]     crowd lowered, 0.5 s of silence
                          [whisper]  "Watch it again… watch the machine… it simply… cannot… reach."
t = goal  (payoff peak lands on the goal frame)
                          [erupt]    "AND IT'S IN!"   plus a crowd roar
after     freeze frame    [tail]     "One nil. And the laboratory… will never be the same."
```
**Sync rule:** start the payoff at `goal_time − peak_offset_ms` (measured per clip at render time,
stored in `manifest.json`), so the loudest word hits the goal frame exactly.

### 5.2 Structure of the reel
1. **Opening monologue:** "Let us remember… let us relive…" plus the names.
2. **Goals in order,** with the scoreline growing in each context line ("One nil… one all… two one").
3. **Turning point:** automatically pick the lead change or equaliser and give it the longest slow motion.
4. **Awards:** Rocket (fastest shot), The Wall (AI saves), The Marathon (longest rally).
5. **Closing monologue** over the winner screen and confetti.

### 5.3 Optional: a closing written by Claude
Send the match facts from `match.json` (names, goals, times, speeds, saves, lead changes) to Claude to
write a **3-sentence original closing** in this style. Render it with F5 while the full-time screen is
up (~15 s). No internet or too slow → use a template. Each match gets a unique ending.

---

## 6. Risks to plan for

| Risk | How to handle it |
|---|---|
| Over-talking | Talk budget, colour lines only in lulls |
| Late commentary | Short expiry times on build-ups and saves |
| Obvious repetition | 3–5 versions per event, cooldowns, history |
| Choppy glued clips | Same tone reference per sentence; full renders for signature lines |
| Wrong saves / near misses from noisy tracking | Confirm after 2–3 frames of agreement; prefer missing an event over a false one |
| Name pronunciation | "Say it like" field |
| Too loud for the room | Voice, crowd and effects on separate channels with ducking |
| Tuning | Run `--sim` and print a **commentary log** (time, event, clip) to review afterwards |

---

## 7. Where it fits in the code
- `lines.py` becomes a clip bank with category, tone, cooldown and conditions for each line.
- A new *director* sits between the tracker/predictor output and `voice.say`. It detects events,
  tracks tension and match memory, and picks clips.
- `show.on_line` already receives `G` / `START` / `MODE`, and `stats.py` already counts saves and rallies.
- `recorder.py` knows the goal frames, which the highlight timeline needs.
