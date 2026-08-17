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

// --- contour lines -> fillable areas -------------------------------------------
// The API returns isodose contours as MultiLineString: boundaries, not regions.
// A boundary alone leaves the reader to infer which side is hot, which is what
// made the national envelope read as ~600 overlapping rings. These helpers turn
// each closed contour into a polygon so the area can be tinted underneath the
// line. The LINE stays the authoritative geometry -- the fill is a readability
// aid drawn beneath it, never a substitute.

/** Is `pt` inside `ring`? Standard ray casting; the ring is treated as closed
 * whether or not its last vertex repeats the first. */
function pointInRing(pt: [number, number], ring: number[][]): boolean {
  const [x, y] = pt;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    // Half-open crossing test (yi > y) !== (yj > y) counts each edge once, so
    // a ray passing exactly through a shared vertex isn't double-counted.
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** A ring GeoJSON will accept as a polygon boundary: at least 3 distinct
 * vertices, explicitly closed. Returns null for anything that can't bound an
 * area. Contours clipped by the edge of the computed grid come back open, and
 * closing them with a straight chord is what keeps the biggest band filled;
 * the fill can then under-cover near that edge, which is the safe direction --
 * it never paints area the model didn't compute. */
function asClosedRing(ring: number[][]): number[][] | null {
  if (ring.length < 3) return null;
  const first = ring[0];
  const last = ring[ring.length - 1];
  const closed = first[0] === last[0] && first[1] === last[1];
  const distinct = closed ? ring.length - 1 : ring.length;
  if (distinct < 3) return null;
  return closed ? ring : [...ring, first];
}

/** Convert MultiLineString contour features into filled MultiPolygon features
 * with the same properties.
 *
 * Nesting is resolved rather than ignored: a ring contained by an odd number
 * of other rings at the same level is a HOLE (a pocket the contour encloses
 * but does not cover), and painting it solid would claim a hazard the model
 * didn't compute there. Each hole is attached to the innermost ring that
 * contains it, so an island inside a hole fills again correctly. */
export function contourFillFeatures(
  features: GeoJsonFeatureCollection["features"],
): GeoJsonFeatureCollection["features"] {
  const out: GeoJsonFeatureCollection["features"] = [];

  for (const f of features) {
    const raw = f.geometry.coordinates;
    if (!Array.isArray(raw)) continue;
    // LineString (one ring) and MultiLineString (many) both arrive here.
    const candidates: number[][][] =
      typeof (raw as number[][])[0]?.[0] === "number"
        ? [raw as unknown as number[][]]
        : (raw as unknown as number[][][]);

    const rings: number[][][] = [];
    for (const c of candidates) {
      const ring = asClosedRing(c);
      if (ring) rings.push(ring);
    }
    if (rings.length === 0) continue;

    // Containment depth per ring: how many OTHER rings enclose it.
    const depth = rings.map((ring, i) =>
      rings.reduce(
        (n, other, j) => (j !== i && pointInRing(ring[0] as [number, number], other) ? n + 1 : n),
        0,
      ),
    );

    // Even depth = a filled region; odd = a hole in the ring just outside it.
    const polygons: number[][][][] = [];
    const exteriorIndex = new Map<number, number>(); // ring index -> polygon index
    rings.forEach((ring, i) => {
      if (depth[i] % 2 === 0) {
        exteriorIndex.set(i, polygons.length);
        polygons.push([ring]);
      }
    });
    rings.forEach((ring, i) => {
      if (depth[i] % 2 === 0) return;
      // The innermost containing exterior ring is the one with the greatest
      // depth among those that contain this hole.
      let best = -1;
      for (const j of exteriorIndex.keys()) {
        if (!pointInRing(ring[0] as [number, number], rings[j])) continue;
        if (best < 0 || depth[j] > depth[best]) best = j;
      }
      if (best >= 0) polygons[exteriorIndex.get(best)!].push(ring);
    });
    if (polygons.length === 0) continue;

    out.push({
      type: "Feature",
      properties: f.properties,
      geometry: { type: "MultiPolygon", coordinates: polygons },
    });
  }

  return out;
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
