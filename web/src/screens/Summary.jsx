import { ARM_COLORS } from "../arms";
import AngleChart from "../components/AngleChart";
import Feed from "../components/Feed";
import { Button, HomeIcon, RepeatIcon, TopBar } from "../components/ui";
import { useHeader, useStation } from "../station";

const accept = (h) => h.screen === "summary";
const CARD = "rounded-card border border-ink/10 bg-card shadow-card";

// After the set: the replay with its skeleton and goniometer, the count from
// the post-hoc analysis (which replaces the live number), each arm's best
// angle, fatigue, the angle through the set and how fast each rep was
// lifted. The app's set summary, minus what needs a phone. Each card rises
// into place in turn.
export default function Summary() {
  const { summary: s, exercise } = useStation();
  const playhead = useHeader((h) => h.replay?.t);
  if (!s) return null;
  // An arm that hung still through a one-arm set is left off the chart.
  const used = s.arms.some((arm) => arm.used) ? s.arms.map((arm) => arm.used) : s.arms.map(() => true);
  const series = s.arms
    .map((arm, i) => ({ name: arm.name, color: ARM_COLORS[i], deg: s.chart.arms[i] }))
    .filter((_, i) => used[i]);
  const note = noteFor(s);

  return (
    <div className="absolute inset-0 animate-fade bg-bg">
      <div className="absolute inset-x-0 top-0 h-[45%] bg-[radial-gradient(ellipse_at_25%_0%,rgba(58,123,213,0.28),transparent_70%)]" />
      <TopBar
        left={
          <div className="px-1">
            <p className="eyebrow text-secondary">
              Set {s.setNo} · {exercise?.name}
            </p>
            <h1 className="mt-1 text-4xl font-bold tracking-tight">Set summary</h1>
          </div>
        }
      />

      <div className="absolute inset-x-5 top-[8.25rem] flex h-[33.25rem] gap-5">
        <Rise className={`relative w-[18.7rem] shrink-0 overflow-hidden ${CARD}`}>
          <Feed accept={accept} goniometer={exercise?.joint} className="absolute inset-0 size-full" />
          <span className="eyebrow glass absolute top-3 left-3 rounded-pill px-3 py-1 text-xs text-ink">Replay</span>
        </Rise>
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <Rise delay={80} className="flex flex-1">
            <Reps s={s} />
          </Rise>
          <Rise delay={160}>
            <Peaks arms={s.arms} used={used} title={exercise?.peak ?? "Peak angle"} />
          </Rise>
          <Rise delay={240}>
            <Fatigue s={s} />
          </Rise>
        </div>
      </div>

      <div className="absolute inset-x-5 top-[42.5rem] bottom-[9.5rem] flex flex-col gap-4">
        <Rise delay={320} className={`${CARD} px-6 pt-5 pb-3`}>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-2xl font-bold">{exercise?.angle ?? "Joint angle"}</p>
            {/* One line is named by the title; two need telling apart. */}
            {series.length > 1 && (
              <div className="flex gap-5">
                {series.map((l) => (
                  <span key={l.name} className="flex items-center gap-2 text-lg font-semibold text-ink">
                    <span className="h-1 w-6 rounded-full" style={{ background: l.color }} />
                    {l.name} arm
                  </span>
                ))}
              </div>
            )}
            {series.length === 1 && <p className="text-lg font-semibold text-muted">{series[0].name} arm</p>}
          </div>
          <AngleChart
            t={s.chart.t}
            series={series}
            repEnds={s.repEnds}
            duration={s.duration}
            playhead={playhead}
            label={`${exercise?.angle ?? "Joint angle"} across the set`}
          />
        </Rise>
        <Rise delay={400} className="flex min-h-0 flex-1">
          {note ? <Note text={note} /> : <Speeds speeds={s.repSpeeds ?? []} />}
        </Rise>
      </div>

      <div className="absolute inset-x-5 bottom-5 flex gap-5">
        <Button id="done" className="h-28 flex-1">
          <HomeIcon className="size-8" /> Done
        </Button>
        <Button id="next" primary className="h-28 flex-1">
          <RepeatIcon className="size-8" /> Next set
        </Button>
      </div>
    </div>
  );
}

function Rise({ delay = 0, className = "", children }) {
  return (
    <div className={`animate-rise ${className}`} style={{ animationDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

function Reps({ s }) {
  const failed = s.trackingFailed || s.reps === 0;
  return (
    <div className={`flex flex-1 items-end justify-between border-primary/60 px-6 py-4 ${CARD}`}>
      <div>
        <p className="eyebrow text-muted">{s.reps === 1 ? "Rep" : "Reps"}</p>
        <p className={`text-[6.5rem] leading-none font-bold tabular ${failed ? "text-muted" : "lit"}`}>{s.reps}</p>
      </div>
      <div className="pb-2 text-right">
        <p className="text-3xl font-bold tabular">{formatTime(s.duration)}</p>
        <p className="text-lg text-muted">Set time</p>
      </div>
    </div>
  );
}

// Each arm's furthest angle in its best rep, its average over the reps, and
// how far apart the arms were. An arm that sat the set out is said to have.
function Peaks({ arms, used, title }) {
  const working = arms.filter((_, i) => used[i]);
  const gap =
    working.length === 2 && working[0].best != null && working[1].best != null
      ? Math.abs(working[0].best - working[1].best)
      : null;
  return (
    <div className={`px-6 py-4 ${CARD}`}>
      <div className="flex items-baseline justify-between">
        <p className="eyebrow text-muted">{title}</p>
        {gap != null && <p className="text-lg font-semibold text-muted tabular">{gap}° apart</p>}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-4">
        {arms.map((arm, i) => {
          const shown = used[i] && arm.best != null;
          return (
            <div key={arm.name}>
              <p className="flex items-center gap-2 text-lg font-semibold text-ink">
                <span className="size-3 rounded-full" style={{ background: ARM_COLORS[i] }} />
                {arm.name}
              </p>
              <p className={`text-5xl font-bold tabular ${shown ? "" : "text-muted/60"}`}>
                {shown ? arm.best : "–"}
                {shown && <span className="text-3xl">°</span>}
              </p>
              <p className="text-base text-muted tabular">
                {shown ? `Average ${arm.mean}°` : arm.best == null ? "Not in view" : "Not used"}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// How much the lift slowed from the first rep to the last.
function Fatigue({ s }) {
  const score = s.fatigue;
  return (
    <div className={`px-6 py-4 ${CARD}`}>
      <div className="flex items-baseline justify-between">
        <p className="eyebrow text-muted">Fatigue</p>
        <p className={`text-4xl font-bold tabular ${score == null ? "text-muted/60" : ""}`}>
          {score ?? "–"}
          {score != null && <span className="text-2xl">%</span>}
        </p>
      </div>
      <div className="mt-3 h-3 overflow-hidden rounded-full bg-low/45">
        {score != null && (
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-secondary"
            style={{ width: `${Math.max(3, score)}%` }}
          />
        )}
      </div>
      <p className="mt-2 text-lg font-semibold text-ink">{s.fatigueLabel}</p>
      <p className="text-base text-muted">Drop in lifting speed, first rep to last</p>
    </div>
  );
}

// How fast each rep was lifted, a bar a rep: the slowing that the fatigue
// score puts a number on, where you can see it.
function Speeds({ speeds }) {
  const top = Math.max(0, ...speeds.filter((v) => v != null));
  if (!top) return null;
  // Numbered at the ends, and all the way along when there is room.
  const numbered = (i) => speeds.length <= 12 || i === 0 || i === speeds.length - 1;
  return (
    <div className={`flex min-h-0 flex-1 items-stretch gap-6 px-6 py-4 ${CARD}`}>
      <div className="flex w-[10rem] shrink-0 flex-col justify-center">
        <p className="text-2xl font-bold">Lift speed</p>
        <p className="mt-1 text-base text-muted">Each rep, fastest at {top}°/s</p>
      </div>
      <div className="flex min-w-0 flex-1 items-stretch gap-[0.3rem]" role="img" aria-label="Lifting speed of each rep">
        {speeds.map((v, i) => (
          <div key={i} className="flex min-w-0 flex-1 flex-col items-center">
            <div className="flex min-h-0 w-full flex-1 items-end justify-center">
              <div
                className="w-full max-w-[1.5rem] origin-bottom animate-grow rounded-t-[0.25rem] bg-secondary"
                style={{
                  height: v == null ? "3%" : `${Math.max(6, (v / top) * 100)}%`,
                  opacity: v == null ? 0.25 : 1,
                  animationDelay: `${500 + i * 45}ms`,
                }}
              />
            </div>
            <p className="mt-1 h-5 text-sm font-medium text-muted tabular">{numbered(i) ? i + 1 : ""}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Why there is no count, when there is none. How sure the analysis is of a
// count it did make is for whoever runs the station (the terminal and the
// HUD), not for the screen.
function noteFor(s) {
  if (s.trackingFailed) return "Tracking failed. Check you're in view of the camera.";
  if (s.reps === 0) return "No reps detected.";
  return null;
}

function Note({ text }) {
  return (
    <div className="flex flex-1 items-center gap-4 rounded-card border border-warning/60 bg-warning/15 px-6 py-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-full border-2 border-warning text-xl font-bold text-warning-ink">
        ?
      </span>
      <p className="text-xl font-semibold text-warning-ink">{text}</p>
    </div>
  );
}

function formatTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
