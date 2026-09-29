"""
B1 — Frame sources.

  Camera    : phone via Continuity Camera (iPhone) or DroidCam/Iriun USB (Android).
              A background thread always keeps only the NEWEST frame, so we never
              process stale, buffered video (that is where most lag comes from).
  SimArena  : a fake top-down arena with a bouncing ball and a taped AI carriage
              that obeys the L/R/S commands — test everything with no hardware.
"""
import random
import sys
import threading
import time

import cv2
import numpy as np

import config as C

# Native camera system per OS: AVFoundation on Mac, DirectShow on Windows (opens fast, works
# with Iriun / DroidCam), whatever OpenCV picks elsewhere.
BACKEND = (cv2.CAP_AVFOUNDATION if sys.platform == "darwin"
           else cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)


def list_cameras(max_index=4):
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, BACKEND)
        if cap.isOpened() and cap.read()[0]:
            found.append(i)
        cap.release()
    return found


class Camera:
    def __init__(self, index=C.CAMERA_INDEX):
        if index is None:
            cams = list_cameras()
            if not cams:
                raise RuntimeError(
                    "No camera found.\n"
                    "  1. Allow camera access (Mac: System Settings > Privacy & Security > Camera > Terminal;\n"
                    "     Windows: Settings > Privacy > Camera > let desktop apps use the camera)\n"
                    "  2. Is the phone connected (Iriun / DroidCam / iPhone Continuity Camera)?")
            # Index 0 is usually the laptop's own webcam; the phone is usually the last one.
            index = cams[-1]
            print(f"[camera] found {cams}, using index {index} (override with --cam N)")
        self.cap = cv2.VideoCapture(index, BACKEND)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, C.CAMERA_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, C.CAMERA_H)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {index}")
        self.frame, self.stamp, self.seq = None, 0.0, 0
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._grab, daemon=True).start()

    def _grab(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame, self.stamp, self.seq = f, time.time(), self.seq + 1

    def read(self):
        """Returns (frame, timestamp, seq). Blocks until the first frame arrives."""
        while True:
            with self.lock:
                if self.frame is not None:
                    return self.frame.copy(), self.stamp, self.seq
            time.sleep(0.005)

    def on_command(self, cmd):
        pass

    def close(self):
        self.running = False
        self.cap.release()


# How the simulator paints each config colour (BGR).
SIM_BGR = {"orange": (20, 130, 245), "green": (60, 210, 90), "blue": (210, 110, 30),
           "red": (40, 40, 210), "black": (20, 20, 20)}


class SimArena:
    """
    Fake phone view of the real board: white floor, cream walls, steel rods, white carriages
    with black servos, coloured tape on the AI carriage, black wires lying on the table outside.
    Seen slightly off-angle. The board is tilted like the real one (config.SIM_SLOPE).

    Player 1's carriage stands still in the middle, unless the laptop drives it (AI vs AI, game 3:
    'B' 'N' 'M' move, 'G' fire): then it has blue tape (config.P1_CARRIAGE_COLOR) and plays back.
    """
    MARGIN = 70
    CARRIAGE_SPEED = 30.0  # cm/s, from the project plan

    def __init__(self, match_seconds=60):
        from arena import Arena
        s = C.PX_PER_CM
        self.arena = Arena()
        self.w_px, self.h_px = int(C.ARENA_W * s), int(C.ARENA_H * s)
        self.img_w, self.img_h = self.w_px + 2 * self.MARGIN, self.h_px + 2 * self.MARGIN
        m = self.MARGIN
        flat = np.float32([[0, 0], [self.w_px, 0], [self.w_px, self.h_px], [0, self.h_px]])
        view = np.float32([[m + 30, m], [m + self.w_px - 30, m + 10],
                           [m + self.w_px, m + self.h_px], [m, m + self.h_px - 5]])
        self.M = cv2.getPerspectiveTransform(flat, view)
        # Where calibration clicks would land in the "camera" image.
        to_cam = lambda pts: cv2.perspectiveTransform(np.float32([[(x * s, y * s) for x, y in pts]]), self.M)[0]
        self.corners = to_cam([(C.X0, 0), (C.X0 + C.BASE_W, 0), (C.X0 + C.BASE_W, C.ARENA_H), (C.X0, C.ARENA_H)])
        base = {(C.X0, 0), (C.X0 + C.BASE_W, 0), (C.X0 + C.BASE_W, C.ARENA_H), (C.X0, C.ARENA_H)}
        extra = [p for p in self.arena.poly if p not in base]    # a rectangular board has none
        self.wall_px = to_cam(extra) if extra else []
        self.background = self._draw_static()
        self.carriage_x = C.X0 + C.BASE_W / 2
        self.cmd = "S"
        self.fire_until = 0.0
        self.p1_x = C.X0 + C.BASE_W / 2      # player 1's carriage
        self.cmd1 = "M"
        self.fire1_until = 0.0
        self.p1_driven = False               # the laptop drives player 1 (AI vs AI)
        self.slow_since = None
        self.t = time.time()
        self.seq = 0
        self.stats = {"blocked": 0, "conceded": 0}
        self.lines = []            # fake ATmega status lines for the live show
        # Fake firmware lobby: "READY" every second until the laptop sends '1'/'2' + 'K'.
        self.match_seconds = match_seconds
        self.game = 1
        self.in_match = False
        self.match_end = 0.0
        self.next_ready = 0.0
        self._serve()

    def _draw_static(self):
        s = C.PX_PER_CM
        img = np.full((self.h_px, self.w_px, 3), (40, 50, 70), np.uint8)       # brown table
        rng = np.random.default_rng(0)
        for _ in range(12):                                                    # black wires
            pts = rng.integers(0, [self.w_px, self.h_px], (4, 2)).astype(np.int32)
            cv2.polylines(img, [pts], False, (15, 15, 15), 3)
        poly = np.int32([(x * s, y * s) for x, y in self.arena.poly])
        cv2.fillPoly(img, [poly], (228, 232, 235))                             # white floor
        cv2.polylines(img, [poly], True, (190, 215, 225), 6)                   # cream walls
        for y in (C.ARENA_H * 0.3, C.ARENA_H * 0.7):                           # pencil lines
            cv2.line(img, (0, int(y * s)), (self.w_px, int(y * s)), (170, 170, 170), 1)
        for y in (-1.0, C.ARENA_H + 1.0):                                      # steel rods
            cv2.line(img, (int((C.X0 - 4) * s), int(y * s) + 5), (int((C.X0 + C.BASE_W + 4) * s), int(y * s) + 5), (120, 120, 125), 5)
        return img

    def _draw_carriage(self, img, x_cm, top, red, tape=None):
        s = C.PX_PER_CM
        x0, x1 = int((x_cm - C.CARRIAGE_W / 2) * s), int((x_cm + C.CARRIAGE_W / 2) * s)
        y0 = 0 if top else int((C.ARENA_H - C.CARRIAGE_DEPTH) * s)
        y1 = int(C.CARRIAGE_DEPTH * s) if top else self.h_px
        cv2.rectangle(img, (x0, y0), (x1, y1), (200, 220, 230), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (150, 170, 180), 2)
        cv2.rectangle(img, (x0 + 10, y0 + 12), (x0 + 30, y1 - 12), (20, 20, 20), -1)   # black drive wheel
        if red or tape:                                                # coloured tape, centred
            xc = (x0 + x1) // 2
            cv2.rectangle(img, (xc - 15, y0 + 10), (xc + 15, y1 - 10), SIM_BGR[tape or C.CARRIAGE_COLOR], -1)

    def _serve(self, from_ai=False):
        """A new shot. One player: always a hard, wide shot from the human's end at the AI.
        AI vs AI: the side that conceded restarts, struck from in front of its own carriage."""
        if self.p1_driven:
            top = from_ai
            self.bx = self.carriage_x if top else self.p1_x
            self.by = (C.CARRIAGE_DEPTH + C.BALL_RADIUS + 0.5) if top else (C.ARENA_H - C.CARRIAGE_DEPTH - C.BALL_RADIUS - 0.5)
            ang, speed = random.uniform(-0.5, 0.5), random.uniform(35, 65)
            self.vx, self.vy = speed * np.sin(ang), speed * np.cos(ang) * (1 if top else -1)
            self.served = time.time()
            return
        self.bx = random.uniform(C.X0 + 4, C.X0 + C.BASE_W - 4)
        self.by = C.ARENA_H - C.CARRIAGE_DEPTH - C.BALL_RADIUS - 0.5
        ang = random.uniform(-0.8, 0.8)            # wide angles -> side-wall bounces
        speed = random.uniform(40, 80)
        self.vx, self.vy = speed * np.sin(ang), -speed * np.cos(ang)
        self.served = time.time()

    def on_command(self, cmd):
        if len(cmd) > 1 and cmd[-1] != ";":   # the heartbeat sends the AI's and player 1's move together
            for c in cmd:
                self.on_command(c)
            return
        if cmd == "F":
            self.fire_until = time.time() + 0.09
        elif cmd == "G":
            self.fire1_until = time.time() + 0.09
            self.p1_driven = True
        elif cmd in ("B", "N", "M"):
            self.cmd1 = cmd
            self.p1_driven = True
        elif cmd in ("L", "R", "S"):
            self.cmd = cmd
        elif cmd in ("1", "2", "3"):
            self.game = int(cmd)
        elif cmd == "K" and not self.in_match:
            self.in_match = True
            self.match_end = time.time() + self.match_seconds
            self.lines.append(f"START LEVEL 2 {'AI' if self.game == 3 else f'{self.game}P'}")
        elif cmd == "E" and self.in_match:
            self.in_match = False
            self.lines.append("END")

    @staticmethod
    def _return_speed(vy, struck):
        """Speed of a returned ball: a servo strike always hits about as hard (it doesn't add to the
        incoming speed); a carriage that doesn't strike only bounces it back softer."""
        return random.uniform(35, 65) if struck else max(abs(vy) * 0.7, 15.0)

    def _step(self, dt):
        r = C.BALL_RADIUS
        self.vy += C.SIM_SLOPE[0 if self.by < C.ARENA_H / 2 else 1] * dt     # the tilted board
        self.bx, self.by, self.vx, self.vy = self.arena.advance(self.bx, self.by, self.vx, self.vy, dt)
        if self.p1_driven:                   # AI vs AI: player 1's carriage plays the ball back
            at_p1 = self.by + r >= C.ARENA_H - C.CARRIAGE_DEPTH and self.vy > 0
            if at_p1 and abs(self.bx - self.p1_x) < C.CARRIAGE_W / 2 + r:
                self.vy = -self._return_speed(self.vy, time.time() < self.fire1_until)
                self.vx += random.uniform(-15, 15)
            d1 = {"B": -1, "N": 1}.get(self.cmd1, 0) * self.CARRIAGE_SPEED * dt
            self.p1_x = min(max(self.p1_x + d1, C.CARRIAGE_MIN_X), C.CARRIAGE_MAX_X)
        at_line = self.by - r <= C.CARRIAGE_DEPTH and self.vy < 0
        if at_line and abs(self.bx - self.carriage_x) < C.CARRIAGE_W / 2 + r:
            self.vy = self._return_speed(self.vy, time.time() < self.fire_until)
            self.vx += random.uniform(-15, 15)
            self.stats["blocked"] += 1
        if self.by < 0:
            self.stats["conceded"] += 1
            if self.in_match:
                self.lines.append("G H")           # past the AI: the human scores
            self._serve(from_ai=True)
        elif self.p1_driven:
            if self.by > C.ARENA_H:                 # past player 1's carriage: the AI scores
                if self.in_match:
                    self.lines.append("G A")
                self._serve()
            elif (self.vx ** 2 + self.vy ** 2) ** 0.5 < 3:   # stuck somewhere: serve again after 2 s
                self.slow_since = self.slow_since or time.time()
                if time.time() - self.slow_since > 2:
                    self._serve()
            else:
                self.slow_since = None
        elif self.by > C.ARENA_H - C.CARRIAGE_DEPTH or time.time() - self.served > 4:
            human_x = C.X0 + C.BASE_W / 2           # the human carriage never moves in the sim
            if self.in_match and self.by > C.ARENA_H - C.CARRIAGE_DEPTH and abs(self.bx - human_x) > C.CARRIAGE_W / 2 + r:
                self.lines.append("G A")           # got past the human's carriage: the AI scores
            self._serve()                           # back at the human: serve a new shot
        d = {"L": -1, "R": 1}.get(self.cmd, 0) * self.CARRIAGE_SPEED * dt
        self.carriage_x = min(max(self.carriage_x + d, C.CARRIAGE_MIN_X), C.CARRIAGE_MAX_X)

    def read(self):
        now = time.time()
        dt = min(now - self.t, 0.05)
        self.t = now
        if self.in_match and now >= self.match_end:
            self.in_match = False
            self.lines.append("END")
        if not self.in_match and now >= self.next_ready:
            self.next_ready = now + 1.0
            self.lines.append("READY")
        self._step(dt)
        s = C.PX_PER_CM
        flat = self.background.copy()
        self._draw_carriage(flat, self.carriage_x, top=True, red=True)
        self._draw_carriage(flat, self.p1_x, top=False, red=False, tape=C.P1_CARRIAGE_COLOR if self.p1_driven else None)
        cv2.circle(flat, (int(self.bx * s), int(self.by * s)), int(C.BALL_RADIUS * s), SIM_BGR[C.BALL_COLOR], -1)
        frame = np.full((self.img_h, self.img_w, 3), (40, 50, 70), np.uint8)
        cv2.warpPerspective(flat, self.M, (self.img_w, self.img_h), dst=frame, borderMode=cv2.BORDER_TRANSPARENT)
        frame = cv2.add(frame, np.random.randint(0, 12, frame.shape, np.uint8))
        time.sleep(1 / 60)
        self.seq += 1
        return frame, now, self.seq

    def pop_lines(self):
        out, self.lines = self.lines, []
        return out

    def close(self):
        pass
