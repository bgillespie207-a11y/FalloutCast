"""Attack-scenario assumptions: the hypothetical INCOMING weapon per target
class, kept separate from target metadata (`targetdeck.py`).

WHY THIS IS SEPARATE. An incoming burst's yield is an assumption about the
*attacking* force, not a property of the target. Deriving a silo's burst yield
from the W87/W78 that the silo itself carries (as an earlier version did) is a
category error: the target's resident weapon is not what detonates on it. These
are therefore framed as a named, editable SCENARIO of representative incoming
yields, with sensitivity bands, not as target attributes.

SOURCING / HONESTY. The yields below are ILLUSTRATIVE, order-of-magnitude
public values for a generic modern strategic strike -- a counterforce RV in the
few-hundred-kiloton class, a countervalue weapon up to ~1 Mt -- with explicit
min/max bands so the sensitivity is visible rather than hidden behind a single
number. They are NOT sourced to a specific adversary weapon system, and must
not be read as one. Fission fraction is held at 0.5 (varying it per class has
no sourced basis).

BOUNDING ASSUMPTION (state this plainly wherever the envelope is shown). This
scenario assumes a SURFACE burst at EVERY site, including population and
industrial centers. Surface bursts maximize local fallout; real countervalue
strikes are often air bursts (little local fallout, more blast). So this is a
severe fallout-MAXIMIZING bounding case, not a neutral "what would happen"
forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

SCENARIO_NAME = "generic-modern-strategic-v1"

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


_COUNTERFORCE = "counterforce hard-target RV (few-hundred-kt class), illustrative"
_COUNTERVALUE = "countervalue / soft-target weapon (up to ~1 Mt), illustrative"

# Nominal incoming yields per target class. Differentiated so counterforce and
# countervalue footprints differ; every entry is an ATTACKER assumption.
DEFAULT_SCENARIO: dict[str, YieldAssumption] = {
    "icbm_lf": YieldAssumption("icbm_lf", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "icbm_lcc": YieldAssumption("icbm_lcc", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "bomber_base": YieldAssumption("bomber_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
    "ssbn_base": YieldAssumption("ssbn_base", 0.30, 0.30, 0.50, 0.5, _COUNTERFORCE),
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
