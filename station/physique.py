"""Physique: your shoulders against your waist, measured off the silhouette.

The pose model gives two things: 33 landmarks, and a mask of which pixels are
the person. Landmarks sit on joint centres, so they say where to look but not
how wide anything is; the mask says where the body ends. Both measures here
are widths across the mask, at a place the landmarks pick:

- Shoulders: across the shoulder joints, edge to edge, so the deltoids count.
- Waist: the narrowest the torso gets between the ribs and the hips.

Nothing knows how far away the camera is, so nothing is in centimetres. What
is shown is the one over the other. 1.618, the golden ratio, is the classic
ideal.

Each needs a pose it can be read in:

- Shoulders need both arms down. A raised arm carries the silhouette out
  along it, and there is no edge of the shoulder left to find.
- The waist needs the trunk's own edge. With a gap between arm and body that
  is the silhouette's. With the arm against the body the mask does not open
  up, but it is less sure of the crease between them, and that dip is taken
  for the edge. With neither on one side, that side mirrors the other.
- Both need you square on to the camera: turned, a width is partly a depth.
  Turned is judged against how you have been standing, by how far apart your
  shoulders are.

It is measured once. Stand still and square on, arms a little out, for
MEASURE_S, and the number is the median of what was read in that time. With
it comes a verdict: a meme, picked by how big the number is. From then on
nothing more is measured, and the two lines stay on the body through
whatever pose comes next, placed by the landmarks. The next person, or a
reset, starts it again.

Like workout.py, nothing here knows about cameras: `Physique.update` takes the
landmarks ((x, y, visibility) canvas fractions), the mask, how far the
shoulders are turned and the time.
"""

import math
import warnings
from collections import deque

import numpy as np

# What the number earns, best first: (at least this, picture, words over
# it). The pictures are web/public/memes/<picture>.jpg. A picture that says
# it all has no words.
VERDICTS = (
    (1.62, "gigachad", "Average golden ratio enjoyer"),
    (1.54, "doge", "Absolute unit"),
    (1.46, "stonks", None),
    (1.38, "honest-work", "It ain't much, but it's honest work"),
    (1.28, "harold", "It's called bulking"),
    (0.0, "fine", "This is fine"),
)

MIN_VIS = 0.5
INSIDE = 0.5            # the mask's value at the silhouette's edge
# Where an arm lies against the body the mask does not open up, but it does
# dip: it is less sure of the crease between them than of either. Below this
# is taken for the crease, looked for only where an arm is known to be.
CREASE = 0.8

L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 11, 12, 23, 24
# Shoulder, elbow, wrist and index knuckle of each arm, by the tracker's own
# left and right.
ARM_POINTS = ((11, 13, 15, 19), (12, 14, 16, 20))

# Rows across the trunk are placed by how far down it they are: 0 at the
# shoulder joints, 1 at the hip joints.
ROW_STEP = 0.0125
ROWS = np.arange(-0.08, 1.0, ROW_STEP)
# The shoulders are read on the rows through the joints themselves. Lower
# down, an arm held out from the body carries the edge out with it.
SHOULDER_ROWS = (-0.03, 0.04)
# The waist is the narrowest row from under the ribs to above the hip bones.
WAIST_ROWS = (0.42, 0.92)
# How far out from the midline an edge is looked for, in half shoulder widths
# (joint to joint). Further than this is not the trunk.
REACH = 2.2
# The upper arm from the trunk's line, in degrees: past this, the shoulder's
# edge runs out along the arm.
SHOULDER_ARM_MAX = 32.0
# An edge this close to the arm's own line (in half shoulder widths) is the
# arm's, not the trunk's: the arm is against the body there. A crease only
# has to come before the arm's line by the second, smaller margin: it is on
# the arm's own surface.
ARM_CLEARANCE = 0.30
CREASE_CLEARANCE = 0.10
# Square on to the camera, the shoulder joints are about 0.7 trunk lengths
# apart. Turned, they close up, and a width is partly a depth. How far apart
# they are square on differs from one build to the next, so each person is
# held to their own: a frame is read only if their shoulders are at least
# FACING_SHARE as far apart as they have usually been over FACING_WINDOW_S.
# FACING_MIN is the floor under that, for someone who walks in side-on.
FACING_MIN = 0.45
FACING_SHARE = 0.92
FACING_WINDOW_S = 10.0
# The tracker's own sense of depth also gives a turn, in degrees, but not one
# to lean on: standing square it reads anything up to 8 on one clip and up to
# 16 on the same clip mirrored. It only rules out what is plainly side-on.
TURN_MAX = 20.0
MIN_ROWS = 0.4          # of a band's rows must be readable

# The number is the median of this long standing still and readable. A frame
# or two that cannot be read does not start the wait again; GAP_S of them
# does, and so does moving more than MOVE trunk lengths from where it began:
# walking in is not standing there.
MEASURE_S = 1.5
GAP_S = 0.4
MOVE = 0.15

GONE_S = 2.5            # nobody for this long, and the next person starts fresh
LINE_TAU_S = 0.07       # how much the drawn lines are steadied
LINE_GRACE_S = 0.2      # a line survives this long without a body to sit on
LINES = ("shoulders", "waist")


def verdict(ratio):
    """The meme a number has earned: {"image", "caption"}."""
    for least, image, caption in VERDICTS:
        if ratio >= least:
            return {"image": image, "caption": caption}


class Physique:
    def __init__(self):
        self.reset()

    def reset(self):
        self.ratio = None       # shoulders over waist, once measured
        self.verdict = None
        self.headline, self.cue = "STEP IN", "Step in front of the screen"
        self._held = []         # (time, ratio, lines): this wait's readings
        self._anchor = None     # where the trunk was, and how long, when the wait began
        self._seen = None       # when the last of them was read
        self._measured = {}     # where each line sits on the body, once measured
        self._lines = {}        # id -> [a, b, last seen], as drawn
        self._facing = deque()  # (time, how far apart the shoulders were)
        self._met = False       # whether anyone has stepped in since the reset
        self._gone = None
        self._t = None

    def update(self, t, lms, mask, turn=None):
        """One frame: the landmarks, the silhouette, and how far the
        shoulders are turned from the camera in degrees, if known."""
        dt = 0.0 if self._t is None else t - self._t
        self._t = t
        if lms is None or mask is None:
            if self._gone is None:
                self._gone = t
            if t - self._gone >= GONE_S and self._met:
                self.reset()
                self._gone = t
            read = Reading("STEP IN", "Step in front of the screen")
        else:
            self._gone = None
            self._met = True
            read = measure(lms, mask, turn)
            if self._turned(t, read.facing):
                read.ratio = None
                read.headline, read.cue = "FACE THE SCREEN", "Stand square on to the screen"

        if self.ratio is None:
            self._wait(t, read)
        # Until the number is in, the lines are each frame's own reading of
        # the body. After, they are the measured ones, on the body as it is
        # now.
        if self.ratio is not None:
            lines = self._measured
        else:
            lines = read.lines if read.ratio is not None else {}
        self._follow_lines(t, dt, {} if read.body is None else
                           {name: read.body.place(line) for name, line in lines.items()})
        if self.ratio is not None:
            self.headline = self.cue = None
        elif read.headline:
            self.headline, self.cue = read.headline, read.cue
        else:
            self.headline, self.cue = "HOLD STILL", "Measuring"

    def _turned(self, t, facing):
        """Whether this frame's shoulders are closer together than this
        person's usually are: they have turned from the camera."""
        if facing is None:
            return False
        self._facing.append((t, facing))
        while self._facing[0][0] < t - FACING_WINDOW_S:
            self._facing.popleft()
        usual = float(np.median([f for _, f in self._facing]))
        return facing < FACING_SHARE * usual

    def _wait(self, t, read):
        """Before the number: gather readings while the person stands still,
        and once that has gone on for MEASURE_S, take their median."""
        if read.ratio is None:
            if self._seen is not None and t - self._seen > GAP_S:
                self._held, self._anchor, self._seen = [], None, None
            return
        body = read.body
        if self._anchor is not None:
            where, long = self._anchor
            if (np.linalg.norm(body.top - where) > MOVE * long
                    or abs(body.length - long) > MOVE * long):
                self._held, self._anchor = [], None
        if self._anchor is None:
            self._anchor = (body.top, body.length)
        self._seen = t
        self._held.append((t, read.ratio, read.lines))
        if t - self._held[0][0] < MEASURE_S:
            return
        self.ratio = round(float(np.median([r for _, r, _ in self._held])), 2)
        self.verdict = verdict(self.ratio)
        self._measured = {
            name: tuple(float(v) for v in
                        np.median([lines[name] for _, _, lines in self._held], axis=0))
            for name in LINES}

    def _follow_lines(self, t, dt, lines):
        k = 1 - math.exp(-dt / LINE_TAU_S) if dt > 0 else 1.0
        for name, (a, b) in lines.items():
            was = self._lines.get(name)
            if was is None:
                self._lines[name] = [a, b, t]
            else:
                was[0] = _towards(was[0], a, k)
                was[1] = _towards(was[1], b, k)
                was[2] = t
        for name in [n for n, line in self._lines.items() if t - line[2] > LINE_GRACE_S]:
            del self._lines[name]

    def header(self):
        """What the page draws: the cue, the number, its meme and the lines."""
        return {
            "headline": self.headline, "cue": self.cue,
            "ratio": self.ratio, "verdict": self.verdict,
            "lines": [{"id": name, "a": _rounded(a), "b": _rounded(b)}
                      for name, (a, b, _) in self._lines.items()],
        }


class Body:
    """Where the trunk is in one frame, in pixels: the middle of the
    shoulders, which way is down it and across it, how long it is, and half
    the distance between the shoulder joints. Lines are kept in its terms, so
    one measured in one frame can be drawn on the body in another."""

    def __init__(self, top, down, across, length, half, size):
        self.top, self.down, self.across = top, down, across
        self.length, self.half, self.size = length, half, size

    def place(self, line):
        """A line's two ends as canvas fractions. The line is (how far down
        the trunk, how far it runs to the left of the midline, and to the
        right), in trunk lengths and half shoulder widths."""
        k, left, right = line
        centre = self.top + k * self.length * self.down
        return ((centre - left * self.half * self.across) / self.size,
                (centre + right * self.half * self.across) / self.size)


class Reading:
    """One frame's measures: what could be read, and what is in the way."""

    def __init__(self, headline=None, cue=None):
        self.headline, self.cue = headline, cue
        self.ratio = None               # shoulders / waist
        self.lines = {}                 # id -> a line in the body's terms
        self.body = None                # the trunk, when it is all in view
        # How far apart the shoulder joints are, in trunk lengths: less when
        # turned from the camera.
        self.facing = None


def measure(lms, mask, turn=None):
    """Everything that can be read off one frame."""
    h, w = mask.shape
    size = np.array([w, h], np.float32)

    def px(i):
        return np.array([lms[i][0] * w, lms[i][1] * h], np.float32)

    def seen(*idx):
        return all(lms[i][2] >= MIN_VIS for i in idx)

    if not seen(L_SHOULDER, R_SHOULDER):
        return Reading("SHOULDERS HIDDEN", "Keep your shoulders in view")
    if not seen(L_HIP, R_HIP):
        return Reading("STEP BACK", "Fit your shoulders and hips in view")
    top = (px(L_SHOULDER) + px(R_SHOULDER)) / 2
    bottom = (px(L_HIP) + px(R_HIP)) / 2
    length = float(np.linalg.norm(bottom - top))
    if length < 0.08 * h:
        return Reading("STEP CLOSER", "Come a little closer")
    down = (bottom - top) / length
    across = np.array([down[1], -down[0]], np.float32)
    if across[0] < 0:
        across = -across            # towards the right of the screen
    half = abs(float((px(R_SHOULDER) - px(L_SHOULDER)) @ across)) / 2
    read = Reading()
    read.body = Body(top, down, across, length, half, size)
    read.facing = 2 * half / length
    if read.facing < FACING_MIN or (turn is not None and abs(turn) > TURN_MAX):
        read.headline, read.cue = "FACE THE SCREEN", "Stand square on to the screen"
        return read
    waist_end = top + WAIST_ROWS[1] * length * down
    if not (0 <= waist_end[0] < w and 0 <= waist_end[1] < h):
        read.headline, read.cue = "STEP BACK", "Fit your shoulders and hips in view"
        return read

    # The arms in screen order: which is on the left of the screen.
    order = (0, 1) if (px(L_SHOULDER) - top) @ across <= 0 else (1, 0)
    arms = [ARM_POINTS[i] for i in order]

    centres = top + ROWS[:, None] * length * down
    reach = REACH * half
    steps = (-across, across)
    edges = [_march(mask, centres, step, reach) for step in steps]

    # ---- shoulders --------------------------------------------------------
    # Both arms have to be down: one shoulder mirrored onto the other reads
    # narrow when the raised arm lifts and tilts the shoulders.
    rows = (ROWS >= SHOULDER_ROWS[0]) & (ROWS <= SHOULDER_ROWS[1])
    lowered = all(seen(e) and _angle(px(e) - px(s), down) <= SHOULDER_ARM_MAX
                  for s, e, _, _ in arms)
    shoulders = _widest(edges[0], edges[1], rows) if lowered else None

    # ---- waist ------------------------------------------------------------
    rows = (ROWS >= WAIST_ROWS[0]) & (ROWS <= WAIST_ROWS[1])
    for side, arm in enumerate(arms):
        pts = [px(i) for i in arm if seen(i)]
        # An edge found out at the arm's own line is the arm's: it is against
        # the body there. The trunk's edge is then the crease before it, if
        # the mask shows one.
        at = _arm_at_rows(pts, top, down, across, length)
        blocked = rows & (edges[side] >= at - ARM_CLEARANCE * half)
        crease = _march(mask, centres, steps[side], reach, CREASE)
        crease = np.where(crease < at - CREASE_CLEARANCE * half, crease, np.nan)
        edges[side] = np.where(blocked, crease, edges[side])
    # Arms hang close on one side more often than not, and the mask closes a
    # narrow gap. A side with no edge is taken to mirror the other, about the
    # middle of the shoulders' own outline when there is one: the landmarks'
    # midline is a centimetre or two out, which doubled is a lot of waist.
    off = (shoulders[3] - shoulders[2]) / 2 if shoulders is not None else 0.0
    waist = _narrowest(edges[0], edges[1], rows, off)

    for name, found in (("shoulders", shoulders), ("waist", waist)):
        if found is not None:
            _, row, left, right = found
            read.lines[name] = (float(ROWS[row]), left / half, right / half)
    if waist is not None and shoulders is not None:
        read.ratio = shoulders[0] / waist[0]
    elif not lowered:
        read.headline, read.cue = "ARMS DOWN", "Arms down, a little out from your sides"
    else:
        read.headline, read.cue = "ARMS OUT A LITTLE", "Leave a gap between your arms and your body"
    return read


def _march(mask, start, step, reach, level=INSIDE):
    """From each start point, pixels along `step` to the silhouette's edge:
    where the mask first falls below `level`.

    NaN where there is no edge to find: the start is not on the body, or the
    body runs on past `reach` or off the picture.
    """
    h, w = mask.shape
    start = np.asarray(start, np.float32).reshape(-1, 2)
    step = np.broadcast_to(np.asarray(step, np.float32), start.shape)
    s = np.arange(int(reach) + 1, dtype=np.float32)
    x = np.rint(start[:, :1] + s * step[:, :1]).astype(np.intp)
    y = np.rint(start[:, 1:] + s * step[:, 1:]).astype(np.intp)
    inside = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    body = ~inside
    body[inside] = mask[y[inside], x[inside]] >= level
    out = body.argmin(axis=1).astype(np.float32)
    out[body.all(axis=1) | ~body[:, 0]] = np.nan
    return out


def _arm_at_rows(pts, top, down, across, length):
    """Where an arm's line crosses each trunk row: its distance from the
    midline in pixels, NaN on rows it does not reach. Where it crosses a row
    twice (a bent arm), the crossing nearer the midline."""
    out = np.full(len(ROWS), np.nan, np.float32)
    for p, q in zip(pts, pts[1:]):
        kp, kq = ((p - top) @ down) / length, ((q - top) @ down) / length
        dp, dq = (p - top) @ across, (q - top) @ across
        rows = (ROWS >= min(kp, kq)) & (ROWS <= max(kp, kq))
        if not rows.any():
            continue
        f = (ROWS[rows] - kp) / (kq - kp) if abs(kq - kp) > 1e-6 else 0.5
        d = np.abs(dp + f * (dq - dp))
        was = out[rows]
        out[rows] = np.where(np.isnan(was) | (d < was), d, was)
    return out


def _band_widths(left, right, rows, off=None):
    """Each row's width, and its two half widths out from the midline. With
    `off` (how far right of the midline the body's middle really is), a row
    read on one side only is mirrored onto the other."""
    l, r = left, right
    if off is not None:
        l = np.where(np.isnan(left), right - 2 * off, left)
        r = np.where(np.isnan(right), left + 2 * off, right)
    width = np.where(rows, l + r, np.nan)
    return width, l, r


def _steadied(width, n=5):
    """Each row as the median of itself and its neighbours: one row's notch
    or spur in the mask is not the body's."""
    pad = n // 2
    padded = np.pad(width, pad, constant_values=np.nan)
    stack = np.stack([padded[i:i + len(width)] for i in range(n)])
    counts = np.isfinite(stack).sum(axis=0)
    with warnings.catch_warnings():
        # A row with no readable neighbours is an all-NaN slice, as expected.
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(stack, axis=0)
    return np.where(np.isfinite(width) & (counts >= 2), med, np.nan)


def _narrowest(left, right, rows, off):
    """(width, row index, left half, right half) of the band's narrowest row,
    or None when too little of the band can be read."""
    width, l, r = _band_widths(left, right, rows, off)
    if np.isfinite(width).sum() < MIN_ROWS * rows.sum():
        return None
    width = _steadied(width)
    if not np.isfinite(width).any():
        return None
    i = int(np.nanargmin(width))
    return float(width[i]), i, float(l[i]), float(r[i])


def _widest(left, right, rows):
    """The same for the band's widest row, read on both sides or not at all."""
    width, l, r = _band_widths(left, right, rows)
    if np.isfinite(width).sum() < MIN_ROWS * rows.sum():
        return None
    width = _steadied(width, 3)
    if not np.isfinite(width).any():
        return None
    i = int(np.nanargmax(width))
    return float(width[i]), i, float(l[i]), float(r[i])


def _angle(a, b):
    """Degrees between two vectors."""
    mag = float(np.linalg.norm(a) * np.linalg.norm(b))
    if mag < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / mag))))


def _towards(was, now, k):
    return was + k * (np.asarray(now) - was)


def _rounded(p):
    return [round(float(p[0]), 4), round(float(p[1]), 4)]
