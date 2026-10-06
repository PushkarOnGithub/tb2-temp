#!/usr/bin/env python3
"""Reference solution: thermophysical inversion of the two-block heater test.

Reads only /app/data and writes /app/answer.json.

Chain (each step is forced by a stated property of the apparatus):
 1. Bead depths: the radiograph projects from a point focal spot, so depths
    measured at the detector are magnified by M = SID / (SID - OID).
 2. Heater power: the supply's voltage is taken at its own terminals, so V*I
    includes the lead/connector drop (V/I = 6.17 ohm vs a 5.800 ohm element).
    The power dissipated between the blocks is I^2 * R_element.
 3. Both blocks are half-spaces for the whole run (Fourier numbers checked), and
    they share the massless heater plane, so the specimen-side rise is
        theta(x, t) = sum_j dP_j/A * 2/(e_s + e_b) * sqrt(tau) * ierfc(x/(2 sqrt(alpha tau))):
    the data fix alpha_s and the *sum* of effusivities; the base block's
    effusivity is subtracted to get e_s.
 4. Logged values are means over the 2 s window ending at each timestamp; the
    model is integrated over each window in closed form
    (int_0^tau sqrt(s) ierfc(c/sqrt(s)) ds = 4 tau^{3/2} i^3erfc(c/sqrt(tau))).
 5. k = e_s sqrt(alpha), rho_c = e_s / sqrt(alpha).
 6. Panel scenarios: eigenfunction series, mu tan mu = Bi, Duhamel superposition.
"""

import csv
import json
import math
import os

import numpy as np
from scipy.optimize import brentq, least_squares
from scipy.special import erfc

DATA = "/app/data"
OUT = "/app/answer.json"
TC_COLUMNS = ("TC1_C", "TC2_C", "TC3_C", "TC4_C")


def read_csv(path):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {key: np.array([float(r[key]) for r in rows]) for key in rows[0]}


def ierfc3(z):
    """i^3 erfc(z) for z >= 0 by upward recurrence (clamped where it underflows)."""
    z = np.asarray(z, dtype=float)
    zc = np.minimum(z, 6.0)
    a = 2.0 / math.sqrt(math.pi) * np.exp(-zc * zc)
    b = erfc(zc)
    for k in (1, 2, 3):
        a, b = b, (a - 2.0 * zc * b) / (2.0 * k)
    return np.where(z > 6.0, 0.0, b)


def g3(x, tau, alpha):
    tau = np.asarray(tau, dtype=float)
    pos = tau > 0.0
    safe = np.where(pos, tau, 1.0)
    val = 4.0 * safe ** 1.5 * ierfc3(x / (2.0 * np.sqrt(alpha * safe)))
    return np.where(pos, val, 0.0)


def power_segments(t, current, r_element, window):
    """Piecewise-constant heater power from the logged (window-mean) current.

    The current only changes at timestamps, so consecutive windows with the same
    set point form a segment; its power is R * mean(I^2) over the segment.
    Returns a list of (start_time, power_increment).
    """
    edges = [0]
    for i in range(1, len(current)):
        if abs(current[i] - current[i - 1]) > 0.05:
            edges.append(i)
    edges.append(len(current))
    steps, prev = [], 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        p = r_element * float(np.mean(current[a:b] ** 2))
        if p < 1e-3:  # supply output off: readback noise only
            p = 0.0
        steps.append((float(t[a] - window), p - prev))
        prev = p
    return steps


def logger_means(x, t, window, steps, area, e_sum, alpha):
    out = np.zeros_like(t)
    for t_j, d_p in steps:
        out += d_p / area * 2.0 / e_sum * (g3(x, t - t_j, alpha) - g3(x, t - window - t_j, alpha)) / window
    return out


def panel_rise(k, rho_c, h, length, segments, x, t):
    alpha = k / rho_c
    bi = h * length / k
    steps, prev = [], 0.0
    for start, q in segments:
        steps.append((t - start, q - prev))
        prev = q
    taus = [tau for tau, dq in steps if tau > 0.0 and dq != 0.0]
    if not taus:
        return 0.0
    n = int(math.sqrt(50.0 * length ** 2 / (alpha * min(taus))) / math.pi) + 5
    f = lambda m: m * math.sin(m) - bi * math.cos(m)
    mu = np.array([brentq(f, j * math.pi, j * math.pi + 0.5 * math.pi, xtol=1e-14)
                   for j in range(n)])
    norm = 0.5 * length * (1.0 + np.sin(2.0 * mu) / (2.0 * mu))
    total = 0.0
    for tau, dq in steps:
        if tau <= 0.0 or dq == 0.0:
            continue
        coef = ((dq / k) * length ** 2 / mu ** 2 * (1.0 - np.cos(mu)) + (dq / h) * length * np.sin(mu) / mu) / norm
        total += dq * (length - x) / k + dq / h - float(np.sum(coef * np.cos(mu * x / length)
                                                                 * np.exp(-mu ** 2 * alpha * tau / length ** 2)))
    return total


def main():
    with open(os.path.join(DATA, "apparatus.json")) as fh:
        app = json.load(fh)
    with open(os.path.join(DATA, "queries.json")) as fh:
        scenarios = json.load(fh)["scenarios"]
    with open(os.path.join(DATA, "sensors.csv"), newline="") as fh:
        sensors = {r["id"]: float(r["depth_mm"]) for r in csv.DictReader(fh)}

    window = float(app["logger"]["interval_s"])
    area = app["heater"]["width_m"] * app["heater"]["length_m"]
    r_element = float(app["heater"]["element_resistance_ohm"])
    k_b = app["base_block"]["k_W_per_mK"]
    rc_b = app["base_block"]["rho_c_J_per_m3K"]
    e_b = math.sqrt(k_b * rc_b)
    thickness = app["specimen_block"]["thickness_m"]

    # 1. radiographic magnification
    sid = app["radiograph"]["focal_spot_to_detector_mm"]
    oid = app["radiograph"]["bead_plane_to_detector_mm"]
    mag = sid / (sid - oid)
    depths = [sensors["TC%d" % (j + 1)] / mag * 1e-3 for j in range(4)]

    runs = []
    for name in ("A", "B"):
        d = read_csv(os.path.join(DATA, "run_%s.csv" % name))
        # 2. element power, not supply-terminal power
        ratio = d["V_supply_V"][d["I_A"] > 0.5] / d["I_A"][d["I_A"] > 0.5]
        print("run %s: V/I = %.4f ohm vs element %.4f ohm -> leads dissipate the difference"
              % (name, float(np.median(ratio)), r_element))
        steps = power_segments(d["t_s"], d["I_A"], r_element, window)
        runs.append((d, steps))

    def residuals(p):
        e_sum, alpha = p[0] * 1e3, p[1] * 1e-7
        res = []
        for j, (d, steps) in enumerate(runs):
            for c, x in zip(TC_COLUMNS, depths):
                res.append(p[2 + j] + logger_means(x, d["t_s"], window, steps, area, e_sum, alpha) - d[c])
        return np.concatenate(res)

    t0_guess = [float(np.mean(d["TC1_C"][:10])) for d, _ in runs]
    fit = least_squares(residuals, [2.0, 3.0] + t0_guess, x_scale="jac", xtol=1e-14, ftol=1e-14, gtol=1e-14)
    e_sum, alpha = fit.x[0] * 1e3, fit.x[1] * 1e-7
    rms = float(np.sqrt(np.mean(fit.fun ** 2)))
    # pre-heating scatter, pooled over channels and runs (first 14 windows are before power-on)
    noise = float(np.sqrt(np.mean([np.var(d[c][:14], ddof=1) for d, _ in runs for c in TC_COLUMNS])))
    print("fit: e_s+e_b = %.2f, alpha = %.5e, rms = %.4f K (pre-heating scatter %.4f K)" % (e_sum, alpha, rms, noise))

    # 3. split: the base block takes e_b / (e_s + e_b) of the heater power
    e_s = e_sum - e_b
    k = e_s * math.sqrt(alpha)
    rho_c = e_s / math.sqrt(alpha)
    t_end = max(float(d["t_s"][-1]) for d, _ in runs)
    fo_s = alpha * t_end / thickness ** 2
    fo_b = (k_b / rc_b) * t_end / app["base_block"]["thickness_m"] ** 2
    print("k = %.5f W/m/K, rho_c = %.5e J/m3/K, Fo_specimen = %.3f, Fo_base = %.3f" % (k, rho_c, fo_s, fo_b))
    if not (fo_s < 0.1 and fo_b < 0.1 and rms < 2.0 * noise):
        raise SystemExit("half-space model not adequate for these data")

    preds = {}
    for sc in scenarios:
        segs = [(float(s), float(q)) for s, q in sc["flux_segments"]]
        rise = panel_rise(k, rho_c, float(sc["h_W_per_m2K"]), float(sc["L_mm"]) * 1e-3, segs,
                          float(sc["x_mm"]) * 1e-3, float(sc["t_s"]))
        preds[sc["id"]] = float(sc["T_init_C"]) + rise

    with open(OUT, "w") as fh:
        json.dump({"k": k, "rho_c": rho_c, "predictions": preds}, fh, indent=2)
        fh.write("\n")
    print("wrote", OUT, json.dumps(preds))


if __name__ == "__main__":
    main()
