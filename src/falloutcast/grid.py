"""Sample a WSEG-10 solution onto a regular ground grid (statute-mile offsets
from ground zero), ready for contouring.

The grid auto-sizes to the plume: it extends far enough downwind to capture the
lowest dose-rate band of interest and stays tight crosswind/upwind.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .physics.wseg10 import WSEG10


@dataclass
class DoseGrid:
    x_miles: np.ndarray  # 1D east offsets from GZ
    y_miles: np.ndarray  # 1D north offsets from GZ
    dose_rate_h1: np.ndarray  # 2D (len(y), len(x)) R/hr at H+1


def sample(
    model: WSEG10,
    *,
    downwind_max_miles: float = 500.0,
    crosswind_max_miles: float = 120.0,
    upwind_miles: float = 40.0,
    resolution_miles: float = 2.0,
) -> DoseGrid:
    """Evaluate the H+1 dose-rate field on a grid.

    The grid is built in east/north space but sized in the wind frame, then we
    just take a generous bounding box so any plume orientation fits. For a v1
    this is simple and robust; a later optimization can rotate the grid to the
    hotline to cut wasted cells.
    """
    reach = downwind_max_miles + upwind_miles
    half = max(reach, crosswind_max_miles)
    n = int(2 * half / resolution_miles) + 1

    axis = np.linspace(-half, half, n)
    gx, gy = np.meshgrid(axis, axis)
    field = model.dose_rate_h1(gx, gy)

    return DoseGrid(x_miles=axis, y_miles=axis, dose_rate_h1=field)
