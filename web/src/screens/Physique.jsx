import { useEffect, useRef, useState } from "react";
import Feed from "../components/Feed";
import { BackIcon, Button, Cue, TopBar } from "../components/ui";
import { useHeader } from "../station";

const accept = (h) => h.screen === "physique";
const IDLE = { headline: "STEP IN", cue: "Step in front of the screen", ratio: null, verdict: null };
// The number runs up from a straight trunk, and the meme lands once it is in.
const FROM = 1.0;
const COUNT_MS = 900;
const MEME_MS = 1400;

// Posing. The camera as it is, a line across your shoulders and one across
// your waist, and the one over the other as a number. Then the verdict: a
// meme, picked by the number.
export default function Physique() {
  const p =
    useHeader(
      (h) =>
        h.physique && {
          headline: h.physique.headline,
          cue: h.physique.cue,
          ratio: h.physique.ratio,
          verdict: h.physique.verdict,
        },
    ) ?? IDLE;
  const shown = useCountUp(p.ratio, FROM, COUNT_MS);
  const [judged, setJudged] = useState(false);
  const v = p.verdict;
  const picture = usePicture(v?.image);

  useEffect(() => {
    setJudged(false);
    if (p.ratio == null) return;
    const id = setTimeout(() => setJudged(true), MEME_MS);
    return () => clearTimeout(id);
  }, [p.ratio]);

  // The sticker waits for its picture, so it lands whole. A picture that is
  // not on the station leaves the words to make the sticker, and one with no
  // words is left out.
  const meme = judged && v && picture !== "loading" && (picture === "ready" || v.caption) ? v : null;

  return (
    <div className="absolute inset-0 animate-fade bg-black">
      <Feed accept={accept} lines className="absolute inset-0 size-full" />
      <div className="absolute inset-x-0 top-0 h-[20%] bg-gradient-to-b from-bg/85 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-[30%] bg-gradient-to-t from-bg/90 via-bg/45 to-transparent" />

      <TopBar
        left={
          <Button id="back" className="h-24 w-[11rem]">
            <BackIcon className="size-7" /> Back
          </Button>
        }
      />

      {/* Down where the number will be, out of the way of the pose. */}
      {p.headline && (
        <Cue headline={p.headline} cue={p.cue} good={p.headline === "HOLD STILL"} className="bottom-12" />
      )}

      {shown != null && (
        <div className="absolute inset-x-5 bottom-9 flex items-end justify-center">
          <div className="flex shrink-0 animate-pop flex-col items-center">
            <span className="lit text-[9.5rem] leading-[0.85] font-bold text-ink tabular">{shown.toFixed(2)}</span>
            <span className="mt-4 text-xl font-bold tracking-[0.14em] text-ink/85 uppercase">Shoulder to waist</span>
          </div>
          {/* The number moves over as the sticker's place opens beside it. */}
          <div
            className={`relative shrink-0 transition-[width,margin] duration-500 ease-out ${
              meme ? "ml-6 w-[16.5rem]" : "ml-0 w-0"
            }`}
          >
            {meme && <Meme verdict={meme} bare={picture !== "ready"} />}
          </div>
        </div>
      )}
    </div>
  );
}

// The verdict, slapped on like a sticker: the picture in a white border, a
// little askew, with its words across the bottom the way memes wear them.
function Meme({ verdict, bare }) {
  return (
    <figure className="absolute bottom-0 left-0 grid w-[16.5rem] animate-slap overflow-hidden rounded-[0.5rem] border-[0.35rem] border-white bg-black shadow-float">
      {!bare && (
        <img
          src={memeUrl(verdict.image)}
          alt=""
          className="col-start-1 row-start-1 block max-h-[19rem] w-full object-cover object-top"
        />
      )}
      {verdict.caption && (
        <figcaption className={`meme col-start-1 row-start-1 self-end px-3 ${bare ? "py-8" : "pb-2"}`}>
          {verdict.caption}
        </figcaption>
      )}
    </figure>
  );
}

const memeUrl = (image) => `/memes/${image}.jpg`;

// Whether a verdict's picture is in: "loading", "ready" or "missing". It is
// fetched as soon as the verdict is known, while the number is still running
// up.
function usePicture(image) {
  const [state, setState] = useState({ image: null, is: "loading" });
  useEffect(() => {
    if (!image) return;
    const img = new Image();
    img.onload = () => setState({ image, is: "ready" });
    img.onerror = () => setState({ image, is: "missing" });
    img.src = memeUrl(image);
    return () => {
      img.onload = img.onerror = null;
    };
  }, [image]);
  return state.image === image ? state.is : "loading";
}

// A number that runs up from `from` to its value when it first appears.
function useCountUp(target, from, ms) {
  const [shown, setShown] = useState(target == null ? null : from);
  const at = useRef(null);
  useEffect(() => {
    if (target == null) {
      at.current = null;
      setShown(null);
      return;
    }
    const start = at.current ?? from;
    const t0 = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const k = Math.min(1, (now - t0) / ms);
      at.current = start + (target - start) * (1 - (1 - k) ** 3);
      setShown(at.current);
      if (k < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [target, from, ms]);
  return shown;
}
