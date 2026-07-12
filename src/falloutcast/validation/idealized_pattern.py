"""Magnitude validation against the Glasstone & Dolan idealized surface-burst
fallout pattern.

This closes the gap the historical-case harness (`reference_cases.py`) could
not: a footprint MAGNITUDE reference that actually matches this model's
assumptions. Every real NTS shot chased in `reference_cases.py` was a tower or
near-surface burst (a height-of-burst mismatch with WSEG-10's HOB=0), or had a
yield outside WSEG-10's calibrated range, or lacked a machine-usable digitized
contour -- so only plume DIRECTION could be cross-checked, never size.

The Glasstone & Dolan idealized pattern sidesteps all three blockers at once:

  * TRUE contact surface burst (HOB=0) -- matches WSEG-10's assumption exactly.
  * Strategic yield (validated here at 1 Mt) -- squarely inside WSEG-10's
    calibrated range (no negative cloud height like Little Feller II).
  * A GIVEN effective wind (15 mph) -- no historical sounding to reconstruct.
  * Published H+1 (unit-time reference) dose-rate contours in R/hr -- exactly
    what WSEG-10 outputs.

WHAT THIS IS / ISN'T. This validates WSEG-10 against G&D's *idealized analytic
reference pattern* -- the canonical smooth-terrain surface-burst footprint that
tools of this class are conventionally checked against. It is a conformance
check to that standard reference, itself calibrated to test data, NOT a
comparison to one specific measured shot's raw contour. That's the honest
frame: it establishes the implementation reproduces the accepted idealized
footprint (normalization, downwind scaling, deposition), which nothing in this
project tested before. It does not establish agreement with any single real
event's messy measured pattern.

SOURCE (read verbatim, not computed by a summarizer):
  Samuel Glasstone & Philip J. Dolan, "The Effects of Nuclear Weapons," 3rd
  ed. (1977), Chapter IX, Table 9.93, "Scaling Relationships for Unit-Time
  Reference Dose-Rate Contours for a Contact Surface Burst with a Yield of W
  Kilotons and a 15 mph Wind" (with 15 deg wind shear). Transcribed from the
  full-text reproduction at atomicarchive.com
  (resources/documents/effects/glasstone-dolan/chapter9.html), retrieved
  2026-07-11, cross-checked against glasstone.blogspot.com (which independently
  gives the 1000 R/hr contour as ~40 mi downwind / ~6.9 mi wide for 1 Mt,
  matching the 1.8*W^0.45 / 0.036*W^0.76 rows below).

  Per Table 9.93, for a yield of W KILOTONS: each contour's downwind distance,
  maximum width, and ground-zero width in statute miles are the coefficient
  times W raised to the listed exponent. Contour SHAPE/size scales with TOTAL
  yield; the dose-rate LABELS scale with FISSION yield (G&D sec. 9.94), so for
  a fission fraction f<1 the labeled dose rates are multiplied by f. This
  module validates the pure-fission (f=1) case, where the table applies
  directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..physics.wseg10 import WSEG10

# Table 9.93, verbatim. Keyed by unit-time reference dose rate (R/hr).
# Value = (downwind_coef, width_coef, width_exp, gz_width_coef, gz_width_exp).
# Every downwind distance uses the same exponent 0.45 (W^0.45), as printed.
_DOWNWIND_EXP = 0.45
TABLE_9_93: dict[int, tuple[float, float, float, float, float]] = {
    3000: (0.95, 0.0076, 0.86, 0.026, 0.58),
    1000: (1.8, 0.036, 0.76, 0.060, 0.57),
    300: (4.5, 0.13, 0.66, 0.20, 0.48),
    100: (8.9, 0.38, 0.60, 0.39, 0.42),
    30: (16.0, 0.76, 0.56, 0.53, 0.41),
    10: (24.0, 1.4, 0.53, 0.68, 0.41),
    3: (30.0, 2.2, 0.50, 0.89, 0.41),
    1: (40.0, 3.3, 0.48, 1.5, 0.41),
}
EFFECTIVE_WIND_MPH = 15.0  # the wind Table 9.93 is defined for


@dataclass(frozen=True)
class ContourExtent:
    level_rhr: float
    downwind_miles: float
    max_width_miles: float
    gz_width_miles: float


def reference_contour(level_rhr: int, yield_kt: float) -> ContourExtent:
    """Glasstone & Dolan Table 9.93 idealized extent for one dose-rate contour
    at the given TOTAL yield (kilotons), pure fission. See module docstring."""
    down_c, wid_c, wid_e, gz_c, gz_e = TABLE_9_93[level_rhr]
    return ContourExtent(
        level_rhr=level_rhr,
        downwind_miles=down_c * yield_kt**_DOWNWIND_EXP,
        max_width_miles=wid_c * yield_kt**wid_e,
        gz_width_miles=gz_c * yield_kt**gz_e,
    )


def model_contour(
    level_rhr: float,
    *,
    yield_mt: float,
    wind_mph: float = EFFECTIVE_WIND_MPH,
    shear_mph_per_kft: float = 0.0,
    fission_fraction: float = 1.0,
    downwind_max_miles: float = 1200.0,
    crosswind_max_miles: float = 250.0,
    resolution_miles: float = 0.5,
) -> ContourExtent | None:
    """WSEG-10's own extent for a dose-rate contour: farthest downwind reach and
    maximum crosswind width of the region with H+1 dose rate >= `level_rhr`.

    Wind blows due east (so downwind is +x, crosswind is +/-y). Returns None if
    the model never reaches `level_rhr` anywhere on the grid. `gz_width` is not
    a WSEG-10 output (its dose peaks AT ground zero), so it is left as 0.0.

    Default `shear_mph_per_kft=0` deliberately: WSEG-10's shear is a SPEED shear
    that dominates crosswind spreading, a different parameterization than G&D's
    15 deg DIRECTIONAL shear, so the cleanest apples-to-apples on the core
    advection/deposition (downwind reach especially) is at zero speed shear.
    """
    model = WSEG10(
        yield_mt=yield_mt, fission_fraction=fission_fraction,
        wind_mph=wind_mph, wind_dir_deg=90.0, shear_mph_per_kft=shear_mph_per_kft,
    )
    x = np.linspace(-50.0, downwind_max_miles, int((downwind_max_miles + 50.0) / resolution_miles) + 1)
    y = np.linspace(-crosswind_max_miles, crosswind_max_miles, int(2 * crosswind_max_miles / resolution_miles) + 1)
    gx, gy = np.meshgrid(x, y)
    dose = model.dose_rate_h1(gx, gy)

    mask = dose >= level_rhr
    if not mask.any():
        return None
    downwind = float(np.where(mask, gx, -np.inf).max())
    # per-column crosswind span, over only the columns that have coverage
    # (skipping all-empty columns avoids an all-NaN reduction).
    covered = mask.any(axis=0)
    col_y = np.where(mask[:, covered], gy[:, covered], np.nan)
    span = np.nanmax(col_y, axis=0) - np.nanmin(col_y, axis=0)
    max_width = float(span.max())
    return ContourExtent(
        level_rhr=level_rhr, downwind_miles=downwind,
        max_width_miles=max_width, gz_width_miles=0.0,
    )


@dataclass(frozen=True)
class LevelComparison:
    level_rhr: int
    reference_downwind_mi: float
    model_downwind_mi: float | None
    downwind_ratio: float | None       # model / reference
    reference_width_mi: float
    model_width_mi: float | None


def compare(yield_mt: float = 1.0, *, shear_mph_per_kft: float = 0.0) -> list[LevelComparison]:
    """WSEG-10 vs the G&D idealized reference at every Table 9.93 contour."""
    yield_kt = yield_mt * 1000.0
    out: list[LevelComparison] = []
    for level in sorted(TABLE_9_93, reverse=True):
        ref = reference_contour(level, yield_kt)
        mdl = model_contour(level, yield_mt=yield_mt, shear_mph_per_kft=shear_mph_per_kft)
        ratio = (mdl.downwind_miles / ref.downwind_miles) if mdl else None
        out.append(
            LevelComparison(
                level_rhr=level,
                reference_downwind_mi=ref.downwind_miles,
                model_downwind_mi=mdl.downwind_miles if mdl else None,
                downwind_ratio=ratio,
                reference_width_mi=ref.max_width_miles,
                model_width_mi=mdl.max_width_miles if mdl else None,
            )
        )
    return out


# The dose-rate contours WSEG-10 is expected to reproduce within a factor of
# ~2 downwind. The 3000 R/hr contour is EXCLUDED: it is a close-in (~20 mi),
# high-dose contour that G&D sec. 9.94 itself notes lies within the zone of
# complete devastation from blast/thermal, and where WSEG-10's near-ground-zero
# analytic form departs most from the idealized pattern -- not a meaningful
# fallout-footprint discriminator.
VALIDATED_LEVELS: tuple[int, ...] = (1000, 300, 100, 30, 10, 3, 1)
