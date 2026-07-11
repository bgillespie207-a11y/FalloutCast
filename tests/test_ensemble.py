"""Ensemble wrapper tests: probability validity, sharpness under zero jitter,
and band-widening under more uncertainty."""

import numpy as np
import pytest

from falloutcast.physics import ensemble

H = np.array([100, 1500, 3000, 5500, 9000, 12000.0])
BASE_U = np.array([10, 12, 15, 20, 25, 30.0])
BASE_V = np.array([12, 9, 6, 3, 0, -3.0])

FAST = dict(n_bins=6, n_layers=6, dt_s=300.0, resolution_miles=5.0)


def _run(jitter_deg, speed_frac, n=6, seed=1):
    members = ensemble.perturb_profile(
        BASE_U, BASE_V, n_members=n, dir_jitter_deg=jitter_deg,
        speed_jitter_frac=speed_frac, shear_jitter_frac=0.0, seed=seed,
    )
    return ensemble.run_ensemble(
        yield_mt=1.0, fission_fraction=1.0, heights_m=H, members=members, **FAST
    )


def test_probabilities_bounded():
    res = _run(12.0, 0.15)
    for p in res.prob_by_level.values():
        assert p.min() >= 0.0 and p.max() <= 1.0


def test_member_count_respected():
    res = _run(10.0, 0.1, n=5)
    assert res.n_members == 5


def test_zero_jitter_is_sharp():
    res = _run(0.0, 0.0, n=5)
    p = res.prob_by_level[1.0]
    intermediate = ((p > 0.05) & (p < 0.95)).mean()
    assert intermediate < 0.01   # essentially binary: identical members


def test_more_jitter_widens_band():
    narrow = _run(4.0, 0.05, seed=3)
    wide = _run(20.0, 0.25, seed=3)

    def band_area(res):
        p = res.prob_by_level[1.0]
        return ((p > 0.05) & (p < 0.95)).sum()

    assert band_area(wide) > band_area(narrow)


def test_exceedance_monotonic_in_level():
    """A cell exceeding a high dose implies it exceeds a low one, so the total
    probable area shrinks (or holds) as the dose level rises."""
    res = _run(12.0, 0.15)
    areas = {lvl: (p > 0.5).sum() for lvl, p in res.prob_by_level.items()}
    ordered = [areas[l] for l in sorted(areas)]
    assert all(ordered[i] >= ordered[i + 1] for i in range(len(ordered) - 1))
