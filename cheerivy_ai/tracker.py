"""
B3 — Object detection on the flat (warped) arena image.

  Carriage : coloured tape/paper on TOP of the AI carriage (config.CARRIAGE_COLOR, e.g. green),
             searched only near the AI baseline.
  Ball     : round, sensible size, config.BALL_COLOR (e.g. orange, or black) — searched only
             INSIDE the arena walls, with the AI carriage's footprint hidden (its wheel is black).

Returns positions in CENTIMETRES. In the top-down view of the main window:
  LEFT-click the carriage tape -> re-sample its exact colour under your lighting
  RIGHT-click the ball         -> re-sample the ball's colour
"""
import cv2
import numpy as np

import config as C


def _hue_ranges(h, s, v, dh):
    """HSV ranges around a sampled colour (hue wraps at 180, so red can need two ranges)."""
    lo_s, lo_v = max(40, s - 60), max(40, v - 70)
    lo_h, hi_h = h - dh, h + dh
    out = [((max(0, lo_h), lo_s, lo_v), (min(180, hi_h), 255, 255))]
    if lo_h < 0:
        out.append(((180 + lo_h, lo_s, lo_v), (180, 255, 255)))
    if hi_h > 180:
        out.append(((0, lo_s, lo_v), (hi_h - 180, 255, 255)))
    return out


def _sample(flat_img, x_px, y_px):
    """Median HSV of a 7x7 patch as plain ints (OpenCV 5 rejects numpy ints), or None."""
    hsv = cv2.cvtColor(flat_img, cv2.COLOR_BGR2HSV)
    patch = hsv[max(0, y_px - 3):y_px + 4, max(0, x_px - 3):x_px + 4].reshape(-1, 3)
    if patch.size == 0:
        return None
    return tuple(int(c) for c in np.median(patch, axis=0))


class Tracker:
    def __init__(self, arena):
        self.arena = arena
        self.carriage_ranges = C.COLORS[C.CARRIAGE_COLOR]
        self.ball_ranges = C.COLORS[C.BALL_COLOR]     # None = black ball (dark pixels)
        self.last_ball = None
        self.ball_mask = self.carriage_mask = None
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

    def sample_carriage(self, flat_img, x_px, y_px):
        hsv = _sample(flat_img, x_px, y_px)
        if hsv is None:
            return
        h, s, v = hsv
        if s < 60:
            print(f"[tracker] ignored click: that's not a colour (H={h} S={s} V={v}) — click ON the carriage tape")
            return
        self.carriage_ranges = _hue_ranges(h, s, v, 10)
        print(f"[tracker] carriage colour sampled: H={h} S={s} V={v}")

    def sample_ball(self, flat_img, x_px, y_px):
        hsv = _sample(flat_img, x_px, y_px)
        if hsv is None:
            return
        h, s, v = hsv
        if v < C.BALL_MAX_V:
            self.ball_ranges = None                       # a dark ball: use "black" mode
            print(f"[tracker] ball colour sampled: black (V={v})")
        elif s < 60:
            print(f"[tracker] ignored click: that's white/grey (H={h} S={s} V={v}) — right-click ON the ball")
        else:
            self.ball_ranges = _hue_ranges(h, s, v, 8)
            print(f"[tracker] ball colour sampled: H={h} S={s} V={v}")

    def _color_mask(self, hsv, ranges):
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        return mask

    def find_carriage(self, hsv):
        s = C.PX_PER_CM
        mask = self._color_mask(hsv, self.carriage_ranges)
        # The carriage can only be on its rail: between the baseline walls, near the AI end.
        # (Everything else — e.g. a brown/maroon table or the ball — must not count.)
        mask[int(C.CARRIAGE_BAND_CM * s):, :] = 0
        mask[:, :int(C.X0 * s)] = 0
        mask[:, int((C.X0 + C.BASE_W) * s):] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        self.carriage_mask = mask
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
        if self.ball_ranges is None:
            mask = cv2.inRange(hsv, (0, 0, 0), (180, 255, C.BALL_MAX_V))
        else:
            mask = self._color_mask(hsv, self.ball_ranges)
        mask &= self.field_mask(mask.shape)
        if carriage_x is not None:
            half = C.CARRIAGE_W / 2 + C.CARRIAGE_MASK_MARGIN
            cv2.rectangle(mask, (int((carriage_x - half) * s), 0),
                          (int((carriage_x + half) * s), int((C.CARRIAGE_DEPTH - 0.5) * s)), 0, -1)
        if self.carriage_box is not None:  # wherever the tape appears, the carriage is there too
            x, y, w, h = self.carriage_box
            g = int(C.CARRIAGE_MASK_MARGIN * s)
            cv2.rectangle(mask, (x - g, 0), (x + w + g, y + h + g), 0, -1)
        # The human's carriage has black parts; the AI doesn't need the ball there.
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
