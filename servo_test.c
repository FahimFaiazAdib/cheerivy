/*
 * CHEERIVY servo test — find the right REST and STRIKE angles, and check a servo that acts up.
 * Same pins and servo timing as main.c. Burn SERVO_TEST.hex, test, then burn CHEERIVY.hex again.
 *
 *   Joystick 1 (X PA1, Y PA3, button PB1) -> player 1 servo  (PD5 / pin 19)
 *   Joystick 2 (X PA0, Y PA2, button PB0) -> player 2 / AI servo (PD4 / pin 18)
 *
 *   X left / right    move that servo slowly (about 20° per second), 1° steps
 *   Y up              test strike: full-speed swing of SWING_DEG from here, then back here
 *   button            beep + print the angle again
 *
 * Every change is printed over the HC-05 (9600 baud), e.g. "P1 100" = player 1 at 100°.
 * A short beep every 10°, a long beep at 90° (the centre).
 * At power-on both servos go to the angles main.c uses for REST (P1 100°, P2 87°).
 */
#define F_CPU 8000000UL
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include <stdint.h>

#define SWING_DEG   67
#define START_P1    100
#define START_P2    87
#define JOY_LOW     350
#define JOY_HIGH    650
#define STEP_MS     50            /* 1° per 50 ms while the stick is held */
#define SERVO_US(d) (600 + (uint16_t)(d) * 10)

static void uart_putc(char c) { while (!(UCSRA & (1 << UDRE))) {} UDR = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }
static void uart_putu(uint16_t v) {
  char b[6]; uint8_t i = 0;
  do { b[i++] = '0' + v % 10; v /= 10; } while (v);
  while (i) uart_putc(b[--i]);
}

static uint16_t adc_read(uint8_t ch) {
  ADMUX = (1 << REFS0) | (ch & 0x0F);
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) {}
  return ADC;
}

static void beep(uint8_t ms10, uint8_t ocr) {  /* Timer2 CTC on OC2 (PD7), blocking */
  OCR2 = ocr;
  TCCR2 = (1 << WGM21) | (1 << COM20) | (1 << CS22) | (1 << CS21);   /* /256 */
  while (ms10--) _delay_ms(10);
  TCCR2 = 0;
  PORTD &= ~(1 << PD7);
}

static void servo_set(uint8_t p, int16_t deg) {   /* p = 1: player 1 (OC1A), 2: player 2 (OC1B) */
  uint16_t us = SERVO_US(deg);
  if (p == 1) OCR1A = us; else OCR1B = us;
}

static void report(uint8_t p, int16_t deg) {
  uart_puts(p == 1 ? "P1 " : "P2 ");
  uart_putu(deg);
  uart_puts("\r\n");
}

int main(void) {
  uint8_t v = MCUCSR | (1 << JTD);     /* JTAG off, as in main.c */
  MCUCSR = v; MCUCSR = v;

  DDRD |= (1 << PD4) | (1 << PD5) | (1 << PD7);
  TCCR1A = (1 << COM1A1) | (1 << COM1B1) | (1 << WGM11);
  TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);   /* 1 us per tick */
  ICR1 = 20000;                                         /* 50 Hz */

  DDRB &= ~((1 << PB0) | (1 << PB1));
  PORTB |= (1 << PB0) | (1 << PB1);
  DDRA |= (1 << PA4); PORTA &= ~(1 << PA4);            /* motor driver off: carriages stay put */

  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1);
  const uint16_t ubrr = F_CPU / (16UL * 9600) - 1;
  UBRRH = ubrr >> 8; UBRRL = ubrr;
  UCSRB = (1 << TXEN);
  UCSRC = (1 << URSEL) | (1 << UCSZ1) | (1 << UCSZ0);

  int16_t deg[3] = {0, START_P1, START_P2};
  const uint8_t xch[3] = {0, 1, 0}, ych[3] = {0, 3, 2}, btn[3] = {0, PB1, PB0};
  uint8_t fired[3] = {0, 0, 0}, pressed[3] = {0, 0, 0};
  servo_set(1, deg[1]);
  servo_set(2, deg[2]);
  uart_puts("\r\nSERVO TEST  (joystick X = move, Y up = strike, button = print)\r\n");
  report(1, deg[1]);
  report(2, deg[2]);
  beep(15, 60);

  for (;;) {
    for (uint8_t p = 1; p <= 2; p++) {
      uint16_t x = adc_read(xch[p]), y = adc_read(ych[p]);
      int8_t d = (x < JOY_LOW) ? -1 : (x > JOY_HIGH) ? 1 : 0;
      if (d) {
        int16_t n = deg[p] + d;
        if (n >= 0 && n <= 180) {
          deg[p] = n;
          servo_set(p, n);
          report(p, n);
          if (n == 90) beep(20, 40); else if (n % 10 == 0) beep(3, 60);
        }
      }
      if (y > JOY_HIGH && !fired[p]) {             /* test strike from here, same as the game */
        fired[p] = 1;
        int16_t to = deg[p] - SWING_DEG;
        if (to < 0) to = 0;
        uart_puts(p == 1 ? "P1 strike " : "P2 strike ");
        uart_putu(deg[p]); uart_puts(" -> "); uart_putu(to); uart_puts("\r\n");
        servo_set(p, to);
        _delay_ms(122);                            /* 67° x 1.6 ms + 15 ms, as main.c */
        servo_set(p, deg[p]);
        _delay_ms(122);
      } else if (y < JOY_HIGH - 100) {
        fired[p] = 0;
      }
      uint8_t down = !(PINB & (1 << btn[p]));
      if (down && !pressed[p]) { report(p, deg[p]); beep(10, 30); }
      pressed[p] = down;
    }
    _delay_ms(STEP_MS);
  }
}
