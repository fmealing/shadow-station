"""Half reps: reps that keep stopping short of the lift's full range.

Nothing here counts or discounts a rep: the count is the rep counter's
(reps.py), and a short rep is a rep. This watches each arm's angle turn round
at the top and the bottom of every rep, and says when two running stopped
short at the same end, and which arms', so the screen can show where they
should get to. Some lifters stop short on purpose, so it is only shown, and
one rep that gets there takes it back.

Like press.py, nothing here knows about cameras: it takes each arm's angle as
a goniometer reads it (workout.read) and the time.
"""

import math

TOP, BOTTOM = "top", "bottom"

# A full rep at each joint, as the goniometer reads it: the top gets at least
# as far as the first angle, and the arm comes back down at least as far as
# the second. Both are generous, so that only a rep cut to about half its
# range is called short:
# - A raise to shoulder height reads about 85 to 105 on the station, and arms
#   hanging with dumbbells in them 20 to 35.
# - An elbow's angle is measured flat on the picture, and a curl comes
#   towards the camera: below level it reads straighter than it is, above
#   level more bent. Level reads 90 from any side, so the top has to be clear
#   of that.
# These are from one filmed set of raises and the geometry, not from the
# lab's captures. They are the numbers to change if the cue comes too easily
# or not at all.
FULL = {"shoulder": (65.0, 50.0), "elbow": (100.0, 50.0)}
TURN_DEG = 15.0   # an arm has turned round once it is this far back from its furthest
RUN = 2           # this many short reps in a row is a habit, not a slip
STALE_S = 4.0     # an arm that turned round longer ago than this has stopped lifting


class HalfReps:
    def __init__(self, joint):
        self.top_min, self.bottom_max = FULL[joint]
        # The arms the last verdict was of, in the order they are given.
        self.arms = [False, False]
        self._arms = [_Arm(), _Arm()]

    def update(self, t, arms):
        """Feed each arm's angle (or None) at time `t` in seconds. Returns
        the end the reps keep stopping short of, TOP or BOTTOM, or None."""
        for arm, deg in zip(self._arms, arms):
            if deg is not None:
                arm.add(t, deg, self.top_min, self.bottom_max)
        self.arms = [False, False]
        last = max(a.turned for a in self._arms)
        if t - last > STALE_S:
            return None     # nobody is lifting: before the set, or after it
        # The arm that hangs through a one-arm set never turns round. Arms
        # that are lifting have to agree: one arm short of the other is the
        # summary's to show.
        lifting = [last - a.turned <= STALE_S for a in self._arms]
        for end in (TOP, BOTTOM):
            if all(a.short[end] >= RUN for a, on in zip(self._arms, lifting) if on):
                self.arms = lifting
                return end
        return None


class _Arm:
    """One arm's reps: where its angle turns round, and how many of its last
    tops and bottoms in a row stopped short."""

    def __init__(self):
        self.short = {TOP: 0, BOTTOM: 0}
        self.turned = -math.inf     # when it last turned round
        self._rising = None         # None until it has left where it began
        self._far = None            # the furthest it has got the way it is going
        self._lo, self._hi = math.inf, -math.inf

    def add(self, t, deg, top_min, bottom_max):
        # Getting there takes the cue back at once, without waiting for the
        # rep to be over.
        if deg >= top_min:
            self.short[TOP] = 0
        if deg <= bottom_max:
            self.short[BOTTOM] = 0
        if self._rising is None:
            # Where the arm was when the set began is not the end of a rep:
            # it only says which way the arm set off.
            self._lo, self._hi = min(self._lo, deg), max(self._hi, deg)
            if deg - self._lo >= TURN_DEG or self._hi - deg >= TURN_DEG:
                self._rising, self._far = deg - self._lo >= TURN_DEG, deg
            return
        way = 1 if self._rising else -1
        if (deg - self._far) * way >= 0:
            self._far = deg
        elif (self._far - deg) * way >= TURN_DEG:
            if self._rising and self._far < top_min:
                self.short[TOP] += 1
            if not self._rising and self._far > bottom_max:
                self.short[BOTTOM] += 1
            self._rising, self._far, self.turned = not self._rising, deg, t
