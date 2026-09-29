"""
What is happening on the table, frame by frame.

PlayWatcher turns ball + carriage positions into play events for the Flow (and so the commentary):
    ('hit', p, {'speed': cm/s, 'close': bool})   carriage p sent the ball back (a save); close = edge / last moment
    ('wall',)                                     the ball bounced off a side wall
    ('danger', p)                                 the ball is heading past carriage p: it can't get there in time
    ('rollback', p)                               a slow ball couldn't climb the tilted board: it rolls back to p
    ('rest', p)                                   the ball has stopped in player p's half
It also keeps .eta (seconds to the next carriage line, None when not moving) and .last_touch (who
struck the ball last: a goal against the last toucher is an own goal).
The same watcher reads the real camera AI later (main.py) and the simulated table below.

SimTable is a stand-in for the robot on the Mac: ball physics on the rectangular, tilted board, bots on
both carriages (the AI one plays like the difficulty), real goals, and it obeys the robot commands
the Flow sends (lock, unlock, freeze, mode).
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C  # noqa: E402

H = C.ARENA_H
XL, XR = C.X0, C.X0 + C.BASE_W          # side walls = the ends of the rails (rectangular board)
R, CW = C.BALL_RADIUS, C.CARRIAGE_W
LINE = {2: C.AI_LINE_Y, 1: H - C.AI_LINE_Y}   # ball centre touching carriage p's face
CARRIAGE_SPEED = C.MOTOR_SPEED_CM_S

HIT_ZONE_CM = 4.0       # a bounce this close to a carriage line is a hit by that carriage
CLOSE_EDGE_CM = 1.2     # ball this close to the carriage's corner = an edge save
DANGER_ETA_S = 1.0      # only warn about balls arriving within this
REST_SPEED = 2.0        # cm/s
REST_S = 1.5
STEP_S = 0.01           # integration step for predictions on the tilted board
HORIZON_S = 4.0


def fold(x, lo, hi):
    """x after bouncing between two walls (mirror folding)."""
    w = hi - lo
    if w <= 0:
        return lo
    t = (x - lo) % (2 * w)
    return lo + (t if t <= w else 2 * w - t)


def accel(y, slope):
    return slope[0 if y < H / 2 else 1]


def travel(x, y, vx, vy, slope=(0.0, 0.0), points=False):
    """Follow a rolling ball to the next carriage line.
    -> (carriage p, x where it meets that line, seconds, path points) or None if it stops first."""
    if slope == (0.0, 0.0) or slope == [0.0, 0.0]:
        if abs(vy) < 0.5:
            return None
        p = 2 if vy < 0 else 1
        t = (LINE[p] - y) / vy
        if t < 0:
            return None
        pts = path_straight(x, y, vx, vy, t, p) if points else []
        return p, fold(x + vx * t, XL + R, XR - R), t, pts
    t, pts, x0 = 0.0, [[round(fold(x, XL + R, XR - R), 1), round(y, 1)]], x
    last = 0.0
    while t < HORIZON_S:
        vy += accel(y, slope) * STEP_S
        y += vy * STEP_S
        t += STEP_S
        if points and t - last >= 0.05:
            last = t
            pts.append([round(fold(x0 + vx * t, XL + R, XR - R), 1), round(y, 1)])
        for p in (1, 2):
            if (p == 2 and y <= LINE[2]) or (p == 1 and y >= LINE[1]):
                xl = fold(x0 + vx * t, XL + R, XR - R)
                pts.append([round(xl, 1), round(LINE[p], 1)])
                return p, xl, t, pts
        if abs(vy) < 0.3 and abs(accel(y, slope)) < 0.3:
            return None                                   # stopped on a flat spot
    return None


def path_straight(x, y, vx, vy, t_end, p):
    """Straight path with side-wall bounces (flat board), as points."""
    pts = [[round(x, 1), round(y, 1)]]
    t = 0.0
    for _ in range(8):
        tx = ((XR - R - x) / vx if vx > 0 else (XL + R - x) / vx) if abs(vx) > 1e-6 else math.inf
        if t + tx >= t_end:
            break
        x, y, t, vx = x + vx * tx, y + vy * tx, t + tx, -vx
        pts.append([round(x, 1), round(y, 1)])
    dt = t_end - t
    pts.append([round(x + vx * dt, 1), round(LINE[p], 1)])
    return pts


class PlayWatcher:
    def __init__(self, slope=(0.0, 0.0)):
        self.slope = tuple(slope)
        self.last_touch = None
        self.reset()

    def reset(self):
        self.prev = None           # (t, x, y, vx, vy)
        self.eta = None
        self.danger_on = {1: False, 2: False}
        self.rest_since = None
        self.rested = False
        self.last_hit = 0.0
        self.heading = 0           # +1 toward P1 / -1 toward the AI: the last clear direction along the board

    def touch(self, p):
        """Carriage p struck the ball (the kick-off / restart strike)."""
        self.last_touch = p

    def update(self, t, ball, vel, carriage):
        """ball (x, y) or None, vel (vx, vy) or None, carriage {1: x, 2: x}. Returns a list of events."""
        ev = []
        if ball is None or vel is None:
            self.prev, self.eta = None, None
            return ev
        (x, y), (vx, vy) = ball, vel
        speed = math.hypot(vx, vy)
        if self.prev:
            _, px, py, pvx, pvy = self.prev
            flipped = False
            for p in (1, 2):                              # a carriage sent it back
                toward = pvy > 1 if p == 1 else pvy < -1
                away = vy < -1 if p == 1 else vy > 1
                if toward and away and abs(y - LINE[p]) < HIT_ZONE_CM and t - self.last_hit > 0.25:
                    edge = abs(x - carriage[p]) > CW / 2 - CLOSE_EDGE_CM
                    ev.append(("hit", p, {"speed": round(speed), "close": bool(edge or self.danger_on[p])}))
                    self.danger_on[p] = False
                    self.last_hit = t
                    self.last_touch = p
                    flipped = True
            if flipped:
                self.heading = 1 if vy > 0 else -1
            elif abs(vy) > 1.5:
                h = 1 if vy > 0 else -1
                if (self.heading and h != self.heading
                        and min(abs(y - LINE[1]), abs(y - LINE[2])) > HIT_ZONE_CM):
                    ev.append(("rollback", 1 if h > 0 else 2))   # it gave up the climb and turned back
                self.heading = h
            if pvx * vx < 0 and (x < XL + R + 2 or x > XR - R - 2) and abs(vx) > 3:
                ev.append(("wall",))
        land = travel(x, y, vx, vy, self.slope) if speed > REST_SPEED or self.slope != (0.0, 0.0) else None
        self.eta = land[2] if land else None
        if land:
            p, lx, eta, _ = land
            reach = abs(lx - carriage[p]) - CW / 2 - R * 0.5
            if eta < DANGER_ETA_S and reach > CARRIAGE_SPEED * eta and not self.danger_on[p]:
                self.danger_on[p] = True
                ev.append(("danger", p))
        if speed < REST_SPEED:
            self.rest_since = self.rest_since or t
            if not self.rested and t - self.rest_since >= REST_S:
                self.rested = True
                ev.append(("rest", 1 if y > H / 2 else 2))
        elif speed > 2 * REST_SPEED:
            self.rest_since, self.rested = None, False
        self.prev = (t, x, y, vx, vy)
        return ev


class SimTable:
    """Fake robot + camera for the simulator. step() -> (frame dict for the screen, goal scorer or None)."""
    BOTS = {  # difficulty -> (carriage speed cm/s, aiming error cm, reaction s)
        "EASY": (18, 5.0, 0.35), "MEDIUM": (26, 3.0, 0.2), "HARD": (34, 1.5, 0.1)}
    HUMAN = (24, 4.0, 0.3)
    WEAK_P = 0.12            # a weak strike (may not make the climb and roll back)

    def __init__(self, slope=C.SIM_SLOPE):
        self.slope = tuple(slope)
        self.x, self.y, self.vx, self.vy = (XL + XR) / 2, H / 2, 0.0, 0.0
        self.car = {1: (XL + XR) / 2, 2: (XL + XR) / 2}
        self.locked = True
        self.frozen = {1: 0.0, 2: 0.0}
        self.mode, self.difficulty = "ai", "MEDIUM"
        self.placer = 1
        self.striker = None          # who struck last (the flow asks, for own goals)
        self.aim = {1: None, 2: None}          # (target x, start moving at)
        self.rest_until = None

    def command(self, cmd, now):
        a = cmd.split()
        if a[0] == "lock":
            self.locked = True
        elif a[0] == "unlock" and self.locked:
            self.locked = False
            self._launch(self.placer if self.placer in (1, 2) else 1)
        elif a[0] == "freeze":
            self.frozen[int(a[1])] = now + float(a[2])
        elif a[0] == "mode":
            self.mode = a[1]
            if len(a) > 2:
                self.difficulty = a[2]

    def _launch(self, p, speed=None):
        """Carriage p strikes: the ball goes toward the other side."""
        if speed is None:
            speed = random.uniform(10, 20) if random.random() < self.WEAK_P else random.uniform(30, 60)
        ang = random.uniform(-0.6, 0.6)
        self.vx = speed * math.sin(ang)
        self.vy = speed * math.cos(ang) * (-1 if p == 1 else 1)
        self.aim = {1: None, 2: None}
        self.striker = p

    def _bot(self, p):
        if (p == 2 and self.mode == "ai") or self.mode == "aivai":
            return self.BOTS.get(self.difficulty, self.BOTS["MEDIUM"])
        return self.HUMAN

    def step(self, dt, now, placer):
        self.placer = placer
        mid = (XL + XR) / 2
        if self.locked:                              # ball waits in front of whoever restarts
            top = placer == 2
            self.x += (self.car[2 if top else 1] - self.x) * 0.15
            self.y += ((LINE[2] + 1 if top else LINE[1] - 1) - self.y) * 0.15
            self.vx = self.vy = 0.0
            return self._frame(), None
        goal = None
        if self.rest_until is not None:              # a stopped ball: someone fetches it after a while
            if now >= self.rest_until:
                self.rest_until = None
                self._launch(1 if self.y > H / 2 else 2, random.uniform(25, 40))
        else:
            self.vy += accel(self.y, self.slope) * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.x < XL + R:
                self.x, self.vx = 2 * (XL + R) - self.x, abs(self.vx)
            elif self.x > XR - R:
                self.x, self.vx = 2 * (XR - R) - self.x, -abs(self.vx)
            if self.slope == (0.0, 0.0):             # flat board: a weak ball slows down and stops
                sp = math.hypot(self.vx, self.vy)
                if sp < 12:
                    k = max(0.0, sp - 6 * dt) / sp if sp > 0 else 0
                    self.vx, self.vy = self.vx * k, self.vy * k
                    if sp < 0.5:
                        self.vx = self.vy = 0.0
                        self.rest_until = now + 3.5
            for p in (1, 2):
                crossing = self.vy < 0 and self.y <= LINE[2] if p == 2 else self.vy > 0 and self.y >= LINE[1]
                if crossing:
                    if abs(self.x - self.car[p]) <= CW / 2 + R * 0.6:
                        self.y = LINE[p]
                        off = (self.x - self.car[p]) / (CW / 2)
                        self._launch(p)
                        self.vx += off * 15
                    else:
                        goal = 3 - p
                        self.locked = True
        for p in (1, 2):                             # the bots
            if now < self.frozen[p]:
                continue
            spd, err, react = self._bot(p)
            land = travel(self.x, self.y, self.vx, self.vy, self.slope)
            if self.rest_until is not None and (self.y > H / 2) == (p == 1):
                target = self.x                          # go and get a stopped ball on my side
            elif land and land[0] == p:
                if self.aim[p] is None:
                    self.aim[p] = (land[1] + random.gauss(0, err), now + react)
                target = self.aim[p][0] if now >= self.aim[p][1] else self.car[p]
            else:
                self.aim[p] = None
                target = mid
            d = max(-spd * dt, min(spd * dt, target - self.car[p]))
            self.car[p] = max(XL + CW / 2, min(XR - CW / 2, self.car[p] + d))
        return self._frame(), goal

    def _frame(self):
        moving = not self.locked and (abs(self.vx) + abs(self.vy) > 0.5 or self.slope != (0.0, 0.0))
        land = travel(self.x, self.y, self.vx, self.vy, self.slope, points=True) if moving else None
        return {"ball": [round(self.x, 2), round(self.y, 2)], "vel": [round(self.vx, 1), round(self.vy, 1)],
                "path": land[3] if land else [],
                "ai_x": round(self.car[2], 2), "p1_x": round(self.car[1], 2)}
