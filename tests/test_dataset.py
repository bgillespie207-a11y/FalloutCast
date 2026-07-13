"""CI checks for the versioned target dataset (targetdeck.py).

These are the guardrails the review asked for: correct counts, unique ids,
points inside their wing bounds, no duplicate coordinates, required provenance
on every record, and ZERO synthetic points in the verified view. They fail the
build if the dataset drifts out of its documented structure.
"""

import pytest

from falloutcast import targetdeck


def test_structure_counts_match_documented_force():
    """450 launch facilities + 45 launch control centers (150 LF + 15 LCC per
    wing x 3 wings), per GAO 2025 / USAF wing organization."""
    fields = targetdeck.generate_all_fields()
    assert sum(t.category == "icbm_lf" for t in fields) == 450
    assert sum(t.category == "icbm_lcc" for t in fields) == 45


def test_all_ids_unique():
    full = targetdeck.load_expanded_targets()
    ids = [t.id for t in full]
    assert all(ids), "every target must have an id"
    assert len(ids) == len(set(ids)), "target ids must be unique"


def test_field_points_lie_within_their_wing_bounds():
    by_slug = {w.name.replace(" ", ""): w for w in targetdeck.WINGS}
    for t in targetdeck.generate_all_fields():
        slug = t.id.split("-")[0]
        w = by_slug[slug]
        assert w.lon_min <= t.lon <= w.lon_max, f"{t.id} lon out of {slug} bounds"
        assert w.lat_min <= t.lat <= w.lat_max, f"{t.id} lat out of {slug} bounds"


def test_no_duplicate_coordinates():
    full = targetdeck.load_expanded_targets()
    coords = [(round(t.lat, 4), round(t.lon, 4)) for t in full]
    assert len(coords) == len(set(coords)), "no two targets may share a coordinate"


def test_every_record_carries_required_provenance():
    for t in targetdeck.load_expanded_targets():
        assert t.geography_mode in ("synthetic", "observed", "field_polygon"), t.id
        assert t.accuracy_m and t.accuracy_m > 0, t.id
        assert t.confidence in ("high", "medium", "low"), t.id
        assert t.source, t.id
        assert t.verify_date, t.id


def test_synthetic_points_are_flagged_with_low_confidence_and_field_scale_accuracy():
    synth = [t for t in targetdeck.load_expanded_targets() if t.category in ("icbm_lf", "icbm_lcc")]
    assert synth
    for t in synth:
        assert t.geography_mode == "synthetic", t.id
        assert t.confidence == "low", t.id
        assert t.accuracy_m >= 1000.0, t.id  # flight-scale, not survey precision
        # provenance must disclaim surveyed/precise coordinates
        assert "NOT surveyed coordinates" in t.source


def test_verified_view_has_zero_synthetic_points():
    """The review's key guardrail: in verified mode there are NO invented precise
    points -- only observed/field_polygon geography survives."""
    verified = targetdeck.verified_targets()
    assert verified  # cities/installations remain
    assert all(t.geography_mode != "synthetic" for t in verified)
    assert all(t.category not in ("icbm_lf", "icbm_lcc") for t in verified)


def test_lccs_sit_at_the_map_anchored_flight_centers():
    """Each flight's LCC is placed at its real documented (map-anchored)
    location -- so the field layout follows the actual flight geography, not a
    jittered grid. Flight letters run A..O (15 flights)."""
    for wing in targetdeck.WINGS:
        wing_slug = wing.name.replace(" ", "")
        by_id = {t.id: t for t in targetdeck.generate_wing(wing) if t.category == "icbm_lcc"}
        assert len(by_id) == 15
        letters = {a[0] for a in wing.flights}
        assert letters == set("ABCDEFGHIJKLMNO")
        for letter, lat, lon in wing.flights:
            lcc = by_id[f"{wing_slug}-{letter}-LCC"]
            assert lcc.lat == round(lat, 4) and lcc.lon == round(lon, 4)


def test_field_polygons_are_the_verifiable_geography():
    polys = targetdeck.field_polygons()
    assert len(polys) == 3
    for p in polys:
        assert p.geography_mode == "field_polygon"
        assert p.lf_count == 150 and p.lcc_count == 15
        assert p.polygon[0] == p.polygon[-1], "ring must be closed"
        assert len(p.polygon) >= 4
        assert p.source and p.verify_date


def test_content_hash_is_deterministic_and_versioned():
    assert targetdeck.dataset_content_hash() == targetdeck.dataset_content_hash()
    meta = targetdeck.deck_meta()
    assert meta.version == targetdeck.DATASET_VERSION
    assert len(meta.content_hash) == 64  # sha256 hex
    assert meta.n_synthetic == 495       # 450 LF + 45 LCC
    assert len(meta.fields) == 3
