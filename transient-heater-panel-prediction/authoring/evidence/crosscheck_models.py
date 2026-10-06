"""Independent cross-check of the verifier's forward models (authoring only).

Structurally different route: exact Laplace-domain solutions of the *finite*
geometries stated in the instruction, inverted numerically with Talbot's method
at 30 significant digits (mpmath), versus the closed forms in tests/thermal_model.py.

1. Two-block test: 60 mm specimen + 60 mm base, insulated outer faces, massless
   heater at the interface.  For a unit power step,
       Tbar_h(s) = P / (A s sqrt(s) [e_s tanh(L sqrt(s/a_s)) + e_b tanh(L sqrt(s/a_b))])
       Tbar_s(x, s) = Tbar_h cosh((L - x) sqrt(s/a_s)) / cosh(L sqrt(s/a_s))
   The logger mean over a window is the time integral, i.e. Tbar/s, differenced.
2. Panel: flux step q on x = 0, Robin (h) on x = L:
       thetabar(x, s) = (q/s) [cosh(b(L-x)) + (h/(k b)) sinh(b(L-x))] / (k b sinh(bL) + h cosh(bL)).

Run from the task root:  python3 authoring/evidence/crosscheck_models.py
"""

import os
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__

import mpmath as mp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
import instance as I  # noqa: E402
import thermal_model as tm  # noqa: E402

mp.mp.dps = 30


def finite_window_mean(x, t_end, window, steps, area):
    ks, rcs = mp.mpf(I.K_SPECIMEN), mp.mpf(I.RHO_C_SPECIMEN)
    kb, rcb = mp.mpf(I.BASE_K), mp.mpf(I.BASE_RHO_C)
    a_s, a_b = ks / rcs, kb / rcb
    e_s, e_b = mp.sqrt(ks * rcs), mp.sqrt(kb * rcb)
    L = mp.mpf(I.BLOCK_THICKNESS)
    x = mp.mpf(x)

    def integral_unit(tau):
        # time integral from 0 to tau of the response to a unit power step
        if tau <= 0:
            return mp.mpf(0)
        f = lambda s: (1 / (mp.mpf(area) * s * s * mp.sqrt(s)
                            * (e_s * mp.tanh(L * mp.sqrt(s / a_s)) + e_b * mp.tanh(L * mp.sqrt(s / a_b))))
                       * mp.cosh((L - x) * mp.sqrt(s / a_s)) / mp.cosh(L * mp.sqrt(s / a_s)))
        return mp.invertlaplace(f, mp.mpf(tau), method="talbot")

    total = mp.mpf(0)
    for t_j, d_p in steps:
        total += mp.mpf(d_p) * (integral_unit(t_end - t_j) - integral_unit(t_end - window - t_j)) / window
    return total


def laplace_panel(k, rho_c, h, length, segments, x, t):
    k, rho_c, h, L, x = map(mp.mpf, (k, rho_c, h, length, x))
    a = k / rho_c

    def unit(tau):
        if tau <= 0:
            return mp.mpf(0)
        def f(s):
            b = mp.sqrt(s / a)
            return (1 / s) * (mp.cosh(b * (L - x)) + h / (k * b) * mp.sinh(b * (L - x))) / (
                k * b * mp.sinh(b * L) + h * mp.cosh(b * L))
        return mp.invertlaplace(f, mp.mpf(tau), method="talbot")

    out = mp.mpf(0)
    prev = 0.0
    for start, q in segments:
        out += (q - prev) * unit(t - start)
        prev = q
    return out


def main():
    worst = 0.0
    depths = I.true_depths_m()
    area = I.HEATER_W * I.HEATER_L
    e_sum = I.effusivity(I.K_SPECIMEN, I.RHO_C_SPECIMEN) + I.effusivity(I.BASE_K, I.BASE_RHO_C)
    alpha = I.K_SPECIMEN / I.RHO_C_SPECIMEN
    print("[1] two-block logger means: closed form (half-spaces) vs finite 60 mm blocks (Talbot)")
    for run in ("A", "B"):
        steps = I.power_steps(I.RUNS[run]["program"])
        for t in (32.0, 34.0, 60.0, 182.0, 300.0, 400.0, 480.0):
            for x in (depths[0], depths[3]):
                a = tm.window_mean_rise(x, t, I.INTERVAL, steps, area, e_sum, alpha)
                b = float(finite_window_mean(x, t, I.INTERVAL, steps, area))
                worst = max(worst, abs(a - b))
                print("  run %s t=%6.1f x=%.5f m  closed=%.9f  talbot=%.9f  diff=%.2e K" % (run, t, x, a, b, a - b))
    print("  max |diff| = %.2e K (logger resolution 1e-3 K, noise 1.5e-2 K)" % worst)

    print("[2] panel series vs Talbot inversion")
    worst_p = 0.0
    cases = list(I.VISIBLE) + [sc for sc in I.heldout_scenarios()[:12]]
    for sc in cases:
        segs = [(float(s), float(q)) for s, q in sc["flux_segments"]]
        a = tm.panel_theta(I.K_SPECIMEN, I.RHO_C_SPECIMEN, sc["h_W_per_m2K"], sc["L_mm"] * 1e-3,
                           segs, sc["x_mm"] * 1e-3, sc["t_s"])
        b = float(laplace_panel(I.K_SPECIMEN, I.RHO_C_SPECIMEN, sc["h_W_per_m2K"], sc["L_mm"] * 1e-3,
                                segs, sc["x_mm"] * 1e-3, sc["t_s"]))
        worst_p = max(worst_p, abs(a - b) / max(abs(b), 1e-12))
        print("  %s series=%.10f talbot=%.10f rel=%.2e" % (sc["id"], a, b, (a - b) / b))
    print("  max rel diff = %.2e" % worst_p)
    ok = worst < 2e-5 and worst_p < 1e-9
    print("CROSSCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
