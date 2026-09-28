"""
Goal clips: a rolling buffer of the last few seconds of the live stage
(camera + AI view, no scoreboard), saved as an .mp4 when a goal is scored.
"""
import os
import threading
import time
from collections import deque

import cv2

PRE_S = 3.0       # seconds kept BEFORE the goal signal
POST_S = 0.8      # keep recording a little after it (the goal signal arrives slightly late)
CLIP_W = 960      # stored width; height follows the stage's aspect


class Clip:
    def __init__(self, path, frames, stamps, goal_t):
        self.path = path
        self.frames = frames        # kept in memory until the highlight reel has been played
        self.stamps = stamps
        self.goal_t = goal_t
        dur = stamps[-1] - stamps[0] if len(stamps) > 1 else 1.0
        self.fps = max(10.0, min(60.0, (len(stamps) - 1) / dur)) if dur > 0 else 30.0
        # index of the frame closest to the goal moment (for slow motion)
        self.goal_index = min(range(len(stamps)), key=lambda i: abs(stamps[i] - goal_t)) if stamps else 0

    def load(self):
        """Frames from disk if they were dropped from memory."""
        if self.frames:
            return self.frames
        cap = cv2.VideoCapture(self.path)
        out = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            out.append(f)
        cap.release()
        return out


class Recorder:
    def __init__(self, folder):
        self.folder = folder
        self.buf = deque()
        self.pending = []           # [goal_t, callback]
        self.lock = threading.Lock()
        self.writing = 0

    def new_match(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        with self.lock:
            self.pending.clear()

    def push(self, stage, t):
        h, w = stage.shape[:2]
        small = cv2.resize(stage, (CLIP_W, int(h * CLIP_W / w) // 2 * 2), interpolation=cv2.INTER_AREA)
        with self.lock:
            self.buf.append((t, small))
            while self.buf and t - self.buf[0][0] > PRE_S + POST_S + 0.5:
                self.buf.popleft()
            ready = [p for p in self.pending if t >= p[0] + POST_S]
            self.pending = [p for p in self.pending if p not in ready]
            snaps = [(p, [(ft, f) for ft, f in self.buf if p[0] - PRE_S <= ft <= p[0] + POST_S]) for p in ready]
        for (goal_t, name, cb), frames in snaps:
            self._save(goal_t, name, frames, cb)

    def mark_goal(self, name, callback, goal_t=None):
        """Ask for a clip around now; callback(Clip) runs once it's saved."""
        with self.lock:
            self.pending.append((goal_t or time.time(), name, callback))

    def _save(self, goal_t, name, frames, cb):
        if len(frames) < 5:
            return
        stamps = [t for t, _ in frames]
        imgs = [f for _, f in frames]
        path = os.path.join(self.folder, name + ".mp4")
        clip = Clip(path, imgs, stamps, goal_t)
        cb(clip)                                   # usable straight away (frames are in memory)
        self.writing += 1

        def write():
            try:
                h, w = imgs[0].shape[:2]
                vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), clip.fps, (w, h))
                for f in imgs:
                    vw.write(f)
                vw.release()
            finally:
                self.writing -= 1
        threading.Thread(target=write, daemon=True).start()
