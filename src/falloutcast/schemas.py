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


class WeatherProvenance(BaseModel):
    """Which forecast the winds came from -- so 'current weather' is auditable
    (fixes the long-standing bug where index 0 = 00:00 UTC was used)."""

    valid_time: str                       # forecast hour used, ISO UTC
    model: str                            # e.g. "GFS (Open-Meteo gfs_seamless)"
    retrieved_at: Optional[str] = None    # when the winds were fetched, ISO UTC
    age_seconds: Optional[int] = None     # staleness of the (possibly cached) winds


class WindProfilePoint(BaseModel):
    """One pressure level of the fetched vertical wind profile, for the UI's
    wind-by-altitude visualization."""

    height_m: float
    height_kft: float
    speed_mph: float
    from_deg: float             # meteorological "from" direction
    toward_deg: float           # compass bearing the wind carries fallout TOWARD
    in_fallout_layer: bool      # within the stabilized-cloud descent layer that
    #                             shapes the local footprint (reduce_profile's
    #                             averaging layer); higher levels loft fines away


class PlumeResponse(BaseModel):
    ground_zero: list[float]  # [lon, lat]
    tier_requested: int
    tier_used: int
    wind: WindUsed
    disclaimer: str
    notes: list[str] = []
    fraction_aloft: Optional[float] = None  # Tier-1 only: activity gone regional/global
    weather: Optional[WeatherProvenance] = None  # None for manual wind (nothing fetched)
    wind_profile: Optional[list[WindProfilePoint]] = None  # None for manual wind
    contours: dict  # GeoJSON FeatureCollection


class Target(BaseModel):
    id: str = ""  # stable identifier (see targetdeck); used for included/excluded reporting
    name: str
    lat: float
    lon: float
    category: str
    note: str = ""
    # --- provenance (versioned dataset; see targetdeck.py) -------------------
    wing: Optional[str] = None
    site_type: Optional[str] = None       # launch_facility | launch_control_center | city | ...
    designator: Optional[str] = None      # public designator, if any
    accuracy_m: Optional[float] = None    # positional accuracy, metres (large for synthetic)
    confidence: Optional[str] = None      # high | medium | low
    geography_mode: Optional[str] = None  # synthetic | observed | field_polygon
    source: Optional[str] = None          # source doc/URL for what IS asserted
    pub_date: Optional[str] = None        # source publication date
    verify_date: Optional[str] = None     # when this record was last verified
    status: Optional[str] = None          # facility status (NOT missile-loading, which is not public)


class FieldPolygon(BaseModel):
    """A documented missile-field FOOTPRINT (the verifiable geography when
    individual facility coordinates cannot be sourced to precision)."""

    id: str
    wing: str
    base: str
    lf_count: int
    lcc_count: int
    geography_mode: str = "field_polygon"
    confidence: str
    source: str
    pub_date: str
    verify_date: str
    # closed ring of [lon, lat] pairs
    polygon: list[list[float]]


class TargetDeckMeta(BaseModel):
    """Versioned dataset metadata for provenance + change tracking."""

    version: str
    content_hash: str          # sha256 over the deterministic target set
    generated: str             # ISO date this deck build was produced
    n_targets: int
    n_synthetic: int
    fields: list[FieldPolygon] = []
    notes: list[str] = []


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


class PointExposureRequest(BaseModel):
    """Exposure assessment at one map point under a Tier-0 (WSEG-10) plume.

    The effective wind is REQUIRED and never fetched here: callers echo back
    the wind a /plume response reported, so the assessment is exactly
    consistent with the contours already on screen (same model, same wind --
    no second live fetch that could silently disagree). Tier-1 has no
    time-of-arrival, so this endpoint is Tier-0 only.
    """

    lat: float = Field(ge=-90, le=90, description="ground zero latitude")
    lon: float = Field(ge=-180, le=180, description="ground zero longitude")
    yield_mt: float = Field(gt=0)
    fission_fraction: float = Field(gt=0, le=1.0, default=0.5)
    wind: ManualWind
    point_lat: float = Field(ge=-90, le=90, description="assessment point latitude")
    point_lon: float = Field(ge=-180, le=180, description="assessment point longitude")
    exit_hours: Optional[float] = Field(
        default=None, gt=0, description="end of the exposure window, hours after burst"
    )
    protection_factor: float = Field(
        default=1.0, ge=1.0, le=10000,
        description="shielding divisor: dose inside = outdoor dose / PF",
    )


class PointExposureResponse(BaseModel):
    point: list[float]  # [lon, lat]
    distance_miles: float
    bearing_from_gz_deg: float          # compass bearing GZ -> point
    arrival_hours: float                # WSEG-10 time of arrival (clamped >= 0.5)
    dose_rate_h1_rhr: float             # H+1 reference rate at the point, unshielded
    rate_at_arrival_rhr: float          # Way-Wigner rate at the arrival time, unshielded
    rate_curve: list[DoseSample] = []   # unshielded outdoor rates at times >= arrival
    protection_factor: float
    # Doses over [arrival, exit_hours] (None when exit_hours not given). Zero
    # when the window closes before fallout arrives.
    unsheltered_dose_window_r: Optional[float] = None
    sheltered_dose_window_r: Optional[float] = None
    # Doses over [arrival, infinity): staying exposed indefinitely.
    unsheltered_dose_to_infinity_r: float
    sheltered_dose_to_infinity_r: float
    disclaimer: str
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


class ExchangeEnvelopeResponse(BaseModel):
    """Composite dose surface across the curated target deck -- one grid/contour
    set, not a per-target overlay (contrast the plain dict `/exchange` returns).

    NOTE on semantics: `aggregation="max_single_source"` is a SCREENING envelope
    (worst dose from any ONE target at each point), NOT a combined-exchange
    total; `aggregation="sum"` adds overlapping contributions. See `notes`."""

    n_targets: int
    aggregation: str                       # "max_single_source" or "sum"
    deck_version: str = ""                 # versioned target-deck the run used
    yield_policy: dict                     # scenario/uniform yield assumptions (see scenario.py)
    included_target_ids: list[str] = []    # targets that contributed
    excluded_target_ids: list[str] = []    # targets dropped (e.g. wind-fetch failure)
    disclaimer: str
    notes: list[str] = []
    weather: Optional[WeatherProvenance] = None
    contours: dict  # one FeatureCollection of isodose contours


# --- disclaimers, one per model ------------------------------------------------
# This text is the frontend's "Methodology & limits" panel: whatever the
# response carries is what the user is told the result came from. A single
# shared string therefore described WSEG-10 to everyone -- including Tier-1 and
# ensemble results, which do not run it. Each compute path now returns the
# limits of the model it actually ran.
#
# The lede/coda are shared so the panel reads consistently and only the
# genuinely model-dependent middle changes.

_LEDE = "Planning estimate only, not an operational product. "
_CODA = " Do not use for real-world decisions."

DISCLAIMER_TIER0 = (
    _LEDE + "Uses the WSEG-10 analytic fallout model driven by a single "
    "effective wind; it assumes a flat-terrain surface burst and does not "
    "resolve local terrain, fractionation, or hot spots." + _CODA
)

# Back-compat alias: Tier-0/WSEG-10 is the default model, and this name is what
# the rest of the codebase imported before the split.
DISCLAIMER = DISCLAIMER_TIER0

DISCLAIMER_TIER1 = (
    _LEDE + "Uses the multi-layer (Tier-1) model: the stabilized cloud is "
    "split into height layers and particle-size bins, each falling at its own "
    "terminal velocity through the fetched vertical wind profile, so the "
    "pattern bends with wind shear. That profile is taken as horizontally "
    "uniform (one sounding, at ground zero), the burst is treated as a "
    "flat-terrain surface burst, and terrain, fractionation, and hot spots are "
    "not resolved. Activity is converted to dose rate with a calibration "
    "anchored to the Glasstone & Dolan (1977) idealized pattern, not to "
    "measured shots." + _CODA
)

DISCLAIMER_ENSEMBLE = (
    _LEDE + "Runs the multi-layer (Tier-1) model once per GFS-ensemble wind "
    "member and maps how many members put a location above the chosen dose "
    "rate. The spread between bands is WIND-forecast uncertainty only: it "
    "does not include uncertainty in the fallout model itself, the yield, the "
    "fission fraction, or the deposition calibration, so the true uncertainty "
    "is wider than the bands show. Tier-1's own limits apply to every member "
    "(horizontally uniform wind profile, flat-terrain surface burst, no "
    "terrain/fractionation/hot spots)." + _CODA
)

DISCLAIMER_ENVELOPE = (
    _LEDE + "Composites one WSEG-10 (Tier-0) surface-burst plume per target "
    "across a curated, incomplete target deck onto a single national grid. "
    "Under 'max_single_source' each cell shows the worst H+1 dose rate from "
    "any ONE target -- a screening envelope, not a combined total, and not a "
    "forecast of any particular attack. Yields are illustrative per-class "
    "attacker assumptions rather than the targets' own weapons, every site is "
    "modeled as a surface burst (a fallout-maximizing bounding case), and some "
    "ground zeros are synthetic illustrative positions. Tier-0's limits apply "
    "to each plume." + _CODA
)

DISCLAIMER_EXPOSURE = (
    _LEDE + "Assesses one point under the WSEG-10 (Tier-0) plume shown, using "
    "that plume's own wind: arrival time from the cloud-transport model and "
    "accumulated dose from Way-Wigner t^-1.2 decay. Dose rates are unshielded "
    "outdoor values; any protection factor is your assumption, not an estimate "
    "of a real structure. It models neither shielding geometry, nor "
    "weathering, nor internal (inhaled/ingested) dose." + _CODA
)
