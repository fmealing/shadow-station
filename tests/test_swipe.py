import unittest

from station.swipe import DOWN, DRAG, FLICK, UP, Debounce, Swipe, grabbing


def move(swipe, points, t=0.0, dt=1 / 30, held=False):
    """Feed palm positions; return (swipes, end time)."""
    out = []
    for p in points:
        way = swipe.update(t, p, held)
        if way:
            out.append(way)
        t += dt
    return out, t


def line(y0, y1, frames, x=0.5):
    return [(x, y0 + (y1 - y0) * i / (frames - 1)) for i in range(frames)]


def settled(points):
    """The hand held still in view first, so flicks are allowed."""
    return [points[0]] * 12 + points


class FlickTest(unittest.TestCase):
    def test_fast_flick_up(self):
        out, _ = move(Swipe(FLICK), settled(line(0.6, 0.3, 5)))  # 0.3 in 0.13 s
        self.assertEqual(out, [UP])

    def test_fast_flick_down(self):
        out, _ = move(Swipe(FLICK), settled(line(0.3, 0.6, 5)))
        self.assertEqual(out, [DOWN])

    def test_small_flick_counts(self):
        # 0.12 of the frame in 0.13 s: too small before sensitivity went up.
        out, _ = move(Swipe(FLICK), settled(line(0.6, 0.48, 5)))
        self.assertEqual(out, [UP])

    def test_slight_angle_counts(self):
        pts = [(0.5 + 0.02 * i, 0.6 - 0.04 * i) for i in range(5)]
        out, _ = move(Swipe(FLICK), settled(pts))
        self.assertEqual(out, [UP])

    def test_hand_rising_into_view_is_not_a_flick(self):
        # Raised from below the frame: first seen at the bottom, rising fast.
        pts = [None] * 10 + line(0.95, 0.6, 6) + line(0.6, 0.5, 10)
        out, _ = move(Swipe(FLICK), pts)
        self.assertEqual(out, [])

    def test_flick_once_settled_after_appearing(self):
        pts = [None] * 10 + [(0.5, 0.6)] * 12 + line(0.6, 0.45, 5)
        out, _ = move(Swipe(FLICK), pts)
        self.assertEqual(out, [UP])

    def test_dropout_mid_flick_still_counts(self):
        # Seen with the real tracker: it lost the hand for one frame of a
        # fast flick, and neither half was long enough on its own.
        pts = line(0.47, 0.19, 7)
        pts[3] = None
        out, _ = move(Swipe(FLICK), settled(pts))
        self.assertEqual(out, [UP])

    def test_slow_reach_is_not_a_flick(self):
        # Up 0.3 of the frame over a second: reaching for a top button.
        out, _ = move(Swipe(FLICK), line(0.6, 0.3, 30))
        self.assertEqual(out, [])

    def test_return_stroke_is_ignored(self):
        s = Swipe(FLICK, lockout_s=0.7)
        out, t = move(s, settled(line(0.6, 0.3, 5)))
        back, _ = move(s, line(0.3, 0.6, 5), t=t)  # straight back down
        self.assertEqual(out + back, [UP])

    def test_down_works_again_after_the_lockout(self):
        s = Swipe(FLICK, lockout_s=0.7)
        out, t = move(s, settled(line(0.6, 0.3, 5)))
        out2, t = move(s, [(0.5, 0.3)] * 25, t=t)  # hold still ~0.8 s
        out3, _ = move(s, line(0.3, 0.6, 5), t=t)
        self.assertEqual(out + out2 + out3, [UP, DOWN])

    def test_repeated_up_flicks(self):
        s = Swipe(FLICK, cooldown_s=0.4)
        out, t = move(s, [(0.5, 0.6)] * 12)
        for _ in range(3):
            o, t = move(s, line(0.6, 0.3, 5), t=t)
            out += o
            o, t = move(s, [(0.5, 0.6)] * 12, t=t)  # hand reset off camera
            out += o
        self.assertEqual(out, [UP, UP, UP])

    def test_sideways_is_not_a_flick(self):
        pts = [(0.2 + 0.1 * i, 0.6 - 0.05 * i) for i in range(5)]
        out, _ = move(Swipe(FLICK), pts)
        self.assertEqual(out, [])

    def test_held_hand_does_not_flick(self):
        out, _ = move(Swipe(FLICK), settled(line(0.6, 0.3, 5)), held=True)
        self.assertEqual(out, [])


class DragTest(unittest.TestCase):
    def test_grab_and_pull_up(self):
        out, _ = move(Swipe(DRAG), line(0.6, 0.45, 20), held=True)
        self.assertEqual(out, [UP])

    def test_short_pull_counts(self):
        out, _ = move(Swipe(DRAG), line(0.6, 0.53, 10), held=True)
        self.assertEqual(out, [UP])

    def test_slow_drag_still_counts(self):
        out, _ = move(Swipe(DRAG), line(0.6, 0.45, 60), held=True)
        self.assertEqual(out, [UP])

    def test_one_swipe_per_grab(self):
        out, _ = move(Swipe(DRAG), line(0.7, 0.2, 30), held=True)
        self.assertEqual(out, [UP])

    def test_open_hand_moves_do_nothing(self):
        out, _ = move(Swipe(DRAG), line(0.6, 0.3, 5), held=False)
        self.assertEqual(out, [])

    def test_regrab_swipes_again(self):
        s = Swipe(DRAG, cooldown_s=0.4)
        a, t = move(s, line(0.6, 0.45, 10), held=True)
        b, t = move(s, line(0.45, 0.6, 15), t=t, held=False)  # open, go back
        c, _ = move(s, line(0.6, 0.45, 10), t=t, held=True)
        self.assertEqual(a + b + c, [UP, UP])


class GrabbingTest(unittest.TestCase):
    OPEN = frozenset({"index", "middle", "ring", "pinky"})

    def test_shapes(self):
        self.assertTrue(grabbing(frozenset()))
        self.assertFalse(grabbing(self.OPEN))
        self.assertFalse(grabbing(frozenset({"index", "middle"})))
        # One finger is on the way between the two: keep the last state.
        self.assertIsNone(grabbing(frozenset({"index"})))
        self.assertIsNone(grabbing(None))


class DebounceTest(unittest.TestCase):
    def feed(self, d, values, dt=1 / 30):
        return [d.update(i * dt, v) for i, v in enumerate(values)]

    def test_needs_to_settle(self):
        out = self.feed(Debounce(settle_s=0.08), [True] * 5)
        self.assertEqual(out, [False, False, False, True, True])

    def test_one_frame_flicker_is_ignored(self):
        d = Debounce(settle_s=0.08)
        self.feed(d, [True] * 6)
        out = [d.update(0.3 + i / 30, v)
               for i, v in enumerate([False, True, True])]
        self.assertEqual(out, [True, True, True])

    def test_in_between_keeps_state(self):
        d = Debounce(settle_s=0.08)
        self.feed(d, [True] * 6)
        self.assertTrue(d.update(0.3, None))

    def test_lost_hand_releases(self):
        d = Debounce(settle_s=0.08, lost_s=0.3)
        self.feed(d, [True] * 6)
        out = [d.update(0.3 + i / 30, None) for i in range(12)]
        self.assertTrue(out[0])
        self.assertFalse(out[-1])


if __name__ == "__main__":
    unittest.main()
