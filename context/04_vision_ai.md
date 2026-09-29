# Vision + AI (`cheerivy_ai/`)

Python 3 (must also run on **3.9 / 3.11**: Atiq's PC. No `match`, no nested same-quote f-strings).
Needs OpenCV, numpy, pyserial, pygame (sound). Run: `python main.py --port COM10` from `cheerivy_ai/`.
`python main.py --sim` = a virtual table (no camera, no robot).

## Coordinates
After calibration everything is in **centimetres** on a flat top-down image (10 px per cm):
x → right, y ↓. The AI side (player 2) wall is y = 0, player 1's wall is y = `ARENA_H` (46 cm).
The rail runs from `X0` to `X0 + BASE_W` (3 … 41 cm). All sizes are in `config.py`.

## Files
| File | Job |
|---|---|
| `config.py` | every tunable number (board sizes, colours, AI timing, difficulty, strike zones) |
| `camera.py` | the camera reader thread; `SimArena` = the simulator (renders frames, fake robot) |
| `calibrate.py` | 4 clicked corners (2 at the AI end, then 2 at player 1's end) → homography; `calib.json` |
| `tracker.py` | finds the tapes (green AI carriage near the top, blue player 1 near the bottom) and the ball (colour + roundness); strike zones |
| `predictor.py` | ball velocity (least squares), learns each half's slope, predicts where/when it crosses the AI's line (wall bounces included) |
| `controller.py` | decides L / R / S and when to strike; timed moves (the camera and Bluetooth lag); learns motor speed and rail ends |
| `link.py` | serial to the HC-05, heartbeat resend, L/R swaps (`swap` AI side, `swap1` player 1) |
| `main.py` | the loop: camera → warp → track → predict → decide → send; runs the browser game (`ui/live.py`) |
| `goals.py` | camera goal detection (used while the lasers aren't wired) |
| `test_predictor.py` | unit tests: `python test_predictor.py` |

## How the AI plays
- A shot coming (`predictor.intercept()`): drive to the predicted crossing point, strike
  `FIRE_LEAD_S` before it arrives if the ball is within reach of the striker.
- A slow ball near its line: go to it and strike when lined up ("BALL AT MY FEET").
- No shot coming: stay put anywhere within `IDLE_ZONE_CM` of the middle (it used to run back to the
  exact middle after every shot, too much for the slow N20).
- **Strike zones**: a thin band (`STRIKE_ZONE_CM`) just in front of each carriage's tape, as the camera
  sees it. Any ball colour in it (moving or still) = strike at once. Checked on its own, not through
  the ball tracking. Drawn on the game screen, lit while the ball is in it.
- Moves are timed pulses (distance / learned motor speed), then a wait (`SETTLE_S`) so the camera
  shows where it really stopped. Driving without moving near an end = that's the rail end.
  Going the wrong way twice in a row = L/R swapped automatically (and saved in Settings).
- Difficulty (`DIFFICULTY` in config): reaction delay, aiming error, strike probability.
  HARD = no delay, no error.
- AI VS AI: a second predictor + controller for player 1 sees the board mirrored (y → H − y), so it
  is the same code; it drives player 1 with `B N M G`.

## Testing without the robot
`--sim` for the whole loop. A headless benchmark with realistic delays was used during development
(simulator + 0.15 s command delay + 0.08 s camera delay, counts saves/goals). The simulator's numbers
vary run to run (and with CPU load): compare several runs side by side.
