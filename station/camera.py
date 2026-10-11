"""Frames in: the camera, or a video file standing in for it.

Both hand back portrait (9:16) frames at the source's own resolution, up to
MAX_W wide, so nothing downstream knows which it is. `to_canvas` brings one
to the 720x1280 canvas everything else works on; the mirror shows the
original.
"""

import time

import cv2

CANVAS_W, CANVAS_H = 720, 1280
# The station's monitor is 1080 wide; anything sharper is never seen.
MAX_W = 1080
ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}


class Camera:
    """A live camera, mirrored so the screen works like a mirror."""

    mirrored = True

    def __init__(self, index, rotate=0):
        self.rotate = rotate
        self._cap = cv2.VideoCapture(index)
        # Ask for 1080p: a landscape camera loses most of its width to the
        # portrait crop, so start from as many pixels as it will give.
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        if not self._cap.isOpened():
            raise SystemExit(
                f"could not open camera {index}.\n"
                "On macOS, allow camera access for your terminal (or VS Code) "
                "in System Settings > Privacy & Security > Camera, then rerun.\n"
                "If another camera opened instead, try --camera 1.")

    def read(self):
        ok, frame = self._cap.read()
        return portrait(frame, self.rotate, mirror=self.mirrored) if ok else None

    def close(self):
        self._cap.release()


class VideoFile:
    """A recording played at its own speed, looping, for testing without
    standing in front of the camera. Not mirrored: it was filmed facing the
    lifter, not reflecting them."""

    mirrored = False

    def __init__(self, path, rotate=0):
        self.rotate = rotate
        self._cap = cv2.VideoCapture(str(path))
        if not self._cap.isOpened():
            raise SystemExit(f"could not open video {path}")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._step = 1 / fps if fps and fps > 0 else 1 / 30
        self._next = None

    def read(self):
        now = time.monotonic()
        if self._next is not None and now < self._next:
            time.sleep(self._next - now)
        self._next = max(now, self._next or now) + self._step
        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return portrait(frame, self.rotate, mirror=self.mirrored) if ok else None

    def close(self):
        self._cap.release()


def portrait(frame, rotate=0, mirror=True):
    """A camera frame cut to 9:16, at most MAX_W wide.

    Turned upright first, for a camera mounted sideways; that uses the whole
    sensor. Whatever is still wider than 9:16 after that (any landscape camera
    left the normal way up) is cropped to its middle strip.
    """
    if rotate:
        frame = cv2.rotate(frame, ROTATIONS[rotate])
    if mirror:
        frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    if w * CANVAS_H > h * CANVAS_W:
        cw = round(h * CANVAS_W / CANVAS_H)
        frame = frame[:, (w - cw) // 2:(w - cw) // 2 + cw]
    elif w * CANVAS_H < h * CANVAS_W:
        ch = round(w * CANVAS_H / CANVAS_W)
        frame = frame[(h - ch) // 2:(h - ch) // 2 + ch]
    if frame.shape[1] > MAX_W:
        frame = cv2.resize(frame, (MAX_W, MAX_W * CANVAS_H // CANVAS_W),
                           interpolation=cv2.INTER_AREA)
    return frame


def to_canvas(frame):
    """A portrait frame at the canvas size, 720x1280."""
    h, w = frame.shape[:2]
    if (w, h) == (CANVAS_W, CANVAS_H):
        return frame
    interp = cv2.INTER_AREA if w > CANVAS_W else cv2.INTER_LINEAR
    return cv2.resize(frame, (CANVAS_W, CANVAS_H), interpolation=interp)
