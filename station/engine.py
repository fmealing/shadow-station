"""The station's main loop: camera in, tracking, presses, screens, frames out.

The engine owns all the state; the page is a view. It draws what the engine
publishes and reports where its buttons are, and the engine decides what a
hover on them does. That keeps the one press logic (press.py) in tested
Python, and a page reload loses nothing.

Screens:
- HOME: the hand/pose toggle and the apps.
- PICK: Shadow's exercises, to choose the set's from. Skipped when the
  station was told what to count.
- WORKOUT: one set of the exercise, from getting into position to Finish
  (workout.py).
- SUMMARY: the analysed set, with the recording replayed.
- PHYSIQUE: shoulders against waist, measured off the silhouette, and the
  meme the number earns (physique.py).
- MIRROR: the camera, full screen and as sharp as it comes.
- TIKTOK: the window itself goes over to TikTok (tiktok.py), which has its
  own cursor and Back; the station's page comes back after.
"""

import bisect
import math
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from . import camera, physique, reps
from .halfreps import BOTTOM, TOP
from .press import Button, OneEuro, Presser
from .swipe import FLICK, Debounce, Swipe, grabbing
from .tiktok import GONE, TikTok
from .tracking import HAND_EDGES, POSE_EDGES
from .workout import COUNTDOWN, DONE, PREROLL, RECORDING, Workout

HOME, WORKOUT, SUMMARY, MIRROR = "home", "workout", "summary", "mirror"
PICK = "pick"
PHYSIQUE = "physique"
TIKTOK = "tiktok"
# What a set can be of. The counter is the lab's; the words are the screen's:
# what the set is called, what its angle is, what the most of that angle is,
# and what to do about reps that keep stopping short at either end
# (halfreps.py). The lab's lateral raise is here twice: in a gym's words, and
# as shoulder abduction, its name in physiotherapy. That one has nothing for
# short reps and shows nothing: in a clinic, how far the arm gets is what is
# being measured.
EXERCISES = {
    "curl": {"counter": reps.CURL, "name": "Bicep curl",
             "tagline": "Bicep curls, counted live",
             "angle": "Elbow flexion", "peak": "Peak flexion",
             "short": {TOP: "Curl all the way up",
                       BOTTOM: "Lower all the way down"}},
    "raise": {"counter": reps.LATERAL_RAISE, "name": "Lateral raise",
              "tagline": "Lateral raises, counted live",
              "angle": "Shoulder angle", "peak": "Peak raise",
              "short": {TOP: "Raise to shoulder height",
                        BOTTOM: "Lower all the way down"}},
    "abduction": {"counter": reps.LATERAL_RAISE, "name": "Shoulder abduction",
                  "tagline": "Shoulder abduction, measured live",
                  "angle": "Shoulder abduction", "peak": "Peak abduction"},
}
# The exercises Shadow offers, in the order they are listed. The clinic's set
# is not one of them: a clinic asks for it by name, and is then asked nothing.
PICKS = ("curl", "raise")
# What reps that keep stopping short are called, over the exercise's line
# about what to do. The page shows the lifter the rest: see `_live`.
HALF_REPS = "HALF REPS"
# An arm that got this far, in degrees and as a share of the other's best,
# was part of the set. In a one-arm set the other hangs still, and its
# numbers would only be noise beside the working arm's.
USED_MIN_DEG, USED_SHARE = 25, 0.4
TOGGLE = "toggle"
W, H = camera.CANVAS_W, camera.CANVAS_H
# After a press, nothing more can be pressed until the cursor has moved this
# far or been lost. A press usually changes the screen, and a hand left where
# it was would otherwise dwell straight onto whatever button is now there.
REARM_PX = 60
JPEG_QUALITY = 70
MIRROR_QUALITY = 85
PHYSIQUE_QUALITY = 82
# The set is replayed on the summary from these smaller frames.
REPLAY_W, REPLAY_H = 405, 720
REPLAY_QUALITY = 70
# The page shows "Opening TikTok" this long before the window goes over.
TIKTOK_OPEN_S = 0.35
# After a swipe, TikTok clicks are ignored this long: a flick up carries the
# cursor with it, and the hand can pause long enough to click.
SWIPE_QUIET_S = 1.0


class Engine:
    def __init__(self, source, trackers, server, mode="hand", dwell_s=0.8,
                 toggle_hold_s=0.5, auto_finish_s=10.0, chrome=None,
                 home_url=None, swipe=FLICK, tiktok=True, exercise=None):
        self.source = source
        # Which arm is which, in the order they appear on screen: a mirrored
        # camera shows each arm on its own side.
        self.arm_names = (["Left", "Right"] if getattr(source, "mirrored", True)
                          else ["Right", "Left"])
        self.trackers = trackers
        # The pose tracker that also gives the silhouette, for Physique.
        self._body = trackers.get("body", trackers["pose"])
        # Told what to count, the station counts that and offers nothing.
        # Otherwise the exercise is whichever was picked last.
        self.picks = () if exercise else PICKS
        self.exercise = EXERCISES[exercise] if exercise else None
        self.server = server
        # The station's window, which TikTok takes over; None without one.
        self.chrome = chrome
        self.tiktok = tiktok and chrome is not None
        self.home_url = home_url
        self.mode = mode
        self.toggle_hold_s = toggle_hold_s
        self.auto_finish_s = auto_finish_s
        self.running = True

        self.screen = HOME
        self.set_no = 0
        self.workout = None
        self._short = None         # the set's `short`, as last logged
        self._took_over = False    # and whether its count had taken over
        self.summary = None
        self.physique = None
        self._mode_before = None   # the mode Physique was opened from
        self._replay = []          # (seconds into the set, jpeg, points, arms)
        self._replay_start = 0.0

        self.presser = Presser(dwell_s=dwell_s)
        self.dwell_s = dwell_s
        self._smooth = OneEuro()
        self._buttons = []
        self._rearm = None
        self._t0 = time.monotonic()
        self._last = self._t0
        self._last_ms = -1
        self._mirror_header = None
        self._tiktok = None
        self._tiktok_at = 0.0
        self._grip = Debounce()
        self._swipe = Swipe(swipe)
        self._swiped = -1e9
        self.fps = 0.0
        # The hand tracker's own thread, so it can run beside the pose's.
        self._side = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hand")

    def close(self):
        """Wait out a hand still being tracked, before the trackers close."""
        self._side.shutdown()

    def run(self, keep_going=lambda: True):
        self._publish_state()
        while self.running and keep_going():
            if not self.step():
                print("camera stopped sending frames")
                break

    def step(self):
        full = self.source.read()
        if full is None:
            return False
        if self.screen == MIRROR and self._mirror_header is not None:
            # Sent before tracking, with the last frame's cursor: in a mirror,
            # the delay is what you notice.
            self.server.publish_frame(self._mirror_header,
                                      _jpeg(full, MIRROR_QUALITY))
        frame = camera.to_canvas(full)
        now = time.monotonic()
        t = now - self._t0
        if now > self._last:
            self.fps = 0.9 * self.fps + 0.1 / (now - self._last)
        self._last = now
        self._drain_inbox(t)

        # VIDEO mode needs strictly increasing timestamps.
        self._last_ms = max(int(t * 1000), self._last_ms + 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # A set in hand mode needs both trackers. One after the other they
        # took 30 of the 33 ms between camera frames; side by side, 18.
        handing = None
        if self.mode == "hand":
            handing = self._side.submit(self.trackers["hand"].process,
                                        rgb, self._last_ms)
        pose = None
        if self.screen == PHYSIQUE:
            pose = self._body.process(rgb, self._last_ms)
        elif self.screen == WORKOUT or self.mode == "pose":
            pose = self.trackers["pose"].process(rgb, self._last_ms)
        hand = None if handing is None else handing.result()
        pointing = hand if self.mode == "hand" else pose

        aim = None
        if pointing is None or pointing.pointer is None:
            self._smooth.reset()
        else:
            aim = self._smooth(t, pointing.pointer)
        cursor = None if aim is None else (aim[0] * W, aim[1] * H)
        if self.screen == TIKTOK:
            self._run_tiktok(t, aim, cursor, hand)
            return True
        if self._rearm is not None and (
                cursor is None or math.dist(cursor, self._rearm) > REARM_PX):
            self._rearm = None
        pressed = self.presser.update(
            t, None if self._rearm is not None else cursor, self._buttons)
        if pressed is not None:
            self._rearm = cursor
            print(f"{t:8.2f}s  press {pressed.id:<8} after "
                  f"{self.presser.pressed_after:.2f}s hovering")
            self.server.publish({"type": "pressed", "id": pressed.id})
            self._act(pressed.id, t)

        header = {"screen": self.screen, "fps": round(self.fps, 1),
                  "cursor": None if aim is None else [round(aim[0], 4),
                                                      round(aim[1], 4)],
                  "hover": self._hover()}
        if self.screen == WORKOUT:
            w = self.workout
            w.update(t, None if pose is None else pose.landmarks)
            if w.short != self._short:
                self._short = w.short
                if w.short:
                    print(f"{t:8.2f}s  half reps: stopping short at the {w.short}")
            if w.took_over and not self._took_over:
                self._took_over = True
                print(f"{t:8.2f}s  half reps: counting the ones the live "
                      f"counter let by ({w.reps}, where it has {w._live.count})")
            header["live"] = self._live(t)
            header["skeletons"] = _skeletons(pose, hand)
            header["arms"] = _degrees(w.arms)
            if w.phase in (RECORDING, DONE) and w.frames:
                small = cv2.resize(frame, (REPLAY_W, REPLAY_H),
                                   interpolation=cv2.INTER_AREA)
                self._replay.append((w.frames[-1][0], _jpeg(small, REPLAY_QUALITY),
                                     _points(pose), header["arms"]))
            if w.phase == DONE:
                self._to_summary(t)
        if self.screen == MIRROR:
            self._mirror_header = header
            return True
        if self.screen == SUMMARY and self._replay:
            header["skeletons"], jpeg = self._replay_frame(t, header)
        elif self.screen == PHYSIQUE:
            p = self.physique
            lms, mask, turn = ((None, None, None) if pose is None
                               else (pose.landmarks, pose.mask, pose.turn))
            measured = p.ratio is not None
            p.update(t, lms, mask, turn)
            if p.ratio is not None and not measured:
                print(f"{t:8.2f}s  physique: {p.ratio:.2f} ({p.verdict['image']})")
            header["physique"] = p.header()
            jpeg = _jpeg(frame, PHYSIQUE_QUALITY)
        else:
            if self.screen in (HOME, PICK):
                header["skeletons"] = _skeletons(pose, hand)
            jpeg = _jpeg(frame, JPEG_QUALITY)
        self.server.publish_frame(header, jpeg)
        return True

    # ---- what a press or a key does ---------------------------------------

    def _act(self, what, t):
        w = self.workout
        if what == TOGGLE:
            self.mode = "pose" if self.mode == "hand" else "hand"
            self._mode_before = None
            self._smooth.reset()
            print(f"{t:8.2f}s  mode: {self.mode}")
            self._publish_state()
        elif self.screen == HOME and what == "shadow":
            if self.picks:
                self._go(PICK)
            else:
                self._to_workout()
        elif self.screen == PICK and what in self.picks:
            self.exercise = EXERCISES[what]
            self._to_workout()
        elif self.screen == HOME and what == "mirror":
            self._go(MIRROR)
        elif self.screen == HOME and what == "physique":
            # You pose from further back than a fingertip can be tracked, and
            # the pose is being tracked anyway: pointing with it saves
            # running the hand tracker, a third of each frame. Home gets its
            # own mode back, unless it is changed while posing.
            self._mode_before = self.mode
            if self.mode == "hand":
                self.mode = "pose"
                self._smooth.reset()
            self.physique = physique.Physique()
            self._go(PHYSIQUE)
        elif self.screen == HOME and what == "tiktok" and self.tiktok:
            if self.mode == "pose":
                # TikTok is pointed at with a fingertip, and flicked by hand.
                self.mode = "hand"
                self._smooth.reset()
            self._tiktok_at = t + TIKTOK_OPEN_S
            self._go(TIKTOK)
        elif (self.screen, what) in ((WORKOUT, "back"), (SUMMARY, "done"),
                                     (MIRROR, "back"), (PHYSIQUE, "back"),
                                     (PICK, "back")):
            if self.screen == PHYSIQUE and self._mode_before not in (None, self.mode):
                self.mode = self._mode_before
                self._smooth.reset()
            self._mode_before = None
            self.set_no = 0
            # Back from a set is to where its exercise was picked.
            self._go(PICK if self.screen == WORKOUT and self.picks else HOME)
        elif self.screen == WORKOUT and what == "start":
            w.start(t)
        elif self.screen == WORKOUT and what == "cancel":
            w.cancel()
        elif self.screen == WORKOUT and what == "finish":
            if w.phase == RECORDING:
                w.finish(t)
                self._to_summary(t)
        elif self.screen == SUMMARY and what == "next":
            self._to_workout()

    def _key(self, key, t):
        """Keyboard stand-ins for the buttons, for testing at a desk."""
        if key == "t":
            self._act(TOGGLE, t)
        elif key == "q":
            self.running = False
        elif key == "Escape":
            self._act("done" if self.screen == SUMMARY else "back", t)
        elif key == "m" and self.screen == HOME:
            self._act("mirror", t)
        elif key == "p" and self.screen == HOME:
            self._act("physique", t)
        elif self.screen == PICK:
            # The exercises, numbered down the screen.
            pick = dict(zip("123456789", self.picks)).get(key)
            if pick:
                self._act(pick, t)
        elif key == "Enter":
            if self.screen == HOME:
                self._act("shadow", t)
            elif self.screen == SUMMARY:
                self._act("next", t)
            elif self.screen == PHYSIQUE:
                self.physique.reset()   # measure again from nothing
            elif self.screen != WORKOUT:
                pass
            elif self.workout.phase == PREROLL:
                self._act("start", t)
            elif self.workout.phase == COUNTDOWN:
                self._act("cancel", t)
            elif self.workout.phase == RECORDING:
                self._act("finish", t)

    # ---- screens ------------------------------------------------------------

    def _go(self, screen):
        self.screen = screen
        self._mirror_header = None
        # The page reports the new screen's buttons; until it does, the old
        # ones must not be pressable.
        self._buttons = []
        print(f"screen: {screen}")
        self._publish_state()

    def _run_tiktok(self, t, aim, cursor, hand):
        if self._tiktok is None:
            if t < self._tiktok_at:
                return
            try:
                self._tiktok = TikTok(self.chrome, self.home_url, self.dwell_s)
            except GONE as e:
                print(f"could not open TikTok: {e}")
                self._go(HOME)
                return
        fist = self._grip.update(t, grabbing(None if hand is None else hand.fingers))
        way = self._swipe.update(t, None if hand is None else hand.motion, fist)
        if way is not None:
            self._swiped = t
            print(f"{t:8.2f}s  swipe {way}")
            self._tiktok.swipe(way)
        if not self._tiktok.update(t, aim, quiet=t - self._swiped < SWIPE_QUIET_S):
            print(f"{t:8.2f}s  TikTok closed")
            self._tiktok = None
            self._rearm = cursor
            self._go(HOME)

    def _to_workout(self):
        self.workout = Workout(self.exercise["counter"], self.auto_finish_s)
        self._short, self._took_over = None, False
        self._replay = []
        self._go(WORKOUT)

    def _to_summary(self, t):
        self.set_no += 1
        self.summary = _summary(self.workout, self.set_no, self.arm_names)
        self._replay_start = t
        a = self.workout.analysis
        peaks = ", ".join(f"{arm['name'].lower()} {arm['best']}°"
                          for arm in self.summary["arms"] if arm["best"] is not None)
        print(f"{t:8.2f}s  set {self.set_no}, {self.exercise['name'].lower()}: "
              f"{a.count} reps "
              f"(live {self.workout.reps}), peak {peaks or '-'}, "
              f"fatigue {a.intensity}, "
              f"{'confident' if a.confident else 'not confident'}")
        self._go(SUMMARY)

    def _publish_state(self):
        self.server.publish({
            "type": "state", "screen": self.screen, "mode": self.mode,
            "apps": ["shadow", "physique", "mirror"]
                    + (["tiktok"] if self.tiktok else []),
            "setNo": self.set_no,
            "exercise": _words(self.exercise),
            "exercises": [{"id": k, **_words(EXERCISES[k])} for k in self.picks],
            "arms": self.arm_names,
            "dwellS": self.dwell_s, "toggleHoldS": self.toggle_hold_s,
            "summary": self.summary if self.screen == SUMMARY else None,
            "edges": {"pose": POSE_EDGES, "hand": HAND_EDGES},
        })

    # ---- messages from the page ------------------------------------------

    def _drain_inbox(self, t):
        while not self.server.inbox.empty():
            msg = self.server.inbox.get_nowait()
            if msg.get("type") == "key":
                self._key(msg.get("key"), t)
            elif msg.get("type") == "layout" and msg.get("screen") == self.screen:
                try:
                    self._buttons = [self._button(b) for b in msg["buttons"]]
                except (KeyError, TypeError, ValueError):
                    print(f"ignored a malformed layout: {msg}")

    def _button(self, b):
        """A button the page reported, its rect from stage fractions to
        canvas pixels."""
        x, y, w, h = (float(v) * s for v, s in zip(b["rect"], (W, H, W, H)))
        return Button(str(b["id"]), str(b["id"]),
                      (round(x), round(y), round(w), round(h)),
                      hold_s=self.toggle_hold_s if b.get("hold") else None)

    # ---- what goes in a frame --------------------------------------------

    def _hover(self):
        h = self.presser.hovered
        if h is None:
            return None
        return {"id": h.id, "p": round(self.presser.progress, 3)}

    def _live(self, t):
        w = self.workout
        # Reps stopping short are shown on the lifter, who is too far back
        # to read: the page draws where each of those arms should get to, so
        # it is told which end and which arms. The words are for whoever is
        # watching. Losing the lifter comes first: nothing is measured then.
        short = None
        words = self.exercise.get("short")
        if w.short and words and not w.warning:
            short = {"end": w.short, "arms": w.short_arms,
                     "headline": HALF_REPS, "cue": words[w.short]}
        return {"phase": w.phase, "countdown": w.countdown(t),
                "headline": w.headline, "cue": w.cue, "warning": w.warning,
                "short": short,
                "reps": w.reps, "elapsed": round(w.elapsed(t), 1)}

    def _replay_frame(self, t, header):
        """The analysed part of the set on a loop, at the speed it was
        recorded."""
        w = self.workout
        dur = max(w.duration, 1e-3)
        pos = w.begin + (t - self._replay_start) % dur
        i = max(0, bisect.bisect_right(self._replay, pos,
                                       key=lambda r: r[0]) - 1)
        rel, jpeg, points, header["arms"] = self._replay[i]
        # On the summary's chart, whose clock starts where the analysis does.
        header["replay"] = {"t": round(max(0.0, rel - w.begin), 2),
                            "dur": round(dur, 2)}
        skel = [{"edges": "pose", "points": points}] if points else []
        return skel, jpeg


def _summary(workout, set_no, arm_names):
    """The analysed set, as the page's summary screen needs it. Each arm's
    numbers are in the order the arms appear on screen, with their names."""
    a = workout.analysis
    arms = []
    for name, peaks in zip(arm_names, workout.arm_peaks):
        seen = [p for p in peaks if p is not None]
        arms.append({"name": name, "peaks": _degrees(peaks),
                     "best": round(max(seen)) if seen else None,
                     "mean": round(float(np.mean(seen))) if seen else None})
    top = max((arm["best"] for arm in arms if arm["best"] is not None), default=None)
    for arm in arms:
        arm["used"] = (arm["best"] is not None
                       and arm["best"] >= max(USED_MIN_DEG, USED_SHARE * top))
    # How fast each rep was lifted, in degrees a second: the bars the fatigue
    # score is a line through.
    speeds = {r["num"]: round(r["vel"]) for r in a.reps}
    return {
        "setNo": set_no,
        "reps": a.count,
        "liveReps": workout.reps,
        "arms": arms,
        # The intensity score is how much the lift slowed from the first rep
        # to the last, as a percentage: fatigue, in a clinic's words.
        "fatigue": a.intensity,
        "fatigueLabel": (_fatigue_label(a.intensity)
                         if a.intensity is not None else "Needs 3 reps or more"),
        "confident": a.confident,
        "trackingFailed": a.tracking_failed,
        "duration": round(workout.duration, 2),
        "chart": {"t": [round(float(v), 3) for v in a.times],
                  "arms": [[None if np.isnan(v) else round(float(v), 1) for v in deg]
                           for deg in workout.arm_angles]},
        "repEnds": [round(float(a.times[i]), 3) for i in a.rep_ends],
        "repSpeeds": [speeds.get(n) for n in range(1, a.count + 1)],
    }


def _words(exercise):
    """An exercise as the page needs it: its words, and the joint its angle
    is measured at. None before one has been picked."""
    if exercise is None:
        return None
    return {"joint": exercise["counter"].joint,
            **{k: exercise[k] for k in ("name", "tagline", "angle", "peak")}}


def _fatigue_label(score):
    """What the slowdown means, on the app's intensity bands."""
    if score <= 15:
        return "Little or no slowing"
    if score <= 40:
        return "Some slowing"
    if score <= 70:
        return "Clear slowing"
    return "Marked slowing"


def _degrees(values):
    return [None if v is None else round(v) for v in values]


def _points(tracked):
    if tracked is None or not tracked.points:
        return []
    return [[round(x, 4), round(y, 4)] for x, y in tracked.points]


def _skeletons(*tracked):
    out = []
    for tr in tracked:
        if tr is not None and tr.points:
            out.append({"edges": "hand" if tr.edges is HAND_EDGES else "pose",
                        "points": _points(tr)})
    return out


def _jpeg(img, quality):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
