"""
CHEERIVY game flow (GAMEFLOW.md §3): the laptop decides what happens; the robot, the screen and the
sound follow. No hardware in here: inputs come in as events, outputs go out through hooks.

Events (from the robot, or from the keyboard in the simulator):
    ('dir', p, 'L'|'R'|'U'|'D')   joystick flick of player p (1 or 2)
    ('btn', p)                     button tap (confirm in menus / buzzer race in play)
    ('back', p)                    joystick held down 1 s
    ('pause',)                     both buttons held 3 s
    ('goal', p[, 'own'])           player p scored (p 2 = the AI in VS MACHINE); 'own' = the other side's own goal
    ('home',) ('settings',)        organiser keys
Play events (from play.PlayWatcher, see play()): hit, wall, danger, rollback, rest.

Hooks (all optional, dict of callables):
    say(key, text) -> seconds|None  speak a line (key = voice bank name); returns its length if known
    voice_busy() -> bool            still speaking? (scripts wait for it)
    hush()                          cut the current line (80 ms fade): a goal never waits for a sentence
    crowd(what, value=None)         'roar' 'ooh' 'gasp' 'applause' 'whistle' 'swell', ('tension', 0..1)
    robot(cmd)                      'lock', 'unlock', 'beep 3', 'beep go', 'buzz', 'freeze 2 3', 'mode ai', ...
    lcd(line1, line2)               16x2 text
    setting(key, value)             a setting changed (servo angles, volumes, ...)
    action(key)                     a settings action ('p1_test', 'recalibrate', ...)
"""
import json
import os
import random

from commentary import MINUTES, Commentary

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "settings.json")

LENGTHS = (60, 120, 180, 300)
DIFFICULTIES = ("EASY", "MEDIUM", "HARD")
IDLE_ATTRACT_S = 60       # home untouched this long -> attract loop
RESULT_HOLD_S = 6         # result card stays after the outro
HIGHLIGHT_S = 8           # per goal in the (placeholder) highlights
PRE_COUNT_S = 1.0         # silence before "three"
BUZZ_GAP_S = {"OFTEN": (8, 15), "NORMAL": (12, 25), "RARE": (20, 40)}   # live seconds between buzzes
BUZZ_WINDOW_S = 3.0       # the race is open this long after the beep (first-timers react in ~0.5-1 s)
BUZZ_AI_REACT_S = (0.12, 0.30)   # when the AI takes the buzzer, it presses this fast
BUZZ_SHOW_S = 2.5         # the race result stays on screen
BUZZ_MIN_CLOCK_S = 4      # no buzzer in the last seconds
SHORT_GAP_S = 4.0         # at most one short call ("Saved!") per this many seconds
SAVE_CALL_P = 0.35        # an ordinary save gets a call this often (close saves always)
FAST_SHOT = 60            # cm/s: a "rocket"
WALL_CALL_P = 0.2
DANGER_CALL_P = 0.5
ROLLBACK_CALL_P = 0.6
GAP_QUIET_S = 2.5         # a guiding line only after this much silence
GAP_EVERY_S = 9.0         # and at most one per this many seconds
TOPIC_COOLDOWN_S = 35.0   # the same topic not again within this
RALLY_CALLS = {5: "rally_5", 8: "rally_8", 12: "rally_12"}   # then 17, 22, ...: rally_more
MATCH_SCREENS = ("prematch", "ready", "countdown", "live", "goal")

# (group, key, label, choices (None = action), default)
SETTINGS = [
    ("Sound", "voice_vol", "Commentary volume", tuple(range(11)), 8),
    ("Sound", "crowd_vol", "Crowd volume", tuple(range(11)), 5),
    ("Sound", "commentary", "Commentary", (True, False), True),
    ("Sound", "sound_test", "Output test", None, None),
    ("Gameplay", "length_s", "Default match length", LENGTHS, 180),
    ("Gameplay", "golden", "Golden goal", (True, False), True),
    ("Gameplay", "freeze", "Buzzer freeze", (True, False), True),
    ("Gameplay", "buzz_gap", "Buzzer how often", ("OFTEN", "NORMAL", "RARE"), "NORMAL"),
    ("Gameplay", "freeze_s", "Freeze length (s)", (2, 3, 4, 5), 3),
    ("Gameplay", "ai_buzz", "AI wins the buzzer (%)", tuple(range(0, 101, 10)), 60),
    ("Gameplay", "difficulty", "Default AI difficulty", DIFFICULTIES, "MEDIUM"),
    ("Servo tuning", "p1_rest", "P1 rest angle", tuple(range(40, 141)), 97),
    ("Servo tuning", "p1_swing", "P1 swing", tuple(range(10, 91)), 41),
    ("Servo tuning", "p1_test", "P1 test strike", None, None),
    ("Servo tuning", "p2_rest", "P2 rest angle", tuple(range(40, 141)), 87),
    ("Servo tuning", "p2_swing", "P2 swing", tuple(range(10, 91)), 67),
    ("Servo tuning", "p2_test", "P2 test strike", None, None),
    ("Camera & AI", "recalibrate", "Recalibrate board", None, None),
    ("Camera & AI", "reteach", "Re-teach colours", None, None),
    ("Camera & AI", "swap_lr", "Swap L/R (AI carriage)", (True, False), True),
    ("Camera & AI", "swap_lr_p1", "Swap L/R (player 1, AI vs AI)", (False, True), False),
    ("Camera & AI", "debug", "AI debug overlay", (False, True), False),
    ("Debug", "motor_test", "Motor & striker test", None, None),
]
DEBUG_MOVE_S = 0.3        # debug: one key press drives a carriage this long
SPEC = {s[1]: s for s in SETTINGS}
GROUPS = list(dict.fromkeys(s[0] for s in SETTINGS))

WORDS = ("nil", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def W(n):
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def cap(s):
    return s[:1].upper() + s[1:]


def mmss(s):
    s = max(0, int(s + 0.999))
    return f"{s // 60}:{s % 60:02d}"


def estimate(text):
    return 0.5 + len(text) / 15.0 if text else 0.0


class Flow:
    def __init__(self, hooks=None, sim=False):
        self.hooks = hooks or {}
        self.sim = sim
        self.settings = self._load()
        self.log = []
        self.quiet_from = 0.0
        self.cm = Commentary()
        self.now = self.t0 = 0.0
        self.last_input = 0.0
        self.lcd_lines = ("", "")
        self.mode = None
        self.difficulty = self.settings["difficulty"]
        self.length_s = self.settings["length_s"]
        self._reset_match()
        self._home(0.0)

    # ---------------------------------------------------------------- settings
    def _load(self):
        s = {k: d for _, k, _, ch, d in SETTINGS if ch is not None}
        try:
            with open(SETTINGS_FILE) as f:
                saved = json.load(f)
            s.update({k: v for k, v in saved.items() if k in s and v in SPEC[k][3]})
        except (OSError, ValueError):
            pass
        return s

    def _save(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=1)
        except OSError:
            pass

    # ---------------------------------------------------------------- hooks
    def _hook(self, name, *a):
        f = self.hooks.get(name)
        if name != "say":
            self._log(f"{name}: {' '.join(str(x) for x in a)}")
        return f(*a) if f else None

    def _robot(self, cmd):
        self._hook("robot", cmd)

    def _log(self, msg):
        self.log.append(f"{self.now - self.t0:7.1f}  {msg}")
        del self.log[:-12]

    def _say(self, key, text):
        """Speak (if commentary is on) and show the subtitle. Returns the line's length in seconds."""
        n = None
        if self.settings["commentary"] and key:
            n = self._hook("say", key, text)
        d = n or estimate(text)
        if text:
            self.caption, self.caption_until = text, self.now + d + 0.5
        self.quiet_from = max(self.quiet_from, self.now + d + GAP_QUIET_S)
        return d

    def _crowd(self, what, value=None):
        f = self.hooks.get("crowd")
        if f:
            f(what, value)

    def _quiet(self):
        """Nothing is being said, and nothing has been for a moment."""
        return not self._busy() and self.now >= self.quiet_from

    def _L(self, moment, **kw):
        """A script step that speaks one commentary line (see commentary.py)."""
        key, text = self.cm.line(moment, **kw)
        return (text, key, None)

    def _speak(self, moment, index=None, **kw):
        key, text = self.cm.line(moment, index, **kw)
        self._say(key, text)

    def _busy(self):
        f = self.hooks.get("voice_busy")
        return bool(f and f())

    # ---------------------------------------------------------------- names
    # AI vs AI: the camera AI drives both carriages (blue tape on player 1's): Machine One / Machine Two
    def name(self, p):
        if self.mode == "aivai":
            return "MACHINE ONE" if p == 1 else "MACHINE TWO"
        if p == 1:
            return "PLAYER ONE"
        return "CHEERIVY AI" if self.mode == "ai" else "PLAYER TWO"

    def spoken(self, p):
        if self.mode == "aivai":
            return "Machine One" if p == 1 else "Machine Two"
        if p == 1:
            return "Player One"
        return "the machine" if self.mode == "ai" else "Player Two"

    def tag(self, p):
        if self.mode == "aivai":
            return f"M{p}"
        if p == 1:
            return "P1"
        return "AI" if self.mode == "ai" else "P2"

    def machine(self, p):
        """Is side p played by the AI?"""
        return (p == 2 and self.mode == "ai") or self.mode == "aivai"

    # ---------------------------------------------------------------- scripts
    def _run(self, steps, then=None):
        """steps: (text, voice_key, seconds or None = as long as the line, optional fn(now))."""
        self.script, self.then = list(steps), then
        self._step()

    def _stop_script(self):
        self.script, self.then = None, None

    def _step(self):
        if not self.script:
            then = self.then
            self._stop_script()
            if then:
                then()
            return
        text, key, dur, *fn = self.script.pop(0)
        if fn:
            fn[0]()
        if key and key.startswith("sfx:"):
            self._crowd(key[4:])
            d = 0.0
        else:
            d = self._say(key, text) if (text or key) else 0.0
        self.step_end = self.now + (dur if dur is not None else d)

    # ---------------------------------------------------------------- menus
    def _menu(self, screen, title, items, cursor=0):
        self._stop_script()
        self.screen, self.since = screen, self.now
        self.menu = {"title": title, "items": items, "cursor": cursor}

    def _home(self, now):
        if getattr(self, "screen", None) == "debug":
            self._robot("debug off")
        self._stop_script()
        self.last_input = self.now
        self.running = False
        self._robot("lock")
        self._menu("home", "CHEERIVY", [
            {"id": "ai", "label": "VS MACHINE"},
            {"id": "2p", "label": "2 PLAYERS"},
            {"id": "aivai", "label": "AI VS AI"},
            {"id": "settings", "label": "SETTINGS"}])

    def _difficulty(self, mode="ai"):
        self.mode = mode
        items = [{"id": d, "label": d} for d in DIFFICULTIES] + [{"id": "back", "label": "BACK"}]
        self._menu("difficulty", "DIFFICULTY", items, DIFFICULTIES.index(self.difficulty))

    def _join(self):
        self.mode = "2p"
        self._stop_script()
        self._enter("join")        # only player two's button counts here; hold down = back

    def _length(self):
        items = [{"id": s, "label": mmss(s)} for s in LENGTHS] + [{"id": "back", "label": "BACK"}]
        d = self.settings["length_s"]
        self._menu("length", "MATCH LENGTH", items, LENGTHS.index(d) if d in LENGTHS else 2)

    def _settings_groups(self, cursor=0):
        items = [{"id": g, "label": g.upper()} for g in GROUPS] + [{"id": "back", "label": "BACK"}]
        self._menu("settings", "SETTINGS", items, cursor)
        self.menu["group"] = None

    def _settings_items(self, group, cursor=0):
        items = []
        for g, k, label, ch, _ in SETTINGS:
            if g == group:
                it = {"id": k, "label": label}
                if ch is not None:
                    v = self.settings[k]
                    it["value"] = ("ON" if v else "OFF") if isinstance(v, bool) else \
                        (mmss(v) if k == "length_s" else str(v))
                items.append(it)
        items.append({"id": "back", "label": "BACK"})
        self._menu("settings", group.upper(), items, cursor)
        self.menu["group"] = group

    def _change_setting(self, key, step):
        ch = SPEC[key][3]
        i = ch.index(self.settings[key])
        i = max(0, min(len(ch) - 1, i + step)) if len(ch) > 11 else (i + step) % len(ch)
        self.settings[key] = ch[i]
        self._save()
        self._hook("setting", key, ch[i])
        self._settings_items(self.menu["group"], self.menu["cursor"])

    def _choose(self, item, p):
        s, i = self.screen, item["id"]
        if i == "back":
            return self._back()
        if s == "home":
            if i == "ai":
                return self._difficulty()
            if i == "2p":
                return self._join()
            if i == "aivai":
                return self._difficulty("aivai")
            return self._settings_groups()
        if s == "difficulty":
            self.difficulty = i
            return self._length()
        if s == "length":
            self.length_s = i
            return self._prematch()
        if s == "settings":
            if self.menu.get("group") is None:
                return self._settings_items(i)
            if i == "motor_test":
                return self._debug()
            if SPEC[i][3] is None:
                return self._hook("action", i)
            return self._change_setting(i, +1)
        if s == "pause":
            if i == "resume":
                return self._resume()
            if i == "restart":
                return self._prematch()
            return self._home(self.now)

    def _back(self):
        s = self.screen
        if s in ("difficulty", "join"):
            return self._home(self.now)
        if s == "length":
            return self._join() if self.mode == "2p" else self._difficulty(self.mode)
        if s == "settings":
            if self.menu.get("group") is not None:
                return self._settings_groups(GROUPS.index(self.menu["group"]))
            return self._home(self.now)
        if s == "pause":
            return self._resume()
        if s == "debug":
            self._robot("debug off")
            return self._settings_items("Debug")

    # ---------------------------------------------------------------- debug
    # Motor & striker test (Settings > Debug), with the camera view on screen:
    #   the joysticks drive their carriage + striker directly on the robot (firmware game 4);
    #   the keyboard too: player 1 W A S D, the AI side arrows (one press = a short move).
    def _debug(self):
        self._stop_script()
        self._enter("debug")
        self.debug_last = {1: "—", 2: "—"}
        self._robot("debug on")

    def _debug_input(self, kind, a):
        if kind == "back":
            return self._back()
        p = a[0]
        if kind == "dbg":                     # the robot moved it itself: just show it
            self.debug_last[p] = {"L": "LEFT", "R": "RIGHT", "U": "STRIKE", "D": "DOWN", "B": "BUTTON"}.get(a[1], a[1])
            return
        if kind == "dir":
            d = a[1]
            if d in "LR":
                self._robot(f"test {p} {d} {DEBUG_MOVE_S}")
                self.debug_last[p] = "LEFT" if d == "L" else "RIGHT"
            elif d == "U":
                self._robot(f"test {p} F")
                self.debug_last[p] = "STRIKE"
            else:
                self._robot(f"test {p} S")
                self.debug_last[p] = "STOP"
        elif kind == "btn":
            self._robot(f"test {p} F")
            self.debug_last[p] = "STRIKE"

    # ---------------------------------------------------------------- match
    def _reset_match(self):
        self.score = [0, 0]
        self.goals = []
        self.clock = float(self.length_s)
        self.running = False
        self.golden = False
        self.kicked_off = False
        self.kicker = self.placer = None
        self.count = None
        self.cd_start = None
        self.go_until = 0.0
        self.flash = None
        self.called = set()
        self.frozen = {1: 0.0, 2: 0.0}      # frozen until
        self.live_again_at = None
        self.live_t = 0.0                   # seconds of live play (the buzzer clock)
        self.buzz = None                    # open race: {"at": opened, "ai_at": AI press time or None}
        self.buzz_result = None             # {"winner", "victim", "until"} for the screen
        self.next_buzz = self._buzz_gap()
        self._reset_play()
        self.result = None
        self.hl_index = None
        self.menu = None
        self.caption, self.caption_until = "", 0.0
        self.script, self.then, self.step_end = None, None, 0.0

    def _enter(self, screen):
        self.menu = None
        self.screen, self.since = screen, self.now

    def _prematch(self):
        self._reset_match()
        self._enter("prematch")
        self._robot("lock")
        self._robot(f"mode {self.mode} {self.difficulty if self.mode != '2p' else ''}".strip())
        mins = MINUTES.get(self.length_s, f"{self.length_s // 60} minutes")
        steps = [(None, "sfx:swell", 3.0),
                 self._L({"ai": "intro_ai", "aivai": "intro_aivai"}.get(self.mode, "intro_2p")),
                 self._L("battle_aivai" if self.mode == "aivai" else "battle", p=self.spoken(1), v=self.spoken(2)),
                 self._L("rules_clock" if self.settings["golden"] else "rules_clock_plain", mins=mins)]
        if self.settings["freeze"]:                 # the buzzer rule, once, before kick-off
            steps.append(self._L("rules_buzz_aivai" if self.mode == "aivai" else "rules_buzz",
                                 fs=self.settings["freeze_s"]))
        self._run(steps, lambda: self._restart_for(1, kickoff=True))

    def _restart_for(self, c, kickoff=False):
        """Player c places the ball (the one who conceded). In VS MACHINE player one places it for the AI."""
        if self.mode == "aivai":             # nobody at the controls: someone places the ball,
            step = self._L("kickoff_aivai" if kickoff else "place_aivai", p=self.spoken(c))  # either stick starts
        elif kickoff:
            step = self._L("kickoff", p=self.spoken(1))
        elif self.mode == "ai" and c == 2:
            step = self._L("place_for_ai")
        else:
            step = self._L("place", p=self.spoken(c))
        self._enter("ready")
        self.kicker = "any" if self.mode == "aivai" else 1 if self.mode == "ai" else c
        self.placer = c
        self._run([step])

    def _resume(self):
        if self.kicked_off:
            self._enter("ready")
            self.kicker = self.placer = "any"
            self._run([self._L("place_any")])
        else:
            self._restart_for(1, kickoff=True)

    def _countdown(self):
        self._stop_script()
        self._enter("countdown")
        self.cd_start, self.count = self.now, None
        self.caption_until = 0.0

    def _go(self):
        self._enter("live")
        self.count, self.cd_start = None, None
        self.go_until = self.now + 1.0
        self.kicked_off, self.kicker = True, None
        self.running = True
        self.caption_until = 0.0
        self._robot("beep go")
        self._robot("unlock")

    def _score_line(self):
        """-> (voice key, text) for the current score."""
        a, b = self.score
        lead = 1 if a > b else 2
        return self.cm.score(a, b, self.spoken(lead), self.spoken(3 - lead), self.mode == "ai", lead == 1)

    def _goal(self, p, own=False):
        if self.screen != "live":
            return
        self.running = False
        self._robot("lock")
        self.score[p - 1] += 1
        self.goals.append({"scorer": p, "score": list(self.score), "golden": self.golden, "own": own,
                           "at": round(self.length_s - self.clock, 1)})
        self.frozen = {1: 0.0, 2: 0.0}
        self.live_again_at = None
        self.buzz = self.buzz_result = None
        self._hook("hush")                  # whatever was being said stops now: the goal comes first
        self._crowd("tension", 0.0)
        self.rally = self.rally_said = 0
        self.danger = False
        self.conceded[3 - p] += 1
        self._enter("goal")
        self.flash = p
        if self.golden:
            return self._run([(None, "sfx:roar", 0.5), self._L("golden_winner", p=self.spoken(p))],
                             self._full_time)
        if own:                             # it rolled back down the tilt into the striker's own goal
            call = (self._L("own_goal_ai") if (self.mode == "ai" and p == 1)
                    else self._L("own_goal", v=self.spoken(3 - p), p=self.spoken(p)))
        elif self.mode == "ai":
            call = self._L("goal_ai") if p == 2 else self._L("goal_beats_ai", p=self.spoken(p))
        else:
            call = self._L("goal", p=self.spoken(p))
        key, text = self._score_line()
        self._run([(None, "sfx:roar", 0.5), call, (text, key, None)], lambda: self._restart_for(3 - p))

    # Buzzer race: at a random moment the buzzer beeps; whoever presses first freezes the other.
    # Pressing with no buzzer does nothing. In VS MACHINE the AI takes the race ai_buzz % of the time
    # (it then presses within BUZZ_AI_REACT_S, faster than a person reacts); otherwise it doesn't press.
    def _buzz_gap(self):
        return self.live_t + random.uniform(*BUZZ_GAP_S[self.settings["buzz_gap"]])

    def _buzz_open(self):
        ai_at, ai_p = None, 2
        if self.mode == "ai" and random.random() * 100 < self.settings["ai_buzz"]:
            ai_at = self.now + random.uniform(*BUZZ_AI_REACT_S)
        elif self.mode == "aivai":                    # two machines: the quicker one this time
            ai_at, ai_p = self.now + random.uniform(*BUZZ_AI_REACT_S), random.choice((1, 2))
        self.buzz = {"at": self.now, "ai_at": ai_at, "ai_p": ai_p}
        self._robot("buzz")

    def _buzz_close(self):
        self.buzz = None
        self.next_buzz = self._buzz_gap()

    def _buzz_press(self, p, by_ai=False):
        if not self.buzz or (self.machine(p) and not by_ai):
            return                      # no buzzer running (early press) / a machine's side: only the AI presses
        self._buzz_close()
        fs, victim = self.settings["freeze_s"], 3 - p
        self.frozen[victim] = self.now + fs
        self.live_again_at = self.now + fs
        self.next_buzz = max(self.next_buzz, self.live_t + fs)
        self.buzz_result = {"winner": p, "victim": victim, "until": self.now + BUZZ_SHOW_S}
        self._robot(f"freeze {victim} {fs}")
        self._hook("hush")                  # the race result is news: it cuts any short call
        if self.mode == "ai" and p == 2:
            self._speak("buzz_win_ai", v=self.spoken(victim), fs=fs)
        else:
            self._speak("buzz_win", p=self.spoken(p), v=self.spoken(victim), fs=fs)

    def _buzz_tick(self, dt):
        if not self.settings["freeze"]:
            return
        self.live_t += dt
        b = self.buzz
        if b:
            if b["ai_at"] is not None and self.now >= b["ai_at"]:
                self._buzz_press(b["ai_p"], by_ai=True)
            elif self.now - b["at"] >= BUZZ_WINDOW_S:
                self._buzz_close()
                self.buzz_result = {"winner": None, "victim": None, "until": self.now + BUZZ_SHOW_S}
                self._speak("buzz_none")
        elif (self.live_t >= self.next_buzz and self.now >= max(self.frozen.values())
              and (self.golden or self.clock > BUZZ_MIN_CLOCK_S)):
            self._buzz_open()

    # ---------------------------------------------------------------- play commentary
    # During play the crowd carries the atmosphere; the commentator only
    #   * fires SHORT calls (under ~1 s) the instant something happens, never queued behind anything,
    #   * says a longer, guiding line only in a quiet moment when the AI sees no goal coming.
    # A goal always cuts in (hush), so nothing ever makes the goal call late.
    def _reset_play(self):
        self.rally = self.rally_said = 0
        self.saves = {1: 0, 2: 0}
        self.conceded = {1: 0, 2: 0}
        self.danger = False
        self.last_short = self.last_gap = -99.0
        self.topic_at = {}

    def play(self, ev):
        """A play event from play.PlayWatcher (only counts while the ball is live)."""
        if self.screen != "live" or not self.running:
            return
        kind, *a = ev
        if kind == "hit":
            p, info = a
            self.rally += 1
            self.saves[p] += 1
            if self.danger or info.get("close"):
                self._crowd("ooh")
            self.danger = False
            self._crowd("tension", 0.0)
            if self.rally in (6, 10, 15, 20):
                self._crowd("applause")
            if info.get("close"):
                self._short("save_close", 1.0)
            elif info.get("speed", 0) >= FAST_SHOT:
                self._short("hit_fast_ai" if (self.mode == "ai" and p == 2) else "hit_fast", 0.7)
            else:
                self._short("save", SAVE_CALL_P)
        elif kind == "wall":
            self._short("wall", WALL_CALL_P)
        elif kind == "rollback":
            self._crowd("ooh")
            self._short("rollback", ROLLBACK_CALL_P)
        elif kind == "danger":
            self.danger = True
            self._crowd("tension", 1.0)
            self._short("danger", DANGER_CALL_P)
        elif kind == "rest":
            p = a[0]
            if not self._busy():
                if self.mode == "ai" and p == 2:
                    self._speak("rest_ai")
                elif self.mode == "aivai":
                    self._speak("rest_side", p=self.spoken(p))
                else:
                    self._speak("rest", p=self.spoken(p))

    def _short(self, moment, chance):
        """A short call, only if nothing is being said (never queued) and not too often."""
        if (self.now - self.last_short < SHORT_GAP_S or self._busy() or random.random() > chance
                or self.now - self.go_until < 1.0):
            return
        self.last_short = self.now
        key, text = self.cm.line(moment)
        n = self._hook("say", key, text) if self.settings["commentary"] else None
        self.caption, self.caption_until = text, self.now + (n or estimate(text)) + 0.5

    def _gap_line(self):
        """One guiding line, when it's quiet and the AI predicts no goal on this attack."""
        if (self.danger or not self._quiet() or self.now - self.last_gap < GAP_EVERY_S
                or self.now < self.go_until + 3.0 or (not self.golden and self.clock < 12)):
            return
        for topic, fn in self._topics():
            if self.now - self.topic_at.get(topic, -99.0) >= TOPIC_COOLDOWN_S and fn():
                self.topic_at[topic] = self.last_gap = self.now
                return

    def _topics(self):
        a, b = self.score
        lead = 1 if a > b else 2
        L, T = self.spoken(lead), self.spoken(3 - lead)

        def rally():
            n = self.rally
            m = RALLY_CALLS.get(n) or ("rally_more" if n >= 17 and n % 5 == 2 else None)
            if not m or n <= self.rally_said:
                return False
            self.rally_said = n
            self._speak(m, n=n)
            return True

        def late():
            if a == b or self.golden or self.clock > 45:
                return False
            self._speak("late_trail", trail=T, lead=L)
            return True

        def unbeaten():
            for p in (1, 2):
                if self.conceded[p] == 0 and self.saves[p] >= 5:
                    self._speak("unbeaten", p=self.spoken(p), n=self.saves[p])
                    return True
            return False

        def situation():
            if a == b:
                self._speak("next_nil" if a == 0 else "next_level", a=a, b=b)
            elif abs(a - b) >= 2:
                self._speak("next_big", lead=L, trail=T, n=abs(a - b))
            elif self.mode == "ai":
                self._speak("next_hlead_ai" if lead == 1 else "next_alead_ai")
            else:
                self._speak("next_lead", lead=L, trail=T)
            return True

        return [("rally", rally), ("late", late), ("unbeaten", unbeaten), ("situation", situation)]

    def _clock_calls(self):
        L, c = self.length_s, self.clock
        calls = []
        if L >= 60:
            calls.append(("half", L / 2, self._half_time_call))
        if L > 60:
            calls.append(("30", 30, lambda: self._speak("clk_30")))
        calls.append(("10", 10, lambda: self._speak("clk_10")))
        for n in (5, 4, 3, 2, 1):
            calls.append((str(n), n, lambda n=n: self._speak("clk_count", 5 - n)))
        for key, at, call in calls:
            if c <= at and key not in self.called:
                self.called.add(key)
                if not (key == "half" and c < 10):     # skip stale calls (resumed past them)
                    call()

    def _half_time_call(self):
        k1, t1 = self.cm.line("clk_half")
        k2, t2 = self._score_line()
        self._say(f"{k1}+{k2}", f"{t1} {t2}")         # two clips, played back to back

    def _time_up(self):
        self.running = False
        self._robot("lock")
        if self.settings["golden"] and self.score[0] == self.score[1]:
            self._enter("goal")
            self.flash = None
            self.golden = True
            self._run([(None, "sfx:whistle", 1.0),
                       self._L("golden")],
                      lambda: self._restart_for(2))
        else:
            self._full_time()

    def _full_time(self):
        self.running = False
        self._robot("lock")
        self._enter("fulltime")
        a, b = self.score
        hi, lo = max(a, b), min(a, b)
        if a == b:
            call = self._L({"ai": "result_draw_ai", "aivai": "result_draw_aivai"}.get(self.mode, "result_draw_2p"), a=a, b=b)
            winner = None
        else:
            winner, loser = (1, 2) if a > b else (2, 1)
            kw = dict(p=self.spoken(winner), v=self.spoken(loser), hi=hi, lo=lo)
            if self.mode == "ai":
                call = self._L("result_ai" if winner == 2 else "result_h_ai", **kw)
            else:
                call = self._L("result", **kw)
        self.result = {"winner": winner, "score": list(self.score), "awards": self._awards(winner)}
        self._run([(None, "sfx:whistle", 1.2), (None, "sfx:applause", 0.0), call, self._L("outro"),
                   (None, None, RESULT_HOLD_S)], self._highlights)

    def _awards(self, winner):
        out = []
        if winner and any(g["score"][winner - 1] < g["score"][2 - winner] for g in self.goals):
            out.append({"title": "COMEBACK", "who": winner})
        if self.goals and self.goals[-1]["golden"]:
            out.append({"title": "GOLDEN GOAL", "who": self.goals[-1]["scorer"]})
        for p in (1, 2):
            if self.score[p - 1] >= 3:
                out.append({"title": "HAT-TRICK", "who": p})
        if winner and self.score[2 - winner] == 0:
            out.append({"title": "CLEAN SHEET", "who": winner})
        return out[:3]

    def _highlights(self):
        self._enter("highlights")
        steps = []
        for i, g in enumerate(self.goals):
            a, b = g["score"]
            _, text = self.cm.line("hl_goal", t="Golden goal" if g["golden"] else mmss(g["at"]),
                                   p=self.spoken(g["scorer"]), a=a, b=b)
            steps.append((text, None, HIGHLIGHT_S, lambda i=i: setattr(self, "hl_index", i)))
        if not steps:
            steps.append((self.cm.line("hl_nogoal")[1], None, 4.0))
        steps.append((self.cm.line("hl_end")[1], None, 3.0, lambda: setattr(self, "hl_index", None)))
        self._run(steps, lambda: self._home(self.now))

    # ---------------------------------------------------------------- input
    def event(self, ev, now):
        self.now, self.last_input = now, now
        kind, *a = ev
        if kind == "home":
            return self._home(now)
        if kind == "settings":
            return self._settings_groups()
        if kind == "pause":
            if self.screen in MATCH_SCREENS:
                self._stop_script()
                self.running = False
                self._robot("lock")
                self.caption_until = 0.0
                return self._menu("pause", "PAUSED", [
                    {"id": "resume", "label": "RESUME"},
                    {"id": "restart", "label": "RESTART MATCH"},
                    {"id": "home", "label": "HOME"}])
            if self.screen in ("highlights", "fulltime"):
                return self._home(now)
            return
        if kind == "goal":
            return self._goal(a[0], own=len(a) > 1 and a[1] == "own")
        if self.screen == "debug":
            return self._debug_input(kind, a)
        if self.screen == "attract":
            return self._home(now)
        if kind == "back":
            return self._back()
        if self.screen == "join":
            if kind == "btn" and a[0] == 2:
                return self._length()
            return
        if self.menu:
            m = self.menu
            if kind == "dir":
                d = a[1]
                if self.screen == "settings" and m.get("group") and d in "LR":
                    k = m["items"][m["cursor"]]["id"]
                    if k in SPEC and SPEC[k][3] is not None:
                        self._change_setting(k, 1 if d == "R" else -1)
                    return
                m["cursor"] = (m["cursor"] + (-1 if d in "LU" else 1)) % len(m["items"])
            elif kind == "btn":
                self._choose(m["items"][m["cursor"]], a[0])
            return
        if kind == "dir" and a[1] == "U":
            # "I'm ready" = push the joystick FORWARD (the button is only for the buzzer, so it never
            # means two things): the placing player starts the 3-2-1
            p = a[0]
            if self.screen == "ready" and (self.kicker == "any" or p == self.kicker):
                return self._countdown()
        if kind == "btn" and self.screen == "live":
            return self._buzz_press(a[0])
        # other joystick moves during play: the robot moves the carriages itself

    # ---------------------------------------------------------------- time
    def tick(self, now):
        if not self.now:                        # first tick: start the clocks here
            self.now = self.last_input = self.since = self.t0 = now
        dt = max(0.0, now - self.now)
        self.now = now
        if self.script is not None and now >= self.step_end and not self._busy():
            self._step()
        if self.screen == "home" and now - self.last_input > IDLE_ATTRACT_S:
            self._enter("attract")
        if self.screen == "countdown":
            el = now - self.cd_start
            if el >= PRE_COUNT_S + 3:
                self._go()
            elif el >= PRE_COUNT_S:
                n = 3 - int(el - PRE_COUNT_S)
                if n != self.count:
                    self.count = n
                    self._robot(f"beep {n}")
                    self._speak("countdown", 3 - n)
        if self.running:
            if not self.golden:
                self.clock = max(0.0, self.clock - dt)
                self._clock_calls()
                if self.clock <= 0:
                    self._time_up()
            self._buzz_tick(dt)
            self._gap_line()
            if self.live_again_at and now >= self.live_again_at:
                self.live_again_at = None
                self._speak("live_again")
        self._update_lcd()

    # ---------------------------------------------------------------- outputs
    def _update_lcd(self):
        s, (a, b) = self.screen, self.score
        t2 = self.tag(2)
        sc = f"{self.tag(1)}  {a} - {b}  {t2}"
        if s in ("home", "attract"):
            l = ("CHEERIVY", "Select mode <>")
        elif s in ("difficulty", "join", "length"):
            l = ({"ai": "VS MACHINE", "aivai": "AI VS AI"}.get(self.mode, "2 PLAYERS"),
                 f"{self.difficulty + '  ' if self.mode != '2p' else ''}{mmss(self.length_s)}")
        elif s == "settings":
            l = ("SETTINGS", self.menu.get("group") or "")
        elif s == "prematch":
            l = (f"P1 vs {t2}  {mmss(self.length_s)}", "Get ready...")
        elif s == "ready":
            who = "P1" if self.kicker == 1 else ("P2" if self.kicker == 2 else "anyone")
            l = (sc, f"Push fwd: {who}")
        elif s == "countdown":
            l = (sc, str(self.count) if self.count else "Get ready...")
        elif s == "live":
            l = (sc, "GOLDEN GOAL" if self.golden else f"{mmss(self.clock)}    LIVE")
        elif s == "goal":
            l = (f"GOAL! {self.tag(self.flash)}" if self.flash else "GOLDEN GOAL", sc)
        elif s == "pause":
            l = ("PAUSED", "Resume  Home")
        elif s == "debug":
            l = ("DEBUG", "Motor test")
        else:
            l = ("FULL TIME", sc)
        l = tuple(x[:16].ljust(16) for x in l)
        if l != self.lcd_lines:
            self.lcd_lines = l
            f = self.hooks.get("lcd")
            if f:
                f(*l)

    def snapshot(self):
        now = self.now
        cd = None
        if self.screen == "countdown":
            cd = self.count
        elif now < self.go_until:
            cd = "GO"
        m = None
        if self.menu:
            m = dict(self.menu)
        return {
            "sim": self.sim,
            "screen": self.screen,
            "mode": self.mode,
            "difficulty": self.difficulty,
            "length_s": self.length_s,
            "names": {"1": self.name(1), "2": self.name(2)},
            "tags": {"1": self.tag(1), "2": self.tag(2)},
            "debug": getattr(self, "debug_last", None) if self.screen == "debug" else None,
            "score": self.score,
            "clock": round(self.clock, 1),
            "running": self.running,
            "golden": self.golden,
            "kicker": self.kicker,
            "placer": self.placer,
            "kicked_off": self.kicked_off,
            "countdown": cd,
            "flash": self.flash if self.screen == "goal" else None,
            "menu": m,
            "caption": self.caption if now < self.caption_until else "",
            "freeze": {str(p): {"frozen": round(max(0.0, self.frozen[p] - now), 1)} for p in (1, 2)},
            "freeze_s": self.settings["freeze_s"],
            "rally": self.rally,
            "freeze_on": self.settings["freeze"],
            "buzz": {"open": self.buzz is not None, "window": BUZZ_WINDOW_S,
                     "left": round(max(0.0, BUZZ_WINDOW_S - (now - self.buzz["at"])), 1) if self.buzz else 0,
                     "result": ({k: self.buzz_result[k] for k in ("winner", "victim")}
                                if self.buzz_result and now < self.buzz_result["until"] else None)},
            "goals": self.goals,
            "result": self.result,
            "highlight": {"index": self.hl_index, "total": len(self.goals)},
            "lcd": list(self.lcd_lines),
            "log": self.log,
        }
