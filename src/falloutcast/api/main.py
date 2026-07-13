"""FalloutCast API.

Endpoints
---------
GET  /health              liveness
GET  /targets             public CONUS strategic-site set
POST /plume               single-detonation fallout contours
POST /dose                time-evolution of exposure at a point
POST /ensemble             wind-ensemble dose-exceedance probability bands
POST /exchange             multi-target overlay (N separate per-target plumes)
POST /exchange/envelope    true national max-envelope dose surface (PRD.md M2):
                           one composite CONUS grid, cell-wise max across all
                           targets, contoured once -- not an overlay of N
                           separate contour sets.
"""

from __future__ import annotations

import asyncio
import time as _time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .. import contour, grid, scenario, targetdeck, targets as targets_mod
from ..physics import decay, ensemble
from ..physics import tier1
from ..physics.wseg10 import WSEG10, cloud_top_height_m
from ..schemas import (
    DISCLAIMER,
    DoseRequest,
    DoseResponse,
    DoseSample,
    EnsembleRequest,
    EnsembleResponse,
    ExchangeEnvelopeResponse,
    PlumeRequest,
    PlumeResponse,
    Target,
    TargetDeckMeta,
    WindUsed,
)
from ..weather import openmeteo

app = FastAPI(
    title="FalloutCast",
    version="0.2.0",
    summary="Weather-driven nuclear fallout visualization (WSEG-10 + multi-layer).",
)

# The web frontend (web/, M4) is served separately (Vite dev server / static
# host) from this API, so it needs CORS. Open to any origin: every endpoint
# here is read-only/side-effect-free (compute a plume, no auth, no user
# data), so there's nothing a cross-origin request could do that a same-origin
# one couldn't -- this isn't a credentialed API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def _resolve_wind(req: PlumeRequest) -> WindUsed:
    if req.wind is not None:
        return WindUsed(
            speed_mph=req.wind.speed_mph,
            bearing_deg=req.wind.bearing_deg,
            shear_mph_per_kft=req.wind.shear_mph_per_kft,
            source="manual",
        )
    profile = await openmeteo.fetch_profile(req.lat, req.lon)
    eff = openmeteo.reduce_profile(profile, cloud_top_height_m(req.yield_mt))
    return WindUsed(
        speed_mph=eff.speed_mph,
        bearing_deg=eff.bearing_deg,
        shear_mph_per_kft=eff.shear_mph_per_kft,
        source="open-meteo-gfs",
    )


def _tier0_contours(req: PlumeRequest, wind: WindUsed) -> dict:
    model = WSEG10(
        yield_mt=req.yield_mt,
        fission_fraction=req.fission_fraction,
        wind_mph=wind.speed_mph,
        wind_dir_deg=wind.bearing_deg,
        shear_mph_per_kft=wind.shear_mph_per_kft,
    )
    g = grid.sample(model)
    levels = tuple(req.levels_rhr) if req.levels_rhr else contour.DEFAULT_LEVELS
    return contour.to_geojson(g, lat0=req.lat, lon0=req.lon, levels=levels)


def _tier1_contours(req: PlumeRequest, profile) -> tuple[dict, float]:
    heights, u, v = openmeteo.profile_uv(profile)
    result = tier1.simulate(
        yield_mt=req.yield_mt,
        fission_fraction=req.fission_fraction,
        heights_m=heights,
        wind_u_ms=u,
        wind_v_ms=v,
    )
    dose_grid = grid.DoseGrid(
        x_miles=result.x_miles,
        y_miles=result.y_miles,
        dose_rate_h1=result.dose_rate_h1,
    )
    levels = tuple(req.levels_rhr) if req.levels_rhr else contour.DEFAULT_LEVELS
    gj = contour.to_geojson(dose_grid, lat0=req.lat, lon0=req.lon, levels=levels)
    return gj, result.fraction_aloft


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "models": ["wseg10", "tier1"], "tiers": [0, 1]}


@app.get("/deck", response_model=TargetDeckMeta)
def get_deck() -> TargetDeckMeta:
    """Versioned target-deck metadata: dataset version, content hash, and the
    documented field FOOTPRINT polygons (the verifiable geography -- the
    individual silo/LCC points are synthetic; see targetdeck.py)."""
    return targetdeck.deck_meta()


@app.get("/targets", response_model=list[Target])
def get_targets(expanded: bool = False, verified_only: bool = False) -> list[Target]:
    """Public target set.

    `expanded=false` (default): the 10 curated installations (unchanged).
    `expanded=true`: the full national deck used by the exchange envelope --
    the three Minuteman fields resolved to their individual launch facilities
    and control centers (illustrative distribution within the documented field
    footprints; see targetdeck.py) plus curated public high-value targets
    (population centers, industry, government C2).

    `verified_only=true`: drop synthetic-geography points (silos/LCCs), leaving
    only observed/field_polygon targets -- there are no verified precise facility
    coordinates to stand behind.
    """
    if verified_only:
        return targetdeck.verified_targets()
    return targetdeck.load_expanded_targets() if expanded else targets_mod.load_targets()


@app.post("/dose", response_model=DoseResponse)
def dose(req: DoseRequest) -> DoseResponse:
    """Time-evolution of exposure at a point via Way-Wigner (t^-1.2) decay.

    Given the H+1 reference dose rate, returns the decaying rate at requested
    times, the accumulated dose over a shelter window, and the total dose if
    exposed from arrival onward.
    """
    default_times = [1, 2, 6, 12, 24, 48, 168]
    times = req.times_hours or default_times
    times = [t for t in times if t >= req.arrival_hours]

    curve = [
        DoseSample(t_hours=t, dose_rate_rhr=float(decay.dose_rate_at(req.dose_rate_h1, t)))
        for t in times
    ]

    accumulated = None
    notes: list[str] = []
    if req.exit_hours is not None:
        if req.exit_hours <= req.arrival_hours:
            raise HTTPException(status_code=422, detail="exit_hours must exceed arrival_hours")
        accumulated = float(
            decay.accumulated_dose(req.dose_rate_h1, req.arrival_hours, req.exit_hours)
        )

    total_inf = float(decay.accumulated_dose_to_infinity(req.dose_rate_h1, req.arrival_hours))
    notes.append(
        "Dose in roentgens (~rem whole-body). Decay assumes no weathering or "
        "shielding; divide by a protection factor for sheltered exposure."
    )
    return DoseResponse(
        rate_curve=curve,
        accumulated_dose_r=accumulated,
        total_to_infinity_r=total_inf,
        notes=notes,
    )


@app.post("/ensemble", response_model=EnsembleResponse)
async def ensemble_band(req: EnsembleRequest) -> EnsembleResponse:
    """Ensemble uncertainty band: probability that H+1 dose rate exceeds a level.

    Runs Tier-1 across real Open-Meteo GFS-ensemble wind members (31 members:
    1 control + 30 perturbed) and contours the exceedance probability at
    10/50/90%. The outer band is where fallout could reach; the inner is where
    it very likely will. This is the antidote to a single crisp (and
    false-confident) plume line.

    If the ensemble endpoint is unreachable, falls back to the deterministic
    forecast's synthetic perturbation (`ensemble.perturb_profile`) rather than
    failing outright -- the response says plainly which source was used.
    """
    notes: list[str] = []
    try:
        profiles = await openmeteo.fetch_ensemble_profiles(
            req.lat, req.lon, n_members=req.n_members
        )
        heights, _, _ = openmeteo.profile_uv(profiles[0])
        members = [openmeteo.profile_uv(p)[1:] for p in profiles]
        notes.append(
            f"Members are real Open-Meteo GFS-ensemble forecasts "
            f"({openmeteo.ENSEMBLE_MODEL}), not synthetic perturbations."
        )
    except Exception as exc:
        try:
            profile = await openmeteo.fetch_profile(req.lat, req.lon)
        except Exception as exc2:
            raise HTTPException(status_code=502, detail=f"wind fetch failed: {exc2}")
        heights, u, v = openmeteo.profile_uv(profile)
        members = ensemble.perturb_profile(u, v, n_members=req.n_members)
        notes.append(
            f"Ensemble wind fetch failed ({exc}); fell back to synthetic "
            "perturbation of the deterministic forecast."
        )

    res = ensemble.run_ensemble(
        yield_mt=req.yield_mt, fission_fraction=req.fission_fraction,
        heights_m=heights, members=members, levels_rhr=(req.level_rhr,),
    )

    prob_field = res.prob_by_level[req.level_rhr]
    prob_grid = grid.DoseGrid(
        x_miles=res.x_miles, y_miles=res.y_miles, dose_rate_h1=prob_field
    )
    gj = contour.to_geojson(
        prob_grid, lat0=req.lat, lon0=req.lon, levels=ensemble.DEFAULT_PROB_LEVELS
    )
    # relabel the contour property: it's a probability, not a dose rate
    for f in gj["features"]:
        f["properties"] = {"exceedance_probability": f["properties"].pop("dose_rate_h1_rhr")}

    notes.append(
        f"Bands are P(H+1 dose rate >= {req.level_rhr:g} R/hr) at 10/50/90% across "
        f"{res.n_members} wind members."
    )
    return EnsembleResponse(
        ground_zero=[req.lon, req.lat], level_rhr=req.level_rhr,
        n_members=res.n_members, mean_fraction_aloft=res.mean_fraction_aloft,
        disclaimer=DISCLAIMER, notes=notes, contours=gj,
    )


@app.post("/plume", response_model=PlumeResponse)
async def plume(req: PlumeRequest) -> PlumeResponse:
    if not req.surface_burst:
        raise HTTPException(
            status_code=422,
            detail="WSEG-10 fallout modeling assumes a surface burst; air bursts "
            "produce negligible local fallout and are out of scope.",
        )

    notes: list[str] = []

    # Tier-1 needs a full vertical wind profile. A manual single-vector wind
    # cannot drive it, so we honor the request by downgrading to Tier-0 and say
    # so plainly -- never silently, never with an error.
    if req.tier == 1 and req.wind is not None:
        notes.append(
            "Tier-1 requires a fetched vertical wind profile; a manual single "
            "wind vector has no shear to advect through. Downgraded to Tier-0."
        )
        wind = await _resolve_wind(req)
        contours = _tier0_contours(req, wind)
        return PlumeResponse(
            ground_zero=[req.lon, req.lat], tier_requested=1, tier_used=0,
            wind=wind, disclaimer=DISCLAIMER, notes=notes, contours=contours,
        )

    if req.tier == 1:
        try:
            profile = await openmeteo.fetch_profile(req.lat, req.lon)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"wind fetch failed: {exc}")
        contours, aloft = _tier1_contours(req, profile)
        if aloft > 0.05:
            notes.append(
                f"{aloft:.0%} of activity is still airborne at 24 h (fine particles "
                "carried to regional/global scale, beyond this local footprint)."
            )
        return PlumeResponse(
            ground_zero=[req.lon, req.lat], tier_requested=1, tier_used=1,
            wind=WindUsed(source="open-meteo-gfs-profile"),
            disclaimer=DISCLAIMER, notes=notes, fraction_aloft=aloft,
            contours=contours,
        )

    # Tier-0
    try:
        wind = await _resolve_wind(req)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"wind fetch failed: {exc}")
    contours = _tier0_contours(req, wind)
    return PlumeResponse(
        ground_zero=[req.lon, req.lat], tier_requested=0, tier_used=0,
        wind=wind, disclaimer=DISCLAIMER, notes=notes, contours=contours,
    )


@app.post("/exchange")
async def exchange(yield_mt: float = 0.3, fission_fraction: float = 0.5) -> dict:
    """Overlay fallout from the full public target set under current winds.

    v1 semantics: each target is modeled independently with its own local wind
    and the resulting contour sets are returned together (one FeatureCollection
    per target). This is honest about what it is -- an overlay, not a summed
    national dose surface. The max-envelope CONUS grid is the next milestone.
    """
    tgts = targets_mod.load_targets()
    results = []
    for t in tgts:
        req = PlumeRequest(
            lat=t.lat, lon=t.lon, yield_mt=yield_mt, fission_fraction=fission_fraction
        )
        try:
            wind = await _resolve_wind(req)
            contours = _tier0_contours(req, wind)
        except Exception as exc:
            results.append({"target": t.name, "error": str(exc)})
            continue
        results.append(
            {
                "target": t.name,
                "category": t.category,
                "ground_zero": [t.lon, t.lat],
                "wind": wind.model_dump(),
                "contours": contours,
            }
        )
    return {"disclaimer": DISCLAIMER, "yield_mt": yield_mt, "targets": results}


# Wind-fetch scaling for large decks. Fetching one live wind per target is fine
# at 10 targets but fatal at ~500 (serial: minutes + rate-limiting). Adjacent
# targets share the same synoptic-scale transport wind, so we bucket targets
# into ~1-degree cells and fetch ONE profile per bucket, concurrently. A whole
# Minuteman field (~1-2 deg across) collapses from 165 fetches to a handful.
_WIND_BUCKET_DEG = 1.0
# Politeness cap on simultaneous Open-Meteo requests (keyless API). ~8 in flight
# keeps a big deck fast (a few waves) without tripping rate limits.
_WIND_FETCH_CONCURRENCY = 8


async def _build_models_bucketed(
    tgts: list[Target], yield_fn, *, valid_time: str | None = None
) -> tuple[list[tuple[WSEG10, float, float]], list[Target], list[Target], dict]:
    """Build one WSEG-10 model per target, sharing a single fetched wind
    *profile* across all targets in the same ~1-degree bucket. Returns
    (models, failed_names).

    `yield_fn(target) -> (yield_mt, fission_fraction)` lets each target carry
    its own yield (e.g. per target class). The expensive part -- the live
    Open-Meteo fetch -- is done once per bucket; the cheap part --
    `reduce_profile`, which depends on the yield (via cloud-top height) -- is
    redone per target, so targets in one bucket can differ in yield while still
    sharing a single network call.

    A bucket whose wind fetch fails excludes every target in it from the
    envelope rather than failing the whole request; those names are returned so
    the response can report them. Fetches run concurrently under a small
    semaphore.
    """
    # One valid forecast hour chosen up front, shared by every bucket/target,
    # so the whole envelope uses a single consistent 'current weather' hour.
    vt = valid_time or openmeteo.current_valid_time()

    buckets: dict[tuple[int, int], list[Target]] = defaultdict(list)
    for t in tgts:
        buckets[(round(t.lat / _WIND_BUCKET_DEG), round(t.lon / _WIND_BUCKET_DEG))].append(t)

    keys = list(buckets.keys())
    sem = asyncio.Semaphore(_WIND_FETCH_CONCURRENCY)

    async def fetch_for_bucket(members: list[Target]):
        # representative point = centroid of the bucket's targets
        rlat = sum(m.lat for m in members) / len(members)
        rlon = sum(m.lon for m in members) / len(members)
        # One retry with brief backoff: a burst of concurrent requests draws
        # occasional transient rate-limit/timeout errors from the keyless
        # Open-Meteo endpoint even though the same point succeeds in isolation.
        # A single retry recovers those without slowing the happy path.
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                async with sem:
                    # Cached wrapper (keyed to the shared valid hour): repeat/
                    # concurrent envelope calls reuse the per-bucket profile.
                    return await openmeteo.cached_fetch_profile(rlat, rlon, valid_time=vt)
            except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.75)
        raise last_exc  # type: ignore[misc]

    results = await asyncio.gather(
        *(fetch_for_bucket(buckets[k]) for k in keys), return_exceptions=True
    )

    models: list[tuple[WSEG10, float, float]] = []
    included: list[Target] = []
    excluded: list[Target] = []
    oldest_retrieved = 0.0
    for k, res in zip(keys, results):
        members = buckets[k]
        if isinstance(res, Exception):
            excluded.extend(members)
            continue
        profile = res
        if profile.retrieved_at:
            oldest_retrieved = (
                profile.retrieved_at if oldest_retrieved == 0.0
                else min(oldest_retrieved, profile.retrieved_at)
            )
        for t in members:
            y_mt, ff = yield_fn(t)
            eff = openmeteo.reduce_profile(profile, cloud_top_height_m(y_mt))
            model = WSEG10(
                yield_mt=y_mt, fission_fraction=ff,
                wind_mph=eff.speed_mph, wind_dir_deg=eff.bearing_deg,
                shear_mph_per_kft=eff.shear_mph_per_kft,
            )
            models.append((model, t.lat, t.lon))
            included.append(t)

    provenance = _weather_provenance(vt, oldest_retrieved)
    return models, included, excluded, provenance


def _weather_provenance(valid_time: str, retrieved_at: float) -> dict:
    """Structured weather provenance for API/UI/export: which forecast hour the
    winds are for, the model, when they were retrieved, and how stale that is."""
    now = _time.time()
    return {
        "valid_time": valid_time,
        "model": openmeteo.MODEL_NAME,
        "retrieved_at": (
            datetime.fromtimestamp(retrieved_at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if retrieved_at else None
        ),
        "age_seconds": int(now - retrieved_at) if retrieved_at else None,
    }


# API-facing aggregation names (the honest labels) -> grid.sample_envelope names.
_AGGREGATION_MAP = {"max_single_source": "max", "sum": "sum"}


@app.post("/exchange/envelope", response_model=ExchangeEnvelopeResponse)
async def exchange_envelope(
    expanded: bool = True,
    per_class: bool = True,
    aggregation: str = Query(
        "max_single_source",
        description="max_single_source (screening: worst dose from any ONE target) "
        "| sum (adds overlapping contributions)",
    ),
    uniform_yield_mt: float = Query(
        0.3, gt=0, description="uniform incoming yield (Mt); used only when per_class=false"
    ),
    uniform_fission_fraction: float = Query(
        0.5, gt=0, le=1.0, description="uniform fission fraction; used only when per_class=false"
    ),
) -> ExchangeEnvelopeResponse:
    """Composite dose surface over the CURATED target deck (not "all targets").

    IMPORTANT -- what the aggregation means:
      * `max_single_source` (default): a SCREENING envelope -- at each point, the
        worst H+1 dose from any ONE target. It does NOT sum overlapping plumes,
        so it is not a combined-exchange total.
      * `sum`: adds overlapping H+1 contributions (a simultaneous-detonation
        total; not yet time-aligned for staggered fallout arrival).

    `expanded=true` (default) uses the full curated deck (three Minuteman fields
    resolved to individual LFs/LCCs + curated high-value targets, ~500+ ground
    zeros); `expanded=false` uses the 10 curated installations.

    `per_class=true` (default) applies the attack-SCENARIO incoming yields per
    target class (see `scenario.py` -- these are attacker assumptions, NOT the
    target's resident weapon), reported in `yield_policy`. Set `per_class=false`
    to use one uniform `uniform_yield_mt`/`uniform_fission_fraction`.

    Winds are fetched per ~1-degree bucket, concurrently, all at one shared
    forecast valid hour; a bucket whose fetch fails excludes its targets (not
    fatal) -- see `included_target_ids`/`excluded_target_ids`.
    """
    if aggregation not in _AGGREGATION_MAP:
        raise HTTPException(
            status_code=422,
            detail=f"aggregation must be one of {list(_AGGREGATION_MAP)}, got {aggregation!r}",
        )

    tgts = targetdeck.load_expanded_targets() if expanded else targets_mod.load_targets()

    if per_class:
        yield_fn = lambda t: scenario.yield_for(t.category)  # noqa: E731
    else:
        yield_fn = lambda t: (uniform_yield_mt, uniform_fission_fraction)  # noqa: E731

    models, included, excluded, weather = await _build_models_bucketed(tgts, yield_fn)
    if not models:
        raise HTTPException(status_code=502, detail="wind fetch failed for all targets")

    # Full grid for the small set (exact, cheap); local-window path for the big
    # deck. Sized beyond the reach of the largest scenario yield so no tail clips.
    radius = 10.0 if expanded else None
    g = grid.sample_envelope(models, radius_deg=radius, aggregation=_AGGREGATION_MAP[aggregation])
    gj = contour.to_geojson_lonlat(g)

    if per_class:
        yield_policy = scenario.yield_policy({t.category for t in included})
    else:
        yield_policy = {
            "scenario": "uniform",
            "mode": "uniform",
            "surface_burst_caveat": scenario.SURFACE_BURST_CAVEAT,
            "yield_mt": uniform_yield_mt,
            "fission_fraction": uniform_fission_fraction,
        }

    agg_desc = (
        "worst H+1 dose from any ONE target (screening envelope -- NOT a combined total)"
        if aggregation == "max_single_source"
        else "sum of overlapping H+1 contributions (simultaneous total, not time-aligned)"
    )
    notes = [
        f"Aggregation '{aggregation}': at each point, {agg_desc}. "
        f"{len(included)} target(s) on one shared CONUS grid.",
        scenario.SURFACE_BURST_CAVEAT,
    ]
    if expanded:
        notes.append(
            "Curated deck: the three Minuteman fields resolved to individual "
            "launch facilities/control centers (SYNTHETIC illustrative positions "
            "within documented field footprints, not surveyed coordinates) plus a "
            "curated, incomplete set of high-value targets."
        )
    if excluded:
        ex_ids = [t.id for t in excluded]
        shown = ", ".join(ex_ids[:5]) + (f", +{len(ex_ids) - 5} more" if len(ex_ids) > 5 else "")
        notes.append(f"Excluded {len(excluded)} target(s) with failed wind fetch: {shown}.")
    notes.append(
        f"Winds valid {weather['valid_time']}Z from {weather['model']}"
        + (f", retrieved {weather['retrieved_at']}." if weather["retrieved_at"] else ".")
    )

    return ExchangeEnvelopeResponse(
        n_targets=len(models),
        aggregation=aggregation,
        deck_version=targetdeck.DATASET_VERSION,
        yield_policy=yield_policy,
        included_target_ids=[t.id for t in included],
        excluded_target_ids=[t.id for t in excluded],
        disclaimer=DISCLAIMER,
        notes=notes,
        weather=weather,
        contours=gj,
    )
