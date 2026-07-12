"""Magnitude validation against a REAL MEASURED shot: Castle Bravo (1954).

This is the project's first comparison to an actual event's measured fallout
footprint. `idealized_pattern.py` validated WSEG-10 against Glasstone & Dolan's
*idealized* surface-burst reference (clean, but a model-vs-model conformance
check). Bravo is the complement: the most-documented real surface-burst fallout
pattern in existence, so the comparison is against measured ground truth -- with
all the messiness that entails.

HONEST CAVEATS (this is a coarse, order-of-magnitude / factor-~2 sanity check,
NOT a precision validation -- and it must not be read as one):
  * SURFACE MATERIAL MISMATCH. Bravo was a coral-reef/water surface burst;
    WSEG-10 (and G&D Table 9.93) are calibrated to CONTINENTAL-US soil (cf.
    G&D sec. 9.63). Coral fallout has different particle size/activity, a real
    physical mismatch this model can't capture.
  * THE MEASURED PATTERN IS ITSELF UNCERTAIN. G&D sec. 9.105 states the Fig.
    9.105 contours are "largely a matter of guesswork" because of the absence
    of observations over large ocean areas; the 100-mi/3300-rad Rongelap point
    "may possibly have represented a hot spot." So the reference has large
    error bars of its own.
  * REFERENCE IS ACCUMULATED 96-h DOSE, not H+1 dose rate. WSEG-10's H+1 field
    is converted to 96-h accumulated dose here via the project's own Way-Wigner
    `decay.accumulated_dose` using WSEG-10's per-point `time_of_arrival`. That
    conversion is standard but adds its own assumption. (roentgen ~= rad for
    gamma at this precision; treated as equal.)
  * SINGLE EFFECTIVE WIND for a strongly wind-sheared real event, and the wind
    SPEED itself is DERIVED, not directly tabulated: fallout reached Rongelap
    (~100-115 mi) about 4-6 h after burst (G&D sec. 9.108), i.e. a leading-edge
    transport of ~17-29 mph; `EFFECTIVE_WIND_MPH = 20` is taken from that
    sourced arrival, and flagged as derived. shear is set to 0 for the same
    apples-to-apples reason as idealized_pattern (WSEG-10 speed shear != real
    directional shear).

What the comparison establishes despite all that: WSEG-10 at Bravo's sourced
yield/fission/burst produces a lethal footprint of the right SCALE -- a 700-rad
belt within a factor of ~2 of the measured ~170 x 35 mi. That's a real (if
loose) tie to ground truth, which nothing in this project had before.

SOURCES (all read/quoted, not guessed):
  * Yield, burst height, footprint dimensions, the 700-rad lethal belt, the
    Rongelap dose points, and fallout arrival time: Glasstone & Dolan, "The
    Effects of Nuclear Weapons" (1977), sec. 9.104-9.109 (atomicarchive.com
    full text, retrieved 2026-07-11). Quoted figures: 15 Mt total; ~7 ft above
    a coral reef; contaminated area >330 mi downwind, up to >60 mi wide, ~20 mi
    upwind, >7,000 sq mi; a 700-rad/96-h belt "about 170 miles long and up to
    35 miles wide"; Rongelap NW tip 100 mi -> 3,300 rad, ~25 mi south / 115 mi
    -> 220 rad; fallout began ~4-6 h after burst.
  * Fission yield ~10 of 15 Mt (fission fraction ~2/3): nuclearweaponarchive.org
    (Sublette, "Operation Castle") and multiple compilations, retrieved
    2026-07-11.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..physics import decay
from ..physics.wseg10 import WSEG10

# --- Sourced measured facts (see module docstring for citations) -------------
MEASURED_YIELD_MT = 15.0
FISSION_YIELD_MT = 10.0
FISSION_FRACTION = FISSION_YIELD_MT / MEASURED_YIELD_MT  # ~0.667
HOB_FT = 7.0  # above coral reef -- negligible vs the ~2-mi fireball, ~= surface

# Measured footprint (G&D 9.104, 9.107, 9.109). Accumulated dose at 96 h.
OVERALL_DOWNWIND_MI = 330.0
OVERALL_MAX_WIDTH_MI = 60.0
UPWIND_MI = 20.0
CONTAMINATED_AREA_SQMI = 7000.0
LETHAL_700RAD_LENGTH_MI = 170.0
LETHAL_700RAD_WIDTH_MI = 35.0
RONGELAP_NW_MI, RONGELAP_NW_RAD = 100.0, 3300.0   # possible hot spot per G&D
RONGELAP_S_MI, RONGELAP_S_RAD = 115.0, 220.0      # the cleaner comparison point
FALLOUT_ARRIVAL_HR = (4.0, 6.0)
ACCUMULATION_END_HR = 96.0

# Effective wind DERIVED from the sourced arrival (see docstring), not tabulated.
EFFECTIVE_WIND_MPH = 20.0
LETHAL_DOSE_RAD = 700.0


@dataclass(frozen=True)
class BravoModelResult:
    belt_length_mi: float       # along-wind extent of the 700-rad/96h contour
    belt_width_mi: float        # max crosswind width of that contour
    overall_extent_mi: float    # downwind reach of a low (100-rad/96h) contour
    dose_at_rongelap_s_rad: float  # 96-h accumulated dose on centerline at 115 mi


def _accumulated_dose_field(
    wind_mph: float, shear_mph_per_kft: float, x_mi: np.ndarray, y_mi: np.ndarray
):
    """96-h accumulated dose field (rad ~ R) for Bravo, wind blowing due east
    (+x downwind). Converts WSEG-10's H+1 rate via Way-Wigner decay integrated
    from each point's fallout arrival time to 96 h."""
    model = WSEG10(
        yield_mt=MEASURED_YIELD_MT, fission_fraction=FISSION_FRACTION,
        wind_mph=wind_mph, wind_dir_deg=90.0, shear_mph_per_kft=shear_mph_per_kft,
    )
    gx, gy = np.meshgrid(x_mi, y_mi)
    r1 = model.dose_rate_h1(gx, gy)
    toa = model.time_of_arrival(gx, gy)
    acc = decay.accumulated_dose(r1, toa, ACCUMULATION_END_HR)
    return gx, gy, acc


def run_model(
    *, wind_mph: float = EFFECTIVE_WIND_MPH, shear_mph_per_kft: float = 0.0
) -> BravoModelResult:
    """WSEG-10's Bravo footprint, reduced to the few numbers G&D actually
    measured: the 700-rad/96-h lethal belt (length x width), the overall
    contaminated extent, and the centerline dose at Rongelap-south (115 mi)."""
    x = np.linspace(-60.0, 600.0, 1321)   # 0.5 mi steps downwind
    y = np.linspace(-120.0, 120.0, 961)   # 0.25 mi steps crosswind
    gx, gy, acc = _accumulated_dose_field(wind_mph, shear_mph_per_kft, x, y)

    lethal = acc >= LETHAL_DOSE_RAD
    if lethal.any():
        belt_length = float(gx[lethal].max() - gx[lethal].min())
        covered = lethal.any(axis=0)
        col_y = np.where(lethal[:, covered], gy[:, covered], np.nan)
        belt_width = float(np.nanmax(np.nanmax(col_y, axis=0) - np.nanmin(col_y, axis=0)))
    else:
        belt_length = belt_width = 0.0

    low = acc >= 100.0
    overall_extent = float(gx[low].max()) if low.any() else 0.0

    i = int(np.argmin(np.abs(x - RONGELAP_S_MI)))
    j = int(np.argmin(np.abs(y - 0.0)))
    dose_115 = float(acc[j, i])

    return BravoModelResult(
        belt_length_mi=belt_length, belt_width_mi=belt_width,
        overall_extent_mi=overall_extent, dose_at_rongelap_s_rad=dose_115,
    )
