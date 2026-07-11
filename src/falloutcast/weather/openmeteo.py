"""Open-Meteo GFS/HRRR wind client.

We fetch winds at several pressure levels, build a coarse vertical profile up to
the stabilized-cloud center height, and reduce it to the three numbers Tier-0
WSEG-10 needs: an effective wind speed, a downwind bearing, and a shear
magnitude.

Open-Meteo is free and keyless for non-commercial use, combines NOAA GFS with
high-resolution HRRR over the US, and exposes winds at pressure levels plus
geopotential heights -- exactly the vertical information a fallout model wants.

Design note: the network call is isolated in `fetch_profile`. Everything else
(the reduction to effective wind + shear) is pure and unit-tested offline, and
the API layer can also accept a hand-specified wind to bypass the network.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..physics import units

GFS_ENDPOINT = "https://api.open-meteo.com/v1/gfs"
ENSEMBLE_ENDPOINT = "https://ensemble-api.open-meteo.com/v1/ensemble"
# NOTE: the resolution-suffixed id from the docs prose ("gfs025") silently
# returns all-null data with a 200 status -- no error, just empty arrays.
# Verified live 2026-07-10 that "gfs_seamless" is the working identifier for
# the GFS ensemble (31 members: control + 30 perturbed) on this endpoint.
ENSEMBLE_MODEL = "gfs_seamless"

# Pressure levels to sample (hPa) and their approx geopotential heights (m)
# under a standard atmosphere -- used only as a fallback if the API's own
# geopotential_height fields are unavailable.
_STD_LEVELS_HPA = (1000, 925, 850, 700, 500, 300, 250)
_STD_HEIGHTS_M = (110, 760, 1460, 3010, 5570, 9160, 10360)

# Open-Meteo's GFS Ensemble (gfs025 / gfs05) both ship 31 members total: an
# unsuffixed control member plus 30 perturbed members ("_member01".."_member30"
# in the hourly response keys). Confirmed against the live endpoint 2026-07-10
# (https://open-meteo.com/en/docs/ensemble-api) -- not a documented constant,
# so re-check if Open-Meteo changes their ensemble configuration.
ENSEMBLE_MEMBERS_AVAILABLE = 31


@dataclass
class WindProfile:
    """Vertical wind profile at a point/time. Arrays are level-aligned."""

    height_m: np.ndarray
    speed_ms: np.ndarray
    direction_deg: np.ndarray  # meteorological "from" direction


@dataclass
class EffectiveWind:
    """Reduced wind for Tier-0 WSEG-10."""

    speed_mph: float
    bearing_deg: float  # compass bearing the plume travels TOWARD
    shear_mph_per_kft: float


def _dir_to_uv(speed, direction_from_deg):
    """Meteorological 'from' direction -> math u (east), v (north) components of
    the vector the wind blows TOWARD."""
    # wind blows toward (from + 180). Convert compass-from to math toward.
    rad = np.deg2rad(direction_from_deg)
    u = -speed * np.sin(rad)  # east component
    v = -speed * np.cos(rad)  # north component
    return u, v


def reduce_profile(profile: WindProfile, cloud_top_m: float) -> EffectiveWind:
    """Collapse a vertical profile into an effective wind + shear.

    - Effective wind: the vector-mean of winds from the surface up to the
      cloud top (the layer through which fallout actually descends).
    - Shear: magnitude of the vector difference between the top and bottom of
      that layer, per kilofoot of separation.
    """
    mask = profile.height_m <= max(cloud_top_m, profile.height_m[0])
    if not mask.any():
        mask = np.array([True] + [False] * (len(profile.height_m) - 1))

    h = profile.height_m[mask]
    s = profile.speed_ms[mask]
    d = profile.direction_deg[mask]

    u, v = _dir_to_uv(s, d)
    u_mean, v_mean = float(np.mean(u)), float(np.mean(v))

    speed_ms = float(np.hypot(u_mean, v_mean))
    # bearing the plume travels toward, compass degrees
    bearing = (np.rad2deg(np.arctan2(u_mean, v_mean))) % 360.0

    # shear across the sampled layer
    du = u[-1] - u[0]
    dv = v[-1] - v[0]
    dspeed_ms = float(np.hypot(du, dv))
    dz_m = float(h[-1] - h[0]) if len(h) > 1 else 1.0
    shear_ms_per_m = dspeed_ms / dz_m if dz_m > 0 else 0.0

    return EffectiveWind(
        speed_mph=units.ms_to_mph(speed_ms),
        bearing_deg=float(bearing),
        shear_mph_per_kft=units.shear_ms_per_m_to_mph_per_kilofoot(shear_ms_per_m),
    )


def profile_uv(profile: WindProfile):
    """Return (heights_m, u_ms, v_ms) where u,v are the components the wind blows
    TOWARD -- the form the Tier-1 engine consumes."""
    u, v = _dir_to_uv(profile.speed_ms, profile.direction_deg)
    return profile.height_m, u, v


async def fetch_profile(lat: float, lon: float, *, client=None) -> WindProfile:
    """Fetch the current wind profile from Open-Meteo GFS.

    `client` is an optional httpx.AsyncClient (injectable for tests). If not
    given, one is created for the call.
    """
    import httpx

    hourly_vars = []
    for hpa in _STD_LEVELS_HPA:
        hourly_vars += [
            f"windspeed_{hpa}hPa",
            f"winddirection_{hpa}hPa",
            f"geopotential_height_{hpa}hPa",
        ]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "ms",
        "forecast_days": 1,
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=15.0)
    try:
        resp = await client.get(GFS_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    hourly = data["hourly"]
    idx = 0  # current hour

    heights, speeds, dirs = [], [], []
    for hpa, std_h in zip(_STD_LEVELS_HPA, _STD_HEIGHTS_M):
        sp = hourly.get(f"windspeed_{hpa}hPa", [None])[idx]
        dr = hourly.get(f"winddirection_{hpa}hPa", [None])[idx]
        gh = hourly.get(f"geopotential_height_{hpa}hPa", [None])[idx]
        if sp is None or dr is None:
            continue
        heights.append(gh if gh is not None else std_h)
        speeds.append(sp)
        dirs.append(dr)

    order = np.argsort(heights)
    return WindProfile(
        height_m=np.asarray(heights)[order],
        speed_ms=np.asarray(speeds)[order],
        direction_deg=np.asarray(dirs)[order],
    )


# --- profile cache -----------------------------------------------------------
# `fetch_profile` above stays pure (always hits the network). This is an opt-in
# cached wrapper for callers that fetch the same points repeatedly -- notably
# the exchange envelope, which re-fetches every target/bucket on every request.
#
# Keying: the cache key folds in a wall-clock time window (default 1 h) so an
# entry naturally expires roughly on the model's refresh cadence. This is a
# pragmatic stand-in for keying to the actual GFS run id (which the endpoint
# doesn't cleanly expose): fetch_profile reads the *current-hour* forecast, so
# a 1 h window matches what actually changes between reads. GFS refreshes
# ~4x/day and HRRR hourly, so nothing served is more than ~1 h stale.
#
# In-flight de-duplication means concurrent requests for the same key share a
# single network call (no thundering herd) rather than all missing at once.
# Single-process, in-memory only -- fine for a single-node dev/personal deploy;
# a multi-worker deployment would want a shared cache (Redis, etc.).
import asyncio as _asyncio
import time as _time

_PROFILE_TTL_S = 3600.0
_PROFILE_CACHE: dict[tuple, WindProfile] = {}
_PROFILE_INFLIGHT: dict[tuple, "_asyncio.Future[WindProfile]"] = {}


def _profile_key(lat: float, lon: float, ttl_s: float) -> tuple:
    # round to ~0.1 deg (bucket reps are ~1 deg apart, so this never collides
    # distinct buckets) and bucket the clock into ttl-wide windows.
    return (round(lat, 1), round(lon, 1), int(_time.time() // ttl_s))


def clear_profile_cache() -> None:
    """Drop all cached profiles (test hook / manual invalidation)."""
    _PROFILE_CACHE.clear()
    _PROFILE_INFLIGHT.clear()


async def cached_fetch_profile(
    lat: float, lon: float, *, ttl_s: float = _PROFILE_TTL_S, client=None
) -> WindProfile:
    """`fetch_profile` with a single-process TTL cache + in-flight de-dup.

    Repeat calls for the same point within the same time window return the
    cached profile with no network call; concurrent misses for the same key
    await one shared fetch.
    """
    key = _profile_key(lat, lon, ttl_s)
    cached = _PROFILE_CACHE.get(key)
    if cached is not None:
        return cached

    inflight = _PROFILE_INFLIGHT.get(key)
    if inflight is not None:
        return await inflight

    loop = _asyncio.get_event_loop()
    fut: "_asyncio.Future[WindProfile]" = loop.create_future()
    _PROFILE_INFLIGHT[key] = fut
    try:
        profile = await fetch_profile(lat, lon, client=client)
    except Exception as exc:
        fut.set_exception(exc)
        _PROFILE_INFLIGHT.pop(key, None)
        raise
    # prune entries from older time windows so the dict can't grow unbounded
    # over a long-running process.
    current_window = key[2]
    for k in [k for k in _PROFILE_CACHE if k[2] != current_window]:
        _PROFILE_CACHE.pop(k, None)
    _PROFILE_CACHE[key] = profile
    _PROFILE_INFLIGHT.pop(key, None)
    fut.set_result(profile)
    return profile


async def fetch_ensemble_profiles(
    lat: float, lon: float, *, n_members: int = ENSEMBLE_MEMBERS_AVAILABLE, client=None
) -> list[WindProfile]:
    """Fetch real Open-Meteo GFS-ensemble wind profiles, one per member.

    Same pressure levels and geopotential-height reduction as `fetch_profile`,
    pulled from the ensemble endpoint's per-member fields:
    `windspeed_{hpa}hPa` is the unsuffixed control member, `..._memberNN` (01..30)
    are the 30 perturbed members. This is the true-ensemble replacement for
    `ensemble.perturb_profile`'s synthetic jitter -- same downstream shape
    (`list[WindProfile]`), so `ensemble.run_ensemble` needs no changes.

    A pressure level is included only if the CONTROL member has data there
    (mirrors `fetch_profile`'s below-terrain skip, so every returned profile
    shares one common height axis -- required because `ensemble.run_ensemble`
    advects every member over the same `heights_m` array). If an individual
    perturbed member is unexpectedly missing a value at a level the control
    has (terrain masking is member-independent at a fixed lat/lon, so this
    should not occur in practice), that member falls back to the control's
    reading at that level rather than desynchronizing the arrays.

    `n_members` is capped at `ENSEMBLE_MEMBERS_AVAILABLE` (31: 1 control + 30
    perturbed -- see that constant's docstring). `client` is an optional
    httpx.AsyncClient (injectable for tests).
    """
    import httpx

    n_members = max(1, min(n_members, ENSEMBLE_MEMBERS_AVAILABLE))
    member_suffixes = [""] + [f"_member{i:02d}" for i in range(1, n_members)]

    hourly_vars = []
    for hpa in _STD_LEVELS_HPA:
        hourly_vars += [
            f"windspeed_{hpa}hPa",
            f"winddirection_{hpa}hPa",
            f"geopotential_height_{hpa}hPa",
        ]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly_vars),
        "models": ENSEMBLE_MODEL,
        "wind_speed_unit": "ms",
        "forecast_days": 1,
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=20.0)
    try:
        resp = await client.get(ENSEMBLE_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    hourly = data["hourly"]
    idx = 0  # current hour

    # Levels present for the CONTROL member define the shared height axis
    # every member's arrays get aligned to (see docstring).
    levels = []
    for hpa, std_h in zip(_STD_LEVELS_HPA, _STD_HEIGHTS_M):
        sp = hourly.get(f"windspeed_{hpa}hPa", [None])[idx]
        dr = hourly.get(f"winddirection_{hpa}hPa", [None])[idx]
        if sp is None or dr is None:
            continue
        gh = hourly.get(f"geopotential_height_{hpa}hPa", [None])[idx]
        levels.append((hpa, gh if gh is not None else std_h, sp, dr))

    heights = np.asarray([h for _, h, _, _ in levels], dtype=float)
    order = np.argsort(heights)

    profiles = []
    for suffix in member_suffixes:
        speeds, dirs = [], []
        for hpa, _h, control_sp, control_dr in levels:
            sp = hourly.get(f"windspeed_{hpa}hPa{suffix}", [None])[idx]
            dr = hourly.get(f"winddirection_{hpa}hPa{suffix}", [None])[idx]
            speeds.append(control_sp if sp is None else sp)
            dirs.append(control_dr if dr is None else dr)
        profiles.append(
            WindProfile(
                height_m=heights[order],
                speed_ms=np.asarray(speeds, dtype=float)[order],
                direction_deg=np.asarray(dirs, dtype=float)[order],
            )
        )
    return profiles
