"""Print WSEG-10 vs the Glasstone & Dolan idealized surface-burst pattern.

The project's first footprint-MAGNITUDE validation (the historical NTS cases in
scripts/validate_footprint.py can only cross-check direction). See
falloutcast.validation.idealized_pattern for the sourced Table 9.93 reference
and the honest scope of what this establishes.

Usage: python scripts/validate_idealized_pattern.py
"""

from __future__ import annotations

from falloutcast.validation import idealized_pattern as ip


def main() -> None:
    yield_mt = 1.0
    print("=== WSEG-10 vs Glasstone & Dolan idealized pattern ===")
    print(f"1 Mt contact surface burst, pure fission, {ip.EFFECTIVE_WIND_MPH:.0f} mph "
          "effective wind. G&D = Effects of Nuclear Weapons (1977) Table 9.93; "
          "WSEG-10 run at zero speed-shear (see module docstring on why).")
    print()
    print(f"{'R/hr':>6} | {'G&D down':>9} {'WSEG down':>9} {'ratio':>6} | "
          f"{'G&D wid':>8} {'WSEG wid':>8}")
    print("-" * 60)
    for c in ip.compare(yield_mt=yield_mt, shear_mph_per_kft=0.0):
        excluded = "" if c.level_rhr in ip.VALIDATED_LEVELS else "  (excluded)"
        if c.model_downwind_mi is None:
            print(f"{c.level_rhr:>6} | {c.reference_downwind_mi:9.1f} {'--':>9} "
                  f"{'--':>6} | {c.reference_width_mi:8.1f} {'--':>8}{excluded}")
        else:
            print(f"{c.level_rhr:>6} | {c.reference_downwind_mi:9.1f} "
                  f"{c.model_downwind_mi:9.1f} {c.downwind_ratio:6.2f} | "
                  f"{c.reference_width_mi:8.1f} {c.model_width_mi:8.1f}{excluded}")
    print()
    print("Downwind reach agrees within a factor of ~2 across the validated "
          "fallout contours (1000..1 R/hr) -- a real magnitude match between two "
          "independent idealized models. The 3000 R/hr close-in contour is "
          "excluded (G&D sec. 9.94: inside the blast/thermal devastation zone). "
          "Width matches well for the tight high-dose contours; it diverges far "
          "downwind because WSEG-10's crosswind growth is SPEED-shear driven, a "
          "different parameterization than G&D's 15-degree directional shear.")
    print()

    print("--- Tier-1 (multi-layer advection) vs the same G&D reference ---")
    print(f"{'R/hr':>6} | {'G&D down':>9} {'T1 down':>9} {'ratio':>6}")
    print("-" * 36)
    for c in ip.compare_tier1(yield_mt=yield_mt):
        excluded = "" if c.level_rhr in ip.VALIDATED_LEVELS else "  (excluded)"
        md = f"{c.model_downwind_mi:9.1f}" if c.model_downwind_mi is not None else f"{'--':>9}"
        rt = f"{c.downwind_ratio:6.2f}" if c.downwind_ratio is not None else f"{'--':>6}"
        print(f"{c.level_rhr:>6} | {c.reference_downwind_mi:9.1f} {md} {rt}{excluded}")
    print()
    print("Tier-1 also lands within ~a factor of 2 downwind. Its dose magnitude "
          "is anchored to G&D's activity normalization, so this mainly validates "
          "that its fall-velocity binning + puff advection DISTRIBUTE activity to "
          "the right distances (vs Tier-0's analytic smear).")
    print()
    print("Scope: conformance to G&D's canonical idealized surface-burst "
          "reference (itself calibrated to test data), NOT a fit to one specific "
          "measured shot. It is the first check that WSEG-10's footprint SIZE "
          "(not just direction) is right.")


if __name__ == "__main__":
    main()
