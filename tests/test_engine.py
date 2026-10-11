import contextlib
import io
import queue
import unittest

from station import reps
from station.engine import HOME, PICK, SUMMARY, WORKOUT, Engine
from station.halfreps import BOTTOM, TOP
from station.workout import RECORDING
from tests.lifts import FPS, raise_set, standing


class Page:
    """The server as the engine sees it, keeping the last state it was sent."""

    def __init__(self):
        self.inbox = queue.Queue()
        self.state = None

    def publish(self, msg):
        if msg["type"] == "state":
            self.state = msg

    def publish_frame(self, header, jpeg):
        pass


class ScreensTest(unittest.TestCase):
    """Shadow's way through its screens, by the presses and keys the engine
    is handed. No camera: nothing here steps a frame."""

    def setUp(self):
        # The engine logs each screen and set; not in the tests' output.
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def station(self, **kw):
        page = Page()
        e = Engine(None, {"hand": None, "pose": None}, page, **kw)
        self.addCleanup(e.close)
        return e, page

    def test_shadow_asks_which_exercise(self):
        e, page = self.station()
        e._act("shadow", 0.0)
        self.assertEqual(e.screen, PICK)
        self.assertEqual([(x["id"], x["name"]) for x in page.state["exercises"]],
                         [("curl", "Bicep curl"), ("raise", "Lateral raise")])
        self.assertIsNone(e.workout)

    def test_picking_an_exercise_starts_its_set(self):
        for pick, counter, joint in (("curl", reps.CURL, "elbow"),
                                     ("raise", reps.LATERAL_RAISE, "shoulder")):
            with self.subTest(pick):
                e, page = self.station()
                e._act("shadow", 0.0)
                e._act(pick, 1.0)
                self.assertEqual(e.screen, WORKOUT)
                self.assertIs(e.workout.exercise, counter)
                self.assertEqual(page.state["exercise"]["joint"], joint)

    def test_a_raise_reads_as_a_gym_would_say_it(self):
        e, page = self.station()
        e._act("shadow", 0.0)
        e._act("raise", 1.0)
        words = page.state["exercise"]
        self.assertEqual(words["name"], "Lateral raise")
        self.assertNotIn("abduction", " ".join(words.values()).lower())

    def test_back_goes_one_screen_at_a_time(self):
        e, _ = self.station()
        e._act("shadow", 0.0)
        e._act("raise", 1.0)
        e._act("back", 2.0)
        self.assertEqual(e.screen, PICK)
        e._act("curl", 3.0)
        self.assertIs(e.workout.exercise, reps.CURL)
        e._act("back", 4.0)
        e._act("back", 5.0)
        self.assertEqual(e.screen, HOME)

    def test_an_exercise_is_only_picked_on_its_screen(self):
        e, _ = self.station()
        e._act("raise", 0.0)
        self.assertEqual(e.screen, HOME)

    def test_keys_pick_too(self):
        e, _ = self.station()
        e._key("Enter", 0.0)
        self.assertEqual(e.screen, PICK)
        e._key("Enter", 1.0)   # no main button here: there are two
        e._key("3", 1.0)
        self.assertEqual(e.screen, PICK)
        e._key("2", 2.0)
        self.assertIs(e.workout.exercise, reps.LATERAL_RAISE)
        e._key("Escape", 3.0)
        e._key("1", 4.0)
        self.assertIs(e.workout.exercise, reps.CURL)
        e._key("Escape", 5.0)
        e._key("Escape", 6.0)
        self.assertEqual(e.screen, HOME)

    def test_the_next_set_is_of_the_same_exercise(self):
        e, page = self.station()
        e._act("shadow", 0.0)
        e._act("raise", 0.0)
        w = e.workout
        w.start(0.0)
        t = 0.0
        while w.phase != RECORDING:
            w.update(t, standing())
            t += 1 / FPS
        for frame in raise_set(reps=5, rest_before=1, rest_after=1)[1]:
            w.update(t, frame)
            t += 1 / FPS
        e._act("finish", t)
        self.assertEqual(e.screen, SUMMARY)
        self.assertEqual(page.state["summary"]["reps"], 5)
        self.assertEqual(page.state["exercise"]["peak"], "Peak raise")
        e._act("next", t + 1)
        self.assertEqual(e.screen, WORKOUT)
        self.assertIsNot(e.workout, w)
        self.assertIs(e.workout.exercise, reps.LATERAL_RAISE)
        self.assertEqual(page.state["setNo"], 1)

    def test_done_goes_home_and_asks_again(self):
        e, page = self.station()
        e._act("shadow", 0.0)
        e._act("curl", 0.0)
        e.workout.start(0.0)
        t = 0.0
        while e.workout.phase != RECORDING:
            e.workout.update(t, standing())
            t += 1 / FPS
        e._act("finish", t)
        e._act("done", t + 1)
        self.assertEqual(e.screen, HOME)
        self.assertEqual(page.state["setNo"], 0)
        e._act("shadow", t + 2)
        self.assertEqual(e.screen, PICK)

    def test_half_reps_are_shown_on_the_arms_that_are_short(self):
        for pick, top in (("curl", "Curl all the way up"),
                          ("raise", "Raise to shoulder height")):
            with self.subTest(pick):
                e, _ = self.station()
                e._act("shadow", 0.0)
                e._act(pick, 1.0)
                self.assertIsNone(e._live(2.0)["short"])
                # The page draws it from which end and which arms.
                e.workout.short, e.workout.short_arms = TOP, [True, False]
                self.assertEqual(e._live(2.0)["short"],
                                 {"end": "top", "arms": [True, False],
                                  "headline": "HALF REPS", "cue": top})
                e.workout.short = BOTTOM
                self.assertEqual(e._live(2.0)["short"]["cue"], "Lower all the way down")
                self.assertIsNone(e._live(2.0)["warning"])
                # Losing the lifter is the more pressing thing to show.
                e.workout.warning = "Shadow lost you. Step back into view."
                self.assertIsNone(e._live(2.0)["short"])
                self.assertEqual(e._live(2.0)["warning"], e.workout.warning)

    def test_the_clinic_s_set_shows_nothing_of_half_reps(self):
        e, _ = self.station(exercise="abduction")
        e._act("shadow", 0.0)
        e.workout.short, e.workout.short_arms = TOP, [True, True]
        self.assertIsNone(e._live(1.0)["short"])

    def test_told_what_to_count_nothing_is_asked(self):
        e, page = self.station(exercise="abduction")
        e._act("shadow", 0.0)
        self.assertEqual(e.screen, WORKOUT)
        self.assertIs(e.workout.exercise, reps.LATERAL_RAISE)
        self.assertEqual(page.state["exercise"]["name"], "Shoulder abduction")
        self.assertEqual(page.state["exercises"], [])
        e._act("back", 1.0)
        self.assertEqual(e.screen, HOME)


if __name__ == "__main__":
    unittest.main()
