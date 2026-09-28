# CHEERIVY — Project Build Plan (v3.1: Self-Propelled Wheeled Carriage & Dual-Gate AI Duel)

**Course:** CSE316, BUET, Section C  
**Team:** Tahmid Khan (2205159) · Atik Khan (2205171) · Fahim Faiaz Adib (2205177)  
**Target MCU:** Single ATmega32 (DIP-40) @ Internal 8 MHz Clock  
**Document Version:** 3.1 (Official Build Specification). Updated with Self-Propelled On-Board N20 Wheeled Carriages, MG90S Flipper Servos, Dynamic Gate Bar, Dual Horizontal Sensor Gates (Gate 1 & 2), 16x2 Character LCD, Single-Ball Duel, and Native ATmega32 AI Automation.  
**Status:** Core mechanical drive upgraded & verified. Ready for full integration and dual-gate trajectory AI testing.

---

## Table of Contents

1. [What We Are Building](#1-what-we-are-building)
2. [Hardware Evolution & Architectural Decisions](#2-hardware-evolution--architectural-decisions)
3. [Mechanical Design: Self-Propelled Wheeled Carriages](#3-mechanical-design-self-propelled-wheeled-carriages)
4. [Game Rules (Single-Ball Duel)](#4-game-rules-single-ball-duel)
5. [Dual-Gate Trajectory & Velocity AI Architecture](#5-dual-gate-trajectory--velocity-ai-architecture)
6. [Master Electronics & Pin Map (Single ATmega32)](#6-master-electronics--pin-map-single-atmega32)
7. [Team Division of Labor](#7-team-division-of-labor)
8. [Technical Risks & Mitigations](#8-technical-risks--mitigations)
9. [Progress Log](#9-progress-log)

---

## 1. What We Are Building

**CHEERIVY** is a **two-player, face-to-face arcade robotic disc/ball duel** on a flat ~40–60 cm arena with real-time physical motorized self-propelled carriages, fast servo striking flippers, dynamic obstacles, and zero wireless latency.

- **Two Players:** Face-to-face setup (Player 1 Human bottom, Player 2 Human/AI top).
- **Self-Propelled Wheeled Carriages:** Each striker carriage houses its own **N20 DC gear motor and rubber drive wheel inside the carriage chassis**, rolling directly along the baseline track. This replaces old external belt-pulley setups with higher top speed, instant acceleration, and zero belt slipping.
- **Physical Controls:**
  1. **Steer:** Tilt joystick left/right (VRX) to drive the wheeled carriage along the baseline.
  2. **Shoot:** Push joystick UP (VRY > 650) to snap the rapid **MG90S Metal-Gear Servo Flipper**, launching the ball across the arena.
  3. **Freeze Attack:** Press the **Joystick thumb button (SW)** to trigger a 3-second motor stun on the opponent (15-second cooldown).
- **Dynamic Middle Obstacle:** A moving gate bar with gaps sweeps across the center of the field, requiring players to time shots through the openings.
- **Single Ball Rally:** Exactly 1 high-visibility ball/disc is in active play.
- **Scoring & Audio:** Laser break-beams connected to ATmega32 External Interrupts (`INT0` on `PD2` / `INT1` on `PD3`) register goals with microsecond response, trigger distinct buzzer tones, and update the live **16×2 Character LCD** scoreboard (180s countdown).
- **Dual-Mode System:**
  * **2-Player Mode:** Human vs Human via dual KY-023 joysticks.
  * **AI Duel Mode:** Human vs ATmega32 Autonomous Laser AI.

```
                          PLAYER 2 (AI END)
       ┌─────────────────────────────────────────────────────────────┐
       │             [P2 ON-BOARD WHEELED CARRIAGE + MG90S]          │
       │                                                             │
       │ (•)   (•)   (•)   (•)   (•)   (•)   (•)   (•)   (•)   GATE 2│ ← Y2 Sensor Line
       │                                                             │
       │ (•)   (•)   (•)   (•)   (•)   (•)   (•)   (•)   (•)   GATE 1│ ← Y1 Sensor Line
       │ ▀▀▀▀▀▀▀▀▀▀▀▀▀        ▀▀▀▀▀▀▀▀▀▀▀▀▀        ▀▀▀▀▀▀▀▀▀▀▀▀▀▀    │ ← Moving Gate Bar
       │                                                             │
       │                       ● (Single Ball)                       │
       │                                                             │
       │E ~~~~~~~~~~~~~~~~~~~~~ laser A ~~~~~~~~~~~~~~~~~~~~~~~~~~~~R│ ← P1 Goal Line (INT0)
       │                                                             │
       │             [P1 ON-BOARD WHEELED CARRIAGE + MG90S]          │
       └─────────────────────────────────────────────────────────────┘
                          PLAYER 1 (HUMAN END)
```

---

## 2. Hardware Evolution & Architectural Decisions

| Component | Initial Proposal | Iteration v2 (Belt-Pulley) | Final Build (v3.1 Verified) | Engineering Rationale |
|---|---|---|---|---|
| **Carriage Motion** | Fixed Pivot Striker | Stationary N20 + Timing Belt & Pulley | **Self-Propelled On-Board N20 Motor & Wheel** | Belt tensioning caused drag and slipping; internal wheel drive gives instant torque, higher linear speed, and rock-solid reliability. |
| **Ball Launcher** | Solenoid (5N) | Solenoid (12V) | **MG90S Metal-Gear Micro Servo** | Solenoids lacked reach and drew high inrush current; MG90S delivers 2.2 kg·cm crisp snap with direct 50Hz PWM control. |
| **Player Input** | HC-05 Phone App | Touch Sensors | **2× KY-023 Analog Joysticks** | 0 ms ADC reading, no Bluetooth disconnects or pairing lag. |
| **Scoreboard** | MAX7219 Dot Matrix | MAX7219 Matrix | **16×2 Character LCD (4-Bit Mode)** | Crystal clear match time, player scores, freeze cooldowns, and mode indicators without consuming SPI pins. |
| **System Clock** | 16 MHz Crystal | 16 MHz Crystal | **Internal 8 MHz RC Oscillator** | Eliminates crystal/load capacitor failures and frees pins for GPIO. |
| **AI Sensing** | Overhead Camera + OpenCV | Bluetooth Commands | **Dual-Gate Horizontal Array (Gate 1 & 2)** | Sub-millisecond optical sensing natively on ATmega32 with real-time trajectory and velocity math. |

---

## 3. Mechanical Design: Self-Propelled Wheeled Carriages

### 3.1 On-Board Motor & Wheel Assembly
* **Chassis:** Compact 3D-printed / lightweight PVC carriage box riding on a linear guide rail or smooth slot channel.
* **Actuator Placement:** The **N20 micro metal gear motor (12V)** is housed **directly inside the carriage body**.
* **Direct Traction:** The N20 output shaft directly drives a **high-grip rubber wheel (34 mm / 43 mm diameter)** contacting the baseline track.
* **Advantages over Belt-Pulley:**
  1. **Zero Mechanical Backlash:** No belt slack, tooth skipping, or belt stretch over time.
  2. **High Linear Velocity:** Reaches $>30\text{ cm/s}$ rapidly across the 40 cm width.
  3. **Simplified Frame:** No end-bearing idler pulleys or tensioner brackets needed on the arena side walls.

### 3.2 Flipper Striker
* **Actuator:** **MG90S Metal-Gear Micro Servo** mounted rigidly on top of the moving carriage.
* **Striking Pad:** Acrylic/PVC arm with high-density EVA foam pad.
* **Strike Motion:** Fast $90\text{ ms}$ snap ($43^\circ \to 160^\circ \to 43^\circ$) delivering repeatable high-speed shots.

---

## 4. Game Rules (Single-Ball Duel)

1. **Match Time:** Standard 3-minute (180 seconds) countdown displayed live on the 16x2 LCD.
2. **Start:** 1 single ball/disc is placed in the center of the arena.
3. **Point Scoring:** +1 point each time a player shoots the ball through the moving gate gaps past the opponent's flipper into their goal line.
4. **Freeze Attack:** Clicking the joystick thumb button triggers a 3-second motor freeze stun on the opponent's carriage (15-second cooldown).
5. **Win Condition:** Higher score when match timer hits 0:00 wins. Equal points triggers sudden death.

---

## 5. Dual-Gate Trajectory & Velocity AI Architecture

```
     ▀▀▀▀▀▀▀▀▀▀▀▀▀        ▀▀▀▀▀▀▀▀▀▀▀▀▀        ▀▀▀▀▀▀▀▀▀▀▀▀▀▀ [Moving Gate Bar]
     ────────────────────────────────────────────────────────
     (•)   (•)   (•)   (•)   (🟠)   (•)   (•)   (•)   (•)    GATE 1 (X1, Time t1)
                               \
     ───────────────────────────\────────────────────────────
     (•)   (•)   (•)   (•)   (•) \ (🟠)   (•)   (•)   (•)    GATE 2 (X2, Time t2)
                                   \
                                    ▼
                             ┌──────────────┐
                             │  AI CARRIAGE │                  AI END
                             └──────────────┘
```

### The Real-Time Math Executed on ATmega32:
1. **Entry Point & Time:** Ball passes Gate 1 at column $X_1$ and timestamp $t_1$.
2. **Vector Point & Time:** Ball passes Gate 2 at column $X_2$ and timestamp $t_2$.
3. **Forward Velocity:** $V_y = \frac{D_{\text{gate}}}{t_2 - t_1}$
4. **Target Intercept Prediction:**
   $$X_{\text{intercept}} = X_2 + \left(\frac{X_2 - X_1}{D_{\text{gate}}}\right) \times D_{\text{to\_carriage}}$$
5. **Carriage Action:** Drive the self-propelled AI wheeled carriage directly to $X_{\text{intercept}}$ and trigger `fire_servo2()` exactly when the ball reaches the flipper.

---

## 6. Master Electronics & Pin Map (Single ATmega32)

*Fully verified with [`CHEERIVY_Master_Wiring_and_Firmware_Guide.md`](file:///Users/fahimfaiazadib/Downloads/microcontroller/CHEERIVY_Master_Wiring_and_Firmware_Guide.md).*

| Function | Pin Name | DIP Pin # | Description / Circuit Notes |
|---|---|---|---|
| **P1 Freeze Attack SW** | `PB0` | Pin 1 | Active-LOW digital input (Internal pull-up enabled) |
| **P2 Freeze Attack SW** | `PB1` | Pin 2 | Active-LOW digital input (Internal pull-up enabled) |
| **LCD 16x2 RS** | `PB2` | Pin 3 | Register Select |
| **LCD 16x2 EN** | `PB3` | Pin 4 | Enable Strobe Pulse |
| **LCD 16x2 D4..D7** | `PB4..PB7` | Pins 5..8 | 4-bit Data Lines |
| **TB6612 AIN1 / AIN2** | `PC0 / PC1` | Pins 22 / 23 | Player 1 Wheeled Carriage Motor Direction |
| **TB6612 BIN1 / BIN2** | `PC2 / PC3` | Pins 24 / 25 | Player 2 Wheeled Carriage Motor Direction |
| **TB6612 PWMB** | `PC4` | Pin 26 | Player 2 Carriage Motor Speed / Enable |
| **Laser Receiver A (P1 Goal)** | `PD2 (INT0)` | Pin 16 | External Interrupt 0 (Falling edge on goal) |
| **Laser Receiver B (P2 Goal)** | `PD3 (INT1)` | Pin 17 | External Interrupt 1 (Falling edge on goal) |
| **Servo 1 Flipper (P1)** | `PD4 (OC1B)` | Pin 18 | Timer1 Fast PWM 50Hz (P1 Strike) |
| **Servo 2 Flipper (P2)** | `PD5 (OC1A)` | Pin 19 | Timer1 Fast PWM 50Hz (P2 Strike) |
| **TB6612 PWMA** | `PD6` | Pin 20 | Player 1 Carriage Motor Speed / Enable |
| **Passive Buzzer** | `PD7 (OC2)` | Pin 21 | Timer2 CTC square-wave tone generation |
| **TB6612 STBY** | `PA4` | Pin 36 | Motor Driver Enable (HIGH = Run Both Motors) |
| **P2 Joystick Y-Axis (Shoot)** | `PA3 (ADC3)` | Pin 37 | Analog In: Push UP (Y > 650) to Strike |
| **P1 Joystick Y-Axis (Shoot)** | `PA2 (ADC2)` | Pin 38 | Analog In: Push UP (Y > 650) to Strike |
| **P2 Joystick X-Axis (Steer)** | `PA1 (ADC1)` | Pin 39 | Analog In: Left (X < 350) / Right (X > 650) |
| **P1 Joystick X-Axis (Steer)** | `PA0 (ADC0)` | Pin 40 | Analog In: Left (X < 350) / Right (X > 650) |

---

## 7. Team Division of Labor

| Member | Focus Area | Primary Modules |
|---|---|---|
| **Tahmid Khan** | Mechanics, Power Rails (12V/5V LM2596), Wheeled Carriage Chassis, Arena Build | Self-Propelled Carriages, Power Distribution, Chassis |
| **Atik Khan** | Optical Sensing, 16x2 LCD, Audio Tone Synthesis, Arena Calibration | Goal & Gate Sensors, Display, Audio Feedback |
| **Fahim Faiaz Adib** | Firmware Architecture, Timer1 50Hz Servo PWM, Dual Joystick ADC, AI Trajectory State Machine | Core Game Engine, Trajectory Math, Integration |

---

## 8. Progress Log

| Date | Milestone / Technical Decision |
|---|---|
| 22 Aug 2026 | Initial components purchased. |
| 11 Sep 2026 | Game layout transitioned to face-to-face duel with moving gate. |
| 16 Sep 2026 | Replaced weak solenoids with MG90S metal-gear servo flippers; dropped Bluetooth for native analog joysticks. |
| 24 Sep 2026 | **Mechanical Upgrade (v3.1):** Replaced stationary belt-pulley system with **Self-Propelled On-Board N20 Wheeled Carriages**. Greatly increased linear speed and eliminated belt slipping. |
| 27 Sep 2026 | **AI Architecture Finalized:** Transitioned from OpenCV to **Dual-Gate Horizontal Array (Gate 1 & 2)** for real-time trajectory vector and velocity calculation natively on single ATmega32. |
