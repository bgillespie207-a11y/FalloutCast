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

2. NO MACHINE-USABLE TARGET FOOTPRINT -- started, still partial. A fourth
   research pass fetched the actual scanned page IMAGES for Figures 329-332
   from archive.org (not just the OCR text -- the plates are graphics, so
   OCR text alone couldn't carry them; see `_fetch_scan_page` methodology
   note below) and hand-traced three points by eye against the figures' own
   printed mile gridlines: `SMALL_BOY_DIGITIZED_POINTS`. This is a real
   first-pass digitization, not prose -- but it is HAND-TRACED FROM A LOW-
   RESOLUTION 1970s PHOTOCOPY SCAN, so treat the numbers as approximate
   (see each point's `note` for what's solid vs. uncertain). The scan
   resolution was good enough to trace CONTOUR LINE PATHS against the sharp
   printed gridlines with reasonable confidence, but NOT good enough to
   reliably read every small typewritten R/hr label where multiple contours
   cluster close together near GZ -- so only the more isolated, legible
   labels/points were digitized; the full contour family (0.01 through 1000
   R/hr) is visible in the source but not fully extracted. A genuinely
   striking result: three independently-traced points (close-in Fig. 331
   "0.01 R/hr" line, the Fig. 332 "2 R/hr" plume's far end, and a separate
   secondary deposition patch far from the main plume) all land at compass
   bearings 41-52 degrees from GZ -- consistent with EACH OTHER, and with
   the same report's own prose ("as far as western Nebraska," bearing ~58
   deg from GZ) and this project's own Tier-1 run against the real wind
   (bearing ~67 deg, see `scripts/validate_footprint.py`). That agreement is
   a real, unforced signal, not cherry-picked -- but note gap 1 (burst-height
   mismatch) and the hand-digitization uncertainty here mean this still
   isn't a tight quantitative validation, just a much better structural
   comparison than prose alone.

3. NO HISTORICAL WIND PROFILE -- CLOSED. The same DNA 1251-1-EX entry
   includes Table 109, "NEVADA WIND DATA FOR OPERATION SUNBEAM - SMALL BOY":
   a real balloon/tower sounding at Frenchman's Flat, NTS, at H+5 min,
   H+15 min, and H+70 min post-burst, altitude 3,078-20,000 ft MSL. This is
   digitized below as `SMALL_BOY_WIND_H5MIN_*` / `small_boy_wind_h5min()`.
   Open-Meteo's own historical ERA5 archive was a dead end for this (covers
   1962 but doesn't expose pressure-level wind fields, confirmed live) --
   this real sounding came from the primary test report instead.

Given gaps 1 and 2 remain, `run_case` is still a tool for manual/structural
comparison, not something wired into pytest's assert-based tests -- there is
still no sourced numeric contour to assert equality/tolerance against, and
the burst-height mismatch (gap 1) means even a perfect wind and a digitized
target contour wouldn't make this an apples-to-apples validation. See
`tests/test_footprint_validation_harness.py` for what IS tested: the harness
plumbing runs and returns sane, finite, structurally-bounded output (a
code-correctness check, not a physics validation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..physics import tier1

_MPH_TO_MS = 0.44704
_FT_TO_M = 0.3048


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
        "Read DNA 1251-1-EX Vol. I directly (DTIC ADA079309, via archive.org "
        "OCR text; the entry starts under 'OPERATION SUNBEAM - Small Boy', "
        "p.~569 of the scanned volume). A first-pass digitization of three "
        "points from the actual figures now exists -- see "
        "SMALL_BOY_DIGITIZED_POINTS below -- hand-traced from the scanned "
        "plates (329: close-in GZ contours; 330: H+1 hour contours to 50,000 "
        "ft downwind; 331: off-site pattern to 29 mi; 332: off-site pattern "
        "to 300 mi; 333: cloud path to western Nebraska). Still NOT a full "
        "digitized contour polygon -- only 3 discrete points with "
        "hand-estimated coordinates, not the whole R/hr-vs-distance family. "
        "Separately, the report states in prose that fallout 'started "
        "arriving at 250 to 400 "
        "miles downwind... late... D+1 day reaching a peak at D+2 days,' "
        "tracked by ground monitors 'as far as western Nebraska' (NNE-ish of "
        "NTS). Two other real sourced numbers, neither a footprint target "
        "but worth keeping: observed CLOUD TOP HEIGHT 19,000 ft MSL (a "
        "sanity check for this project's own wseg10.cloud_center_height_kft, "
        "which is a different quantity -- center vs top -- so not a direct "
        "equality check), and I-131 venting release of 270 kCi (10,000 TBq) "
        "off-site (a different physical quantity than a gamma dose-rate "
        "contour; would need fractionation/timing assumptions this project "
        "won't invent -- see sizedist.F_VOLATILE_PLACEHOLDER for the same "
        "category of gap)."
    ),
    citation=(
        "PRIMARY SOURCE READ DIRECTLY: DNA 1251-1-EX, 'Compilation of Local "
        "Fallout Data from Test Detonations 1945-1962 Extracted from DASA "
        "1251,' Vol. I -- Continental U.S. Tests (DTIC ADA079309), 'OPERATION "
        "SUNBEAM - Small Boy' entry, via archive.org OCR transcription "
        "(https://archive.org/details/DTIC_ADA079309, retrieved 2026-07-10). "
        "The PDF itself (apps.dtic.mil, dtra.mil) still blocks automated "
        "fetch, but archive.org's plaintext OCR of the same scanned document "
        "was directly readable, including Table 109's numeric wind sounding. "
        "Cross-checked against secondary compilation: Wikipedia, 'Operation "
        "Sunbeam,' shot table citing DOE/NV-209 Rev 15, Norris & Cochran (NWD "
        "94-1, 1994), Hansen ('Swords of Armageddon' Vol. 8, 1995), and "
        "Sublette's Nuclear Weapons Archive -- coordinates and site elevation "
        "agree closely (3,078 ft MSL here vs. 940 m there = 3,084 ft)."
    ),
)


@dataclass(frozen=True)
class DigitizedContourPoint:
    """One hand-digitized point read off a scanned DNA 1251-1-EX contour
    figure. `distance_mi`/`bearing_deg` are DERIVED from hand-traced
    (x_mi, y_mi) coordinates read against the figure's own printed mile
    gridlines (x_mi = "east"-ish, y_mi = "north"-ish per each figure's small
    drawn compass rose -- the rose's exact tilt off vertical was not
    separately measured, so treat bearing as accurate to perhaps +-5-10 deg,
    not survey-grade). `dose_rate_rhr` is None where the line's own
    typewritten label was legible enough to identify roughly which decade
    but not confidently read exactly (see `note`).
    """

    label: str
    x_mi: float
    y_mi: float
    dose_rate_rhr: float | None
    source_figure: str
    note: str

    @property
    def distance_mi(self) -> float:
        return float(np.hypot(self.x_mi, self.y_mi))

    @property
    def bearing_deg(self) -> float:
        return float(np.degrees(np.arctan2(self.x_mi, self.y_mi)) % 360.0)


# Hand-traced from archive.org scan images of DNA 1251-1-EX Vol. I (DTIC
# ADA079309), leaves 0574/0576/0577 (printed pages 570/572/573), fetched via
# archive.org's BookReaderImages.php page-image endpoint (the PDF itself
# still blocks automated fetch; archive.org serves the same scan's
# individual page images without that block). Read 2026-07-10. Each point's
# (x_mi, y_mi) is a by-eye estimate of where a traced contour line crosses
# or terminates, read against the figure's own sharp printed gridlines
# (reliable) -- NOT a claim of survey-grade precision. See
# DigitizedContourPoint's docstring for the bearing-accuracy caveat.
SMALL_BOY_DIGITIZED_POINTS = [
    DigitizedContourPoint(
        label="close-in contour, upper end",
        x_mi=15.0, y_mi=17.3, dose_rate_rhr=0.01,
        source_figure="Fig. 331 (H+1hr, to 29 mi downwind), p.572",
        note=(
            "Traced the outermost (steepest, most isolated) dashed contour "
            "from the GZ cluster to where it exits the plotted area near the "
            "top edge. Labeled '0.01' at both this point and again lower on "
            "the same line near the GZ cluster (contour lines in this figure "
            "are relabeled at multiple points along their length) -- the two "
            "labels agreeing is a small confidence boost, though both "
            "readings come from the same blurry font."
        ),
    ),
    DigitizedContourPoint(
        label="main plume, 2 R/hr contour far end",
        x_mi=170.0, y_mi=150.0, dose_rate_rhr=2.0,
        source_figure="Fig. 332 (H+1hr, to 300 mi downwind), p.573",
        note=(
            "Traced the '2'-labeled contour from the close-in cluster "
            "(where it's one of several nested labeled contours: 100, 20, "
            "10, 4, 2) out to where the source's own dashing indicates "
            "'uncertainty' near the edge of continuous tracking. This is "
            "the most confidently read of the three points -- '2' is an "
            "unambiguous single digit, unlike the decimal labels elsewhere."
        ),
    ),
    DigitizedContourPoint(
        label="secondary deposition patch, approx. center",
        x_mi=265.0, y_mi=210.0, dose_rate_rhr=None,
        source_figure="Fig. 332 (H+1hr, to 300 mi downwind), p.573",
        note=(
            "A DISTINCT, DISCONNECTED contour cluster (separate from the "
            "main plume traced above) appears far downwind, with legible "
            "labels '4', '10', '20' on its nested contours (exact boundary "
            "not fully traced, just an eyeballed center of the cluster). "
            "Real fallout is patchy -- rainout/washout secondary hot spots "
            "disconnected from the main plume are a well documented "
            "phenomenon Tier-1's single smooth Gaussian-puff model cannot "
            "reproduce; this point is here as a real feature of the source "
            "data, not something to expect Tier-1 to match."
        ),
    ),
]
# observed at Frenchman's Flat, NTS -- digitized from DNA 1251-1-EX Vol. I,
# Table 109, "NEVADA WIND DATA FOR OPERATION SUNBEAM - SMALL BOY" (see
# SMALL_BOY_1962.citation). The table also gives H+15min and H+70min
# columns; H+5min is used here as the most altitude-complete of the three
# and closest to burst-time conditions. The original table has no reading
# at 15,000 ft for this column -- that altitude is skipped rather than
# interpolated or invented; tier1.simulate's np.interp handles the sparser
# altitude spacing fine. Direction is meteorological "from" degrees, speed
# in mph, exactly as tabulated in the source (both units given explicitly
# in the table header).
SMALL_BOY_WIND_H5MIN_FT_MSL = np.array(
    [3078, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 14000, 16000, 18000, 20000],
    dtype=float,
)
SMALL_BOY_WIND_H5MIN_DIR_FROM_DEG = np.array(
    [135, 300, 310, 330, 280, 250, 240, 240, 240, 240, 240, 280, 280], dtype=float
)
SMALL_BOY_WIND_H5MIN_SPEED_MPH = np.array(
    [2.3, 1.2, 1.2, 2.3, 2.3, 6.9, 13.8, 18.4, 9.2, 9.2, 9.2, 16.1, 28.8], dtype=float
)


def small_boy_wind_h5min() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Small Boy's real H+5min wind sounding as (heights_m, wind_u_ms, wind_v_ms)
    -- the form `run_case`/`tier1.simulate` expect. See the module-level
    `SMALL_BOY_WIND_H5MIN_*` arrays for the citation and caveats.

    u/v convention matches `weather.openmeteo._dir_to_uv`: meteorological
    "from" direction converted to the (east, north) vector the wind blows
    TOWARD.
    """
    heights_m = SMALL_BOY_WIND_H5MIN_FT_MSL * _FT_TO_M
    speed_ms = SMALL_BOY_WIND_H5MIN_SPEED_MPH * _MPH_TO_MS
    rad = np.deg2rad(SMALL_BOY_WIND_H5MIN_DIR_FROM_DEG)
    u = -speed_ms * np.sin(rad)
    v = -speed_ms * np.cos(rad)
    return heights_m, u, v


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
