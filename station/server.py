"""The station's web server: the UI's files, and one WebSocket to the engine.

The engine runs the camera loop on the main thread; this runs an asyncio loop
on a thread of its own. Between the two:

- `publish_frame(header, jpeg)` hands over the newest frame. Each client gets
  the latest one whenever it is ready for another, so a slow page drops frames
  instead of falling behind.
- `publish(msg)` sends a JSON message to every page, in order, ahead of any
  later frame. The last "state" message is replayed to a page that connects.
- Messages from the page (button layout, keys) land on `inbox`, which the
  engine drains every frame.

A frame is one binary message: a 4-byte big-endian header length, the JSON
header (cursor, skeleton, live set state), then the JPEG. Header and image
travel together, so a skeleton is never drawn over the wrong frame.
"""

import asyncio
import collections
import json
import queue
import struct
import threading
from pathlib import Path

from aiohttp import WSMsgType, web

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Shadow Station</title>
<body style="background:#0D1117;color:#E8EFF8;font:16px system-ui;padding:24px">
<p>The station's UI has not been built. In the repo:</p>
<pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p>then reload. (Or run <code>npm run dev</code> there and open
<a style="color:#5BA3F5" href="http://localhost:5173">localhost:5173</a>.)</p>"""


class Server:
    def __init__(self, host="127.0.0.1", port=8765, static_dir=WEB_DIST):
        self.host, self.port = host, port
        self.static_dir = Path(static_dir)
        self.inbox = queue.Queue()
        self._clients = set()
        self._state = None
        self._loop = None
        self._error = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="server",
                                        daemon=True)

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/"

    @property
    def built(self):
        return (self.static_dir / "index.html").exists()

    def start(self):
        self._thread.start()
        self._ready.wait(10)
        if self._error:
            raise SystemExit(f"could not serve on port {self.port}: "
                             f"{self._error}\nIs the station already running? "
                             "Otherwise pick another with --port.")

    def stop(self):
        """Close every page's connection and the server, then the loop."""
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(3)
        except Exception as e:
            print(f"server did not shut down cleanly: {e}")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(3)

    def publish(self, msg):
        text = json.dumps(msg, separators=(",", ":"))
        if msg.get("type") == "state":
            self._state = text
        self._call(self._push_all, text)

    def publish_frame(self, header, jpeg):
        head = json.dumps(header, separators=(",", ":")).encode()
        self._call(self._offer_all, struct.pack(">I", len(head)) + head + jpeg)

    @property
    def clients(self):
        return len(self._clients)

    # ---- the server thread ------------------------------------------------

    def _call(self, fn, arg):
        if self._loop is not None and self._clients:
            self._loop.call_soon_threadsafe(fn, arg)

    def _push_all(self, text):
        for c in self._clients:
            c.push(text)

    def _offer_all(self, frame):
        for c in self._clients:
            c.offer(frame)

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/", self._index)
        if self.built:
            app.router.add_static("/", self.static_dir)
        # Pages hold connections open between requests; at shutdown there is
        # nothing to wait for.
        self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=0.5)
        try:
            loop.run_until_complete(self._runner.setup())
            loop.run_until_complete(
                web.TCPSite(self._runner, self.host, self.port).start())
        except OSError as e:
            self._error = e
            self._ready.set()
            return
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        loop.close()

    async def _shutdown(self):
        for c in list(self._clients):
            await c.ws.close()
        await self._runner.cleanup()

    async def _index(self, request):
        if not self.built:
            return web.Response(text=NOT_BUILT, content_type="text/html")
        return web.FileResponse(self.static_dir / "index.html",
                                headers={"Cache-Control": "no-cache"})

    async def _ws(self, request):
        ws = web.WebSocketResponse(heartbeat=5)
        await ws.prepare(request)
        client = _Client(ws)
        if self._state:
            client.push(self._state)
        self._clients.add(client)
        sender = asyncio.create_task(client.run())
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        self.inbox.put(json.loads(msg.data))
                    except ValueError:
                        pass
        finally:
            self._clients.discard(client)
            sender.cancel()
        return ws


class _Client:
    def __init__(self, ws):
        self.ws = ws
        self.texts = collections.deque()
        self.frame = None
        self.wake = asyncio.Event()

    def push(self, text):
        self.texts.append(text)
        self.wake.set()

    def offer(self, frame):
        self.frame = frame  # replaces any frame not yet sent
        self.wake.set()

    async def run(self):
        try:
            while not self.ws.closed:
                await self.wake.wait()
                self.wake.clear()
                while self.texts:
                    await self.ws.send_str(self.texts.popleft())
                if self.frame is not None:
                    frame, self.frame = self.frame, None
                    await self.ws.send_bytes(frame)
        except (ConnectionError, RuntimeError):
            pass
