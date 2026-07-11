"""Tests for the Open-Meteo ensemble wind fetch.

`fetch_ensemble_profiles` is network I/O, so these inject a fake httpx client
(same DI pattern `fetch_profile` already supports) rather than hitting the
live API. No live-network test here -- that would be flaky/rate-limited, not
a unit test.
"""

import asyncio

import numpy as np

from falloutcast.weather import openmeteo

LEVELS = (1000, 925, 850)
HEIGHTS = (110, 760, 1460)


def _payload(n_members: int, *, missing_member_level: tuple[int, int] | None = None):
    """Build a synthetic Open-Meteo ensemble response for LEVELS/HEIGHTS.

    Control member (no suffix) gets a fixed speed/direction per level.
    Perturbed members (member01..) get speed = control + member_index,
    direction = control unchanged -- distinct but deterministic, so tests can
    assert on exact values. `missing_member_level=(member_idx, hpa)` nulls out
    that one member/level's windspeed to exercise the control-fallback path.
    """
    hourly = {"time": ["2026-07-10T00:00"]}
    for hpa, h in zip(LEVELS, HEIGHTS):
        hourly[f"windspeed_{hpa}hPa"] = [10.0]
        hourly[f"winddirection_{hpa}hPa"] = [270.0]
        hourly[f"geopotential_height_{hpa}hPa"] = [float(h)]
        for m in range(1, n_members):
            speed = 10.0 + m
            if missing_member_level == (m, hpa):
                speed = None
            hourly[f"windspeed_{hpa}hPa_member{m:02d}"] = [speed]
            hourly[f"winddirection_{hpa}hPa_member{m:02d}"] = [270.0]
    return {"hourly": hourly}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, url, params=None):
        return _FakeResponse(self._payload)

    async def aclose(self):
        pass


def _fetch(n_members, payload):
    client = _FakeClient(payload)
    return asyncio.run(
        openmeteo.fetch_ensemble_profiles(
            41.14, -104.82, n_members=n_members, client=client
        )
    )


def test_returns_one_profile_per_requested_member():
    profiles = _fetch(5, _payload(5))
    assert len(profiles) == 5


def test_control_member_is_first_and_matches_unsuffixed_fields():
    profiles = _fetch(3, _payload(3))
    control = profiles[0]
    np.testing.assert_allclose(control.speed_ms, [10.0, 10.0, 10.0])
    np.testing.assert_allclose(sorted(control.height_m), sorted(HEIGHTS))


def test_perturbed_members_differ_from_control():
    profiles = _fetch(4, _payload(4))
    control_speed = profiles[0].speed_ms
    for member in profiles[1:]:
        assert not np.allclose(member.speed_ms, control_speed)


def test_all_members_share_the_same_height_axis():
    """Required for ensemble.run_ensemble, which advects every member over
    one shared heights_m array."""
    profiles = _fetch(6, _payload(6))
    for p in profiles[1:]:
        np.testing.assert_array_equal(p.height_m, profiles[0].height_m)


def test_n_members_capped_at_available():
    profiles = _fetch(1000, _payload(31))
    assert len(profiles) == openmeteo.ENSEMBLE_MEMBERS_AVAILABLE


def test_missing_member_value_falls_back_to_control():
    """If one member is unexpectedly missing a value at a level the control
    has, that member uses the control's reading rather than desyncing the
    per-member array length from the shared height axis."""
    payload = _payload(4, missing_member_level=(2, 925))
    profiles = _fetch(4, payload)
    member2 = profiles[2]
    idx_925 = list(profiles[0].height_m).index(760.0)  # 925 hPa -> 760 m
    assert member2.speed_ms[idx_925] == 10.0  # control's value, not NaN/crash


# --- cached_fetch_profile ----------------------------------------------------


def _fake_profile():
    return openmeteo.WindProfile(
        height_m=np.array([110.0]),
        speed_ms=np.array([10.0]),
        direction_deg=np.array([270.0]),
    )


def test_cached_fetch_profile_serves_repeat_calls_from_cache(monkeypatch):
    """A second call for the same point in the same window makes no network
    call -- this is what makes repeat envelope requests near-instant."""
    openmeteo.clear_profile_cache()
    calls = {"n": 0}

    async def fake(lat, lon, *, client=None):
        calls["n"] += 1
        return _fake_profile()

    monkeypatch.setattr(openmeteo, "fetch_profile", fake)

    async def run():
        a = await openmeteo.cached_fetch_profile(41.1, -104.8)
        b = await openmeteo.cached_fetch_profile(41.1, -104.8)
        return a, b

    a, b = asyncio.run(run())
    assert calls["n"] == 1
    assert a is b
    openmeteo.clear_profile_cache()


def test_cached_fetch_profile_dedupes_concurrent_misses(monkeypatch):
    """Two concurrent misses for the same key share ONE fetch (no thundering
    herd), which matters when several targets/buckets resolve at once."""
    openmeteo.clear_profile_cache()
    calls = {"n": 0}

    async def fake(lat, lon, *, client=None):
        calls["n"] += 1
        await asyncio.sleep(0.02)  # hold the fetch open so both calls overlap
        return _fake_profile()

    monkeypatch.setattr(openmeteo, "fetch_profile", fake)

    async def run():
        return await asyncio.gather(
            openmeteo.cached_fetch_profile(30.0, -90.0),
            openmeteo.cached_fetch_profile(30.0, -90.0),
        )

    res = asyncio.run(run())
    assert calls["n"] == 1
    assert res[0] is res[1]
    openmeteo.clear_profile_cache()


def test_cached_fetch_profile_refetches_after_window_rolls(monkeypatch):
    """A short TTL window that elapses between calls forces a refetch -- the
    cache is time-bounded, not sticky forever."""
    openmeteo.clear_profile_cache()
    calls = {"n": 0}

    async def fake(lat, lon, *, client=None):
        calls["n"] += 1
        return _fake_profile()

    monkeypatch.setattr(openmeteo, "fetch_profile", fake)

    async def run():
        await openmeteo.cached_fetch_profile(45.0, -100.0, ttl_s=0.05)
        await asyncio.sleep(0.06)
        await openmeteo.cached_fetch_profile(45.0, -100.0, ttl_s=0.05)

    asyncio.run(run())
    assert calls["n"] == 2
    openmeteo.clear_profile_cache()
