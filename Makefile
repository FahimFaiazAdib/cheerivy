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

# Test build: camera AI only (no Mirror AI fallback, no two-player mode).
camera-only: main.c
	avr-gcc $(CFLAGS) -DMIRROR_AI=0 -DALLOW_2P=0 -o camera_only.elf main.c
	avr-objcopy -O ihex -R .eeprom camera_only.elf CHEERIVY_camera_only.hex
	avr-size --mcu=$(MCU) -C camera_only.elf

clean:
	rm -f main.elf main.hex

.PHONY: flash clean camera-only

servo-test: servo_test.c
	avr-gcc $(CFLAGS) -o servo_test.elf servo_test.c
	avr-objcopy -O ihex -R .eeprom servo_test.elf SERVO_TEST.hex
	avr-size --mcu=$(MCU) -C servo_test.elf
