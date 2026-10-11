# Shadow Station

The hardware version of Shadow: a portrait monitor and a USB camera in a
case. Step one was the controls: press buttons by pointing, without touching
anything. This is step two: the apps. **Shadow** asks which exercise, bicep
curls or lateral raises, counts a set of it live, reps and each arm's angle,
and shows the set summary, the way the app does. (`--exercise abduction` is
the lateral raise as a clinic measures it, with nothing to pick.)
**Physique** draws a line across your shoulders and one across your waist,
says the ratio, and slaps on the meme the number earns. **Mirror** is just
the camera. **TikTok** is its For You feed, run by hand; it's there for filming,
so it's built to look part of the station rather than to be a feature. The
UI is Shadow's dark theme.

Two halves:

- **The engine, in Python** (OpenCV, MediaPipe, numpy/scipy): the camera,
  tracking, hover-to-press, the set, and the rep counter. The counter is
  shadow-lab's champion, which the app ships, copied in (`station/reps.py`).
- **The UI, a web page** (React, Tailwind, Vite) that the engine serves and
  opens in the station's own Chrome, full screen on the station. It gets
  Shadow's fonts, colours and components the way a site or an app would,
  instead of shapes drawn onto the camera image.

## Run it

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
(cd web && npm install && npm run build)    # the UI, once and after changes
python3 -m station
```

On the first run, the hand and pose models (~17 MB) download into `models/`.
macOS then asks for camera access for your terminal or VS Code. If the wrong
camera opens (an iPhone via Continuity Camera can take index 0), use
`--camera 1`.

The station opens its window on the laptop screen. On the station, pass
`--fullscreen` for kiosk mode, which also draws pages at 2x: on the 1080x1920
monitor they're laid out 540 wide, so the station looks the same and TikTok
picks its phone layout. Closing the window stops the station.

The screen is portrait (9:16). A normal landscape camera gets cropped to the
middle strip of its image, which throws away about 70% of its width. That's
fine on the laptop, but for the station, mount the camera sideways in the
case and pass `--rotate 90` (or `270`, whichever way up it's mounted). Then
the whole sensor is used and a person fits head to toe from much closer.

| Flag | Default | |
|---|---|---|
| `--camera N` | 0 | Which camera. The USB camera will be another index. |
| `--video PATH` | | Play a recording, looping, instead of the camera. |
| `--rotate 0\|90\|180\|270` | 0 | Turns the image upright for a camera mounted sideways. |
| `--start hand\|pose` | hand | The station will start in pose. |
| `--exercise curl\|raise\|abduction` | | Counts sets of this one and skips the choice of exercise. `abduction` is the clinic's set: the lateral raise, in a clinic's words. |
| `--hand right\|left` | right | The hand that points. Hand mode ignores the other one; pose mode uses it only while this one is down. |
| `--dwell S` | 0.8 | Seconds to hover before a press. |
| `--toggle-hold S` | 0.5 | Seconds in the top-right zone to switch hand/pose. `0` switches on entry. |
| `--swipe flick\|drag` | flick | How you flick through TikTok: a quick flick, or a fist dragged up or down. |
| `--auto-finish S` | 10 | End a set once reps have been counted and none has come for S seconds. `0` turns it off. |
| `--no-tiktok` | off | Leaves TikTok off the home screen: for demos. |
| `--fullscreen` | off | Kiosk mode: the window fills its screen. |
| `--quit-apps` | off | Quits the other open apps first, to free memory (see Memory). |
| `--port N` | 8765 | Where the engine serves the UI. |
| `--no-browser` | off | Don't open a window; open the URL in any browser. |
| `--dev` | off | Open the UI's dev server instead (see Working on the UI). |

Keys, in the station's window: `t` hand/pose · `Enter` the screen's main
button · `1` and `2` the exercises · `Esc` back · `p` Physique and `m` Mirror
(from home) · `d` HUD · `f` fullscreen · `q` quit.

The HUD is for whoever is running the station: the frame rate, and on the
summary, the live count beside the analysed one and whether the analysis
was sure of itself. None of that is on the screens themselves; it is also
in the terminal's log.

### Memory

The laptop has 8 GB, and with other apps open the station's memory gets
pushed out to disk, which costs frame rate. Before filming, start it with
`--quit-apps`: every app in the Dock is asked to quit, the way Cmd-Q asks.
An app with unsaved work puts up its own dialog and stays open; the terminal
names those and waits for Enter. Nothing is force-quit.

Finder stays, and so does whatever the station was started from. Started
from VS Code's terminal, VS Code stays, and it is the biggest of them: for
the most memory, start the station from Terminal with VS Code closed.
`KEEP` and `BACKGROUND` in `station/preflight.py` hold the exceptions.

`quit-apps` does the same on its own, from any terminal and any folder, and
`quit-apps --list` only names what it would quit. It is the `quit-apps` file
here, linked onto the PATH once:

```sh
ln -s "$PWD/quit-apps" /opt/homebrew/bin/quit-apps
```

## Using it

Point with your right index finger; the cursor sits on your fingertip, and
your left hand is ignored (`--hand left` swaps them). Hover on a button and
hold still until the ring fills to press it (0.8 s). Pose mode points with
your raised right hand, or your left while the right is down, measured in
shoulder widths from your shoulders, so the same gesture lands in the same place whether you are
1 m or 4 m away. **HAND | POSE** (top right, on every screen) is a zone: keep
your hand in it for `--toggle-hold` seconds to switch.

Top left is always the way back, top right always the mode toggle.

1. **Home**: choose hand or pose, then an app.
2. **Shadow, the exercise**: Bicep curl or Lateral raise. Its heading sits
   where Shadow's row was on home, so the hand that pressed Shadow isn't
   already on one of them. Back goes home. With `--exercise` there is no
   such screen: Shadow goes straight to the set.
3. **Shadow, the set**: step back until your shoulders, elbows, hands and
   hips are in view. For a lateral raise there also has to be room for your
   arms out to the sides: at the top your hands are an arm's length
   out from your shoulders. The station says what to fix (STEP IN, STEP
   BACK, STEP CLOSER, HANDS HIDDEN...). Once you're in position and holding
   still, a 3 s countdown starts, and moving out of position calls it off.
   Or press **Start** at the screen for a 6 s countdown that gives you time
   to walk back. Then lift: the big number is the live count, with a ring
   thrown out as each rep lands, and a goniometer on each arm shows its
   angle: at the elbow for a curl (flexion, read from straight, so the arm
   that isn't curling shows nothing), at the shoulder for a lateral raise. The
   live count sits at 0 for the first 3.5 s while it finds your range, then
   jumps to the true number. Two reps in a row that stop short, at the top
   or on the way back down, and the station shows it, big enough to see from
   where you lift: your arms and the count turn amber, and a ring on the
   camera marks where each hand should get to, with the way there dotted in.
   "HALF REPS" and a line about what to do sit above, for whoever is
   watching. The reps count all the same, and one full rep takes it all
   away. The set ends when you press **Finish set**
   (raise a hand to the top left, in pose mode), or by itself 10 s after
   your last rep; `--auto-finish 4` gets to the summary sooner when filming.
   Back, before the set starts, goes to the exercises.
4. **Shadow, the summary**: the count from the full analysis, which
   replaces the live number, and the set's time. Each arm's peak angle (its best rep and its
   average) and how far apart the arms were; in a one-arm set, the arm that
   hung still is marked not used and left off the chart. Fatigue: how much
   the lifting speed dropped from the first rep to the last (the app's
   intensity score), and under the chart, the speed of each rep as a bar.
   The angle through the set with a tick where each rep finished, and the
   set replayed with its skeleton and goniometer. **Next set** goes again,
   the same exercise; **Done** goes home.

   Arms are named by where they are on screen: the camera is mirrored, so
   the arm on the left of the screen is your left. A `--video` isn't
   mirrored, and names them the other way round.
5. **Physique** (switches to pose mode, and back when you leave): the
   camera as it is, like the mirror. Stand square on to the screen with
   your shoulders and hips in view and your arms down, a little out from
   your sides. A line lands across your shoulders and another across your
   waist; hold still for a second and a half and the number runs up:
   shoulder width over waist width. A moment later the verdict is slapped
   on beside it, a meme picked by the number. It is measured once: after
   that the two lines stay on your body through whatever pose you strike.
   Step out of view for a few seconds, or press `Enter`, and it starts
   again. See Physique below for what is being measured, and how to change
   the memes.
6. **Mirror**: the camera, full screen, sent sharper than on the other
   screens and before tracking, to keep the delay down. Back and the toggle
   fade out when nobody is pointing and come back when you point.
7. **TikTok** (switches to hand mode): the window goes over to TikTok's For
   You feed, which can't be embedded in the station's page. The station's
   cursor and a Back button in its style are drawn into TikTok's page.
   Hovering still on anything else clicks it; flick up for the next video,
   down for the previous one. Back comes home. The first time, log in and
   answer TikTok's cookie prompt in the station's window with the laptop's
   mouse; the station's Chrome profile (`~/.shadow-station/chrome`) keeps
   it. Search is out: it asks for a captcha every time.

After a press, nothing else can be pressed until the cursor has moved a
little, so a hand left where it was doesn't press the next screen's button.

Every press and set is logged in the terminal:

```
   12.41s  press shadow   after 0.82s hovering
   14.02s  press raise    after 0.81s hovering
   48.07s  set 1, lateral raise: 8 reps (live 8), peak left 94°, right 92°, fatigue 12, confident
   61.30s  swipe up
```

## Rep counting

`station/reps.py` is shadow-lab's champion config (`bodycount_robust`), the
same algorithm as the app's `rep_counter.dart`, with two exercises set up.
The curl follows the elbow, and the lifter rests at the top of its angle
(arm straight). The lateral raise follows the shoulder and rests at the
bottom; the clinic's shoulder abduction is the same counter under another
name (`EXERCISES` in `station/engine.py` holds each one's words). The lateral raise
was checked against the lab's own implementation over all 37 lateral
raise captures in shadow-lab: the live count, the final count and
confidence all match, and intensity is the same or one point higher (the
lab truncates the score where the app and the station round it). Against the
labelled counts it gets 36 of 37 sets exactly right after the set and 32
live. The curl is the same code with the other config and hasn't had that
check against the lab here; the tests run both.

Angles on screen are measured flat on the picture. For a lateral raise,
which stays in the picture's plane, that is the real angle. For a curl it isn't
quite: at the top the forearm comes towards the camera, and the reading
runs high (about 160 on the curl clips, where an elbow bends to 145 or 150
at most). An arm's best in a rep is the highest it held for a quarter of a
second, so the frames where forearm and upper arm line up and read 180
don't count.

One thing the station does that the app doesn't: it cuts the stillness off
both ends of the set before analysing it (`station/workout.py`). App users
trim their recordings; the station's sets start when the countdown ends and
finish with 10 s of standing still (the auto-finish wait) or a walk to the
screen. On a lateral raise the start is what matters, because the lift is
timed from rest to the top: 1-4 s of standing still before the first rep
moved intensity by 5-8 points on average, and 36 on one set. With the cut,
the lab's 32 MediaPipe lateral raise captures keep every count but one,
which moves to the right answer, and intensity moves by 3-4.5 points. (On curls it's the end that matters: 10 s left on changed one
count from 7 to 21.)

### Half reps

`station/halfreps.py` watches each arm's angle turn round at the top and the
bottom of every rep, and leaves the count alone. A rep is short at the top
when it stays under 65° at the shoulder or 100° of elbow flexion, and short
at the bottom when the arm doesn't come back under 50° (`FULL`). Two in a
row short at the same end (`RUN`) and the terminal logs it and the engine
tells the page which end and which arms (`short`, in a frame's `live`). A
rep that gets there takes it back at once, and so does stopping. In a
one-arm set the arm that hangs is left out; when both arms lift, both have
to be short.

The lifter is a few metres back and mid-rep, so the page shows it rather
than says it (`drawTargets` in `web/src/components/Feed.jsx`): the short
arms in amber, a ring where each hand belongs at that end of the rep, and
the hand's path to it. For a raise that is level with the shoulder, or back
down by the hip; for a curl, up by the shoulder, or where a straight arm
puts the hand. The count goes amber with them. The words above ("HALF
REPS", and the exercise's line from `short` in `EXERCISES`) are the caption.
The ring marks a full rep, which is further than the line that clears the
cue, so it goes before the hand reaches it. The clinic's abduction set has
no line for it and shows nothing: there, how far the arm gets is what is
being measured.

## Physique

`station/physique.py`. The pose model gives a mask of which pixels are the
person as well as its landmarks. Landmarks sit on joint centres, so they say
where to look but not how wide anything is; the mask says where the body
ends. Both measures are widths across the mask at a place the landmarks
pick: across the shoulder joints (so the deltoids count), and the narrowest
row between the ribs and the hips.

Nothing knows how far away the camera is, so there are no centimetres, only
the one width over the other. These are widths, not the tape-measure
circumferences the golden ratio (1.618) is usually quoted for: a width
ratio runs a little higher. And the silhouette is whatever the camera sees,
so a loose top reads as a wide waist: a hoodie read 1.40 on someone who
reads 1.7 with it off.

Each is only read in a pose it can be read in. Shoulders need both arms
down: a raised arm carries the outline out along it. The waist needs the
trunk's edge, and where an arm hangs against the body the mask doesn't open
up, but it does dip, so the crease is used as the edge. Turned from square,
nothing is read; turned is judged by how far apart your shoulders are
against how far apart they have usually been, since the tracker's own sense
of depth read differently on the same clip mirrored.

The number is measured once: the median of 1.5 s (`MEASURE_S`) of standing
still and readable. Moving more than 15% of your trunk's length from where
the wait began starts it again, so walking in isn't measured. After that
the two lines are kept in the body's own terms (how far down the trunk, how
far either side of its middle) and drawn on the landmarks each frame, so
they stay on you through a flex, where the shoulders couldn't be read
again.

The verdicts are `VERDICTS` at the top of `station/physique.py`: for each
band, the least the number must be, a picture and the words over it. The
pictures are `web/public/memes/<name>.jpg` (rebuild the UI after changing
them); a missing picture leaves the words on a black sticker. As it stands:
1.62 and up Gigachad, 1.54 Swole Doge, 1.46 Stonks, 1.38 "it ain't much,
but it's honest work", 1.28 Hide the Pain Harold, and under that "this is
fine". The pictures are meme templates off the web, not the project's own.

On a clip of one person, top off: 1.68 to 1.71 whichever second of the clip
it starts from. It hasn't met a second body or the station's own camera
yet.

## Working on the UI

The UI lives in `web/`. `npm run build` puts it in `web/dist`, which the
engine serves. While styling, run the dev server for hot reload:

```sh
cd web && npm run dev                # :5173, passes /ws through to the engine
python3 -m station --dev             # in another terminal
```

- Shadow's design tokens (colours, radii, Space Grotesk) are Tailwind theme
  values in `web/src/index.css`, taken from the app's design system: its
  dark theme, with secondary text a step lighter than the app's, to read
  across a room and on film. Surfaces over the camera are `.glass`; big
  numbers over it are `.lit`.
- The page is a 9:16 stage, and 1rem is 1/45 of its width (16px on the 720px
  design canvas, 24px on a 1080px monitor), so everything scales together.
- Anything pressable is a `<Pressable id=...>`. It reports its rect to the
  engine, which hit-tests the cursor and runs the dwell. The page never
  decides a press itself.

## How the pieces talk

The engine runs the camera loop on the main thread and an aiohttp server on
another, with one WebSocket to the page:

- engine → page: `state` messages (screen, mode, the set summary) when they
  change; `pressed` events; and ~30 frames a second, each a JSON header
  (cursor, hover progress, skeleton, the live set) followed by the JPEG. A
  slow page drops frames rather than falling behind.
- page → engine: `layout` (where its buttons are, as fractions of the
  stage) and `key`.

The engine owns all the state, so reloading the page loses nothing.

## Not solved yet

- **Hand tracking range.** The hand detector needs your hand to fill a decent
  part of the frame. Find how far back hand mode still works with the
  station's camera. That decides whether you have to walk up to the screen
  between sets.
- **Controls during a set.** Lateral raises keep your hands at shoulder
  height and out wide, past pose mode's reach box, so the pointer stays off
  Finish and the toggle. An overhead press would put a hand in the
  top-right zone or on Finish. Other exercises will need the controls
  locked while a set is running.
- **Short reps the count drops.** The live counter's bands sit at fractions
  of the range the set has shown so far. Reps that are short from the first
  one are counted. Reps that shrink part-way through a set are not, once
  they get less than about 70% of the way the earlier ones did, and neither
  are reps that stop coming back down (staying above about 30% of the way
  up). Auto-finish and the tail cut both go by the live counter's last rep,
  so the summary loses them too, and the set can end itself while they are
  still being lifted: 4 full made-up reps and then 6 half ones read 4 live
  and 5 on the summary. The analysis counts all 10 when it is given the
  whole recording. The half-rep cue comes up in both cases, over a count
  that has stopped.
- **Half-rep thresholds and targets.** `FULL` in `station/halfreps.py` is
  from one filmed set of lateral raises and from geometry, and has only met
  made-up sets. A curl facing the camera is the one to try first: its elbow
  angle is the least true of the readings, and its rings are placed from a
  forearm that points at the camera for half the rep.
- **Pose reach box.** `POSE_REACH` in `station/tracking.py` is a first guess.
  Tune it with the real camera in its real position.
- **Tested on clips, not in front of the station.** Everything has been run
  end to end through the engine with recordings standing in for the camera:
  barbell curls and lateral raises from the app's share videos, and one clip
  of someone posing for Physique. The framing thresholds
  (`station/workout.py`) and Physique's (`station/physique.py`) haven't met
  the station's camera yet, and a one-arm dumbbell curl has only been run
  as a made-up set. The choice of exercise has only been pressed by a
  scripted fingertip, on made-up sets of each.
- **Physique on other bodies.** See Physique above: one person, top off.
  Where the bands between the memes should sit is a guess until it has met
  more people.

Tried and dropped: pinching to press (the tracker can't reliably tell
whether two fingertips touch), and pressing with a fist or two fingers
(hovering won).

## Code

- `station/app.py`: the CLI; starts the engine, the server and the window.
- `station/engine.py`: the main loop: frames in, tracking, presses, screens,
  frames out.
- `station/workout.py`: one set: the framing check, countdown, recording,
  auto-finish and the tail cut. Pure logic, no camera.
- `station/reps.py`: the rep counter and intensity. Pure logic.
- `station/halfreps.py`: says when reps keep stopping short of the full
  range. Pure logic.
- `station/physique.py`: shoulders over waist off the silhouette, and the
  meme the number earns. No camera.
- `station/press.py`: hovering becomes presses. Pure logic.
- `station/tracking.py`: MediaPipe hand/pose, and where on screen you're
  pointing.
- `station/camera.py`: the camera or a video file, on the portrait canvas.
- `station/preflight.py`: quits the other apps before a run, for
  `--quit-apps` and the `quit-apps` command.
- `station/server.py`: serves `web/dist` and the WebSocket.
- `station/browser.py`: the station's own Chrome, over the DevTools
  protocol.
- `station/tiktok.py`: TikTok in the station's window: the overlay,
  hover-clicks, swipes as arrow keys, Back.
- `station/swipe.py`: flick and fist-drag swipes. Pure logic.
- `web/src/`: the UI. `station.js` is the connection; `screens/` has Home,
  Pick (the exercises), Workout, Summary, Physique, Mirror, and the moment
  TikTok is opening.

Tests (no camera needed): `python3 -m unittest`
