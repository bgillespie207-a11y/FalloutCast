"""Historical-test reference cases for Tier-1 footprint validation.

STATUS: scaffolding, not a validation suite. TIER1_SPEC.md test-plan item 7
calls for comparing a Tier-1 footprint against a published DELFIC or HYSPLIT
reference before trusting Tier-1 shapes in the UI. This module is the
research result of trying to assemble one such case, and an honest account
of why it isn't a passing/failing test yet -- per this project's rule against
claiming validation that didn't happen, nothing here is wired into a
numeric assertion.

What blocked a full case (as of this research pass, 2026-07, updated across
five research passes -- see git history on this file for the trail):

1. NO CONFIRMED HOB=0 SURFACE BURST -- narrowed, still not a match.
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

   SMALL_BOY_1962 was the first candidate: a ~3 m (9.8 ft) tower/stand shot,
   confirmed via both the primary source and an independent secondary shot
   table -- close to the ground for a 1.7 kt device, but a confirmed,
   quantified mismatch with HOB=0, not a match (see `height_of_burst_m`,
   `burst_type_note`).

   LITTLE_FELLER_II_1962 (added in a fifth pass) is a materially closer HOB
   match: primary-source-confirmed HEIGHT OF BURST = 3 FT (0.91 m),
   "near-surface, over Nevada soil. Device supported by a cable suspended
   between two posts" -- roughly 3x closer to the ground than Small Boy.
   The tradeoff is severe, and worse than first suspected: its yield is tiny
   (22 tons = 0.022 kt, per Wikipedia's 'Operation Sunbeam' table, not
   independently primary-sourced) -- far enough below WSEG-10's designed
   yield range that `wseg10.cloud_center_height_kft(0.022/1000)` returns a
   NEGATIVE height (~-7.3 kft), not just an inaccurate one. This is the
   empirical curve fit (Hanifen 1980, fit to strategic-scale yields)
   extrapolating nonsensically outside its calibrated range, not a bug in
   this codebase's arithmetic -- but it means Tier-1 CANNOT be meaningfully
   run on this case as-is (see `LITTLE_FELLER_II_1962.footprint_target_note`
   and `tests/test_footprint_validation_harness.py`'s test documenting this
   directly). So: better burst-height match, but currently un-runnable
   through this engine; Small Boy remains the only case Tier-1 can actually
   simulate. Kept here (wind + one digitized point) for whoever extends the
   cloud-height model to tactical yields.

2. NO MACHINE-USABLE TARGET FOOTPRINT -- started, still partial. A fourth
   research pass fetched the actual scanned page IMAGES for Small Boy's
   Figures 329-332 from archive.org (not just the OCR text -- the plates are
   graphics, so OCR text alone couldn't carry them; fetched via
   archive.org's BookReaderImages.php page-image endpoint, which serves
   individual scan pages even though the source PDF itself blocks automated
   fetch) and hand-traced three points by eye against the figures' own
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

   The fifth pass digitized one point for LITTLE_FELLER_II_1962 too (its
   Figure 323, the clearest-labeled of its contour plates):
   `LITTLE_FELLER_II_DIGITIZED_POINTS`. Its wind (Table 107) is dominated by
   ~180 deg (from-south) flow through the low-to-mid levels, which blows
   TOWARD ~north -- roughly consistent with the digitized point's bearing
   (~20 deg), another real, if rougher, internal cross-check.

3. NO HISTORICAL WIND PROFILE -- CLOSED, and doubled. DNA 1251-1-EX includes
   real balloon/tower soundings for BOTH cases: Table 109 (Small Boy,
   Frenchman's Flat, H+5/H+15/H+70 min, altitude 3,078-20,000 ft MSL --
   digitized as `SMALL_BOY_WIND_H5MIN_*` / `small_boy_wind_h5min()`) and
   Table 107 (Little Feller II, forward control point at Area 18, a single
   clean H-hour column, surface to 18,000 ft MSL -- digitized as
   `LITTLE_FELLER_II_WIND_HHOUR_*` / `little_feller_ii_wind_hhour()`).
   Open-Meteo's own historical ERA5 archive was a dead end for this (covers
   1962 but doesn't expose pressure-level wind fields, confirmed live) --
   both real soundings came from the primary test report instead.

Given gaps 1 and 2 remain, `run_case` is still a tool for manual/structural
comparison, not something wired into a sourced-contour equality assertion --
there is still no sourced numeric contour to assert magnitude against, and the
burst-height mismatch (gap 1) means even a perfect wind and a digitized target
contour wouldn't make this an apples-to-apples *magnitude* validation.

What IS validated (directionally): two things now cross-check the plume
DIRECTION against the real Small Boy sounding, in
`tests/test_footprint_validation_harness.py` --
  (a) Tier-1's advected hotline bearing lands in the same band as the
      independently hand-traced digitized points (a data cross-check), and
  (b) Tier-0 (analytic; plume axis = layer-mean effective-wind bearing, via
      `small_boy_effective_wind()`) and Tier-1 (multi-layer advection) agree
      on that direction to within a tight tolerance -- a cross-ENGINE check
      that would catch an advection-direction bug in either, independent of
      the digitized data.
These are genuine (if partial) directional validations against real historical
data, not just plumbing tests. Footprint MAGNITUDE remains unvalidated for the
reasons above. The rest of the harness tests are code-correctness checks (the
plumbing runs and returns finite, structurally-bounded output).
"""

from __future__ import annotations

from dataclasses import dataclass

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

# Real historical wind sounding for Small Boy, H+5 minutes post-burst,
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


def small_boy_effective_wind():
    """Small Boy's real sounding reduced to ONE Tier-0 effective wind (the
    layer-mean over the stabilized-cloud depth, via the same
    `weather.openmeteo.reduce_profile` the live API uses).

    Purpose: a Tier-0/Tier-1 cross-check. Tier-0's analytic dose peaks AT ground
    zero, so its plume axis is definitionally this effective (mean) wind
    bearing; comparing it to Tier-1's advected peak-dose bearing on the SAME
    real wind checks that the two independent engines agree on plume direction
    (see `tests/test_footprint_validation_harness.py`). Small Boy's 1.7 kt yield
    gives a positive WSEG-10 cloud height (unlike Little Feller II's 22 tons),
    so Tier-0 is runnable here. This validates DIRECTION only -- not footprint
    magnitude, which the burst-height/fission-fraction gaps still preclude.
    """
    # Local imports: keep this validation module's top-level dependencies light
    # (numpy + physics.tier1); the weather reduction is only needed for this
    # one Tier-0 cross-check helper.
    from ..physics.wseg10 import cloud_top_height_m
    from ..weather import openmeteo

    profile = openmeteo.WindProfile(
        height_m=SMALL_BOY_WIND_H5MIN_FT_MSL * _FT_TO_M,
        speed_ms=SMALL_BOY_WIND_H5MIN_SPEED_MPH * _MPH_TO_MS,
        direction_deg=SMALL_BOY_WIND_H5MIN_DIR_FROM_DEG,
    )
    cloud_top_m = cloud_top_height_m(SMALL_BOY_1962.yield_kt / 1000.0)
    return openmeteo.reduce_profile(profile, cloud_top_m)


# --- second case: Little Feller II (1962-07-07) -----------------------------
#
# Found in a fifth research pass while reading the same DNA 1251-1-EX volume
# for Small Boy's entry (its text runs immediately before Small Boy's in the
# document). A materially better height-of-burst match than Small Boy (3 ft
# vs. 9.8 ft) -- see the module docstring's gap-1 discussion for the
# yield-range tradeoff this case brings instead.
#
# Site coordinates as printed directly in the DNA 1251-1-EX entry (37 07'
# 09.1611" N, 116 18' 10.3321" W) -- unlike Small Boy's, which needed OCR of
# a garbled arcsecond field, this one read cleanly.
_LITTLE_FELLER_II_LAT = 37.0 + 7 / 60 + 9.1611 / 3600
_LITTLE_FELLER_II_LON = -(116.0 + 18 / 60 + 10.3321 / 3600)

LITTLE_FELLER_II_1962 = ReferenceCase(
    name="Little Feller II",
    date="1962-07-07",
    lat=_LITTLE_FELLER_II_LAT,
    lon=_LITTLE_FELLER_II_LON,
    yield_kt=0.022,
    yield_source=(
        "22 tons per Wikipedia's 'Operation Sunbeam' shot table (same "
        "citation chain as SMALL_BOY_1962.yield_source: DOE/NV-209 Rev 15, "
        "Norris & Cochran NWD 94-1, Hansen 'Swords of Armageddon' Vol. 8). "
        "NOT independently cross-checked against the primary DNA 1251-1-EX "
        "text read for this case (that entry gives burst/site/wind data but "
        "does not restate yield)."
    ),
    height_of_burst_m=0.9144,  # 3 ft, exact conversion
    burst_type_note=(
        "PRIMARY-SOURCE CONFIRMED (read directly, not via secondary table): "
        "DNA 1251-1-EX Vol. I gives 'HEIGHT OF BURST: 3 ft' and 'TYPE OF "
        "BURST AND PLACEMENT: Near-surface, over Nevada soil. Device "
        "supported by a cable suspended between two posts.' This is ~3x "
        "closer to this project's HOB=0 assumption than Small Boy's 3 m "
        "tower -- the best HOB match found across all candidate cases -- "
        "but still not a literal ground-level burst. And the yield (22 "
        "tons) is severely outside WSEG-10's designed range: "
        "wseg10.cloud_center_height_kft(0.022/1000) returns approximately "
        "-7.3 kft -- NEGATIVE, not just inaccurate. Hanifen (1980)'s "
        "empirical cloud-height fit was calibrated to strategic-scale "
        "yields and does not extrapolate sanely down to 22 tons. This is a "
        "property of that curve fit, not an arithmetic bug here. Practical "
        "consequence: Tier-1 CANNOT be meaningfully run on this case with "
        "the current cloud-height source -- see `footprint_target_note` "
        "and the harness test that documents this directly."
    ),
    fission_fraction_note=(
        "Same category of gap as SMALL_BOY_1962: not publicly published. "
        "PLACEHOLDER assumption of 1.0 (pure fission) used here too."
    ),
    footprint_target_note=(
        "PRIMARY SOURCE READ DIRECTLY (DNA 1251-1-EX Vol. I, 'OPERATION "
        "SUNBEAM - Little Feller II' entry, p.557-559 of the scanned "
        "volume): 'The close-in and distant contours of residual radiation "
        "are shown in Figures 322 thru 324. All the contours are "
        "considered reliable.' Figures 322 (to 1,200 ft downwind) and 323 "
        "(to 12,000 ft downwind) are clearly legible scans -- materially "
        "better print quality than Small Boy's figures. One point "
        "digitized so far: `LITTLE_FELLER_II_DIGITIZED_POINTS`. BUT: per "
        "`burst_type_note`, Tier-1 cannot currently be run on this case at "
        "all (negative modeled cloud height at this yield), so there is no "
        "model output to compare this point against today -- it is kept "
        "here as real, sourced data waiting on a small-yield cloud-height "
        "fix, not as a working comparison. Do not treat a run_case() call "
        "on this case as meaningful; it would silently run on a garbage "
        "release altitude rather than failing loudly, which is exactly the "
        "kind of false-confidence output this project's honesty rules "
        "exist to prevent -- flagging it explicitly instead."
    ),
    citation=(
        "PRIMARY SOURCE READ DIRECTLY: DNA 1251-1-EX, Vol. I (DTIC "
        "ADA079309), 'OPERATION SUNBEAM - Little Feller II' entry, via "
        "archive.org page images (BookReaderImages.php endpoint) and OCR "
        "text, retrieved 2026-07-10. Yield cross-referenced from Wikipedia's "
        "'Operation Sunbeam' shot table (see SMALL_BOY_1962.citation for "
        "that table's own reference chain)."
    ),
)


# Real historical wind sounding for Little Feller II, AT H-HOUR (burst time),
# observed at the forward control point, NTS Area 18 -- digitized from DNA
# 1251-1-EX Vol. I, Table 107, "NEVADA WIND DATA FOR OPERATION SUNBEAM -
# LITTLE FELLER II". Unlike Small Boy's table, this one has a single time
# column (H-hour only), so there's no multi-snapshot choice to make. The
# source's first row is labeled "Surface" rather than a numeric altitude;
# that row is taken here as the site elevation (5,129 ft MSL, from this
# case's own SITE ELEVATION field) since "surface" at a specific site is
# that site's own elevation, not sea level.
LITTLE_FELLER_II_WIND_HHOUR_FT_MSL = np.array(
    [5129, 6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14000,
     15000, 16000, 17000, 18000],
    dtype=float,
)
LITTLE_FELLER_II_WIND_HHOUR_DIR_FROM_DEG = np.array(
    [171, 190, 180, 180, 180, 180, 140, 120, 110, 100, 90, 140, 200, 200],
    dtype=float,
)
LITTLE_FELLER_II_WIND_HHOUR_SPEED_MPH = np.array(
    [8.1, 16.1, 19.6, 15.0, 11.5, 11.5, 8.1, 15.0, 21.9, 18.4,
     10.4, 3.5, 8.1, 9.2],
    dtype=float,
)


def little_feller_ii_wind_hhour() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Little Feller II's real H-hour wind sounding as (heights_m,
    wind_u_ms, wind_v_ms). See `LITTLE_FELLER_II_WIND_HHOUR_*` for citation.
    Same u/v convention as `small_boy_wind_h5min`."""
    heights_m = LITTLE_FELLER_II_WIND_HHOUR_FT_MSL * _FT_TO_M
    speed_ms = LITTLE_FELLER_II_WIND_HHOUR_SPEED_MPH * _MPH_TO_MS
    rad = np.deg2rad(LITTLE_FELLER_II_WIND_HHOUR_DIR_FROM_DEG)
    u = -speed_ms * np.sin(rad)
    v = -speed_ms * np.cos(rad)
    return heights_m, u, v


LITTLE_FELLER_II_DIGITIZED_POINTS = [
    DigitizedContourPoint(
        label="outer contour, upper end",
        x_mi=4000.0 / 5280.0, y_mi=10700.0 / 5280.0, dose_rate_rhr=0.01,
        source_figure="Fig. 323 (H+1hr, to 12,000 ft downwind), p.559",
        note=(
            "Traced the outermost clearly-continuous contour line (labeled "
            "'0.01' near this point) from the GZ cluster to where it exits "
            "the plotted area. This figure's print quality is noticeably "
            "better than Small Boy's equivalent-scale figure, so the TRACE "
            "itself carries somewhat more confidence than Small Boy's -- but "
            "there is currently no Tier-1 output to compare it against (see "
            "LITTLE_FELLER_II_1962.footprint_target_note: this case's yield "
            "makes the cloud-height model go negative). Kept as real, "
            "sourced data for future use, not a working comparison today."
        ),
    ),
]


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
