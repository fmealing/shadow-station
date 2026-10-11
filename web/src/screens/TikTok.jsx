import { MusicIcon } from "../components/ui";

// On screen for a moment while the window goes over to TikTok, and until
// TikTok paints. Black, as TikTok's dark feed is, so the change is a fade and
// not a flash: the one screen that keeps the dark colours.
export default function TikTok() {
  return (
    <div className="absolute inset-0 grid animate-fade place-items-center bg-black text-[#e8eff8]">
      <div className="flex flex-col items-center gap-7">
        <div className="grid size-40 animate-pop place-items-center rounded-full border-2 border-primary bg-[#0d1117] shadow-[0_0_4rem_rgba(58,123,213,0.35)]">
          <MusicIcon className="size-20" />
        </div>
        <p className="text-5xl font-bold tracking-tight">TikTok</p>
        <div className="size-10 animate-spin rounded-full border-4 border-[#4a6080]/40 border-t-secondary" />
      </div>
    </div>
  );
}
