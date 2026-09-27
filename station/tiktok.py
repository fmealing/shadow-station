"""TikTok mode: TikTok's For You feed in the station's Chrome, run by hand.

- The hand cursor is drawn into the page, since DevTools mouse events do not
  move the real pointer, and hovering still on anything clicks it: the same
  dwell as the station's own buttons.
- Swipes become the arrow keys TikTok's feed uses for next and previous.
- A Close zone in the page's top-right corner, like the station's hand/pose
  toggle, shuts TikTok and hands back to the station.

The For You feed rather than search, because search puts up a captcha every
time and the feed does not. The station's account gets trained on brainrot
instead.
"""

import websocket

from .browser import Chrome
from .press import Button, Dwell, Presser
from .swipe import UP

URL = "https://www.tiktok.com/foryou"
# Close zone, CSS px: its right edge's inset from the page's, then top, w, h.
CLOSE_RIGHT, CLOSE_TOP, CLOSE_W, CLOSE_H = 12, 12, 120, 56
# What a lost Chrome looks like: its window closed, its socket gone.
GONE = (OSError, RuntimeError, websocket.WebSocketException)

# Draws the cursor, its dwell ring, the Close zone and swipe arrows over the
# page, and exposes window.__station to move them. Built with DOM calls rather
# than innerHTML, which TikTok's security policy may refuse, and hung off
# <html> rather than <body>, which TikTok's own code re-renders. Running it
# again is harmless, so the station reruns it in case the page was replaced.
OVERLAY_JS = r"""(() => {
  if (document.getElementById('station-overlay') || !document.documentElement) return;
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, css, parent) => {
    const e = document.createElement(tag); e.style.cssText = css;
    if (parent) parent.appendChild(e); return e;
  };
  const root = el('div', 'position:fixed;inset:0;pointer-events:none;z-index:2147483647');
  root.id = 'station-overlay';
  const close = el('div', 'position:absolute;top:CLOSE_TOPpx;right:CLOSE_RIGHTpx;width:CLOSE_Wpx;height:CLOSE_Hpx;'
    + 'box-sizing:border-box;border-radius:14px;background:rgba(17,24,39,.8);border:1px solid #4A6080;'
    + 'overflow:hidden;display:flex;align-items:center;justify-content:center', root);
  const fill = el('div', 'position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(58,123,213,.65)', close);
  el('span', 'position:relative;color:#E8EFF8;font:600 16px system-ui,sans-serif', close)
    .textContent = '✕  Close';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', '64'); svg.setAttribute('height', '64');
  svg.style.cssText = 'position:absolute;left:0;top:0;overflow:visible;display:none';
  const circle = (r, stroke, width) => {
    const c = document.createElementNS(NS, 'circle');
    for (const [k, v] of Object.entries({cx: 32, cy: 32, r, fill: 'none', stroke, 'stroke-width': width}))
      c.setAttribute(k, v);
    svg.appendChild(c); return c;
  };
  circle(14, '#111827', 6); circle(14, '#E8EFF8', 2);
  const ring = circle(24, '#E8EFF8', 5);
  ring.setAttribute('transform', 'rotate(-90 32 32)');
  root.appendChild(svg);
  const arrow = el('div', 'position:absolute;left:50%;top:42%;transform:translate(-50%,-50%);opacity:0;'
    + 'font:700 140px system-ui,sans-serif;color:#5BA3F5;text-shadow:0 0 14px #111827', root);
  document.documentElement.appendChild(root);
  const C = 2 * Math.PI * 24;
  window.__station = {
    update(x, y, dwell, closing) {
      svg.style.display = x === null ? 'none' : 'block';
      if (x !== null) svg.style.transform = `translate(${x - 32}px, ${y - 32}px)`;
      ring.setAttribute('stroke-dasharray', `${dwell * C} ${C}`);
      fill.style.width = `${closing * 100}%`;
      close.style.borderColor = closing > 0 ? '#5BA3F5' : '#4A6080';
    },
    swipe(way) {
      arrow.textContent = way === 'up' ? '↑' : '↓';
      arrow.animate([
        {opacity: 1, transform: 'translate(-50%,-50%)'},
        {opacity: 0, transform: `translate(-50%, ${way === 'up' ? '-90%' : '-10%'})`},
      ], {duration: 600, easing: 'ease-out'});
    },
  };
})()"""
for _name in ("CLOSE_TOP", "CLOSE_RIGHT", "CLOSE_W", "CLOSE_H"):
    OVERLAY_JS = OVERLAY_JS.replace(_name, str(globals()[_name]))


class TikTok:
    def __init__(self, position, size, dwell_s=0.8, close_hold_s=0.5,
                 extra_args=()):
        self._chrome = Chrome(URL, position, size, extra_args)
        self._click = Dwell(dwell_s)
        self._close = Presser()
        self.close_hold_s = close_hold_s
        self._viewport = (size[0], size[1])
        self._refreshed = -1e9
        self._last_move = None
        self.open = True

    def update(self, t, cursor, quiet=False):
        """One frame. `cursor` is in screen fractions, or None. `quiet`
        holds off clicks, as after a swipe. Returns whether TikTok is still
        open: False once the Close zone fires or its window is shut."""
        if not self.open:
            return False
        try:
            self._update(t, cursor, quiet)
        except GONE:
            self.close()
        return self.open

    def swipe(self, way):
        if not self.open:
            return
        try:
            self._chrome.key("ArrowDown" if way == UP else "ArrowUp")
            self._chrome.evaluate(f"window.__station && __station.swipe('{way}')")
        except GONE:
            self.close()

    def close(self):
        if not self.open:
            return
        self.open = False
        try:
            self._chrome.close()
        except GONE:
            pass

    def _update(self, t, cursor, quiet):
        if t - self._refreshed > 1.0:
            # Once a second: the page may have been replaced, the window resized.
            self._chrome.evaluate(OVERLAY_JS)
            viewport = self._chrome.evaluate("[innerWidth, innerHeight]")
            if viewport:  # nothing while a page is still loading
                self._viewport = tuple(viewport)
            self._refreshed = t
        vw, vh = self._viewport
        p = None if cursor is None else (cursor[0] * vw, cursor[1] * vh)

        zone = Button("close", "Close",
                      (vw - CLOSE_RIGHT - CLOSE_W, CLOSE_TOP, CLOSE_W, CLOSE_H),
                      hold_s=self.close_hold_s)
        if self._close.update(t, None if quiet else p, [zone]):
            self.close()
            return
        if quiet or self._close.hovered is not None:
            self._click.reset()
            click = None
        else:
            click = self._click.update(t, p)

        if p is not None and p != self._last_move:
            # Real mouse moves, so TikTok shows its hover states as well.
            self._chrome.move(*p)
            self._last_move = p
        if click is not None:
            self._chrome.click(*click)
        x, y = ("null", "null") if p is None else (f"{p[0]:.0f}", f"{p[1]:.0f}")
        self._chrome.evaluate(
            f"window.__station && __station.update({x}, {y}, "
            f"{self._click.progress:.3f}, {self._close.progress:.3f})")
