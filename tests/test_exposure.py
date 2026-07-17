"""Tests for the point-exposure assessment (exposure.assess).

Offline and structural, matching this repo's pattern: they check internal
consistency against the same WSEG-10/decay primitives the module composes
(projection round-trip, PF division, window-vs-lifetime relationships), not
against any external reference values.
"""

import math

import pytest

from falloutcast import exposure
from falloutcast.physics import decay
from falloutcast.physics.wseg10 import WSEG10
from falloutcast.schemas import ManualWind, PointExposureRequest


GZ_LAT, GZ_LON = 41.14, -104.82
WIND = ManualWind(speed_mph=15.0, bearing_deg=90.0, shear_mph_per_kft=0.5)


def _req(point_lat, point_lon, **kw):
    return PointExposureRequest(
        lat=GZ_LAT, lon=GZ_LON, yield_mt=0.3, fission_fraction=0.5,
        wind=WIND, point_lat=point_lat, point_lon=point_lon, **kw,
    )


def _model():
    return WSEG10(
        yield_mt=0.3, fission_fraction=0.5,
        wind_mph=15.0, wind_dir_deg=90.0, shear_mph_per_kft=0.5,
    )


def _point_east(miles: float) -> tuple[float, float]:
    """A point `miles` due east of GZ under the module's own projection."""
    return GZ_LAT, GZ_LON + miles / (69.0 * math.cos(math.radians(GZ_LAT)))


def test_matches_direct_model_evaluation():
    """Regression on the lon/lat -> mile-offset conversion: the assessed H+1
    rate and arrival must reproduce a direct WSEG10 call at the equivalent
    (east, north) offset -- same check style as the envelope's."""
    lat, lon = _point_east(30.0)
    resp = exposure.assess(_req(lat, lon))
    model = _model()
    assert resp.dose_rate_h1_rhr == pytest.approx(float(model.dose_rate_h1(30.0, 0.0)), rel=1e-9)
    assert resp.arrival_hours == pytest.approx(float(model.time_of_arrival(30.0, 0.0)), rel=1e-9)
    assert resp.distance_miles == pytest.approx(30.0, rel=1e-9)
    assert resp.bearing_from_gz_deg == pytest.approx(90.0, abs=1e-6)


def test_arrival_increases_downwind_and_respects_floor():
    arrivals = [
        exposure.assess(_req(*_point_east(m))).arrival_hours for m in (1.0, 20.0, 80.0, 200.0)
    ]
    assert arrivals == sorted(arrivals)
    assert all(a >= 0.5 for a in arrivals)


def test_rate_at_arrival_is_way_wigner_at_toa():
    resp = exposure.assess(_req(*_point_east(50.0)))
    expected = float(decay.dose_rate_at(resp.dose_rate_h1_rhr, resp.arrival_hours))
    assert resp.rate_at_arrival_rhr == pytest.approx(expected, rel=1e-9)


def test_protection_factor_divides_doses_exactly():
    lat, lon = _point_east(40.0)
    unshielded = exposure.assess(_req(lat, lon, exit_hours=48.0, protection_factor=1.0))
    pf10 = exposure.assess(_req(lat, lon, exit_hours=48.0, protection_factor=10.0))
    assert pf10.sheltered_dose_window_r == pytest.approx(
        unshielded.unsheltered_dose_window_r / 10.0, rel=1e-9
    )
    assert pf10.sheltered_dose_to_infinity_r == pytest.approx(
        unshielded.unsheltered_dose_to_infinity_r / 10.0, rel=1e-9
    )
    # PF never changes the unshielded (outdoor) values
    assert pf10.unsheltered_dose_window_r == pytest.approx(
        unshielded.unsheltered_dose_window_r, rel=1e-9
    )


def test_window_dose_zero_when_exit_precedes_arrival():
    lat, lon = _point_east(200.0)  # far downwind: arrival is many hours out
    resp = exposure.assess(_req(lat, lon, exit_hours=1.0))
    assert resp.arrival_hours > 1.0  # premise of the scenario
    assert resp.unsheltered_dose_window_r == 0.0
    assert resp.sheltered_dose_window_r == 0.0
    assert any("before" in n and "arriv" in n for n in resp.notes)


def test_window_plus_tail_equals_infinity_dose():
    """Exact additivity of the Way-Wigner integral: dose(arrival->exit) plus
    the analytic tail dose(exit->inf) must equal dose(arrival->inf). (A 'big
    exit ~ infinity' comparison would be wrong: the t^-0.2 tail converges far
    too slowly for that.)"""
    lat, lon = _point_east(40.0)
    resp = exposure.assess(_req(lat, lon, exit_hours=24.0))
    tail = float(decay.accumulated_dose_to_infinity(resp.dose_rate_h1_rhr, 24.0))
    assert resp.unsheltered_dose_window_r + tail == pytest.approx(
        resp.unsheltered_dose_to_infinity_r, rel=1e-9
    )
    assert resp.unsheltered_dose_window_r < resp.unsheltered_dose_to_infinity_r


def test_rate_curve_starts_at_or_after_arrival():
    lat, lon = _point_east(120.0)
    resp = exposure.assess(_req(lat, lon))
    assert resp.rate_curve, "expected at least one sample within 168 h"
    assert all(s.t_hours >= resp.arrival_hours for s in resp.rate_curve)
    rates = [s.dose_rate_rhr for s in resp.rate_curve]
    assert rates == sorted(rates, reverse=True)  # monotone decay


def test_negligible_point_is_flagged():
    resp = exposure.assess(_req(GZ_LAT + 5.0, GZ_LON))  # ~345 mi crosswind/north
    assert resp.dose_rate_h1_rhr < 1e-3
    assert any("outside the modeled deposition" in n for n in resp.notes)
