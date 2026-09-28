"""
B4 — Trajectory prediction. Pure math, no OpenCV, fully unit-testable.

Feed it (t, x, y) ball samples in cm; ask it where the ball will cross the
AI flipper line, including bounces off the side and diagonal (chamfer) walls.
"""
from collections import deque

import config as C
from arena import Arena


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


class Predictor:
    def __init__(self, arena=None, line_y=C.AI_LINE_Y):
        self.arena = arena or Arena()
        self.line_y = line_y
        self.hist = deque()
        self.vx = self.vy = 0.0

    def reset(self):
        self.hist.clear()
        self.vx = self.vy = 0.0

    def update(self, t, x, y):
        # A big jump means a hit/bounce/misdetection: old history no longer valid.
        if self.hist:
            _, px, py = self.hist[-1]
            if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 > C.BALL_MAX_JUMP_CM:
                self.hist.clear()
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > C.VEL_WINDOW_S:
            self.hist.popleft()
        if len(self.hist) >= C.VEL_MIN_POINTS:
            self.vx, self.vy = fit_velocity(list(self.hist))
            # A side-wall bounce inside the window flips vx; refit on the newest leg.
            self._trim_after_bounce()

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

    def incoming(self):
        return self.position is not None and self.vy < -C.MIN_APPROACH_SPEED

    def _trace(self):
        if not self.incoming():
            return None
        x, y = self.position
        if y <= self.line_y:
            return x, 0.0, [(x, y)]
        return self.arena.trace_to_line(x, y, self.vx, self.vy, self.line_y)

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
