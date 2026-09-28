/*
 * CHEERIVY — 2-PLAYER firmware (no AI, no laptop needed). ATmega32 @ internal 8 MHz (lfuse 0xE4).
 *
 *  PLAYER 1                              PLAYER 2
 *  Joystick X   PA1 / pin 39             Joystick X   PA0 / pin 40
 *  Joystick Y   PA3 / pin 37             Joystick Y   PA2 / pin 38
 *  Joystick SW  PB1 / pin 2              Joystick SW  PB0 / pin 1
 *  Motor ch B   BIN1 PC2 / pin 24        Motor ch A   AIN1 PC0 / pin 22
 *               BIN2 PC3 / pin 25                     AIN2 PC1 / pin 23
 *               PWMB PC4 / pin 26                     PWMA PD6 / pin 20
 *  Servo        PD5 (OC1A) / pin 19      Servo        PD4 (OC1B) / pin 18
 *
 *  Shared: TB6612 STBY PA4 / pin 36, buzzer PD7 / pin 21.
 *  Goal lasers: OFF in this build (USE_LASERS 0). With USE_LASERS 1:
 *    receiver on P1's goal line -> PD2 / pin 16 (P2 scores),
 *    receiver on P2's goal line -> PD3 / pin 17 (P1 scores).
 *
 *  HOW TO PLAY
 *   - Power on: one beep = ready. Press either joystick button to start.
 *     (Hold player 1's button while powering on = self-test of both motors and servos.)
 *   - Countdown beeps 3-2-1, high GO tone, then 3 minutes of play.
 *   - Joystick left/right: drive your carriage.   Joystick UP: servo push.
 *   - FREEZE DUEL: every 20-25 s (random) a rising "da-da-da-DING" plays.
 *     The first player to PRESS their joystick button after the DING wins; the OTHER player is
 *     frozen 5 s (siren; can't move or push). A short blip = unfrozen.
 *     No press within 4 s = low tone, duel cancelled.
 *     Anti-cheat: pressing your button in the 1 s before the duel, or during the "da-da-da"
 *     before the DING = you can't win that duel.
 *   - Last 10 s: a tick every second. Full time: end tune.
 *     With lasers on: winner's goal tune plays after the end tune (two beeps = draw).
 *   - Press either button to play again.
 *
 *  The HC-05 (if connected) receives status lines for the laptop show:
 *   "READY" (every second while waiting), "START LEVEL 2 2P", "T <seconds left> P2",
 *   "G H <p1> <p2>" / "G A <p1> <p2>" goals, "FREEZE 1|2" (who got frozen), "END <p1> <p2>".
 *   Nothing is received; the robot never waits for the laptop.
 */
#ifndef F_CPU
#define F_CPU 8000000UL
#endif
#include <avr/interrupt.h>
#include <avr/io.h>
#include <stdint.h>
#include <util/atomic.h>
#include <util/delay.h>

/* ============================================================== TUNING */
#define MATCH_SECONDS          180
#define JOY_LOW                350   /* X below this = left            */
#define JOY_HIGH               650   /* X above = right, Y above = push */
#define P1_DIR_SIGN            (+1)
#define P2_DIR_SIGN            (+1)
#define DUEL_MIN_MS            20000UL
#define DUEL_MAX_MS            25000UL
#define DUEL_WINDOW_MS         4000UL   /* time to press after the DING */
#define DUEL_CHEAT_MS          1000UL   /* a press this long before the DING disqualifies */
#define DUEL_DING_AT_MS        270UL    /* the DING starts 270 ms into SND_DUEL (3 x (60 + 30) ms) */
#define USE_LASERS             0        /* 0 = goal lasers off (not built yet); 1 = count goals on PD2/PD3 */
#define FREEZE_MS              5000UL
#define BTN_DEBOUNCE_MS        40
#define GOAL_LOCKOUT_MS        1500
#define UART_BAUD              9600

/* Servo angles (same as the tested v5 firmware) */
#define P2_REST_DEG            87
#define P2_STRIKE_DEG          20
#define P1_REST_DEG            90
#define P1_STRIKE_DEG          25
#define SERVO_MS_PER_DEG_X10   16
#define SERVO_SETTLE_MS        15
#define SERVO_FRAME_US         20000

#define SERVO_US(deg)          (600 + (uint16_t)(deg) * 10)
#define SWING_DEG(a, b)        ((a) > (b) ? (a) - (b) : (b) - (a))
#define TRAVEL_MS(a, b)        (SWING_DEG(a, b) * SERVO_MS_PER_DEG_X10 / 10 + SERVO_SETTLE_MS)

#define P1 0
#define P2 1

/* ============================================================== TIME (Timer0, 1 ms) */
static volatile uint32_t g_ms;
ISR(TIMER0_COMP_vect) { g_ms++; }

static uint32_t millis(void) {
  uint32_t t;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { t = g_ms; }
  return t;
}

/* ============================================================== RANDOM */
static uint16_t rng = 0xACE1;

static uint16_t rand16(void) {           /* xorshift16 */
  rng ^= rng << 7;
  rng ^= rng >> 9;
  rng ^= rng << 8;
  return rng;
}

static uint32_t rand_range(uint32_t lo, uint32_t hi) {
  return lo + ((uint32_t)rand16() * (hi - lo + 1)) / 65536UL;
}

static void rng_mix(uint16_t v) {
  rng ^= v;
  if (!rng) rng = 0xACE1;
  rand16();
}

/* ============================================================== SERVOS (Timer1, 1 us ticks) */
static const uint8_t rest_deg[2] = {P1_REST_DEG, P2_REST_DEG};
static const uint8_t strike_deg[2] = {P1_STRIKE_DEG, P2_STRIKE_DEG};
static uint32_t servo_back_at[2], servo_ready_at[2];
static uint8_t servo_out[2];

static void servo_write(uint8_t p, uint16_t us) {
  if (p == P1) OCR1A = us; else OCR1B = us;
}

static void servo_init(void) {
  DDRD |= (1 << PD4) | (1 << PD5);
  TCCR1A = (1 << COM1A1) | (1 << COM1B1) | (1 << WGM11);   /* fast PWM 14, TOP = ICR1, /8 */
  TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);
  ICR1 = SERVO_FRAME_US;
  servo_write(P1, SERVO_US(P1_REST_DEG));
  servo_write(P2, SERVO_US(P2_REST_DEG));
}

static void servo_fire(uint8_t p, uint32_t now) {
  if (now < servo_ready_at[p]) return;
  uint16_t travel = TRAVEL_MS(rest_deg[p], strike_deg[p]);
  servo_write(p, SERVO_US(strike_deg[p]));
  servo_out[p] = 1;
  servo_back_at[p] = now + travel;
  servo_ready_at[p] = now + 2UL * travel;
}

static void servo_update(uint32_t now) {
  for (uint8_t p = 0; p < 2; p++) {
    if (servo_out[p] && now >= servo_back_at[p]) {
      servo_write(p, SERVO_US(rest_deg[p]));
      servo_out[p] = 0;
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

static void motor(uint8_t p, int8_t d) { /* -1 left, 0 stop, +1 right */
  if (p == P2) {                          /* channel A */
    if (d < 0)      { PORTC |= (1 << PC0);  PORTC &= ~(1 << PC1); PORTD |= (1 << PD6); }
    else if (d > 0) { PORTC &= ~(1 << PC0); PORTC |= (1 << PC1);  PORTD |= (1 << PD6); }
    else            { PORTD &= ~(1 << PD6); }
  } else {                                /* channel B */
    if (d < 0)      { PORTC |= (1 << PC2);  PORTC &= ~(1 << PC3); PORTC |= (1 << PC4); }
    else if (d > 0) { PORTC &= ~(1 << PC2); PORTC |= (1 << PC3);  PORTC |= (1 << PC4); }
    else            { PORTC &= ~(1 << PC4); }
  }
}

static void motors_stop(void) { motor(P1, 0); motor(P2, 0); }

/* ============================================================== JOYSTICKS */
static const uint8_t adc_x[2] = {1, 0};
static const uint8_t adc_y[2] = {3, 2};
static const int8_t dir_sign[2] = {P1_DIR_SIGN, P2_DIR_SIGN};

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

static int8_t joy_dir(uint16_t x) { return (x < JOY_LOW) ? -1 : (x > JOY_HIGH) ? 1 : 0; }

static uint8_t btn_down(uint8_t p) {
  return p == P1 ? !(PINB & (1 << PB1)) : !(PINB & (1 << PB0));
}

/* Debounced press detection: returns 1 once per press. */
static uint8_t btn_prev[2];
static uint32_t btn_edge_at[2];

static void btn_sync(void) {              /* forget presses already in progress */
  btn_prev[P1] = btn_down(P1);
  btn_prev[P2] = btn_down(P2);
}

static uint8_t btn_pressed(uint8_t p, uint32_t now) {
  uint8_t d = btn_down(p);
  uint8_t hit = d && !btn_prev[p] && (now - btn_edge_at[p] >= BTN_DEBOUNCE_MS);
  if (d != btn_prev[p]) btn_edge_at[p] = now;
  btn_prev[p] = d;
  return hit;
}

/* ============================================================== BUZZER (Timer2, non-blocking) */
typedef struct { uint8_t ocr; uint8_t cs; } Note;   /* f = 62500 / (1 + ocr) Hz; cs = 10 ms units */

static const Note SND_READY[]    = {{45, 8}};
static const Note SND_COUNT[]    = {{62, 15}};
static const Note SND_GO[]       = {{30, 40}};
static const Note SND_DUEL[]     = {{70, 6}, {0, 3}, {50, 6}, {0, 3}, {35, 6}, {0, 3}, {25, 25}};
static const Note SND_FROZEN[]   = {{30, 4}, {70, 4}, {30, 4}, {70, 4}, {30, 4}, {70, 4}, {30, 4}, {70, 4}};
static const Note SND_UNFREEZE[] = {{40, 5}, {0, 3}, {30, 8}};
static const Note SND_NOBODY[]   = {{83, 25}};
static const Note SND_TICK[]     = {{30, 3}};
static const Note SND_GOAL_P1[]  = {{62, 8}, {49, 8}, {41, 8}, {30, 30}};
static const Note SND_GOAL_P2[]  = {{41, 12}, {49, 12}, {62, 12}, {83, 30}};
static const Note SND_DRAW[]     = {{45, 8}, {0, 10}, {45, 8}};
static const Note SND_END[]      = {{62, 60}, {0, 10}, {41, 15}, {0, 5}, {41, 15}, {0, 5}, {41, 15}};
static const Note SND_BEEP1[]    = {{45, 8}};
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
    OCR2 = n.ocr;
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

static void buzz_update(uint32_t now) {
  if (bz_seq && now >= bz_note_end) { bz_i++; buzz_note(); }
}

static void wait_ms(uint32_t ms) {      /* blocking wait that keeps sounds and servos running */
  uint32_t end = millis() + ms;
  while (millis() < end) {
    uint32_t now = millis();
    buzz_update(now);
    servo_update(now);
  }
}

/* ============================================================== UART (status out only) */
static void uart_init(void) {
  const uint16_t ubrr = F_CPU / (16UL * UART_BAUD) - 1;
  UBRRH = (uint8_t)(ubrr >> 8);
  UBRRL = (uint8_t)ubrr;
  UCSRB = (1 << TXEN);
  UCSRC = (1 << URSEL) | (1 << UCSZ1) | (1 << UCSZ0);  /* 8N1 */
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

static void uart_score(const char *tag, uint8_t s1, uint8_t s2) {
  uart_puts(tag);
  uart_putu(s1);
  uart_putc(' ');
  uart_putu(s2);
  uart_putc('\n');
}

/* ============================================================== GOAL LASERS (optional) */
#define GOAL_AT_P1  1                    /* beam on P1's goal line broke -> P2 scores */
#define GOAL_AT_P2  2                    /* beam on P2's goal line broke -> P1 scores */
static volatile uint8_t goal_flags;

ISR(INT0_vect) { goal_flags |= GOAL_AT_P1; }
ISR(INT1_vect) { goal_flags |= GOAL_AT_P2; }

static void lasers_init(void) {
  DDRD &= ~((1 << PD2) | (1 << PD3));
  PORTD |= (1 << PD2) | (1 << PD3);                  /* pull-ups: nothing plugged in = no goals */
  MCUCR |= (1 << ISC01) | (1 << ISC11);              /* falling edge = beam just broke */
  GIFR = (1 << INTF0) | (1 << INTF1);
  GICR |= (1 << INT0) | (1 << INT1);
}

static uint8_t goal_flags_take(void) {
  uint8_t g;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { g = goal_flags; goal_flags = 0; }
  return g;
}

/* ============================================================== SELF-TEST */
static void self_test(void) {
  PLAY(SND_BEEP1); wait_ms(600);
  motor(P2, -1); wait_ms(400); motor(P2, 0); wait_ms(400);
  motor(P2, +1); wait_ms(400); motor(P2, 0); wait_ms(400);
  servo_fire(P2, millis()); wait_ms(600);
  PLAY(SND_DRAW); wait_ms(800);
  motor(P1, -1); wait_ms(400); motor(P1, 0); wait_ms(400);
  motor(P1, +1); wait_ms(400); motor(P1, 0); wait_ms(400);
  servo_fire(P1, millis()); wait_ms(600);
  PLAY(SND_END); wait_ms(1500);
}

/* ============================================================== INIT */
static void init_all(void) {
  servo_init();                         /* first: both servos straight to REST */

  uint8_t v = MCUCSR | (1 << JTD);      /* free PC2..PC5 from JTAG: two writes in 4 cycles */
  MCUCSR = v;
  MCUCSR = v;

  DDRB &= ~((1 << PB0) | (1 << PB1));   /* joystick buttons, active low */
  PORTB |= (1 << PB0) | (1 << PB1);
  DDRD |= (1 << PD7);                   /* buzzer */

  TCCR0 = (1 << WGM01) | (1 << CS01) | (1 << CS00);   /* CTC, /64 */
  OCR0 = 124;                                         /* 8 MHz / 64 / 125 = 1 kHz */
  TIMSK |= (1 << OCIE0);

  motors_init();
  motors_stop();
  adc_init();
  uart_init();
  if (USE_LASERS) lasers_init();        /* off: PD2/PD3 stay plain inputs, no interrupts, no goals */
  sei();
}

/* ============================================================== WAIT FOR START */
static void wait_for_start(void) {
  motors_stop();
  PLAY(SND_READY);
  uint32_t next_ready = 0;
  btn_sync();
  for (;;) {
    uint32_t now = millis();
    buzz_update(now);
    servo_update(now);
    rng_mix(adc_read(7) ^ (uint16_t)now);          /* floating pin noise + time */
    if (now >= next_ready) {
      next_ready = now + 1000;
      uart_puts("READY\n");
    }
    if (btn_pressed(P1, now) || btn_pressed(P2, now)) {
      rng_mix((uint16_t)millis());
      return;
    }
  }
}

/* ============================================================== MATCH */
static void play_match(void) {
  for (uint8_t i = 0; i < 3; i++) { PLAY(SND_COUNT); wait_ms(1000); }
  PLAY(SND_GO);
  uart_puts("START LEVEL 2 2P\n");

  uint32_t start = millis();
  uint32_t frozen_until[2] = {0, 0};
  uint8_t frozen[2] = {0, 0};
  uint32_t last_press[2] = {0, 0};
  uint8_t score[2] = {0, 0};
  uint32_t next_duel = start + rand_range(DUEL_MIN_MS, DUEL_MAX_MS);
  uint8_t duel = 0, can_win[2] = {0, 0};
  uint32_t duel_open_at = 0, duel_end = 0, goal_ready_at = 0, next_telemetry = 0;
  uint16_t last_tick_sec = 0xFFFF;
  goal_flags_take();
  btn_sync();

  for (;;) {
    uint32_t now = millis();
    uint32_t elapsed = now - start;
    if (elapsed >= (uint32_t)MATCH_SECONDS * 1000) break;
    uint16_t left = MATCH_SECONDS - (uint16_t)(elapsed / 1000);

    buzz_update(now);
    servo_update(now);

    uint8_t pressed[2];
    for (uint8_t p = 0; p < 2; p++) {
      pressed[p] = btn_pressed(p, now);
      if (pressed[p]) last_press[p] = now;
    }

    /* ---------------- FREEZE DUEL ---------------- */
    if (!duel && now >= next_duel) {
      if (left > 12) {                   /* no duel in the final seconds */
        duel = 1;
        duel_open_at = now + DUEL_DING_AT_MS;
        duel_end = duel_open_at + DUEL_WINDOW_MS;
        for (uint8_t p = 0; p < 2; p++)
          can_win[p] = !(last_press[p] && now - last_press[p] < DUEL_CHEAT_MS) && !frozen[p];
        PLAY(SND_DUEL);
        pressed[P1] = pressed[P2] = 0;
      } else {
        next_duel = 0xFFFFFFFFUL;
      }
    } else if (duel && now < duel_open_at) {
      for (uint8_t p = 0; p < 2; p++)    /* pressed during "da-da-da", before the DING: jumped the gun */
        if (pressed[p]) can_win[p] = 0;
    } else if (duel) {
      uint8_t w1 = pressed[P1] && can_win[P1];
      uint8_t w2 = pressed[P2] && can_win[P2];
      if (w1 || w2) {
        uint8_t winner = (w1 && w2) ? (rand16() & 1) : (w1 ? P1 : P2);
        uint8_t loser = winner == P1 ? P2 : P1;
        frozen[loser] = 1;
        frozen_until[loser] = now + FREEZE_MS;
        motor(loser, 0);
        PLAY(SND_FROZEN);
        uart_puts(loser == P1 ? "FREEZE 1\n" : "FREEZE 2\n");
        duel = 0;
        next_duel = now + rand_range(DUEL_MIN_MS, DUEL_MAX_MS);
      } else if (now >= duel_end) {
        duel = 0;
        PLAY(SND_NOBODY);
        next_duel = now + rand_range(DUEL_MIN_MS, DUEL_MAX_MS);
      }
    }

    /* ---------------- PLAYERS ---------------- */
    for (uint8_t p = 0; p < 2; p++) {
      if (frozen[p] && now >= frozen_until[p]) {
        frozen[p] = 0;
        PLAY(SND_UNFREEZE);
      }
      if (frozen[p]) {
        motor(p, 0);
        continue;
      }
      uint16_t x = adc_read(adc_x[p]), y = adc_read(adc_y[p]);
      motor(p, dir_sign[p] * joy_dir(x));
      if (y > JOY_HIGH) servo_fire(p, now);          /* does nothing until the servo is back */
    }

    /* ---------------- GOALS (only with USE_LASERS 1) ---------------- */
    uint8_t g = USE_LASERS ? goal_flags_take() : 0;
    if (g && now >= goal_ready_at) {
      goal_ready_at = now + GOAL_LOCKOUT_MS;
      uint8_t p1_scored = (g & GOAL_AT_P2) != 0;
      if (p1_scored) { score[P1]++; PLAY(SND_GOAL_P1); }
      else           { score[P2]++; PLAY(SND_GOAL_P2); }
      uart_score(p1_scored ? "G H " : "G A ", score[P1], score[P2]);
    }

    /* ---------------- CLOCK ---------------- */
    if (left <= 10 && left != last_tick_sec && !duel) {
      last_tick_sec = left;
      PLAY(SND_TICK);
    }
    if (now >= next_telemetry) {
      next_telemetry = now + 1000;
      uart_puts("T ");
      uart_putu(left);
      uart_puts(" P2\n");
    }
  }

  /* ---------------- FULL TIME ---------------- */
  motors_stop();
  uart_score("END ", score[P1], score[P2]);
  PLAY(SND_END);
  wait_ms(2000);
  if (score[P1] || score[P2]) {
    if (score[P1] > score[P2])      PLAY(SND_GOAL_P1);
    else if (score[P2] > score[P1]) PLAY(SND_GOAL_P2);
    else                            PLAY(SND_DRAW);
    wait_ms(1500);
  }
}

/* ============================================================== MAIN */
int main(void) {
  init_all();
  _delay_ms(50);
  if (btn_down(P1)) {
    self_test();
    while (btn_down(P1)) {}             /* wait for release */
  }
  for (;;) {
    wait_for_start();
    play_match();
  }
}
