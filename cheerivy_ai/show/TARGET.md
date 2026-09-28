# CHEERIVY Live Show: Target Features

The Mac app that runs next to the robot. It shows the match live, records every goal,
and plays a highlight show after the final whistle.
It runs inside the vision AI (`cheerivy_ai/main.py`) because only one program can
own the camera and the HC-05 port at a time.

Status: ✅ in v1 · ⏳ later · 🔌 waits on hardware

---

## v1 (building now)

- ✅ **Player names**: type the player's name (and the AI's name) before the match.
- ✅ **Live view**: real camera footage **side by side** with the AI's view, in the best
  ratio for the screen:
  - the camera is cropped to the arena, and the AI view is turned to face the same way as the camera
  - the AI view shows the ball, its **predicted path with every wall bounce**, the impact
    point and the AI carriage's target
  - the two panels share one height and the layout adapts to the window size
- ✅ **Scoreboard**: names, score, match clock (red in the last 10 s), level, AI mode (Camera / Mirror).
- ✅ **Goal replays**: the last **3 seconds before a goal** (+ a moment after) are saved as a clip,
  with a big GOAL animation, the scorer's name and an instant-replay picture-in-picture.
- ✅ **Shot speed**: every goal shows its speed in cm/s (from the ball tracker).
- ✅ **Highlight reel after the game**: every goal played back (slow motion on the finish),
  with animated name banners, then the awards, then the winner with confetti.
- ✅ **Match stats & awards**: shots, AI saves, longest rally, fastest shot
  ("Rocket", "The Wall", …).
- ✅ **Voice commentary**: **Kokoro TTS, British voice `bm_george`** ("What a goal by Fahim!",
  "10 seconds left!", full-time result). Falls back to macOS `say` if Kokoro can't start.
- ✅ **Leaderboard**: kept across matches (name, score against the AI, fastest shot).
- ✅ **Manual goal keys** (`h` player / `j` AI): to test before the lasers are wired, and to fix a missed goal later.
- ✅ **Simulator** (`--sim`): the whole show runs without the robot.

## Later

- ⏳ **Exported highlight video (.mp4)**: after the game, an auto-edited highlight film:
  - cool transitions and text animations / overlays (names, score, speed)
  - AI voice-over (George) narrating the goals
  - background music
  - "best highlight" edit made from the goal clips, saved for the presentation
- ⏳ **Winner photo (optional)**: the MacBook's own camera takes a photo of the winner for the
  final screen and the leaderboard. **If there is no camera or no permission, skip it quietly.**
- ⏳ **Freeze & AI-mode alerts**: "❄️ FROZEN!" on screen when the freeze is used
  (needs the firmware to report freeze presses).

## Hardware dependency

- 🔌 **Goal lasers**: firmware support is written (`main.c`: INT0/PD2 = human goal line → AI scores,
  INT1/PD3 = AI goal line → human scores; it sends `G H|A <human> <ai>`), but **the receivers are not
  wired yet**. Until they are, goals come from the manual keys or the simulator.
  After wiring, check the `LASER A OK` / `LASER B OK` lines at kick-off.

---

## How to run (v1)

```
cd cheerivy_ai
python3 main.py            # real robot: camera + HC-05 + live show
python3 main.py --sim      # everything simulated (60 s matches)
python3 main.py --no-voice # no commentary      --no-show  only the old vision window
```

1. The **CHEERIVY LIVE** window opens on the name screen: type the name, `TAB` for the AI's name, `ENTER`.
   (While the name screen is up, every key goes to the name, so `q` only quits after ENTER.)
2. Kick-off happens when the robot sends `START` (power on / press FREEZE after a match), or press `k`.
   The AI unpauses by itself at kick-off and pauses at full time.
3. Goals: laser `G` lines (once wired), or `h` = player goal, `j` = AI goal. `e` ends the match early.
4. After the match: full time → highlights (up to 6 goals) → awards → winner and leaderboard.
   `r` replay · `ENTER` next match · `n` new player · `v` fullscreen.

Files: goal clips + `match.json` in `show/matches/<date>_<player>/`, the leaderboard in `show/leaderboard.json`,
and George's rendered lines in `show/cache/voice/`. The first launch of the voice takes about 10 s (until then it uses macOS `say`).
