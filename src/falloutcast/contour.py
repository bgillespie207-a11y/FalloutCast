"""Turn a sampled dose-rate grid into GeoJSON isodose contours in WGS84.

Standard protective-action dose-rate bands (R/hr at H+1) are used by default;
these are the same tiers civil-defense planning tends to care about. The
mile-offset -> lat/lon step uses a local equirectangular approximation centered
on ground zero, which is accurate to well within plume-scale error.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .grid import DoseGrid

# Default H+1 dose-rate contour levels, R/hr.
DEFAULT_LEVELS: tuple[float, ...] = (1.0, 10.0, 100.0, 1000.0)

_MILES_PER_DEG_LAT = 69.0


def _offsets_to_lonlat(x_mi, y_mi, lat0, lon0):
    lat = lat0 + y_mi / _MILES_PER_DEG_LAT
    lon = lon0 + x_mi / (_MILES_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return lon, lat


def to_geojson(
    grid: DoseGrid,
    lat0: float,
    lon0: float,
    levels: Sequence[float] = DEFAULT_LEVELS,
) -> dict:
    """Return a GeoJSON FeatureCollection of MultiLineString isodose contours.

    Each feature carries {"dose_rate_h1_rhr": level}. Contours are extracted
    with a marching-squares implementation (matplotlib) with no figure/GUI.
    """
    # contourpy is the maintained marching-squares library (matplotlib's
    # backend). Keeping it here means the core physics stays dependency-light.
    from contourpy import contour_generator

    x = grid.x_miles
    y = grid.y_miles
    z = np.ascontiguousarray(grid.dose_rate_h1, dtype=np.float64)
    gx, gy = np.meshgrid(x, y)

    gen = contour_generator(gx, gy, z)

    features = []
    for level in levels:
        lines = gen.lines(level)  # list of (N,2) arrays in mile-offset space
        coords = []
        for seg in lines:
            if len(seg) < 2:
                continue
            ring = [list(_offsets_to_lonlat(px, py, lat0, lon0)) for px, py in seg]
            coords.append(ring)
        if not coords:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"dose_rate_h1_rhr": level},
                "geometry": {"type": "MultiLineString", "coordinates": coords},
            }
        )

    return {"type": "FeatureCollection", "features": features}
