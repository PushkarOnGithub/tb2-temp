"""Reference solution: shear-frame model update from rolling-shutter video (output-only test).

Pipeline
 1. tracks (px) -> floor displacements (mm) with each target's own scale and
    the tracker-label -> floor map; remove the static image positions.
 2. Covariance-driven stochastic subspace identification (SSI-cov) on the four
    channels -> discrete poles lambda_r and complex shapes psi_r.
 3. Rolling shutter: floor j is sampled at t_n + delta_j, so its shape
    component carries exp(s_r * delta_j) with the *continuous* pole s_r.
    The video fixes only lambda_r = exp(s_r * dt): s_r is known up to
    2*pi*i*n/dt and conjugation.  Classical (Rayleigh) damping means real
    mode shapes, so the branch is the one whose shutter-corrected shape is
    real.  The highest mode is not where the spectrum shows it.
 4. Mass-normalise with the as-tested masses (design + mounted items),
    project M Phi Omega^2 Phi^T M onto the shear-frame pattern, then refine
    k by Newton on the four natural frequencies (far more precise than the
    shapes) starting from that projection, so the iteration stays on the
    branch the mode shapes select: several stiffness vectors share the same
    four frequencies.
"""

import json
import os
import sys

import numpy as np

DATA = "/app/data"
OUT = "/app/output/model.json"


def load():
    with open(os.path.join(DATA, "targets.json")) as fh:
        targets = json.load(fh)
    with open(os.path.join(DATA, "test_record.json")) as fh:
        record = json.load(fh)
    with open(os.path.join(DATA, "tracks.csv")) as fh:
        header = fh.readline().strip().split(",")
    raw = np.loadtxt(os.path.join(DATA, "tracks.csv"), delimiter=",", skiprows=1)
    t = raw[:, 0]
    n_floor = len(targets)
    disp = np.zeros((len(t), n_floor))
    delay = np.zeros(n_floor)
    for col, label in enumerate(header[1:], start=1):
        info = targets[label]
        j = int(info["floor"]) - 1
        disp[:, j] = (raw[:, col] - raw[:, col].mean()) * float(info["mm_per_px"])
        delay[j] = int(info["image_row"]) * float(record["camera"]["row_period_s"])
    mass = np.array([float(record["design_floor_mass_kg"][str(j + 1)]) for j in range(n_floor)])
    for item in record["mounted_during_test"]:
        mass[int(item["floor"]) - 1] += float(item["mass_kg"])
    return t, disp, delay, mass


def ssi_cov(y, block_rows=40, order=8):
    """Covariance-driven SSI: poles (upper half plane) and complex output shapes."""
    n, p = y.shape
    lags = [y[k:].T @ y[:n - k] / (n - k) for k in range(2 * block_rows + 1)]
    hank = np.block([[lags[a + b + 1] for b in range(block_rows)] for a in range(block_rows)])
    u, s, _ = np.linalg.svd(hank)
    obs = u[:, :order] * np.sqrt(s[:order])
    a = np.linalg.pinv(obs[:-p]) @ obs[p:]
    lam, vec = np.linalg.eig(a)
    shapes = obs[:p] @ vec
    keep = lam.imag > 0
    lam, shapes = lam[keep], shapes[:, keep]
    idx = np.argsort(np.abs(np.angle(lam)))
    return lam[idx], shapes[:, idx]


def realness(psi):
    """Rotate psi to its best real direction; return (real vector, imag/real ratio)."""
    r = psi * np.exp(-0.5j * np.angle(np.sum(psi ** 2)))
    return r.real, np.linalg.norm(r.imag) / np.linalg.norm(r.real)


def shear_k(k):
    n = len(k)
    kk = np.zeros((n, n))
    for j in range(n):
        kk[j, j] += k[j]
        if j > 0:
            kk[j - 1, j - 1] += k[j]
            kk[j - 1, j] -= k[j]
            kk[j, j - 1] -= k[j]
    return kk


def unit_storey(j, n):
    e = np.zeros(n)
    e[j] = 1.0
    return shear_k(e)


def eig_modes(k, mass):
    r = 1.0 / np.sqrt(mass)
    w2, v = np.linalg.eigh(shear_k(k) * np.outer(r, r))
    return w2, v * r[:, None]


def resolve_branch(lam, psi, delay, dt, n_max=3):
    """Continuous pole and shutter-corrected real shape for one identified mode."""
    cands = []
    for conj in (False, True):
        lm = np.conj(lam) if conj else lam
        ps = np.conj(psi) if conj else psi
        for n in range(-n_max, n_max + 1):
            s = (np.log(lm) + 2j * np.pi * n) / dt
            if s.imag <= 0:
                continue
            phi, ratio = realness(ps * np.exp(-s * delay))
            cands.append((ratio, s, phi))
    cands.sort(key=lambda c: c[0])
    return cands[0], cands[1][0] / cands[0][0]


def main():
    t, disp, delay, mass = load()
    dt = float(np.median(np.diff(t)))
    lam, psi = ssi_cov(disp)
    if len(lam) != 4:
        raise SystemExit("expected four oscillatory modes, found %d" % len(lam))

    poles, shapes = [], []
    for r in range(4):
        (ratio, s, phi), margin = resolve_branch(lam[r], psi[:, r], delay, dt)
        print("mode %d: apparent %.4f Hz -> %.4f Hz, shutter-corrected imag/real %.2e, next branch x%.0f worse"
              % (r + 1, abs(np.angle(lam[r])) / (2 * np.pi * dt), s.imag / (2 * np.pi), ratio, margin))
        poles.append(s)
        shapes.append(phi)
    poles = np.array(poles)
    order = np.argsort(np.abs(poles))
    omega = np.abs(poles)[order]
    phi = np.array(shapes).T[:, order]

    m = np.diag(mass)
    phi = phi / np.sqrt(np.einsum("ir,ij,jr->r", phi, m, phi))
    k_mat = m @ phi @ np.diag(omega ** 2) @ phi.T @ m
    n = len(mass)
    basis = np.array([unit_storey(j, n).ravel() for j in range(n)]).T
    k0, *_ = np.linalg.lstsq(basis, k_mat.ravel(), rcond=None)
    resid = np.linalg.norm(k_mat.ravel() - basis @ k0) / np.linalg.norm(k_mat)
    print("shear-pattern residual of M Phi W^2 Phi^T M: %.2e; projected k: %s" % (resid, np.round(k0, 1)))

    k = k0.copy()
    for _ in range(60):
        w2, v = eig_modes(k, mass)
        jac = np.array([[v[:, r] @ unit_storey(j, n) @ v[:, r] for j in range(n)] for r in range(n)])
        step = np.linalg.solve(jac, omega ** 2 - w2)
        k = k + step
        if np.max(np.abs(step) / k) < 1e-13:
            break
    _, v = eig_modes(k, mass)
    mac = [(v[:, r] @ m @ phi[:, r]) ** 2 / ((v[:, r] @ m @ v[:, r]) * (phi[:, r] @ m @ phi[:, r]))
           for r in range(n)]
    print("refined k:", np.round(k, 1), " MAC vs measured shapes:", np.round(mac, 4))
    if min(mac) < 0.95 or np.any(k <= 0):
        raise SystemExit("frequency refinement left the branch selected by the mode shapes")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"k": [float(x) for x in k]}, fh, indent=2)
        fh.write("\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
