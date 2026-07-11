"""Historical-test reference cases for Tier-1 footprint validation.

STATUS: scaffolding, not a validation suite. TIER1_SPEC.md test-plan item 7
calls for comparing a Tier-1 footprint against a published DELFIC or HYSPLIT
reference before trusting Tier-1 shapes in the UI. This module is the
research result of trying to assemble one such case, and an honest account
of why it isn't a passing/failing test yet -- per this project's rule against
claiming validation that didn't happen, nothing here is wired into a
numeric assertion.

What blocked a full case (as of this research pass, 2026-07, updated after a
second pass that pinned down SMALL_BOY_1962's numbers more precisely):

1. NO CONFIRMED SURFACE BURST -- now precisely quantified, still unresolved.
   FalloutCast models surface bursts only. The one detailed published
   DELFIC/HYSPLIT accuracy study located (Miller, "A Comparison in the
   Accuracy of Mapping Nuclear Fallout Patterns using HPAC, HYSPLIT, DELFIC
   FPT and an AFIT FORTRAN95 Fallout Deposition Code", AFIT thesis, 2011,
   DTIC ADA538272) validates DELFIC FPT against 6 real NTS shots (George,
   Ess, Zucchini, Priscilla, Smoky, Johnie Boy) -- but none is a true
   surface burst (mostly 300-700 ft tower shots; Ess and Johnie Boy are
   shallow-subsurface cratering shots). Comparing our surface-burst-only
   model against a tower shot's footprint would be a physical mismatch, not
   a real test.

   SMALL_BOY_1962 below was the one NTS shot this project hoped might be a
   true (HOB=0) surface detonation. A second research pass found a
   well-sourced shot table (see `citation`) that RESOLVES the ambiguity, but
   not in our favor: Small Boy was a ~3 m tower/stand shot, not a literal
   ground-level burst. It's confirmed close to the ground for a 1.7 kt
   device, but it is a confirmed, quantified mismatch with HOB=0, not a
   match -- see `height_of_burst_m` and `burst_type_note`.

2. NO MACHINE-USABLE TARGET FOOTPRINT. The AFIT thesis reports DELFIC FPT's
   accuracy as a Normalized Absolute Difference (NAD ~0.12-0.28) against the
   real DNA 1251-1-EX contours, and shows comparison figures -- but neither
   is a number I could assert as "the Tier-1 footprint's reach should be
   X miles". Turning this into a real test needs either the raw DNA
   1251-1-EX contour digitization, or hand-extracted coordinates from the
   thesis's figures (28-32).

3. NO HISTORICAL WIND PROFILE. Tier-1 needs a full vertical wind profile.
   Open-Meteo's historical ERA5 archive (`archive-api.open-meteo.com`)
   covers 1962, confirmed live -- but does NOT expose the pressure-level
   wind fields (`windspeed_XXXhPa` etc.) that `weather/openmeteo.py` uses;
   they return null with no error. So there is currently no automated way
   to fetch the actual wind ground zero saw on the test date. A wind
   profile must be supplied by hand (see `run_case`) from some other
   source (e.g. digitized radiosonde data from the test report) to run a
   case at all.

Given all three gaps, `run_case` below is a tool for a future contributor who
tracks down the missing pieces -- not something wired into pytest's assert-
based tests. See `tests/test_footprint_validation_harness.py` for the one
thing that IS tested here: that the harness plumbing itself runs and returns
sane, finite, structurally-bounded output (a code-correctness check, not a
physics validation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..physics import tier1


@dataclass(frozen=True)
class ReferenceCase:
    """A historical-test candidate for footprint validation.

    Every field is either a cited fact or an explicit, labeled unknown --
    nothing here is a filled-in guess presented as sourced (project rule 1).
    """

    name: str
    date: str
    lat: float
    lon: float
    yield_kt: float
    yield_source: str
    height_of_burst_m: float      # confirmed tower/stand height above grade
    burst_type_note: str          # what's known/unresolved about HOB
    fission_fraction_note: str    # DOE/NV-209 does not publish this; unknown
    footprint_target_note: str    # what (if anything) exists to compare against
    citation: str


SMALL_BOY_1962 = ReferenceCase(
    name="Small Boy",
    date="1962-07-14",
    # NTS Area 5, 36.798N 115.932W -- per the sourced table below (not the
    # earlier approximate guess this field held before that table was found).
    lat=36.798,
    lon=-115.932,
    yield_kt=1.7,
    yield_source=(
        "CONFIRMED 1.7 kt via Wikipedia's 'Operation Sunbeam' shot table "
        "(https://en.wikipedia.org/wiki/Operation_Sunbeam, retrieved "
        "2026-07-10), which cites DOE/NV-209 Rev 15 ('United States Nuclear "
        "Tests, July 1945 through September 1992'), Norris & Cochran, "
        "'United States nuclear tests, July 1945 to 31 December 1992' (NWD "
        "94-1, NRDC Nuclear Weapons Databook, 1994), and Hansen, 'The Swords "
        "of Armageddon', Vol. 8 (1995) in agreement. The primary DOE/NV-209 "
        "PDF (nnss.gov) itself still blocks automated fetch (WAF challenge), "
        "so this is a secondary-source confirmation, not a primary-document "
        "read -- but three independent secondary compilations agreeing is "
        "materially stronger than the single unverified figure this field "
        "held before."
    ),
    height_of_burst_m=3.0,
    burst_type_note=(
        "RESOLVED (was previously ambiguous): the same sourced table lists "
        "delivery as 'tower, weapon effect' at 'elevation 940 m (3,080 ft) + "
        "height 3 m (9.8 ft)' -- i.e. a ~3 m tower/stand, NOT a literal "
        "height-of-burst=0 surface burst. This project's model assumes "
        "surface burst (HOB=0); a 3 m stand for a 1.7 kt device is close to "
        "the ground (fireball radius for a burst this size is order-10s-of-"
        "meters per Glasstone & Dolan HOB-scaling curves) but is still a "
        "confirmed, quantified MISMATCH with the model's assumption, not an "
        "exact match. Also correcting an earlier draft of this note, which "
        "speculatively described Small Boy's purpose as fallout-pattern "
        "study: the sourced table instead gives the purpose as 'missile "
        "silo hardening principles, specifically EMP' -- that speculation "
        "was this project's own unsourced inference and has been removed."
    ),
    fission_fraction_note=(
        "Not publicly published for any specific device. Low-yield, "
        "unboosted primaries are often assumed ~1.0 (pure fission, no "
        "thermonuclear stage) -- but that is an ASSUMPTION, not a citation, "
        "and drives the total activity linearly. PLACEHOLDER until sourced."
    ),
    footprint_target_note=(
        "Still NO downwind-distance, contour-area, or crosswind-width number "
        "-- the actual gap this field exists to flag. One adjacent real "
        "number was found, though: the sourced table reports 'I-131 venting "
        "detected, 270 kCi (10,000 TBq)' released off-site. That's a "
        "genuine measured quantity from the event, not a guess -- but it's "
        "total iodine-131 activity release, a different physical quantity "
        "from an H+1 gamma dose-rate contour (this model's output), and "
        "converting one to the other would need fractionation/timing "
        "assumptions this project isn't prepared to invent (see "
        "sizedist.F_VOLATILE_PLACEHOLDER for the same category of gap). "
        "Left here as a lead, not used as a target. DNA 1251-1-EX "
        "(Compilation of Local Fallout Data from Test Detonations "
        "1945-1962) remains the primary source most likely to have an "
        "actual contour; not accessed in this pass."
    ),
    citation=(
        "Wikipedia, 'Operation Sunbeam' (retrieved 2026-07-10), shot table "
        "citing DOE/NV-209 Rev 15; Norris & Cochran, NWD 94-1 (NRDC, 1994); "
        "Hansen, 'The Swords of Armageddon' Vol. 8 (1995); Sublette, "
        "Nuclear Weapons Archive. DNA 6027F, Operation Dominic II, Shots "
        "Little Feller II, Johnie Boy, Small Boy (DTIC ADA128367) was "
        "identified as the primary shot report but rate-limited during "
        "automated fetch in both research passes -- still not "
        "independently read. DOE/NV-209 itself (nnss.gov) still blocks "
        "automated fetch (WAF challenge)."
    ),
)


@dataclass
class HarnessResult:
    case_name: str
    hotline_bearing_deg: float | None
    downwind_reach_miles: float
    fraction_aloft: float
    tier1: tier1.Tier1Result


def _hotline_bearing_deg(result: tier1.Tier1Result) -> float | None:
    """Compass bearing from ground zero to the peak-dose cell -- the plume's
    dominant direction, for eyeballing against a published figure's plume
    axis. None if the grid carries no meaningful signal."""
    if result.dose_rate_h1.max() <= 0:
        return None
    j = np.unravel_index(np.argmax(result.dose_rate_h1), result.dose_rate_h1.shape)
    x, y = result.x_miles[j[1]], result.y_miles[j[0]]
    if x == 0 and y == 0:
        return None
    return float(np.degrees(np.arctan2(x, y)) % 360.0)


def run_case(
    case: ReferenceCase,
    *,
    heights_m: np.ndarray,
    wind_u_ms: np.ndarray,
    wind_v_ms: np.ndarray,
    fission_fraction: float,
    **tier1_kwargs,
) -> HarnessResult:
    """Run Tier-1 for a `ReferenceCase` against a caller-supplied wind profile.

    The wind profile and `fission_fraction` are required arguments, not
    defaults, because neither is currently obtainable automatically for a
    historical case (see module docstring) -- forcing the caller to supply
    them (and, implicitly, to have sourced them) rather than silently
    substituting today's weather or a guessed fission fraction.

    Returns structural summary numbers for MANUAL comparison against a
    published figure. This function does not assert anything -- there is no
    sourced target to assert against yet.
    """
    result = tier1.simulate(
        yield_mt=case.yield_kt / 1000.0,
        fission_fraction=fission_fraction,
        heights_m=heights_m,
        wind_u_ms=wind_u_ms,
        wind_v_ms=wind_v_ms,
        **tier1_kwargs,
    )
    return HarnessResult(
        case_name=case.name,
        hotline_bearing_deg=_hotline_bearing_deg(result),
        downwind_reach_miles=float(result.x_miles.max()),
        fraction_aloft=result.fraction_aloft,
        tier1=result,
    )
