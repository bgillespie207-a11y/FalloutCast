"""Attack-scenario assumptions: the hypothetical INCOMING weapon per target
class, kept separate from target metadata (`targetdeck.py`).

WHY THIS IS SEPARATE. An incoming burst's yield is an assumption about the
*attacking* force, not a property of the target. Deriving a silo's burst yield
from the W87/W78 that the silo itself carries (as an earlier version did) is a
category error: the target's resident weapon is not what detonates on it. These
are therefore framed as a named, editable SCENARIO of representative incoming
yields, with sensitivity bands, not as target attributes.

SOURCING / HONESTY. The scenario STRUCTURE -- a US/Russia exchange escalating
tactical -> counterforce (nuclear forces: ICBM fields, bomber/sub bases,
command) -> countervalue (the ~30 most-populous cities/economic centers) -- is
grounded in Princeton Science & Global Security's "Plan A" (Wellerstein, Patton,
Kutt, Glaser, 2019; see SOURCES). The per-class YIELDS below remain
ILLUSTRATIVE order-of-magnitude values (Plan A itself used the actual deployed
arsenals, a mix of real yields, and did not publish a single per-class table),
with explicit min/max bands so sensitivity is visible. They are NOT sourced to a
specific adversary weapon system. Fission fraction is held at 0.5 (varying it
per class has no sourced basis).

NOT YET MODELED (documented Plan A feature). Plan A's countervalue phase puts
5-10 warheads on EACH major city (scaled by population), not one. This deck
models ONE ground zero per city -- a conservative simplification for fallout;
the higher countervalue yield partially compensates. Multi-warhead-per-city is
a real future refinement (would need the `sum` aggregation to be meaningful).

BOUNDING ASSUMPTION (state this plainly wherever the envelope is shown). This
scenario assumes a SURFACE burst at EVERY site, including population and
industrial centers. Surface bursts maximize local fallout; real countervalue
strikes are often air bursts (little local fallout, more blast). So this is a
severe fallout-MAXIMIZING bounding case, not a neutral "what would happen"
forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

SCENARIO_NAME = "planA-informed-strategic-v1"

# Citable sources the scenario's structure/casualty scale rest on.
SOURCES = [
    "Princeton Science & Global Security, 'Plan A' nuclear-war simulation "
    "(A. Wellerstein, T. Patton, M. Kutt, A. Glaser, 2019): "
    "https://sgs.princeton.edu/the-lab/plan-a -- US/Russia exchange, phases "
    "tactical -> counterforce -> countervalue (30 most-populous cities/economic "
    "centers, 5-10 warheads each by population); >90M casualties in the first "
    "hours. Uses real deployed weapon yields/targets; casualties via NUKEMAP.",
    "Arms Control Association, 'Plan A: How a Nuclear War Could Progress' "
    "(2020): https://www.armscontrol.org/act/2020-07/features/plan-how-nuclear-war-could-progress",
    "Force structure (450 US Minuteman III silos; 400 deployed ICBMs): GAO 2025.",
]

# Documented Plan A feature this deck does NOT yet model (see module docstring).
MULTI_WARHEAD_PER_CITY_NOTE = (
    "Plan A puts 5-10 warheads on each major city (by population); this deck "
    "models one ground zero per city (conservative for fallout)."
)

SURFACE_BURST_CAVEAT = (
    "Scenario assumes a SURFACE burst at every site (including cities and "
    "industry). Surface bursts maximize local fallout -- this is a fallout-"
    "maximizing bounding case, not a neutral forecast; real countervalue "
    "strikes are often air bursts with far less local fallout."
)


@dataclass(frozen=True)
class YieldAssumption:
    """Assumed incoming weapon for a target class (attacker scenario)."""

    category: str
    yield_mt: float          # nominal assumed incoming yield
    yield_min_mt: float      # sensitivity band, low
    yield_max_mt: float      # sensitivity band, high
    fission_fraction: float
    rationale: str           # attacker-scenario framing (NOT the target's weapon)


_COUNTERFORCE = (
    "counterforce hard-target RV (few-hundred-kt class); Plan A counterforce "
    "phase targets nuclear forces. Yield illustrative, not a specific weapon."
)
_COUNTERFORCE_MIL = (
    "counterforce strike on a military installation (naval/air/missile-defense; "
    "few-hundred-kt class). Yield illustrative, not a specific weapon."
)
_COUNTERVALUE = (
    "countervalue weapon (up to ~1 Mt); Plan A city phase hits the ~30 largest "
    "cities. Yield illustrative, not a specific weapon."
)

# Nominal incoming yields per target class. Differentiated so counterforce and
# countervalue footprints differ; every entry is an ATTACKER assumption.
DEFAULT_SCENARIO: dict[str, YieldAssumption] = {
    "icbm_lf": YieldAssumption("icbm_lf", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "icbm_lcc": YieldAssumption("icbm_lcc", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "bomber_base": YieldAssumption("bomber_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "ssbn_base": YieldAssumption("ssbn_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "naval_base": YieldAssumption("naval_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE_MIL),
    "air_base": YieldAssumption("air_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE_MIL),
    "army_base": YieldAssumption("army_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE_MIL),
    "missile_defense": YieldAssumption("missile_defense", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE_MIL),
    "storage": YieldAssumption("storage", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "command": YieldAssumption("command", 0.50, 0.30, 1.00, 0.5, _COUNTERVALUE),
    "city_population": YieldAssumption("city_population", 0.50, 0.30, 1.00, 0.5, _COUNTERVALUE),
    "industry": YieldAssumption("industry", 0.50, 0.30, 1.00, 0.5, _COUNTERVALUE),
}

_DEFAULT = YieldAssumption("default", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE)

# Largest nominal yield in play, so callers can size a plume-reach window that
# stays safe for every class.
MAX_SCENARIO_YIELD_MT = max(a.yield_mt for a in DEFAULT_SCENARIO.values())


def assumption_for(category: str) -> YieldAssumption:
    return DEFAULT_SCENARIO.get(category, _DEFAULT)


def yield_for(category: str) -> tuple[float, float]:
    """Nominal (yield_mt, fission_fraction) assumed for a target class."""
    a = assumption_for(category)
    return a.yield_mt, a.fission_fraction


def yield_policy(present_categories: set[str]) -> dict:
    """Structured, self-describing yield policy for the API response -- replaces
    the old `yield_mt: 0.0` sentinel. Lists the per-class assumption (nominal +
    sensitivity band) for exactly the categories present in this run."""
    return {
        "scenario": SCENARIO_NAME,
        "mode": "per_class",
        "surface_burst_caveat": SURFACE_BURST_CAVEAT,
        "sources": SOURCES,
        "scenario_notes": [MULTI_WARHEAD_PER_CITY_NOTE],
        "assumptions": [
            {
                "category": a.category,
                "yield_mt": a.yield_mt,
                "yield_min_mt": a.yield_min_mt,
                "yield_max_mt": a.yield_max_mt,
                "fission_fraction": a.fission_fraction,
                "rationale": a.rationale,
            }
            for cat in sorted(present_categories)
            if (a := assumption_for(cat))
        ],
    }
