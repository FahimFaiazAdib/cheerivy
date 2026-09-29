"""
B4 tests — run with:   python3 -m unittest -v test_predictor
Synthetic ball paths, no camera needed.
"""
import unittest

import config as C
from arena import Arena, default_polygon
from predictor import Predictor


def fold(x, lo, hi):
    """Reference answer for a plain rectangle: mirror x back between the walls."""
    span = hi - lo
    u = (x - lo) % (2 * span)
    return lo + (2 * span - u if u > span else u)


def rect_predictor():
    """40 x 60 rectangular box, point ball — easy to check by hand."""
    return Predictor(Arena([(0, 0), (40, 0), (40, 60), (0, 60)], radius=0, goal_ys=(0, 60)), line_y=5)


def feed(pred, x0, y0, vx, vy, n=8, dt=1 / 30, noise=0.0):
    import random
    for i in range(n):
        t = i * dt
        pred.update(t, x0 + vx * t + random.uniform(-noise, noise),
                    y0 + vy * t + random.uniform(-noise, noise))


class TestOctagon(unittest.TestCase):
    """The real board: diagonal chamfers near both baselines."""
    def setUp(self):
        self.arena = Arena(radius=0)

    def test_baselines_are_open_goals(self):
        self.assertEqual(len(self.arena.walls), len(self.arena.poly) - 2)

    def test_straight_shot_down_the_middle(self):
        x_mid = C.X0 + C.BASE_W / 2
        x, t, path = self.arena.trace_to_line(x_mid, 40, 0, -50, C.AI_LINE_Y)
        self.assertAlmostEqual(x, x_mid, delta=1e-6)
        self.assertEqual(len(path), 2)            # no bounces

    @unittest.skipIf(C.CHAMFER_DX == 0, "rectangular board: no chamfers")
    def test_chamfer_redirects_ball(self):
        # Ball running up along the far-left side wall must hit the AI-side
        # chamfer and get pushed back toward the middle (x increases).
        x_side = C.X0 - C.CHAMFER_DX + 1
        res = self.arena.trace_to_line(x_side, C.ARENA_H / 2, 0, -50, C.AI_LINE_Y)
        self.assertIsNotNone(res)
        x, _, path = res
        self.assertGreater(len(path), 2)          # at least one bounce
        self.assertGreater(x, x_side)
        self.assertTrue(C.X0 <= x <= C.X0 + C.BASE_W)

    def test_hits_stay_inside_board(self):
        import random
        random.seed(3)
        for _ in range(300):
            x0 = random.uniform(C.X0, C.X0 + C.BASE_W)
            vx, vy = random.uniform(-80, 80), -random.uniform(10, 80)
            res = self.arena.trace_to_line(x0, C.ARENA_H - 8, vx, vy, C.AI_LINE_Y)
            if res:
                self.assertTrue(self.arena.contains(res[0], C.AI_LINE_Y, margin=1e-6), res)

    def test_hull_accepts_any_click_order(self):
        import random
        pts = default_polygon()
        random.shuffle(pts)
        self.assertEqual(sorted(Arena(pts).poly), sorted(Arena().poly))


class TestPredictor(unittest.TestCase):
    def test_straight_shot(self):
        p = rect_predictor()
        feed(p, 20, 50, 0, -40)
        x, t = p.intercept(latency=0)
        self.assertAlmostEqual(x, 20, delta=0.2)
        # Last sample at y = 50 - 40*7/30; time to reach y=5
        y_last = 50 - 40 * 7 / 30
        self.assertAlmostEqual(t, (y_last - 5) / 40, delta=0.02)

    def test_diagonal_no_bounce(self):
        p = rect_predictor()
        feed(p, 10, 45, 10, -40)
        x, _ = p.intercept(latency=0)
        x_last, y_last = p.position
        self.assertAlmostEqual(x, x_last + 10 * (y_last - 5) / 40, delta=0.3)

    def test_one_wall_bounce(self):
        p = rect_predictor()
        feed(p, 30, 50, 30, -40)          # heading into the right wall
        x_last, y_last = p.position
        raw = x_last + 30 * (y_last - 5) / 40
        self.assertGreater(raw, 40)
        x, _ = p.intercept(latency=0)
        self.assertAlmostEqual(x, 80 - raw, delta=0.4)

    def test_two_wall_bounces(self):
        p = rect_predictor()
        feed(p, 20, 58, 80, -40)
        x, _ = p.intercept(latency=0)
        self.assertTrue(0 <= x <= 40)
        x_last, y_last = p.position
        self.assertAlmostEqual(x, fold(x_last + 80 * (y_last - 5) / 40, 0, 40), delta=0.5)

    def test_moving_away_is_not_incoming(self):
        p = Predictor()
        feed(p, 20, 20, 5, +40)
        self.assertIsNone(p.intercept())

    def test_noisy_detections(self):
        p = rect_predictor()
        feed(p, 20, 50, 5, -45, noise=0.3)
        x, _ = p.intercept(latency=0)
        x_last, y_last = p.position
        self.assertAlmostEqual(x, x_last + 5 * (y_last - 5) / 45, delta=2.0)

    def test_latency_reduces_time(self):
        p = Predictor()
        feed(p, 20, 50, 0, -40)
        self.assertAlmostEqual(p.intercept(latency=0)[1] - p.intercept(latency=0.07)[1], 0.07, delta=1e-6)

    def test_teleport_clears_history(self):
        p = Predictor()
        feed(p, 20, 50, 0, -40)
        p.update(1.0, 5, 10)               # jump > BALL_MAX_JUMP_CM
        self.assertEqual(len(p.hist), 1)

    def test_bounce_inside_window_uses_newest_leg(self):
        p = rect_predictor()
        dt = 1 / 30
        pts = [(36, 40), (38, 38), (40, 36), (38, 34), (36, 32)]  # hit right wall, now going left
        for i, (x, y) in enumerate(pts):
            p.update(i * dt, x, y)
        self.assertLess(p.vx, 0)



def roll(p, x, y, vx, vy, secs, slope, dt=1 / 30):
    """Feed a ball rolling on a sloped board (slope = (AI half, P1 half) in cm/s²)."""
    t = 0.0
    while t < secs:
        p.update(t, x, y)
        a = slope[0 if y < C.ARENA_H / 2 else 1]
        vy += a * dt
        x += vx * dt
        y += vy * dt
        t += dt
    return x, y, vx, vy


class TestTilt(unittest.TestCase):
    SLOPE = (-6.0, 6.0)        # sheet under the middle: each half rolls down to its own end

    def tilted(self):
        p = Predictor()
        p.slope = list(self.SLOPE)
        return p

    def test_slow_push_rolls_back(self):
        # pushed by the human at 12 cm/s: on a flat board it would reach the AI, uphill it can't
        flat, tilt = Predictor(), self.tilted()
        for p in (flat, tilt):
            roll(p, 22, 38, 0, -12, 0.2, (0, 0))
        self.assertIsNotNone(flat.intercept())
        self.assertIsNone(tilt.intercept())

    def test_fast_push_arrives_later_uphill(self):
        # uphill to the middle, then downhill to the AI: still gets there
        flat, tilt = Predictor(), self.tilted()
        for p in (flat, tilt):
            roll(p, 22, 38, 0, -40, 0.2, (0, 0))
        self.assertIsNotNone(tilt.intercept())
        self.assertNotAlmostEqual(tilt.intercept()[1], flat.intercept()[1], delta=0.01)

    def test_ball_in_ai_half_comes_to_ai(self):
        p = self.tilted()
        roll(p, 22, 18, 0, 3, 0.3, self.SLOPE)          # drifting away, but downhill is toward the AI
        self.assertIsNotNone(p.intercept())

    def test_learns_the_slope(self):
        p = Predictor()
        p.slope = [0.0, 0.0]
        for k in range(40):                               # many slow free rolls in the P1 half
            p.reset()
            roll(p, 22, 32, 0, -8, 0.8, self.SLOPE)
        self.assertAlmostEqual(p.slope[1], self.SLOPE[1], delta=1.5)

    def test_flat_board_unchanged(self):
        p = Predictor()
        p.slope = [0.0, 0.0]
        feed(p, 20, 50, 0, -40)
        self.assertFalse(p.tilted)
        self.assertIsNotNone(p.intercept())


if __name__ == "__main__":
    unittest.main()
