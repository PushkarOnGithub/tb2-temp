# transient-heater-panel-prediction

Category: Scientific Computing / Research Engineering — Engineering (heat transfer, thermophysical metrology).

## The real job

A thermal test engineer qualifying a potting compound for heater-mat panels gets raw logs from a
**two-block transient contact test** (a thin heater clamped between the specimen and a reference
block — the configuration of one-sided transient plane-source and modified-TPS instruments) and must
deliver the material's conductivity `k` and volumetric heat capacity `ρc`, then predict panel
temperatures under new heat loads. The work is a dependent chain: electrical and radiographic data
reduction → measurement model of an integrating logger → inverse heat conduction → forward
prediction in a different configuration. A subtle mistake early in the chain produces a perfect fit
and wrong physics.

## Workflow

| File | Purpose |
|---|---|
| `instruction.md` | Task statement given to the agent |
| `environment/` | Agent image: Ubuntu 24.04 (digest-pinned), python3 + numpy + scipy (apt), `/app/data/*` |
| `solution/solve.sh`, `solution/solve.py` | Reference solution (reads only `/app/data`, writes `/app/answer.json`, 0.4 s) |
| `tests/` | Separate verifier image: stdlib grader (`python3 -I -S`), truth deriver + lock, pytest report |
| `authoring/` | Author-side generator, evidence, harnesses (never read at build, solve or grade time) |

Data shipped to the agent (`/app/data`, 22 KB): `apparatus.json` (heater, base block, logger,
radiograph geometry), `sensors.csv` (thermocouple depths as measured on the radiograph),
`run_A.csv` and `run_B.csv` (210 × 2 s logger windows each: current, supply voltage, four
thermocouples), `queries.json` (six panel scenarios to predict).

Deliverable: `/app/answer.json` = `{"k": …, "rho_c": …, "predictions": {"P1": …, …, "P6": …}}`.

## Difficulty

The logs are generated exactly from the stated apparatus (closed form verified against 30-digit
Laplace inversion of the finite 60 mm stack to < 1e-5 K). Each run identifies two numbers exactly:
the specimen diffusivity `α` (from the *shape* of the four responses) and a *sum of effusivities*
`e_s + e_b` scaled by the heater power (from their *amplitudes*). Everything else comes from three
apparatus statements that change the answer while leaving the fit untouched. These are the cruxes.

| Crux | Instruction sentence (binding condition) | Tempting default | Effect of the default |
|---|---|---|---|
| **T1 Heater power** | "logged its output current and the voltage across its own output terminals" + element resistance 5.800 Ω in `apparatus.json` | `P = V·I` (or `V²/R`) | V/I is 6.172 Ω: 0.372 Ω of leads dissipate 6 % outside the stack. `k`, `ρc` +15.6 % (`V·I`) / +32 % (`V²/R`) |
| **T2 Two-sided heat flow** | "clamped between the specimen block and a borosilicate-glass base block" (base `k`, `ρc` given) | all power into the specimen, or the symmetric-sandwich `P/2` | only `e_s/(e_s+e_b)` = 41 % enters the specimen. `k`, `ρc` +143 % (all) / +22 % (half) |
| **T3 Radiographic magnification** | "measured at the detector on an edge-on radiograph … focal spot and bead plane at the distances … given" | use the listed depths as physical depths | depths are magnified by M = 1000/880 = 1.136; `α` +29 %, `k` +13.6 %, `ρc` −12 % |
| Logger model | "every value … is the mean over the 2 s interval ending at its timestamp" | sample at the timestamp, or the window anchored at the wrong end | `k` −3 % / −6 %; visible as RMS 7–15× noise (time cost, then wrong if waved away) |
| Numerics | 0.5 % + 0.01 K band; P4 and P6 are queried 4–5 s after a flux switch at or near the heated face | FD with dt ≈ 1 s, CN at dt = 0.25 s, `solve_ivp(BDF)` at default `rtol` | 0.6–3.9 % errors on P2/P4/P6 (`calibration_extras.log`) |

**Why the defaults are silent.** With half-space blocks sharing a massless heater, the specimen-side
rise is `θ(x,t) = Σ ΔP_j/A · 2/(e_s+e_b) · √τ · ierfc(x/(2√(ατ)))`. A wrong power scale is absorbed
exactly by `e_s+e_b`; a wrong split is absorbed exactly by the effusivity the agent attributes to
the specimen; a common scale on all depths is absorbed exactly by `α` (`x/√α` invariance). Every
trap-blind pipeline therefore fits both runs to the same 0.0155 K RMS as the reference solution
(pre-heating scatter 0.0141 K; see `authoring/evidence/calibration_run.log`). Cross-validating one
run against the other also passes, because both runs share the apparatus: every trap-blind fit of
run A predicts the unseen run B to 0.0155–0.0156 K RMS, the same as the reference. The agent's natural
self-checks all succeed while `k` and `ρc` are wrong by 12–190 %.

**Why the answer moves.** The graded scenarios are a different configuration: a single panel heated
by a known *net* flux and cooled by convection. There the solution depends on `k` and `ρc`
separately (early times on `e`, interior on `α`, late times on `k` and Bi = hL/k), so every silent
default fails 28–30 of the 30 hidden scenarios and all six visible ones.

**No self-check, no brute force.** No file reveals the correct power, split or depth scale through
a residual. The answer is two continuous numbers judged on 36 temperatures at 0.5 %. A search over
the 27 combinations of the three silent readings (power × split × depth scale) cannot be scored
against anything the agent holds, because all 27 fit the logs equally well. Guessing `k`, `ρc` to 0.5 % is hopeless.

**Why it fits 600 s.** Setup is small (five files, 22 KB, all documented). Once the cruxes are seen,
the solution is about 150 lines and runs in under a second. The tempting path is short and ends in a
confident, well-formed wrong answer (committed-wrong, the countable failure).

## Reference solution

`solution/solve.py` (0.4 s, numpy/scipy):

1. **Depths.** M = SID/(SID − OID) = 1000/880; true depth = listed depth / M.
2. **Power.** Detect current plateaus (current changes only at timestamps) and use
   `P = R_element · mean(I²)` per plateau. The logged `V/I` = 6.172 Ω exceeds the 5.800 Ω element,
   so `V·I` would include the lead loss.
3. **Model.** Two half-spaces share the massless heater plane. The Fourier numbers over 420 s are
   0.042 (specimen) and 0.077 (base), so the outer faces are never felt. The window means are
   computed in closed form from `∫₀^τ √s·ierfc(c/√s) ds = 4τ^{3/2}·i³erfc(c/√τ)`, differenced over
   each (t − 2 s, t] window.
4. **Fit.** Nonlinear least squares on all 1680 thermocouple values for `e_s+e_b`, `α_s` and one
   initial temperature per run. RMS 0.0155 K equals the pre-heating scatter.
5. **Split.** `e_s = (e_s+e_b) − √(k_b ρc_b)`; then `k = e_s√α`, `ρc = e_s/√α`. Result: k = 0.58629
   (true 0.5862) and ρc = 1.63890e6 (true 1.6385e6).
6. **Panels.** Eigenfunction series with `μ tan μ = Bi`, steady part plus transient, Duhamel
   superposition over flux segments. Enough terms are kept that `exp(−μ²ατ_min/L²) < e⁻⁵⁰`.

How it rules out the alternatives: steps 1, 2 and 5 are each forced by one stated fact (projection
geometry, terminal-voltage measurement, two-sided contact). The fit cannot arbitrate between them,
which is the point. An independent finite-volume solver of the whole stack, which never derives the
split, reproduces k and ρc to 0.06 % (`authoring/evidence/independent_solver.py`).

## Fairness and real-world counterparts

- **T1**: two-wire versus four-wire power measurement. Guarded-hot-plate and transient methods
  require the heater power measured across the element (voltage taps), because supply readbacks
  include lead and connector drops. The evidence witnesses it: V/I = 6.172 Ω in every powered
  window versus the stated 5.800 Ω element.
- **T2**: one-sided transient sensors (TPS/MTPS) with a backing of known effusivity. Heat divides
  between the two contacts in proportion to effusivity. The "identical halves, P/2" convention
  holds only for a symmetric sandwich, which this is not.
- **T3**: projection radiography magnifies by SID/(SID − OID). Thermocouple-bead verification by
  X-ray is routine; dimensions read off the detector must be divided by M.
- **Logger**: integrating ADCs (multi-PLC averaging) report window means, time-stamped at the
  window end.

Every binding condition appears once, in plain words, in `instruction.md`. A methodical expert who
checks each stated fact avoids every trap without guessing. Every graded value is forced:
α and `e_s+e_b` are witnessed by the logs, and the split, power and depth scale follow from stated
facts. See `authoring/README.md` for the identifiability argument and the rival-reading enumeration.

## Verification

- **Grader** `tests/check_submission.py` runs as `python3 -I -S` (stdlib only). It reads only
  `/app/answer.json` (lstat, `O_NOFOLLOW`, regular file, ≤ 64 KiB, strict JSON, no `NaN`, no
  duplicate keys). It checks the contract first (exact keys, number types, ranges, exact scenario
  ids), then accuracy. It never evaluates submission content as code.
- **Truth** comes from `tests/derive_truth.py` in a second isolated interpreter. It regenerates the
  shipped data byte-for-byte from `tests/instance.py`, recomputes the six visible and 30 held-out
  answers, and checks a SHA-256 lock over **instance bytes + hidden constants + graded answers**
  (`tests/lock.json`). The digest was reproduced identically under Python 3.13 (authoring host) and
  3.12 (verifier image).
- **Held-out inputs**: 30 scenarios drawn from a fixed seed inside the verifier, never shipped,
  disjoint from the visible ones. They are evaluated with the agent's reported `k`, `ρc` through
  the stdlib eigen-series. That series matches Talbot inversion to 2e-15 relative.
- **Tolerance**: |T − T_true| ≤ 0.005·(T_true − T_init) + 0.01 K on all 36. Over 60 fresh noise
  realisations the reference pipeline's spread is 2.0e-4 (1σ) on k and 1.8e-4 on ρc. Its worst
  graded temperature uses at most 12 % of the band (median 3.6 %), so a correct solution has about
  9× headroom. Every silent-trap variant leaves at least 34 of the 36 graded temperatures outside
  the band. A wider band would only admit wrong methods; a narrower one would start rejecting
  converged numerics.
- **Reward plumbing**: grader exit 0 with the verdict line and pytest exit 0 gives reward 1. Grader
  exit 1 gives reward 0. Anything else is an infrastructure error with no reward file (see the header
  of `tests/test.sh`).

## Hidden adversarial tests

The checks run in the verifier, plus the attack battery recorded in
`authoring/evidence/calibration_run.log`: 52 runs, all as expected.

- 13 wrong-method artifacts: each trap alone, the compound default, two logger anchorings and four
  unconverged numerical schemes. All score 0.
- 18 exploit probes: symlinks to verifier data, `/etc/passwd` and `/dev/zero`; a FIFO; a directory;
  a file over 64 KiB; code-injection strings; NaN/Infinity; `1e999`; duplicate keys; booleans; a
  20 000-level nesting bomb; extra and missing keys; guessed hidden ids; out-of-range `k`; an answer
  built only from shipped objects; correct visible predictions with a perturbed model. All score 0,
  with a flag-file check showing no side effect.
- 12 legitimate serialisations of a correct answer (compact, indented, reordered, exponent notation,
  integer `rho_c`, rounded, CRLF, no newline, BOM, escaped keys, padding). All score 1.
- A lying ground-truth module (`instance.py` rewritten to agree with a trap-blind answer) ends as an
  infrastructure error, not a reward.

## Expected frontier-model behaviour (predicted, not yet measured)

Agent trials were not run while authoring. What follows is the expected first-ten-minutes path,
grounded in the discriminator harness.

1. **Read and fit.** The agent reads the files and writes a forward model. The most common choice
   is a single-domain flux model of the specimen or an FD solver, which assumes the power enters the
   specimen alone. Less often it models the full stack, which handles T2 automatically.
2. **Power.** Electrical power from logged `V` and `I` is reflexively `V·I`. Spotting that the
   supply voltage includes leads requires connecting two separate statements and checking V/I.
3. **Depths.** The sensor table's depths look like ordinary metadata. Projection magnification has
   to be recognised from one clause.
4. **Verify.** The fit reaches noise-level RMS, the second run cross-validates, and the agent
   commits. This is weak verification: none of its checks cover the binding conditions.
5. **Numerics.** Agents who use FD for the panels with dt ≈ 1 s, or `solve_ivp` defaults, miss the
   switch-adjacent scenarios.

Failure modes differ between trials (power, split, depths, logger, numerics), so the pass@k
analysis should see varied failures, not one underspecified test failing uniformly.

## Difficulty calibration

Estimated per-crux catch rates for a top agent at 600 s: T1 0.5–0.65, T2 0.6–0.75, T3 0.65–0.8,
logger 0.75–0.85 (visible), numerics 0.8–0.9. That gives P(solve) ≈ 0.10–0.30 per trial and
P(≥3 of 5 fail) ≈ 0.8–0.99. These are estimates; pre-measuring on the built image is recommended.
Difficulty knobs, all cheap to regenerate (`authoring/generate.py`):

- lead resistance (T1 size);
- base-block material (T2 size and direction);
- radiograph geometry (T3);
- logger interval;
- how close visible scenarios sit to flux switches.

## Effort

An expert who sees the three apparatus facts needs about 45–60 min: data reduction 10 min, half-space
model with exact window means 15 min, fit 5 min, panel series 15 min. The estimate is
`expert_time_estimate_hours = 1.0`. The oracle runs in 0.4 s; the verifier in about 0.5 s.
