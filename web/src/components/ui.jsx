import { useStation } from "../station";
import Pressable from "./Pressable";

// Shared pieces of every screen: the top bar and its hand/pose toggle, the
// wordmark, buttons, the menus' rows, icons.

export function TopBar({ left }) {
  return (
    <header className="absolute inset-x-5 top-5 z-20 flex h-24 items-center justify-between gap-5">
      <div className="flex h-full min-w-0 items-center">{left}</div>
      <ModeToggle />
    </header>
  );
}

// Hand or pose. A zone rather than a button: it switches after the toggle's
// own hold time, and works the same way in both modes, since pose mode needs a
// way back.
export function ModeToggle() {
  const { mode } = useStation();
  return (
    <Pressable
      id="toggle"
      hold
      className="glass h-24 w-[15.625rem] shrink-0 rounded-card data-[hovered]:border-primary data-[hovered]:shadow-glow"
    >
      <div className="flex h-full gap-2 p-2">
        {["hand", "pose"].map((m) => (
          <div
            key={m}
            className={`flex flex-1 items-center justify-center gap-2 rounded-button text-lg font-bold tracking-wider transition-colors duration-200 ${
              m === mode ? "bg-primary text-black" : "text-muted"
            }`}
          >
            {m === "hand" ? <HandIcon /> : <PoseIcon />}
            {m.toUpperCase()}
          </div>
        ))}
      </div>
    </Pressable>
  );
}

export function Wordmark({ className = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <img src="/ghost.svg" alt="" className="size-12" />
      <span className="text-4xl font-bold tracking-tight text-ink">Shadow</span>
    </div>
  );
}

// A button in one of the app's two styles: filled blue (the next step) or
// outlined (everything else).
export function Button({ id, primary = false, className = "", children }) {
  return (
    <Pressable
      id={id}
      fill={primary ? "bg-white/35" : "bg-primary/40"}
      className={`rounded-pill ${
        primary
          ? "bg-primary text-black shadow-[0_0_2.5rem_rgba(58,123,213,0.45)] data-[hovered]:shadow-glow"
          : "glass text-ink data-[hovered]:border-primary data-[hovered]:shadow-glow"
      } ${className}`}
    >
      <div className="flex h-full items-center justify-center gap-3 px-8 text-2xl font-bold">{children}</div>
    </Pressable>
  );
}

// A row of a menu: an icon in a ring, a name and a line about it. `delay`
// staggers the rows as they rise into place.
export function Tile({ id, title, subtitle, icon, delay = 0 }) {
  return (
    <div className="animate-rise" style={{ animationDelay: `${delay}ms` }}>
      <Pressable
        id={id}
        className="glass h-44 rounded-[1.5rem] shadow-float data-[hovered]:border-primary data-[hovered]:shadow-glow"
      >
        <div className="flex h-full items-center gap-7 px-7">
          <div className="grid size-28 shrink-0 place-items-center rounded-full border-2 border-primary bg-bg shadow-[0_0_2rem_rgba(58,123,213,0.35)]">
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-5xl font-bold tracking-tight">{title}</h2>
            <p className="mt-2 text-2xl text-muted">{subtitle}</p>
          </div>
          <ChevronIcon className="size-14 shrink-0 text-secondary" />
        </div>
      </Pressable>
    </div>
  );
}

// The label under the top bar that says what this screen is.
export function Tag({ children }) {
  return (
    <p className="eyebrow glass absolute top-[8.25rem] left-5 z-10 rounded-pill px-4 py-1.5 text-ink">{children}</p>
  );
}

// What the station wants from you, or that it is about to start: a headline
// and a line under it. Blue when things are going well, amber when there is
// something to fix. `className` says how far down the screen it sits.
export function Cue({ headline, cue, good, className = "top-[13rem]" }) {
  return (
    <div className={`absolute inset-x-5 z-10 flex justify-center ${className}`}>
      <div
        key={headline}
        className={`glass flex animate-pop flex-col items-center rounded-card border-2 px-10 py-6 text-center shadow-float ${
          good ? "border-primary" : "border-warning/80"
        }`}
      >
        <div className="flex items-center gap-4">
          <span className={`size-4 rounded-full ${good ? "bg-secondary" : "bg-warning"} animate-pulse-dot`} />
          <span className="text-4xl font-bold tracking-wide">{headline}</span>
        </div>
        {cue && <p className="mt-2 text-2xl text-muted">{cue}</p>}
      </div>
    </div>
  );
}

// Material-style glyphs, drawn inline so the kiosk needs nothing from the web.
const icon = (d, props) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={props?.className ?? "size-6"} aria-hidden>
    <path d={d} />
  </svg>
);

export const HandIcon = (p) =>
  icon(
    "M23 5.5V20c0 2.2-1.8 4-4 4h-7.3c-1.08 0-2.1-.43-2.85-1.19L1 14.83s1.26-1.23 1.3-1.25c.22-.19.49-.29.79-.29.22 0 .42.06.6.16.04.01 4.31 2.46 4.31 2.46V4c0-.83.67-1.5 1.5-1.5S11 3.17 11 4v7h1V1.5c0-.83.67-1.5 1.5-1.5S15 .67 15 1.5V11h1V2.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5V11h1V5.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5z",
    p,
  );

export const PoseIcon = (p) =>
  icon("M12 2c1.1 0 2 .9 2 2s-.9 2-2 2-2-.9-2-2 .9-2 2-2zm9 7h-6v13h-2v-6h-2v6H9V9H3V7h18v2z", p);

export const BackIcon = (p) => icon("M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z", p);

export const ChevronIcon = (p) => icon("M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z", p);

export const StopIcon = (p) => icon("M6 6h12v12H6z", p);

export const PlayIcon = (p) => icon("M8 5v14l11-7z", p);

export const RepeatIcon = (p) => icon("M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z", p);

export const HomeIcon = (p) => icon("M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z", p);

export const MusicIcon = (p) =>
  icon("M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z", p);

const stroked = (children, p) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={p?.className ?? "size-6"}
    aria-hidden
  >
    {children}
  </svg>
);

// A hand mirror: an oval glass on a stand, with a glint.
export const MirrorIcon = (p) =>
  stroked(
    <>
      <ellipse cx="12" cy="9.5" rx="6" ry="7.5" />
      <path d="M9.6 6.2 8.4 8.8M11.8 5.4l-2.6 5.4" />
      <path d="M12 17v4.5M8.5 21.5h7" />
    </>,
    p,
  );

// A head over a torso that is wide at the shoulders and narrow at the waist.
export const PhysiqueIcon = (p) =>
  stroked(
    <>
      <circle cx="12" cy="4.6" r="2.4" />
      <path d="M3.4 10.4C6.1 9 9 8.4 12 8.4s5.9.6 8.6 2L16.4 21H7.6z" />
    </>,
    p,
  );

// A lifter from the front with both forearms curled up, a dumbbell (the dot)
// in each hand.
export const CurlIcon = (p) =>
  stroked(
    <>
      <circle cx="12" cy="4" r="2.3" />
      <path d="M12 8.6v7M12 15.6l-2.6 6M12 15.6l2.6 6" />
      <path d="M12 9.8 7.4 10.6 6.4 15 3.8 11.6M12 9.8l4.6.8 1 4.4 2.6-3.4" />
      <circle cx="3.2" cy="10.6" r="0.9" />
      <circle cx="20.8" cy="10.6" r="0.9" />
    </>,
    p,
  );

// The same lifter with both arms raised out to the sides.
export const RaiseIcon = (p) =>
  stroked(
    <>
      <circle cx="12" cy="4" r="2.3" />
      <path d="M12 8.6v7M12 15.6l-2.6 6M12 15.6l2.6 6" />
      <path d="M4 8.9 12 10l8-1.1" />
      <circle cx="3" cy="8.7" r="0.9" />
      <circle cx="21" cy="8.7" r="0.9" />
    </>,
    p,
  );
