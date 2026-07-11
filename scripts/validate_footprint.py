"""Run a footprint-validation reference case and print structural output.

This is a research tool, not a test: see
`falloutcast.validation.reference_cases` for exactly what is and is not
sourced about the one candidate case (Small Boy, 1962) assembled so far.

As of the third research pass, the wind IS real: `small_boy_wind_h5min()` is
digitized from DNA 1251-1-EX's actual Table 109 sounding (see that module for
the citation), not a placeholder. What's still missing is a digitized target
footprint (contour geometry) to assert against -- the source report's own
prose says fallout "started arriving at 250 to 400 miles downwind... late...
D+1 day reaching a peak at D+2 days," tracked as far as western Nebraska.
This script prints that alongside the model's own output for a human to
eyeball the order of magnitude; it does not assert a pass/fail, because a
qualitative range in prose isn't a number precise enough to assert against,
and the burst-height mismatch (Small Boy was a ~3 m tower shot, not HOB=0)
means even a perfect match here wouldn't be a clean validation anyway.

Usage: python scripts/validate_footprint.py
"""

from __future__ import annotations

import numpy as np

from falloutcast.validation import reference_cases as ref

# Rough reference point for "western Nebraska" (Scottsbluff), just to compute
# a bearing for eyeballing against the model's own hotline bearing below --
# not a precise target, the source only says "as far as western Nebraska."
_W_NEBRASKA_LAT, _W_NEBRASKA_LON = 41.87, -103.66


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return float(np.degrees(np.arctan2(y, x)) % 360.0)


def main() -> None:
    case = ref.SMALL_BOY_1962
    print(f"=== {case.name} ({case.date}) ===")
    print(f"yield: {case.yield_kt} kt -- {case.yield_source}")
    print(f"burst type: {case.burst_type_note}")
    print(f"fission fraction: {case.fission_fraction_note}")
    print(f"target footprint: {case.footprint_target_note}")
    print()

    heights_m, u, v = ref.small_boy_wind_h5min()
    print("Wind: REAL historical sounding (DNA 1251-1-EX Table 109, H+5min, "
          "Frenchman's Flat) -- see reference_cases.py module docstring.")
    print()

    # t_max=48h to reach the source's "peak at D+2 days", not the 24h default
    # (which only covers to "D+1", the report's "started arriving" boundary).
    result = ref.run_case(
        case,
        heights_m=heights_m, wind_u_ms=u, wind_v_ms=v,
        fission_fraction=1.0,  # unboosted-fission assumption, see case note
        t_max_s=48 * 3600.0,
    )
    print(f"hotline bearing: {result.hotline_bearing_deg} deg "
          f"(bearing to western Nebraska from GZ, for context: "
          f"{_bearing_deg(case.lat, case.lon, _W_NEBRASKA_LAT, _W_NEBRASKA_LON):.0f} deg)")
    print(f"downwind reach: {result.downwind_reach_miles:.1f} mi (grid extent, "
          f"48h run) -- source reports fallout reaching 250-400 mi by late D+1")
    print(f"fraction still aloft at t_max: {result.fraction_aloft:.3f}")
    print()
    print("This is an order-of-magnitude/bearing eyeball check against prose, "
          "not an assertion -- no digitized contour to check against, and the "
          "burst-height mismatch (3 m tower vs this model's HOB=0 assumption) "
          "means agreement wouldn't be a clean validation even with one.")
    print("Real wind used, but note it's a single H+5min snapshot from a site "
          "sounding, not a multi-day, multi-station reconstruction -- Tier-1 "
          "holds the top/bottom-level wind constant beyond the sounding's own "
          "3,078-20,000 ft range and for the full 48h simulated, which the "
          "real atmosphere did not do.")


if __name__ == "__main__":
    main()
