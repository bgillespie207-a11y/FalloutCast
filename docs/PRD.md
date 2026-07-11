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
semantics:** each target is modeled independently with its own local wind and
the contour sets are returned together. This is an overlay, not a summed
national dose surface — stated plainly so it is not mistaken for more than it
is. The true national max-envelope grid is milestone M2.

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

## 10. Roadmap / milestones

- **M0 (done):** Tier-0 engine, decay, contours, wind feed, API, tests.
- **M1 (done):** Tier-1 multi-layer advection (atmosphere + Best-number fall
  velocity + lognormal bins + puff advection); `/plume?tier=1`; aloft-fraction
  reporting; shear-curvature capability test.
- **M1.5 (mostly done):** ensemble-wind uncertainty band — `/ensemble` runs
  Tier-1 over perturbed members and contours P(dose ≥ level) at 10/50/90%;
  `/dose` time-evolution endpoint; dose calibrated to Glasstone & Dolan and size
  distribution grounded in DELFIC (σ_ln ≈ ln 2). **Remaining:** DELFIC
  fractionation rule (activity-vs-size), and swapping perturbed members for true
  Open-Meteo ensemble members (fetch-layer change).
- **M2:** Exchange national max-envelope dose surface (shared CONUS grid,
  precompute-per-target-then-composite, aggressive per-met-run caching).
- **M3:** Optional HYSPLIT Tier-2 backend behind the same `/plume` contract.
- **M4:** MapLibre + deck.gl frontend; decay time slider; GeoJSON/export.

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
