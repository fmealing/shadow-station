"""Everything drawn over the camera feed: top bar, cursor, landmarks, HUD.

Colours are Shadow's dark theme (lib/theme/app_theme.dart in the app), in
OpenCV's BGR order. Sizes are designed for the 720x1280 portrait canvas and
go through `scale`, so the layout holds at any size.
"""

import cv2
import numpy as np

from .press import Button

PRIMARY = (213, 123, 58)     # #3A7BD5 electric blue
SECONDARY = (245, 163, 91)   # #5BA3F5 lighter blue
TEXT = (248, 239, 232)       # #E8EFF8 cool white
CARD = (39, 24, 17)          # #111827 card surface
MUTED = (128, 96, 74)        # #4A6080 slate

FONT = cv2.FONT_HERSHEY_DUPLEX
AA = cv2.LINE_AA

TOGGLE = "toggle"
# Placeholders: pressing one only shows a toast until the apps exist.
APPS = (("shadow", "Shadow"), ("tiktok", "TikTok"))

FLASH_S = 0.4
TOAST_S = 1.4
SWIPE_S = 0.6


def scale(w, h):
    """Size multiplier against the 720x1280 design canvas. The smaller axis
    wins, so nothing outgrows a canvas of a different shape."""
    return min(w / 720, h / 1280)


def layout(w, h, mode, toggle_hold):
    """The top bar. The hand/pose toggle is a zone in the top-right corner in
    both modes, since pose mode needs a way back; the app buttons only exist
    in hand mode."""
    s = scale(w, h)
    # margin, bar height, toggle width, app button width: fills 720 across
    m, bh, tw, bw = (round(v * s) for v in (20, 96, 250, 195))
    buttons = [Button(TOGGLE, "", (w - m - tw, m, tw, bh), hold_s=toggle_hold)]
    if mode == "hand":
        for i, (id_, label) in enumerate(APPS):
            buttons.append(Button(id_, label, (m + i * (bw + m), m, bw, bh)))
    return buttons


def draw_landmarks(img, tracked):
    if not tracked.points:
        return
    h, w = img.shape[:2]
    pts = [(round(x * w), round(y * h)) for x, y in tracked.points]
    used = {i for edge in tracked.edges for i in edge}
    for a, b in tracked.edges:
        cv2.line(img, pts[a], pts[b], SECONDARY, 2, AA)
    for i in used:
        cv2.circle(img, pts[i], 4, TEXT, -1, AA)


def draw_bar(img, buttons, mode, presser, flashes, t):
    s = scale(img.shape[1], img.shape[0])
    for b in buttons:
        x, y, w, h = b.rect
        r = round(18 * s)
        hovered = presser.hovered is not None and presser.hovered.id == b.id
        _fill(img, b.rect, r, CARD, 0.78)
        if hovered and presser.progress > 0:
            _fill(img, b.rect, r, PRIMARY, 0.6, frac=presser.progress)
        flash = 1 - (t - flashes.get(b.id, -1e9)) / FLASH_S
        if flash > 0:
            _fill(img, b.rect, r, SECONDARY, 0.8 * flash)
        _outline(img, b.rect, r, SECONDARY if hovered else MUTED,
                 3 if hovered else 1)

        if b.id == TOGGLE:
            pad = round(8 * s)
            half = (w - 3 * pad) // 2
            for k, name in enumerate(("hand", "pose")):
                seg = (x + pad + k * (half + pad), y + pad, half, h - 2 * pad)
                active = name == mode
                if active:
                    _fill(img, seg, r - pad // 2, PRIMARY, 0.95)
                _text(img, name.upper(), (seg[0] + half / 2, y + h / 2),
                      0.9 * s, TEXT if active else MUTED)
        else:
            _text(img, b.label, (x + w / 2, y + h / 2), 1.2 * s, TEXT)


def draw_cursor(img, p, progress, held):
    s = scale(img.shape[1], img.shape[0])
    p = (round(p[0]), round(p[1]))
    r = round(16 * s)
    cv2.circle(img, p, r, CARD, round(6 * s), AA)
    cv2.circle(img, p, r, TEXT, round(2 * s) or 1, AA)
    if held:
        cv2.circle(img, p, round(9 * s), SECONDARY, -1, AA)
    if progress > 0:
        ring = round(27 * s)
        # White, not blue: it sits over the button's blue dwell fill.
        cv2.ellipse(img, p, (ring, ring), -90, 0, 360 * progress, TEXT,
                    round(6 * s), AA)


def draw_toast(img, label, sub, since):
    strength = 1 - since / TOAST_S
    if strength <= 0:
        return
    h, w = img.shape[:2]
    s = scale(w, h)
    bw, bh = round(520 * s), round(150 * s)
    rect = ((w - bw) // 2, round(h * 0.55), bw, bh)
    _fill(img, rect, round(22 * s), CARD, 0.85 * min(1, strength * 2))
    _text(img, label, (w / 2, rect[1] + bh * 0.4), 1.6 * s, TEXT, 2)
    _text(img, sub, (w / 2, rect[1] + bh * 0.75), 0.8 * s, MUTED, 1)


def draw_swipe(img, way, since):
    """A big arrow in the direction of the swipe, rising or falling as it
    fades."""
    strength = 1 - since / SWIPE_S
    if strength <= 0:
        return
    h, w = img.shape[:2]
    s = scale(w, h)
    sign = -1 if way == "up" else 1
    cy = h * 0.42 + sign * (1 - strength) * 60 * s
    tail = (round(w / 2), round(cy - sign * 110 * s))
    tip = (round(w / 2), round(cy + sign * 110 * s))
    overlay = img.copy()
    cv2.arrowedLine(overlay, tail, tip, CARD, round(34 * s), AA, tipLength=0.45)
    cv2.arrowedLine(overlay, tail, tip, SECONDARY, round(22 * s), AA,
                    tipLength=0.45)
    cv2.addWeighted(overlay, 0.9 * strength, img, 1 - 0.9 * strength, 0, img)


def draw_banner(img, text):
    """A notice across the top, where the bar sits when it is showing."""
    h, w = img.shape[:2]
    s = scale(w, h)
    m, bh = round(20 * s), round(64 * s)
    rect = (m, m, w - 2 * m, bh)
    _fill(img, rect, round(18 * s), CARD, 0.85)
    _outline(img, rect, round(18 * s), SECONDARY, 2)
    _text(img, text, (w / 2, m + bh / 2), 0.7 * s, TEXT, 1)


def draw_hud(img, lines):
    h, w = img.shape[:2]
    s = scale(w, h)
    step = round(30 * s)
    y = h - round(20 * s) - step * (len(lines) - 1)
    for line in lines:
        org = (round(20 * s), y)
        cv2.putText(img, line, org, FONT, 0.65 * s, CARD, 4, AA)
        cv2.putText(img, line, org, FONT, 0.65 * s, TEXT, 1, AA)
        y += step


def _fill(img, rect, r, color, alpha, frac=1.0):
    """Blend `color` into a rounded rect, optionally only its left `frac`."""
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return
    mask = np.zeros((h, w), np.uint8)
    r = max(0, min(r, w // 2, h // 2))
    cv2.rectangle(mask, (r, 0), (w - 1 - r, h - 1), 255, -1)
    cv2.rectangle(mask, (0, r), (w - 1, h - 1 - r), 255, -1)
    for cx, cy in ((r, r), (w - 1 - r, r), (r, h - 1 - r), (w - 1 - r, h - 1 - r)):
        cv2.circle(mask, (cx, cy), r, 255, -1, AA)
    if frac < 1:
        mask[:, round(w * frac):] = 0
    a = (mask.astype(np.float32) / 255 * alpha)[..., None]
    roi = img[y:y + h, x:x + w]
    roi[:] = (roi * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


def _outline(img, rect, r, color, thickness):
    x, y, w, h = rect
    x2, y2 = x + w - 1, y + h - 1
    for a, b in (((x + r, y), (x2 - r, y)), ((x + r, y2), (x2 - r, y2)),
                 ((x, y + r), (x, y2 - r)), ((x2, y + r), (x2, y2 - r))):
        cv2.line(img, a, b, color, thickness, AA)
    for c, start in (((x + r, y + r), 180), ((x2 - r, y + r), 270),
                     ((x2 - r, y2 - r), 0), ((x + r, y2 - r), 90)):
        cv2.ellipse(img, c, (r, r), start, 0, 90, color, thickness, AA)


def _text(img, label, center, size, color, thickness=2):
    (tw, th), _ = cv2.getTextSize(label, FONT, size, thickness)
    org = (round(center[0] - tw / 2), round(center[1] + th / 2))
    cv2.putText(img, label, org, FONT, size, color, thickness, AA)
