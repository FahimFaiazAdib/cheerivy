@echo off
REM ============================================================
REM  CHEERIVY - burn firmware to ATmega32 with USBasp
REM  Double-click this file. Everything it needs is in this folder.
REM
REM  BEFORE RUNNING:
REM   - USBasp plugged into this PC (driver: Zadig -> libusbK or libusb-win32)
REM   - USBasp: yellow cap on 5V, nothing on JP2
REM   - ATmega wired: MOSI->6  MISO->7  SCK->8  RST->9  GND->11 (+31)
REM   - Power: USBasp VCC->10 (+30)  OR  5V charger (then NO USBasp VCC wire)
REM   - GND shared between USBasp, ATmega and charger. 12V supply OFF.
REM ============================================================
cd /d "%~dp0"

echo.
echo ===== STEP 1: check the connection (read only, safe) =====
echo Good: "Device signature = 0x1e9502"
echo.
avrdude -c usbasp -p m32 -B 32
if errorlevel 1 (
  echo.
  echo *** STEP 1 FAILED. Take a screenshot of this window and send it. ***
  echo     "could not find USB device"  = driver problem ^(Zadig^)
  echo     "target doesn't answer"      = wiring / GND / power / clock problem
  echo.
  pause
  exit /b 1
)

echo.
echo ===== STEP 2: read the fuses (read only, safe) =====
echo Expected lfuse = 0xe4. Write down both values.
echo.
avrdude -c usbasp -p m32 -B 32 -U lfuse:r:-:h -U hfuse:r:-:h

echo.
echo ===== STEP 3: burn the firmware =====
echo Press any key to burn, or close this window to stop.
pause
avrdude -c usbasp -p m32 -B 32 -U flash:w:CHEERIVY.hex:i
echo.
echo Good result: "... bytes of flash verified". Fuses were NOT touched.
pause
