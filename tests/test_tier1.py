"""Tier-1 engine tests. These assert the capabilities Tier-0 structurally CANNOT
have -- shear-driven curvature and size-dependent range -- plus physical
conservation and limit checks.
"""

import numpy as np
import pytest

from falloutcast.physics import atmosphere, fallvelocity, sizedist, tier1

H = np.array([100.0, 1500.0, 3000.0, 5500.0, 9000.0, 12000.0])


def _single_bin(d_m):
    return sizedist.SizeBins(
        diameter_m=np.array([d_m]),
        activity_share=np.array([1.0]),
        edges_m=np.array([d_m * 0.9, d_m * 1.1]),
    )


def _hotline(result):
    xs, ys = [], []
    for j, xv in enumerate(result.x_miles):
        col = result.dose_rate_h1[:, j]
        if col.max() > 1.0:
            xs.append(xv)
            ys.append(result.y_miles[np.argmax(col)])
    return np.array(xs), np.array(ys)


# --- headline: shear curves the plume -----------------------------------------

def test_shear_produces_curvature():
    uniform = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=np.full(6, 15.0), wind_v_ms=np.zeros(6),
    )
    sheared = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=np.array([10, 12, 15, 20, 25, 30.0]),
        wind_v_ms=np.array([12, 9, 6, 3, 0, -3.0]),
    )
    _, yu = _hotline(uniform)
    _, ys = _hotline(sheared)
    uniform_drift = yu.max() - yu.min()
    sheared_drift = ys.max() - ys.min()

    assert uniform_drift < 2.0           # straight
    assert sheared_drift > 30.0          # clearly curved
    assert sheared_drift > 10 * (uniform_drift + 1e-6)


# --- size sorts by range ------------------------------------------------------

def test_heavier_particles_land_closer():
    """Under identical uniform wind, a larger (faster-falling) particle lands
    closer to ground zero than a smaller one."""
    wind_u, wind_v = np.full(6, 15.0), np.zeros(6)
    big = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=wind_u, wind_v_ms=wind_v, bins=_single_bin(1500e-6),
    )
    small = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=wind_u, wind_v_ms=wind_v, bins=_single_bin(80e-6),
    )
    big_peak_x = big.x_miles[big.dose_rate_h1.max(axis=0).argmax()]
    small_peak_x = small.x_miles[small.dose_rate_h1.max(axis=0).argmax()]
    assert big_peak_x < small_peak_x


# --- altitude effect on fall speed --------------------------------------------

def test_particle_falls_faster_aloft():
    d = 100e-6
    v_sea = float(fallvelocity.velocity_at_altitude(d, 0.0))
    v_high = float(fallvelocity.velocity_at_altitude(d, 10000.0))
    assert v_high > v_sea


# --- Stokes limit -------------------------------------------------------------

def test_stokes_limit_small_particle():
    rho, mu = atmosphere.properties(0.0)
    d = 5e-6  # tiny -> Re << 1 -> Stokes valid
    full = float(fallvelocity.terminal_velocity(d, rho, mu))
    stokes = float(fallvelocity.stokes_velocity(d, rho, mu))
    assert full == pytest.approx(stokes, rel=0.02)


def test_large_particle_below_stokes():
    """For a big particle, drag correction makes true velocity well below the
    (invalid) Stokes extrapolation."""
    rho, mu = atmosphere.properties(0.0)
    d = 1000e-6
    full = float(fallvelocity.terminal_velocity(d, rho, mu))
    stokes = float(fallvelocity.stokes_velocity(d, rho, mu))
    assert full < 0.2 * stokes


# --- activity conservation / aloft tracking -----------------------------------

def test_fines_stay_aloft_coarse_deposits():
    wind_u, wind_v = np.full(6, 15.0), np.zeros(6)
    fines = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=wind_u, wind_v_ms=wind_v, bins=_single_bin(15e-6),
    )
    coarse = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=wind_u, wind_v_ms=wind_v, bins=_single_bin(1000e-6),
    )
    assert fines.fraction_aloft > 0.5      # tiny particles largely still airborne at t_max
    assert coarse.fraction_aloft < 0.01    # coarse fully deposited


def test_fraction_aloft_bounded():
    r = tier1.simulate(
        yield_mt=0.3, fission_fraction=0.5, heights_m=H,
        wind_u_ms=np.full(6, 10.0), wind_v_ms=np.zeros(6),
    )
    assert 0.0 <= r.fraction_aloft <= 1.0


# --- reduces toward Tier-0 magnitude ------------------------------------------

def test_uniform_wind_magnitude_sane():
    r = tier1.simulate(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=np.full(6, 15.0), wind_v_ms=np.zeros(6),
    )
    assert r.dose_rate_h1.max() > 1000.0   # same order as Tier-0
    assert np.all(r.dose_rate_h1 >= 0.0)


# --- atmosphere sanity --------------------------------------------------------

def test_density_decreases_with_altitude():
    assert atmosphere.density(0.0) > atmosphere.density(5000.0) > atmosphere.density(10000.0)


def test_sea_level_density():
    assert float(atmosphere.density(0.0)) == pytest.approx(1.225, abs=0.01)
