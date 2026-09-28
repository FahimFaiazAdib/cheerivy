"""
Bluetooth link test: how steady is the laptop -> HC-05 -> ATmega connection?

    python linktest.py COM10

Sends 'S' (stop, harmless) every 50 ms for 8 s, exactly like the AI's heartbeat, and times the
echoes that come back from the robot. The robot switches to Mirror AI when it hears nothing
for 400 ms (older firmware) or 1.5 s (newer firmware), so the longest gap is what matters.
Close main.py first: only one program can use the port.
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
DURATION, PERIOD = 8.0, 0.05

ser = serial.Serial(port, 9600, timeout=0, write_timeout=0.3)
time.sleep(0.5)
ser.reset_input_buffer()
print(f"connected to {port}; sending for {DURATION:.0f} s ...")

sent = write_ms_max = 0
echoes, mode_lines, buf = [], 0, ""
t0 = next_send = time.time()
while time.time() - t0 < DURATION:
    now = time.time()
    if now >= next_send:
        w0 = time.time()
        try:
            ser.write(b"S")
            sent += 1
        except serial.SerialTimeoutException:
            print("  write timed out")
        write_ms_max = max(write_ms_max, (time.time() - w0) * 1000)
        next_send += PERIOD
    data = ser.read(ser.in_waiting or 1).decode(errors="ignore")
    for ch in data:
        if ch == "s":
            echoes.append(time.time())
        else:
            buf += ch
    time.sleep(0.002)
ser.close()

mode_lines = buf.count("MODE MIRROR")
gaps = [(b - a) * 1000 for a, b in zip(echoes, echoes[1:])]
print(f"sent {sent} bytes, got {len(echoes)} echoes back ({100 * len(echoes) / max(sent, 1):.0f}%)")
print(f"slowest single write: {write_ms_max:.0f} ms")
if gaps:
    print(f"gap between echoes: typical {sorted(gaps)[len(gaps) // 2]:.0f} ms, "
          f"longest {max(gaps):.0f} ms, gaps over 400 ms: {sum(g > 400 for g in gaps)}")
print(f"robot switched to Mirror {mode_lines} times during the test")
