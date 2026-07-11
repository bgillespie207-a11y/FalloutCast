"""Structural test of the footprint-validation harness plumbing.

This still does NOT tightly validate Tier-1's physics against a real
footprint -- the target points in `SMALL_BOY_DIGITIZED_POINTS` are hand-traced
from a low-resolution 1970s photocopy scan (approximate by construction,
see each point's `note`), and the burst-height mismatch (module docstring,
gap 1) means even a perfect match wouldn't be a clean validation. What CAN
be asserted honestly: the harness code runs correctly (most tests below, via
a synthetic wind profile), and the model's own bearing lands in the same
broad compass quadrant as the independently-traced digitized points when run
against the real historical wind -- a loose sanity bound wide enough to
reflect the real uncertainty here, not a precision check.
"""

import numpy as np
import pytest

from falloutcast.physics import tier1
from falloutcast.validation import reference_cases as ref

H = np.array([100.0, 1500.0, 3000.0, 5500.0, 9000.0, 12000.0])


def test_run_case_returns_finite_bounded_summary():
    result = ref.run_case(
        ref.SMALL_BOY_1962,
        heights_m=H,
        wind_u_ms=np.full(6, 5.0),
        wind_v_ms=np.zeros(6),
        fission_fraction=1.0,
    )
    assert result.case_name == "Small Boy"
    assert np.isfinite(result.downwind_reach_miles)
    assert result.downwind_reach_miles > 0
    assert 0.0 <= result.fraction_aloft <= 1.0
    assert result.hotline_bearing_deg is None or 0.0 <= result.hotline_bearing_deg < 360.0


def test_run_case_converts_yield_kt_to_mt_correctly():
    """run_case must call tier1.simulate with yield_mt = case.yield_kt / 1000,
    not e.g. yield_kt reinterpreted as yield_mt directly. Cross-checked
    against a direct tier1.simulate call with the same (deterministic, no
    randomness) inputs -- a real regression check for the harness glue, not
    a physics claim."""
    wind_u, wind_v = np.full(6, 5.0), np.zeros(6)
    result = ref.run_case(
        ref.SMALL_BOY_1962,
        heights_m=H, wind_u_ms=wind_u, wind_v_ms=wind_v, fission_fraction=1.0,
    )
    direct = tier1.simulate(
        yield_mt=ref.SMALL_BOY_1962.yield_kt / 1000.0,
        fission_fraction=1.0,
        heights_m=H, wind_u_ms=wind_u, wind_v_ms=wind_v,
    )
    np.testing.assert_allclose(result.tier1.dose_rate_h1, direct.dose_rate_h1)
    assert result.fraction_aloft == direct.fraction_aloft


def test_reference_case_fields_document_their_own_uncertainty():
    """Every field that isn't a hard fact must say so in its own text --
    this is a documentation-completeness check, not a physics check: it
    guards against a future edit silently dropping the uncertainty caveats
    (project rule 2/3) rather than updating them."""
    case = ref.SMALL_BOY_1962
    for field_name in ("yield_source", "burst_type_note", "fission_fraction_note",
                       "footprint_target_note"):
        text = getattr(case, field_name)
        assert len(text) > 20, f"{field_name} looks unpopulated"


def test_small_boy_wind_h5min_shape_and_units():
    """Digitized DNA 1251-1-EX Table 109 sounding: same length across all
    three returned arrays, heights strictly increasing (source table is
    altitude-ordered), and the fastest tabulated leg (20,000 ft, 280 deg,
    28.8 mph) converts to the expected ~12.9 m/s -- catches a unit-conversion
    regression (mph/ft mixed up with m/s/m) without re-asserting the whole
    table."""
    heights_m, u, v = ref.small_boy_wind_h5min()
    assert len(heights_m) == len(u) == len(v) == len(ref.SMALL_BOY_WIND_H5MIN_FT_MSL)
    assert np.all(np.diff(heights_m) > 0)
    top_speed_ms = np.hypot(u[-1], v[-1])
    assert top_speed_ms == pytest.approx(28.8 * 0.44704, rel=1e-3)


def test_run_case_with_real_small_boy_wind_is_finite_and_bounded():
    """End-to-end integration of the real digitized sounding through
    run_case -- not a physics validation (see module docstring: still no
    tight target), just confirms the real-data path produces sane,
    finite, non-crashing output the way the synthetic-wind tests above do."""
    heights_m, u, v = ref.small_boy_wind_h5min()
    result = ref.run_case(
        ref.SMALL_BOY_1962, heights_m=heights_m, wind_u_ms=u, wind_v_ms=v,
        fission_fraction=1.0, t_max_s=48 * 3600.0,
    )
    assert np.isfinite(result.downwind_reach_miles)
    assert result.downwind_reach_miles > 0
    assert 0.0 <= result.fraction_aloft <= 1.0


def test_digitized_contour_point_bearing_and_distance_math():
    """Regression check on DigitizedContourPoint's derived properties --
    plain trigonometry (x=east, y=north convention matching
    weather.openmeteo._dir_to_uv), verified against hand-computed values for
    a simple case so a future refactor can't silently flip x/y or the
    arctan2 argument order without a test catching it."""
    p = ref.DigitizedContourPoint(
        label="test", x_mi=3.0, y_mi=4.0, dose_rate_rhr=1.0,
        source_figure="n/a", note="n/a",
    )
    assert p.distance_mi == pytest.approx(5.0)
    assert p.bearing_deg == pytest.approx(36.87, abs=0.01)  # atan2(3,4)

    due_north = ref.DigitizedContourPoint(
        label="test", x_mi=0.0, y_mi=10.0, dose_rate_rhr=1.0,
        source_figure="n/a", note="n/a",
    )
    assert due_north.bearing_deg == pytest.approx(0.0)

    due_east = ref.DigitizedContourPoint(
        label="test", x_mi=10.0, y_mi=0.0, dose_rate_rhr=1.0,
        source_figure="n/a", note="n/a",
    )
    assert due_east.bearing_deg == pytest.approx(90.0)


def test_digitized_points_are_documented_and_ordered_by_distance():
    """Each digitized point must carry its sourcing note (rule 1/2: no
    unsourced numbers presented as fact), and -- since all three were traced
    off figures at increasing map scale (29mi, 300mi, 300mi) representing
    increasingly far features of the same plume -- their distances should be
    monotonically increasing in the order captured. This would catch a
    transposed x_mi/y_mi typo between points."""
    points = ref.SMALL_BOY_DIGITIZED_POINTS
    assert len(points) >= 3
    for p in points:
        assert len(p.note) > 20, f"{p.label} note looks unpopulated"
        assert len(p.source_figure) > 5
    distances = [p.distance_mi for p in points]
    assert distances == sorted(distances)


def test_model_bearing_lands_in_same_quadrant_as_digitized_points():
    """Loose sanity bound, not a validation: run Tier-1 against the real
    digitized wind and check its hotline bearing falls within a generous
    +-45 deg band of the digitized points' bearing range. The band is wide
    on purpose -- the digitized points are hand-traced from a low-resolution
    scan (+-5-10 deg bearing uncertainty per DigitizedContourPoint's
    docstring), the wind used is a single H+5min snapshot rather than a full
    multi-day reconstruction, and the burst-height mismatch (module
    docstring gap 1) means exact agreement was never expected. This exists
    to catch a GROSS error (wind sign flip, wrong u/v convention, transposed
    axes) rather than to claim quantitative footprint validation."""
    heights_m, u, v = ref.small_boy_wind_h5min()
    result = ref.run_case(
        ref.SMALL_BOY_1962, heights_m=heights_m, wind_u_ms=u, wind_v_ms=v,
        fission_fraction=1.0, t_max_s=48 * 3600.0,
    )
    digitized_bearings = [p.bearing_deg for p in ref.SMALL_BOY_DIGITIZED_POINTS]
    lo, hi = min(digitized_bearings) - 45.0, max(digitized_bearings) + 45.0
    assert result.hotline_bearing_deg is not None
    assert lo <= result.hotline_bearing_deg <= hi
