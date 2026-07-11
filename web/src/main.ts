import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";

import {
  fetchPlume,
  fetchExchangeEnvelope,
  fetchTargets,
  geocodeZip,
  ApiError,
  type PlumeResponse,
  type GeoJsonFeatureCollection,
} from "./api";
import { fetchLevelSet, levelsForTime, TIME_MIN_HOURS, TIME_MAX_HOURS } from "./decay";

// Free, keyless vector basemap (openfreemap.org) -- no API key/signup needed,
// which matters for a project meant to run out of the box.
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

const SLIDER_STEPS = 1000;

// Fixed color per civil-defense dose-rate band, brightest/most alarming for
// the highest band. RGBA, deck.gl convention.
const LEVEL_COLORS: Record<number, [number, number, number, number]> = {
  1: [255, 221, 87, 200],
  10: [255, 152, 0, 210],
  100: [230, 74, 25, 220],
  1000: [136, 14, 14, 230],
};

const form = document.getElementById("plume-form") as HTMLFormElement;
const latInput = document.getElementById("lat") as HTMLInputElement;
const lonInput = document.getElementById("lon") as HTMLInputElement;
const zipInput = document.getElementById("zip") as HTMLInputElement;
const zipLookupBtn = document.getElementById("zip-lookup-btn") as HTMLButtonElement;
const exchangeModeCheckbox = document.getElementById("exchange-mode") as HTMLInputElement;
const singleTargetFields = document.getElementById("single-target-fields") as HTMLElement;
const yieldInput = document.getElementById("yield_mt") as HTMLInputElement;
const ffInput = document.getElementById("fission_fraction") as HTMLInputElement;
const computeBtn = document.getElementById("compute-btn") as HTMLButtonElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const timeControl = document.getElementById("time-control") as HTMLElement;
const timeSlider = document.getElementById("time-slider") as HTMLInputElement;
const timeLabel = document.getElementById("time-label") as HTMLSpanElement;
const legendEl = document.getElementById("legend") as HTMLDivElement;
const exportBtn = document.getElementById("export-btn") as HTMLButtonElement;
const notesEl = document.getElementById("notes") as HTMLDivElement;
const disclaimerEl = document.getElementById("disclaimer") as HTMLDivElement;

timeSlider.max = String(SLIDER_STEPS);

const map = new maplibregl.Map({
  container: "map",
  style: BASEMAP_STYLE,
  center: [-98.5, 39.8], // CONUS centroid-ish
  zoom: 3.3,
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

// MapLibre's own `trackResize` only listens for window "resize" events, so a
// container that reaches its final flexbox-computed size without the window
// itself resizing (e.g. sidebar content changing height on load) leaves the
// canvas stuck at its construction-time size -- verified live: the canvas
// stayed at a 400x300 fallback while its #map container was correctly
// 960x684. A ResizeObserver catches container-size changes a window resize
// listener alone would miss.
new ResizeObserver(() => map.resize()).observe(document.getElementById("map") as HTMLElement);

let overlay: MapboxOverlay;
let gzMarker: maplibregl.Marker | null = null;
let currentPlume: PlumeResponse | null = null;

// `overlay` (and anything that calls its `setProps`) isn't ready until this
// fires, which can take a moment on a slow connection -- computePlume/
// computeExchangeEnvelope await this before touching it, rather than
// assuming the map has finished loading by the time the user hits Compute.
const mapReady: Promise<void> = new Promise((resolve) => {
  map.on("load", () => {
    overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    resolve();
  });
});

// A bare `await mapReady` would hang the "Computing..." status forever if
// the basemap's tiles never finish loading (slow/blocked network) -- fail
// loudly after a timeout instead of leaving the user with no feedback.
function ensureMapReady(): Promise<void> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(
      () => reject(new ApiError("Map tiles never finished loading. Check your connection and reload.")),
      15000,
    ),
  );
  return Promise.race([mapReady, timeout]);
}

// Click the map to set ground zero -- friendlier than typing coordinates.
// No-op in exchange mode: there's no single ground zero to set (the
// envelope covers all public targets at once).
map.on("click", (e) => {
  if (exchangeModeCheckbox.checked) return;
  latInput.value = e.lngLat.lat.toFixed(4);
  lonInput.value = e.lngLat.lng.toFixed(4);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  await computePlume();
});

// --- ZIP code lookup ---------------------------------------------------------

zipLookupBtn.addEventListener("click", () => void lookupZip());
zipInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    void lookupZip();
  }
});

async function lookupZip(): Promise<void> {
  const zip = zipInput.value.trim();
  if (!/^\d{5}$/.test(zip)) {
    statusEl.textContent = "Enter a 5-digit US ZIP code.";
    statusEl.classList.add("error");
    return;
  }
  zipLookupBtn.disabled = true;
  statusEl.textContent = `Looking up ZIP ${zip}...`;
  statusEl.classList.remove("error");
  try {
    const loc = await geocodeZip(zip);
    latInput.value = loc.lat.toFixed(4);
    lonInput.value = loc.lon.toFixed(4);
    map.flyTo({ center: [loc.lon, loc.lat], zoom: 8 });
    statusEl.textContent = `ZIP ${zip} -> ${loc.place} (${loc.lat.toFixed(3)}, ${loc.lon.toFixed(3)})`;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `ZIP lookup failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    zipLookupBtn.disabled = false;
  }
}

// --- full nuclear exchange toggle --------------------------------------------
// /exchange/envelope has no per-target lat/lon/tier -- it always runs Tier-0
// (WSEG-10) across the fixed public target set (see targets.py) and returns
// one composited CONUS grid. So single-target fields are hidden, not just
// ignored, while this is checked.

exchangeModeCheckbox.addEventListener("change", () => {
  singleTargetFields.hidden = exchangeModeCheckbox.checked;
  computeBtn.textContent = exchangeModeCheckbox.checked
    ? "Compute national envelope"
    : "Compute plume";
  statusEl.textContent = "";
  statusEl.classList.remove("error");
  timeControl.hidden = true;
  exportBtn.hidden = true;
  overlay?.setProps({ layers: [] });
  currentPlume = null;
  exportGeoJson = null;
  notesEl.innerHTML = "";
  legendEl.innerHTML = "";
  if (exchangeModeCheckbox.checked) {
    clearGzMarker();
  } else {
    clearTargetMarkers();
  }
});

async function computePlume(): Promise<void> {
  if (exchangeModeCheckbox.checked) {
    await computeExchangeEnvelope();
  } else {
    await computeSinglePlume();
  }
}

async function computeSinglePlume(): Promise<void> {
  computeBtn.disabled = true;
  statusEl.textContent = "Computing (fetches live wind)...";
  statusEl.classList.remove("error");
  timeControl.hidden = true;
  exportBtn.hidden = true;

  const tierInput = form.querySelector<HTMLInputElement>('input[name="tier"]:checked');
  const tier = tierInput ? (Number(tierInput.value) as 0 | 1) : 0;

  try {
    await ensureMapReady();
    const resp = await fetchPlume({
      lat: Number(latInput.value),
      lon: Number(lonInput.value),
      yield_mt: Number(yieldInput.value),
      fission_fraction: Number(ffInput.value),
      tier,
      levels_rhr: fetchLevelSet(),
    });
    currentPlume = resp;
    disclaimerEl.textContent = resp.disclaimer;
    placeGzMarker(resp.ground_zero[1], resp.ground_zero[0]);
    map.flyTo({ center: resp.ground_zero, zoom: 6 });

    statusEl.textContent = `Tier ${resp.tier_used} used. Wind: ${describeWind(resp)}`;
    renderNotes(resp);
    timeControl.hidden = false;
    exportBtn.hidden = false;
    timeSlider.value = "0";
    renderAtCurrentTime();
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `Failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    computeBtn.disabled = false;
  }
}

async function computeExchangeEnvelope(): Promise<void> {
  computeBtn.disabled = true;
  statusEl.textContent = "Computing national max-envelope (fetches live wind for all targets)...";
  statusEl.classList.remove("error");
  timeControl.hidden = true; // envelope has no dense level set -- no decay slider
  exportBtn.hidden = true;
  clearGzMarker();
  currentPlume = null;

  try {
    await ensureMapReady();
    const resp = await fetchExchangeEnvelope({
      yield_mt: Number(yieldInput.value),
      fission_fraction: Number(ffInput.value),
    });
    disclaimerEl.textContent = resp.disclaimer;
    await plotTargetMarkers();
    map.flyTo({ center: [-98.5, 39.8], zoom: 3.3 });

    statusEl.textContent = `Envelope computed across ${resp.n_targets} target(s).`;
    renderPlainNotes(resp.notes);
    renderStaticContours(resp.contours);
    exportGeoJson = resp.contours;
    exportBtn.hidden = false;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `Failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    computeBtn.disabled = false;
  }
}

function describeWind(resp: PlumeResponse): string {
  const w = resp.wind;
  if (w.speed_mph == null) return w.source;
  return `${w.speed_mph.toFixed(0)} mph @ ${w.bearing_deg?.toFixed(0)}° (${w.source})`;
}

function renderNotes(resp: PlumeResponse): void {
  notesEl.innerHTML = "";
  const allNotes = [...resp.notes];
  if (resp.fraction_aloft != null && resp.fraction_aloft > 0.01) {
    allNotes.push(
      `${(resp.fraction_aloft * 100).toFixed(0)}% of activity carried past the local footprint (regional/global).`,
    );
  }
  for (const note of allNotes) {
    const p = document.createElement("p");
    p.textContent = note;
    notesEl.appendChild(p);
  }
}

function renderPlainNotes(notes: string[]): void {
  notesEl.innerHTML = "";
  for (const note of notes) {
    const p = document.createElement("p");
    p.textContent = note;
    notesEl.appendChild(p);
  }
}

function placeGzMarker(lat: number, lon: number): void {
  clearGzMarker();
  gzMarker = new maplibregl.Marker({ color: "#7a1f1f" }).setLngLat([lon, lat]).setPopup(
    new maplibregl.Popup().setText("Ground zero"),
  ).addTo(map);
}

function clearGzMarker(): void {
  if (gzMarker) {
    gzMarker.remove();
    gzMarker = null;
  }
}

// --- full nuclear exchange: target markers + static contours -----------------

let targetMarkers: maplibregl.Marker[] = [];

async function plotTargetMarkers(): Promise<void> {
  clearTargetMarkers();
  const targets = await fetchTargets();
  for (const t of targets) {
    const marker = new maplibregl.Marker({ color: "#7a1f1f", scale: 0.7 })
      .setLngLat([t.lon, t.lat])
      .setPopup(new maplibregl.Popup().setText(`${t.name} (${t.category})`))
      .addTo(map);
    targetMarkers.push(marker);
  }
}

function clearTargetMarkers(): void {
  for (const marker of targetMarkers) marker.remove();
  targetMarkers = [];
}

// Exchange-envelope contours have no per-target ground zero or decay-time
// slider to drive (see the comment on the exchange-mode toggle above) --
// just render the fixed H+1 dose-rate levels the API returns.
function renderStaticContours(fc: GeoJsonFeatureCollection): void {
  overlay.setProps({
    layers: [
      new GeoJsonLayer({
        id: "contours",
        data: fc as unknown as GeoJSON.FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: (f: any) => LEVEL_COLORS[f.properties.dose_rate_h1_rhr] ?? [255, 255, 255, 200],
        getLineWidth: 3,
        lineWidthUnits: "pixels",
        pickable: true,
      }),
    ],
  });
  renderLegend(fc.features.map((f) => f.properties.dose_rate_h1_rhr).sort((a, b) => a - b));
}

// --- decay-time slider ------------------------------------------------------

function sliderToHours(step: number): number {
  const t = step / SLIDER_STEPS;
  const logMin = Math.log(TIME_MIN_HOURS);
  const logMax = Math.log(TIME_MAX_HOURS);
  return Math.exp(logMin + t * (logMax - logMin));
}

timeSlider.addEventListener("input", renderAtCurrentTime);

function renderAtCurrentTime(): void {
  if (!currentPlume) return;
  const hours = sliderToHours(Number(timeSlider.value));
  timeLabel.textContent = formatHours(hours);

  const picks = levelsForTime(hours, availableLevels(currentPlume.contours));

  const features = currentPlume.contours.features
    .map((f) => {
      const pick = picks.find((p) => p.h1Level === f.properties.dose_rate_h1_rhr);
      if (!pick) return null;
      return {
        ...f,
        properties: { ...f.properties, display_level_rhr: pick.displayLevel },
      };
    })
    .filter((f): f is NonNullable<typeof f> => f !== null);

  const displayed: GeoJsonFeatureCollection = { type: "FeatureCollection", features };

  overlay.setProps({
    layers: [
      new GeoJsonLayer({
        id: "contours",
        // deck.gl's `data` prop type is a large union (including Promise
        // variants) that TS can't structurally match against our plain
        // FeatureCollection interface even though the shape is correct at
        // runtime -- a cast here is the standard workaround.
        data: displayed as unknown as GeoJSON.FeatureCollection,
        stroked: true,
        filled: false,
        getLineColor: (f: any) => LEVEL_COLORS[f.properties.display_level_rhr] ?? [255, 255, 255, 200],
        getLineWidth: 3,
        lineWidthUnits: "pixels",
        pickable: true,
      }),
    ],
  });

  renderLegend(picks.map((p) => p.displayLevel));
  exportGeoJson = displayed;
}

function availableLevels(fc: GeoJsonFeatureCollection): number[] {
  return fc.features.map((f) => f.properties.dose_rate_h1_rhr).sort((a, b) => a - b);
}

function renderLegend(levels: number[]): void {
  legendEl.innerHTML = "";
  for (const level of levels) {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    const [r, g, b] = LEVEL_COLORS[level] ?? [255, 255, 255, 200];
    swatch.style.background = `rgb(${r},${g},${b})`;
    row.appendChild(swatch);
    const label = document.createElement("span");
    label.textContent = `${level} R/hr`;
    row.appendChild(label);
    legendEl.appendChild(row);
  }
}

function formatHours(hours: number): string {
  if (hours < 48) return `H+${hours.toFixed(1)}h`;
  return `H+${(hours / 24).toFixed(1)}d`;
}

// --- GeoJSON export ----------------------------------------------------------

let exportGeoJson: GeoJsonFeatureCollection | null = null;

exportBtn.addEventListener("click", () => {
  if (!exportGeoJson) return;
  const blob = new Blob([JSON.stringify(exportGeoJson, null, 2)], {
    type: "application/geo+json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "falloutcast-contours.geojson";
  a.click();
  URL.revokeObjectURL(url);
});

// --- disclaimer --------------------------------------------------------------
// Shown immediately with the static text, then replaced with the API's own
// disclaimer string once a plume has actually been computed -- the API's
// text is the source of truth, this is just a sane default before any
// request has been made.
disclaimerEl.textContent =
  "Planning estimate only, not an operational product. Do not use for real-world decisions.";
