"""Terminal (settling) velocity of fallout particles.

Terminal velocity is where gravity balances aerodynamic drag on a sphere:

    v_t = sqrt( 4 g d (rho_p - rho_a) / (3 rho_a C_d) )

C_d (drag coefficient) depends on Reynolds number, which depends on v_t --
implicit. We break the circularity with the Best (Davies) number, which is
independent of velocity:

    N_Be = C_d * Re^2 = 4 rho_a (rho_p - rho_a) g d^3 / (3 mu^2)

We compute N_Be directly, then invert the Schiller-Naumann drag law
    C_d = (24/Re)(1 + 0.15 Re^0.687)   ->   N_Be = 24 Re (1 + 0.15 Re^0.687)
for Re with a damped Newton iteration run over the WHOLE array a fixed number of
times (no per-particle Python loop), then

    v_t = Re * mu / (rho_a * d).

In the small-particle limit this reduces to Stokes' law,
    v_t = (rho_p - rho_a) g d^2 / (18 mu),
which we assert in the tests.

SI units throughout: d [m], rho [kg/m^3], mu [Pa*s], v_t [m/s].
"""

from __future__ import annotations

import numpy as np

from . import atmosphere

G = 9.80665
# Silicate/glass fallout particle density. PLACEHOLDER pending DELFIC value;
# ~2600 kg/m^3 is the standard assumption for soil-derived fallout.
RHO_P_DEFAULT = 2600.0


def _re_from_best(n_be: np.ndarray, iters: int = 60) -> np.ndarray:
    """Invert  N_Be = 24 Re (1 + 0.15 Re^0.687)  for Re, vectorized.

    Damped Newton in Re, seeded with the Stokes guess Re0 = N_Be/24. Runs a
    fixed number of iterations across the entire array; converges well before
    `iters` for the fallout size/altitude range.
    """
    n_be = np.asarray(n_be, dtype=float)
    re = np.maximum(n_be / 24.0, 1e-12)  # Stokes seed
    for _ in range(iters):
        f = 24.0 * re * (1.0 + 0.15 * re ** 0.687) - n_be
        df = 24.0 * (1.0 + 0.15 * 1.687 * re ** 0.687)
        step = f / df
        # damp to keep Re positive and avoid overshoot for large N_Be
        re = np.maximum(re - 0.5 * step, 1e-12)
    return re


def terminal_velocity(d, rho_a, mu, rho_p: float = RHO_P_DEFAULT) -> np.ndarray:
    """Terminal velocity [m/s] for particle diameter(s) d in air (rho_a, mu)."""
    d = np.asarray(d, dtype=float)
    rho_a = np.asarray(rho_a, dtype=float)
    mu = np.asarray(mu, dtype=float)

    n_be = 4.0 * rho_a * (rho_p - rho_a) * G * d ** 3 / (3.0 * mu ** 2)
    re = _re_from_best(n_be)
    return re * mu / (rho_a * d)


def stokes_velocity(d, rho_a, mu, rho_p: float = RHO_P_DEFAULT) -> np.ndarray:
    """Closed-form Stokes velocity [m/s] (valid only for Re << 1). Used in tests
    to check the small-particle limit of the full solver."""
    d = np.asarray(d, dtype=float)
    return (rho_p - rho_a) * G * d ** 2 / (18.0 * mu)


def velocity_at_altitude(d, z, rho_p: float = RHO_P_DEFAULT) -> np.ndarray:
    """Terminal velocity [m/s] for diameter d at altitude z [m]."""
    rho_a, mu = atmosphere.properties(z)
    return terminal_velocity(d, rho_a, mu, rho_p=rho_p)
