"""
Everything the commentator says in a match (GAMEFLOW.md §5: a guide, not a radio host).
Every line tells the players something: the score, whose restart it is, a rule, the clock, or what
just happened. Each moment has a few versions; the same one is never used twice in a row.

A version is either
  * RECORDED: a list of clips from the F5 voice bank (show/voice_bank), glued together:
        "pay_sv_01"    a clip id from manifest.json
        "@p:erupt"     the name clip of a role (p, v, lead, trail) in that tone (calm / build / erupt)
        "#score"       the score clip, e.g. sc_2_1 "Two, one." (only exists up to 5)
  * WRITTEN: a sentence with {placeholders}. It is spoken from ui/voice/<key>.wav once rendered in the
    same voice; until then the laptop's own voice reads it (simulator) and it's only used when the
    moment has no recorded version.
Placeholders: {p} who did it, {v} the other side, {a} {b} score, {hi} {lo} higher/lower score,
{lead}/{trail} who leads/trails, {n} a count, {fs} freeze seconds, {mins} match length.
"""
import hashlib
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(os.path.dirname(HERE), "show", "voice_bank")
RENDERED_DIR = os.path.join(HERE, "voice")          # written lines rendered in the F5 voice: <key>.wav
CLIP_GAP_S = 0.14

LINES = {
    # ---- pre-match
    "intro_ai": [["intro_ai_01"], ["kick_ai_02"],
                 "Good evening, and welcome to Cheerivy! Tonight, flesh and blood takes on the machine."],
    "intro_2p": [["intro_pvp_01"], ["kick_pvp_03"],
                 "Welcome to Cheerivy! Two rivals, one table, and only one of them walks away a winner."],
    "intro_aivai": ["Welcome to Cheerivy! Tonight there are no hands on the controls. Machine against machine!"],
    "battle": ["We are about to witness a battle between {p} and {v}!"],
    "rules_clock": [
        "{mins} on the clock. And if it's level at the end, a golden goal will settle it.",
        "We have {mins} on the clock, and should it finish level, the next goal wins it.",
    ],
    "rules_clock_plain": ["{mins} on the clock. Make every second count."],
    "rules_buzz": [
        "And listen for the buzzer! At any moment it will sound, and whoever hits their button first "
        "freezes their opponent for {fs} seconds. Press too early, and nothing happens.",
        "Keep one ear on the buzzer! When it sounds, the first to press their button freezes the other "
        "side for {fs} seconds. So stay sharp!",
    ],
    "kickoff": [
        "{p}, you have the privilege to start. Place the ball just in front of your carriage, "
        "and push your joystick forward when you're ready.",
        "{p}, the honour of the kick-off is yours. Set the ball just in front of your carriage, "
        "and push your joystick forward when you're ready.",
    ],
    # ---- restarts
    "place": [
        "{p}, the restart is yours. Place the ball in front of your carriage, and push your joystick forward when you're ready.",
        "Over to you, {p}. Set the ball in front of your carriage, and push your joystick forward when you're ready.",
    ],
    "place_for_ai": [
        "Player One, kindly place the ball in front of the machine's carriage, and push your joystick forward when you're ready.",
        "Player One, set the ball in front of the machine's carriage for the restart, and push your joystick forward when you're ready.",
    ],
    "kickoff_aivai": [
        "{p} will start. Place the ball just in front of {p}'s carriage, and push either joystick forward when you're ready.",
    ],
    "place_aivai": [
        "Place the ball in front of {p}'s carriage for the restart, and push either joystick forward when you're ready.",
    ],
    "place_any": ["Set the ball back in play, and push your joystick forward when you're ready."],
    "countdown": [["cd_03"], ["cd_02"], ["cd_01"]],          # picked by number
    # ---- goals
    "goal": [["pay_g_02", "@p:erupt"], ["@p:erupt", "pay_g_01"], ["@p:erupt", "pay_g_03"],
             ["pay_g_07", "@p:erupt"], ["@p:erupt", "pay_g_08"], ["pay_g_05", "@p:erupt"],
             "GOAL! {p} finds the net!", "It's in! {p} scores!"],
    "goal_beats_ai": [["pay_gh_ai"], ["pay_g_02", "@p:erupt"], ["@p:erupt", "pay_g_01"], ["pay_g_07", "@p:erupt"],
                      "GOAL! {p} beats the machine!"],
    "goal_ai": [["pay_ga_01"], ["pay_ga_03"], ["pay_ga_04"], ["pay_ga_02"],
                "GOAL! The machine finds the net. Ruthless!"],
    "own_goal": [
        "Oh no! It's rolled all the way back! An own goal by {v}!",
        "It couldn't make the climb, and it's rolled back in! Own goal, {v}!",
    ],
    "own_goal_ai": [
        "The machine has beaten itself! It's rolled back in! An own goal!",
        "It couldn't make the climb! The machine scores against itself!",
    ],
    "golden_winner": ["And it's the golden goal! {p} wins it!", "The golden goal! {p} takes the glory!"],
    # ---- the score, after a goal and at half time (see Commentary.score)
    "sc_first": [["sit_open", "@lead:build", "#score"], "{hi}–{lo}. {lead} draws first blood."],
    "sc_first_h_ai": [["sit_open_h_ai", "#score"]],
    "sc_first_a_ai": [["sit_open_a_ai", "#score"]],
    "sc_nil": [["sc_0_0"], "Still goalless."],
    "sc_level": [["sit_equal_02", "#score"], "All square, {a}–{b}."],
    "sc_lead": [["#score", "@lead:calm", "fill_lead_02"], "{hi}–{lo}, and {lead} edges in front."],
    "sc_lead_h_ai": [["sit_lead_h_ai", "#score"]],
    "sc_lead_a_ai": [["sit_lead_a_ai", "#score"]],
    "sc_big": [["sit_rout", "#score"], "{hi}–{lo}! {lead} is running away with this!"],
    "sc_big_h_ai": [["sit_rout_h_ai", "#score"]],
    # ---- clock
    "clk_half": ["That's half the time gone.", "We're halfway there."],
    "clk_30": ["Only thirty seconds remaining!", ["clk_30b"], ["clk_30a"]],
    "clk_10": ["Only ten seconds remaining!"],
    "clk_count": [["cd_05"], ["cd_04"], ["cd_03"], ["cd_02"], ["cd_01"]],   # picked by number
    "golden": [
        "It's all square at the final whistle! So it's golden goal. The next goal wins it all!",
        "Level when the clock runs out! Golden goal, and whoever scores next takes the match!",
    ],
    # ---- buzzer race
    "buzz_win": [
        "{p} hits the buzzer first! {v} is frozen for {fs} seconds!",
        "{p} is quickest to the buzzer! {v} is frozen, {fs} seconds!",
        "Lightning reactions from {p}! {v} is frozen for {fs} seconds!",
    ],
    "buzz_win_ai": [
        "The machine beats {v} to the buzzer! {v} is frozen for {fs} seconds!",
        "Too quick! The machine takes the buzzer, and {v} is frozen for {fs} seconds!",
    ],
    "buzz_none": ["The buzzer goes unanswered!", "Nobody reacts to the buzzer!"],
    "live_again": ["And they're live again!", "The freeze is over. Back to battle!"],
    # ---- during play: SHORT calls (under ~1.2 s), fired the instant it happens, never queued
    "save": [["pay_sv_01"], ["pay_sv_02"], ["pay_sv_03"], ["pay_sv_05"], "Turned away!"],
    "save_close": [["pay_nm_01"], ["pay_nm_02"], ["pay_sv_04"], "Kept out at the last moment!"],
    "hit_fast": [["fast_03"], ["bld_10"], ["bld_07"], "What a strike!"],
    "hit_fast_ai": [["bld_ai_02"], ["bld_ai_03"]],
    "wall": [["bld_02"], "Off the side!"],
    "rollback": ["It's rolling back!", "It won't make it over!", "Not enough on it! It's coming back!"],
    "danger": [["bld_06"], ["bld_09"], ["bld_08"], ["bld_04"]],
    # ---- during play: guiding lines, only when the AI predicts no goal on the current attack
    "rally_5": [["rally_05"]],
    "rally_8": [["rally_08"]],
    "rally_12": [["rally_12"]],
    "rally_more": [["rally_gen"], "{n} in a row now! Neither side will give an inch."],
    "unbeaten": ["{p} has kept out all {n} shots so far.", "{p} is still unbeaten. {n} saves and counting."],
    "next_nil": [["fill_nil_01"], ["fill_nil_04"], ["fill_nil_03"],
                 "Still goalless. Somebody has to break the deadlock!"],
    "next_level": [["fill_lvl_01"], ["fill_lvl_02"], ["fill_lvl_03"],
                   "Level at {a}–{b}. The next goal puts someone in front."],
    "next_lead": [["@lead:calm", "fill_lead_02"], ["@lead:calm", "fill_lead_01"],
                  "One more goal and {lead} is two clear.", "{trail} is only one goal away from levelling it."],
    "next_hlead_ai": [["fill_hlead_01"], ["fill_hlead_02"], ["fill_hlead_03"]],
    "next_alead_ai": [["fill_alead_01"], ["fill_alead_02"]],
    "next_big": [["fill_big_01"], "{trail} needs {n} goals just to draw level."],
    "late_trail": [["fill_late_01"], ["fill_late_02"], "{trail} needs a goal, and time is running out!"],
    "rest": ["The ball has stopped in {p}'s half. Go and get it!",
             "It's come to rest on {p}'s side. Over to you, {p}!"],
    "rest_ai": ["The ball has stopped on the machine's side."],
    "rest_side": ["The ball has stopped on {p}'s side."],
    # ---- full time
    "result": [["ft_over", "@p:calm", "ft_win_pvp_01", "#score"],
               "It's all over! {p} beats {v}, {hi}–{lo}!"],
    "result_h_ai": [["ft_over", "@p:calm", "ft_h_ai_02", "#score"], ["ft_h_ai_01", "#score"],
                    "It's all over! {p} beats the machine, {hi}–{lo}!"],
    "result_ai": [["ft_over", "ft_a_ai_02", "#score"], ["ft_a_ai_01", "#score"], ["ft_over", "ft_a_ai_03", "#score"],
                  "It's all over! The machine triumphs, {hi}–{lo}!"],
    "result_draw_ai": [["ft_draw_ai"], "It's all over, and honours are even at {a}–{b}!"],
    "result_draw_2p": [["ft_draw_pvp"], "It's all over, and honours are even at {a}–{b}!"],
    "outro": [["outro_01"], ["outro_03"], ["outro_02"],
              "What a contest that was! Thank you for joining us at Cheerivy, and until next time, goodnight!"],
    # ---- highlights (captions only, for now)
    "hl_goal": ["{t}. {p} makes it {a}–{b}."],
    "hl_nogoal": ["Not a single goal. Two defences that simply would not break!"],
    "hl_end": ["And that's the story of the match."],
}

WORDS = ("nil", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
         "nineteen", "twenty")
MINUTES = {60: "one minute", 120: "two minutes", 180: "three minutes", 300: "five minutes"}
NAME_SLUG = {"Player One": "player-one", "Player Two": "player-two", "the machine": "the-machine",
             "the challenger": "the-challenger"}


def W(n):
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def cap(s):
    return s[:1].upper() + s[1:]


# tone of the F5 reference each written moment is rendered with (ui/render_lines.py)
TONE = {"own_goal": "erupt", "own_goal_ai": "erupt", "rollback": "build", "goal": "erupt", "goal_beats_ai": "erupt", "goal_ai": "erupt", "golden_winner": "erupt", "golden": "erupt",
        "buzz_win": "erupt", "buzz_win_ai": "erupt", "battle": "build", "clk_30": "build", "clk_10": "build",
        "save": "build", "save_close": "build", "hit_fast": "build", "wall": "build", "rally_more": "build",
        "late_trail": "build", "live_again": "build", "buzz_none": "build", "rules_buzz": "build"}   # else calm


def written_key(moment, i, text):
    """Rendered file name of a written line: the moment, the version and the exact words."""
    return f"{moment}_{i + 1:02d}_{hashlib.sha1(text.encode()).hexdigest()[:6]}"


class Bank:
    """The recorded clips (show/voice_bank) and the rendered written lines (ui/voice)."""

    def __init__(self):
        self.clips, self.names = {}, {}
        self._rendered = None       # ui/voice/index.json, read when first needed
        try:
            with open(os.path.join(BANK_DIR, "manifest.json")) as f:
                for c in json.load(f)["clips"]:
                    path = os.path.join(BANK_DIR, c["file"])
                    if os.path.exists(path):
                        text = re.sub(r"\s*/+\s*", " ", c["text"]).strip()
                        self.clips[c["id"]] = (path, text, c["duration_ms"] / 1000.0)
            with open(os.path.join(BANK_DIR, "names", "index.json")) as f:
                for slug, e in json.load(f).items():
                    self.names[slug] = {t: os.path.join(BANK_DIR, p) for t, p in e["files"].items()}
                    self.names[slug]["_text"] = e["name"]
        except (OSError, ValueError, KeyError):
            pass

    def part(self, ref):
        """'rec:<id>' / 'name:<slug>:<tone>' / '<written key>' -> (path or None, seconds or None)."""
        if ref.startswith("rec:"):
            c = self.clips.get(ref[4:])
            return (c[0], c[2]) if c else (None, None)
        if ref.startswith("name:"):
            _, slug, tone = ref.split(":")
            p = self.names.get(slug, {}).get(tone)
            return (p, 0.9) if p and os.path.exists(p) else (None, None)
        p = os.path.join(RENDERED_DIR, ref + ".wav")
        if not os.path.exists(p):
            return None, None
        if self._rendered is None:
            try:
                with open(os.path.join(RENDERED_DIR, "index.json")) as f:
                    self._rendered = json.load(f)
            except (OSError, ValueError):
                self._rendered = {}
        d = self._rendered.get(ref, {}).get("duration_ms")
        return p, (d / 1000.0 if d else None)

    def files(self, key):
        """All files of a line key ('a+b+c'), or None if any part has no sound file yet."""
        out = []
        for ref in key.split("+"):
            p, _ = self.part(ref)
            if not p:
                return None
            out.append(p)
        return out

    def seconds(self, key):
        total = 0.0
        for ref in key.split("+"):
            _, s = self.part(ref)
            if s is None:
                return None
            total += s + CLIP_GAP_S
        return total


class Commentary:
    def __init__(self, bank=None):
        self.bank = bank or Bank()
        self._last = {}

    def _recipe(self, parts, kw):
        """A recorded version -> (key, text), or None if a clip is missing."""
        refs, texts = [], []
        for part in parts:
            if part.startswith("@"):
                role, _, tone = part[1:].partition(":")
                slug = NAME_SLUG.get(kw.get(role))
                n = self.bank.names.get(slug)
                if not n or (tone or "calm") not in n:
                    return None
                refs.append(f"name:{slug}:{tone or 'calm'}")
                texts.append(n["_text"] + ".")
                continue
            cid = f"sc_{kw.get('hi')}_{kw.get('lo')}" if part == "#score" else part
            c = self.bank.clips.get(cid)
            if not c:
                return None
            refs.append(f"rec:{cid}")
            texts.append(c[1])
        return "+".join(refs), " ".join(texts)

    def _written(self, moment, i, text, kw):
        text = text.format(**{k: (W(v) if isinstance(v, int) else v) for k, v in kw.items()})
        text = re.sub(r"([.!?…] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), cap(text))
        return written_key(moment, i, text), text

    def line(self, moment, index=None, **kw):
        """-> (voice key, subtitle text). Recorded versions first; written ones when they are rendered,
        or when the moment has nothing recorded. index picks a fixed version (countdowns)."""
        opts = LINES[moment]
        made = {}
        for i, o in enumerate(opts):
            if isinstance(o, list):
                r = self._recipe(o, kw)
                if r:
                    made[i] = (r, True)
            else:
                k, t = self._written(moment, i, o, kw)
                made[i] = ((k, t), self.bank.part(k)[0] is not None)
        if not made:
            return None                           # only recordings, and none of them fits
        if index is not None and index in made:
            return made[index][0]
        voiced = [i for i, (_, has_sound) in made.items() if has_sound]
        pool = voiced or list(made)
        choices = [i for i in pool if i != self._last.get(moment)] or pool
        i = random.choice(choices)
        self._last[moment] = i
        return made[i][0]

    def score(self, a, b, lead, trail, vs_ai, leader_is_human):
        """The score, after a goal and at half time -> (key, text)."""
        hi, lo = max(a, b), min(a, b)
        kw = dict(a=a, b=b, hi=hi, lo=lo, lead=lead, trail=trail)
        if a == b:
            return self.line("sc_nil" if a == 0 else "sc_level", **kw)
        if a + b == 1:
            m = ("sc_first_h_ai" if leader_is_human else "sc_first_a_ai") if vs_ai else "sc_first"
        elif hi - lo >= 3:
            m = "sc_big_h_ai" if (vs_ai and leader_is_human) else "sc_big"
        elif vs_ai and hi - lo == 1:
            m = "sc_lead_h_ai" if leader_is_human else "sc_lead_a_ai"
        else:
            m = "sc_lead"
        return self.line(m, **kw) or self.line("sc_lead" if hi - lo < 3 else "sc_big", **kw)

    def written_lines(self):
        """Every written version (for rendering them in the F5 voice later): [(key, template)]."""
        return [(f"{m}_{i + 1:02d}", o) for m, opts in LINES.items() for i, o in enumerate(opts) if isinstance(o, str)]
