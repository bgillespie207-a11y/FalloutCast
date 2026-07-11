# Tier-1 Engine Spec — Multi-Layer Particle Advection

Status: design, ready to implement. Reuses the Tier-0 cloud model and the entire
grid → contour → decay → API pipeline unchanged.

---

## 1. What changes vs Tier-0

Tier-0 (WSEG-10) collapses the whole atmosphere into **one effective wind** and
draws an idealized smear. It physically cannot curve the plume, because curvature
comes from wind *shear* — wind that changes direction/speed with altitude — and a
single vector has no shear to express.

Tier-1 keeps the vertical dimension. It releases radioactive particles across the
cloud's full height, lets each one **fall at its own speed through the real winds
at each altitude it passes**, and sums where they land. That single change is the
entire source of realism. Everything below is the machinery to do it.

---

## 2. Physical picture (the one paragraph that matters)

A surface burst lofts soil-derived radioactive particles across a tall column
(thousands to 50,000+ ft for megaton yields). Particles then fall back down.
A **big, heavy** particle falls fast, only samples the low-level wind, and lands
close-in roughly straight downwind. A **small, light** particle falls slowly,
stays aloft for hours, and drifts through many wind layers each pushing it a
different way. Sum millions of particles of every size from every altitude and
the collective footprint hooks and fans — the real fallout shape. Tier-1
reproduces this by discretizing "every size" and "every altitude" into a tractable
set of trajectories.

---

## 3. Model components

### 3.1 Cloud source (reused from Tier-0)
`wseg10.py` already computes the stabilized cloud center height `H_c` and vertical
spread `σ_h` from yield. Tier-1 uses these as the **initial condition**: particles
are released over a vertical Gaussian centered at `H_c` with spread `σ_h`,
discretized into ~`N_z` release altitudes. No new cloud model needed.

### 3.2 Particle size distribution (`sizedist.py`)
Fallout particle diameters are modeled as **lognormal** (the DELFIC assumption).
If `d` is lognormal, `ln d ~ Normal(μ_ln, σ_ln²)`, with number density

```
f(d) = 1 / (d · σ_ln · √(2π)) · exp( −(ln d − μ_ln)² / (2 σ_ln²) )
```

Discretize into `N_d ≈ 15` bins with **log-spaced edges** (equal diameter ratios)
across ~20–2000 µm. Each bin gets a representative diameter `d_b` (geometric-mean
of its edges) and an activity share `a_b` (§3.3).

> Coefficient to pin: `μ_ln`, `σ_ln` for a surface land burst. DELFIC defaults
> exist in the literature; use those rather than inventing them. Structurally the
> code takes them as parameters so the source distribution is swappable.

### 3.3 Activity apportionment
v1 default: **activity ∝ particle mass ∝ d³**, so a bin's activity share is
`a_b ∝ ∫_bin d³ f(d) dd`, normalized to sum to 1. This is the simple, transparent
choice. It is deliberately swappable because it's *wrong in a known direction*:
**fractionation** means volatile fission products condense late onto smaller,
higher-drifting particles, shifting activity toward the small end and lengthening
the far-downwind tail. A DELFIC fractionation rule is the M1.5 upgrade; the
interface (`activity_shares(bins) -> array`) stays identical.

### 3.4 Fall (terminal settling) velocity (`fallvelocity.py`) — the core physics
Terminal velocity is where gravity balances aerodynamic drag. Force balance on a
sphere of diameter `d`, particle density `ρ_p`, in air of density `ρ_a`:

```
(π/6) d³ (ρ_p − ρ_a) g  =  (1/2) ρ_a v_t² (π/4 d²) C_d
```

Solving for `v_t`:

```
v_t = √( 4 g d (ρ_p − ρ_a) / (3 ρ_a C_d) )
```

The snag: the drag coefficient `C_d` depends on Reynolds number `Re = ρ_a v_t d/μ`,
which depends on `v_t` — implicit. Two regimes:

- **Stokes (small particles, Re ≲ 1):** `C_d = 24/Re`, which collapses the above to
  the clean closed form
  ```
  v_t = (ρ_p − ρ_a) g d² / (18 μ)
  ```
  Valid up to roughly 50–80 µm at sea level. Most sub-100 µm particles live here.

- **Intermediate/turbulent (larger particles):** Stokes over-predicts. Use a
  drag correlation, e.g. Schiller–Naumann (good to Re ≈ 800):
  ```
  C_d = (24/Re) (1 + 0.15 Re^0.687)
  ```

**Recommended implementation — solve without iteration via the Best (Davies)
number.** Note that `C_d · Re²` is independent of velocity:

```
C_d Re² = 4 ρ_a (ρ_p − ρ_a) g d³ / (3 μ²)        # "Best number" N_Be, computable directly
```

Invert a correlation of `Re` vs `N_Be` (Clift–Gauvin form) to get `Re`, then

```
v_t = Re · μ / (ρ_a d)
```

This is fully explicit and **vectorizes cleanly** over all bins × altitudes ×
timesteps — no per-particle iteration loop. Strongly preferred for the NumPy port.

### 3.5 Atmosphere model (altitude dependence) — why the same particle falls faster up high
`ρ_a` and `μ` both appear above and both vary with altitude, so `v_t` is
recomputed as the particle descends. Thinner air aloft → less drag → **faster
fall up high, slower near the ground.** Use the US Standard Atmosphere 1976:

- Temperature (troposphere): `T(z) = 288.15 − 6.5·z` K (z in km) up to 11 km, then
  constant 216.65 K to 20 km.
- Pressure: barometric formula; Density: `ρ_a = P / (R_specific · T)`,
  `R_specific = 287.05 J/(kg·K)`.
- Viscosity (Sutherland's law):
  `μ(T) = 1.716e−5 · (T/273.15)^1.5 · (273.15 + 110.4)/(T + 110.4)` Pa·s.

These are standard, high-confidence constants — no sourcing risk.

### 3.6 Winds (reused from Open-Meteo)
Tier-1 consumes the **full `WindProfile`** we already fetch (pressure-level winds +
geopotential heights) — it does *not* call `reduce_profile` (that's Tier-0's
collapse-to-one-vector step). Horizontal wind `(u, v)` at a puff's current altitude
is linearly interpolated between profile levels. Above the top level, hold the top
wind; below the bottom, hold the bottom.

> Consequence for the API: a **manual single-vector wind override cannot drive
> Tier-1** (it has no vertical structure). Manual mode falls back to Tier-0. Note
> this in the schema.

### 3.7 Horizontal diffusion (puff growth)
Each released puff isn't a point; turbulence spreads it. Grow a horizontal spread
`σ_puff` with time-aloft, `σ_puff² += 2 K dt` (K = eddy diffusivity), or the
simpler engineering form `σ_puff(t) = σ_0 + c · t^p`. This softens the footprint
and prevents unphysically thin filaments. Keep `K`/`c` as tunables.

### 3.8 Deposition & dose conversion
When a puff reaches the ground (`z ≤ 0`), deposit its activity `a_b`/`N_z` onto the
grid as a 2-D Gaussian with spread `σ_puff` centered at its landing `(x, y)`. Sum
all puffs' contributions per cell → deposited activity density → **H+1 reference
dose rate** via the standard activity-to-dose-rate conversion (same normalization
philosophy as WSEG-10's built-in factor; Glasstone & Dolan gives the conversion).
Then `decay.py` handles any H+t and accumulated dose — unchanged.

---

## 4. Algorithm (vectorized pseudocode)

```
inputs: yield, fission_fraction, ground_zero, WindProfile
        N_d bins, N_z release altitudes, dt, t_max

# --- setup (once) ---
H_c, sigma_h        = cloud_params(yield)                 # from wseg10
bins                = lognormal_bins(N_d, d_min, d_max)   # (d_b, a_b) per bin
z_release, w_z      = gaussian_layers(H_c, sigma_h, N_z)  # altitudes + weights

# one puff per (bin, release altitude): stack into flat arrays of length N_d*N_z
x, y   = zeros, zeros
z      = tile(z_release over bins)
d      = repeat(d_b over altitudes)
act    = (a_b * w_z) * yield * fission_fraction           # activity carried
sigma  = full(sigma_0)
alive  = ones(bool)

grid   = zeros((ny, nx))                                  # deposited activity

# --- march all puffs together ---
for t in arange(0, t_max, dt):
    if not alive.any(): break
    u, v      = interp_wind(WindProfile, z[alive])        # vectorized interp
    x[alive] += u * dt
    y[alive] += v * dt

    rho, mu   = atmosphere(z[alive])                      # US Std Atm 1976
    v_t       = terminal_velocity(d[alive], rho, mu)      # Best-number, no iter
    z[alive] -= v_t * dt

    sigma[alive] = grow(sigma[alive], dt)

    landed = alive & (z <= 0)
    deposit_gaussian(grid, x[landed], y[landed], act[landed], sigma[landed])
    alive &= ~landed
    # optional: any still alive at t_max -> global fallout, drop (out of scope)

dose_h1 = activity_to_dose_rate(grid)                     # -> same DoseGrid format
```

`interp_wind`, `atmosphere`, `terminal_velocity`, `deposit_gaussian` are all pure
array ops. Scale: `N_d·N_z ≈ 150` puffs, `dt` 1–5 min, `t_max` ~24–48 h → cheap.

---

## 5. Numerical defaults (all tunable)

| Param | Default | Note |
|-------|---------|------|
| `N_d` size bins | 15 | log-spaced 20–2000 µm |
| `N_z` release layers | 10 | Gaussian over `H_c ± ~2σ_h` |
| `dt` | 120 s | 1–5 min fine |
| `t_max` | 24 h | particles still aloft → global, dropped |
| `ρ_p` | ~2600 kg/m³ | silicate; pin from DELFIC |
| diffusion `K` | tunable | calibrate to footprint width |

---

## 6. Coefficients to pin from primary sources (don't invent)

1. Lognormal size params `μ_ln`, `σ_ln` — DELFIC surface-land-burst defaults.
2. Particle density `ρ_p` — DELFIC.
3. Activity-to-H+1-dose-rate conversion — Glasstone & Dolan, *Effects of Nuclear
   Weapons*.
4. (M1.5, implemented) Fractionation activity-vs-size rule — `sizedist.py`
   now models the refractory (volume ∝ d³) / volatile (surface ∝ d²) split
   structurally (see its module docstring for the derivation), opt-in via
   `lognormal_bins(fractionation=...)`. The bulk refractory/volatile activity
   partition fraction (`F_VOLATILE_PLACEHOLDER`) is still unsourced — flagged
   in code, needs a DELFIC/Freiling value before this is more than
   directionally correct.

High-confidence, no sourcing needed: US Standard Atmosphere 1976, Sutherland's law,
Stokes law, Schiller–Naumann / Clift–Gauvin drag, lognormal math.

---

## 7. Integration & API changes

- `/plume` gains `tier: 0 | 1` (default 0 for now, flip to 1 once validated).
- Tier-1 requires a fetched `WindProfile`; **manual wind → Tier-0 fallback** (422 or
  silent downgrade with a `wind.source` note — decide; I lean on a clear note).
- Output is a `DoseGrid` in the existing format → `grid`/`contour`/`decay` and the
  whole GeoJSON response are **unchanged**.

## 8. New modules

- `physics/atmosphere.py` — US Std Atm 1976: `ρ_a(z)`, `μ(z)`.
- `physics/fallvelocity.py` — `terminal_velocity(d, ρ_a, μ)` via Best number.
- `physics/sizedist.py` — lognormal binning + activity shares.
- `physics/tier1.py` — the advection engine (§4), returns a `DoseGrid`.
- Everything else reused.

## 9. Test plan (assert what Tier-0 *can't* do)

1. **Shear produces curvature.** A veering wind profile yields a footprint whose
   hotline bearing rotates with distance; a uniform profile does not. This is the
   headline capability test.
2. **Size sorts by range.** Heavier bins deposit closer to GZ; lighter bins reach
   farther. Assert monotonic landing-distance vs diameter under uniform wind.
3. **Altitude effect on fall speed.** `terminal_velocity(d, high-alt) >
   terminal_velocity(d, sea-level)` for fixed `d`.
4. **Activity conservation.** Total deposited activity (within `t_max`) ≈ released
   activity, minus the explicitly-dropped still-aloft fraction.
5. **Stokes limit.** For small `d`, Best-number solver matches the closed-form
   Stokes velocity to tight tolerance.
6. **Reduces toward Tier-0.** With a near-uniform wind profile, the Tier-1 footprint
   should resemble Tier-0's order of magnitude and reach (sanity, not identity).
7. **Footprint validation.** Compare one case against a published DELFIC or HYSPLIT
   footprint for shape/scale before trusting Tier-1 shapes in the UI.
   **Status: scaffolding only, not a validation.** `falloutcast/validation/
   reference_cases.py` documents three research passes assembling a
   candidate case (Small Boy, 1962-07-14, NTS Area 5). Progress:
   - **Wind: CLOSED.** `small_boy_wind_h5min()` digitizes a real balloon/
     tower sounding straight from the primary source (DNA 1251-1-EX Vol. I,
     Table 109) -- not a placeholder.
   - **Burst height: precisely sourced, still a mismatch.** Confirmed (both
     the primary source's "Tower, over Nevada soil" and an independent
     secondary shot table agree) as a ~3 m tower/stand, not this project's
     assumed HOB=0. None of the other historical shots with published
     DELFIC/HYSPLIT comparisons are true surface bursts either (mostly
     300-700 ft tower shots).
   - **Target footprint: still no digitized contour**, but no longer
     nothing -- the primary source's own prose gives a real order-of-
     magnitude/bearing check (fallout reached 250-400 mi downwind by late
     D+1, peaking D+2, tracked to western Nebraska). `scripts/
     validate_footprint.py` runs Tier-1 against the real wind and prints
     this alongside the model's own bearing/reach for a human to eyeball --
     bearing came out close (67 deg modeled vs. 58 deg to western Nebraska);
     reach undershot (129 mi vs. reported 250-400 mi by D+1). The actual
     contour plates (DNA 1251-1-EX Figures 329-332) are scanned images, not
     OCR-legible as geometry -- digitizing those from the scan would close
     this gap for real.

   `tests/test_footprint_validation_harness.py` tests the harness code
   (including the real wind digitization) but still asserts no physics
   claim -- see the module docstring for exactly what's left.

## 10. Open decisions (your call)

- Manual-wind-in-Tier-1: hard 422 vs silent Tier-0 downgrade-with-note.
- `t_max` and the treatment of the still-aloft fraction (drop vs report as a
  separate "regional/global" mass number).
- Whether M1 ships the ensemble-wind uncertainty band now or right after.
