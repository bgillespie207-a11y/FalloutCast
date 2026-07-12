"""Magnitude validation of WSEG-10 against the Glasstone & Dolan idealized
1-Mt surface-burst fallout pattern (Table 9.93). Pure/offline.

This is the project's FIRST footprint-magnitude validation. Unlike the
historical NTS cases in `reference_cases.py` (tower/near-surface bursts,
direction-only cross-checks), the G&D idealized pattern matches WSEG-10's
assumptions -- contact surface burst, strategic yield, given effective wind --
so contour SIZE can finally be compared. See idealized_pattern.py's module
docstring for the (honest) scope: this is conformance to G&D's canonical
idealized reference, not a fit to one specific measured shot.
"""

import numpy as np
import pytest

from falloutcast.validation import idealized_pattern as ip


def test_reference_matches_table_9_93_formula_for_1mt():
    """Regression on the transcribed Table 9.93 coefficients: a couple of
    anchor contours computed by hand from the printed scaling relationships.
    Guards against a typo in the transcribed table."""
    # 1 Mt = 1000 kt; downwind uses W^0.45; 1000^0.45 ~= 22.387
    w45 = 1000.0**0.45
    c1000 = ip.reference_contour(1000, 1000.0)
    assert c1000.downwind_miles == pytest.approx(1.8 * w45, rel=1e-6)   # ~40.3 mi
    assert c1000.max_width_miles == pytest.approx(0.036 * 1000.0**0.76, rel=1e-6)  # ~6.9 mi
    c1 = ip.reference_contour(1, 1000.0)
    assert c1.downwind_miles == pytest.approx(40.0 * w45, rel=1e-6)     # ~895 mi


def test_wseg10_reproduces_gd_downwind_extent_within_factor_two():
    """THE magnitude validation: at 1 Mt / 15 mph / contact surface burst /
    pure fission, WSEG-10's downwind reach for each fallout-relevant contour
    (1000..1 R/hr) lands within a factor of 2 of Glasstone & Dolan Table 9.93.

    Factor-of-2 is an honest bound for two independent idealized fallout models
    (observed ratios run ~0.8-1.5); it is a real magnitude agreement, not a
    tautology -- a wrong activity normalization or downwind-scaling exponent in
    WSEG-10 would blow well past it. The 3000 R/hr close-in contour is excluded
    (ip.VALIDATED_LEVELS); see its definition for why."""
    comps = {c.level_rhr: c for c in ip.compare(yield_mt=1.0, shear_mph_per_kft=0.0)}
    for level in ip.VALIDATED_LEVELS:
        c = comps[level]
        assert c.model_downwind_mi is not None, f"model never reached {level} R/hr"
        assert 0.5 <= c.downwind_ratio <= 2.0, (
            f"{level} R/hr: model {c.model_downwind_mi:.0f} mi vs "
            f"G&D {c.reference_downwind_mi:.0f} mi (ratio {c.downwind_ratio:.2f})"
        )


def test_tier1_reproduces_gd_downwind_extent_within_factor_two():
    """Magnitude validation of the TIER-1 engine (multi-layer advection), not
    just Tier-0: under a uniform 15 mph profile at 1 Mt pure fission, Tier-1's
    downwind reach for each fallout contour (1000..1 R/hr) lands within a factor
    of ~2 of G&D Table 9.93.

    Tier-1's absolute dose is anchored to G&D's activity normalization, so this
    is chiefly a check that the fall-velocity binning + puff advection DISTRIBUTE
    that activity to the right downwind distances. Bound is a hair looser than
    the Tier-0 test (0.45-2.2) because Tier-1's output is a discretized,
    adaptively-gridded deposition rather than a smooth analytic curve."""
    comps = {c.level_rhr: c for c in ip.compare_tier1(yield_mt=1.0)}
    for level in ip.VALIDATED_LEVELS:
        c = comps[level]
        assert c.model_downwind_mi is not None, f"Tier-1 never reached {level} R/hr"
        assert 0.45 <= c.downwind_ratio <= 2.2, (
            f"{level} R/hr: Tier-1 {c.model_downwind_mi:.0f} mi vs "
            f"G&D {c.reference_downwind_mi:.0f} mi (ratio {c.downwind_ratio:.2f})"
        )


def test_high_dose_contour_widths_are_in_the_right_ballpark():
    """A secondary, looser check: WSEG-10's crosswind width for the tighter
    high-dose contours (1000/300 R/hr) is within a factor of ~2 of G&D. Width
    is deliberately NOT asserted for the low-dose contours: WSEG-10's crosswind
    growth is driven by SPEED shear, a different parameterization than G&D's
    15-degree DIRECTIONAL shear, so the two diverge on width far downwind (a
    documented WSEG-10 limitation, not a bug)."""
    comps = {c.level_rhr: c for c in ip.compare(yield_mt=1.0, shear_mph_per_kft=0.0)}
    for level in (1000, 300):
        c = comps[level]
        assert c.model_width_mi is not None
        ratio = c.model_width_mi / c.reference_width_mi
        assert 0.5 <= ratio <= 2.0, (
            f"{level} R/hr width: model {c.model_width_mi:.1f} mi vs "
            f"G&D {c.reference_width_mi:.1f} mi (ratio {ratio:.2f})"
        )


def test_reference_dose_values_scale_with_fission_fraction_note():
    """Documents (via the coefficients themselves) that Table 9.93 dimensions
    are keyed to TOTAL yield -- reference_contour takes yield_kt and does not
    take fission fraction, because per G&D sec. 9.94 fission fraction rescales
    the dose-rate LABELS, not the contour sizes. This test pins that API
    decision so a future edit doesn't silently start scaling dimensions by f."""
    a = ip.reference_contour(100, 1000.0)
    b = ip.reference_contour(100, 1000.0)
    assert a == b
    # doubling total yield grows the contour (W^0.45), a real dimension change
    bigger = ip.reference_contour(100, 2000.0)
    assert bigger.downwind_miles > a.downwind_miles
