import { describe, expect, it } from "vitest";

import { buildUrlParams, parseUrlParams, type UrlState } from "./urlstate";

const roundTrip = (state: UrlState) => parseUrlParams(`?${buildUrlParams(state)}`);

const plume: UrlState = { mode: "plume", yieldMt: "0.3", ff: "0.5", lat: "41.14", lon: "-104.82" };

describe("buildUrlParams", () => {
  it("captures the single-plume scenario", () => {
    const params = buildUrlParams({ ...plume, tier: 1 });
    expect(params.get("mode")).toBe("plume");
    expect(params.get("yield_mt")).toBe("0.3");
    expect(params.get("ff")).toBe("0.5");
    expect(params.get("lat")).toBe("41.14");
    expect(params.get("lon")).toBe("-104.82");
    expect(params.get("tier")).toBe("1");
    expect(params.get("wind")).toBeNull(); // live wind: nothing to pin
  });

  it("defaults the tier rather than leaving it out", () => {
    // A link with no tier would reopen on whatever the form defaults to; the
    // point of the link is that it pins the scenario.
    expect(buildUrlParams(plume).get("tier")).toBe("0");
  });

  it("packs manual wind into one speed,bearing,shear param", () => {
    const params = buildUrlParams({ ...plume, wind: { speed: 25, bearing: 270, shear: 3 } });
    expect(params.get("wind")).toBe("25,270,3");
  });

  it("omits lat/lon for the national envelope, which has no single GZ", () => {
    const params = buildUrlParams({ mode: "exchange", yieldMt: "0.3", ff: "0.5", lat: "41", lon: "-104" });
    expect(params.get("lat")).toBeNull();
    expect(params.get("lon")).toBeNull();
    expect(params.get("tier")).toBeNull();
  });

  it("carries the ensemble's level and member count", () => {
    const params = buildUrlParams({ ...plume, mode: "ensemble", level: "10", members: "20" });
    expect(params.get("level")).toBe("10");
    expect(params.get("members")).toBe("20");
    expect(params.get("tier")).toBeNull(); // tier is a plume-only choice
  });
});

describe("round trip", () => {
  it("restores a live-wind plume", () => {
    expect(roundTrip({ ...plume, tier: 0 })).toEqual({
      mode: "plume",
      yieldMt: "0.3",
      ff: "0.5",
      lat: "41.14",
      lon: "-104.82",
      tier: 0,
    });
  });

  it("restores a manual-wind Tier-1 plume", () => {
    const state: UrlState = { ...plume, tier: 1, wind: { speed: 25, bearing: 270, shear: 3 } };
    expect(roundTrip(state)).toEqual({
      mode: "plume",
      yieldMt: "0.3",
      ff: "0.5",
      lat: "41.14",
      lon: "-104.82",
      tier: 1,
      wind: { speed: 25, bearing: 270, shear: 3 },
    });
  });

  it("restores an ensemble run", () => {
    expect(roundTrip({ ...plume, mode: "ensemble", level: "10", members: "20" })).toEqual({
      mode: "ensemble",
      yieldMt: "0.3",
      ff: "0.5",
      lat: "41.14",
      lon: "-104.82",
      level: "10",
      members: "20",
    });
  });

  it("restores the envelope", () => {
    expect(roundTrip({ mode: "exchange", yieldMt: "0.3", ff: "0.5" })).toEqual({
      mode: "exchange",
      yieldMt: "0.3",
      ff: "0.5",
    });
  });

  it("keeps the user's own number formatting and a negative longitude", () => {
    const state: UrlState = { ...plume, yieldMt: "0.30", lat: "-41.1400", lon: "-104.8200" };
    const back = roundTrip(state)!;
    expect(back.yieldMt).toBe("0.30");
    expect(back.lat).toBe("-41.1400");
    expect(back.lon).toBe("-104.8200");
  });
});

describe("parseUrlParams", () => {
  it("returns null for a URL with no scenario, so defaults stand", () => {
    expect(parseUrlParams("")).toBeNull();
    expect(parseUrlParams("?foo=bar")).toBeNull();
  });

  it("rejects an unknown mode instead of half-applying the link", () => {
    expect(parseUrlParams("?mode=banana&yield_mt=0.3")).toBeNull();
  });

  it("drops non-numeric and empty values rather than writing NaN into the form", () => {
    const state = parseUrlParams("?mode=plume&yield_mt=abc&ff=&lat=41.14&lon=-104.82")!;
    expect(state.yieldMt).toBeUndefined();
    expect(state.ff).toBeUndefined();
    expect(state.lat).toBe("41.14");
  });

  it("ignores a tier that isn't 0 or 1", () => {
    expect(parseUrlParams("?mode=plume&tier=7")!.tier).toBeUndefined();
    expect(parseUrlParams("?mode=plume&tier=1")!.tier).toBe(1);
  });

  it("takes manual wind all-or-nothing", () => {
    // A partial triple would blend a shared wind with whatever the form held,
    // producing a scenario that matches neither.
    expect(parseUrlParams("?mode=plume&wind=25,270")!.wind).toBeUndefined();
    expect(parseUrlParams("?mode=plume&wind=25,west,3")!.wind).toBeUndefined();
    expect(parseUrlParams("?mode=plume&wind=25,270,3")!.wind).toEqual({
      speed: 25,
      bearing: 270,
      shear: 3,
    });
  });

  it("ignores plume-only params on an envelope link", () => {
    const state = parseUrlParams("?mode=exchange&yield_mt=0.3&ff=0.5&lat=41&tier=1&wind=25,270,3")!;
    expect(state.lat).toBeUndefined();
    expect(state.tier).toBeUndefined();
    expect(state.wind).toBeUndefined();
  });
});
