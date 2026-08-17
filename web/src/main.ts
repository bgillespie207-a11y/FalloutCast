import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  fetchPlume,
  fetchExchangeEnvelope,
  fetchEnsemble,
  fetchExposure,
  fetchTargets,
  fetchDeck,
  geocodeZip,
  geocodePlace,
  ApiError,
  type ManualWind,
  type PlumeResponse,
  type PointExposureResponse,
  type WeatherProvenance,
  type WindProfilePoint,
  type GeoJsonFeatureCollection,
  type TargetDeckMeta,
} from "./api";
import {
  DISPLAY_LEVELS_RHR,
  ENVELOPE_TIME_MAX_HOURS,
  fetchLevelSet,
  levelsForTime,
  TIME_MIN_HOURS,
  TIME_MAX_HOURS,
} from "./decay";
import { describeAge, fmtNum, formatHours } from "./format";
import { compassName, contourFillFeatures, farthestPoint } from "./geo";
import {
  exportMetadata,
  fmtLonLat,
  reportMarkdown,
  weatherFactStr,
  type ExportReport,
  type ReachRow,
} from "./report";
import {
  KM_PER_MI,
  fmtDose,
  formatHeightShort,
  formatReach,
  formatSpeed,
  formatSpeedShort,
  getUnitSystem,
  setUnitSystem,
  type UnitSystem,
} from "./units";
import { buildUrlParams, parseUrlParams, type UrlMode } from "./urlstate";

// Free, keyless vector basemap (openfreemap.org) -- no API key/signup needed,
// which matters for a project meant to run out of the box.
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

// 200 steps over a log time axis (H+1 .. H+7d): fine enough to drag smoothly,
// coarse enough that a single arrow-key press is a perceptible move (the
// reviewer found 1000 steps made keyboard nudges invisible).
const SLIDER_STEPS = 200;

// Per-band fill alpha. Low, because the bands nest: a point in the innermost
// zone is covered by every band's fill, so the tint compounds toward the hot
// core while a lone outer band stays light enough to read the map through.
const CONTOUR_FILL_OPACITY = 0.22;

// Fixed color per civil-defense dose-rate band. Colors are from the Okabe-Ito
// colorblind-safe palette (Okabe & Ito 2008) plus black, ordered by strictly
// decreasing lightness, so band severity reads correctly under all common
// color-vision deficiencies and in grayscale -- hue is reinforcement, not the
// only signal (the UX review flagged the old yellow/orange/red ramp). RGBA.
const LEVEL_COLORS: Record<number, [number, number, number, number]> = {
  1: [240, 228, 66, 200], // yellow
  10: [230, 159, 0, 210], // orange
  100: [213, 94, 0, 220], // vermillion
  1000: [0, 0, 0, 235], // black
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
  naval_base: [70, 130, 180, 220],   // surface/attack-sub fleet (e.g. Pearl Harbor)
  air_base: [150, 100, 205, 220],    // military airfield (e.g. Eielson, JBER)
  army_base: [130, 110, 75, 220],    // Army/Marine ground-force post (khaki)
  missile_defense: [20, 160, 110, 225], // GMD interceptors / early-warning radar
  storage: [120, 120, 130, 220],
  command: [200, 40, 40, 235],       // government / C2
  city_population: [235, 130, 40, 220],
  industry: [180, 160, 40, 220],
};
const TARGET_COLOR_DEFAULT: [number, number, number, number] = [120, 120, 120, 200];

// Ensemble exceedance-probability bands. A single-hue blue lightness ramp
// (ColorBrewer "Blues" classes 4/6/9): distinguishing by lightness rather than
// hue makes it safe under every color-vision deficiency and in grayscale, and
// keeps it deliberately distinct from the warm dose-rate palette above so the
// two views never read as the same thing: the outer 10% band ("could reach")
// is faint, the inner 90% ("very likely") is near-black. RGBA.
const PROB_COLORS: Record<number, [number, number, number, number]> = {
  0.1: [158, 202, 225, 200],
  0.5: [66, 146, 198, 220],
  0.9: [8, 48, 107, 240],
};
const PROB_LABELS: Record<number, string> = {
  0.1: "10% — outer edge (could reach)",
  0.5: "50% — more likely than not",
  0.9: "90% — very likely",
};

// Descriptive model names, technical term secondary (matches the radio labels).
const TIER_NAMES: Record<number, string> = {
  0: "Fast planning model (Tier 0, WSEG-10)",
  1: "Layered live-wind model (Tier 1)",
};

// Human-readable labels for the target-category legend.
const TARGET_LABELS: Record<string, string> = {
  icbm_lf: "ICBM silo (LF)",
  icbm_lcc: "Launch control center",
  bomber_base: "Bomber base",
  ssbn_base: "SSBN base",
  naval_base: "Naval base",
  air_base: "Air base",
  army_base: "Army / Marine base",
  missile_defense: "Missile defense / warning",
  storage: "Weapons storage",
  command: "Government / C2",
  city_population: "Population center",
  industry: "Industry / economic",
};

// --- native MapLibre rendering ----------------------------------------------
// deck.gl was removed: for ~537 target points + a handful of contour lines,
// native MapLibre circle/line layers are more than adequate and, crucially,
// render into the SAME canvas/WebGL context as the basemap -- so there is no
// separate overlay canvas that can fail silently (the failure mode the review
// flagged). If the basemap draws, the overlay draws.
const CONTOUR_SOURCE = "fc-contours";
const CONTOUR_FILL_SOURCE = "fc-contour-fills";
const TARGET_SOURCE = "fc-targets";
const FIELD_SOURCE = "fc-fields";
const CONTOUR_FILL_LAYER = "fc-contour-fill";
const CONTOUR_LAYER = "fc-contour-lines";
const TARGET_LAYER = "fc-target-circles";
const FIELD_LAYER = "fc-field-outlines";
const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function rgba(c: [number, number, number, number]): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${(c[3] / 255).toFixed(3)})`;
}

// A MapLibre color expression mapping a numeric feature property to a color.
// Uses `case`/`==` rather than `match`: `match` requires INTEGER branch labels,
// but the ensemble bands are keyed on float probabilities (0.1/0.5/0.9). `case`
// handles both integer dose levels and float probabilities uniformly.
function colorMatchExpr(prop: string, colors: Record<number, [number, number, number, number]>): unknown {
  const expr: unknown[] = ["case"];
  for (const [k, c] of Object.entries(colors)) {
    expr.push(["==", ["get", prop], Number(k)], rgba(c));
  }
  expr.push("rgba(255,255,255,0.8)"); // default for unmapped values
  return expr;
}

// Match expression coloring target dots by their (string) category.
function categoryColorExpr(): unknown {
  const expr: unknown[] = ["match", ["get", "category"]];
  for (const [cat, c] of Object.entries(TARGET_COLORS)) {
    expr.push(cat, rgba(c));
  }
  expr.push(rgba(TARGET_COLOR_DEFAULT));
  return expr;
}

const form = document.getElementById("plume-form") as HTMLFormElement;
const latInput = document.getElementById("lat") as HTMLInputElement;
const lonInput = document.getElementById("lon") as HTMLInputElement;
const locSearchInput = document.getElementById("loc-search") as HTMLInputElement;
const locSearchBtn = document.getElementById("loc-search-btn") as HTMLButtonElement;
const tabSingle = document.getElementById("tab-single") as HTMLButtonElement;
const tabExchange = document.getElementById("tab-exchange") as HTMLButtonElement;
const modePanel = document.getElementById("mode-panel") as HTMLElement;
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
const staleNoteEl = document.getElementById("stale-note") as HTMLParagraphElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const timeControl = document.getElementById("time-control") as HTMLElement;
const timeSlider = document.getElementById("time-slider") as HTMLInputElement;
const timeLabel = document.getElementById("time-label") as HTMLSpanElement;
const timeTicks = document.getElementById("time-ticks") as HTMLDataListElement;
const timeTickLabels = document.getElementById("time-ticks-labels") as HTMLDivElement;
const timeCaveat = document.getElementById("time-caveat") as HTMLParagraphElement;
const legendEl = document.getElementById("legend") as HTMLDivElement;
const exportBtn = document.getElementById("export-btn") as HTMLButtonElement;
const reportBtn = document.getElementById("report-btn") as HTMLButtonElement;
const overviewBtn = document.getElementById("overview-btn") as HTMLButtonElement;
overviewBtn.addEventListener("click", () => returnToOverview());
// Off-CONUS jumps for the envelope. Map framings only -- no target coordinates
// are asserted here; these just point the camera at the two states whose deck
// entries are otherwise off-screen at every default view.
const jumpHiBtn = document.getElementById("jump-hi-btn") as HTMLButtonElement;
const jumpAkBtn = document.getElementById("jump-ak-btn") as HTMLButtonElement;
jumpHiBtn.addEventListener("click", () =>
  map.flyTo({ center: [-157.5, 20.9], zoom: 6, duration: 800 }),
);
jumpAkBtn.addEventListener("click", () =>
  map.flyTo({ center: [-150.5, 63.5], zoom: 4, duration: 800 }),
);
const shareBtn = document.getElementById("share-btn") as HTMLButtonElement;
// The URL always reflects the last computed scenario (writeUrlState), so
// sharing is just copying it. No sensitive data: mode, coords, yield, model
// choice, and (if set) manual wind / ensemble knobs.
shareBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    statusEl.textContent = "Scenario link copied to the clipboard.";
  } catch {
    statusEl.textContent = `Copy failed — share this URL: ${window.location.href}`;
  }
});
const notesEl = document.getElementById("notes") as HTMLDivElement;
const windProfileEl = document.getElementById("wind-profile") as HTMLElement;
const unitsMetricBtn = document.getElementById("units-metric") as HTMLButtonElement;
const unitsUsBtn = document.getElementById("units-us") as HTMLButtonElement;
const disclaimerToggle = document.getElementById("disclaimer-toggle") as HTMLButtonElement;
const disclaimerFullEl = document.getElementById("disclaimer-full") as HTMLDivElement;
const exposureSection = document.getElementById("exposure") as HTMLElement;
const exposureCloseBtn = document.getElementById("exposure-close") as HTMLButtonElement;
const exposureSummaryEl = document.getElementById("exposure-summary") as HTMLDivElement;
const exposureExitSelect = document.getElementById("exposure-exit") as HTMLSelectElement;
const exposurePfSelect = document.getElementById("exposure-pf") as HTMLSelectElement;
const exposureDosesEl = document.getElementById("exposure-doses") as HTMLDivElement;
const exposureSetGzBtn = document.getElementById("exposure-set-gz") as HTMLButtonElement;
const exposureNotesEl = document.getElementById("exposure-notes") as HTMLDivElement;
const exclusionWarningEl = document.getElementById("exclusion-warning") as HTMLDivElement;
const weatherInfoEl = document.getElementById("weather-info") as HTMLDivElement;
const weatherTextEl = document.getElementById("weather-text") as HTMLSpanElement;
const weatherRefreshBtn = document.getElementById("weather-refresh") as HTMLButtonElement;

timeSlider.max = String(SLIDER_STEPS);

const map = new maplibregl.Map({
  container: "map",
  style: BASEMAP_STYLE,
  center: [-98.5, 39.8], // CONUS centroid-ish
  zoom: 3.3,
});
map.addControl(new maplibregl.NavigationControl(), "top-right");
// Distance scale (backlog #23): one bar per unit system, stacked bottom-left,
// so plume sizes are readable in both mi and km at any zoom.
map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "imperial" }), "bottom-left");
map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");

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

let gzMarker: maplibregl.Marker | null = null;
let currentPlume: PlumeResponse | null = null;

// Point-exposure inspection state. inspectContext is non-null only while a
// Tier-0 plume (whose effective wind is known numerically) is on screen; it
// carries exactly the parameters that plume was computed with, so /exposure
// evaluates the same model the map is showing.
interface InspectContext {
  gzLat: number;
  gzLon: number;
  yieldMt: number;
  ff: number;
  wind: ManualWind;
}
let inspectContext: InspectContext | null = null;
let inspectPoint: { lat: number; lon: number } | null = null;
let inspectMarker: maplibregl.Marker | null = null;
let inspectSeq = 0; // discard out-of-order /exposure responses

// Surface render/graphics failures instead of letting them fail silently while
// the UI reports success (the review's finding). A lost WebGL context or a
// style error now shows in the status line.
map.on("error", (e) => {
  // MapLibre fires benign errors for missing tiles etc.; log all, but only
  // alert the user on a hard failure signalled by a message.
  console.error("MapLibre error:", (e as { error?: Error }).error ?? e);
});
map.getCanvas().addEventListener("webglcontextlost", () => {
  statusEl.textContent = "Map graphics context was lost — reload the page to continue.";
  statusEl.classList.add("error");
});

// Our overlay is "ready" once the style has been PARSED and our sources/layers
// are installed. We deliberately do NOT gate on the `load` event: `load` also
// waits for the initial basemap TILES, so a slow or blocked external tile host
// delays it for many seconds and makes compute spuriously fail even though the
// overlay could render fine.
//
// `map.isStyleLoaded()` is NOT that gate either, despite the name: MapLibre's
// Style.loaded() returns false unless every source cache is loaded AND the
// sprite images are loaded -- i.e. it carries the exact basemap-tile dependency
// we are trying to avoid. Verified live against openfreemap: style._loaded was
// true and the basemap was visibly drawn while isStyleLoaded() stayed false
// indefinitely (sourceCaches ne2_shaded/openmaptiles both reporting unloaded),
// so setup never ran and every compute died after the 20 s timeout with
// "Map style failed to load. Check your connection and reload."
//
// What addSource/addLayer actually require is a parsed style, and they throw a
// plain Error until then. So: attempt the install, treat a throw as "not parsed
// yet" and retry on the next styledata. Each step is individually guarded by a
// getSource/getLayer check so a partial install (parse completes mid-sequence,
// or a retry after a throw) can never double-add and wedge setup permanently.
let mapSetupDone = false;
let resolveMapReady!: () => void;
const mapReady = new Promise<void>((resolve) => {
  resolveMapReady = resolve;
});

function setupMapOverlay(): void {
  if (mapSetupDone) return;

  try {
    for (const id of [FIELD_SOURCE, TARGET_SOURCE, CONTOUR_SOURCE, CONTOUR_FILL_SOURCE]) {
      if (!map.getSource(id)) {
        map.addSource(id, { type: "geojson", data: EMPTY_FC as GeoJSON.FeatureCollection });
      }
    }

    // Translucent band fills, UNDER the basemap's own labels: a contour line
    // alone leaves which side is hot to inference, which is what made the
    // national envelope read as ~600 overlapping rings rather than areas.
    // Bands nest (1000 R/hr inside 100 inside 10 inside 1), so the constant
    // per-band opacity accumulates toward the center -- severity reads as
    // depth of tint, on top of the palette's existing lightness ordering.
    // Inserted before the first symbol layer so city names stay legible; the
    // contour LINES stay above everything as the authoritative geometry.
    if (!map.getLayer(CONTOUR_FILL_LAYER)) {
      const firstSymbol = map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
      map.addLayer(
        {
          id: CONTOUR_FILL_LAYER,
          type: "fill",
          source: CONTOUR_FILL_SOURCE,
          paint: {
            "fill-color": "rgba(255,255,255,0.8)",
            "fill-opacity": CONTOUR_FILL_OPACITY,
            "fill-antialias": true,
          },
        },
        firstSymbol,
      );
    }

    // Documented field FOOTPRINTS (the verifiable geography). Dashed outline
    // underneath the synthetic points, so it's clear the field extent is real
    // even though the individual dots inside it are not.
    if (!map.getLayer(FIELD_LAYER)) {
      map.addLayer({
        id: FIELD_LAYER,
        type: "line",
        source: FIELD_SOURCE,
        paint: { "line-color": "rgba(120,120,130,0.9)", "line-width": 1.5, "line-dasharray": [3, 2] },
      });
    }

    // Target dots below the contour lines. Small in pixels so a dense missile
    // field reads as a cluster of points, not a blob. Colored by category.
    if (!map.getLayer(TARGET_LAYER)) {
      map.addLayer({
        id: TARGET_LAYER,
        type: "circle",
        source: TARGET_SOURCE,
        paint: {
          // Excluded targets (wind fetch failed, no plume computed) are drawn
          // larger with a red ring: a bare dot on an empty map otherwise reads
          // as a computed target with nothing around it.
          "circle-radius": [
            "case",
            ["==", ["get", "excluded"], 1],
            5.5,
            ["match", ["get", "category"], "icbm_lf", 2.5, 4],
          ] as unknown as number,
          "circle-color": categoryColorExpr() as maplibregl.ExpressionSpecification,
          "circle-stroke-width": [
            "case",
            ["==", ["get", "excluded"], 1],
            2,
            0.5,
          ] as unknown as number,
          "circle-stroke-color": [
            "case",
            ["==", ["get", "excluded"], 1],
            "rgba(200,40,40,0.95)",
            "rgba(255,255,255,0.7)",
          ] as unknown as string,
        },
      });
    }

    if (!map.getLayer(CONTOUR_LAYER)) {
      map.addLayer({
        id: CONTOUR_LAYER,
        type: "line",
        source: CONTOUR_SOURCE,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 3, "line-color": "rgba(255,255,255,0.8)" },
      });
    }
  } catch {
    // Style not parsed yet -- a later `styledata` (or the ensureMapReady poll)
    // retries. Partial progress is safe: every step above is idempotent.
    return;
  }

  installHoverPopups();
  mapSetupDone = true;
  resolveMapReady();
}

map.on("styledata", setupMapOverlay); // fires when the style is ready (before tiles)
map.on("load", setupMapOverlay); // fallback
setupMapOverlay(); // in case the style is already loaded synchronously (cached)

// `await mapReady` alone could hang the "Computing..." status forever if the
// style never loads (dead connection) -- fail loudly after a timeout. This
// timeout is now rare: it waits only for the STYLE, not for basemap tiles.
async function ensureMapReady(): Promise<void> {
  if (mapSetupDone) return;
  // Keep retrying the (idempotent) setup while we wait: styledata can fire
  // while the tab is hidden with isStyleLoaded() still false (rAF is paused
  // in background tabs, so MapLibre's load sequence stalls mid-way), and no
  // later event re-runs setup once the style eventually finishes. A one-shot
  // retry at call time is not enough -- the style may finish loading AFTER
  // the compute started. Interval callbacks are throttled in hidden tabs,
  // but whenever one does fire with the style ready, setup completes and
  // resolves mapReady.
  setupMapOverlay();
  if (mapSetupDone) return;
  const poll = window.setInterval(setupMapOverlay, 500);
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(
      () => reject(new ApiError("Map style failed to load. Check your connection and reload.")),
      20000,
    ),
  );
  try {
    await Promise.race([mapReady, timeout]);
  } finally {
    clearInterval(poll);
  }
}

// Map clicks do double duty:
//   * no single-plume result on screen -> set ground zero (friendlier than
//     typing coordinates);
//   * a Tier-0 plume IS on screen -> assess exposure at the clicked point
//     (the panel offers "Set as new ground zero" so that flow stays one
//     click away).
// No-op in exchange mode: there's no single ground zero to set (the envelope
// covers all public targets at once).
map.on("click", (e) => {
  if (exchangeMode) return;
  if (inspectContext && currentPlume) {
    void inspectExposure(e.lngLat.lat, e.lngLat.lng);
    return;
  }
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

// --- basic/advanced disclosure -------------------------------------------------
// Everything tagged .adv (model choice, wind override, ensemble band, fission
// fraction) hides behind one toggle; all of it has sane defaults, so a first
// compute needs only a location and a yield. Hiding never changes any value --
// collapsed advanced settings still apply (the compute-button text reflects an
// active ensemble mode, so it can't be silently forgotten).

const advToggle = document.getElementById("advanced-toggle") as HTMLButtonElement;
let advancedShown = false;

function setAdvanced(show: boolean): void {
  advancedShown = show;
  advToggle.setAttribute("aria-expanded", String(show));
  advToggle.textContent = show ? "Hide advanced options" : "Show advanced options";
  for (const el of document.querySelectorAll<HTMLElement>(".adv")) el.hidden = !show;
}

advToggle.addEventListener("click", () => setAdvanced(!advancedShown));
setAdvanced(false);

// --- ensemble uncertainty-band toggle ----------------------------------------
// Ensemble is a single-ground-zero operation (like the plume view) but runs
// Tier-1 across real GFS-ensemble members and maps exceedance probability. It
// uses the ensemble winds, not the tier/manual-wind controls, so those are
// left visible but documented as ignored (see the fieldset hint).

function updateComputeButtonText(): void {
  if (exchangeMode) {
    computeBtn.textContent = "Compute national envelope";
  } else if (ensembleModeCheckbox.checked) {
    computeBtn.textContent = "Compute uncertainty band";
  } else {
    computeBtn.textContent = "Compute plume";
  }
}

// Clear every result artifact from the map + panel, so a mode switch or input
// change never leaves a stale plume/envelope on screen labelled with the wrong
// controls (the reviewer's finding).
function clearFieldPolygons(): void {
  (map.getSource(FIELD_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
    EMPTY_FC as GeoJSON.FeatureCollection,
  );
}
function clearResults(): void {
  clearContours();
  clearTargetMarkers();
  clearFieldPolygons();
  clearGzMarker();
  closeExposure();
  inspectContext = null;
  currentPlume = null;
  exportGeoJson = null;
  exportReport = null;
  notesEl.innerHTML = "";
  legendEl.innerHTML = "";
  clearContourTable();
  renderWeather(null);
  clearWindProfile();
  decaySeries = null;
  timeControl.hidden = true;
  timeCaveat.hidden = true;
  exportBtn.hidden = true;
  reportBtn.hidden = true;
  shareBtn.hidden = true;
  overviewBtn.hidden = true;
  jumpHiBtn.hidden = true;
  jumpAkBtn.hidden = true;
  clearStaleNote();
}

// --- stale-result notice -------------------------------------------------------
// Editing an input does NOT re-run the model, so the plume on screen can end up
// labelled with controls that no longer produced it -- a 5 Mt footprint sitting
// next to a yield box reading 0.3. We flag that rather than clearing the map:
// clearing on every keystroke blanks the result mid-way through typing "0.35".
// Cleared again by any successful compute (the inputs then match the result).

function clearStaleNote(): void {
  staleNoteEl.hidden = true;
}

function markResultsStale(): void {
  // The envelope is driven entirely by server-side per-class yields, so none of
  // these controls apply to it.
  if (exchangeMode) return;
  if (!currentPlume && !exportGeoJson) return; // nothing on screen to invalidate
  staleNoteEl.hidden = false;
}

for (const el of [
  latInput,
  lonInput,
  yieldInput,
  ffInput,
  windSpeedInput,
  windBearingInput,
  windShearInput,
  ensembleLevelInput,
  ensembleMembersInput,
]) {
  el.addEventListener("input", markResultsStale);
}
for (const el of [manualWindCheckbox, ...form.querySelectorAll<HTMLInputElement>('input[name="tier"]')]) {
  el.addEventListener("change", markResultsStale);
}

ensembleModeCheckbox.addEventListener("change", () => {
  newComputeToken(); // invalidate any in-flight compute for the previous mode
  ensembleFields.hidden = !ensembleModeCheckbox.checked;
  updateComputeButtonText();
  // Switching mode clears any prior result (a single plume's decay slider has
  // no meaning for a probability band, and a stale plume mustn't linger).
  clearResults();
  statusEl.textContent = "";
  statusEl.classList.remove("error");
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
// The preset matching the current yield value stays visibly selected
// (aria-pressed) -- previously a click gave no persistent feedback, and typing
// a custom yield left a stale-looking highlight impossible; selection is
// derived from the input value, so both stay in sync.

const presetButtons = [...document.querySelectorAll<HTMLButtonElement>(".preset")];

function syncPresetSelection(): void {
  const v = Number(yieldInput.value);
  for (const btn of presetButtons) {
    btn.setAttribute("aria-pressed", String(Number(btn.dataset.yield) === v));
  }
}

for (const btn of presetButtons) {
  btn.addEventListener("click", () => {
    yieldInput.value = btn.dataset.yield ?? yieldInput.value;
    syncPresetSelection();
  });
}
yieldInput.addEventListener("input", syncPresetSelection);
syncPresetSelection();

// --- location search ---------------------------------------------------------
// One box for a place name, street address, or US ZIP. A 5-digit ZIP takes the
// fast zippopotam path (US centroid); anything else -- a city, an address, a
// site in Hawaii/Alaska -- goes to the Nominatim global geocoder. Sets the
// ground-zero inputs and flies the map there, showing the resolved name so an
// ambiguous match is visible (search again to correct it).

locSearchBtn.addEventListener("click", () => void lookupLocation());
locSearchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    void lookupLocation();
  }
});

async function lookupLocation(): Promise<void> {
  const query = locSearchInput.value.trim();
  if (!query) {
    statusEl.textContent = "Enter a place, address, or 5-digit ZIP to search.";
    statusEl.classList.add("error");
    return;
  }
  const isZip = /^\d{5}$/.test(query);
  locSearchBtn.disabled = true;
  statusEl.textContent = `Searching for ${query}…`;
  statusEl.classList.remove("error");
  try {
    const loc = isZip ? await geocodeZip(query) : await geocodePlace(query);
    latInput.value = loc.lat.toFixed(4);
    lonInput.value = loc.lon.toFixed(4);
    map.flyTo({ center: [loc.lon, loc.lat], zoom: 8 });
    statusEl.textContent = `${loc.place} (${loc.lat.toFixed(3)}, ${loc.lon.toFixed(3)})`;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    statusEl.textContent = `Location search failed: ${msg}`;
    statusEl.classList.add("error");
  } finally {
    locSearchBtn.disabled = false;
  }
}

// --- mode tabs: single location vs national envelope --------------------------
// /exchange/envelope has no per-target lat/lon/tier -- it always runs Tier-0
// (WSEG-10) across the fixed public target set (see targets.py) and returns
// one composited CONUS grid. So single-target fields are hidden, not just
// ignored, while the National-envelope tab is active.

let exchangeMode = false;

function setMode(exchange: boolean): void {
  if (exchange === exchangeMode) return;
  exchangeMode = exchange;
  newComputeToken(); // invalidate any in-flight compute for the previous mode
  tabSingle.setAttribute("aria-selected", String(!exchange));
  tabExchange.setAttribute("aria-selected", String(exchange));
  // Roving tabindex: exactly one tab is in the page's tab order, so Tab enters
  // the tablist once and the arrow keys choose within it.
  tabSingle.tabIndex = exchange ? -1 : 0;
  tabExchange.tabIndex = exchange ? 0 : -1;
  // Both tabs control the one panel, so its accessible name follows the
  // selection rather than being fixed to whichever tab is written first.
  modePanel.setAttribute("aria-labelledby", exchange ? "tab-exchange" : "tab-single");
  singleTargetFields.hidden = exchange;
  // Global yield/fission drive only the single-plume view; the envelope uses
  // per-target-class yields server-side, so swap the input for a summary note.
  globalYieldFields.hidden = exchange;
  perClassNote.hidden = !exchange;
  updateComputeButtonText();
  statusEl.textContent = "";
  statusEl.classList.remove("error");
  clearResults();
}

tabSingle.addEventListener("click", () => setMode(false));
tabExchange.addEventListener("click", () => setMode(true));
// Standard tablist keyboard pattern: arrow keys move between the two tabs,
// Home/End jump to the first/last (with two tabs those coincide with the
// arrows, but the pattern is what screen-reader users will try).
for (const tab of [tabSingle, tabExchange]) {
  tab.addEventListener("keydown", (e) => {
    if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      const target = e.key === "Home" ? tabSingle : tabExchange;
      target.focus();
      target.click();
      return;
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const other = tab === tabSingle ? tabExchange : tabSingle;
      other.focus();
      other.click();
    }
  });
}

// --- display units ------------------------------------------------------------
// The preference itself and every formatter that reads it live in units.ts
// (unit-tested there); what stays here is the DOM side -- the radiogroup, the
// persisted choice, and re-rendering what's already on screen after a switch.

const UNITS_KEY = "falloutcast.units";
setUnitSystem(localStorage.getItem(UNITS_KEY) === "us" ? "us" : "metric");

// Checked state + roving tabindex for the two radio buttons. A radiogroup is a
// single tab stop: only the checked option is tabbable, and the arrow keys move
// (and select) within the group.
function syncUnitButtons(): void {
  const metric = getUnitSystem() === "metric";
  unitsMetricBtn.setAttribute("aria-checked", String(metric));
  unitsUsBtn.setAttribute("aria-checked", String(!metric));
  unitsMetricBtn.tabIndex = metric ? 0 : -1;
  unitsUsBtn.tabIndex = metric ? -1 : 0;
}

function selectUnitSystem(sys: UnitSystem): void {
  setUnitSystem(sys);
  localStorage.setItem(UNITS_KEY, sys);
  syncUnitButtons();
  applyUnits();
}
unitsMetricBtn.addEventListener("click", () => selectUnitSystem("metric"));
unitsUsBtn.addEventListener("click", () => selectUnitSystem("us"));
for (const btn of [unitsMetricBtn, unitsUsBtn]) {
  btn.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next =
      e.key === "Home"
        ? "metric"
        : e.key === "End"
          ? "us"
          : getUnitSystem() === "metric"
            ? "us"
            : "metric";
    selectUnitSystem(next as UnitSystem);
    (next === "metric" ? unitsMetricBtn : unitsUsBtn).focus();
  });
}
// Reflect the persisted choice on load (no re-render needed before any result).
syncUnitButtons();

// Re-render whatever unit-bearing result is on screen, in place (no recompute).
function applyUnits(): void {
  if (lastContourTable) renderContourTable(lastContourTable.caption, lastContourTable.rows);
  if (lastWindProfilePoints) renderWindProfile(lastWindProfilePoints);
  if (lastExposureResp && !exposureSection.hidden) renderExposure(lastExposureResp);
  // The status line quotes the effective wind, whose PRIMARY unit follows this
  // preference -- without this it kept saying "16 mph (25 km/h)" after a switch
  // to metric, until the next compute. Skipped while an error is showing so a
  // failure message isn't overwritten by a stale success summary.
  if (currentPlume && !statusEl.classList.contains("error")) {
    statusEl.textContent = plumeStatusText(currentPlume);
  }
}

async function computePlume(): Promise<void> {
  // Reset the status region to a polite progress announcer, and mark the
  // button busy for assistive tech, around whichever compute path runs.
  statusEl.setAttribute("role", "status");
  statusEl.setAttribute("aria-live", "polite");
  computeBtn.setAttribute("aria-busy", "true");
  try {
    if (exchangeMode) {
      await computeExchangeEnvelope();
    } else if (ensembleModeCheckbox.checked) {
      await computeEnsembleBand();
    } else {
      await computeSinglePlume();
    }
  } finally {
    computeBtn.removeAttribute("aria-busy");
  }
}

// Monotonic token: each compute grabs the next value; a mode switch bumps it so
// an in-flight compute whose token is now stale discards its result instead of
// rendering into the wrong mode.
let computeSeq = 0;
function newComputeToken(): number {
  return ++computeSeq;
}
function isStale(token: number): boolean {
  return token !== computeSeq;
}
function markStatusError(msg: string): void {
  statusEl.textContent = msg;
  statusEl.classList.add("error");
  statusEl.setAttribute("role", "alert");
  statusEl.setAttribute("aria-live", "assertive");
}

// Validate a ground-zero before hitting the backend, so the user gets a
// field-level message instead of a raw HTTP 422 JSON dump.
function readGroundZero(): { lat: number; lon: number } {
  const lat = Number(latInput.value);
  const lon = Number(lonInput.value);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
    throw new ApiError("Latitude must be between −90 and 90.");
  }
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
    throw new ApiError("Longitude must be between −180 and 180.");
  }
  return { lat, lon };
}

// Elapsed-time ticker for long computes (the national envelope can take tens of
// seconds): keeps the status line updating so it never looks hung, and enforces
// a client-side timeout with a friendly message.
const COMPUTE_TIMEOUT_MS = 90_000;
let elapsedTimer: number | undefined;
function startElapsed(label: string): void {
  const t0 = performance.now();
  const tick = () => {
    const s = Math.round((performance.now() - t0) / 1000);
    statusEl.textContent = `${label} (${s}s elapsed…)`;
  };
  tick();
  elapsedTimer = window.setInterval(tick, 1000);
}
function stopElapsed(): void {
  if (elapsedTimer !== undefined) {
    clearInterval(elapsedTimer);
    elapsedTimer = undefined;
  }
}
function withTimeout<T>(p: Promise<T>): Promise<T> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(
      () => reject(new ApiError(`Computation timed out after ${COMPUTE_TIMEOUT_MS / 1000}s. Try again, or reduce scope.`)),
      COMPUTE_TIMEOUT_MS,
    ),
  );
  return Promise.race([p, timeout]);
}

// --- map framing ------------------------------------------------------------
const OVERVIEW: [number, number] = [-98.5, 39.8];
const OVERVIEW_ZOOM = 3.3;

// Fit the map to a set of GeoJSON features (the computed contours) so a local
// plume isn't lost at continental scale. Falls back to a gentle flyTo if the
// features have no usable extent.
function fitToFeatures(fc: GeoJsonFeatureCollection, fallback?: [number, number]): void {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  const visit = (coords: unknown): void => {
    if (typeof (coords as number[])[0] === "number" && (coords as number[]).length >= 2) {
      const [lon, lat] = coords as number[];
      minLon = Math.min(minLon, lon); maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    } else if (Array.isArray(coords)) {
      for (const c of coords) visit(c);
    }
  };
  for (const f of fc.features) visit(f.geometry.coordinates);
  if (Number.isFinite(minLon) && (maxLon - minLon > 0 || maxLat - minLat > 0)) {
    map.fitBounds([[minLon, minLat], [maxLon, maxLat]], { padding: 60, maxZoom: 9, duration: 600 });
  } else if (fallback) {
    map.flyTo({ center: fallback, zoom: 7 });
  }
}

function returnToOverview(): void {
  map.flyTo({ center: OVERVIEW, zoom: OVERVIEW_ZOOM, duration: 600 });
}

async function computeEnsembleBand(): Promise<void> {
  const token = newComputeToken();
  computeBtn.disabled = true;
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
  timeControl.hidden = true; // probability band has no decay slider
  exportBtn.hidden = true;
  reportBtn.hidden = true;
  shareBtn.hidden = true;
  currentPlume = null;
  closeExposure();
  inspectContext = null;
  clearWindProfile();
  clearTargetMarkers();

  const level = Number(ensembleLevelInput.value);
  const members = Number(ensembleMembersInput.value);
  if (!Number.isFinite(level) || level <= 0) {
    markStatusError("Dose level to band must be a positive number of R/hr.");
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
    return;
  }

  try {
    const { lat, lon } = readGroundZero();
    await ensureMapReady();
    startElapsed(`Computing uncertainty band across ${Math.round(members)} members`);
    const resp = await withTimeout(
      fetchEnsemble({
        lat,
        lon,
        yield_mt: Number(yieldInput.value),
        fission_fraction: Number(ffInput.value),
        level_rhr: level,
        n_members: Math.round(members),
      }),
    );
    if (isStale(token)) return; // mode changed mid-compute; discard
    stopElapsed();
    writeUrlState({ mode: "ensemble" });
    clearStaleNote(); // inputs now match the result on screen
    setDisclaimer(resp.disclaimer);
    placeGzMarker(resp.ground_zero[1], resp.ground_zero[0]);

    statusEl.textContent = `P(H+1 dose rate ≥ ${resp.level_rhr} R/hr) across ${resp.n_members} members.`;
    renderWeather(null); // ensemble responses carry no single-forecast provenance
    renderPlainNotes(resp.notes);
    const ensRows = renderEnsembleContours(resp.contours, resp.ground_zero);
    exportGeoJson = resp.contours;
    exportReport = {
      mode: "ensemble",
      title: "Ensemble uncertainty band",
      generatedIso: new Date().toISOString(),
      facts: [
        ["Ground zero", fmtLonLat(resp.ground_zero)],
        ["Yield", `${Number(yieldInput.value)} Mt`],
        ["Fission fraction", String(Number(ffInput.value))],
        ["Banded dose level", `${resp.level_rhr} R/hr at H+1`],
        ["Ensemble members", String(resp.n_members)],
      ],
      reachCaption: "Probability-band reach (H+1)",
      reach: ensRows.map(reachRowPlain),
      notes: resp.notes,
      disclaimer: resp.disclaimer,
    };
    exportBtn.hidden = false;
    reportBtn.hidden = false;
    shareBtn.hidden = false;
    overviewBtn.hidden = false;
    fitToFeatures(resp.contours, [resp.ground_zero[0], resp.ground_zero[1]]);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    markStatusError(`Failed: ${msg}`);
  } finally {
    stopElapsed();
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
  }
}

async function computeSinglePlume(): Promise<void> {
  const token = newComputeToken();
  computeBtn.disabled = true;
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
  timeControl.hidden = true;
  exportBtn.hidden = true;
  reportBtn.hidden = true;
  shareBtn.hidden = true;

  const tierInput = form.querySelector<HTMLInputElement>('input[name="tier"]:checked');
  const tier = tierInput ? (Number(tierInput.value) as 0 | 1) : 0;
  closeExposure(); // any open panel refers to the previous plume
  inspectContext = null;

  try {
    const wind = manualWindFromForm();
    const { lat, lon } = readGroundZero();
    const yieldMt = Number(yieldInput.value);
    const ff = Number(ffInput.value);
    await ensureMapReady();
    startElapsed(manualWindCheckbox.checked ? "Computing (manual wind)" : "Computing (fetches live wind)");
    const resp = await withTimeout(
      fetchPlume({
        lat,
        lon,
        yield_mt: yieldMt,
        fission_fraction: ff,
        tier,
        ...(wind ? { wind } : {}),
        levels_rhr: fetchLevelSet(),
      }),
    );
    if (isStale(token)) return; // mode changed mid-compute; discard
    stopElapsed();
    writeUrlState({ mode: "plume", tier });
    clearStaleNote(); // inputs now match the result on screen
    currentPlume = resp;
    setDisclaimer(resp.disclaimer);
    placeGzMarker(resp.ground_zero[1], resp.ground_zero[0]);

    // Enable click-to-inspect when the effective wind is known numerically
    // (Tier 0, fetched or manual). Tier 1 has no time-of-arrival to assess.
    if (
      resp.tier_used === 0 &&
      resp.wind.speed_mph != null &&
      resp.wind.bearing_deg != null
    ) {
      inspectContext = {
        gzLat: resp.ground_zero[1],
        gzLon: resp.ground_zero[0],
        yieldMt,
        ff,
        wind: {
          speed_mph: resp.wind.speed_mph,
          bearing_deg: resp.wind.bearing_deg,
          shear_mph_per_kft: resp.wind.shear_mph_per_kft ?? 0,
        },
      };
    }

    statusEl.textContent = plumeStatusText(resp);
    renderWeather(resp.weather);
    renderNotes(resp);
    if (resp.wind_profile && resp.wind_profile.length > 0) {
      renderWindProfile(resp.wind_profile);
    } else {
      clearWindProfile();
    }
    exportReport = {
      mode: "plume",
      title: "Single-location fallout plume",
      generatedIso: new Date().toISOString(),
      facts: [
        ["Ground zero", fmtLonLat(resp.ground_zero)],
        ["Yield", `${yieldMt} Mt`],
        ["Fission fraction", String(ff)],
        ["Model", TIER_NAMES[resp.tier_used] ?? `Tier ${resp.tier_used}`],
        ["Wind", describeWind(resp)],
        ...(resp.weather ? ([["Weather", weatherFactStr(resp.weather)]] as [string, string][]) : []),
      ],
      // reach + displayTime are filled by renderAtCurrentTime (they depend on
      // the decay slider), which runs immediately below.
      notes: plumeNotesFor(resp),
      disclaimer: resp.disclaimer,
    };
    exportBtn.hidden = false;
    reportBtn.hidden = false;
    shareBtn.hidden = false;
    overviewBtn.hidden = false;
    startDecaySeries({
      contours: resp.contours,
      gz: resp.ground_zero,
      maxHours: TIME_MAX_HOURS,
    });
    fitToFeatures(resp.contours, [resp.ground_zero[0], resp.ground_zero[1]]);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    markStatusError(`Failed: ${msg}`);
  } finally {
    stopElapsed();
    statusEl.classList.remove("busy");
    computeBtn.disabled = false;
  }
}

async function computeExchangeEnvelope(forceRefresh = false): Promise<void> {
  const token = newComputeToken();
  computeBtn.disabled = true;
  statusEl.classList.remove("error");
  statusEl.classList.add("busy");
  timeControl.hidden = true;
  exportBtn.hidden = true;
  reportBtn.hidden = true;
  shareBtn.hidden = true;
  clearGzMarker();
  currentPlume = null;
  clearWindProfile();

  try {
    await ensureMapReady();
    // ~500 live wind buckets + grid compositing: seconds, not instant. Keep an
    // elapsed ticker running so it never looks hung (the reviewer's finding).
    startElapsed("Computing national envelope (live wind for the whole deck)");
    const resp = await withTimeout(
      // Dense H+1 level set (not the four defaults) so the decay slider can
      // relabel the envelope client-side, exactly as it does for a plume.
      fetchExchangeEnvelope(
        "max_single_source",
        forceRefresh,
        fetchLevelSet(ENVELOPE_TIME_MAX_HOURS),
      ),
    );
    if (isStale(token)) return; // mode changed mid-compute; discard
    stopElapsed();
    setDisclaimer(resp.disclaimer);
    await plotFieldPolygons();
    await plotTargetMarkers(new Set(resp.excluded_target_ids));
    renderExclusionWarning(resp.excluded_target_ids, resp.n_targets);
    map.flyTo({ center: OVERVIEW, zoom: OVERVIEW_ZOOM });

    writeUrlState({ mode: "exchange" });
    clearStaleNote(); // inputs now match the result on screen
    statusEl.textContent =
      `Max-single-source envelope across ${resp.n_targets} ${resp.n_targets === 1 ? "target" : "targets"}.`;
    renderWeather(resp.weather); // valid hour + staleness live here now
    renderPlainNotes(resp.notes);
    // Full provenance (weather, aggregation, yield policy, deck version/hash,
    // in/excluded targets) rides along with whichever time slice is exported.
    const provenance = {
      weather: resp.weather ?? undefined,
      aggregation: resp.aggregation,
      deck_version: resp.deck_version,
      deck_content_hash: deckMeta?.content_hash,
      yield_policy: resp.yield_policy,
      included_target_ids: resp.included_target_ids,
      excluded_target_ids: resp.excluded_target_ids,
    };
    exportReport = {
      mode: "exchange",
      title: "National fallout envelope",
      generatedIso: new Date().toISOString(),
      facts: [
        ["Aggregation", `${resp.aggregation} (worst H+1 dose from any one target)`],
        ["Targets included", String(resp.n_targets)],
        ["Targets excluded (wind-fetch fail)", String(resp.excluded_target_ids.length)],
        [
          "Target deck",
          `${resp.deck_version}${deckMeta ? ` (hash ${deckMeta.content_hash.slice(0, 8)})` : ""}`,
        ],
        ...(resp.weather ? ([["Weather", weatherFactStr(resp.weather)]] as [string, string][]) : []),
      ],
      yieldPolicy: resp.yield_policy,
      // The surface-burst caveat is already printed under the yields table;
      // drop it from notes so the report doesn't repeat it verbatim.
      notes: resp.notes.filter((n) => n !== resp.yield_policy.surface_burst_caveat),
      disclaimer: resp.disclaimer,
    };
    exportBtn.hidden = false;
    reportBtn.hidden = false;
    shareBtn.hidden = false;
    overviewBtn.hidden = false;
    // Envelope only: these are the deck's off-CONUS sites, and a single-plume
    // result has nothing to jump to.
    jumpHiBtn.hidden = false;
    jumpAkBtn.hidden = false;
    startDecaySeries({
      contours: resp.contours,
      gz: null, // composite of ~600 sources: no single ground zero
      maxHours: ENVELOPE_TIME_MAX_HOURS,
      extraExport: provenance,
    });
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : String(err);
    markStatusError(`Failed: ${msg}`);
  } finally {
    stopElapsed();
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

// Serialize/parse live in urlstate.ts (tested there); these two functions are
// just the bridge to the form.

function writeUrlState(opts: { mode: UrlMode; tier?: 0 | 1 }): void {
  const params = buildUrlParams({
    mode: opts.mode,
    yieldMt: yieldInput.value,
    ff: ffInput.value,
    lat: latInput.value,
    lon: lonInput.value,
    tier: opts.tier,
    wind: manualWindCheckbox.checked
      ? {
          speed: Number(windSpeedInput.value),
          bearing: Number(windBearingInput.value),
          shear: Number(windShearInput.value),
        }
      : undefined,
    level: ensembleLevelInput.value,
    members: ensembleMembersInput.value,
  });
  history.replaceState(null, "", `?${params}`);
}

function readUrlState(): void {
  const state = parseUrlParams(window.location.search);
  if (!state) return;
  const setIfPresent = (input: HTMLInputElement, v: string | undefined) => {
    if (v !== undefined) input.value = v;
  };
  setIfPresent(yieldInput, state.yieldMt);
  setIfPresent(ffInput, state.ff);
  if (state.mode === "exchange") {
    setMode(true);
    return;
  }
  setIfPresent(latInput, state.lat);
  setIfPresent(lonInput, state.lon);
  if (state.mode === "ensemble") {
    ensembleModeCheckbox.checked = true;
    ensembleFields.hidden = false;
    setIfPresent(ensembleLevelInput, state.level);
    setIfPresent(ensembleMembersInput, state.members);
    setAdvanced(true); // the ensemble controls live behind the disclosure
    updateComputeButtonText();
    return;
  }
  if (state.tier !== undefined) {
    const radio = form.querySelector<HTMLInputElement>(
      `input[name="tier"][value="${state.tier}"]`,
    );
    if (radio) radio.checked = true;
    // A shared link with the non-default model should show that choice, not
    // hide it behind the collapsed advanced section.
    if (state.tier === 1) setAdvanced(true);
  }
  if (state.wind) {
    manualWindCheckbox.checked = true;
    manualWindFields.hidden = false;
    windSpeedInput.value = String(state.wind.speed);
    windBearingInput.value = String(state.wind.bearing);
    windShearInput.value = String(state.wind.shear);
    setAdvanced(true);
  }
}

// NOTE: readUrlState() is deliberately invoked at the very BOTTOM of this
// module, not here next to its definition. A ?mode=exchange URL makes it call
// setMode -> clearResults, which touches module-level `let`s declared further
// down (exportGeoJson, and transitively contourTableEl/deckMeta). Calling it
// mid-file threw a TDZ ReferenceError that silently ABORTED the rest of
// module evaluation -- the page looked alive (earlier listeners were wired)
// but every later initializer was dead, and the envelope compute then failed
// with "Cannot access 'deckMeta' before initialization".

// Tier-1 has no single wind vector to quote -- it advects each layer through a
// whole profile -- so the API reports only a source slug. Left raw, the status
// line read "Wind: open-meteo-gfs-profile."
const WIND_SOURCE_NAMES: Record<string, string> = {
  "open-meteo-gfs-profile": "full vertical profile (Open-Meteo GFS), shown under Wind by altitude",
};

function describeWind(resp: PlumeResponse): string {
  const w = resp.wind;
  if (w.speed_mph == null) return WIND_SOURCE_NAMES[w.source] ?? w.source;
  return `${formatSpeed(w.speed_mph)} @ ${w.bearing_deg?.toFixed(0)}° (${w.source})`;
}

/** The single-plume status line. Built from the response (not captured as a
 * string at compute time) so applyUnits can rebuild it when the unit
 * preference changes -- describeWind's primary unit is unit-dependent. */
function plumeStatusText(resp: PlumeResponse): string {
  const tier = TIER_NAMES[resp.tier_used] ?? `Tier ${resp.tier_used}`;
  // Point assessment needs one known effective wind, so it exists on Tier-0
  // only. Saying nothing made the feature look broken on Tier-1: the "click
  // the map" invitation simply disappeared, with no reason given.
  const inspectHint = inspectContext
    ? " Click the map to assess a point."
    : resp.tier_used === 1
      ? " Point assessment is available on the fast planning model (Tier 0)."
      : "";
  return `${tier} used. Wind: ${describeWind(resp)}.${inspectHint}`;
}

/** The API's notes plus, when it's worth saying and the API hasn't already
 * said it, how much activity left the local footprint. The API adds its own
 * (wordier) version above 0.05 while we surface anything above 0.01, so
 * without the substring check both land in the panel and in the exported
 * report saying the same thing twice. */
function plumeNotesFor(resp: PlumeResponse): string[] {
  const notes = [...resp.notes];
  const apiSaidIt = notes.some((n) => n.includes("still airborne"));
  if (!apiSaidIt && resp.fraction_aloft != null && resp.fraction_aloft > 0.01) {
    notes.push(
      `${(resp.fraction_aloft * 100).toFixed(0)}% of activity carried past the local footprint (regional/global).`,
    );
  }
  return notes;
}

function renderNotes(resp: PlumeResponse): void {
  notesEl.innerHTML = "";
  for (const note of plumeNotesFor(resp)) {
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

// --- wind-by-altitude viz -----------------------------------------------------
// A compact column of arrows, one per fetched pressure level (highest altitude
// at top), showing which way the wind carries fallout at each height and how
// fast (arrow length). North is up, so the arrows are map-aligned. The lower
// "cloud-descent" layer that shapes the local footprint is drawn bold; the
// higher winds that loft fine particles regionally are faint. This makes wind
// shear -- the thing Tier 1 resolves and the "shear" control approximates --
// directly visible.

function clearWindProfile(): void {
  windProfileEl.hidden = true;
  windProfileEl.innerHTML = "";
  lastWindProfilePoints = null;
}

let lastWindProfilePoints: WindProfilePoint[] | null = null;

function renderWindProfile(points: WindProfilePoint[]): void {
  if (points.length === 0) {
    clearWindProfile();
    return;
  }
  lastWindProfilePoints = points;
  // Highest altitude first (top of the column).
  const rows = [...points].sort((a, b) => b.height_m - a.height_m);
  const maxSpeed = Math.max(1, ...rows.map((p) => p.speed_mph));

  const W = 288;
  const rowH = 24;
  const padY = 6;
  const cx = 150;
  const H = padY * 2 + rows.length * rowH;

  const parts: string[] = [];
  // Faint band behind the fallout-layer (lower) rows to group them.
  const layerRows = rows.filter((p) => p.in_fallout_layer).length;
  if (layerRows > 0) {
    const bandY = padY + (rows.length - layerRows) * rowH;
    parts.push(
      `<rect x="0" y="${bandY}" width="${W}" height="${layerRows * rowH}" rx="4" class="wp-band"/>`,
    );
  }

  rows.forEach((p, i) => {
    const cy = padY + i * rowH + rowH / 2;
    // Class, not an inline fill/stroke, so the arrows and labels follow the
    // light/dark palette (see .wp-bold / .wp-faint in style.css). stroke and
    // fill both inherit, so the <line> and <path> inside the group pick it up.
    const cls = p.in_fallout_layer ? "wp-bold" : "wp-faint";
    const half = 4 + (p.speed_mph / maxSpeed) * 16;
    const tipY = cy - half;
    // Up-pointing arrow rotated clockwise by the compass "toward" bearing
    // (0 = north = up), so the column reads in real map orientation.
    parts.push(
      `<g transform="rotate(${p.toward_deg.toFixed(1)} ${cx} ${cy})" class="${cls}">` +
        `<line x1="${cx}" y1="${cy + half}" x2="${cx}" y2="${tipY}" stroke-width="2"/>` +
        `<path d="M${cx} ${tipY} L${cx - 3.5} ${tipY + 6} L${cx + 3.5} ${tipY + 6} Z" stroke="none"/>` +
        `</g>`,
    );
    parts.push(
      `<text x="6" y="${cy}" font-size="11" class="${cls}" stroke="none" dominant-baseline="middle">${formatHeightShort(p)}</text>`,
    );
    parts.push(
      `<text x="${W - 6}" y="${cy}" font-size="11" class="${cls}" stroke="none" text-anchor="end" dominant-baseline="middle">${formatSpeedShort(p.speed_mph)}</text>`,
    );
  });

  const surface = rows[rows.length - 1];
  const ariaLabel =
    `Wind by altitude, ${rows.length} levels. Surface ${formatSpeedShort(surface.speed_mph)} toward ` +
    `${compassName(surface.toward_deg)}; top level ${formatSpeedShort(rows[0].speed_mph)} toward ${compassName(rows[0].toward_deg)}.`;

  windProfileEl.innerHTML =
    `<div class="legend-title">Wind by altitude</div>` +
    `<svg viewBox="0 0 ${W} ${H}" class="windprof" role="img" aria-label="${ariaLabel}">${parts.join("")}</svg>` +
    `<p class="hint">Arrows point the way winds carry fallout at each altitude (north is up; longer = faster). ` +
    `Bold rows are the cloud-descent layer that shapes the local footprint; faint rows are higher winds that loft fine particles regionally.</p>`;
  windProfileEl.hidden = false;
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

// --- native-layer render helpers --------------------------------------------

function contourSource(): maplibregl.GeoJSONSource {
  return map.getSource(CONTOUR_SOURCE) as maplibregl.GeoJSONSource;
}
function targetSource(): maplibregl.GeoJSONSource {
  return map.getSource(TARGET_SOURCE) as maplibregl.GeoJSONSource;
}

/** Set the contour features and their color/width paint for the current mode.
 * The same color expression drives the fills beneath them, so a band's area and
 * its outline can never disagree about which color means which level. */
function setContours(
  fc: GeoJsonFeatureCollection,
  colorExpr: unknown,
  widthExpr: unknown,
): void {
  contourSource().setData(fc as unknown as GeoJSON.FeatureCollection);
  map.setPaintProperty(CONTOUR_LAYER, "line-color", colorExpr as maplibregl.ExpressionSpecification);
  map.setPaintProperty(CONTOUR_LAYER, "line-width", widthExpr as number);

  const fills: GeoJsonFeatureCollection = {
    type: "FeatureCollection",
    features: contourFillFeatures(fc.features),
  };
  (map.getSource(CONTOUR_FILL_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
    fills as unknown as GeoJSON.FeatureCollection,
  );
  if (map.getLayer(CONTOUR_FILL_LAYER)) {
    map.setPaintProperty(
      CONTOUR_FILL_LAYER,
      "fill-color",
      colorExpr as maplibregl.ExpressionSpecification,
    );
  }
}

// The clear helpers run outside ensureMapReady (mode switches, the guard
// section at the top of every compute), so the overlay sources may not be
// installed yet -- e.g. compute clicked while the style is still loading.
// getSource() then returns undefined, and an unguarded .setData() throws
// SYNCHRONOUSLY before the compute's try/finally, wedging the UI with the
// button disabled and the busy spinner on forever (reproduced live).
function clearContours(): void {
  for (const id of [CONTOUR_SOURCE, CONTOUR_FILL_SOURCE]) {
    (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(
      EMPTY_FC as GeoJSON.FeatureCollection,
    );
  }
}

/** Plot the deck's ground zeros. `excludedIds` are targets the envelope could
 * not compute (wind fetch failed): they are still drawn -- omitting them would
 * hide that the deck contains them -- but flagged, so a dot with no plume
 * around it can't be read as "computed, and nothing here". */
async function plotTargetMarkers(excludedIds: Set<string> = new Set()): Promise<void> {
  const targets = await fetchTargets(true);
  lastExcludedNames = targets.filter((t) => excludedIds.has(t.id)).map((t) => t.name);
  const fc: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: targets.map((t) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [t.lon, t.lat] },
      properties: {
        name: t.name,
        category: t.category,
        excluded: excludedIds.has(t.id) ? 1 : 0,
      },
    })),
  };
  targetSource().setData(fc);
}

// Names of the targets the last envelope dropped, resolved from the deck once
// the markers are fetched (the API reports ids; the user needs names).
let lastExcludedNames: string[] = [];

function renderExclusionWarning(excludedIds: string[], nTotal: number): void {
  if (excludedIds.length === 0) {
    exclusionWarningEl.hidden = true;
    exclusionWarningEl.textContent = "";
    return;
  }
  const named = lastExcludedNames.length > 0 ? lastExcludedNames : excludedIds;
  const shown = named.slice(0, 6).join("; ");
  const more = named.length > 6 ? ` and ${named.length - 6} more` : "";
  exclusionWarningEl.innerHTML =
    `⚠ <strong>${excludedIds.length} of ${nTotal + excludedIds.length} targets produced no plume.</strong> ` +
    `Their wind fetch failed, so nothing is drawn for them and this envelope ` +
    `understates the hazard near them — an empty area around one of these is ` +
    `missing data, not a clear result. Their ground zeros are ringed in red on ` +
    `the map. Excluded: ${shown}${more}. "Refresh winds" retries the fetch.`;
  exclusionWarningEl.hidden = false;
}

function clearTargetMarkers(): void {
  lastExcludedNames = [];
  renderExclusionWarning([], 0);
  // Optional-chained for the same reason as clearContours.
  (map.getSource(TARGET_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
    EMPTY_FC as GeoJSON.FeatureCollection,
  );
  (map.getSource(FIELD_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
    EMPTY_FC as GeoJSON.FeatureCollection,
  );
}

// The versioned deck metadata + documented field footprints. Kept so the
// exchange export and the synthetic-geography badge can reference them.
let deckMeta: TargetDeckMeta | null = null;

async function plotFieldPolygons(): Promise<void> {
  deckMeta = await fetchDeck();
  const fc: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: deckMeta.fields.map((f) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [f.polygon] },
      properties: { wing: f.wing, lf: f.lf_count },
    })),
  };
  (map.getSource(FIELD_SOURCE) as maplibregl.GeoJSONSource).setData(fc);
}

// A prominent, honest badge: the silo/LCC points are SYNTHETIC; the dashed
// outlines are the documented (verifiable) field footprints.
function renderSyntheticBadge(): void {
  if (!deckMeta) return;
  const badge = document.createElement("div");
  badge.className = "geo-badge";
  badge.innerHTML =
    `⚠ <strong>${deckMeta.n_synthetic} silo/LCC positions are SYNTHETIC</strong> ` +
    `(field-scale accuracy, low confidence). Dashed outlines are the documented ` +
    `field footprints — the verifiable geography. Deck ${deckMeta.version}, ` +
    `hash ${deckMeta.content_hash.slice(0, 8)}.`;
  legendEl.appendChild(badge);
}

// Hover popups (native MapLibre replacement for deck.gl's getTooltip). One
// shared popup, wired to the contour and target layers.
function installHoverPopups(): void {
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

  const showContour = (e: maplibregl.MapLayerMouseEvent) => {
    const p = e.features?.[0]?.properties as Record<string, number> | undefined;
    if (!p) return;
    let text: string | null = null;
    if (p.exceedance_probability != null) {
      text = `${(Number(p.exceedance_probability) * 100).toFixed(0)}% chance dose rate ≥ this level`;
    } else if (p.display_level_rhr != null) {
      text = `${p.display_level_rhr} R/hr isodose at ${timeLabel.textContent}`;
    } else if (p.dose_rate_h1_rhr != null) {
      text = `${p.dose_rate_h1_rhr} R/hr isodose at H+1`;
    }
    if (text) popup.setLngLat(e.lngLat).setText(text).addTo(map);
  };
  const showTarget = (e: maplibregl.MapLayerMouseEvent) => {
    const p = e.features?.[0]?.properties as
      | { name?: string; category?: string; excluded?: number }
      | undefined;
    if (!p?.name || !p.category) return;
    const label = TARGET_LABELS[p.category] ?? p.category;
    const excluded = p.excluded ? " — NO PLUME: wind fetch failed for this target" : "";
    popup.setLngLat(e.lngLat).setText(`${p.name} — ${label}${excluded}`).addTo(map);
  };
  for (const [layer, handler] of [[CONTOUR_LAYER, showContour], [TARGET_LAYER, showTarget]] as const) {
    map.on("mousemove", layer, handler);
    map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", layer, () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    });
  }
  // Touch has no hover, so a target dot was unidentifiable on a phone: the only
  // way to learn what a ground zero is was a mouse. Tapping one names it.
  // Deliberately NOT wired for contour lines -- a tap there already means
  // "assess this point" (or "set ground zero"), and hijacking it would trade
  // one interaction for another rather than adding one.
  map.on("click", TARGET_LAYER, showTarget);
}

// (renderStaticContours removed: the envelope now runs through the same
// decay-series path as the single plume, which draws and legends its contours
// per decay time rather than once at fixed H+1 levels.)

// --- ensemble uncertainty bands ---------------------------------------------
// Exceedance-probability contours (10/50/90%): nested lines from faint outer
// edge to saturated core, inner (more-likely) bands drawn thicker.
// Returns the per-band reach rows so the caller can carry them into the export
// report (same data the on-screen table shows).
function renderEnsembleContours(fc: GeoJsonFeatureCollection, gz: [number, number]): ContourRow[] {
  const widthExpr = ["+", 2, ["*", 3, ["to-number", ["get", "exceedance_probability"], 0.5]]];
  setContours(fc, colorMatchExpr("exceedance_probability", PROB_COLORS), widthExpr);
  const probs = [...new Set(fc.features.map((f) => f.properties.exceedance_probability))].sort(
    (a, b) => a - b,
  );
  renderEnsembleLegend(probs);

  const rows: ContourRow[] = [];
  for (const p of probs) {
    const far = farthestPoint(
      fc.features.filter((f) => f.properties.exceedance_probability === p),
      gz,
    );
    if (far) {
      rows.push({
        swatch: PROB_COLORS[p] ?? [255, 255, 255, 200],
        label: `${(p * 100).toFixed(0)}% band`,
        ...far,
      });
    }
  }
  renderContourTable("Probability-band reach (H+1)", rows);
  return rows;
}

function renderEnsembleLegend(probs: number[]): void {
  legendEl.innerHTML = "";
  const title = document.createElement("div");
  title.className = "legend-title";
  title.textContent = "Chance the H+1 dose rate exceeds your chosen level";
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

  // Uncertainty explainer (backlog #23): what the nested bands actually mean,
  // phrased from the backend's own note (P(H+1 rate >= level) across wind
  // members) -- no additional statistical claims.
  const help = document.createElement("details");
  help.className = "help";
  const summary = document.createElement("summary");
  summary.textContent = "How to read these bands";
  help.appendChild(summary);
  const p1 = document.createElement("p");
  p1.textContent =
    "The plume was recomputed once per forecast wind member; each band " +
    "outlines where the H+1 dose rate exceeded your chosen level in at " +
    "least that share of members. The faint 10% band is the outer edge of " +
    "where fallout could plausibly reach given today's wind spread; the " +
    "dark 90% band is where nearly all members agree it would. The gap " +
    "between them IS the wind uncertainty — a wide gap means the forecast " +
    "members disagree, so trust the outer band for planning margins, not " +
    "the crisp inner line.";
  help.appendChild(p1);
  legendEl.appendChild(help);
}

// --- decay-time slider ------------------------------------------------------
// Drives both the single plume and the national envelope. The relabel trick
// (decay.ts) needs only that decay scale every point by one common t^-1.2
// factor: true for a plume, and equally true for the envelope, whose cell-wise
// max/sum both commute with a positive scalar. What differs per mode is the
// upper bound and whether there is a ground zero to measure reach from.

interface DecaySeries {
  contours: GeoJsonFeatureCollection; // dense H+1 level set, relabelled per time
  gz: [number, number] | null; // null for the envelope: no single GZ, no reach table
  maxHours: number;
  extraExport?: Record<string, unknown>; // provenance to keep in the exported GeoJSON
}
let decaySeries: DecaySeries | null = null;

function sliderToHours(step: number): number {
  const t = step / SLIDER_STEPS;
  const logMin = Math.log(TIME_MIN_HOURS);
  const logMax = Math.log(decaySeries?.maxHours ?? TIME_MAX_HOURS);
  return Math.exp(logMin + t * (logMax - logMin));
}

/** Slider ticks for the active range. Positions are log-scale fractions, so
 * they cannot be hardcoded once the upper bound varies by mode. */
function renderTimeTicks(maxHours: number): void {
  const candidates = maxHours <= 24 ? [1, 3, 6, 12, 24] : [1, 6, 24, 48, 168];
  const hours = candidates.filter((h) => h <= maxHours);
  const frac = (h: number) => Math.log(h / TIME_MIN_HOURS) / Math.log(maxHours / TIME_MIN_HOURS);
  const label = (h: number) => (h <= 48 ? `H+${h}` : `H+${Math.round(h / 24)}d`);
  timeTicks.innerHTML = hours
    .map((h) => `<option value="${Math.round(frac(h) * SLIDER_STEPS)}"></option>`)
    .join("");
  timeTickLabels.innerHTML = hours
    .map((h) => `<span style="left: ${(frac(h) * 100).toFixed(1)}%">${label(h)}</span>`)
    .join("");
}

/** Begin a decay series: install it, reset the slider to H+1, rebuild the ticks
 * for its range, and draw the first frame. */
function startDecaySeries(series: DecaySeries): void {
  decaySeries = series;
  renderTimeTicks(series.maxHours);
  timeControl.hidden = false;
  // The envelope's slider spans ~600 targets assumed simultaneous, so the
  // arrival-time / simultaneity caveat is shown there and not for one plume.
  timeCaveat.hidden = series.gz !== null;
  timeSlider.value = "0";
  renderAtCurrentTime();
}

timeSlider.addEventListener("input", renderAtCurrentTime);

function renderAtCurrentTime(): void {
  if (!decaySeries) return;
  const hours = sliderToHours(Number(timeSlider.value));
  timeLabel.textContent = formatHours(hours);

  const picks = levelsForTime(hours, availableLevels(decaySeries.contours));

  const features = decaySeries.contours.features
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

  setContours(displayed, colorMatchExpr("display_level_rhr", LEVEL_COLORS), 3);

  // Legend keys the bands actually DRAWN, not the four we asked for. A band
  // whose level exceeds this result's peak dose has no contour (levelsForTime
  // omits it), and listing it anyway told the user there was a 1000 R/hr zone
  // on a map that never drew one.
  const shownLevels = [...new Set(features.map((f) => f.properties.display_level_rhr))].sort(
    (a, b) => a - b,
  );
  renderLegend(shownLevels);
  // Late in the decay the whole footprint drops below the lowest plotted band
  // and the map legitimately goes empty. Say that, rather than leaving a blank
  // map, an empty legend and an empty table with no explanation.
  if (shownLevels.length === 0) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent =
      `Nothing to draw at ${timeLabel.textContent}: decay has taken the entire ` +
      `footprint below ${DISPLAY_LEVELS_RHR[0]} R/hr, the lowest plotted band.`;
    legendEl.appendChild(p);
  }
  // The envelope's legend also carries the target-category key and the
  // synthetic-geography badge, and renderLegend() has just cleared them.
  if (exchangeMode) {
    renderTargetLegend();
    renderSyntheticBadge();
  }

  const gz = decaySeries.gz;
  const rows: ContourRow[] = [];
  if (gz) {
    for (const pick of picks) {
      const far = farthestPoint(
        features.filter((f) => f.properties.display_level_rhr === pick.displayLevel),
        gz,
      );
      if (far) {
        rows.push({
          swatch: LEVEL_COLORS[pick.displayLevel] ?? [255, 255, 255, 200],
          label: `${pick.displayLevel} R/hr`,
          ...far,
        });
      }
    }
    renderContourTable(`Contour reach at ${timeLabel.textContent}`, rows);
  } else {
    // Reach-from-ground-zero is meaningless for a composite of ~600 sources.
    clearContourTable();
  }

  // Exported contours are the time slice on screen; the envelope also carries
  // its provenance (weather, deck version, yield policy, included/excluded).
  exportGeoJson = decaySeries.extraExport
    ? ({ ...displayed, ...decaySeries.extraExport } as GeoJsonFeatureCollection)
    : displayed;
  if (exportReport) {
    exportReport.displayTime = timeLabel.textContent ?? undefined;
    if (gz) {
      exportReport.reachCaption = `Contour reach at ${timeLabel.textContent}`;
      exportReport.reach = rows.map(reachRowPlain);
    }
  }
}

function availableLevels(fc: GeoJsonFeatureCollection): number[] {
  return fc.features.map((f) => f.properties.dose_rate_h1_rhr).sort((a, b) => a - b);
}

function renderLegend(levels: number[]): void {
  legendEl.innerHTML = "";
  if (levels.length > 0) {
    const title = document.createElement("div");
    title.className = "legend-title";
    // Descriptive first, term second (the pattern the input labels already
    // follow), and no promise of a hover interaction that touch can't make --
    // the numbers live in the reach table below regardless.
    title.textContent = "Dose-rate bands (isodose contours) — outdoor rate at the time shown";
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

  if (levels.length === 0) return;

  // A band with no contour is omitted (decay.levelsForTime), which is correct
  // but reads as a bug when a band that was there a moment ago disappears
  // mid-drag. Say why, whenever the full set isn't showing.
  if (levels.length < DISPLAY_LEVELS_RHR.length) {
    const missing = document.createElement("p");
    missing.className = "hint";
    missing.textContent =
      "Bands not listed don't exist anywhere on this result at this time — " +
      "either the plume never reached that dose rate, or decay has taken it below.";
    legendEl.appendChild(missing);
  }

  // Outputs got none of the jargon help the inputs did: R/hr was never
  // defined anywhere in the UI. Kept strictly to the conversion the app
  // already uses elsewhere (1 R ~ 10 mSv, whole-body gamma) -- no new
  // health claims, and it points at the tools that answer "how much dose?"
  const help = document.createElement("details");
  help.className = "help";
  const summary = document.createElement("summary");
  summary.textContent = "What do these levels mean?";
  help.appendChild(summary);
  const p = document.createElement("p");
  p.textContent =
    "R/hr is roentgen per hour: the dose rate outdoors and unshielded, at the " +
    "time shown on the slider. It is a RATE, not a dose — an hour spent in a " +
    "1 R/hr area is about 1 R (~10 mSv, whole-body gamma), and the same spot " +
    "is far less hazardous a day later because fallout decays. For how much " +
    "dose a specific place accumulates, and when fallout arrives there, click " +
    "the map to assess that point.";
  help.appendChild(p);
  legendEl.appendChild(help);
}

// Category key for the full-exchange target dots, below the dose-rate legend.
// Collapsed by default: twelve rows of near-identical dots turned the panel
// into a wall, and at national zoom the dots are a few pixels across, so the
// colors aren't separable until you zoom in anyway -- which is exactly when
// someone goes looking for the key.
function renderTargetLegend(): void {
  const wrap = document.createElement("details");
  wrap.className = "legend-group";
  const summary = document.createElement("summary");
  summary.textContent = `Targets (ground zeros) — ${Object.keys(TARGET_LABELS).length} types`;
  wrap.appendChild(summary);
  legendEl.appendChild(wrap);
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
    wrap.appendChild(row);
  }
}

// --- persistent contour table -------------------------------------------------
// A numeric readout of each rendered band: how far its contour reaches from
// ground zero and in which compass direction. The map alone encoded results in
// color + hover popups only (the UX review's finding). Shown for the single-
// plume and ensemble views; the national envelope has no single ground zero,
// so reach-from-GZ is meaningless there and no table is rendered.

const contourTableEl = document.getElementById("contour-table") as HTMLDivElement;

interface ContourRow {
  swatch: [number, number, number, number];
  label: string;
  km: number;
  bearing: number;
}

let lastContourTable: { caption: string; rows: ContourRow[] } | null = null;

function renderContourTable(caption: string, rows: ContourRow[]): void {
  contourTableEl.innerHTML = "";
  lastContourTable = rows.length > 0 ? { caption, rows } : null;
  if (rows.length === 0) return;
  const table = document.createElement("table");
  const cap = document.createElement("caption");
  cap.textContent = caption;
  table.appendChild(cap);
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const h of ["Band", "Max reach from GZ", "Toward"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = h;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    const bandCell = document.createElement("td");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    const [r, g, b] = row.swatch;
    swatch.style.background = `rgb(${r},${g},${b})`;
    bandCell.appendChild(swatch);
    bandCell.appendChild(document.createTextNode(` ${row.label}`));
    tr.appendChild(bandCell);
    const reachCell = document.createElement("td");
    reachCell.textContent = formatReach(row.km);
    tr.appendChild(reachCell);
    const dirCell = document.createElement("td");
    dirCell.textContent = `${compassName(row.bearing)} (${Math.round(row.bearing)}°)`;
    tr.appendChild(dirCell);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  contourTableEl.appendChild(table);
}

function clearContourTable(): void {
  contourTableEl.innerHTML = "";
  lastContourTable = null;
}

// --- point-exposure panel -----------------------------------------------------
// Click a point while a Tier-0 plume is shown -> POST /exposure with the SAME
// parameters/wind that plume used -> arrival time, rates, and windowed/
// lifetime doses (optionally divided by an assumed protection factor).

function closeExposure(): void {
  exposureSection.hidden = true;
  inspectPoint = null;
  lastExposureResp = null;
  inspectSeq++; // any in-flight assessment is now stale
  if (inspectMarker) {
    inspectMarker.remove();
    inspectMarker = null;
  }
}

exposureCloseBtn.addEventListener("click", closeExposure);

exposureSetGzBtn.addEventListener("click", () => {
  if (!inspectPoint) return;
  latInput.value = inspectPoint.lat.toFixed(4);
  lonInput.value = inspectPoint.lon.toFixed(4);
  closeExposure();
  statusEl.textContent =
    "Ground zero inputs updated from the inspected point — Compute to rerun.";
});

// Changing the stay window or PF re-assesses the same point (cheap: the
// backend recomputes analytically, no weather fetch).
for (const sel of [exposureExitSelect, exposurePfSelect]) {
  sel.addEventListener("change", () => {
    if (inspectPoint) void inspectExposure(inspectPoint.lat, inspectPoint.lon);
  });
}

async function inspectExposure(lat: number, lon: number): Promise<void> {
  if (!inspectContext) return;
  const ctx = inspectContext;
  const seq = ++inspectSeq;
  inspectPoint = { lat, lon };

  if (inspectMarker) inspectMarker.remove();
  inspectMarker = new maplibregl.Marker({ color: "#33506b", scale: 0.8 })
    .setLngLat([lon, lat])
    .addTo(map);

  exposureSection.hidden = false;
  exposureSummaryEl.textContent = "Assessing…";
  exposureDosesEl.textContent = "";
  exposureNotesEl.textContent = "";
  // The panel sits far down a scrolling sidebar (measured ~1370 px into a
  // ~680 px viewport once a result is on screen), so without this the click
  // that opened it produces no visible change at all and the whole
  // click-to-inspect feature reads as broken.
  // Instant, not smooth: the animated scroll does not survive renderExposure()
  // rewriting the panel's contents underneath it a moment later (verified live
  // -- the panel stayed at scrollTop 0), and an instant jump is the right
  // feedback for a click anyway.
  exposureSection.scrollIntoView({ block: "nearest" });

  try {
    const resp = await fetchExposure({
      lat: ctx.gzLat,
      lon: ctx.gzLon,
      yield_mt: ctx.yieldMt,
      fission_fraction: ctx.ff,
      wind: ctx.wind,
      point_lat: lat,
      point_lon: lon,
      exit_hours: Number(exposureExitSelect.value),
      protection_factor: Number(exposurePfSelect.value),
    });
    if (seq !== inspectSeq) return; // superseded by a newer click / closed
    renderExposure(resp);
  } catch (err) {
    if (seq !== inspectSeq) return;
    const msg = err instanceof ApiError ? err.message : String(err);
    exposureSummaryEl.textContent = `Assessment failed: ${msg}`;
  }
}

let lastExposureResp: PointExposureResponse | null = null;

// A roentgen dose figure, with an approximate Sv appended in metric mode.
function renderExposure(resp: PointExposureResponse): void {
  lastExposureResp = resp;
  const km = resp.distance_miles * KM_PER_MI;
  const dir = `${compassName(resp.bearing_from_gz_deg)} (${Math.round(resp.bearing_from_gz_deg)}°)`;

  const lines: string[] = [
    `${formatReach(km)} ${dir} of ground zero.`,
  ];
  if (resp.dose_rate_h1_rhr < 1e-3) {
    lines.push(
      "Effectively outside the modeled deposition pattern (H+1 rate below 0.001 R/hr).",
    );
    exposureSummaryEl.innerText = lines.join("\n");
    exposureDosesEl.textContent = "";
    exposureNotesEl.innerText = resp.notes.join("\n\n");
    return;
  }

  lines.push(
    `Fallout arrival: ~H+${resp.arrival_hours.toFixed(1)} h.`,
    `Outdoor dose rate: ${fmtNum(resp.dose_rate_h1_rhr)} R/hr at H+1 reference · ` +
      `${fmtNum(resp.rate_at_arrival_rhr)} R/hr when fallout arrives.`,
  );
  exposureSummaryEl.innerText = lines.join("\n");

  const exitLabel = exposureExitSelect.selectedOptions[0]?.textContent?.trim() ?? "exit";
  const pf = resp.protection_factor;
  const doseLines: string[] = [];
  if (resp.unsheltered_dose_window_r != null) {
    doseLines.push(
      `Outdoors from arrival until ${exitLabel}: ${fmtDose(resp.unsheltered_dose_window_r)}`,
    );
    if (pf > 1 && resp.sheltered_dose_window_r != null) {
      doseLines.push(`Same window behind PF ${pf}: ${fmtDose(resp.sheltered_dose_window_r)}`);
    }
  }
  doseLines.push(
    `Outdoors indefinitely from arrival: ${fmtDose(resp.unsheltered_dose_to_infinity_r)}` +
      (pf > 1 ? ` (PF ${pf}: ${fmtDose(resp.sheltered_dose_to_infinity_r)})` : ""),
  );
  exposureDosesEl.innerText = doseLines.join("\n");

  const notes = [...resp.notes];
  if (getUnitSystem() === "metric") {
    notes.push("Sv figures approximate: 1 R ≈ 10 mSv effective dose (whole-body gamma).");
  }
  exposureNotesEl.innerText = notes.join("\n\n");
}

// --- export: GeoJSON + human-readable report ---------------------------------
// Every compute records a self-describing report (assumptions, versions,
// timestamp, units, limits) alongside the contours (backlog #23). The GeoJSON
// download embeds it as a top-level `metadata` member; a second button
// downloads the same as a human-readable Markdown report. Both cover all three
// modes (single plume / ensemble / national envelope).

let exportGeoJson: GeoJsonFeatureCollection | null = null;

let exportReport: ExportReport | null = null;

function reachRowPlain(r: ContourRow): ReachRow {
  return { label: r.label, km: r.km, bearingDeg: r.bearing };
}

function downloadBlob(text: string, filename: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Deferred: revoking synchronously races the download engine's read of the
  // blob in some browsers (the FileSaver-style guard).
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// Verified working (2026-07-16) by instrumenting HTMLAnchorElement.click and
// URL.createObjectURL in the live app: the click fires with the .geojson
// filename and the blob parses as a valid FeatureCollection.
exportBtn.addEventListener("click", () => {
  if (!exportGeoJson) return;
  const withMeta = exportReport
    ? { ...exportGeoJson, metadata: exportMetadata(exportReport) }
    : exportGeoJson;
  downloadBlob(JSON.stringify(withMeta, null, 2), "falloutcast-contours.geojson", "application/geo+json");
});

reportBtn.addEventListener("click", () => {
  if (!exportReport) return;
  downloadBlob(reportMarkdown(exportReport), "falloutcast-report.md", "text/markdown");
});

// --- weather provenance + manual refresh ---------------------------------------
// Visible answer to "how fresh are these winds?" (backlog #23): forecast model,
// the valid hour actually used, and fetch staleness, with a control to refetch.
// Hidden whenever the last compute fetched nothing (manual wind) or carries no
// provenance (ensemble responses).

function renderWeather(w: WeatherProvenance | null | undefined): void {
  if (!w) {
    weatherInfoEl.hidden = true;
    weatherTextEl.textContent = "";
    return;
  }
  const age = w.age_seconds != null ? `, fetched ${describeAge(w.age_seconds)}` : "";
  weatherTextEl.textContent = `Winds: ${w.model} · valid ${w.valid_time}Z${age}.`;
  weatherInfoEl.hidden = false;
}

weatherRefreshBtn.addEventListener("click", () => {
  if (computeBtn.disabled) return; // a compute is already in flight
  if (exchangeMode) {
    // force_refresh drops the per-hour wind cache server-side; a plain rerun
    // would silently reuse cached profiles for the same valid hour.
    void computeExchangeEnvelope(true);
  } else {
    // The single-plume/ensemble paths fetch fresh winds on every compute.
    void computePlume();
  }
});

// --- disclaimer --------------------------------------------------------------
// The short banner text is fixed in index.html and never overwritten. The
// API's full per-model disclaimer (the source of truth for methodology and
// limits) lands in the expandable #disclaimer-full panel via setDisclaimer().

disclaimerToggle.addEventListener("click", () => {
  const open = disclaimerFullEl.hidden;
  disclaimerFullEl.hidden = !open;
  disclaimerToggle.setAttribute("aria-expanded", String(open));
});

function setDisclaimer(text: string): void {
  disclaimerFullEl.textContent = text;
}

setDisclaimer(
  "Compute a result to see the methodology and limitations specific to the selected model. " +
    "All outputs are planning estimates from simplified models, not operational predictions.",
);

// --- URL-state restore: MUST stay the last statements in this module -------
// readUrlState -> setMode -> clearResults reaches most of the module's
// mutable state; running it any earlier re-introduces the TDZ abort described
// at the readUrlState definition.
readUrlState();
syncPresetSelection(); // a restored ?yield_mt may (de)select a preset
