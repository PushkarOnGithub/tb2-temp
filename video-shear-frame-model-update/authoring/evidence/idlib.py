"""Author-side identification toolkit used by variants.py (numpy/scipy).

Nothing in solution/ or tests/ imports this file.  Each building block has a
switch for one plausible way of getting a step wrong, so that every wrong
method can be driven all the way to a submitted model.json.
"""

import json
import os

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("VSF_DATA") or os.path.normpath(os.path.join(HERE, "..", "..", "environment", "data"))


def load(mapping="file", units="per_target"):
    with open(os.path.join(DATA, "targets.json")) as fh:
        targets = json.load(fh)
    with open(os.path.join(DATA, "test_record.json")) as fh:
        record = json.load(fh)
    with open(os.path.join(DATA, "tracks.csv")) as fh:
        header = fh.readline().strip().split(",")
    raw = np.loadtxt(os.path.join(DATA, "tracks.csv"), delimiter=",", skiprows=1)
    t = raw[:, 0]
    labels = header[1:]
    disp = np.zeros((len(t), 4))
    delay = np.zeros(4)
    mean_scale = np.mean([targets[l]["mm_per_px"] for l in labels])
    for col, label in enumerate(labels, start=1):
        info = targets[label]
        j = int(info["floor"]) - 1 if mapping == "file" else col - 1
        if units == "per_target":
            sc = info["mm_per_px"]
        elif units == "mean":
            sc = mean_scale
        else:
            sc = 1.0
        disp[:, j] = raw[:, col] * sc
        delay[j] = info["image_row"] * record["camera"]["row_period_s"] if mapping == "file" else \
            targets[label]["image_row"] * record["camera"]["row_period_s"]
    design = np.array([record["design_floor_mass_kg"][str(j + 1)] for j in range(4)], float)
    tested = design.copy()
    for item in record["mounted_during_test"]:
        tested[item["floor"] - 1] += item["mass_kg"]
    return t, disp, delay, design, tested


def shear_k(k):
    K = np.zeros((4, 4))
    for j in range(4):
        K[j, j] += k[j]
        if j > 0:
            K[j - 1, j - 1] += k[j]; K[j - 1, j] -= k[j]; K[j, j - 1] -= k[j]
    return K


def eig_modes(k, mass):
    r = 1.0 / np.sqrt(mass)
    w2, v = np.linalg.eigh(shear_k(k) * np.outer(r, r))
    return np.sqrt(np.abs(w2)), v * r[:, None]


def era(y, order=8, block_rows=100):
    n, p = y.shape
    cols = n - block_rows
    h0 = np.empty((block_rows * p, cols)); h1 = np.empty((block_rows * p, cols))
    for i in range(block_rows):
        h0[i * p:(i + 1) * p] = y[i:i + cols].T
        h1[i * p:(i + 1) * p] = y[i + 1:i + 1 + cols].T
    u, s, vt = np.linalg.svd(h0, full_matrices=False)
    u, s, vt = u[:, :order], s[:order], vt[:order]
    sh = np.diag(s ** -0.5)
    a = sh @ u.T @ h1 @ vt.T @ sh
    c = (u * np.sqrt(s))[:p]
    lam, vec = np.linalg.eig(a)
    shp = c @ vec
    keep = lam.imag > 0
    lam, shp = lam[keep], shp[:, keep]
    o = np.argsort(np.abs(np.angle(lam)))
    return lam[o], shp[:, o]


def ssi_cov(y, block_rows=40, order=8):
    n, p = y.shape
    lags = [y[k:].T @ y[:n - k] / (n - k) for k in range(2 * block_rows + 1)]
    hank = np.block([[lags[a + b + 1] for b in range(block_rows)] for a in range(block_rows)])
    u, s, _ = np.linalg.svd(hank)
    obs = u[:, :order] * np.sqrt(s[:order])
    a = np.linalg.pinv(obs[:-p]) @ obs[p:]
    lam, vec = np.linalg.eig(a)
    shp = obs[:p] @ vec
    keep = lam.imag > 0
    lam, shp = lam[keep], shp[:, keep]
    o = np.argsort(np.abs(np.angle(lam)))
    return lam[o], shp[:, o]


def next_era(y, max_lag=200, order=8, block_rows=80):
    """NExT-ERA: cross-correlations with every reference channel, then ERA."""
    y = y - y.mean(0)
    n, p = y.shape
    blocks = []
    for ref in range(p):
        r = np.array([y[k:].T @ y[:n - k, ref] / (n - k) for k in range(1, max_lag + 1)])
        blocks.append(r)
    lam, shp = era(np.concatenate(blocks, axis=1), order=order, block_rows=block_rows)
    out = []
    for i in range(len(lam)):
        sh = shp[:, i].reshape(p, p, order="F")
        out.append(sh[:, np.argmax(np.linalg.norm(sh, axis=0))])
    return lam, np.array(out).T


def fdd_modes(t, disp, n_modes=4, nperseg=4096, min_sep_hz=0.5):
    """Frequency-domain decomposition: peaks of the first singular value of the CSD matrix.

    Returns a list of (apparent frequency Hz, complex singular vector).
    """
    from scipy.signal import csd
    dt = float(np.median(np.diff(t)))
    y = disp - disp.mean(0)
    p = y.shape[1]
    G = None
    for i in range(p):
        for j in range(p):
            f, g = csd(y[:, i], y[:, j], fs=1.0 / dt, nperseg=nperseg)
            if G is None:
                G = np.zeros((len(f), p, p), complex)
            G[:, i, j] = g
    u1 = np.zeros((len(f), p), complex)
    s1 = np.zeros(len(f))
    for n in range(len(f)):
        u, sv, _ = np.linalg.svd(G[n])
        u1[n], s1[n] = u[:, 0], sv[0]
    peaks = [n for n in range(2, len(f) - 2) if s1[n] > s1[n - 1] and s1[n] >= s1[n + 1]]
    chosen = []
    for n in sorted(peaks, key=lambda n: -s1[n]):
        if all(abs(f[n] - f[c]) > min_sep_hz for c in chosen):
            chosen.append(n)
        if len(chosen) == n_modes:
            break
    out = []
    for n in sorted(chosen):
        a, b, c = np.log(s1[n - 1:n + 2])
        d = 0.5 * (a - c) / (a - 2 * b + c)
        out.append((f[n] + d * (f[1] - f[0]), u1[n]))
    return out


def fdd_resolve(fa, u, delay, fs, m_max=3):
    """Branch for an FDD peak: the component at continuous frequency nu = fa + m*fs."""
    best = None
    for psi in (u, np.conj(u)):
        for m in range(-m_max, m_max + 1):
            nu = fa + m * fs
            if nu == 0:
                continue
            phi, ratio = realness(psi * np.exp(-2j * np.pi * nu * delay))
            if best is None or ratio < best[0]:
                best = (ratio, abs(nu), phi)
    return best


def realness(psi):
    ang = -0.5 * np.angle(np.sum(psi ** 2))
    r = psi * np.exp(1j * ang)
    if r.real[np.argmax(np.abs(r))] < 0:
        r = -r
    return r.real, np.linalg.norm(r.imag) / np.linalg.norm(r.real)


def candidates(lam, psi, dt, n_max=3):
    out = []
    for conj in (False, True):
        lm = np.conj(lam) if conj else lam
        ps = np.conj(psi) if conj else psi
        for n in range(-n_max, n_max + 1):
            s = (np.log(lm) + 2j * np.pi * n) / dt
            if s.imag > 0:
                out.append((s, ps))
    return out


def true_frequencies_hz():
    """Author-side oracle used only to isolate one error per variant."""
    import sys
    sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "tests")))
    import frame_model
    import instance
    return frame_model.natural_frequencies_hz(instance.K_TRUE, instance.as_tested_mass())


def identify(t, disp, delay, branch="realness", shutter="modal", preprocess="ssi"):
    """Return list of (continuous pole, real mode shape) for the four modes.

    branch:   'principal' (alias-blind), 'realness' (shutter-corrected shape must
              be real), 'rayleigh' (decay rates on one Rayleigh line), 'fold'
              (highest mode assumed folded once without reflection), 'oracle'
              (the true branch; isolates the effect of another error).
    shutter:  'modal' (correct shapes with exp(-s*delta)), 'ignore',
              'spline' (resample channels to frame times before ERA).
    """
    import itertools
    dt = float(np.median(np.diff(t)))
    y = disp.copy()
    if shutter == "spline":
        tt = t[2:-2]
        y = np.column_stack([CubicSpline(t + delay[j], disp[:, j])(tt) for j in range(4)])
    y = y - y.mean(0)
    lam, psi = next_era(y) if preprocess == "next" else ssi_cov(y)
    corr = delay if shutter == "modal" else np.zeros(4)
    cand = [candidates(lam[r], psi[:, r], dt) for r in range(4)]
    if branch == "principal":
        chosen = [(np.log(lam[r]) / dt, psi[:, r]) for r in range(4)]
    elif branch == "fold":
        chosen = [(np.log(lam[r]) / dt + (2j * np.pi / dt if r == 3 else 0), psi[:, r]) for r in range(4)]
    elif branch == "realness":
        chosen = [min(c, key=lambda x: realness(x[1] * np.exp(-x[0] * delay))[1]) for c in cand]
    elif branch == "naive-positive":
        # fold rule applied, but every candidate is a positive frequency f = n*fs +/- fa and the
        # identified (positive-frequency) shape is referred to a common instant with exp(-2j*pi*f*delta):
        # the conjugate image of a mode folded from the upper half-band is never considered.
        fs = 1.0 / dt
        chosen = []
        for r in range(4):
            fa = abs(np.angle(lam[r])) / (2 * np.pi * dt)
            best = None
            for n in range(0, 4):
                for sgn in (1, -1):
                    f = n * fs + sgn * fa
                    if f <= 0:
                        continue
                    ratio = realness(psi[:, r] * np.exp(-2j * np.pi * f * delay))[1]
                    if best is None or ratio < best[0]:
                        sigma = -np.log(abs(lam[r])) / dt
                        best = (ratio, complex(-sigma, 2 * np.pi * f), psi[:, r])
            chosen.append((best[1], best[2]))
    elif branch == "oracle":
        ft = true_frequencies_hz()
        chosen = []
        for c in cand:
            chosen.append(min(c, key=lambda x: min(abs(x[0].imag / (2 * np.pi) - f) for f in ft)))
    elif branch == "rayleigh":
        best, best_res = None, np.inf
        for combo in itertools.product(*cand):
            s = np.array([c[0] for c in combo])
            w = np.abs(s)
            if np.max(w) > 2 * np.pi * 60:
                continue
            A = np.column_stack([np.ones(4), w ** 2])
            sig = -s.real
            coef, *_ = np.linalg.lstsq(A, sig, rcond=None)
            res = np.linalg.norm(A @ coef - sig) / np.linalg.norm(sig)
            if coef.min() >= 0 and res < best_res:
                best, best_res = combo, res
        chosen = list(best)
    else:
        raise ValueError(branch)
    sel = [(s, realness(ps * np.exp(-s * corr))[0]) for s, ps in chosen]
    sel.sort(key=lambda x: abs(x[0]))
    return sel


def modal_arrays(sel, mass):
    s = np.array([x[0] for x in sel])
    phi = np.array([x[1] for x in sel]).T
    M = np.diag(mass)
    phi = phi / np.sqrt(np.einsum("ir,ij,jr->r", phi, M, phi))
    return np.abs(s), -s.real / np.abs(s), phi


def k_from_shapes(omega, phi, mass):
    M = np.diag(mass)
    K = M @ phi @ np.diag(omega ** 2) @ phi.T @ M
    basis = np.array([shear_k(np.eye(4)[j]).ravel() for j in range(4)]).T
    k, *_ = np.linalg.lstsq(basis, K.ravel(), rcond=None)
    return k


def k_from_frequencies(omega, mass, k0):
    r = lambda lk: np.log(eig_modes(np.exp(lk), mass)[0] / omega)
    sol = least_squares(r, np.log(np.maximum(k0, 1.0)), xtol=1e-15, ftol=1e-15, gtol=1e-15)
    return np.exp(sol.x), sol.cost


def rayleigh(omega, zeta, units="rad"):
    w = omega if units == "rad" else omega / (2 * np.pi)
    A = np.column_stack([1 / (2 * w), w / 2])
    coef, *_ = np.linalg.lstsq(A, zeta, rcond=None)
    return float(coef[0]), float(coef[1])


def fft_peaks(t, disp, n_modes=4, min_sep_hz=0.5):
    """Peak picking on the Welch auto-spectra summed over channels; half-power damping."""
    from scipy.signal import welch
    dt = float(np.median(np.diff(t)))
    fr, p = welch(disp - disp.mean(0), fs=1.0 / dt, nperseg=4096, axis=0)
    spec = p.sum(axis=1)
    cand = [i for i in range(2, len(spec) - 2) if spec[i] > spec[i - 1] and spec[i] >= spec[i + 1]]
    peaks = []
    for i in sorted(cand, key=lambda i: -spec[i]):
        if all(abs(fr[i] - fr[c]) > min_sep_hz for c in peaks):
            peaks.append(i)
        if len(peaks) == n_modes:
            break
    peaks = sorted(peaks)
    f, z = [], []
    for i in peaks:
        half = spec[i] / 2
        lo = i
        while lo > 0 and spec[lo] > half:
            lo -= 1
        hi = i
        while hi < len(spec) - 1 and spec[hi] > half:
            hi += 1
        f.append(fr[i]); z.append((fr[hi] - fr[lo]) / (2 * fr[i]))
    return 2 * np.pi * np.array(f), np.array(z)
