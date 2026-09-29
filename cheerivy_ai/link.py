"""
B6 — Link to the ATmega32 through the HC-05 (Bluetooth serial).

Sends single bytes. The current move command is re-sent every HEARTBEAT_S so
the firmware can tell the laptop is alive (and fall back to Mirror AI if not).
With no HC-05 found it runs in SIM mode and keeps retrying in the background,
so you can start this program before or after powering the robot, and a dropped
Bluetooth link reconnects by itself.
"""
import threading
import time

import serial
import serial.tools.list_ports

import config as C


USB_SERIAL = ("usbserial", "wchusb", "slab", "ch340", "cp210", "ft232", "usb-serial", "usb serial")


def _windows_bt_outgoing(p):
    """Windows shows a paired HC-05 as TWO "Standard Serial over Bluetooth link" COM ports.
    The outgoing one (the one to open) carries the module's address in its hardware id;
    the incoming one has 000000000000 there."""
    hwid = (p.hwid or "").upper()
    return "BTHENUM" in hwid and "000000000000" not in hwid


def find_port():
    for p in serial.tools.list_ports.comports():
        name = f"{p.device} {p.description}".lower()
        if "incoming-port" in name or "bluetooth-modem" in name:
            continue
        if any(k in name for k in ("hc-05", "hc05", "hc-06", "cheerivy") + USB_SERIAL):
            return p.device
        if _windows_bt_outgoing(p):
            return p.device
    return None


class Link:
    def __init__(self, port=None, sink=None, enabled=True):
        """sink: optional object with on_command(cmd) — the simulator uses this.
        enabled=False never opens a serial port (simulator / tracking-only test)."""
        self.sink = sink
        self.ser = None
        self.enabled = enabled
        self.port_hint = port
        self.running = True
        self.swap = C.SWAP_LR   # motor wired the other way round -> swap L and R
        self.swap1 = C.SWAP_LR_P1   # the same for player 1's carriage (AI vs AI)
        self.current = None
        self.current1 = None    # AI vs AI: player 1's move ('B' 'N' 'M' on the wire)
        self.last_send = 0.0
        self.sent_count = 0
        self.echo_count = 0     # lowercase echoes from the MCU = proof the link works both ways
        self._rx = ""
        self._wlock = threading.Lock()   # the main loop and the heartbeat thread both write
        if enabled:
            self._try_open(verbose=True)
            threading.Thread(target=self._reconnect_loop, daemon=True).start()
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _try_open(self, verbose=False):
        port = self.port_hint or find_port()
        if not port:
            if verbose:
                print("[link] no HC-05 found yet — will keep trying. Ports:")
                for p in serial.tools.list_ports.comports():
                    print("        ", p.device, "-", p.description)
            return
        try:
            # Opening a Bluetooth port can block for seconds while it connects.
            # write_timeout > 0: each write waits until it has really been sent. With 0 (non-blocking),
            # Windows starts a new Bluetooth write while the last one is still pending and bytes get
            # dropped, so the robot hears gaps and keeps flipping to Mirror AI.
            ser = serial.Serial(port, C.BAUD, timeout=0, write_timeout=0.3)
            self.ser = ser
            self.current = None     # resend the current command straight away
            print(f"[link] connected to {port} @ {C.BAUD}")
        except (serial.SerialException, OSError) as e:
            if verbose:
                print(f"[link] could not open {port} ({e}) — is the robot powered? Retrying...")

    def _reconnect_loop(self):
        while self.running:
            time.sleep(2.0)
            if self.ser is None and self.running:
                self._try_open()

    def _heartbeat_loop(self):
        """Re-send the current move command on a steady clock, independent of the camera loop.
        The firmware drops to Mirror AI after 400 ms of silence, and a slow camera frame or a
        Windows hiccup in the main loop must not cause that."""
        while self.running:
            time.sleep(C.HEARTBEAT_S / 2)
            cmd = self.current
            if cmd is not None and self.ser and time.time() - self.last_send > C.HEARTBEAT_S:
                self._write(self._wire(cmd) + (self._wire1(self.current1) if self.current1 else ""))
                self.last_send = time.time()

    def _drop(self, why):
        if self.ser:
            print(f"[link] lost connection ({why}) — reconnecting...")
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    @property
    def mode(self):
        if self.ser:
            return "HC-05"
        return "RECONNECTING" if self.enabled else "SIM"

    def _write(self, cmd):
        with self._wlock:
            ser = self.ser
            if ser:
                try:
                    ser.write(cmd.encode())
                except serial.SerialTimeoutException:
                    pass                      # Bluetooth busy for a moment: skip this byte, the heartbeat resends
                except (serial.SerialException, OSError) as e:
                    self._drop(e)
            if self.sink:
                self.sink.on_command(cmd)
            self.sent_count += 1

    def _wire(self, cmd):
        return {"L": "R", "R": "L"}.get(cmd, cmd) if self.swap else cmd

    def _wire1(self, cmd):
        if self.swap1:
            cmd = {"L": "R", "R": "L"}.get(cmd, cmd)
        return {"L": "B", "R": "N", "S": "M"}[cmd]

    def move1(self, cmd):
        """AI vs AI: move player 1's carriage ('L' 'R' 'S', like move()). None = not in AI vs AI."""
        if cmd is None:
            self.current1 = None
            return
        if cmd != self.current1:
            self._write(self._wire1(cmd))
            self.current1 = cmd

    def move(self, cmd):
        now = time.time()
        if cmd != self.current or now - self.last_send > C.HEARTBEAT_S:
            self._write(self._wire(cmd))
            self.current, self.last_send = cmd, now

    def send(self, cmd):
        """One-shot commands: 'F' fire, 'Z' freeze (AI side); 'G' fire, 'Y' freeze (player 1, AI vs AI)."""
        self._write(cmd)

    def read_lines(self):
        """Status lines from the MCU (e.g. 'T 179 CAM'). Lowercase echo bytes are counted, not returned."""
        ser = self.ser
        if not ser:
            return []
        try:
            n = ser.in_waiting
            data = ser.read(n).decode(errors="ignore") if n else ""
        except (serial.SerialException, OSError) as e:
            self._drop(e)
            return []
        for ch in data:
            if ch in "lrsfzbnmgy":
                self.echo_count += 1
            else:
                self._rx += ch
        *lines, self._rx = self._rx.split("\n")
        return [x.strip() for x in lines if x.strip()]

    def close(self):
        self.running = False
        if self.ser:
            self._write("S")
            try:
                self.ser.close()
            except Exception:
                pass
