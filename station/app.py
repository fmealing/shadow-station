"""Shadow Station: counts your reps, run by pointing at a web UI in Chrome.

    python3 -m station                  # built-in camera, hand mode
    python3 -m station --camera 1       # another camera (e.g. the USB one)
    python3 -m station --start pose     # start in pose mode, as the station will
    python3 -m station --hand left      # point with the left hand
    python3 -m station --rotate 90      # camera mounted sideways in the case
    python3 -m station --video clip.mp4 # a recording instead of the camera
    python3 -m station --fullscreen     # kiosk: the whole screen, no window
    python3 -m station --exercise abduction   # the clinic's set, nothing to pick
    python3 -m station --quit-apps      # quit the other apps first, for filming

Point with your right index finger (hand) or raised right hand (pose) and
hover on a button to press it. Shadow asks for an exercise, curls or lateral
raises, counts a set of it and shows its summary; Physique measures your
proportions while you pose; Mirror is just the camera; TikTok takes the
window over, run by hand.

Keys, in the station's window: t hand/pose, Enter the screen's main button,
1 and 2 the exercises, Esc back, p Physique and m Mirror (from home), d HUD,
f fullscreen, q quit.
Presses and sets are logged here.
"""

import argparse

from . import preflight
from .browser import Chrome
from .camera import Camera, VideoFile
from .engine import EXERCISES, Engine
from .server import Server
from .swipe import METHODS as SWIPES
from .tracking import HandTracker, PoseTracker, ensure_model

# The window starts on the laptop screen's top left, sized to fit it. Its
# page keeps the station's 9:16 portrait shape inside whatever size it gets.
WINDOW_POS = (20, 20)
WINDOW_SIZE = (506, 920)
DEV_URL = "http://localhost:5173/"


def main(argv=None):
    args = _parse(argv)
    if args.quit_apps:
        # Before anything is loaded, and before the station's Chrome opens.
        preflight.quit_others()
    # Models first, so a first-run download is not spent with the camera on.
    trackers = {"hand": HandTracker(ensure_model("hand"), args.hand),
                "pose": PoseTracker(ensure_model("pose"), args.hand),
                "body": PoseTracker(ensure_model("pose"), args.hand, masks=True)}
    server = Server(port=args.port)
    server.start()
    if not server.built and not args.dev:
        print("The UI is not built yet: cd web && npm install && npm run build")
    source = (VideoFile(args.video, args.rotate) if args.video
              else Camera(args.camera, args.rotate))
    url = DEV_URL if args.dev else server.url
    chrome = None
    if not args.no_browser:
        chrome = _open_window(url, args.fullscreen)
    engine = Engine(source, trackers, server, mode=args.start,
                    dwell_s=args.dwell, toggle_hold_s=args.toggle_hold,
                    auto_finish_s=args.auto_finish, chrome=chrome,
                    home_url=url, swipe=args.swipe, tiktok=not args.no_tiktok,
                    exercise=args.exercise)
    print(f"Shadow Station at {url}")
    print("t: hand/pose   Enter: main button   1/2: exercise   Esc: back   "
          "p: Physique   m: Mirror   d: HUD   f: fullscreen   q: quit")
    try:
        # Closing the window ends the station, as closing the old one did.
        engine.run(keep_going=lambda: chrome is None or chrome.alive())
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        if chrome is not None:
            chrome.close()
        source.close()
        for tr in trackers.values():
            tr.close()
        server.stop()


def _open_window(url, fullscreen):
    """The station's Chrome showing the UI, or None with the reason printed
    (the station keeps running; open the URL in any browser)."""
    # On the station's 1080x1920 monitor, pages are laid out at 540 wide and
    # drawn at 2x: the station's page looks the same, and TikTok picks its
    # phone layout instead of its desktop grid.
    extra = ["--kiosk", "--force-device-scale-factor=2"] if fullscreen else []
    try:
        return Chrome(url, WINDOW_POS, WINDOW_SIZE, extra_args=extra)
    except (OSError, RuntimeError) as e:
        print(f"could not open the station's window: {e}")
        return None


def _parse(argv):
    p = argparse.ArgumentParser(prog="station", description=__doc__.split("\n")[0])
    p.add_argument("--camera", type=int, default=0,
                   help="camera index (default 0)")
    p.add_argument("--video", metavar="PATH",
                   help="play a recording, looping, instead of the camera")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0,
                   help="degrees clockwise to turn the camera image upright, "
                        "for a camera mounted sideways (default 0)")
    p.add_argument("--start", choices=("hand", "pose"), default="hand")
    p.add_argument("--exercise", choices=tuple(EXERCISES),
                   help="count sets of this and skip the choice: curls, "
                        "lateral raises, or shoulder abduction as a clinic "
                        "measures it (default: pick on the screen)")
    p.add_argument("--hand", choices=("right", "left"), default="right",
                   help="the hand that points; the other is ignored in hand "
                        "mode, and points in pose mode only while this one "
                        "is down (default right)")
    p.add_argument("--swipe", choices=SWIPES, default=SWIPES[0],
                   help="how you flick through TikTok: a quick flick, or a "
                        "fist dragged up or down (default flick)")
    p.add_argument("--dwell", type=float, default=0.8,
                   help="seconds to hold on a button (default 0.8)")
    # How long a hand has to stay in the top-right toggle zone. Instant (0)
    # also fires whenever a hand passes through the corner.
    p.add_argument("--toggle-hold", type=float, default=0.5,
                   help="seconds in the top-right zone to switch hand/pose; "
                        "0 switches on entry (default 0.5)")
    p.add_argument("--auto-finish", type=float, default=10.0, metavar="S",
                   help="end a set once reps have been counted and none has "
                        "come for S seconds; 0 turns it off (default 10)")
    p.add_argument("--no-tiktok", action="store_true",
                   help="leave TikTok off the home screen")
    p.add_argument("--fullscreen", action="store_true",
                   help="open the window in kiosk mode, filling its screen")
    p.add_argument("--quit-apps", action="store_true",
                   help="quit the other open apps first, to free memory; one "
                        "with unsaved work asks you and stays open")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true",
                   help="don't open a window; open the URL yourself")
    p.add_argument("--dev", action="store_true",
                   help=f"open the Vite dev server ({DEV_URL}) instead of the "
                        "built UI; run `npm run dev` in web/ first")
    return p.parse_args(argv)
