"""Point-exposure assessment: what the plume means at one specific map point.

Combines the WSEG-10 H+1 reference dose-rate field and its time-of-arrival
(both from Hanifen 1980; see physics/wseg10.py) with Way-Wigner t^-1.2 decay
(physics/decay.py) to answer what the contour map alone cannot: WHEN fallout
reaches a point, how intense it is on arrival, and what dose accumulates over
a stay window -- optionally divided by a protection factor (PF), the standard
shielding divisor (dose inside = outdoor dose / PF; the PF VALUE is the
caller's assumption, nothing here asserts what any real structure provides).

Uses the same local equirectangular mile-offset convention as grid.py /
contour.py (69 mi per degree latitude, cos(lat0) shrink on longitude), so a
point clicked on a rendered isodose line evaluates to that line's level rather
than drifting from a second, subtly different projection.
"""

from __future__ import annotations

import math

from .physics import decay
from .physics.wseg10 import WSEG10
from .schemas import DISCLAIMER, DoseSample, PointExposureRequest, PointExposureResponse

# Kept in sync with contour.py/grid.py (same deliberate duplication as
# grid.py's own copy -- see the note there).
_MILES_PER_DEG_LAT = 69.0

# Default report times (hours after burst), same set the /dose endpoint uses.
_DEFAULT_TIMES = (1.0, 2.0, 6.0, 12.0, 24.0, 48.0, 168.0)


def assess(req: PointExposureRequest) -> PointExposureResponse:
    """Evaluate arrival time, dose rates, and windowed/lifetime doses at a point."""
    model = WSEG10(
        yield_mt=req.yield_mt,
        fission_fraction=req.fission_fraction,
        wind_mph=req.wind.speed_mph,
        wind_dir_deg=req.wind.bearing_deg,
        shear_mph_per_kft=req.wind.shear_mph_per_kft,
    )

    # Same projection as the contours the caller is looking at.
    x_mi = (req.point_lon - req.lon) * _MILES_PER_DEG_LAT * math.cos(math.radians(req.lat))
    y_mi = (req.point_lat - req.lat) * _MILES_PER_DEG_LAT

    r1 = float(model.dose_rate_h1(x_mi, y_mi))
    arrival = float(model.time_of_arrival(x_mi, y_mi))
    rate_at_arrival = float(decay.dose_rate_at(r1, arrival))

    distance = math.hypot(x_mi, y_mi)
    bearing = math.degrees(math.atan2(x_mi, y_mi)) % 360.0

    curve = [
        DoseSample(t_hours=t, dose_rate_rhr=float(decay.dose_rate_at(r1, t)))
        for t in _DEFAULT_TIMES
        if t >= arrival
    ]

    notes = [
        "Rates are unshielded outdoor values; doses divided by the requested "
        "protection factor are labeled 'sheltered'. The PF is your assumption "
        "-- real structures vary enormously and nothing here estimates one.",
        "Arrival time and rates are WSEG-10 idealizations (Hanifen 1980) with "
        "Way-Wigner t^-1.2 decay, valid roughly 0.5-200 h after burst. "
        "Planning estimate only -- not for real-world protective-action "
        "decisions.",
    ]

    window_unsheltered: float | None = None
    window_sheltered: float | None = None
    if req.exit_hours is not None:
        if req.exit_hours > arrival:
            window_unsheltered = float(
                decay.accumulated_dose(r1, arrival, req.exit_hours)
            )
        else:
            window_unsheltered = 0.0
            notes.append(
                f"The exposure window ends at H+{req.exit_hours:g} h, before "
                f"fallout arrives at H+{arrival:.1f} h, so the windowed dose "
                "is zero."
            )
        window_sheltered = window_unsheltered / req.protection_factor

    inf_unsheltered = float(decay.accumulated_dose_to_infinity(r1, arrival))

    if r1 < 1e-3:
        notes.append(
            "The H+1 reference rate at this point is below 0.001 R/hr -- "
            "effectively outside the modeled deposition pattern."
        )

    return PointExposureResponse(
        point=[req.point_lon, req.point_lat],
        distance_miles=distance,
        bearing_from_gz_deg=bearing,
        arrival_hours=arrival,
        dose_rate_h1_rhr=r1,
        rate_at_arrival_rhr=rate_at_arrival,
        rate_curve=curve,
        protection_factor=req.protection_factor,
        unsheltered_dose_window_r=window_unsheltered,
        sheltered_dose_window_r=window_sheltered,
        unsheltered_dose_to_infinity_r=inf_unsheltered,
        sheltered_dose_to_infinity_r=inf_unsheltered / req.protection_factor,
        disclaimer=DISCLAIMER,
        notes=notes,
    )
