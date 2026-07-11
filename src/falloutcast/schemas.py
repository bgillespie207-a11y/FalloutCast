"""API request/response schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ManualWind(BaseModel):
    """Override the fetched wind with an explicit effective wind."""

    speed_mph: float = Field(gt=0)
    bearing_deg: float = Field(ge=0, lt=360, description="compass bearing plume travels toward")
    shear_mph_per_kft: float = Field(ge=0, default=0.0)


class PlumeRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    yield_mt: float = Field(gt=0, description="total yield, megatons")
    fission_fraction: float = Field(gt=0, le=1.0, default=0.5)
    # burst height is fixed at surface for fallout; kept explicit for honesty
    surface_burst: bool = Field(default=True)
    tier: int = Field(default=0, ge=0, le=1, description="0=WSEG-10, 1=multi-layer advection")
    wind: Optional[ManualWind] = None
    levels_rhr: Optional[list[float]] = None


class WindUsed(BaseModel):
    speed_mph: Optional[float] = None
    bearing_deg: Optional[float] = None
    shear_mph_per_kft: Optional[float] = None
    source: str  # "open-meteo-gfs", "manual", or "open-meteo-gfs-profile"


class PlumeResponse(BaseModel):
    ground_zero: list[float]  # [lon, lat]
    tier_requested: int
    tier_used: int
    wind: WindUsed
    disclaimer: str
    notes: list[str] = []
    fraction_aloft: Optional[float] = None  # Tier-1 only: activity gone regional/global
    contours: dict  # GeoJSON FeatureCollection


class Target(BaseModel):
    name: str
    lat: float
    lon: float
    category: str
    note: str = ""


class DoseRequest(BaseModel):
    """Time-evolution of exposure at a point with a known H+1 dose rate."""

    dose_rate_h1: float = Field(gt=0, description="reference dose rate at H+1, R/hr")
    arrival_hours: float = Field(gt=0, default=1.0, description="fallout arrival time")
    exit_hours: Optional[float] = Field(default=None, description="when shelter is left")
    times_hours: Optional[list[float]] = Field(
        default=None, description="times to report instantaneous dose rate"
    )


class DoseSample(BaseModel):
    t_hours: float
    dose_rate_rhr: float


class DoseResponse(BaseModel):
    rate_curve: list[DoseSample]
    accumulated_dose_r: Optional[float] = None    # arrival -> exit
    total_to_infinity_r: float                    # arrival -> forever
    notes: list[str] = []


class EnsembleRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    yield_mt: float = Field(gt=0)
    fission_fraction: float = Field(gt=0, le=1.0, default=0.5)
    level_rhr: float = Field(gt=0, default=1.0, description="dose level to band, R/hr")
    n_members: int = Field(default=12, ge=3, le=40)


class EnsembleResponse(BaseModel):
    ground_zero: list[float]
    level_rhr: float
    n_members: int
    mean_fraction_aloft: float
    disclaimer: str
    notes: list[str] = []
    contours: dict  # probability bands: P(dose rate >= level_rhr)


DISCLAIMER = (
    "Planning estimate only, not an operational product. Uses the WSEG-10 "
    "analytic fallout model driven by a single effective wind; it assumes a "
    "flat-terrain surface burst and does not resolve local terrain, "
    "fractionation, or hot spots. Do not use for real-world decisions."
)
