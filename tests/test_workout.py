import unittest

import numpy as np

from station import engine
from station.halfreps import BOTTOM, TOP
from station.reps import CURL, LATERAL_RAISE, joint_angle
from station.workout import (COUNTDOWN, DONE, HOLD_S, PREROLL, RECORDING,
                             Workout, arm_angles, framing, read)
from tests.lifts import (CURL_REST, CURL_TOP, FPS, RAISE_REST, RAISE_TOP,
                         curl_set, raise_set, standing)

DT = 1 / FPS


def run(w, frames, t=0.0):
    """Feed frames one per 1/30 s; return the time after the last."""
    for f in frames:
        w.update(t, f)
        t += DT
    return t


def start_recording(w):
    """Start by hand and stand still through the countdown."""
    w.start(0.0)
    t = 0.0
    while w.phase != RECORDING:
        t = run(w, [standing()], t)
    return t


class FramingTest(unittest.TestCase):
    def test_nobody(self):
        self.assertEqual(framing(None)[0], "STEP IN")

    def test_in_position(self):
        self.assertEqual(framing(standing()), (None, None))

    def test_too_close_clips_the_hands(self):
        self.assertEqual(framing(standing(scale=4))[0], "STEP BACK")

    def test_too_close_for_the_arms_to_go_out(self):
        # Everything is in view, but not the hands at the top of a raise.
        self.assertEqual(framing(standing(scale=1.2))[0], "STEP BACK")

    def test_a_curl_needs_no_room_for_the_arms_to_go_out(self):
        self.assertEqual(framing(standing(scale=1.2), CURL), (None, None))

    def test_off_to_one_side(self):
        lms = [(x + 0.2, y, v) for x, y, v in standing()]
        self.assertEqual(framing(lms)[0], "MOVE TO THE MIDDLE")

    def test_too_far(self):
        self.assertEqual(framing(standing(scale=0.4))[0], "STEP CLOSER")

    def test_hidden_arms(self):
        lms = standing()
        for i in (15, 16):
            lms[i] = (*lms[i][:2], 0.2)
        self.assertEqual(framing(lms)[0], "HANDS HIDDEN")


class WorkoutTest(unittest.TestCase):
    def test_holding_position_counts_down_then_records(self):
        w = Workout()
        t = run(w, [standing()] * int(HOLD_S * FPS + 2))
        self.assertEqual(w.phase, COUNTDOWN)
        self.assertEqual(w.countdown(t), 3)
        run(w, [standing()] * (3 * FPS + 2), t)
        self.assertEqual(w.phase, RECORDING)

    def test_countdown_called_off_when_you_leave(self):
        w = Workout()
        t = run(w, [standing()] * int(HOLD_S * FPS + 2))
        run(w, [None], t)
        self.assertEqual(w.phase, PREROLL)
        self.assertEqual(w.headline, "STEP IN")

    def test_start_by_hand_waits_longer_and_holds(self):
        w = Workout()
        w.start(0.0)
        t = run(w, [None] * (5 * FPS))  # walking back, out of shot
        self.assertEqual(w.phase, COUNTDOWN)
        run(w, [None] * (1 * FPS + 2), t)
        self.assertEqual(w.phase, RECORDING)

    def test_a_set_finishes_itself_and_is_analysed(self):
        w = Workout(auto_finish_s=10)
        t = start_recording(w)
        _, frames = raise_set(reps=6, rest_before=1, rest_after=0)
        t = run(w, frames, t)
        self.assertEqual(w.reps, 6)
        run(w, [standing()] * (11 * FPS), t)
        self.assertEqual(w.phase, DONE)
        self.assertEqual(w.analysis.count, 6)
        # The 10 s wait is trimmed off, so it can't read as fatigue.
        self.assertLess(w.begin + w.duration, w.frames[-1][0] - 5)
        self.assertLessEqual(w.analysis.intensity, 15)

    def test_stillness_before_the_first_rep_is_cut(self):
        # The countdown ends, and the lifter takes a few seconds to start.
        w = Workout(auto_finish_s=10)
        t = start_recording(w)
        _, frames = raise_set(reps=6, rest_before=4, rest_after=0)
        t = run(w, frames, t)
        run(w, [standing()] * (11 * FPS), t)
        a = w.analysis
        self.assertEqual(a.count, 6)
        self.assertGreater(w.begin, 3)
        # The first rep's lift is timed like the others, not with the wait.
        t_con = [r["t_con"] for r in a.reps]
        self.assertLess(t_con[0], 1.5 * np.median(t_con[1:]))
        self.assertAlmostEqual(a.times[-1], w.duration, delta=0.1)

    def test_finish_by_hand(self):
        w = Workout(auto_finish_s=0)
        t = start_recording(w)
        _, frames = raise_set(reps=5, rest_after=15)
        t = run(w, frames, t)
        self.assertEqual(w.phase, RECORDING)  # auto-finish is off
        a = w.finish(t)
        self.assertEqual(w.phase, DONE)
        self.assertEqual(a.count, 5)

    def test_each_arm_is_measured_on_its_own(self):
        # The arm on the right of the screen only gets two thirds of the way.
        w = Workout(auto_finish_s=10)
        t = start_recording(w)
        _, frames = raise_set(reps=6, other=2 / 3, rest_before=1, rest_after=0)
        t = run(w, frames, t)
        run(w, [standing()] * (11 * FPS), t)
        other_top = RAISE_REST + (RAISE_TOP - RAISE_REST) * 2 / 3
        top = [joint_angle(standing(raise_deg=RAISE_TOP, other_deg=other_top), "shoulder", side)
               for side in (True, False)]
        for arm in (0, 1):
            self.assertEqual(len(w.arm_peaks[arm]), 6)
            for peak in w.arm_peaks[arm]:
                self.assertAlmostEqual(peak, top[arm], delta=3)
            self.assertEqual(len(w.arm_angles[arm]), len(w.analysis.times))

    def test_arms_go_by_where_they_are_on_screen(self):
        lms = standing(raise_deg=90, other_deg=30)
        wide, low = arm_angles(lms, "shoulder")
        self.assertGreater(wide, low)
        mirrored = [(1 - x, y, v) for x, y, v in lms]
        swapped = arm_angles(mirrored, "shoulder")
        self.assertAlmostEqual(swapped[0], low)
        self.assertAlmostEqual(swapped[1], wide)

    def test_an_elbow_is_read_from_straight(self):
        self.assertEqual(read(170.0, "elbow"), 10.0)
        self.assertEqual(read(40.0, "elbow"), 140.0)
        self.assertEqual(read(40.0, "shoulder"), 40.0)
        self.assertIsNone(read(None, "elbow"))
        straight, bent = arm_angles(standing(elbow_deg=170, other_elbow=40), "elbow")
        self.assertAlmostEqual(straight, 10, delta=1)
        self.assertAlmostEqual(bent, 140, delta=1)

    def curls(self, **kw):
        """A set of curls through the station's set, and its summary."""
        w = Workout(CURL, auto_finish_s=10)
        t = start_recording(w)
        _, frames = curl_set(rest_before=1, rest_after=0, **kw)
        t = run(w, frames, t)
        run(w, [standing()] * (11 * FPS), t)
        self.assertEqual(w.phase, DONE)
        return w, engine._summary(w, 1, ["Left", "Right"])

    def test_a_set_of_curls(self):
        w, s = self.curls(reps=6)
        self.assertEqual(w.reps, 6)
        self.assertEqual(s["reps"], 6)
        top = 180 - CURL_TOP
        for arm in s["arms"]:
            self.assertTrue(arm["used"])
            self.assertAlmostEqual(arm["best"], top, delta=6)
        # The chart is flexion: near nothing at rest, up to the top.
        left = [v for v in s["chart"]["arms"][0] if v is not None]
        self.assertLess(min(left), 180 - CURL_REST + 8)
        self.assertGreater(max(left), top - 8)
        self.assertEqual(len(s["repSpeeds"]), 6)
        self.assertTrue(all(v and v > 0 for v in s["repSpeeds"]))

    def test_a_one_arm_set_leaves_the_other_arm_out(self):
        _, s = self.curls(reps=6, other=0.0)
        self.assertEqual(s["reps"], 6)
        self.assertEqual([arm["used"] for arm in s["arms"]], [True, False])
        self.assertAlmostEqual(s["arms"][0]["best"], 180 - CURL_TOP, delta=6)

    def said(self, exercise, frames):
        """A set through the station's set: the set, and each thing it said
        of the reps stopping short while it was recording."""
        w = Workout(exercise, auto_finish_s=10)
        t = start_recording(w)
        said = set()
        for f in frames + [standing()] * (11 * FPS):
            t = run(w, [f], t)
            if w.phase == RECORDING:
                said.add(w.short)
        self.assertEqual(w.phase, DONE)
        return w, said

    def test_half_reps_are_said_and_still_counted(self):
        for name, ex, make in (("raise", LATERAL_RAISE, raise_set), ("curl", CURL, curl_set)):
            with self.subTest(name):
                _, frames = make(reps=6, reach=0.5, rest_before=1, rest_after=0)
                w, said = self.said(ex, frames)
                self.assertEqual(said, {None, TOP})
                self.assertEqual(w.reps, 6)
                self.assertEqual(w.analysis.count, 6)

    def test_full_reps_have_nothing_said_of_them(self):
        for name, ex, make in (("raise", LATERAL_RAISE, raise_set), ("curl", CURL, curl_set)):
            with self.subTest(name):
                _, frames = make(reps=6, rest_before=1, rest_after=0)
                self.assertEqual(self.said(ex, frames)[1], {None})

    def test_reps_that_stop_short_of_the_bottom_are_said(self):
        for name, ex, make in (("raise", LATERAL_RAISE, raise_set), ("curl", CURL, curl_set)):
            with self.subTest(name):
                _, frames = make(reps=6, low=0.5, rest_before=1, rest_after=0)
                self.assertEqual(self.said(ex, frames)[1], {None, BOTTOM})

    def test_warns_when_you_leave_mid_set(self):
        w = Workout()
        t = start_recording(w)
        run(w, [None] * (2 * FPS), t)
        self.assertIsNotNone(w.warning)


if __name__ == "__main__":
    unittest.main()
