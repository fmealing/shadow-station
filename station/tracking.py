"""MediaPipe hand and pose tracking, reduced to what the controls need.

Each tracker takes a mirrored RGB frame and returns a `Tracked`: the
landmarks to draw, and where on screen the user is pointing. Frames are
flipped before detection, so every coordinate here is already in the
selfie-view space the screen shows.

Hand and pose point differently:

- Hand mode points with the index fingertip, or with the palm, mapped
  through `HAND_REACH`: a box a little inside the camera frame, so the top
  buttons can be reached without lifting the hand out of view. It also says
  which fingers are extended, which is what the press methods and swipes
  read.
- Pose mode has no usable fingers, so it points with the whole hand,
  measured relative to the body. Shoulder width is the unit, which makes the
  mapping the same at 1 m or 4 m from the camera.

One hand points, the right unless told otherwise. Hand mode ignores the
other hand, so the cursor cannot jump to it. Pose mode uses the other hand
only while the pointing hand is down.
"""

import math
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from mediapipe import Image, ImageFormat
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (HandLandmarker,
                                           HandLandmarkerOptions,
                                           HandLandmarksConnections,
                                           PoseLandmarker,
                                           PoseLandmarkerOptions,
                                           PoseLandmarksConnections)
from mediapipe.tasks.python.vision.core.vision_task_running_mode import \
    VisionTaskRunningMode

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_URLS = {
    "hand": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/latest/hand_landmarker.task",
    "pose": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/latest/pose_landmarker_full.task",
}

# Frame region (x0, y0, x1, y1, as frame fractions) the fingertip moves in.
# Its edges map to the screen's edges.
HAND_REACH = (0.10, 0.08, 0.90, 0.80)

# Pose reach box, in shoulder widths from the shoulder midpoint: left, up,
# right, down. A hand raised about a forearm above the head reaches the top
# bar. First guesses, to be tuned with the station's real camera.
POSE_REACH = (1.4, 1.5, 1.4, 0.6)

HAND_EDGES = tuple((c.start, c.end)
                   for c in HandLandmarksConnections.HAND_CONNECTIONS)
# Body only: the face points add clutter and nothing to the controls.
POSE_EDGES = tuple((c.start, c.end)
                   for c in PoseLandmarksConnections.POSE_LANDMARKS
                   if c.start >= 11 and c.end >= 11)


# MediaPipe names hands as if the photo were not mirrored, and the frames here
# are, so its "Left" is the user's right hand. Pose landmarks are the same:
# 15, its left wrist, is the user's right. (Checked on MediaPipe's sample
# photos, flipped as the camera's frames are.)
HAND_LABEL = {"right": "Left", "left": "Right"}
POSE_HAND = {"right": (15, 17, 19), "left": (16, 18, 20)}  # wrist, pinky, index
# A lone hand the model calls the other side is still followed if its palm is
# within this much (frame fractions) of where the pointing hand was, less than
# FOLLOW_MS ago: the label flickers on a hand seen edge-on or blurred
# mid-flick.
FOLLOW_NEAR = 0.15
FOLLOW_MS = 300

FINGERS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12),
           "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}
# A finger counts as extended when its tip is this much further from the
# wrist than its middle joint is. Extended fingers measured 1.23-1.61 on
# MediaPipe's sample gesture photos, curled ones 0.60-0.99; 1.1 splits them.
# (Knuckle-to-tip straightness was tried first and read the curled fingers
# of a thumbs-up as extended.)
EXTENDED = 1.1
PALM = (0, 5, 9, 13, 17)  # wrist and knuckles: still when the fingers move


@dataclass
class Tracked:
    points: list = field(default_factory=list)  # landmarks, frame fractions
    edges: tuple = ()
    pointer: tuple | None = None   # fingertip (or hand, in pose), screen fractions
    palm: tuple | None = None      # palm centre, screen fractions
    motion: tuple | None = None    # palm centre, frame fractions, unclamped
    fingers: frozenset | None = None  # extended fingers, thumb not counted
    landmarks: list | None = None  # pose only: all 33 as (x, y, visibility)
    # Pose with `masks` only: how much each pixel of the frame is the person,
    # 0 to 1, the frame's own size.
    mask: np.ndarray | None = None
    # Pose only: how far the shoulders are turned from square on to the
    # camera, in degrees, from the tracker's sense of depth.
    turn: float | None = None


def ensure_model(name):
    """Fetch a model once into models/. They are a few MB and not committed."""
    url = MODEL_URLS[name]
    dest = MODELS_DIR / url.rsplit("/", 1)[1]
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {name} model -> {dest} ...")
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dest)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"could not download the {name} model ({e}).\n"
                         f"Fetch it manually and save it to {dest}:\n  {url}")
    return dest


class HandTracker:
    edges = HAND_EDGES

    def __init__(self, model_file, hand="right"):
        # Two hands, so the other one is seen and passed over. With one, the
        # model takes whichever hand it finds first after losing the last,
        # and the cursor jumps to the other hand.
        self._lm = HandLandmarker.create_from_options(HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_file)),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_hands=2))
        self._label = HAND_LABEL[hand]
        self._last = None  # (t_ms, palm) of the hand followed

    def process(self, rgb, t_ms):
        res = self._lm.detect_for_video(_image(rgb), t_ms)
        seen = []
        for lms, (cat, *_) in zip(res.hand_landmarks, res.handedness):
            ours = cat.score if cat.category_name == self._label else 1 - cat.score
            seen.append((ours, _palm([(p.x, p.y) for p in lms])))
        last = self._last
        if last is not None and t_ms - last[0] > FOLLOW_MS:
            last = None
        i = pick_hand(seen, None if last is None else last[1])
        if i is None:
            return Tracked(edges=self.edges)
        palm = seen[i][1]
        self._last = (t_ms, palm)
        pts = [(p.x, p.y) for p in res.hand_landmarks[i]]
        world = [(p.x, p.y, p.z) for p in res.hand_world_landmarks[i]]
        return Tracked(points=pts, edges=self.edges,
                       pointer=reach_to_screen(pts[8], HAND_REACH),
                       palm=reach_to_screen(palm, HAND_REACH),
                       motion=palm, fingers=fingers_up(world))

    def close(self):
        self._lm.close()


class PoseTracker:
    edges = POSE_EDGES

    def __init__(self, model_file, hand="right", masks=False):
        # `masks` also asks for the person's silhouette, which Physique
        # measures. It costs a few ms a frame, so the tracker the rest of the
        # station uses goes without.
        self._lm = PoseLandmarker.create_from_options(PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_file)),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_poses=1, output_segmentation_masks=masks))
        self._hand = hand

    def process(self, rgb, t_ms):
        res = self._lm.detect_for_video(_image(rgb), t_ms)
        if not res.pose_landmarks:
            return Tracked(edges=self.edges)
        lms = [(p.x, p.y, p.visibility or 0.0) for p in res.pose_landmarks[0]]
        h, w = rgb.shape[:2]
        mask = None
        if res.segmentation_masks:
            # Copied: the view is MediaPipe's own buffer, reused next frame.
            mask = np.array(res.segmentation_masks[0].numpy_view(),
                            np.float32).reshape(h, w)
        turn = None
        if res.pose_world_landmarks:
            a, b = res.pose_world_landmarks[0][11], res.pose_world_landmarks[0][12]
            turn = math.degrees(math.atan2(a.z - b.z, abs(a.x - b.x)))
        return Tracked(points=[(x, y) for x, y, _ in lms], edges=self.edges,
                       pointer=pose_pointer(lms, w, h, self._hand),
                       landmarks=lms, mask=mask, turn=turn)

    def close(self):
        self._lm.close()


def reach_to_screen(p, box, margin=0.15):
    """Map a point inside `box` to screen fractions, or None if well outside.

    A small overshoot is clamped to the edge so the edge buttons are easy to
    hit. Anything further out is treated as not pointing at the screen, which
    keeps a hand that is far off to the side from pinning the cursor to a
    corner button.
    """
    x0, y0, x1, y1 = box
    u = (p[0] - x0) / (x1 - x0)
    v = (p[1] - y0) / (y1 - y0)
    if not (-margin <= u <= 1 + margin and -margin <= v <= 1 + margin):
        return None
    return min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)


def pick_hand(seen, last, near=FOLLOW_NEAR):
    """Which of the hands in view points: an index into `seen`, or None.

    `seen` is (ours, palm) per hand: how sure the model is that it is the
    pointing hand, and its palm centre in frame fractions. `last` is the palm
    of the hand followed a moment ago, or None.

    With two in view, the one surer to be the pointing hand wins: comparing
    the two holds up even when neither label is sure. A hand alone is
    followed if it is called the pointing hand, or is where that hand just
    was; otherwise it is the other hand, and ignored.
    """
    if not seen:
        return None
    i = max(range(len(seen)), key=lambda k: seen[k][0])
    ours, palm = seen[i]
    if len(seen) > 1 or ours >= 0.5:
        return i
    if last is not None and math.dist(palm, last) <= near:
        return i
    return None


def pose_pointer(lms, w, h, hand="right", min_vis=0.5):
    """Screen point for the pointing hand, relative to the body.

    `lms` is the 33 pose landmarks as (x, y, visibility) frame fractions.
    Works in pixels so that shoulder width means the same thing along both
    axes. The hand point is the mean of wrist, pinky and index, which is
    steadier than any one of them. The other hand points only while this one
    is out of view or out of reach (down by the side, say).
    """
    def px(i):
        return lms[i][0] * w, lms[i][1] * h

    if lms[11][2] < min_vis or lms[12][2] < min_vis:
        return None
    (lx, ly), (rx, ry) = px(11), px(12)
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    unit = math.hypot(lx - rx, ly - ry)
    # Side-on, the shoulders overlap and their width collapses towards zero,
    # which would blow the mapping up. Torso length does not collapse.
    if lms[23][2] >= min_vis and lms[24][2] >= min_vis:
        hx = (lms[23][0] + lms[24][0]) / 2 * w
        hy = (lms[23][1] + lms[24][1]) / 2 * h
        unit = max(unit, 0.6 * math.hypot(hx - cx, hy - cy))
    if unit < 1:
        return None

    left, up, right, down = POSE_REACH
    box = (cx - left * unit, cy - up * unit, cx + right * unit, cy + down * unit)
    other = "left" if hand == "right" else "right"
    for side in (hand, other):
        wrist, pinky, index = POSE_HAND[side]
        if lms[wrist][2] < min_vis:
            continue
        pts = [px(i) for i in (wrist, pinky, index)]
        at = reach_to_screen((sum(p[0] for p in pts) / 3,
                              sum(p[1] for p in pts) / 3), box)
        if at is not None:
            return at
    return None


def fingers_up(world):
    """Which fingers are extended, from the 21 hand world landmarks.

    World landmarks are in metres, so this holds for a finger pointing
    straight at the camera, which looks curled in image coordinates. The
    thumb is left out: it folds sideways rather than curling, and no gesture
    here needs it.
    """
    wrist = world[0]
    return frozenset(
        name for name, (_, pip, _, tip) in FINGERS.items()
        if math.dist(wrist, world[tip]) > EXTENDED * math.dist(wrist, world[pip]))


def _palm(pts):
    return (sum(pts[i][0] for i in PALM) / len(PALM),
            sum(pts[i][1] for i in PALM) / len(PALM))


def _image(rgb):
    return Image(image_format=ImageFormat.SRGB, data=rgb)
