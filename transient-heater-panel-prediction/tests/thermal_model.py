"""Verifier-side forward models, standard library only.

Two models live here:

* ``window_mean_rise`` - temperature rise inside the specimen block of the
  two-block transient heater test, averaged over a logger integration window.
  The heater plane is shared by two blocks that behave as half-spaces for the
  duration of a run, so the specimen-side rise is
      theta(x, t) = sum_j dP_j / A * 2 / (e_s + e_b) * sqrt(tau_j) * ierfc(x / (2 sqrt(alpha_s tau_j)))
  with tau_j = t - t_j.  Its time integral is closed form because
      d/dtau [tau^{3/2} i^3erfc(c / sqrt(tau))] = (1/4) tau^{1/2} ierfc(c / sqrt(tau)).
  Used only by the instance generator to produce the shipped logs.

* ``panel_theta`` - rise in a slab heated by a piecewise-constant net flux on
  x = 0 and cooled by convection on x = L (the graded scenario family), by
  eigenfunction expansion with mu tan mu = Bi.  Used to grade predictions.

Nothing here reads files or the environment.
"""

import math

SQRT_PI = math.sqrt(math.pi)


def ierfc_n(z, n):
    """n-th repeated integral of erfc for z >= 0 (i^0 erfc = erfc)."""
    if z > 6.0:
        # i^n erfc(6) < 1e-17 for n >= 0; the multiplying powers of tau are
        # tiny whenever z is this large, so the contribution is below 1e-15 K.
        return 0.0
    a = 2.0 / SQRT_PI * math.exp(-z * z)  # i^{-1} erfc
    b = math.erfc(z)  # i^0 erfc
    for k in range(1, n + 1):
        a, b = b, (a - 2.0 * z * b) / (2.0 * k)
    return b


def _g3(x, tau, alpha):
    """Antiderivative 4 tau^{3/2} i^3erfc(x / (2 sqrt(alpha tau))), zero for tau <= 0."""
    if tau <= 0.0:
        return 0.0
    return 4.0 * tau ** 1.5 * ierfc_n(x / (2.0 * math.sqrt(alpha * tau)), 3)


def window_mean_rise(x, t_end, window, power_steps, area, e_sum, alpha):
    """Mean specimen-side rise over (t_end - window, t_end] at depth x (m).

    power_steps: list of (t_j, dP_j) increments of the heater power (W).
    e_sum: e_specimen + e_base (W s^0.5 m^-2 K^-1); alpha: specimen diffusivity.
    """
    total = 0.0
    for t_j, d_p in power_steps:
        g = _g3(x, t_end - t_j, alpha) - _g3(x, t_end - window - t_j, alpha)
        total += d_p / area * 2.0 / e_sum * g / window
    return total


# ---------------------------------------------------------------------------
# Panel scenarios
# ---------------------------------------------------------------------------

def panel_roots(bi, count):
    """First ``count`` positive roots of mu tan(mu) = bi (bi > 0), by bisection.

    Root j lies in (j pi, j pi + pi/2); f(mu) = mu sin(mu) - bi cos(mu)
    changes sign across that bracket.
    """
    roots = []
    for j in range(count):
        lo = j * math.pi
        hi = lo + 0.5 * math.pi
        f_lo = lo * math.sin(lo) - bi * math.cos(lo)
        for _ in range(64):
            mid = 0.5 * (lo + hi)
            f_mid = mid * math.sin(mid) - bi * math.cos(mid)
            if f_mid == 0.0:
                lo = hi = mid
                break
            if (f_mid < 0.0) == (f_lo < 0.0):
                lo, f_lo = mid, f_mid
            else:
                hi = mid
        roots.append(0.5 * (lo + hi))
    return roots


def panel_theta(k, rho_c, h, length, segments, x, t):
    """Temperature rise at depth x (m), time t (s) in a slab of thickness ``length``.

    segments: list of (start_s, q_W_per_m2); q applies from its start to the
    next start (the last indefinitely); the first start is 0.  Face x = 0
    absorbs q, face x = length convects with coefficient h to the initial
    temperature.
    """
    alpha = k / rho_c
    bi = h * length / k
    steps = []
    prev = 0.0
    for start, q in segments:
        steps.append((t - start, q - prev))
        prev = q
    taus = [tau for tau, dq in steps if tau > 0.0 and dq != 0.0]
    if not taus:
        return 0.0
    tau_min = min(taus)
    # Enough terms that exp(-mu^2 alpha tau_min / L^2) < exp(-46) at the tail.
    mu_max = math.sqrt(46.0 * length * length / (alpha * tau_min))
    count = int(mu_max / math.pi) + 3
    if count > 200000:
        raise ValueError("panel series would need %d terms" % count)
    mus = panel_roots(bi, count)
    theta = 0.0
    for tau, dq in steps:
        if tau <= 0.0 or dq == 0.0:
            continue
        steady = dq * (length - x) / k + dq / h
        series = 0.0
        for mu in mus:
            norm = 0.5 * length * (1.0 + math.sin(2.0 * mu) / (2.0 * mu))
            coef = ((dq / k) * (length * length / (mu * mu)) * (1.0 - math.cos(mu))
                    + (dq / h) * (length * math.sin(mu) / mu)) / norm
            series += coef * math.cos(mu * x / length) * math.exp(-mu * mu * alpha * tau / (length * length))
        theta += steady - series
    return theta
