"""Wrong-method discriminator harness (authoring only).

Every variant is the reference pipeline with ONE analysis decision changed (or
several, for the compound trap-blind default), driven all the way to a written
answer.json and graded with the verifier's own reader and grading function.
For each variant the harness reports the fit RMS against the pre-heating
scatter (does the agent's natural self-check flag anything?), the recovered
k and rho_c, the visible/hidden scenarios outside tolerance, and the reward.

Run from the task root:  python3 authoring/evidence/variants.py [OUTDIR]
OUTDIR (optional) receives one answer.json per variant for docker re-grading.
"""

import importlib.util
import json
import math
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__

import numpy as np
from scipy.optimize import least_squares

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "environment", "data")
sys.path.insert(0, os.path.join(ROOT, "tests"))
import answer_format  # noqa: E402
import check_submission  # noqa: E402
import instance  # noqa: E402

spec = importlib.util.spec_from_file_location("ref", os.path.join(ROOT, "solution", "solve.py"))
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)

TCS = ref.TC_COLUMNS


def load():
    with open(os.path.join(DATA, "apparatus.json")) as fh:
        app = json.load(fh)
    with open(os.path.join(DATA, "queries.json")) as fh:
        scen = json.load(fh)["scenarios"]
    import csv
    with open(os.path.join(DATA, "sensors.csv"), newline="") as fh:
        sens = {r["id"]: float(r["depth_mm"]) for r in csv.DictReader(fh)}
    runs = [ref.read_csv(os.path.join(DATA, "run_%s.csv" % n)) for n in ("A", "B")]
    return app, scen, sens, runs


def segments_from(d, window, power_of):
    """Piecewise-constant power from window-mean readbacks with a chosen power formula."""
    cur, volt, t = d["I_A"], d["V_supply_V"], d["t_s"]
    edges = [0] + [i for i in range(1, len(cur)) if abs(cur[i] - cur[i - 1]) > 0.05] + [len(cur)]
    steps, prev = [], 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        p = float(np.mean(power_of(cur[a:b], volt[a:b])))
        if p < 1e-3:
            p = 0.0
        steps.append((float(t[a] - window), p - prev))
        prev = p
    return steps


def model_values(x, t, window, steps, area, e_sum, alpha, logger):
    if logger == "window_end":
        return ref.logger_means(x, t, window, steps, area, e_sum, alpha)
    if logger == "window_start":   # mean over (t, t + window]
        return ref.logger_means(x, t + window, window, steps, area, e_sum, alpha)
    if logger == "midpoint":       # instantaneous value at the window centre
        tt = t - 0.5 * window
    else:                          # "instant": instantaneous value at the timestamp
        tt = t
    out = np.zeros_like(t)
    for t_j, d_p in steps:
        tau = tt - t_j
        pos = tau > 0
        safe = np.where(pos, tau, 1.0)
        z = np.minimum(x / (2.0 * np.sqrt(alpha * safe)), 6.0)
        from scipy.special import erfc
        i1 = np.exp(-z * z) / math.sqrt(math.pi) - z * erfc(z)
        out += np.where(pos, d_p / area * 2.0 / e_sum * np.sqrt(safe) * i1, 0.0)
    return out


def pipeline(power="I2R", split="effusivity", depth="magnified", logger="window_end", t0="fit",
             panel_terms=None):
    app, scen, sens, runs = load()
    window = app["logger"]["interval_s"]
    area = app["heater"]["width_m"] * app["heater"]["length_m"]
    r_el = app["heater"]["element_resistance_ohm"]
    e_b = math.sqrt(app["base_block"]["k_W_per_mK"] * app["base_block"]["rho_c_J_per_m3K"])
    sid = app["radiograph"]["focal_spot_to_detector_mm"]
    oid = app["radiograph"]["bead_plane_to_detector_mm"]
    mag = {"magnified": sid / (sid - oid), "image": 1.0, "multiply": (sid - oid) / sid,
           "sod_over_sid_swapped": sid / oid}[depth]
    xs = [sens["TC%d" % (j + 1)] / mag * 1e-3 for j in range(4)]
    power_of = {"I2R": lambda i, v: r_el * i * i, "VI": lambda i, v: v * i, "V2R": lambda i, v: v * v / r_el}[power]
    steps = [segments_from(d, window, power_of) for d in runs]

    def resid(p):
        e_sum, alpha = p[0] * 1e3, p[1] * 1e-7
        out = []
        for j, d in enumerate(runs):
            base = p[2 + j] if t0 == "fit" else float(np.mean(np.concatenate([d[c][:14] for c in TCS])))
            for c, x in zip(TCS, xs):
                out.append(base + model_values(x, d["t_s"], window, steps[j], area, e_sum, alpha, logger) - d[c])
        return np.concatenate(out)

    p0 = [2.0, 3.0] + [float(np.mean(d["TC1_C"][:10])) for d in runs]
    if t0 != "fit":
        p0 = p0[:2]
    fit = least_squares(resid, p0, x_scale="jac", xtol=1e-14, ftol=1e-14, gtol=1e-14)
    e_sum, alpha = fit.x[0] * 1e3, fit.x[1] * 1e-7
    rms = float(np.sqrt(np.mean(fit.fun ** 2)))
    noise = float(np.sqrt(np.mean([np.var(d[c][:14], ddof=1) for d in runs for c in TCS])))
    e_s = {"effusivity": e_sum - e_b, "all_power_into_specimen": e_sum, "symmetric_half": e_sum / 2.0}[split]
    k, rho_c = e_s * math.sqrt(alpha), e_s / math.sqrt(alpha)
    preds = {}
    for sc in scen:
        segs = [(float(s), float(q)) for s, q in sc["flux_segments"]]
        if panel_terms is None:
            rise = ref.panel_rise(k, rho_c, sc["h_W_per_m2K"], sc["L_mm"] * 1e-3, segs, sc["x_mm"] * 1e-3, sc["t_s"])
        elif panel_terms == "fd_ie_51_1s":
            rise = fd_panel(k, rho_c, sc, 51, 1.0, 1.0)
        elif panel_terms == "fd_cn_51_1s":
            rise = fd_panel(k, rho_c, sc, 51, 1.0, 0.5)
        elif panel_terms == "fd_cn_101_0.25s":
            rise = fd_panel(k, rho_c, sc, 101, 0.25, 0.5)
        elif panel_terms == "fd_cn_401_0.02s":
            rise = fd_panel(k, rho_c, sc, 401, 0.02, 0.5)
        elif panel_terms == "mol_bdf_default":
            rise = mol_panel(k, rho_c, sc, 51, "BDF")
        else:
            rise = truncated_panel(k, rho_c, sc, panel_terms)
        preds[sc["id"]] = sc["T_init_C"] + rise
    return {"k": k, "rho_c": rho_c, "predictions": preds}, rms, noise


def truncated_panel(k, rho_c, sc, n_terms):
    """The panel series cut at a fixed small number of terms (a numerics shortcut)."""
    from scipy.optimize import brentq
    L, h, x, t = sc["L_mm"] * 1e-3, sc["h_W_per_m2K"], sc["x_mm"] * 1e-3, sc["t_s"]
    alpha, bi = k / rho_c, h * sc["L_mm"] * 1e-3 / k
    f = lambda m: m * math.sin(m) - bi * math.cos(m)
    mu = np.array([brentq(f, j * math.pi, j * math.pi + math.pi / 2, xtol=1e-14) for j in range(n_terms)])
    norm = 0.5 * L * (1 + np.sin(2 * mu) / (2 * mu))
    total, prev = 0.0, 0.0
    for start, q in sc["flux_segments"]:
        tau, dq = t - start, q - prev
        prev = q
        if tau <= 0 or dq == 0:
            continue
        coef = ((dq / k) * L * L / mu ** 2 * (1 - np.cos(mu)) + (dq / h) * L * np.sin(mu) / mu) / norm
        total += dq * (L - x) / k + dq / h - float(np.sum(coef * np.cos(mu * x / L) * np.exp(-mu ** 2 * alpha * tau / L ** 2)))
    return total


def fd_panel(k, rho_c, sc, nx, dt, theta_m):
    """Theta-method finite differences (ghost-node flux/Robin BCs), the usual quick numerics."""
    L, h, a = sc["L_mm"] * 1e-3, sc["h_W_per_m2K"], k / rho_c
    dx, n = L / (nx - 1), nx
    main = np.full(n, -2.0)
    up, lo = np.ones(n - 1), np.ones(n - 1)
    up[0], lo[-1], main[-1] = 2.0, 2.0, -2.0 - 2.0 * dx * h / k
    A = np.diag(main) + np.diag(up, 1) + np.diag(lo, -1)
    r = a * dt / dx ** 2
    M1 = np.eye(n) - theta_m * r * A
    M2 = np.eye(n) + (1 - theta_m) * r * A
    M1inv = np.linalg.inv(M1)
    def q_at(tt):
        q = 0.0
        for st, qq in sc["flux_segments"]:
            if st <= tt:
                q = qq
        return q
    T, t = np.zeros(n), 0.0
    b = np.zeros(n)
    b[0] = 2.0 * dx / k * a / dx ** 2
    for _ in range(int(round(sc["t_s"] / dt))):
        rhs = M2 @ T + dt * b * ((1 - theta_m) * q_at(t) + theta_m * q_at(t + dt))
        T = M1inv @ rhs
        t += dt
    return float(np.interp(sc["x_mm"] * 1e-3, np.linspace(0, L, n), T))


def mol_panel(k, rho_c, sc, nx, method):
    """Method of lines with SciPy's default solve_ivp tolerances."""
    from scipy.integrate import solve_ivp
    L, h, a = sc["L_mm"] * 1e-3, sc["h_W_per_m2K"], k / rho_c
    dx, n = L / (nx - 1), nx
    def q_at(tt):
        q = 0.0
        for st, qq in sc["flux_segments"]:
            if st <= tt:
                q = qq
        return q
    def f(t, T):
        d = np.empty(n)
        d[1:-1] = a * (T[:-2] - 2 * T[1:-1] + T[2:]) / dx ** 2
        d[0] = a * (2 * T[1] - 2 * T[0]) / dx ** 2 + 2 * a * q_at(t) / (k * dx)
        d[-1] = a * (2 * T[-2] - 2 * T[-1]) / dx ** 2 - 2 * a * h * T[-1] / (k * dx)
        return d
    sol = solve_ivp(f, (0.0, sc["t_s"]), np.zeros(n), method=method)
    return float(np.interp(sc["x_mm"] * 1e-3, np.linspace(0, L, n), sol.y[:, -1]))


VARIANTS = [
    # name, kwargs, expected reward, which trap / why
    ("P1_reference", {}, 1, "positive: the oracle pipeline"),
    ("P3_t0_from_pre_heating_mean", {"t0": "premean"}, 1, "positive: different nuisance handling"),
    ("P3_window_midpoint_approx", {"logger": "midpoint"}, 1, "positive-boundary: midpoint rule for the integrating logger"),
    ("N1_power_V_times_I", {"power": "VI"}, 0, "trap T1: supply-terminal power includes the lead drop"),
    ("N2_power_V2_over_R", {"power": "V2R"}, 0, "trap T1: supply-terminal voltage across the element"),
    ("N3_all_power_into_specimen", {"split": "all_power_into_specimen"}, 0, "trap T2: base block ignored"),
    ("N4_symmetric_half_split", {"split": "symmetric_half"}, 0, "trap T2: symmetric-sandwich assumption"),
    ("N5_radiograph_depths_as_is", {"depth": "image"}, 0, "trap T3: no magnification correction"),
    ("N6_magnification_inverted", {"depth": "multiply"}, 0, "trap T3: magnification applied the wrong way"),
    ("N7_logger_instantaneous", {"logger": "instant"}, 0, "logger integration ignored"),
    ("N8_logger_window_starts_at_stamp", {"logger": "window_start"}, 0, "logger window anchored at the wrong end"),
    ("N9_compound_default", {"power": "VI", "split": "all_power_into_specimen", "depth": "image", "logger": "instant"}, 0,
     "every tempting default at once"),
    ("P2b_panel_cn_401_nodes_0.02s", {"panel_terms": "fd_cn_401_0.02s"}, 1, "positive: converged finite differences"),
    ("B1_panel_series_5_terms", {"panel_terms": 5}, None, "boundary: panel series truncated at 5 terms"),
    ("N10_panel_fd_implicit_euler_51x1s", {"panel_terms": "fd_ie_51_1s"}, 0, "numerics: unconverged implicit Euler"),
    ("N11_panel_fd_cn_51x1s", {"panel_terms": "fd_cn_51_1s"}, 0, "numerics: Crank-Nicolson, coarse step after flux switches"),
    ("N12_panel_fd_cn_101x0.25s", {"panel_terms": "fd_cn_101_0.25s"}, 0, "numerics: Crank-Nicolson, still unconverged"),
    ("N13_panel_mol_bdf_default_tol", {"panel_terms": "mol_bdf_default"}, 0, "numerics: solve_ivp BDF at default rtol=1e-3"),
]


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else None
    proc = subprocess.run([sys.executable, "-I", "-S", os.path.join(ROOT, "tests", "derive_truth.py")],
                          capture_output=True, check=True, timeout=120)
    truth = json.loads(proc.stdout)
    rows, ok_all = [], True
    for name, kw, expect, why in VARIANTS:
        ans, rms, noise = pipeline(**kw)
        doc = answer_format.validate(json.loads(json.dumps(ans)), truth["visible_ids"])
        failures = check_submission.grade(truth, doc)
        reward = 0 if failures else 1
        vis_bad = sum(1 for f in failures if f.startswith("predictions."))
        hid_bad = 0
        for f in failures:
            if "hidden scenarios" in f:
                hid_bad = int(f.split()[0])
        dk = 100 * (ans["k"] / instance.K_SPECIMEN - 1)
        drc = 100 * (ans["rho_c"] / instance.RHO_C_SPECIMEN - 1)
        ok = expect is None or reward == expect
        ok_all &= ok
        rows.append((name, rms, noise, dk, drc, vis_bad, hid_bad, reward, expect, ok, why))
        if outdir:
            os.makedirs(os.path.join(outdir, name), exist_ok=True)
            with open(os.path.join(outdir, name, "answer.json"), "w") as fh:
                json.dump(ans, fh, indent=1)
    print("%-34s %8s %8s %9s %9s %5s %6s %6s %6s  %s" % ("variant", "fit_rms", "noise", "dk_%", "drho_c_%",
                                                             "vis!", "hid!", "reward", "expect", "why"))
    for r in rows:
        print("%-34s %8.4f %8.4f %+9.2f %+9.2f %3d/6 %3d/30 %6d %6d  %s%s" % (
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], -1 if r[8] is None else r[8], r[10], "" if r[9] else "   <-- UNEXPECTED"))
    print("HARNESS", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
