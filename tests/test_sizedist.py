"""Size-distribution / fractionation tests.

These are structural (property) tests, not golden-number tests: no published
reference footprint or activity split is available yet (see
`sizedist.F_VOLATILE_PLACEHOLDER`), so we assert the *qualitative* physics the
task requires -- fractionation shifts activity toward smaller particles, and
that in turn lengthens downwind reach / raises the aloft fraction -- rather
than any specific numeric value.
"""

import numpy as np
import pytest

from falloutcast.physics import sizedist, tier1

H = np.array([100.0, 1500.0, 3000.0, 5500.0, 9000.0, 12000.0])


def _weighted_mean_diameter(bins: sizedist.SizeBins) -> float:
    return float(np.sum(bins.diameter_m * bins.activity_share))


def _small_half_share(bins: sizedist.SizeBins) -> float:
    """Sum of activity_share over the bins below the median diameter."""
    order = np.argsort(bins.diameter_m)
    half = len(order) // 2
    return float(bins.activity_share[order[:half]].sum())


# --- basic invariants -----------------------------------------------------

def test_pure_lognormal_shares_sum_to_one():
    bins = sizedist.lognormal_bins()
    assert bins.activity_share.sum() == pytest.approx(1.0)


def test_fractionated_shares_sum_to_one():
    bins = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(f_volatile=0.7)
    )
    assert bins.activity_share.sum() == pytest.approx(1.0)


def test_zero_volatile_fraction_reproduces_pure_lognormal():
    """f_volatile=0.0 (all-refractory) must exactly reproduce the default
    pure-lognormal branch -- the interface's backward-compatible limit."""
    pure = sizedist.lognormal_bins()
    refractory_only = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(f_volatile=0.0)
    )
    np.testing.assert_allclose(
        pure.activity_share, refractory_only.activity_share, rtol=1e-12
    )
    np.testing.assert_allclose(pure.diameter_m, refractory_only.diameter_m)


# --- headline structural claim: fractionation shifts activity to small end ---

def test_fractionation_increases_small_bin_share():
    """With fractionation ON, the small-diameter half of the bins carries a
    larger activity share than under the pure-lognormal (refractory-only)
    baseline."""
    pure = sizedist.lognormal_bins()
    fractionated = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(f_volatile=0.5)
    )
    assert _small_half_share(fractionated) > _small_half_share(pure)


def test_activity_weighted_mean_diameter_decreases_monotonically_with_f_volatile():
    diam_means = [
        _weighted_mean_diameter(
            sizedist.lognormal_bins(
                fractionation=sizedist.FractionationParams(f_volatile=f_v)
            )
        )
        for f_v in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    assert all(
        diam_means[i] > diam_means[i + 1] for i in range(len(diam_means) - 1)
    )


def test_fully_volatile_shifts_smaller_than_fully_refractory():
    refractory = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(f_volatile=0.0)
    )
    volatile = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(f_volatile=1.0)
    )
    assert _weighted_mean_diameter(volatile) < _weighted_mean_diameter(refractory)


# --- consequences at the engine level: reach / aloft fraction ---------------

def _activity_weighted_mean_x(result: tier1.Tier1Result) -> float:
    """Activity(dose)-weighted mean downwind distance of the deposited grid.

    Landing POSITIONS depend only on particle diameter and wind (unaffected
    by activity weighting -- the same 15 diameter bins land in the same
    places whether fractionation is on or off), so the grid's raw x-extent
    doesn't move. What fractionation changes is how much activity each
    landing position carries: reweighting toward small, slow-falling
    particles shifts more of the deposited mass to the far (downwind) end of
    that fixed set of landing positions. This weighted mean captures that
    shift where raw grid extent cannot.
    """
    col_mass = result.dose_rate_h1.sum(axis=0)  # total dose-mass per x-column
    return float(np.sum(col_mass * result.x_miles) / col_mass.sum())


def test_fractionation_increases_aloft_fraction_and_downwind_reach():
    """Feeding fractionated bins into Tier-1 (via the existing `bins=`
    override -- tier1.py itself is untouched) should raise the still-aloft
    fraction and shift the deposited footprint's activity-weighted mean
    distance farther downwind, because fractionation shifts activity onto
    slower-falling, farther-drifting small particles."""
    wind_u, wind_v = np.full(6, 15.0), np.zeros(6)
    common = dict(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H,
        wind_u_ms=wind_u, wind_v_ms=wind_v, n_bins=15, n_layers=8,
    )

    pure = tier1.simulate(**common, bins=sizedist.lognormal_bins(n_bins=15))
    fractionated = tier1.simulate(
        **common,
        bins=sizedist.lognormal_bins(
            n_bins=15, fractionation=sizedist.FractionationParams(f_volatile=0.5)
        ),
    )

    assert fractionated.fraction_aloft > pure.fraction_aloft
    assert _activity_weighted_mean_x(fractionated) > _activity_weighted_mean_x(pure)


# --- per-nuclide alternative (f_volatile_from_yields) -----------------------

def test_f_volatile_from_yields_in_unit_interval():
    assert 0.0 < sizedist.f_volatile_from_yields() < 1.0


def test_f_volatile_from_yields_matches_hand_computation():
    """Regression check against the specific cited yield values -- catches a
    silent edit to FISSION_PRODUCT_CHAINS (added/removed/reclassified chain,
    typo'd yield) without hardcoding a numeric literal the docstring can't
    explain; the arithmetic here is the same sum-and-divide the module
    docstring describes."""
    volatile_yield = 5.73 + 6.221       # Sr-90/Y-90 + Cs-137/Ba-137m
    refractory_yield = 6.502 + 6.132    # Zr-95/Nb-95 + Mo-99/Tc-99m
    expected = volatile_yield / (volatile_yield + refractory_yield)
    assert sizedist.f_volatile_from_yields() == pytest.approx(expected)


def test_fission_product_chains_are_documented_and_unique():
    """Every chain must cite both its yield source and its classification
    source (rule 1/2: no unsourced numbers presented as fact), and mass
    numbers must be unique -- this table intentionally excludes several
    candidate chains (89, 91, 97, 131, 140, 141, 143, 144) for insufficient
    sourcing rather than guessing; a duplicate or unlabeled entry would mean
    that discipline slipped."""
    chains = sizedist.FISSION_PRODUCT_CHAINS
    assert len(chains) >= 2  # need at least one of each class to be useful
    mass_numbers = [c.mass_number for c in chains]
    assert len(mass_numbers) == len(set(mass_numbers))
    for c in chains:
        assert len(c.yield_citation) > 20, f"mass {c.mass_number} yield_citation looks unpopulated"
        assert len(c.classification_citation) > 20, f"mass {c.mass_number} classification_citation looks unpopulated"
        assert c.cumulative_yield_percent > 0


def test_fission_product_chains_include_both_classes():
    """The set must have at least one refractory and one volatile chain, or
    f_volatile_from_yields() would silently degenerate to 0.0 or 1.0."""
    chains = sizedist.FISSION_PRODUCT_CHAINS
    assert any(c.is_volatile for c in chains)
    assert any(not c.is_volatile for c in chains)


def test_f_volatile_from_yields_usable_as_fractionation_param():
    """Integration: the sourced alternative plugs into the same
    FractionationParams interface as the placeholder, unchanged."""
    bins = sizedist.lognormal_bins(
        fractionation=sizedist.FractionationParams(
            f_volatile=sizedist.f_volatile_from_yields()
        )
    )
    assert bins.activity_share.sum() == pytest.approx(1.0)
