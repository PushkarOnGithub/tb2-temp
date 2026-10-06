# Authoring evidence (author-side only)

This folder holds provenance, calibration and review evidence only. Neither
Dockerfile copies it, nothing at build, solve or grade time reads it, and
`solution/` and `tests/` never import, open or mention it. The scripts here
import the verifier modules from `tests/` read-only, to drive the real grader.

## How to reproduce

```
bash authoring/evidence/run_evidence.sh      # needs docker; builds both images
python3 authoring/evidence/identifiability.py
python3 authoring/evidence/mutations.py
python3 authoring/evidence/seed_sweep.py 10
```

`run_evidence.sh` builds the agent and verifier images, runs the oracle with
the network removed, grades it in the separate verifier image, grades a no-op
run, then runs the independent truth check, the identifiability enumeration,
the wrong-method harness, the independent spectral solver and the probe
battery. Sandbox note: the authoring machine cannot download blobs from
public.ecr.aws, so the images are built from copies of the two Dockerfiles whose
`FROM` names the same manifest digest on Docker Hub (identical index digest
`sha256:534baea6...`), with the local TLS proxy's CA trusted for the pip step.
The shipped Dockerfiles are unchanged.

## Evidence index

| file | what it shows |
|---|---|
| `offline_oracle_run.log` | network probe (`interfaces present: lo:`, `NETWORK: unreachable -> gaierror`), oracle exit 0 in 0.19 s, the artifact, verifier verdict line, pytest 5 passed, reward 1 |
| `nop_run.log` | no artifact: contract failure, reward 0 |
| `calibration_run.log`, `run_records.json` | P1-P3 positive variants (reward 1) and 12 wrong methods driven to a submitted `model.json` and graded by `tests/check_submission.py`, with their worst error and number of failed values out of 164 |
| `seed_sweep.log` | the same estimators on 10 further noise realisations: tolerance calibration |
| `identifiability.log` | branch enumeration with three independent criteria, isospectral twins, outside readings of the timing convention |
| `independent_truth.log` | generator reproduced by an independent real state-space ZOH integrator to the file rounding; eigenvalues agree with numpy |
| `independent_solver.log` | structurally different estimator (Whittle fit of the physical model with explicit folding and shutter phases) converges to the truth from the oracle start and from the alias-blind default; negative controls without folding / without shutter phases miss by 25 % / 27 % |
| `mutation_run.log` | each stated rule broken once in the oracle, scored by evidence contradiction and by graded effect |
| `probe_run.log`, `probe_records.json` | 16 exploit probes (reward 0, no side effect), the lying ground-truth module (infrastructure error), 12 legitimate serialisations (reward 1), all through the real `test.sh` |

## Positive variants (all reward 1)

* P1 oracle: SSI-cov, shutter-realness branch, shapes then frequency refinement (0.08 %).
* P2 materially different identification: frequency-domain decomposition of the
  Welch cross-spectral matrix, branch from the realness of the singular vector (0.54 %).
* P3 equivalent estimate: stiffness projected from the mode shapes without the
  frequency refinement (1.26 %).
* Format re-parameterisations: 12 serialisations in `probe_run.log` (integers,
  exponents, 3-significant-digit rounding, BOM, CRLF, escaped key, ...).

## Wrong-method harness (each driven to a submitted model, graded by the real grader)

| variant | class | worst error | out of 164 |
|---|---|---|---|
| N1 principal-branch poles, frequency updating (the default) | crux | 31.4 % | 71 |
| N2 principal-branch poles, stiffness from shapes | crux | 28.2 % | 164 |
| N3 principal-branch poles, shapes + frequency refinement | crux | 31.4 % | 71 |
| N4 aliasing suspected, wrong (non-reflected) fold | crux | 148.7 % | 58 |
| N5 Welch peak picking, frequency updating | crux | 31.5 % | 70 |
| N6 design masses (logger omitted) | trap (a) | 9.7 % | 65 |
| N8 shutter handled by spline resampling | trap (a), loud | negative stiffness | 164 |
| N9 pixels / common scale, stiffness from shapes | trap (a) for shape-based estimators | 6.0 % | 42 |
| N10 labels taken as floors 1..4 | trap (a) | 18.2 % | 83 |
| N11 frequency-only updating, uniform start | identifiability (a) | 19.2 % | 87 |
| N12 frequency-only updating onto the exact isospectral twin | identifiability (a) | 18.2 % | 83 |
| N7 shutter delays ignored in the shapes (branch known) | (b) time/precision cost | 1.8 % | 0 |

Classification follows the playbook: (a) changes graded values; (b) costs
precision or time but not correctness on this instance. N7 is (b): 1.9-4.3 %
across the seed sweep, so it is not counted as a discriminator. Inert traps: none
are claimed.

## Contested conventions (enumerated; each pinned in instruction.md or inert)

| convention | resolution |
|---|---|
| which time a frame timestamp refers to | instruction: row r captured at t_n + r*tau. Any reading that shifts all targets by the same time (timestamp at mid-frame, rows counted from 1) selects the same branch and the same k (identifiability.log, section 3): inert. |
| readout direction | pinned by the formula; the reversed reading leaves no branch with real shapes (ratio 0.31) and contradicts the instruction. |
| as-tested mass | instruction: design mass plus everything mounted during the test. |
| label to floor | `targets.json` gives the floor of every label. |
| units | positions in pixels, scale per target in `targets.json`, stiffness in N/m. |
| natural frequency | undamped, compared in ascending order; damped vs undamped differs by at most zeta^2/2 = 2.6e-5 here, so it is inert at 3 %. |
| held-out variants | instruction gives family, ranges, count and split (19 + 21); added mass is a lumped mass on the floor, the factor multiplies k_j. |
| ordering ambiguity | every graded configuration has consecutive true frequencies at least 48 % apart (deriver asserts at least 7 % = more than twice the tolerance). |

## Disclosed invariance band (mutation_run.log)

The per-target image scale is documented mechanics, not a deciding rule:
frequency-refined estimators are insensitive to per-channel real scaling (the
oracle with positions left in pixels returns the same k), while estimators that
build K from the mode shapes are not (N9, 6.0-9.1 %). The as-tested mass rule
and the label map cannot be contradicted by output-only data (masses and floor
order do not change any fit), but they are stated in the shipped files and
move up to 65 and 83 graded values respectively. The shutter-timing rule is
both witnessed by the data (worst imag/real 0.22 when ignored, 0.31 when
reversed, against 0.003) and graded (31 % and 73 %).

## Brute-force and shortcut pricing

* No deterministic forward model exists for the agent: the force was not
  recorded, so the tracks cannot be simulated and fitted point by point. An
  earlier impact-hammer version of this task was rejected for exactly this
  reason: from a uniform physical starting guess, a direct time-domain fit
  reached the true model without the aliasing insight, with the residual
  serving as a self-check.
* The answer is continuous and graded through 164 frequencies at 3 %; the
  apparent-frequency frame, the design-mass frame, the label-swapped frame and
  the isospectral twin are the cheap candidates, and all score 0.
* Every search that can test candidates against the evidence (branch
  enumeration scored by shutter realness, shear pattern or Rayleigh line, or a
  spectral likelihood with explicit folding and shutter phases) already embodies
  the insight; without folding or without shutter phases the spectral likelihood
  converges confidently to a 25-27 % wrong model.

## Anti-cheat summary

Truth is regenerated in an isolated interpreter (`python3 -I -S`) and locked by
one SHA-256 digest over the shipped bytes and the 164 graded answers; the
grader reads only the declared artifact through a bounded-regular-file reader
and never evaluates it; the reward requires the grader's verdict line and
pytest; infrastructure errors leave no reward file. Shortcut attempts recorded:
X01-X16 (all reward 0, no side effect) and I01 (lying ground truth,
infrastructure error, not counted among the shortcut attempts).
