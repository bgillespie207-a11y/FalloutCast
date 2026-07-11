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
