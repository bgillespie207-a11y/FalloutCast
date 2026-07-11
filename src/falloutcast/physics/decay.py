"""Fallout decay and accumulated-dose math.

WSEG-10 gives an H+1 *reference* dose rate. Real exposure depends on when
fallout arrives and how long someone stays. Fission-product decay follows the
Way-Wigner approximation, dose rate proportional to t**-1.2 (t in hours after
burst), which is accurate from roughly 30 minutes to ~200 hours.

All functions take/return dose rate in R/hr and dose in R (roentgen). Times are
hours after burst.
"""

from __future__ import annotations

import numpy as np

DECAY_EXPONENT = 1.2


def dose_rate_at(dose_rate_h1, t_hours):
    """Dose rate at time t given the H+1 reference dose rate.

    R(t) = R_1 * t**-1.2
    """
    t = np.asarray(t_hours, dtype=float)
    return np.asarray(dose_rate_h1, dtype=float) * t ** (-DECAY_EXPONENT)


def accumulated_dose(dose_rate_h1, t_start_hours, t_end_hours):
    """Integrated dose (R) accumulated by someone present from t_start to t_end.

    integral of R_1 * t**-1.2 dt = R_1 * (t_start**-0.2 - t_end**-0.2) / 0.2
    """
    r1 = np.asarray(dose_rate_h1, dtype=float)
    t0 = np.asarray(t_start_hours, dtype=float)
    t1 = np.asarray(t_end_hours, dtype=float)
    p = DECAY_EXPONENT - 1.0  # 0.2
    return r1 * (t0 ** (-p) - t1 ** (-p)) / p


def accumulated_dose_to_infinity(dose_rate_h1, t_start_hours):
    """Total lifetime dose (R) if present from arrival onward with no decay of
    presence. Closed form of the integral to infinity: R_1 * t_start**-0.2 / 0.2
    """
    r1 = np.asarray(dose_rate_h1, dtype=float)
    t0 = np.asarray(t_start_hours, dtype=float)
    p = DECAY_EXPONENT - 1.0
    return r1 * t0 ** (-p) / p
