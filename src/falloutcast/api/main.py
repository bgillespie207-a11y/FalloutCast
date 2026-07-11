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
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .. import contour, grid, targetdeck, targets as targets_mod
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


@app.get("/targets", response_model=list[Target])
def get_targets(expanded: bool = False) -> list[Target]:
    """Public target set.

    `expanded=false` (default): the 10 curated installations (unchanged).
    `expanded=true`: the full national deck used by the exchange envelope --
    the three Minuteman fields resolved to their individual launch facilities
    and control centers (illustrative distribution within the documented field
    footprints; see targetdeck.py) plus curated public high-value targets
    (population centers, industry, government C2).
    """
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
    tgts: list[Target], yield_mt: float, fission_fraction: float
) -> tuple[list[tuple[WSEG10, float, float]], list[str]]:
    """Build one WSEG-10 model per target, sharing a single fetched wind across
    all targets in the same ~1-degree bucket. Returns (models, failed_names).

    A bucket whose (single, shared) wind fetch fails excludes every target in
    it from the envelope rather than failing the whole request; those names are
    returned so the response can report them. Fetches run concurrently under a
    small semaphore.
    """
    cloud_top_m = cloud_top_height_m(yield_mt)

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
                    profile = await openmeteo.fetch_profile(rlat, rlon)
                return openmeteo.reduce_profile(profile, cloud_top_m)
            except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.75)
        raise last_exc  # type: ignore[misc]

    results = await asyncio.gather(
        *(fetch_for_bucket(buckets[k]) for k in keys), return_exceptions=True
    )

    models: list[tuple[WSEG10, float, float]] = []
    failed: list[str] = []
    for k, res in zip(keys, results):
        members = buckets[k]
        if isinstance(res, Exception):
            failed.extend(m.name for m in members)
            continue
        eff = res
        for t in members:
            model = WSEG10(
                yield_mt=yield_mt, fission_fraction=fission_fraction,
                wind_mph=eff.speed_mph, wind_dir_deg=eff.bearing_deg,
                shear_mph_per_kft=eff.shear_mph_per_kft,
            )
            models.append((model, t.lat, t.lon))
    return models, failed


@app.post("/exchange/envelope", response_model=ExchangeEnvelopeResponse)
async def exchange_envelope(
    yield_mt: float = 0.3, fission_fraction: float = 0.5, expanded: bool = True
) -> ExchangeEnvelopeResponse:
    """True national max-envelope dose surface (PRD.md M2).

    Unlike `/exchange` (a per-target overlay -- N separate plumes returned
    side by side), this composites all targets onto ONE shared CONUS grid and
    takes the cell-wise MAX H+1 dose rate across targets, then contours that
    single composite field. It answers "what's the worst dose rate at this
    point from ANY of these targets," which an overlay of separate contour
    sets cannot directly show without a human eyeballing overlaps.

    `expanded=true` (default) uses the full national deck: the three Minuteman
    fields resolved to their individual launch facilities/control centers plus
    curated high-value targets (see targetdeck.py) -- ~500+ ground zeros.
    `expanded=false` keeps the original 10-installation set.

    Winds are fetched per ~1-degree bucket, concurrently, and shared across
    targets in a bucket (see `_build_models_bucketed`); a bucket whose wind
    fetch fails excludes its targets (not fatal) and they're named in notes.
    For the large deck each target's dose is evaluated only within a local
    window of its ground zero (`radius_deg`), which is what makes ~500 targets
    tractable in one grid pass.
    """
    tgts = targetdeck.load_expanded_targets() if expanded else targets_mod.load_targets()

    models, failed = await _build_models_bucketed(tgts, yield_mt, fission_fraction)
    if not models:
        raise HTTPException(status_code=502, detail="wind fetch failed for all targets")

    # Full grid for the small set (exact, cheap); local-window path for the big
    # deck (bounded cost per target).
    radius = 8.0 if expanded else None
    g = grid.sample_envelope(models, radius_deg=radius)
    gj = contour.to_geojson_lonlat(g)

    notes = [
        f"Max H+1 dose rate at each point from any of {len(models)} ground zeros, "
        "on one shared CONUS grid -- not a per-target overlay.",
    ]
    if expanded:
        notes.append(
            "Deck includes the three Minuteman fields resolved to individual "
            "launch facilities/control centers (illustrative distribution within "
            "the documented field footprints, not surveyed silo coordinates) plus "
            "curated public high-value targets."
        )
    if failed:
        shown = ", ".join(failed[:5]) + (f", +{len(failed) - 5} more" if len(failed) > 5 else "")
        notes.append(f"Excluded {len(failed)} target(s) with failed wind fetch: {shown}.")

    return ExchangeEnvelopeResponse(
        yield_mt=yield_mt, fission_fraction=fission_fraction, n_targets=len(models),
        disclaimer=DISCLAIMER, notes=notes, contours=gj,
    )
