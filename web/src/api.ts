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

export interface PlumeResponse {
  ground_zero: [number, number];
  tier_requested: number;
  tier_used: number;
  wind: WindUsed;
  disclaimer: string;
  notes: string[];
  fraction_aloft: number | null;
  contours: GeoJsonFeatureCollection;
}

export interface Target {
  name: string;
  lat: number;
  lon: number;
  category: string;
  note: string;
}

export interface ExchangeEnvelopeRequest {
  yield_mt: number;
  fission_fraction: number;
}

export interface ExchangeEnvelopeResponse {
  yield_mt: number;
  fission_fraction: number;
  n_targets: number;
  disclaimer: string;
  notes: string[];
  contours: GeoJsonFeatureCollection;
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

// /exchange/envelope takes query params, not a JSON body (see schemas.py) --
// no Pydantic request model on that endpoint, unlike /plume.
export async function fetchExchangeEnvelope(
  req: ExchangeEnvelopeRequest,
): Promise<ExchangeEnvelopeResponse> {
  const params = new URLSearchParams({
    yield_mt: String(req.yield_mt),
    fission_fraction: String(req.fission_fraction),
  });
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
