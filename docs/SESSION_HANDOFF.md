# FalloutCast — Session Handoff (UX-review backlog)

Written 2026-07-16, **last updated 2026-07-29**. Read this first if you're
picking up the remaining work. (There is an older `docs/HANDOFF.md` from the
physics-era session; this file supersedes it for "what's the current state and
what's next.")

## Snapshot

- **Branch:** `delfic-fractionation`. `main` is fast-forwarded to it after every
  commit, and **pushed to GitHub** (`origin` = https://github.com/bgillespie207-a11y/FalloutCast).
  The credential is cached in the macOS keychain, so `git push` works
  non-interactively. **Workflow: commit → `git branch -f main delfic-fractionation`
  → `git push origin main`.**
- **Latest commit:** `1c1c739` (run-dev.sh). Local branch, `main`, and
  `origin/main` are all in sync as of 2026-07-29 — nothing unpushed.
- **Tests:** **118 passing** — `source .venv/bin/activate && pytest -q` from repo
  root. (Frontend still has NO test suite — the standing gap; see "What's next".)
- **Versions:** API + pyproject + web/package.json all `0.3.0` (kept in sync).
- **Target deck:** **600 ground zeros**, dataset version `2025.8-more-bases`.
- **Working tree:** two INTENTIONALLY uncommitted local files —
  `.claude/launch.json` (has a `chemprep` dev-server entry for an unrelated
  project at `~/Downloads/chem281-prep`) and `.claude/settings.local.json`.
  **Leave both alone; do not commit them and do not touch chem281-prep.**

## Running it (verify changes in the browser)

**Preferred: `bash run-dev.sh`** — starts BOTH servers, each in a restart loop,
from the user's own terminal. Servers started from inside an agent/tool session
get reaped when that session ends, which is why they kept "crashing"; run-dev.sh
is the durable fix. Leave the window open; Ctrl-C stops both.

Manually, if needed:
```bash
# API (must restart to pick up backend changes; --reload helps)
source .venv/bin/activate && uvicorn falloutcast.api.main:app --reload --port 8010
# Frontend (defaults to the :8010 API)
npm --prefix web run dev            # http://localhost:5173
```
Frontend typecheck: `cd web && npx tsc -b`. There is no frontend unit-test
suite yet (a gap; see "What's next").

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

One task remains: #23. (#22 — usability polish — was completed 2026-07-16:
top-level mode tabs replacing the exchange checkbox, Basic/Advanced disclosure
+ inline jargon help, descriptive tier names, persistent contour table with
reach-from-GZ + direction, Okabe-Ito/Blues color-vision-safe palettes, yield
preset selected-state, short banner + expandable methodology panel, and the
GeoJSON export verified live (anchor click + valid FeatureCollection blob;
revocation now deferred). A map-recovery bug found along the way is also
fixed: the overlay setup now retries at compute time if the style finished
loading after the last styledata event, e.g. in a background tab.)

### #23 — SME / domain features

**Done 2026-07-17** (see git log for the commits):
- Arrival time + cumulative dose: new `POST /exposure` (exposure.py, 8 offline
  tests) + click-to-inspect panel (click the map while a Tier-0 plume is shown).
- Shelter / protection-factor: PF selector (1/10/100, labeled illustrative) in
  that panel; doses divided server-side, disclaimers rendered verbatim.
- Weather age / refresh: `weather` provenance now also on /plume responses; UI
  line (model · valid hour · fetch age) + "Refresh winds" button;
  `force_refresh=true` on the envelope busts the per-hour wind cache.
- Uncertainty explainer: "How to read these bands" under the ensemble legend.
- Distance scale: mi + km ScaleControls bottom-left.
- Shareable links: URL state covers manual wind and ensemble mode
  (`?mode=ensemble&level=&members=`, `wind=speed,bearing,shear`) + a
  "Copy scenario link" button with a no-clipboard fallback.

**Also done (2026-07-20):**
- Place/address search: the ZIP box is now a general "Find a place, address, or
  ZIP" search. 5-digit ZIPs keep the zippopotam fast path; everything else
  (city, address, HI/AK site) resolves via the keyless Nominatim geocoder
  (`geocodePlace` in api.ts). Sets GZ inputs + flies the map + shows the
  resolved name.
- Richer exported report: every compute records an `exportReport`
  (assumptions/versions/timestamp/units/limits) in main.ts. The GeoJSON export
  embeds it as a top-level `metadata` member; a new "Download report" button
  writes the same as human-readable Markdown (`falloutcast-report.md`). Covers
  all three modes — plume (reach table follows the decay slider), ensemble
  (probability-band reach), and envelope (per-class yield policy table). App
  version comes from a new `__APP_VERSION__` Vite define (package.json);
  changing vite.config requires a dev-server restart to take effect.

**Also done (2026-07-20):**
- Wind-by-altitude viz: `/plume` now returns the fetched vertical `wind_profile`
  (one point per pressure level: height, speed, from/toward bearing,
  `in_fallout_layer`) for live-wind computes — no extra fetch, `_resolve_wind`
  just also returns the profile it already fetched. Frontend renders a compact
  SVG arrow column (`renderWindProfile` in main.ts, `#wind-profile`): north-up
  arrows per level, length ∝ speed, bold for the cloud-descent layer / faint
  for higher winds — makes shear visible. Hidden for manual wind (nothing
  fetched) and ensemble/envelope modes.
- Metric/US unit switch: a persisted (localStorage `falloutcast.units`) global
  toggle below the mode tabs. Distances stay dual but flip which is primary
  (`formatReach`); wind speed switches km/h↔mph (`formatSpeed`/`formatSpeedShort`
  in `describeWind` + wind profile); heights switch km↔kft; and metric mode adds
  an approximate Sv to the exposure-panel doses (`svApprox`, labeled "1 R ≈ 10
  mSv, whole-body gamma"). `applyUnits()` re-renders the on-screen table / wind
  profile / exposure panel in place (state stored in `lastContourTable`,
  `lastWindProfilePoints`, `lastExposureResp`) — no recompute.

**#23 is complete.** Both tracked review tasks (#22, #23) are done.

## Work after the backlog (2026-07-20 → 07-29)

All landed and pushed. Not part of #22/#23 — driven by user spot-checks:

- **Target deck expansion, 537 → 600 ground zeros.** (a) Population centers were
  the top-25 by *municipal* population, an artifact of city limits that hid big
  metros (Cleveland, Milwaukee, Raleigh…); rebased on the ~50 largest **metro
  areas** (49 entries). (b) Added Hawaii/Alaska strategic sites (Pearl Harbor,
  JBER, Eielson, Fort Greely GMD, Clear SFS) — this required widening the
  envelope grid to `grid.US_*` bounds, because the local-window path SKIPS
  targets outside the grid, which would have made them bare dots with no plume.
  (c) Added Hoover + Grand Coulee dams. (d) Two passes of major military bases
  (~32): all major combatant-command HQs, Army/Marine posts (new `army_base`
  category), more AF/Navy. Every addition: public installation centroids, public
  role in the note, **no troop counts asserted as sourced data**.
- **UI/UX:** results-panel reorder + heading consistency + dividers; dark theme
  via a token palette; a11y (real tabpanel, roving tabindex, radiogroup arrow
  keys, focus rings); mobile fixes; stale-result flagging.
- **Bug fixes:** map overlay gate, contour band mislabeling, level-set waste,
  unit toggle on the status line.
- **Decay-time slider for the national envelope** (H+1 → H+24), with tests.
- **run-dev.sh** (see "Running it").

## What's next (nothing is tracked/committed-to — these are candidates)

1. **Frontend test suite** — the clearest real gap. Backend has 118 tests; the
   frontend has zero, despite `main.ts` now holding unit conversions, decay-time
   relabeling, URL-state round-trips, report/metadata builders, and geometry
   helpers (`farthestPoint`, `compassName`). A Vitest suite over the pure
   functions is self-contained and high-leverage. **Recommended.**
2. **USSTRATCOM/Offutt lone-bucket hardening.** Investigated 2026-07-29: the
   Omaha plume DOES compute (confirmed on the map and in the contour data), but
   Offutt is the **only target in its ~1° wind-fetch bucket** and Omaha is not a
   deck city — so if that single Open-Meteo fetch fails, the whole Omaha plume
   silently vanishes (it lands in `excluded_target_ids` + a note). Options: a
   visible UI warning when strategic targets are excluded, and/or a stronger
   retry for solo buckets. Not implemented.
3. **Deploy** — currently local-only dev servers. Needs a Python API host, a
   static host, and CORS/`FALLOUTCAST_API_URL` wiring. Real scope; only worth it
   if you want it shareable.
4. Minor: a "jump to Hawaii/Alaska" control (those plumes are off-screen at the
   default CONUS view); revisiting the naval_base/air_base/missile_defense split.

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
- **Background/hidden Browser-pane tab freezes MapLibre** (rAF is paused, so the
  style load stalls and the map stays blank; `visibilityState === "hidden"`).
  Taking a screenshot forces a compositor frame and un-sticks the style load;
  DOM-level assertions via `javascript_tool` work regardless. The app-side
  recovery (setup retry in `ensureMapReady`) means computes succeed once the
  style JSON is in, even if the canvas can't paint until the tab is visible.
- The frontend has **no unit-test suite** still (unchanged gap; #23 note).
- **Compute-before-map-ready is a guarded path now**: the clear helpers
  (`clearContours` etc.) are optional-chained because `map.getSource()` is
  undefined until `setupMapOverlay` runs — an unguarded `.setData()` there
  throws synchronously OUTSIDE the compute's try/finally and wedges the UI
  (button disabled + spinner forever, no error). `ensureMapReady` also polls
  the idempotent setup every 500 ms while waiting. Keep both properties if you
  touch that code.
- **Frozen/hidden browser-pane tabs also throttle timers** (not just rAF), so
  elapsed tickers/timeouts lag there; `read_network_requests` does not record
  the page's cross-origin :8010 fetches, and uvicorn only logs requests on
  completion — check all three before concluding "no request was sent".
- **Dev servers started inside an agent session get reaped with it.** They will
  appear to "crash" repeatedly. Don't keep restarting them from the session —
  tell the user to run `bash run-dev.sh` in their own terminal.
- **Adding a target outside the CONUS box needs a grid change.** The envelope's
  local-window path (`radius_deg`) skips any target whose window falls entirely
  outside the grid bounds, producing a bare dot with NO plume and no error.
  `grid.US_*` currently covers CONUS + HI + AK; widen it before adding targets
  beyond that, and add a coverage test (see `test_exchange_envelope.py`).
- **New target categories need three edits, or they degrade silently:**
  `scenario.py` (yield — otherwise it falls back to `_DEFAULT` and the yield
  policy misreports), plus `TARGET_COLORS` and `TARGET_LABELS` in `main.ts`
  (otherwise grey dot + raw slug in the legend).
