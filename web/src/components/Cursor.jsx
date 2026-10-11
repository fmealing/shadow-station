import { useHeader } from "../station";

// How far down the screen the top bar's buttons reach, and a little more.
const CONTROLS = 0.22;

// The pointer: a ring on the fingertip (or raised hand), with the dwell
// filling around it while a button is hovered. Blue with a white halo, so it
// reads on the dark screens and on the camera alike.
//
// While you are the picture (lifting in a set, posing in Physique), your
// hands are all over the screen without pointing at anything. There the ring
// only shows up by the buttons at the top.
export default function Cursor() {
  const cursor = useHeader((h) => h.cursor);
  const progress = useHeader((h) => h.hover?.p ?? 0) ?? 0;
  const hovering = useHeader((h) => h.hover != null) ?? false;
  const busy = useHeader((h) => h.screen === "physique" || h.live?.phase === "recording") ?? false;
  if (!cursor) return null;
  if (busy && !hovering && cursor[1] > CONTROLS) return null;
  const R = 26;
  const C = 2 * Math.PI * R;
  return (
    <svg
      viewBox="0 0 64 64"
      className="pointer-events-none absolute z-50 size-16 -translate-x-1/2 -translate-y-1/2 overflow-visible transition-[left,top] duration-[40ms] ease-linear"
      style={{ left: `${cursor[0] * 100}%`, top: `${cursor[1] * 100}%` }}
    >
      <circle cx="32" cy="32" r="14" fill="none" stroke="#FFFFFF" strokeWidth="8" opacity="0.85" />
      <circle cx="32" cy="32" r="14" fill="rgba(58,123,213,0.25)" stroke="#3A7BD5" strokeWidth="3" />
      {progress > 0 && (
        <g fill="none" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - progress)} transform="rotate(-90 32 32)">
          <circle cx="32" cy="32" r={R} stroke="#FFFFFF" strokeWidth="9" opacity="0.85" />
          <circle cx="32" cy="32" r={R} stroke="#3A7BD5" strokeWidth="5" />
        </g>
      )}
    </svg>
  );
}
