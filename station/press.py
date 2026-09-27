"""How a tracked hand becomes a press: hover still and the ring fills.

Nothing in here knows about cameras or MediaPipe. It takes a cursor position
(or None when nothing is tracked) each frame and says when something was
pressed, so it can be unit-tested without a camera.

Hover (dwell) is the one way to press. It works at any distance and in pose
mode, and it won the comparison: pinch was dropped because the tracker cannot
reliably tell whether two fingertips touch, and pressing with hand shapes
(fist, two fingers) lost to it in use.

- `Presser` presses the station's own buttons.
- `Dwell` clicks anywhere, for pages the station does not lay out itself,
  such as TikTok.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Button:
    id: str
    label: str
    rect: tuple  # x, y, w, h in canvas pixels
    # A zone's own hold time instead of the dwell; 0 fires on entry.
    hold_s: float | None = None

    def contains(self, p, pad=0):
        x, y, w, h = self.rect
        return x - pad <= p[0] <= x + w + pad and y - pad <= p[1] <= y + h + pad


class Presser:
    """Turns a cursor into presses of the buttons on screen, frame by frame.

    Three rules keep it from misfiring:

    - One press per visit. A button that just fired cannot fire again until the
      cursor has been seen off it. Without this, dwelling on the mode toggle
      would flip it back and forth every `dwell_s`.
    - Sticky hover. Once a button is hovered its hit area grows by `sticky_px`,
      so cursor jitter at the edge does not keep restarting the dwell.
    - Dropout grace. The tracker loses the hand for a frame or two all the
      time; the hover survives gaps shorter than `lost_grace_s`.
    """

    def __init__(self, dwell_s=0.8, lost_grace_s=0.25, sticky_px=24):
        self.dwell_s = dwell_s
        self.lost_grace_s = lost_grace_s
        self.sticky_px = sticky_px

        self.hovered = None
        self.progress = 0.0        # dwell fill, 0..1, for drawing
        self.pressed_after = 0.0   # seconds of hover before the last press
        self._hover_start = 0.0
        self._lost_at = None
        self._spent = None

    def update(self, t, cursor, buttons):
        if cursor is None:
            if self._lost_at is None:
                self._lost_at = t
            if t - self._lost_at >= self.lost_grace_s:
                self.hovered = None
                self.progress = 0.0
            return None
        self._lost_at = None

        target = self._hit(cursor, buttons)
        if self._spent and (target is None or target.id != self._spent):
            self._spent = None
        if _id(target) != _id(self.hovered):
            self._hover_start = t
        self.hovered = target

        self.progress = 0.0
        if target is None or target.id == self._spent:
            return None
        hold = self.dwell_s if target.hold_s is None else target.hold_s
        hovered_for = t - self._hover_start
        self.progress = 1.0 if hold <= 0 else min(1.0, hovered_for / hold)
        if self.progress < 1.0:
            return None
        self._spent = target.id
        self.pressed_after = hovered_for
        self.progress = 0.0
        return target

    def _hit(self, cursor, buttons):
        if self.hovered is not None:
            for b in buttons:
                if b.id == self.hovered.id and b.contains(cursor, self.sticky_px):
                    return b
        for b in buttons:
            if b.contains(cursor):
                return b
        return None


def _id(button):
    return None if button is None else button.id


class Dwell:
    """Hover-to-click anywhere, with no buttons to aim at.

    Fires when the cursor stays within `radius` of where it settled for
    `dwell_s`, then waits for the cursor to move off before it can fire
    again: a hand held still clicks once, not every `dwell_s`. Same dropout
    grace as `Presser`.
    """

    def __init__(self, dwell_s=0.8, radius=24, lost_grace_s=0.25):
        self.dwell_s = dwell_s
        self.radius = radius
        self.lost_grace_s = lost_grace_s
        self.progress = 0.0
        self.reset()

    def reset(self):
        self.progress = 0.0
        self._anchor = None
        self._start = 0.0
        self._spent = False
        self._lost_at = None

    def update(self, t, p):
        if p is None:
            if self._lost_at is None:
                self._lost_at = t
            if t - self._lost_at >= self.lost_grace_s:
                self.reset()
            return None
        self._lost_at = None
        if self._anchor is None or math.dist(p, self._anchor) > self.radius:
            self._anchor, self._start, self._spent = p, t, False
        if self._spent:
            self.progress = 0.0
            return None
        self.progress = min(1.0, (t - self._start) / self.dwell_s)
        if self.progress < 1.0:
            return None
        self._spent = True
        self.progress = 0.0
        return p


class OneEuro:
    """One Euro filter (Casiez et al. 2012) for a 2D cursor.

    Heavy smoothing when the hand is still, so a dwell target does not
    shimmer, and little when it moves fast, so the cursor does not lag behind
    a deliberate reach. Units are screen fractions and seconds: `beta` scales
    how quickly the cutoff opens up with speed in screen-widths per second.
    """

    def __init__(self, min_cutoff=1.2, beta=8.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self._t = None
        self._x = None
        self._dx = (0.0, 0.0)

    def __call__(self, t, p):
        if self._t is None:
            self._t, self._x = t, tuple(p)
            return self._x
        dt = max(t - self._t, 1e-3)
        self._t = t
        dx = tuple((a - b) / dt for a, b in zip(p, self._x))
        ad = _alpha(self.d_cutoff, dt)
        self._dx = tuple(ad * d + (1 - ad) * pd for d, pd in zip(dx, self._dx))
        a = _alpha(self.min_cutoff + self.beta * math.hypot(*self._dx), dt)
        self._x = tuple(a * v + (1 - a) * pv for v, pv in zip(p, self._x))
        return self._x


def _alpha(cutoff, dt):
    tau = 1.0 / (2 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)
