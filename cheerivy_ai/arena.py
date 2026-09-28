"""
Arena geometry — the octagonal CHEERIVY board.

      X0            X0+BASE_W
       ┌──── AI baseline ────┐            y = 0
       │                     │  END_STRAIGHT
      ╱                       ╲  CHAMFER (DX x DY)
     │                         │
     │                         │  long side walls
      ╲                       ╱
       │                     │
       └─── human baseline ──┘            y = ARENA_H

The two baselines are GOALS (open), every other edge is a wall that
reflects the ball. All maths here is pure Python (unit-testable).
"""
import config as C


def default_polygon():
    """Nominal board from config.py (used by the simulator and before calibration)."""
    x0, bw, h = C.X0, C.BASE_W, C.ARENA_H
    dx, dy, s = C.CHAMFER_DX, C.CHAMFER_DY, C.END_STRAIGHT
    return [(x0, 0), (x0 + bw, 0), (x0 + bw, s), (x0 + bw + dx, s + dy),
            (x0 + bw + dx, h - s - dy), (x0 + bw, h - s), (x0 + bw, h), (x0, h),
            (x0, h - s), (x0 - dx, h - s - dy), (x0 - dx, s + dy), (x0, s)]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def convex_hull(points):
    """Monotone chain. Lets the user click wall corners in any order."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and _cross((out[-1][0] - out[-2][0], out[-1][1] - out[-2][1]),
                                           (p[0] - out[-2][0], p[1] - out[-2][1])) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]
    return half(pts) + half(reversed(pts))


def _line_intersect(p, d, q, e):
    den = _cross(d, e)
    if abs(den) < 1e-12:
        return None
    t = _cross((q[0] - p[0], q[1] - p[1]), e) / den
    return p[0] + t * d[0], p[1] + t * d[1]


class Arena:
    def __init__(self, polygon=None, radius=C.BALL_RADIUS, goal_ys=(0.0, C.ARENA_H)):
        self.poly = convex_hull(polygon or default_polygon())
        n = len(self.poly)
        cx = sum(p[0] for p in self.poly) / n
        cy = sum(p[1] for p in self.poly) / n

        # Offset every edge inward by the ball radius, so we trace the ball's CENTRE.
        lines = []
        for i in range(n):
            a, b = self.poly[i], self.poly[(i + 1) % n]
            d = (b[0] - a[0], b[1] - a[1])
            ln = (d[0] ** 2 + d[1] ** 2) ** 0.5
            nx, ny = -d[1] / ln, d[0] / ln
            if nx * (cx - a[0]) + ny * (cy - a[1]) < 0:
                nx, ny = -nx, -ny
            is_goal = any(abs(a[1] - g) < 0.5 and abs(b[1] - g) < 0.5 for g in goal_ys)
            lines.append(((a[0] + radius * nx, a[1] + radius * ny), d, (nx, ny), is_goal))
        self.inner = []
        for i in range(n):
            p = _line_intersect(lines[i - 1][0], lines[i - 1][1], lines[i][0], lines[i][1])
            self.inner.append(p or lines[i][0])
        self.walls = []  # (a, b, inward_normal) — goal edges excluded
        for i in range(n):
            if not lines[i][3]:
                self.walls.append((self.inner[i], self.inner[(i + 1) % n], lines[i][2]))

    def contains(self, x, y, margin=0.0):
        for a, b, nrm in self.walls:
            if (x - a[0]) * nrm[0] + (y - a[1]) * nrm[1] < -margin:
                return False
        return True

    def _next_wall(self, x, y, vx, vy, skip):
        best = None
        for i, (a, b, nrm) in enumerate(self.walls):
            if i == skip or vx * nrm[0] + vy * nrm[1] >= 0:   # only walls we move INTO
                continue
            e = (b[0] - a[0], b[1] - a[1])
            den = _cross((vx, vy), e)
            if abs(den) < 1e-12:
                continue
            ap = (a[0] - x, a[1] - y)
            t = _cross(ap, e) / den
            u = _cross(ap, (vx, vy)) / den
            if t > 1e-9 and -1e-6 <= u <= 1 + 1e-6 and (best is None or t < best[0]):
                best = (t, i)
        return best

    @staticmethod
    def _reflect(vx, vy, nrm):
        d = vx * nrm[0] + vy * nrm[1]
        return vx - 2 * d * nrm[0], vy - 2 * d * nrm[1]

    def trace_to_line(self, x, y, vx, vy, line_y, max_bounces=6):
        """
        Follow the ball (bouncing off walls) until its centre reaches y = line_y.
        Returns (x_hit, t_hit, path_points) or None if it never gets there.
        """
        if vy >= 0 or y <= line_y:
            return None
        path, t_total, skip = [(x, y)], 0.0, None
        for _ in range(max_bounces + 1):
            t_line = (line_y - y) / vy
            hit = self._next_wall(x, y, vx, vy, skip)
            if hit is None or t_line <= hit[0]:
                x, y = x + vx * t_line, line_y
                path.append((x, y))
                return x, t_total + t_line, path
            t, skip = hit
            x, y = x + vx * t, y + vy * t
            t_total += t
            path.append((x, y))
            vx, vy = self._reflect(vx, vy, self.walls[skip][2])
            if vy >= 0:
                return None    # a wall sent it back toward the human
        return None

    def advance(self, x, y, vx, vy, dt):
        """Physics step for the simulator: move for dt, bouncing off walls."""
        skip = None
        for _ in range(8):
            hit = self._next_wall(x, y, vx, vy, skip)
            if hit is None or hit[0] >= dt:
                return x + vx * dt, y + vy * dt, vx, vy
            t, skip = hit
            x, y, dt = x + vx * t, y + vy * t, dt - t
            vx, vy = self._reflect(vx, vy, self.walls[skip][2])
        return x, y, vx, vy
