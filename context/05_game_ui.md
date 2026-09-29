# The browser game (`cheerivy_ai/ui/`)

A 1920×1080 page (scaled to fit), served by the laptop at `http://localhost:8316`, fullscreen with F.
`main.py` starts it (live, with the camera and robot); `python ui/server.py` runs it alone as a
simulator. Plain HTML/CSS/JS, no build step; only the Python standard library on the server side.

| File | Job |
|---|---|
| `flow.py` | the game itself, no hardware: every screen, the clock, goals, buzzer race, commentary scripts, settings (saved in `ui/settings.json`) |
| `server.py` | HTTP: the page, `GET /events` (state as server-sent events), `POST /key`, MJPEG `/video` (top-down) and `/raw` (camera as filmed, for calibration), `/replay`, `/calib`, `/sample` |
| `live.py` | bridges `main.py` ↔ Flow ↔ robot: robot lines → game events, game → robot bytes, camera frames → the page, goal replays, calibration on the page |
| `play.py` | turns the ball's motion into play events (hit, wall, danger, roll-back, rest); the simulator table |
| `commentary.py` | all commentary lines (`LINES`): recorded clips first, else written lines rendered in the same voice |
| `sound.py` | pygame: crowd, effects, voice; `hush` fades the voice out |
| `render_lines.py` | renders the written lines with F5-TTS in Tahmid's cloned voice → `ui/voice/` |
| `web/index.html`, `web/app.js` | every screen (one function per screen in `SCREENS`) |
| `web/board.js` | AI VISION: the camera picture with the ball, predicted paths, carriages, strike zones |
| `web/style.css` | the look; colours at the top: player 1 warm orange, player 2 / AI cool cyan, gold for wins |

## Screens (see `GAMEFLOW.md`)
home → mode → difficulty / join → match length → pre-match intro → ready (place the ball, push
forward) → 3-2-1 → live → goal → … → full time → highlights → home. Also settings, pause, debug,
calibrate (board corners) and colours.

## Inputs
Robot joysticks (via `IN …` lines) or the keyboard: player 1 W A S D / Space / Q, player 2 arrows /
Enter / Backspace, Esc home, F1 settings, H pause, G / K fake goals, **Tab or N = skip the talk**
(also pressing a joystick in while the commentator talks; the buzzer rule is never skipped).
Only one tab: a newer CHEERIVY tab puts the older ones to sleep (browsers allow 6 connections per
site, and each tab keeps 2–3 open).

## Commentary
- 73 moments, ~167 versions, picked at random (never the same twice in a row), recorded clips from
  `show/voice_bank` first. Short in-play calls only when nothing else is being said.
- Names: Player One / Player Two / the machine; in AI VS AI "Machine One" / "Machine Two".
- Voice files are **not in git** (`ui/voice/`, `show/voice_bank/`): they are shared as a zip and
  extracted into the repo on Atiq's PC.

## Highlights
The live game keeps the last 5 s of picture + what the AI saw; at a goal it keeps 5 s before and 1.5 s
after. After full time each goal replays in slow motion with the AI's predicted path drawn on it.

## Calibration and colours
Settings › Camera & AI › Recalibrate board: the camera picture on the page, click the 4 inside
corners (2 at player 2's end, then 2 at player 1's), SAVE. Re-teach colours: left-click a tape,
right-click the ball, on the top-down picture.
