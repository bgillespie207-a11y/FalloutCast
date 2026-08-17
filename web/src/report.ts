// The self-describing report that accompanies every result (backlog #23).
//
// Two renderings of one object: a structured `metadata` member embedded in the
// exported GeoJSON, and a human-readable Markdown file. Both exist so an
// exported plume can't circulate as a bare set of polygons -- the assumptions,
// versions, units, and disclaimer travel with it.

import type { WeatherProvenance, YieldPolicy } from "./api";
import { describeAge } from "./format";
import { compassName } from "./geo";
import { formatReach } from "./units";

export interface ReachRow {
  label: string;
  km: number;
  bearingDeg: number;
}

export interface ExportReport {
  mode: "plume" | "ensemble" | "exchange";
  title: string;
  generatedIso: string;
  facts: [string, string][]; // ordered label/value assumption pairs
  displayTime?: string; // plume: the decay time the exported contours are at
  reachCaption?: string;
  reach?: ReachRow[];
  yieldPolicy?: YieldPolicy; // envelope: per-class attacker yields
  notes: string[];
  disclaimer: string;
}

export const UNITS_NOTE =
  "Units: distances shown in both km and mi; dose rate in R/hr (roentgen/hour, " +
  "~rem/hr whole-body); accumulated dose in R (1 R ≈ 10 mSv effective, whole-body " +
  "gamma); times are hours after burst (H+1 = one hour after detonation).";

const MI_PER_KM = 0.621371; // the metadata carries both figures, unformatted

/** Ground zero is carried as GeoJSON [lon, lat]; humans read lat, lon. */
export function fmtLonLat(gz: [number, number]): string {
  return `${gz[1].toFixed(4)}, ${gz[0].toFixed(4)} (lat, lon)`;
}

export function weatherFactStr(w: WeatherProvenance): string {
  const age = w.age_seconds != null ? `, fetched ${describeAge(w.age_seconds)}` : "";
  return `${w.model}, valid ${w.valid_time}Z${age}`;
}

export function round1(v: number): number {
  return Math.round(v * 10) / 10;
}

/** Structured, self-describing metadata block embedded in the exported GeoJSON. */
export function exportMetadata(r: ExportReport): Record<string, unknown> {
  return {
    generated: r.generatedIso,
    app: `FalloutCast ${__APP_VERSION__}`,
    api_url: __API_URL__,
    mode: r.mode,
    title: r.title,
    assumptions: Object.fromEntries(r.facts),
    ...(r.displayTime ? { display_time: r.displayTime } : {}),
    ...(r.reach
      ? {
          contour_reach: r.reach.map((x) => ({
            band: x.label,
            max_reach_km: round1(x.km),
            max_reach_mi: round1(x.km * MI_PER_KM),
            toward_deg: Math.round(x.bearingDeg),
            toward_compass: compassName(x.bearingDeg),
          })),
        }
      : {}),
    ...(r.yieldPolicy ? { yield_policy: r.yieldPolicy } : {}),
    notes: r.notes,
    units: UNITS_NOTE,
    disclaimer: r.disclaimer,
  };
}

export function reportMarkdown(r: ExportReport): string {
  const lines: string[] = [];
  lines.push(`# FalloutCast — ${r.title}`, "");
  lines.push(`_Planning estimate, not an operational product. Generated ${r.generatedIso}._`, "");
  lines.push(`**App:** FalloutCast ${__APP_VERSION__} · **API:** ${__API_URL__}`, "");
  // The contours are a decay-time slice, so the report has to say which one.
  // For a plume the time was only implicit in the reach caption; the envelope
  // has no reach table, so without this its time went unrecorded entirely.
  if (r.displayTime) {
    lines.push(`**Contours shown at:** ${r.displayTime} after burst`, "");
  }

  lines.push("## Inputs & assumptions", "");
  for (const [k, v] of r.facts) lines.push(`- **${k}:** ${v}`);
  lines.push("");

  if (r.reach && r.reach.length > 0) {
    lines.push(`## ${r.reachCaption ?? "Contour reach"}`, "");
    lines.push("| Band | Max reach from GZ | Toward |", "| --- | --- | --- |");
    for (const x of r.reach) {
      lines.push(
        `| ${x.label} | ${formatReach(x.km)} | ${compassName(x.bearingDeg)} (${Math.round(x.bearingDeg)}°) |`,
      );
    }
    lines.push("");
  }

  if (r.yieldPolicy?.assumptions?.length) {
    lines.push("## Attack-scenario yields (per target class)", "");
    lines.push(`Scenario: **${r.yieldPolicy.scenario}** (${r.yieldPolicy.mode}). Illustrative attacker assumptions, not the targets' own weapons.`, "");
    lines.push("| Class | Nominal | Range | Fission |", "| --- | --- | --- | --- |");
    for (const a of r.yieldPolicy.assumptions) {
      lines.push(
        `| ${a.category} | ${a.yield_mt} Mt | ${a.yield_min_mt}–${a.yield_max_mt} Mt | ${a.fission_fraction} |`,
      );
    }
    lines.push("", `_${r.yieldPolicy.surface_burst_caveat}_`, "");
  }

  if (r.notes.length > 0) {
    lines.push("## Notes", "");
    for (const n of r.notes) lines.push(`- ${n}`);
    lines.push("");
  }

  lines.push("## Units & limitations", "");
  lines.push(UNITS_NOTE, "");
  lines.push(r.disclaimer, "");
  return lines.join("\n");
}
