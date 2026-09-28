"""
B2 — Arena calibration (two steps, one-time, redo with 'c' if the phone moves).

Step 1 — click the 4 inner corners of the two STRAIGHT BASELINE walls:
    first the 2 corners of the wall behind the RED (AI) carriage, any order,
    then the 2 corners of the other end wall, any order.
  These are a real rectangle BASE_W x ARENA_H cm, so every pixel -> centimetres.
  The camera can be at any angle / rotation; the order is sorted out automatically.

Step 2 — click every other wall corner (where the short straight walls meet the
  diagonals, and where the diagonals meet the long side walls), in ANY order.
  Press ENTER. That gives the true octagon shape for the bounce prediction.
  (Press ENTER straight away to use the nominal shape from config.py.)
"""
import json
import os

import cv2
import numpy as np

import config as C
from arena import Arena, default_polygon

ORDER = ["a corner of the wall behind the RED carriage", "the OTHER corner of that wall",
         "a corner of the far end wall (your side)", "the OTHER corner of the far end wall"]
SNAPSHOT = "snapshot.jpg"


def order_corners(base):
    """
    base = [ai, ai, human, human] in any left/right order. Returns them as
    [ai_a, ai_b, human_b, human_a] going clockwise ON SCREEN, which is what the
    homography expects (AI edge on top, x increasing to the right).
    """
    import math
    cx = sum(p[0] for p in base) / 4
    cy = sum(p[1] for p in base) / 4
    ai = {tuple(base[0]), tuple(base[1])}
    ring = sorted(base, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))  # clockwise (y is down)
    for i in range(4):
        if tuple(ring[i]) in ai and tuple(ring[(i + 1) % 4]) in ai:
            return [ring[(i + k) % 4] for k in range(4)]
    return list(base)  # degenerate clicks — keep as given


class Calibration:
    def __init__(self, corners_px, wall_px=()):
        self.corners = np.float32(order_corners([tuple(p) for p in corners_px]))
        self.wall_px = [tuple(map(float, p)) for p in wall_px]
        s = C.PX_PER_CM
        self.out_w, self.out_h = int(C.ARENA_W * s), int(C.ARENA_H * s)
        x0, x1, h = C.X0 * s, (C.X0 + C.BASE_W) * s, C.ARENA_H * s
        dst = np.float32([[x0, 0], [x1, 0], [x1, h], [x0, h]])
        self.M = cv2.getPerspectiveTransform(self.corners, dst)
        self.arena = Arena(self._polygon_cm())

    def _polygon_cm(self):
        if not self.wall_px:
            return default_polygon()
        base = [(C.X0, 0), (C.X0 + C.BASE_W, 0), (C.X0 + C.BASE_W, C.ARENA_H), (C.X0, C.ARENA_H)]
        pts = cv2.perspectiveTransform(np.float32([self.wall_px]), self.M)[0] / C.PX_PER_CM
        return base + [tuple(p) for p in pts]

    def warp(self, frame):
        """Camera frame -> flat top-down arena image (PX_PER_CM pixels per cm)."""
        return cv2.warpPerspective(frame, self.M, (self.out_w, self.out_h))

    def save(self, path=C.CALIB_FILE):
        with open(path, "w") as f:
            json.dump({"corners": self.corners.tolist(), "walls": self.wall_px,
                       "geometry": [C.BASE_W, C.ARENA_H, C.X0]}, f, indent=2)

    @classmethod
    def load(cls, path=C.CALIB_FILE):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            d = json.load(f)
        if d.get("geometry") != [C.BASE_W, C.ARENA_H, C.X0]:
            print("[calib] board size in config.py changed — recalibrating")
            return None
        return cls(d["corners"], d.get("walls", []))


def run_calibration(source, win="CHEERIVY calibrate"):
    base, walls = [], []

    def click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            (base if len(base) < 4 else walls).append((x, y))
            print(f"[calib] click {len(base) + len(walls)} at ({x}, {y})")

    cv2.namedWindow(win)
    first = True
    while True:
        frame, _, _ = source.read()
        for i, p in enumerate(base):
            cv2.circle(frame, p, 7, (0, 255, 0), -1)
            cv2.putText(frame, str(i + 1), (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if len(base) > 1:
            cv2.polylines(frame, [np.int32(base)], len(base) == 4, (0, 255, 0), 2)
        for p in walls:
            cv2.circle(frame, p, 6, (255, 150, 0), -1)
        if len(base) == 4 and walls:
            hull = cv2.convexHull(np.int32(base + walls))
            cv2.polylines(frame, [hull], True, (255, 150, 0), 2)

        if len(base) < 4:
            msg = f"STEP 1: click {ORDER[len(base)]}   (u undo, q cancel)"
        else:
            msg = f"STEP 2: click other wall corners ({len(walls)} so far), ENTER when done   (u undo)"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(frame, msg, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow(win, frame)
        if first:
            # macOS: the mouse callback must be attached AFTER the window has shown an image.
            cv2.setMouseCallback(win, click)
            first = False

        k = cv2.waitKey(1) & 0xFF
        if k == ord("s"):
            cv2.imwrite(SNAPSHOT, source.read()[0])
            print(f"[calib] saved {os.path.abspath(SNAPSHOT)}")
        if k == ord("u"):
            (walls if walls else base).pop() if (walls or base) else None
        elif k == ord("q"):
            cv2.destroyWindow(win)
            return None
        elif k in (13, 10) and len(base) == 4:
            cal = Calibration(base, walls)
            cal.save()
            cv2.destroyWindow(win)
            print(f"[calib] saved to {C.CALIB_FILE} ({len(walls)} wall corners)")
            return cal
