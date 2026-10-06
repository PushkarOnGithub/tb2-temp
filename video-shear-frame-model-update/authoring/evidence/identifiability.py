"""Identifiability evidence for the shipped instance.

1. Branch (alias) enumeration.  For every identified mode, every continuous
   pole consistent with its discrete pole (n in -3..3, with and without
   conjugation) is scored by three independent criteria:
     a. realness of the rolling-shutter-corrected shape (classical damping),
     b. shear-frame pattern of M Phi W^2 Phi^T M (zero entries outside the
        tridiagonal and zero row sums for floors 2..4),
     c. Rayleigh consistency: decay rates sigma_r = a0/2 + a1 w_r^2 / 2 with
        a0, a1 >= 0.
   The joint enumeration over all four modes is reported for (b) and (c).
2. Isospectral twins.  All positive stiffness vectors that reproduce the
   four true natural frequencies with the as-tested masses are enumerated by
   multistart Newton; the measured mode shapes (MAC) select one of them.
3. Outside readings of the stated conventions (timestamp reference row,
   row indexing base, readout direction) and whether they survive.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import itertools
import os
import sys

import numpy as np

import idlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
import frame_model  # noqa: E402
import instance  # noqa: E402

FS = 25.0
DT = 1.0 / FS


def pattern_residual(omega, phi, mass):
    M = np.diag(mass)
    phi = phi / np.sqrt(np.einsum("ir,ij,jr->r", phi, M, phi))
    K = M @ phi @ np.diag(omega ** 2) @ phi.T @ M
    basis = np.array([idlib.shear_k(np.eye(4)[j]).ravel() for j in range(4)]).T
    coef, *_ = np.linalg.lstsq(basis, K.ravel(), rcond=None)
    return np.linalg.norm(K.ravel() - basis @ coef) / np.linalg.norm(K)


def rayleigh_residual(poles):
    w = np.abs(poles)
    sig = -poles.real
    A = np.column_stack([np.ones(len(w)), w ** 2])
    coef, *_ = np.linalg.lstsq(A, sig, rcond=None)
    if coef.min() < 0:
        return np.inf
    return np.linalg.norm(A @ coef - sig) / np.linalg.norm(sig)


def main():
    lines = []
    out = lines.append
    t, disp, delay, design, mass = idlib.load()
    lam, psi = idlib.ssi_cov(disp - disp.mean(0))
    true_f = frame_model.natural_frequencies_hz(instance.K_TRUE, instance.as_tested_mass())
    out("true natural frequencies (Hz): %s" % np.round(true_f, 4))
    out("frame rate %.1f Hz, Nyquist %.2f Hz" % (FS, FS / 2))
    out("")
    out("1a. per-mode branch scores, criterion = imag/real of shutter-corrected shape")
    per_mode = []
    for r in range(4):
        cands = idlib.candidates(lam[r], psi[:, r], DT)
        scored = []
        for s, ps in cands:
            phi, ratio = idlib.realness(ps * np.exp(-s * delay))
            scored.append((ratio, s, phi))
        scored.sort(key=lambda x: x[0])
        per_mode.append(scored)
        f_app = abs(np.angle(lam[r])) / (2 * np.pi * DT)
        out("  mode %d (apparent %.4f Hz): best %.4f Hz ratio %.2e | runner-up %.4f Hz ratio %.2e | margin x%.0f"
            % (r + 1, f_app, scored[0][1].imag / (2 * np.pi), scored[0][0], scored[1][1].imag / (2 * np.pi),
               scored[1][0], scored[1][0] / scored[0][0]))
    out("")
    out("1b/1c. joint enumeration over all branch combinations (frequencies <= 60 Hz)")
    combos = []
    pools = [[c for c in pm if c[1].imag / (2 * np.pi) <= 60.0] for pm in per_mode]
    for combo in itertools.product(*pools):
        poles = np.array([c[1] for c in combo])
        phi = np.array([c[2] for c in combo]).T
        order = np.argsort(np.abs(poles))
        poles, phi = poles[order], phi[:, order]
        combos.append((pattern_residual(np.abs(poles), phi, mass), rayleigh_residual(poles),
                       max(c[0] for c in combo), np.round(np.abs(poles) / (2 * np.pi), 3)))
    n = len(combos)
    by_pattern = sorted(combos, key=lambda c: c[0])
    by_rayleigh = sorted(combos, key=lambda c: c[1])
    out("  %d combinations enumerated" % n)
    out("  shear-pattern residual: best %.2e at f=%s; runner-up %.2e at f=%s (x%.0f)"
        % (by_pattern[0][0], by_pattern[0][3], by_pattern[1][0], by_pattern[1][3], by_pattern[1][0] / by_pattern[0][0]))
    out("  Rayleigh-line residual: best %.3f at f=%s; runner-up %.3f at f=%s"
        % (by_rayleigh[0][1], by_rayleigh[0][3], by_rayleigh[1][1], by_rayleigh[1][3]))
    app = [c for c in combos if np.allclose(c[3], np.round(np.sort([abs(np.angle(l)) / (2 * np.pi * DT) for l in lam]), 3), atol=2e-3)]
    if app:
        out("  principal-branch (alias-blind) combination: pattern residual %.2e, Rayleigh residual %.3f"
            % (app[0][0], app[0][1]))
    agree = by_pattern[0][3].tolist() == by_rayleigh[0][3].tolist()
    out("  pattern and Rayleigh criteria select the same combination: %s" % agree)
    out("")

    out("2. isospectral twins of the true spectrum (as-tested masses)")
    rng = np.random.default_rng(0)
    w_true = 2 * np.pi * np.array(true_f)
    sols = []
    for _ in range(400):
        k0 = np.exp(rng.uniform(np.log(1e3), np.log(1e5), 4))
        k, cost = idlib.k_from_frequencies(w_true, mass, k0)
        if cost < 1e-20 and np.all(k > 0) and not any(np.allclose(k, q, rtol=1e-6) for q in sols):
            sols.append(k)
    sel = idlib.identify(t, disp, delay)
    _, _, phi_meas = idlib.modal_arrays(sel, mass)
    M = np.diag(mass)
    for k in sols:
        _, v = idlib.eig_modes(k, mass)
        mac = [(v[:, r] @ M @ phi_meas[:, r]) ** 2 / ((v[:, r] @ M @ v[:, r]) * (phi_meas[:, r] @ M @ phi_meas[:, r]))
               for r in range(4)]
        out("  k=%s  min MAC vs measured shapes %.4f%s" % (np.round(k, 1), min(mac),
                                                          "   <- true" if np.allclose(k, instance.K_TRUE, rtol=1e-6) else ""))
    out("  %d positive stiffness vectors share the four true frequencies" % len(sols))
    out("")

    out("3. outside readings of stated conventions (branch chosen by shutter-corrected realness)")
    readings = {
        "stated: row r captured at t_n + r*tau": delay,
        "timestamp at mid-frame row 540": delay - 540 * instance.ROW_PERIOD_S,
        "rows counted from 1": delay + instance.ROW_PERIOD_S,
        "rows read bottom-to-top (1080 rows)": (1079 - np.array(instance.FLOOR_ROW)) * instance.ROW_PERIOD_S,
    }
    for name, d in readings.items():
        fsel, best = [], []
        for r in range(4):
            sc = sorted(((idlib.realness(ps * np.exp(-s * d))[1], s) for s, ps in idlib.candidates(lam[r], psi[:, r], DT)),
                        key=lambda x: x[0])
            fsel.append(sc[0][1].imag / (2 * np.pi))
            best.append(sc[0][0])
        out("  %-42s -> f=%s  worst best-ratio %.2e" % (name, np.round(sorted(fsel), 3), max(best)))
    text = "\n".join(lines) + "\n"
    print(text)
    with open(os.path.join(HERE, "identifiability.log"), "w") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
