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


# Aggregation policies for compositing many targets onto one grid.
#   "max"  -- cell-wise MAX: the worst dose from ANY SINGLE source at each point.
#             A screening envelope, NOT a combined-exchange total.
#   "sum"  -- cell-wise SUM: dose contributions from overlapping plumes ADD, a
#             simultaneous-detonation total at H+1. Still not time-aligned for
#             staggered arrivals (a documented future step).
AGGREGATIONS = ("max", "sum")


def sample_envelope(
    models: list[tuple[WSEG10, float, float]],
    *,
    lon_bounds: tuple[float, float] = (CONUS_LON_MIN, CONUS_LON_MAX),
    lat_bounds: tuple[float, float] = (CONUS_LAT_MIN, CONUS_LAT_MAX),
    resolution_deg: float = 0.1,
    radius_deg: float | None = None,
    aggregation: str = "max",
) -> DoseGridLonLat:
    """Composite a dose-rate grid across multiple ground zeros.

    `models` is a list of (WSEG10 model, ground-zero lat, ground-zero lon)
    triples -- one per target, each already carrying its own wind. For every
    cell of a shared lon/lat grid, converts that cell to the (east, north)
    mile-offset each target's own WSEG10 model expects (a per-target local
    equirectangular approximation centered on THAT target's own latitude,
    matching `contour.to_geojson`'s inverse conversion -- accurate near each
    target, which is what matters since WSEG-10 dose decays to ~0 within a
    few hundred miles) and evaluates that target's dose rate there.

    `aggregation` (see AGGREGATIONS) chooses how per-target contributions
    combine at each cell: "max" is the max-single-source screening envelope
    (the worst dose from any ONE target -- NOT a combined total); "sum" adds
    overlapping contributions for a simultaneous H+1 total. This is one grid,
    one contour set -- not a per-target overlay.

    `resolution_deg` trades accuracy for the O(len(models) * grid_size) cost of
    evaluating every target's (vectorized, but not free) analytic dose function.
    0.1 deg (~7 mi) is a reasonable default.

    `radius_deg` is a scaling optimization for large decks (e.g. the ~500-point
    expanded target deck in `targetdeck.py`): instead of evaluating every
    target against the entire CONUS grid, evaluate each target only within a
    +/-`radius_deg` lon/lat window around its own ground zero, and combine just
    that sub-block into the envelope. Cells outside every target's window stay
    zero -- which is correct as long as `radius_deg` comfortably exceeds the
    plume reach (WSEG-10 dose decays to ~0 within a few hundred miles; ~10 deg
    ~= 690 mi is safe for the deck's yields). `None` (default) keeps the exact
    original full-grid behavior, so existing results/tests are unchanged.
    """
    if aggregation not in AGGREGATIONS:
        raise ValueError(f"aggregation must be one of {AGGREGATIONS}, got {aggregation!r}")
    combine = np.maximum if aggregation == "max" else np.add

    n_lon = int((lon_bounds[1] - lon_bounds[0]) / resolution_deg) + 1
    n_lat = int((lat_bounds[1] - lat_bounds[0]) / resolution_deg) + 1
    lon_axis = np.linspace(lon_bounds[0], lon_bounds[1], n_lon)
    lat_axis = np.linspace(lat_bounds[0], lat_bounds[1], n_lat)

    envelope = np.zeros((n_lat, n_lon), dtype=float)

    if radius_deg is None:
        glon, glat = np.meshgrid(lon_axis, lat_axis)
        for model, gz_lat, gz_lon in models:
            y_mi = (glat - gz_lat) * _MILES_PER_DEG_LAT
            x_mi = (glon - gz_lon) * _MILES_PER_DEG_LAT * np.cos(np.radians(gz_lat))
            dose = model.dose_rate_h1(x_mi, y_mi)
            combine(envelope, dose, out=envelope)
        return DoseGridLonLat(lon_deg=lon_axis, lat_deg=lat_axis, dose_rate_h1=envelope)

    # Local-window path: only touch the sub-grid within radius_deg of each GZ.
    for model, gz_lat, gz_lon in models:
        i0 = int(np.searchsorted(lon_axis, gz_lon - radius_deg, side="left"))
        i1 = int(np.searchsorted(lon_axis, gz_lon + radius_deg, side="right"))
        j0 = int(np.searchsorted(lat_axis, gz_lat - radius_deg, side="left"))
        j1 = int(np.searchsorted(lat_axis, gz_lat + radius_deg, side="right"))
        if i0 >= i1 or j0 >= j1:
            continue  # target's window falls entirely outside the grid
        sub_lon, sub_lat = np.meshgrid(lon_axis[i0:i1], lat_axis[j0:j1])
        y_mi = (sub_lat - gz_lat) * _MILES_PER_DEG_LAT
        x_mi = (sub_lon - gz_lon) * _MILES_PER_DEG_LAT * np.cos(np.radians(gz_lat))
        dose = model.dose_rate_h1(x_mi, y_mi)
        block = envelope[j0:j1, i0:i1]
        combine(block, dose, out=block)

    return DoseGridLonLat(lon_deg=lon_axis, lat_deg=lat_axis, dose_rate_h1=envelope)
