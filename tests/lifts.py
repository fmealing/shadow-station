"""Made-up sets: 33 pose landmarks per frame, as the tracker gives them, for
testing the rep counter and the set flow without a camera. Lateral raises are
what the station counts. Curls rest at the other end of their joint's angle,
so they keep the counter tested both ways."""

import math

import numpy as np

from station.reps import ASPECT

FPS = 30
UPPER_ARM, FOREARM = 0.12, 0.11  # in canvas heights, at scale 1
RAISE_REST, RAISE_TOP = 10.0, 90.0   # the arm, out from hanging straight down
CURL_REST, CURL_TOP = 170.0, 40.0    # the elbow
# Far enough back for the arms to stay in view at the top of a raise.
SCALE = 0.7


def standing(raise_deg=RAISE_REST, elbow_deg=CURL_REST, scale=SCALE, vis=1.0,
             other_deg=None, other_elbow=None):
    """A lifter facing the camera, both arms `raise_deg` out to the sides and
    both elbows at `elbow_deg`. A smaller `scale` stands them further away.
    `other_deg` raises the arm on the right of the screen differently, and
    `other_elbow` bends it differently."""
    def at(x, y):
        return (0.5 + (x - 0.5) * scale, 0.45 + (y - 0.45) * scale, vis)

    lms = [at(0.5, 0.2)] * 33  # face points on the nose
    body = {11: (0.42, 0.3), 12: (0.58, 0.3),
            23: (0.45, 0.52), 24: (0.55, 0.52), 25: (0.45, 0.68), 26: (0.55, 0.68),
            27: (0.45, 0.84), 28: (0.55, 0.84)}
    for i, p in body.items():
        lms[i] = at(*p)
    # Angles from hanging straight down, out to the side. The upper arm is
    # raised, and the forearm swings back in from it as the elbow closes.
    for shoulder, elbow, wrist, out, deg, bend in (
            (11, 13, 15, -1, raise_deg, elbow_deg),
            (12, 14, 16, 1, raise_deg if other_deg is None else other_deg,
             elbow_deg if other_elbow is None else other_elbow)):
        upper = math.radians(deg)
        fore = upper - math.radians(180 - bend)
        sx, sy = body[shoulder]
        ex = sx + out * UPPER_ARM * math.sin(upper) / ASPECT
        ey = sy + UPPER_ARM * math.cos(upper)
        wx = ex + out * FOREARM * math.sin(fore) / ASPECT
        wy = ey + FOREARM * math.cos(fore)
        lms[elbow] = at(ex, ey)
        for i in (wrist, wrist + 2, wrist + 4, wrist + 6):  # wrist, pinky, index, thumb
            lms[i] = at(wx, wy)
    return lms


def raise_set(reps=8, other=1.0, **kw):
    """(times, frames) for a set of lateral raises; see `_set`. The arm on
    the right of the screen goes `other` times as far as the one on the left."""
    def pose(a):
        return standing(raise_deg=a, other_deg=RAISE_REST + (a - RAISE_REST) * other)
    return _set(pose, RAISE_REST, RAISE_TOP, reps, **kw)


def curl_set(reps=8, other=1.0, **kw):
    """(times, frames) for a set of curls; see `_set`. The arm on the right
    of the screen curls `other` times as far as the one on the left: 0 leaves
    it hanging, as in a one-arm set."""
    def pose(a):
        return standing(elbow_deg=a, other_elbow=CURL_REST + (a - CURL_REST) * other)
    return _set(pose, CURL_REST, CURL_TOP, reps, **kw)


def _set(pose, rest, top, reps, rep_s=2.5, slowdown=0.0, rest_before=3.0,
         rest_after=3.0, noise=0.002, seed=0, reach=1.0, low=0.0):
    """Standing still, `reps` reps from `rest` to `top` and back, standing
    still. Each rep takes `rep_s`, and `slowdown` more seconds than the one
    before it. A rep gets `reach` of the way to the top, and comes back down
    to `low` of the way there before the next one; the last comes all the
    way down. Either can be one number or one for each rep."""
    rng = np.random.default_rng(seed)
    reach, low = np.broadcast_to(reach, reps), np.broadcast_to(low, reps)
    angles = [rest] * int(rest_before * FPS)
    start = rest
    for r in range(reps):
        n = int((rep_s + r * slowdown) * FPS)
        high = rest + (top - rest) * reach[r]
        end = rest if r == reps - 1 else rest + (top - rest) * low[r]
        for k in range(n):
            pulse = (1 - math.cos(2 * math.pi * k / n)) / 2
            base = start if 2 * k < n else end
            angles.append(base + (high - base) * pulse)
        start = end
    angles += [rest] * int(rest_after * FPS)
    times = np.arange(len(angles)) / FPS
    frames = []
    for a in angles:
        frames.append([(x + rng.normal(0, noise), y + rng.normal(0, noise), v)
                       for x, y, v in pose(a)])
    return times, frames
