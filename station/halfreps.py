"""Half reps: reps that keep stopping short of the lift's full range.

A short rep is a rep, and two things here see to it:

- `HalfReps` watches each arm's angle turn round at the top and the bottom of
  every rep, and says when two running stopped short at the same end, and
  which arms', so the screen can show where they should get to. Some lifters
  stop short on purpose, so it is only shown, and one rep that gets there
  takes it back.
- `Uncounted` counts the short reps the live counter (reps.py) lets go by,
  so the number keeps going up and the set is not taken to be over.

Like press.py, nothing here knows about cameras: they take angles and the
time.
"""

import math

from . import reps

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
    """One arm's reps: how many of its last tops and bottoms in a row stopped
    short, and when it last turned round."""

    def __init__(self):
        self.short = {TOP: 0, BOTTOM: 0}
        self.turned = -math.inf     # when it last turned round
        self._turns = _Turns()

    def add(self, t, deg, top_min, bottom_max):
        # Getting there takes the cue back at once, without waiting for the
        # rep to be over.
        if deg >= top_min:
            self.short[TOP] = 0
        if deg <= bottom_max:
            self.short[BOTTOM] = 0
        end = self._turns.add(deg, TURN_DEG)
        if end is None:
            return
        if end == TOP and self._turns.at < top_min:
            self.short[TOP] += 1
        if end == BOTTOM and self._turns.at > bottom_max:
            self.short[BOTTOM] += 1
        self.turned = t


class _Turns:
    """Where a signal turns round: the top and the bottom of each rep."""

    def __init__(self):
        self.at = None              # how far it got before it last turned
        self._rising = None         # None until it has left where it began
        self._far = None            # the furthest it has got the way it is going
        self._lo, self._hi = math.inf, -math.inf

    def add(self, v, back):
        """Feed the signal's next value. Returns TOP or BOTTOM once it has
        come `back` from one, and None otherwise."""
        if self._rising is None:
            # Where the signal began is not the end of a rep: it only says
            # which way it set off.
            self._lo, self._hi = min(self._lo, v), max(self._hi, v)
            if v - self._lo >= back or self._hi - v >= back:
                self._rising, self._far = v - self._lo >= back, v
            return None
        way = 1 if self._rising else -1
        if (v - self._far) * way >= 0:
            self._far = v
            return None
        if (self._far - v) * way < back:
            return None
        end, self.at = (TOP if self._rising else BOTTOM), self._far
        self._rising, self._far = not self._rising, v
        return end


# The live counter's bands sit at fixed places in the range the set has shown
# so far (30% and 70% of the way up), and a rep that stops short of either
# goes by uncounted: reps that shrink part-way through a set, and reps that
# stop coming back down. The analysis afterwards counts by prominence instead
# (reps.PROMINENCE_FRAC of the set's range) and takes them. So that rule is
# kept running during the set as well, on the live counter's own smoothed
# angle and range. While the live counter is counting, its number stands,
# which is every set it was measured on. Once it has let this many reps
# running go by, the number is this count instead, for the rest of the set.
# Not measured on the lab's captures: only on made-up sets.
LET_BY = 2


class Uncounted:
    def __init__(self, rest_at_max):
        self.rest_at_max = rest_at_max
        # Whether the live counter has let reps go by, and this count stands.
        self.took_over = False
        self._count = None          # None until the live counter has a range
        self._seen = 0              # the live counter's number at the last top
        self._turns = _Turns()

    def update(self, angle, rng, count):
        """Feed the live counter's smoothed angle, the range it has seen (its
        10th to 90th percentile) and its count."""
        if rng < reps.LiveRepCounter.MIN_RANGE_DEG:
            return
        if self._count is None:
            self._count = self._seen = count
        # The top of a rep is where the lifter is furthest from rest.
        v = -angle if self.rest_at_max else angle
        if self._turns.add(v, reps.PROMINENCE_FRAC * rng) != TOP:
            return
        if self.took_over:
            self._count += 1
        elif count > self._seen:
            # The live counter took this rep, as it takes each rep on the
            # way up. A stray turn before it is forgotten.
            self._count = count
        else:
            self._count += 1
            self.took_over = self._count - count >= LET_BY
        self._seen = count

    def reps(self, count):
        """The number to show, given the live counter's."""
        return max(count, self._count) if self.took_over else count
