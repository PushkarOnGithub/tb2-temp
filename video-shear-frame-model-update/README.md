# Video shear-frame model update (rolling shutter, output-only test)

## Real job and deliverable

A structural-dynamics research engineer updates the finite-element (lumped
shear-frame) model of a laboratory specimen from vision-based measurements: a
consumer-grade rolling-shutter camera filmed an operational (shaker-driven,
force not recorded) vibration test. The deliverable is the updated storey
stiffness vector, which the lab then uses to predict how the frame's natural
frequencies change when equipment is added or a storey is stiffened. That
"what-if" prediction is exactly what the verifier grades, on configurations
the agent never sees.

The agent writes `/app/output/model.json` = `{"k": [k1, k2, k3, k4]}` (N/m).

## Task statement

`instruction.md` is the exact text given to the model (about 450 words, closing line
as required by the pipeline). It discloses the model family, the
rolling-shutter timing convention, the as-tested mass rule, the output
contract, the held-out family, count and split (19 mass-only and 21
mass-plus-stiffness variants), the tolerance and the binary reward rule. It
also pins the rules that decide the answer, phrased as properties of the
specimen and the camera:

* "Damping is classical, ... so every mode shape is real: referred to a common
  instant, the floor motions of a mode are in phase or in antiphase." and "The
  camera has no anti-aliasing filter, and natural frequencies may exceed half
  the frame rate F. A mode of frequency f appears in the video at f - qF, for the
  integer q that puts it between -F/2 and F/2. When f - qF is negative, the video
  shows the mode at qF - f through its negative-frequency component, so the
  shape identified there carries the rolling-shutter phase of frequency -f: it
  is the complex conjugate of the shape the mode would show at +f." Together
  these fix the continuous-time branch of every identified mode, including the
  sign convention for a mode folded from the upper half of a band.
* "Several stiffness vectors share the frame's four natural frequencies; the
  specimen's k is the one whose mode shapes also match the measured ones." This
  fixes the stiffness branch.

It does not say which mode is folded or at what frequency; the agent has to
apply these properties to its own identified modes.

## Environment and inputs

Agent image (`environment/Dockerfile`): Ubuntu 24.04 (pinned by digest),
Python 3.12, `numpy==2.1.3`, `scipy==1.14.1`, network `public`.

| file | size | content |
|---|---|---|
| `/app/data/tracks.csv` | 612 KB | 15 000 frames (600 s at 25 fps): `t_s,T1,T2,T3,T4`, positions in pixels (0.001 px) |
| `/app/data/targets.json` | 0.3 KB | label -> floor, image row of the target centre, mm per pixel |
| `/app/data/test_record.json` | 0.4 KB | design floor masses, items mounted during the test, shaker floor, camera row period |

The data are synthetic by construction (`tests/instance.py`, standard library
only): a 4-DOF shear frame with Rayleigh damping driven at floor 1 by a
zero-order-hold Gaussian force (2 ms steps), integrated exactly in complex
modal coordinates, sampled at every target's rolling-shutter capture time,
converted to pixels with per-target scales and rest positions, plus 0.012 px
tracker noise. Hidden specimen: as-tested masses 5.10, 5.25, 5.95, 7.50 kg
(design 4.85 kg on floor 3 plus a 1.10 kg logger), stiffnesses
4930, 18880, 5080, 5100 N/m (storey 2 is braced), a0 = 0.147 s^-1,
a1 = 9.3e-5 s. True natural frequencies 1.755, 4.673, 7.652, 14.524 Hz;
the frame rate is 25 fps, so the fourth mode lies above the 12.5 Hz Nyquist
frequency and appears in the video at 10.47 Hz.

## Verification and grading criteria

* Separate verifier image (`tests/Dockerfile`, no network). `test.sh` runs the
  authoritative grader `python3 -I -S /tests/check_submission.py`, requires its
  exact verdict line, then renders an itemised pytest report; reward 1 only if
  both succeed. Exit-status mapping (result vs infrastructure error) is
  documented at the top of `test.sh`.
* Contract (checked first, field-specific messages): bounded regular file
  (`lstat`, no symlink/FIFO/device, <= 64 KiB), UTF-8 JSON object with the
  single key `k`, four JSON numbers in [1, 1e9]; duplicate keys, NaN/Infinity,
  strings and booleans rejected; nothing is ever evaluated as code.
* Accuracy: for 41 configurations (the tested frame plus 40 held-out variants
  generated only inside the verifier from a fixed SHA-256 counter stream),
  the four undamped natural frequencies of `K(k)` with the as-tested masses
  (plus the variant's added masses and stiffness factor) must each be within
  3 % of the truth, compared in ascending order: 164 graded values.
* Truth is regenerated, never stored: `derive_truth.py` (stdlib, isolated
  interpreter) rebuilds the three shipped files byte for byte, computes the 164
  true frequencies with two independent eigen-solvers (Jacobi rotations and
  Sturm-sequence bisection; agreement 1e-9 required) and checks one SHA-256
  digest over the shipped bytes **and** the graded answers. A forged generator
  that reproduces the shipped files but lies about the answers ends as an
  infrastructure error (probe I01).
* Why 3 %: correct pipelines on this instance land at 0.08 % (oracle),
  0.54 % (frequency-domain decomposition) and 1.26 % (stiffness projected from
  noisy mode shapes, no frequency refinement). Over 10 further noise
  realisations of the same specimen (`authoring/evidence/seed_sweep.log`) the
  worst cases are 0.30 %, 0.95 % and 1.14 %, while the nearest wrong pipelines
  never come closer than 6.6 % (positions left in pixels, shape-based
  stiffness), 9.5 % (design masses) and 31 % (aliasing default). A tighter band
  would start to reject correct shape-based estimators; a looser one would
  start to admit the pixel-unit error.

## Reference solution

`solution/solve.py` (numpy, 0.2 s):

1. Map tracker labels to floors, convert pixels to mm with each target's own
   scale, remove the static image positions; compute each floor's shutter
   delay `delta_j = row_j * tau` (2.9 to 16.4 ms).
2. Covariance-driven stochastic subspace identification (output-only), order
   8: four discrete poles `lambda_r` and complex shapes `psi_r`.
3. **Branch resolution.** The samples fix only `lambda_r = exp(s_r * dt)`; the
   continuous pole is `s_r = (Log lambda_r + 2 pi i n)/dt` or its conjugate.
   Because floor j is sampled at `t_n + delta_j`, its shape component carries
   `exp(s_r * delta_j)` with the true continuous pole. Classical damping means
   real mode shapes, so for each mode the branch is the one whose
   shutter-corrected shape `psi_r * exp(-s_r * delta)` is real. Result: modes
   1-3 are unaliased; mode 4 is the reflected alias, 25 - 10.466 = 14.534 Hz
   (shape imag/real 2.2e-3 against 0.16 for the runner-up branch).
4. Mass-normalise with the as-tested masses, project `M Phi W^2 Phi^T M` onto
   the shear-frame pattern (gives a starting k and selects the stiffness branch),
   then Newton-refine k on the four natural frequencies with analytic
   eigenvalue sensitivities (the identified frequencies are good to about
   0.05 %, the shapes only to about 1 %); a MAC check confirms the refinement
   stayed on the branch the shapes selected.

Two further, independent checks select the same branch (identifiability log):
the stiffness matrix rebuilt from the modes has the shear-frame pattern only for
the true assignment (residual 3.0e-3 vs 4.9e-2 for the runner-up and 1.4e-1
for the principal branch), and the Rayleigh-line criterion (decay rates
sigma_r = a0/2 + a1 w_r^2/2 with a0, a1 >= 0) ranks the same assignment first
(residual 0.029 vs 0.048 for the runner-up and 0.118 for the principal branch;
output-only damping estimates are noisy, so this pin is the weakest of the three).

Expert time once the crux is seen: well under an hour (estimate 1.5 h in
`task.toml` including reading and checking).

## Difficulty

**Crux 1: which mode is folded (a stated rule the data never flag).** The
instruction says modes may lie above half the frame rate and appear folded, but
nothing in the data points at one. The textbook output-only pipeline (SSI,
NExT-ERA, FDD or Welch peaks) reports four clean modes at 1.75, 4.67, 7.65 and
10.47 Hz, all comfortably below 12.5 Hz, with ordinary damping ratios and the
apparent modes in the expected order (the fourth shape is almost zero at the
roof, so its sign pattern is not diagnostic). Updating four storey stiffnesses
to those four frequencies succeeds *exactly* (residual 4e-31) and returns a
plausible frame, k = 6983, 6984, 6665, 3848 N/m, which fails 71 of the 164
graded frequencies with errors up to 31 % (N1, N3, N5). An agent that applies
the folding statement only where the data look suspicious applies it nowhere.

**Crux 2: applying the stated sign convention to the folded mode.** The
instruction states that a mode folded from the upper half of a band is seen
through its negative-frequency component; the agent still has to recognise that
mode 4 is such a mode and carry the convention through its own identification
code (pole, shape and shutter phase must use the same signed frequency). A mode at 14.53 Hz has components at +14.53 and -14.53 Hz; at 25 fps
it is the -14.53 Hz component that lands at +10.47 Hz, so the shape identified
at +10.47 Hz carries the shutter phase of -14.53 Hz. Referring that shape to a
common instant with +14.53 Hz instead, which is what the habitual
positive-frequency bookkeeping does, makes it *less* real (imag/real 0.45) than
leaving the mode at 10.47 Hz (0.38), and the most nearly real positive
candidate is 85.47 Hz (0.16). An agent that slips here keeps 10.47 Hz (31 %) or
takes 85.47 Hz (k_1 = 1.5 MN/m, 610 %; N13). Only the signed frequency -14.53 Hz,
equivalently the conjugate shape referred at +14.53 Hz, gives a real shape
(imag/real 0.002, the next branch 73 times worse). The decay-rate route (the
Rayleigh line implied by C = a0*M + a1*K) avoids the sign issue but separates
the true assignment from the runner-up by only 0.029 vs 0.048 with output-only
damping estimates.

Mishandling the shutter delays is silent as well. Resampling every channel onto
the frame time with a spline (the usual "fix") is wrong for a folded component,
because the interpolant reconstructs the 10.47 Hz image (N8 produces a negative
stiffness). A physical spectral fit that models the folding but ignores the
shutter delays converges to a 27 % wrong model, and one that models the shutter
but not the folding converges to a 25 % wrong model (independent_solver.log).

**Trap A (authoritative source): as-tested masses.** Instruction sentence:
"Floor j ... is a rigid lumped mass m_j equal to its design mass plus everything
mounted on it during the test." The 1.10 kg logger on floor 3 is listed only in
`test_record.json` under `mounted_during_test`. Using the design masses changes
no fit and no residual (masses are invisible in output-only data), but misses
held-out frequencies by up to 9.7 % (N6). Real-world counterpart: instrumentation
and DAQ hardware left on a specimen during a test is routinely forgotten in
model updating.

**Trap B (look-alike labels): tracker label != floor.** Instruction sentence:
"`/app/data/targets.json`: for each target, the floor it is fixed to, ...".
Trackers number targets in creation order. Here T1..T4 are floors 2, 4, 1, 3. Reading
T1..T4 as floors 1..4 lands, after frequency refinement, on an isospectral frame
that matches all four tested frequencies and misses held-out ones by 18 % (N10).

**Isospectral stiffness vectors (stated rule, procedural).** Two positive
stiffness vectors reproduce the four true frequencies with the as-tested masses:
the true one and k = 36674, 5045, 4475, 2913 N/m. The instruction states that
the specimen's k is the one whose mode shapes also match. Frequency-only
updating lands on the twin (N12, 18 %) or, from most uniform starts, on a local
minimum (N11, 19 %); the mode shapes (MAC 1.00 vs 0.60) separate them.

**Documented mechanics with an invariance band (category b, disclosed):**
per-target image scales (mm per pixel) matter for estimators that build
stiffness from mode shapes (N9, 6.0 %; the stated shape-match rule makes such
estimators the natural choice), but a frequency-refined estimator is
insensitive to per-channel real scaling (mutation run). Ignoring the shutter
delays when forming shapes (after the branch is known) costs precision but
stays inside tolerance on this instance (N7, 1.8 %; 1.9-4.3 % across the 10
realisations of the seed sweep, so it is not counted as a discriminator).

**Why brute force does not fit.** The deliverable is continuous (4 stiffnesses
graded to 3 % through 164 frequencies), so guessing is hopeless. The force is
not recorded, so no deterministic time-domain simulation can be fitted to the
tracks and used as a self-check; an earlier impact-test version of this task
was abandoned because a direct time-domain fit from a uniform start found the
truth without the insight. The only searches that can test candidates against
the evidence (branch enumeration scored by shutter realness with the correct
sign, shear pattern or Rayleigh line; or a spectral fit with explicit folding
and shutter phases) are the insight itself.

**Why the agent has no self-check.** Every natural check passes for the default:
identified modes reproduce the sampled covariance, the updated frame reproduces
the identified frequencies exactly, apparent frequencies sit below Nyquist,
mode ordering is as expected, and the obvious realness test of the obvious fold
(+14.53 Hz) comes out worse than no fold at all. There is no file, tool or
oracle that evaluates a candidate model.

## Expected failure modes of frontier models and why each is hard to detect

| # | likely behaviour | why it is silent |
|---|---|---|
| 1 | Reads the folding sentence but finds no mode that looks folded, takes SSI/FDD/peak frequencies at face value and updates k to them (N1/N3/N5). | Exact frequency match; every value below Nyquist; plausible near-uniform frame. "Below Nyquist" is a common but fallacious sanity check: folded frequencies are always below Nyquist. |
| 2 | Tests the fold but refers the identified shape at a positive candidate frequency, contrary to the stated convention (N13), or assumes the non-reflected fold fs + f (N4). | The true fold then looks *worse* than no fold (0.45 vs 0.38) and the least-complex candidate is 85.47 Hz; each candidate yields a well-formed frame. The convention is stated, but it has to be applied inside the agent's own pole/shape bookkeeping. |
| 3 | Treats the rolling shutter as a preprocessing nuisance: resamples channels by interpolation (N8), or ignores it (N7), or corrects shapes with the apparent pole. | Interpolation assumes band-limited signals, which is exactly what fails; the output still looks like four modes. |
| 4 | Uses design masses (N6). | Masses never enter an output-only fit; all diagnostics are unchanged. |
| 5 | Assumes T1..T4 = floors 1..4 (N10). | Frequencies are unaffected; refinement lands on an isospectral frame that matches the tested frame exactly. |
| 6 | Frequency-only model updating from a generic start (N11/N12). | Four equations, four unknowns, an exact or near-exact match; only the stated shape-match rule rejects it, and nothing in the fit prompts the agent to check it. |
| 7 | Leaves pixels as units and builds K from shapes (N9). | A common scale cancels in mass normalisation, so "units don't matter" sounds right; per-target scales do not cancel. |
| 8 | Physical spectral fit without folding (25 %) or without shutter phases (27 %). | The optimiser converges and the residual looks like a normal model-error residual. |

## Difficulty calibration

Each independent crux has a fast, confident, well-formed wrong default. Rough
per-trial estimates for a strong agent now that both deciding rules are stated:
applies the folding rule to every mode, including ones that look ordinary, 0.8;
carries the stated sign convention through its own pole/shape code (or uses the
Rayleigh line) 0.7;
respects the as-tested mass rule 0.85; reads the label map 0.95; keeps
per-target scales in a shape-based estimator 0.9; completes output-only
identification correctly inside 600 s 0.9. Product: about 0.35-0.4 per trial,
which gives at least 3 failures in 5 trials with probability about 0.65-0.75.
Stating the fold, the sign convention and the shape-match rule (required by the
contested-conventions review) lowered the difficulty: what remains is applying
stated physics to modes that the data do not flag, inside a long output-only
identification chain, plus the mass, label and scale traps. If the difficulty
gate reports the task as too easy, the structural lever is a second folded mode
(new instance, same verifier design). Most failures should be committed-wrong
rather than in-progress: the default pipeline finishes in a few minutes and
every check it runs passes. The task separates models on one decision, whether
they treat the identified frequencies as the frame's frequencies. Pipeline
mechanics are not what separates them.

## Fairness and identifiability (authoring/evidence)

* Both deciding rules are pinned in `instruction.md` (quoted under "Task
  statement"); the evidence below shows that each pins a unique answer.
* `identifiability.log`: per-mode branch enumeration (n in -3..3, with and without
  conjugation): the true branch wins by x73 to x851 on shutter realness; the
  joint enumeration of 500 branch combinations gives the same winner for the
  shear-pattern and the Rayleigh-line criteria. Readings of the stated timing
  convention that differ only by a common time shift (timestamp at mid-frame,
  rows counted from 1) select the same branch; the reversed readout contradicts
  the instruction and leaves no branch with real shapes (ratio 0.31).
* `independent_solver.log`: a structurally different estimator (Whittle fit of
  the physical model to the Welch cross-spectral matrix with explicit folding
  and shutter phases) converges to the truth (0.02 % held-out error) from the
  reference start **and** from the alias-blind default.
* `independent_truth.log`: the shipped tracks are reproduced to the file's
  rounding (5e-4 px) by an independent real state-space integrator (matrix
  exponential of the augmented ZOH system), and the eigenvalues agree with numpy
  to 4e-16.
* `mutation_run.log`: each stated rule is broken in the oracle; the mass rule,
  shutter-timing rule and label map each change graded values; the per-target
  scale is the disclosed invariance band.

## Anti-cheat and adversarial hidden tests

`authoring/evidence/probe_run.log` (all run through the real `test.sh` in the
verifier image, network disabled): 16 exploit probes score 0 within about 2 s
including container start-up, with no side effect (code-injection strings, dunder walk, reward-file write payload,
30 000-deep JSON bomb, symlinks to the truth deriver and `/dev/zero`, FIFO,
oversized file, NaN/Infinity, duplicate keys, extra "alternatives" key, string
numbers, out-of-range values, the visible-objects-only frame, empty object,
eight stiffnesses). The lying ground-truth module ends as an infrastructure
error. Twelve legitimate serialisations of the correct answer (compact, indented,
CRLF, BOM, escaped key, exponents, integers, 3-significant-digit rounding, ...)
all score 1. The hidden tests themselves are adversarial by construction: the 40
held-out variants are where the default, the design-mass model, the
label-swapped model and the isospectral twins disagree with the truth (out of 164
values, they miss 71, 65, 83 and 83).

## Files

```
instruction.md, task.toml, README.md
environment/   Dockerfile, .dockerignore, data/{tracks.csv,targets.json,test_record.json}
solution/      solve.sh, solve.py
tests/         Dockerfile, .dockerignore, test.sh, test_outputs.py, check_submission.py,
               derive_truth.py, instance.py, heldout.py, frame_model.py, answer_format.py
authoring/     README.md, evidence/ (logs, run records, harness scripts; author-side only)
```
