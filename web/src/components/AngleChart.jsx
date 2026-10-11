// The angle across the set, a line an arm, a tick where each rep finished,
// and a dot on each line following the replay. The app's JointAngleChart, as
// SVG. Angles run up from 0, gridded every 45° as a goniometer reads them,
// so 90° is always a line. The lines draw themselves in when the chart
// first shows.

const W = 640;
const H = 232;
const PAD = { l: 58, r: 72, t: 12, b: 30 };
const STEP = 45;
// The card the chart sits on: the ring round the replay's dots is cut in it.
const SURFACE = "#111827";

export default function AngleChart({ t, series, repEnds, duration, playhead, label }) {
  const vals = series.flatMap((s) => s.deg).filter((v) => v != null);
  if (vals.length < 2 || !duration) {
    return <p className="py-10 text-center text-xl text-muted">No movement to show</p>;
  }
  // Up to the gridline above the highest reading, and never past 180: a
  // joint has no more than that to give.
  const hi = Math.min(180, Math.max(90, Math.ceil((Math.max(...vals) + 2) / STEP) * STEP));
  const ticks = Array.from({ length: hi / STEP + 1 }, (_, i) => i * STEP);
  const x = (s) => PAD.l + (s / duration) * (W - PAD.l - PAD.r);
  const y = (d) => PAD.t + (1 - Math.min(d, hi) / hi) * (H - PAD.t - PAD.b);

  const next = playhead == null ? -1 : t.findIndex((s) => s >= playhead);
  const at = playhead == null ? null : next < 0 ? t.length - 1 : next;
  const lines = series.map((s) => ({ ...s, path: path(t, s.deg, x, y), end: lastPoint(t, s.deg, x, y) }));
  // Names at the ends of the lines, kept from overlapping.
  const ends = lines.filter((l) => l.end).sort((a, b) => a.end[1] - b.end[1]);
  for (let i = 1; i < ends.length; i++) {
    ends[i].labelY = Math.max(ends[i].end[1], (ends[i - 1].labelY ?? ends[i - 1].end[1]) + 20);
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={label}>
      {ticks.map((d) => (
        <g key={d}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(d)} y2={y(d)} className="stroke-slate" strokeOpacity={d === 90 ? 0.75 : 0.35} />
          <text x={PAD.l - 10} y={y(d) + 6} textAnchor="end" className="fill-muted" fontSize="17" fontWeight="500">
            {d}°
          </text>
        </g>
      ))}
      {repEnds.map((s) => (
        <line key={s} x1={x(s)} x2={x(s)} y1={PAD.t} y2={H - PAD.b} className="stroke-slate" strokeOpacity="0.45" />
      ))}
      {lines.map((l) => (
        <path
          key={l.name}
          d={l.path}
          pathLength="1"
          strokeDasharray="1"
          className="animate-draw"
          style={{ animationDelay: "450ms" }}
          fill="none"
          stroke={l.color}
          strokeWidth="3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
      {lines.length > 1 &&
        lines.map(
          (l) =>
            l.end && (
              <text key={l.name} x={W - PAD.r + 10} y={(l.labelY ?? l.end[1]) + 6} className="fill-ink" fontSize="17" fontWeight="600">
                {l.name}
              </text>
            ),
        )}
      {at != null && (
        <>
          <line x1={x(t[at])} x2={x(t[at])} y1={PAD.t} y2={H - PAD.b} className="stroke-ink" strokeOpacity="0.4" />
          {lines.map(
            (l) =>
              l.deg[at] != null && (
                <circle key={l.name} cx={x(t[at])} cy={y(l.deg[at])} r="8" fill={l.color} stroke={SURFACE} strokeWidth="3" />
              ),
          )}
        </>
      )}
      <text x={PAD.l} y={H - 6} className="fill-muted" fontSize="17" fontWeight="500">
        0s
      </text>
      <text x={W - PAD.r} y={H - 6} textAnchor="end" className="fill-muted" fontSize="17" fontWeight="500">
        {duration.toFixed(0)}s
      </text>
    </svg>
  );
}

// One path, broken wherever tracking was: a gap stays a gap.
function path(t, deg, x, y) {
  let d = "";
  let run = 0;
  deg.forEach((v, i) => {
    if (v == null) {
      run = 0;
      return;
    }
    d += `${run++ ? "L" : "M"}${x(t[i]).toFixed(1)},${y(v).toFixed(1)}`;
  });
  return d;
}

function lastPoint(t, deg, x, y) {
  for (let i = deg.length - 1; i >= 0; i--) {
    if (deg[i] != null) return [x(t[i]), y(deg[i])];
  }
  return null;
}
