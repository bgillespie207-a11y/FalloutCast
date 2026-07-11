# FalloutCast

Weather-driven nuclear fallout visualization for CONUS. Given a surface burst
and current winds, it computes ground-level fallout dose-rate contours. Two
modes: single detonation and a multi-target overlay over known public strategic
sites.

This is a civil-defense / educational tool in the lineage of NUKEMAP and NOAA's
HYSPLIT — it answers "where does the fallout go, and where is it survivable,"
not anything about weapon design or employment. Every output is a **planning
estimate, not an operational product.**

## Status

Tier-0 (WSEG-10 analytic) and **Tier-1 (multi-layer particle advection)** are
both implemented, tested, and wired to the API. Tier-1 is the differentiator:
wind shear through the fall curves and fans the footprint the way Tier-0 cannot.

- [x] WSEG-10 fallout model, faithful to Hanifen (1980) with documented fixes
- [x] Way-Wigner (t^-1.2) decay + accumulated-dose math
- [x] Grid sampling → GeoJSON isodose contours (contourpy)
- [x] Open-Meteo GFS multi-level wind fetch → effective wind + shear
- [x] **Tier-1 engine: US Std Atmosphere + Best-number fall velocity +
      lognormal size bins + Lagrangian puff advection**
- [x] **Dose calibrated to Glasstone & Dolan (9,000 R/hr·km²/kt); size
      distribution grounded in DELFIC (σ_ln ≈ ln 2)**
- [x] **Ensemble uncertainty band: P(dose ≥ level) across wind members**
- [x] FastAPI: `/plume` (tier 0/1), `/ensemble`, `/dose`, `/exchange`,
      `/exchange/envelope`, `/targets`, `/health`
- [x] 67-test suite (physics structural + magnitude + curvature + ensemble + fractionation)
- [x] DELFIC-style fractionation rule for activity-vs-size (refractory/volume
      vs volatile/surface split, opt-in). `F_VOLATILE_PLACEHOLDER` (0.5,
      illustrative) remains the default; `f_volatile_from_yields()` is a
      real, sourced, per-nuclide alternative (4 fission-product mass chains,
      yield-weighted, cross-cited) — still a partial proxy, not a true
      dose-weighted DELFIC-equivalent, see `sizedist.py`
- [x] `/ensemble` runs real Open-Meteo GFS-ensemble wind members (31: control +
      30 perturbed), falling back to synthetic perturbation only if the
      ensemble fetch fails
- [ ] Footprint validation: scaffolding with first-pass digitized targets for
      2 historical cases (`falloutcast/validation/`) -- real historical
      winds (DNA 1251-1-EX Tables 109 & 107) and hand-traced target points
      from the source's own contour figures; Small Boy's 3 points
      independently agree on bearing (~41-52° vs. model's ~67°). Little
      Feller II has a much closer burst-height match (3 ft vs. 9.8 ft) but
      its tiny 22-ton yield breaks WSEG-10's cloud-height formula
      (goes negative) — a real, documented model limitation, not run
      through Tier-1. Still not a full contour for either case, see
      TIER1_SPEC.md §9.7
- [x] Exchange mode: true national max-envelope dose surface
      (`POST /exchange/envelope`) — one composite CONUS grid, cell-wise max
      across all targets; no result caching yet (recomputes live every call)
- [x] Web map frontend (`web/`, MapLibre + deck.gl) — single-plume view only
      (Tier 0/1 toggle, click-to-set-GZ, decay time slider computed
      client-side with zero extra API calls, GeoJSON export). Exchange
      overlay/envelope and ensemble bands have no frontend yet.

## Quickstart

```bash
pip install -e ".[dev]"
pytest                      # 67 passing
uvicorn falloutcast.api.main:app --reload
```

Single plume with an explicit wind (no network):

```bash
curl -s localhost:8000/plume -H 'content-type: application/json' -d '{
  "lat": 41.14, "lon": -104.82, "yield_mt": 1.0, "fission_fraction": 1.0,
  "wind": {"speed_mph": 15, "bearing_deg": 90, "shear_mph_per_kft": 0.5}
}'
```

Omit `wind` to pull live winds from Open-Meteo GFS for the ground-zero point.

Tier-1 (multi-layer advection — shear curves the plume) uses the full vertical
wind profile, so it fetches winds and ignores any manual single vector:

```bash
curl -s localhost:8000/plume -H 'content-type: application/json' -d '{
  "lat": 41.14, "lon": -104.82, "yield_mt": 1.0, "fission_fraction": 1.0,
  "tier": 1
}'
```

The response carries `tier_requested`/`tier_used` and, for Tier-1,
`fraction_aloft` — the share of activity carried past the local footprint to
regional/global scale.

National max-envelope across the full public target set (one composite
CONUS grid, not a per-target overlay — see `/exchange` for the overlay
instead):

```bash
curl -s -X POST 'localhost:8000/exchange/envelope?yield_mt=0.3&fission_fraction=0.5'
```

## Web frontend

```bash
cd web
npm install
npm run dev          # http://localhost:5173, expects the API on :8000
```

Single-plume view: click the map (or type coordinates) to set ground zero,
pick yield/fission-fraction/tier, hit Compute. The decay-time slider doesn't
re-hit the API as you drag it — Way-Wigner decay (dose rate ∝ t^-1.2) is
separable, so the contour for level *L* at time *t* is exactly the H+1
contour for level *L·t^1.2*; the app fetches one dense set of H+1 levels
once and relabels/reselects client-side (`web/src/decay.ts`). No exchange
overlay/envelope or ensemble-band view yet — single detonations only.

Basemap is [OpenFreeMap](https://openfreemap.org) (free, keyless, no signup
needed). CORS is wide open on the API (`allow_origins=["*"]`) since every
endpoint is read-only/side-effect-free — there's no credentialed state a
cross-origin request could touch.

## Architecture

```
weather (Open-Meteo GFS)  ──►  effective wind + shear
                                      │
        yield, fission fraction, GZ ──┼──►  WSEG-10 (physics/)  ──►  H+1 dose-rate field
                                      │                                    │
                                grid.sample()  ──►  contour.to_geojson()  ──►  GeoJSON isodose
                                                                             │
                                                                     FastAPI (api/)
```

- `physics/wseg10.py` — pure model, native units (mi/mph/kft), no I/O.
- `physics/decay.py` — decay + dose integrals.
- `physics/units.py` — SI ↔ native conversions at the boundary.
- `weather/openmeteo.py` — network isolated in one function; reduction is pure.
- `grid.py`, `contour.py` — sampling and GeoJSON.
- `api/main.py` — HTTP surface.

## Honest limitations

WSEG-10 is a single-effective-wind smearing model. It will not curve the plume
with real wind shear the way nature (or HYSPLIT) does — that is exactly what
Tier-1 fixes. It also ignores fractionation, particle-size activity
distribution, hot spots, and terrain. The slick map is the dangerous part:
treat contours as order-of-magnitude planning bands, not truth.

## References

- Hanifen, *Documentation and Analysis of the WSEG-10 Fallout Prediction
  Model*, AFIT, 1980 (DTIC ADA083515).
- Glasstone & Dolan, *The Effects of Nuclear Weapons*, 3rd ed. (decay, dose).
- NOAA ARL HYSPLIT (Tier-2 reference engine).
