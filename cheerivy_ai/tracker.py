"""
B3 — Object detection on the flat (warped) arena image.

  Carriage : red tape stuck on TOP of the AI carriage, searched only near the AI baseline.
  Ball     : solid black, round, sensible size — searched only INSIDE the arena walls,
             with the AI carriage's footprint hidden (its servo/motor are black too).

Returns positions in CENTIMETRES. Click on the red tape in the main window
to re-sample its exact colour under your lighting.
"""
import cv2
import numpy as np

import config as C


class Tracker:
    def __init__(self, arena):
        self.arena = arena
        self.red_ranges = [((0, 90, 70), (10, 255, 255)), ((165, 90, 70), (180, 255, 255))]
        self.last_ball = None
        self.ball_mask = self.red_mask = None
        self.carriage_box = None
        self._field = None

    def field_mask(self, shape):
        """White inside the walls (shrunk a little), black outside — hides wires, rods, table."""
        if self._field is None or self._field.shape != shape:
            s = C.PX_PER_CM
            m = np.zeros(shape, np.uint8)
            cv2.fillPoly(m, [np.int32([(x * s, y * s) for x, y in self.arena.poly])], 255)
            k = max(1, int(C.WALL_MASK_MARGIN * s))
            self._field = cv2.erode(m, np.ones((2 * k + 1, 2 * k + 1), np.uint8))
        return self._field

    def sample_red(self, flat_img, x_px, y_px):
        hsv = cv2.cvtColor(flat_img, cv2.COLOR_BGR2HSV)
        patch = hsv[max(0, y_px - 3):y_px + 4, max(0, x_px - 3):x_px + 4].reshape(-1, 3)
        if patch.size == 0:
            return
        h, s, v = (int(c) for c in np.median(patch, axis=0))  # plain ints: OpenCV 5 rejects numpy ints
        if s < 60:
            print(f"[tracker] ignored click: that's not a colour (H={h} S={s} V={v}) — click ON the red tape")
            return
        lo_s, lo_v = max(40, s - 60), max(40, v - 70)
        lo_h, hi_h = h - 10, h + 10
        # Hue wraps around at 180 (red sits on both ends).
        self.red_ranges = [((max(0, lo_h), lo_s, lo_v), (min(180, hi_h), 255, 255))]
        if lo_h < 0:
            self.red_ranges.append(((180 + lo_h, lo_s, lo_v), (180, 255, 255)))
        if hi_h > 180:
            self.red_ranges.append(((0, lo_s, lo_v), (hi_h - 180, 255, 255)))
        print(f"[tracker] carriage colour sampled: H={h} S={s} V={v}")

    def find_carriage(self, hsv):
        s = C.PX_PER_CM
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in self.red_ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        # The carriage can only be on its rail: between the baseline walls, near the AI end.
        # (Everything else — e.g. a brown/maroon table — must not count as "red".)
        mask[int(C.CARRIAGE_BAND_CM * s):, :] = 0
        mask[:, :int(C.X0 * s)] = 0
        mask[:, int((C.X0 + C.BASE_W) * s):] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        self.red_mask = mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self.carriage_box = None
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) / (s * s) < C.CARRIAGE_MIN_AREA_CM2:
            return None
        self.carriage_box = cv2.boundingRect(c)
        m = cv2.moments(c)
        return m["m10"] / m["m00"] / s

    def find_ball(self, hsv, carriage_x):
        s = C.PX_PER_CM
        mask = cv2.inRange(hsv, (0, 0, 0), (180, 255, C.BALL_MAX_V))
        mask &= self.field_mask(mask.shape)
        if carriage_x is not None:
            half = C.CARRIAGE_W / 2 + C.CARRIAGE_MASK_MARGIN
            cv2.rectangle(mask, (int((carriage_x - half) * s), 0),
                          (int((carriage_x + half) * s), int((C.CARRIAGE_DEPTH - 0.5) * s)), 0, -1)
        if self.carriage_box is not None:  # wherever the tape appears, the carriage is there too
            x, y, w, h = self.carriage_box
            g = int(C.CARRIAGE_MASK_MARGIN * s)
            cv2.rectangle(mask, (x - g, 0), (x + w + g, y + h + g), 0, -1)
        # The human's carriage has black parts too; the AI doesn't need the ball there.
        mask[int((C.ARENA_H - C.CARRIAGE_DEPTH + 0.5) * s):, :] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        self.ball_mask = mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_score = None, -1e9
        for c in contours:
            area = cv2.contourArea(c) / (s * s)
            if not C.BALL_MIN_AREA_CM2 <= area <= C.BALL_MAX_AREA_CM2:
                continue
            per = cv2.arcLength(c, True)
            circ = 4 * np.pi * cv2.contourArea(c) / (per * per) if per else 0
            if circ < C.BALL_MIN_CIRCULARITY:
                continue
            (x, y), _ = cv2.minEnclosingCircle(c)
            x, y = x / s, y / s
            score = circ
            if self.last_ball is not None:  # prefer the blob closest to last position
                d = np.hypot(x - self.last_ball[0], y - self.last_ball[1])
                if d > C.BALL_MAX_JUMP_CM:
                    continue
                score -= d / C.BALL_MAX_JUMP_CM
            if score > best_score:
                best, best_score = (x, y), score
        self.last_ball = best
        return best

    def process(self, flat_img):
        hsv = cv2.cvtColor(cv2.GaussianBlur(flat_img, (5, 5), 0), cv2.COLOR_BGR2HSV)
        carriage_x = self.find_carriage(hsv)
        return self.find_ball(hsv, carriage_x), carriage_x
