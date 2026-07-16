# FalloutCast — Session Handoff (UX-review backlog)

Written 2026-07-16. Read this first if you're picking up the remaining work.
(There is an older `docs/HANDOFF.md` from the physics-era session; this file
supersedes it for "what's the current state and what's next.")

## Snapshot

- **Branch:** `delfic-fractionation`. `main` is fast-forwarded to it after every
  commit, and **pushed to GitHub** (`origin` = https://github.com/bgillespie207-a11y/FalloutCast).
  The credential is cached in the macOS keychain, so `git push` works
  non-interactively. **Workflow: commit → `git branch -f main delfic-fractionation`
  → `git push origin main`.**
- **Latest commit:** `b4d5171` (mobile layout + time-slider ticks + landmarks).
- **Tests:** 105 passing — `source .venv/bin/activate && pytest -q` from repo root.
- **Versions:** API + pyproject + web/package.json all `0.3.0` (kept in sync).
- **Working tree:** clean.

## Running it (verify changes in the browser)

```bash
# API (must restart to pick up backend changes; --reload helps)
source .venv/bin/activate && uvicorn falloutcast.api.main:app --reload --port 8010
# Frontend (defaults to the :8010 API)
npm --prefix web run dev            # http://localhost:5173
```
Frontend typecheck: `cd web && npx tsc -b`. There is no frontend unit-test
suite yet (a gap; see #22).

## House rules (binding — every prior commit followed them)

1. **Never invent a physical constant / coordinate and present it as sourced.**
   Flag illustrative/synthetic values explicitly (see `targetdeck.py`,
   `scenario.py`). This is the project's #1 rule.
2. **Never claim validation that didn't happen.** Structural/labeled tests only
   unless there's a sourced reference.
3. **Logical, well-described commits**, each self-contained with a "why". Land +
   push after each (workflow above).
4. **Verify in the browser** for observable frontend changes (the Browser-pane
   tools), not just typecheck.

## What's been done (this review cycle)

The reviewer's two big passes (a code review + a UX review) are mostly cleared.
Highlights, newest last — read `git log` for detail:

- Weather-hour bug fixed (`openmeteo.py` used idx 0 = 00:00 UTC; now selects the
  current/nearest hour) + valid-time provenance surfaced in API/UI/export.
- deck.gl removed → native MapLibre circle/line layers (no more silent WebGL
  failure); render failures now surface.
- Exchange semantics corrected: `aggregation=max_single_source|sum`, honest
  naming ("curated target deck", not "all public targets"), `Query()` validation
  → 422 not 500, structured `yield_policy` (no more `yield_mt:0.0` sentinel),
  `included/excluded_target_ids`.
- Attacker-yield **scenario** split out of target metadata into `scenario.py`,
  grounded/cited to Princeton **Plan A** (structure only; yields still labeled
  illustrative). Surface-burst bounding caveat stated everywhere.
- Versioned target dataset (`targetdeck.py`): stable IDs, provenance
  (accuracy_m/confidence/geography_mode/source/dates), content hash, `/deck`
  endpoint + documented **field-polygon footprints** (the verifiable geography;
  silo points are flagged `synthetic`). Flights are **map-anchored** to the
  public USAF site maps; **90 MW Alpha & Echo verified by a former missileer**
  (others are approximate map readings).
- Validation: Small Boy directional cross-check, Glasstone-Dolan idealized
  magnitude (Tier-0 AND Tier-1), Castle Bravo measured-shot magnitude — all
  honestly scoped in `validation/`.
- **UX review — the whole "largest immediate improvement" cluster is DONE:**
  mobile layout (map was 70px → now ~50dvh + sticky Compute), time-slider tick
  labels + step fix, compute feedback (elapsed ticker + 90s timeout + disabled
  button), coordinate validation (min/max + friendly messages, no raw 422),
  auto-fit-to-plume + "Return to overview", clear-stale-results on mode change,
  `<main>`/skip-links/landmarks, 44px touch targets.

## Remaining backlog (this is the work to hand to the new context)

Two tasks remain (they were tracked as tasks #22 and #23). Both are large and
multi-item. Everything below is frontend unless noted.

### #22 — usability polish (higher leverage; reshapes core workflow)
- **Two top-level tabs** "Single location" / "National envelope" instead of the
  `#exchange-mode` checkbox (it's a major mode change hidden as a checkbox).
- **Basic/Advanced modes** + inline help/tooltips for jargon (WSEG-10, fission
  fraction, shear, Tier, ensemble members).
- **Rename Tier 0/1** to descriptive names (keep the technical term secondary).
- **Persistent contour table** (values, distances from GZ, directions, ensemble
  probabilities) — currently results depend on color + hover only.
- **Color-vision-safe palette** for the dose-rate bands (`LEVEL_COLORS` in
  `web/src/main.ts`) and probability bands (`PROB_COLORS`).
- **Yield preset selected-state** (mark the active preset; presets have no
  persistent selected style — see `.preset` in `style.css` / the preset click
  handler in `main.ts`).
- **Expandable disclaimer**: keep a short sticky banner (`#disclaimer`), move the
  full methodology into an expandable panel (it currently overwrites the banner
  with the long API `disclaimer` text via `disclaimerEl.textContent`).
- **Verify GeoJSON download** actually fires (reviewer couldn't observe the
  download event in the automated browser; the handler is the `#export-btn`
  click in `main.ts` using a Blob + `a.click()`).

### #23 — SME / domain features
- **Arrival time + cumulative dose** distinct from H+1 rate. Backend already has
  `POST /dose` (Way-Wigner accumulated dose) and `WSEG10.time_of_arrival()` —
  needs a frontend surface (e.g. click a point → show arrival, peak rate,
  integrated dose over a shelter window).
- **Shelter / protection-factor** scenarios (divide dose by PF) with strong
  non-operational disclaimers.
- **Weather age / refresh**: `valid_time`, `retrieved_at`, `age_seconds` are
  already returned (`weather` on the envelope response, and `openmeteo`
  provenance) — add a visible timestamp + a manual refresh control.
- **Wind arrows / altitude-profile** viz (the profile is fetched in `openmeteo`).
- **Metric/US unit switch** (miles↔km, R↔Sv-ish).
- **Shareable scenario links** (URL already encodes some state via
  `writeUrlState`/`readUrlState` in `main.ts` — extend, no sensitive data).
- **Place/address search** (currently only US ZIP via zippopotam + lat/lon).
- **Uncertainty-explainer panel** for the 10/50/90% ensemble bands.
- **Distance scale + distances from GZ** on the map.
- **Richer exported report** (assumptions/versions/timestamps/units/limits) —
  the envelope export already carries weather/aggregation/yield_policy/deck
  version/in-excluded IDs; extend to a human-readable report and cover the
  single-plume/ensemble exports too.

## Architecture map (where things live)

```
src/falloutcast/
  physics/wseg10.py     Tier-0 analytic model (time_of_arrival here)
  physics/tier1.py      Tier-1 multi-layer advection (_DOSE_CONV anchored to G&D)
  physics/decay.py      Way-Wigner decay + accumulated_dose
  grid.py               sample() + sample_envelope(aggregation=, radius_deg=)
  contour.py            marching-squares -> GeoJSON
  weather/openmeteo.py  fetch_profile / cached_fetch_profile (valid_time keyed),
                        fetch_ensemble_profiles, current_valid_time()
  scenario.py           attacker yields + Plan A sourcing + surface-burst caveat
  targetdeck.py         versioned deck, map-anchored flights, field polygons, /deck
  targets.py            the 10 curated installations
  schemas.py            all pydantic models (Target has provenance fields)
  api/main.py           FastAPI: /plume /dose /ensemble /exchange/envelope /deck /targets
  validation/           reference_cases (Small Boy), idealized_pattern (G&D),
                        castle_bravo (measured)
web/
  index.html            single page: #panel (controls) + #map, <main>, skip links
  src/main.ts           all UI logic: compute paths, native MapLibre layers,
                        mode toggles, elapsed timer, fit/validation helpers
  src/api.ts            typed API client
  src/decay.ts          client-side decay relabeling for the time slider
  src/style.css         layout (flex column, responsive @media max-width:700px)
docs/
  PRD.md TARGET_DECK.md TIER1_SPEC.md   kept current
```

## Gotchas (learned the hard way this session)

- **Restart the :8010 API to see backend changes** (uvicorn without --reload
  won't pick them up; a stale process silently serves old code).
- **HMR mid-click** can make one compute fail transiently after a hot reload;
  a fresh page load or a retry is fine. Not a code bug.
- **Number-input Enter** doesn't reliably submit the form in the automated
  browser; click the actual Compute button (resize the viewport taller to reach
  it, or it's below the fold at 720px — note the sticky-button fix is mobile-only).
- **Coordinate/pixel clicks** in the Browser pane are unreliable for small/hidden
  controls; prefer `read_page` refs, or `form_input`/`javascript_tool`.
- The **exchange envelope takes ~5–6 s cold** (500+ live wind fetches, bucketed);
  warm ~0.76 s (cache keyed to the forecast valid hour).
