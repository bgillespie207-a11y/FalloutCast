"""Correctness tests for the WSEG-10 engine and decay math.

We don't have Hanifen's exact printed sample outputs to assert against, so
these tests pin down (a) structural properties the model MUST satisfy and
(b) order-of-magnitude sanity for a canonical 1 Mt surface burst. If a future
change breaks one of these, something is wrong.
"""

import numpy as np
import pytest

from falloutcast.physics import WSEG10, decay, units


def make_model(wind_dir_deg=90.0, wind_mph=15.0, yld=1.0, ff=1.0, shear=0.5):
    return WSEG10(
        yield_mt=yld,
        fission_fraction=ff,
        wind_mph=wind_mph,
        wind_dir_deg=wind_dir_deg,
        shear_mph_per_kft=shear,
    )


# --- derived cloud constants -------------------------------------------------

def test_cloud_height_increases_with_yield():
    small = make_model(yld=0.01)
    big = make_model(yld=5.0)
    assert big.H_c > small.H_c > 0


def test_n_uses_F_not_fission_fraction():
    """n must be identical for ff=1.0 and ff=0.5 (regression on the classic bug
    where fission fraction was wrongly substituted for the F scale factor)."""
    a = make_model(ff=1.0)
    b = make_model(ff=0.5)
    assert a.n == pytest.approx(b.n)


# --- dose-rate field ---------------------------------------------------------

def test_dose_rate_positive_downwind():
    m = make_model()  # wind toward east
    # 10 mi due east of GZ (downwind) should have positive dose rate
    assert m.dose_rate_h1(10.0, 0.0) > 0.0


def test_crosswind_symmetry():
    m = make_model()  # downwind = +x (east)
    left = m.dose_rate_h1(20.0, 5.0)
    right = m.dose_rate_h1(20.0, -5.0)
    assert left == pytest.approx(right, rel=1e-9)


def test_hotline_is_peak_across_wind():
    m = make_model()
    on = m.dose_rate_h1(20.0, 0.0)
    off = m.dose_rate_h1(20.0, 8.0)
    assert on > off


def test_downwind_falls_off_far_out():
    m = make_model()
    near = m.dose_rate_h1(20.0, 0.0)
    far = m.dose_rate_h1(300.0, 0.0)
    assert near > far


def test_little_fallout_far_upwind():
    m = make_model()  # wind toward east; upwind is -x (west)
    downwind = m.dose_rate_h1(30.0, 0.0)
    upwind = m.dose_rate_h1(-30.0, 0.0)
    assert upwind < downwind
    assert upwind < 1.0  # essentially negligible upwind


def test_fission_fraction_scales_linearly():
    full = make_model(ff=1.0).dose_rate_h1(25.0, 0.0)
    half = make_model(ff=0.5).dose_rate_h1(25.0, 0.0)
    assert half == pytest.approx(0.5 * full, rel=1e-9)


def test_wind_direction_rotates_plume():
    east = make_model(wind_dir_deg=90.0)   # plume east
    north = make_model(wind_dir_deg=0.0)   # plume north
    # point 25 mi east: hot for east-plume, cold for north-plume
    assert east.dose_rate_h1(25.0, 0.0) > north.dose_rate_h1(25.0, 0.0)
    # point 25 mi north: hot for north-plume
    assert north.dose_rate_h1(0.0, 25.0) > east.dose_rate_h1(0.0, 25.0)


def test_one_megaton_order_of_magnitude():
    """Canonical 1 Mt, 15 mph: near-in hotline dose rates are enormous
    (thousands+ R/hr) and there is a meaningful 1 R/hr footprint far downwind."""
    m = make_model(yld=1.0, wind_mph=15.0)
    xs = np.linspace(1.0, 400.0, 400)
    profile = m.dose_rate_h1(xs, np.zeros_like(xs))
    assert profile.max() > 1000.0                 # intense close in
    # 1 R/hr contour reaches well past 100 mi downwind
    reach = xs[profile >= 1.0].max()
    assert reach > 100.0


def test_vectorized_grid_shape():
    m = make_model()
    xs = np.linspace(-50, 300, 60)
    ys = np.linspace(-60, 60, 40)
    gx, gy = np.meshgrid(xs, ys)
    field = m.dose_rate_h1(gx, gy)
    assert field.shape == gx.shape
    assert np.all(field >= 0.0)


# --- time of arrival ---------------------------------------------------------

def test_toa_minimum_half_hour():
    m = make_model()
    assert m.time_of_arrival(0.0, 0.0) >= 0.5


def test_toa_increases_downwind():
    m = make_model()
    near = m.time_of_arrival(20.0, 0.0)
    far = m.time_of_arrival(200.0, 0.0)
    assert far > near


# --- decay -------------------------------------------------------------------

def test_decay_reduces_dose_rate():
    r1 = 1000.0
    assert decay.dose_rate_at(r1, 7.0) < r1
    # 7x rule of thumb: ~7 hours -> ~1/10 the rate
    assert decay.dose_rate_at(r1, 7.0) == pytest.approx(r1 * 7.0 ** -1.2, rel=1e-9)


def test_accumulated_dose_matches_closed_form():
    r1 = 500.0
    # numeric integral vs closed form
    t = np.linspace(1.0, 49.0, 200000)
    rate = decay.dose_rate_at(r1, t)
    numeric = np.trapezoid(rate, t)
    closed = decay.accumulated_dose(r1, 1.0, 49.0)
    assert closed == pytest.approx(numeric, rel=1e-3)


def test_infinite_dose_is_finite_and_bounded():
    r1 = 500.0
    # the t**-0.2 tail converges slowly; need a very large upper bound
    finite = decay.accumulated_dose(r1, 1.0, 1e12)
    to_inf = decay.accumulated_dose_to_infinity(r1, 1.0)
    assert to_inf == pytest.approx(finite, rel=1e-2)


# --- units -------------------------------------------------------------------

def test_speed_roundtrip():
    assert units.mph_to_ms(units.ms_to_mph(10.0)) == pytest.approx(10.0)


def test_known_speed_conversion():
    assert units.ms_to_mph(10.0) == pytest.approx(22.369, abs=1e-2)
