// Unit-independent formatting shared by the panel, the contour table, and the
// exported report. (Anything whose output depends on the metric/US preference
// lives in units.ts instead.)

/** Dose rates and doses span many decades, so the significant-figure rule has
 * to move with the magnitude: whole numbers when large, two significant
 * figures down to 0.01, exponential below that. Plain "0" for exact zero,
 * since "0.0e+0" reads like a measurement. */
export function fmtNum(v: number): string {
  if (v >= 100) return v.toFixed(0);
  if (v >= 10) return v.toFixed(1);
  if (v >= 0.01) return v.toPrecision(2);
  if (v === 0) return "0";
  return v.toExponential(1);
}

/** Decay-slider label. Hours are the useful unit early on; past two days the
 * hour count stops being readable and days take over. */
export function formatHours(hours: number): string {
  if (hours < 48) return `H+${hours.toFixed(1)}h`;
  return `H+${(hours / 24).toFixed(1)}d`;
}

/** How stale the fetched winds are, in words. Deliberately coarse -- the point
 * is "is this forecast current?", not a precise duration. */
export function describeAge(seconds: number): string {
  if (seconds < 90) return "just now";
  const min = Math.round(seconds / 60);
  if (min < 90) return `${min} min ago`;
  return `${(min / 60).toFixed(1)} h ago`;
}
