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

# Pressure levels to sample (hPa) and their approx geopotential heights (m)
# under a standard atmosphere -- used only as a fallback if the API's own
# geopotential_height fields are unavailable.
_STD_LEVELS_HPA = (1000, 925, 850, 700, 500, 300, 250)
_STD_HEIGHTS_M = (110, 760, 1460, 3010, 5570, 9160, 10360)


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
