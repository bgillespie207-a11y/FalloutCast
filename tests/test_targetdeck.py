"""Structural tests for the expanded target deck and the local-window envelope
path. Pure/offline (no network) -- matches this repo's convention of keeping
physics/grid/data tests network-isolated.

These are structural/property checks, not validated against any external truth:
the LF/LCC positions are an illustrative distribution by design (see
targetdeck.py's honesty note), so there is nothing external to assert them
against -- only the invariants the generator promises.
"""

import numpy as np
import pytest

from falloutcast import grid, targetdeck
from falloutcast.physics.wseg10 import WSEG10


def test_each_wing_has_real_minuteman_structure():
    for wing in targetdeck.WINGS:
        pts = targetdeck.generate_wing(wing)
        lf = [t for t in pts if t.category == "icbm_lf"]
        lcc = [t for t in pts if t.category == "icbm_lcc"]
        assert len(lf) == targetdeck.LF_PER_WING == 150
        assert len(lcc) == targetdeck.LCC_PER_WING == 15


def test_generated_points_stay_within_the_documented_footprint():
    for wing in targetdeck.WINGS:
        for t in targetdeck.generate_wing(wing):
            assert wing.lon_min <= t.lon <= wing.lon_max
            assert wing.lat_min <= t.lat <= wing.lat_max


def test_generation_is_deterministic():
    a = targetdeck.generate_all_fields()
    b = targetdeck.generate_all_fields()
    assert [(t.name, t.lat, t.lon) for t in a] == [(t.name, t.lat, t.lon) for t in b]


def test_expanded_deck_supersedes_single_point_icbm_fields():
    full = targetdeck.load_expanded_targets()
    # the three single icbm_field points are dropped in favor of resolved fields
    assert not any(t.category == "icbm_field" for t in full)
    # fields + HVTs are present
    assert sum(t.category == "icbm_lf" for t in full) == 450
    assert any(t.category == "city_population" for t in full)
    assert any(t.category == "command" for t in full)


def test_per_class_yields_differentiate_silos_from_cities():
    """Silos carry the sourced ~0.30 Mt counterforce yield; countervalue/
    hardened-C2 classes carry a higher illustrative yield. yield_for must
    reflect that (so footprints differ by class) and fall back cleanly."""
    silo_y, silo_ff = targetdeck.yield_for("icbm_lf")
    city_y, _ = targetdeck.yield_for("city_population")
    assert silo_y == 0.30
    assert 0.0 < silo_ff <= 1.0
    assert city_y > silo_y  # bigger yield -> larger footprint, the whole point
    # unknown category -> documented default, never a crash
    assert targetdeck.yield_for("nonexistent") == (0.30, 0.5)


def test_higher_class_yield_produces_a_larger_footprint():
    """Sanity that a city's yield actually makes a bigger plume than a silo's
    under identical wind -- confirms the per-class table feeds through WSEG-10
    the way the feature intends."""
    silo_y, silo_ff = targetdeck.yield_for("icbm_lf")
    city_y, city_ff = targetdeck.yield_for("city_population")
    wind = dict(wind_mph=15.0, wind_dir_deg=90.0, shear_mph_per_kft=0.5)
    silo = WSEG10(yield_mt=silo_y, fission_fraction=silo_ff, **wind)
    city = WSEG10(yield_mt=city_y, fission_fraction=city_ff, **wind)
    # area above 1 R/hr on a shared local grid
    g = grid.sample_envelope  # noqa: F841 (documenting intent)
    import numpy as np
    axis = np.linspace(-300, 300, 121)
    gx, gy = np.meshgrid(axis, axis)
    silo_area = (silo.dose_rate_h1(gx, gy) >= 1.0).sum()
    city_area = (city.dose_rate_h1(gx, gy) >= 1.0).sum()
    assert city_area > silo_area


def _model(gz_lat, gz_lon):
    return WSEG10(
        yield_mt=0.3, fission_fraction=0.5,
        wind_mph=15.0, wind_dir_deg=90.0, shear_mph_per_kft=0.5,
    ), gz_lat, gz_lon


def test_local_radius_matches_full_grid_near_a_target():
    """The radius-limited path must reproduce the full-grid path at cells
    within the radius, and be zero well outside it -- guards the windowing/
    slicing math against an off-by-one that would shift or drop a target's
    contribution."""
    m = _model(41.14, -104.82)
    full = grid.sample_envelope([m], resolution_deg=0.2)
    windowed = grid.sample_envelope([m], resolution_deg=0.2, radius_deg=6.0)

    gz_lat, gz_lon = 41.14, -104.82
    within = (np.abs(windowed.lat_deg[:, None] - gz_lat) <= 6.0) & (
        np.abs(windowed.lon_deg[None, :] - gz_lon) <= 6.0
    )
    # inside the window, the two agree exactly
    np.testing.assert_allclose(windowed.dose_rate_h1[within], full.dose_rate_h1[within])
    # outside the window the windowed path deposits nothing
    assert np.all(windowed.dose_rate_h1[~within] == 0.0)


def test_local_radius_scales_to_the_full_deck_cheaply():
    """Sanity that the whole expanded deck composites through the local path
    without error and produces a non-trivial dose field (three overlapping
    missile fields guarantee a hot envelope)."""
    models = [_model(t.lat, t.lon) for t in targetdeck.load_expanded_targets()]
    g = grid.sample_envelope(models, resolution_deg=0.2, radius_deg=8.0)
    assert g.dose_rate_h1.max() > 100.0  # dense silo overlap -> high dose rate
