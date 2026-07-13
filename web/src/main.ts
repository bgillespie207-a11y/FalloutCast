import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";

import {
  fetchPlume,
  fetchExchangeEnvelope,
  fetchEnsemble,
  fetchTargets,
  geocodeZip,
  ApiError,
  type ManualWind,
  type PlumeResponse,
  type GeoJsonFeatureCollection,
  type Target,
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

// Ground-zero dot color per target category, for the full-exchange scatter
// layer. Counterforce (silos/LCC/military) in cool blues/greys, countervalue
// (population/industry/command) in warmer tones so the two kinds of target read
// apart at a glance. RGBA, deck.gl convention.
const TARGET_COLORS: Record<string, [number, number, number, number]> = {
  icbm_lf: [40, 90, 170, 200],       // launch facility (silo)
  icbm_lcc: [10, 40, 110, 230],      // launch control center
  bomber_base: [90, 60, 160, 220],
  ssbn_base: [0, 130, 150, 220],
  storage: [120, 120, 130, 220],
  command: [200, 40, 40, 235],       // government / C2
  city_population: [235, 130, 40, 220],
  industry: [180, 160, 40, 220],
};
const TARGET_COLOR_DEFAULT: [number, number, number, number] = [120, 120, 120, 200];

// Ensemble exceedance-probability bands. A cool sequential ramp, deliberately
// distinct from the warm dose-rate palette above so the two views never read as
// the same thing: the outer 10% band ("could reach") is faint, the inner 90%
// ("very likely") is saturated. RGBA, deck.gl convention.
const PROB_COLORS: Record<number, [number, number, number, number]> = {
  0.1: [140, 190, 225, 200],
  0.5: [60, 120, 200, 220],
  0.9: [30, 40, 130, 240],
};
const PROB_LABELS: Record<number, string> = {
  0.1: "10% — outer edge (could reach)",
  0.5: "50% — more likely than not",
  0.9: "90% — very likely",
};

// Human-readable labels for the target-category legend.
const TARGET_LABELS: Record<string, string> = {
  icbm_lf: "ICBM silo (LF)",
  icbm_lcc: "Launch control center",
  bomber_base: "Bomber base",
  ssbn_base: "SSBN base",
  storage: "Weapons storage",
  command: "Government / C2",
  city_population: "Population center",
  industry: "Industry / economic",
};

const form = document.getElementById("plume-form") as HTMLFormElement;
const latInput = document.getElementById("lat") as HTMLInputElement;
const lonInput = document.getElementById("lon") as HTMLInputElement;
const zipInput = document.getElementById("zip") as HTMLInputElement;
const zipLookupBtn = document.getElementById("zip-lookup-btn") as HTMLButtonElement;
const exchangeModeCheckbox = document.getElementById("exchange-mode") as HTMLInputElement;
const singleTargetFields = document.getElementById("single-target-fields") as HTMLElement;
const globalYieldFields = document.getElementById("global-yield-fields") as HTMLElement;
const perClassNote = document.getElementById("per-class-note") as HTMLElement;
const yieldInput = document.getElementById("yield_mt") as HTMLInputElement;
const ffInput = document.getElementById("fission_fraction") as HTMLInputElement;
const manualWindCheckbox = document.getElementById("manual-wind") as HTMLInputElement;
const manualWindFields = document.getElementById("manual-wind-fields") as HTMLElement;
const windSpeedInput = document.getElementById("wind_speed") as HTMLInputElement;
const windBearingInput = document.getElementById("wind_bearing") as HTMLInputElement;
const windShearInput = document.getElementById("wind_shear") as HTMLInputElement;
const ensembleModeCheckbox = document.getElementById("ensemble-mode") as HTMLInputElement;
const ensembleFields = document.getElementById("ensemble-fields") as HTMLElement;
const ensembleLevelInput = document.getElementById("ensemble-level") as HTMLInputElement;
const ensembleMembersInput = document.getElementById("ensemble-members") as HTMLInputElement;
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

// Dev-only escape hatch for debugging map/tile state from the console
// (map.loaded(), map.isStyleLoaded(), ...) -- module scope hides `map`.
if (import.meta.env.DEV) {
  (window as unknown as { __map: maplibregl.Map }).__map = map;
}

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
    overlay = new MapboxOverlay({
      // Non-interleaved: deck.gl draws on its own canvas above the map.
      // Hover picking for getTooltip was verified broken live in interleaved
      // mode (pointer within 2px of a contour line, pickingRadius 8, no
      // pick); thin lines sitting above basemap labels is an acceptable
      // trade for working tooltips.
      interleaved: false,
      layers: [],
      // Contours are thin (3px) lines; without a picking radius the hover
      // target is nearly impossible to hit.
      pickingRadius: 8,
      getTooltip: ({ object }) => {
        if (!object) return null;
        // Target scatter dots are plain Target objects (name/category), not
        // GeoJSON features -- surface which target the dot is.
        const t = object as { name?: string; category?: string };
        if (t.name != null && t.category != null) {
          const label = TARGET_LABELS[t.category] ?? t.category;
          return { text: `${t.name} -- ${label}` };
        }
        const p = (object as { properties?: Record<string, number> }).properties;
        if (!p) return null;
        // Ensemble bands carry an exceedance probability, not a dose level.
        if (p.exceedance_probability != null) {
          return { text: `${(p.exceedance_probability * 100).toFixed(0)}% chance dose rate ≥ this level` };
        }
        // Single-plume features carry display_level_rhr (decay-relabeled by
        // the slider); envelope features only have the raw H+1 level.
        if (p.display_level_rhr != null) {
          return { text: `${p.display_level_rhr} R/hr isodose at ${timeLabel.textContent}` };
        }
        if (p.dose_rate_h1_rhr != null) {
          return { text: `${p.dose_rate_h1_rhr} R/hr isodose at H+1` };
        }
        return null;
      },
    });
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

// --- manual wind override -----------------------------------------------------

manualWindCheckbox.addEventListener("change", () => {
  manualWindFields.hidden = !manualWindCheckbox.checked;
});

// --- ensemble uncertainty-band toggle ----------------------------------------
// Ensemble is a single-ground-zero operation (like the plume view) but runs
// Tier-1 across real GFS-ensemble members and maps exceedance probability. It
// uses the ensemble winds, not the tier/manual-wind controls, so those are
// left visible but documented as ignored (see the fieldset hint).

function updateComputeButtonText(): void {
  if (exchangeModeCheckbox.checked) {
    computeBtn.textContent = "Compute national envelope";
  } else if (ensembleModeCheckbox.checked) {
    computeBtn.textContent = "Compute uncertainty band";
  } else {
    computeBtn.textContent = "Compute plume";
  }
}

ensembleModeCheckbox.addEventListener("change", () => {
  ensembleFields.hidden = !ensembleModeCheckbox.checked;
  updateComputeButtonText();
  // Switching mode invalidates any deterministic plume on screen (the decay
  // slider has no meaning for a probability band), so clear that state.
  timeControl.hidden = true;
  currentPlume = null;
});

/** Returns the manual wind to send, or null if the override is off.
 * Throws ApiError on out-of-range values (mirrors the API's own bounds in
 * schemas.py so the user gets a readable message instead of a 422). */
function manualWindFromForm(): ManualWind | null {
  if (!manualWindCheckbox.checked) return null;
  const speed = Number(windSpeedInput.value);
  const bearing = Number(windBearingInput.value);
  const shear = Number(windShearInput.value);
  if (!Number.isFinite(speed) || speed <= 0) {
    throw new ApiError("Manual wind speed must be a positive number of mph.");
  }
  if (!Number.isFinite(bearing) || bearing < 0 || bearing >= 360) {
    throw new ApiError("Manual wind bearing must be 0-359.9 degrees.");
  }
  if (!Number.isFinite(shear) || shear < 0) {
    throw new ApiError("Manual wind shear must be zero or positive.");
  }
  return { speed_mph: speed, bearing_deg: bearing, shear_mph_per_kft: shear };
}

// --- yield presets --------------------------------------------------------------

for (const btn of document.querySelectorAll<HTMLButtonElement>(".preset")) {
  btn.addEventListener("click", () => {
    yieldInput.value = btn.dataset.yield ?? yieldInput.value;
  });
}

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
  // Global yield/fission drive only the single-plume view; the envelope uses
  // per-target-class yields server-side, so swap the input for a summary note.
  globalYieldFields.hidden = exchangeModeCheckbox.checked;
  perClassNote.hidden = !exchangeModeCheckbox.checked;
  updateComputeButtonText();
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
  } else if (ensembleModeCheckbox.checked) {
    await computeEnsembleBand();
  } else {
    await computeSinglePlume();
  }
}

async function computeEnsembleBand(): Promise<void> {
  computeBtn.disabled = true;
  statusEl.textContent = "Computing ensemble band (fetches live GFS-ensemble winds, runs Tier-1 per member)...";
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
  timeControl.hidden = true; // probability band has no decay slider
  exportBtn.hidden = true;
  currentPlume = null;
  clearTargetMarkers();

  const level = Number(ensembleLevelInput.value);
  const members = Number(ensembleMembersInput.value);
  if (!Number.isFinite(level) || level <= 0) {
    statusEl.textContent = "Dose level to band must be a positive number of R/hr.";
    statusEl.classList.remove("busy");
    statusEl.classList.add("error");
    computeBtn.disabled = false;
    return;
  }

  try {
    await ensureMapReady();
    const resp = await fetchEnsemble({
      lat: Number(latInput.value),
      lon: Number(lonInput.value),
      yield_mt: Number(yieldInput.value),
      fission_fraction: Number(ffInput.value),
      level_rhr: level,
      n_members: Math.round(members),
    });
    disclaimerEl.textContent = resp.disclaimer;
    placeGzMarker(resp.ground_zero[1], resp.ground_zero[0]);
    map.flyTo({ center: resp.ground_zero, zoom: 6 });

    statusEl.textContent = `P(H+1 dose rate ≥ ${resp.level_rhr} R/hr) across ${resp.n_members} members.`;
    renderPlainNotes(resp.notes);
    renderEnsembleContours(resp.contours);
    exportGeoJson = resp.contours;
    exportBtn.hidden = false;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `Failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
  }
}

async function computeSinglePlume(): Promise<void> {
  computeBtn.disabled = true;
  statusEl.textContent = manualWindCheckbox.checked
    ? "Computing (manual wind)..."
    : "Computing (fetches live wind)...";
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
  timeControl.hidden = true;
  exportBtn.hidden = true;

  const tierInput = form.querySelector<HTMLInputElement>('input[name="tier"]:checked');
  const tier = tierInput ? (Number(tierInput.value) as 0 | 1) : 0;

  try {
    const wind = manualWindFromForm();
    await ensureMapReady();
    const resp = await fetchPlume({
      lat: Number(latInput.value),
      lon: Number(lonInput.value),
      yield_mt: Number(yieldInput.value),
      fission_fraction: Number(ffInput.value),
      tier,
      ...(wind ? { wind } : {}),
      levels_rhr: fetchLevelSet(),
    });
    writeUrlState({ mode: "plume", tier });
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
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
  }
}

async function computeExchangeEnvelope(): Promise<void> {
  computeBtn.disabled = true;
  statusEl.textContent = "Computing national max-envelope (fetches live wind for all targets)...";
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
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

    writeUrlState({ mode: "exchange" });
    const validHour = resp.weather ? ` · winds valid ${resp.weather.valid_time}Z` : "";
    statusEl.textContent = `Envelope computed across ${resp.n_targets} target(s).${validHour}`;
    renderPlainNotes(resp.notes);
    renderStaticContours(resp.contours);
    // Carry weather provenance into the export so a downloaded envelope records
    // which forecast hour produced it.
    exportGeoJson = { ...resp.contours, weather: resp.weather ?? undefined } as GeoJsonFeatureCollection;
    exportBtn.hidden = false;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `Failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
  }
}

// --- shareable URL state ------------------------------------------------------
// The scenario a user just computed is encoded into the query string
// (replaceState -- no history spam), so the URL can be copied to share or
// bookmark it. On load, matching params prefill the form but do NOT
// auto-compute: computing fetches live wind, and firing a network-dependent
// request nobody asked for on every page load would be rude to Open-Meteo
// and confusing on a dead connection.

function writeUrlState(opts: { mode: "plume" | "exchange"; tier?: 0 | 1 }): void {
  const params = new URLSearchParams();
  params.set("mode", opts.mode);
  params.set("yield_mt", yieldInput.value);
  params.set("ff", ffInput.value);
  if (opts.mode === "plume") {
    params.set("lat", latInput.value);
    params.set("lon", lonInput.value);
    params.set("tier", String(opts.tier ?? 0));
  }
  history.replaceState(null, "", `?${params}`);
}

function readUrlState(): void {
  const params = new URLSearchParams(window.location.search);
  if (!params.has("mode")) return;
  const setIfFinite = (input: HTMLInputElement, key: string) => {
    const v = Number(params.get(key));
    if (params.has(key) && Number.isFinite(v)) input.value = params.get(key)!;
  };
  setIfFinite(yieldInput, "yield_mt");
  setIfFinite(ffInput, "ff");
  if (params.get("mode") === "exchange") {
    exchangeModeCheckbox.checked = true;
    // Reuse the change handler to hide single-target fields etc.
    exchangeModeCheckbox.dispatchEvent(new Event("change"));
    return;
  }
  setIfFinite(latInput, "lat");
  setIfFinite(lonInput, "lon");
  const tier = params.get("tier");
  if (tier === "0" || tier === "1") {
    const radio = form.querySelector<HTMLInputElement>(`input[name="tier"][value="${tier}"]`);
    if (radio) radio.checked = true;
  }
}

readUrlState();

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

// --- full nuclear exchange: target scatter layer + static contours -----------
// The expanded deck is ~500+ ground zeros (three Minuteman fields resolved to
// individual silos/LCCs, plus HVTs). One MapLibre DOM Marker per target would
// be hundreds of DOM nodes; a single deck.gl ScatterplotLayer draws them all in
// one GPU pass and stays responsive. It's kept in a module var so the contour
// setProps calls can re-include it instead of clobbering it.
let targetLayer: ScatterplotLayer | null = null;

// deck.gl replaces ALL layers on each setProps, so every setProps in exchange
// mode must re-include the target scatter beneath the contour lines.
function setOverlayLayers(...layers: (GeoJsonLayer | ScatterplotLayer | null)[]): void {
  overlay.setProps({ layers: layers.filter((l): l is NonNullable<typeof l> => l !== null) });
}

async function plotTargetMarkers(): Promise<void> {
  const targets = await fetchTargets(true);
  targetLayer = new ScatterplotLayer<Target>({
    id: "targets",
    data: targets,
    getPosition: (t) => [t.lon, t.lat],
    // Silos are tiny and dense; keep dots small in pixels so a whole field
    // reads as a cluster of points rather than a blob.
    getRadius: (t) => (t.category === "icbm_lf" ? 2.5 : 4),
    radiusUnits: "pixels",
    radiusMinPixels: 2,
    getFillColor: (t) => TARGET_COLORS[t.category] ?? TARGET_COLOR_DEFAULT,
    stroked: true,
    getLineColor: [255, 255, 255, 180],
    lineWidthUnits: "pixels",
    getLineWidth: 0.5,
    pickable: true,
  });
}

function clearTargetMarkers(): void {
  targetLayer = null;
}

// Exchange-envelope contours have no per-target ground zero or decay-time
// slider to drive (see the comment on the exchange-mode toggle above) --
// just render the fixed H+1 dose-rate levels the API returns, above the target
// scatter layer.
function renderStaticContours(fc: GeoJsonFeatureCollection): void {
  const contourLayer = new GeoJsonLayer({
    id: "contours",
    data: fc as unknown as GeoJSON.FeatureCollection,
    stroked: true,
    filled: false,
    getLineColor: (f: any) => LEVEL_COLORS[f.properties.dose_rate_h1_rhr] ?? [255, 255, 255, 200],
    getLineWidth: 3,
    lineWidthUnits: "pixels",
    pickable: true,
  });
  setOverlayLayers(targetLayer, contourLayer);
  renderLegend(fc.features.map((f) => f.properties.dose_rate_h1_rhr).sort((a, b) => a - b));
  renderTargetLegend();
}

// --- ensemble uncertainty bands ---------------------------------------------
// Exceedance-probability contours (10/50/90%). Rendered as nested lines from
// the faint outer edge to the saturated core, with the inner (more-likely)
// bands drawn thicker to reinforce the nesting.
function renderEnsembleContours(fc: GeoJsonFeatureCollection): void {
  const layer = new GeoJsonLayer({
    id: "ensemble",
    data: fc as unknown as GeoJSON.FeatureCollection,
    stroked: true,
    filled: false,
    getLineColor: (f: any) => PROB_COLORS[f.properties.exceedance_probability] ?? [255, 255, 255, 200],
    getLineWidth: (f: any) => 2 + 3 * (f.properties.exceedance_probability ?? 0.5),
    lineWidthUnits: "pixels",
    pickable: true,
  });
  setOverlayLayers(layer);
  const probs = [...new Set(fc.features.map((f) => f.properties.exceedance_probability))].sort(
    (a, b) => a - b,
  );
  renderEnsembleLegend(probs);
}

function renderEnsembleLegend(probs: number[]): void {
  legendEl.innerHTML = "";
  const title = document.createElement("div");
  title.className = "legend-title";
  title.textContent = "Chance H+1 dose rate exceeds the level (hover a band)";
  legendEl.appendChild(title);
  for (const p of probs) {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    const [r, g, b] = PROB_COLORS[p] ?? [255, 255, 255, 200];
    swatch.style.background = `rgb(${r},${g},${b})`;
    row.appendChild(swatch);
    const label = document.createElement("span");
    label.textContent = PROB_LABELS[p] ?? `${(p * 100).toFixed(0)}%`;
    row.appendChild(label);
    legendEl.appendChild(row);
  }
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
  if (levels.length > 0) {
    const title = document.createElement("div");
    title.className = "legend-title";
    title.textContent = "Dose-rate isodose lines (hover a contour for its value)";
    legendEl.appendChild(title);
  }
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

// Category key/legend for the full-exchange target dots, appended below the
// dose-rate isodose legend.
function renderTargetLegend(): void {
  const title = document.createElement("div");
  title.className = "legend-title";
  title.textContent = "Targets (ground zeros)";
  legendEl.appendChild(title);
  for (const [cat, label] of Object.entries(TARGET_LABELS)) {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    const [r, g, b] = TARGET_COLORS[cat] ?? TARGET_COLOR_DEFAULT;
    swatch.style.background = `rgb(${r},${g},${b})`;
    swatch.style.borderRadius = "50%";
    row.appendChild(swatch);
    const text = document.createElement("span");
    text.textContent = label;
    row.appendChild(text);
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
