import { useEffect, useRef } from "react";
import { ARM_COLORS, SHORT_COLOR, armsOnScreen, limbsOnScreen } from "../arms";
import { onFrame, useStation } from "../station";

// A canvas the station's frames are drawn into, with the tracked skeleton on
// top. `accept` picks the frames meant for it (by the header), so a frame
// still in flight from the last screen is not drawn on this one. With
// `goniometer` (a joint's name), each arm's angle at that joint is drawn on
// the body too, and while its reps are stopping short, where it should get
// to. With `lines`, the frame's measuring lines are drawn in place of the
// skeleton.
export default function Feed({ accept, goniometer = null, lines = false, className = "" }) {
  const canvas = useRef(null);
  const { edges } = useStation();
  const edgesRef = useRef(edges);
  edgesRef.current = edges;
  // When each measuring line came on, so it can be drawn opening out.
  const opened = useRef(new Map());

  useEffect(
    () =>
      onFrame(({ header, bitmap }) => {
        const c = canvas.current;
        if (!c || !accept(header)) return;
        const dpr = window.devicePixelRatio || 1;
        const w = Math.round(c.clientWidth * dpr);
        const h = Math.round(c.clientHeight * dpr);
        if (!w || !h) return;
        if (c.width !== w || c.height !== h) {
          c.width = w;
          c.height = h;
        }
        const ctx = c.getContext("2d");
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(bitmap, 0, 0, w, h);
        if (lines) {
          drawLines(ctx, header.physique?.lines ?? [], w, h, opened.current, performance.now());
          return;
        }
        for (const s of header.skeletons ?? []) {
          drawSkeleton(ctx, s.points, edgesRef.current?.[s.edges] ?? [], w, h);
          if (goniometer && s.edges === "pose" && header.arms) {
            const short = header.live?.short;
            if (short) drawTargets(ctx, s.points, goniometer, short, w, h, performance.now());
            drawGoniometer(ctx, s.points, header.arms, goniometer, short?.arms, w, h);
          }
        }
      }),
    [accept, goniometer, lines],
  );

  return <canvas ref={canvas} className={className} />;
}

// Each arm's angle as a goniometer reads it: the wedge it has opened at the
// joint, and the station's measure of it. The number is the station's, which
// only measures an arm it can see well. An arm in `short` is one whose reps
// are stopping short.
function drawGoniometer(ctx, points, degrees, joint, short, w, h) {
  const found = armsOnScreen(points, joint);
  if (!found) return;
  const at = (i) => [points[i][0] * w, points[i][1] * h];
  const r = w * 0.075;
  ctx.save();
  found.arms.forEach(([vertex, a, b], side) => {
    const deg = degrees[side];
    // A straight elbow has opened no wedge to draw: the arm that is not
    // curling stays clean.
    if (deg == null || (joint === "elbow" && deg < 12)) return;
    const v = at(vertex);
    const p = at(a);
    const q = at(b);
    const from = found.through ? Math.atan2(v[1] - p[1], v[0] - p[0]) : Math.atan2(p[1] - v[1], p[0] - v[0]);
    const to = Math.atan2(q[1] - v[1], q[0] - v[0]);
    const sweep = Math.atan2(Math.sin(to - from), Math.cos(to - from));
    const color = short?.[side] ? SHORT_COLOR : ARM_COLORS[side];

    ctx.beginPath();
    ctx.moveTo(...v);
    ctx.arc(v[0], v[1], r, from, from + sweep, sweep < 0);
    ctx.closePath();
    ctx.globalAlpha = 0.34;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(v[0], v[1], r, from, from + sweep, sweep < 0);
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(4, w * 0.011);
    ctx.strokeStyle = "#E8EFF8";
    ctx.stroke();
    ctx.lineWidth = Math.max(2, w * 0.006);
    ctx.strokeStyle = color;
    ctx.stroke();

    // The reading, out along the middle of the wedge, on a dark tag edged in
    // the arm's colour.
    const mid = from + sweep / 2;
    tag(ctx, `${deg}°`, v[0] + Math.cos(mid) * r * 1.95, v[1] + Math.sin(mid) * r * 1.95, w * 0.044, color, w);
  });
  ctx.restore();
}

// How far out from hanging straight down a resting hand sits, and how far
// out from the upper arm a hand curled all the way up does, in radians.
const HANG = 0.21;
const FOLD = 0.38;

// Where an arm whose reps are stopping short should get to, drawn on the
// lifter, who is too far back to read: the arm in the warning's colour, a
// ring where its hand belongs at that end of the rep, and the way there from
// where the hand is now. At the shoulder the hand goes out level with it, or
// back down by the hip. At the elbow it comes up by the shoulder, or back to
// where a straight arm puts it.
function drawTargets(ctx, points, joint, short, w, h, now) {
  const limbs = limbsOnScreen(points);
  if (!limbs) return;
  const at = (i) => [points[i][0] * w, points[i][1] * h];
  const len = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  const dir = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
  const top = short.end === "top";
  const line = Math.max(3, w * 0.009);
  ctx.save();
  ctx.lineCap = "round";
  limbs.forEach(([si, ei, wi, oi], side) => {
    if (!short.arms?.[side] || !points[ei] || !points[wi]) return;
    const [s, e, hand, o] = [si, ei, wi, oi].map(at);
    const out = s[0] < o[0] ? -1 : 1;
    let pivot, reach, goal, bones;
    if (joint === "shoulder") {
      pivot = s;
      reach = len(s, e) + len(e, hand);
      goal = top ? (out > 0 ? 0 : Math.PI) : Math.PI / 2 - out * HANG;
      bones = [s, e, hand];
    } else {
      pivot = e;
      reach = len(s, e) * 0.95;
      goal = top ? dir(e, s) + out * FOLD : dir(s, e);
      bones = [e, hand];
    }
    const from = dir(pivot, hand);
    const sweep = Math.atan2(Math.sin(goal - from), Math.cos(goal - from));
    const end = [pivot[0] + Math.cos(goal) * reach, pivot[1] + Math.sin(goal) * reach];

    // The arm, over the skeleton's blue.
    ctx.shadowColor = "rgba(224, 160, 48, 0.9)";
    ctx.shadowBlur = w * 0.02;
    ctx.strokeStyle = SHORT_COLOR;
    ctx.lineWidth = line;
    ctx.beginPath();
    ctx.moveTo(...bones[0]);
    for (const p of bones.slice(1)) ctx.lineTo(...p);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#E8EFF8";
    for (const p of bones) {
      ctx.beginPath();
      ctx.arc(p[0], p[1], Math.max(2, w * 0.0065), 0, Math.PI * 2);
      ctx.fill();
    }

    // The way there: where the arm will lie, and the hand's path to it.
    ctx.setLineDash([w * 0.006, w * 0.022]);
    ctx.lineWidth = line * 0.8;
    ctx.globalAlpha = 0.75;
    ctx.beginPath();
    ctx.moveTo(...pivot);
    ctx.lineTo(...end);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(pivot[0], pivot[1], reach, from, from + sweep, sweep < 0);
    ctx.stroke();
    ctx.setLineDash([]);

    // The ring the hand belongs in, breathing so it catches the eye.
    const r = w * 0.034 * (1 + 0.1 * Math.sin(now / 240));
    ctx.beginPath();
    ctx.arc(end[0], end[1], r, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(13, 17, 23, 0.55)";
    ctx.fill();
    ctx.lineWidth = line * 1.3;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(end[0], end[1], w * 0.009, 0, Math.PI * 2);
    ctx.fillStyle = "#E8EFF8";
    ctx.fill();
  });
  ctx.restore();
}

// A reading on a dark pill, centred on (cx, cy).
function tag(ctx, text, cx, cy, size, edge, w, spaced = false) {
  ctx.save();
  ctx.font = `700 ${Math.round(size)}px "Space Grotesk", sans-serif`;
  if (spaced) ctx.letterSpacing = `${size * 0.12}px`;
  const tw = ctx.measureText(text).width;
  const pw = tw + size * 1.0;
  const ph = size * 1.5;
  ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
  ctx.shadowBlur = size * 0.5;
  ctx.beginPath();
  ctx.roundRect(cx - pw / 2, cy - ph / 2, pw, ph, ph / 2);
  ctx.fillStyle = "rgba(13, 17, 23, 0.9)";
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.lineWidth = Math.max(2, w * 0.0045);
  ctx.strokeStyle = edge;
  ctx.stroke();
  ctx.fillStyle = "#E8EFF8";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, cx + (spaced ? size * 0.06 : 0), cy + size * 0.05);
  ctx.restore();
  return pw;
}

const OPEN_MS = 420;
// A line not sent for this long has gone; when it comes back, it opens again.
const GONE_MS = 500;

// The measuring lines, one across the shoulders and one across the waist,
// drawn the way the skeleton is: a blue line with a white dot at each end.
// Each opens out from its middle when it first comes on.
function drawLines(ctx, list, w, h, seen, now) {
  for (const [id, s] of seen) if (now - s.last > GONE_MS) seen.delete(id);
  ctx.save();
  ctx.lineCap = "round";
  for (const l of list) {
    const s = seen.get(l.id) ?? { since: now };
    s.last = now;
    seen.set(l.id, s);
    const k = 1 - (1 - Math.min(1, (now - s.since) / OPEN_MS)) ** 3;
    const a = [l.a[0] * w, l.a[1] * h];
    const b = [l.b[0] * w, l.b[1] * h];
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const ends = [a, b].map((e) => [mid[0] + (e[0] - mid[0]) * k, mid[1] + (e[1] - mid[1]) * k]);

    ctx.shadowColor = "rgba(58, 123, 213, 0.9)";
    ctx.shadowBlur = w * 0.02;
    ctx.strokeStyle = "#5BA3F5";
    ctx.lineWidth = Math.max(3, w * 0.009);
    ctx.beginPath();
    ctx.moveTo(...ends[0]);
    ctx.lineTo(...ends[1]);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#E8EFF8";
    for (const e of ends) {
      ctx.beginPath();
      ctx.arc(e[0], e[1], Math.max(3, w * 0.011), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

function drawSkeleton(ctx, points, edges, w, h) {
  if (!points.length) return;
  const at = (i) => [points[i][0] * w, points[i][1] * h];
  const used = new Set(edges.flat());
  ctx.save();
  ctx.lineCap = "round";
  ctx.shadowColor = "rgba(58, 123, 213, 0.9)";
  ctx.shadowBlur = w * 0.02;
  ctx.strokeStyle = "#5BA3F5";
  ctx.lineWidth = Math.max(2, w * 0.007);
  ctx.beginPath();
  for (const [a, b] of edges) {
    if (!points[a] || !points[b]) continue;
    ctx.moveTo(...at(a));
    ctx.lineTo(...at(b));
  }
  ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#E8EFF8";
  const r = Math.max(2, w * 0.0065);
  for (const i of used) {
    if (!points[i]) continue;
    ctx.beginPath();
    ctx.arc(...at(i), r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}
