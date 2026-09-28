"""
The recorded commentary voice bank (show/voice_bank/, rendered with F5-TTS from a team member's
own voice; see VOICE_RENDER_SPEC.md). Picks the right clips for each moment of the match and
returns them as a list of .wav paths to play back to back.

  voice_bank/manifest.json      every clip: id, file, category, mode (all / ai / pvp), tone,
                                name_before (play the player's name in that tone first) ...
  voice_bank/names/index.json   recorded names (fahim, atik, ...), one clip per tone

If the folder is missing, `VoiceBank.ok` is False and the show uses text-to-speech instead.
The folder is NOT on GitHub (voices stay private): copy it to cheerivy_ai/show/voice_bank/.
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "voice_bank")


# Other spellings of names that were recorded (typed name -> recorded name).
ALIASES = {"atiq": "atik", "atique": "atik", "fahim-faiaz": "fahim", "fahim-faiaz-adib": "fahim",
           "tahmid-khan": "tahmid", "atik-khan": "atik", "atiq-khan": "atik"}


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return ALIASES.get(s, s)


class VoiceBank:
    def __init__(self, folder=DEFAULT_DIR):
        self.dir = folder
        self.clips = {}
        self.names = {}
        self._last = {}
        try:
            with open(os.path.join(folder, "manifest.json")) as f:
                for c in json.load(f)["clips"]:
                    if os.path.exists(os.path.join(folder, c["file"])):
                        self.clips[c["id"]] = c
            with open(os.path.join(folder, "names", "index.json")) as f:
                self.names = json.load(f)
        except (OSError, ValueError, KeyError):
            pass
        self.ok = len(self.clips) > 20

    # ------------------------------------------------------------ low level
    def _path(self, rel):
        return os.path.join(self.dir, rel)

    def name_clip(self, name, tone, fallback):
        """The recorded name, or a stand-in ("the challenger", "player one") if it wasn't recorded."""
        for key in (slug(name), fallback):
            entry = self.names.get(key)
            if entry:
                rel = entry["files"].get(tone) or next(iter(entry["files"].values()))
                if os.path.exists(self._path(rel)):
                    return self._path(rel)
        return None

    def _pick(self, prefixes, game):
        """A random clip whose id starts with one of `prefixes` and fits the game; never the same one twice in a row."""
        mode_ok = ("all", "ai") if game == 1 else ("all", "pvp")
        pool = [c for cid, c in self.clips.items()
                if cid.startswith(tuple(prefixes)) and c["mode"] in mode_ok]
        if not pool:
            return None
        key = tuple(prefixes)
        fresh = [c for c in pool if c["id"] != self._last.get(key)] or pool
        c = random.choice(fresh)
        self._last[key] = c["id"]
        return c

    def seq(self, clip, name=None, name_fallback="the-challenger"):
        """Clip -> [name clip (if the line wants one), clip]."""
        if clip is None:
            return []
        out = []
        if clip.get("name_before"):
            n = self.name_clip(name, clip["name_before"], name_fallback)
            if n:
                out.append(n)
        out.append(self._path(clip["file"]))
        return out

    def line(self, prefixes, game, name=None, name_fallback="the-challenger"):
        return self.seq(self._pick(prefixes, game), name, name_fallback)

    def exact(self, cid, name=None, name_fallback="the-challenger"):
        return self.seq(self.clips.get(cid), name, name_fallback)

    # ------------------------------------------------------------ match moments
    def kickoff(self, game, p, ai, fb_p, fb_ai):
        if game == 2:
            return (self.line(["kick_pvp_"], 2) + self.name_seq(p, "calm", fb_p)
                    + self.exact("kick_versus") + self.name_seq(ai, "calm", fb_ai) + self.line(["kick_05", "kick_06"], 2))
        if random.random() < 0.5:
            return self.line(["kick_ai_01", "kick_ai_02", "kick_ai_03"], 1) + self.line(["kick_05", "kick_06"], 1)
        return (self.exact("kick_intro", p, fb_p) + self.exact("kick_ai_04", ai, fb_ai)
                + self.line(["kick_05", "kick_06"], 1))

    def name_seq(self, name, tone, fallback):
        n = self.name_clip(name, tone, fallback)
        return [n] if n else []

    def goal(self, game, who, score, scorer, fb_scorer, clock_left, history):
        """Payoff + situation / tail + the score. `history` = list of (h, a) after each earlier goal."""
        h, a = score
        if game == 1 and who == "A":
            payoff = self.line(["pay_ga_"], 1)
        elif game == 1:
            payoff = self.line(["pay_g_", "pay_gh_ai"], 1, scorer, fb_scorer)
        else:
            payoff = self.line(["pay_g_"], 2, scorer, fb_scorer)

        mine, theirs = (h, a) if who == "H" else (a, h)
        was_two_behind = any((x[1] - x[0] if who == "H" else x[0] - x[1]) >= 2 for x in history)
        if clock_left < 5:
            tail = self.exact("clk_last", scorer, fb_scorer)
        elif h + a == 1:
            ids = ("sit_open_h_ai" if who == "H" else "sit_open_a_ai") if game == 1 else "sit_open"
            tail = self.exact(ids, scorer, fb_scorer)
        elif mine == theirs:
            tail = self.line(["sit_equal_"], game)
        elif mine == theirs + 1 and was_two_behind:
            tail = self.exact("sit_comeback")
        elif mine == theirs + 1:
            if game == 1:
                tail = self.exact("sit_lead_h_ai" if who == "H" else "sit_lead_a_ai")
            else:
                tail = self.exact("sit_lead", scorer, fb_scorer)
        elif mine >= theirs + 3:
            tail = self.exact("sit_rout_h_ai" if (game == 1 and who == "H") else "sit_rout")
        elif mine >= theirs + 2:
            tail = self.exact("sit_extend")
        elif game == 2:
            tail = self.line(["tail_pvp_", "tail_g_"], 2)
        else:
            tail = self.line(["tail_gh_ai_", "tail_g_"] if who == "H" else ["tail_ga_"], 1)
        return payoff, tail + self.score(h, a)

    def score(self, h, a):
        hi, lo = max(h, a), min(h, a)
        clip = self.clips.get(f"sc_{hi}_{lo}")
        return [self._path(clip["file"])] if clip else []

    def fast(self, speed):
        tens = min(150, int(speed // 10) * 10)
        for t in range(tens, 50, -10):
            clip = self.clips.get(f"spd_{t:03d}")
            if clip:
                return [self._path(clip["file"])]
        return self.line(["fast_"], 1)

    def countdown(self, n):
        return self.exact(f"cd_{n:02d}")

    def full_time(self, game, h, a, p, ai, fb_p, fb_ai):
        out = self.exact("clk_whistle") + self.exact("ft_over")
        if game == 2:
            if h == a:
                return out + self.exact("ft_draw_pvp") + self.score(h, a)
            win, fb = (p, fb_p) if h > a else (ai, fb_ai)
            return out + self.line(["ft_win_pvp_"], 2, win, fb) + self.score(h, a)
        if h > a:
            out += (self.exact("ft_h_ai_01") if random.random() < 0.5 else self.exact("ft_h_ai_02", p, fb_p))
            if a == 0:
                out += self.exact("ft_clean")
        elif a > h:
            out += self.line(["ft_a_ai_"], 1)
        else:
            out += self.exact("ft_draw_ai")
        return out + self.score(h, a)

    def blind(self):
        return self.exact("blind_01") + self.exact("blind_02")

    def sight(self):
        return self.exact("sight_01")

    def highlights_open(self):
        return self.line(["hl_open_"], 1)

    def replay(self, game):
        return self.line(["hl_w_0", "hl_w_ai_"] if game == 1 else ["hl_w_0"], game)

    def closing(self, game, h, a):
        if h == a:
            cid = "hl_close_d"
        elif game == 2:
            cid = "hl_close_pvp"
        else:
            cid = "hl_close_h_ai" if h > a else "hl_close_a_ai"
        return self.exact(cid) + self.exact("hl_end")

    def award(self, kind, name, fallback):
        cid = {"rocket": "aw_rocket", "wall": "aw_wall"}.get(kind)
        return self.exact(cid) + self.exact("aw_goes") + self.name_seq(name, "calm", fallback)
