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
// Valid range per decay.py: t roughly 0.5 to 200 hours.

export const DECAY_EXPONENT = 1.2;

// The bands actually shown at any moment -- civil-defense-standard dose-rate
// tiers, same as contour.DEFAULT_LEVELS on the backend.
export const DISPLAY_LEVELS_RHR = [1, 10, 100, 1000] as const;

export const TIME_MIN_HOURS = 1;
export const TIME_MAX_HOURS = 168; // 1 week

// The fetched grid is ANCHORED at the display levels: exactly LEVELS_PER_DECADE
// steps per decade starting from 1 R/hr, so every DISPLAY_LEVELS_RHR value (and
// every decade-multiple of one) is a grid point. That makes the default H+1 view
// exact -- the old unanchored 1e-3..1e7 ramp landed the "100 R/hr" band on the
// 86.4 R/hr contour and the "1000 R/hr" band on 890 R/hr.
const LEVELS_PER_DECADE = 16;
// Only [1 .. 1000 * 168^1.2 = 4.7e5] is ever displayable: the smallest band at
// the earliest time up to the largest band at the latest time. The old set also
// spanned 1e-3..1 R/hr, four decades of levels that can never be shown but which
// produce the widest, most vertex-heavy contours -- ~75% of the response payload.
const LEVEL_DECADES = 6; // 1 .. 1e6 R/hr
const LEVEL_COUNT = LEVELS_PER_DECADE * LEVEL_DECADES + 1;

// Half a grid step in log space (plus a hair of float slack). A display band
// whose required H+1 level is further than this from anything `available` does
// not exist in this plume, and must NOT fall back to the nearest contour that
// does -- see nearest().
const MAX_LOG_DIST = (Math.LN10 / LEVELS_PER_DECADE) * 0.5 * 1.01;

/** Log-spaced H+1 levels to request from the API once per plume, covering
 * DISPLAY_LEVELS_RHR * t^1.2 across the whole time range. */
export function fetchLevelSet(): number[] {
  const levels: number[] = [];
  for (let i = 0; i < LEVEL_COUNT; i++) {
    levels.push(Math.pow(10, i / LEVELS_PER_DECADE));
  }
  return levels;
}

/** For each display level, the level actually present in `available` (the H+1
 * levels the API returned contours for) that renders it at time t -- i.e. the
 * grid point matching L * t^1.2. Bands with no matching contour are OMITTED,
 * not approximated: a 300 kt plume peaking near 490 R/hr has no 1000 R/hr zone,
 * and drawing its 490 R/hr contour labelled "1000 R/hr" would overstate the
 * hazard by 2x. Callers should render only what comes back. */
export function levelsForTime(
  t_hours: number,
  available: number[],
): Array<{ displayLevel: number; h1Level: number }> {
  const picks: Array<{ displayLevel: number; h1Level: number }> = [];
  for (const displayLevel of DISPLAY_LEVELS_RHR) {
    const target = displayLevel * Math.pow(t_hours, DECAY_EXPONENT);
    const h1Level = nearest(available, target);
    if (h1Level !== null) picks.push({ displayLevel, h1Level });
  }
  return picks;
}

/** Closest available level to `target`, or null if even the closest is more
 * than half a grid step away (i.e. the target is off the end of what this
 * plume actually produced). */
function nearest(sorted: number[], target: number): number | null {
  // available levels are log-spaced and small in count (LEVEL_COUNT), so a
  // linear scan compared in log-space (matches how they were spaced) is
  // simple and plenty fast for a UI-driven lookup.
  if (sorted.length === 0) return null;
  let best = sorted[0];
  let bestDist = Math.abs(Math.log(best) - Math.log(target));
  for (const level of sorted) {
    const dist = Math.abs(Math.log(level) - Math.log(target));
    if (dist < bestDist) {
      best = level;
      bestDist = dist;
    }
  }
  return bestDist <= MAX_LOG_DIST ? best : null;
}
