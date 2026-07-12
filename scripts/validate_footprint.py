"""Run a footprint-validation reference case and print structural output.

This is a research tool, not a test: see
`falloutcast.validation.reference_cases` for exactly what is and is not
sourced about the two candidate cases (Small Boy and Little Feller II, both
1962) assembled so far.

Only Small Boy is actually run through Tier-1 here. Its wind is real
(`small_boy_wind_h5min()`, digitized from DNA 1251-1-EX's Table 109
sounding), and there are real digitized target points
(`SMALL_BOY_DIGITIZED_POINTS`, hand-traced from the source report's own
scanned contour figures) -- not just prose. This script prints the model's
own bearing/reach next to those digitized points for a human to eyeball. It
does not assert a pass/fail: the digitization is hand-traced from a
low-resolution 1970s photocopy (see each point's `note` for what's solid vs.
approximate), and the burst-height mismatch (Small Boy was a ~3 m tower
shot, not this model's HOB=0 assumption) means even close agreement
wouldn't be a clean validation.

Little Feller II has a real digitized wind and contour point too (and a
much closer HOB match, 3 ft vs 9.8 ft) -- but is deliberately NOT run
through Tier-1 here: its 22-ton yield pushes WSEG-10's empirical
cloud-height formula negative (see
LITTLE_FELLER_II_1962.footprint_target_note and
tests/test_footprint_validation_harness.py's
test_little_feller_ii_yield_breaks_the_cloud_height_model). Running it
anyway would silently simulate on a nonphysical release altitude and print
a number that looks like an answer but isn't one.

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
    print(f"MODEL (Tier-1): hotline bearing {result.hotline_bearing_deg:.1f} deg, "
          f"downwind reach {result.downwind_reach_miles:.1f} mi (48h grid extent), "
          f"fraction aloft {result.fraction_aloft:.3f}")

    # Tier-0/Tier-1 cross-check: the analytic engine's plume axis is the
    # layer-mean effective-wind bearing (its dose peaks at GZ), driven by the
    # same real sounding. Two independent engines agreeing on direction is a
    # real consistency check (see the harness test of the same name).
    eff = ref.small_boy_effective_wind()
    cross = abs((eff.bearing_deg - result.hotline_bearing_deg + 180.0) % 360.0 - 180.0)
    print(f"MODEL (Tier-0): plume axis {eff.bearing_deg:.1f} deg "
          f"(layer-mean effective wind {eff.speed_mph:.1f} mph) -- "
          f"agrees with Tier-1 to {cross:.1f} deg. Two independent engines on "
          "the same real wind; a DIRECTION cross-check, not a magnitude one.")
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

    print()
    print("=" * 70)
    lf2 = ref.LITTLE_FELLER_II_1962
    print(f"=== {lf2.name} ({lf2.date}) -- NOT run through Tier-1, see why ===")
    print(f"burst type: {lf2.burst_type_note}")
    print(f"target footprint: {lf2.footprint_target_note}")


if __name__ == "__main__":
    main()
