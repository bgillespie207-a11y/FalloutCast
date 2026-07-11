"""Unit conversions between SI (what weather APIs give us) and WSEG-10's
native unit system.

WSEG-10 is an artifact of 1970s defense analysis and works internally in
**statute miles, miles per hour, and kilofeet**. Rather than fight that, we
keep the model pure in its native units (so it can be checked against the
Hanifen reference) and convert only at the boundary.
"""

from __future__ import annotations

# Length
MILES_PER_METER = 1.0 / 1609.344
METERS_PER_MILE = 1609.344
KILOFEET_PER_METER = 1.0 / 304.8

# Speed
MPH_PER_MS = 2.2369362920544
MS_PER_MPH = 0.44704


def ms_to_mph(v_ms: float) -> float:
    return v_ms * MPH_PER_MS


def mph_to_ms(v_mph: float) -> float:
    return v_mph * MS_PER_MPH


def meters_to_miles(d_m: float) -> float:
    return d_m * MILES_PER_METER


def miles_to_meters(d_mi: float) -> float:
    return d_mi * METERS_PER_MILE


def shear_ms_per_m_to_mph_per_kilofoot(shear_ms_per_m: float) -> float:
    """Convert a wind-shear magnitude expressed as (m/s) per meter of altitude
    into WSEG-10's expected (mph) per kilofoot of altitude.

    (m/s)/m  ->  mph/kft :  multiply by MPH_PER_MS, divide by KILOFEET_PER_METER
    """
    return shear_ms_per_m * MPH_PER_MS / KILOFEET_PER_METER
