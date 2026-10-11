"""Chrome, driven over the DevTools protocol.

The station opens its UI in its own Chrome, with its own profile, as an app
window (no tabs or address bar) or in kiosk mode on the station's monitor.
Over the DevTools connection the station notices the window has closed, and
TikTok mode takes the window over: the hand cursor becomes mouse moves and
clicks, gestures become key presses. Input sent this way reaches the page
whether or not Chrome has focus.
"""

import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Outside the repo: it holds TikTok's login cookies.
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
             # TikTok's videos start with sound, without a click first.
             "--autoplay-policy=no-user-gesture-required",
             # Pages that follow the system theme come up dark: TikTok is
             # filmed in its dark mode. The station's own page is light.
             "--force-dark-mode", "--hide-scrollbars",
             f"--window-position={position[0]},{position[1]}",
             f"--window-size={size[0]},{size[1]}",
             f"--app={url}", *extra_args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = _wait_for_port(port_file, self._proc)
        self._port = port
        self._checked, self._open = 0.0, True
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

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", format="png")["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def alive(self):
        """Whether the page is still open. On macOS, closing the window
        leaves Chrome running, so this asks Chrome for its pages, at most
        once a second."""
        now = time.monotonic()
        if now - self._checked >= 1.0:
            self._checked = now
            try:
                self._open = bool(_pages(self._port))
            except OSError:
                self._open = False
        return self._open

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
        pages = _pages(port)
        if pages:
            return pages[0]
        time.sleep(0.1)
    raise RuntimeError("Chrome started but opened no page")


def _pages(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list",
                                timeout=2) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]
