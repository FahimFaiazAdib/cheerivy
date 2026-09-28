# CHEERIVY — Master Build, Wiring & Firmware Guide

**Course:** CSE316, BUET, Section C  
**Team:** Tahmid Khan (2205159) · Atik Khan (2205171) · Fahim Faiaz Adib (2205177)  
**System:** Single ATmega32 @ Internal 8 MHz Clock (`lfuse=0xE4`, `hfuse=0xC9`), Dual Independent Self-Propelled N20 Wheeled Striker Carriages (TB6612 Dual Drive), Dual MG90S Metal-Gear Servo Kickers, 2-Axis Joysticks with 3-Second Freeze Attack, Dual-Gate Horizontal Trajectory AI Grid, 16x2 Character LCD Scoreboard, and Passive Buzzer Audio.

---

## 1. Complete ATmega32 (DIP-40) Master Pinout Diagram

> 💡 **নোট:** বাম পাশের পিনগুলোর বর্ণনা বাম পাশে এবং ডান পাশের পিনগুলোর বর্ণনা ডান পাশে সুস্পষ্টভাবে দেওয়া হয়েছে। যেগুলোতে **`(Leave Empty)`** লেখা আছে, সেগুলো ব্রেডবোর্ডে সম্পূর্ণ **ফাঁকা / খালি** থাকবে।

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

| Pin # | Port Pin | Connects To (Module / Rail) | Description / Notes |
|:---:|:---:|---|---|
| **1** | `PB0` | **P1 Joystick `SW` Pin** | Active-LOW Thumb Button for 3s Freeze Attack |
| **2** | `PB1` | **P2 Joystick `SW` Pin** | Active-LOW Thumb Button for 3s Freeze Attack |
| **3** | `PB2` | **LCD 16x2 `RS` (Pin 4)** | LCD Register Select (0 = Command, 1 = Data) |
| **4** | `PB3` | **LCD 16x2 `EN` (Pin 6)** | LCD Enable Strobe Pulse |
| **5** | `PB4` | **LCD 16x2 `D4` (Pin 11)** | LCD 4-bit Data Line 4 |
| **6** | `PB5` | **LCD 16x2 `D5` (Pin 12) & USBasp `MOSI`** | LCD 4-bit Data Line 5 |
| **7** | `PB6` | **LCD 16x2 `D6` (Pin 13) & USBasp `MISO`** | LCD 4-bit Data Line 6 |
| **8** | `PB7` | **LCD 16x2 `D7` (Pin 14) & USBasp `SCK`** | LCD 4-bit Data Line 7 |
| **9** | `RESET`| **10k Resistor to 5V & USBasp `RST`** | Reset Circuit (Pull-up) |
| **10**| `VCC` | **`+5V` Power Rail** | Microcontroller Main Power |
| **11**| `GND` | **`GND` Power Rail** | Microcontroller Ground |
| **12**| `XTAL2`| **খালি (Leave Empty)** | Internal 8 MHz মোডে কোনো তার লাগবে না |
| **13**| `XTAL1`| **খালি (Leave Empty)** | Internal 8 MHz মোডে কোনো তার লাগবে না |
| **14**| `PD0` | **খালি (Leave Empty)** | UART RXD (Unused) |
| **15**| `PD1` | **খালি (Leave Empty)** | UART TXD (Unused) |
| **16**| `PD2` | **Laser Receiver A `OUT`** | External Interrupt INT0 (Player 1 Side) |
| **17**| `PD3` | **Laser Receiver B `OUT`** | External Interrupt INT1 (Player 2 Side) |
| **18**| `PD4` | **MG90S Servo 1 Signal (Orange Wire)** | 50Hz PWM Signal for Player 1 Flipper |
| **19**| `PD5` | **MG90S Servo 2 Signal (Orange Wire)** | 50Hz PWM Signal for Player 2 Flipper |
| **20**| `PD6` | **TB6612 `PWMA` Pin** | Player 1 Carriage Motor Speed / Enable |
| **21**| `PD7` | **Passive Buzzer Positive (+)** | Timer2 CTC Square-Wave Tone Output |
| **22**| `PC0` | **TB6612 `AIN1` Pin** | Player 1 Motor Direction Pin 1 |
| **23**| `PC1` | **TB6612 `AIN2` Pin** | Player 1 Motor Direction Pin 2 |
| **24**| `PC2` | **TB6612 `BIN1` Pin** | Player 2 Motor Direction Pin 1 |
| **25**| `PC3` | **TB6612 `BIN2` Pin** | Player 2 Motor Direction Pin 2 |
| **26**| `PC4` | **TB6612 `PWMB` Pin** | Player 2 Carriage Motor Speed / Enable |
| **27**| `PC5` | **খালি (Leave Empty)** | Spare GPIO |
| **28**| `PC6` | **খালি (Leave Empty)** | Spare GPIO |
| **29**| `PC7` | **খালি (Leave Empty)** | Spare GPIO |
| **30**| `AVCC`| **`+5V` Power Rail** | ADC Power Supply |
| **31**| `GND` | **`GND` Power Rail** | Analog Ground |
| **32**| `AREF`| **`+5V` Power Rail** | ADC Reference Voltage |
| **33**| `PA7` | **খালি (Leave Empty)** | Spare ADC7 |
| **34**| `PA6` | **খালি (Leave Empty)** | Spare ADC6 |
| **35**| `PA5` | **খালি (Leave Empty)** | Spare ADC5 |
| **36**| `PA4` | **TB6612 `STBY` Pin** | Motor Driver Enable (HIGH = Run Both Motors) |
| **37**| `PA3` | **P2 Joystick `VRY` (Y-Axis)** | Analog In: Push UP (Y > 650) to Shoot P2 Ball |
| **38**| `PA2` | **P1 Joystick `VRY` (Y-Axis)** | Analog In: Push UP (Y > 650) to Shoot P1 Ball |
| **39**| `PA1` | **P2 Joystick `VRX` (X-Axis)** | Analog In: Steer P2 Motor Left (X < 350) $\leftrightarrow$ Right (X > 650) |
| **40**| `PA0` | **P1 Joystick `VRX` (X-Axis)** | Analog In: Steer P1 Motor Left (X < 350) $\leftrightarrow$ Right (X > 650) |

---

## 3. USBasp In-System Programming (ISP) Header Connection

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

### AVR Fuse Settings (Internal 8 MHz Clock):
* **Low Fuse (`lfuse`):** `0xE4` *(Internal 8 MHz RC Oscillator)*
* **High Fuse (`hfuse`):** `0xC9` *(JTAG disabled, SPI enabled)*

```bash
avrdude -c usbasp -p m32 -U lfuse:w:0xe4:m -U hfuse:w:0xc9:m
```

> ⚠️ **IMPORTANT (Pin 26 / PC4 & JTAG Issue):**  
> On ATmega32, **Pin 24 (PC2), Pin 25 (PC3), Pin 26 (PC4), and Pin 27 (PC5)** are mapped to the on-chip JTAG debugger by default (`JTAGEN` fuse active).  
> When JTAG is active, the chip locks **Pin 26 (`TDO` / `PC4`)** and prevents standard GPIO output, causing **Player 2 Motor (`PWMB`) to not work**.  
> The firmware includes `MCUCSR = (1 << JTD); MCUCSR = (1 << JTD);` in `init_all()` to disable JTAG in software and release Pin 26 for normal GPIO operation. Setting `hfuse=0xC9` also permanently disables JTAG.

---

## 4. Power & Driver Connections

| Subsystem | Module Pin | Connected to ATmega32 / Power | Description / Role |
|---|---|---|---|
| **Power Input** | 12V DC Adapter (+) | LM2596 `IN+` & TB6612 `VM` | Main 12V DC power rail |
| | 12V DC Adapter (-) | LM2596 `IN-` & Breadboard `GND` | Common system ground |
| **Regulated 5V** | LM2596 `OUT+` | Breadboard `+5V` Rail | Set trimmer knob to **exact 5.0 V** |
| | LM2596 `OUT-` | Breadboard `GND` Rail | Common ground |
| **Capacitors** | 470–1000 µF 16V | Between `+5V` and `GND` Rails | Absorbs motor/servo current spikes |
| **P1 MG90S Servo**| Red / Brown | `+5V` / `GND` | Dedicated 5V servo power |
| | Orange (Signal) | **Pin 18 (`PD4` / OC1B)** | 50Hz PWM strike pulse |
| **P2 MG90S Servo**| Red / Brown | `+5V` / `GND` | Dedicated 5V servo power |
| | Orange (Signal) | **Pin 19 (`PD5` / OC1A)** | 50Hz PWM strike pulse |
| **TB6612 Motor Driver**| `VM` | **12V Rail** | 12V Motor power |
| | `VCC` / `GND` | `+5V` / `GND` | Logic power |
| | `STBY` | **Pin 36 (`PA4`)** | Standby enable (HIGH = Run both motors) |
| | `AIN1` / `AIN2` | **Pin 22 (`PC0`) / Pin 23 (`PC1`)** | **P1 Motor Direction** |
| | `PWMA` | **Pin 20 (`PD6`)** | **P1 Motor Speed / Enable** |
| | `AO1` / `AO2` | **Player 1 N20 Motor** | Wires to P1 carriage motor |
| | `BIN1` / `BIN2` | **Pin 24 (`PC2`) / Pin 25 (`PC3`)** | **P2 Motor Direction** |
| | `PWMB` | **Pin 26 (`PC4`)** | **P2 Motor Speed / Enable** |
| | `BO1` / `BO2` | **Player 2 N20 Motor** | Wires to P2 carriage motor |
| **Laser Emitters**| Red / Black (both) | `+5V` / `GND` | Constant 5V beam across field |
| **Laser Receiver A**| `OUT` / `+` / `-` | **Pin 16 (`PD2` / INT0)** + 5V/GND | Falling edge when broken (P1 side) |
| **Laser Receiver B**| `OUT` / `+` / `-` | **Pin 17 (`PD3` / INT1)** + 5V/GND | Falling edge when broken (P2 side) |
| **Buzzer / Speaker**| Positive (+) | **Pin 21 (`PD7` / OC2)** | Timer2 CTC tone & siren generation |
| | Negative (-) | `GND` | Ground return |
| **LCD 16x2 (16-Pin)** | `VSS` (Pin 1) / `VDD` (Pin 2) | `GND` / `+5V` Rail | LCD Power |
| | `V0` (Pin 3) | **GND** (or Potentiometer Wiper) | Contrast Control |
| | `RS` (Pin 4) | **Pin 3 (`PB2`)** | Register Select |
| | `RW` (Pin 5) | **GND** Rail | Read/Write (Write mode) |
| | `E` (Pin 6) | **Pin 4 (`PB3`)** | Enable Strobe Pulse |
| | `D0` .. `D3` (Pins 7..10) | **খালি (Leave Empty)** | 4-Bit মোডে লাগবে না |
| | `D4` (Pin 11) | **Pin 5 (`PB4`)** | 4-bit Data bit 4 |
| | `D5` (Pin 12) | **Pin 6 (`PB5`)** | 4-bit Data bit 5 (shared with MOSI) |
| | `D6` (Pin 13) | **Pin 7 (`PB6`)** | 4-bit Data bit 6 (shared with MISO) |
| | `D7` (Pin 14) | **Pin 8 (`PB7`)** | 4-bit Data bit 7 (shared with SCK) |
| | `A` (Pin 15) / `K` (Pin 16) | `+5V` / `GND` Rail | LCD Backlight Power |

---

## 5. Complete Production-Ready C Firmware (Dual Motors & Servos @ 8 MHz)

```c
#define F_CPU 8000000UL  // Configured for Internal 8 MHz RC Oscillator
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>

/* ==========================================================================
   GAME STATE & TIMING VARIABLES
   ========================================================================== */
volatile uint8_t score_p1 = 0;
volatile uint8_t score_p2 = 0;
volatile uint16_t match_seconds_left = 180; // 3-minute match timer

volatile uint32_t system_millis = 0;
volatile uint32_t time_beam_a = 0;
volatile uint32_t time_beam_b = 0;
volatile uint32_t last_fire_p1 = 0;
volatile uint32_t last_fire_p2 = 0;

// Freeze Attack Status
volatile uint32_t p1_frozen_until = 0;
volatile uint32_t p2_frozen_until = 0;
volatile uint32_t p1_stun_cooldown = 0;
volatile uint32_t p2_stun_cooldown = 0;

/* ==========================================================================
   ADC DRIVER (10-Bit Analog Reading on PORTA)
   ========================================================================== */
void adc_init(void) {
    ADMUX = (1 << REFS0); // AREF = AVCC (5V)
    ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1); // Prescaler 64 (125 kHz)
}

uint16_t adc_read(uint8_t channel) {
    ADMUX = (ADMUX & 0xF0) | (channel & 0x0F);
    ADCSRA |= (1 << ADSC);
    while (ADCSRA & (1 << ADSC));
    return ADC;
}

/* ==========================================================================
   16x2 CHARACTER LCD DRIVER (4-Bit Mode on PORTB)
   RS: PB2 (Pin 3), EN: PB3 (Pin 4), D4..D7: PB4..PB7 (Pins 5..8)
   RW: Connected to GND
   ========================================================================== */
#define LCD_PORT PORTB
#define LCD_DDR  DDRB
#define LCD_RS   PB2
#define LCD_EN   PB3

static void lcd_pulse_enable(void) {
    LCD_PORT |= (1 << LCD_EN);
    _delay_us(2);
    LCD_PORT &= ~(1 << LCD_EN);
    _delay_us(50);
}

static void lcd_send_nibble(uint8_t nibble) {
    LCD_PORT = (LCD_PORT & 0x0F) | (nibble & 0xF0);
    lcd_pulse_enable();
}

void lcd_send_cmd(uint8_t cmd) {
    LCD_PORT &= ~(1 << LCD_RS); // RS = 0 for command
    lcd_send_nibble(cmd & 0xF0);
    lcd_send_nibble((cmd << 4) & 0xF0);
    if (cmd == 0x01 || cmd == 0x02) {
        _delay_ms(2);
    } else {
        _delay_us(50);
    }
}

void lcd_send_data(uint8_t data) {
    LCD_PORT |= (1 << LCD_RS); // RS = 1 for data
    lcd_send_nibble(data & 0xF0);
    lcd_send_nibble((data << 4) & 0xF0);
    _delay_us(50);
}

void lcd_init(void) {
    LCD_DDR |= (1 << LCD_RS) | (1 << LCD_EN) | (1 << PB4) | (1 << PB5) | (1 << PB6) | (1 << PB7);
    _delay_ms(50); // Power-on delay

    LCD_PORT &= ~(1 << LCD_RS);
    lcd_send_nibble(0x30);
    _delay_ms(5);
    lcd_send_nibble(0x30);
    _delay_us(150);
    lcd_send_nibble(0x30);
    _delay_us(150);
    lcd_send_nibble(0x20); // Switch to 4-bit mode
    _delay_us(150);

    lcd_send_cmd(0x28); // 2-line mode, 5x8 dots
    lcd_send_cmd(0x0C); // Display ON, Cursor OFF
    lcd_send_cmd(0x06); // Auto-increment cursor
    lcd_send_cmd(0x01); // Clear screen
    _delay_ms(2);
}

void lcd_set_cursor(uint8_t row, uint8_t col) {
    uint8_t addr = (row == 0) ? (0x80 + col) : (0xC0 + col);
    lcd_send_cmd(addr);
}

void lcd_print(const char *str) {
    while (*str) {
        lcd_send_data((uint8_t)*str++);
    }
}

void lcd_print_num(uint16_t num) {
    char buf[6];
    uint8_t i = 0;
    if (num == 0) {
        lcd_send_data('0');
        return;
    }
    while (num > 0) {
        buf[i++] = (num % 10) + '0';
        num /= 10;
    }
    while (i > 0) {
        lcd_send_data(buf[--i]);
    }
}

void lcd_update_display(uint8_t p1, uint8_t p2, uint16_t time_sec) {
    // Row 0: "P1: 0     P2: 0"
    lcd_set_cursor(0, 0);
    lcd_print("P1: ");
    lcd_print_num(p1);
    lcd_print("     P2: ");
    lcd_print_num(p2);
    lcd_print("  ");

    // Row 1: "TIME: 180s"
    lcd_set_cursor(1, 0);
    lcd_print("TIME: ");
    lcd_print_num(time_sec);
    lcd_print("s       ");
}

/* ==========================================================================
   AUDIO TONE GENERATION (Passive Buzzer on PD7 / OC2 @ 8 MHz)
   ========================================================================== */
void buzzer_tone(uint8_t ocr_val, uint16_t duration_ms) {
    OCR2 = ocr_val;
    TCCR2 = (1 << WGM21) | (1 << COM20) | (1 << CS22); // CTC Toggle, Prescaler 64
    for (uint16_t i = 0; i < duration_ms; i++) {
        _delay_ms(1);
    }
    TCCR2 = 0;
    PORTD &= ~(1 << PD7);
}

void play_goal_p1(void) {
    buzzer_tone(41, 180); // High "Tung!" (~1.5 kHz)
}

void play_goal_p2(void) {
    buzzer_tone(62, 180); // Medium "Tung!" (~1.0 kHz)
}

void play_stun_siren(void) {
    for (uint8_t i = 0; i < 4; i++) {
        buzzer_tone(30, 40);
        buzzer_tone(70, 40);
    }
}

void play_game_start(void) {
    buzzer_tone(75, 100); _delay_ms(50);
    buzzer_tone(60, 100); _delay_ms(50);
    buzzer_tone(45, 250);
}

/* ==========================================================================
   TIMER0: 1 MS SYSTEM TICK & MATCH CLOCK
   ========================================================================== */
ISR(TIMER0_COMP_vect) {
    system_millis++;
    static uint16_t second_counter = 0;
    if (++second_counter >= 1000) {
        second_counter = 0;
        if (match_seconds_left > 0) {
            match_seconds_left--;
        }
    }
}

/* ==========================================================================
   DUAL-LASER DIRECTION SCORING (INT0 / INT1) — [DISABLED/COMMENTED OUT]
   ========================================================================== */
/*
ISR(INT0_vect) {
    time_beam_a = system_millis;
    if ((time_beam_a - time_beam_b) > 0 && (time_beam_a - time_beam_b) < 600) {
        score_p2++;
        time_beam_a = 0;
        time_beam_b = 0;
        play_goal_p2();
        max7219_update_scores(score_p1, score_p2);
    }
}

ISR(INT1_vect) {
    time_beam_b = system_millis;
    if ((time_beam_b - time_beam_a) > 0 && (time_beam_b - time_beam_a) < 600) {
        score_p1++;
        time_beam_a = 0;
        time_beam_b = 0;
        play_goal_p1();
        max7219_update_scores(score_p1, score_p2);
    }
}
*/

/* ==========================================================================
   MG90S SERVO KICKERS (Timer1 Fast PWM 50Hz @ 8 MHz: ICR1 = 20000)
   ========================================================================== */
#define SERVO_DEG(deg)    (600 + ((uint16_t)(deg) * 10))

#define P1_SERVO_REST     SERVO_DEG(87)   // 87 deg = 1470 us (Resting position)
#define P1_SERVO_STRIKE   SERVO_DEG(20)   // 20 deg = 800 us (Strike kick downwards)

#define P2_SERVO_REST     SERVO_DEG(43)   // 43 deg = 1030 us (Resting position)
#define P2_SERVO_STRIKE   SERVO_DEG(160)  // 160 deg = 2200 us (Strike kick upwards)

#define SERVO_STRIKE_MS   90

void fire_servo1(void) {
    OCR1B = P1_SERVO_STRIKE;
    _delay_ms(SERVO_STRIKE_MS);
    OCR1B = P1_SERVO_REST;
}

void fire_servo2(void) {
    OCR1A = P2_SERVO_STRIKE;
    _delay_ms(SERVO_STRIKE_MS);
    OCR1A = P2_SERVO_REST;
}

/* ==========================================================================
   TB6612 DUAL MOTOR DRIVER (P1 Motor on Ch A, P2 Motor on Ch B)
   ========================================================================== */
void motors_init(void) {
    // P1 Direction: PC0 (AIN1), PC1 (AIN2)
    // P2 Direction: PC2 (BIN1), PC3 (BIN2)
    // P2 Speed: PC4 (PWMB)
    // STBY Enable: PA4
    DDRC |= (1 << PC0) | (1 << PC1) | (1 << PC2) | (1 << PC3) | (1 << PC4);
    DDRA |= (1 << PA4);
    PORTA |= (1 << PA4); // Enable STBY

    // P1 Speed: PD6 (PWMA)
    DDRD |= (1 << PD6);
}

void set_p1_motor(int8_t speed) { // speed: -1 (Left), 0 (Stop), 1 (Right)
    if (speed < 0) {
        PORTC |= (1 << PC0); PORTC &= ~(1 << PC1); PORTD |= (1 << PD6);
    } else if (speed > 0) {
        PORTC &= ~(1 << PC0); PORTC |= (1 << PC1); PORTD |= (1 << PD6);
    } else {
        PORTD &= ~(1 << PD6); // Stop
    }
}

void set_p2_motor(int8_t speed) { // speed: -1 (Left), 0 (Stop), 1 (Right)
    if (speed < 0) {
        PORTC |= (1 << PC2); PORTC &= ~(1 << PC3); PORTC |= (1 << PC4);
    } else if (speed > 0) {
        PORTC &= ~(1 << PC2); PORTC |= (1 << PC3); PORTC |= (1 << PC4);
    } else {
        PORTC &= ~(1 << PC4); // Stop
    }
}

/* ==========================================================================
   SINGLE-LASER GOAL SENSOR (INT0 on PD2 / Pin 16)
   ========================================================================== */
volatile uint32_t last_goal_time = 0;

ISR(INT0_vect) {
    if (system_millis - last_goal_time > 800) { // 800ms debounce per ball pass
        last_goal_time = system_millis;
        score_p1++;
        play_goal_p1();
        lcd_update_display(score_p1, score_p2, match_seconds_left);
    }
}

/* ==========================================================================
   HARDWARE INITIALIZATION
   ========================================================================== */
void init_all(void) {
    // 0. Disable JTAG interface to free PC2 (Pin 24), PC3 (Pin 25), PC4 (Pin 26), PC5 (Pin 27) for GPIO
    MCUCSR = (1 << JTD);
    MCUCSR = (1 << JTD);

    // 1. Digital Inputs: Joystick Freeze Buttons (PB0, PB1) with Pull-Ups
    DDRB &= ~((1 << PB0) | (1 << PB1));
    PORTB |= (1 << PB0) | (1 << PB1);

    // 2. Outputs: Buzzer (PD7), Servos (PD4, PD5)
    DDRD |= (1 << PD7) | (1 << PD4) | (1 << PD5);

    // 3. Timer0: 1 ms System Tick (CTC Mode, Prescaler 64, OCR0 = 124 @ 8 MHz)
    TCCR0 = (1 << WGM01) | (1 << CS01) | (1 << CS00);
    OCR0 = 124;
    TIMSK |= (1 << OCIE0);

    // 4. Timer1: 50 Hz Servo PWM (Fast PWM Mode 14, ICR1 = 20000 @ 8 MHz, Prescaler 8)
    TCCR1A = (1 << COM1A1) | (1 << COM1B1) | (1 << WGM11);
    TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);
    ICR1 = 20000;
    OCR1A = P2_SERVO_REST;
    OCR1B = P1_SERVO_REST;

    // 5. External Interrupt: Single Laser Goal Sensor on INT0 (PD2 / Pin 16)
    DDRD &= ~(1 << PD2);
    PORTD |= (1 << PD2);
    MCUCR |= (1 << ISC01); // Falling Edge triggers INT0
    MCUCR &= ~(1 << ISC00);
    GICR |= (1 << INT0);

    // 6. ADC, Display & Dual Motors
    adc_init();
    lcd_init();
    motors_init();

    sei(); // Global Interrupts ON
}

/* ==========================================================================
   MAIN GAME LOOP
   ========================================================================== */
int main(void) {
    init_all();
    play_game_start();
    lcd_update_display(score_p1, score_p2, match_seconds_left);

    static uint16_t last_disp_sec = 999;

    while (1) {
        // -------------------------------------------------------------
        // DISPLAY UPDATE (Every second or when time/score changes)
        // -------------------------------------------------------------
        if (last_disp_sec != match_seconds_left) {
            last_disp_sec = match_seconds_left;
            lcd_update_display(score_p1, score_p2, match_seconds_left);
        }

        // -------------------------------------------------------------
        // PLAYER 1 CONTROLS (Active only when NOT frozen)
        // -------------------------------------------------------------
        if (system_millis > p1_frozen_until) {
            // (A) Steer P1 Motor (VRX on PA0: Left < 350, Right > 650)
            uint16_t p1_x = adc_read(0);
            if (p1_x < 350) {
                set_p1_motor(-1); // Move Left
            } else if (p1_x > 650) {
                set_p1_motor(1);  // Move Right
            } else {
                set_p1_motor(0);  // Stop
            }

            // (B) Shoot on Push UP (VRY on PA2 > 650)
            uint16_t p1_y = adc_read(2);
            if (p1_y > 650 && (system_millis - last_fire_p1 > 250)) {
                last_fire_p1 = system_millis;
                fire_servo1();
            }

            // (C) 3-Second Freeze Attack on Thumb Click (PB0 LOW)
            if (!(PINB & (1 << PB0)) && (system_millis > p1_stun_cooldown)) {
                p2_frozen_until = system_millis + 3000;   // Freeze P2 for 3s!
                p1_stun_cooldown = system_millis + 15000; // 15s cooldown
                set_p2_motor(0);                          // Immediately stop P2 motor
                play_stun_siren();
            }
        } else {
            set_p1_motor(0); // P1 is frozen! Stop motor!
        }

        // -------------------------------------------------------------
        // PLAYER 2 CONTROLS (Active only when NOT frozen)
        // -------------------------------------------------------------
        if (system_millis > p2_frozen_until) {
            // (A) Steer P2 Motor (VRX on PA1: Left < 350, Right > 650)
            uint16_t p2_x = adc_read(1);
            if (p2_x < 350) {
                set_p2_motor(-1); // Move Left
            } else if (p2_x > 650) {
                set_p2_motor(1);  // Move Right
            } else {
                set_p2_motor(0);  // Stop
            }

            // (B) Shoot on Push UP (VRY on PA3 > 650)
            uint16_t p2_y = adc_read(3);
            if (p2_y > 650 && (system_millis - last_fire_p2 > 250)) {
                last_fire_p2 = system_millis;
                fire_servo2();
            }

            // (C) 3-Second Freeze Attack on Thumb Click (PB1 LOW)
            if (!(PINB & (1 << PB1)) && (system_millis > p2_stun_cooldown)) {
                p1_frozen_until = system_millis + 3000;   // Freeze P1 for 3s!
                p2_stun_cooldown = system_millis + 15000; // 15s cooldown
                set_p1_motor(0);                          // Immediately stop P1 motor
                play_stun_siren();
            }
        } else {
            set_p2_motor(0); // P2 is frozen! Stop motor!
        }
    }
}
```

---

## 6. Post-Build Testing Checklist

1. **Power Check:** Turn on 12V adapter $\rightarrow$ Buzzer plays start chime, 16x2 LCD displays `P1: 0     P2: 0` and `TIME: 180s`.
2. **P1 Steering & Shoot:** Tilt Joystick 1 Left/Right $\rightarrow$ P1 carriage motor moves. Push UP $\rightarrow$ P1 Servo kicks.
3. **P2 Steering & Shoot:** Tilt Joystick 2 Left/Right $\rightarrow$ P2 carriage motor moves. Push UP $\rightarrow$ P2 Servo kicks.
4. **Freeze Attack:** Click Joystick 1 Button $\rightarrow$ Siren sounds! P2 motor and servo immediately freeze for 3 seconds!
5. **Goal Scoring:**
   * Break Laser Beam on PD2 (INT0) $\rightarrow$ P1 scores (+1 point, LCD updates `P1: 1`, High "Tung!").
