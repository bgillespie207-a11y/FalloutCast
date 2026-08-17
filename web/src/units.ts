// Metric/US display preference and every formatter that depends on it.
//
// The preference is module state rather than a parameter on each call: it's a
// single global UI setting, and threading it through every render path would
// be noise. main.ts owns the DOM side of it -- the radiogroup, localStorage
// persistence, and re-rendering what's on screen after a switch.
//
// Distances are always shown in BOTH units; the preference only decides which
// one leads. Dose stays in R (the model's native roentgen) with an approximate
// Sv alongside in metric mode -- clearly labeled, since R->Sv is only a
// whole-body-gamma rule of thumb.

import type { WindProfilePoint } from "./api";
import { fmtNum } from "./format";

export type UnitSystem = "metric" | "us";

export const KM_PER_MI = 1.609344;
export const MSV_PER_R = 10; // ~1 R exposure ~ 10 mSv effective dose, whole-body gamma (approx)

let unitSystem: UnitSystem = "metric";

export function getUnitSystem(): UnitSystem {
  return unitSystem;
}

/** Set the preference. Persistence and re-render are the caller's job. */
export function setUnitSystem(sys: UnitSystem): void {
  unitSystem = sys;
}

/** Sub-10 distances keep a decimal; above that it's false precision. */
export function fmtDist(v: number): string {
  return v >= 10 ? v.toFixed(0) : v.toFixed(1);
}

/** Distance in both units, primary per the preference. */
export function formatReach(km: number): string {
  const mi = km / KM_PER_MI;
  return unitSystem === "metric"
    ? `${fmtDist(km)} km (${fmtDist(mi)} mi)`
    : `${fmtDist(mi)} mi (${fmtDist(km)} km)`;
}

/** Wind speed, primary per preference with the other in parentheses. */
export function formatSpeed(mph: number): string {
  const kmh = mph * KM_PER_MI;
  return unitSystem === "metric"
    ? `${kmh.toFixed(0)} km/h (${mph.toFixed(0)} mph)`
    : `${mph.toFixed(0)} mph (${kmh.toFixed(0)} km/h)`;
}

/** Compact, primary-unit-only speed for the wind-profile rows. */
export function formatSpeedShort(mph: number): string {
  return unitSystem === "metric" ? `${(mph * KM_PER_MI).toFixed(0)} km/h` : `${mph.toFixed(0)} mph`;
}

export function formatHeightShort(p: WindProfilePoint): string {
  return unitSystem === "metric" ? `${(p.height_m / 1000).toFixed(1)} km` : `${p.height_kft.toFixed(0)} kft`;
}

/** Approximate SI dose for a roentgen figure (metric mode only). */
export function svApprox(r: number): string {
  const mSv = r * MSV_PER_R;
  return mSv >= 1000 ? `${(mSv / 1000).toFixed(mSv >= 10000 ? 0 : 1)} Sv` : `${mSv.toFixed(mSv >= 10 ? 0 : 1)} mSv`;
}

/** A dose in R, with the approximate Sv appended in metric mode. */
export function fmtDose(r: number): string {
  const base = `${fmtNum(r)} R`;
  return unitSystem === "metric" ? `${base} (≈ ${svApprox(r)})` : base;
}
