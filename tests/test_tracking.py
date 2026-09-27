import unittest

from station.tracking import (FINGERS, HAND_REACH, fingers_up, pose_pointer,
                              reach_to_screen)

W, H = 720, 1280  # the portrait canvas
SHOULDER_HALF = 0.1  # frame fractions; shoulder width = 144 px
UNIT_Y = 2 * SHOULDER_HALF * W / H  # one shoulder width, as a fraction of H


def body(hand_y, hand_x=0.5, hips=True, shoulder_half=SHOULDER_HALF):
    """33 pose landmarks as (x, y, visibility): shoulders at y=0.4, hips one
    shoulder width below, one hand at (hand_x, hand_y), the other hanging by
    the hip."""
    lms = [(0.5, 0.5, 0.0)] * 33
    lms[11] = (0.5 + shoulder_half, 0.4, 1.0)
    lms[12] = (0.5 - shoulder_half, 0.4, 1.0)
    for i in (15, 17, 19):
        lms[i] = (hand_x, hand_y, 1.0)
    for i in (16, 18, 20):
        lms[i] = (0.4, 0.4 + 1.2 * UNIT_Y, 1.0)
    vis = 1.0 if hips else 0.0
    lms[23] = (0.56, 0.4 + UNIT_Y, vis)
    lms[24] = (0.44, 0.4 + UNIT_Y, vis)
    return lms


class ReachTest(unittest.TestCase):
    def test_box_corners_are_screen_corners(self):
        x0, y0, x1, y1 = HAND_REACH
        self.assertEqual(reach_to_screen((x0, y0), HAND_REACH), (0.0, 0.0))
        self.assertEqual(reach_to_screen((x1, y1), HAND_REACH), (1.0, 1.0))

    def test_small_overshoot_clamps(self):
        self.assertEqual(reach_to_screen((-0.05, 0.5), (0, 0, 1, 1)), (0.0, 0.5))

    def test_far_outside_is_not_pointing(self):
        self.assertIsNone(reach_to_screen((-0.5, 0.5), (0, 0, 1, 1)))

    def test_fingertip_at_frame_top_reaches_top_bar(self):
        _, y = reach_to_screen((0.5, 0.02), HAND_REACH)
        self.assertEqual(y, 0.0)


class PosePointerTest(unittest.TestCase):
    def test_raised_hand_reaches_the_top(self):
        _, y = pose_pointer(body(hand_y=0.4 - 1.4 * UNIT_Y), W, H)
        self.assertLess(y, 0.1)

    def test_hand_at_chest_is_low_on_screen(self):
        _, y = pose_pointer(body(hand_y=0.4 + 0.5 * UNIT_Y), W, H)
        self.assertGreater(y, 0.7)

    def test_picks_the_higher_hand(self):
        x, _ = pose_pointer(body(hand_y=0.2, hand_x=0.65), W, H)
        self.assertGreater(x, 0.5)

    def test_same_gesture_same_point_at_any_distance(self):
        # Halve the body's size in frame (twice as far away): the same
        # gesture, in body terms, must land on the same screen point.
        near = pose_pointer(body(hand_y=0.4 - 1.0 * UNIT_Y,
                                 hand_x=0.6), W, H)
        far_lms = [(0.5 + (x - 0.5) / 2, 0.4 + (y - 0.4) / 2, v)
                   for x, y, v in body(hand_y=0.4 - 1.0 * UNIT_Y,
                                       hand_x=0.6)]
        far = pose_pointer(far_lms, W, H)
        self.assertAlmostEqual(near[0], far[0], places=6)
        self.assertAlmostEqual(near[1], far[1], places=6)

    def test_side_on_does_not_pin_to_a_corner(self):
        # Shoulders nearly overlapping, hands up at a back-squat bar. Shoulder
        # width alone would send this to the top corner (the mode toggle).
        lms = body(hand_y=0.38, hand_x=0.52, shoulder_half=0.002)
        p = pose_pointer(lms, W, H)
        self.assertTrue(p is None or p[1] > 0.3)

    def test_no_shoulders_no_pointer(self):
        lms = body(hand_y=0.2)
        lms[11] = (0.55, 0.4, 0.1)
        self.assertIsNone(pose_pointer(lms, W, H))


def hand(curled=()):
    """21 world landmarks for a flat hand pointing up (y is up here), with
    the named fingers curled back towards the palm."""
    pts = [(0.0, 0.0, 0.0)] * 21
    for k, (name, joints) in enumerate(FINGERS.items()):
        x = -0.03 + 0.02 * k
        for j, idx in enumerate(joints):  # knuckle, PIP, DIP, tip
            pts[idx] = (x, 0.09 + 0.025 * j, 0.0)
        if name in curled:
            mcp, pip, dip, tip = joints
            pts[dip] = (x, 0.11, 0.02)
            pts[tip] = (x, 0.085, 0.025)
    return pts


class FingersUpTest(unittest.TestCase):
    def test_open_hand(self):
        self.assertEqual(fingers_up(hand()), set(FINGERS))

    def test_fist(self):
        self.assertEqual(fingers_up(hand(curled=FINGERS)), set())

    def test_two_fingers(self):
        self.assertEqual(fingers_up(hand(curled=("ring", "pinky"))),
                         {"index", "middle"})


if __name__ == "__main__":
    unittest.main()
