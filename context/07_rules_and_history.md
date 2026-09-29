# Rules, decisions, known problems

## Hard rules
- **Never change the ATmega32 fuses.** Never use `avrdude -F`. Never "Write All" in eXtreme Burner.
- **Voice recordings stay out of git** (`show/voice_bank/`, `ui/voice/`, `ui/cache/`, `ui/settings.json`
  are ignored). They are clones of a team member's voice (Tahmid) made with permission.
  `fahadmahmudvoice.mp3` is **not** a team member: never use or publish it. Never clone a real
  voice actor's voice without permission. No made-up TTS voices: everything is in Tahmid's voice.
- Python must run on 3.9 and 3.11 (Atiq's PC).
- Don't break the protocol between `main.c` and `link.py` / `live.py` without changing both sides,
  and remember that a firmware change means Atiq has to burn.
- Push only to `cheerivy-v5-lobby-2p`.

## Decisions already taken (don't undo them without asking)
- The browser game is the main interface; the old OpenCV "show" window only with `--old-show`.
- Strike = joystick **forward**; buzzer / skip = pressing the joystick **in**. Restart after a goal =
  push forward (not the button).
- Commentary can be skipped (Tab / N / press a stick in), except the buzzer rule and freeze calls.
- AI VS AI names: Machine One (player 1, blue tape) and Machine Two (player 2, green tape).
- Goals come from the camera until the lasers are wired (`LASER_GOALS = False`).
- The AI shouldn't run back to the exact middle after every shot (the N20 is slow).
- Servo timing per strike comes from the swing (no fixed minimum); experiments with a minimum hold
  time and with "arm follows the joystick" were tried on the robot and rejected by the team.

## Things that were tried and reverted
- Showing extra margin around the calibrated board, faster re-planning mid-move, striker offsets,
  corner-ball rules (late September 2026): the team found the earlier AI played better, so
  `controller.py` / `tracker.py` / `config.py` went back to that version (strike zones and the calmer
  idle behaviour were added on top).

## Known problems / open work
- Player 1's servo hardware (see 02_hardware.md); a bigger player 1 swing is recommended.
- Player 1's AI (AI VS AI) defends worse than player 2's: it is the far end from the camera
  (smaller, less precise), and its servo is the unreliable one.
- The laser goal sensors are not wired; camera goals can miss or invent a goal now and then.
- LCD 16×2 text not done.
- If clicks/keys on the page seem to do nothing: more than one CHEERIVY tab is probably open.
