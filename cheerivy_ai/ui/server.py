"""
CHEERIVY screen server: serves the browser UI (ui/web/) and streams the game state to it.

    python ui/server.py                 (from cheerivy_ai/) -> opens http://localhost:8316
    python ui/server.py --no-browser

Standard library only (nothing to pip install). The browser gets the state as Server-Sent Events
(GET /events) and sends key presses with POST /key.

Right now it runs the game flow on its own (SIMULATOR): the keyboard stands in for the robot's
joysticks and the laser goals. Later main.py drives the same Flow from the robot.

Simulator keys:
    Player 1   W A S D  joystick     Space  button     Q  back (= hold down)
    Player 2   arrows   joystick     Enter  button     Backspace  back
    H  both buttons held 3 s (pause)     G  goal player 1     K  goal player 2 / AI
    Esc  home     F1  settings     `  show/hide the dev panel (LCD + log)
"""
import argparse
import faulthandler
import json
import mimetypes
import os
import signal
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
from flow import Flow  # noqa: E402
from play import PlayWatcher, SimTable  # noqa: E402
from sound import Sound  # noqa: E402
import config as C  # noqa: E402
from arena import Arena  # noqa: E402

# board shape for the AI VISION drawing (cm). Later: the calibrated polygon from calib.json.
ARENA = {"w": C.ARENA_W, "h": C.ARENA_H, "poly": [list(p) for p in Arena().poly],
         "rail": [C.X0, C.X0 + C.BASE_W], "depth": C.CARRIAGE_DEPTH, "cw": C.CARRIAGE_W, "r": C.BALL_RADIUS}

PORT = 8316
WEB = os.path.join(HERE, "web")
TICK_S = 0.05

SIM_KEYS = {
    "KeyW": ("dir", 1, "U"), "KeyA": ("dir", 1, "L"), "KeyS": ("dir", 1, "D"), "KeyD": ("dir", 1, "R"),
    "Space": ("btn", 1), "KeyQ": ("back", 1),
    "ArrowUp": ("dir", 2, "U"), "ArrowLeft": ("dir", 2, "L"), "ArrowDown": ("dir", 2, "D"),
    "ArrowRight": ("dir", 2, "R"), "Enter": ("btn", 2), "NumpadEnter": ("btn", 2), "Backspace": ("back", 2),
    "KeyH": ("pause",), "KeyG": ("goal", 1), "KeyK": ("goal", 2),
}
ORGANISER_KEYS = {"Escape": ("home",), "F1": ("settings",)}
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class Hub:
    """The one Flow, shared by the tick thread and the web handlers."""

    def __init__(self, flow, keys, table=None, sound=None):
        self.flow, self.keys = flow, keys
        self.table, self.sound = table, sound       # simulated robot + camera, laptop sound
        self.watcher = PlayWatcher(table.slope if table else (0.0, 0.0))
        self.board = None
        self.cond = threading.Condition()
        self.version, self.data = 0, "{}"
        self.last = time.monotonic()
        self.extra = {}                             # extra fields for the page (live: {"video": True})
        self.vcond = threading.Condition()          # live camera picture (JPEG) for /video
        self.video, self.video_seq = None, 0

    def set_video(self, jpg):
        with self.vcond:
            self.video, self.video_seq = jpg, self.video_seq + 1
            self.vcond.notify_all()

    def feed(self, board, events=()):
        """Live game: the camera AI's view of the table (and play events from it), once per frame."""
        with self.cond:
            self.board = board
            for ev in events:
                self.flow.play(ev)

    def event(self, ev):
        with self.cond:
            self.flow.event(ev, time.monotonic())
            self._publish()

    def tick(self):
        with self.cond:
            now = time.monotonic()
            dt, self.last = min(0.2, now - self.last), now
            self.flow.tick(now)
            if self.table:
                self.board, goal = self.table.step(dt, now, self.flow.placer)
                live = not self.table.locked
                for ev in self.watcher.update(now, self.board["ball"] if live else None,
                                              self.board["vel"] if live else None,
                                              {1: self.board["p1_x"], 2: self.board["ai_x"]}):
                    self.flow.play(ev)
                if goal:                            # an own goal: the conceder struck it last
                    own = "own" if self.watcher.last_touch == 3 - goal else ""
                    self.flow.event(("goal", goal, own), now)
            if self.sound:
                self.sound.update(dt, now)
            self._publish()

    def robot(self, cmd):
        """Commands the Flow sends to the robot: here they go to the simulated table."""
        if self.table:
            self.table.command(cmd, time.monotonic())
            if cmd == "unlock":
                self.watcher.reset()
                self.watcher.touch(self.table.striker)

    def _publish(self):
        snap = {**self.flow.snapshot(), "arena": ARENA, **self.extra}
        if self.board and self.flow.screen in ("prematch", "ready", "countdown", "live", "goal", "pause", "debug"):
            snap["board"] = self.board
        d = json.dumps(snap, separators=(",", ":"))
        if d != self.data:
            self.data, self.version = d, self.version + 1
            self.cond.notify_all()

    def run(self):
        while True:
            self.tick()
            time.sleep(TICK_S)


class Handler(BaseHTTPRequestHandler):
    hub = None

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/events":
            return self._events()
        if path == "/video":
            return self._video()
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/key":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            key = json.loads(self.rfile.read(n) or b"{}").get("key")
        except ValueError:
            key = None
        ev = self.hub.keys.get(key)
        if ev:
            self.hub.event(ev)
        self.send_response(204)
        self.end_headers()

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        hub, seen = self.hub, -1
        try:
            while True:
                with hub.cond:
                    hub.cond.wait_for(lambda: hub.version != seen, timeout=10)
                    v, data = hub.version, hub.data
                self.wfile.write(b": ping\n\n" if v == seen else f"data: {data}\n\n".encode())
                self.wfile.flush()
                seen = v
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _video(self):
        """The live top-down camera picture as MJPEG (an <img> shows it; the page draws on top)."""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        hub, seen = self.hub, -1
        try:
            while True:
                with hub.vcond:
                    hub.vcond.wait_for(lambda: hub.video_seq != seen, timeout=5)
                    jpg, seen = hub.video, hub.video_seq
                if jpg is None:
                    continue
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def log_message(self, *a):
        pass


def serve(hub, port=PORT, open_browser=True, label=""):
    """Run the web server + game clock in background threads. Returns the page's address."""
    Handler.hub = hub
    threading.Thread(target=hub.run, daemon=True, name="game").start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="web").start()
    url = f"http://localhost:{port}"
    print(f"CHEERIVY screen{label} at {url}  (F in the browser = fullscreen)")
    if open_browser:
        webbrowser.open(url)
    return url


def main():
    # If the screen ever freezes: `kill -USR1 <pid>` prints where every thread is stuck.
    faulthandler.enable()
    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-sound", action="store_true", help="no crowd / commentary on the laptop")
    args = ap.parse_args()

    flow = Flow(sim=True)
    st = flow.settings
    sound = None if args.no_sound else Sound(flow.cm.bank, st["voice_vol"] / 10, st["crowd_vol"] / 10)
    Handler.hub = hub = Hub(flow, {**SIM_KEYS, **ORGANISER_KEYS}, SimTable(), sound)

    def setting(key, value):
        if sound and key == "voice_vol":
            sound.voice_vol = value / 10
        elif sound and key == "crowd_vol":
            sound.crowd_vol = value / 10

    flow.hooks.update(robot=hub.robot, setting=setting)
    if sound and sound.ok:
        flow.hooks.update(say=sound.say, voice_busy=sound.voice_busy, hush=sound.hush, crowd=sound.crowd)
    threading.Thread(target=hub.run, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    url = f"http://localhost:{args.port}"
    print(f"CHEERIVY screen (simulator) at {url}   Ctrl+C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
