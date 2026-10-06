"""Independent cross-check of the instance generator (structurally different algorithm).

tests/instance.py integrates the shaker response in complex modal coordinates
with a closed-form zero-order-hold update and a pure-Python Jacobi eigen-solver.
This script re-integrates the same force sequence with a real 8-state
state-space model (no modal decomposition): exact ZOH discretisation by the
matrix exponential of the augmented matrix [[A, B], [0, 0]] (scipy.linalg.expm),
including the partial step to every target's rolling-shutter capture time.
It compares the noise-free pixel tracks with the shipped file minus the
generator's tracker noise, and the eigenvalues with numpy's dense solver.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import os
import sys

import numpy as np
from scipy.linalg import expm, eigh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
import frame_model  # noqa: E402
import instance as I  # noqa: E402


def main():
    m = np.array(I.as_tested_mass())
    k = np.array(I.K_TRUE)
    K = np.array(frame_model.shear_stiffness(list(k)))
    M = np.diag(m)
    C = I.A0_TRUE * M + I.A1_TRUE * K
    n = 4
    A = np.block([[np.zeros((n, n)), np.eye(n)], [-np.linalg.solve(M, K), -np.linalg.solve(M, C)]])
    B = np.zeros(2 * n)
    B[n + I.SHAKER_FLOOR - 1] = 1.0 / m[I.SHAKER_FLOOR - 1]

    def zoh(h):
        aug = np.zeros((2 * n + 1, 2 * n + 1))
        aug[:2 * n, :2 * n] = A * h
        aug[:2 * n, 2 * n] = B * h
        E = expm(aug)
        return E[:2 * n, :2 * n], E[:2 * n, 2 * n]

    h = I.FORCE_STEP_S
    Ad, Bd = zoh(h)
    n_check = 1500                              # first 60 s of the record
    dt = 1.0 / I.FRAME_RATE
    order = sorted(range(n), key=lambda j: I.FLOOR_ROW[j])
    force = I.GaussStream("shaker")
    x = np.zeros(2 * n)
    step = 0
    u = I.FORCE_STD_N * force.next()
    disp = np.zeros((n_check, n))
    cache = {}
    for fr in range(n_check):
        for j in order:
            t = I.BURN_IN_S + fr * dt + I.FLOOR_ROW[j] * I.ROW_PERIOD_S
            while (step + 1) * h <= t:
                x = Ad @ x + Bd * u
                step += 1
                u = I.FORCE_STD_N * force.next()
            rho = round(t - step * h, 12)
            if rho not in cache:
                cache[rho] = zoh(rho)
            Ar, Br = cache[rho]
            disp[fr, j] = (Ar @ x + Br * u)[j]

    raw = np.loadtxt(os.path.join(HERE, "..", "..", "environment", "data", "tracks.csv"), delimiter=",", skiprows=1)
    labels = sorted(I.TARGET_FLOOR)
    worst = 0.0
    for col, lab in enumerate(labels, start=1):
        j = I.TARGET_FLOOR[lab] - 1
        noise = I.GaussStream("tracker-" + lab)
        nz = np.array([I.NOISE_PX * noise.next() for _ in range(n_check)])
        px = I.FLOOR_REST_PX[j] + 1000.0 * disp[:, j] / I.FLOOR_MM_PER_PX[j] + nz
        dev = np.abs(raw[:n_check, col] - px)
        worst = max(worst, dev.max())
        print("%s (floor %d): max |shipped - independent| = %.2e px over %d frames (file rounding 5e-4 px)"
              % (lab, j + 1, dev.max(), n_check))
    w2 = eigh(K, M, eigvals_only=True)
    f_np = np.sqrt(w2) / (2 * np.pi)
    f_st = np.array(frame_model.natural_frequencies_hz(list(k), list(m)))
    print("natural frequencies numpy %s vs stdlib %s, max rel diff %.1e"
          % (np.round(f_np, 6), np.round(f_st, 6), np.max(np.abs(f_np / f_st - 1))))
    ok = worst <= 5.0001e-4 and np.max(np.abs(f_np / f_st - 1)) < 1e-12
    print("INDEPENDENT TRUTH CHECK:", "PASS" if ok else "FAIL")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
