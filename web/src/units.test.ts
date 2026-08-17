import { beforeEach, describe, expect, it } from "vitest";

import type { WindProfilePoint } from "./api";
import {
  KM_PER_MI,
  fmtDist,
  fmtDose,
  formatHeightShort,
  formatReach,
  formatSpeed,
  formatSpeedShort,
  getUnitSystem,
  setUnitSystem,
  svApprox,
} from "./units";

// The preference is module state, so every test starts from a known one.
beforeEach(() => setUnitSystem("metric"));

const profilePoint = (over: Partial<WindProfilePoint> = {}): WindProfilePoint => ({
  height_m: 3048,
  height_kft: 10,
  speed_mph: 30,
  from_deg: 270,
  toward_deg: 90,
  in_fallout_layer: true,
  ...over,
});

describe("the preference itself", () => {
  it("defaults to metric and switches", () => {
    expect(getUnitSystem()).toBe("metric");
    setUnitSystem("us");
    expect(getUnitSystem()).toBe("us");
  });
});

describe("formatReach", () => {
  it("always shows both units, and flips which one leads", () => {
    // The dual readout is deliberate: the model is US-unit native but the
    // audience isn't, and a single-unit label invites misreading by 1.6x.
    expect(formatReach(100)).toBe("100 km (62 mi)");
    setUnitSystem("us");
    expect(formatReach(100)).toBe("62 mi (100 km)");
  });

  it("quotes the same physical distance in both modes", () => {
    const metric = formatReach(42);
    setUnitSystem("us");
    const us = formatReach(42);
    const nums = (s: string) => s.match(/[\d.]+/g)!;
    expect(nums(metric)).toEqual(nums(us).reverse());
  });

  it("keeps a decimal only below 10", () => {
    expect(fmtDist(9.94)).toBe("9.9");
    expect(fmtDist(10)).toBe("10");
    expect(formatReach(4)).toBe("4.0 km (2.5 mi)");
  });
});

describe("wind speed", () => {
  it("converts mph to km/h with the primary unit first", () => {
    expect(formatSpeed(100)).toBe(`${Math.round(100 * KM_PER_MI)} km/h (100 mph)`);
    expect(formatSpeed(20)).toBe("32 km/h (20 mph)");
    setUnitSystem("us");
    expect(formatSpeed(20)).toBe("20 mph (32 km/h)");
  });

  it("gives the wind-profile rows one unit only", () => {
    expect(formatSpeedShort(20)).toBe("32 km/h");
    setUnitSystem("us");
    expect(formatSpeedShort(20)).toBe("20 mph");
  });
});

describe("formatHeightShort", () => {
  it("shows km in metric and kft in US, from the two fields the API sends", () => {
    expect(formatHeightShort(profilePoint())).toBe("3.0 km");
    setUnitSystem("us");
    expect(formatHeightShort(profilePoint())).toBe("10 kft");
  });
});

describe("svApprox", () => {
  it("scales roentgen to mSv and rolls over to Sv at 1000 mSv", () => {
    expect(svApprox(0.05)).toBe("0.5 mSv");
    expect(svApprox(5)).toBe("50 mSv");
    expect(svApprox(99)).toBe("990 mSv");
    expect(svApprox(100)).toBe("1.0 Sv");
    expect(svApprox(1000)).toBe("10 Sv");
  });
});

describe("fmtDose", () => {
  it("keeps R as the stated figure and adds Sv only as an approximation", () => {
    // The model computes roentgen; the Sv is a whole-body-gamma rule of thumb,
    // so it must never look like the primary, precise number.
    expect(fmtDose(450)).toBe("450 R (≈ 4.5 Sv)");
  });

  it("omits the Sv reference entirely in US mode", () => {
    setUnitSystem("us");
    expect(fmtDose(450)).toBe("450 R");
  });
});
