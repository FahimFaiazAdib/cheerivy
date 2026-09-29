"""
The new browser game, played for real: main.py (camera AI + robot link) runs it through this.

    robot  <- lock / unlock / countdown beeps / buzzer / freezes / game type  (firmware "screen mode")
    robot  -> every joystick flick + button press, laser goals               ("IN 1 U", "G H", ...)
    camera -> the live top-down picture (AI VISION box) + ball / prediction / carriages + play events
    Flow   -> decides everything (menus, clock, goals, commentary); main.py lets the AI play only
              while the Flow says the ball is live.
"""
import os
import sys
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import config as C  # noqa: E402
from flow import Flow  # noqa: E402
from play import PlayWatcher  # noqa: E402
from server import ORGANISER_KEYS, PORT, SIM_KEYS, Hub, serve  # noqa: E402
from sound import Sound  # noqa: E402

GAME_CODE = {"ai": 1, "2p": 2, "aivai": 3}
LEVEL = {"EASY": 1, "MEDIUM": 2, "HARD": 3}
VIDEO_FPS = 15
VIDEO_QUALITY = 70
INPUT = {"L": "L", "R": "R", "U": "U", "D": "D"}


class LiveGame:
    def __init__(self, link, port=PORT, open_browser=True, sound=True):
        self.link = link
        self.flow = Flow(sim=False)
        st = self.flow.settings
        self.sound = Sound(self.flow.cm.bank, st["voice_vol"] / 10, st["crowd_vol"] / 10) if sound else None
        # the keyboard still works (organisers / no joysticks): the same keys as the simulator
        self.hub = Hub(self.flow, {**SIM_KEYS, **ORGANISER_KEYS}, table=None, sound=self.sound)
        self.hub.extra = {"video": True}
        self.watcher = PlayWatcher()
        self.game = 0                    # the robot's game type (0 = menus)
        self.difficulty = 2
        self.locked = True
        self.robot_screen = False        # the robot is in screen mode (it says "SCREEN" every second)
        self.want_recalibrate = False
        self.calib = None                # the page's corner clicks: {"points": [[x, y] x4]} or "cancel"
        self.samples = []                # the page's colour clicks: (what, x, y) on the top-down picture
        self._last_raw = 0.0
        self.hub.posts.update({"/calib": self._calib_post, "/sample": self._sample_post})
        self.debug = False               # Settings > Debug > Motor & striker test is open
        self.manual = {1: ("S", 0.0), 2: ("S", 0.0)}   # debug keyboard moves: (L/R/S, until)
        self._last_video = 0.0
        self.flow.hooks.update(robot=self._robot, setting=self._setting, action=self._action)
        if self.sound and self.sound.ok:
            self.flow.hooks.update(say=self.sound.say, voice_busy=self.sound.voice_busy,
                                   hush=self.sound.hush, crowd=self.sound.crowd)
        serve(self.hub, port, open_browser, label=" (live)")

    # ------------------------------------------------------------ what main.py asks
    @property
    def mode(self):
        return self.flow.mode

    def ai_plays(self):
        """The camera AI moves only while the ball is live (and never in a two-player game)."""
        return self.flow.screen == "live" and self.flow.running and self.flow.mode in ("ai", "aivai")

    def in_play(self):
        return self.flow.screen == "live" and self.flow.running

    # ------------------------------------------------------------ robot -> game
    def on_line(self, line):
        """A line from the robot. Returns True if it was for the game."""
        p = line.split()
        if not p:
            return False
        if p[0] == "READY":                          # the robot is in its old lobby: switch it over
            self.robot_screen = False
            self.link.send(f"C{self.game};")
            return True
        if p[0] == "SCREEN":
            if not self.robot_screen:                # (re)connected: tell it everything again
                self.robot_screen = True
                self.link.send(f"C{self.game};")
                self.link.send("O0;" if self.locked else "O1;")
                print("[live] the robot is in screen mode: the browser game runs it")
            return True
        if p[0] == "IN" and len(p) >= 2:
            if p[1] == "P":
                self.hub.event(("pause",))
            elif len(p) == 3 and p[1] in "12":
                who, what = int(p[1]), p[2]
                if self.flow.screen == "debug" and what in "LRUDB":
                    self.hub.event(("dbg", who, what))   # the robot already moved it: just show it
                elif what in INPUT:
                    self.hub.event(("dir", who, INPUT[what]))
                elif what == "B":
                    self.hub.event(("btn", who))
                elif what == "X":
                    self.hub.event(("back", who))
            return True
        if p[0] == "G" and len(p) >= 2 and p[1] in "HA":
            self.goal(p[1])
            return True
        return False

    def goal(self, who, camera=False):
        """'H' = the human side (player 1) scored, 'A' = the AI side / player 2 scored."""
        scorer = 1 if who == "H" else 2
        own = "own" if self.watcher.last_touch == 3 - scorer else ""
        if camera and self.in_play():               # the lasers beep by themselves; for the camera, ask
            self.link.send("D7;" if scorer == 1 else "D8;")
        self.hub.event(("goal", scorer, own))

    def manual_cmd(self, p, now):
        """Debug: the keyboard's move for carriage p right now ('L' 'R' 'S')."""
        cmd, until = self.manual[p]
        return cmd if now < until else "S"

    # ------------------------------------------------------------ calibration on the page
    def begin_calibration(self):
        """main.py: show the board-corner screen (start-up without a saved calibration)."""
        self.calib = None
        self.hub.event(("calib", "board"))

    def raw(self, frame):
        """The camera picture as filmed, for clicking the corners (10 per second is plenty)."""
        now = time.time()
        if now - self._last_raw >= 0.1:
            self._last_raw = now
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_QUALITY])
            if ok:
                self.hub.set_video(jpg.tobytes(), "raw")

    def take_calibration(self):
        c, self.calib = self.calib, None
        return c

    def end_calibration(self, message=None):
        self.hub.event(("calib_done",))
        if message:
            self.notice(message)

    def take_samples(self):
        s, self.samples = self.samples, []
        return s

    def notice(self, text, seconds=6.0):
        with self.hub.cond:
            self.flow.notice(text, seconds)

    def _calib_post(self, data):
        if data.get("cancel"):
            self.calib = "cancel"
        elif len(data.get("points") or []) == 4:
            self.calib = {"points": [tuple(map(float, p)) for p in data["points"]]}

    def _sample_post(self, data):
        if data.get("what") in ("carriage", "ball"):
            self.samples.append((data["what"], int(data["x"]), int(data["y"])))

    # ------------------------------------------------------------ camera -> game
    def frame(self, stamp, flat, board, slope):
        """Once per camera frame: the picture, and what the AI sees on it."""
        now = time.time()
        if flat is not None and now - self._last_video >= 1.0 / VIDEO_FPS:
            self._last_video = now
            ok, jpg = cv2.imencode(".jpg", flat, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_QUALITY])
            if ok:
                self.hub.set_video(jpg.tobytes())
        events = []
        if self.in_play():
            self.watcher.slope = tuple(slope)
            events = self.watcher.update(stamp, board.get("ball"), board.get("vel"),
                                         {1: board.get("p1_x"), 2: board.get("ai_x")})
        self.hub.feed(board, events)

    # ------------------------------------------------------------ game -> robot
    def _robot(self, cmd):
        a = cmd.split()
        send = self.link.send
        if a[0] == "lock":
            self.locked = True
            send("O0;")
        elif a[0] == "unlock":
            self.locked = False
            self.watcher.reset()
            placer = self.flow.placer
            self.watcher.touch(placer if placer in (1, 2) else None)   # the restart strike
            send("O1;")
        elif a[0] == "beep":
            send("D0;" if a[1] == "go" else f"D{a[1]};")
        elif a[0] == "buzz":
            send("D9;")
        elif a[0] == "freeze":
            send(f"I{a[1]}{a[2]};")
        elif a[0] == "debug":                        # motor & striker test: firmware game 4
            self.debug = a[1] == "on"
            self.manual = {1: ("S", 0.0), 2: ("S", 0.0)}
            if self.debug:
                self.locked = False
                send("C4;")
                send("O1;")
            else:
                self.locked = True
                send("O0;")
                send(f"C{self.game};")
        elif a[0] == "test" and self.debug:          # test <p> L|R <seconds> / F / S
            p = int(a[1])
            if a[2] in "LR":
                self.manual[p] = (a[2], time.time() + float(a[3]))
            elif a[2] == "F":
                send("G" if p == 1 else "F")
            else:
                self.manual[p] = ("S", 0.0)
        elif a[0] == "mode":
            self.game = GAME_CODE.get(a[1], 0)
            if len(a) > 2:
                self.difficulty = LEVEL.get(a[2], 2)
            send(f"C{self.game};")

    def _setting(self, key, value):
        s = self.flow.settings
        if self.sound and key == "voice_vol":
            self.sound.voice_vol = value / 10
        elif self.sound and key == "crowd_vol":
            self.sound.crowd_vol = value / 10
        elif key in ("p1_rest", "p1_swing"):        # player 1's striker: rest angle, strike = rest - swing
            self.link.send(f"H{s['p1_rest']};J{max(0, s['p1_rest'] - s['p1_swing'])};")
        elif key in ("p2_rest", "p2_swing"):
            self.link.send(f"Q{s['p2_rest']};W{max(0, s['p2_rest'] - s['p2_swing'])};")
        elif key == "swap_lr":
            self.link.swap = bool(value)
        elif key == "swap_lr_p1":
            self.link.swap1 = bool(value)
            self.link.current1 = None

    def _action(self, key):
        if key == "p1_test":
            self.link.send("U1;")
        elif key == "p2_test":
            self.link.send("T1;")
        elif key == "recalibrate":
            self.want_recalibrate = True
        elif key == "calib_cancel":
            self.calib = "cancel"
        elif key == "sound_test" and self.sound:
            self.sound.crowd("roar")
