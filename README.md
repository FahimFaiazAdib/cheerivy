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

| | Human | AI (green note on the carriage) |
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

Install the packages with `python3 -m pip install -r cheerivy_ai/requirements.txt`. Board measurements are in
`cheerivy_ai/config.py` (see `cheerivy_ai/measurements.svg`). Run the tests with
`cd cheerivy_ai && python3 -m unittest test_predictor`.

### Running on Windows

1. Install **Python 3.10 or newer** from python.org (tick **"Add python.exe to PATH"**).
2. Install **Iriun Webcam** (or DroidCam) on the PC and the phone.
3. Pair the HC-05 (or "CHEERIVY") in **Settings → Bluetooth** (PIN `1234` or `0000`).
4. In Command Prompt, inside the `cheerivy` folder:
   ```
   python -m pip install -r cheerivy_ai\requirements.txt
   cd cheerivy_ai
   python main.py --sim        (test without the robot)
   python main.py              (real robot)
   ```
- **Camera:** if the laptop's own webcam opens, quit with `q` and try `python main.py --cam 1`.
- **Calibration:** `calib.json` is not shared, so the first run asks you to click the board corners.
- **Bluetooth:** found automatically. If not, look up the port in
  *Device Manager → Ports (COM & LPT)* ("Standard Serial over Bluetooth link", the **outgoing** one) and run
  `python main.py --port COM5` with your number.
- **Voice:** the commentary uses the built-in Windows voice.

### Ball and carriage colours

The tracker looks for an **orange ball** and a **green (tia) note on the AI carriage**; change
`BALL_COLOR` / `CARRIAGE_COLOR` in `cheerivy_ai/config.py` for other colours (black ball: `"black"`).
In the right-hand (top-down) view: **left-click the carriage note** and **right-click the ball** to fine-tune
the colours to your lighting.
