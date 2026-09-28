"""
Goals seen by the camera — a stand-in until the laser goal sensors are wired.

A goal is the ball getting past a carriage to the baseline wall behind it:
  * seen in the strip behind the AI carriage face                   -> the human scores
  * last seen near the human carriage, heading there, then gone      -> the AI scores
    (the tracker ignores the strip behind the human carriage, so a ball there just vanishes)
  * last seen near the AI carriage, heading there, then gone         -> the human scores
    (it can disappear under the AI carriage's mask)

After a goal nothing counts until the ball has been back in midfield for a moment (re-served),
so a ball lying in the goal or picked up by hand isn't counted twice.

As soon as the robot reports a goal itself ("G H ..." from the lasers), main.py switches this off.
"""
import config as C

GONE_S = 0.6          # ball must stay out of sight this long to count as a goal
NEAR_CM = 5.0         # "near a carriage" = ball centre within this of its front face line
MIN_TOWARD = 5.0      # cm/s: last seen moving toward that end at least this fast
BEHIND_CM = C.CARRIAGE_DEPTH - 0.8   # ball centre this close to the AI wall = past the carriage
RESERVE_S = 0.4       # after a goal: ball back in midfield this long = play again
MIDFIELD_CM = 10.0    # "midfield" = at least this far from both baselines


class GoalWatcher:
    def __init__(self):
        self.last = None          # (t, x, y, vy) when the ball was last seen
        self.armed = True
        self._mid_since = None

    def update(self, t, ball, vy):
        """Call every frame. Returns 'H' (human scored), 'A' (AI scored) or None."""
        if ball is not None:
            x, y = ball
            if not self.armed:
                if MIDFIELD_CM < y < C.ARENA_H - MIDFIELD_CM:
                    self._mid_since = self._mid_since or t
                    if t - self._mid_since >= RESERVE_S:
                        self.armed, self._mid_since = True, None
                else:
                    self._mid_since = None
                self.last = (t, x, y, vy)
                return None
            self.last = (t, x, y, vy)
            if y < BEHIND_CM:
                return self._goal("H")
            return None

        if not self.armed or self.last is None:
            return None
        t0, x, y, vy0 = self.last
        if t - t0 < GONE_S:
            return None
        if y > C.ARENA_H - C.AI_LINE_Y - NEAR_CM and vy0 > MIN_TOWARD:
            return self._goal("A")
        if y < C.AI_LINE_Y + NEAR_CM and vy0 < -MIN_TOWARD:
            return self._goal("H")
        return None

    def _goal(self, who):
        self.armed, self._mid_since, self.last = False, None, None
        return who
