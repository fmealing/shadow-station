import unittest

from station.press import Button, Dwell, OneEuro, Presser

A = Button("a", "A", (0, 0, 100, 100))
B = Button("b", "B", (200, 0, 100, 100))
BUTTONS = [A, B]
ON_A, ON_B, OFF = (50, 50), (250, 50), (150, 300)


def run(presser, frames, dt=1 / 30, t=0.0):
    """Feed `frames` cursor positions; return (pressed ids, end time)."""
    out = []
    for cursor in frames:
        hit = presser.update(t, cursor, BUTTONS)
        if hit:
            out.append(hit.id)
        t += dt
    return out, t


class PresserTest(unittest.TestCase):
    def test_fires_once_after_dwell(self):
        p = Presser(dwell_s=0.8)
        pressed, _ = run(p, [ON_A] * 60)  # 2 s on the button
        self.assertEqual(pressed, ["a"])

    def test_not_before_dwell(self):
        p = Presser(dwell_s=0.8)
        pressed, _ = run(p, [ON_A] * 20)  # ~0.67 s
        self.assertEqual(pressed, [])
        self.assertGreater(p.progress, 0.5)

    def test_rearms_after_leaving(self):
        p = Presser(dwell_s=0.8)
        pressed, _ = run(p, [ON_A] * 30 + [OFF] * 3 + [ON_A] * 30)
        self.assertEqual(pressed, ["a", "a"])

    def test_losing_the_hand_does_not_rearm(self):
        # Mode switch: the tracker changes and the cursor vanishes for a
        # while, then comes back on the toggle. It must not fire again.
        p = Presser(dwell_s=0.8)
        pressed, _ = run(p, [ON_A] * 30 + [None] * 30 + [ON_A] * 60)
        self.assertEqual(pressed, ["a"])

    def test_moving_to_another_button_restarts(self):
        p = Presser(dwell_s=0.8)
        pressed, _ = run(p, [ON_A] * 20 + [ON_B] * 20)
        self.assertEqual(pressed, [])
        pressed, _ = run(p, [ON_B] * 10, t=40 / 30)
        self.assertEqual(pressed, ["b"])

    def test_short_dropout_keeps_progress(self):
        p = Presser(dwell_s=0.8, lost_grace_s=0.25)
        pressed, _ = run(p, [ON_A] * 12 + [None] * 3 + [ON_A] * 12)
        self.assertEqual(pressed, ["a"])

    def test_long_dropout_resets(self):
        p = Presser(dwell_s=0.8, lost_grace_s=0.25)
        pressed, _ = run(p, [ON_A] * 20 + [None] * 15 + [ON_A] * 20)
        self.assertEqual(pressed, [])

    def test_jitter_at_the_edge_does_not_restart(self):
        # Once hovered, drifting just outside the edge still counts.
        p = Presser(dwell_s=0.8, sticky_px=24)
        edge_in, edge_out = (95, 50), (110, 50)
        pressed, _ = run(p, [edge_in, edge_out] * 15)
        self.assertEqual(pressed, ["a"])

    def test_sticky_zone_is_not_a_hit_on_its_own(self):
        p = Presser(dwell_s=0.8, sticky_px=24)
        pressed, _ = run(p, [(110, 50)] * 60)
        self.assertEqual(pressed, [])


class ZoneTest(unittest.TestCase):
    ZONE = Button("toggle", "", (0, 0, 100, 100), hold_s=0.0)

    def run_zone(self, presser, frames):
        out, t = [], 0.0
        for cursor in frames:
            if presser.update(t, cursor, [self.ZONE, B]):
                out.append("toggle")
            t += 1 / 30
        return out

    def test_instant_zone_fires_on_entry(self):
        self.assertEqual(self.run_zone(Presser(), [OFF, ON_A]), ["toggle"])

    def test_staying_in_an_instant_zone_does_not_flip_back(self):
        # The mode switch swaps trackers, so the cursor may vanish and
        # come back while the hand is still in the corner.
        frames = [ON_A] * 30 + [None] * 10 + [ON_A] * 30
        self.assertEqual(self.run_zone(Presser(), frames), ["toggle"])

    def test_zone_uses_its_own_hold_time(self):
        zone = Button("toggle", "", (0, 0, 100, 100), hold_s=0.5)
        p, t, out = Presser(dwell_s=0.8), 0.0, []
        for _ in range(30):
            if p.update(t, ON_A, [zone]):
                out.append(t)
            t += 1 / 30
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0], 0.5, delta=1 / 30)


class DwellAnywhereTest(unittest.TestCase):
    def feed(self, d, points, t=0.0, dt=1 / 30):
        out = []
        for p in points:
            hit = d.update(t, p)
            if hit:
                out.append(hit)
            t += dt
        return out, t

    def test_clicks_where_the_cursor_rests(self):
        out, _ = self.feed(Dwell(dwell_s=0.8), [(200, 300)] * 30)
        self.assertEqual(out, [(200, 300)])

    def test_small_drift_still_clicks(self):
        pts = [(200 + (i % 3) * 5, 300) for i in range(30)]
        out, _ = self.feed(Dwell(dwell_s=0.8, radius=24), pts)
        self.assertEqual(len(out), 1)

    def test_resting_hand_clicks_once(self):
        # Watching with a hand left in view must not keep pausing the video.
        out, _ = self.feed(Dwell(dwell_s=0.8), [(200, 300)] * 120)
        self.assertEqual(len(out), 1)

    def test_moving_rearms(self):
        d = Dwell(dwell_s=0.8, radius=24)
        out, t = self.feed(d, [(200, 300)] * 30)
        out2, _ = self.feed(d, [(300, 300)] * 30, t=t)
        self.assertEqual(out + out2, [(200, 300), (300, 300)])

    def test_moving_hand_never_clicks(self):
        pts = [(100 + 10 * i, 300) for i in range(60)]
        out, _ = self.feed(Dwell(dwell_s=0.8, radius=24), pts)
        self.assertEqual(out, [])

    def test_lost_hand_resets(self):
        d = Dwell(dwell_s=0.8, lost_grace_s=0.25)
        out, _ = self.feed(d, [(200, 300)] * 20 + [None] * 15 + [(200, 300)] * 20)
        self.assertEqual(out, [])


class OneEuroTest(unittest.TestCase):
    def test_still_hand_is_smoothed(self):
        f = OneEuro()
        jitter = [(0.5 + (0.01 if i % 2 else -0.01), 0.5) for i in range(60)]
        out = [f(i / 30, p) for i, p in enumerate(jitter)]
        spread = max(x for x, _ in out[30:]) - min(x for x, _ in out[30:])
        self.assertLess(spread, 0.01)  # raw spread is 0.02

    def test_fast_move_keeps_up(self):
        f = OneEuro()
        for i in range(10):
            f(i / 30, (0.1, 0.5))
        for i in range(10, 25):  # sweep across the screen in half a second
            x, _ = f(i / 30, (0.1 + (i - 9) * 0.05, 0.5))
        self.assertGreater(x, 0.75 * (0.1 + 15 * 0.05))


if __name__ == "__main__":
    unittest.main()
