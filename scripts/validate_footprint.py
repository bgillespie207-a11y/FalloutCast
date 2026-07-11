"""Run a footprint-validation reference case and print structural output.

This is a research tool, not a test: see
`falloutcast.validation.reference_cases` for exactly what is and is not
sourced about the one candidate case (Small Boy, 1962) assembled so far, and
why nothing here is asserted against a target number.

The wind profile below is NOT the real wind Small Boy's cloud saw on
1962-07-14 -- no automated source for that was found (see the module
docstring). It's a placeholder westerly profile so this script is runnable;
replace it with a digitized historical sounding before drawing any
conclusion from the output.

Usage: python scripts/validate_footprint.py
"""

from __future__ import annotations

import numpy as np

from falloutcast.validation import reference_cases as ref

# PLACEHOLDER wind profile -- see module docstring. NOT sourced to the actual
# 1962-07-14 Nevada Test Site sounding.
_PLACEHOLDER_HEIGHTS_M = np.array([100.0, 1500.0, 3000.0, 5500.0, 9000.0, 12000.0])
_PLACEHOLDER_WIND_U_MS = np.array([3.0, 4.0, 6.0, 8.0, 10.0, 12.0])
_PLACEHOLDER_WIND_V_MS = np.zeros(6)


def main() -> None:
    case = ref.SMALL_BOY_1962
    print(f"=== {case.name} ({case.date}) ===")
    print(f"yield: {case.yield_kt} kt -- {case.yield_source}")
    print(f"burst type: {case.burst_type_note}")
    print(f"fission fraction: {case.fission_fraction_note}")
    print(f"target footprint: {case.footprint_target_note}")
    print()
    print("!! Wind profile below is a PLACEHOLDER, not the real historical "
          "sounding. Structural smoke-run only. !!")
    print()

    result = ref.run_case(
        case,
        heights_m=_PLACEHOLDER_HEIGHTS_M,
        wind_u_ms=_PLACEHOLDER_WIND_U_MS,
        wind_v_ms=_PLACEHOLDER_WIND_V_MS,
        fission_fraction=1.0,  # unboosted-fission assumption, see case note
    )
    print(f"hotline bearing: {result.hotline_bearing_deg} deg")
    print(f"downwind reach: {result.downwind_reach_miles:.1f} mi (grid extent)")
    print(f"fraction still aloft at t_max: {result.fraction_aloft:.3f}")
    print()
    print("No target number exists yet to compare these against -- see "
          "reference_cases.py for what's still needed.")


if __name__ == "__main__":
    main()
