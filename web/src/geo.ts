// Geometry helpers behind the contour table's "how far, and in which
// direction" readout. Spherical earth throughout: these describe plume reach
// over a few hundred km, where the ellipsoidal correction is far below the
// model's own uncertainty.

import type { GeoJsonFeatureCollection } from "./api";

export const EARTH_RADIUS_KM = 6371;
const DEG = Math.PI / 180;

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * DEG;
  const dLon = (lon2 - lon1) * DEG;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * DEG) * Math.cos(lat2 * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

/** Great-circle bearing at the start point, degrees clockwise from true north. */
export function initialBearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const y = Math.sin((lon2 - lon1) * DEG) * Math.cos(lat2 * DEG);
  const x =
    Math.cos(lat1 * DEG) * Math.sin(lat2 * DEG) -
    Math.sin(lat1 * DEG) * Math.cos(lat2 * DEG) * Math.cos((lon2 - lon1) * DEG);
  return (Math.atan2(y, x) / DEG + 360) % 360;
}

const COMPASS_16 = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];

export function compassName(bearing: number): string {
  return COMPASS_16[Math.round(bearing / 22.5) % 16];
}

/** Farthest vertex of the given contour features from ground zero (gz is
 * [lon, lat], GeoJSON order). Null if the features have no coordinates. */
export function farthestPoint(
  features: GeoJsonFeatureCollection["features"],
  gz: [number, number],
): { km: number; bearing: number } | null {
  let best: { km: number; bearing: number } | null = null;
  const visit = (coords: unknown): void => {
    if (typeof (coords as number[])[0] === "number" && (coords as number[]).length >= 2) {
      const [lon, lat] = coords as number[];
      const km = haversineKm(gz[1], gz[0], lat, lon);
      if (!best || km > best.km) {
        best = { km, bearing: initialBearingDeg(gz[1], gz[0], lat, lon) };
      }
    } else if (Array.isArray(coords)) {
      for (const c of coords) visit(c);
    }
  };
  for (const f of features) visit(f.geometry.coordinates);
  return best;
}
