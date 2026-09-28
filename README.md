# CHEERIVY

Robotic ball duel: a human player vs an AI, on a single ATmega32 (internal 8 MHz).
CSE316, BUET.

## Burn the firmware

**`CHEERIVY.hex`** is the firmware. Burn it onto the ATmega32 with a USBasp. **Do NOT change the fuses.**

- **Windows:** unzip `CHEERIVY_burn.zip` and double-click `BURN.bat` (avrdude is included).
- **Mac/Linux:** `make flash` (needs `avr-gcc` and `avrdude`).
- USBasp wiring: see `USBASP_wiring.svg`. Use the USBasp's JP3 (slow clock) jumper if the chip does not answer.

To rebuild after changing `main.c`: `make`, then copy `main.hex` to `CHEERIVY.hex`.

## Hardware (v5)

| | Human | AI (red tape on carriage) |
|---|---|---|
| Control | Joystick X pin 39, Y pin 37, button pin 2 | Laptop camera via HC-05 (pin 14), or Mirror AI when the laptop is silent |
| Motor | TB6612 channel B (pins 24, 25, 26) | TB6612 channel A (pins 22, 23, 20) |
| Striker | Servo on pin 19 (rest 90°, strike 25°) | Servo on pin 18 (rest 87°, strike 20°) |

Shared: TB6612 STBY pin 36, buzzer pin 21. Goal lasers (optional): pins 16 and 17.

## Power-up

- **Hold the freeze button while powering on:** self-test (motors and both servos, with beeps between).
- Otherwise: beeps show the difficulty (2 = medium). Press freeze within 3 s to change it.
- Then the robot waits in its **lobby** for the laptop: the laptop app connects over the HC-05, you pick
  **1 = single player** (vs the AI) or **2 = two players** (2nd joystick on pins 40 / 38 / 1), type the names,
  and the robot starts that game. After each match it goes back to the lobby.
- No laptop? Press freeze in the lobby to play single player against Mirror AI.

## Vision AI (laptop)

`cheerivy_ai/` tracks the ball with a phone camera (Iriun / Continuity Camera) and drives the AI carriage over Bluetooth.

```
cd cheerivy_ai
python3 main.py --sim       # virtual board, no hardware needed
python3 main.py --no-send   # real camera, tracking only
python3 main.py --no-show   # real camera + robot, AI window only
```

Needs `pip install opencv-python numpy pyserial`. Board measurements are in `cheerivy_ai/config.py`
(see `cheerivy_ai/measurements.svg`). Run the tests with `cd cheerivy_ai && python3 -m unittest test_predictor`.
