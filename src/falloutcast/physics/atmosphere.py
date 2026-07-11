"""US Standard Atmosphere 1976 (troposphere + lower stratosphere) and
Sutherland's-law viscosity.

Provides air density rho_a(z) and dynamic viscosity mu(z), the two altitude-
dependent quantities that set how fast a particle falls. Thinner, warmer/colder
air aloft changes drag, so the same particle falls FASTER up high and slows near
the ground -- which is why particles spend real time in the upper (sheared) wind
layers.

Valid to ~20 km, which covers fallout cloud tops for all yields of interest.
Above 20 km we hold the isothermal stratospheric values; air is so thin there
that the drag correction is negligible for settling.

All inputs/outputs SI: z [m], rho [kg/m^3], mu [Pa*s], T [K].
"""

from __future__ import annotations

import numpy as np

# US Standard Atmosphere 1976 constants
T0 = 288.15          # sea-level temperature, K
P0 = 101325.0        # sea-level pressure, Pa
L = 0.0065           # tropospheric lapse rate, K/m
G0 = 9.80665         # m/s^2
R_AIR = 287.05287    # specific gas constant for dry air, J/(kg K)
Z_TROPOPAUSE = 11000.0
T_TROPOPAUSE = T0 - L * Z_TROPOPAUSE            # 216.65 K
_EXP = G0 / (R_AIR * L)                          # ~5.2559
P_TROPOPAUSE = P0 * (T_TROPOPAUSE / T0) ** _EXP

# Sutherland's law (air)
MU_REF = 1.716e-5    # Pa*s at T_REF
T_REF = 273.15       # K
S_SUTH = 110.4       # K


def temperature(z):
    z = np.asarray(z, dtype=float)
    z = np.clip(z, 0.0, None)
    return np.where(z <= Z_TROPOPAUSE, T0 - L * z, T_TROPOPAUSE)


def pressure(z):
    z = np.asarray(z, dtype=float)
    z = np.clip(z, 0.0, None)
    trop = P0 * (np.clip(1.0 - L * z / T0, 1e-6, None)) ** _EXP
    strat = P_TROPOPAUSE * np.exp(-G0 * (z - Z_TROPOPAUSE) / (R_AIR * T_TROPOPAUSE))
    return np.where(z <= Z_TROPOPAUSE, trop, strat)


def density(z):
    """Air density [kg/m^3]."""
    T = temperature(z)
    P = pressure(z)
    return P / (R_AIR * T)


def viscosity(z):
    """Dynamic viscosity [Pa*s] via Sutherland's law."""
    T = temperature(z)
    return MU_REF * (T / T_REF) ** 1.5 * (T_REF + S_SUTH) / (T + S_SUTH)


def properties(z):
    """Convenience: (density, viscosity) at altitude(s) z."""
    return density(z), viscosity(z)
