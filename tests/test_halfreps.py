import math
import unittest

from station.halfreps import BOTTOM, FULL, LET_BY, RUN, STALE_S, TOP, HalfReps, Uncounted

FPS = 30
DT = 1 / FPS
# A lateral raise as the goniometer reads it: hanging, a full rep's top, and
# a rep cut to half.
REST, HIGH, HALF = 25.0, 95.0, 55.0


def lift(tops, low=REST, rep_s=2.5):
    """An arm's angle a frame at a time: up from `low` to each of `tops` in
    turn and back down, a rep every `rep_s`."""
    n = int(rep_s * FPS / 2)
    out = []
    for top in tops:
        up = [low + (top - low) * (1 - math.cos(math.pi * k / n)) / 2 for k in range(n)]
        out += up + [low + top - a for a in up]
    return out


def still(seconds, at=REST):
    return [at] * int(seconds * FPS)


def watch(h, left, right=None, t=0.0):
    """Feed the arms' angles a frame at a time; what was said after each
    frame, and the time after the last."""
    said = []
    for i, a in enumerate(left):
        said.append(h.update(t, (a, None if right is None else right[i])))
        t += DT
    return said, t


class HalfRepsTest(unittest.TestCase):
    def test_full_reps_say_nothing(self):
        said, _ = watch(HalfReps("shoulder"), lift([HIGH] * 8))
        self.assertEqual(set(said), {None})

    def test_short_at_the_top_is_said_once_it_is_a_habit(self):
        h = HalfReps("shoulder")
        said, t = watch(h, lift([HALF] * (RUN - 1)))
        self.assertEqual(set(said), {None})
        said, _ = watch(h, lift([HALF] * 3), t=t)
        self.assertEqual(said[-1], TOP)
        # From the top of the rep that made it a habit, not a rep later.
        self.assertLess(said.index(TOP) * DT, 2.5)

    def test_two_running_are_a_habit(self):
        said, _ = watch(HalfReps("shoulder"), lift([HIGH, HALF, HALF]))
        self.assertEqual(said[-1], TOP)

    def test_not_coming_back_down_is_said(self):
        # Up from hanging, then every rep stops well short of hanging again.
        up = int(1.25 * FPS)
        frames = lift([HIGH])[:up] + lift([HIGH] * 6, low=65.0)[up:]
        said, _ = watch(HalfReps("shoulder"), frames)
        self.assertEqual(said[-1], BOTTOM)
        self.assertNotIn(TOP, said)

    def test_getting_there_takes_it_back_at_once(self):
        h = HalfReps("shoulder")
        said, t = watch(h, lift([HALF] * 4))
        self.assertEqual(said[-1], TOP)
        said, _ = watch(h, lift([HIGH, HALF, HIGH]), t=t)
        # Gone on the way up, before the full rep has even turned round.
        gone = said.index(None)
        self.assertLess(gone * DT, 1.25)
        # And it takes a habit again to bring it back, not one short rep.
        self.assertEqual(set(said[gone:]), {None})

    def test_one_short_rep_is_a_slip(self):
        tops = [HIGH, HALF, HIGH, HIGH, HALF, HIGH, HALF, HIGH]
        said, _ = watch(HalfReps("shoulder"), lift(tops))
        self.assertEqual(set(said), {None})

    def test_the_arm_that_hangs_is_left_out(self):
        short = lift([HALF] * 5)
        h = HalfReps("shoulder")
        said, _ = watch(h, short, still(len(short) / FPS))
        self.assertEqual(said[-1], TOP)
        # And it is the lifting arm that is said to be short, not both.
        self.assertEqual(h.arms, [True, False])
        both = HalfReps("shoulder")
        watch(both, short, short)
        self.assertEqual(both.arms, [True, True])
        full = lift([HIGH] * 5)
        said, _ = watch(HalfReps("shoulder"), full, still(len(full) / FPS))
        self.assertEqual(set(said), {None})

    def test_an_arm_out_of_view_is_left_out(self):
        said, _ = watch(HalfReps("shoulder"), lift([HALF] * 5))
        self.assertEqual(said[-1], TOP)
        h = HalfReps("shoulder")
        self.assertIsNone(h.update(0.0, (None, None)))

    def test_the_arms_have_to_agree(self):
        # One arm all the way, one half way, and then both down: at no point
        # is the short one judged alone.
        full = lift([HIGH] * 6) + still(STALE_S + 2)
        short = lift([HALF] * 6) + still(STALE_S + 2)
        said, _ = watch(HalfReps("shoulder"), full, short)
        self.assertEqual(set(said), {None})

    def test_it_goes_when_the_lifting_stops(self):
        h = HalfReps("shoulder")
        said, t = watch(h, lift([HALF] * 5))
        self.assertEqual(said[-1], TOP)
        said, _ = watch(h, still(STALE_S + 1), t=t)
        self.assertIsNone(said[-1])
        self.assertEqual(h.arms, [False, False])

    def test_slow_reps_are_still_being_lifted(self):
        said, _ = watch(HalfReps("shoulder"), lift([HALF] * 6, rep_s=6.0))
        first = said.index(TOP)
        self.assertEqual(set(said[first:]), {TOP})

    def test_an_elbow_has_its_own_range(self):
        top_min, bottom_max = FULL["elbow"]
        said, _ = watch(HalfReps("elbow"), lift([top_min + 30] * 5, low=10.0))
        self.assertEqual(set(said), {None})
        said, _ = watch(HalfReps("elbow"), lift([top_min - 20] * 5, low=10.0))
        self.assertEqual(said[-1], TOP)
        said, _ = watch(HalfReps("elbow"), lift([top_min + 30] * 5, low=bottom_max + 20))
        self.assertEqual(said[-1], BOTTOM)


class UncountedTest(unittest.TestCase):
    """The count that takes the reps the live counter lets go by. Here the
    live counter is played by hand: it takes a rep on the way up, or not."""

    RANGE = HIGH - REST

    def lift(self, u, tops, taken, count=0):
        """Reps to each of `tops`; the live counter takes those in `taken`
        (by position). Returns its count after."""
        for i, top in enumerate(tops):
            rep = lift([top])
            for k, a in enumerate(rep):
                if i in taken and k == len(rep) // 3:
                    count += 1
                u.update(a, self.RANGE, count)
        return count

    def test_the_live_counter_s_number_stands_while_it_counts(self):
        u = Uncounted(rest_at_max=False)
        count = self.lift(u, [HIGH] * 6, taken=range(6))
        self.assertEqual(u.reps(count), 6)
        self.assertFalse(u.took_over)

    def test_reps_it_lets_go_by_are_counted(self):
        u = Uncounted(rest_at_max=False)
        count = self.lift(u, [HIGH] * 3, taken=range(3))
        # One let by could be a stray turn: not yet.
        count = self.lift(u, [HALF] * (LET_BY - 1), taken=(), count=count)
        self.assertEqual(u.reps(count), 3)
        count = self.lift(u, [HALF] * 4, taken=(), count=count)
        self.assertTrue(u.took_over)
        self.assertEqual(count, 3)
        self.assertEqual(u.reps(count), 3 + LET_BY - 1 + 4)

    def test_one_let_by_between_reps_it_takes_is_forgotten(self):
        u = Uncounted(rest_at_max=False)
        count = self.lift(u, [HIGH, HALF, HIGH, HIGH, HALF, HIGH], taken=(0, 2, 3, 5))
        self.assertFalse(u.took_over)
        self.assertEqual(u.reps(count), 4)

    def test_once_it_has_taken_over_every_rep_is_its_own(self):
        u = Uncounted(rest_at_max=False)
        count = self.lift(u, [HIGH] * 2, taken=range(2))
        count = self.lift(u, [HALF] * 3, taken=(), count=count)
        # The live counter picks up again; no rep is counted twice.
        count = self.lift(u, [HIGH] * 3, taken=range(3), count=count)
        self.assertEqual(count, 5)
        self.assertEqual(u.reps(count), 8)

    def test_a_curl_s_top_is_where_its_angle_is_least(self):
        # The elbow rests straight, at the most of its angle.
        u = Uncounted(rest_at_max=True)
        count = 0
        for a in lift([120.0] * 4, low=40.0):
            u.update(180.0 - a, 130.0, count)
        self.assertTrue(u.took_over)
        self.assertEqual(u.reps(count), 4)

    def test_nothing_is_counted_without_a_range(self):
        u = Uncounted(rest_at_max=False)
        for a in lift([REST + 10] * 6):
            u.update(a, 10.0, 0)
        self.assertEqual(u.reps(0), 0)


if __name__ == "__main__":
    unittest.main()
