# CHEERIVY screen

The game screen from GAMEFLOW.md: a browser page in fullscreen, driven by the laptop.

```
python ui/server.py            (from cheerivy_ai/)  → opens http://localhost:8316, press F for fullscreen
```

Only the Python standard library is needed. The fonts are in `web/fonts/`, so it works offline.

| File | What it does |
|---|---|
| `flow.py` | The game itself: home → setup → pre-match → kick-off → live → goal → restart → time up / golden goal → full time → highlights → home. No hardware in it. |
| `server.py` | Serves `web/`, runs the Flow, streams its state to the page (`GET /events`) and takes keys (`POST /key`). |
| `web/app.js` | Draws every screen from the state (one function per screen in `SCREENS`, overlays in `overlayFor`). |
| `web/board.js` | AI VISION: the top-down board, ball, carriages and predicted path, drawn from centimetres. |
| `web/style.css` | The whole look. Colours are variables at the top: `--p1` warm, `--p2` cool, `--gold` wins only. |

The page is a fixed 1920×1080 stage, scaled to fit, so it looks the same on the laptop and on a projector.

## Simulator keys (until the robot drives it)

| | Joystick | Button | Back (hold down) |
|---|---|---|---|
| Player 1 | W A S D | Space | Q |
| Player 2 | arrows | Enter | Backspace |

`H` = both buttons held 3 s (pause) · `G` = goal for player 1 · `K` = goal for player 2 / the AI ·
`Esc` = home · `F1` = settings · `` ` `` = dev panel (LCD preview + robot commands) · `F` = fullscreen

## State the page receives (one JSON per change)

`screen` (home, attract, difficulty, join, length, settings, prematch, ready, countdown, live, goal, pause, fulltime, highlights) ·
`mode` (ai / 2p) · `difficulty` · `length_s` · `names` {1, 2} · `score` [p1, p2] · `clock` (s left) · `running` · `golden` ·
`kicker` (1, 2 or "any": whose button starts) · `placer` (who places the ball) · `kicked_off` ·
`countdown` (3, 2, 1, "GO" or null) · `flash` (scorer on the goal screen) · `menu` {title, items[{id, label, value}], cursor, group} ·
`caption` (what the commentator is saying) · `freeze` {1, 2: {frozen, cooldown, cooldown_total}} ·
`goals` [{scorer, score, at, golden}] · `result` {winner, score, awards[{title, who}]} · `highlight` {index, total} ·
`lcd` [line1, line2] · `log` · `arena` {w, h, poly, rail, depth, cw, r} · `board` (from the AI, later: {ball, path, ai_x, p1_x}).

## Still to connect
- `main.py` drives the same Flow: robot joystick/button events in, `lock`/`unlock`/`beep`/`freeze`/LCD out (needs the firmware changes in GAMEFLOW.md §9).
- The AI's live numbers go into `board`; voice and crowd go through the `say` hook (the Flow waits for `voice_busy`).
- Real replays in the highlights reel.
