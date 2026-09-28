"""What George says. {p} = player, {ai} = AI name, {v} = shot speed, {h}/{a} = score."""
import random

KICKOFF = ["Welcome to CHEERIVY! {p} versus {ai}. Three minutes on the clock. Let's go!",
           "It's {p} against the machine, {ai}. Kick off!"]
GOAL_H = ["What a goal by {p}!", "{p} scores! The machine had no answer!",
          "Brilliant finish from {p}!", "Goal! {p} beats the A I!"]
GOAL_A = ["The A I strikes! Goal for {ai}.", "{ai} scores. The machine is learning.",
          "Clinical from {ai}. That one's in."]
FAST = "Clocked at {v} centimetres per second!"
SCORE = ["{h} {a}.", "It's {h} {a}."]
SECONDS_30 = "Thirty seconds left!"
SECONDS_10 = "Ten seconds! Can {p} do it?"
FULL_TIME_WIN_H = "Full time! {p} defeats the machine, {h} to {a}!"
FULL_TIME_WIN_A = "Full time! {ai} wins, {a} to {h}. Better luck next time, {p}."
FULL_TIME_DRAW = "Full time! It ends all square, {h} all."
HIGHLIGHTS = "Here are your match highlights."
NO_GOALS = "No goals today. A defensive masterclass."
AWARD_ROCKET = "The Rocket award goes to {who}, at {v} centimetres per second."
AWARD_WALL = "The Wall. {ai} saved {n} shots."

FAST_SPEED = 60.0   # cm/s: say the speed only for shots faster than this


def fill(t, **kw):
    kw = {k: (str(int(round(v))) if isinstance(v, float) else str(v)) for k, v in kw.items()}
    return t.format(**{"p": "", "ai": "", "v": "", "h": "", "a": "", "who": "", "n": "", **kw})


def pick(options, **kw):
    return fill(random.choice(options) if isinstance(options, list) else options, **kw)


def all_goal_lines(p, ai):
    """Everything worth pre-rendering once the names are known."""
    out = [fill(t, p=p, ai=ai) for t in KICKOFF + GOAL_H + GOAL_A]
    out += [fill(SECONDS_30), fill(SECONDS_10, p=p), HIGHLIGHTS]
    return out
