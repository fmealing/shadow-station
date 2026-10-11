"""One set, from stepping into position to the analysed result.

The station's version of the app's set_tracking_screen. Nothing is recorded
until the lifter is in position, because a set recorded from a bad position
gives a confidently wrong count rather than an obvious failure:

PREROLL    the framing check. In position and holding still for HOLD_S
           starts a 3 s countdown, which a broken position calls off. Start,
           pressed by hand at the screen, is a 6 s countdown that nothing
           calls off, since the lifter has to walk back into shot.
COUNTDOWN
RECORDING  the live counter runs and every frame's landmarks are kept. Ends
           on Finish, or by itself once reps have been counted and none has
           come for `auto_finish_s`.
DONE       `analysis` holds the post-hoc result the summary shows.

While recording, `short` says when the reps keep stopping short of the lift's
full range (halfreps.py). They are counted all the same: `reps` is the live
counter's number until it lets short reps go by, and then the count that
takes them (halfreps.Uncounted).

Like press.py, nothing here knows about cameras: it takes the pose each frame
(33 landmarks as (x, y, visibility) canvas fractions, or None) and the time.
"""

import math

import numpy as np

from . import reps
from .halfreps import HalfReps, Uncounted

PREROLL, COUNTDOWN, RECORDING, DONE = "preroll", "countdown", "recording", "done"

HOLD_S = 1.2            # in position this long before the countdown starts
AUTO_COUNTDOWN_S = 3
MANUAL_COUNTDOWN_S = 6
LOST_S = 1.0            # nobody tracked this long mid-set shows a warning
MAX_SET_S = 180         # a set this long is finished: bounds the recording
# A set here starts and ends standing still: the recording starts when the
# countdown ends, auto-finish waits 10 s, and Finish means walking to the
# screen. In the app the lifter trims both off by hand, and the analysis was
# never measured with them on. So the station cuts them before the summary:
# - Standing still at the end lowers the range the rep threshold is measured
#   against, and the count can jump (7 to 21 on one lab curl capture with
#   10 s added). So nothing more than LIVE_TAIL_S past the live counter's
#   last rep is analysed at all.
# - Each rep's rest is looked for anywhere in the stillness next to it, which
#   stretches that rep and reads as fatigue (or as speeding up). Which end
#   does the harm depends on which half of the rep is timed: the lift of a
#   lateral raise runs from rest to the top, so it is the first rep and the
#   stillness before it; on a curl it is the last rep and the stillness
#   after. So the set is then cut as far before the first rep's top as the
#   lifter's other reps took to get there from rest, and as far past the last
#   rep's top as they took to get back (ONE_REP_S when there is only one).
# Over the lab's 32 MediaPipe lateral raise captures with 10 s of standing
# still added after and 1-4 s before, this keeps every count but one (which
# it gets right: 10 where the capture as recorded reads 9) and moves
# intensity by 3.3-4.5 points on average (4.9-7.7 cutting only the end, 5-8
# with nothing cut). On the 21 curl captures, 1.7-4.0 (22-25 with nothing cut).
LIVE_TAIL_S = 4.0
ONE_REP_S = 1.5

MIN_VIS = 0.5
EDGE = 0.04             # landmarks closer than this to the frame edge are clipped
# Shoulder-to-hip height, as a fraction of the canvas, below which the lifter
# is too far away to track well.
MIN_TORSO = 0.10

# Body parts the raise is counted from, with the landmarks (either side) that
# stand for each. Left and right are collapsed, as in the app's framing check:
# the far side is often hidden and still tracks well enough.
PARTS = {"shoulders": (11, 12), "elbows": (13, 14), "hands": (15, 16),
         "hips": (23, 24)}
# Shoulder, elbow and wrist of each arm, and the other shoulder, which says
# which way is out.
ARMS = ((11, 13, 15, 12), (12, 14, 16, 11))
# Each arm's angle on screen is smoothed this much, so the number reads
# steadily rather than flickering with the tracker's jitter.
ARM_TAU_S = 0.1
# At the elbow, an arm's best angle in a rep is the highest it held for this
# long, not the highest it touched. The angle is measured flat on the
# picture, and at the top of a curl the forearm comes over the upper arm
# towards the camera: for a frame or two they line up and read as folded
# shut, 180 degrees. A raise stays in the plane of the picture, and its
# highest is its highest.
HELD_S = 0.25


class Workout:
    def __init__(self, exercise=reps.LATERAL_RAISE, auto_finish_s=10.0):
        self.exercise = exercise
        self.auto_finish_s = auto_finish_s
        self.phase = PREROLL
        self.headline, self.cue = "STEP IN", "Step in front of the screen"
        self.warning = None
        # The end the last reps stopped short of, halfreps.TOP or BOTTOM,
        # while that is so, and which arms' (in the order of `arms`).
        self.short = None
        self.short_arms = [False, False]
        self.analysis = None
        self.frames = []            # (seconds into the set, landmarks or None)
        # The part of the recording that was analysed, once DONE: where it
        # starts, in seconds into the set, and how long it is.
        self.begin = 0.0
        self.duration = 0.0
        # Each arm, the one on the left of the screen first: its angle now,
        # and once DONE, its angle across the analysed set and its highest in
        # each rep.
        self.arms = [None, None]
        self.arm_angles = [np.array([]), np.array([])]
        self.arm_peaks = [[], []]
        self._arms_t = None

        self._good_since = None
        self._countdown_end = None
        self._guarded = False
        self._started = None
        self._seen = None
        self._live = reps.LiveRepCounter(exercise)
        self._half = HalfReps(exercise.joint)
        self._uncounted = Uncounted(exercise.rest_at_max)
        self._last_count = 0
        self._last_rep_t = None     # when the count last went up

    @property
    def reps(self):
        return self._uncounted.reps(self._live.count)

    @property
    def took_over(self):
        """Whether the live counter let short reps go by and they are being
        counted for it."""
        return self._uncounted.took_over

    def countdown(self, t):
        if self.phase != COUNTDOWN:
            return 0
        return max(1, math.ceil(self._countdown_end - t))

    def elapsed(self, t):
        return 0.0 if self._started is None else t - self._started

    def update(self, t, lms):
        if self.phase == DONE:
            return
        self._follow_arms(t, lms)
        if self.phase == RECORDING:
            self._record(t, lms)
            return

        self.headline, self.cue = framing(lms, self.exercise)
        good = self.headline is None
        if self.phase == PREROLL:
            if not good:
                self._good_since = None
            elif self._good_since is None:
                self._good_since = t
            if good:
                self.headline, self.cue = "HOLD IT", "Hold still"
                if t - self._good_since >= HOLD_S:
                    self._count_down(t, AUTO_COUNTDOWN_S, guarded=True)
        if self.phase == COUNTDOWN:
            if self._guarded and not good:
                self.cancel()
                return
            self.headline, self.cue = "GET SET", "Get into position"
            if t >= self._countdown_end:
                self.phase = RECORDING
                self._started = self._seen = t
                self._record(t, lms)

    def start(self, t):
        """Start by hand: a longer countdown, not called off by the framing."""
        if self.phase == PREROLL:
            self._count_down(t, MANUAL_COUNTDOWN_S, guarded=False)

    def cancel(self):
        if self.phase == COUNTDOWN:
            self.phase = PREROLL
            self._good_since = None
            self._countdown_end = None

    def finish(self, t):
        """End the set and analyse it. Harmless to call twice."""
        if self.phase != RECORDING:
            return self.analysis
        self.phase = DONE
        self._live.finish()
        t_s = np.array([f[0] for f in self.frames])
        lms = np.full((len(self.frames), 33, 3), np.nan)
        for i, (_, frame) in enumerate(self.frames):
            if frame is not None:
                lms[i] = frame
        if self._last_rep_t is not None:
            keep = t_s <= self._last_rep_t - self._started + LIVE_TAIL_S
            t_s, lms = t_s[keep], lms[keep]
        a = reps.analyse_set(t_s, lms, self.exercise)
        self.duration = float(t_s[-1]) if len(t_s) else 0.0
        if a.peaks:
            first, last = _without_stillness(a)
            keep = (t_s >= first) & (t_s <= last)
            if not keep.all():
                trimmed = reps.analyse_set(t_s[keep], lms[keep], self.exercise)
                # Trimming must not change the count; if it would, what was
                # cut was not idle and the whole recording stands.
                if trimmed.count == a.count:
                    a = trimmed
                    t_s, lms = t_s[keep], lms[keep]
                    self.begin = float(t_s[0])
                    self.duration = float(t_s[-1]) - self.begin
        self.analysis = a
        if len(a.times):
            self.arm_angles, self.arm_peaks = _arm_angles(t_s, lms, a, self.exercise.joint)
        return a

    def _follow_arms(self, t, lms):
        now = arm_angles(lms, self.exercise.joint)
        dt = 0.0 if self._arms_t is None else t - self._arms_t
        k = 1 - math.exp(-dt / ARM_TAU_S) if dt > 0 else 0.0
        self._arms_t = t
        self.arms = [None if v is None else v if was is None else was + k * (v - was)
                     for v, was in zip(now, self.arms)]

    def _count_down(self, t, seconds, guarded):
        self.phase = COUNTDOWN
        self._countdown_end = t + seconds
        self._guarded = guarded

    def _record(self, t, lms):
        rel = t - self._started
        self.frames.append((rel, lms))
        self._live.add(lms, rel)
        self.short = self._half.update(rel, self.arms)
        self.short_arms = self._half.arms
        live = self._live
        if live._ema is not None:
            q = live.BAND_PERCENTILE
            rng = (reps._sorted_percentile(live._hist, 100 - q)
                   - reps._sorted_percentile(live._hist, q))
            self._uncounted.update(live._ema, rng, live.count)
        if lms is not None:
            self._seen = t
        self.warning = ("Shadow lost you. Step back into view."
                        if t - self._seen > LOST_S else None)
        if self.reps != self._last_count:
            self._last_count, self._last_rep_t = self.reps, t
        idle = (self.auto_finish_s and self._last_rep_t is not None
                and t - self._last_rep_t >= self.auto_finish_s)
        if idle or rel >= MAX_SET_S:
            self.finish(t)


def arm_angles(lms, joint):
    """Each arm's angle this frame as a goniometer reads it (see `read`), the
    one on the left of the screen first, or None for an arm not tracked well
    enough. Ordered by where the arms are on screen, not by the tracker's
    left and right, so each arm's numbers can sit on its own side whether or
    not the camera is mirrored."""
    if lms is None:
        return None, None
    left = read(reps.joint_angle(lms, joint, True), joint)
    right = read(reps.joint_angle(lms, joint, False), joint)
    return (left, right) if lms[11][0] <= lms[12][0] else (right, left)


def read(angle, joint):
    """A joint's angle as a goniometer reads it: how far it has moved from
    where it rests. The shoulder's is the angle itself, the arm out from the
    trunk. An elbow is read from straight, so a curl's flexion goes up as the
    hand does: 0 with the arm straight, 140 or so at the top."""
    if joint != "elbow" or angle is None:
        return angle
    return 180.0 - angle


def _best(deg, joint):
    """An arm's best angle in one rep, or None when it was not tracked. At
    the shoulder that is the highest it reached. At the elbow it is the
    highest it held for HELD_S (see there)."""
    if not np.isfinite(deg).any():
        return None
    n = max(1, round(HELD_S * reps.ANALYSIS_FPS))
    if joint != "elbow" or len(deg) < n:
        return float(np.nanmax(deg))
    held = np.lib.stride_tricks.sliding_window_view(deg, n).min(axis=1)
    return float(np.nanmax(held)) if np.isfinite(held).any() else None


def _arm_angles(t, lms, a, joint):
    """Each arm's angle across an analysed set, on its 30 fps grid and
    smoothed as its counting angle is, and each arm's highest in every rep (a
    rep running from the end of the one before to its own end; see `_best`).
    The arm on the left of the screen first, as in `arm_angles`."""
    xy = lms[:, :, :2].transpose(1, 0, 2)
    vis = lms[:, :, 2].T
    left = reps._side_angles(xy, vis, joint, True, reps.ASPECT)
    right = reps._side_angles(xy, vis, joint, False, reps.ASPECT)
    first = xy[11, :, 0] <= xy[12, :, 0]
    grid = a.times + t[0]
    angles, peaks = [], []
    for arm in (np.where(first, left, right), np.where(first, right, left)):
        deg = read(reps._smooth(reps._resample_on(t, arm, grid), reps.ANALYSIS_FPS), joint)
        highest = []
        for i in range(len(a.peaks)):
            seg = deg[(a.rep_ends[i - 1] if i else 0):
                      (a.rep_ends[i] + 1 if i < len(a.rep_ends) else len(deg))]
            highest.append(_best(seg, joint))
        angles.append(deg)
        peaks.append(highest)
    return angles, peaks


def _without_stillness(a):
    """(first, last) seconds of an analysed set worth keeping: from as long
    before the first rep's top as the other reps took to rise to theirs, to
    as long after the last rep's top as they took to get back to rest."""
    fps = reps.ANALYSIS_FPS
    up = [(p - e) / fps for e, p in zip(a.rep_ends[:-1], a.peaks[1:])]
    down = [(e - p) / fps for p, e in zip(a.peaks[:-1], a.rep_ends[:-1])]
    first = a.times[a.peaks[0]] - (float(np.median(up)) if up else ONE_REP_S)
    last = a.times[a.peaks[-1]] + (float(np.median(down)) if down else ONE_REP_S)
    return first, last


def framing(lms, exercise=reps.LATERAL_RAISE):
    """(headline, cue) for what is wrong with the position, or (None, None)
    when it is good. The most useful fix comes first."""
    if lms is None:
        return "STEP IN", "Step in front of the screen"
    best = {name: max((lms[i] for i in idx), key=lambda p: p[2])
            for name, idx in PARTS.items()}
    clipped = [n for n, p in best.items()
               if not (EDGE <= p[0] <= 1 - EDGE and EDGE <= p[1] <= 1 - EDGE)]
    if clipped:
        sides_only = all(EDGE <= best[n][1] <= 1 - EDGE for n in clipped)
        if sides_only:
            return "MOVE TO THE MIDDLE", "Stand in the middle of the screen"
        return "STEP BACK", "Step back so your arms fit in view"
    hidden = [n for n, p in best.items() if p[2] < MIN_VIS]
    if hidden:
        return f"{hidden[0].upper()} HIDDEN", f"Keep your {hidden[0]} in view"
    # At the top of a raise the arms are out level with the shoulders, so
    # there has to be room for the hands either side, not just where they
    # hang now. A curl stays where it starts.
    hands = []
    if exercise.joint == "shoulder":
        hands = [x for x in (_hand_at_top(lms, *arm) for arm in ARMS) if x is not None]
    if any(not 0 <= x <= 1 for x in hands):
        if len(hands) == 2 and max(hands) - min(hands) <= 1:
            return "MOVE TO THE MIDDLE", "Stand in the middle of the screen"
        return "STEP BACK", "Step back so your arms fit in view"
    torso = abs((best["hips"][1]) - (best["shoulders"][1]))
    if torso < MIN_TORSO:
        return "STEP CLOSER", "Come a little closer"
    return None, None


def _hand_at_top(lms, shoulder, elbow, wrist, other):
    """Where a hand will be, as a canvas x fraction, with its arm straight out
    to the side, or None when the arm is not tracked well enough to say.

    That is as far as the hand can go, so the frame's own edge is the limit
    rather than EDGE: most raises stop short of it or keep a bend."""
    s, e, w, o = (lms[i] for i in (shoulder, elbow, wrist, other))
    if min(s[2], e[2], w[2]) < MIN_VIS:
        return None
    ax = reps.ASPECT
    arm = (math.hypot((e[0] - s[0]) * ax, e[1] - s[1])
           + math.hypot((w[0] - e[0]) * ax, w[1] - e[1]))
    return s[0] + math.copysign(arm / ax, s[0] - o[0])
