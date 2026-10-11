import unittest

import numpy as np

from station.reps import (CURL, LATERAL_RAISE, LiveRepCounter, analyse_set,
                          intensity_label, joint_angle)
from tests.lifts import (CURL_REST, CURL_TOP, RAISE_REST, RAISE_TOP,
                         curl_set, raise_set, standing)

# Each lift, with its made-up sets and how far its joint travels in a rep.
LIFTS = {"raise": (LATERAL_RAISE, raise_set, RAISE_TOP - RAISE_REST),
         "curl": (CURL, curl_set, CURL_REST - CURL_TOP)}


def analyse(exercise, times, frames):
    return analyse_set(times, np.array(frames, float), exercise)


class JointAngleTest(unittest.TestCase):
    def test_reads_the_elbow(self):
        for deg in (170, 90, 40):
            self.assertAlmostEqual(joint_angle(standing(elbow_deg=deg), "elbow", True), deg, 3)
            self.assertAlmostEqual(joint_angle(standing(elbow_deg=deg), "elbow", False), deg, 3)

    def test_reads_the_shoulder(self):
        # Measured from the hip, so the arm hanging down reads a few degrees
        # already; raising it adds exactly the raise.
        for left in (True, False):
            down = joint_angle(standing(raise_deg=0), "shoulder", left)
            for deg in (30, 60, 90):
                self.assertAlmostEqual(
                    joint_angle(standing(raise_deg=deg), "shoulder", left) - down, deg, 3)

    def test_untrusted_landmarks_give_nothing(self):
        self.assertIsNone(joint_angle(standing(vis=0.3), "shoulder", True))


class LiveCounterTest(unittest.TestCase):
    def count(self, exercise, times, frames):
        live = LiveRepCounter(exercise)
        for t, f in zip(times, frames):
            live.add(f, t)
        live.finish()
        return live.count

    def test_counts_a_set(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                self.assertEqual(self.count(ex, *make(reps=8)), 8)

    def test_standing_still_counts_nothing(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                self.assertEqual(self.count(ex, *make(reps=0, rest_before=10)), 0)

    def test_survives_dropped_frames(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                times, frames = make(reps=6)
                frames = [None if i % 7 == 0 else f for i, f in enumerate(frames)]
                self.assertEqual(self.count(ex, times, frames), 6)


class AnalyseSetTest(unittest.TestCase):
    def test_counts_a_set(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                a = analyse(ex, *make(reps=8))
                self.assertEqual(a.count, 8)
                self.assertTrue(a.confident)
                self.assertFalse(a.tracking_failed)
                self.assertEqual(len(a.rep_ends), 8)

    def test_angle_is_in_degrees(self):
        for name, (ex, make, travel) in LIFTS.items():
            with self.subTest(name):
                a = analyse(ex, *make(reps=5))
                self.assertAlmostEqual(np.nanmax(a.angle) - np.nanmin(a.angle), travel, delta=10)
                self.assertEqual(len(a.angle), len(a.times))

    def test_steady_set_is_low_intensity(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                a = analyse(ex, *make(reps=8, rest_before=1, rest_after=1))
                self.assertLessEqual(a.intensity, 15)

    def test_stillness_stretches_the_timed_rep(self):
        # Why the station trims the set before it is analysed (workout.py).
        # The lift of a raise runs from rest to the top, so the stillness
        # before the first rep stretches it; a curl is timed from the top
        # back to rest, so it is the stillness after the last.
        a = analyse(LATERAL_RAISE, *raise_set(reps=8, rest_before=6))
        self.assertGreater(a.reps[0]["t_con"], 2 * a.reps[-1]["t_con"])
        a = analyse(CURL, *curl_set(reps=8, rest_after=6))
        self.assertGreater(a.reps[-1]["t_con"], 2 * a.reps[0]["t_con"])

    def test_slowing_down_raises_intensity(self):
        for name, (ex, make, _) in LIFTS.items():
            with self.subTest(name):
                a = analyse(ex, *make(reps=8, rep_s=2.0, slowdown=0.35,
                                      rest_before=1, rest_after=1))
                self.assertEqual(a.count, 8)
                self.assertGreater(a.intensity, 40)

    def test_nobody_there(self):
        times = np.arange(90) / 30
        a = analyse_set(times, np.full((90, 33, 3), np.nan), LATERAL_RAISE)
        self.assertEqual(a.count, 0)
        self.assertTrue(a.tracking_failed)
        self.assertIsNone(a.intensity)

    def test_under_three_reps_has_no_intensity(self):
        self.assertIsNone(analyse(LATERAL_RAISE, *raise_set(reps=2)).intensity)

    def test_labels(self):
        self.assertEqual(intensity_label(0), "Steady, consistent effort")
        self.assertEqual(intensity_label(100), "Max intensity, pushed to the limit")


if __name__ == "__main__":
    unittest.main()
