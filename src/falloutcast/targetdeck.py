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
The individual LF/LCC coordinates here are a DETERMINISTIC ILLUSTRATIVE
DISTRIBUTION generated within each wing's documented public field footprint --
NOT surveyed launch-facility coordinates. This project's first rule is "never
invent a physical constant and present it as sourced" (see docs/HANDOFF.md).
Real LF coordinates exist in public arms-control/OSINT sources, but they are
not reproduced here to survey accuracy, and fabricating ~500 precise points
and passing them off as real would violate that rule.

For fallout-footprint modeling this is the right trade anyway: the WSEG-10
footprint of a field is driven by the field's *extent and density*, not by
meter-accurate silo positions. What is faithful here is the count (150 LF + 15
LCC/wing), the organization (flights of 10), the wing's real geographic
bounding footprint, and the rough LF spacing. What is synthetic is the exact
placement within that footprint. The generator is seeded, so the deck is
stable run-to-run. Swap in a sourced LF coordinate set (and drop the seeding)
to make this a real coordinate product.
==============================================================================

Nothing in `targets.py` changes: `load_targets()` still returns the original
10-site set, keeping existing behavior and tests intact. The expanded deck is
opt-in via `load_expanded_targets()`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .schemas import Target
from .targets import load_targets

# --- Minuteman III wing footprints (public, documented) ----------------------
# Each footprint is an approximate geographic bounding box of the wing's
# dispersed launch facilities, drawn from public descriptions of where each
# missile field lies. These are field EXTENTS, not silo coordinates.


@dataclass(frozen=True)
class Wing:
    name: str            # short wing label used in target names
    base: str            # host base
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    seed: int


# 90th Missile Wing -- F.E. Warren AFB. Largest field by area: SE Wyoming,
# the western Nebraska panhandle, and northern Colorado.
WARREN = Wing("90 MW", "F.E. Warren AFB", -104.90, -102.20, 40.50, 42.20, 9001)

# 341st Missile Wing -- Malmstrom AFB, central Montana around Great Falls.
MALMSTROM = Wing("341 MW", "Malmstrom AFB", -112.40, -109.10, 46.80, 48.45, 9002)

# 91st Missile Wing -- Minot AFB, northwestern North Dakota.
MINOT = Wing("91 MW", "Minot AFB", -102.45, -100.35, 47.85, 48.95, 9003)

WINGS = (WARREN, MALMSTROM, MINOT)

# Real Minuteman III wing structure.
SQUADRONS_PER_WING = 3
FLIGHTS_PER_SQUADRON = 5
LF_PER_FLIGHT = 10
FLIGHTS_PER_WING = SQUADRONS_PER_WING * FLIGHTS_PER_SQUADRON  # 15
LF_PER_WING = FLIGHTS_PER_WING * LF_PER_FLIGHT                # 150
LCC_PER_WING = FLIGHTS_PER_WING                              # 15

# A flight's LFs are spread over a real area (an LCC controls 10 LFs dispersed
# so no single weapon takes out the flight). This is the scatter radius, in
# degrees, of LFs about their flight center -- a rough public-knowledge spacing,
# not a surveyed value.
_FLIGHT_SPREAD_DEG = 0.18


def _flight_centers(wing: Wing, rng: random.Random) -> list[tuple[float, float]]:
    """Place FLIGHTS_PER_WING flight centers across the wing footprint.

    Uses a jittered near-square grid so flights tile the field roughly evenly
    (as real dispersed fields do) rather than clumping. Deterministic given the
    wing's seed.
    """
    import math

    n = FLIGHTS_PER_WING
    cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    centers: list[tuple[float, float]] = []
    lon_span = wing.lon_max - wing.lon_min
    lat_span = wing.lat_max - wing.lat_min
    for i in range(n):
        r, c = divmod(i, cols)
        # cell center in [0,1] grid space, then jittered within the cell
        fx = (c + 0.5) / cols + rng.uniform(-0.25, 0.25) / cols
        fy = (r + 0.5) / rows + rng.uniform(-0.25, 0.25) / rows
        lon = wing.lon_min + fx * lon_span
        lat = wing.lat_min + fy * lat_span
        centers.append((lon, lat))
    return centers


def generate_wing(wing: Wing) -> list[Target]:
    """150 launch facilities + 15 launch control centers for one wing.

    See the module-level HONESTY NOTE: positions are an illustrative
    distribution within the wing's documented footprint, deterministic per
    seed, not surveyed coordinates.
    """
    rng = random.Random(wing.seed)
    out: list[Target] = []
    for f_idx, (clon, clat) in enumerate(_flight_centers(wing, rng), start=1):
        squadron = (f_idx - 1) // FLIGHTS_PER_SQUADRON + 1
        flight_letter = chr(ord("A") + (f_idx - 1))
        # One LCC (missile alert facility) at the flight center.
        out.append(
            Target(
                name=f"{wing.name} {flight_letter}-01 LCC",
                lat=round(clat, 4),
                lon=round(clon, 4),
                category="icbm_lcc",
                note=f"{wing.base} launch control center (illustrative)",
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
                Target(
                    name=f"{wing.name} {flight_letter}-{lf:02d}",
                    lat=round(lat, 4),
                    lon=round(lon, 4),
                    category="icbm_lf",
                    note=f"squadron {squadron}, flight {flight_letter} (illustrative silo)",
                )
            )
    return out


def generate_all_fields() -> list[Target]:
    out: list[Target] = []
    for wing in WINGS:
        out.extend(generate_wing(wing))
    return out


# --- High-value targets (public) ---------------------------------------------
# Major population centers, economic/industrial nodes, and government C2. City
# coordinates are ordinary public geography; the government/industrial sites are
# publicly documented locations. Categories drive the frontend styling/legend.

# (name, lon, lat, category, note)
_HVT: list[tuple[str, float, float, str, str]] = [
    # Population centers (approx. city-center coordinates, top US metros)
    ("New York City", -74.006, 40.713, "city_population", "largest US metro"),
    ("Los Angeles", -118.244, 34.052, "city_population", ""),
    ("Chicago", -87.630, 41.878, "city_population", ""),
    ("Houston", -95.369, 29.760, "city_population", "port + petrochemical"),
    ("Phoenix", -112.074, 33.448, "city_population", ""),
    ("Philadelphia", -75.165, 39.953, "city_population", ""),
    ("San Antonio", -98.494, 29.424, "city_population", ""),
    ("San Diego", -117.161, 32.716, "city_population", "major naval complex"),
    ("Dallas", -96.797, 32.777, "city_population", ""),
    ("San Jose", -121.887, 37.339, "city_population", ""),
    ("Austin", -97.743, 30.267, "city_population", ""),
    ("Jacksonville", -81.656, 30.332, "city_population", ""),
    ("Columbus", -82.999, 39.961, "city_population", ""),
    ("Charlotte", -80.843, 35.227, "city_population", ""),
    ("Indianapolis", -86.158, 39.768, "city_population", ""),
    ("San Francisco", -122.419, 37.775, "city_population", ""),
    ("Seattle", -122.332, 47.606, "city_population", ""),
    ("Denver", -104.991, 39.739, "city_population", ""),
    ("Boston", -71.058, 42.360, "city_population", ""),
    ("Detroit", -83.046, 42.331, "city_population", ""),
    ("Atlanta", -84.388, 33.749, "city_population", ""),
    ("Miami", -80.192, 25.762, "city_population", ""),
    ("Minneapolis", -93.265, 44.978, "city_population", ""),
    ("Portland", -122.676, 45.523, "city_population", ""),
    ("St. Louis", -90.199, 38.627, "city_population", ""),
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
]


def high_value_targets() -> list[Target]:
    return [
        Target(name=n, lat=lat, lon=lon, category=cat, note=note)
        for (n, lon, lat, cat, note) in _HVT
    ]


# --- Per-target-class yields -------------------------------------------------
# Representative (yield_mt, fission_fraction) per target category, so the
# national envelope produces footprints that differ by target class rather than
# one uniform yield everywhere. This is DESCRIPTIVE modeling (a silo gets a
# counterforce-appropriate warhead, a city a countervalue-scale surface burst),
# NOT weaponeering/yield-optimization -- the PRD non-goal is about anything that
# increases lethality, which picking a representative public yield per class
# does not.
#
# Sourcing, honestly:
#   * Silos/LCCs at 0.30 Mt are grounded: the W87 on Minuteman III is ~300 kt
#     and the W78 ~335-350 kt -- 0.30 Mt is a real, public, representative
#     counterforce RV yield, not a guess.
#   * The other classes are ILLUSTRATIVE, order-of-magnitude public values
#     (hardened C2 / countervalue on the higher ~0.5 Mt tier, other military
#     installations on the ~0.3 Mt tier), in the same "labeled, not surveyed"
#     spirit as the silo coordinates above. Fission fraction is held at the
#     project's 0.5 default everywhere -- varying it per class has no sourced
#     basis, so it isn't invented here.
_DEFAULT_YIELD_MT = 0.30
_DEFAULT_FISSION = 0.5

CATEGORY_YIELD: dict[str, tuple[float, float]] = {
    # (yield_mt, fission_fraction)
    "icbm_lf": (0.30, 0.5),          # W87/W78-class RV (~300-350 kt), sourced
    "icbm_lcc": (0.30, 0.5),
    "bomber_base": (0.30, 0.5),
    "ssbn_base": (0.30, 0.5),
    "storage": (0.30, 0.5),
    "command": (0.50, 0.5),          # hardened C2 -> higher tier (illustrative)
    "city_population": (0.50, 0.5),  # countervalue surface burst (illustrative)
    "industry": (0.50, 0.5),         # (illustrative)
}

# Largest per-class yield, so callers can size a plume-reach window (the
# envelope's local-evaluation radius) that stays safe for every class.
MAX_CATEGORY_YIELD_MT = max(y for y, _ in CATEGORY_YIELD.values())


def yield_for(category: str) -> tuple[float, float]:
    """Representative (yield_mt, fission_fraction) for a target category."""
    return CATEGORY_YIELD.get(category, (_DEFAULT_YIELD_MT, _DEFAULT_FISSION))


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
