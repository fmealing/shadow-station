"""Chrome, driven over the DevTools protocol.

The station launches its own Chrome with its own profile, so a TikTok login
lives there and nowhere else, and drives the page directly: the hand cursor
becomes mouse moves and clicks, gestures become key presses and scrolls.
Input sent this way reaches the page whether or not Chrome has focus, so the
camera window never has to fight Chrome for it.
"""

import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Outside the repo: it holds login cookies.
PROFILE = Path.home() / ".shadow-station" / "chrome"

KEY_CODES = {"ArrowDown": 40, "ArrowUp": 38, "Enter": 13, "Escape": 27}


class Chrome:
    def __init__(self, url, position=(0, 0), size=(1080, 1920), extra_args=()):
        PROFILE.mkdir(parents=True, exist_ok=True)
        port_file = PROFILE / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        self._proc = subprocess.Popen(
            [CHROME, f"--user-data-dir={PROFILE}",
             # 0 picks a free port; Chrome writes it to DevToolsActivePort.
             "--remote-debugging-port=0",
             "--no-first-run", "--no-default-browser-check",
             # Videos start with sound without a click first.
             "--autoplay-policy=no-user-gesture-required",
             f"--window-position={position[0]},{position[1]}",
             f"--window-size={size[0]},{size[1]}",
             f"--app={url}", *extra_args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = _wait_for_port(port_file, self._proc)
        ws_url = _page_target(port)["webSocketDebuggerUrl"]
        # Chrome refuses DevTools sockets that carry an Origin header.
        self._ws = websocket.create_connection(ws_url, timeout=30,
                                               suppress_origin=True)
        self._id = 0

    def send(self, method, **params):
        self._id += 1
        self._ws.send(json.dumps({"id": self._id, "method": method,
                                  "params": params}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def goto(self, url):
        self.send("Page.navigate", url=url)

    def evaluate(self, js):
        res = self.send("Runtime.evaluate", expression=js, returnByValue=True,
                        awaitPromise=True)
        return res.get("result", {}).get("value")

    def key(self, key):
        for kind in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", type=kind, key=key, code=key,
                      windowsVirtualKeyCode=KEY_CODES[key])

    def move(self, x, y):
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)

    def click(self, x, y):
        self.move(x, y)
        for kind in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y,
                      button="left", clickCount=1)

    def scroll(self, x, y, dy):
        self.send("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y,
                  deltaX=0, deltaY=dy)

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", format="png")["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def close(self):
        try:
            self.send("Browser.close")
        except Exception:
            self._proc.terminate()
        self._ws.close()


def _wait_for_port(port_file, proc, timeout=20):
    end = time.monotonic() + timeout
    # A Chrome already running on this profile takes the launch over and the
    # new process exits at once, without ever opening the port.
    while time.monotonic() < end and proc.poll() is None:
        if port_file.exists():
            first = port_file.read_text().split("\n", 1)[0].strip()
            if first.isdigit():
                return int(first)
        time.sleep(0.1)
    raise RuntimeError("Chrome did not start. If the station's Chrome is "
                       "already open (say from logging in), quit it first.")


def _page_target(port, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as r:
            pages = [t for t in json.load(r) if t.get("type") == "page"]
        if pages:
            return pages[0]
        time.sleep(0.1)
    raise RuntimeError("Chrome started but opened no page")
