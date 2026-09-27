"""Up and down swipes, for scrolling a feed like TikTok.

Like press.py, nothing here knows about cameras: it takes the palm position
each frame and whether the hand is a fist, and says when a swipe happened.
Two ways to swipe, switchable live:

- FLICK: a quick flick of the hand. The catch is the return stroke: after
  flicking up, the hand comes back down, which looks just like a flick down.
  So after a swipe the opposite direction is ignored for `lockout_s`.
- DRAG: make a fist, move up or down, open the hand. One swipe per grab.
  The hand goes back open, so the return stroke cannot count.

Up is the next video, as on a phone. Positions are frame fractions, y down.
Every threshold is a first guess, to tune from the terminal log.
"""

from collections import deque

UP = "up"
DOWN = "down"
FLICK = "flick"
DRAG = "drag"
METHODS = (FLICK, DRAG)


class Swipe:
    def __init__(self, method=FLICK, flick_dist=0.10, flick_s=0.25,
                 drag_dist=0.06, vertical=1.5, lockout_s=0.7, cooldown_s=0.4,
                 settle_s=0.3, gone_s=0.3):
        self.method = method
        # A flick covers flick_dist of the frame height within flick_s, so
        # it is at least 0.4 frames/s. Reaching up to a button is slower.
        # (Was 0.18 in 0.25 s, 0.7 frames/s, which took too hard a flick.)
        self.flick_dist = flick_dist
        self.flick_s = flick_s
        self.drag_dist = drag_dist
        # Vertical movement must be this many times the horizontal, so
        # moving across to a button is not a swipe.
        self.vertical = vertical
        self.lockout_s = lockout_s
        self.cooldown_s = cooldown_s
        # A hand coming into view rises fast from the bottom edge, which
        # looks like a flick up. No flicks until it has been in view settle_s;
        # it counts as having left after gone_s unseen.
        self.settle_s = settle_s
        self.gone_s = gone_s
        self._trail = deque()
        self._anchor = None
        self._dragged = False
        self._blocked = {UP: 0.0, DOWN: 0.0}
        self._last_seen = None
        self._appeared = 0.0

    def update(self, t, p, held=False):
        if p is None:
            # A fast flick blurs, and the tracker drops a frame or two in the
            # middle of it. Keep the trail: its points age out by time anyway,
            # and a drag's anchor goes when the hold does.
            return None
        if self._last_seen is None or t - self._last_seen > self.gone_s:
            self._appeared = t
        self._last_seen = t
        if self.method == DRAG:
            return self._drag(t, p, held)
        if held:
            # A fist is grabbing, not flicking.
            self._trail.clear()
            return None
        return self._flick(t, p)

    def _flick(self, t, p):
        if t - self._appeared < self.settle_s:
            self._trail.clear()
            return None
        self._trail.append((t, p))
        while t - self._trail[0][0] > self.flick_s:
            self._trail.popleft()
        _, start = self._trail[0]
        return self._check(t, start, p, self.flick_dist)

    def _drag(self, t, p, held):
        if not held:
            self._anchor = None
            return None
        if self._anchor is None:
            self._anchor, self._dragged = p, False
            return None
        if self._dragged:
            return None
        swipe = self._check(t, self._anchor, p, self.drag_dist)
        self._dragged = swipe is not None
        return swipe

    def _check(self, t, start, p, dist):
        dx, dy = p[0] - start[0], p[1] - start[1]
        if abs(dy) < dist or abs(dy) < self.vertical * abs(dx):
            return None
        way = UP if dy < 0 else DOWN
        if t < self._blocked[way]:
            return None
        self._trail.clear()
        other = DOWN if way == UP else UP
        self._blocked[other] = max(self._blocked[other], t + self.lockout_s)
        self._blocked[way] = t + self.cooldown_s
        return way


def grabbing(fingers):
    """Whether the hand is a fist, from its set of extended fingers.

    None with no hand, and None for one finger up: a fist opening passes
    through that on its way, so the last state should stand.
    """
    if fingers is None:
        return None
    if not fingers:
        return True
    return False if len(fingers) >= 2 else None


class Debounce:
    """A fist/open state that ignores flicker.

    Finger shapes read from single frames flicker at the moment of change,
    and a flicker mid-drag would end the grab. A new value has to persist for
    `settle_s` to take over. None (no reading) keeps the current state, but a
    hand gone for `lost_s` counts as open.
    """

    def __init__(self, settle_s=0.08, lost_s=0.3):
        self.settle_s = settle_s
        self.lost_s = lost_s
        self.state = False
        self._candidate = None
        self._since = 0.0
        self._lost_at = None

    def update(self, t, value):
        if value is None:
            if self._lost_at is None:
                self._lost_at = t
            if t - self._lost_at >= self.lost_s:
                self.state = False
            self._candidate = None
            return self.state
        self._lost_at = None
        if value == self.state:
            self._candidate = None
        elif value != self._candidate:
            self._candidate, self._since = value, t
        elif t - self._since >= self.settle_s:
            self.state, self._candidate = value, None
        return self.state
