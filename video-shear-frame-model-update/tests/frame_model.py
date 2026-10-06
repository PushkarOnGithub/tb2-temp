"""Shear-frame forward model, standard library only.

The verifier runs this module under ``python3 -I -S``, so nothing outside the
standard library may be imported.  Two structurally different eigen-solvers
are provided: a cyclic Jacobi rotation solver on the full symmetric matrix and
a Sturm-sequence bisection on the tridiagonal form.  ``derive_truth`` requires
them to agree before any value is graded.
"""

import math

N_FLOORS = 4


def shear_stiffness(k):
    """Lateral stiffness matrix of a shear frame fixed at its base.

    Storey j (1-based) joins floor j-1 and floor j; floor 0 is the rigid base.
    """
    n = len(k)
    K = [[0.0] * n for _ in range(n)]
    for j in range(n):
        K[j][j] += k[j]
        if j > 0:
            K[j - 1][j - 1] += k[j]
            K[j - 1][j] -= k[j]
            K[j][j - 1] -= k[j]
    return K


def _mass_scaled(k, m):
    """Return A = M^-1/2 K M^-1/2 (symmetric, tridiagonal)."""
    K = shear_stiffness(k)
    n = len(m)
    r = [1.0 / math.sqrt(x) for x in m]
    return [[K[i][j] * r[i] * r[j] for j in range(n)] for i in range(n)]


def jacobi_eigh(A, tol=1e-15, max_sweeps=100):
    """Cyclic Jacobi eigen-decomposition of a small symmetric matrix.

    Returns (eigenvalues ascending, eigenvectors as columns).
    """
    n = len(A)
    a = [row[:] for row in A]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    scale = max(abs(a[i][j]) for i in range(n) for j in range(n)) or 1.0
    for _ in range(max_sweeps):
        off = math.sqrt(sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j))
        if off <= tol * scale:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) <= 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * apq)
                t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for i in range(n):
                    aip, aiq = a[i][p], a[i][q]
                    a[i][p] = c * aip - s * aiq
                    a[i][q] = s * aip + c * aiq
                for i in range(n):
                    api, aqi = a[p][i], a[q][i]
                    a[p][i] = c * api - s * aqi
                    a[q][i] = s * api + c * aqi
                for i in range(n):
                    vip, viq = v[i][p], v[i][q]
                    v[i][p] = c * vip - s * viq
                    v[i][q] = s * vip + c * viq
    else:
        raise ArithmeticError("Jacobi iteration did not converge")
    order = sorted(range(n), key=lambda i: a[i][i])
    vals = [a[i][i] for i in order]
    vecs = [[v[r][i] for i in order] for r in range(n)]
    return vals, vecs


def sturm_eigenvalues(k, m, rel_tol=1e-15):
    """Eigenvalues of M^-1 K by Sturm-sequence bisection on the tridiagonal form."""
    A = _mass_scaled(k, m)
    n = len(A)
    d = [A[i][i] for i in range(n)]
    e = [A[i][i + 1] for i in range(n - 1)]
    bound = max(abs(d[i]) + (abs(e[i - 1]) if i > 0 else 0.0) + (abs(e[i]) if i < n - 1 else 0.0)
                for i in range(n))

    def count_below(x):
        cnt = 0
        q = d[0] - x
        if q < 0.0:
            cnt += 1
        for i in range(1, n):
            if q == 0.0:
                q = 1e-300
            q = d[i] - x - e[i - 1] * e[i - 1] / q
            if q < 0.0:
                cnt += 1
        return cnt

    vals = []
    for idx in range(n):
        lo, hi = -bound, bound
        for _ in range(400):
            mid = 0.5 * (lo + hi)
            if count_below(mid) > idx:
                hi = mid
            else:
                lo = mid
            if hi - lo <= rel_tol * max(abs(hi), abs(lo), 1e-300):
                break
        vals.append(0.5 * (lo + hi))
    return vals


def modes(k, m):
    """Undamped modes: (omega rad/s ascending, mass-normalised shapes as columns)."""
    vals, vecs = jacobi_eigh(_mass_scaled(k, m))
    n = len(m)
    omegas = []
    for lam in vals:
        if not lam > 0.0:
            raise ArithmeticError("non-positive eigenvalue")
        omegas.append(math.sqrt(lam))
    # phi = M^-1/2 v  (mass-normalised because v is orthonormal)
    phi = [[vecs[i][r] / math.sqrt(m[i]) for r in range(n)] for i in range(n)]
    return omegas, phi


def natural_frequencies_hz(k, m):
    vals, _ = jacobi_eigh(_mass_scaled(k, m))
    out = []
    for lam in vals:
        if not lam > 0.0:
            raise ArithmeticError("non-positive eigenvalue")
        out.append(math.sqrt(lam) / (2.0 * math.pi))
    return out


def rayleigh_zeta(a0, a1, omega):
    """Modal damping ratio of C = a0*M + a1*K for a mode of frequency omega (rad/s)."""
    return a0 / (2.0 * omega) + a1 * omega / 2.0


def configuration_frequencies(k, m, added_mass, stiffness_factor):
    """Undamped natural frequencies (Hz, ascending) of one configuration."""
    kk = [k[j] * stiffness_factor[j] for j in range(len(k))]
    mm = [m[j] + added_mass[j] for j in range(len(m))]
    return natural_frequencies_hz(kk, mm)
