"""Structurally different solver: physical spectral (Whittle) fit with explicit aliasing.

No modal identification and no branch enumeration.  The model is the shear
frame itself (k1..k4, a0, a1) driven at floor 1 by white force of unknown
level, plus white tracker noise of unknown level.  Its sampled cross-spectral
matrix is computed exactly as the camera sees it:

    S_y(nu) = sum_m D(w_m) H(w_m) S0 H(w_m)^H D(w_m)^H / dt + sigma^2 I,
    w_m = 2 pi (nu + m fs),  D(w) = diag(exp(i w delta_j)),

i.e. every continuous frequency folds onto nu and carries its own rolling-
shutter phase.  The Welch CSD matrix of the shipped tracks is fitted by the
Whittle likelihood.  Started from the reference estimate it must converge
to the same stiffnesses; started from the alias-blind default it must
either move to the true model or end with a far worse likelihood.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import json
import os

import numpy as np
from scipy.optimize import minimize
from scipy.signal import csd

import idlib

HERE = os.path.dirname(os.path.abspath(__file__))
FS = 25.0
DT = 1.0 / FS
M_FOLD = 4


def welch_matrix(disp, nperseg=1024):
    y = disp - disp.mean(0)
    p = y.shape[1]
    G = None
    for i in range(p):
        for j in range(p):
            f, g = csd(y[:, i], y[:, j], fs=FS, nperseg=nperseg, return_onesided=True)
            if G is None:
                G = np.zeros((len(f), p, p), complex)
            G[:, i, j] = g
    keep = (f > 0.05) & (f < FS / 2 - 0.05)
    nseg = 2 * len(y) // nperseg - 1
    # scipy csd(x, y) = E[conj(X) Y]; the model is E[Y Y^H], so conjugate.
    return f[keep], np.conj(G[keep]), nseg


def model_matrix(theta, f, delay, mass):
    k = np.exp(theta[:4])
    a0, a1 = theta[4], theta[5] * 1e-4
    s0, s2 = np.exp(theta[6]), np.exp(theta[7])
    w, phi = idlib.eig_modes(k, mass)
    z = a0 / (2 * w) + a1 * w / 2
    S = np.zeros((len(f), 4, 4), complex)
    for m in range(-M_FOLD, M_FOLD + 1):
        om = 2 * np.pi * (f + m * FS)
        H = np.zeros((len(f), 4), complex)
        for r in range(4):
            H += np.outer(1.0 / (w[r] ** 2 - om ** 2 + 2j * z[r] * w[r] * om), phi[:, r] * phi[0, r])
        H = H * np.exp(1j * np.outer(om, delay))
        S += s0 * H[:, :, None] * np.conj(H[:, None, :])
    S += s2 * np.eye(4)[None]
    return S


def whittle(theta, f, G, delay, mass):
    if theta[4] < 0 or theta[5] < 0:
        return 1e12
    S = model_matrix(theta, f, delay, mass)
    try:
        L = np.linalg.cholesky(S)
    except np.linalg.LinAlgError:
        return 1e12
    logdet = 2 * np.sum(np.log(np.abs(np.diagonal(L, axis1=1, axis2=2))))
    tr = np.real(np.trace(np.linalg.solve(S, G), axis1=1, axis2=2))
    return float(np.sum(logdet + tr))


def fit(theta0, f, G, delay, mass):
    res = minimize(whittle, theta0, args=(f, G, delay, mass), method="Nelder-Mead",
                   options={"maxiter": 20000, "maxfev": 20000, "xatol": 1e-7, "fatol": 1e-6})
    res = minimize(whittle, res.x, args=(f, G, delay, mass), method="Powell",
                   options={"maxiter": 20000, "xtol": 1e-8, "ftol": 1e-10})
    return res


def level_guess(theta_k, f, G, delay, mass):
    """Best force and noise levels for given (k, a0, a1), by a coarse scan."""
    best = None
    for ls0 in np.linspace(-12, 4, 33):
        for ls2 in np.linspace(-16, -4, 25):
            th = np.r_[theta_k, ls0, ls2]
            v = whittle(th, f, G, delay, mass)
            if best is None or v < best[0]:
                best = (v, th)
    return best[1]


def heldout_error(k):
    import variants
    return variants.worst_error({"k": [float(x) for x in k]})[0]


def main():
    global M_FOLD
    t, disp, delay, design, mass = idlib.load()
    f, G, nseg = welch_matrix(disp)
    with open(os.path.join(HERE, "run_records.json")) as fh:
        recs = {r["variant"]: r for r in json.load(fh)}
    ref_k = np.array(recs["P1-oracle"]["artifact"]["k"])
    blind_k = np.array(recs["N1-alias-blind-freq-update"]["artifact"]["k"])
    lines = ["Whittle fit of the shear-frame model to the Welch CSD matrix (%d bins, %d segments)" % (len(f), nseg),
             "graded quantity: max relative error of the 164 held-out natural frequencies (tolerance 3%)", ""]
    runs = [
        ("folding |m|<=4, shutter modelled, start: reference x1.05", 4, True, ref_k * 1.05),
        ("folding |m|<=4, shutter modelled, start: alias-blind default", 4, True, blind_k),
        ("negative control: no folding, shutter modelled", 0, True, blind_k),
        ("negative control: folding, shutter delays ignored", 4, False, blind_k),
    ]
    for name, mf, use_rs, k0 in runs:
        M_FOLD = mf
        d = delay if use_rs else np.zeros(4)
        th0 = level_guess(np.r_[np.log(k0), 0.15, 1.0], f, G, d, mass)
        res = fit(th0, f, G, d, mass)
        k = np.exp(res.x[:4])
        lines.append("%-62s -> k=%s a0=%.4f a1=%.3e  -logL=%.4e  held-out max err %.2f%%"
                     % (name, np.round(k, 1), res.x[4], res.x[5] * 1e-4, res.fun, 100 * heldout_error(k)))
        print(lines[-1], flush=True)
    text = "\n".join(lines)
    with open(os.path.join(HERE, "independent_solver.log"), "w") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
