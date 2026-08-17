import { describe, expect, it } from "vitest";

import {
  DECAY_EXPONENT,
  DISPLAY_LEVELS_RHR,
  ENVELOPE_TIME_MAX_HOURS,
  TIME_MAX_HOURS,
  fetchLevelSet,
  levelsForTime,
} from "./decay";

// Half a grid step in log space -- the tolerance decay.ts's nearest() allows
// between a display band's required H+1 level and the grid point it snaps to.
// Recomputed here from the module's own contract (16 levels per decade) rather
// than imported, so a change to the spacing has to be a deliberate one.
const HALF_STEP_LOG = (Math.LN10 / 16) * 0.5;

const requiredH1 = (displayLevel: number, hours: number): number =>
  displayLevel * Math.pow(hours, DECAY_EXPONENT);

describe("fetchLevelSet", () => {
  it("is ascending and starts at 1 R/hr", () => {
    const levels = fetchLevelSet();
    expect(levels[0]).toBeCloseTo(1, 12);
    for (let i = 1; i < levels.length; i++) {
      expect(levels[i]).toBeGreaterThan(levels[i - 1]);
    }
  });

  it("puts every display band exactly on a grid point (the anchoring fix)", () => {
    // The regression this guards: an unanchored 1e-3..1e7 ramp landed the
    // "100 R/hr" band on the 86.4 R/hr contour, so the default H+1 view was
    // mislabeled by ~15%.
    const levels = fetchLevelSet();
    for (const band of DISPLAY_LEVELS_RHR) {
      const hit = levels.find((l) => Math.abs(l - band) < band * 1e-9);
      expect(hit, `no exact grid point for the ${band} R/hr band`).toBeDefined();
    }
  });

  it("spans the whole slider range: the largest band at the latest time", () => {
    const levels = fetchLevelSet();
    const top = requiredH1(DISPLAY_LEVELS_RHR[DISPLAY_LEVELS_RHR.length - 1], TIME_MAX_HOURS);
    expect(levels[levels.length - 1]).toBeGreaterThanOrEqual(top);
  });

  it("requests fewer levels for the envelope's shorter H+24 range", () => {
    // Payload size is the point: the envelope grid is ~480k cells, so every
    // level that can never be displayed is wasted contouring work.
    expect(fetchLevelSet(ENVELOPE_TIME_MAX_HOURS).length).toBeLessThan(fetchLevelSet().length);
    const envelope = fetchLevelSet(ENVELOPE_TIME_MAX_HOURS);
    const top = requiredH1(DISPLAY_LEVELS_RHR[DISPLAY_LEVELS_RHR.length - 1], ENVELOPE_TIME_MAX_HOURS);
    expect(envelope[envelope.length - 1]).toBeGreaterThanOrEqual(top);
  });
});

describe("levelsForTime", () => {
  const available = fetchLevelSet();

  it("relabels H+1 to itself", () => {
    const picks = levelsForTime(1, available);
    expect(picks.map((p) => p.displayLevel)).toEqual([...DISPLAY_LEVELS_RHR]);
    for (const p of picks) expect(p.h1Level).toBeCloseTo(p.displayLevel, 9);
  });

  it("snaps each band to the grid point for L * t^1.2", () => {
    for (const hours of [1.5, 6, 24, 168]) {
      for (const { displayLevel, h1Level } of levelsForTime(hours, available)) {
        const want = requiredH1(displayLevel, hours);
        expect(
          Math.abs(Math.log(h1Level) - Math.log(want)),
          `${displayLevel} R/hr at H+${hours} snapped to ${h1Level}, wanted ~${want}`,
        ).toBeLessThanOrEqual(HALF_STEP_LOG * 1.02);
      }
    }
  });

  it("moves each band to a higher H+1 level as time advances", () => {
    // Later time -> the same displayed dose rate corresponds to a hotter H+1
    // contour, i.e. a smaller footprint. Sanity check on the direction of the
    // t^-1.2 relabel; getting the sign wrong would make plumes grow with time.
    const at1 = levelsForTime(1, available);
    const at12 = levelsForTime(12, available);
    for (const band of DISPLAY_LEVELS_RHR) {
      const a = at1.find((p) => p.displayLevel === band);
      const b = at12.find((p) => p.displayLevel === band);
      if (a && b) expect(b.h1Level).toBeGreaterThan(a.h1Level);
    }
  });

  it("omits bands this plume never produced instead of approximating them", () => {
    // A plume peaking near 490 R/hr has no 1000 R/hr zone; drawing its 490
    // contour labelled "1000 R/hr" would overstate the hazard 2x.
    const capped = available.filter((l) => l <= 490);
    const picks = levelsForTime(1, capped);
    expect(picks.map((p) => p.displayLevel)).toEqual([1, 10, 100]);
  });

  it("returns nothing when no contours are available at all", () => {
    expect(levelsForTime(1, [])).toEqual([]);
  });

  it("omits every band once the required level runs off the top of the set", () => {
    const available24 = fetchLevelSet(ENVELOPE_TIME_MAX_HOURS);
    // Well past what the envelope's level set covers: the highest band's
    // required H+1 level is off the end, so it must drop out rather than snap
    // back to the top contour.
    const far = levelsForTime(TIME_MAX_HOURS, available24);
    expect(far.map((p) => p.displayLevel)).not.toContain(1000);
  });
});
