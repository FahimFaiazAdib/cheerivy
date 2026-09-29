# Firmware (`main.c`)

One C file for the ATmega32, built with avr-gcc (`make` → `main.hex`, then copied to `CHEERIVY.hex`).
`finalworkingcherivy.hex` is a known-good copy kept on purpose; `CHEERIVY_burn/CHEERIVY.hex` is what
`CHEERIVY_burn/BURN.bat` burns (keep it identical to `CHEERIVY.hex`).

## Structure
- Timer0: 1 ms clock (`millis()`). Timer1: both servos. Timer2: buzzer tones. ADC: joysticks.
- UART RX interrupt parses laptop bytes into flags (`rx_move`, `rx_fire`, `rx_move1`, `rx_fire1`, …).
  `uart_putc` is interrupt-safe (letters used to get lost: "IN 1 U" arrived as "I 1 U").
- Power-up: hold the freeze button = self-test. Otherwise a lobby waits for the laptop.
- `play_match()` = the older standalone game (difficulty beeps, Mirror AI when the laptop is silent).
- `screen_game()` = **screen mode**, used by the browser game: the laptop decides everything, the
  robot moves, strikes, beeps and reports inputs.

## Protocol, laptop → robot
| Bytes | Meaning |
|---|---|
| `L` `R` `S` | move / stop the AI-side carriage |
| `F` | AI-side servo strike |
| `B` `N` `M` / `G` | move left / right / stop player 1's carriage / strike (AI VS AI and debug) |
| `C<n>;` | screen mode game: 0 menus, 1 VS MACHINE, 2 2 PLAYERS, 3 AI VS AI, 4 debug |
| `O1;` / `O0;` | unlock (play) / lock (carriages stop, strikers rest, joysticks only report) |
| `D<n>;` | sounds: 3 2 1 countdown, 0 GO, 9 buzzer-race beep, 7 / 8 goal tune (P1 / AI side) |
| `I<p><s>;` | freeze side p (1 = player 1, 2 = AI / player 2) for s seconds (beeps until it ends) |
| `H<deg>;` `J<deg>;` `U1;` | player 1 servo rest / strike / test strike (`U0;` = report) |
| `Q<deg>;` `W<deg>;` `T1;` | the same for the AI-side servo |
| `P<n>;` `V<n>;` `A` `X` | DFPlayer: play track n, volume, … |
The laptop resends the current move every 0.1 s; silence for 0.4 s stops the carriage, 1.5 s = link lost.

## Protocol, robot → laptop (lines)
`SCREEN` (every second in screen mode) · `READY` (lobby) · `IN <p> L|R|U|D` joystick flicks ·
`IN <p> B` button tap · `IN <p> X` joystick held down 1 s (back) · `IN P` both buttons held 3 s (pause) ·
`G H` / `G A` laser goals · `P1SERVO <rest> <strike>` / `P2SERVO …` servo angles.
Laser goals are ignored on the laptop while `config.LASER_GOALS = False` (not wired: noise).

## Build and burn
- Mac: `make` in the repo root (avr-gcc from Homebrew), then `cp main.hex CHEERIVY.hex`.
- Windows (Atiq), from `~/cheerivy/CHEERIVY_burn` in Git Bash:
  `./avrdude.exe -C avrdude.conf -c usbasp -p m32 -B 32 -U flash:w:../CHEERIVY.hex:i`
  ("cannot set sck period" is normal; "cannot find USB device" = USBasp not plugged in / driver;
  "target does not answer" = wiring or power).
- Never write fuses, never use `avrdude -F`, never "Write All" in eXtreme Burner.
