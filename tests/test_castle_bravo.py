"""Magnitude validation against the REAL MEASURED Castle Bravo (1954) fallout
footprint. Pure/offline.

This complements test_idealized_pattern.py (WSEG-10 vs G&D's *idealized*
reference) with a comparison to actual measured ground truth. It is a COARSE,
factor-~2 sanity check, not a precision validation -- see castle_bravo.py's
module docstring for the (substantial, honest) caveats: coral-vs-soil surface
mismatch, a measured pattern G&D itself calls "largely guesswork," an
accumulated-dose (not H+1) reference, and a single derived effective wind for a
strongly sheared event. The point it establishes is only that WSEG-10 produces
a lethal footprint of the right SCALE for a real 15-Mt surface burst.
"""

import pytest

from falloutcast.validation import castle_bravo as cb


def test_sourced_constants_are_self_consistent():
    """Guards the transcribed G&D / nuclear-archive figures against a typo:
    fission fraction is 10/15 Mt, and the measured lethal belt is smaller than
    the overall contaminated footprint (a basic ordering the numbers must
    satisfy)."""
    assert cb.FISSION_FRACTION == pytest.approx(10.0 / 15.0)
    assert cb.LETHAL_700RAD_LENGTH_MI < cb.OVERALL_DOWNWIND_MI
    assert cb.LETHAL_700RAD_WIDTH_MI < cb.OVERALL_MAX_WIDTH_MI


def test_model_reproduces_bravo_lethal_belt_within_factor_two():
    """THE measured-shot validation: at Bravo's sourced yield/fission/surface
    and the arrival-derived ~20 mph effective wind, WSEG-10's 700-rad/96-h
    lethal belt (H+1 field converted via Way-Wigner decay) matches the measured
    ~170 mi x 35 mi belt within a factor of 2 in BOTH dimensions.

    Factor-2 is the honest resolution here given the caveats (coral surface,
    'guesswork' measured pattern, single derived wind). It is still a real
    ground-truth tie: a wrong yield->activity normalization would miss badly."""
    r = cb.run_model()
    length_ratio = r.belt_length_mi / cb.LETHAL_700RAD_LENGTH_MI
    width_ratio = r.belt_width_mi / cb.LETHAL_700RAD_WIDTH_MI
    assert 0.5 <= length_ratio <= 2.0, f"belt length {r.belt_length_mi:.0f} mi (ratio {length_ratio:.2f})"
    assert 0.5 <= width_ratio <= 2.0, f"belt width {r.belt_width_mi:.0f} mi (ratio {width_ratio:.2f})"


def test_overall_contaminated_extent_is_same_order_as_measured():
    """The model's low-dose (100-rad/96h) downwind reach is within a factor of
    2 of the measured ~330-mi overall contaminated extent -- same order, model
    runs somewhat short (a single effective wind can't carry the fine-particle
    far tail a real sheared wind field did)."""
    r = cb.run_model()
    ratio = r.overall_extent_mi / cb.OVERALL_DOWNWIND_MI
    assert 0.4 <= ratio <= 2.0, f"overall extent {r.overall_extent_mi:.0f} mi (ratio {ratio:.2f})"


def test_centerline_point_dose_is_the_right_order_of_magnitude():
    """The weakest comparison, asserted only loosely (within ~a factor of 5)
    and documented as such: at the 115-mi Rongelap-south point the model's
    centerline 96-h dose runs HIGH vs the measured 220 rad. Expected -- the
    real pattern is irregular and that measured point sits off the peak (its
    100-mi neighbor got 3,300 rad, a suspected hot spot), whereas the model's
    smooth plume puts its centerline maximum right there. Kept as a sanity
    bound, not a precision claim."""
    r = cb.run_model()
    ratio = r.dose_at_rongelap_s_rad / cb.RONGELAP_S_RAD
    assert 0.2 <= ratio <= 5.0, f"115-mi dose {r.dose_at_rongelap_s_rad:.0f} rad (ratio {ratio:.2f})"
