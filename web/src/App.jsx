import { useEffect, useState } from "react";
import Cursor from "./components/Cursor";
import Home from "./screens/Home";
import Mirror from "./screens/Mirror";
import Physique from "./screens/Physique";
import Pick from "./screens/Pick";
import Summary from "./screens/Summary";
import TikTok from "./screens/TikTok";
import Workout from "./screens/Workout";
import { send, setLayoutScreen, useHeader, useStation } from "./station";

const SCREENS = {
  home: Home,
  pick: Pick,
  workout: Workout,
  summary: Summary,
  physique: Physique,
  mirror: Mirror,
  tiktok: TikTok,
};
// Keys the station handles; the rest are the page's own.
const STATION_KEYS = new Set(["t", "Enter", "Escape", "1", "2", "m", "p", "q"]);

export default function App() {
  const station = useStation();
  const [hud, setHud] = useState(false);

  useEffect(() => setLayoutScreen(station.screen ?? null), [station.screen]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.repeat) return;
      if (STATION_KEYS.has(e.key)) send({ type: "key", key: e.key });
      else if (e.key === "d") setHud((v) => !v);
      else if (e.key === "f") {
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const Screen = SCREENS[station.screen];
  return (
    <div
      id="stage"
      className="relative overflow-hidden bg-bg"
      style={{ width: "min(100vw, calc(100vh * 9 / 16))", aspectRatio: "9 / 16" }}
    >
      {Screen && <Screen key={station.screen} />}
      {station.screen !== "tiktok" && <Cursor />}
      {hud && <Hud mode={station.mode} screen={station.screen} summary={station.summary} />}
      {!station.connected && <Connecting />}
    </div>
  );
}

// For whoever is running the station, not for whoever is using it: what the
// screens leave out goes here.
function Hud({ mode, screen, summary }) {
  const fps = useHeader((h) => h.fps);
  return (
    <div className="absolute bottom-3 left-3 z-40 rounded-button border border-white/15 bg-black/85 px-3 py-2 font-mono text-sm leading-relaxed text-white/90">
      <div>
        {screen} · {mode} · {fps ?? "–"} fps
      </div>
      {summary && (
        <div>
          {summary.reps} reps · {summary.liveReps} counted live · {summary.confident ? "confident" : "hard to read"}
        </div>
      )}
      <div className="text-white/60">
        [t] hand/pose [Enter] main [1/2] exercise [Esc] back [p] physique [m] mirror [d] HUD [f] fullscreen [q] quit
      </div>
    </div>
  );
}

// Only once the wait is noticeable: a reload reconnects in a blink, and a
// flash of this would be worse than a moment of nothing.
function Connecting() {
  const [late, setLate] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setLate(true), 800);
    return () => clearTimeout(id);
  }, []);
  if (!late) return <div className="absolute inset-0 z-50 bg-bg" />;
  return (
    <div className="absolute inset-0 z-50 grid animate-fade place-items-center bg-bg">
      <div className="flex flex-col items-center gap-6">
        <img src="/ghost.svg" alt="" className="w-28 animate-pulse-dot" />
        <p className="text-2xl text-muted">Connecting to the station…</p>
      </div>
    </div>
  );
}
