// Client-side decay-time relabeling.
//
// The API's `/plume` returns isodose-rate contours at fixed H+1 dose-rate
// levels. Way-Wigner decay (src/falloutcast/physics/decay.py) says dose rate
// at any later time is R(t) = R_h1 * t^-1.2 (t in hours), applied UNIFORMLY
// at every point on the ground. That separability means the contour for
// display level L at time t is EXACTLY the H+1 contour for level L * t^1.2 --
// so a decay-time slider doesn't need a new API call (and a fresh live wind
// fetch) on every drag. Fetch one dense, log-spaced set of H+1 levels once,
// then just look up the nearest one as the slider moves.
//
// Valid range per decay.py: t roughly 0.5 to 200 hours. Levels are spaced
// finely enough in log space (see LEVEL_COUNT) that snapping to the nearest
// fetched level shifts the displayed contour by an imperceptible amount.

export const DECAY_EXPONENT = 1.2;

// The bands actually shown at any moment -- civil-defense-standard dose-rate
// tiers, same as contour.DEFAULT_LEVELS on the backend.
export const DISPLAY_LEVELS_RHR = [1, 10, 100, 1000] as const;

export const TIME_MIN_HOURS = 1;
export const TIME_MAX_HOURS = 168; // 1 week

const LEVEL_MIN_RHR = 1e-3;
const LEVEL_MAX_RHR = 1e7;
const LEVEL_COUNT = 80;

/** Dense log-spaced H+1 levels to request from the API once per plume. Wide
 * enough to cover DISPLAY_LEVELS_RHR * t^1.2 across the whole time range
 * (1000 * 168^1.2 =~ 5.4e5, comfortably inside LEVEL_MAX_RHR). */
export function fetchLevelSet(): number[] {
  const levels: number[] = [];
  const logMin = Math.log(LEVEL_MIN_RHR);
  const logMax = Math.log(LEVEL_MAX_RHR);
  for (let i = 0; i < LEVEL_COUNT; i++) {
    const t = i / (LEVEL_COUNT - 1);
    levels.push(Math.exp(logMin + t * (logMax - logMin)));
  }
  return levels;
}

/** For each display level, find the closest level actually present in
 * `available` (the H+1 levels the API was asked for) to L * t^1.2. Returns
 * pairs of (displayLevel, h1LevelToRender) so the caller can select which
 * fetched contour feature to show for each display band. */
export function levelsForTime(
  t_hours: number,
  available: number[],
): Array<{ displayLevel: number; h1Level: number }> {
  return DISPLAY_LEVELS_RHR.map((displayLevel) => {
    const target = displayLevel * Math.pow(t_hours, DECAY_EXPONENT);
    const h1Level = nearest(available, target);
    return { displayLevel, h1Level };
  });
}

function nearest(sorted: number[], target: number): number {
  // available levels are log-spaced and small in count (LEVEL_COUNT), so a
  // linear scan compared in log-space (matches how they were spaced) is
  // simple and plenty fast for a UI-driven lookup.
  let best = sorted[0];
  let bestDist = Math.abs(Math.log(best) - Math.log(target));
  for (const level of sorted) {
    const dist = Math.abs(Math.log(level) - Math.log(target));
    if (dist < bestDist) {
      best = level;
      bestDist = dist;
    }
  }
  return best;
}
