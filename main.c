/*
 * CHEERIVY v5 — Human (servo) vs AI (servo), single ATmega32 @ internal 8 MHz
 *
 *  HUMAN player                         AI player (red tape on carriage)
 *  ─────────────────────────            ─────────────────────────────────
 *  Joystick X   PA1 / pin 39            Motor ch A  AIN1 PC0 / pin 22
 *  Joystick Y   PA3 / pin 37                        AIN2 PC1 / pin 23
 *  Freeze btn   PB1 / pin 2                         PWMA PD6 / pin 20
 *  Motor ch B   BIN1 PC2 / pin 24       Servo        PD4 (OC1B) / pin 18
 *               BIN2 PC3 / pin 25       Brain: laptop camera via HC-05 (PD0 RXD / pin 14)
 *               PWMB PC4 / pin 26              or Mirror AI when the laptop is silent
 *  Servo        PD5 (OC1A) / pin 19
 *
 *  Servos (MG90S): both strike at FULL speed (jump straight to the strike angle), hold just
 *  long enough to finish the swing, return, and only fire again once back at rest.
 *  At power-on both servos go to REST — attach the human servo's horn in that position.
 *
 *  Shared: TB6612 STBY PA4 / pin 36, buzzer PD7 / pin 21, HC-05 TX->pin 14, pin 15->HC-05 RX
 *  Goals:  Laser receiver A OUT -> PD2 (INT0) / pin 16   beam on the HUMAN goal line -> AI scores
 *          Laser receiver B OUT -> PD3 (INT1) / pin 17   beam on the AI goal line    -> HUMAN scores
 *          Receiver OUT is HIGH while it sees the laser; the ball breaks the beam = falling edge.
 *
 *  Two-player mode: joystick 2 (X PA0 / pin 40, Y PA2 / pin 38, button PB0 / pin 1) drives
 *  the AI-side carriage and servo instead of the AI.
 *
 *  Power-up:
 *    - hold the FREEZE button while powering on  -> SELF-TEST (motors, both servos)
 *    - otherwise: difficulty beeps (2 = medium). Press FREEZE within 3 s to change
 *      1 / 2 / 3 beeps = easy / medium / hard (only affects Mirror AI).
 *    - then the LOBBY: the robot waits for the laptop menu (or press FREEZE = 1P vs Mirror AI).
 *      After every match it goes back to the lobby.
 *
 *  Laptop protocol (single bytes):
 *    'L' 'R' 'S' move/stop AI carriage   'F' fire AI servo   'Z' freeze the human
 *      (these are echoed back in lowercase)
 *    '1' / '2' / '3'   choose single player / two players / AI vs AI (lobby)   'K' kick off   'E' end the match now
 *    AI vs AI (game 3): the laptop's camera AI also drives PLAYER 1's carriage (blue tape on it):
 *      'B' 'N' 'M' move left / right / stop player 1   'G' fire player 1's servo   'Y' freeze the AI side
 *      (echoed in lowercase too). The joystick and button of player 1 are ignored in this game.
 *    No byte for LINK_HOLD_MS (0.4 s) -> AI carriage stops and waits; for LINK_TIMEOUT_MS (1.5 s) ->
 *    Mirror AI takes over (falling tone); link back -> rising tone.
 *
 *  Lines sent to the laptop:  "READY" (every second in the lobby)
 *    "START LEVEL n 1P|2P|AI"   "T <seconds left> CAM|MIR|P2|AI"
 *    "G H <human> <ai>" human scored   "G A <human> <ai>" AI scored   "END <human> <ai>"
 */
#ifndef F_CPU
#define F_CPU 8000000UL
#endif
#include <avr/eeprom.h>
#include <avr/interrupt.h>
#include <avr/io.h>
#include <stdint.h>
#include <util/atomic.h>
#include <util/delay.h>

/* ============================================================== TUNING */
#define MATCH_SECONDS          180
#define JOY_LOW                350   /* X below this = left            */
#define JOY_HIGH               650   /* X above = right, Y above = fire */
#define FREEZE_MS              3000
#define FREEZE_COOLDOWN_MS     15000
#define LINK_TIMEOUT_MS        1500  /* laptop silent this long -> Mirror AI. Windows Bluetooth
                                        delivers bytes in bursts with gaps > 0.4 s, so be patient */
#define LINK_HOLD_MS           400   /* silent this long (but not yet timed out): AI carriage stops
                                        and waits instead of driving on a stale command */
#define MIRROR_SIGN            (+1)  /* set to -1 if Mirror AI moves OPPOSITE to the human */
#define P2_DIR_SIGN            (+1)  /* set to -1 if player 2's carriage moves opposite to their joystick */
/* Build switches (the Makefile's `camera-only` target builds CHEERIVY_camera_only.hex with both 0):
   MIRROR_AI 0 -> no Mirror AI: without the laptop's camera AI the AI carriage just stops, so
                  everything it does comes from the camera.   ALLOW_2P 0 -> single player only. */
#ifndef MIRROR_AI
#define MIRROR_AI              1
#endif
#ifndef ALLOW_2P
#define ALLOW_2P               1
#endif
#define MIRROR_FIRE_DELAY_MS   550   /* ~ball travel time from human flipper to AI */
#define TELEMETRY_MS           1000
#define GOAL_LOCKOUT_MS        1500  /* ignore the same beam this long after a goal (ball bouncing in the beam) */
#define SWAP_GOAL_SENSORS      0     /* 1 if goals are credited to the wrong player */
#define UART_BAUD              9600

static const uint16_t MIRROR_DELAY_MS[3] = {300, 180, 80};  /* easy, medium, hard */

/* ============================================================== SERVO ANGLES + SPEED
 * Angles in degrees (0..180). The strike angle should go ~20° PAST the point where the arm
 * touches the ball: a servo slows down near its target, so the ball must be hit mid-swing
 * while the arm is still at full speed.
 *
 * AI servo: already mounted, keep its tested angles (67° swing).
 * HUMAN servo: not mounted yet. Rest at 90° = centre of the range, so there is room to
 *   tune either way. Strike 65° away. If it swings the WRONG way once mounted, change
 *   HUMAN_STRIKE_DEG to 155 (= 90 + 65).                                                  */
#define AI_REST_DEG            87
#define AI_STRIKE_DEG          20
#define HUMAN_REST_DEG         97    /* tuned on the robot (live, from the laptop) */
#define HUMAN_STRIKE_DEG       56    /* 41° swing, tuned on the robot */

/* MG90S: 0.10 s / 60° at 4.8-5 V = 1.6 ms per degree (0.08 s / 60° at 6 V -> use 13).     */
#define SERVO_MS_PER_DEG_X10   16
#define SERVO_SETTLE_MS        15    /* start-up + stop time on top of the pure travel time */
#define SERVO_FRAME_US         20000 /* 50 Hz. 10000 (100 Hz) makes most analog servos snappier;
                                        go back to 20000 if the servo buzzes or gets hot. */

#define SERVO_US(deg)          (600 + (uint16_t)(deg) * 10)
#define SWING_DEG(a, b)        ((a) > (b) ? (a) - (b) : (b) - (a))
#define TRAVEL_MS(a, b)        (SWING_DEG(a, b) * SERVO_MS_PER_DEG_X10 / 10 + SERVO_SETTLE_MS)
static uint8_t ai_rest = AI_REST_DEG, ai_strike = AI_STRIKE_DEG;      /* tunable too, like player 1's */
#define AI_TRAVEL_MS           TRAVEL_MS(ai_rest, ai_strike)             /* ~122 ms for 67° */
/* Player 1's angles can be changed live from the laptop ("H<deg>;" rest, "J<deg>;" strike) and
   are kept in EEPROM, so they survive power-off. HUMAN_REST_DEG / HUMAN_STRIKE_DEG are only the
   defaults for a fresh chip. */
static uint8_t human_rest = HUMAN_REST_DEG, human_strike = HUMAN_STRIKE_DEG;
#define HUMAN_TRAVEL_MS        TRAVEL_MS(human_rest, human_strike)       /* ~119 ms for 67° */
#define HUMAN_CONTACT_MS       (HUMAN_TRAVEL_MS * 2 / 3)  /* ball is hit ~2/3 into the swing */

/* ============================================================== TIME (Timer0, 1 ms) */
static volatile uint32_t g_ms;

ISR(TIMER0_COMP_vect) { g_ms++; }

static uint32_t millis(void) {
  uint32_t t;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { t = g_ms; }
  return t;
}

/* ============================================================== SERVOS (Timer1, 1 us ticks)
 * AI    = OC1B / PD4 / pin 18      HUMAN = OC1A / PD5 / pin 19
 * One strike: jump to STRIKE (full speed) -> hold TRAVEL ms (swing completes) -> jump back to
 * REST -> ready again after another TRAVEL ms (back at rest, so the next swing is a full one). */
#define SERVO_AI     0
#define SERVO_HUMAN  1

static uint32_t servo_back_at[2], servo_ready_at[2];
static uint8_t servo_out[2];

static void servo_write(uint8_t s, uint16_t us) {   /* direct register writes (16-bit safe) */
  if (s == SERVO_AI) OCR1B = us; else OCR1A = us;
}

static void servo_init(void) {
  DDRD |= (1 << PD4) | (1 << PD5);
  /* Fast PWM mode 14, TOP = ICR1, prescaler 8 -> 1 us per tick. Both outputs driven. */
  TCCR1A = (1 << COM1A1) | (1 << COM1B1) | (1 << WGM11);
  TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);
  ICR1 = SERVO_FRAME_US;
  if (eeprom_read_byte((uint8_t *)3) == 0xC6) {        /* player 2 angles saved from the laptop */
    uint8_t r = eeprom_read_byte((uint8_t *)4), k = eeprom_read_byte((uint8_t *)5);
    if (r <= 180 && k <= 180) { ai_rest = r; ai_strike = k; }
  }
  servo_write(SERVO_AI, SERVO_US(ai_rest));
  if (eeprom_read_byte((uint8_t *)0) == 0xC5) {        /* angles saved from the laptop */
    uint8_t r = eeprom_read_byte((uint8_t *)1), k = eeprom_read_byte((uint8_t *)2);
    if (r <= 180 && k <= 180) { human_rest = r; human_strike = k; }
  }
  servo_write(SERVO_HUMAN, SERVO_US(human_rest));
}

static uint8_t servo_ready(uint8_t s, uint32_t now) { return now >= servo_ready_at[s]; }

static void servo_fire(uint8_t s, uint32_t now) {
  if (!servo_ready(s, now)) return;
  uint16_t travel = (s == SERVO_AI) ? AI_TRAVEL_MS : HUMAN_TRAVEL_MS;
  servo_write(s, SERVO_US(s == SERVO_AI ? ai_strike : human_strike));
  servo_out[s] = 1;
  servo_back_at[s] = now + travel;
  servo_ready_at[s] = now + 2UL * travel;
}

static void servo_update(uint32_t now) {
  for (uint8_t s = 0; s < 2; s++) {
    if (servo_out[s] && now >= servo_back_at[s]) {
      servo_write(s, SERVO_US(s == SERVO_AI ? ai_rest : human_rest));
      servo_out[s] = 0;
    }
  }
}

/* ============================================================== MOTORS (TB6612) */
static void motors_init(void) {
  DDRC |= (1 << PC0) | (1 << PC1) | (1 << PC2) | (1 << PC3) | (1 << PC4);
  DDRD |= (1 << PD6);
  DDRA |= (1 << PA4);
  PORTA |= (1 << PA4);                  /* STBY high = driver enabled */
}

static void motor_ai(int8_t d) {        /* channel A: -1 left, 0 stop, +1 right */
  if (d < 0)      { PORTC |= (1 << PC0);  PORTC &= ~(1 << PC1); PORTD |= (1 << PD6); }
  else if (d > 0) { PORTC &= ~(1 << PC0); PORTC |= (1 << PC1);  PORTD |= (1 << PD6); }
  else            { PORTD &= ~(1 << PD6); }
}

static void motor_human(int8_t d) {     /* channel B */
  if (d < 0)      { PORTC |= (1 << PC2);  PORTC &= ~(1 << PC3); PORTC |= (1 << PC4); }
  else if (d > 0) { PORTC &= ~(1 << PC2); PORTC |= (1 << PC3);  PORTC |= (1 << PC4); }
  else            { PORTC &= ~(1 << PC4); }
}

/* ============================================================== JOYSTICK (ADC) */
static void adc_init(void) {
  ADMUX = (1 << REFS0);                               /* AVCC reference */
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1); /* /64 -> 125 kHz */
}

static uint16_t adc_read(uint8_t ch) {
  ADMUX = (ADMUX & 0xF0) | (ch & 0x0F);
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) {}
  return ADC;
}

static uint8_t freeze_btn_down(void) { return !(PINB & (1 << PB1)); }

/* Joystick 2 (two-player mode only): X PA0 / pin 40, Y PA2 / pin 38, button PB0 / pin 1.
   It drives the carriage + servo on the AI side. */
static uint8_t freeze2_btn_down(void) { return !(PINB & (1 << PB0)); }

static int8_t joy_dir(uint16_t x) { return (x < JOY_LOW) ? -1 : (x > JOY_HIGH) ? 1 : 0; }

/* ============================================================== BUZZER (Timer2, non-blocking) */
typedef struct { uint8_t ocr; uint8_t cs; } Note;   /* ocr 0 = rest; cs = duration in 10 ms */

static const Note SND_START[] = {{75, 10}, {0, 5}, {60, 10}, {0, 5}, {45, 25}};
static const Note SND_BEEP1[] = {{45, 8}};
static const Note SND_BEEP2[] = {{45, 8}, {0, 10}, {45, 8}};
static const Note SND_BEEP3[] = {{45, 8}, {0, 10}, {45, 8}, {0, 10}, {45, 8}};
static const Note SND_LINK_UP[] = {{70, 6}, {50, 6}, {35, 10}};
static const Note SND_LINK_DOWN[] = {{35, 6}, {50, 6}, {70, 10}};
static const Note SND_SIREN[] = {{30, 4}, {70, 4}, {30, 4}, {70, 4}, {30, 4}, {70, 4}, {30, 4}, {70, 4}};
static const Note SND_TICK[] = {{30, 3}};
/* While a carriage is frozen the buzzer keeps beeping until the freeze ends:
   low beeps = player 1 frozen, high beeps = the AI side frozen. */
static const Note SND_FROZEN_HUMAN[] = {{70, 10}, {0, 8}};
static const Note SND_FROZEN_AI[] = {{35, 10}, {0, 8}};
static const Note SND_GOAL_HUMAN[] = {{62, 8}, {49, 8}, {41, 8}, {30, 30}};
static const Note SND_GOAL_AI[] = {{41, 12}, {49, 12}, {62, 12}, {83, 30}};
static const Note SND_END[] = {{62, 60}, {0, 10}, {41, 15}, {0, 5}, {41, 15}, {0, 5}, {41, 15}};
#define PLAY(s) buzz_play((s), sizeof(s) / sizeof(Note))

static const Note *bz_seq;
static uint8_t bz_len, bz_i;
static uint32_t bz_note_end;

static void buzz_off(void) {
  TCCR2 = 0;
  PORTD &= ~(1 << PD7);
}

static void buzz_note(void) {
  if (bz_i >= bz_len) { buzz_off(); bz_seq = 0; return; }
  Note n = bz_seq[bz_i];
  if (n.ocr) {
    OCR2 = n.ocr;                                        /* f = 62500 / (1 + ocr) Hz */
    TCCR2 = (1 << WGM21) | (1 << COM20) | (1 << CS22);   /* CTC, toggle OC2, /64 */
  } else {
    buzz_off();
  }
  bz_note_end = millis() + (uint32_t)n.cs * 10;
}

static void buzz_play(const Note *s, uint8_t n) {
  bz_seq = s; bz_len = n; bz_i = 0;
  buzz_note();
}

static void df_update(uint32_t now);

static void buzz_update(uint32_t now) { /* every main loop calls this: also passes voice clips on */
  if (bz_seq && now >= bz_note_end) { bz_i++; buzz_note(); }
  df_update(now);
}

static void wait_ms(uint32_t ms) {      /* blocking wait that keeps sounds and pulses running */
  uint32_t end = millis() + ms;
  while (millis() < end) {
    uint32_t now = millis();
    buzz_update(now); servo_update(now);
  }
}

/* ============================================================== DFPLAYER MINI (voice) */
/* Commentary clips on the microSD card, played by a DFPlayer Mini through the PAM8610 amp.
   The laptop picks the clip and sends it over Bluetooth; this forwards it to the DFPlayer:
     "P<n>;"  play /MP3/<n>.mp3 as the main track (the crowd loop)      "P0;" = stop everything
     "A<n>;"  play /ADVERT/<n>.mp3 on top: the main track pauses and carries on afterwards
              (commentary with crowd mixed in)                          "A0;" = stop the advert
     "V<n>;"  volume 0..30
     "X<c>;"  raw DFPlayer command c with no number (test: X1; = next track, like touching IO2)
   DFPlayer RX <- PA5 / pin 35 through a 1k resistor. Software serial, 9600 8N1, send only. */
#define DF_PORT PORTA
#define DF_DDR  DDRA
#define DF_BIT  PA5
#define DF_VOLUME_DEFAULT 14    /* the PAM8610 has a fixed high gain: keep this low; the laptop sets ROBOT_VOLUME */
#define DF_BOOT_MS 1500                 /* the DFPlayer ignores commands while it reads the card */

static volatile uint8_t df_cmd;         /* 'P' or 'V' while its number is arriving, else 0 */
static volatile uint16_t df_num;
static volatile uint16_t df_play_req;   /* track + 1 (0 = nothing waiting) */
static volatile uint16_t df_adv_req;    /* advert + 1 */
static volatile uint8_t df_raw_req;     /* raw command + 1 */
static volatile uint8_t df_vol_req;     /* volume + 1 */
static volatile uint8_t tune_rest_req[2], tune_strike_req[2], tune_test_req[2];   /* [SERVO_AI / SERVO_HUMAN], value + 1 */
static uint8_t df_booted;

/* 9600 baud = 104.2 us per bit. The loop itself takes ~1.3 us per bit at 8 MHz, so the delay is
   103 us (measured from the compiled code: ~836 cycles = 104.5 us per bit). */
#define DF_BIT_US 103
static void df_byte(uint8_t b) {        /* ~1 ms with interrupts off: the UART hardware holds 2 bytes meanwhile */
  uint8_t sreg = SREG;
  cli();
  DF_PORT &= ~(1 << DF_BIT);            /* start bit */
  _delay_us(DF_BIT_US);
  for (uint8_t i = 0; i < 8; i++) {
    if (b & 1) DF_PORT |= (1 << DF_BIT); else DF_PORT &= ~(1 << DF_BIT);
    b >>= 1;
    _delay_us(DF_BIT_US);
  }
  DF_PORT |= (1 << DF_BIT);             /* stop bit */
  SREG = sreg;
  _delay_us(DF_BIT_US);
}

static void df_send(uint8_t cmd, uint16_t arg) {
  uint8_t f[6] = {0xFF, 0x06, cmd, 0x00, (uint8_t)(arg >> 8), (uint8_t)arg};
  uint16_t sum = 0;
  for (uint8_t i = 0; i < 6; i++) sum += f[i];
  sum = -sum;
  df_byte(0x7E);
  for (uint8_t i = 0; i < 6; i++) df_byte(f[i]);
  df_byte(sum >> 8);
  df_byte(sum & 0xFF);
  df_byte(0xEF);
}

static void df_init(void) {
  DF_DDR |= (1 << DF_BIT);
  DF_PORT |= (1 << DF_BIT);             /* idle high */
}

static void servo_fire(uint8_t s, uint32_t now);
static void uart_puts(const char *s);
static void uart_putu(uint16_t v);

/* Servo tuning from the laptop, for both strikers:
     player 1 (human side):  "H<deg>;" rest   "J<deg>;" strike   "U1;" test strike   "U0;" report
     player 2 (AI side):     "Q<deg>;" rest   "W<deg>;" strike   "T1;" test strike   "T0;" report
   New angles are used at once, saved to EEPROM and reported back as "P1SERVO <rest> <strike>"
   or "P2SERVO <rest> <strike>". */
static void servo_tuning(uint8_t s, uint32_t now) {
  uint8_t r, k, t;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    r = tune_rest_req[s]; tune_rest_req[s] = 0;
    k = tune_strike_req[s]; tune_strike_req[s] = 0;
    t = tune_test_req[s]; tune_test_req[s] = 0;
  }
  uint8_t *rest = (s == SERVO_HUMAN) ? &human_rest : &ai_rest;
  uint8_t *strike = (s == SERVO_HUMAN) ? &human_strike : &ai_strike;
  uint8_t base = (s == SERVO_HUMAN) ? 0 : 3;          /* EEPROM: magic, rest, strike */
  if (r || k) {
    if (r) *rest = r - 1;
    if (k) *strike = k - 1;
    if (!servo_out[s]) servo_write(s, SERVO_US(*rest));
    eeprom_update_byte((uint8_t *)(uint16_t)(base + 1), *rest);
    eeprom_update_byte((uint8_t *)(uint16_t)(base + 2), *strike);
    eeprom_update_byte((uint8_t *)(uint16_t)base, s == SERVO_HUMAN ? 0xC5 : 0xC6);
  }
  if (r || k || t) {
    uart_puts(s == SERVO_HUMAN ? "P1SERVO " : "P2SERVO ");
    uart_putu(*rest);
    uart_puts(" ");
    uart_putu(*strike);
    uart_puts("\n");
  }
  if (t == 2) servo_fire(s, now);
}

static void df_update(uint32_t now) {   /* called from the main loops (via buzz_update) */
  if (!df_booted) {
    if (now < DF_BOOT_MS) return;
    df_booted = 1;
    df_send(0x06, DF_VOLUME_DEFAULT);
  }
  uint8_t v, x; uint16_t p, a;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    v = df_vol_req; df_vol_req = 0;
    x = df_raw_req; df_raw_req = 0;
    p = df_play_req; df_play_req = 0;
    a = df_adv_req; df_adv_req = 0;
  }
  if (v) df_send(0x06, v - 1 > 30 ? 30 : v - 1);
  if (x) df_send(x - 1, 0);
  if (p == 1) df_send(0x16, 0);                     /* "P0;" = stop */
  else if (p) df_send(0x12, p - 1);                 /* play /MP3/<n>.mp3 */
  if (a == 1) df_send(0x15, 0);                     /* "A0;" = stop the advert, back to the main track */
  else if (a) df_send(0x13, a - 1);                 /* play /ADVERT/<n>.mp3 over the main track */
  servo_tuning(SERVO_HUMAN, now);
  servo_tuning(SERVO_AI, now);
}

/* ============================================================== UART / HC-05 */
static volatile char rx_move = 'S';
static volatile uint8_t rx_fire, rx_freeze;
static volatile uint32_t rx_last_ms;
static volatile uint8_t rx_seen;
static volatile uint8_t rx_game = 1;    /* '1' / '2' / '3' from the laptop menu: vs AI, two players, AI vs AI */
static volatile char rx_move1 = 'M';    /* AI vs AI: the laptop's move for player 1 ('B' 'N' 'M') */
static volatile uint8_t rx_fire1, rx_freeze1;
static volatile uint8_t rx_kick, rx_end; /* 'K' kick off (in the lobby), 'E' end the match early */

static void uart_init(void) {
  const uint16_t ubrr = F_CPU / (16UL * UART_BAUD) - 1;
  UBRRH = (uint8_t)(ubrr >> 8);
  UBRRL = (uint8_t)ubrr;
  UCSRB = (1 << RXEN) | (1 << TXEN) | (1 << RXCIE);
  UCSRC = (1 << URSEL) | (1 << UCSZ1) | (1 << UCSZ0);  /* 8N1 */
}

ISR(USART_RXC_vect) {                   /* keep this tiny: no delays, no sounds */
  char c = UDR;
  uint8_t echo = 1;                     /* only moves / fire / freeze are echoed; menu bytes would garble status lines */
  if (df_cmd) {                         /* inside "P123;" / "V25;": collect the number */
    if (c >= '0' && c <= '9') { df_num = df_num * 10 + (c - '0'); return; }
    if (c == ';') {
      if (df_cmd == 'P') df_play_req = df_num + 1;
      else if (df_cmd == 'A') df_adv_req = df_num + 1;
      else if (df_cmd == 'V') df_vol_req = df_num + 1;
      else if (df_cmd == 'X') { if (df_num < 255) df_raw_req = df_num + 1; }
      else if (df_num <= 180) {
        if (df_cmd == 'H') tune_rest_req[SERVO_HUMAN] = df_num + 1;
        else if (df_cmd == 'J') tune_strike_req[SERVO_HUMAN] = df_num + 1;
        else if (df_cmd == 'U') tune_test_req[SERVO_HUMAN] = df_num + 1;
        else if (df_cmd == 'Q') tune_rest_req[SERVO_AI] = df_num + 1;
        else if (df_cmd == 'W') tune_strike_req[SERVO_AI] = df_num + 1;
        else tune_test_req[SERVO_AI] = df_num + 1;       /* 'T' */
      }
    }
    df_cmd = 0;
    if (c == ';') return;               /* anything else: a lost ';' — treat c as a normal byte */
  }
  switch (c) {
    case 'P': case 'A': case 'V': case 'X': case 'H': case 'J': case 'U': case 'Q': case 'W': case 'T':
      df_cmd = c; df_num = 0; return;
    case 'L': case 'R': case 'S': rx_move = c; break;
    case 'F': rx_fire = 1; break;
    case 'Z': rx_freeze = 1; break;
    case 'B': case 'N': case 'M': rx_move1 = c; break;   /* AI vs AI: player 1's carriage */
    case 'G': rx_fire1 = 1; break;
    case 'Y': rx_freeze1 = 1; break;
    case '1': case '2': case '3': rx_game = c - '0'; echo = 0; break;
    case 'K': rx_kick = 1; echo = 0; break;
    case 'E': rx_end = 1; echo = 0; break;
    default: return;
  }
  rx_last_ms = g_ms;
  rx_seen = 1;
  if (echo && (UCSRA & (1 << UDRE))) UDR = c | 0x20;  /* lowercase echo, so the laptop can check the link */
}

static void uart_putc(char c) {
  while (!(UCSRA & (1 << UDRE))) {}
  UDR = c;
}

static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

static void uart_putu(uint16_t v) {
  char b[6]; uint8_t i = 0;
  do { b[i++] = '0' + v % 10; v /= 10; } while (v);
  while (i) uart_putc(b[--i]);
}

/* ============================================================== GOAL LASERS (INT0 / INT1) */
#define GOAL_AT_HUMAN  1                 /* beam on the human's goal line broke -> AI scores */
#define GOAL_AT_AI     2                 /* beam on the AI's goal line broke    -> human scores */
static volatile uint8_t goal_flags;

#if SWAP_GOAL_SENSORS
ISR(INT0_vect) { goal_flags |= GOAL_AT_AI; }
ISR(INT1_vect) { goal_flags |= GOAL_AT_HUMAN; }
#else
ISR(INT0_vect) { goal_flags |= GOAL_AT_HUMAN; }
ISR(INT1_vect) { goal_flags |= GOAL_AT_AI; }
#endif

static void lasers_init(void) {
  DDRD &= ~((1 << PD2) | (1 << PD3));
  PORTD |= (1 << PD2) | (1 << PD3);                  /* pull-ups: an unplugged receiver reads "beam OK" */
  MCUCR |= (1 << ISC01) | (1 << ISC11);              /* falling edge = beam just broke */
  GIFR = (1 << INTF0) | (1 << INTF1);
  GICR |= (1 << INT0) | (1 << INT1);
}

static uint8_t goal_flags_take(void) {
  uint8_t g;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { g = goal_flags; goal_flags = 0; }
  return g;
}

static void lasers_report(void) {       /* LOW = receiver sees no laser (misaligned or blocked) */
  uart_puts((PIND & (1 << PD2)) ? "LASER A OK\n" : "LASER A BLOCKED\n");
  uart_puts((PIND & (1 << PD3)) ? "LASER B OK\n" : "LASER B BLOCKED\n");
}

/* ============================================================== MIRROR AI */
/* Record the human's left/right every 10 ms; the AI replays it `delay` later.
   Straight shots come back along the same line, so copying the human blocks them. */
#define MIRROR_SLOTS 64                  /* 64 x 10 ms = 640 ms of history */
static int8_t mirror_buf[MIRROR_SLOTS];
static uint8_t mirror_head;
static uint32_t mirror_next_sample, mirror_fire_at;

static void mirror_record(uint32_t now, int8_t human_dir) {
  if (now < mirror_next_sample) return;
  mirror_next_sample = now + 10;
  mirror_buf[mirror_head] = human_dir;
  mirror_head = (mirror_head + 1) % MIRROR_SLOTS;
}

__attribute__((unused)) static int8_t mirror_dir(uint8_t level) {
  uint8_t back = MIRROR_DELAY_MS[level] / 10;
  uint8_t i = (mirror_head + MIRROR_SLOTS - 1 - back) % MIRROR_SLOTS;
  return MIRROR_SIGN * mirror_buf[i];
}

/* ============================================================== SELF-TEST */
static void self_test(void) {
  uart_puts("SELFTEST\n");
  PLAY(SND_BEEP1); wait_ms(600);
  uart_puts("AI motor LEFT\n");    motor_ai(-1);    wait_ms(400); motor_ai(0);    wait_ms(400);
  uart_puts("AI motor RIGHT\n");   motor_ai(+1);    wait_ms(400); motor_ai(0);
  PLAY(SND_BEEP2); wait_ms(800);
  uart_puts("AI servo\n");         servo_fire(SERVO_AI, millis()); wait_ms(600);
  PLAY(SND_BEEP3); wait_ms(900);
  uart_puts("HUMAN motor LEFT\n"); motor_human(-1); wait_ms(400); motor_human(0); wait_ms(400);
  uart_puts("HUMAN motor RIGHT\n");motor_human(+1); wait_ms(400); motor_human(0);
  PLAY(SND_BEEP1); wait_ms(600);
  uart_puts("HUMAN servo\n");      servo_fire(SERVO_HUMAN, millis()); wait_ms(600);
  lasers_report();
  uart_puts("SELFTEST done\n");
  PLAY(SND_END); wait_ms(1500);
}

/* ============================================================== DIFFICULTY SELECT */
static uint8_t select_level(void) {
  static const Note *const beeps[3] = {SND_BEEP1, SND_BEEP2, SND_BEEP3};
  static const uint8_t lens[3] = {1, 3, 5};
  uint8_t level = 1;                    /* index: 0 easy, 1 medium, 2 hard */
  buzz_play(beeps[level], lens[level]);
  uint32_t deadline = millis() + 3000;
  uint8_t was_down = 0;
  while (millis() < deadline) {
    uint32_t now = millis();
    buzz_update(now);
    uint8_t down = freeze_btn_down();
    if (down && !was_down) {
      level = (level + 1) % 3;
      buzz_play(beeps[level], lens[level]);
      deadline = now + 3000;            /* more time after every press */
      _delay_ms(30);                    /* debounce */
    }
    was_down = down;
  }
  return level;
}

/* ============================================================== INIT */
static void init_all(void) {
  servo_init();                         /* first: both servos straight to REST */

  uint8_t v = MCUCSR | (1 << JTD);      /* free PC2..PC5 from JTAG: two writes in 4 cycles */
  MCUCSR = v;
  MCUCSR = v;

  DDRB &= ~((1 << PB0) | (1 << PB1));   /* freeze buttons (PB0 = unused old P1 button) */
  PORTB |= (1 << PB0) | (1 << PB1);
  DDRD |= (1 << PD7);                   /* buzzer */

  TCCR0 = (1 << WGM01) | (1 << CS01) | (1 << CS00);   /* CTC, /64 */
  OCR0 = 124;                                         /* 8 MHz / 64 / 125 = 1 kHz */
  TIMSK |= (1 << OCIE0);

  motors_init();
  adc_init();
  df_init();
  uart_init();
  lasers_init();
  sei();
}

/* ============================================================== LOBBY */
/* Wait here between matches. The laptop sends '1' or '2' (menu) and then 'K' (kick off).
   Without a laptop, pressing FREEZE starts a single-player game against Mirror AI.
   Returns the game: 1 = human vs AI, 2 = two players, 3 = AI vs AI (camera AI on both sides). */
static uint8_t lobby(void) {
  motor_ai(0);
  motor_human(0);
  rx_kick = rx_end = 0;
  uint32_t next_ready = 0;
  uint8_t was_down = 1;                 /* ignore a button still held from before */
  for (;;) {
    uint32_t now = millis();
    buzz_update(now);
    servo_update(now);
    if (now >= next_ready) {
      next_ready = now + 1000;
      uart_puts("READY\n");             /* the laptop's "connecting..." screen waits for this */
    }
    if (rx_kick) {
      rx_kick = 0;
      if (rx_game == 3) return 3;
      return (ALLOW_2P && rx_game == 2) ? 2 : 1;
    }
    uint8_t down = freeze_btn_down();
    if (down && !was_down) {
      _delay_ms(30);                    /* debounce */
      return 1;
    }
    was_down = down;
  }
}

/* ============================================================== MATCH */
static void play_match(uint8_t game, uint8_t level) {
  PLAY(SND_START);
  wait_ms(700);
  uart_puts("START LEVEL ");
  uart_putu(level + 1);
  uart_puts(game == 3 ? " AI\n" : game == 2 ? " 2P\n" : " 1P\n");
  lasers_report();

  uint32_t start = millis();
  uint32_t human_frozen_until = 0, ai_frozen_until = 0;
  uint32_t human_freeze_ready = 0, ai_freeze_ready = 0;
  uint32_t next_telemetry = 0;
  uint16_t last_tick_sec = 0xFFFF;
  uint8_t link_up = 0, btn_was_down = 1, btn2_was_down = 1;
  uint8_t score_human = 0, score_ai = 0;
  uint32_t goal_ready_at = 0;
  mirror_fire_at = 0;
  rx_end = 0;
  goal_flags_take();                    /* forget anything that broke a beam before kick-off */

  for (;;) {
    uint32_t now = millis();
    uint16_t left = MATCH_SECONDS - (uint16_t)((now - start) / 1000);
    if ((now - start) / 1000 >= MATCH_SECONDS) break;
    if (rx_end) { rx_end = 0; break; }  /* laptop ended the match early */

    buzz_update(now);
    servo_update(now);

    /* link to the laptop (checked here: in AI vs AI it drives player 1 too) */
    uint32_t last_rx;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { last_rx = rx_last_ms; }
    /* A byte can arrive after `now` was read, making last_rx newer than now. Unsigned
       now - last_rx would then wrap to ~49 days and look like "laptop gone". */
    uint32_t rx_age = (last_rx > now) ? 0 : now - last_rx;
    uint8_t link_now = rx_seen && (rx_age < LINK_TIMEOUT_MS);
    if (link_now != link_up) {
      link_up = link_now;
      if (game != 2) {                  /* in 2P nobody cares which AI would be playing */
        PLAY(link_up ? SND_LINK_UP : SND_LINK_DOWN);
        uart_puts(link_up ? "MODE CAMERA\n" : (MIRROR_AI && game == 1 ? "MODE MIRROR\n" : "MODE WAIT\n"));
      }
    }

    /* ---------------- PLAYER 1: the human, or the camera AI in AI vs AI ---------------- */
    int8_t human_dir = 0;
    if (game == 3) {
      if (now >= human_frozen_until && link_up) {
        human_dir = (rx_move1 == 'B') ? -1 : (rx_move1 == 'N') ? 1 : 0;
        if (rx_age >= LINK_HOLD_MS) human_dir = 0;   /* laptop quiet for a moment: wait */
        if (rx_fire1) { rx_fire1 = 0; servo_fire(SERVO_HUMAN, now); }
        if (rx_freeze1) {
          rx_freeze1 = 0;
          if (now >= human_freeze_ready) {
            ai_frozen_until = now + FREEZE_MS;
            human_freeze_ready = now + FREEZE_COOLDOWN_MS;
            PLAY(SND_SIREN);
          }
        }
      } else {
        rx_fire1 = rx_freeze1 = 0;      /* frozen or no laptop: stand still, drop queued actions */
      }
    } else if (now >= human_frozen_until) {
      uint16_t x = adc_read(1), y = adc_read(3);
      human_dir = joy_dir(x);
      if (y > JOY_HIGH && servo_ready(SERVO_HUMAN, now)) {
        servo_fire(SERVO_HUMAN, now);
        /* the ball leaves when the arm hits it, ~2/3 into the swing */
        if (!mirror_fire_at) mirror_fire_at = now + HUMAN_CONTACT_MS + MIRROR_FIRE_DELAY_MS;
      }
      uint8_t down = freeze_btn_down();
      if (down && !btn_was_down && now >= human_freeze_ready) {
        ai_frozen_until = now + FREEZE_MS;
        human_freeze_ready = now + FREEZE_COOLDOWN_MS;
        PLAY(SND_SIREN);
      }
      btn_was_down = down;
    }
    motor_human(human_dir);
    mirror_record(now, human_dir);

    /* ---------------- AI side: laptop AI / Mirror AI / player 2 ---------------- */

    int8_t ai_dir = 0;
    if (now >= ai_frozen_until) {
      if (game == 2) {
        uint16_t x2 = adc_read(0), y2 = adc_read(2);
        ai_dir = P2_DIR_SIGN * joy_dir(x2);
        if (y2 > JOY_HIGH) servo_fire(SERVO_AI, now);   /* does nothing until the servo is ready */
        uint8_t down2 = freeze2_btn_down();
        if (down2 && !btn2_was_down && now >= ai_freeze_ready) {
          human_frozen_until = now + FREEZE_MS;
          ai_freeze_ready = now + FREEZE_COOLDOWN_MS;
          PLAY(SND_SIREN);
        }
        btn2_was_down = down2;
        rx_fire = rx_freeze = 0;        /* the laptop AI is only watching in 2P */
      } else if (link_up) {
        ai_dir = (rx_move == 'L') ? -1 : (rx_move == 'R') ? 1 : 0;
        if (rx_age >= LINK_HOLD_MS) ai_dir = 0;   /* laptop quiet for a moment: wait, don't guess */
        if (rx_fire) { rx_fire = 0; servo_fire(SERVO_AI, now); }
        if (rx_freeze) {
          rx_freeze = 0;
          if (now >= ai_freeze_ready) {
            human_frozen_until = now + FREEZE_MS;
            ai_freeze_ready = now + FREEZE_COOLDOWN_MS;
            PLAY(SND_SIREN);
          }
        }
        mirror_fire_at = 0;
      } else if (game == 3) {
        ai_dir = 0;                     /* AI vs AI without the laptop: nobody to copy, stand still */
        mirror_fire_at = 0;
      } else {
#if MIRROR_AI
        ai_dir = mirror_dir(level);
        if (mirror_fire_at && now >= mirror_fire_at) {
          mirror_fire_at = 0;
          servo_fire(SERVO_AI, now);
        }
#else
        ai_dir = 0;                     /* camera-only test build: no camera AI -> stand still */
        mirror_fire_at = 0;
#endif
      }
    } else {
      rx_fire = rx_freeze = 0;          /* frozen: ignore queued actions */
    }
    motor_ai(ai_dir);

    /* ---------------- FROZEN: beep until the freeze is over ---------------- */
    if (!bz_seq) {                      /* after the siren (or any other sound) has finished */
      if (now < human_frozen_until) PLAY(SND_FROZEN_HUMAN);
      else if (now < ai_frozen_until) PLAY(SND_FROZEN_AI);
    }

    /* ---------------- GOALS ---------------- */
    uint8_t g = goal_flags_take();
    if (g && now >= goal_ready_at) {
      goal_ready_at = now + GOAL_LOCKOUT_MS;
      uint8_t human_scored = (g & GOAL_AT_AI) != 0;   /* both at once can't really happen; favour the human */
      if (human_scored) { score_human++; PLAY(SND_GOAL_HUMAN); }
      else              { score_ai++;    PLAY(SND_GOAL_AI); }
      uart_puts(human_scored ? "G H " : "G A ");
      uart_putu(score_human);
      uart_putc(' ');
      uart_putu(score_ai);
      uart_putc('\n');
    }

    /* ---------------- TIMER SOUNDS + TELEMETRY ---------------- */
    if (left <= 10 && left != last_tick_sec) {
      last_tick_sec = left;
      PLAY(SND_TICK);
    }
    if (now >= next_telemetry) {
      next_telemetry = now + TELEMETRY_MS;
      uart_puts("T ");
      uart_putu(left);
      uart_puts(game == 2 ? " P2\n" : game == 3 ? (link_up ? " AI\n" : " WAIT\n")
                : link_up ? " CAM\n" : (MIRROR_AI ? " MIR\n" : " WAIT\n"));
    }
  }

  /* ---------------- MATCH OVER ---------------- */
  motor_ai(0);
  motor_human(0);
  uart_puts("END ");
  uart_putu(score_human);
  uart_putc(' ');
  uart_putu(score_ai);
  uart_putc('\n');
  PLAY(SND_END);
  wait_ms(1500);
}

/* ============================================================== MAIN */
int main(void) {
  init_all();
  _delay_ms(50);
  if (freeze_btn_down()) {
    self_test();
    while (freeze_btn_down()) {}        /* wait for release */
  }

  uint8_t level = select_level();

  for (;;) {
    uint8_t game = lobby();             /* laptop menu (or FREEZE button) picks the game */
    play_match(game, level);
  }
}
