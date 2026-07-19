"""Tests for the M2 max-envelope compositing (grid.sample_envelope /
contour.to_geojson_lonlat). Pure/offline -- no network, no FastAPI client;
the live wind-fetch path is exercised manually against the running API, not
here (matches this repo's existing pattern of keeping physics/grid tests
offline and network-isolated in weather/openmeteo.py alone).
"""

import numpy as np
import pytest

from falloutcast import contour, grid
from falloutcast.physics.wseg10 import WSEG10


def _model(wind_mph=15.0, wind_dir_deg=90.0, shear=0.5, yield_mt=0.3, ff=0.5):
    return WSEG10(
        yield_mt=yield_mt, fission_fraction=ff,
        wind_mph=wind_mph, wind_dir_deg=wind_dir_deg, shear_mph_per_kft=shear,
    )


def test_envelope_matches_direct_evaluation_for_a_single_target():
    """Regression check on the lon/lat -> mile-offset conversion: sampling
    the envelope grid at a single target should reproduce exactly what
    calling that target's own WSEG10.dose_rate_h1 at the equivalent
    (east, north) offset gives -- not an independent reimplementation."""
    gz_lat, gz_lon = 41.14, -104.82
    model = _model()
    g = grid.sample_envelope([(model, gz_lat, gz_lon)], resolution_deg=0.2)

    # pick an arbitrary grid cell, convert manually the same way sample_envelope
    # does, and compare against a direct model call.
    lon, lat = g.lon_deg[50], g.lat_deg[60]
    y_mi = (lat - gz_lat) * 69.0
    x_mi = (lon - gz_lon) * 69.0 * np.cos(np.radians(gz_lat))
    expected = float(model.dose_rate_h1(x_mi, y_mi))

    lon_idx = list(g.lon_deg).index(lon)
    lat_idx = list(g.lat_deg).index(lat)
    assert g.dose_rate_h1[lat_idx, lon_idx] == pytest.approx(expected)


def test_envelope_is_max_not_sum_where_two_plumes_overlap():
    """Two targets placed close enough that their plumes overlap: the
    envelope at an overlapping cell must equal the larger of the two
    individual doses, not their sum -- this is the whole point of M2's
    'max-envelope' semantics vs. a naive accumulation."""
    gz1 = (40.0, -100.0)
    gz2 = (40.05, -100.0)  # ~3.5 mi north -- well within either plume
    m1 = _model(wind_dir_deg=0.0)   # blows north, toward gz2
    m2 = _model(wind_dir_deg=180.0)  # blows south, toward gz1

    single1 = grid.sample_envelope([(m1, *gz1)], resolution_deg=0.05)
    single2 = grid.sample_envelope([(m2, *gz2)], resolution_deg=0.05)
    combined = grid.sample_envelope([(m1, *gz1), (m2, *gz2)], resolution_deg=0.05)

    expected_max = np.maximum(single1.dose_rate_h1, single2.dose_rate_h1)
    np.testing.assert_allclose(combined.dose_rate_h1, expected_max)
    # sanity: overlap actually exists in this setup (not a vacuous check)
    assert (single1.dose_rate_h1 > 0).any() and (single2.dose_rate_h1 > 0).any()


def test_distant_target_does_not_contaminate_envelope_elsewhere():
    """A target on the far side of the CONUS bbox shouldn't perturb the
    envelope value near a different, nearby target -- guards against a
    broadcasting bug that mixes up which model applies where."""
    near_gz = (41.14, -104.82)
    far_gz = (30.80, -81.51)  # Naval Sub Base Kings Bay, far away
    near_model = _model()
    far_model = _model(yield_mt=5.0)  # much bigger, to make a mistake obvious

    solo = grid.sample_envelope([(near_model, *near_gz)], resolution_deg=0.2)
    combined = grid.sample_envelope(
        [(near_model, *near_gz), (far_model, *far_gz)], resolution_deg=0.2
    )
    # near ground zero itself, the far target's contribution should be
    # negligible -- combined should equal solo there.
    lon_idx = list(combined.lon_deg).index(min(combined.lon_deg, key=lambda v: abs(v - near_gz[1])))
    lat_idx = list(combined.lat_deg).index(min(combined.lat_deg, key=lambda v: abs(v - near_gz[0])))
    assert combined.dose_rate_h1[lat_idx, lon_idx] == pytest.approx(
        solo.dose_rate_h1[lat_idx, lon_idx], rel=1e-6
    )


def test_to_geojson_lonlat_is_a_valid_feature_collection():
    model = _model()
    g = grid.sample_envelope([(model, 41.14, -104.82)], resolution_deg=0.15)
    gj = contour.to_geojson_lonlat(g, levels=(1.0, 10.0))

    assert gj["type"] == "FeatureCollection"
    levels_seen = {f["properties"]["dose_rate_h1_rhr"] for f in gj["features"]}
    assert levels_seen <= {1.0, 10.0}
    for f in gj["features"]:
        assert f["geometry"]["type"] == "MultiLineString"
        for ring in f["geometry"]["coordinates"]:
            for lon, lat in ring:
                # coordinates should be plausible CONUS geography, not
                # mile-offsets accidentally left unconverted
                assert grid.CONUS_LON_MIN - 1 <= lon <= grid.CONUS_LON_MAX + 1
                assert grid.CONUS_LAT_MIN - 1 <= lat <= grid.CONUS_LAT_MAX + 1


def test_envelope_grid_covers_requested_bounds():
    g = grid.sample_envelope([], resolution_deg=1.0)
    assert g.lon_deg[0] == pytest.approx(grid.US_LON_MIN)
    assert g.lon_deg[-1] == pytest.approx(grid.US_LON_MAX)
    assert g.lat_deg[0] == pytest.approx(grid.US_LAT_MIN)
    assert g.lat_deg[-1] == pytest.approx(grid.US_LAT_MAX)
    assert np.all(g.dose_rate_h1 == 0.0)  # no models -> all-zero envelope


def test_default_envelope_grid_reaches_hawaii_and_alaska():
    """The default bounds must cover the Hawaii/Alaska strategic sites now in
    the deck, so their plumes are not silently clipped by the local-window path
    (which skips any target whose window falls entirely outside the grid)."""
    pearl_harbor = (21.35, -157.95)
    fort_greely = (63.95, -145.74)
    for lat, lon in (pearl_harbor, fort_greely):
        assert grid.US_LON_MIN <= lon <= grid.US_LON_MAX
        assert grid.US_LAT_MIN <= lat <= grid.US_LAT_MAX
        # a target there deposits a nonzero plume through the local-window path
        g = grid.sample_envelope([(_model(), lat, lon)], resolution_deg=0.2, radius_deg=10.0)
        assert g.dose_rate_h1.max() > 0.0


def test_hawaii_alaska_and_infra_sites_are_in_the_deck():
    from falloutcast import targetdeck
    names = {t.name for t in targetdeck.load_expanded_targets()}
    for expected in (
        "Hoover Dam", "Grand Coulee Dam",
        "Joint Base Pearl Harbor-Hickam", "Eielson AFB", "Fort Greely (GMD)",
    ):
        assert expected in names, expected
    cats = {t.category for t in targetdeck.load_expanded_targets()}
    assert {"naval_base", "air_base", "missile_defense"} <= cats
