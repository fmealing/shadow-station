import { useEffect, useState } from "react";
import Feed from "../components/Feed";
import { BackIcon, Button, TopBar } from "../components/ui";
import { useHeader } from "../station";

const accept = (h) => h.screen === "mirror";
// How long the buttons stay after the last sight of a pointing hand, and how
// long they show on the way in, so you see where they went.
const LINGER_MS = 2500;
const INTRO_MS = 3500;

// Just the camera. The buttons get out of the way unless you point.
export default function Mirror() {
  const pointing = useHeader((h) => h.cursor != null) ?? false;
  const [shown, setShown] = useState(true);
  const [intro, setIntro] = useState(true);

  useEffect(() => {
    const id = setTimeout(() => setIntro(false), INTRO_MS);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    if (pointing || intro) {
      setShown(true);
      return;
    }
    const id = setTimeout(() => setShown(false), LINGER_MS);
    return () => clearTimeout(id);
  }, [pointing, intro]);

  return (
    <div className="absolute inset-0 animate-fade bg-black">
      <Feed accept={accept} className="absolute inset-0 size-full" />
      <div className={`transition-opacity duration-500 ${shown ? "opacity-100" : "opacity-0"}`}>
        <div className="absolute inset-x-0 top-0 h-[18%] bg-gradient-to-b from-bg/80 to-transparent" />
        <TopBar
          left={
            <Button id="back" className="h-24 w-[11rem]">
              <BackIcon className="size-7" /> Back
            </Button>
          }
        />
        <div
          className={`absolute inset-x-5 bottom-10 flex justify-center transition-opacity duration-500 ${
            intro ? "opacity-100" : "opacity-0"
          }`}
        >
          <p className="glass rounded-pill px-6 py-3 text-2xl font-medium text-ink">
            Point at the screen to bring these back
          </p>
        </div>
      </div>
    </div>
  );
}
