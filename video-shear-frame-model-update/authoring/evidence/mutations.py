"""Two-sided mutation test of the stated rules (playbook section 9.1).

The oracle pipeline (SSI-cov, shutter-corrected realness branch, shapes then
frequency refinement) is broken once per rule stated in instruction.md.
Each mutant is scored two ways:
  * evidence contradiction: the worst shutter-corrected imag/real ratio of the
    four selected modes (about 3e-3 when every stated rule is honoured), i.e.
    how strongly the shipped data object to the mutant;
  * graded effect: grader verdict and number of the 164 graded frequencies
    out of tolerance.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import json
import os

import numpy as np

import idlib
import variants

HERE = os.path.dirname(os.path.abspath(__file__))


def oracle_like(masses="tested", units="per_target", mapping="file", delay_fn=None):
    t, disp, delay, design, tested = idlib.load(mapping=mapping, units=units)
    mass = tested if masses == "tested" else design
    if delay_fn is not None:
        delay = delay_fn(delay)
    dt = float(np.median(np.diff(t)))
    lam, psi = idlib.ssi_cov(disp - disp.mean(0))
    sel, worst = [], 0.0
    for r in range(4):
        best = min(idlib.candidates(lam[r], psi[:, r], dt),
                   key=lambda c: idlib.realness(c[1] * np.exp(-c[0] * delay))[1])
        phi, ratio = idlib.realness(best[1] * np.exp(-best[0] * delay))
        worst = max(worst, ratio)
        sel.append((best[0], phi))
    sel.sort(key=lambda x: abs(x[0]))
    omega, _, phi = idlib.modal_arrays(sel, mass)
    k, _ = idlib.k_from_frequencies(omega, mass, idlib.k_from_shapes(omega, phi, mass))
    return k, worst, omega / (2 * np.pi)


TAU = 1.86e-5
MUTANTS = [
    ("none (oracle)", {}),
    ("as-tested mass rule -> design masses", {"masses": "design"}),
    ("shutter timing rule -> all targets at t_n", {"delay_fn": lambda d: 0 * d}),
    ("shutter timing rule -> rows read bottom-to-top", {"delay_fn": lambda d: 1079 * TAU - d}),
    ("per-target scale rule -> pixels", {"units": "pixels"}),
    ("target->floor map -> T1..T4 = floors 1..4", {"mapping": "labels"}),
]


def main():
    lines = ["mutant                                             evidence(worst imag/real)  reward  out-of-tol/164  max|df/f|   k"]
    for name, kw in MUTANTS:
        k, worst, f = oracle_like(**kw)
        model = {"k": [float(x) for x in k]}
        if min(k) <= 0:
            reward, ef, nbad = 0, float("nan"), 164
        else:
            _, reward, _ = variants.grade(model)
            ef, nbad = variants.worst_error(model)
        lines.append("%-50s %10.2e %16d %10d %10.2f%%   %s" % (name, worst, reward, nbad, 100 * ef, np.round(k)))
        print(lines[-1], flush=True)
    with open(os.path.join(HERE, "mutation_run.log"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
