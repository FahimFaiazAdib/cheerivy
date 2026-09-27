# cheerivy

CHEERIVY robotic duel — ATmega32 firmware.

**`CHEERIVY_v4.hex`** — burn this onto the ATmega32 (internal 8 MHz) with a USBasp.
Do NOT change the fuses.

- Human player: joystick (pins 39/37/2), motor channel B, solenoid on pin 19
- AI player: motor channel A, servo on pin 18, controlled by the laptop camera via HC-05,
  or Mirror AI when the laptop is not connected
- Hold the freeze button while powering on = self-test
