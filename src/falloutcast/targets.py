"""Load the public CONUS target set used by exchange mode."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .schemas import Target

# data/ lives at the repo root, one level above the package. Resolve robustly.
_DATA = Path(__file__).resolve().parents[2] / "data" / "targets_conus.geojson"


def _slug(name: str) -> str:
    """Stable id slug from an installation name."""
    out: list[str] = []
    prev_dash = False
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "site-" + "".join(out).strip("-")


def load_targets(path: Path | None = None) -> list[Target]:
    p = path or _DATA
    gj = json.loads(Path(p).read_text())
    out: list[Target] = []
    for feat in gj["features"]:
        lon, lat = feat["geometry"]["coordinates"]
        props = feat["properties"]
        out.append(
            Target(
                id=props.get("id") or _slug(props["name"]),
                name=props["name"],
                lat=lat,
                lon=lon,
                category=props.get("category", "unknown"),
                note=props.get("note", ""),
            )
        )
    return out
