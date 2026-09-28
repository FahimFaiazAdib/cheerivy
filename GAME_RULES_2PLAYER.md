# CHEERIVY: 2-Player Game Rules

Firmware: **`cheerivy2player.hex`** (no AI, no laptop needed). Goal lasers are **off** in this version.

---

## 1. Turning it on

1. Switch on the power (ATmega + 12 V).
2. You hear **one short beep**. The robot is ready and waiting.
3. **Either player presses their joystick button** to start.
4. **Countdown:** beep, beep, beep (3 s), then a **high "GO" tone**. The match starts.

**Self-test (optional):** hold **Player 1's button while powering on**. Player 2's carriage moves left and
right and its servo pushes once, then the same for Player 1. Use it to check that everything works
before playing.

---

## 2. Controls

| Joystick | Action |
|---|---|
| **Left / right** | Drive your carriage along your baseline |
| **Push up** | Your servo strikes the ball (**push**) |
| **Press the button** (click the stick) | Only used in **freeze duels** (section 4) and to **start** a match |

A push takes about 0.12 s out and 0.12 s back. You can push again **once the arm is back at rest**
(about 4 pushes per second at most). Holding the stick up repeats automatically.

| | Player 1 | Player 2 |
|---|---|---|
| Joystick left/right, up, button | pins 39, 37, 2 | pins 40, 38, 1 |
| Motor | TB6612 channel B | TB6612 channel A |
| Servo | pin 19 | pin 18 |

---

## 3. Match time

- **3 minutes** of play.
- **Last 10 seconds:** a **tick every second**.
- **Full time:** an **end tune** plays and both carriages stop.
- **Play again:** either player presses their button, and a new countdown starts.

---

## 4. Freeze duel

- At a **random moment every 20–25 seconds**, the buzzer plays **"da-da-da-DING"**.
- **Wait for the DING**, then **press your joystick button as fast as you can**.
- **The first press after the DING wins.** The **other player is frozen for 5 seconds**:
  - a **siren** plays
  - the frozen player **can't move or push**
  - a **short blip** means they're unfrozen
- **Pressing too early disqualifies you from that duel:**
  - pressing during the "da-da-da" (before the DING), **or**
  - pressing in the **1 second before** the duel sound started
- **Both press at exactly the same time:** the robot picks the winner at random.
- **Nobody presses within 4 seconds:** a **low tone** plays and the duel is cancelled.
- **No duels in the last 12 seconds**, so the ending stays fair.

---

## 5. Scoring

The **goal lasers are off**, so **the robot doesn't count goals**. The players count them:

- **Goal:** the ball crosses the **opponent's goal line** (the baseline behind their carriage).
- After a goal, **put the ball back in the centre**. The player who conceded serves.
- **After 3 minutes, whoever scored more wins.**
- **Draw: sudden death.** The next goal wins.

The restart and draw rules are table rules; the robot doesn't enforce them.

When the lasers are installed (`USE_LASERS 1` in `cheerivy2player.c`), the robot counts the goals,
plays a goal tune for each one, and announces the winner after the end tune.

---

## 6. Sounds

| Sound | Meaning |
|---|---|
| One short beep | Ready: press a button to start |
| 3 beeps + high tone | Countdown, then GO |
| **"da-da-da-DING"** | **Freeze duel**: press after the DING |
| Siren | Someone has just been frozen for 5 s |
| Short blip | The frozen player can move again |
| Low tone | Duel cancelled (nobody pressed) |
| Tick every second | Last 10 seconds |
| Long end tune | Full time |

---

## 7. Burning the firmware

- Burn **`cheerivy2player.hex`** with **Write → Flash only**. **Never "Write All"**: it also
  overwrites the fuse bits and can change the chip's clock.
- The chip must stay on its internal 8 MHz clock (**low fuse 0xE4**).
