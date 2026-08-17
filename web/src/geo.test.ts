import { describe, expect, it } from "vitest";

import type { GeoJsonFeatureCollection } from "./api";
import { compassName, farthestPoint, haversineKm, initialBearingDeg } from "./geo";

const feature = (
  type: string,
  coordinates: unknown,
): GeoJsonFeatureCollection["features"][number] => ({
  type: "Feature",
  properties: { level_rhr: 100 },
  geometry: { type, coordinates },
});

describe("haversineKm", () => {
  it("matches the spherical arc length for a degree of latitude", () => {
    // 1 deg of latitude on a 6371 km sphere = 6371 * pi/180 = 111.19 km.
    expect(haversineKm(0, 0, 1, 0)).toBeCloseTo(111.195, 2);
    expect(haversineKm(45, -100, 46, -100)).toBeCloseTo(111.195, 2);
  });

  it("shrinks a degree of longitude by cos(latitude)", () => {
    expect(haversineKm(0, 0, 0, 1)).toBeCloseTo(111.195, 2);
    expect(haversineKm(60, 0, 60, 1)).toBeCloseTo(111.195 / 2, 1);
  });

  it("is zero for the same point and symmetric between endpoints", () => {
    expect(haversineKm(41.5, -81.7, 41.5, -81.7)).toBe(0);
    expect(haversineKm(38.9, -77.0, 41.9, -87.6)).toBeCloseTo(
      haversineKm(41.9, -87.6, 38.9, -77.0),
      9,
    );
  });

  it("gets a known long pair about right (DC -> Chicago ~ 960 km)", () => {
    expect(haversineKm(38.9072, -77.0369, 41.8781, -87.6298)).toBeGreaterThan(940);
    expect(haversineKm(38.9072, -77.0369, 41.8781, -87.6298)).toBeLessThan(980);
  });
});

describe("initialBearingDeg", () => {
  it("reads the cardinal directions", () => {
    expect(initialBearingDeg(0, 0, 1, 0)).toBeCloseTo(0, 6); // north
    expect(initialBearingDeg(0, 0, 0, 1)).toBeCloseTo(90, 6); // east
    expect(initialBearingDeg(1, 0, 0, 0)).toBeCloseTo(180, 6); // south
    expect(initialBearingDeg(0, 1, 0, 0)).toBeCloseTo(270, 6); // west
  });

  it("always returns 0..360, never a negative angle", () => {
    // The atan2 branch is negative for anything west of north; a raw value
    // would then index compassName() out of the table.
    for (const [lat, lon] of [
      [1, -1],
      [-1, -1],
      [0.001, -0.5],
    ]) {
      const b = initialBearingDeg(0, 0, lat, lon);
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThan(360);
    }
  });
});

describe("compassName", () => {
  it("maps the 16-point rose", () => {
    expect(compassName(0)).toBe("N");
    expect(compassName(22.5)).toBe("NNE");
    expect(compassName(90)).toBe("E");
    expect(compassName(135)).toBe("SE");
    expect(compassName(180)).toBe("S");
    expect(compassName(270)).toBe("W");
    expect(compassName(337.5)).toBe("NNW");
  });

  it("wraps back to N at the top of the circle", () => {
    expect(compassName(349)).toBe("N");
    expect(compassName(360)).toBe("N");
  });
});

describe("farthestPoint", () => {
  const gz: [number, number] = [-77, 38.9]; // [lon, lat], GeoJSON order

  it("finds the farthest vertex of a polygon ring and its bearing", () => {
    const features = [
      feature("Polygon", [
        [
          [-77, 39.0],
          [-77, 39.5], // ~66 km due north -- the winner
          [-77.2, 38.9],
          [-77, 39.0],
        ],
      ]),
    ];
    const best = farthestPoint(features, gz);
    expect(best).not.toBeNull();
    expect(best!.km).toBeCloseTo(haversineKm(38.9, -77, 39.5, -77), 9);
    expect(compassName(best!.bearing)).toBe("N");
  });

  it("recurses through MultiPolygon nesting", () => {
    // Contours come back as a mix of Polygon and MultiPolygon; a version that
    // only walked one level deep would silently under-report reach.
    const features = [
      feature("MultiPolygon", [
        [[[-77, 39.0], [-77, 39.1], [-77, 39.0]]],
        [[[-77, 40.0], [-77, 39.9], [-77, 40.0]]], // ~122 km north
      ]),
    ];
    expect(farthestPoint(features, gz)!.km).toBeCloseTo(haversineKm(38.9, -77, 40, -77), 9);
  });

  it("takes the max across every feature, not just the first", () => {
    const features = [
      feature("LineString", [
        [-77, 39.0],
        [-77, 39.2],
      ]),
      feature("LineString", [
        [-76, 38.9], // ~87 km due east
        [-76.5, 38.9],
      ]),
    ];
    const best = farthestPoint(features, gz)!;
    expect(best.km).toBeCloseTo(haversineKm(38.9, -77, 38.9, -76), 9);
    expect(compassName(best.bearing)).toBe("E");
  });

  it("returns null when there is nothing to measure", () => {
    expect(farthestPoint([], gz)).toBeNull();
    expect(farthestPoint([feature("Polygon", [])], gz)).toBeNull();
  });

  it("ignores the elevation slot in a 3-element position", () => {
    const best = farthestPoint([feature("LineString", [[-77, 39.5, 120]])], gz)!;
    expect(best.km).toBeCloseTo(haversineKm(38.9, -77, 39.5, -77), 9);
  });
});
