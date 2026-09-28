# CHEERIVY — ATmega32 Pinout & Hardware Connection Diagram

**Project:** CHEERIVY — Microcontroller Dual-Striker Air Hockey Game  
**Target MCU:** ATmega32 (DIP-40 Package) @ Internal 8 MHz Clock  

---

## 1. ATmega32 (DIP-40) Master Pinout Diagram

```
                                      ATmega32 (DIP-40)
                                    ┌─────────▼─────────┐
         [P1 Joystick Freeze SW]PB0─│ 1               40│─ PA0 (ADC0) ── [P1 Joystick X-Axis: Steer Left/Right]
         [P2 Joystick Freeze SW]PB1─│ 2               39│─ PA1 (ADC1) ── [P2 Joystick X-Axis: Steer Left/Right]
                  [LCD 16x2 RS] PB2─│ 3               38│─ PA2 (ADC2) ── [P1 Joystick Y-Axis: Push UP Shoot]
                  [LCD 16x2 EN] PB3─│ 4               37│─ PA3 (ADC3) ── [P2 Joystick Y-Axis: Push UP Shoot]
                  [LCD 16x2 D4] PB4─│ 5 (SS)          36│─ PA4 ───────── [TB6612 STBY (Enable Both Motors)]
     [LCD 16x2 D5 / USBasp MOSI]PB5─│ 6 (MOSI)        35│─ PA5 ───────── (Leave Empty: No Wire)
     [LCD 16x2 D6 / USBasp MISO]PB6─│ 7 (MISO)        34│─ PA6 ───────── (Leave Empty: No Wire)
      [LCD 16x2 D7 / USBasp SCK]PB7─│ 8 (SCK)         33│─ PA7 ───────── (Leave Empty: No Wire)
        [10k to 5V / USBasp RST]RESET│ 9               32│─ AREF ──────── [5V Rail]
             [5V Rail / USBasp VCC]VCC 10              31│─ GND ───────── [GND Rail / USBasp GND]
             [GND Rail / USBasp GND]GND 11             30│─ AVCC ──────── [5V Rail]
         (Leave Empty: Internal 8MHz) 12 (XTAL2)       29│─ PC7 ───────── (Leave Empty: No Wire)
         (Leave Empty: Internal 8MHz) 13 (XTAL1)       28│─ PC6 ───────── (Leave Empty: No Wire)
        (Leave Empty: No Wire)   PD0─│ 14 (RXD)        27│─ PC5 ───────── (Leave Empty: No Wire)
        (Leave Empty: No Wire)   PD1─│ 15 (TXD)        26│─ PC4 ───────── [TB6612 PWMB (P2 Motor Speed)]
       [Laser Receiver A (P1)]   PD2─│ 16 (INT0)       25│─ PC3 ───────── [TB6612 BIN2 (P2 Motor Dir)]
       [Laser Receiver B (P2)]   PD3─│ 17 (INT1)       24│─ PC2 ───────── [TB6612 BIN1 (P2 Motor Dir)]
        [MG90S Servo 1 (P1)]     PD4─│ 18 (OC1B)       23│─ PC1 ───────── [TB6612 AIN2 (P1 Motor Dir)]
        [MG90S Servo 2 (P2)]     PD5─│ 19 (OC1A)       22│─ PC0 ───────── [TB6612 AIN1 (P1 Motor Dir)]
        [TB6612 PWMA (P1 Speed)] PD6─│ 20 (ICP1)       21│─ PD7 (OC2) ─── [Passive Buzzer / Speaker (+)]
                                    └───────────────────┘
```

---

## 2. All 40 Pins Sequential Lookup Table (Pin 1 to Pin 40)

| Pin # | Port Pin | Module / Component Pin | Description & Function |
|:---:|:---:|---|---|
| **1** | `PB0` | **P1 Joystick `SW` Pin** | Active-LOW Push Button for 3s Freeze Attack |
| **2** | `PB1` | **P2 Joystick `SW` Pin** | Active-LOW Push Button for 3s Freeze Attack |
| **3** | `PB2` | **LCD 16x2 `RS` (Pin 4)** | Register Select (0 = Command, 1 = Data) |
| **4** | `PB3` | **LCD 16x2 `EN` (Pin 6)** | Enable Strobe Pulse |
| **5** | `PB4` | **LCD 16x2 `D4` (Pin 11)** | 4-bit Data Line 4 |
| **6** | `PB5` | **LCD 16x2 `D5` (Pin 12) & USBasp `MOSI`** | 4-bit Data Line 5 / ISP MOSI |
| **7** | `PB6` | **LCD 16x2 `D6` (Pin 13) & USBasp `MISO`** | 4-bit Data Line 6 / ISP MISO |
| **8** | `PB7` | **LCD 16x2 `D7` (Pin 14) & USBasp `SCK`** | 4-bit Data Line 7 / ISP SCK |
| **9** | `RESET`| **10k Resistor to 5V & USBasp `RST`** | Reset Circuit (Pull-Up) |
| **10**| `VCC` | **`+5V` Power Rail** | Microcontroller Main VCC |
| **11**| `GND` | **`GND` Power Rail** | Microcontroller Main Ground |
| **12**| `XTAL2`| **Leave Empty (খালি)** | Internal 8 MHz RC Oscillator Mode |
| **13**| `XTAL1`| **Leave Empty (খালি)** | Internal 8 MHz RC Oscillator Mode |
| **14**| `PD0` | **Leave Empty (খালি)** | Unused UART RXD |
| **15**| `PD1` | **Leave Empty (খালি)** | Unused UART TXD |
| **16**| `PD2` | **Laser Receiver A `OUT`** | INT0 Interrupt (P1 Goal Line) |
| **17**| `PD3` | **Laser Receiver B `OUT`** | INT1 Interrupt (P2 Goal Line) |
| **18**| `PD4` | **MG90S Servo 1 Signal (Orange)** | Timer1 OC1B 50 Hz PWM (Player 1 Kicker) |
| **19**| `PD5` | **MG90S Servo 2 Signal (Orange)** | Timer1 OC1A 50 Hz PWM (Player 2 Kicker) |
| **20**| `PD6` | **TB6612 `PWMA` Pin** | Player 1 Motor Speed / Enable |
| **21**| `PD7` | **Passive Buzzer Positive (+)** | Timer2 OC2 Tone & Siren Output |
| **22**| `PC0` | **TB6612 `AIN1` Pin** | Player 1 Motor Direction 1 |
| **23**| `PC1` | **TB6612 `AIN2` Pin** | Player 1 Motor Direction 2 |
| **24**| `PC2` | **TB6612 `BIN1` Pin** | Player 2 Motor Direction 1 *(JTAG TCK - Disabled in SW)* |
| **25**| `PC3` | **TB6612 `BIN2` Pin** | Player 2 Motor Direction 2 *(JTAG TMS - Disabled in SW)* |
| **26**| `PC4` | **TB6612 `PWMB` Pin** | Player 2 Motor Speed / Enable *(JTAG TDO - Disabled in SW)* |
| **27**| `PC5` | **Leave Empty (খালি)** | Spare GPIO *(JTAG TDI)* |
| **28**| `PC6` | **Leave Empty (খালি)** | Spare GPIO |
| **29**| `PC7` | **Leave Empty (খালি)** | Spare GPIO |
| **30**| `AVCC`| **`+5V` Power Rail** | ADC Power Supply (Must connect to 5V) |
| **31**| `GND` | **`GND` Power Rail** | Analog Ground (Must connect to GND) |
| **32**| `AREF`| **`+5V` Power Rail** | ADC Reference Voltage |
| **33**| `PA7` | **Leave Empty (খালি)** | Spare ADC7 |
| **34**| `PA6` | **Leave Empty (খালি)** | Spare ADC6 |
| **35**| `PA5` | **Leave Empty (খালি)** | Spare ADC5 |
| **36**| `PA4` | **TB6612 `STBY` Pin** | Motor Driver Standby (HIGH = Enable Drivers) |
| **37**| `PA3` | **P2 Joystick `VRY` (Y-Axis)** | ADC3: Push UP (Y > 650) to Shoot P2 Ball |
| **38**| `PA2` | **P1 Joystick `VRY` (Y-Axis)** | ADC2: Push UP (Y > 650) to Shoot P1 Ball |
| **39**| `PA1` | **P2 Joystick `VRX` (X-Axis)** | ADC1: Steer P2 Left (X < 350) / Right (X > 650) |
| **40**| `PA0` | **P1 Joystick `VRX` (X-Axis)** | ADC0: Steer P1 Left (X < 350) / Right (X > 650) |

---

## 3. Module-by-Module Wiring Checklist

### A. 16×2 Character LCD (HD44780, 4-Bit Mode)
| LCD Pin # | LCD Pin Label | Connected To | Description |
|:---:|:---:|:---|:---|
| **1** | `VSS` | **GND Rail** | LCD Ground |
| **2** | `VDD` | **`+5V` Rail** | LCD Power |
| **3** | `V0` | **GND Rail** (or 10k pot wiper) | Contrast |
| **4** | `RS` | **ATmega32 Pin 3 (`PB2`)** | Register Select |
| **5** | `RW` | **GND Rail** | Read/Write (Write Mode) |
| **6** | `E` | **ATmega32 Pin 4 (`PB3`)** | Enable Pulse |
| **7..10** | `D0`..`D3` | **Leave Empty (খালি)** | Not used in 4-bit mode |
| **11** | `D4` | **ATmega32 Pin 5 (`PB4`)** | Data Bit 4 |
| **12** | `D5` | **ATmega32 Pin 6 (`PB5`)** | Data Bit 5 |
| **13** | `D6` | **ATmega32 Pin 7 (`PB6`)** | Data Bit 6 |
| **14** | `D7` | **ATmega32 Pin 8 (`PB7`)** | Data Bit 7 |
| **15** | `A` (LED+) | **`+5V` Rail** | Backlight Anode |
| **16** | `K` (LED-) | **GND Rail** | Backlight Cathode |

---

### B. TB6612FNG Dual DC Motor Driver
| TB6612 Pin | Connected To | Role / Description |
|---|---|---|
| `VM` | **12V DC Rail** | Motor Driving Power |
| `VCC` | **`+5V` Rail** | Logic Supply Power |
| `GND` | **GND Rail** | Common Ground |
| `STBY` | **ATmega32 Pin 36 (`PA4`)** | Standby Pin (HIGH = Enable Driver) |
| `AIN1` | **ATmega32 Pin 22 (`PC0`)** | Player 1 Motor Direction 1 |
| `AIN2` | **ATmega32 Pin 23 (`PC1`)** | Player 1 Motor Direction 2 |
| `PWMA` | **ATmega32 Pin 20 (`PD6`)** | Player 1 Motor Speed / Enable |
| `AO1`, `AO2` | **Player 1 N20 Motor** | Left/Right Striker 1 |
| `BIN1` | **ATmega32 Pin 24 (`PC2`)** | Player 2 Motor Direction 1 |
| `BIN2` | **ATmega32 Pin 25 (`PC3`)** | Player 2 Motor Direction 2 |
| `PWMB` | **ATmega32 Pin 26 (`PC4`)** | Player 2 Motor Speed / Enable |
| `BO1`, `BO2` | **Player 2 N20 Motor** | Left/Right Striker 2 |

---

### C. Joysticks (2-Axis + Push Button)
| Joystick | Pin Name | Connected To | Role |
|---|---|---|---|
| **P1 Joystick** | `VCC` / `GND` | `+5V` / `GND` Rails | Power |
| | `VRX` | **ATmega32 Pin 40 (`PA0`)** | Left $\leftrightarrow$ Right Steer |
| | `VRY` | **ATmega32 Pin 38 (`PA2`)** | Push UP Shoot Strike |
| | `SW` | **ATmega32 Pin 1 (`PB0`)** | 3-Second Freeze Attack Button |
| **P2 Joystick** | `VCC` / `GND` | `+5V` / `GND` Rails | Power |
| | `VRX` | **ATmega32 Pin 39 (`PA1`)** | Left $\leftrightarrow$ Right Steer |
| | `VRY` | **ATmega32 Pin 37 (`PA3`)** | Push UP Shoot Strike |
| | `SW` | **ATmega32 Pin 2 (`PB1`)** | 3-Second Freeze Attack Button |

---

### D. Servos & Audio
| Component | Pin / Wire | Connected To | Role |
|---|---|---|---|
| **P1 MG90S Servo** | Red / Brown | `+5V` / `GND` Rails | Dedicated 5V Servo Power |
| | Orange (Signal)| **ATmega32 Pin 18 (`PD4`)** | Strike Flipper 1 |
| **P2 MG90S Servo** | Red / Brown | `+5V` / `GND` Rails | Dedicated 5V Servo Power |
| | Orange (Signal)| **ATmega32 Pin 19 (`PD5`)** | Strike Flipper 2 |
| **Passive Buzzer** | Positive (+) | **ATmega32 Pin 21 (`PD7`)** | CTC Square-Wave Tone & Siren |
| | Negative (-) | **GND Rail** | Ground |

---

### E. KY-008 Laser Emitters & Receivers
| Module | Pin | Connected To | Role |
|---|---|---|---|
| **KY-008 Laser 1 & 2** | `S` (Signal) | **`+5V` Rail** | Constant 5V Beam |
| | `-` (Minus) | **GND Rail** | Ground |
| | Middle Pin | **Leave Empty (খালি)** | Unconnected |
| **Laser Receiver A** | `+` / `-` / `OUT` | `+5V` / `GND` / **Pin 16 (`PD2`)** | P1 Goal Line Gate |
| **Laser Receiver B** | `+` / `-` / `OUT` | `+5V` / `GND` / **Pin 17 (`PD3`)** | P2 Goal Line Gate |

---

## 4. USBasp In-System Programming (ISP) Header Connection

```
     USBasp 10-Pin Header (Top View)          ATmega32 (DIP-40) Pin
     ┌────────────────────────────┐
     │  MOSI (1)  ●   ● (2) VCC   │ ───►  MOSI (Pin 6 / PB5)  |  VCC (Pin 10)
     │    NC (3)  ●   ● (4) GND   │ ───►   NC                 |  GND (Pin 11)
     │ RESET (5)  ●   ● (6) GND   │ ───►  RESET (Pin 9)       |  GND (Pin 11)
     │   SCK (7)  ●   ● (8) GND   │ ───►   SCK (Pin 8 / PB7)  |  GND (Pin 11)
     │  MISO (9)  ●   ● (10) GND  │ ───►  MISO (Pin 7 / PB6)  |  GND (Pin 11)
     └────────────────────────────┘
```

### AVR Fuse Settings & Flash Command:
```bash
avrdude -c usbasp -p m32 -U lfuse:w:0xe4:m -U hfuse:w:0xc9:m -U flash:w:cheerivy.hex:i
```
