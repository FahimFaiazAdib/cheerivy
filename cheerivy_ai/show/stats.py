"""
Match statistics from the ball tracker, plus the leaderboard kept across matches.

Coordinates are the tracker's centimetres: AI baseline at y = 0, human baseline at y = ARENA_H.
The ball moving toward the AI has vy < 0.
"""
import json
import math
import os
import time
from collections import deque

import config as C

DIR_SPEED = 15.0          # cm/s: slower than this doesn't count as a direction
DIR_FRAMES = 3            # frames in a row before a new direction is believed
AI_ZONE_CM = C.AI_LINE_Y + 14.0   # a turn-around this close to the AI = an AI save
SPEED_SPAN_S = 0.10       # measure speed over this much movement


class MatchStats:
    def __init__(self):
        self.speeds = deque()        # (t, speed cm/s)
        self.top_speed = 0.0
        self.shots = {"H": 0, "A": 0}
        self.ai_saves = 0
        self.rally = 0
        self.longest_rally = 0
        self._dir = 0
        self._cand, self._cand_n = 0, 0
        self._pos = deque()           # (t, x, y) recent ball positions
        self._recent = deque(maxlen=3)

    def update(self, t, ball, vx=0.0, vy=0.0):
        """Speed and direction are measured here from positions ~0.1 s apart (the predictor's
        velocity is tuned for reaction time, not for honest shot speeds)."""
        if ball is None:
            return
        pos = self._pos
        if pos and math.dist(pos[-1][1:], ball) > C.BALL_MAX_JUMP_CM:
            pos.clear()                            # re-serve / misdetection
        pos.append((t, ball[0], ball[1]))
        while pos and t - pos[0][0] > 0.25:
            pos.popleft()
        old = next((p for p in pos if t - p[0] <= SPEED_SPAN_S), None)
        if old is None or t - old[0] < SPEED_SPAN_S * 0.6:
            return
        dt = t - old[0]
        vx, vy = (ball[0] - old[1]) / dt, (ball[1] - old[2]) / dt
        sp = math.hypot(vx, vy)
        self._recent.append(sp)
        sp = sorted(self._recent)[len(self._recent) // 2]     # median of the last 3
        if sp < 400:
            self.speeds.append((t, sp))
            self.top_speed = max(self.top_speed, sp)
        while self.speeds and t - self.speeds[0][0] > 2.0:
            self.speeds.popleft()
        d = 0 if abs(vy) < DIR_SPEED else (-1 if vy < 0 else 1)
        if d == 0:
            return
        if d == self._cand:
            self._cand_n += 1
        else:
            self._cand, self._cand_n = d, 1
        if self._cand_n >= DIR_FRAMES and d != self._dir:
            if d == -1:                           # now heading to the AI -> the human shot it
                self.shots["H"] += 1
            else:                                 # now heading to the human -> the AI sent it back
                self.shots["A"] += 1
                if ball[1] < AI_ZONE_CM and self._dir == -1:
                    self.ai_saves += 1
            if self._dir != 0:
                self.rally += 1
                self.longest_rally = max(self.longest_rally, self.rally)
            self._dir = d

    def shot_speed(self, t=None, window=1.2):
        """Fastest ball speed in the last `window` seconds (the scoring shot)."""
        t = t or time.time()
        v = [s for ts, s in self.speeds if t - ts <= window]
        return max(v) if v else 0.0

    def goal_scored(self):
        self.rally = 0
        self._dir = 0


class Leaderboard:
    def __init__(self, path):
        self.path = path
        self.rows = []
        try:
            with open(path) as f:
                self.rows = json.load(f)
        except (OSError, ValueError):
            self.rows = []

    def add(self, name, scored, conceded, fastest, level):
        row = {"name": name, "scored": scored, "conceded": conceded, "fastest": round(fastest),
               "level": level, "date": time.strftime("%Y-%m-%d %H:%M")}
        self.rows.append(row)
        try:
            with open(self.path, "w") as f:
                json.dump(self.rows, f, indent=1)
        except OSError:
            pass
        return row

    def top(self, n=8):
        key = lambda r: (r["scored"] - r["conceded"], r["scored"], r["fastest"])
        return sorted(self.rows, key=key, reverse=True)[:n]
