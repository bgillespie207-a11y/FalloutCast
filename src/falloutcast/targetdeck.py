"""Expanded CONUS target deck for the "full nuclear exchange" envelope.

This module builds on the small curated installation set in `targets.py` and
adds the two things a national fallout-envelope view actually needs to be
representative:

  1. The three CONUS Minuteman III missile fields, resolved down to their
     individual launch facilities (LFs, the silos) and launch control centers
     (LCCs / missile alert facilities). Each wing really is 150 LF + 15 LCC,
     organized as 3 squadrons x 5 flights x (10 LF + 1 LCC). Silo fields are
     THE dominant fallout source in any real counterforce exchange -- hundreds
     of surface bursts on hardened silos is the canonical high-fallout
     scenario civil-defense fallout maps are built around -- so modeling a
     field as a single point (as `targets.py` does) badly understates both the
     spatial extent and the intensity of the resulting fallout.

  2. A curated set of public high-value targets (HVTs): major population
     centers, key economic/industrial nodes, and government command-and-
     control sites.

============================ HONESTY NOTE (read this) =========================
Each flight's LCC is placed at its REAL documented location, anchored to the
public USAF missile site maps (F.E. Warren "Missile Site Map, Space Command",
and the equivalent public 91 MW/Minot and 341 MW/Malmstrom field maps) via the
named town each flight sits near. Those flight LOCATIONS are real public
geography. What remains APPROXIMATE is the position of each individual launch
facility WITHIN its flight: the source maps are explicitly "not to scale" (and
the Warren map is historical -- it shows the 200-missile / 20-flight era, while
the current wing is 150 LF / 15 flights per GAO 2025), so per-silo coordinates
cannot be digitized from them. The 10 LFs of each flight are therefore
scattered (deterministically, seeded) around the real flight center and stay
geography_mode="synthetic". This project's first rule -- "never invent a
physical constant and present it as sourced" -- is why the individual points
are flagged synthetic rather than dressed up as surveyed coordinates.

For fallout-footprint modeling this is the right level of fidelity: the WSEG-10
footprint of a field is driven by the field's *extent and where the flights
are*, not by meter-accurate silo positions. Faithful here: the count (150 LF +
15 LCC/wing), the flight organization, and now the real per-flight locations.
Approximate: the exact silo placement within each flight. Swap in a sourced
per-LF coordinate set (and set geography_mode="observed") to make this a real
coordinate product.
==============================================================================

Nothing in `targets.py` changes: `load_targets()` still returns the original
10-site set, keeping existing behavior and tests intact. The expanded deck is
opt-in via `load_expanded_targets()`.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .schemas import FieldPolygon, Target, TargetDeckMeta
from .targets import load_targets

# --- versioned dataset metadata ----------------------------------------------
# This is a VERSIONED dataset, not a one-off: silo geography is expected to be
# refined over time (the USAF began a supplemental Sentinel EIS in 2025 for
# facility siting). Bump DATASET_VERSION and VERIFY_DATE when the data changes.
DATASET_VERSION = "2025.8-more-bases"
VERIFY_DATE = "2026-07-13"
# Date of the most recent HVT (population/economic/C2) curation pass. Kept
# SEPARATE from VERIFY_DATE on purpose: the metro-population expansion below was
# reviewed today, but the missileer-verified silo/field geography was NOT
# re-verified, so it keeps its own (earlier) VERIFY_DATE rather than being
# restamped as freshly checked (project rule #1: never claim a verification that
# did not happen).
HVT_VERIFY_DATE = "2026-07-19"

# Provenance. Flight ORGANIZATION and each flight's approximate geographic AREA
# are now anchored to public USAF missile site maps (flights sit at real,
# documented locations near named towns). What is STILL approximate: the
# position of each individual launch facility WITHIN its flight -- the source
# maps are explicitly "not to scale" (and the Warren map is historical,
# 200-missile / 20-flight era), so per-silo coordinates cannot be digitized
# from them. Those points remain geography_mode="synthetic".
_STRUCTURE_SOURCE = (
    "Flight organization + approximate flight locations from PUBLIC USAF "
    "missile site maps (F.E. Warren 'Missile Site Map, Space Command'; "
    "equivalent public 91 MW/Minot and 341 MW/Malmstrom field maps). Those maps "
    "are NOT TO SCALE and partly historical. Flight CENTERS are anchored to the "
    "documented flight areas / named towns on those maps; INDIVIDUAL launch-"
    "facility positions within each flight are scattered around the center and "
    "are NOT surveyed coordinates. Structure is the CURRENT force: 15 flights / "
    "150 LF + 15 LCC per wing (450 silos total, per GAO 2025) -- the Warren and "
    "Malmstrom site maps show the historical 20-flight/200-missile field, which "
    "is NOT reproduced here. Flight centers are anchored to the maps to within "
    "~5-7 mi (per former-missileer guidance that the maps are ~90% accurate). "
    "90 MW flights Alpha and Echo were corrected/verified by a former 90 MW 13N "
    "missileer (2026); the other flight letters are best-effort map readings, "
    "not individually verified."
)
_STRUCTURE_PUB_DATE = "public USAF site maps (historical/undated); count GAO 2025"
# Flight-scale positional uncertainty: each point sits within its real flight
# area (~10-20 km across) but its exact spot is approximate.
_SYNTHETIC_ACCURACY_M = 15000.0

# --- Minuteman III wing footprints (public, documented) ----------------------
# Each footprint is an approximate geographic bounding box of the wing's
# dispersed launch facilities, drawn from public descriptions of where each
# missile field lies. These are field EXTENTS, not silo coordinates.


# Flight anchors read from the public USAF missile site maps. Each entry is
# (flight_letter, lat, lon) placed at the flight's real documented area (near
# the named town). These are APPROXIMATE (maps are not-to-scale); the letters
# follow the current 15-flight structure, not the historical 20-flight Warren
# map. Coordinates are ordinary public town/area geography.
FlightAnchor = tuple[str, float, float]


@dataclass(frozen=True)
class Wing:
    name: str            # short wing label used in target names
    base: str            # host base
    seed: int
    flights: tuple[FlightAnchor, ...]   # 15 map-anchored flight centers
    lon_min: float       # footprint bbox (encompasses anchors + LF scatter)
    lon_max: float
    lat_min: float
    lat_max: float


# 90th MW -- F.E. Warren AFB: SE Wyoming + W Nebraska panhandle + NE Colorado.
# Alpha and Echo positions corrected/verified by a former 90 MW 13N missileer
# (2026): Alpha sits just north of I-80 just WEST of Pine Bluffs; Echo just EAST
# of Pine Bluffs across the Nebraska line. Other flight letters are approximate
# readings of the public site map, not individually verified.
_WARREN_FLIGHTS: tuple[FlightAnchor, ...] = (
    ("A", 41.21, -104.15),  # NW of Pine Bluffs, N of I-80 (13N-verified)
    ("B", 41.05, -104.35),  # Burns / Carpenter WY
    ("C", 41.42, -104.13),  # Albin WY
    ("D", 41.72, -104.58),  # Chugwater WY (N)
    ("E", 41.20, -103.97),  # E of Pine Bluffs across the NE line (13N-verified)
    ("F", 41.56, -104.12),  # Hawk Springs / Yoder WY
    ("G", 41.25, -103.68),  # Kimball NE
    ("H", 41.16, -103.30),  # Potter NE
    ("I", 41.14, -102.98),  # Sidney NE
    ("J", 41.15, -102.64),  # Lodgepole NE
    ("K", 41.50, -103.36),  # Gurley / Dalton NE
    ("L", 41.56, -103.74),  # Harrisburg NE
    ("M", 41.66, -103.10),  # Bridgeport NE
    ("N", 40.62, -103.22),  # Sterling CO
    ("O", 40.66, -103.86),  # New Raymer / Keota CO
)
WARREN = Wing("90 MW", "F.E. Warren AFB", 9001, _WARREN_FLIGHTS, -104.95, -102.35, 40.40, 42.20)

# 341st MW -- Malmstrom AFB: around Great Falls MT, NW lobe + E toward Lewistown.
_MALMSTROM_FLIGHTS: tuple[FlightAnchor, ...] = (
    ("A", 48.30, -111.80),  # Shelby / Ledger MT
    ("B", 48.10, -111.95),  # Conrad MT
    ("C", 47.88, -112.10),  # Brady / Choteau MT
    ("D", 47.62, -111.99),  # Fairfield MT
    ("E", 47.50, -111.90),  # Simms / Sun River MT
    ("F", 47.38, -110.93),  # Belt MT
    ("G", 47.27, -110.73),  # Raynesford MT
    ("H", 47.55, -110.55),  # Geyser MT
    ("I", 47.15, -110.22),  # Stanford MT
    ("J", 47.32, -109.95),  # Denton MT
    ("K", 47.58, -110.26),  # Geraldine MT
    ("L", 47.06, -109.43),  # Lewistown MT
    ("M", 47.56, -109.38),  # Winifred MT
    ("N", 46.99, -109.87),  # Hobson / Moore MT
    ("O", 46.68, -109.75),  # Judith Gap MT
)
MALMSTROM = Wing("341 MW", "Malmstrom AFB", 9002, _MALMSTROM_FLIGHTS, -112.45, -108.60, 46.35, 48.60)

# 91st MW -- Minot AFB: broad ring around Minot ND.
_MINOT_FLIGHTS: tuple[FlightAnchor, ...] = (
    ("A", 48.67, -102.08),  # Kenmare ND
    ("B", 48.56, -102.55),  # Powers Lake / Ross ND
    ("C", 48.32, -102.39),  # Stanley ND
    ("D", 48.31, -101.74),  # Berthold ND
    ("E", 48.44, -101.71),  # Carpio ND
    ("F", 48.77, -101.52),  # Mohall ND
    ("G", 48.90, -101.63),  # Sherwood ND
    ("H", 48.52, -101.22),  # Glenburn ND
    ("I", 48.38, -100.88),  # Deering / Granville ND
    ("J", 48.35, -100.45),  # Towner ND
    ("K", 48.06, -100.93),  # Velva ND
    ("L", 47.92, -100.42),  # Drake ND
    ("M", 47.85, -101.30),  # Max ND
    ("N", 47.94, -101.70),  # Ryder / Makoti ND
    ("O", 47.66, -101.42),  # Garrison ND
)
MINOT = Wing("91 MW", "Minot AFB", 9003, _MINOT_FLIGHTS, -102.85, -100.20, 47.45, 49.05)

WINGS = (WARREN, MALMSTROM, MINOT)

# Real Minuteman III wing structure (current force).
SQUADRONS_PER_WING = 3
FLIGHTS_PER_SQUADRON = 5
LF_PER_FLIGHT = 10
FLIGHTS_PER_WING = SQUADRONS_PER_WING * FLIGHTS_PER_SQUADRON  # 15
LF_PER_WING = FLIGHTS_PER_WING * LF_PER_FLIGHT                # 150
LCC_PER_WING = FLIGHTS_PER_WING                              # 15

# A flight's LFs are dispersed over a real area (an LCC controls 10 LFs spread
# out so no single weapon takes out the flight). Scatter radius, in degrees, of
# LFs about their (now map-anchored) flight center -- ~10-15 km, approximate.
_FLIGHT_SPREAD_DEG = 0.14


def generate_wing(wing: Wing) -> list[Target]:
    """150 launch facilities + 15 launch control centers for one wing.

    Each flight's LCC is placed at its map-anchored real location (see the
    per-wing FlightAnchor tables, from public USAF site maps); its 10 LFs are
    scattered around that center. Flight LOCATIONS are documented/real; the
    individual LF positions within a flight are approximate (deterministic per
    seed), NOT surveyed coordinates -- see the module provenance note.
    """
    rng = random.Random(wing.seed)
    wing_slug = wing.name.replace(" ", "")  # e.g. "90MW"

    def _synthetic(**kw) -> Target:
        # shared provenance for every synthetic field point.
        return Target(
            wing=wing.name,
            accuracy_m=_SYNTHETIC_ACCURACY_M,
            confidence="low",
            geography_mode="synthetic",
            source=_STRUCTURE_SOURCE,
            pub_date=_STRUCTURE_PUB_DATE,
            verify_date=VERIFY_DATE,
            status="documented active wing; individual facility status not asserted",
            **kw,
        )

    out: list[Target] = []
    for f_idx, (flight_letter, clat, clon) in enumerate(wing.flights, start=1):
        squadron = (f_idx - 1) // FLIGHTS_PER_SQUADRON + 1
        # One LCC (missile alert facility) at the map-anchored flight center.
        out.append(
            _synthetic(
                id=f"{wing_slug}-{flight_letter}-LCC",
                name=f"{wing.name} {flight_letter}-01 LCC",
                lat=round(clat, 4),
                lon=round(clon, 4),
                category="icbm_lcc",
                site_type="launch_control_center",
                designator=f"{flight_letter}-01",
                note=f"{wing.base} flight {flight_letter} LCC (map-anchored; position approximate)",
            )
        )
        # Ten LFs scattered around the flight center.
        for lf in range(1, LF_PER_FLIGHT + 1):
            lon = clon + rng.uniform(-_FLIGHT_SPREAD_DEG, _FLIGHT_SPREAD_DEG)
            lat = clat + rng.uniform(-_FLIGHT_SPREAD_DEG, _FLIGHT_SPREAD_DEG)
            # keep it inside the wing footprint
            lon = min(max(lon, wing.lon_min), wing.lon_max)
            lat = min(max(lat, wing.lat_min), wing.lat_max)
            out.append(
                _synthetic(
                    id=f"{wing_slug}-{flight_letter}-{lf:02d}",
                    name=f"{wing.name} {flight_letter}-{lf:02d}",
                    lat=round(lat, 4),
                    lon=round(lon, 4),
                    category="icbm_lf",
                    site_type="launch_facility",
                    designator=f"{flight_letter}-{lf:02d}",
                    note=f"squadron {squadron}, flight {flight_letter} (SYNTHETIC silo position)",
                )
            )
    return out


def generate_all_fields() -> list[Target]:
    out: list[Target] = []
    for wing in WINGS:
        out.extend(generate_wing(wing))
    return out


# --- High-value targets (public) ---------------------------------------------
# Major population centers, economic/industrial nodes (incl. critical
# infrastructure like the largest dams), government C2, the major Hawaii /
# Alaska military installations, and strategically significant / large CONUS
# military bases (air, ground, naval, command). City coordinates are ordinary
# public geography; the government/industrial/military sites are publicly
# documented locations. Categories drive the frontend styling/legend and the
# per-class scenario yield.

# (name, lon, lat, category, note)
#
# POPULATION CENTERS -- selection basis (was a subtle bug worth stating):
# these are the ~50 most populous US METROPOLITAN areas (Census MSA), NOT the
# top cities by municipal ("city-proper") population. City-proper population is
# an artifact of where municipal boundaries were drawn (it inflates cities like
# Jacksonville/San Jose and hides large metros like Cleveland, Milwaukee, or
# Raleigh whose population sits mostly in suburbs), so it is the wrong proxy for
# a population-center fallout source. Coordinates are approximate metro-anchor
# city centers (ordinary public geography). The Washington, DC metro (Census #6)
# is represented by the national-C2 command node below, not duplicated here.
# This is an illustrative, curated set for fallout modeling -- NOT a claim that
# these specific cities are targeted. Tail membership (~#45-50) varies by
# Census vintage.
_HVT: list[tuple[str, float, float, str, str]] = [
    ("New York City", -74.006, 40.713, "city_population", "largest US metro"),
    ("Los Angeles", -118.244, 34.052, "city_population", ""),
    ("Chicago", -87.630, 41.878, "city_population", ""),
    ("Dallas", -96.797, 32.777, "city_population", ""),
    ("Houston", -95.369, 29.760, "city_population", "port + petrochemical"),
    ("Philadelphia", -75.165, 39.953, "city_population", ""),
    ("Atlanta", -84.388, 33.749, "city_population", ""),
    ("Miami", -80.192, 25.762, "city_population", ""),
    ("Phoenix", -112.074, 33.448, "city_population", ""),
    ("Boston", -71.058, 42.360, "city_population", ""),
    ("Riverside–San Bernardino", -117.396, 33.953, "city_population", "Inland Empire metro"),
    ("San Francisco", -122.419, 37.775, "city_population", ""),
    ("Detroit", -83.046, 42.331, "city_population", ""),
    ("Seattle", -122.332, 47.606, "city_population", ""),
    ("Minneapolis", -93.265, 44.978, "city_population", ""),
    ("Tampa", -82.457, 27.951, "city_population", ""),
    ("San Diego", -117.161, 32.716, "city_population", "major naval complex"),
    ("Denver", -104.991, 39.739, "city_population", ""),
    ("Baltimore", -76.612, 39.290, "city_population", ""),
    ("Orlando", -81.379, 28.538, "city_population", ""),
    ("Charlotte", -80.843, 35.227, "city_population", ""),
    ("St. Louis", -90.199, 38.627, "city_population", ""),
    ("San Antonio", -98.494, 29.424, "city_population", ""),
    ("Portland", -122.676, 45.523, "city_population", ""),
    ("Austin", -97.743, 30.267, "city_population", ""),
    ("Pittsburgh", -79.996, 40.441, "city_population", ""),
    ("Sacramento", -121.494, 38.582, "city_population", ""),
    ("Las Vegas", -115.139, 36.170, "city_population", ""),
    ("Cincinnati", -84.512, 39.103, "city_population", ""),
    ("Kansas City", -94.579, 39.100, "city_population", ""),
    ("Columbus", -82.999, 39.961, "city_population", ""),
    ("Indianapolis", -86.158, 39.768, "city_population", ""),
    ("Cleveland", -81.694, 41.499, "city_population", ""),
    ("San Jose", -121.887, 37.339, "city_population", ""),
    ("Nashville", -86.784, 36.163, "city_population", ""),
    ("Virginia Beach–Norfolk", -76.285, 36.851, "city_population",
     "major naval complex (Naval Station Norfolk)"),
    ("Jacksonville", -81.656, 30.332, "city_population", ""),
    ("Milwaukee", -87.906, 43.039, "city_population", ""),
    ("Providence", -71.413, 41.824, "city_population", ""),
    ("Oklahoma City", -97.517, 35.467, "city_population", ""),
    ("Raleigh", -78.638, 35.780, "city_population", ""),
    ("Memphis", -90.049, 35.149, "city_population", ""),
    ("Richmond", -77.436, 37.541, "city_population", ""),
    ("Louisville", -85.759, 38.253, "city_population", ""),
    ("New Orleans", -90.071, 29.951, "city_population", ""),
    ("Salt Lake City", -111.891, 40.761, "city_population", ""),
    ("Hartford", -72.685, 41.764, "city_population", ""),
    ("Buffalo", -78.878, 42.886, "city_population", ""),
    ("Birmingham", -86.802, 33.521, "city_population", ""),
    # Government command & control
    ("Washington, D.C. (national C2)", -77.037, 38.907, "command",
     "national command authority / Pentagon"),
    ("Cheyenne Mountain / Peterson SFB (NORAD)", -104.848, 38.744, "command",
     "aerospace warning"),
    ("Raven Rock (Site R)", -77.375, 39.734, "command", "alternate military C2"),
    ("Mount Weather", -77.888, 39.062, "command", "continuity-of-government site"),
    # Economic / industrial nodes
    ("Port of Los Angeles / Long Beach", -118.216, 33.740, "industry",
     "largest US container port complex"),
    ("Port of NY/NJ", -74.148, 40.667, "industry", "major container port"),
    ("Houston Ship Channel refineries", -95.100, 29.720, "industry",
     "Gulf Coast refining"),
    ("Port Arthur / Beaumont refineries", -93.940, 29.885, "industry",
     "Gulf Coast refining"),
    ("Baton Rouge petrochemical corridor", -91.187, 30.451, "industry", ""),
    ("Silicon Valley (tech industry)", -122.083, 37.386, "industry", ""),
    # Critical infrastructure -- major hydroelectric / water. Illustrative, not
    # exhaustive: these are the two iconic large US dams (public geography).
    ("Hoover Dam", -114.737, 36.016, "industry",
     "hydroelectric + Colorado River water (Lake Mead)"),
    ("Grand Coulee Dam", -118.982, 47.957, "industry",
     "largest US hydroelectric power station"),

    # --- Non-CONUS strategic sites: Hawaii & Alaska --------------------------
    # Publicly documented major military installations outside the CONUS box.
    # Coordinates are ordinary public geography (installation centroids). The
    # envelope grid was widened to cover these (see grid.US_* bounds) so they
    # produce real fallout plumes, not bare dots. Illustrative/incomplete.
    ("Joint Base Pearl Harbor-Hickam", -157.950, 21.350, "naval_base",
     "US Pacific Fleet HQ; Hickam airfield; INDOPACOM (Camp Smith) adjacent (HI)"),
    ("Joint Base Elmendorf-Richardson", -149.800, 61.250, "air_base",
     "11th Air Force / Alaskan NORAD Region (ALCOM); F-22s (Anchorage, AK)"),
    ("Eielson AFB", -147.100, 64.670, "air_base",
     "F-35 + aerial-refueling hub; Pacific/Arctic operations (AK)"),
    ("Fort Greely (GMD)", -145.740, 63.950, "missile_defense",
     "Ground-based Midcourse Defense interceptor field -- homeland missile defense (AK)"),
    ("Clear Space Force Station", -149.190, 64.300, "missile_defense",
     "early-warning radar (BMEWS / Long Range Discrimination Radar) (AK)"),

    # --- Major CONUS military installations ----------------------------------
    # Strategically significant and/or large-population (~10k+ personnel) bases
    # that the earlier deck missed. Publicly documented installations; the
    # coordinates are ordinary public geography (installation centroids) and the
    # notes describe the base's public role -- no troop counts are asserted as
    # sourced data. Counterforce/military class in the scenario (illustrative).
    # Curated and incomplete, like the rest of the deck.
    #
    # Air Force / Space
    ("Wright-Patterson AFB", -84.048, 39.813, "air_base",
     "Air Force Materiel Command HQ; Nat'l Air & Space Intelligence Center (Dayton, OH)"),
    ("Hill AFB", -111.973, 41.124, "air_base",
     "ICBM (Minuteman III) sustainment; F-35 (Ogden, UT)"),
    ("Tinker AFB", -97.386, 35.417, "air_base",
     "major logistics depot; E-3 AWACS / E-6 airborne command post (Oklahoma City, OK)"),
    ("Vandenberg SFB", -120.573, 34.742, "air_base",
     "ICBM flight testing + Western space launch range (CA)"),
    ("Ellsworth AFB", -103.104, 44.145, "bomber_base",
     "28th Bomb Wing, B-1 bombers (Rapid City, SD)"),
    ("Dyess AFB", -99.854, 32.421, "bomber_base",
     "7th Bomb Wing, B-1 bombers (Abilene, TX)"),
    # Army / Marine ground-force posts
    ("Fort Liberty (Fort Bragg)", -79.006, 35.139, "army_base",
     "XVIII Airborne Corps, 82nd Airborne, Army special operations (Fayetteville, NC)"),
    ("Fort Cavazos (Fort Hood)", -97.775, 31.135, "army_base",
     "III Armored Corps, 1st Cavalry Division (Killeen, TX)"),
    ("Fort Campbell", -87.462, 36.668, "army_base",
     "101st Airborne Division (Air Assault) (KY/TN)"),
    ("Joint Base Lewis-McChord", -122.581, 47.086, "army_base",
     "I Corps + McChord airlift (Tacoma, WA)"),
    ("Fort Bliss", -106.421, 31.813, "army_base",
     "1st Armored Division; air-defense center (El Paso, TX)"),
    ("Fort Moore (Fort Benning)", -84.952, 32.353, "army_base",
     "Infantry & Armor center (Columbus, GA)"),
    ("Fort Carson", -104.788, 38.738, "army_base",
     "4th Infantry Division (Colorado Springs, CO)"),
    ("MCB Camp Lejeune", -77.351, 34.601, "army_base",
     "Marine Corps -- II MEF ground forces (Jacksonville, NC)"),
    ("MCB Camp Pendleton", -117.400, 33.350, "army_base",
     "Marine Corps -- I MEF ground forces (Oceanside, CA)"),
    # Navy
    ("Naval Submarine Base New London", -72.088, 41.398, "naval_base",
     "primary East Coast attack-submarine base; Submarine Force HQ (Groton, CT)"),
    ("Portsmouth Naval Shipyard", -70.739, 43.079, "naval_base",
     "nuclear-submarine overhaul/refueling shipyard (Kittery, ME)"),
    ("Naval Base San Diego", -117.130, 32.680, "naval_base",
     "major Pacific Fleet surface-ship homeport (San Diego, CA)"),
    # Command / intelligence
    ("Fort Meade", -76.741, 39.108, "command",
     "National Security Agency / US Cyber Command (MD)"),

    # --- Additional major installations (second pass) ------------------------
    # Combatant-command HQs and further large posts. Same standard: public
    # geography, public role in the note, no asserted troop counts.
    #
    # Combatant-command headquarters (strategic C2)
    ("MacDill AFB", -82.521, 27.849, "command",
     "US Central Command + US Special Operations Command HQ (Tampa, FL)"),
    ("Scott AFB", -89.835, 38.545, "command",
     "US Transportation Command + Air Mobility Command HQ (IL)"),
    ("Fort Eisenhower (Fort Gordon)", -82.150, 33.420, "command",
     "US Army Cyber Command; NSA Georgia (Augusta, GA)"),
    # Army posts (large; mostly new coverage)
    ("Fort Stewart", -81.609, 31.869, "army_base",
     "3rd Infantry Division (Hinesville, GA)"),
    ("Fort Drum", -75.766, 44.051, "army_base",
     "10th Mountain Division (Watertown, NY)"),
    ("Fort Riley", -96.809, 39.083, "army_base",
     "1st Infantry Division (Junction City, KS)"),
    ("Fort Sill", -98.402, 34.661, "army_base",
     "Field Artillery & air-defense center (Lawton, OK)"),
    ("Fort Leonard Wood", -92.132, 37.748, "army_base",
     "Army engineer/MP/chemical training center (MO)"),
    ("Fort Jackson", -80.850, 34.040, "army_base",
     "largest Army basic-training center (Columbia, SC)"),
    ("Fort Johnson (Fort Polk)", -93.180, 31.050, "army_base",
     "Joint Readiness Training Center (Leesville, LA)"),
    # Air Force (large; new coverage)
    ("Eglin AFB", -86.550, 30.460, "air_base",
     "armament development & test; large training range (FL panhandle)"),
    ("Davis-Monthan AFB", -110.883, 32.166, "air_base",
     "A-10s; aircraft boneyard (AMARG) (Tucson, AZ)"),
    ("Joint Base San Antonio", -98.620, 29.380, "air_base",
     "largest joint base by population; basic military training; Army medical (TX)"),
]


def _slug(name: str) -> str:
    """Stable id slug from an HVT name (lowercase, alnum + hyphens)."""
    out = []
    prev_dash = False
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "hvt-" + "".join(out).strip("-")


def high_value_targets() -> list[Target]:
    # City centers etc. are ordinary public geography (observed, ~1 km accuracy).
    return [
        Target(
            id=_slug(n), name=n, lat=lat, lon=lon, category=cat, note=note,
            site_type=cat, accuracy_m=1000.0, confidence="high",
            geography_mode="observed", source="public geography (city/site centroid)",
            pub_date="n/a", verify_date=HVT_VERIFY_DATE,
            status="curated, incomplete selection",
        )
        for (n, lon, lat, cat, note) in _HVT
    ]


# NOTE: per-class INCOMING yields are an attacker-scenario assumption, not a
# target attribute -- they live in `scenario.py` (see its docstring for why),
# not here. This module is target metadata only.


# --- Assembly ----------------------------------------------------------------
# The three single `icbm_field` points in targets.py (Warren/Malmstrom/Minot)
# are superseded by the generated fields, so they're dropped from the expanded
# deck to avoid double-counting the same three ground zeros.
_SUPERSEDED = "icbm_field"


def load_expanded_targets() -> list[Target]:
    """Full deck: base installations + resolved missile fields + HVTs.

    = (the 10 curated sites minus the 3 single-point ICBM fields)
      + 495 generated LF/LCC points across the 3 wings
      + curated public high-value targets.
    """
    installations = [t for t in load_targets() if t.category != _SUPERSEDED]
    return installations + generate_all_fields() + high_value_targets()


def verified_targets() -> list[Target]:
    """Targets whose geography is NOT synthetic (observed/field_polygon only).
    The synthetic silo/LCC points are excluded -- there are no verified precise
    facility coordinates to stand behind."""
    return [t for t in load_expanded_targets() if t.geography_mode != "synthetic"]


# --- field polygons: the verifiable geography --------------------------------
# When individual facility coordinates can't be sourced to precision, the
# HONEST geography is the documented field FOOTPRINT. Each wing's footprint is
# rendered as a rectangle from its documented bounding box -- the extent is
# public knowledge even though the ~165 points inside it are synthetic.

def field_polygon(wing: Wing) -> FieldPolygon:
    ring = [
        [wing.lon_min, wing.lat_min],
        [wing.lon_max, wing.lat_min],
        [wing.lon_max, wing.lat_max],
        [wing.lon_min, wing.lat_max],
        [wing.lon_min, wing.lat_min],  # closed
    ]
    return FieldPolygon(
        id=f"field-{wing.name.replace(' ', '')}",
        wing=wing.name,
        base=wing.base,
        lf_count=LF_PER_WING,
        lcc_count=LCC_PER_WING,
        confidence="medium",  # footprint documented; exact boundary approximate
        source=_STRUCTURE_SOURCE,
        pub_date=_STRUCTURE_PUB_DATE,
        verify_date=VERIFY_DATE,
        polygon=ring,
    )


def field_polygons() -> list[FieldPolygon]:
    return [field_polygon(w) for w in WINGS]


def dataset_content_hash() -> str:
    """Deterministic sha256 over the target set's identity + geography, so a
    dataset change is detectable. Rounds coords to the stored precision."""
    parts = []
    for t in load_expanded_targets():
        parts.append(f"{t.id}|{round(t.lat, 4)}|{round(t.lon, 4)}|{t.category}|{t.geography_mode}")
    blob = "\n".join(sorted(parts)).encode()
    return hashlib.sha256(blob).hexdigest()


def deck_meta() -> TargetDeckMeta:
    """Versioned dataset metadata + field polygons for provenance/export."""
    targets = load_expanded_targets()
    n_synth = sum(1 for t in targets if t.geography_mode == "synthetic")
    return TargetDeckMeta(
        version=DATASET_VERSION,
        content_hash=dataset_content_hash(),
        generated=HVT_VERIFY_DATE,
        n_targets=len(targets),
        n_synthetic=n_synth,
        fields=field_polygons(),
        notes=[
            "Silo/LCC positions are SYNTHETIC (generated within documented field "
            "footprints); their accuracy_m is field-scale and confidence is low. "
            "The verifiable geography is the field polygons, not the points.",
            "Versioned dataset: expected to be refined (USAF supplemental Sentinel "
            "EIS, 2025). Bump DATASET_VERSION/VERIFY_DATE when data changes.",
        ],
    )
