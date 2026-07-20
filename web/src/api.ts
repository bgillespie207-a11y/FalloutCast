// Thin typed client for the FalloutCast API (see src/falloutcast/schemas.py
// for the authoritative shapes -- kept in sync by hand, this frontend has no
// codegen step).

export interface ManualWind {
  speed_mph: number;
  bearing_deg: number;
  shear_mph_per_kft: number;
}

export interface PlumeRequest {
  lat: number;
  lon: number;
  yield_mt: number;
  fission_fraction: number;
  surface_burst?: boolean;
  tier?: 0 | 1;
  wind?: ManualWind;
  levels_rhr?: number[];
}

export interface WindUsed {
  speed_mph: number | null;
  bearing_deg: number | null;
  shear_mph_per_kft: number | null;
  source: string;
}

export interface GeoJsonFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: Record<string, number>;
    geometry: { type: string; coordinates: unknown };
  }>;
}

export interface WindProfilePoint {
  height_m: number;
  height_kft: number;
  speed_mph: number;
  from_deg: number;
  toward_deg: number;
  in_fallout_layer: boolean;
}

export interface PlumeResponse {
  ground_zero: [number, number];
  tier_requested: number;
  tier_used: number;
  wind: WindUsed;
  disclaimer: string;
  notes: string[];
  fraction_aloft: number | null;
  weather?: WeatherProvenance | null; // null/absent for manual wind (nothing fetched)
  wind_profile?: WindProfilePoint[] | null; // vertical profile; null for manual wind
  contours: GeoJsonFeatureCollection;
}

export interface Target {
  name: string;
  lat: number;
  lon: number;
  category: string;
  note: string;
}

export type Aggregation = "max_single_source" | "sum";

export interface WeatherProvenance {
  valid_time: string;
  model: string;
  retrieved_at: string | null;
  age_seconds: number | null;
}

export interface YieldPolicy {
  scenario: string;
  mode: string;
  surface_burst_caveat: string;
  assumptions?: Array<{
    category: string;
    yield_mt: number;
    yield_min_mt: number;
    yield_max_mt: number;
    fission_fraction: number;
    rationale: string;
  }>;
  yield_mt?: number;
  fission_fraction?: number;
}

export interface ExchangeEnvelopeResponse {
  n_targets: number;
  aggregation: Aggregation;
  deck_version: string;
  yield_policy: YieldPolicy;
  included_target_ids: string[];
  excluded_target_ids: string[];
  disclaimer: string;
  notes: string[];
  weather?: WeatherProvenance | null;
  contours: GeoJsonFeatureCollection;
}

export interface DoseSample {
  t_hours: number;
  dose_rate_rhr: number;
}

// Point assessment under a Tier-0 plume. `wind` echoes the effective wind the
// /plume response reported, so the backend evaluates the SAME model the map is
// showing (no second live fetch that could disagree).
export interface PointExposureRequest {
  lat: number; // ground zero
  lon: number;
  yield_mt: number;
  fission_fraction: number;
  wind: ManualWind;
  point_lat: number;
  point_lon: number;
  exit_hours?: number;
  protection_factor?: number;
}

export interface PointExposureResponse {
  point: [number, number]; // [lon, lat]
  distance_miles: number;
  bearing_from_gz_deg: number;
  arrival_hours: number;
  dose_rate_h1_rhr: number;
  rate_at_arrival_rhr: number;
  rate_curve: DoseSample[];
  protection_factor: number;
  unsheltered_dose_window_r: number | null;
  sheltered_dose_window_r: number | null;
  unsheltered_dose_to_infinity_r: number;
  sheltered_dose_to_infinity_r: number;
  disclaimer: string;
  notes: string[];
}

export function fetchExposure(req: PointExposureRequest): Promise<PointExposureResponse> {
  return postJson<PointExposureResponse>("/exposure", req);
}

export interface EnsembleRequest {
  lat: number;
  lon: number;
  yield_mt: number;
  fission_fraction: number;
  level_rhr: number;
  n_members: number;
}

export interface EnsembleResponse {
  ground_zero: [number, number];
  level_rhr: number;
  n_members: number;
  mean_fraction_aloft: number;
  disclaimer: string;
  notes: string[];
  // contour features carry { exceedance_probability: 0.1 | 0.5 | 0.9 }
  contours: GeoJsonFeatureCollection;
}

export interface FieldPolygon {
  id: string;
  wing: string;
  base: string;
  lf_count: number;
  lcc_count: number;
  geography_mode: string;
  confidence: string;
  source: string;
  pub_date: string;
  verify_date: string;
  polygon: number[][]; // closed ring of [lon, lat]
}

export interface TargetDeckMeta {
  version: string;
  content_hash: string;
  generated: string;
  n_targets: number;
  n_synthetic: number;
  fields: FieldPolygon[];
  notes: string[];
}

export function fetchDeck(): Promise<TargetDeckMeta> {
  return fetch(`${__API_URL__}/deck`).then((resp) => {
    if (!resp.ok) throw new ApiError(`/deck -> HTTP ${resp.status}`);
    return resp.json() as Promise<TargetDeckMeta>;
  });
}

export interface ZipLocation {
  lat: number;
  lon: number;
  place: string;
}

export class ApiError extends Error {}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${__API_URL__}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText);
    throw new ApiError(`${path} -> HTTP ${resp.status}: ${detail}`);
  }
  return resp.json() as Promise<T>;
}

export function fetchPlume(req: PlumeRequest): Promise<PlumeResponse> {
  return postJson<PlumeResponse>("/plume", req);
}

export function fetchEnsemble(req: EnsembleRequest): Promise<EnsembleResponse> {
  return postJson<EnsembleResponse>("/ensemble", req);
}

export function fetchTargets(expanded = false): Promise<Target[]> {
  const q = expanded ? "?expanded=true" : "";
  return fetch(`${__API_URL__}/targets${q}`).then((resp) => {
    if (!resp.ok) throw new ApiError(`/targets -> HTTP ${resp.status}`);
    return resp.json() as Promise<Target[]>;
  });
}

// /exchange/envelope takes query params, not a JSON body. Under the default
// per-class scenario the yields come from scenario.py (not the frontend), so no
// yield params are sent -- only the aggregation policy.
export async function fetchExchangeEnvelope(
  aggregation: Aggregation = "max_single_source",
  forceRefresh = false,
): Promise<ExchangeEnvelopeResponse> {
  const params = new URLSearchParams({ aggregation });
  if (forceRefresh) params.set("force_refresh", "true");
  const resp = await fetch(`${__API_URL__}/exchange/envelope?${params}`, { method: "POST" });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText);
    throw new ApiError(`/exchange/envelope -> HTTP ${resp.status}: ${detail}`);
  }
  return resp.json() as Promise<ExchangeEnvelopeResponse>;
}

// Zippopotam.us: free, keyless, CORS-open (access-control-allow-origin: *)
// US ZIP -> lat/lon lookup. Same "no signup required" bar as the OpenFreeMap
// basemap and Open-Meteo wind data this app already depends on -- called
// directly from the browser, no backend endpoint needed for it.
export async function geocodeZip(zip: string): Promise<ZipLocation> {
  const resp = await fetch(`https://api.zippopotam.us/us/${zip}`);
  if (!resp.ok) {
    throw new ApiError(resp.status === 404 ? `ZIP ${zip} not found` : `ZIP lookup HTTP ${resp.status}`);
  }
  const data = await resp.json();
  const place = data.places?.[0];
  if (!place) throw new ApiError(`ZIP ${zip} not found`);
  return {
    lat: Number(place.latitude),
    lon: Number(place.longitude),
    place: `${place["place name"]}, ${place["state abbreviation"]}`,
  };
}

// Nominatim (OpenStreetMap): free, keyless, CORS-open global forward geocoder
// for place names / addresses -- same "no API key/signup" bar as the ZIP
// lookup, basemap, and wind data above. Called directly from the browser
// (one request per explicit user action, well within Nominatim's 1 req/s
// usage policy). Complements geocodeZip: ZIP centroids stay on zippopotam
// (fast, US-specific); everything else -- "Cleveland", a street address, a
// place in Hawaii/Alaska -- resolves here. `limit=1` takes the best match; the
// resolved display name is surfaced so the user can see what it matched.
export async function geocodePlace(query: string): Promise<ZipLocation> {
  const params = new URLSearchParams({ format: "jsonv2", limit: "1", q: query });
  const resp = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!resp.ok) throw new ApiError(`Place search HTTP ${resp.status}`);
  const results = (await resp.json()) as Array<{
    lat: string;
    lon: string;
    display_name: string;
  }>;
  const top = results[0];
  if (!top) throw new ApiError(`No match for "${query}"`);
  return { lat: Number(top.lat), lon: Number(top.lon), place: top.display_name };
}
