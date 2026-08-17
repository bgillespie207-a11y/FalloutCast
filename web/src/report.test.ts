import { beforeEach, describe, expect, it } from "vitest";

import type { YieldPolicy } from "./api";
import { setUnitSystem } from "./units";
import {
  UNITS_NOTE,
  exportMetadata,
  fmtLonLat,
  reportMarkdown,
  round1,
  weatherFactStr,
  type ExportReport,
} from "./report";

beforeEach(() => setUnitSystem("metric"));

const baseReport: ExportReport = {
  mode: "plume",
  title: "Single plume — 0.3 Mt",
  generatedIso: "2026-08-17T20:15:00.000Z",
  facts: [
    ["Ground zero", "41.1400, -104.8200 (lat, lon)"],
    ["Yield", "0.3 Mt"],
  ],
  displayTime: "H+1.0h",
  reachCaption: "Contour reach at H+1.0h",
  reach: [
    { label: "1 R/hr", km: 463.27, bearingDeg: 112.4 },
    { label: "10 R/hr", km: 153.4, bearingDeg: 112.0 },
  ],
  notes: ["3% of activity carried past the local footprint (regional/global)."],
  disclaimer: "Planning estimate only, not an operational product.",
};

const yieldPolicy: YieldPolicy = {
  scenario: "Plan A (Princeton)",
  mode: "per_class",
  surface_burst_caveat: "All bursts modeled as surface bursts, which bounds fallout.",
  assumptions: [
    {
      category: "icbm_field",
      yield_mt: 0.8,
      yield_min_mt: 0.5,
      yield_max_mt: 1,
      fission_fraction: 0.5,
      rationale: "illustrative",
    },
  ],
};

describe("fmtLonLat", () => {
  it("prints GeoJSON [lon, lat] in the lat, lon order people read", () => {
    // The swap is the whole point: silently reversed coordinates put Cheyenne
    // in the Indian Ocean and nothing in the output would look wrong.
    expect(fmtLonLat([-104.82, 41.14])).toBe("41.1400, -104.8200 (lat, lon)");
  });
});

describe("weatherFactStr", () => {
  it("states model, valid hour, and fetch age", () => {
    expect(
      weatherFactStr({
        model: "GFS (Open-Meteo gfs_seamless)",
        valid_time: "2026-08-17T20:00",
        retrieved_at: "2026-08-17T20:10:00Z",
        age_seconds: 600,
      }),
    ).toBe("GFS (Open-Meteo gfs_seamless), valid 2026-08-17T20:00Z, fetched 10 min ago");
  });

  it("omits the age when the API didn't report one", () => {
    expect(
      weatherFactStr({
        model: "GFS",
        valid_time: "2026-08-17T20:00",
        retrieved_at: null,
        age_seconds: null,
      }),
    ).toBe("GFS, valid 2026-08-17T20:00Z");
  });
});

describe("round1", () => {
  it("rounds to a tenth", () => {
    expect(round1(463.27)).toBe(463.3);
    expect(round1(0.04)).toBe(0);
  });
});

describe("exportMetadata", () => {
  it("stamps app version, API, mode and the assumption pairs", () => {
    const meta = exportMetadata(baseReport);
    expect(meta.app).toBe(`FalloutCast ${__APP_VERSION__}`);
    expect(meta.api_url).toBe(__API_URL__);
    expect(meta.mode).toBe("plume");
    expect(meta.generated).toBe("2026-08-17T20:15:00.000Z");
    expect(meta.assumptions).toEqual({
      "Ground zero": "41.1400, -104.8200 (lat, lon)",
      Yield: "0.3 Mt",
    });
  });

  it("always carries the units note and the disclaimer", () => {
    // An exported file circulates without the app around it, so these have to
    // be in the file itself.
    const meta = exportMetadata(baseReport);
    expect(meta.units).toBe(UNITS_NOTE);
    expect(meta.disclaimer).toBe(baseReport.disclaimer);
  });

  it("gives contour reach in both units, plus degrees and compass", () => {
    const meta = exportMetadata(baseReport) as { contour_reach: Record<string, unknown>[] };
    expect(meta.contour_reach[0]).toEqual({
      band: "1 R/hr",
      max_reach_km: 463.3,
      max_reach_mi: 287.9,
      toward_deg: 112,
      toward_compass: "ESE",
    });
  });

  it("records the decay time the contours are a slice of", () => {
    expect(exportMetadata(baseReport).display_time).toBe("H+1.0h");
  });

  it("leaves out sections the mode doesn't have", () => {
    // The envelope has no single GZ (no reach table); a plume has no
    // per-class yield policy. Emitting empty keys would imply otherwise.
    const envelope: ExportReport = {
      ...baseReport,
      mode: "exchange",
      displayTime: undefined,
      reach: undefined,
      reachCaption: undefined,
      yieldPolicy,
    };
    const meta = exportMetadata(envelope);
    expect(meta).not.toHaveProperty("contour_reach");
    expect(meta).not.toHaveProperty("display_time");
    expect(meta.yield_policy).toEqual(yieldPolicy);
    expect(exportMetadata(baseReport)).not.toHaveProperty("yield_policy");
  });

  it("survives JSON round-tripping (it ships inside the GeoJSON)", () => {
    const meta = exportMetadata(baseReport);
    expect(JSON.parse(JSON.stringify(meta))).toEqual(meta);
  });
});

describe("reportMarkdown", () => {
  it("leads with the title, the planning-estimate line, and the versions", () => {
    const md = reportMarkdown(baseReport);
    expect(md.startsWith(`# FalloutCast — ${baseReport.title}`)).toBe(true);
    expect(md).toContain("_Planning estimate, not an operational product. Generated 2026-08-17T20:15:00.000Z._");
    expect(md).toContain(`**App:** FalloutCast ${__APP_VERSION__} · **API:** ${__API_URL__}`);
    expect(md).toContain("**Contours shown at:** H+1.0h after burst");
  });

  it("lists the assumptions in the order they were recorded", () => {
    const md = reportMarkdown(baseReport);
    expect(md.indexOf("- **Ground zero:**")).toBeLessThan(md.indexOf("- **Yield:**"));
  });

  it("renders the reach table in the reader's own units", () => {
    expect(reportMarkdown(baseReport)).toContain("| 1 R/hr | 463 km (288 mi) | ESE (112°) |");
    setUnitSystem("us");
    expect(reportMarkdown(baseReport)).toContain("| 1 R/hr | 288 mi (463 km) | ESE (112°) |");
  });

  it("prints the per-class yields with the surface-burst caveat", () => {
    // The yields are illustrative attacker assumptions; the caveat is what
    // keeps the table from reading as sourced weapon data.
    const md = reportMarkdown({ ...baseReport, mode: "exchange", yieldPolicy });
    expect(md).toContain("## Attack-scenario yields (per target class)");
    expect(md).toContain("Scenario: **Plan A (Princeton)** (per_class)");
    expect(md).toContain("Illustrative attacker assumptions, not the targets' own weapons.");
    expect(md).toContain("| icbm_field | 0.8 Mt | 0.5–1 Mt | 0.5 |");
    expect(md).toContain("_All bursts modeled as surface bursts, which bounds fallout._");
  });

  it("ends with the units note and the disclaimer", () => {
    const md = reportMarkdown(baseReport);
    expect(md).toContain("## Units & limitations");
    expect(md).toContain(UNITS_NOTE);
    expect(md.trimEnd().endsWith(baseReport.disclaimer)).toBe(true);
  });

  it("skips empty sections", () => {
    const bare: ExportReport = {
      ...baseReport,
      displayTime: undefined,
      reach: [],
      notes: [],
      yieldPolicy: undefined,
    };
    const md = reportMarkdown(bare);
    expect(md).not.toContain("## Notes");
    expect(md).not.toContain("Max reach from GZ");
    expect(md).not.toContain("Contours shown at");
    // ...but never the parts that carry the caveats.
    expect(md).toContain(UNITS_NOTE);
    expect(md).toContain(bare.disclaimer);
  });

  it("falls back to a generic caption when the mode didn't set one", () => {
    const md = reportMarkdown({ ...baseReport, reachCaption: undefined });
    expect(md).toContain("## Contour reach");
  });
});
