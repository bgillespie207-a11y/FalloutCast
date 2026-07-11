"""Tier-1 fallout engine: multi-layer particle advection.

Releases radioactive particles across the stabilized cloud's height, lets each
size bin fall at its own altitude-dependent terminal velocity through the real
wind profile (which changes direction/speed with height), and sums where they
land. Wind shear through the fall is what curves and fans the footprint --
exactly what the single-wind Tier-0 model cannot do.

The wind profile is taken as horizontally uniform (one vertical profile at
ground zero). Output is a DoseGrid in the same format Tier-0 produces, so the
grid -> contour -> decay -> API pipeline is reused unchanged.

Internal units: position in statute miles (to match DoseGrid), altitude in
meters, time in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..physics import fallvelocity
from ..physics.sizedist import SizeBins, lognormal_bins
from ..physics.wseg10 import cloud_center_height_kft

_KFT_TO_M = 304.8
_M_PER_MILE = 1609.344

# Deposition / diffusion tunables
_SIGMA0_MI = 0.5              # initial puff horizontal spread, miles
_K_DIFF_MI2_PER_S = 0.0012    # horizontal eddy diffusivity, miles^2/s

# Activity -> H+1 dose-rate calibration, anchored to Glasstone & Dolan:
# a 1 kt fission surface burst deposits ~9,000 R/hr-km^2 of total H+1 activity
# (area-integrated dose-rate content; National Academies / Glasstone-Dolan 1977).
# Each puff deposits a normalized Gaussian, so the grid's area-integral (in mi^2)
# equals the deposited activity = yield_mt * fission_fraction * (1 - aloft).
# Setting  integral(dose dA_km2) = 9000 * kt_fission  gives:
#   _DOSE_CONV = 9000 [R/hr-km2/kt] * 1000 [kt/Mt] / 2.58999 [km2/mi2]
_GLASSTONE_RHR_KM2_PER_KT = 9000.0
_KT_PER_MT = 1000.0
_KM2_PER_MI2 = 2.58999
_DOSE_CONV = _GLASSTONE_RHR_KM2_PER_KT * _KT_PER_MT / _KM2_PER_MI2  # ~3.47e6


@dataclass
class Tier1Result:
    x_miles: np.ndarray
    y_miles: np.ndarray
    dose_rate_h1: np.ndarray
    fraction_aloft: float           # activity still airborne at t_max (regional/global)
    n_bins: int
    n_layers: int
    cloud_center_m: float = field(default=0.0)


def _release_layers(H_c_m: float, sigma_h_m: float, n_layers: int):
    """Gaussian-weighted release altitudes spanning the cloud's vertical extent."""
    lo = max(H_c_m - 2.0 * sigma_h_m, 100.0)
    hi = H_c_m + 2.0 * sigma_h_m
    z = np.linspace(lo, hi, n_layers)
    w = np.exp(-0.5 * ((z - H_c_m) / sigma_h_m) ** 2)
    w = w / w.sum()
    return z, w


def simulate(
    *,
    yield_mt: float,
    fission_fraction: float,
    heights_m: np.ndarray,
    wind_u_ms: np.ndarray,     # eastward component the wind blows TOWARD, per level
    wind_v_ms: np.ndarray,     # northward component, per level
    n_bins: int = 15,
    n_layers: int = 10,
    dt_s: float = 120.0,
    t_max_s: float = 24 * 3600.0,
    resolution_miles: float = 2.0,
    bins: SizeBins | None = None,
) -> Tier1Result:
    """Run the advection and return a dose-rate grid + aloft fraction."""
    # --- source geometry (reused from Tier-0 cloud model) ---
    H_c_kft = cloud_center_height_kft(yield_mt)
    H_c_m = H_c_kft * _KFT_TO_M
    sigma_h_m = 0.18 * H_c_kft * _KFT_TO_M
    z_layers, w_layers = _release_layers(H_c_m, sigma_h_m, n_layers)

    if bins is None:
        bins = lognormal_bins(n_bins=n_bins)
    n_bins = len(bins.diameter_m)

    # --- build one puff per (bin, layer) ---
    d_puff = np.repeat(bins.diameter_m, n_layers)                    # diameter
    act_puff = (
        np.repeat(bins.activity_share, n_layers)
        * np.tile(w_layers, n_bins)
        * yield_mt
        * fission_fraction
    )
    x_mi = np.zeros_like(d_puff)
    y_mi = np.zeros_like(d_puff)
    z_m = np.tile(z_layers, n_bins).astype(float)
    t_land = np.full_like(d_puff, np.nan)

    # sort wind levels ascending in height for np.interp
    order = np.argsort(heights_m)
    h = np.asarray(heights_m, dtype=float)[order]
    u = np.asarray(wind_u_ms, dtype=float)[order]
    v = np.asarray(wind_v_ms, dtype=float)[order]

    n_steps = int(t_max_s / dt_s)
    for step in range(n_steps):
        alive = z_m > 0.0
        if not alive.any():
            break
        t = step * dt_s

        uu = np.interp(z_m, h, u, left=u[0], right=u[-1])
        vv = np.interp(z_m, h, v, left=v[0], right=v[-1])
        x_mi = np.where(alive, x_mi + (uu / _M_PER_MILE) * dt_s, x_mi)
        y_mi = np.where(alive, y_mi + (vv / _M_PER_MILE) * dt_s, y_mi)

        vt = fallvelocity.velocity_at_altitude(d_puff, np.clip(z_m, 0.0, None))
        z_new = np.where(alive, z_m - vt * dt_s, z_m)

        newly_landed = alive & (z_new <= 0.0)
        t_land = np.where(newly_landed, t, t_land)
        z_m = z_new

    landed = ~np.isnan(t_land)
    total_act = act_puff.sum()
    fraction_aloft = float(act_puff[~landed].sum() / total_act) if total_act > 0 else 1.0

    if not landed.any():
        # everything still aloft (extreme small-yield / all-fines edge case)
        empty_axis = np.array([-1.0, 0.0, 1.0])
        return Tier1Result(
            x_miles=empty_axis,
            y_miles=empty_axis,
            dose_rate_h1=np.zeros((3, 3)),
            fraction_aloft=fraction_aloft,
            n_bins=n_bins,
            n_layers=n_layers,
            cloud_center_m=H_c_m,
        )

    lx, ly = x_mi[landed], y_mi[landed]
    la = act_puff[landed]
    lt = t_land[landed]
    sigma_mi = np.sqrt(_SIGMA0_MI ** 2 + 2.0 * _K_DIFF_MI2_PER_S * lt)

    # --- adaptive grid sized to the deposited footprint ---
    pad = 20.0
    x_min, x_max = lx.min() - pad, lx.max() + pad
    y_min, y_max = ly.min() - pad, ly.max() + pad
    nx = int((x_max - x_min) / resolution_miles) + 1
    ny = int((y_max - y_min) / resolution_miles) + 1
    nx, ny = min(nx, 600), min(ny, 600)
    x_axis = np.linspace(x_min, x_max, nx)
    y_axis = np.linspace(y_min, y_max, ny)
    gx, gy = np.meshgrid(x_axis, y_axis)

    field = np.zeros_like(gx)
    for xi, yi, ai, si in zip(lx, ly, la, sigma_mi):
        r2 = (gx - xi) ** 2 + (gy - yi) ** 2
        field += ai * np.exp(-r2 / (2.0 * si ** 2)) / (2.0 * np.pi * si ** 2)

    dose_h1 = field * _DOSE_CONV

    return Tier1Result(
        x_miles=x_axis,
        y_miles=y_axis,
        dose_rate_h1=dose_h1,
        fraction_aloft=fraction_aloft,
        n_bins=n_bins,
        n_layers=n_layers,
        cloud_center_m=H_c_m,
    )
