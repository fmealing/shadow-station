import Feed from "../components/Feed";
import { MirrorIcon, MusicIcon, PhysiqueIcon, Tile, TopBar, Wordmark } from "../components/ui";
import { useStation } from "../station";

const accept = (h) => h.screen === "home";

const APPS = {
  shadow: { title: "Shadow", subtitle: "Count your reps", icon: <img src="/ghost.svg" alt="" className="w-16" /> },
  physique: { title: "Physique", subtitle: "Your proportions, measured", icon: <PhysiqueIcon className="size-14 text-ink" /> },
  mirror: { title: "Mirror", subtitle: "Check posture and form", icon: <MirrorIcon className="size-14 text-ink" /> },
  tiktok: { title: "TikTok", subtitle: "Flick for the next video", icon: <MusicIcon className="size-14 text-ink" /> },
};

// The start screen: choose hand or pose, then an app. The camera runs behind
// it, dimmed, so you can see yourself aim.
export default function Home() {
  const { mode, apps = ["shadow"], exercise, exercises = [] } = useStation();
  // Shadow's line names the exercise, when the station counts only the one.
  const subtitle = (id) =>
    id === "shadow" && exercise && !exercises.length ? exercise.tagline : APPS[id].subtitle;
  return (
    <div className="absolute inset-0 animate-fade bg-bg">
      <Feed accept={accept} className="absolute inset-0 size-full" />
      <div className="absolute inset-0 bg-bg/60" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_40%,transparent_0%,rgba(13,17,23,0.92)_78%)]" />

      <TopBar left={<Wordmark />} />

      <main className="absolute inset-x-5 top-[15%]">
        <p className="eyebrow mb-4 px-1 text-muted">Apps</p>
        <div className="flex flex-col gap-5">
          {apps.map((id, i) => (
            <Tile key={id} id={id} {...APPS[id]} subtitle={subtitle(id)} delay={i * 70} />
          ))}
        </div>
      </main>

      <footer className="absolute inset-x-5 bottom-10 text-center">
        <p className="text-2xl font-medium text-ink">
          {mode === "pose" ? "Raise a hand to point." : "Point with your finger."}{" "}
          <span className="text-muted">Hold still to press.</span>
        </p>
      </footer>
    </div>
  );
}
