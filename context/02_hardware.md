# Hardware

**MCU:** ATmega32, internal RC oscillator at **8 MHz** (fuses already set; never change them).
Pin numbers are the DIP-40 package.

| Function | Pin | Notes |
|---|---|---|
| Joystick 1 X / Y | PA1 (39) / PA3 (37) | player 1; Y > 650 = forward = strike |
| Joystick 1 button (push-in) | PB1 (2) | buzzer / freeze; skip commentary |
| Joystick 2 X / Y | PA0 (40) / PA2 (38) | player 2 in 2 PLAYERS and debug |
| Joystick 2 button | PB0 (1) | |
| TB6612 STBY | PA4 (36) | high = driver on |
| Motor A (AI side / player 2) | AIN1 PC0 (22), AIN2 PC1 (23), PWMA PD6 (20) | full speed or stop (coast) |
| Motor B (player 1) | BIN1 PC2 (24), BIN2 PC3 (25), PWMB PC4 (26) | full speed or stop (coast) |
| Servo, AI side / player 2 | PD4 = OC1B (18) | MG90S |
| Servo, player 1 | PD5 = OC1A (19) | MG90S |
| Buzzer | PD7 (21) | Timer2 tones |
| HC-05 Bluetooth | RXD PD0 (14), TXD PD1 (15) | 9600 baud; Atiq's PC sees it as **COM10** |
| DFPlayer (robot speaker) | RX via 1 kΩ from PA5 (35) | PAM8610 amp, 12 V |
| Laser receiver, player 1's goal line | PD2 / INT0 (16) | **not wired yet** |
| Laser receiver, AI's goal line | PD3 / INT1 (17) | **not wired yet** |
| USBasp (programming) | MOSI 6, MISO 7, SCK 8, RST 9, GND 11 | |

## Servos
- Both driven by Timer1 fast PWM (mode 14, 50 Hz, 1 µs ticks): pulse = 600 + 10 × degrees µs.
- Firmware defaults: AI side rest 87°, strike 20° (67° swing); player 1 rest 97°, strike 56° (41°).
  The laptop can change them live (Settings › Servo tuning) and they are saved in EEPROM and in
  `cheerivy_ai/servo_angles.json` on the laptop (burning erases the EEPROM; the laptop resends them).
- A strike = go to the strike angle, wait `swing × 1.6 ms + 15 ms`, go back; ready again after twice
  that. With player 1's short 41° swing the arm gets only ~80 ms and often turns back halfway:
  a bigger swing (e.g. 67°, like player 2) gives it the same time as player 2.
- Player 1's servo has had real hardware trouble (no power at first, stalling mid-swing). Suspects:
  a weak 5 V supply, a loose signal/ground wire, a worn servo. Advice given: servos on their own 5–6 V
  ≥ 2 A supply, common ground, a 470–1000 µF capacitor across the servo power near the servos,
  swap the two servos to see whether the fault follows the servo.

## Camera
- A phone through the **Iriun** webcam app, placed at the side of player 2's end, looking down at an
  angle. The software turns it into a flat top-down view (calibration), so any angle works as long
  as all four board corners are visible. Raised things (the tape on the carriages) look shifted
  towards the far side from an angle.
