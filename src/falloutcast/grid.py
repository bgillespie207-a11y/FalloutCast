"""Sample a WSEG-10 solution onto a regular ground grid (statute-mile offsets
from ground zero), ready for contouring.

The grid auto-sizes to the plume: it extends far enough downwind to capture the
lowest dose-rate band of interest and stays tight crosswind/upwind.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .physics.wseg10 import WSEG10

# Same mean-Earth-radius-based degrees-latitude-to-miles approximation
# contour.py uses for the inverse (local mile-offset -> lon/lat) conversion;
# kept in sync with that module's `_MILES_PER_DEG_LAT` rather than imported,
# since this file has no other dependency on contour.py.
_MILES_PER_DEG_LAT = 69.0


@dataclass
class DoseGrid:
    x_miles: np.ndarray  # 1D east offsets from GZ
    y_miles: np.ndarray  # 1D north offsets from GZ
    dose_rate_h1: np.ndarray  # 2D (len(y), len(x)) R/hr at H+1


@dataclass
class DoseGridLonLat:
    """A dose-rate field on a grid natively in geographic coordinates, for
    compositing across multiple ground zeros that don't share a common local
    origin (see `sample_envelope`). `contour.to_geojson_lonlat` consumes this
    directly -- no mile-offset/origin conversion needed, since the axes
    already are lon/lat."""

    lon_deg: np.ndarray  # 1D
    lat_deg: np.ndarray  # 1D
    dose_rate_h1: np.ndarray  # 2D (len(lat), len(lon)) R/hr at H+1, max envelope


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


# Generous CONUS bounding box (degrees), not a physical constant -- an
# engineering/UX choice of how much map to cover, same spirit as `sample`'s
# downwind/crosswind reach defaults above. Includes margin beyond the
# coastline/border so a plume centered near an edge target isn't clipped.
CONUS_LON_MIN, CONUS_LON_MAX = -125.5, -66.0
CONUS_LAT_MIN, CONUS_LAT_MAX = 24.0, 50.0


def sample_envelope(
    models: list[tuple[WSEG10, float, float]],
    *,
    lon_bounds: tuple[float, float] = (CONUS_LON_MIN, CONUS_LON_MAX),
    lat_bounds: tuple[float, float] = (CONUS_LAT_MIN, CONUS_LAT_MAX),
    resolution_deg: float = 0.1,
) -> DoseGridLonLat:
    """Composite max-envelope dose-rate grid across multiple ground zeros.

    `models` is a list of (WSEG10 model, ground-zero lat, ground-zero lon)
    triples -- one per target, each already carrying its own wind. For every
    cell of a shared lon/lat grid, converts that cell to the (east, north)
    mile-offset each target's own WSEG10 model expects (a per-target local
    equirectangular approximation centered on THAT target's own latitude,
    matching `contour.to_geojson`'s inverse conversion -- accurate near each
    target, which is what matters since WSEG-10 dose decays to ~0 within a
    few hundred miles), evaluates that target's dose rate there, and takes
    the cell-wise MAX across all targets. This is a true national
    max-envelope surface (PRD.md M2), not a per-target overlay: one grid,
    one contour set, answering "what's the worst H+1 dose rate at this point
    from ANY of these targets" rather than returning N separate plumes.

    `resolution_deg` trades accuracy for the O(len(models) * grid_size) cost
    of evaluating every target's (vectorized, but not free) analytic dose
    function at every grid cell. 0.1 deg (~7 mi) is a reasonable default for
    ~10 CONUS-scale targets; there is no caching yet (PRD.md's "aggressive
    per-met-run caching" is a documented future step, not implemented here).
    """
    n_lon = int((lon_bounds[1] - lon_bounds[0]) / resolution_deg) + 1
    n_lat = int((lat_bounds[1] - lat_bounds[0]) / resolution_deg) + 1
    lon_axis = np.linspace(lon_bounds[0], lon_bounds[1], n_lon)
    lat_axis = np.linspace(lat_bounds[0], lat_bounds[1], n_lat)
    glon, glat = np.meshgrid(lon_axis, lat_axis)

    envelope = np.zeros_like(glon)
    for model, gz_lat, gz_lon in models:
        y_mi = (glat - gz_lat) * _MILES_PER_DEG_LAT
        x_mi = (glon - gz_lon) * _MILES_PER_DEG_LAT * np.cos(np.radians(gz_lat))
        dose = model.dose_rate_h1(x_mi, y_mi)
        np.maximum(envelope, dose, out=envelope)

    return DoseGridLonLat(lon_deg=lon_axis, lat_deg=lat_axis, dose_rate_h1=envelope)
