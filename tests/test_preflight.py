import os
import unittest

from station import preflight
from station.preflight import others

FINDER = {"pid": 10, "id": "com.apple.finder", "name": "Finder", "dock": True}
CODE = {"pid": 20, "id": "com.microsoft.VSCode", "name": "Code", "dock": True}
FUSION = {"pid": 30, "id": "com.autodesk.fusion360", "name": "Autodesk Fusion",
          "dock": True}
GRAMMARLY = {"pid": 40, "id": "com.grammarly.ProjectLlama",
             "name": "Grammarly Desktop", "dock": False}
WIFI = {"pid": 50, "id": "com.apple.wifi.WiFiAgent", "name": "Wi-Fi",
        "dock": False}
# The station's own Chrome from a run that didn't close it, and yours.
CHROMES = [{"pid": 60, "id": "com.google.Chrome", "name": "Google Chrome",
            "dock": True},
           {"pid": 61, "id": "com.google.Chrome", "name": "Google Chrome",
            "dock": True}]
NAMELESS = {"pid": 70, "name": "helper", "dock": False}


class OthersTest(unittest.TestCase):
    def test_quits_dock_apps_and_keeps_finder(self):
        self.assertEqual(others([FINDER, FUSION, *CHROMES], set()),
                         [FUSION, *CHROMES])

    def test_keeps_the_app_the_station_was_started_from(self):
        # python (pid 22) under a shell (21) under VS Code (20).
        self.assertEqual(others([CODE, FUSION], {22, 21, 20}), [FUSION])

    def test_menu_bar_apps_stay_unless_named(self):
        self.assertEqual(others([WIFI, GRAMMARLY, NAMELESS], set()),
                         [GRAMMARLY])


class AncestorsTest(unittest.TestCase):
    def test_holds_this_process_and_its_parent(self):
        pids = preflight._ancestors()
        self.assertIn(os.getpid(), pids)
        self.assertIn(os.getppid(), pids)


class NamesTest(unittest.TestCase):
    def test_drops_invisible_marks(self):
        self.assertEqual(preflight._names([{"name": "‎WhatsApp"}, FUSION]),
                         "WhatsApp, Autodesk Fusion")
