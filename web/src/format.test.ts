import { describe, expect, it } from "vitest";

import { describeAge, fmtNum, formatHours } from "./format";

describe("fmtNum", () => {
  it("drops decimals once the magnitude makes them false precision", () => {
    expect(fmtNum(1234.5)).toBe("1235");
    expect(fmtNum(100)).toBe("100");
    expect(fmtNum(99.94)).toBe("99.9");
    expect(fmtNum(10)).toBe("10.0");
  });

  it("keeps two significant figures down to 0.01", () => {
    expect(fmtNum(9.87)).toBe("9.9");
    expect(fmtNum(0.456)).toBe("0.46");
    expect(fmtNum(0.01)).toBe("0.010");
  });

  it("goes exponential below 0.01 rather than showing 0.00", () => {
    // Dose rates far downwind land here; rounding them to "0.00" would read as
    // "nothing", which is a different claim from "very small".
    expect(fmtNum(0.004)).toBe("4.0e-3");
    expect(fmtNum(1e-7)).toBe("1.0e-7");
  });

  it("shows an exact zero as plain 0", () => {
    expect(fmtNum(0)).toBe("0");
  });
});

describe("formatHours", () => {
  it("labels the first two days in hours", () => {
    expect(formatHours(1)).toBe("H+1.0h");
    expect(formatHours(6.25)).toBe("H+6.3h");
    expect(formatHours(47.9)).toBe("H+47.9h");
  });

  it("switches to days at H+48", () => {
    expect(formatHours(48)).toBe("H+2.0d");
    expect(formatHours(168)).toBe("H+7.0d");
  });
});

describe("describeAge", () => {
  it("calls a fresh fetch 'just now'", () => {
    expect(describeAge(0)).toBe("just now");
    expect(describeAge(89)).toBe("just now");
  });

  it("reports minutes up to an hour and a half", () => {
    expect(describeAge(90)).toBe("2 min ago");
    expect(describeAge(600)).toBe("10 min ago");
    expect(describeAge(60 * 89)).toBe("89 min ago");
  });

  it("switches to hours beyond that", () => {
    expect(describeAge(60 * 90)).toBe("1.5 h ago");
    expect(describeAge(3600 * 6)).toBe("6.0 h ago");
  });
});
