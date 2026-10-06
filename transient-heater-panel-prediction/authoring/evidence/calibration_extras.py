"""Extra calibration measurements on the final instance (authoring only).

1. Monte Carlo: 60 fresh noise realisations of both runs, full reference
   pipeline, graded with the verifier's grade(); reports the spread of k, rho_c
   and the worst |T - T_true| / band over all 36 graded temperatures.
2. Numerical-scheme errors on the six visible scenarios.
3. Cross-validation false confidence: fit run A only, predict run B, for the
   reference and each silent trap.
Run from the task root:  python3 authoring/evidence/calibration_extras.py
"""

import importlib.util
import json
import math
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import answer_format  # noqa: E402
import check_submission  # noqa: E402
import instance  # noqa: E402
import variants  # noqa: E402

spec = importlib.util.spec_from_file_location("ref", os.path.join(ROOT, "solution", "solve.py"))
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def band_ratio(truth, ans):
    worst = 0.0
    for sc in truth["visible_scenarios"]:
        t = truth["visible"][sc["id"]]
        worst = max(worst, abs(ans["predictions"][sc["id"]] - t) / (truth["rel_tol"] * abs(t - sc["T_init_C"]) + truth["abs_tol"]))
    for item in truth["heldout"]:
        sc, t = item["scenario"], item["T_true"]
        p = check_submission.scenario_temperature(ans["k"], ans["rho_c"], sc)
        worst = max(worst, abs(p - t) / (truth["rel_tol"] * abs(t - sc["T_init_C"]) + truth["abs_tol"]))
    return worst


def main():
    truth = json.loads(subprocess.run([sys.executable, "-I", "-S", os.path.join(ROOT, "tests", "derive_truth.py")],
                                      capture_output=True, check=True, timeout=120).stdout)
    print("[1] Monte Carlo over noise realisations (reference pipeline)")
    dk, drc, ratios = [], [], []
    files = instance.shipped_files()
    for seed in range(60):
        with tempfile.TemporaryDirectory() as d:
            for name, blob in files.items():
                if name.startswith("run_"):
                    blob = instance.run_csv(name[4], noise_tag="-mc%d" % seed)
                with open(os.path.join(d, name), "wb") as fh:
                    fh.write(blob)
            out = os.path.join(d, "answer.json")
            ref.DATA, ref.OUT = d, out
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                ref.main()
            ans = answer_format.read_answer(out, truth["visible_ids"])
        dk.append(ans["k"] / instance.K_SPECIMEN - 1)
        drc.append(ans["rho_c"] / instance.RHO_C_SPECIMEN - 1)
        ratios.append(band_ratio(truth, ans))
    dk, drc, ratios = map(np.array, (dk, drc, ratios))
    print("    k: mean %+.2e sd %.2e max|.| %.2e   rho_c: mean %+.2e sd %.2e max|.| %.2e"
          % (dk.mean(), dk.std(), np.abs(dk).max(), drc.mean(), drc.std(), np.abs(drc).max()))
    print("    worst |T - T_true| / band over 36 graded temperatures: median %.3f, max %.3f (pass needs <= 1)"
          % (np.median(ratios), ratios.max()))

    print("[2] numerical schemes on the visible scenarios (relative error of the rise)")
    k, rc = instance.K_SPECIMEN, instance.RHO_C_SPECIMEN
    schemes = [("FD implicit Euler 51 nodes dt=1s", lambda sc: variants.fd_panel(k, rc, sc, 51, 1.0, 1.0)),
               ("FD Crank-Nicolson 51 nodes dt=1s", lambda sc: variants.fd_panel(k, rc, sc, 51, 1.0, 0.5)),
               ("FD Crank-Nicolson 101 nodes dt=0.25s", lambda sc: variants.fd_panel(k, rc, sc, 101, 0.25, 0.5)),
               ("FD Crank-Nicolson 401 nodes dt=0.02s", lambda sc: variants.fd_panel(k, rc, sc, 401, 0.02, 0.5)),
               ("MOL solve_ivp BDF default tolerances", lambda sc: variants.mol_panel(k, rc, sc, 51, "BDF")),
               ("MOL solve_ivp RK45 default tolerances", lambda sc: variants.mol_panel(k, rc, sc, 51, "RK45")),
               ("eigen-series 5 terms", lambda sc: variants.truncated_panel(k, rc, sc, 5))]
    for name, fn in schemes:
        cells = []
        for sc in instance.VISIBLE:
            tr = instance.scenario_theta(k, rc, sc)
            band = (instance.REL_TOL * tr + instance.ABS_TOL) / tr
            e = fn(sc) / tr - 1
            cells.append("%s %+.4f%s" % (sc["id"], e, "*" if abs(e) > band else " "))
        print("    %-40s %s" % (name, "  ".join(cells)))
    print("    (* = outside the band)")

    print("[3] fit run A only, predict run B (RMS on run B; pre-heating scatter ~0.014 K)")
    for label, kw in [("reference", {}), ("T1 V*I", {"power": "VI"}), ("T2 all power", {"split": "all_power_into_specimen"}),
                      ("T3 depths as-is", {"depth": "image"})]:
        print("    %-16s RMS on unseen run B = %.4f K" % (label, crossval(**kw)))


def crossval(power="I2R", split="effusivity", depth="magnified"):
    from scipy.optimize import least_squares
    app, scen, sens, runs = variants.load()
    window = app["logger"]["interval_s"]
    area = app["heater"]["width_m"] * app["heater"]["length_m"]
    r_el = app["heater"]["element_resistance_ohm"]
    sid = app["radiograph"]["focal_spot_to_detector_mm"]
    oid = app["radiograph"]["bead_plane_to_detector_mm"]
    mag = sid / (sid - oid) if depth == "magnified" else 1.0
    xs = [sens["TC%d" % (j + 1)] / mag * 1e-3 for j in range(4)]
    pw = {"I2R": lambda i, v: r_el * i * i, "VI": lambda i, v: v * i}[power]
    steps = [variants.segments_from(d, window, pw) for d in runs]

    def model(p, j):
        return [p[2] + ref.logger_means(x, runs[j]["t_s"], window, steps[j], area, p[0] * 1e3, p[1] * 1e-7) for x in xs]

    def resid_a(p):
        return np.concatenate([m - runs[0][c] for m, c in zip(model(p, 0), ref.TC_COLUMNS)])
    fa = least_squares(resid_a, [2.0, 3.0, 22.0], x_scale="jac", xtol=1e-14, ftol=1e-14, gtol=1e-14)

    def resid_b(t0):
        p = [fa.x[0], fa.x[1], t0[0]]
        return np.concatenate([m - runs[1][c] for m, c in zip(model(p, 1), ref.TC_COLUMNS)])
    fb = least_squares(resid_b, [23.0])
    return float(np.sqrt(np.mean(fb.fun ** 2)))


if __name__ == "__main__":
    main()
