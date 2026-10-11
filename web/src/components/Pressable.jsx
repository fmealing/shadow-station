import { useEffect, useRef, useState } from "react";
import { onPressed, register, useHeader } from "../station";

// Something the cursor can press. It tells the station where it is, and shows
// what the station says about it: the dwell filling up while hovered, and a
// flash when pressed. The station does the hit-testing and the timing.
//
// `fill` is the colour the dwell grows in: blue on dark buttons, white on
// blue ones. `hold` marks a zone with the toggle's own hold time.
export default function Pressable({ id, hold = false, fill = "bg-primary/40", className = "", children }) {
  const ref = useRef(null);
  const progress = useHeader((h) => (h.hover?.id === id ? h.hover.p : 0)) ?? 0;
  const hovered = useHeader((h) => h.hover?.id === id) ?? false;
  const [flash, setFlash] = useState(0);

  useEffect(() => register(id, ref.current, hold), [id, hold]);
  useEffect(() => onPressed((pressed) => pressed === id && setFlash((n) => n + 1)), [id]);

  return (
    <div
      ref={ref}
      data-hovered={hovered || undefined}
      className={`group relative overflow-hidden transition-[box-shadow,border-color] duration-150 ${className}`}
    >
      <div className={`absolute inset-y-0 left-0 ${fill}`} style={{ width: `${progress * 100}%` }} />
      {flash > 0 && (
        <div key={flash} className="absolute inset-0 animate-flash bg-secondary" />
      )}
      <div className="relative h-full">{children}</div>
    </div>
  );
}
