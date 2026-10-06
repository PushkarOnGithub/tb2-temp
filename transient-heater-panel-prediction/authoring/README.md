# Authoring notes and evidence (author-side only)

This folder holds author-side provenance, calibration and review evidence only. Nothing at build,
solve or grade time reads it. Neither Dockerfile copies it, and `solution/` and `tests/` never
import, open or mention it. Scripts here import `tests/` and `solution/` modules to *exercise* them;
the dependency never runs the other way.

## Regenerating the instance

```
python3 authoring/generate.py           # writes environment/data/* and tests/lock.json
python3 authoring/generate.py --check   # asserts environment/data and the lock match tests/instance.py
bash authoring/evidence/run_evidence.sh # rebuilds both images, drives every calibration run
```

`tests/instance.py` is the single source of truth. It holds the hidden constants, the apparatus,
both current programs, the visible scenarios and the seeded held-out generator. It is standard
library only, so the verifier regenerates the agent's files byte-for-byte inside `python3 -I -S`.

## Evidence files

| File | What it shows |
|---|---|
| `evidence/offline_oracle_run.log` | Oracle in the agent image with `--network none` (`NETWORK: unreachable -> gaierror`, `interfaces present: lo:`), exit 0 in 0.42 s, artifact hash, verifier reward 1, 7/7 pytest |
| `evidence/calibration_run.log`, `evidence/run_records.json` | 52 runs through the real images: positives P1–P3 (=1), no-op (=0), 13 wrong methods (=0), 12 legitimate serialisations (=1), 18 exploit probes (=0, no side effects), lying ground truth (infrastructure error). `unexpected=0` |
| `evidence/variants.py`, `variants.log` | Wrong-method discriminator harness: the oracle with one decision flipped, driven to a graded artifact (19 variants, `HARNESS PASS`). All 27 combinations of the three silent readings fit at 0.01547–0.01548 K RMS |
| `evidence/independent_solver.py` | P2: structurally different solver (finite-volume stack, Crank–Nicolson, no closed forms) scoring 1 |
| `evidence/crosscheck_models.py`, `.log` | Both verifier forward models versus 30-digit Talbot inversion of the *finite* stated geometries: two-block closed form within 1e-5 K, panel series within 2e-15 relative |
| `evidence/mutation_study.py`, `.log` | Two-sided mutation of the stated physical assumptions |
| `evidence/calibration_extras.py`, `.log` | Noise Monte Carlo (60 seeds), numerical-scheme errors, cross-validation false confidence |

## Contested conventions (each pinned in instruction.md)

| Convention | Alternatives that would change the verdict | Pinned by |
|---|---|---|
| Logger timestamps | instantaneous sample; window centred on, or starting at, the stamp | "mean over the 2 s interval ending at its timestamp" |
| When current changes | inside a window | "the current changed only at logged timestamps" |
| Heater power | V·I, V²/R, I²R | "voltage across its own output terminals" + element resistance (temperature-independent) |
| Depth reference and scale | depths from another face; image versus object scale | "depths below the heater plane … measured at the detector … central ray in the heater plane" + distances |
| Heat path | heater into the specimen only; symmetric split | "clamped between the specimen block and a … base block" + base properties |
| Heater, contacts, sensors | heater thermal mass, contact resistance, sensor lag | "negligible heat capacity", "contact resistances are negligible", "instantaneous response" |
| Scenario flux semantics | segment end, sign, start | `[start_s, q]` pairs, "holds from its start until the next start", "absorbs the net heat flux" |
| Scenario depth origin, time origin | from the cooled face | "depth `x_mm` below the heated face at time `t_s`", "From t = 0" |
| Ties at flux switches | value just before or after a switch | no query within 2 s of a switch (asserted by the generator) |
| Tolerance | relative to absolute temperature or to rise | "within 0.5 % of the true rise above `T_init_C` plus 0.01 K" |
| Numbers | strings, booleans | "JSON number"; the battery shows integers, exponents, rounding, BOM and CRLF all accepted |

Freedoms not graded: any parameterisation is fine, because only temperatures are compared (k and ρc
are inputs to the hidden-scenario evaluation). Key order, whitespace, number formatting and the
analysis method are free.

## Identifiability: what pins each graded value

The answer depends on `(k, ρc)` only, through α = k/ρc and e = √(kρc).

| Quantity | How it is pinned |
|---|---|
| α_s | **Witnessed.** The shape of four responses at known depths over two power programmes; nonlinear in α, not degenerate with anything once the depth scale is fixed |
| e_s + e_b | **Witnessed.** Amplitudes, given the heater power |
| Heater power | **Fixed by stated state plus witnessed.** Element resistance and terminal-voltage measurement are stated; V/I = 6.172 Ω in every powered window witnesses the 0.372 Ω outside the element |
| Depth scale | **Reached through a stated rule.** Projection magnification SID/(SID − OID) with the stated distances |
| e_s | **Reached through a stated rule.** Two contacting half-spaces share the heater plane; the base effusivity comes from the stated base k, ρc. The half-space regime is checkable (Fo = 0.042 and 0.077) |
| Panel temperatures | **Reached through the stated scenario model.** One-dimensional slab, net flux, convection to T_init |

Every rule in the third category is stated in `instruction.md`.

Rival readings outside what the reference enumerates were tested one axis at a time on the shipped
data (`variants.py`, `mutation_study.py`):

- power as V·I or V²/R;
- split as all-to-specimen or P/2;
- depths unmagnified or inverted;
- window anchored at the stamp, at its centre, or starting at the stamp;
- T0 profiled versus pre-heating mean;
- heater with 400 J/(m²·K) capacity;
- 4e-4 m²·K/W contact resistance;
- isothermal outer faces.

Only the stated reading and its harmless numerical equivalents (T0 handling, the midpoint rule for
the logger, converged FD, a 5-term series) score 1. The three silent rivals (T1–T3) fit the logs
*equally well*. That is the design: they are excluded by stated facts, not by residuals, and the
instruction states those facts. The non-silent rivals are both contradicted by the logs (RMS
0.07–0.21 K versus 0.0155 K) and graded (15–34 of the 36 graded temperatures outside the band).

## Mutation study (two-sided, §9.1)

| Mutated rule | Evidence contradiction (fit RMS) | Graded values moved |
|---|---|---|
| none (stated model) | 0.0155 K | 0/36 |
| heater capacity 400 J/(m²·K) instead of negligible | 0.0713 K | 34/36 |
| contact resistance 4e-4 m²·K/W instead of negligible | 0.0950 K | 34/36 |
| outer faces isothermal instead of insulated | 0.0155 K | 0/36 (**invariance band, disclosed below**) |
| power V·I / V²/R (T1) | 0.0155 K | 35/36 / 36/36 |
| split all / half (T2) | 0.0155 K | 36/36 / 36/36 |
| depths unmagnified / inverted (T3) | 0.0155 K | 34/36 / 34/36 |
| logger instantaneous / window starting at stamp | 0.108 / 0.212 K | 15/36 / 21/36 |

**Disclosed invariance band.** The block thickness (60 mm) and outer-face condition are stated so
that a solver can establish the half-space regime. Any outer-face condition gives the same logs to
< 1e-5 K because the Fourier numbers stay below 0.08 (verified by Talbot inversion of the finite
stack). These facts therefore move no graded value. The answer is unique regardless, and the
statements cost nothing: they only license the half-space model. The same holds for the lead length
(1.5 m), which is context; the lead loss is pinned by V/I and the element resistance, not by length.

## Shortcut attempts (anti-cheat, §10.4)

All scored 0 in the verifier image with a flag-file side-effect check (`pwned=False`). Details are in
`calibration_run.log`:

- symlink to `/tests/lock.json`;
- symlink to `/etc/passwd`;
- `/dev/zero` symlink;
- FIFO;
- directory;
- a file over 64 KiB;
- code-injection strings (never evaluated: the only parser is `json.loads`);
- NaN/Infinity;
- `1e999`;
- duplicate keys;
- booleans;
- a 20 000-level nesting bomb;
- extra top-level key;
- missing prediction;
- predictions for 30 guessed hidden ids;
- out-of-range k;
- an answer assembled only from shipped objects (base k and ρc, `T_init` as every prediction);
- correct visible predictions with a 10 % perturbed model (caught by the held-out scenarios alone).

The lying ground-truth probe rewrote `tests/instance.py` so its constants agree with the V·I
answer. The lock over instance bytes and graded answers turned it into an infrastructure error (no
reward file). It is recorded separately and not counted among the shortcut attempts.

## Pricing brute force (§5.9)

The hidden object is two continuous numbers, judged on 36 temperatures at 0.5 %. The discrete
readings an agent might enumerate (power 3 × split 3 × depth 3 × logger 4 = 108 pipelines) cannot be
ranked by the shipped data. All silent combinations reach the same 0.0155 K RMS, and nothing in the
agent image scores a candidate. Search cost is therefore not the barrier; the absence of an oracle
is.

## Determinism

There is no clock, locale, network or unseeded randomness anywhere. Noise and the held-out scenarios
come from `random.Random(<fixed string>)`. The lock digest was reproduced bit-identically by Python
3.13 on the authoring host and Python 3.12.3 in the verifier image.

## Environment notes and honest limitations

- Both Dockerfiles pin `public.ecr.aws/docker/library/ubuntu:24.04@sha256:534baea6…`. That index
  digest was confirmed identical on ECR Public and Docker Hub. The authoring sandbox could not fetch
  ECR blobs, so the local builds used the Docker Hub copy of the same digest.
- The sandbox's TLS-intercepting proxy also required its CA for the verifier's `pip` layer. That
  local-only change was made in a scratch copy and never in the shipped files.
- `[metadata]` taxonomy labels (domain/field/subfield) were chosen without access to the closed
  taxonomy file. Adjust them to the repository's list if it differs.
- No frontier-agent trials were run during authoring. The difficulty figures in `README.md` are
  estimates from the discriminator harness and should be confirmed by a pre-measurement at 600 s.
