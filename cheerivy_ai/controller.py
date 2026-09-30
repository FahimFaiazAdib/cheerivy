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
        # Where the carriage can really go. Starts from the measured rail, shrinks when the
        # carriage is driven against an end and stops moving (camera calibration is never exact).
        self.rail_lo, self.rail_hi = C.CARRIAGE_MIN_X, C.CARRIAGE_MAX_X
        self.motor_speed = C.MOTOR_SPEED_CM_S   # learned while playing
        self.swap_request = False                # set when the carriage keeps moving the wrong way
        self._wrong_way = 0
        self._move_cmd, self._move_end, self._wait_end, self._move_from = "S", 0.0, 0.0, None

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
            near = pos is not None and pos[1] <= C.AI_LINE_Y + C.NEAR_BALL_CM
            if near:
                # Slow or resting ball right in front: go to it (it's not coming by itself).
                desired = pos[0]
                status = "BALL AT MY FEET"
            else:
                # No incoming shot: stay where it is, unless it's out near a corner; then come back
                # only as far as the edge of a wide middle area. (Running back to the exact middle
                # after every shot is too much for the N20: it's still on its way at the next shot.)
                desired = min(max(self.target, self.centre - C.IDLE_ZONE_CM), self.centre + C.IDLE_ZONE_CM)
                status = "WAITING" if pos else "NO BALL"

        desired = min(max(desired, self.rail_lo + C.RAIL_MARGIN_CM), self.rail_hi - C.RAIL_MARGIN_CM)

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

        # The carriage can never be outside the rail it was seen on: widen the limits if needed.
        self.rail_lo = min(self.rail_lo, carriage_x)
        self.rail_hi = max(self.rail_hi, carriage_x)

        # Timed moves. The camera and Bluetooth lag behind, so "drive until the camera says stop"
        # always overshoots (a full-speed carriage travels speed x delay before the stop lands).
        # Instead: drive for distance / motor speed seconds, stop, wait until the camera shows where
        # it really ended up, correct. Start and stop are delayed equally, so the timing holds.
        if now < self._move_end:
            cmd = self._move_cmd
        elif now < self._wait_end:
            cmd = "S"
        else:
            if self._move_from is not None:            # a move just settled: learn from it
                x_from, dur, d = self._move_from
                moved = (carriage_x - x_from) * (1 if d == "R" else -1)
                if dur >= 0.06 and moved < C.STALL_MOVE_CM and (
                        carriage_x > self.centre + 5 if d == "R" else carriage_x < self.centre - 5):
                    if d == "R":                       # drove but didn't move: that's the real rail end
                        self.rail_hi = carriage_x
                    else:
                        self.rail_lo = carriage_x
                    print(f"[ai] rail end at {carriage_x:.1f} cm -> rail {self.rail_lo:.1f} .. {self.rail_hi:.1f}")
                elif dur >= 0.08 and moved > C.STALL_MOVE_CM:
                    self._wrong_way = 0
                    v = min(max(moved / dur, 5.0), 200.0)
                    self.motor_speed = 0.6 * self.motor_speed + 0.4 * v
                elif dur >= 0.08 and moved < -C.WRONG_WAY_CM:
                    # Clearly went the opposite way (camera image mirrored, motor wires swapped...).
                    # The geared N20 can't be pushed that far by the ball, so this is real:
                    # ask main.py to swap L and R.
                    self._wrong_way += 1               # twice in a row (once can be camera lag)
                    if self._wrong_way >= 2:
                        self.swap_request, self._wrong_way = True, 0
                self._move_from = None
            err = self.target - carriage_x
            band = C.DEADBAND_CM if self.moving != "S" else C.DEADBAND_CM + C.HYSTERESIS_CM
            if x_hit is not None and self.moving == "S":
                band = max(band, C.SHOT_OK_CM)         # already on the plate: stay, don't fine-tune
            cmd = "S" if abs(err) < band else ("R" if err > 0 else "L")
            if (cmd == "R" and carriage_x >= self.rail_hi - 0.3) or (cmd == "L" and carriage_x <= self.rail_lo + 0.3):
                cmd = "S"                               # already at that end of the rail
            if cmd != "S":
                dur = min(max(abs(err) / self.motor_speed, C.MIN_MOVE_S), C.MAX_MOVE_S)
                self._move_cmd = cmd
                self._move_end = now + dur
                self._wait_end = self._move_end + C.SETTLE_S
                self._move_from = (carriage_x, dur, cmd)
        self.moving = cmd

        fire = (x_hit is not None and self._will_fire
                and t_hit <= C.FIRE_LEAD_S
                and abs(x_hit - carriage_x) <= C.FIRE_REACH_CM
                and now - self.last_fire > C.FIRE_COOLDOWN_S)
        if x_hit is None and near and now - self.last_fire > C.FIRE_COOLDOWN_S:
            fire = abs(pos[0] - carriage_x) <= C.FIRE_REACH_CM - 1.0   # lined up: hit it
        if fire:
            self.last_fire = now
            status = "FIRE!"
        return self.moving, fire, status
