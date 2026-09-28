"""
What the commentator says. Original lines in a lyrical, dramatic football-commentary style
(Drury-inspired; none are real quotes). See COMMENTARY_DESIGN.md for the thinking behind them.

Placeholders: {p} = player, {ai} = AI name (player 2 in two-player games), {v} = shot speed,
{h}/{a} = score, {who} = award winner, {n} = a count.

Every entry is a list: one version is picked at random each time, so it rarely repeats.
Written for text-to-speech: commas and full stops make the pauses ("..." is often ignored),
no ALL-CAPS words (some voices spell them out), "A I" instead of "AI".
"""
import random

# ------------------------------------------------------------------ human vs the machine
KICKOFF = [
    "Under the lights of a laboratory in Palashi. One human being. One machine. "
    "Forty six centimetres of destiny between them.",
    "{p}. Flesh, and nerve, and hope. And across the table, {ai}. Eight megahertz of cold intent.",
    "They say the machine cannot be beaten. Tonight, {p} has come to ask it a question.",
    "Three minutes. One ball. And a question as old as invention itself. "
    "Can the maker defeat what was made?",
]
GOAL_H = [
    "Oh, it's in! {p}! Poetry, in a plywood arena!",
    "{p}! Has found a flaw in the code!",
    "The machine calculated everything. Everything, except that!",
    "It's there! For every student who ever lost to a computer!",
    "Written in the stars. And now, on the scoresheet. {p}!",
]
GOAL_A = [
    "Cold. Calculated. Clinical.",
    "The machine does not celebrate. It does not need to.",
    "It saw that, before {p} had even thought it.",
    "Oh, cruel. Cruel mathematics.",
    "{ai} strikes. Thirty two kilobytes of ambition, and not one byte of mercy.",
]
# a second line after a goal, depending on the score (1P)
TAIL_GOAL_H = [
    "The silicon did the maths. The human did the magic.",
    "Somewhere, a transistor weeps.",
    "Mark it down. Remember where you were.",
]
TAIL_EQUALISER = ["Level! Everything we thought we knew, is gone!", "All square. The machine blinks."]
TAIL_LEAD_H = ["{p} leads! Humanity is in front!", "In front! The human race, in front!"]
TAIL_COMEBACK = ["From behind. This is not a match anymore. This is a story."]
TAIL_AI_EXTENDS = ["The grip tightens. Slowly. Mechanically.", "A lesson, being delivered in binary."]
LAST_GASP = ["At the death! {p}! At the very death!", "With the last breath of the clock!"]

FAST = [
    "{v} centimetres a second! The camera barely believed it!",
    "That left the flipper like a monsoon wind! {v} centimetres a second!",
]
AI_BLIND = ["The machine has lost its eyes! It plays now, on memory alone!"]
AI_SEES = ["And the eyes are open again. The machine is watching."]

SECONDS_60 = ["One minute. Sixty heartbeats."]
SECONDS_30 = ["Thirty seconds. And the clock belongs to no one.", "Thirty seconds. Is there time? Is there belief?"]
SECONDS_10 = ["Ten seconds! Can {p} do it?", "Ten seconds. The whole of Palashi holds its breath."]

FULL_TIME_WIN_H = [
    "It is over. {p} has beaten the machine, {h} to {a}. Tell the engineers. Tell the textbooks. Tell everyone.",
    "Full time. {h} to {a}. The maker, has defeated the made.",
]
FULL_TIME_WIN_A = [
    "The machine prevails, {a} to {h}. But {p} made it sweat. If silicon can sweat.",
    "Full time. {a} to {h} to {ai}. A lesson, delivered in binary.",
]
FULL_TIME_DRAW = [
    "Level, {h} all. Human and machine walk away as equals. Tonight, nobody is obsolete.",
]
HIGHLIGHTS = ["Let us remember. Let us relive.", "Here they are again. Every heartbeat of it."]
NO_GOALS = ["No goals. But nobody who watched this will call it empty.", "Not a goal. A defensive masterclass."]
AWARD_ROCKET = ["The Rocket. {who}. {v} centimetres a second. Faster than the eye, faster than the code."]
AWARD_WALL = ["The Wall. {ai}. {n} saves. It stood in the doorway, and it did not move."]

# ------------------------------------------------------------------ two players (no machine)
# {p} = player 1, {ai} = player 2; goal lines get the scorer's name as {p}.
KICKOFF_2P = [
    "{p}, and {ai}. Two players. One ball. Three minutes to decide everything.",
    "Friends, before the whistle. Rivals, for three minutes. {p} against {ai}!",
]
GOAL_2P = [
    "Oh, it's in! {p}!",
    "{p}! Oh, that is beautiful!",
    "There it is! {p}, with the answer!",
    "{p}! And the arena erupts!",
]
TAIL_EQUALISER_2P = ["Level! We start again!", "All square. Nothing separates them."]
TAIL_LEAD_2P = ["{p} leads!", "And {p} is in front!"]
SECONDS_10_2P = ["Ten seconds! Who wants it more?"]
FULL_TIME_WIN_2P = ["Full time! {p} wins it, {h} to {a}!", "It is over. {p}, {h} to {a}. Take a bow."]
FULL_TIME_DRAW_2P = ["Full time. {h} all. Two players, and not a hair between them."]

FAST_SPEED = 60.0   # cm/s: say the speed only for shots faster than this


_last = {}    # id(list) -> the version used last time, so the same line never plays twice in a row


def fill(t, **kw):
    """Fill in the placeholders. `t` may be a list: then one version is picked at random."""
    if isinstance(t, list):
        options = [x for x in t if x != _last.get(id(t))] or t
        _last[id(t)] = t = random.choice(options)
    kw = {k: (str(int(round(v))) if isinstance(v, float) else str(v)) for k, v in kw.items()}
    return t.format(**{"p": "", "ai": "", "v": "", "h": "", "a": "", "who": "", "n": "", **kw})


def pick(options, **kw):
    return fill(options, **kw)


def all_goal_lines(p, ai, game=1):
    """Everything worth pre-rendering once the names are known."""
    if game == 2:
        out = [fill(t, p=p, ai=ai) for t in KICKOFF_2P]
        out += [fill(t, p=who) for t in GOAL_2P for who in (p, ai)]
        out += [fill(t, p=who) for t in TAIL_LEAD_2P for who in (p, ai)]
        out += [fill(t) for t in TAIL_EQUALISER_2P + SECONDS_10_2P]
    else:
        out = [fill(t, p=p, ai=ai) for t in KICKOFF + GOAL_H + GOAL_A + TAIL_GOAL_H + TAIL_EQUALISER
               + TAIL_LEAD_H + TAIL_AI_EXTENDS + SECONDS_10]
    out += [fill(t) for t in SECONDS_60 + SECONDS_30 + HIGHLIGHTS]
    return out
