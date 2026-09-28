/*
 * HC-05 rename + UART test for CHEERIVY (ATmega32 @ internal 8 MHz)
 *
 * Wiring: same as the robot (HC-05 TXD -> pin 14, pin 15 -> HC-05 RXD, buzzer PD7 / pin 21).
 * Before power-on: connect HC-05 EN to HC-05 VCC and KEEP it connected (full AT mode,
 * LED blinks slowly: ~2 s on / 2 s off). AT mode always talks at 38400 baud.
 *
 * Sends, waiting for "OK" after each:
 *   1. AT                    (is anyone listening?)
 *   2. AT+NAME=CHEERIVY      (new Bluetooth name)
 *   3. AT+UART=9600,0,0      (data-mode baud the robot firmware uses)
 *
 * Buzzer result (repeats every 3 s):
 *   3 short rising beeps  = all OK. Remove EN, re-burn CHEERIVY.hex, re-pair "CHEERIVY" on the laptop.
 *   N long low beeps      = step N got no "OK".
 *     1 long  = HC-05 never answered: not in AT mode, or the TX/RX wires are broken.
 *     2 long  = rename refused (keep EN connected during the whole test and retry).
 *     3 long  = baud command refused.
 */
#ifndef F_CPU
#define F_CPU 8000000UL
#endif
#include <avr/io.h>
#include <stdint.h>
#include <util/delay.h>

#define AT_BAUD 38400UL

static void uart_init(void) {
  const uint16_t ubrr = F_CPU / (16UL * AT_BAUD) - 1;   /* 12 -> 38462 baud, 0.2% error */
  UBRRH = (uint8_t)(ubrr >> 8);
  UBRRL = (uint8_t)ubrr;
  UCSRB = (1 << RXEN) | (1 << TXEN);
  UCSRC = (1 << URSEL) | (1 << UCSZ1) | (1 << UCSZ0);  /* 8N1 */
}

static void uart_puts(const char *s) {
  while (*s) {
    while (!(UCSRA & (1 << UDRE))) {}
    UDR = *s++;
  }
}

static void uart_flush_rx(void) {
  while (UCSRA & (1 << RXC)) (void)UDR;
}

/* Wait up to timeout_ms for the letters "OK". */
static uint8_t wait_ok(uint16_t timeout_ms) {
  char prev = 0;
  for (uint32_t t = 0; t < (uint32_t)timeout_ms * 100; t++) {   /* 10 us steps */
    if (UCSRA & (1 << RXC)) {
      char c = UDR;
      if (prev == 'O' && c == 'K') return 1;
      prev = c;
    }
    _delay_us(10);
  }
  return 0;
}

static uint8_t send_cmd(const char *cmd) {
  uart_flush_rx();
  uart_puts(cmd);
  uart_puts("\r\n");
  return wait_ok(1500);
}

/* Square wave on the buzzer pin (PD7). half_us sets the pitch. */
static void tone(uint16_t ms, uint16_t half_us) {
  uint32_t cycles = (uint32_t)ms * 1000 / (2UL * half_us);
  for (uint32_t i = 0; i < cycles; i++) {
    PORTD |= (1 << PD7);
    for (uint16_t k = 0; k < half_us; k += 10) _delay_us(10);
    PORTD &= ~(1 << PD7);
    for (uint16_t k = 0; k < half_us; k += 10) _delay_us(10);
  }
}

int main(void) {
  DDRD |= (1 << PD7);          /* buzzer */
  DDRA |= (1 << PA4);          /* TB6612 STBY low: motors off during the test */
  PORTA &= ~(1 << PA4);
  uart_init();
  _delay_ms(1500);             /* let the HC-05 boot into AT mode */

  static const char *const cmds[3] = {"AT", "AT+NAME=CHEERIVY", "AT+UART=9600,0,0"};
  uint8_t failed = 0;
  for (uint8_t i = 0; i < 3 && !failed; i++) {
    uint8_t ok = send_cmd(cmds[i]);
    if (!ok && i == 0) ok = send_cmd(cmds[i]);   /* first AT sometimes gets lost */
    if (!ok) failed = i + 1;
    _delay_ms(200);
  }

  for (;;) {
    if (!failed) {
      tone(120, 400); _delay_ms(60);
      tone(120, 300); _delay_ms(60);
      tone(200, 200);
    } else {
      for (uint8_t n = 0; n < failed; n++) {
        tone(600, 900);
        _delay_ms(300);
      }
    }
    _delay_ms(3000);
  }
}
