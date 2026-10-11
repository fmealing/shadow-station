"""Rep counting: the algorithm the Shadow app ships, on the station's landmarks.

Copied from shadow-lab, which keeps it in parity with the app's Dart
(rep_counter.dart, body_signal.dart, intensity.dart) and is where every
constant here was measured. The reasoning lives there; this file keeps only
what runs. The lab config it matches is the champion, `bodycount_robust`.

- `LiveRepCounter` is the number on screen during the set. It is causal and
  follows one joint: the shoulder for a lateral raise.
- `analyse_set` is the count the summary shows, over the whole recording: the
  first principal component of the skeleton, resampled to 30 fps, zero-phase
  filtered, and counted at the working extremum (the top of a raise) with a
  minimum rep spacing locked to the set's own cadence.

Landmarks are MediaPipe's 33 pose points, the same layout as ML Kit's, as
fractions of the portrait canvas. `ASPECT` puts x back into pixel proportion
so an angle measured from fractions is a real angle.
"""

import warnings
from bisect import insort
from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

ASPECT = 720 / 1280  # canvas width / height

L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 23, 24, 25, 26, 27, 28

# (proximal, vertex, distal) per joint: left side, right side.
TRIPLES = {
    "elbow": ((L_SHOULDER, L_ELBOW, L_WRIST), (R_SHOULDER, R_ELBOW, R_WRIST)),
    "knee": ((L_HIP, L_KNEE, L_ANKLE), (R_HIP, R_KNEE, R_ANKLE)),
    "hip": ((L_SHOULDER, L_HIP, L_KNEE), (R_SHOULDER, R_HIP, R_KNEE)),
    "shoulder": ((L_HIP, L_SHOULDER, L_ELBOW), (R_HIP, R_SHOULDER, R_ELBOW)),
}
MIN_LIKELIHOOD = 0.5


@dataclass(frozen=True)
class Exercise:
    name: str
    joint: str
    # Where the lifter rests on the joint's angle: a lateral raise ends with
    # the arm down, at the minimum; a curl with the arm straight, at the
    # maximum.
    rest_at_max: bool


LATERAL_RAISE = Exercise("Lateral Raises", "shoulder", rest_at_max=False)
CURL = Exercise("Barbell Curl", "elbow", rest_at_max=True)


def joint_angle(lms, joint, left, aspect=ASPECT):
    """One side's angle in degrees from one frame's (x, y, visibility)
    landmarks, or None when any of its three points is not trusted."""
    a, v, b = (lms[i] for i in TRIPLES[joint][0 if left else 1])
    if min(a[2], v[2], b[2]) < MIN_LIKELIHOOD:
        return None
    ax, ay = (a[0] - v[0]) * aspect, a[1] - v[1]
    bx, by = (b[0] - v[0]) * aspect, b[1] - v[1]
    mag = np.sqrt((ax * ax + ay * ay) * (bx * bx + by * by))
    if mag < 1e-6:
        return None
    return float(np.degrees(np.arccos(np.clip((ax * bx + ay * by) / mag, -1, 1))))


# ---- the live counter ------------------------------------------------------

class LiveRepCounter:
    """LiveRepCounter from rep_counter.dart, frame by frame.

    Watches both sides through a 3.5 s warm-up and follows the one that
    travelled further for the rest of the set. Bands sit at fractions of the
    running 10th-90th percentile range of an EMA-smoothed angle, and a rep
    counts on entering the working band. The warm-up frames are replayed once
    the bands exist, so the number sits at 0 and then jumps to the true count.
    """

    SMOOTHING_TAU_S = 0.155
    WARMUP_S = 3.5
    BAND_PERCENTILE = 10.0
    ENTER, EXIT = 0.30, 0.35
    MIN_RANGE_DEG = 20.0

    def __init__(self, exercise):
        self.exercise = exercise
        self.count = 0
        self._state, self._prev = "NEUTRAL", None
        self._follow_left = None
        self._warmup = []
        self._first_t = None
        self._ema = self._last_t = self._t0 = None
        self._hist, self._pending = [], []

    def add(self, lms, t):
        """Feed one frame's 33 landmarks (or None) at time `t` in seconds."""
        j = self.exercise.joint
        left = None if lms is None else joint_angle(lms, j, True)
        right = None if lms is None else joint_angle(lms, j, False)
        self.add_sides(left, right, t)

    def add_sides(self, left, right, t):
        if self._first_t is None:
            self._first_t = t
        if self._follow_left is None:
            if t - self._first_t <= self.WARMUP_S:
                self._warmup.append((left, right, t))
                return
            self._decide_side()
        self._consume(self._pick(left, right), t)

    def finish(self):
        """Settle the side decision for a set shorter than the warm-up."""
        if self._follow_left is None:
            self._decide_side()

    def _decide_side(self):
        lefts = [l for l, _, _ in self._warmup if l is not None]
        rights = [r for _, r, _ in self._warmup if r is not None]
        self._follow_left = _travel(lefts) >= _travel(rights)
        for l, r, t in self._warmup:
            self._consume(self._pick(l, r), t)
        self._warmup = []

    def _pick(self, left, right):
        first, second = (left, right) if self._follow_left else (right, left)
        return first if first is not None else second

    def _consume(self, angle, t):
        if angle is None:
            return
        # A dropped frame does not advance the clock, so the frame after a
        # gap sees all of it and re-seeds instead of dragging a stale value.
        if self._ema is None or self._last_t is None:
            self._ema = angle
        else:
            dt = t - self._last_t
            a = 0.0 if dt <= 0 else 1 - np.exp(-dt / self.SMOOTHING_TAU_S)
            self._ema = a * angle + (1 - a) * self._ema
        self._last_t = t
        if self._t0 is None:
            self._t0 = t
        insort(self._hist, self._ema)
        self._pending.append(self._ema)
        if t - self._t0 < self.WARMUP_S:
            return

        lo = _sorted_percentile(self._hist, self.BAND_PERCENTILE)
        hi = _sorted_percentile(self._hist, 100 - self.BAND_PERCENTILE)
        rng = hi - lo
        if rng < self.MIN_RANGE_DEG:
            return
        hi_enter, hi_exit = lo + (1 - self.ENTER) * rng, lo + (1 - self.EXIT) * rng
        lo_enter, lo_exit = lo + self.ENTER * rng, lo + self.EXIT * rng
        # The band away from rest ticks the number: the top of a raise.
        count_high = not self.exercise.rest_at_max
        for y in self._pending:
            if self._state != "HIGH" and y > hi_enter:
                self._state = "HIGH"
                if count_high and self._prev == "LOW":
                    self.count += 1
                self._prev = "HIGH"
            if self._state == "HIGH" and y < hi_exit:
                self._state = "NEUTRAL"
            if self._state != "LOW" and y < lo_enter:
                self._state = "LOW"
                if not count_high and self._prev == "HIGH":
                    self.count += 1
                self._prev = "LOW"
            if self._state == "LOW" and y > lo_exit:
                self._state = "NEUTRAL"
        self._pending = []

def _travel(v):
    """Degrees between the 5th and 95th percentile, -1 with too few samples."""
    if len(v) < 8:
        return -1.0
    return float(np.percentile(v, 95) - np.percentile(v, 5))


def _sorted_percentile(s, q):
    m = len(s) - 1
    pos = q / 100 * m
    lo = int(pos)
    return s[lo] + (s[min(lo + 1, m)] - s[lo]) * (pos - lo)


# ---- the post-hoc pass -----------------------------------------------------

ANALYSIS_FPS = 30.0
MAX_GAP_S = 1.0          # wider gaps in the signal stay NaN
CUTOFF_HZ = 5.0

# The 12 landmarks the whole-body signal is built from: limbs and trunk, no
# face, which nods independently of the lift.
CORE = (L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST,
        L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)
DRIFT_HZ = 0.08          # hip motion slower than this is the camera, not the lift
PROMINENCE_FRAC = 0.35   # of the set's own range
DISTANCE_FRAC = 0.50     # of the set's own cadence
DISTANCE_FLOOR_S = 0.8
DISTANCE_CAP_S = 2.5
SEED_DISTANCE_S = 0.8
MAX_PASSES = 3
PROMINENCE_WINDOW_S = 6.0
PROMINENCE_WINDOW_MIN = 20
CADENCE_CV_LIMIT = 0.25


@dataclass
class SetAnalysis:
    count: int
    intensity: int | None      # 0-100, None under 3 measurable reps
    confident: bool            # body and joint agree, and the cadence is regular
    tracking_failed: bool
    times: np.ndarray          # seconds from the recording's start, 30 fps grid
    angle: np.ndarray          # counting joint's smoothed angle on `times`
    peaks: list                # index of each rep's working extremum
    rep_ends: list             # index of each rep's closing rest extremum
    reps: list                 # per-rep dicts: num, rom, t_con, vel, ...


def analyse_set(t, lms, exercise, aspect=ASPECT):
    """The authoritative count over a recorded set.

    `t` is (n,) seconds and `lms` is (n, 33, 3) x, y, visibility, with NaN
    rows for frames where nobody was tracked.
    """
    t = np.asarray(t, float)
    lms = np.asarray(lms, float)
    xy = lms[:, :, :2].transpose(1, 0, 2)          # (33, n, 2)
    vis = lms[:, :, 2].T                           # (33, n)

    left = _side_angles(xy, vis, exercise.joint, True, aspect)
    right = _side_angles(xy, vis, exercise.joint, False, aspect)
    anchor = left if _travel(left[~np.isnan(left)]) >= _travel(
        right[~np.isnan(right)]) else right
    sig = _movement_signal(xy, t, aspect, anchor)
    if np.all(np.isnan(sig)):
        sig = anchor  # never all twelve core points at once: count the joint

    grid, times = _resample(t, sig)
    if grid is None:
        return SetAnalysis(0, None, False, True, np.array([]), np.array([]),
                           [], [], [])
    sm = _smooth(grid, ANALYSIS_FPS)
    deg = _smooth(_resample_on(t, anchor, times), ANALYSIS_FPS)

    rest_at_max = exercise.rest_at_max
    peaks, cv = _cadence_peaks(sm, ANALYSIS_FPS, rest_at_max)
    ends = _rep_ends(sm, peaks, rest_at_max)
    reps = _rep_features(sm, peaks, ends, deg, ANALYSIS_FPS, rest_at_max)
    second, _ = _cadence_peaks(deg, ANALYSIS_FPS, rest_at_max)
    confident = (len(peaks) == len(second) and cv is not None
                 and cv <= CADENCE_CV_LIMIT)
    return SetAnalysis(
        count=len(peaks), intensity=set_intensity(reps), confident=confident,
        tracking_failed=bool(np.all(np.isnan(sm))), times=times - t[0],
        angle=deg, peaks=peaks, rep_ends=ends, reps=reps)


def set_intensity(reps):
    """computeSetIntensity() in intensity.dart: the % drop in concentric
    velocity across the set, from a line fitted through (rep number,
    velocity). 0 is steady, 100 is the largest slowdown."""
    if len(reps) < 3:
        return None
    x = np.array([r["num"] for r in reps], float)
    v = np.array([r["vel"] for r in reps], float)
    slope, inter = np.polyfit(x, v, 1)
    v0, v1 = slope * x[0] + inter, slope * x[-1] + inter
    if v0 == 0:
        return None
    fatigue = float(np.clip((v0 - v1) / v0 * 100, -100, 100))
    return int(round(np.clip(fatigue, 0, 100)))


def intensity_label(score):
    if score <= 15:
        return "Steady, consistent effort"
    if score <= 40:
        return "Building"
    if score <= 70:
        return "Hard, slowing down"
    return "Max intensity, pushed to the limit"


def _side_angles(xy, vis, joint, left, aspect):
    a_i, v_i, b_i = TRIPLES[joint][0 if left else 1]
    a, v, b = xy[a_i], xy[v_i], xy[b_i]
    conf = np.minimum(np.minimum(vis[a_i], vis[v_i]), vis[b_i])
    ax, ay = (a[:, 0] - v[:, 0]) * aspect, a[:, 1] - v[:, 1]
    bx, by = (b[:, 0] - v[:, 0]) * aspect, b[:, 1] - v[:, 1]
    mag = np.sqrt((ax * ax + ay * ay) * (bx * bx + by * by))
    with np.errstate(invalid="ignore", divide="ignore"):
        ang = np.degrees(np.arccos(np.clip((ax * bx + ay * by) / mag, -1, 1)))
    bad = (mag < 1e-6) | (conf < MIN_LIKELIHOOD) | np.isnan(conf)
    return np.where(bad, np.nan, ang)


def _smooth_track(y, window):
    """Zero-phase moving average with reflected edges."""
    n = len(y)
    w = max(3, int(window) | 1)
    if w >= n:
        return np.full(n, float(np.mean(y)))
    half = w // 2
    pad = np.concatenate([y[half:0:-1], y, y[-2:-half - 2:-1]])
    return np.convolve(pad, np.ones(w) / w, mode="valid")[:n]


def _normalised(xy, t, aspect):
    """The skeleton in body units: x back in pixel proportion, origin on a
    slow-moving hip midpoint (removes camera drift, keeps the lift), and the
    set's median shoulder-to-hip length as the unit."""
    xy = xy.astype(float).copy()
    xy[:, :, 0] *= aspect
    with warnings.catch_warnings():
        # A frame with nobody in it is an all-NaN slice, which is expected.
        warnings.simplefilter("ignore", RuntimeWarning)
        hip = np.nanmean(xy[[L_HIP, R_HIP]], axis=0)
        sho = np.nanmean(xy[[L_SHOULDER, R_SHOULDER]], axis=0)
        scale = np.nanmedian(np.hypot(*(sho - hip).T))
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0

    span = max(float(t[-1] - t[0]), 1e-6)
    ref = np.empty_like(hip)
    for d in (0, 1):
        y = hip[:, d]
        m = np.isfinite(y)
        if m.sum() < 4:
            ref[:, d] = np.nan_to_num(np.nanmedian(y) if m.any() else 0.0)
            continue
        filled = np.interp(np.arange(len(y)), np.flatnonzero(m), y[m])
        ref[:, d] = _smooth_track(filled, len(y) / span / DRIFT_HZ)
    return (xy - ref[None, :, :]) / scale


def _top_eigenvector(cov, iters=200, tol=1e-12):
    """Power iteration from a fixed start, so the result is deterministic."""
    n = cov.shape[0]
    v = np.ones(n) / np.sqrt(n)
    for _ in range(iters):
        w = cov @ v
        norm = float(np.linalg.norm(w))
        if norm <= 0:
            return v
        w = w / norm
        if float(np.linalg.norm(w - v)) < tol:
            return w
        v = w
    return v


def _movement_signal(xy, t, aspect, anchor):
    """The set's dominant movement as one number per frame: the skeleton's
    first principal component, its sign fixed to agree with the joint angle."""
    n = xy.shape[1]
    if n < 2:
        return np.full(n, np.nan)
    nx = _normalised(xy, t, aspect)
    X = nx[list(CORE)].transpose(1, 0, 2).reshape(n, -1)
    good = np.isfinite(X).all(axis=1)
    if good.sum() < 16:
        return np.full(n, np.nan)
    Xc = X[good] - X[good].mean(axis=0)
    cov = (Xc.T @ Xc) / max(1, len(Xc) - 1)
    proj = np.full(n, np.nan)
    proj[good] = Xc @ _top_eigenvector(cov)
    m = np.isfinite(proj) & np.isfinite(anchor)
    if m.sum() >= 8:
        a, b = proj[m], anchor[m]
        if a.std() > 0 and b.std() > 0 and float(np.corrcoef(a, b)[0, 1]) < 0:
            proj = -proj
    return proj


def _resample(t, v):
    """A uniform ANALYSIS_FPS grid, gaps over MAX_GAP_S left as NaN."""
    ok = ~np.isnan(v)
    t, v = t[ok], v[ok]
    if len(v) < 3 or not t[-1] > t[0]:
        return None, None
    n = int(round((t[-1] - t[0]) * ANALYSIS_FPS)) + 1
    if n < 3:
        return None, None
    grid = t[0] + np.arange(n) / ANALYSIS_FPS
    return _gapped_interp(t, v, grid), grid


def _resample_on(t, v, grid):
    ok = ~np.isnan(v)
    if ok.sum() < 2:
        return np.full(len(grid), np.nan)
    return _gapped_interp(t[ok], v[ok], grid)


def _gapped_interp(t, v, grid):
    out = np.interp(grid, t, v)
    idx = np.clip(np.searchsorted(t, grid) - 1, 0, len(t) - 2)
    gap = (t[idx + 1] - t[idx]) > MAX_GAP_S
    inside = (grid > t[idx]) & (grid < t[idx + 1])
    out[gap & inside] = np.nan
    return out


def _biquad_lowpass(fc, fps, q):
    w0 = 2 * np.pi * fc / fps
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    a0 = 1 + alpha
    return ([(1 - cw) / 2 / a0, (1 - cw) / a0, (1 - cw) / 2 / a0],
            [1.0, -2 * cw / a0, (1 - alpha) / a0])


def _butter4_lowpass(cutoff, fps):
    """Two cascaded RBJ biquads, as the Dart builds it. Not scipy's butter():
    the coefficients differ, and the difference lands on the set's edges."""
    fc = min(cutoff, fps / 2 * 0.99)
    b, a = np.array([1.0]), np.array([1.0])
    for q in (0.5411961, 1.3065630):
        bi, ai = _biquad_lowpass(fc, fps, q)
        b, a = np.convolve(b, bi), np.convolve(a, ai)
    return b, a


def _lfilter(b, a, x):
    """Direct form II transposed from zero initial conditions, like the Dart."""
    order = len(a)
    z = [0.0] * (order - 1)
    y = np.empty(len(x))
    for i, xi in enumerate(x):
        yi = b[0] * xi + z[0]
        for j in range(1, order - 1):
            z[j - 1] = b[j] * xi + z[j] - a[j] * yi
        z[order - 2] = b[order - 1] * xi - a[order - 1] * yi
        y[i] = yi
    return y


def _filtfilt(b, a, x):
    """Odd extension, pad 3*(order-1), which is the Dart's and not scipy's."""
    n = len(x)
    pad = min(3 * (max(len(b), len(a)) - 1), n - 1)
    if pad <= 0:
        return _lfilter(b, a, _lfilter(b, a, x)[::-1])[::-1]
    head = [2 * x[0] - x[i] for i in range(pad, 0, -1)]
    tail = [2 * x[n - 1] - x[n - i] for i in range(2, pad + 2)]
    ext = np.concatenate([head, x, tail])
    y = _lfilter(b, a, _lfilter(b, a, ext)[::-1])[::-1]
    return y[pad:pad + n]


def _smooth(x, fps, cutoff=CUTOFF_HZ):
    """Zero-phase 4th-order Butterworth, NaN bridged for the filter and then
    put back."""
    m = np.isnan(x)
    if m.all():
        return x
    f = x.copy()
    f[m] = np.interp(np.flatnonzero(m), np.flatnonzero(~m), f[~m])
    y = _filtfilt(*_butter4_lowpass(cutoff, fps), f)
    y[m] = np.nan
    return y


def _signal_range(sig, fps):
    """The median of the 2nd-98th percentile range over 6 s windows, so a
    walk up to the screen at the end of the set cannot inflate it. Falls back
    to the whole set's range when the set is too short for two windows."""
    finite = sig[np.isfinite(sig)]
    if len(finite) < 20:
        return 0.0
    whole = float(np.percentile(finite, 98) - np.percentile(finite, 2))
    w = max(1, int(round(PROMINENCE_WINDOW_S * fps)))
    if len(sig) < 2 * w:
        return whole
    ranges = []
    for start in range(0, len(sig) - w + 1, max(1, w // 2)):
        seg = sig[start:start + w]
        seg = seg[np.isfinite(seg)]
        if len(seg) >= PROMINENCE_WINDOW_MIN:
            ranges.append(np.percentile(seg, 98) - np.percentile(seg, 2))
    return float(np.median(ranges)) if ranges else whole


def _cadence_peaks(sig, fps, rest_at_max):
    """Working extrema of `sig`, the minimum spacing re-derived from the
    set's own median rep interval until the peaks stop moving.

    Returns (peak indices, coefficient of variation of the rep intervals or
    None).
    """
    rng = _signal_range(sig, fps)
    if rng <= 1e-9:
        return [], None
    target = sig * (-1.0 if rest_at_max else 1.0)
    filled = np.nan_to_num(target, nan=-1e18)
    prom = PROMINENCE_FRAC * rng
    peaks = list(find_peaks(filled, prominence=prom,
                            distance=max(1, int(round(SEED_DISTANCE_S * fps))))[0])
    for _ in range(MAX_PASSES - 1):
        if len(peaks) < 3:
            break
        cadence = float(np.median(np.diff(peaks)) / fps)
        dist = float(np.clip(DISTANCE_FRAC * cadence, DISTANCE_FLOOR_S,
                             DISTANCE_CAP_S))
        again = list(find_peaks(filled, prominence=prom,
                                distance=max(1, int(round(dist * fps))))[0])
        if again == peaks:
            break
        peaks = again
    cv = None
    if len(peaks) >= 3:
        gaps = np.diff(peaks) / fps
        if gaps.mean() > 0:
            cv = float(gaps.std() / gaps.mean())
    return [int(p) for p in peaks], cv


def _rep_ends(sig, peaks, rest_at_max):
    """The rest extremum closing each rep: the joint back where it started."""
    rest = sig * (1.0 if rest_at_max else -1.0)
    out = []
    for a, b in zip(peaks, list(peaks[1:]) + [len(sig)]):
        seg = rest[a:b]
        if np.any(np.isfinite(seg)):
            out.append(a + int(np.argmax(np.where(np.isfinite(seg), seg, -np.inf))))
    return out


def _rest_extremum(sig, lo, hi, rest_at_max):
    seg = sig[lo:hi]
    m = np.isfinite(seg)
    if not m.any():
        return -1
    return lo + int(np.argmax(np.where(m, seg if rest_at_max else -seg, -np.inf)))


def _rep_features(sm, peaks, ends, deg, fps, rest_at_max):
    """Per-rep concentric range of motion, duration and velocity.

    Each rep is rest, work, rest. The concentric runs towards the signal's
    maximum: start to work on a lateral raise, work to end on a curl. Events
    come from the body signal, degrees from the joint angle.
    """
    out = []
    for i, work in enumerate(peaks):
        start = (_rest_extremum(sm, 0, work, rest_at_max) if i == 0
                 else (ends[i - 1] if i - 1 < len(ends) else -1))
        end = ends[i] if i < len(ends) else -1
        if start < 0 or start >= work or end <= work:
            continue
        con_a, con_b = (work, end) if rest_at_max else (start, work)
        if np.isnan(deg[con_a]) or np.isnan(deg[con_b]):
            continue
        t_con = (con_b - con_a) / fps
        if t_con <= 0:
            continue
        rom = float(abs(deg[con_b] - deg[con_a]))
        out.append(dict(num=i + 1, rom=rom, t_con=t_con, vel=rom / t_con,
                        start=int(start), work=int(work), end=int(end)))
    return out

