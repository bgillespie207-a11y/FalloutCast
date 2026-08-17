"""The disclaimer each compute path returns must describe the model that path
actually ran.

The frontend renders `response.disclaimer` verbatim into its "Methodology &
limits" panel, so this string IS what the user is told the result came from.
A single shared disclaimer therefore told every Tier-1 and ensemble user that
their result came from "the WSEG-10 analytic fallout model driven by a single
effective wind" -- a model those paths do not run. These tests pin each path to
its own text so that can't silently regress.

Offline/structural only (this repo's rule): they assert which string a path
selects and that the wording carries the caveats that make it honest. They do
not validate any physics.
"""

import pytest

from falloutcast.schemas import (
    DISCLAIMER,
    DISCLAIMER_ENSEMBLE,
    DISCLAIMER_ENVELOPE,
    DISCLAIMER_EXPOSURE,
    DISCLAIMER_TIER0,
    DISCLAIMER_TIER1,
)

ALL = {
    "tier0": DISCLAIMER_TIER0,
    "tier1": DISCLAIMER_TIER1,
    "ensemble": DISCLAIMER_ENSEMBLE,
    "envelope": DISCLAIMER_ENVELOPE,
    "exposure": DISCLAIMER_EXPOSURE,
}


def test_every_disclaimer_is_distinct():
    """The whole point of the split: no two paths share text."""
    assert len(set(ALL.values())) == len(ALL)


@pytest.mark.parametrize("name,text", sorted(ALL.items()))
def test_every_disclaimer_keeps_the_shared_frame(name, text):
    """The lede and coda are what make the panel read consistently across
    models; only the middle is model-specific."""
    assert text.startswith("Planning estimate only, not an operational product.")
    assert text.endswith("Do not use for real-world decisions.")


def test_default_alias_is_tier0():
    """DISCLAIMER predates the split and is still imported as the Tier-0 text."""
    assert DISCLAIMER == DISCLAIMER_TIER0


def test_only_tier0_paths_claim_wseg10_single_wind():
    """The regression that motivated the split: Tier-1 and the ensemble must
    not describe themselves as single-effective-wind WSEG-10 runs."""
    assert "single effective wind" in DISCLAIMER_TIER0
    # The envelope composites Tier-0 plumes, so naming WSEG-10 is correct there.
    assert "WSEG-10" in DISCLAIMER_ENVELOPE
    for text in (DISCLAIMER_TIER1, DISCLAIMER_ENSEMBLE):
        assert "single effective wind" not in text


def test_tier1_states_its_own_method_and_limits():
    lowered = DISCLAIMER_TIER1.lower()
    assert "multi-layer" in lowered
    # The wind profile is one sounding at ground zero (tier1.py's stated
    # assumption), and the dose calibration is anchored to G&D, not measured.
    assert "horizontally uniform" in lowered
    assert "glasstone" in lowered


def test_ensemble_scopes_its_bands_to_wind_uncertainty_only():
    """The bands are a spread over wind members only. Saying so is the
    difference between an uncertainty estimate and a claim of total
    uncertainty -- the model, yield, and fission fraction are all fixed."""
    lowered = DISCLAIMER_ENSEMBLE.lower()
    assert "wind" in lowered and "uncertainty" in lowered
    for fixed in ("yield", "fission fraction"):
        assert fixed in lowered
    assert "wider" in lowered  # true uncertainty is wider than the bands


def test_envelope_states_screening_semantics_and_its_assumptions():
    lowered = DISCLAIMER_ENVELOPE.lower()
    assert "not a combined total" in lowered
    assert "screening envelope" in lowered
    assert "surface burst" in lowered
    assert "illustrative" in lowered  # per-class attacker yields
    assert "synthetic" in lowered  # some ground zeros


def test_exposure_flags_the_protection_factor_as_the_user_s_assumption():
    lowered = DISCLAIMER_EXPOSURE.lower()
    assert "your assumption" in lowered
    assert "unshielded outdoor" in lowered
    # Doses cover external gamma from deposited fallout only.
    assert "internal" in lowered


def test_api_paths_select_the_matching_disclaimer():
    """Guards the wiring, not just the strings: read the endpoint module and
    check each compute path hands back its own constant."""
    from falloutcast.api import main as api_main

    src = (api_main.__file__ or "")
    assert src
    text = open(src).read()
    # The bare DISCLAIMER alias must no longer be wired into any response.
    assert "disclaimer=DISCLAIMER," not in text
    for name in ("DISCLAIMER_TIER0", "DISCLAIMER_TIER1", "DISCLAIMER_ENSEMBLE", "DISCLAIMER_ENVELOPE"):
        assert f"disclaimer={name}" in text
