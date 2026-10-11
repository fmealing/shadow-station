import Feed from "../components/Feed";
import { BackIcon, Button, CurlIcon, RaiseIcon, Tile, TopBar } from "../components/ui";
import { useStation } from "../station";

const accept = (h) => h.screen === "pick";

// What the page adds to each exercise the station offers: the muscle it
// works, and a figure doing it.
const LIFTS = {
  curl: { works: "Biceps", icon: <CurlIcon className="size-[4.5rem] text-ink" /> },
  raise: { works: "Shoulders", icon: <RaiseIcon className="size-[4.5rem] text-ink" /> },
};

// Between Shadow and the set: which exercise. Laid out as home is, with the
// camera dimmed behind. The heading takes up where Shadow's row was on home,
// so the hand that pressed it comes in on words, not on an exercise.
export default function Pick() {
  const { exercises = [] } = useStation();
  return (
    <div className="absolute inset-0 animate-fade bg-bg">
      <Feed accept={accept} className="absolute inset-0 size-full" />
      <div className="absolute inset-0 bg-bg/60" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_40%,transparent_0%,rgba(13,17,23,0.92)_78%)]" />

      <TopBar
        left={
          <Button id="back" className="h-24 w-[11rem]">
            <BackIcon className="size-7" /> Back
          </Button>
        }
      />

      <main className="absolute inset-x-5 top-[15%]">
        <div className="flex h-56 animate-rise flex-col justify-end px-1 pb-3">
          <p className="eyebrow text-secondary">Shadow</p>
          <h1 className="mt-2 text-6xl font-bold tracking-tight">Pick your exercise</h1>
        </div>
        <div className="mt-5 flex flex-col gap-5">
          {exercises.map((e, i) => (
            <Tile
              key={e.id}
              id={e.id}
              title={e.name}
              subtitle={LIFTS[e.id]?.works}
              icon={LIFTS[e.id]?.icon}
              delay={(i + 1) * 70}
            />
          ))}
        </div>
      </main>
    </div>
  );
}
