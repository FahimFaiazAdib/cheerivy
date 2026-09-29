"""
B4 — Trajectory prediction. Pure math, no OpenCV, fully unit-testable.

Feed it (t, x, y) ball samples in cm; ask it where the ball will cross the
AI flipper line, including bounces off the side (and diagonal) walls.

The board may be tilted (a sheet underneath): along its length the ball then speeds up or slows down,
and a slow ball can stop and roll back. The slope is learned from the ball itself (each half on its
own), starting from config.SLOPE_A_AI_HALF / SLOPE_A_P1_HALF.
"""
from collections import deque

import config as C
from arena import Arena

TRACE_DT = 0.005          # integration step for a sloped board (s)
TRACE_HORIZON_S = 4.0     # don't look further ahead than this
LINE_MARGIN_CM = 6.0      # learn only this far from the carriage lines (no hits in the data)
LEARN_MIN_S = 0.15        # a stretch shorter than this in one half teaches nothing


def fit_velocity(samples):
    """Least-squares line through (t, x) and (t, y). Returns (vx, vy) in cm/s."""
    n = len(samples)
    t0 = samples[-1][0]
    ts = [s[0] - t0 for s in samples]
    mt = sum(ts) / n
    var_t = sum((t - mt) ** 2 for t in ts)
    if var_t < 1e-9:
        return 0.0, 0.0
    mx = sum(s[1] for s in samples) / n
    my = sum(s[2] for s in samples) / n
    vx = sum((t - mt) * (s[1] - mx) for t, s in zip(ts, samples)) / var_t
    vy = sum((t - mt) * (s[2] - my) for t, s in zip(ts, samples)) / var_t
    return vx, vy


def fit_accel(samples):
    """Least-squares parabola y = c + v t + a t²/2. Returns a (cm/s²) or None."""
    n = len(samples)
    if n < 6:
        return None
    t0 = samples[0][0]
    ts = [s[0] - t0 for s in samples]
    ys = [s[2] for s in samples]
    # normal equations for [c, v, a/2] with basis 1, t, t²
    s0, s1, s2, s3, s4 = (sum(t ** k for t in ts) for k in range(5))
    b0 = sum(ys)
    b1 = sum(t * y for t, y in zip(ts, ys))
    b2 = sum(t * t * y for t, y in zip(ts, ys))
    m = [[s0, s1, s2, b0], [s1, s2, s3, b1], [s2, s3, s4, b2]]
    for i in range(3):                                  # Gaussian elimination
        piv = m[i][i]
        if abs(piv) < 1e-12:
            return None
        for j in range(i + 1, 3):
            f = m[j][i] / piv
            m[j] = [a - f * b for a, b in zip(m[j], m[i])]
    half_a = m[2][3] / m[2][2]
    return 2 * half_a


class Predictor:
    def __init__(self, arena=None, line_y=C.AI_LINE_Y):
        self.arena = arena or Arena()
        self.line_y = line_y
        self.hist = deque()
        self.seg = []                # the ball's current stretch inside one half (learning the slope)
        self.vx = self.vy = 0.0
        self.slope = [C.SLOPE_A_AI_HALF, C.SLOPE_A_P1_HALF]   # learned: AI half, P1 half

    def reset(self):
        self.hist.clear()
        if self.seg:                     # the ball's last stretch still tells us about the slope
            self._learn(self.seg)
        self.seg = []
        self.vx = self.vy = 0.0

    # ------------------------------------------------------------ slope
    def accel(self, y):
        return self.slope[0 if y < C.ARENA_H / 2 else 1]

    @property
    def tilted(self):
        return abs(self.slope[0]) > 0.5 or abs(self.slope[1]) > 0.5

    def _track_segment(self, t, x, y):
        """Collect the ball's path while it stays in one half, away from both carriages (no hits);
        when it leaves, learn the slope of that half from how its speed changed."""
        mid = C.ARENA_H / 2
        inside = self.line_y + LINE_MARGIN_CM < y < C.ARENA_H - self.line_y - LINE_MARGIN_CM
        if self.seg and (not inside or (self.seg[-1][2] < mid) != (y < mid)):
            self._learn(self.seg)
            self.seg = []
        if inside:
            self.seg.append((t, x, y))

    def _learn(self, pts):
        if not C.SLOPE_LEARN or len(pts) < 6:
            return
        span = pts[-1][0] - pts[0][0]
        if span < LEARN_MIN_S:
            return
        a = fit_accel(pts)
        if a is None or abs(a) > C.SLOPE_MAX:
            return
        half = 0 if pts[-1][2] < C.ARENA_H / 2 else 1
        # a short stretch is a noisy measurement: it counts for less
        rate = C.SLOPE_LEARN_RATE * min(1.0, (span / C.SLOPE_LEARN_S) ** 2)
        self.slope[half] += rate * (a - self.slope[half])

    # ------------------------------------------------------------ tracking
    def update(self, t, x, y):
        # A big jump means a hit/bounce/misdetection: old history no longer valid.
        if self.hist:
            _, px, py = self.hist[-1]
            if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 > C.BALL_MAX_JUMP_CM:
                self.hist.clear()
                self.seg = []
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > C.VEL_WINDOW_S:
            self.hist.popleft()
        if len(self.hist) >= C.VEL_MIN_POINTS:
            self.vx, self.vy = fit_velocity(list(self.hist))
            # A side-wall bounce inside the window flips vx; refit on the newest leg.
            self._trim_after_bounce()
            if self.tilted:                            # the fit is the speed mid-window: bring it to now
                span = self.hist[-1][0] - self.hist[0][0]
                self.vy += self.accel(y) * span / 2
        self._track_segment(t, x, y)

    def _trim_after_bounce(self):
        pts = list(self.hist)
        for i in range(len(pts) - 2, 0, -1):
            dx1 = pts[i][1] - pts[i - 1][1]
            dx2 = pts[i + 1][1] - pts[i][1]
            if dx1 * dx2 < 0 and abs(dx1) > 0.3 and abs(dx2) > 0.3:
                leg = pts[i:]
                if len(leg) >= 2:
                    self.vx, self.vy = fit_velocity(leg)
                return

    @property
    def position(self):
        return (self.hist[-1][1], self.hist[-1][2]) if self.hist else None

    # ------------------------------------------------------------ prediction
    def time_to_line(self, y, vy):
        """Seconds until the ball reaches the AI line, or None if it won't (rolls back / goes away)."""
        if not self.tilted:
            return (self.line_y - y) / vy if vy < -C.MIN_APPROACH_SPEED else None
        far = C.ARENA_H - self.line_y
        t = 0.0
        while t < TRACE_HORIZON_S:
            vy += self.accel(y) * TRACE_DT
            y += vy * TRACE_DT
            t += TRACE_DT
            if y <= self.line_y:
                return t
            if y >= far:                              # reaches the other carriage first
                return None
        return None

    def incoming(self):
        if self.position is None:
            return False
        if not self.tilted:
            return self.vy < -C.MIN_APPROACH_SPEED
        return self.time_to_line(self.position[1], self.vy) is not None

    def _trace(self):
        if self.position is None:
            return None
        x, y = self.position
        if y <= self.line_y:
            return (x, 0.0, [(x, y)]) if self.incoming() or self.tilted else None
        t = self.time_to_line(y, self.vy)
        if t is None:
            return None
        if not self.tilted:
            return self.arena.trace_to_line(x, y, self.vx, self.vy, self.line_y)
        # Sideways the ball still moves at a steady speed; only its progress along the board is
        # curved. Tracing with the average speed along the board gives the same crossing point and time.
        tr = self.arena.trace_to_line(x, y, self.vx, (self.line_y - y) / max(t, 1e-3), self.line_y)
        if tr is None:
            return None
        return tr[0], t, tr[2]

    def intercept(self, latency=C.SYSTEM_LATENCY_S):
        """
        Returns (x_at_line, time_to_line_s) for a ball heading to the AI,
        or None. Time is measured from NOW (latency already subtracted).
        """
        tr = self._trace()
        return None if tr is None else (tr[0], max(0.0, tr[1] - latency))

    def path(self):
        """Predicted path with every wall bounce (for drawing)."""
        tr = self._trace()
        return [] if tr is None else tr[2]
