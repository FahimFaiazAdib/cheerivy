"""
Drawing helpers for the live show: nice fonts (Pillow) on OpenCV images.

Text is rendered once into an RGBA "sprite" and cached, then alpha-blended onto
the BGR canvas every frame. That keeps 30 fps animation cheap.
"""
import math
import os
import random
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- palette (BGR)
BG = (24, 16, 14)
PANEL = (44, 32, 28)
WHITE = (245, 245, 245)
DIM = (150, 140, 135)
HUMAN = (255, 190, 40)      # electric blue
AI = (60, 60, 255)          # red (matches the red tape on the AI carriage)
GOLD = (40, 200, 255)
GREEN = (120, 230, 90)
CYAN = (255, 230, 90)
MAGENTA = (220, 80, 240)

# ---------------------------------------------------------------- fonts
_FONT_CANDIDATES = {
    "display": [("/System/Library/Fonts/Supplemental/Futura.ttc", "Condensed ExtraBold"),
                ("/System/Library/Fonts/Supplemental/Impact.ttf", None)],
    "impact": [("/System/Library/Fonts/Supplemental/Impact.ttf", None),
               ("/System/Library/Fonts/Supplemental/Arial Black.ttf", None)],
    "score": [("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", None),
              ("/System/Library/Fonts/Supplemental/Impact.ttf", None)],
    "ui": [("/System/Library/Fonts/Avenir Next.ttc", "Demi Bold"),
           ("/System/Library/Fonts/Helvetica.ttc", None)],
    "ui_light": [("/System/Library/Fonts/Avenir Next.ttc", "Medium"),
                 ("/System/Library/Fonts/Helvetica.ttc", None)],
}


@lru_cache(maxsize=None)
def _font_source(kind):
    """(path, index) of the first installed font for this role, or None."""
    for path, style in _FONT_CANDIDATES[kind]:
        if not os.path.exists(path):
            continue
        if style is None:
            return path, 0
        for i in range(16):
            try:
                f = ImageFont.truetype(path, 20, index=i)
            except OSError:
                break
            if f.getname()[1] == style:
                return path, i
        return path, 0
    return None


@lru_cache(maxsize=256)
def font(kind, size):
    src = _font_source(kind)
    if src:
        return ImageFont.truetype(src[0], size, index=src[1])
    return ImageFont.load_default(size)


# ---------------------------------------------------------------- text sprites
@lru_cache(maxsize=512)
def text_sprite(text, kind="ui", size=32, color=WHITE, glow=None, stroke=0, stroke_color=(0, 0, 0)):
    """RGBA numpy image (BGR order + alpha) of the text, tightly cropped, with optional glow."""
    f = font(kind, size)
    pad = int(size * 0.6) if glow else 4 + stroke
    x0, y0, x1, y1 = f.getbbox(text, stroke_width=stroke)
    w, h = max(1, x1 - x0) + 2 * pad, max(1, y1 - y0) + 2 * pad
    rgb = (color[2], color[1], color[0])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if glow:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((pad - x0, pad - y0), text, font=f, fill=(glow[2], glow[1], glow[0], 255),
                               stroke_width=stroke + max(2, size // 12))
        g = g.filter(ImageFilter.GaussianBlur(size / 6))
        img = Image.alpha_composite(img, g)
    d = ImageDraw.Draw(img)
    d.text((pad - x0, pad - y0), text, font=f, fill=rgb + (255,),
           stroke_width=stroke, stroke_fill=(stroke_color[2], stroke_color[1], stroke_color[0], 255))
    a = np.array(img)
    return np.ascontiguousarray(a[:, :, [2, 1, 0, 3]])


def blend(canvas, sprite, x, y, alpha=1.0, scale=1.0, anchor="tl"):
    """Alpha-blend an RGBA sprite onto canvas. anchor: tl, tc, c, tr, bl, bc, br, l, r."""
    if alpha <= 0.01 or scale <= 0.01:
        return 0, 0
    if abs(scale - 1.0) > 1e-3:
        sprite = cv2.resize(sprite, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    h, w = sprite.shape[:2]
    if anchor in ("tc", "c", "bc"):
        x -= w // 2
    elif anchor in ("tr", "r", "br"):
        x -= w
    if anchor in ("l", "c", "r"):
        y -= h // 2
    elif anchor in ("bl", "bc", "br"):
        y -= h
    x, y = int(x), int(y)
    H, W = canvas.shape[:2]
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    dx1, dy1 = min(W, x + w), min(H, y + h)
    if dx1 <= dx0 or dy1 <= dy0:
        return w, h
    s = sprite[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]
    a = s[:, :, 3:4].astype(np.float32) * (alpha / 255.0)
    roi = canvas[dy0:dy1, dx0:dx1]
    roi[:] = (s[:, :, :3] * a + roi * (1 - a)).astype(np.uint8)
    return w, h


def text(canvas, s, x, y, kind="ui", size=32, color=WHITE, anchor="tl", alpha=1.0, scale=1.0, glow=None, stroke=0):
    return blend(canvas, text_sprite(str(s), kind, size, tuple(color), glow, stroke), x, y, alpha, scale, anchor)


def text_width(s, kind="ui", size=32):
    return text_sprite(str(s), kind, size).shape[1]


# ---------------------------------------------------------------- shapes
def rect(canvas, x0, y0, x1, y1, color, alpha=1.0):
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    H, W = canvas.shape[:2]
    x0, x1 = max(0, x0), min(W, x1)
    y0, y1 = max(0, y0), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    if alpha >= 0.999:
        canvas[y0:y1, x0:x1] = color
    else:
        roi = canvas[y0:y1, x0:x1]
        roi[:] = (roi * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)


def darken(img, k):
    return cv2.convertScaleAbs(img, alpha=k, beta=0)


def fit(img, w, h):
    """Resize to exactly w x h (caller already picked a matching aspect)."""
    return cv2.resize(img, (int(w), int(h)), interpolation=cv2.INTER_AREA)


def vertical_gradient(w, h, top, bottom):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    g = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    return np.repeat(g, w, axis=1).astype(np.uint8)


def glow_circle(canvas, center, r, color, strength=1.0):
    """Soft neon dot."""
    x, y = int(center[0]), int(center[1])
    R = int(r * 3)
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x - R), max(0, y - R), min(W, x + R), min(H, y + R)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / max(r, 1)
    a = (np.clip(1.6 - d * 0.55, 0, 1) ** 2 * 0.8 * strength)[..., None]
    roi = canvas[y0:y1, x0:x1]
    roi[:] = np.clip(roi + np.array(color, np.float32) * a, 0, 255).astype(np.uint8)
    cv2.circle(canvas, (x, y), int(r), color, -1, cv2.LINE_AA)


def dashed_polyline(canvas, pts, color, thickness=2, dash=14, gap=9, phase=0.0):
    """Animated dashed line (phase moves the dashes along the path)."""
    period = dash + gap
    pos = -phase % period
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-6:
            continue
        ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
        t = -pos
        while t < seg:
            a, b = max(t, 0), min(t + dash, seg)
            if b > a:
                cv2.line(canvas, (int(x0 + ux * a), int(y0 + uy * a)), (int(x0 + ux * b), int(y0 + uy * b)),
                         color, thickness, cv2.LINE_AA)
            t += period
        pos = (pos + seg) % period


def reticle(canvas, c, r, color, t):
    """Spinning target marker for the predicted impact point."""
    x, y = int(c[0]), int(c[1])
    cv2.circle(canvas, (x, y), int(r), color, 2, cv2.LINE_AA)
    for k in range(4):
        a = t * 3 + k * math.pi / 2
        p0 = (int(x + math.cos(a) * r * 0.55), int(y + math.sin(a) * r * 0.55))
        p1 = (int(x + math.cos(a) * r * 1.45), int(y + math.sin(a) * r * 1.45))
        cv2.line(canvas, p0, p1, color, 2, cv2.LINE_AA)


# ---------------------------------------------------------------- easing
def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp01(t)
    return 3 * t * t - 2 * t * t * t


def ease_out_back(t, s=1.7):
    t = clamp01(t) - 1
    return 1 + t * t * ((s + 1) * t + s)


def fade(t, t_in, t_out, total):
    """0->1 over t_in, hold, 1->0 over the last t_out seconds of `total`."""
    if t < 0 or t > total:
        return 0.0
    a = clamp01(t / t_in) if t_in else 1.0
    b = clamp01((total - t) / t_out) if t_out else 1.0
    return min(a, b)


# ---------------------------------------------------------------- confetti
class Confetti:
    COLORS = [GOLD, HUMAN, AI, GREEN, MAGENTA, WHITE, CYAN]

    def __init__(self, w, h, n=160, color_bias=None):
        self.w, self.h = w, h
        cols = self.COLORS + ([color_bias] * 6 if color_bias else [])
        self.p = [self._new(random.uniform(-h, 0), cols) for _ in range(n)]
        self.cols = cols

    def _new(self, y, cols):
        return [random.uniform(0, self.w), y, random.uniform(-40, 40), random.uniform(120, 260),
                random.uniform(0, 6.28), random.uniform(-8, 8), random.choice(cols), random.uniform(6, 13)]

    def draw(self, canvas, dt):
        for q in self.p:
            q[0] += q[2] * dt + math.sin(q[4]) * 20 * dt
            q[1] += q[3] * dt
            q[4] += q[5] * dt
            if q[1] > self.h + 20:
                q[:] = self._new(-20, self.cols)
            s = q[7]
            w = abs(math.cos(q[4])) * s + 2
            box = cv2.boxPoints(((q[0], q[1]), (w, s * 0.55), math.degrees(q[4])))
            cv2.fillConvexPoly(canvas, np.int32(box), q[6], cv2.LINE_AA)


def fmt_clock(sec):
    sec = max(0, int(math.ceil(sec)))
    return f"{sec // 60}:{sec % 60:02d}"
