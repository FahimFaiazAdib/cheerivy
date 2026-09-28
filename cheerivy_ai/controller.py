"""
B5 — Decision making: where should the carriage go, and when to fire.

Output is exactly the byte protocol main.c already understands:
    'L' left   'R' right   'S' stop   'F' fire   'Z' freeze opponent
"""
import random
import time

import config as C


class Controller:
    def __init__(self, difficulty=C.DEFAULT_DIFFICULTY):
        self.set_difficulty(difficulty)
        self.moving = "S"
        self.last_fire = 0.0
        self.target = self.centre = C.X0 + C.BASE_W / 2
        self._pending = None           # (apply_at, target) — simulates human-like reaction
        self._aim_error = 0.0
        self._will_fire = True
        self._in_shot = False

    def set_difficulty(self, level):
        self.level = level
        self.delay, self.error_cm, self.fire_prob = C.DIFFICULTY[level]

    def _new_shot(self):
        # Decide once per incoming shot how "good" this attempt will be.
        if not self._in_shot:
            self._in_shot = True
            self._aim_error = random.uniform(-self.error_cm, self.error_cm)
            self._will_fire = random.random() < self.fire_prob

    def update(self, predictor, carriage_x, now=None):
        """Returns (move_cmd, fire: bool, status_text)."""
        now = now or time.time()
        hit = predictor.intercept()
        if hit is not None:
            x_hit, t_hit = hit
            self._new_shot()
            desired = x_hit + self._aim_error
            status = f"INTERCEPT x={x_hit:4.1f}cm in {t_hit*1000:3.0f}ms"
        else:
            x_hit = t_hit = None
            self._in_shot = False
            pos = predictor.position
            # No incoming shot: shadow the ball's x, drifting toward the centre.
            desired = self.centre if pos is None else 0.5 * pos[0] + 0.5 * self.centre
            status = "TRACKING" if pos else "NO BALL"

        desired = min(max(desired, C.CARRIAGE_MIN_X), C.CARRIAGE_MAX_X)  # rail limits

        # Reaction delay: the new target only takes effect after `delay` seconds.
        if self.delay and abs(desired - self.target) > 2:
            if self._pending is None:
                self._pending = (now + self.delay, desired)
            elif now >= self._pending[0]:
                self.target, self._pending = desired, None
            else:
                self._pending = (self._pending[0], desired)
        else:
            self.target, self._pending = desired, None

        if carriage_x is None:
            return "S", False, "CARRIAGE NOT SEEN (left-click the carriage tape)"

        err = self.target - carriage_x
        band = C.DEADBAND_CM if self.moving != "S" else C.DEADBAND_CM + C.HYSTERESIS_CM
        self.moving = "S" if abs(err) < band else ("R" if err > 0 else "L")

        fire = (x_hit is not None and self._will_fire
                and t_hit <= C.FIRE_LEAD_S
                and abs(x_hit - carriage_x) <= C.FIRE_REACH_CM
                and now - self.last_fire > C.FIRE_COOLDOWN_S)
        if fire:
            self.last_fire = now
            status = "FIRE!"
        return self.moving, fire, status
