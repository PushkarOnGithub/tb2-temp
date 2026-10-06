# Handoff: Terminal-Bench task for Scientific Computing / Research Engineering (Engineering)

Status as of 2026-10-06: **v1 failed the difficulty gate.** The package is complete and passes
every local gate (oracle reward 1, no-op 0, 52 Docker calibration runs as expected, 45 static
checks). But the user reports that frontier models **solved it easily**. The next session should
redesign the cruxes (change the class, not the parameters) and reuse the infrastructure.

## 1. Where everything is

- Repo `PushkarOnGithub/tb2-temp`, branch `ccr-740826c0-05gk40`, PR #1 (open, base `master`):
  https://github.com/PushkarOnGithub/tb2-temp/pull/1. Pushing to the branch updates the PR.
- Task package: `transient-heater-panel-prediction/`. Its `README.md` is the full v1 design doc; its
  `authoring/README.md` holds conventions, identifiability, mutation study and probes.
- Authoring playbook: the user uploaded it (`DOC-20261006-WA0000.md`, "Playbook: Authoring a
  Terminal Bench Benchmarking Harbor task that passes the review gates"). It is **not in the repo**.
  Ask the user to re-upload it; it is the grading spec for every gate. Do not commit it without
  asking. Its key rules are summarised in §5.
- Attempts are limited (the playbook says up to 5 submissions). v1 has presumably used one.

## 2. What v1 is (one paragraph)

The agent gets raw logs of a two-block transient heater test: a foil heater clamped between an
instrumented specimen block and a borosilicate base block. The logs hold supply current and voltage,
four thermocouples read by an integrating 2 s logger, and bead depths measured on a radiograph. It
must report the specimen's `k` and `ρc` and predict six panel temperatures (slab, net flux on one
face, convection on the other). The grader also evaluates 30 hidden panel scenarios from the
reported `k`, `ρc`, at a band of 0.5 % of the rise plus 0.01 K. The truth is `k = 0.5862`,
`ρc = 1.6385e6`. Three cruxes are *exact degeneracies* of the fit, each resolved only by a stated
apparatus fact:

- **T1:** the supply logged its *terminal* voltage. V/I is 6.172 Ω against a 5.800 Ω element, so
  `P = I²R`, not `V·I`.
- **T2:** heat splits between the blocks by effusivity, so `e_s = (e_s+e_b)_fit − e_b`.
- **T3:** the radiograph depths are magnified by SID/(SID−OID) = 1.136.

Every trap-blind pipeline fits at the noise floor (RMS 0.0155 K) and fails ≥ 34 of 36 graded
temperatures. Secondary cruxes: the integrating-logger model, which is visible if ignored, and two
switch-adjacent scenarios that defeat coarse time stepping.

## 3. Why it was too easy (diagnosis, to confirm against the pass@k report)

The trajectories/pass@k analysis were not available in this session. **Step 1 next session: get the
report (decode any base64 payload) and check which cruxes the agents caught and how.** Likely
causes, in order:

1. **Lever E, transcription.** Every deciding rule was written down: where V was measured, that a
   second block exists (with its k and ρc), the radiograph geometry, the logger averaging. A
   careful reader turns each sentence into one line of code. The playbook warns that procedural
   rule-following is exactly what frontier models do well.
2. **The facts were their own tell.** `apparatus.json` contained *only* decision-relevant constants:
   element resistance, base k/ρc, SID, OID. An agent asks "why is this given?" and uses each one.
   The playbook's trap recipe needs a salient condition plus a binding one, look-alikes, and
   **no tell**; here the binding facts were the tell.
3. **The cheap check was right there.** Printing V/I (6.17 versus 5.80 Ω) exposes T1 immediately.
   Given base properties invite a two-sided or full-stack model, and an FD model of the full stack
   handles T2 automatically. The magnification is one formula.
4. **Each crux was one step once noticed.** No exploration was needed, so 600 s was ample: the
   oracle runs in 0.4 s in about 150 lines.
5. **The numerics crux was mild.** An eigen-series panel model (the natural choice) converges fast;
   only coarse FD or default-tolerance `solve_ivp(BDF)` fail.

My pre-submission estimate of per-crux catch rates (0.5–0.8) was too low; assume ≈ 1.0 for any
explicitly stated condition.

## 4. What to reuse (all working, tested)

- `tests/answer_format.py`: strict reader (lstat, `O_NOFOLLOW`, ≤ 64 KiB, no NaN, no duplicate
  keys, exact keys and ids), shared by the grader and pytest.
- `tests/check_submission.py`: stdlib grader for `python3 -I -S`; exit 0 + verdict / 1 / 2.
- `tests/derive_truth.py` + `tests/lock.json`: regenerate the instance in an isolated interpreter
  and SHA-256-lock instance bytes + hidden constants + graded answers. The digest was identical
  under Python 3.13 (host) and 3.12 (image).
- `tests/test.sh`: exit-code-to-reward mapping per playbook §9.4. `tests/test_outputs.py`: pytest
  report with docstrings.
- `tests/instance.py`: the single source of truth and generator (stdlib).
  `tests/thermal_model.py`: closed-form window-averaged half-space response and the panel
  eigen-series (`μ tan μ = Bi`).
- `authoring/generate.py` (`--check` mode), `authoring/check_package.py` (45 static gates),
  `authoring/evidence/run_evidence.py` (oracle offline, no-op, variants, 12-format battery,
  18 exploit probes, lying ground truth; all through the real images), `variants.py` (wrong-method
  harness pattern), `independent_solver.py` (FV full stack), `crosscheck_models.py` (Talbot
  inversion), `mutation_study.py`, `calibration_extras.py` (noise Monte Carlo).

These are domain-agnostic except `instance.py`, `thermal_model.py` and the physics in the
harnesses. A v2 in another domain can keep the whole verifier and authoring skeleton.

## 5. Playbook rules that matter most for v2 (summary)

- The difficulty gate is pass@5 at 600 s. It needs ≥ 3 *countable* failures, meaning committed-wrong
  or idle answers. In-progress timeouts do not count. Design so the first confident answer is
  wrong.
- The reliable failure classes are **rules withheld but inferable from shipped evidence** and
  **derivations the agent must first realize apply**, ideally 2–3 independent cruxes. Implementing a
  documented spec, even a long silent one, gets solved.
- The default must reproduce the shipped evidence (silent). The evidence must still force the true
  rule through an inference the default skips (identifiability proof, §5.6). Give the agent no
  self-check.
- Traps must be stated or witnessed fairly, realistic, without tells, and must move held-out
  graded values. Keep each crux's wrong-hypothesis space small so agents commit instead of
  exploring.
- Escalate the **class**, not the parameter. Bigger numbers or more stated facts will not help.
- Keep: held-out inputs generated only in the verifier, a stdlib grader under `-I -S`, the
  instruction ending with the exact 600 s line, `expert_time_estimate_hours ≤ 1.5`, and no
  deprecated keys in `task.toml`.

## 6. Directions for v2 (my recommendation, not yet prototyped)

Principle: **assume the agent reads and applies every stated fact correctly.** The answer must
hinge on something the agent has no reason to look for. The evidence must contain it, the
instruction must make the relevant *rule family* fair, and nothing may announce "use me".

- **A. Scope or look-alike records instead of physics corrections.** Recommended starting point;
  it reuses the v1 physics and infrastructure.
  - *Setup:* ship 8–12 runs in one log with a separate run sheet. The instruction states a plain
    binding scope rule, e.g. "only runs on specimen lot X, after the re-cut, count". 10–20 % of runs
    are look-alikes (twin specimen, earlier lot) with slightly different properties, distinguishable
    only through the run sheet.
  - *Why it bites:* each run fits perfectly on its own, so the natural pipeline (fit all, pool or
    average) is silently biased. Held-out panels expose the bias.
  - *Risk to rule out:* per-run estimates may visibly form two clusters. Tune the decoy difference
    against the noise-limited spread so pooling stays plausible. Prove the trap moves graded values
    beyond the band and test positional heuristics (§5.7).
- **B. A regime change or exception clause inside the data.** For example, a sensor was replaced or
  re-zeroed mid-campaign, or one channel is a different thermocouple type, recorded in a
  maintenance log rather than the instruction body. The binding sentence is stated once; the point
  of use carries no flag.
  - *Check:* that the trap-blind fit stays at the noise floor. Physics corrections were visible in
    v1 whenever they were not scale-type, so pick effects that are exact scale degeneracies, or
    confine them to data that do not constrain the fit.
- **C. A must-realize derivation with a tempting fast default.** Keep identifiability fair by
  disclosing the rule family, but make the realization non-obvious, e.g. a sampled-data or
  aliasing/discretization effect, or a hidden symmetry the held-out set exercises.
  - *Caution:* check novelty against the TB2 and TB-Science sets.
  - *Caution:* aliasing-style ideas may already be used (the playbook mentions an
    "undersampled-chain-tap" example name).

Whatever is chosen:

1. Prototype the trap-blind pipeline first and measure: (a) fit RMS against noise (must be
   silent); (b) graded temperatures moved (must exceed the band); (c) whether an obvious check
   such as V/I, cluster plots or residual by run reveals it.
2. Write down what a strong model does in its first two minutes; it must end in a well-formed
   wrong answer.
3. If possible, pre-measure a strong model at 600 s before resubmitting.

Rejected or measured ideas from v1, to save time:

- **Back-to-back runs without re-equilibration ("memory" trap).** A linear-drift patch is
  near-silent but biases `k` only ≤ 0.4 %, so it is not a discriminator.
- **Heater heat capacity or contact resistance as hidden effects.** Mis-modelling either is
  visible: the mutation study gives fit RMS 0.07–0.10 K against 0.0155 K, and a prototype with the
  effect present and unmodelled showed offsets of order 1 K. They would cost the agent time, not
  answers.
- **Ignoring logger averaging.** Visible: RMS 7–15× noise.
- **Exact silent degeneracies in this geometry are scale-type only:** power ↔ `e_s+e_b`, common
  depth scale ↔ α, and the split (which only changes the attribution of `e_s`).
- **Finite-block effects.** Inert by design (Fo < 0.08). The 60 mm blocks act as half-spaces to
  < 1e-5 K.

## 7. Environment quirks (cloud sandbox)

- **Docker:** the daemon is not running at start:
  `nohup dockerd --host=unix:///var/run/docker.sock > /tmp/dockerd.log 2>&1 &`. It inherits
  `HTTPS_PROXY`, so pulls work.
- **Base image:** ECR Public blobs are blocked (CloudFront 403); Docker Hub works. The shipped
  Dockerfiles pin `public.ecr.aws/docker/library/ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55`,
  and Docker Hub has the identical index digest. Use
  `docker pull ubuntu:24.04 && docker tag ubuntu:24.04 public.ecr.aws/docker/library/ubuntu:24.04`
  and the pinned `FROM` then resolves locally.
- **pip inside `docker build`:** fails TLS, because the proxy re-terminates it. For the verifier
  image only, build from a scratch copy with the sandbox CA. Never change the shipped Dockerfile.

  ```bash
  CTX=$(mktemp -d); cp -a transient-heater-panel-prediction/tests/. "$CTX/"; cp /root/.ccr/ca-bundle.crt "$CTX/sandbox-ca.crt"
  sed -i 's#^RUN pip install --break-system-packages#COPY sandbox-ca.crt /tmp/sandbox-ca.crt\nRUN PIP_CERT=/tmp/sandbox-ca.crt pip install --break-system-packages#' "$CTX/Dockerfile"
  docker build -q --network host -t thpp-verifier "$CTX"; docker build -q -t thpp-env transient-heater-panel-prediction/environment
  AGENT_IMAGE=thpp-env VERIFIER_IMAGE=thpp-verifier python3 -B transient-heater-panel-prediction/authoring/evidence/run_evidence.py
  ```

- **Host tools:** the host has numpy and pandas but not scipy: `pip install scipy==1.16.2 mpmath`.
  The images use apt `python3-numpy` 1.26.4 and `python3-scipy` 1.11.4 (Python 3.12.3).
- **`/app` on the host:** do not create or remove it; `rm -rf /app` is blocked by a safety check.
  Run solvers on the host through a runner that redirects their `DATA`/`OUT` globals:

  ```python
  import importlib.util, sys
  spec = importlib.util.spec_from_file_location("m", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
  m.DATA, m.OUT = sys.argv[2], sys.argv[3]; m.main()
  ```

- **Waiting:** foreground `sleep` is blocked. Use background tasks or Monitor until-loops.
- **Bytecode caches:** run authoring scripts with `python3 -B`. The scripts also set
  `sys.dont_write_bytecode`, so no `__pycache__` lands in `tests/` or `solution/`.
- **Rebuild after any change to `tests/` or `environment/`.** Stale images once produced a
  misleading 6/52 failure.

## 8. Validation commands (v1, all passing at commit 28c92fb)

```bash
cd transient-heater-panel-prediction
python3 -B authoring/generate.py --check            # data + lock in sync
python3 -B authoring/check_package.py               # 45 static gates
python3 -B authoring/evidence/crosscheck_models.py  # forward models vs Talbot inversion
python3 -B authoring/evidence/variants.py           # 19 variants, HARNESS PASS
python3 -B authoring/evidence/calibration_extras.py # noise MC, numerics, cross-validation
python3 -B authoring/evidence/mutation_study.py     # ~2.5 min
cd ..   # the Docker block in section 7 runs from the repo root -> calibration_run.log: runs=52 unexpected=0
```

## 9. Open items

- The auto-generated PR #1 description says `variants.py` tests "52 variants". It runs 19; 52 is
  the Docker calibration total.
- The `task.toml` taxonomy labels (domain/field/subfield) are guesses; check them against the
  closed list.
- If v1 is kept or adapted, its README's "Difficulty calibration" section is now falsified and must
  be rewritten.
- Decide whether v2 replaces `transient-heater-panel-prediction/` in place (new `task.name`) or
  lives in a new directory. The submission presumably expects one task.
