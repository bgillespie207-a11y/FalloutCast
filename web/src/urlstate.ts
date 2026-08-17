// Shareable-link state: the scenario encoded in the query string.
//
// Serializing and parsing are pure and live here; reading the values off the
// form and writing them back into it stays in main.ts. Keeping the two apart
// is what makes the round trip testable -- a link that doesn't restore what it
// captured is a silent failure, since the app still renders a perfectly
// plausible (wrong) scenario.

export type UrlMode = "plume" | "exchange" | "ensemble";

export interface ManualWindState {
  speed: number;
  bearing: number;
  shear: number;
}

/** What the app puts INTO a link. Numbers are carried as the strings the form
 * holds, so a shared link quotes the user's own values (0.30 stays 0.30). */
export interface UrlState {
  mode: UrlMode;
  yieldMt: string;
  ff: string;
  lat?: string;
  lon?: string;
  tier?: 0 | 1;
  wind?: ManualWindState; // plume mode, manual wind only
  level?: string; // ensemble mode
  members?: string;
  agg?: EnvelopeAggregation; // exchange mode
}

/** Mirrors the API's `aggregation` query parameter. */
export type EnvelopeAggregation = "max_single_source" | "sum";

/** What comes back OUT of one. Every field is optional because a link may be
 * hand-edited or truncated: anything missing or non-numeric is dropped rather
 * than applied as NaN, which would wedge the form. */
export interface ParsedUrlState {
  mode: UrlMode;
  yieldMt?: string;
  ff?: string;
  lat?: string;
  lon?: string;
  tier?: 0 | 1;
  wind?: ManualWindState;
  level?: string;
  members?: string;
  agg?: EnvelopeAggregation;
}

export function buildUrlParams(state: UrlState): URLSearchParams {
  const params = new URLSearchParams();
  params.set("mode", state.mode);
  params.set("yield_mt", state.yieldMt);
  params.set("ff", state.ff);
  // The national envelope has no single ground zero, so lat/lon would be
  // meaningless noise in its link. Its aggregation, on the other hand, changes
  // what the numbers MEAN (screening envelope vs summed total), so a link that
  // dropped it would reopen showing a different quantity under the same view.
  if (state.mode === "exchange") {
    params.set("agg", state.agg ?? "max_single_source");
  } else {
    params.set("lat", state.lat ?? "");
    params.set("lon", state.lon ?? "");
  }
  if (state.mode === "plume") {
    params.set("tier", String(state.tier ?? 0));
    if (state.wind) {
      // speed,bearing,shear -- one param keeps the URL short
      params.set("wind", [state.wind.speed, state.wind.bearing, state.wind.shear].join(","));
    }
  }
  if (state.mode === "ensemble") {
    params.set("level", state.level ?? "");
    params.set("members", state.members ?? "");
  }
  return params;
}

/** Parse a `location.search`. Null when the query carries no scenario at all
 * (the plain / URL), which the caller treats as "leave the defaults alone". */
export function parseUrlParams(search: string): ParsedUrlState | null {
  const params = new URLSearchParams(search);
  const mode = params.get("mode");
  if (mode !== "plume" && mode !== "exchange" && mode !== "ensemble") return null;

  const state: ParsedUrlState = { mode };
  const numeric = (key: string): string | undefined => {
    const raw = params.get(key);
    return raw !== null && raw !== "" && Number.isFinite(Number(raw)) ? raw : undefined;
  };

  state.yieldMt = numeric("yield_mt");
  state.ff = numeric("ff");
  if (mode === "exchange") {
    const agg = params.get("agg");
    if (agg === "sum" || agg === "max_single_source") state.agg = agg;
    return state; // the rest doesn't apply
  }

  state.lat = numeric("lat");
  state.lon = numeric("lon");

  if (mode === "ensemble") {
    state.level = numeric("level");
    state.members = numeric("members");
    return state;
  }

  const tier = params.get("tier");
  if (tier === "0" || tier === "1") state.tier = Number(tier) as 0 | 1;

  const windParam = params.get("wind");
  if (windParam) {
    const [speed, bearing, shear] = windParam.split(",").map(Number);
    // All three or none: a partial triple would mix a shared wind with
    // whatever the form happened to hold.
    if ([speed, bearing, shear].every(Number.isFinite)) state.wind = { speed, bearing, shear };
  }
  return state;
}
