// The page's one connection to the station (station/server.py).
//
// The station owns all the state; the page draws it. Three things come in:
//   - "state" messages: the screen, the mode, the set summary. Rare.
//   - "pressed" events: a button was pressed, so it can flash.
//   - frames: a JSON header (cursor, hover, skeletons, the live set) and a
//     JPEG, ~30 a second.
// and two go out: where the buttons are ("layout"), and key presses.

import { useCallback, useRef, useSyncExternalStore } from "react";

const listeners = { state: new Set(), header: new Set(), frame: new Set(), pressed: new Set() };
let socket = null;
let header = null;
// What useStation() returns: the last "state" message plus `connected`.
// Replaced, never mutated, so React can tell when it changed.
let snapshot = { connected: false };

function setStation(state, connected) {
  snapshot = { ...state, connected };
  emit("state", snapshot);
}

function emit(kind, value) {
  for (const fn of listeners[kind]) fn(value);
}

function subscribe(kind, fn) {
  listeners[kind].add(fn);
  return () => listeners[kind].delete(fn);
}

export function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  socket = new WebSocket(url);
  socket.binaryType = "arraybuffer";
  socket.onopen = () => {
    lastLayout = "";
    setStation(snapshot, true);
  };
  socket.onclose = () => {
    setStation(snapshot, false);
    setTimeout(connect, 1000);
  };
  socket.onmessage = (e) => {
    if (typeof e.data === "string") {
      const msg = JSON.parse(e.data);
      if (msg.type === "state") {
        setStation(msg, true);
      } else if (msg.type === "pressed") {
        emit("pressed", msg.id);
      }
      return;
    }
    const view = new DataView(e.data);
    const len = view.getUint32(0);
    header = JSON.parse(new TextDecoder().decode(new Uint8Array(e.data, 4, len)));
    emit("header", header);
    decode(header, new Blob([new Uint8Array(e.data, 4 + len)], { type: "image/jpeg" }));
  };
}

export function send(msg) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg));
}

// ---- frames ------------------------------------------------------------------

// One JPEG decodes at a time. A frame that arrives meanwhile waits, and a newer
// one replaces it, so a slow decode drops frames rather than queueing them.
let decoding = false;
let waiting = null;

async function decode(h, blob) {
  if (decoding) {
    waiting = [h, blob];
    return;
  }
  decoding = true;
  try {
    const bitmap = await createImageBitmap(blob);
    emit("frame", { header: h, bitmap });
    bitmap.close();
  } catch {
    // A truncated frame: skip it.
  }
  decoding = false;
  if (waiting) {
    const next = waiting;
    waiting = null;
    decode(...next);
  }
}

export const onFrame = (fn) => subscribe("frame", fn);
export const onPressed = (fn) => subscribe("pressed", fn);

// ---- hooks -------------------------------------------------------------------

export function useStation() {
  return useSyncExternalStore(
    useCallback((fn) => subscribe("state", fn), []),
    () => snapshot,
  );
}

// Something from the latest frame header. `select` picks it out, and the
// component re-renders only when that changes (compared as JSON, so objects
// work too), not on every frame.
export function useHeader(select) {
  const cache = useRef({ key: undefined, value: undefined });
  const get = () => {
    const value = header ? select(header) : undefined;
    const key = JSON.stringify(value);
    if (key !== cache.current.key) cache.current = { key, value };
    return cache.current.value;
  };
  return useSyncExternalStore(useCallback((fn) => subscribe("header", fn), []), get);
}

// ---- where the buttons are ------------------------------------------------------

// Every pressable element registers here. Their rects, as fractions of the
// stage, go to the station whenever they change; the station hit-tests the
// cursor against them.
const targets = new Map();
let lastLayout = "";
let screen = null;

export function register(id, el, hold) {
  targets.set(id, { el, hold });
  queueMicrotask(reportLayout);
  return () => {
    if (targets.get(id)?.el === el) targets.delete(id);
    queueMicrotask(reportLayout);
  };
}

export function setLayoutScreen(s) {
  screen = s;
  queueMicrotask(reportLayout);
}

export function reportLayout() {
  const stage = document.getElementById("stage");
  if (!stage || !screen) return;
  const s = stage.getBoundingClientRect();
  if (!s.width) return;
  const buttons = [...targets].map(([id, { el, hold }]) => {
    const r = el.getBoundingClientRect();
    const f = (v) => Math.round(v * 10000) / 10000;
    return {
      id,
      hold: Boolean(hold),
      rect: [f((r.left - s.left) / s.width), f((r.top - s.top) / s.height), f(r.width / s.width), f(r.height / s.height)],
    };
  });
  const msg = { type: "layout", screen, buttons };
  const text = JSON.stringify(msg);
  if (text !== lastLayout && socket?.readyState === WebSocket.OPEN) {
    lastLayout = text;
    socket.send(text);
  }
}

// Layout can also move without anything registering: a font loading, the
// window resizing. Checking a few times a second catches all of it.
setInterval(reportLayout, 300);
window.addEventListener("resize", reportLayout);
