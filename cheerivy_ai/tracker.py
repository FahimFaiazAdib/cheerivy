"""
B3 — Object detection on the flat (warped) arena image.

  Carriage : coloured tape/paper on TOP of the AI carriage (config.CARRIAGE_COLOR, e.g. green),
             searched only near the AI baseline. In AI vs AI also PLAYER 1's carriage
             (config.P1_CARRIAGE_COLOR, blue), searched only near the player 1 baseline.
  Ball     : round, sensible size, config.BALL_COLOR (e.g. orange, or black) — searched only
             INSIDE the arena walls, with the AI carriage's footprint hidden (its wheel is black).

Returns positions in CENTIMETRES. In the top-down view of the main window:
  LEFT-click a carriage tape   -> re-sample its exact colour under your lighting
                                  (top half = AI carriage, bottom half = player 1's carriage)
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



def _said(msg):
    print(f"[tracker] {msg}")
    return msg

class Tracker:
    def __init__(self, arena):
        self.arena = arena
        self.carriage_ranges = C.COLORS[C.CARRIAGE_COLOR]
        self.p1_ranges = C.COLORS[C.P1_CARRIAGE_COLOR]
        self.find_p1 = False          # AI vs AI: look for player 1's carriage as well
        self.p1_box = None
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
        """Learn a carriage's tape colour from a click. Returns what happened (for the screen)."""
        hsv = _sample(flat_img, x_px, y_px)
        if hsv is None:
            return _said("Missed the board. Click on the board picture.")
        h, s, v = hsv
        if s < 60:
            return _said(f"That's not a colour (H={h} S={s} V={v}). Click ON the carriage tape.")
        if y_px > C.ARENA_H / 2 * C.PX_PER_CM:        # the bottom half: player 1's carriage
            self.p1_ranges = _hue_ranges(h, s, v, 10)
            return _said(f"Player 1's carriage colour learned (H={h} S={s} V={v}).")
        self.carriage_ranges = _hue_ranges(h, s, v, 10)
        return _said(f"The AI-side carriage colour learned (H={h} S={s} V={v}).")

    def sample_ball(self, flat_img, x_px, y_px):
        """Learn the ball's colour from a click. Returns what happened (for the screen)."""
        hsv = _sample(flat_img, x_px, y_px)
        if hsv is None:
            return _said("Missed the board. Click on the board picture.")
        h, s, v = hsv
        if v < C.BALL_MAX_V:
            self.ball_ranges = None                       # a dark ball: use "black" mode
            return _said(f"Ball colour learned: black (V={v}).")
        if s < 60:
            return _said(f"That's white or grey (H={h} S={s} V={v}). Right-click ON the ball.")
        self.ball_ranges = _hue_ranges(h, s, v, 8)
        return _said(f"Ball colour learned (H={h} S={s} V={v}).")

    def _color_mask(self, hsv, ranges):
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        return mask

    def find_carriage(self, hsv, player1=False):
        """x (cm) of the AI carriage's tape, or of player 1's with player1=True, or None."""
        s = C.PX_PER_CM
        mask = self._color_mask(hsv, self.p1_ranges if player1 else self.carriage_ranges)
        # The carriage can only be on its rail: between the baseline walls, near its own end.
        # (Everything else — e.g. a brown/maroon table or the ball — must not count.)
        if player1:
            mask[:int((C.ARENA_H - C.CARRIAGE_BAND_CM) * s), :] = 0
        else:
            mask[int(C.CARRIAGE_BAND_CM * s):, :] = 0
        mask[:, :int(C.X0 * s)] = 0
        mask[:, int((C.X0 + C.BASE_W) * s):] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        if not player1:
            self.carriage_mask = mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        box = None
        x = None
        if contours:
            c = max(contours, key=cv2.contourArea)
            if cv2.contourArea(c) / (s * s) >= C.CARRIAGE_MIN_AREA_CM2:
                box = cv2.boundingRect(c)
                m = cv2.moments(c)
                x = m["m10"] / m["m00"] / s
        if player1:
            self.p1_box = box
        else:
            self.carriage_box = box
        return x

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
        # Hide the carriages' tape from the ball detector: only the tape itself (+ a little). Seen
        # from the side, a raised tape looks shifted into the board, right where a slow ball sits in
        # front of the carriage; hiding everything from the tape to the wall hid that ball too.
        g = int(C.TAPE_MASK_MARGIN * s)
        for box in (self.carriage_box, self.p1_box if self.find_p1 else None):
            if box is not None:
                x, y, w, h = box
                cv2.rectangle(mask, (x - g, y - g), (x + w + g, y + h + g), 0, -1)
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
        """-> (ball, AI carriage x, player 1 carriage x). Player 1's is None unless find_p1 is on."""
        hsv = cv2.cvtColor(cv2.GaussianBlur(flat_img, (5, 5), 0), cv2.COLOR_BGR2HSV)
        carriage_x = self.find_carriage(hsv)
        p1_x = self.find_carriage(hsv, player1=True) if self.find_p1 else None
        if not self.find_p1:
            self.p1_box = None
        return self.find_ball(hsv, carriage_x), carriage_x, p1_x
