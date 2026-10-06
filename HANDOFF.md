# Handoff: `video-shear-frame-model-update` (Turing / Terminal-Bench Harbor task)

Written 2026-10-06 at the end of a session. Read this first, then
`video-shear-frame-model-update/README.md` (the task write-up) and
`video-shear-frame-model-update/authoring/README.md` (the evidence index).

## Where things are

- **Repo and branch:** `PushkarOnGithub/tb2-temp`, branch `ccr-e4465abf-l5fwxp`. PR #2 tracks
  it, and pushing to the branch updates the PR. Do not open a new PR.
- **Commits so far:** `f45a588` (task), `a2da819` and `a908590` (review fixes for Checks 2
  and 3), `4c375e5` (Check 1 fix: a shorter `instruction.md`).
- **The playbook is not in the repo.** It is the user's uploaded Turing document "Playbook:
  Authoring a Terminal Bench Benchmarking Harbor task that passes the review gates". Ask the
  user to attach it again. The sections that matter now:
  - §1: the difficulty gate and failure levers A–E, especially E, "the agent is only
    transcribing".
  - §1.1 rules 1–10 and §1.2 (traps).
  - §6: reading pass@k reports.
  - §10.2: the `instruction.md` dimensions, including Check 1, expert voice.
- **Original brief:** one research-grade scientific-computing / research-engineering task
  (Engineering) with 10 deliverables. These are: task statement, environment and data,
  deliverables, verifier strategy, reference method, failure modes, why the failures are hard
  to detect, calibration, reference implementation, and adversarial hidden tests. The task
  must be fair, reproducible, and execution-verifiable, with a 600 s agent budget and pass@5
  needing at least 3 countable failures.

## The task as it stands

The agent gets 600 s of video-tracked floor motion from a 4-storey shear frame under
unrecorded broadband shaking, filmed at 25 fps with a rolling shutter. It must output the
storey stiffnesses `k` (4 numbers, `/app/output/model.json`). The grader rebuilds K from `k`
and the as-tested M, then checks all 4 natural frequencies of 41 configurations (the frame as
tested plus 40 held-out variants with added mass or a stiffness factor) to 3 % relative.
Reward is 1 only if all 164 values pass.

- **Truth:** `k = [4930, 18880, 5080, 5100]` N/m, as-tested masses 5.10 / 5.25 / 5.95 / 7.50 kg
  (a 1.10 kg logger sits on floor 3). Mode 4 is at 14.534 Hz and shows up in the video at
  10.47 Hz as a *reflected* fold (25 − 14.53).
- **Intended cruxes:**
  - (1) Realise mode 4 is aliased. The rolling-shutter phase makes the shape real only on the
    true branch.
  - (2) The reflected fold needs the conjugate shape, i.e. the signed frequency −14.53 Hz.
  - (3) Isospectral twins: frequencies alone don't fix `k`, the shapes do.
  - Traps: the logger mass, the label→floor map, per-target mm/px.
- **Reference:** `solution/solve.py`, which does SSI-cov → branch × conjugate enumeration
  scored by shutter-corrected realness → mass-normalised shapes → shear projection → Newton
  refinement on frequencies. It runs in 0.2 s and is about 0.1 % off.

### Package files (`video-shear-frame-model-update/`)

| file | role |
|---|---|
| `instruction.md` | agent-visible text, 442 words. Each sentence was negotiated with the reviewers (see below) |
| `task.toml` | schema 1.3, agent 600 s, verifier 300 s in a separate no-network image |
| `environment/Dockerfile`, `environment/data/` | ubuntu:24.04 by digest, numpy 2.1.3, scipy 1.14.1. Data: `tracks.csv` (15000 frames), `targets.json`, `test_record.json` |
| `tests/instance.py` | stdlib generator: ambient zero-order-hold simulation, the true parameters and the seed. `python3 tests/instance.py OUTDIR` re-renders the data files |
| `tests/heldout.py` | the 40 held-out configurations, drawn from a SHA-256 counter PRNG |
| `tests/derive_truth.py` | regenerates and locks the instance. `LOCKED_DIGEST` covers the shipped bytes plus the 164 answers. **Any data or truth change means recomputing this digest** |
| `tests/check_submission.py`, `answer_format.py`, `frame_model.py`, `test_outputs.py`, `test.sh`, `Dockerfile` | the grader: run as `python3 -I -S`, exit codes 0 / 1 / 2, and the reward needs the VERDICT line |
| `solution/solve.sh`, `solve.py` | the oracle |
| `README.md` | write-up covering deliverables 1–10, cruxes, the failure-mode table and calibration |
| `authoring/evidence/` | `idlib.py` (identification library), `variants.py` (P1–P3 / N1–N13 graded by the real grader), `identifiability.py`, `independent_truth.py`, `independent_solver.py`, `mutations.py`, `seed_sweep.py`, `probes.py`, `run_evidence.sh`, plus logs |

### Re-running the evidence

These steps rebuild the images, run the oracle offline and grade it in the verifier image.
1. Start Docker if it isn't running:
   `sudo env HTTPS_PROXY=$HTTPS_PROXY HTTP_PROXY=$HTTP_PROXY dockerd &`
2. Run `bash authoring/evidence/run_evidence.sh`. It builds from Docker Hub copies of the same
   ubuntu digest (`sha256:534baea6…`) and adds the proxy CA for pip, because public.ecr.aws
   blobs can't be reached from the sandbox. The shipped Dockerfiles stay untouched.

Quick local check without Docker:
`python3 solution/solve.py && python3 -I -S tests/check_submission.py` (writes to
`/app/output/model.json`).

## Review history (automated rubric checks)

| round | result | what changed |
|---|---|---|
| 1 | Check 2 FAIL (alias branch and twin rule not pinned in agent-visible text), Check 3 FAIL (resolutions only in `solve.py` / README) | added the fold, real-shape and twin sentences to `instruction.md` |
| 2 | Check 2 FAIL (folded-mode sign/conjugation convention not pinned; the alternative `k = [1466111, 4549, 4376, 2858]` fails 98/164), Check 3 FAIL | added an explicit f − qF / negative-frequency / conjugate passage |
| 3 | Check 1 FAIL (expert voice: textbook narration of real modes and of aliasing). Checks 2 and 3 passed | collapsed those passages into one terse sentence (current text) |
| 4 (latest) | **The difficulty gate failed: models solved it easily.** The pass@k report and trajectories were not shared in the session | **open** |

Constraint the user set: don't let a check that currently passes flip to fail. Keep
`instruction.md` minimal.

## Why it is probably easy now (unconfirmed without the trajectories)

This is playbook lever E: every deciding rule is now written down.
- `instruction.md` says outright that frequencies may exceed half the frame rate.
- It says the fold is reflected and states the sign convention.
- It says the twin is resolved by mode shapes.

So the job reduces to "enumerate alias branches × conjugate, keep the one with real shutter-
corrected shapes, then fit `k` to frequencies and shapes". A strong agent writes that in a few
minutes. The remaining traps (logger mass, label map, mm/px) sit in plain JSON fields that
agents read carefully. There is also a structural weakness: grading depends only on the 4
true frequencies plus the twin choice. Once the branch is right, almost any estimator passes
at 3 % (N7, which ignores the shutter, passes at 1.8 %), so the shutter, scale and precision
work doesn't bite.

The reviewers and the gate pull against each other. Checks 2 and 3 demand that every
verdict-changing convention be pinned in agent-visible text. The gate needs the deciding step
to be *derived*. The playbook's way out (§6 "Treat automated difficulty suggestions with
care"):
- Leave **field-standard** facts unstated.
- Pin only **artifact-arbitrary** conventions.
- Make the crux an *inference from shipped evidence* that the default path skips, not a rule
  to transcribe.

## First steps for the next session

1. **Get the pass@k report from the user**, the full analysis plus any base64 payload (§6
   step 3). Find out which route the successful agents took and how long they needed. Check
   whether any trial failed, and why.
2. Decide between **escalating the class** and patching a parameter (§6 step 5). Three
   rounds have already gone into this one idea; do not just tighten the tolerance or move
   frequencies.
3. Candidate directions to price against the trajectories. None is implemented yet, and each
   needs the identifiability, variants and seed-sweep evidence redone:
   - **Make graded values depend on more than the 4 frequencies**, so precision cruxes bite.
     For example, more unknowns than frequencies (a non-shear coupling, or a second target per
     floor exposing torsion), so `k` must come from accurate shapes. That makes the shutter
     correction, the per-target scale and the as-tested mass graded rather than cosmetic.
   - **Add independent cruxes with their own tempting default**, each graded separately
     (§1.1 rule 3, p^k). They must be field-standard so they need no pinning sentence (keeps
     Checks 1–3 green). Ideas:
     - Exposure-time integration recorded in `test_record.json`: a boxcar filter that changes
       the amplitude and phase of a high, folded mode.
     - Variable-frame-rate or dropped-frame timestamps in `t_s`: the default assumes uniform
       sampling, and sampling is no longer uniform.
     - Per-target tracker latency stated in a calibration file.
     Each must survive the agent's own self-checks and move many of the 164 values.
   - **Withdraw the procedural parts of the fold sentence** and let the evidence decide:
     keep "no anti-aliasing filter" plus classical damping plus the shutter formula. Only do
     this if it can be argued to the Check 2 reviewer that the sign convention follows from
     the stated sampling model, i.e. is field-standard. Round 2 says the reviewer did not
     accept that, so this is the riskiest option.
4. After any change:
   - Regenerate the data with `tests/instance.py` and update `LOCKED_DIGEST`.
   - Rerun `run_evidence.sh` and the other evidence scripts.
   - Update both READMEs, which quote the instruction sentences.
   - Commit with the session attribution lines and push to `ccr-e4465abf-l5fwxp`.
