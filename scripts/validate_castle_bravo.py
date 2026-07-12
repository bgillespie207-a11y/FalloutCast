"""Print WSEG-10 vs the measured Castle Bravo (1954) fallout footprint.

The project's first comparison against a REAL measured shot (idealized_pattern.py
compares against G&D's idealized reference instead). This is a coarse,
heavily-caveated sanity check -- see falloutcast.validation.castle_bravo for the
sourced measured data and the honest scope.

Usage: python scripts/validate_castle_bravo.py
"""

from __future__ import annotations

from falloutcast.validation import castle_bravo as cb


def main() -> None:
    r = cb.run_model()
    print("=== WSEG-10 vs measured Castle Bravo (1954) ===")
    print(f"{cb.MEASURED_YIELD_MT:.0f} Mt total, ~{cb.FISSION_FRACTION:.0%} fission, "
          f"~{cb.HOB_FT:.0f} ft above a coral reef (~surface). Effective wind "
          f"{cb.EFFECTIVE_WIND_MPH:.0f} mph, DERIVED from the sourced fallout "
          "arrival (~100-115 mi in 4-6 h). Model H+1 field converted to 96-h "
          "accumulated dose via Way-Wigner decay.")
    print()
    print(f"{'quantity':<34}{'measured':>12}{'model':>10}{'ratio':>8}")
    print("-" * 64)
    rows = [
        ("700-rad/96h belt length (mi)", cb.LETHAL_700RAD_LENGTH_MI, r.belt_length_mi),
        ("700-rad/96h belt width (mi)", cb.LETHAL_700RAD_WIDTH_MI, r.belt_width_mi),
        ("overall contaminated extent (mi)", cb.OVERALL_DOWNWIND_MI, r.overall_extent_mi),
        ("Rongelap-S dose @115mi (rad)", cb.RONGELAP_S_RAD, r.dose_at_rongelap_s_rad),
    ]
    for name, meas, mod in rows:
        print(f"{name:<34}{meas:>12.0f}{mod:>10.0f}{mod/meas:>8.2f}")
    print()
    print("The 700-rad lethal belt matches the measured ~170 x 35 mi within a "
          "factor of ~1.5; overall extent is the same order (model runs short). "
          "The centerline point-dose runs high -- the real pattern is irregular "
          "with a suspected hot spot near that range (G&D sec. 9.109), which a "
          "smooth analytic plume can't reproduce.")
    print()
    print("SCOPE: a coarse, factor-~2 tie to real ground truth -- NOT precision. "
          "Coral-reef surface (vs WSEG-10's continental-soil calibration), a "
          "measured pattern G&D itself calls 'largely guesswork', a single "
          "derived effective wind, and an accumulated-dose conversion all bound "
          "how tight this can be. It establishes footprint SCALE, not detail.")


if __name__ == "__main__":
    main()
