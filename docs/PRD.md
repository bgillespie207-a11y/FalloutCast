# FalloutCast — Product Requirements & Spec

## 1. Overview

FalloutCast visualizes how nuclear fallout would travel over the continental US
under current weather conditions. It models ground-level dose-rate contours for
a surface burst and supports two modes: a single detonation at an arbitrary
point, and an overlay across a set of known public strategic installations.

The framing is deliberately civil-defense/educational — the same question
FEMA, NUKEMAP, and NOAA's HYSPLIT address: *given a detonation, where does the
fallout go and where is it survivable.* It is not a weapon-design or targeting
tool, and the assumptions (surface burst for maximum fallout, public site
locations) reflect that framing.

## 2. Goals / Non-goals

**Goals**
- Fast, current-weather-driven fallout footprints for CONUS.
- Honest uncertainty: outputs clearly labeled as planning estimates.
- A clean physics core that can be swapped from analytic (Tier-0) to
  multi-layer (Tier-1) to full Lagrangian (Tier-2) behind one API.

**Non-goals**
- Weaponeering, yield optimization, height-of-burst optimization, or anything
  that increases lethality. Out of scope by design.
- Air-burst blast/thermal effects (negligible local fallout; different tool).
- Real-world operational or emergency-response use.

## 3. Users

Primary: people interested in nuclear-effects education, preparedness, and
arms-control analysis. Secondary: the builder's own OSINT/analysis workflows
(GeoJSON export is a first-class output for that reason).

## 4. Modes

### 4.1 Single detonation
Input: lat/lon, yield (Mt), fission fraction, surface burst. Output: isodose
contours (default 1 / 10 / 100 / 1000 R/hr at H+1), the effective wind used,
and a disclaimer.

### 4.2 Exchange (multi-target)
Overlay fallout from the public CONUS target set under current winds. **v1
semantics** (`POST /exchange`, unchanged): each target is modeled
independently with its own local wind and the contour sets are returned
together. This is an overlay, not a summed national dose surface — stated
plainly so it is not mistaken for more than it is.

**M2 (done):** `POST /exchange/envelope` composites all targets onto one
shared CONUS grid and takes the cell-wise max H+1 dose rate across targets,
contouring that single field — a true national max-envelope surface, not an
overlay. Each target still gets its own live wind; a target whose wind fetch
fails is excluded (not fatal to the request) and named in the response notes.

**M2.5 (done):** expanded target deck (`targetdeck.py`, `?expanded=true`, now
the envelope default). The three Minuteman fields are resolved to their
individual launch facilities/control centers (150 LF + 15 LCC per wing, real
structure; positions are an illustrative distribution within the documented
field footprint, **not** surveyed coordinates — see `docs/TARGET_DECK.md`),
plus curated public high-value targets (population, industry, government C2):
~537 ground zeros total. Scaling that needed two fixes: wind is fetched **once
per ~1° bucket, concurrently** (not once per target) and each target's dose is
composited only within a **local window** of its ground zero
(`grid.sample_envelope(radius_deg=...)`). Full deck with live wind runs end to
end in ~5–6 s. Still no caching (see M2 note above / TARGET_DECK.md §1).

## 5. Modeling tiers

| Tier | Engine | Weather use | Status |
|------|--------|-------------|--------|
| 0 | WSEG-10 analytic smearing | single effective wind + scalar shear | **done** |
| 1 | Multi-layer particle advection | full vertical wind profile; shear curves the plume | **done** |
| 2 | HYSPLIT (Lagrangian) | ingested GFS/HRRR GRIB | optional backend (M3) |

Tier-0 is the shippable baseline and validation reference. Tier-1 is the
product's actual identity: binning particles by fall speed and advecting each
bin down through the Open-Meteo pressure-level winds is what makes "current
weather reshapes the plume" *true* rather than decorative. Tier-2 is authoritative
but carries an ops burden (registered HYSPLIT binary + met-ingestion pipeline;
the free web path cannot compute concentrations with forecast met), so it slots
behind the same API rather than blocking launch.

## 6. Data sources

- **Winds:** Open-Meteo GFS/HRRR — free, keyless (non-commercial), US
  high-resolution HRRR, winds at pressure levels + geopotential heights. Network
  access is isolated in `weather/openmeteo.fetch_profile`; the reduction to
  effective wind is pure and offline-testable.
- **Target set:** curated public GeoJSON (`data/targets_conus.geojson`),
  versioned; approximate coordinates from public sources.
- **Physics constants:** Hanifen 1980 (WSEG-10); Glasstone & Dolan (decay/dose).

## 7. Functional requirements

1. Compute single-detonation isodose contours from lat/lon + yield + wind.
2. Fetch current winds automatically; allow manual wind override.
3. Reject air bursts (out of scope) with a clear message.
4. Return effective wind actually used, plus the run/source, in every response.
5. Serve the public target set.
6. Exchange overlay across all targets under current winds.
7. GeoJSON output usable directly in any web map or GIS.
8. (M1) Time-evolution: dose rate + accumulated dose at H+t via the decay module.

## 8. Non-functional requirements

- **Honesty first:** every response carries a planning-estimate disclaimer and
  the wind used; contour bands are order-of-magnitude, not truth. This is the
  single most important NFR.
- **Performance:** Tier-0 single plume is sub-second. Tier-1 grids are the cost
  center — cache on `(target, yield, burst, met_run)`; GFS refreshes ~4×/day,
  HRRR hourly, so key caches to the run, not wall-clock.
- **Terrain caveat** surfaced in-product (flat-terrain assumption).
- **Separation of concerns:** physics has no I/O; weather has the only network
  call; API is thin.

## 9. API surface (v0.1)

- `GET /health` — liveness.
- `GET /targets` — public target set.
- `POST /plume` — single-detonation contours. Body: lat, lon, yield_mt,
  fission_fraction, surface_burst, optional wind override, optional levels.
- `POST /exchange` — target overlay (yield_mt, fission_fraction query params).
- `POST /exchange/envelope` — true national max-envelope dose surface, same
  query params, one composite GeoJSON contour set instead of N per-target ones.
- `POST /dose`, `POST /ensemble` — time-evolution and wind-ensemble endpoints
  (M1/M1.5, not listed above when this section was first written).

## 10. Roadmap / milestones

- **M0 (done):** Tier-0 engine, decay, contours, wind feed, API, tests.
- **M1 (done):** Tier-1 multi-layer advection (atmosphere + Best-number fall
  velocity + lognormal bins + puff advection); `/plume?tier=1`; aloft-fraction
  reporting; shear-curvature capability test.
- **M1.5 (done, with two flagged gaps):** ensemble-wind uncertainty band —
  `/ensemble` runs Tier-1 over real Open-Meteo GFS-ensemble members (31:
  control + 30 perturbed; falls back to synthetic perturbation only if that
  fetch fails) and contours P(dose ≥ level) at 10/50/90%; `/dose`
  time-evolution endpoint; dose calibrated to Glasstone & Dolan and size
  distribution grounded in DELFIC (σ_ln ≈ ln 2). DELFIC-style fractionation
  rule (refractory/volume ∝ d³ vs volatile/surface ∝ d² activity split) is
  implemented in `sizedist.py` behind the existing `SizeBins` interface,
  opt-in via `fractionation=`; the refractory/volatile partition coefficient
  itself is a flagged `PLACEHOLDER` pending a sourced DELFIC/Freiling value,
  so fractionated output is directionally validated (structural tests) but
  not quantitatively calibrated by default. **Remaining gap 1, partially
  addressed:** a research pass (2026-07) read DELFIC's actual particle-
  activity source (Tompkins 1968, DASA-1800-5, per Hooper & Jodoin's 2010
  ORNL revision), Miller (1960), and both of Freiling's fractionation
  reports, and found strong convergent evidence that no single bulk constant
  exists in the literature to source — every real model (DELFIC's FRATIO,
  Miller's 1400°C threshold, Freiling's mass-89/mass-95 ratio correlation)
  resolves fractionation per-nuclide, not as one lumped scalar. A follow-up
  pass implemented a SCOPED per-nuclide alternative,
  `sizedist.f_volatile_from_yields()`: 4 fission-product mass chains (Zr-95,
  Mo-99 refractory; Sr-90, Cs-137 volatile) with cross-verified cumulative
  U-235 fission yields and literature-cited refractory/volatile
  classifications, combined by yield-weighted average. Several other
  candidate chains (89, 91, 97, 131, 140, 141, 143, 144) were tried and
  dropped rather than guessed — either their yield couldn't be
  cross-verified or their classification had no explicit citation. This is
  real sourced data, a genuine upgrade over the placeholder, but still a
  4-chain, yield-weighted (not dose-weighted) proxy — `F_VOLATILE_PLACEHOLDER`
  (0.5) remains the default; see `sizedist.py` for the full citation trail
  on both. **Remaining gap 2:** footprint validation against a published
  DELFIC/HYSPLIT case has first-pass digitized targets for two historical
  cases now (`falloutcast/validation/`), not just scaffolding. Small Boy:
  real historical wind (DNA 1251-1-EX Table 109) and 3 points hand-traced
  from the primary source's own scanned contour figures, all independently
  agreeing on bearing (41-52°) with each other and roughly with Tier-1's own
  modeled bearing (~67°). Little Feller II: a much closer burst-height match
  (3 ft vs. Small Boy's 9.8 ft) with its own real wind and digitized point —
  but its 22-ton yield is far enough outside WSEG-10's designed range that
  the cloud-height formula returns a negative value for it, a genuine model
  limitation (not a bug) documented directly in the test suite rather than
  worked around. Neither case is a full digitized contour or a tight
  validation. See TIER1_SPEC.md §9.7 for exactly what's missing.
- **M2 (done):** Exchange national max-envelope dose surface —
  `POST /exchange/envelope` composites all targets onto one shared CONUS
  grid (`grid.sample_envelope`) and contours the cell-wise max
  (`contour.to_geojson_lonlat`). **Not done:** the "aggressive per-met-run
  caching" this milestone originally scoped — v1 recomputes the full CONUS
  grid (10 targets x ~130k cells at the 0.1°/~7mi default resolution) on
  every request, live-fetching each target's wind fresh; fine at the
  current 10-target scale (~6s end to end) but would need real caching to
  scale further or serve concurrent users cheaply.
- **M3:** Optional HYSPLIT Tier-2 backend behind the same `/plume` contract.
- **M4 (done, single-plume only):** MapLibre + deck.gl frontend (`web/`) —
  click-to-set-GZ, Tier 0/1 toggle, decay time slider (client-side only, see
  `web/src/decay.ts`: Way-Wigner decay is separable in time so the slider
  relabels one dense pre-fetched level set instead of re-hitting the API),
  GeoJSON export. **Not done:** no frontend for `/exchange`,
  `/exchange/envelope`, or `/ensemble` — those remain API-only. CORS opened
  on the API (wide open; every endpoint is read-only, nothing credentialed
  to protect) so the separately-served frontend can call it.

### Decisions resolved (were §10 open questions)

- **Manual wind + Tier-1:** explicit downgrade to Tier-0 with `tier_requested`,
  `tier_used`, and a note. Not a silent downgrade, not a hard error.
- **Still-aloft fraction:** `t_max` = 24 h; airborne activity is reported as
  `fraction_aloft` (regional/global), never silently dropped.
- **Ensemble band:** deferred to M1.5 to validate the deterministic core first;
  engine is structured so ensemble is a map-over-members wrapper.

## 11. Risks

- **False precision.** A polished map implies authority the model lacks. Mitigate
  with persistent disclaimers, visible wind source, and (M1) an uncertainty band
  from ensemble winds.
- **Met resolution / terrain.** GFS/HRRR won't resolve local channeling; state it.
- **Validation.** Tier-1 needs ground truth; check footprints against published
  patterns and HYSPLIT runs before trusting shapes.
- **Positioning.** Keep the civil-defense framing explicit in-product (surface
  burst, public sites) so intent is unambiguous.

## 12. References

- Dan W. Hanifen, *Documentation and Analysis of the WSEG-10 Fallout Prediction
  Model*, AFIT thesis, 1980 (DTIC ADA083515).
- Samuel Glasstone & Philip Dolan, *The Effects of Nuclear Weapons*, 3rd ed.
- NOAA Air Resources Laboratory, HYSPLIT.
- Open-Meteo GFS/HRRR API documentation.
