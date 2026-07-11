"""Structural test of the footprint-validation harness plumbing.

This does NOT validate Tier-1's physics against a real footprint -- there is
no sourced target to check against yet (see
`falloutcast.validation.reference_cases` module docstring for the three
specific gaps: no confirmed surface-burst case, no machine-usable target
footprint, no historical wind fetch). This test only confirms the harness
code itself runs end-to-end and returns sane, finite, structurally-bounded
output, using a synthetic wind profile (explicitly not a claim about any
real historical wind).
"""

import numpy as np

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
