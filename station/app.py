"""Shadow Station control test: camera, tracking, buttons, and TikTok.

    python3 -m station                  # built-in camera, hand mode
    python3 -m station --camera 1       # another camera (e.g. the USB one)
    python3 -m station --swipe drag     # or flick; s switches live
    python3 -m station --toggle-hold 0  # hand/pose switches on entering the corner
    python3 -m station --rotate 90      # camera mounted sideways in the case

Point with your index finger and hover on a button to press it. TikTok opens
the station's Chrome beside this window: point at it the same way, hover to
click, swipe for the next video, hover its Close corner to come back.

Keys: s swipe method, t hand/pose, d HUD, f fullscreen, q or Esc quit.
Every press and swipe is logged to the terminal.
"""

import argparse
import time

import cv2

from . import ui
from .press import OneEuro, Presser
from .swipe import METHODS as SWIPES
from .swipe import UP, Debounce, Swipe, grabbing
from .tiktok import TikTok
from .tracking import HandTracker, PoseTracker, ensure_model

WINDOW = "Shadow Station"
# Portrait, 9:16, like the station's monitor.
CANVAS_W, CANVAS_H = 720, 1280
# The camera window starts at the laptop screen's top left, small enough to
# fit it, with TikTok beside it. Fullscreen (f) fills the station's monitor.
WINDOW_POS = (20, 40)
WINDOW_H = 860
WINDOW_W = round(WINDOW_H * CANVAS_W / CANVAS_H)
TIKTOK_POS = (WINDOW_POS[0] + WINDOW_W + 20, WINDOW_POS[1])
TIKTOK_SIZE = (506, 900)
# After a swipe, presses are ignored this long. A flick up carries the cursor
# into the top bar, and the hand can pause there long enough to press.
SWIPE_QUIET_S = 1.0
ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def main(argv=None):
    args = _parse(argv)
    # Models first, so a first-run download is not spent with the camera on.
    trackers = {"hand": HandTracker(ensure_model("hand")),
                "pose": PoseTracker(ensure_model("pose"))}
    cap = _open_camera(args.camera)

    mode = args.start
    presser = Presser(dwell_s=args.dwell)
    grip = Debounce()
    swipe = Swipe(args.swipe)
    smooth = OneEuro()
    tiktok = None
    flashes, toast, swiped = {}, None, None
    presses, swipes, fps = 0, 0, 0.0
    hud, fullscreen = True, args.fullscreen
    last_ms = -1

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, WINDOW_W, WINDOW_H)
    cv2.moveWindow(WINDOW, *WINDOW_POS)
    _set_fullscreen(fullscreen)
    print("s: swipe method   t: hand/pose   d: HUD   f: fullscreen   q: quit")

    t0 = last = time.monotonic()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera stopped sending frames")
                break
            frame = _portrait(frame, args.rotate)
            h, w = frame.shape[:2]
            now = time.monotonic()
            t = now - t0
            if now > last:
                fps = 0.9 * fps + 0.1 / (now - last)
            last = now

            # VIDEO mode needs strictly increasing timestamps.
            last_ms = max(int(t * 1000), last_ms + 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tracked = trackers[mode].process(rgb, last_ms)

            aim = None  # cursor in screen fractions
            if tracked.pointer is None:
                smooth.reset()
            else:
                aim = smooth(t, tracked.pointer)
            cursor = None if aim is None else (aim[0] * w, aim[1] * h)
            fist = grip.update(t, grabbing(tracked.fingers))
            quiet = swiped is not None and t - swiped[1] < SWIPE_QUIET_S

            if tiktok is not None:
                # TikTok has the cursor; the station's buttons step aside.
                buttons = []
                if not tiktok.update(t, aim, quiet):
                    tiktok = None
                    print(f"{t:8.2f}s  TikTok closed")
            else:
                buttons = ui.layout(w, h, mode, args.toggle_hold)
                pressed = presser.update(t, None if quiet else cursor, buttons)
                if pressed is not None:
                    presses += 1
                    flashes[pressed.id] = t
                    how = "zone" if pressed.hold_s is not None else "dwell"
                    print(f"{t:8.2f}s  press #{presses:<3} {pressed.id:<7} "
                          f"{how}, {presser.pressed_after:.2f}s hovering")
                    if pressed.id == ui.TOGGLE:
                        mode = _other(mode)
                        smooth.reset()
                        buttons = ui.layout(w, h, mode, args.toggle_hold)
                    elif pressed.id == "tiktok":
                        tiktok = _open_tiktok(args.dwell)
                        buttons = [] if tiktok else buttons
                        toast = ("TikTok", "opened beside this window" if tiktok
                                 else "couldn't open, see terminal", t)
                    else:
                        toast = (pressed.label, "would open here", t)

            way = swipe.update(t, tracked.motion, fist)
            if way is not None:
                swipes += 1
                swiped = (way, t)
                video = "next" if way == UP else "previous"
                print(f"{t:8.2f}s  swipe #{swipes:<3} {way:<7} "
                      f"{swipe.method}, {video} video")
                if tiktok is not None:
                    tiktok.swipe(way)

            ui.draw_landmarks(frame, tracked)
            if tiktok is not None:
                ui.draw_banner(frame, "TikTok is open. Its Close is top right.")
            else:
                ui.draw_bar(frame, buttons, mode, presser, flashes, t)
            if swiped:
                ui.draw_swipe(frame, swiped[0], t - swiped[1])
            if toast:
                ui.draw_toast(frame, toast[0], toast[1], t - toast[2])
            if cursor is not None:
                progress = 0.0 if tiktok is not None else presser.progress
                ui.draw_cursor(frame, cursor, progress, fist)
            if hud:
                ui.draw_hud(frame, _hud_lines(mode, swipe.method, tracked, fist,
                                              fps, presses, swipes))
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                swipe.method = SWIPES[(SWIPES.index(swipe.method) + 1)
                                      % len(SWIPES)]
                print(f"swipe method: {swipe.method}")
            elif key == ord("t"):
                mode = _other(mode)
                smooth.reset()
                print(f"mode: {mode}")
            elif key == ord("d"):
                hud = not hud
            elif key == ord("f"):
                fullscreen = not fullscreen
                _set_fullscreen(fullscreen)
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        if tiktok is not None:
            tiktok.close()
        cap.release()
        cv2.destroyAllWindows()
        for tr in trackers.values():
            tr.close()


def _open_tiktok(dwell_s):
    """The station's Chrome on TikTok, or None with the reason printed.
    Chrome takes a second or two to start, and the camera pauses meanwhile."""
    try:
        return TikTok(TIKTOK_POS, TIKTOK_SIZE, dwell_s=dwell_s)
    except (OSError, RuntimeError) as e:
        print(f"could not open TikTok: {e}")
        return None


def _parse(argv):
    p = argparse.ArgumentParser(prog="station", description=__doc__.split("\n")[0])
    p.add_argument("--camera", type=int, default=0,
                   help="camera index (default 0)")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0,
                   help="degrees clockwise to turn the camera image upright, "
                        "for a camera mounted sideways (default 0)")
    # The station itself will start in pose mode; this test starts in hand.
    p.add_argument("--start", choices=("hand", "pose"), default="hand")
    p.add_argument("--swipe", choices=SWIPES, default=SWIPES[0])
    p.add_argument("--dwell", type=float, default=0.8,
                   help="seconds to hold on a button (default 0.8)")
    # How long a hand has to stay in the top-right toggle zone. Instant (0)
    # also fires whenever a hand passes through the corner: reaching up,
    # stretching, the lockout of an overhead press.
    p.add_argument("--toggle-hold", type=float, default=0.5,
                   help="seconds in the top-right zone to switch hand/pose; "
                        "0 switches on entry (default 0.5)")
    p.add_argument("--fullscreen", action="store_true")
    return p.parse_args(argv)


def _open_camera(index):
    cap = cv2.VideoCapture(index)
    # Ask for 1080p: a landscape camera loses most of its width to the
    # portrait crop, so start from as many pixels as it will give.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    if not cap.isOpened():
        raise SystemExit(
            f"could not open camera {index}.\n"
            "On macOS, allow camera access for your terminal (or VS Code) in "
            "System Settings > Privacy & Security > Camera, then rerun.\n"
            "If another camera opened instead, try --camera 1.")
    return cap


def _portrait(frame, rotate):
    """Camera frame -> the mirrored portrait canvas.

    Turned upright first, for a camera mounted sideways; that uses the whole
    sensor. Whatever is still wider than 9:16 after that (any landscape camera
    left the normal way up) is cropped to its middle strip.
    """
    if rotate:
        frame = cv2.rotate(frame, ROTATIONS[rotate])
    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    if w * CANVAS_H > h * CANVAS_W:
        cw = round(h * CANVAS_W / CANVAS_H)
        frame = frame[:, (w - cw) // 2:(w - cw) // 2 + cw]
    elif w * CANVAS_H < h * CANVAS_W:
        ch = round(w * CANVAS_H / CANVAS_W)
        frame = frame[(h - ch) // 2:(h - ch) // 2 + ch]
    h, w = frame.shape[:2]
    interp = cv2.INTER_AREA if w > CANVAS_W else cv2.INTER_LINEAR
    return cv2.resize(frame, (CANVAS_W, CANVAS_H), interpolation=interp)


def _set_fullscreen(on):
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN if on else cv2.WINDOW_NORMAL)


def _other(mode):
    return "pose" if mode == "hand" else "hand"


def _hud_lines(mode, swipe, tracked, fist, fps, presses, swipes):
    lines = [f"mode {mode}   swipe {swipe}",
             f"{fps:4.1f} fps   presses {presses}   swipes {swipes}"]
    if mode == "hand":
        if tracked.fingers is None:
            lines.append("no hand")
        else:
            names = " ".join(f for f in ("index", "middle", "ring", "pinky")
                             if f in tracked.fingers)
            state = "   FIST" if fist else ""
            lines.append(f"fingers {len(tracked.fingers)} {names}{state}")
    elif not tracked.points:
        lines.append("no body")
    lines += ["[s] swipe  [t] hand/pose  [d] HUD  [f] fullscreen  [q] quit"]
    return lines
