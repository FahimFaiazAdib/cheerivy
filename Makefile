# CHEERIVY firmware — ATmega32 @ internal 8 MHz
#   make          build main.hex
#   make flash    flash with a USBasp  (does NOT touch fuses)
MCU    = atmega32
F_CPU  = 8000000UL
CFLAGS = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -Wall -Wextra -std=gnu11

main.hex: main.elf
	avr-objcopy -O ihex -R .eeprom main.elf main.hex
	avr-size --mcu=$(MCU) -C main.elf

main.elf: main.c
	avr-gcc $(CFLAGS) -o main.elf main.c

flash: main.hex
	avrdude -c usbasp -p m32 -U flash:w:main.hex:i

clean:
	rm -f main.elf main.hex

.PHONY: flash clean
