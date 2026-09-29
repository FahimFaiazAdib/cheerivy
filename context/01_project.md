# The project

**CHEERIVY** is a CSE316 (Microcontroller) project at BUET: a small robot ball duel, like air hockey on
a lab table, where a person can play against an AI that sees the board through a camera.

## The table
- A rectangular board (it used to be an octagon; code still has `CHAMFER_*` = 0 for that).
- A carriage at each end runs left-right on a rail, driven by an N20 motor. Each carriage has a
  servo "striker" arm that hits the ball.
- The board is slightly tilted (a thin 4 × 50 cm sheet under it), so a weak shot can roll back.
  The AI learns the slope of each half from the ball itself.
- Coloured tape on top of each carriage lets the camera find it: **green** on the AI side
  (player 2, top of the camera picture), **blue** on player 1's carriage (bottom).
- The ball is orange, 4 cm across.

## Game modes (chosen in the browser game)
| Mode | Player 1 (bottom) | Player 2 (top) |
|---|---|---|
| VS MACHINE | a person with joystick 1 | the camera AI |
| 2 PLAYERS | a person with joystick 1 | a person with joystick 2 |
| AI VS AI | the camera AI (via the blue tape) | the camera AI |
| Debug (Settings) | joystick / W A S D | joystick / arrow keys |

Matches are timed (1–5 minutes), golden goal if level. A **buzzer race**: at random moments the robot
beeps; the first to press their button freezes the other side for a few seconds (in VS MACHINE the AI
wins it about 60% of the time). The joystick is pushed **forward to strike**, pressed **in** (its
button) for the buzzer; after a goal the placing player pushes forward to restart.

## Where things stand (end of September 2026)
- Working: firmware "screen mode", the browser game (menus, match, commentary, highlights with goal
  replays), VS MACHINE and 2 PLAYERS on the real robot, calibration and colour teaching in the page.
- AI VS AI works in the simulator; on the real robot it is being tuned (player 1's side is weaker).
- Player 1's servo has been unreliable (hardware: power / wiring / a worn servo suspected).
- The laser goal sensors (PD2/PD3) are **not wired yet**; goals come from the camera.
- An LCD 16×2 is planned, not done.

## People
- The repo owner edits on a Mac and pushes. **Atiq** runs everything on his Windows PC (Git Bash),
  burns the chip and plays. Team voice clones: Tahmid (the commentator's voice).
