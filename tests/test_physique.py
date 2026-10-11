import unittest

import cv2
import numpy as np

from station.physique import (GONE_S, MEASURE_S, VERDICTS, Physique, measure,
                              verdict)

W, H = 720, 1280
FPS = 30
# The made-up figure's sizes, in pixels.
SHOULDERS, WAIST, ARM = 300, 180, 56
JOINTS = {11: (250, 400), 12: (470, 400), 23: (305, 760), 24: (415, 760)}


def figure(arms="out", shift=0):
    """(landmarks, mask) of a figure facing the camera: SHOULDERS wide across
    the shoulder joints and WAIST wide at its narrowest, with arms ARM thick.

    `arms` is "out" (hanging 25 degrees out from the body, with a gap),
    "against" (straight down, touching it), or "flexed" (upper arms level,
    forearms straight up). `shift` moves the whole figure that many pixels
    to the right."""
    mask = np.zeros((H, W), np.uint8)
    trunk = [(210, 380), (510, 380), (510, 430), (450, 634), (460, 760),
             (460, 1150), (260, 1150), (260, 760), (270, 634), (210, 430)]
    cv2.fillPoly(mask, [np.array(trunk, np.int32)], 255)
    cv2.circle(mask, (360, 300), 60, 255, -1)
    cv2.rectangle(mask, (335, 340), (385, 390), 255, -1)

    pts = dict(JOINTS)
    for shoulder, elbow, wrist, knuckle, out in ((11, 13, 15, 19, -1), (12, 14, 16, 20, 1)):
        sx, sy = JOINTS[shoulder]
        if arms == "flexed":
            e = (sx + out * 150, sy)
            w = (e[0], e[1] - 140)
        else:
            lean = np.radians(25 if arms == "out" else 0)
            e = (sx + out * 150 * np.sin(lean), sy + 150 * np.cos(lean))
            w = (e[0] + out * 140 * np.sin(lean), e[1] + 140 * np.cos(lean))
        e, w = (round(e[0]), round(e[1])), (round(w[0]), round(w[1]))
        cv2.line(mask, (sx, sy), e, 255, ARM)
        cv2.line(mask, e, w, 255, ARM - 6)
        pts[elbow], pts[wrist], pts[knuckle] = e, w, w
    lms = [(0.5, 300 / H, 1.0)] * 33
    for i, (x, y) in pts.items():
        lms[i] = ((x + shift) / W, y / H, 1.0)
    mask = np.roll(mask, shift, axis=1)
    return lms, mask.astype(np.float32) / 255


class MeasureTest(unittest.TestCase):
    def test_ratio_is_shoulders_over_waist(self):
        r = measure(*figure("out"))
        self.assertIsNone(r.headline)
        self.assertAlmostEqual(r.ratio, SHOULDERS / WAIST, delta=0.05)

    def test_lines_sit_on_the_edges(self):
        r = measure(*figure("out"))
        (ax, ay), (bx, by) = r.body.place(r.lines["shoulders"])
        self.assertAlmostEqual((bx - ax) * W, SHOULDERS, delta=6)
        self.assertAlmostEqual(ay * H, 400, delta=20)
        (ax, ay), (bx, by) = r.body.place(r.lines["waist"])
        self.assertAlmostEqual((bx - ax) * W, WAIST, delta=6)
        self.assertAlmostEqual(ay * H, 634, delta=20)

    def test_raised_arms_hide_the_shoulders(self):
        r = measure(*figure("flexed"))
        self.assertIsNone(r.ratio)
        self.assertEqual(r.headline, "ARMS DOWN")
        self.assertNotIn("shoulders", r.lines)
        # The waist is in the clear, and still read.
        self.assertIn("waist", r.lines)

    def test_arms_against_the_body_hide_the_waist(self):
        r = measure(*figure("against"))
        self.assertIsNone(r.ratio)
        self.assertEqual(r.headline, "ARMS OUT A LITTLE")

    def test_turned_away_is_not_measured(self):
        r = measure(*figure("out"), turn=30.0)
        self.assertIsNone(r.ratio)
        self.assertEqual(r.headline, "FACE THE SCREEN")
        self.assertEqual(r.lines, {})
        self.assertIsNotNone(r.body)    # there is still a body to draw on

    def test_hips_out_of_shot(self):
        lms, mask = figure("out")
        for i in (23, 24):
            lms[i] = (*lms[i][:2], 0.1)
        r = measure(lms, mask)
        self.assertEqual(r.headline, "STEP BACK")
        self.assertIsNone(r.body)

    def test_a_crease_in_the_mask_is_the_edge_of_the_trunk(self):
        # Arms against the body, but the mask is less sure of the line
        # between them, as the tracker's is.
        lms, mask = figure("against")
        for x in (450, 270):    # the trunk's edge at the waist
            cv2.line(mask, (x, 560), (x, 720), 0.6, 5)
        r = measure(lms, mask)
        self.assertIsNotNone(r.ratio)
        self.assertAlmostEqual(r.ratio, SHOULDERS / WAIST, delta=0.12)


class VerdictTest(unittest.TestCase):
    def test_every_number_earns_one(self):
        for ratio in (0.9, 1.0, 1.27, 1.28, 1.45, 1.61, 1.62, 2.4):
            self.assertIn(verdict(ratio)["image"], [image for _, image, _ in VERDICTS])

    def test_the_golden_ratio_is_the_top(self):
        self.assertEqual(verdict(1.62), verdict(2.0))
        self.assertNotEqual(verdict(1.61), verdict(1.62))

    def test_the_bands_run_best_first(self):
        least = [band[0] for band in VERDICTS]
        self.assertEqual(least, sorted(least, reverse=True))


class PhysiqueTest(unittest.TestCase):
    def run_frames(self, p, frame, seconds, t=0.0):
        for _ in range(round(seconds * FPS)):
            p.update(t, *frame)
            t += 1 / FPS
        return t

    def lines(self, p):
        return {l["id"]: (l["a"], l["b"]) for l in p.header()["lines"]}

    def test_stand_still_and_the_number_comes(self):
        p = Physique()
        self.assertEqual(p.headline, "STEP IN")
        t = self.run_frames(p, figure("out"), 0.5)
        h = p.header()
        self.assertEqual(h["headline"], "HOLD STILL")
        self.assertIsNone(h["ratio"])
        self.assertIsNone(h["verdict"])
        self.assertEqual(set(self.lines(p)), {"shoulders", "waist"})   # already on the body

        self.run_frames(p, figure("out"), MEASURE_S, t)
        h = p.header()
        self.assertAlmostEqual(h["ratio"], SHOULDERS / WAIST, delta=0.05)
        self.assertEqual(h["verdict"], verdict(h["ratio"]))
        self.assertIsNone(h["headline"])

    def test_the_number_is_measured_once(self):
        p = Physique()
        t = self.run_frames(p, figure("out"), MEASURE_S + 0.5)
        was = p.header()
        # Any pose after it, and time, leave it alone.
        t = self.run_frames(p, figure("flexed"), 2.0, t)
        self.run_frames(p, figure("against"), 2.0, t)
        h = p.header()
        self.assertEqual((h["ratio"], h["verdict"]), (was["ratio"], was["verdict"]))
        self.assertIsNone(h["headline"])

    def test_the_lines_stay_on_the_body_through_a_pose(self):
        p = Physique()
        t = self.run_frames(p, figure("out"), MEASURE_S + 0.5)
        standing = self.lines(p)
        # Flexed, the shoulders cannot be read, but their line is still there.
        t = self.run_frames(p, figure("flexed"), 1.0, t)
        self.assertEqual(self.lines(p), standing)
        # And when the body moves across, both go with it.
        self.run_frames(p, figure("flexed", shift=90), 1.0, t)
        for name, (a, b) in self.lines(p).items():
            for now, was in ((a, standing[name][0]), (b, standing[name][1])):
                self.assertAlmostEqual((now[0] - was[0]) * W, 90, delta=3)
                self.assertAlmostEqual(now[1], was[1], delta=0.005)

    def test_walking_in_is_not_standing_there(self):
        p = Physique()
        t = 0.0
        for i in range(round(2 * MEASURE_S * FPS)):     # 120 px a second
            p.update(t, *figure("out", shift=-200 + 4 * i))
            t += 1 / FPS
        self.assertIsNone(p.header()["ratio"])
        self.run_frames(p, figure("out"), MEASURE_S + 0.2, t)
        self.assertIsNotNone(p.header()["ratio"])

    def test_a_pose_passed_through_is_not_measured(self):
        p = Physique()
        t = self.run_frames(p, figure("out"), MEASURE_S / 2)
        t = self.run_frames(p, figure("flexed"), 1.0, t)
        self.assertEqual(p.headline, "ARMS DOWN")
        self.assertEqual(set(self.lines(p)), set())     # nothing drawn until it reads again
        t = self.run_frames(p, figure("out"), MEASURE_S * 0.75, t)
        self.assertIsNone(p.header()["ratio"])
        self.run_frames(p, figure("out"), MEASURE_S * 0.4, t)
        self.assertIsNotNone(p.header()["ratio"])

    def test_a_dropped_frame_or_two_does_not_start_the_wait_again(self):
        p = Physique()
        t = 0.0
        for i in range(round((MEASURE_S + 0.1) * FPS)):
            p.update(t, *(figure("flexed") if i in (10, 11, 20) else figure("out")))
            t += 1 / FPS
        self.assertIsNotNone(p.header()["ratio"])

    def test_turning_away_is_not_measured(self):
        p = Physique()
        t = self.run_frames(p, figure("out"), MEASURE_S * 0.6)
        # The same outline with the shoulder joints closed up, as a turn
        # shows them: not so far that the frame alone says side-on, but far
        # from how this person was standing.
        lms, mask = figure("out")
        for i, x in ((11, 275), (12, 445)):
            lms[i] = (x / W, *lms[i][1:])
        self.assertNotEqual(measure(lms, mask).headline, "FACE THE SCREEN")
        t = self.run_frames(p, (lms, mask), 0.5, t)
        self.assertEqual(p.headline, "FACE THE SCREEN")
        # Square again, the wait starts over.
        self.run_frames(p, figure("out"), MEASURE_S * 0.3, t)
        self.assertIsNone(p.header()["ratio"])

    def test_the_next_person_starts_fresh(self):
        p = Physique()
        t = self.run_frames(p, figure("out"), MEASURE_S + 0.5)
        t = self.run_frames(p, (None, None), 1.0, t)
        self.assertIsNotNone(p.header()["ratio"])     # a moment out of shot
        self.assertEqual(p.header()["lines"], [])
        self.run_frames(p, (None, None), GONE_S, t)
        self.assertIsNone(p.header()["ratio"])
        self.assertEqual(p.headline, "STEP IN")


if __name__ == "__main__":
    unittest.main()
