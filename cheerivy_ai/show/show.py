"""
CHEERIVY Live Show: the big-screen window next to the robot.

    CONNECT  waiting for the robot's "READY" over the HC-05 (s = play without the robot)
    MENU     1 = single player (vs the AI)   2 = two players (joystick vs joystick)
    NAMES    type the player names; ENTER sends the game + kick-off to the robot
    WAITING  live view, waiting for the robot's "START" (or press k)
    LIVE     camera | AI vision side by side, scoreboard, goal animations + instant replay
    RESULTS  full time -> highlight reel -> awards -> winner + leaderboard

All drawing happens on a background thread at ~30 fps; the main loop only feeds it
frames/telemetry/serial lines and shows the finished image with cv2.imshow.
"""
import json
import math
import os
import random
import re
import subprocess
import threading
import time
from collections import deque

import cv2
import numpy as np

import config as C

from . import gfx as G
from . import lines as L
from .recorder import Recorder
from .stats import Leaderboard, MatchStats
from .voice import Voice

HERE = os.path.dirname(os.path.abspath(__file__))
MATCHES = os.path.join(HERE, "matches")

W, H = 1600, 900
FPS = 30
HEADER_H = 124
MARGIN = 26
GAP = 22
FOOTER_MIN = 92

CONNECT, MENU, NAMES, WAITING, LIVE, RESULTS = "CONNECT", "MENU", "NAMES", "WAITING", "LIVE", "RESULTS"
READY_FRESH_S = 3.0        # a "READY" newer than this = the robot is in its lobby and listening
GOAL_ANIM_S = 3.2
MAX_REEL = 6               # goals shown in the highlight reel
END_GRACE_S = 4.0          # clock hit 0 but no END line -> end the match ourselves


def _rot_vec(v, k):
    x, y = v
    for _ in range(k % 4):
        x, y = -y, x       # 90 deg clockwise in image coordinates (y down)
    return x, y


class Burst:
    """Particles exploding from a point (goal celebration)."""

    def __init__(self, x, y, color, n=90):
        self.p = []
        for _ in range(n):
            a, s = random.uniform(0, 2 * math.pi), random.uniform(250, 900)
            self.p.append([x, y, math.cos(a) * s, math.sin(a) * s - 200,
                           random.choice([color, G.GOLD, G.WHITE]), random.uniform(5, 11)])
        self.t = 0.0

    def draw(self, canvas, dt):
        self.t += dt
        fade = max(0.0, 1 - self.t / 1.6)
        for q in self.p:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[2] *= 0.97
            q[3] = q[3] * 0.97 + 900 * dt
            c = tuple(int(v * fade) for v in q[4])
            cv2.circle(canvas, (int(q[0]), int(q[1])), int(q[5] * (0.4 + 0.6 * fade)), c, -1, cv2.LINE_AA)
        return self.t < 1.6


class Show:
    def __init__(self, cal, voice=True, match_seconds=180, level=2, send=None, robot=True):
        """send: function that writes one command byte to the robot (Link.send).
        robot=False: no robot to talk to, so skip the CONNECT screen."""
        self.cal = cal
        self.match_seconds = match_seconds
        self.level = level
        self.send = send or (lambda c: None)
        self.robot = robot
        self.ready_at = 0.0             # last "READY" from the robot's lobby
        self.link_state = ""            # set by main.py: "HC-05" / "RECONNECTING" / "SIM"
        self.game = 1                   # 1 = vs AI, 2 = two players
        self.names = {"H": "", "A": ""}
        self.field = "H"
        self.phase = CONNECT if robot else MENU
        self.phase_t = time.time()
        self.lock = threading.Lock()

        self.voice = Voice(enabled=voice)
        self.board = Leaderboard(os.path.join(HERE, "leaderboard.json"))
        self.recorder = Recorder(MATCHES)
        self._reset_match()

        # inputs from the main loop
        self.frame = None
        self.flat = None
        self.tele = {}
        self.trail = deque(maxlen=18)
        self.link_mode = "—"
        self._mode_said_at = 0.0         # last time the AI's camera loss/return was commented on
        self.lasers = {}

        # layout (computed on the first frame)
        self.layout = None
        self.base_bg = G.vertical_gradient(W, H, (34, 22, 18), (12, 8, 8))

        self._img, self._seq = None, 0
        self._running = True
        self._last_draw = time.time()
        self.fullscreen = False
        threading.Thread(target=self._loop, daemon=True).start()

    # ================================================================ state
    def _reset_match(self):
        self.score = {"H": 0, "A": 0}
        self.goals = []
        self.stats = MatchStats()
        self.clock_left = float(self.match_seconds)
        self.clock_sync = None          # (seconds_left, at_time)
        self.match_start = None
        self.goal_anim = None           # dict while the GOAL animation runs
        self.bursts = []
        self.pip = None                 # instant replay picture-in-picture
        self.said = set()
        self.results = None
        self.result_row = None
        self.ended_at = None

    def _set_phase(self, p):
        self.phase, self.phase_t = p, time.time()

    def player(self):
        return self.names["H"].strip() or ("PLAYER 1" if self.game == 2 else "PLAYER")

    def ai_name(self):
        """The name on the AI side: the AI in 1P, player 2 in 2P."""
        return self.names["A"].strip() or ("PLAYER 2" if self.game == 2 else "CHEERIVY AI")

    def name_of(self, who):
        return self.player() if who == "H" else self.ai_name()

    def side_label(self, who):
        if self.game == 2:
            return "PLAYER 1" if who == "H" else "PLAYER 2"
        return "PLAYER" if who == "H" else "AI"

    def robot_listening(self):
        return self.robot and time.time() - self.ready_at < READY_FRESH_S

    def choose_game(self, game):
        self.game = game
        self.names = {"H": "", "A": ""}
        self.field = "H"
        self._set_phase(NAMES)

    def _names_done(self):
        self.names["H"] = self.player()
        self.names["A"] = self.ai_name()
        self.voice.prepare(L.all_goal_lines(self.player(), self.ai_name(), self.game))
        self._set_phase(WAITING)
        self.request_kickoff()

    def request_kickoff(self):
        """Tell the robot which game to play and start it. Its "START" line then kicks off here."""
        if self.robot_listening():
            self.send(str(self.game))
            self.send("K")

    # ================================================================ inputs (main thread)
    def update(self, frame, flat, stamp, tele):
        with self.lock:
            self.frame, self.flat, self.tele = frame, flat, tele
            b = tele.get("ball")
            if b:
                if self.trail and math.dist(self.trail[-1], b) > C.BALL_MAX_JUMP_CM:
                    self.trail.clear()             # ball re-served / misdetection: don't draw a line across
                self.trail.append(b)
        if self.phase == LIVE:
            self.stats.update(stamp, tele.get("ball"), tele.get("vx", 0.0), tele.get("vy", 0.0))

    def on_line(self, line):
        """A status line from the ATmega. Returns 'start' / 'end' so main.py can (un)pause the AI."""
        parts = line.split()
        if not parts:
            return None
        tag = parts[0]
        if tag == "READY":
            self.ready_at = time.time()
            if self.phase == CONNECT:
                self._set_phase(MENU)
            return None
        if tag == "START":
            m = re.search(r"LEVEL (\d)", line)
            if m:
                self.level = int(m.group(1))
            if "2P" in parts:
                self.game = 2
            elif "1P" in parts and self.game != 1:
                self.game = 1                  # started from the robot's button: always vs the AI
                self.names = {"H": "", "A": ""}
            self.kickoff()
            return "start"
        if tag == "T" and len(parts) >= 2 and parts[1].isdigit():
            self.clock_sync = (int(parts[1]), time.time())
            if len(parts) >= 3:
                self.link_mode = {"CAM": "CAMERA", "MIR": "MIRROR", "P2": "2 PLAYERS"}.get(parts[2], parts[2])
            if self.phase != LIVE and self.phase != RESULTS and int(parts[1]) > 1:
                self.kickoff(announce=False)      # we joined mid-match
            return None
        if tag == "MODE" and len(parts) >= 2:
            self.link_mode = parts[1]
            if self.phase == LIVE and self.game == 1 and time.time() - self._mode_said_at > 30:
                self._mode_said_at = time.time()
                self.voice.say(L.pick(L.AI_BLIND if parts[1] == "MIRROR" else L.AI_SEES), priority=4, max_age=3)
        elif tag == "G" and len(parts) >= 2 and parts[1] in ("H", "A"):
            self.goal(parts[1])
        elif tag == "END":
            if self.phase == LIVE:
                self.end_match()
                return "end"
        elif tag == "LASER" and len(parts) >= 3:
            self.lasers[parts[1]] = parts[2]
        return None

    def on_key(self, k):
        """Returns True if the show used the key (main.py then ignores it)."""
        c = chr(k) if 0 <= k < 128 else ""
        if self.phase == CONNECT:
            if c == "s":                        # play without the robot (keys h / j / k / e)
                self._set_phase(MENU)
                return True
            return c != "q"
        if self.phase == MENU:
            if c in ("1", "2"):
                self.choose_game(int(c))
                return True
            return c != "q"
        if self.phase == NAMES:
            if k in (13, 10):
                self._names_done()
            elif k == 9:
                self.field = "A" if self.field == "H" else "H"
            elif k in (8, 127):
                self.names[self.field] = self.names[self.field][:-1]
            elif k == 27:
                self._names_done()
            elif 32 <= k < 127 and len(self.names[self.field]) < 16:
                self.names[self.field] += chr(k)
            return True
        if c == "n" and self.phase != LIVE:     # new game: back to the 1P / 2P menu
            self._set_phase(MENU)
            return True
        if c == "k" and self.phase in (WAITING, RESULTS):
            if self.robot_listening():
                self.request_kickoff()          # the robot's START line kicks off here
            else:
                self.kickoff()
            return True
        if self.phase == LIVE and c in ("h", "j"):
            self.goal("H" if c == "h" else "A")
            return True
        if self.phase == LIVE and c == "e":
            self.send("E")                      # stop the robot too
            self.end_match()
            return True
        if self.phase == RESULTS:
            if c == "r":
                self.results["t0"] = time.time()
                self.results["said"] = set()
                return True
            if k in (13, 10):                   # next match: same names, same game
                self._set_phase(WAITING)
                self.request_kickoff()
                return True
        return False

    # ================================================================ match events
    def kickoff(self, announce=True):
        if self.phase in (CONNECT, MENU, NAMES):   # match already running on the robot: just join it
            self.names["H"], self.names["A"] = self.player(), self.ai_name()
            self.voice.prepare(L.all_goal_lines(self.player(), self.ai_name(), self.game))
        with self.lock:
            self._reset_match()
            self.match_start = time.time()
            self.clock_sync = (self.match_seconds, time.time())
            folder = os.path.join(MATCHES, time.strftime("%Y%m%d-%H%M%S") + "_" + _safe(self.player()))
            self.recorder.new_match(folder)
            self.match_folder = folder
        self._set_phase(LIVE)
        if announce:
            self.voice.say(L.pick(L.KICKOFF_2P if self.game == 2 else L.KICKOFF, p=self.player(), ai=self.ai_name()),
                           priority=2, max_age=6)

    def goal(self, who):
        if self.phase != LIVE:
            return
        now = time.time()
        self.score[who] += 1
        speed = self.stats.shot_speed(now)
        self.stats.goal_scored()
        g = {"n": len(self.goals) + 1, "who": who, "name": self.name_of(who), "t": now,
             "clock": self._clock(now), "elapsed": now - (self.match_start or now),
             "speed": speed, "score": (self.score["H"], self.score["A"]), "clip": None}
        self.goals.append(g)

        def got_clip(clip, g=g):
            g["clip"] = clip
            if self.goal_anim and self.goal_anim["goal"] is g:
                self.goal_anim["clip"] = clip
            else:
                self.pip = {"clip": clip, "t0": time.time(), "goal": g}

        self.recorder.mark_goal(f"goal_{g['n']:02d}_{_safe(g['name'])}", got_clip, now)
        self.goal_anim = {"t0": now, "goal": g, "clip": None}
        self.pip = None
        self.bursts.append(Burst(W / 2, H * 0.42, G.HUMAN if who == "H" else G.AI))
        _sound("Hero" if who == "H" else "Sosumi")
        self.voice.say(self._goal_line(who), priority=1, max_age=5, interrupt=True)
        tail = self._goal_tail(who, g["clock"])
        if tail:
            self.voice.say(tail, priority=2, max_age=8)
        if speed >= L.FAST_SPEED:
            self.voice.say(L.fill(L.FAST, v=speed), priority=3, max_age=9)

    def _goal_tail(self, who, clock_left):
        """The second line after a goal: last gasp, equaliser, lead, comeback..."""
        h, a = self.score["H"], self.score["A"]
        name = self.name_of(who)
        if clock_left < 5 and self.match_seconds > 20:
            return L.pick(L.LAST_GASP, p=name)
        if self.game == 2:
            if h == a:
                return L.pick(L.TAIL_EQUALISER_2P)
            if (h > a) == (who == "H") and abs(h - a) == 1:
                return L.pick(L.TAIL_LEAD_2P, p=name)
            return None
        if who == "H":
            if h == a:
                return L.pick(L.TAIL_EQUALISER)
            if h == a + 1 and any(g["score"][1] > g["score"][0] for g in self.goals):
                return L.pick(L.TAIL_COMEBACK, p=name)        # was behind earlier, now in front
            if h == a + 1:
                return L.pick(L.TAIL_LEAD_H, p=name)
            return L.pick(L.TAIL_GOAL_H, p=name)
        if a >= h + 2:
            return L.pick(L.TAIL_AI_EXTENDS)
        return None

    def _goal_line(self, who):
        if self.game == 2:
            return L.pick(L.GOAL_2P, p=self.name_of(who))
        return L.pick(L.GOAL_H if who == "H" else L.GOAL_A, p=self.player(), ai=self.ai_name())

    def end_match(self):
        if self.phase != LIVE:
            return
        now = time.time()
        h, a = self.score["H"], self.score["A"]
        fastest_h = max([g["speed"] for g in self.goals if g["who"] == "H"] or [0.0])
        # the leaderboard is "vs the AI", so only single-player games count
        self.result_row = self.board.add(self.player(), h, a, fastest_h, self.level) if self.game == 1 else None
        self.ended_at = now
        self.results = {"t0": now, "said": set(), "scenes": None}
        self._save_summary()
        self._set_phase(RESULTS)
        pl, ai = self.player(), self.ai_name()
        if self.game == 2 and h != a:
            text = L.fill(L.FULL_TIME_WIN_2P, p=pl if h > a else ai, h=max(h, a), a=min(h, a))
        elif self.game == 2:
            text = L.fill(L.FULL_TIME_DRAW_2P, h=h)
        else:
            line = L.FULL_TIME_WIN_H if h > a else L.FULL_TIME_WIN_A if a > h else L.FULL_TIME_DRAW
            text = L.fill(line, p=pl, ai=ai, h=h, a=a)
        self.voice.say(text, priority=1, max_age=8, interrupt=True)

    def _save_summary(self):
        try:
            with open(os.path.join(self.match_folder, "match.json"), "w") as f:
                json.dump({"game": "2P" if self.game == 2 else "1P",
                           "player": self.player(), "ai": self.ai_name(), "level": self.level,
                           "score": self.score, "shots": self.stats.shots, "ai_saves": self.stats.ai_saves,
                           "longest_rally": self.stats.longest_rally, "top_speed": round(self.stats.top_speed),
                           "goals": [{"n": g["n"], "who": g["who"], "name": g["name"], "clock": round(g["clock"]),
                                      "speed": round(g["speed"]), "score": g["score"],
                                      "clip": f"goal_{g['n']:02d}_{_safe(g['name'])}.mp4"} for g in self.goals]},
                          f, indent=1)
        except (OSError, AttributeError):
            pass

    def _clock(self, now=None):
        now = now or time.time()
        if self.clock_sync is None:
            return float(self.match_seconds)
        left, at = self.clock_sync
        return max(0.0, left - (now - at))

    # ================================================================ output (main thread)
    def image(self):
        return self._seq, self._img

    def close(self):
        self._running = False
        self.voice.close()

    # ================================================================ render loop
    def _loop(self):
        while self._running:
            t0 = time.time()
            try:
                img = self._render(t0)
                if img is not None:
                    self._img, self._seq = img, self._seq + 1
            except Exception as e:           # never kill the robot's AI because of a drawing bug
                print("[show] render error:", repr(e))
                time.sleep(0.5)
            time.sleep(max(0.0, 1 / FPS - (time.time() - t0)))

    def _render(self, now):
        dt, self._last_draw = now - self._last_draw, now
        with self.lock:
            frame, flat, tele, trail = self.frame, self.flat, dict(self.tele), list(self.trail)
        if frame is None:
            canvas = self.base_bg.copy()
            G.text(canvas, "Waiting for the camera...", W // 2, H // 2, "ui", 40, G.DIM, "c")
            return canvas
        if self.layout is None:
            self.layout = self._make_layout(frame.shape)

        self._timers(now)
        phase = self.phase          # read once: key presses change it from the main thread mid-frame
        canvas = self.base_bg.copy()
        need_stage = phase in (CONNECT, MENU, NAMES, WAITING, LIVE) or self.recorder.pending
        stage = None
        if need_stage:
            stage = self._draw_stage(frame, flat, tele, trail, now)
            if phase == LIVE or self.recorder.pending:
                self.recorder.push(stage, now)

        if phase in (CONNECT, MENU, NAMES):
            self._draw_blurred_stage(canvas, stage)
            {CONNECT: self._draw_connect, MENU: self._draw_menu, NAMES: self._draw_names}[phase](canvas, now)
        elif phase in (WAITING, LIVE):
            lo = self.layout
            canvas[lo["stage_y"]:lo["stage_y"] + stage.shape[0], lo["stage_x"]:lo["stage_x"] + stage.shape[1]] = stage
            self._draw_header(canvas, now)
            self._draw_footer(canvas, tele, now)
            if phase == WAITING:
                self._draw_waiting(canvas, now)
            self._draw_pip(canvas, now)
            self._draw_goal_anim(canvas, now)
        else:
            self._draw_results(canvas, now, dt)
        self.bursts = [b for b in self.bursts if b.draw(canvas, dt)]
        return canvas

    def _timers(self, now):
        if self.phase != LIVE:
            return
        left = self._clock(now)
        if left <= 60.5 and "60" not in self.said and self.match_seconds > 90:
            self.said.add("60")
            self.voice.say(L.pick(L.SECONDS_60), priority=4, max_age=3)
        if left <= 30.5 and "30" not in self.said and self.match_seconds > 40:
            self.said.add("30")
            self.voice.say(L.pick(L.SECONDS_30), priority=3, max_age=3)
        if left <= 10.5 and "10" not in self.said:
            self.said.add("10")
            self.voice.say(L.pick(L.SECONDS_10_2P if self.game == 2 else L.SECONDS_10, p=self.player()),
                           priority=3, max_age=3)
        if left <= 0 and self.clock_sync and now - self.clock_sync[1] > self.clock_sync[0] + END_GRACE_S:
            self.end_match()

    # ================================================================ layout
    def _make_layout(self, shape):
        fh, fw = shape[:2]
        cal = self.cal
        pts = np.float32(list(cal.corners) + [tuple(p) for p in cal.wall_px])
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        m = 0.10 * max(x1 - x0, y1 - y0)
        cx0, cy0 = max(0, int(x0 - m)), max(0, int(y0 - m))
        cx1, cy1 = min(fw, int(x1 + m)), min(fh, int(y1 + m))

        # Turn the AI view so it faces the same way as the camera (AI end -> human end).
        c = cal.corners
        ai_mid, hu_mid = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2
        v = hu_mid - ai_mid
        k = max(range(4), key=lambda k: np.dot(_rot_vec((0.0, 1.0), k), v))
        fw_px, fh_px = cal.out_w, cal.out_h
        tw, th = (fw_px, fh_px) if k % 2 == 0 else (fh_px, fw_px)
        a_t = tw / th

        avail_w = W - 2 * MARGIN - GAP
        avail_h = H - HEADER_H - FOOTER_MIN - MARGIN
        a_c = (cx1 - cx0) / (cy1 - cy0)
        h = min(avail_h, avail_w / (a_t + a_c))
        if avail_w - h * (a_t + a_c) > 4:
            # Height is the limit: show more of the camera's width instead of empty space.
            want = (avail_w - h * a_t) / h
            crop_h = cy1 - cy0
            new_w = min(fw, int(want * crop_h))
            mid = (cx0 + cx1) / 2
            cx0 = int(max(0, min(fw - new_w, mid - new_w / 2)))
            cx1 = cx0 + new_w
            a_c = (cx1 - cx0) / crop_h
        h = int(min(avail_h, avail_w / (a_t + a_c)))
        cam_w, td_w = int(h * a_c), int(h * a_t)
        stage_w = cam_w + GAP + td_w
        stage_y = HEADER_H + 8 + (avail_h - h) // 3      # spare height: a bit above, the rest to the stats strip
        return {"crop": (cx0, cy0, cx1, cy1), "rot": k, "cam_w": cam_w, "td_w": td_w, "h": h,
                "stage_w": stage_w, "stage_x": (W - stage_w) // 2, "stage_y": stage_y,
                "footer_y": stage_y + h + 14, "flat_wh": (fw_px, fh_px), "td_scale": td_w / tw}

    def _td_pt(self, x_cm, y_cm):
        """Arena cm -> pixel in the (rotated, scaled) AI-vision panel."""
        lo = self.layout
        fw, fh = lo["flat_wh"]
        x, y = x_cm * C.PX_PER_CM, y_cm * C.PX_PER_CM
        k = lo["rot"] % 4
        if k == 1:
            x, y = fh - 1 - y, x
        elif k == 2:
            x, y = fw - 1 - x, fh - 1 - y
        elif k == 3:
            x, y = y, fw - 1 - x
        s = lo["td_scale"]
        return x * s, y * s

    # ================================================================ stage: camera | AI vision
    def _draw_stage(self, frame, flat, tele, trail, now):
        lo = self.layout
        h = lo["h"]
        stage = np.zeros((h, lo["stage_w"], 3), np.uint8)
        stage[:] = G.BG
        cx0, cy0, cx1, cy1 = lo["crop"]
        stage[:, :lo["cam_w"]] = G.fit(frame[cy0:cy1, cx0:cx1], lo["cam_w"], h)
        td = self._draw_ai_view(flat, tele, trail, now)
        stage[:, lo["cam_w"] + GAP:] = td
        for x0, w, label, col in ((0, lo["cam_w"], "LIVE CAMERA", G.WHITE),
                                  (lo["cam_w"] + GAP, lo["td_w"],
                                   "PREDICTION" if self.game == 2 else "AI VISION  ·  PREDICTION", G.CYAN)):
            _brackets(stage, x0, 0, x0 + w - 1, h - 1, col)
            G.rect(stage, x0 + 12, 12, x0 + 22 + G.text_width(label, "ui", 19), 44, (0, 0, 0), 0.55)
            G.text(stage, label, x0 + 17, 28, "ui", 19, col, "l")
        if self.phase == LIVE:
            on = int(now * 2) % 2 == 0
            x = lo["cam_w"] - 20
            G.rect(stage, x - 78, 12, x, 44, (0, 0, 0), 0.55)
            cv2.circle(stage, (x - 64, 28), 7, (40, 40, 235) if on else (40, 40, 110), -1, cv2.LINE_AA)
            G.text(stage, "LIVE", x - 50, 28, "ui", 19, G.WHITE, "l")
        return stage

    def _draw_ai_view(self, flat, tele, trail, now):
        lo = self.layout
        img = cv2.addWeighted(flat, 0.34, np.full_like(flat, G.PANEL), 0.66, 0)
        img = cv2.rotate(img, [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE][lo["rot"]]) \
            if lo["rot"] else img
        img = cv2.resize(img, (lo["td_w"], lo["h"]), interpolation=cv2.INTER_LINEAR)
        P = lambda p: tuple(int(v) for v in self._td_pt(*p))
        s = lo["td_scale"] * C.PX_PER_CM          # panel pixels per cm

        poly = np.int32([P(p) for p in self.cal.arena.poly])
        cv2.polylines(img, [poly], True, (120, 90, 40), 6, cv2.LINE_AA)
        cv2.polylines(img, [poly], True, G.CYAN, 2, cv2.LINE_AA)
        G.dashed_polyline(img, [P((C.X0, C.AI_LINE_Y)), P((C.X0 + C.BASE_W, C.AI_LINE_Y))], (90, 90, 180), 1, 8, 8)
        top, bottom = ("P2 GOAL", "P1 GOAL") if self.game == 2 else ("AI GOAL", "PLAYER GOAL")
        G.text(img, top, *P((C.X0 + C.BASE_W / 2, C.AI_LINE_Y + 3.5)), "ui", 15, (120, 120, 230), "c")
        G.text(img, bottom, *P((C.X0 + C.BASE_W / 2, C.ARENA_H - 3)), "ui", 15, (230, 190, 120), "c")

        # AI carriage + where it's heading
        cx = tele.get("carriage_x")
        if cx is not None:
            pts = np.int32([P(p) for p in ((cx - C.CARRIAGE_W / 2, 0.3), (cx + C.CARRIAGE_W / 2, 0.3),
                                           (cx + C.CARRIAGE_W / 2, C.CARRIAGE_DEPTH), (cx - C.CARRIAGE_W / 2, C.CARRIAGE_DEPTH))])
            cv2.fillConvexPoly(img, pts, (40, 40, 150), cv2.LINE_AA)
            cv2.polylines(img, [pts], True, G.AI, 2, cv2.LINE_AA)
        tgt = tele.get("target")
        if tgt is not None:
            cv2.line(img, P((tgt, 0.3)), P((tgt, C.AI_LINE_Y + 1.5)), G.GREEN, 3, cv2.LINE_AA)

        # ball trail
        for i in range(1, len(trail)):
            f = i / len(trail)
            cv2.line(img, P(trail[i - 1]), P(trail[i]), tuple(int(v * f) for v in G.GOLD), max(1, int(5 * f)), cv2.LINE_AA)

        # predicted path with bounces + impact point
        path = tele.get("path") or []
        if len(path) >= 2:
            pts = [P(p) for p in path]
            cv2.polylines(img, [np.int32(pts)], False, (60, 110, 40), 7, cv2.LINE_AA)
            G.dashed_polyline(img, pts, G.GREEN, 3, 16, 10, phase=now * 90)
            for b in pts[1:-1]:
                cv2.circle(img, b, 6, G.WHITE, 2, cv2.LINE_AA)
            G.reticle(img, pts[-1], max(10, 2.2 * s), G.GOLD, now)
            hit = tele.get("hit")
            if hit:
                G.text(img, f"{hit[1] * 1000:3.0f} ms", pts[-1][0] + 26, pts[-1][1], "score", 26, G.GOLD, "l")

        ball = tele.get("ball")
        if ball:
            bp = P(ball)
            vx, vy = tele.get("vx", 0.0), tele.get("vy", 0.0)
            tip = P((ball[0] + vx * 0.18, ball[1] + vy * 0.18))
            cv2.arrowedLine(img, bp, tip, G.MAGENTA, 2, cv2.LINE_AA, tipLength=0.25)
            G.glow_circle(img, bp, C.BALL_RADIUS * s, G.GOLD)

        status = tele.get("status", "")
        label = ("INCOMING" if self.game == 2 else "INTERCEPTING") if path else ("TRACKING BALL" if ball else "SEARCHING...")
        if status.startswith("FIRE") and self.game == 1:
            label = "FIRE!"
        G.text(img, label, lo["td_w"] - 34, lo["h"] - 20, "ui", 18,
               G.GOLD if label == "FIRE!" else G.GREEN if path else G.DIM, "br")
        return img

    # ================================================================ header / footer
    def _draw_header(self, canvas, now):
        G.rect(canvas, 0, 0, W, HEADER_H, (18, 12, 10))
        G.rect(canvas, 0, HEADER_H - 3, W // 2, HEADER_H, G.HUMAN)
        G.rect(canvas, W // 2, HEADER_H - 3, W, HEADER_H, G.AI)
        cxm = W // 2
        # names
        G.text(canvas, self.side_label("H"), MARGIN + 6, 28, "ui", 17, G.HUMAN, "l")
        G.text(canvas, self.player().upper(), MARGIN + 4, 74, "display", 52, G.WHITE, "l")
        G.text(canvas, self.side_label("A"), W - MARGIN - 6, 28, "ui", 17, G.AI, "r")
        G.text(canvas, self.ai_name().upper(), W - MARGIN - 4, 74, "display", 52, G.WHITE, "r")
        # score (the digit that just changed pops)
        pop = {"H": 1.0, "A": 1.0}
        if self.goal_anim:
            t = now - self.goal_anim["t0"]
            pop[self.goal_anim["goal"]["who"]] = 1.0 + 0.45 * max(0.0, 1 - t / 0.9) * abs(math.sin(t * 9))
        G.text(canvas, str(self.score["H"]), cxm - 70, 58, "score", 92, G.HUMAN, "c", scale=pop["H"], glow=G.HUMAN)
        G.text(canvas, "-", cxm, 52, "score", 60, G.DIM, "c")
        G.text(canvas, str(self.score["A"]), cxm + 70, 58, "score", 92, G.AI, "c", scale=pop["A"], glow=G.AI)
        # clock
        left = self._clock(now)
        red = left <= 10 and self.phase == LIVE
        col = G.AI if red else G.WHITE
        sc = 1.0 + (0.12 * abs(math.sin(now * 6)) if red else 0.0)
        G.rect(canvas, cxm - 62, 92, cxm + 62, HEADER_H - 8, (0, 0, 0), 0.5)
        G.text(canvas, G.fmt_clock(left), cxm, 106, "score", 30, col, "c", scale=sc)
        G.text(canvas, f"LEVEL {self.level}", cxm - 150, 106, "ui", 15, G.DIM, "r")
        G.text(canvas, "2 PLAYERS" if self.game == 2 else f"AI: {self.link_mode}", cxm + 150, 106, "ui", 15, G.DIM, "l")

    def _draw_footer(self, canvas, tele, now):
        lo = self.layout
        y0 = lo["footer_y"]
        y1 = H - 14
        x0, x1 = lo["stage_x"], lo["stage_x"] + lo["stage_w"]
        G.rect(canvas, x0, y0, x1, y1, G.PANEL, 0.7)
        yc = (y0 + y1) // 2
        st = self.stats
        sp = st.speeds[-1][1] if tele.get("ball") and st.speeds and time.time() - st.speeds[-1][0] < 0.3 else 0.0
        two = self.game == 2
        cells = [("BALL SPEED", f"{sp:3.0f}", "cm/s", G.GOLD),
                 ("TOP SPEED", f"{st.top_speed:3.0f}", "cm/s", G.GOLD),
                 ("SHOTS", f"{st.shots['H']} · {st.shots['A']}", "P1 · P2" if two else "you · AI", G.WHITE),
                 ("P2 SAVES" if two else "AI SAVES", str(st.ai_saves), "", G.AI),
                 ("RALLY", str(st.rally), f"best {st.longest_rally}", G.GREEN)]
        cw = (x1 - x0) / (len(cells) + 1.3)
        for i, (lab, val, unit, col) in enumerate(cells):
            cx = x0 + 24 + i * cw
            G.text(canvas, lab, cx, yc - 20, "ui", 14, G.DIM, "l")
            w, _ = G.text(canvas, val, cx, yc + 12, "score", 40, col, "l")
            if unit:
                G.text(canvas, unit, cx + w + 6, yc + 16, "ui_light", 14, G.DIM, "l")
            if i == 0:   # speed gauge
                G.rect(canvas, cx, yc + 34, cx + cw - 40, yc + 38, (70, 60, 55))
                G.rect(canvas, cx, yc + 34, cx + (cw - 40) * min(1.0, sp / 150), yc + 38, G.GOLD)
        info = f"voice: {self.voice.status}"
        blocked = [k for k, v in list(self.lasers.items()) if v != "OK"]
        if blocked:
            info = "LASER " + " & ".join(blocked) + " BLOCKED!"
        G.text(canvas, info, x1 - 18, yc - 14, "ui_light", 14, G.AI if blocked else G.DIM, "r")
        G.text(canvas, "h / j goal · e end · v fullscreen", x1 - 18, yc + 14, "ui_light", 14, G.DIM, "r")

    # ================================================================ phase screens
    def _draw_blurred_stage(self, canvas, stage):
        if stage is None:
            return
        bg = cv2.GaussianBlur(cv2.resize(stage, (W // 4, int(W / 4 * stage.shape[0] / stage.shape[1]))), (0, 0), 3)
        bg = cv2.resize(bg, (W, int(W * stage.shape[0] / stage.shape[1])))
        y = (H - bg.shape[0]) // 2
        if y >= 0:
            canvas[y:y + bg.shape[0]] = G.darken(bg, 0.28)
        else:
            canvas[:] = G.darken(bg[-y:-y + H], 0.28)

    def _draw_title(self, canvas, now, sub):
        t = now - self.phase_t
        G.text(canvas, "CHEERIVY", W // 2, 150, "display", 120, G.WHITE, "c", glow=G.CYAN,
               scale=0.9 + 0.1 * G.ease_out_back(t / 0.6))
        G.text(canvas, sub, W // 2, 235, "ui", 26, G.CYAN, "c")

    def _draw_connect(self, canvas, now):
        self._draw_title(canvas, now, "ROBOT DUEL")
        a = 0.6 + 0.4 * math.sin(now * 3)
        dots = "." * (int(now * 2) % 4)
        G.text(canvas, f"Connecting to the robot{dots}", W // 2, 380, "display", 54, G.WHITE, "c", alpha=a)
        port = {"HC-05": "Bluetooth connected, waiting for the robot",
                "RECONNECTING": "looking for the HC-05...",
                "SIM": "simulator"}.get(self.link_state, self.link_state)
        G.text(canvas, port, W // 2, 450, "ui", 24, G.CYAN, "c")
        G.text(canvas, "Power on the robot  ·  the HC-05 LED should blink twice every 2 s", W // 2, 530,
               "ui_light", 22, G.DIM, "c")
        G.text(canvas, "s = play without the robot   ·   q = quit", W // 2, 580, "ui_light", 20, G.DIM, "c")

    def _draw_menu(self, canvas, now):
        self._draw_title(canvas, now, "CHOOSE A GAME")
        cards = (("1", "SINGLE PLAYER", "you  vs  the AI", "camera AI drives the other carriage", G.HUMAN),
                 ("2", "TWO PLAYERS", "joystick  vs  joystick", "player 2 uses the second joystick", G.AI))
        for i, (key, title, sub, info, col) in enumerate(cards):
            x0 = W // 2 - 520 + i * 540
            G.rect(canvas, x0, 300, x0 + 500, 560, (30, 22, 20), 0.88)
            cv2.rectangle(canvas, (x0, 300), (x0 + 500, 560), col, 3, cv2.LINE_AA)
            G.rect(canvas, x0, 300, x0 + 10, 560, col)
            G.text(canvas, key, x0 + 60, 380, "score", 96, col, "c", glow=col)
            G.text(canvas, title, x0 + 120, 370, "display", 48, G.WHITE, "l")
            G.text(canvas, sub, x0 + 120, 425, "ui", 24, col, "l")
            G.text(canvas, info, x0 + 40, 500, "ui_light", 20, G.DIM, "l")
        ok = self.robot_listening()
        status = "robot ready" if ok else ("robot not connected: goals by keys h / j" if self.robot else "no robot")
        G.text(canvas, f"press 1 or 2   ·   {status}", W // 2, 620, "ui_light", 22, G.GREEN if ok else G.DIM, "c")
        if self.game == 1:
            self._draw_leaderboard(canvas, W // 2 - 330, 670, 660, 3)

    def _draw_names(self, canvas, now):
        self._draw_title(canvas, now, "ROBOT DUEL  ·  " + ("PLAYER 1 vs PLAYER 2" if self.game == 2 else "HUMAN vs AI"))
        labels = ("PLAYER 1", "PLAYER 2") if self.game == 2 else ("PLAYER", "AI OPPONENT")
        for i, (who, col, label) in enumerate((("H", G.HUMAN, labels[0]), ("A", G.AI, labels[1]))):
            x0 = W // 2 - 480 + i * 500
            active = self.field == who
            G.rect(canvas, x0, 320, x0 + 460, 470, (30, 22, 20), 0.85)
            cv2.rectangle(canvas, (x0, 320), (x0 + 460, 470), col if active else (80, 70, 65), 3 if active else 1, cv2.LINE_AA)
            G.rect(canvas, x0, 320, x0 + 8, 470, col)
            G.text(canvas, label, x0 + 30, 355, "ui", 20, col, "l")
            name = self.names[who]
            caret = "|" if active and int(now * 2) % 2 == 0 else ""
            shown = name if name else ("type a name" if not active else "")
            G.text(canvas, (shown + caret) or " ", x0 + 30, 420, "display", 54,
                   G.WHITE if name else G.DIM, "l")
        tab = "TAB switch player" if self.game == 2 else "TAB switch player / AI"
        G.text(canvas, f"type a name   ·   {tab}   ·   ENTER start", W // 2, 520, "ui_light", 22, G.DIM, "c")
        if self.game == 1:
            self._draw_leaderboard(canvas, W // 2 - 330, 575, 660, 5)

    def _draw_waiting(self, canvas, now):
        lo = self.layout
        cy = lo["stage_y"] + lo["h"] // 2
        a = 0.75 + 0.25 * math.sin(now * 3)
        G.rect(canvas, 0, cy - 95, W, cy + 95, (0, 0, 0), 0.72)
        G.text(canvas, f"{self.player().upper()}  vs  {self.ai_name().upper()}", W // 2, cy - 35, "display", 64,
               G.WHITE, "c", glow=G.CYAN)
        msg = "Starting the robot..." if self.robot_listening() else "Waiting for kick-off  ·  robot not in its lobby"
        G.text(canvas, msg, W // 2, cy + 30, "ui", 26, G.CYAN, "c", alpha=a)
        G.text(canvas, "k = kick off now   ·   n = new game", W // 2, cy + 70, "ui_light", 18, G.DIM, "c")

    def _draw_goal_anim(self, canvas, now):
        ga = self.goal_anim
        if not ga:
            return
        t = now - ga["t0"]
        if t > GOAL_ANIM_S:
            self.goal_anim = None
            if ga["clip"]:
                self.pip = {"clip": ga["clip"], "t0": now, "goal": ga["goal"]}
            return
        g = ga["goal"]
        col = G.HUMAN if g["who"] == "H" else G.AI
        if t < 0.35:                                      # flash
            G.rect(canvas, 0, 0, W, H, G.WHITE, 0.75 * (1 - t / 0.35))
        fade = G.fade(t, 0.05, 0.35, GOAL_ANIM_S)
        lo = self.layout
        cy = lo["stage_y"] + lo["h"] // 2
        G.rect(canvas, 0, cy - 150, W, cy + 150, (0, 0, 0), 0.55 * fade)
        shake = (random.uniform(-6, 6), random.uniform(-6, 6)) if t < 0.5 else (0, 0)
        G.text(canvas, "GOAL!", W // 2 + shake[0], cy - 40 + shake[1], "impact", 190, G.WHITE, "c",
               alpha=fade, scale=0.25 + 0.75 * G.ease_out_back(t / 0.45), glow=col, stroke=2, )
        # name banner sweeps in from the side
        k = G.ease_out_cubic((t - 0.35) / 0.45)
        bw = 760
        bx = -bw + k * (W // 2 + bw // 2) if g["who"] == "H" else W - k * (W // 2 + bw // 2)
        G.rect(canvas, bx, cy + 62, bx + bw, cy + 132, col, 0.92 * fade)
        G.text(canvas, g["name"].upper(), bx + bw // 2, cy + 97, "display", 50, G.WHITE, "c", alpha=fade)
        if g["speed"] > 1 and t > 0.9:
            G.text(canvas, f"SHOT SPEED  {g['speed']:.0f} cm/s", W // 2, cy + 162, "ui", 24, G.GOLD, "c",
                   alpha=fade * G.clamp01((t - 0.9) / 0.3))

    def _draw_pip(self, canvas, now):
        p = self.pip
        if not p:
            return
        clip = p["clip"]
        i = int((now - p["t0"]) * clip.fps)
        if i >= len(clip.frames):
            self.pip = None
            return
        lo = self.layout
        f = clip.frames[i]
        pw = int(lo["stage_w"] * 0.36)
        ph = int(f.shape[0] * pw / f.shape[1])
        x1, y1 = lo["stage_x"] + lo["stage_w"] - 14, lo["stage_y"] + lo["h"] - 14
        x0, y0 = x1 - pw, y1 - ph
        k = G.ease_out_cubic((now - p["t0"]) / 0.3)
        y0s = int(y0 + (1 - k) * 60)
        G.rect(canvas, x0 - 4, y0s - 34, x1 + 4, y0s + ph + 4, (0, 0, 0), 0.8)
        canvas[y0s:y0s + ph, x0:x1] = G.fit(f, pw, ph)[:max(0, min(ph, H - y0s))]
        col = G.HUMAN if p["goal"]["who"] == "H" else G.AI
        G.rect(canvas, x0 - 4, y0s - 34, x0 + 6, y0s - 4, col)
        G.text(canvas, f"INSTANT REPLAY  ·  {p['goal']['name'].upper()}", x0 + 14, y0s - 19, "ui", 17, G.WHITE, "l")

    # ================================================================ results / highlight reel
    def _build_scenes(self):
        sc = [("fulltime", 3.6)]
        goals = [g for g in self.goals if g["clip"] and g["clip"].frames]
        if len(goals) > MAX_REEL:
            # best highlights: the player's goals first, then the fastest shots; keep match order
            best = sorted(goals, key=lambda g: (g["who"] == "H", g["speed"]), reverse=True)[:MAX_REEL]
            goals = [g for g in goals if g in best]
        if goals:
            sc.append(("title", 2.2))
            for g in goals:
                sched = _slowmo_schedule(g["clip"])
                g["sched"] = sched
                sc.append((("card", g), 1.6))
                sc.append((("replay", g), len(sched) / FPS))
        elif self.goals:
            sc.append(("noclips", 2.5))
        else:
            sc.append(("nogoals", 3.0))
        awards = self._awards()
        if awards:
            sc.append((("awards", awards), 1.6 + 1.3 * len(awards)))
        sc.append(("winner", 1e9))
        return sc

    def _awards(self):
        out = []
        scored = [g for g in self.goals if g["speed"] > 1]
        if scored:
            best = max(scored, key=lambda g: g["speed"])
            out.append(("ROCKET", "fastest goal", best["name"], f"{best['speed']:.0f} cm/s",
                        L.fill(L.AWARD_ROCKET, who=best["name"], v=best["speed"])))
        two = self.game == 2
        if self.stats.ai_saves:
            out.append(("THE WALL", "shots saved by player 2" if two else "shots saved by the AI", self.ai_name(),
                        f"{self.stats.ai_saves} saves", L.fill(L.AWARD_WALL, ai=self.ai_name(), n=self.stats.ai_saves)))
        for who in ("H", "A") if two else ("H",):
            if self.score[who] >= 3:
                out.append(("HAT-TRICK HERO", "3+ goals" if two else "3+ goals vs the machine", self.name_of(who),
                            f"{self.score[who]} goals", None))
        if self.stats.longest_rally >= 3:
            out.append(("LONGEST RALLY", "hits in one rally", "BOTH", f"{self.stats.longest_rally} hits", None))
        return out[:3]

    def _draw_results(self, canvas, now, dt):
        r = self.results
        if r["scenes"] is None:
            if self.recorder.pending and now - r["t0"] < 3.0:
                self._scene_fulltime(canvas, now - r["t0"])
                return
            r["scenes"] = self._build_scenes()
        t = now - r["t0"]
        for i, (kind, dur) in enumerate(r["scenes"]):
            if t < dur:
                break
            t -= dur
        name = kind if isinstance(kind, str) else kind[0]
        arg = None if isinstance(kind, str) else kind[1]
        key = (i, name)
        first = key not in r["said"]
        r["said"].add(key)
        if name == "fulltime":
            self._scene_fulltime(canvas, t)
        elif name == "title":
            if first:
                self.voice.say(L.pick(L.HIGHLIGHTS), priority=2, max_age=4)
            n = len(self.goals)
            self._scene_title(canvas, t, "MATCH HIGHLIGHTS", f"{n} GOAL{'S' if n != 1 else ''}")
        elif name == "nogoals":
            if first:
                self.voice.say(L.pick(L.NO_GOALS), priority=2, max_age=4)
            self._scene_title(canvas, t, "NO GOALS", "a defensive masterclass")
        elif name == "noclips":
            self._scene_title(canvas, t, "HIGHLIGHTS", "no clips were recorded")
        elif name == "card":
            self._scene_card(canvas, t, arg)
        elif name == "replay":
            if first:
                self.voice.say(self._goal_line(arg["who"]), priority=2, max_age=4)
            self._scene_replay(canvas, t, arg, now)
        elif name == "awards":
            self._scene_awards(canvas, t, arg, first)
        elif name == "winner":
            self._scene_winner(canvas, t, dt, first)

    def _scene_title(self, canvas, t, big, small):
        k = G.ease_out_back(t / 0.5)
        G.text(canvas, big, W // 2, H // 2 - 30, "display", 120, G.WHITE, "c", scale=0.6 + 0.4 * k, alpha=G.clamp01(t / 0.3),
               glow=G.CYAN)
        G.text(canvas, small, W // 2, H // 2 + 60, "ui", 30, G.CYAN, "c", alpha=G.clamp01((t - 0.4) / 0.3))

    def _scene_fulltime(self, canvas, t):
        h, a = self.score["H"], self.score["A"]
        G.text(canvas, "FULL TIME", W // 2, 230, "display", 110, G.WHITE, "c", glow=G.GOLD,
               scale=0.5 + 0.5 * G.ease_out_back(t / 0.5))
        k = G.ease_out_cubic((t - 0.4) / 0.6)
        G.text(canvas, self.player().upper(), W // 2 - 200 - (1 - k) * 600, 450, "display", 64, G.HUMAN, "r")
        G.text(canvas, self.ai_name().upper(), W // 2 + 200 + (1 - k) * 600, 450, "display", 64, G.AI, "l")
        G.text(canvas, f"{h}  -  {a}", W // 2, 450, "score", 150, G.WHITE, "c", alpha=G.clamp01((t - 0.7) / 0.4))

    def _scene_card(self, canvas, t, g):
        col = G.HUMAN if g["who"] == "H" else G.AI
        k = G.ease_out_cubic(t / 0.45)
        out = G.clamp01((t - 1.25) / 0.35)
        x = int(-W + k * W - out * W)
        G.rect(canvas, x, H // 2 - 130, x + W, H // 2 + 130, col, 0.9)
        G.text(canvas, f"GOAL {g['n']}", x + W // 2, H // 2 - 70, "ui", 30, G.WHITE, "c")
        G.text(canvas, g["name"].upper(), x + W // 2, H // 2 + 5, "display", 96, G.WHITE, "c")
        el = int(g["elapsed"])
        extra = f"   ·   {g['speed']:.0f} cm/s" if g["speed"] > 1 else ""
        G.text(canvas, f"{el // 60}:{el % 60:02d} into the match{extra}", x + W // 2, H // 2 + 82, "ui", 26,
               G.WHITE, "c")

    def _scene_replay(self, canvas, t, g, now):
        clip, sched = g["clip"], g["sched"]
        i = min(len(sched) - 1, int(t * FPS))
        idx, slow = sched[i]
        f = clip.frames[idx]
        bar = 70
        avail_h = H - 2 * bar
        fw = min(W, int(f.shape[1] * avail_h / f.shape[0]))
        fh = int(f.shape[0] * fw / f.shape[1])
        # slow, gentle zoom during slow motion
        z = 1.0 + (0.10 * G.ease_in_out((t - g["slow_t0"]) / 2.5) if slow and "slow_t0" in g else 0.0)
        if slow and "slow_t0" not in g:
            g["slow_t0"] = t
        if z > 1.001:
            ch, cw = int(f.shape[0] / z), int(f.shape[1] / z)
            y0, x0 = (f.shape[0] - ch) // 2, (f.shape[1] - cw) // 2
            f = f[y0:y0 + ch, x0:x0 + cw]
        img = cv2.resize(f, (fw, fh), interpolation=cv2.INTER_LINEAR)
        if slow:
            img = cv2.addWeighted(img, 1.08, np.zeros_like(img), 0, 6)
        x, y = (W - fw) // 2, (H - fh) // 2
        canvas[y:y + fh, x:x + fw] = img
        col = G.HUMAN if g["who"] == "H" else G.AI
        G.text(canvas, f"REPLAY  ·  GOAL {g['n']}", 30, bar // 2, "ui", 22, G.WHITE, "l")
        h, a = g["score"]
        G.text(canvas, f"{self.player().upper()} {h}  -  {a} {self.ai_name().upper()}", W - 30, bar // 2, "ui", 22,
               G.WHITE, "r")
        if slow:
            if int(now * 2.5) % 2 == 0:
                G.text(canvas, "SLOW MOTION", 30, H - bar // 2, "ui", 20, G.GOLD, "l")
            k = G.ease_out_cubic((t - g["slow_t0"]) / 0.5)
            bw = 700
            bx = int(W - k * (bw + 40))
            G.rect(canvas, bx, H - bar - 110, bx + bw, H - bar - 20, col, 0.9)
            G.text(canvas, g["name"].upper(), bx + 26, H - bar - 65, "display", 58, G.WHITE, "l")
            if g["speed"] > 1:
                G.text(canvas, f"{g['speed']:.0f} cm/s", bx + bw - 24, H - bar - 65, "score", 40, G.GOLD, "r")

    def _scene_awards(self, canvas, t, awards, first):
        G.text(canvas, "AWARDS", W // 2, 130, "display", 90, G.WHITE, "c", glow=G.GOLD,
               alpha=G.clamp01(t / 0.3))
        for j, (title, sub, who, val, say) in enumerate(awards):
            tj = t - 0.8 - j * 1.3
            if tj < 0:
                continue
            key = ("award", j)
            if say and key not in self.results["said"]:
                self.results["said"].add(key)
                self.voice.say(say, priority=3, max_age=6)
            k = G.ease_out_back(tj / 0.5)
            cx = W // 2 + (j - (len(awards) - 1) / 2) * 470
            y0 = 250
            G.rect(canvas, cx - 210, y0, cx + 210, y0 + 440, (40, 30, 26), 0.9 * G.clamp01(tj / 0.2))
            cv2.rectangle(canvas, (int(cx - 210), y0), (int(cx + 210), y0 + 440), G.GOLD, 2, cv2.LINE_AA)
            G.text(canvas, title, cx, y0 + 70, "display", 50, G.GOLD, "c", scale=0.5 + 0.5 * k, glow=G.GOLD)
            G.text(canvas, sub, cx, y0 + 125, "ui_light", 20, G.DIM, "c")
            G.text(canvas, who.upper(), cx, y0 + 230, "display", 52, G.WHITE, "c", alpha=G.clamp01(tj / 0.4))
            G.text(canvas, val, cx, y0 + 330, "score", 64, G.CYAN, "c", alpha=G.clamp01((tj - 0.3) / 0.4))

    def _scene_winner(self, canvas, t, dt, first):
        h, a = self.score["H"], self.score["A"]
        if first:
            col = G.HUMAN if h > a else G.AI if a > h else None
            self.results["confetti"] = G.Confetti(W, H, 170, col)
        self.results["confetti"].draw(canvas, dt)
        if h == a:
            head, who, col = "IT'S A DRAW", f"{self.player()}  &  {self.ai_name()}", G.GOLD
        else:
            head, who, col = "WINNER", self.player() if h > a else self.ai_name(), G.HUMAN if h > a else G.AI
        G.text(canvas, head, W // 2, 110, "ui", 36, G.GOLD, "c", alpha=G.clamp01(t / 0.4))
        G.text(canvas, who.upper(), W // 2, 210, "display", 120, G.WHITE, "c", glow=col,
               scale=0.4 + 0.6 * G.ease_out_back(t / 0.6), stroke=1)
        G.text(canvas, f"{h}  -  {a}", W // 2, 330, "score", 90, G.WHITE, "c", alpha=G.clamp01((t - 0.4) / 0.4))
        if self.game == 1:          # the leaderboard is only for games vs the AI
            self._draw_leaderboard(canvas, W // 2 - 380, 410, 760, 7, highlight=self.result_row,
                                   alpha=G.clamp01((t - 0.9) / 0.5))
        G.text(canvas, "r replay highlights   ·   ENTER rematch   ·   n new game",
               W // 2, H - 30, "ui_light", 20, G.DIM, "c")

    def _draw_leaderboard(self, canvas, x, y, w, n, highlight=None, alpha=1.0):
        rows = self.board.top(n)
        if not rows or alpha <= 0:
            return
        G.text(canvas, "LEADERBOARD  ·  vs the AI", x + w // 2, y, "ui", 22, G.GOLD, "tc", alpha=alpha)
        y += 42
        for i, r in enumerate(rows):
            hl = r is highlight or (highlight and r == highlight)
            G.rect(canvas, x, y, x + w, y + 38, G.GOLD if hl else (40, 30, 26), (0.35 if hl else 0.75) * alpha)
            G.text(canvas, f"{i + 1}", x + 18, y + 19, "score", 26, G.GOLD, "l", alpha=alpha)
            G.text(canvas, r["name"].upper(), x + 60, y + 19, "ui", 21, G.WHITE, "l", alpha=alpha)
            G.text(canvas, f"{r['scored']} - {r['conceded']}", x + w * 0.62, y + 19, "score", 28, G.WHITE, "c",
                   alpha=alpha)
            G.text(canvas, f"{r['fastest']} cm/s" if r["fastest"] else "—", x + w - 18, y + 19, "ui_light", 18,
                   G.DIM, "r", alpha=alpha)
            y += 44


# ==================================================================== helpers
def _safe(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "player"


def _sound(name):
    path = f"/System/Library/Sounds/{name}.aiff"
    if os.path.exists(path):
        try:
            subprocess.Popen(["afplay", "-v", "0.6", path])
        except OSError:
            pass


def _brackets(img, x0, y0, x1, y1, color, n=22, t=2):
    """Techy corner brackets around a panel."""
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(img, (x, y), (x + dx * n, y), color, t, cv2.LINE_AA)
        cv2.line(img, (x, y), (x, y + dy * n), color, t, cv2.LINE_AA)


def _slowmo_schedule(clip, slow_rate=0.4, slow_before=0.9, slow_after=0.35):
    """
    Output frames (at FPS) for a replay: normal speed, slow motion from `slow_before`
    seconds before the goal to `slow_after` after it, then normal again.
    Returns [(frame_index, is_slow)].
    """
    st = clip.stamps
    t, t_end = st[0], st[-1]
    slow_from, slow_to = clip.goal_t - slow_before, clip.goal_t + slow_after
    out, j = [], 0
    while t <= t_end:
        while j + 1 < len(st) and st[j + 1] <= t:
            j += 1
        slow = slow_from <= t <= slow_to
        out.append((j, slow))
        t += (slow_rate if slow else 1.0) / FPS
    return out or [(0, False)]
