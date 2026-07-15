"""Attack-scenario yield assumptions (separate from target metadata) and the
max-vs-sum aggregation semantics. Pure/offline.
"""

import numpy as np
import pytest

from falloutcast import grid, scenario
from falloutcast.physics.wseg10 import WSEG10


def test_scenario_yields_differentiate_counterforce_from_countervalue():
    """Counterforce classes carry the lower nominal yield; countervalue a
    higher one -- so footprints differ by class. Unknown category -> default."""
    silo_y, silo_ff = scenario.yield_for("icbm_lf")
    city_y, _ = scenario.yield_for("city_population")
    assert silo_y == 0.30
    assert 0.0 < silo_ff <= 1.0
    assert city_y > silo_y
    assert scenario.yield_for("nonexistent") == (0.30, 0.5)


def test_scenario_assumptions_carry_sensitivity_bands_and_rationale():
    """Each assumption exposes a min/max band (so sensitivity is visible, not
    hidden) and an attacker-framing rationale -- never the target's own weapon."""
    a = scenario.assumption_for("city_population")
    assert a.yield_min_mt <= a.yield_mt <= a.yield_max_mt
    assert a.yield_min_mt < a.yield_max_mt
    assert "illustrative" in a.rationale.lower()
    # the rationale must NOT claim to be the target's resident weapon
    assert "w87" not in a.rationale.lower() and "w78" not in a.rationale.lower()


def test_yield_policy_carries_plan_a_sources_and_notes():
    """The scenario structure is grounded in a citable study (Princeton Plan A);
    the policy must expose those sources and the documented not-yet-modelled
    multi-warhead-per-city caveat, so the framing is auditable."""
    policy = scenario.yield_policy({"city_population"})
    joined = " ".join(policy["sources"]).lower()
    assert "plan a" in joined and "princeton" in joined
    assert "gao 2025" in joined
    assert any("5-10 warheads" in n.lower() or "one ground zero per city" in n.lower()
               for n in policy["scenario_notes"])


def test_yield_policy_is_structured_and_states_surface_burst_caveat():
    """The response yield_policy replaces the old yield_mt:0.0 sentinel: it lists
    per-class assumptions for the categories present and states the surface-burst
    bounding caveat plainly."""
    policy = scenario.yield_policy({"icbm_lf", "city_population"})
    assert policy["mode"] == "per_class"
    assert policy["scenario"] == scenario.SCENARIO_NAME
    assert "surface" in policy["surface_burst_caveat"].lower()
    cats = {a["category"] for a in policy["assumptions"]}
    assert cats == {"icbm_lf", "city_population"}
    for a in policy["assumptions"]:
        assert a["yield_min_mt"] <= a["yield_mt"] <= a["yield_max_mt"]


def _model(gz_lat, gz_lon, y):
    return WSEG10(
        yield_mt=y, fission_fraction=0.5,
        wind_mph=15.0, wind_dir_deg=90.0, shear_mph_per_kft=0.5,
    ), gz_lat, gz_lon


def test_sum_aggregation_exceeds_max_where_two_plumes_overlap():
    """max_single_source (max) takes the larger single contribution; sum ADDS
    them. Where two plumes overlap, sum must exceed max -- the whole point of
    the distinction the review flagged."""
    gz1 = (40.0, -100.0)
    gz2 = (40.05, -100.0)  # ~3.5 mi north, well within either plume
    m1 = _model(*gz1, 0.3)
    m2 = _model(*gz2, 0.3)

    g_max = grid.sample_envelope([m1, m2], resolution_deg=0.05, aggregation="max")
    g_sum = grid.sample_envelope([m1, m2], resolution_deg=0.05, aggregation="sum")

    overlap = (g_max.dose_rate_h1 > 0)
    assert overlap.any()
    # sum >= max everywhere, and strictly greater somewhere in the overlap
    assert np.all(g_sum.dose_rate_h1 >= g_max.dose_rate_h1 - 1e-9)
    assert np.any(g_sum.dose_rate_h1 > g_max.dose_rate_h1 + 1e-6)


def test_unknown_aggregation_raises():
    m = _model(40.0, -100.0, 0.3)
    with pytest.raises(ValueError):
        grid.sample_envelope([m], aggregation="bogus")
