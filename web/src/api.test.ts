import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchExchangeEnvelope,
  fetchPlume,
  fetchTargets,
  geocodePlace,
  geocodeZip,
} from "./api";

// The client is thin by design, so what's worth testing is exactly the part
// that isn't: which URL/method/body each call produces, and that a non-ok
// response becomes an ApiError carrying the server's detail (the UI shows that
// text, so losing it means the user sees a bare status code).

const jsonOk = (body: unknown) =>
  ({ ok: true, status: 200, json: async () => body }) as unknown as Response;

const httpError = (status: number, detail: string) =>
  ({
    ok: false,
    status,
    statusText: "error",
    text: async () => detail,
    json: async () => ({}),
  }) as unknown as Response;

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The [url, init] of the nth fetch call. */
const call = (n = 0): [string, RequestInit | undefined] => fetchMock.mock.calls[n] as never;

describe("postJson-backed endpoints", () => {
  it("POSTs JSON to the configured API base", async () => {
    fetchMock.mockResolvedValue(jsonOk({ tier_used: 0 }));
    await fetchPlume({ lat: 38, lon: -77, yield_mt: 0.3, fission_fraction: 0.5 });

    const [url, init] = call();
    expect(url).toBe(`${__API_URL__}/plume`);
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init?.body as string)).toEqual({
      lat: 38,
      lon: -77,
      yield_mt: 0.3,
      fission_fraction: 0.5,
    });
  });

  it("keeps the server's error detail in the thrown ApiError", async () => {
    // A 422 from the API's Query()/schema validation carries the human-readable
    // reason; the compute path surfaces `err.message` verbatim.
    fetchMock.mockResolvedValue(httpError(422, "lat must be between -90 and 90"));
    await expect(fetchPlume({ lat: 999, lon: -77, yield_mt: 1, fission_fraction: 0.5 })).rejects.toThrow(
      ApiError,
    );
    await expect(
      fetchPlume({ lat: 999, lon: -77, yield_mt: 1, fission_fraction: 0.5 }),
    ).rejects.toThrow(/422.*lat must be between/);
  });
});

describe("fetchTargets", () => {
  it("omits the query string unless the expanded deck was asked for", async () => {
    fetchMock.mockResolvedValue(jsonOk([]));
    await fetchTargets();
    expect(call()[0]).toBe(`${__API_URL__}/targets`);

    await fetchTargets(true);
    expect(call(1)[0]).toBe(`${__API_URL__}/targets?expanded=true`);
  });

  it("raises on a non-ok response", async () => {
    fetchMock.mockResolvedValue(httpError(500, "boom"));
    await expect(fetchTargets()).rejects.toThrow(ApiError);
  });
});

describe("fetchExchangeEnvelope", () => {
  it("sends the aggregation policy and no body by default", async () => {
    fetchMock.mockResolvedValue(jsonOk({ n_targets: 600 }));
    await fetchExchangeEnvelope();

    const [url, init] = call();
    expect(url).toBe(`${__API_URL__}/exchange/envelope?aggregation=max_single_source`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
    expect(init?.headers).toBeUndefined();
  });

  it("passes aggregation=sum through", async () => {
    fetchMock.mockResolvedValue(jsonOk({}));
    await fetchExchangeEnvelope("sum");
    expect(call()[0]).toContain("aggregation=sum");
  });

  it("adds force_refresh only when asked (it busts the server wind cache)", async () => {
    fetchMock.mockResolvedValue(jsonOk({}));
    await fetchExchangeEnvelope("max_single_source", true);
    expect(call()[0]).toContain("force_refresh=true");
  });

  it("sends the dense level set as a JSON body when one is given", async () => {
    // This is what lets the decay slider relabel the envelope client-side;
    // dropping the body silently falls back to the API's four default bands.
    fetchMock.mockResolvedValue(jsonOk({}));
    await fetchExchangeEnvelope("max_single_source", false, [1, 10, 100]);

    const [, init] = call();
    expect(init?.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init?.body as string)).toEqual({ levels_rhr: [1, 10, 100] });
  });

  it("keeps the server detail on failure", async () => {
    fetchMock.mockResolvedValue(httpError(503, "wind fetch failed"));
    await expect(fetchExchangeEnvelope()).rejects.toThrow(/503.*wind fetch failed/);
  });
});

describe("geocodeZip", () => {
  const zipBody = {
    places: [{ latitude: "41.4993", longitude: "-81.6944", "place name": "Cleveland", "state abbreviation": "OH" }],
  };

  it("returns numeric coordinates and a display place", async () => {
    fetchMock.mockResolvedValue(jsonOk(zipBody));
    const loc = await geocodeZip("44113");

    expect(call()[0]).toBe("https://api.zippopotam.us/us/44113");
    expect(loc).toEqual({ lat: 41.4993, lon: -81.6944, place: "Cleveland, OH" });
  });

  it("reports an unknown ZIP as not found, not as an HTTP error", async () => {
    fetchMock.mockResolvedValue(httpError(404, ""));
    await expect(geocodeZip("00000")).rejects.toThrow('ZIP 00000 not found');
  });

  it("treats an empty places array as not found", async () => {
    fetchMock.mockResolvedValue(jsonOk({ places: [] }));
    await expect(geocodeZip("44113")).rejects.toThrow("not found");
  });

  it("surfaces other HTTP failures with their status", async () => {
    fetchMock.mockResolvedValue(httpError(500, ""));
    await expect(geocodeZip("44113")).rejects.toThrow("ZIP lookup HTTP 500");
  });
});

describe("geocodePlace", () => {
  it("asks Nominatim for a single best match", async () => {
    fetchMock.mockResolvedValue(
      jsonOk([{ lat: "21.3649", lon: "-157.9507", display_name: "Pearl Harbor, Honolulu, Hawaii" }]),
    );
    const loc = await geocodePlace("Pearl Harbor");

    const url = new URL(call()[0]);
    expect(url.origin + url.pathname).toBe("https://nominatim.openstreetmap.org/search");
    expect(url.searchParams.get("q")).toBe("Pearl Harbor");
    expect(url.searchParams.get("limit")).toBe("1");
    expect(url.searchParams.get("format")).toBe("jsonv2");
    expect(loc).toEqual({ lat: 21.3649, lon: -157.9507, place: "Pearl Harbor, Honolulu, Hawaii" });
  });

  it("escapes the query rather than pasting it into the URL", async () => {
    fetchMock.mockResolvedValue(jsonOk([{ lat: "0", lon: "0", display_name: "x" }]));
    await geocodePlace("100 N Main St, Ada & Sons");
    expect(new URL(call()[0]).searchParams.get("q")).toBe("100 N Main St, Ada & Sons");
  });

  it("names the query when nothing matches", async () => {
    fetchMock.mockResolvedValue(jsonOk([]));
    await expect(geocodePlace("nowhere at all")).rejects.toThrow('No match for "nowhere at all"');
  });
});
