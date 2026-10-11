"""TikTok's For You feed, in the station's own window, run by hand.

For filming, so the bar is that it looks like part of the station, not that
it's a finished feature. TikTok refuses to be embedded in another page, so
the station's window goes over to TikTok itself and comes back on Back:

- The station's cursor and a Back button in the station's style are drawn
  into TikTok's page, in the same place and size as on the station's own
  screens. Hovering still on anything else clicks it.
- Flicks become the arrow keys TikTok's feed uses for next and previous.

The For You feed rather than search, because search puts up a captcha every
time and the feed does not.
"""

import base64
import json
from pathlib import Path

import websocket

from .press import Button, Dwell, Presser
from .swipe import UP

URL = "https://www.tiktok.com/foryou"
# The Back button, in rem as the station's pages use it: 1/45 of the width
# of the 9:16 area the window can hold. x, y, w, h: the top bar's Back.
BACK_REM = (1.25, 1.25, 11, 6)
FONT = (Path(__file__).resolve().parent.parent / "web" / "public" / "fonts"
        / "SpaceGrotesk-Bold.ttf")
# What a lost Chrome looks like: its window closed, its socket gone.
GONE = (OSError, RuntimeError, websocket.WebSocketException)

# Draws the cursor, its dwell ring, Back and the swipe arrow over the page,
# and exposes window.__station to move them. Hung off <html> rather than
# <body>, which TikTok's own code re-renders. Running it again is harmless,
# so the station reruns it in case the page was replaced. The font comes
# inline: loading it from the station's server would have TikTok's page
# asking permission to reach the local network.
OVERLAY_JS = r"""(() => {
  if (document.getElementById('station-overlay') || !document.documentElement) return;
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, css, parent) => {
    const e = document.createElement(tag); e.style.cssText = css;
    if (parent) parent.appendChild(e); return e;
  };
  const svgEl = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    parent.appendChild(e); return e;
  };
  const font = FONT_URL ? `@font-face{font-family:"Station Grotesk";font-weight:700;src:url("${FONT_URL}") format("truetype")}` : '';
  el('style', '', document.documentElement).textContent = font;
  const root = el('div', 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;'
    + 'font-family:"Station Grotesk","Space Grotesk",system-ui,sans-serif');
  root.id = 'station-overlay';

  // Back, as the station's Button: an outlined pill that fills with blue.
  const back = el('div', 'position:absolute;box-sizing:border-box;overflow:hidden;border-radius:1.875em;'
    + 'border:2px solid #4A6080;background:rgba(17,24,39,.85);backdrop-filter:blur(12px);'
    + '-webkit-backdrop-filter:blur(12px);transition:border-color .15s', root);
  const fill = el('div', 'position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(58,123,213,.55)', back);
  const label = el('div', 'position:relative;height:100%;display:flex;align-items:center;justify-content:center;'
    + 'gap:.75em;color:#E8EFF8;font-weight:700;font-size:1.5em', back);
  const arrowIcon = document.createElementNS(NS, 'svg');
  arrowIcon.setAttribute('viewBox', '0 0 24 24');
  arrowIcon.style.cssText = 'width:1.15em;height:1.15em;fill:currentColor';
  svgEl('path', {d: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z'}, arrowIcon);
  label.appendChild(arrowIcon);
  label.appendChild(document.createTextNode('Back'));

  // The cursor, as the station's: a ring with the dwell filling around it.
  const cursor = document.createElementNS(NS, 'svg');
  cursor.setAttribute('viewBox', '0 0 64 64');
  cursor.style.cssText = 'position:absolute;left:0;top:0;width:4em;height:4em;overflow:visible;display:none;'
    + 'transition:transform 40ms linear';
  svgEl('circle', {cx: 32, cy: 32, r: 14, fill: 'none', stroke: '#0D1117', 'stroke-width': 7, opacity: .7}, cursor);
  svgEl('circle', {cx: 32, cy: 32, r: 14, fill: 'rgba(58,123,213,.25)', stroke: '#E8EFF8', 'stroke-width': 2.5}, cursor);
  const C = 2 * Math.PI * 26;
  const ring = svgEl('circle', {cx: 32, cy: 32, r: 26, fill: 'none', stroke: '#E8EFF8', 'stroke-width': 5,
    'stroke-linecap': 'round', 'stroke-dasharray': `0 ${C}`, transform: 'rotate(-90 32 32)'}, cursor);
  root.appendChild(cursor);

  // A chevron in the swipe's direction, which rises or falls as it fades.
  const arrow = document.createElementNS(NS, 'svg');
  arrow.setAttribute('viewBox', '0 0 24 24');
  arrow.style.cssText = 'position:absolute;left:50%;top:42%;width:9em;height:9em;opacity:0;fill:#5BA3F5;'
    + 'filter:drop-shadow(0 0 1.2em rgba(58,123,213,.9))';
  svgEl('path', {d: 'M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z'}, arrow);
  root.appendChild(arrow);
  document.documentElement.appendChild(root);

  const rem = () => Math.min(innerWidth, innerHeight * 9 / 16) / 45;
  window.__station = {
    rem,
    update(x, y, dwell, backing) {
      const r = rem();
      root.style.fontSize = `${r}px`;
      const [bx, by, bw, bh] = BACK_REM;
      Object.assign(back.style, {left: `${bx}em`, top: `${by}em`, width: `${bw}em`, height: `${bh}em`,
        borderColor: backing > 0 ? '#5BA3F5' : '#4A6080'});
      fill.style.width = `${backing * 100}%`;
      cursor.style.display = x === null ? 'none' : 'block';
      if (x !== null) cursor.style.transform = `translate(${x - 2 * r}px, ${y - 2 * r}px)`;
      ring.setAttribute('stroke-dasharray', `${Math.max(dwell, backing) * C} ${C}`);
    },
    swipe(way) {
      const flip = way === 'up' ? '' : ' rotate(180deg)';
      arrow.animate([
        {opacity: 1, transform: `translate(-50%, -50%)${flip}`},
        {opacity: 0, transform: `translate(-50%, ${way === 'up' ? '-90%' : '-10%'})${flip}`},
      ], {duration: 600, easing: 'ease-out'});
    },
  };
})()"""


def _overlay_js():
    font = ""
    if FONT.exists():
        font = "data:font/ttf;base64," + base64.b64encode(FONT.read_bytes()).decode()
    return (OVERLAY_JS.replace("FONT_URL", json.dumps(font))
            .replace("BACK_REM", json.dumps(BACK_REM)))


class TikTok:
    """Opens on creation. `update` every frame; False once Back has been
    pressed (or the window lost), by which time the station is back."""

    def __init__(self, chrome, home_url, dwell_s=0.8):
        self._chrome = chrome
        self._home = home_url
        self._overlay = _overlay_js()
        self._click = Dwell(dwell_s)
        self._back = Presser(dwell_s=dwell_s)
        self._viewport = (1, 1, 1.0)   # width, height, rem, in CSS px
        self._refreshed = -1e9
        self._last_move = None
        self.open = True
        # The page's own policy would refuse the overlay's inline font.
        chrome.send("Page.setBypassCSP", enabled=True)
        chrome.goto(URL)

    def update(self, t, cursor, quiet=False):
        """One frame. `cursor` is in screen fractions, or None. `quiet`
        holds off clicks, as after a swipe."""
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
        """Back to the station's page."""
        if not self.open:
            return
        self.open = False
        try:
            self._chrome.goto(self._home)
        except GONE:
            pass

    def _update(self, t, cursor, quiet):
        if t - self._refreshed > 1.0:
            # Once a second: the page may have been replaced, the window resized.
            self._chrome.evaluate(self._overlay)
            viewport = self._chrome.evaluate(
                "window.__station && [innerWidth, innerHeight, __station.rem()]")
            if viewport:  # nothing while a page is still loading
                self._viewport = tuple(viewport)
            self._refreshed = t
        vw, vh, rem = self._viewport
        p = None if cursor is None else (cursor[0] * vw, cursor[1] * vh)

        x, y, w, h = (v * rem for v in BACK_REM)
        if self._back.update(t, None if quiet else p,
                             [Button("back", "Back", (x, y, w, h))]):
            self.close()
            return
        if quiet or self._back.hovered is not None:
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
        px, py = ("null", "null") if p is None else (f"{p[0]:.1f}", f"{p[1]:.1f}")
        self._chrome.evaluate(
            f"window.__station && __station.update({px}, {py}, "
            f"{self._click.progress:.3f}, {self._back.progress:.3f})")
