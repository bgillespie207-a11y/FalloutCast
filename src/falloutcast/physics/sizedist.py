"""Particle-size distribution and activity apportionment.

Fallout particle diameters are modeled as lognormal (the DELFIC assumption). We
split the distribution into log-spaced bins; each bin gets a representative
diameter and a share of the total radioactivity.

v1 activity rule: the lognormal is treated as the ACTIVITY-vs-size distribution
directly (a DELFIC-style activity-size lognormal), so a bin's share is a clean
normal-CDF difference in log-space -- no numerical integration.

This is deliberately simple and swappable. The physically-richer path is to
model the NUMBER/mass distribution and apply a fractionation rule (volatiles
condensing onto smaller, higher-drifting particles, which lengthens the far
tail). That rule drops into `lognormal_bins`/`activity_shares` later without
touching the engine.

Diameters in meters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

# Activity-size lognormal, grounded in the DELFIC surface-burst distribution for
# US continental soil. Log-slope sigma_ln ~ ln 2 (~0.69) is the value from the
# Nathans/Turco/DELFIC lineage (DTIC ADA179114; Turco et al. hybrid). DELFIC's
# canonical US-soil number range is ~3-450 um; heavy local fallout extends
# higher, so we span 5-2000 um. The activity-MEDIAN diameter still depends on
# fractionation (surface- vs volume-distributed activity) and the primary DELFIC
# report (DNA-5159F) for its exact value; ~200 um is a defensible activity-
# weighted local value pending that. Structural tests don't depend on these;
# footprint validation (TIER1_SPEC test 7) will.
MU_LN_DEFAULT = np.log(200e-6)   # ln of activity-median diameter (m)
SIGMA_LN_DEFAULT = 0.7           # ~ ln 2, DELFIC/Nathans log-slope


@dataclass
class SizeBins:
    diameter_m: np.ndarray       # representative diameter per bin
    activity_share: np.ndarray   # fraction of total activity per bin (sums to 1)
    edges_m: np.ndarray          # bin edges (len = n_bins + 1)


def lognormal_bins(
    n_bins: int = 15,
    d_min_m: float = 5e-6,
    d_max_m: float = 2000e-6,
    mu_ln: float = MU_LN_DEFAULT,
    sigma_ln: float = SIGMA_LN_DEFAULT,
) -> SizeBins:
    edges = np.geomspace(d_min_m, d_max_m, n_bins + 1)
    # representative diameter = geometric mean of each bin's edges
    d_rep = np.sqrt(edges[:-1] * edges[1:])

    # activity share = mass of the activity-size lognormal captured by each bin
    z = (np.log(edges) - mu_ln) / sigma_ln
    cdf = norm.cdf(z)
    share = np.diff(cdf)

    total = share.sum()
    if total <= 0:
        # distribution lies entirely outside [d_min, d_max]; fall back to uniform
        share = np.full(n_bins, 1.0 / n_bins)
    else:
        share = share / total  # renormalize over the captured range

    return SizeBins(diameter_m=d_rep, activity_share=share, edges_m=edges)
