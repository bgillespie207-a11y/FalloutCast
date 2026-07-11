"""Particle-size distribution and activity apportionment.

Fallout particle diameters are modeled as lognormal (the DELFIC assumption). We
split the distribution into log-spaced bins; each bin gets a representative
diameter and a share of the total radioactivity.

v1 activity rule (default, unchanged): the lognormal is treated as the
ACTIVITY-vs-size distribution directly (a DELFIC-style activity-size
lognormal), so a bin's share is a clean normal-CDF difference in log-space --
no numerical integration. `MU_LN_DEFAULT` is documented below as the resulting
activity-MEDIAN diameter, i.e. this branch is already implicitly a
mass/volume-weighted (refractory-like) apportionment.

v1.5 fractionation rule (opt-in via `fractionation=`, M1.5): real fallout
fractionates. As the fireball cools, REFRACTORY fission products (high
condensation temperature -- e.g. Zr, Nb, rare earths) condense early and are
incorporated through the bulk of each soil particle, so their activity is
proportional to particle VOLUME (~ d^3). VOLATILE fission products (low
condensation temperature -- e.g. Cs, I, Ru, Sr) condense later, largely onto
particle surfaces after the refractory core has solidified, so their activity
is proportional to particle SURFACE AREA (~ d^2). Net effect: small particles
carry disproportionate volatile activity, lengthening the far-downwind tail
and increasing the fraction that stays aloft. See Freiling (1961), Miller
(1960), and the DELFIC fractionation submodel (Norment, DNA-5159F) for the
physical basis.

Derivation used here: for X ~ LogNormal(mu, sigma^2), d^k * pdf(d) is itself
proportional to a LogNormal(mu + k*sigma^2, sigma^2) density (a standard
lognormal-moment identity -- e.g. Aitchison & Brown, "The Lognormal
Distribution", 1957, ch. 2; sketch: d^k * exp(-(ln d - mu)^2/2sigma^2)
completes the square in ln d to exp(-(ln d - (mu+k*sigma^2))^2/2sigma^2) times
a d-independent constant that a per-bin renormalization cancels). Since the
existing MU_LN_DEFAULT already represents the volume-weighted (refractory)
activity median, the surface-weighted (volatile) analogue is the SAME
lognormal shape with median shifted down by exp(-sigma_ln^2) -- the
power-2-minus-power-3 moment difference -- with no new size-distribution
parameter needed:

    mu_ln_volatile = mu_ln - sigma_ln**2

The only new physical input is the bulk refractory/volatile activity split,
`f_volatile` (see `F_VOLATILE_PLACEHOLDER` below) -- and that one genuinely
needs a source. Passing `fractionation=None` (the default) reproduces the pure
v1 lognormal exactly, so `tier1.py`/`ensemble.py` are unaffected unless a
caller explicitly opts in via the `bins=` override on `tier1.simulate`.

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

# --- DELFIC-style refractory/volatile fractionation (M1.5) ------------------
#
# PLACEHOLDER: bulk fraction of TOTAL H+1 fission-product activity carried by
# volatile (surface-condensing) nuclides, as opposed to refractory
# (volume-condensing) nuclides -- see the module docstring for the physical
# picture. This is genuinely time- and fissile-material-dependent (U-235 vs
# Pu-239 fission-product yields differ, and the volatile/refractory MIX
# itself shifts as different half-life chains decay), which is exactly why
# DELFIC's own fractionation submodel tracks nuclides individually rather
# than using one lumped constant. No sourced bulk number was located for this
# pass. To replace this placeholder, need one of:
#   - Freiling, E.C., "Radionuclide Fractionation in Bomb Debris," Science
#     133:1991-1998 (1961) -- refractory/volatile element classification and
#     empirical per-element fractionation ratios (R_i).
#   - Norment, H.G., DELFIC: Dep. of Fallout in Land or Coastal Interactive
#     Compute Model, DNA-5159F -- the DELFIC fractionation submodel this file
#     approximates.
#   - Miller, C.F., "A Theory of Formation of Fallout from Land-Surface
#     Nuclear Detonations," USNRDL-TR-425 (1960) -- the volume/surface
#     partition theory this simplified two-branch model is based on.
# Until sourced, 0.5 is an ILLUSTRATIVE default only (chosen for symmetry, not
# evidence). Fractionated output is directionally correct (small particles
# gain a disproportionate activity share, lengthening the downwind tail and
# aloft fraction) but NOT quantitatively validated -- do not treat it as a
# calibrated split.
F_VOLATILE_PLACEHOLDER = 0.5


@dataclass
class SizeBins:
    diameter_m: np.ndarray       # representative diameter per bin
    activity_share: np.ndarray   # fraction of total activity per bin (sums to 1)
    edges_m: np.ndarray          # bin edges (len = n_bins + 1)


@dataclass
class FractionationParams:
    """Refractory/volatile activity-partition fraction for the DELFIC-style
    fractionation branch of `lognormal_bins` (see module docstring).

    f_volatile: fraction of total activity apportioned via the volatile /
    surface-area (~d^2) branch; the remainder (1 - f_volatile) uses the
    refractory / volume (~d^3) branch. f_volatile=0.0 reproduces the pure
    lognormal `lognormal_bins` output exactly; f_volatile=1.0 is all-volatile.
    See `F_VOLATILE_PLACEHOLDER` -- this coefficient is not yet sourced.
    """

    f_volatile: float = F_VOLATILE_PLACEHOLDER


def _lognormal_bin_share(edges: np.ndarray, mu_ln: float, sigma_ln: float) -> np.ndarray:
    """Per-bin share of a LogNormal(mu_ln, sigma_ln) density: normal-CDF
    difference at the (log) bin edges, renormalized over the captured range.

    Factored out of `lognormal_bins` so the fractionation branch can reuse it
    with a shifted `mu_ln` (see module docstring for the shift derivation).
    """
    z = (np.log(edges) - mu_ln) / sigma_ln
    cdf = norm.cdf(z)
    share = np.diff(cdf)
    total = share.sum()
    if total <= 0:
        # distribution lies entirely outside [d_min, d_max]; fall back to uniform
        return np.full(len(share), 1.0 / len(share))
    return share / total  # renormalize over the captured range


def lognormal_bins(
    n_bins: int = 15,
    d_min_m: float = 5e-6,
    d_max_m: float = 2000e-6,
    mu_ln: float = MU_LN_DEFAULT,
    sigma_ln: float = SIGMA_LN_DEFAULT,
    fractionation: FractionationParams | None = None,
) -> SizeBins:
    """Discretize the DELFIC-style activity-size lognormal into bins.

    With `fractionation=None` (default), activity share is the pure v1 rule:
    the lognormal(mu_ln, sigma_ln) treated as the activity distribution
    directly -- unchanged from the original implementation, bit-for-bit.

    With `fractionation=FractionationParams(...)`, activity share blends a
    refractory branch (this same lognormal, i.e. volume/mass-weighted) with a
    volatile branch (the same shape, median shifted down by exp(-sigma_ln^2)
    to represent surface-area weighting), per `fractionation.f_volatile`. See
    the module docstring for the physical picture and derivation.
    """
    edges = np.geomspace(d_min_m, d_max_m, n_bins + 1)
    # representative diameter = geometric mean of each bin's edges
    d_rep = np.sqrt(edges[:-1] * edges[1:])

    refractory_share = _lognormal_bin_share(edges, mu_ln, sigma_ln)

    if fractionation is None:
        share = refractory_share
    else:
        volatile_mu_ln = mu_ln - sigma_ln ** 2
        volatile_share = _lognormal_bin_share(edges, volatile_mu_ln, sigma_ln)
        f_v = fractionation.f_volatile
        share = (1.0 - f_v) * refractory_share + f_v * volatile_share
        share = share / share.sum()

    return SizeBins(diameter_m=d_rep, activity_share=share, edges_m=edges)
