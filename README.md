# Shadow Station

The hardware version of Shadow: a portrait monitor and a USB camera in a
case. This is step one, the controls. It's a test program that starts the
camera, tracks you, and lets you press buttons at the top of the screen
without touching anything.

Python, OpenCV and MediaPipe, the same stack as shadow-lab. That means the
rep counter in `shadow-lab/lab/algo` can come across later without a port.

## Run it

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m station
```

On the first run, the hand and pose models (~17 MB) download into `models/`.
macOS then asks for camera access for your terminal or VS Code. If the wrong
camera opens (an iPhone via Continuity Camera can take index 0), use
`--camera 1`.

The screen is portrait (9:16). A normal landscape camera gets cropped to the
middle strip of its image, which throws away about 70% of its width. That's
fine on the laptop, but for the station, mount the camera sideways in the
case and pass `--rotate 90` (or `270`, whichever way up it's mounted). Then
the whole sensor is used and a person fits head to toe from much closer.

| Flag | Default | |
|---|---|---|
| `--camera N` | 0 | Which camera. The USB camera will be another index. |
| `--rotate 0\|90\|180\|270` | 0 | Turns the image upright for a camera mounted sideways. |
| `--start hand\|pose` | hand | The station will start in pose. This test starts in hand. |
| `--swipe flick\|drag` | flick | How you swipe up and down. `s` switches live. |
| `--dwell S` | 0.8 | Seconds to hover before a press or click. |
| `--toggle-hold S` | 0.5 | Seconds in the top-right zone to switch hand/pose. `0` switches on entry. |
| `--fullscreen` | off | `f` toggles it live. |

Keys: `s` swipe method · `t` hand/pose · `d` HUD · `f` fullscreen · `q`/Esc quit.

## Using it

Point with your index finger; the cursor sits on your fingertip. Hover on
something and hold still until the ring fills to press it (0.8 s). Pose mode
points with whichever hand is raised higher, measured in shoulder widths from
your shoulders, so the same gesture lands in the same place whether you are
1 m or 4 m away.

- **TikTok** (top left, hand mode) opens the station's Chrome on TikTok's
  For You feed, beside the camera window on the laptop screen. There:
  - Your cursor is drawn on the TikTok page, and hovering still on anything
    clicks it: hover on a video to pause it, for example. A hand left
    still clicks once, not over and over.
  - Swipe up for the next video, down for the previous one.
  - Hover the **Close** box in TikTok's top-right corner to close it and get
    the station's buttons back.
- **Shadow** is still a placeholder: pressing it shows a toast.
- **HAND | POSE** (top right) is a zone. Keep your hand in it for
  `--toggle-hold` seconds to switch modes.
- A big arrow shows each swipe.

The first time you open TikTok, the station's Chrome may need you to log
in. Quit any other window of the station's Chrome first: two can't share its
profile.

Swiping:

- **Flick**: a quick flick up or down. After a flick, the opposite direction
  is ignored for 0.7 s, so bringing your hand back doesn't swipe back.
- **Drag**: make a fist, move up or down, open your hand. One swipe per
  grab. The HUD shows `FIST` while it sees one: a finger counts as up when
  its tip is further from the wrist than its middle joint.

For a second after a swipe, presses and clicks are ignored: a flick up
carries the cursor to the top of the screen.

Every press and swipe is logged in the terminal:

```
   12.41s  press #3   tiktok  dwell, 0.82s hovering
   15.02s  press #4   toggle  zone, 0.50s hovering
   18.77s  swipe #1   up      flick, next video
```

Count the misfires (a press or swipe you didn't mean) and the misses (one
that didn't register). The swipe thresholds in `station/swipe.py` are first
guesses.

Tried and dropped: pinching to press (the tracker can't reliably tell
whether two fingertips touch), and pressing with a fist or two fingers
(hovering won).

## Not solved yet

- **Hand tracking range.** The hand detector needs your hand to fill a decent
  part of the frame. Find how far back hand mode still works with the
  station's camera. That distance decides whether the app menu needs you to
  step forward.
- **Controls during a set.** In pose mode, locking out an overhead press puts
  a hand in the top-right zone. The controls need to lock while a set is
  running.
- **TikTok's feed.** Search asks for a captcha every time, so the plan is a
  station account whose For You feed is trained on brainrot. On the
  station's portrait monitor TikTok should go full screen, with page zoom
  to get its compact layout; so far it's only been run in a window.
- **Pose reach box.** `POSE_REACH` in `station/tracking.py` is a first guess.
  Tune it with the real camera in its real position.

## Code

- `station/press.py`: hovering becomes presses and clicks. Pure logic, no
  camera.
- `station/swipe.py`: flicks and fist drags become up/down swipes. Pure
  logic.
- `station/tiktok.py`: TikTok mode: the cursor overlay, hover-clicks, swipes
  as arrow keys, the Close zone.
- `station/tracking.py`: MediaPipe hand/pose, where on screen you're
  pointing, and which fingers are up.
- `station/browser.py`: the station's own Chrome, driven over the DevTools
  protocol.
- `station/ui.py`: drawing, in Shadow's dark-theme colours.
- `station/app.py`: camera loop, keys, CLI.

Tests (no camera needed): `python3 -m unittest`
# shadow-station
