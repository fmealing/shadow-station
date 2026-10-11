import Feed from "../components/Feed";
import { BackIcon, Button, Cue, PlayIcon, StopIcon, Tag, TopBar } from "../components/ui";
import { useHeader, useStation } from "../station";

const accept = (h) => h.screen === "workout";

// One set. Before it starts, the station checks the position and counts
// down; during it, the live rep count is the whole screen's point, with each
// arm's angle drawn on the body. Reps that keep stopping short turn the count
// and the arms amber, and the camera shows where the arms should get to.
export default function Workout() {
  const { setNo, exercise } = useStation();
  const live = useHeader((h) => h.live) ?? { phase: "preroll", headline: "STEP IN", cue: "", reps: 0 };
  const recording = live.phase === "recording";
  const short = recording && !live.warning ? live.short : null;

  return (
    <div className="absolute inset-0 animate-fade bg-black">
      <Feed accept={accept} goniometer={exercise?.joint} className="absolute inset-0 size-full" />
      <div className="absolute inset-x-0 top-0 h-[24%] bg-gradient-to-b from-bg/90 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-[40%] bg-gradient-to-t from-bg via-bg/60 to-transparent" />

      <TopBar
        left={
          recording ? (
            <Button id="finish" primary className="h-24 w-[15rem]">
              <StopIcon className="size-7" /> Finish set
            </Button>
          ) : (
            <Button id="back" className="h-24 w-[11rem]">
              <BackIcon className="size-7" /> Back
            </Button>
          )
        }
      />
      <Tag>
        Set {(setNo ?? 0) + 1} · {exercise?.name}
      </Tag>

      {live.phase === "countdown" && <Countdown n={live.countdown} />}
      {!recording && (
        <Cue
          headline={live.headline}
          cue={live.cue}
          good={live.headline === "HOLD IT" || live.headline === "GET SET"}
        />
      )}
      {short && <Cue headline={short.headline} cue={short.cue} good={false} />}
      {recording && <Counter live={live} short={Boolean(short)} />}

      {live.phase === "preroll" && (
        <div className="absolute inset-x-5 bottom-10 flex flex-col items-center gap-5">
          <Button id="start" primary className="h-28 w-[22rem]">
            <PlayIcon className="size-8" /> Start
          </Button>
          <p className="text-xl text-muted">Or get in position and it starts by itself</p>
        </div>
      )}
      {live.phase === "countdown" && (
        <div className="absolute inset-x-5 bottom-10 flex justify-center">
          <Button id="cancel" className="h-28 w-[22rem]">
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}

function Countdown({ n }) {
  return (
    <div className="absolute inset-0 grid place-items-center bg-bg/55">
      <span key={n} className="lit animate-pop text-[20rem] leading-none font-bold text-secondary tabular">
        {n}
      </span>
    </div>
  );
}

function Counter({ live, short }) {
  const mins = Math.floor(live.elapsed / 60);
  const secs = String(Math.floor(live.elapsed % 60)).padStart(2, "0");
  return (
    <>
      {live.warning && (
        <div className="absolute inset-x-5 top-[13rem] flex justify-center">
          <div className="glass flex items-center gap-4 rounded-card border-2 border-warning/80 px-8 py-5 shadow-float">
            <span className="size-4 animate-pulse-dot rounded-full bg-warning" />
            <span className="text-2xl font-semibold">{live.warning}</span>
          </div>
        </div>
      )}
      <div className="absolute inset-x-5 bottom-10 flex flex-col items-center">
        <div className="glass flex items-center gap-3 rounded-pill px-5 py-2">
          <span className="size-3 animate-pulse-dot rounded-full bg-secondary" />
          <span className="eyebrow text-ink">Counting</span>
          <span className="eyebrow text-muted tabular">
            {mins}:{secs}
          </span>
        </div>
        <div className="relative mt-2 grid place-items-center">
          {/* A ring thrown out as each rep lands. */}
          {live.reps > 0 && (
            <span
              key={live.reps}
              className={`absolute size-[13rem] animate-ring rounded-full border-[0.35rem] ${
                short ? "border-warning" : "border-secondary"
              }`}
            />
          )}
          <span
            key={live.reps}
            className={`relative animate-pop text-[14rem] leading-none font-bold tabular ${
              short ? "lit-warn text-warning-ink" : "lit text-ink"
            }`}
          >
            {live.reps}
          </span>
        </div>
        <span className="eyebrow -mt-2 text-xl text-ink/80">{live.reps === 1 ? "Rep" : "Reps"}</span>
      </div>
    </>
  );
}
