"""WSEG-10 analytic fallout model  (Tier-0 engine).

This is the simplified "smearing" model that has anchored operational fallout
studies for decades and is the basis for tools like NUKEMAP. It computes an
H+1-hour reference dose-rate field on the ground for a single surface burst,
given yield, fission fraction, and an *effective* wind (speed + direction +
shear through the stabilized cloud).

Reference
---------
Dan W. Hanifen, "Documentation and Analysis of the WSEG-10 Fallout Prediction
Model," M.S. thesis, Air Force Institute of Technology, March 1980 (DTIC
ADA083515). This is an unclassified, publicly available government document.

Two corrections from the reference FORTRAN are applied here and flagged inline:
  1. The exponent term `n` uses a scale factor F = 1.0, NOT the fission
     fraction. (Confirmed against Hanifen pp. 10-11.)
  2. Time-of-arrival uses the FORTRAN formulation (Hanifen p. 70), which is
     numerically stable, rather than the printed eq. 26, which can go negative.

Native units (do not "fix" these — convert at the boundary via units.py):
  distance = statute miles, speed = mph, altitude = kilofeet,
  dose rate = roentgen/hour (R/hr).

KNOWN LIMITATIONS (surface these in any UI built on top):
  * Single effective wind: no true multi-layer transport. This is exactly the
    weakness Tier-1 (multi-layer particle advection) is meant to fix.
  * No fractionation, no particle-size activity distribution, no hot spots.
  * sigma_y crosswind growth is shear-dominated, not diffusive.
  * Idealized terrain (flat). Complex terrain channels fallout in ways this
    cannot represent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.special import gamma
from scipy.stats import norm

_SQRT_2PI = 2.5066282746310002

# F is a scale factor on the d(t) activity-decay function inside the derivation
# of `n`. Hanifen's model uses F = 1.0. It is NOT the fission fraction (a
# widely-copied bug conflates the two). See correction (1) above.
_F_SCALE = 1.0

_KFT_TO_M = 304.8


def cloud_center_height_kft(yield_mt: float) -> float:
    """WSEG-10 stabilized-cloud center height (kilofeet), function of yield only."""
    lny = np.log(yield_mt)
    d = lny + 2.42
    return 44.0 + 6.1 * lny - 0.205 * abs(d) * d


def cloud_top_height_m(yield_mt: float) -> float:
    """Approximate cloud top (meters): center height + ~2 sigma_h, for choosing
    the atmospheric layer through which fallout descends."""
    h_c_kft = cloud_center_height_kft(yield_mt)
    top_kft = h_c_kft + 2.0 * (0.18 * h_c_kft)
    return top_kft * _KFT_TO_M


@dataclass
class WSEG10:
    """A single stabilized-cloud fallout solution.

    Parameters
    ----------
    yield_mt : total weapon yield, megatons.
    fission_fraction : 0 < ff <= 1. Scales total deposited activity linearly.
    wind_mph : effective wind speed through the cloud (mph).
    wind_dir_deg : direction the wind blows *toward*? No — meteorological
        convention here is the bearing the fallout is carried along, measured
        clockwise from North (0=N, 90=E). Callers should pass the downwind
        bearing. (See note in _to_hotline.)
    shear_mph_per_kft : effective wind-directional shear, mph per kilofoot.
    """

    yield_mt: float
    fission_fraction: float
    wind_mph: float
    wind_dir_deg: float
    shear_mph_per_kft: float

    # derived cloud/geometry constants (filled in __post_init__)
    H_c: float = field(init=False)      # cloud center height (kilofeet)
    s_0: float = field(init=False)      # sigma_0
    s_h: float = field(init=False)      # sigma_h
    T_c: float = field(init=False)      # cloud time constant
    L_0: float = field(init=False)
    s_x: float = field(init=False)      # sigma_x (downwind)
    L: float = field(init=False)
    n: float = field(init=False)        # peakedness exponent
    a_1: float = field(init=False)      # alpha_1

    def __post_init__(self) -> None:
        y = float(self.yield_mt)
        if y <= 0:
            raise ValueError("yield_mt must be > 0")
        if not (0.0 < self.fission_fraction <= 1.0):
            raise ValueError("fission_fraction must be in (0, 1]")

        lny = np.log(y)
        d = lny + 2.42  # intermediate; appears twice, otherwise meaningless

        self.H_c = 44.0 + 6.1 * lny - 0.205 * abs(d) * d
        self.s_0 = np.exp(0.7 + lny / 3.0 - 3.25 / (4.0 + (lny + 5.4) ** 2))
        self.s_h = 0.18 * self.H_c
        self.T_c = (
            1.0573203
            * (12.0 * (self.H_c / 60.0) - 2.5 * (self.H_c / 60.0) ** 2)
            * (1.0 - 0.5 * np.exp(-((self.H_c / 25.0) ** 2)))
        )

        s_02 = self.s_0 ** 2
        self.L_0 = self.wind_mph * self.T_c
        L_02 = self.L_0 ** 2

        s_x2 = s_02 * (L_02 + 8.0 * s_02) / (L_02 + 2.0 * s_02)
        self.s_x = np.sqrt(s_x2)

        L_2 = L_02 + 2.0 * s_x2
        self.L = np.sqrt(L_2)

        # correction (1): F scale factor, not fission fraction
        self.n = (_F_SCALE * L_02 + s_x2) / (L_02 + 0.5 * s_x2)

        self.a_1 = 1.0 / (1.0 + (0.001 * self.H_c * self.wind_mph) / self.s_0)

        # cache squares used repeatedly
        self._s_02 = s_02
        self._s_x2 = s_x2
        self._L_02 = L_02
        self._L_2 = L_2

    # --- downwind (hotline) shape functions -------------------------------

    def _g(self, x: np.ndarray) -> np.ndarray:
        """Downwind activity distribution g(x) along the hotline."""
        return np.exp(-((np.abs(x) / self.L) ** self.n)) / (
            self.L * gamma(1.0 + 1.0 / self.n)
        )

    def _phi(self, x: np.ndarray) -> np.ndarray:
        """Upwind cutoff (fallout does not extend far upwind)."""
        w = (self.L_0 / self.L) * (x / (self.s_x * self.a_1))
        return norm.cdf(w)

    def _to_hotline(self, x: np.ndarray, y: np.ndarray):
        """Rotate ground coordinates (east, north) in statute miles, relative
        to ground zero, into hotline coordinates where +rx points downwind.

        wind_dir_deg is the compass bearing the plume travels toward.
        A bearing of 90 deg (due east) should map east-displacement -> +rx.
        """
        theta = np.deg2rad(90.0 - self.wind_dir_deg)  # compass -> math angle
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        rx = cos_t * x + sin_t * y
        ry = -sin_t * x + cos_t * y
        return rx, ry

    # --- public API --------------------------------------------------------

    def dose_rate_h1(self, x, y) -> np.ndarray:
        """H+1 reference dose rate (R/hr) at ground point(s).

        x, y : east / north displacement from ground zero, in statute miles.
               Scalars or numpy arrays (broadcast together).

        Returns the dose rate that *will* accumulate at that location
        normalized to 1 hour after burst. Combine with decay.py to get dose
        rate at other times or accumulated dose.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        rx, ry = self._to_hotline(x, y)

        f_x = self.yield_mt * 2.0e6 * self._phi(rx) * self._g(rx) * self.fission_fraction

        s_y = np.sqrt(
            self._s_02
            + (8.0 * np.abs(rx + 2.0 * self.s_x) * self._s_02) / self.L
            + (2.0 * (self.s_x * self.T_c * self.s_h * self.shear_mph_per_kft) ** 2)
            / self._L_2
            + (
                ((rx + 2.0 * self.s_x) * self.L_0 * self.T_c * self.s_h * self.shear_mph_per_kft)
                ** 2
            )
            / self.L ** 4
        )

        a_2 = 1.0 / (
            1.0
            + (0.001 * self.H_c * self.wind_mph / self.s_0)
            * (1.0 - norm.cdf(2.0 * rx / self.wind_mph))
        )

        f_y = np.exp(-0.5 * (ry / (a_2 * s_y)) ** 2) / (_SQRT_2PI * s_y)
        return f_x * f_y

    def time_of_arrival(self, x, y) -> np.ndarray:
        """Fallout time of arrival (hours after burst), min 0.5 hr.

        Uses the numerically-stable FORTRAN formulation (correction 2).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        rx, _ = self._to_hotline(x, y)

        T_14 = self._L_02 + 0.5 * self._s_x2
        T_15 = self._L_02 / self._L_2
        T_10 = rx + 2.0 * self.s_x
        toa = np.sqrt(
            0.25 + (T_15 * T_10 * T_10 * self.T_c * self.T_c * 2.0 * self._s_x2) / T_14
        )
        return np.maximum(toa, 0.5)
