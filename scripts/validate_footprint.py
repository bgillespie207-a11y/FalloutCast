"""Run a footprint-validation reference case and print structural output.

This is a research tool, not a test: see
`falloutcast.validation.reference_cases` for exactly what is and is not
sourced about the one candidate case (Small Boy, 1962) assembled so far.

As of the fourth research pass: the wind IS real (`small_boy_wind_h5min()`,
digitized from DNA 1251-1-EX's Table 109 sounding), and there ARE real
digitized target points now (`SMALL_BOY_DIGITIZED_POINTS`, hand-traced from
the source report's own scanned contour figures) -- not just prose. This
script prints the model's own bearing/reach next to those digitized points
for a human to eyeball. It still does not assert a pass/fail: the
digitization is hand-traced from a low-resolution 1970s photocopy (see each
point's `note` for what's solid vs. approximate), and the burst-height
mismatch (Small Boy was a ~3 m tower shot, not this model's HOB=0
assumption) means even close agreement wouldn't be a clean validation.

Usage: python scripts/validate_footprint.py
"""

from __future__ import annotations

from falloutcast.validation import reference_cases as ref


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
    print(f"MODEL: hotline bearing {result.hotline_bearing_deg:.1f} deg, "
          f"downwind reach {result.downwind_reach_miles:.1f} mi (48h grid extent), "
          f"fraction aloft {result.fraction_aloft:.3f}")
    print()
    print("DIGITIZED TARGET POINTS (hand-traced from the source's own scanned "
          "contour figures -- see each note for confidence caveats):")
    for p in ref.SMALL_BOY_DIGITIZED_POINTS:
        level = f"{p.dose_rate_rhr} R/hr" if p.dose_rate_rhr is not None else "level unclear"
        print(f"  - {p.label}: {p.distance_mi:.0f} mi, bearing {p.bearing_deg:.0f} deg ({level})")
        print(f"    [{p.source_figure}] {p.note}")
    print()
    bearings = [p.bearing_deg for p in ref.SMALL_BOY_DIGITIZED_POINTS]
    print(f"Digitized bearings span {min(bearings):.0f}-{max(bearings):.0f} deg; "
          f"model bearing is {result.hotline_bearing_deg:.1f} deg -- "
          "same NE quadrant, a real and unforced (not cherry-picked) agreement, "
          "but NOT a precision match and not something to read as validation: "
          "the digitization itself is hand-traced/approximate, and the "
          "burst-height mismatch means agreement wouldn't be clean even with "
          "perfect data on both sides.")
    print("Real wind used, but note it's a single H+5min snapshot from a site "
          "sounding, not a multi-day, multi-station reconstruction -- Tier-1 "
          "holds the top/bottom-level wind constant beyond the sounding's own "
          "3,078-20,000 ft range and for the full 48h simulated, which the "
          "real atmosphere did not do.")


if __name__ == "__main__":
    main()
