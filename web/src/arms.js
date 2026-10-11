// Each arm's colour, in the order the arms appear on screen (as the station
// sends their angles): the goniometer on the camera, the summary's cards and
// the chart all use it, so an arm is the same colour everywhere. Brand blue
// and an orange, checked for colour-blind separation and contrast on the
// dark card.
export const ARM_COLORS = ["#3A7BD5", "#E0703A"];

// An arm whose reps keep stopping short wears the warning's colour instead.
export const SHORT_COLOR = "#E0A030";

// Each arm's shoulder, elbow and wrist, then the other arm's shoulder, which
// says which way is out. In screen order, as `armsOnScreen`.
const LIMBS = [
  [11, 13, 15, 12],
  [12, 14, 16, 11],
];
export function limbsOnScreen(points) {
  if (!points[11] || !points[12]) return null;
  return points[11][0] <= points[12][0] ? LIMBS : [LIMBS[1], LIMBS[0]];
}

// What a goniometer is laid along at each joint, by the tracker's own left
// and right: the joint itself, then the two points its angle runs between.
// The shoulder's runs from the trunk (the hip) to the upper arm (the elbow).
// The elbow's runs from the upper arm carried on past the elbow, which is
// where the forearm lies with the arm straight, to the forearm (the wrist):
// `through` says the first point is behind the joint, not ahead of it.
const JOINTS = {
  shoulder: { arms: [[11, 23, 13], [12, 24, 14]], through: false },
  elbow: { arms: [[13, 11, 15], [14, 12, 16]], through: true },
};

// The arms in screen order (the one whose shoulder is further left first),
// each as [joint, from, to], and whether `from` is behind the joint.
export function armsOnScreen(points, joint) {
  const j = JOINTS[joint];
  if (!j || !points[11] || !points[12]) return null;
  const arms = points[11][0] <= points[12][0] ? j.arms : [j.arms[1], j.arms[0]];
  return { arms, through: j.through };
}
