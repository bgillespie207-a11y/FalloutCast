# FalloutCast — Expanded Target Deck & Full-Exchange Analysis

Written 2026-07-11. Covers the "full nuclear exchange" rework: resolving the
three CONUS Minuteman fields down to individual launch facilities and control
centers, adding high-value targets (population/industry/C2), and the scaling
work that made ~500 ground zeros tractable. Also records what's still worth
improving.

## What changed

### 1. Target deck (`src/falloutcast/targetdeck.py`, new)

`targets.py` (10 curated installations) is unchanged — existing behavior and
tests intact. The new module adds an **opt-in** expanded deck:

| Category | Count | Source |
|---|---:|---|
| `icbm_lf`  (silos)         | 450 | generated, 150/wing × 3 wings |
| `icbm_lcc` (control centers) | 45 | generated, 15/wing × 3 wings |
| `city_population`          | 25 | public city-center coords (top US metros) |
| `industry`                | 6  | public ports / refining / tech corridors |
| `command` (government/C2)  | 5  | Offutt + DC, NORAD, Raven Rock, Mt. Weather |
| `bomber_base` / `ssbn_base` / `storage` | 6 | carried over from `targets.py` |
| **Total** | **537** | |

The three single `icbm_field` points in `targets.py` (Warren/Malmstrom/Minot)
are **superseded** by the resolved fields and dropped from the expanded deck to
avoid double-counting the same ground zeros.

Each Minuteman wing is modeled with its **real structure**: 150 LF + 15 LCC,
organized 3 squadrons × 5 flights × (10 LF + 1 LCC). Flight centers tile the
wing's documented geographic footprint; LFs scatter around each flight center.

> **Honesty note (important).** The individual LF/LCC *coordinates* are a
> deterministic, seeded **illustrative distribution within each wing's
> documented public field footprint** — **not** surveyed silo coordinates.
> This is deliberate and matches the project's first house rule ("never invent
> a physical constant and present it as sourced"; see `docs/HANDOFF.md`). For
> fallout-footprint modeling this is the right trade: a field's WSEG-10
> footprint is driven by its *extent and density*, not by meter-accurate silo
> positions. Faithful here: the count, the flight-of-10 organization, the wing
> footprint, rough LF spacing. Synthetic: exact placement within the footprint.
> To make this a real coordinate product, drop the seeding in
> `generate_wing()` and load a sourced LF coordinate set.

### 2. Scaling (`grid.py`, `api/main.py`)

Two hard blockers stood between 10 targets and 500+:

- **Serial per-target wind fetch.** The old envelope fetched one live
  Open-Meteo profile per target, serially — fine at 10, but ~500 serial calls
  is minutes plus rate-limiting. Now targets are **bucketed into ~1° cells and
  one profile is fetched per bucket, concurrently** (semaphore of 8, one retry
  with backoff for transient rate-limit errors). Physically justified:
  adjacent targets share the same synoptic-scale transport wind. A whole
  Minuteman field collapses from 165 fetches to a handful. See
  `_build_models_bucketed`.
- **O(targets × full-CONUS-grid) compositing.** `grid.sample_envelope` gained
  an optional `radius_deg`: each target's dose is evaluated only within a local
  window of its ground zero (WSEG-10 dose decays to ~0 within a few hundred
  miles), so cost is O(targets × local cells). `radius_deg=None` (default)
  keeps the exact original full-grid path, so existing tests/results are
  unchanged; the API passes `radius_deg=8.0` for the expanded deck.

**Measured:** full 537-target envelope with live wind end-to-end **~5–6 s**
(grid math itself ~0.5 s; the rest is the bucketed wind fetches). All 537
targets resolve; a bucket whose wind fetch still fails excludes its targets
(not fatal) and names them in the response notes.

### 3. API

- `GET /targets?expanded=true` → full deck; default (`false`) → original 10.
- `POST /exchange/envelope?expanded=true` (now the **default**) → full deck;
  `expanded=false` → original 10-installation envelope.

### 4. Frontend (`web/src/main.ts`, `web/src/api.ts`)

- The "Full nuclear exchange" mode now requests the expanded deck.
- Targets render as **one deck.gl `ScatterplotLayer`** (color-coded by
  category, hover shows name/type) instead of one MapLibre DOM marker per
  target — ~500 markers as DOM nodes would be sluggish; a scatter layer is one
  GPU pass. A category legend was added below the dose-rate isodose legend.

Verified live: the three fields render as dense silo/LCC clusters with
concentrated overlapping fallout, HVTs across CONUS each show their own plume,
and the composited national max-envelope contours (1/10/100 R/hr) draw over the
top.

## How to run

The API must be restarted to pick up the backend changes (the dev server does
not auto-reload unless started with `--reload`):

```bash
# API (any free port)
source .venv/bin/activate && uvicorn falloutcast.api.main:app --reload --port 8010
# Frontend (points at the API via FALLOUTCAST_API_URL; defaults to :8010)
npm --prefix web run dev            # http://localhost:5173
```

Tick **"Full nuclear exchange"** → **Compute national envelope**.

## Per-target-class yields (done)

Each target now carries a representative yield for its class instead of one
uniform value, so footprints differ by target type (`targetdeck.CATEGORY_YIELD`,
`?per_class=true`, the envelope default):

- **Silos / LCCs → 0.30 Mt.** Grounded, not invented: the W87 on Minuteman III
  is ~300 kt and the W78 ~335–350 kt.
- **Countervalue (population, industry) and hardened C2 → 0.50 Mt.**
  Illustrative order-of-magnitude public values, same "labeled, not surveyed"
  posture as the silo coordinates.
- Fission fraction held at the project's 0.5 default (varying it per class has
  no sourced basis).

This is *descriptive* modeling (a class-appropriate warhead per target), not
weaponeering/yield-optimization. Mechanically: the bucketed wind fetch now
returns the raw profile per bucket and `reduce_profile` (which depends on yield
via cloud-top height) is redone per target, so targets in one bucket can differ
in yield while still sharing one network call. `?per_class=false` restores a
single uniform yield. The frontend hides the global yield input in exchange mode
and shows the per-class summary instead.

## Still worth improving (ranked)

1. **No caching.** Every envelope call re-fetches all wind buckets and
   recomputes the grid. Bucketed fetch made it *fast enough*, but PRD.md's
   "cache on `(bucket, met_run)`" is still the right next step — GFS refreshes
   ~4×/day, so keying to the run (not wall-clock) would make repeat/concurrent
   calls near-instant. This is the single highest-leverage follow-up.
2. **Silo coordinates are synthetic** (see honesty note). If a real product is
   wanted, swap in a sourced LF coordinate set and drop the seeding.
4. **Bucket wind is a shared approximation.** One profile per ~1° cell is fine
   for the transport-scale wind of a dense field, but coastal HVTs sharing a
   bucket with very different local wind could be smeared. Tighten `bucket_deg`
   for sparse categories if this matters, or fetch HVTs individually.
5. **Envelope is Tier-0 (WSEG-10) only.** The exchange view can't use Tier-1
   multi-layer advection yet; the single-plume view can. Wiring Tier-1 into the
   envelope is a larger job (a full vertical profile per bucket + per-target
   advection) but would make the field footprints shear-curved rather than
   analytic smears.
6. **Legend always lists all categories.** It's static; it could reflect only
   the categories actually present in the current deck.
