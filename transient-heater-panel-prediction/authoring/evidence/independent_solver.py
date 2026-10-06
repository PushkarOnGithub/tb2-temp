"""Independent solver (authoring only): no closed forms anywhere.

Structurally different from solution/solve.py:
  * the whole stack (60 mm base + heater + 60 mm specimen, insulated outer
    faces) is simulated by finite volumes on a stretched grid, so the heat split
    between the blocks is never derived - it emerges from the simulation;
  * time integration is Crank-Nicolson with two backward-Euler half steps
    after every power switch (Rannacher start), dt = 0.05 s;
  * logger means are trapezoidal integrals of the simulated history over each
    2 s window; thermocouple temperatures are 3-point Lagrange interpolants;
  * heater power is taken window by window as I^2 R from the logged current
    (no segment detection); initial temperatures are profiled out exactly;
  * k and rho_c are fitted directly (not via effusivity/diffusivity);
  * panel predictions use a separate Crank-Nicolson finite-difference solver.
It reads only environment/data (the same files the agent sees) and writes an
answer.json.  Run from the task root:
    python3 authoring/evidence/independent_solver.py OUT.json
"""

import csv
import json
import math
import os
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__

import numpy as np
from scipy.linalg import solve_banded
from scipy.optimize import least_squares

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "environment", "data")
DT = 0.05


def read_run(name):
    with open(os.path.join(DATA, "run_%s.csv" % name), newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


def stretched(length, first, growth, fine_to, fine_dx):
    """Node positions 0..length: uniform fine_dx up to fine_to, then geometric growth."""
    xs = list(np.arange(0.0, fine_to + 1e-12, fine_dx))
    dx = fine_dx
    while xs[-1] < length - 1e-12:
        dx *= growth
        xs.append(min(xs[-1] + dx, length))
    return np.array(xs)


class Stack:
    def __init__(self, k_s, rc_s, k_b, rc_b, thick, heater_cap=0.0, r_contact=0.0, outer="insulated"):
        """heater_cap (J m^-2 K^-1), r_contact (m^2 K W^-1, specimen side) and outer
        ('insulated' | 'isothermal') default to the stated apparatus; the mutation
        study switches them to probe how much each stated assumption bites."""
        xs = stretched(thick, 0.0, 1.07, 8.0e-3, 0.05e-3)       # specimen side, x >= 0
        xb = stretched(thick, 0.0, 1.07, 2.0e-3, 0.10e-3)       # base side (mirrored)
        self.x = np.concatenate([-xb[::-1], xs[1:]])
        self.i0 = len(xb) - 1                                   # heater node
        n = len(self.x)
        k = np.where(self.x[:-1] + self.x[1:] < 0.0, k_b, k_s)  # face conductivities
        rc = np.where(np.arange(n) < self.i0, rc_b, rc_s)
        dxf = np.diff(self.x)
        cap = np.zeros(n)                                       # node heat capacity per area
        for i in range(n - 1):
            cap[i] += 0.5 * dxf[i] * (rc_b if i < self.i0 else rc_s)
            cap[i + 1] += 0.5 * dxf[i] * (rc_b if i < self.i0 else rc_s)
        g = k / dxf                                             # face conductances
        if r_contact > 0.0:
            g[self.i0] = 1.0 / (1.0 / g[self.i0] + r_contact)
        cap[self.i0] += heater_cap
        self.g_end = 1.0e6 if outer == "isothermal" else 0.0     # tie outer nodes to the initial temperature
        self.cap, self.g, self.n = cap, g, n

    def operator_bands(self, theta, dt):
        """Banded (I - theta dt C^-1 K) and the explicit part's tridiagonal (I + (1-theta) dt C^-1 K)."""
        n, g, cap = self.n, self.g, self.cap
        diag = np.zeros(n)
        diag[:-1] += g
        diag[1:] += g
        diag[0] += self.g_end
        diag[-1] += self.g_end
        lower = np.zeros(n)
        upper = np.zeros(n)
        upper[1:] = -g     # coefficient of T[i+1] in row i stored at upper[i+1]
        lower[:-1] = -g    # coefficient of T[i-1] in row i stored at lower[i-1]
        ab = np.zeros((3, n))
        ab[0] = theta * dt * upper / np.roll(cap, 1)
        ab[0, 0] = 0.0
        ab[1] = 1.0 + theta * dt * diag / cap
        ab[2] = theta * dt * lower / np.roll(cap, -1)
        ab[2, -1] = 0.0
        return ab, diag

    def apply_k(self, T):
        """-(K T): net conductive inflow per node."""
        out = np.zeros(self.n)
        flow = self.g * (T[1:] - T[:-1])
        out[:-1] += flow
        out[1:] -= flow
        out[0] -= self.g_end * T[0]
        out[-1] -= self.g_end * T[-1]
        return out


def simulate_run(stack, power, t_end, window, depths):
    """Logger means at the thermocouples; power[i] is the heater power in window i."""
    n_win = len(power)
    steps_per_win = int(round(window / DT))
    T = np.zeros(stack.n)
    ab_cn, _ = stack.operator_bands(0.5, DT)
    ab_be, _ = stack.operator_bands(1.0, DT / 2.0)
    src = np.zeros(stack.n)
    idx = [int(np.searchsorted(stack.x, d)) for d in depths]

    def probe(T):
        vals = []
        for d, j in zip(depths, idx):
            j = min(max(j, 1), stack.n - 2)
            xa, xb, xc = stack.x[j - 1], stack.x[j], stack.x[j + 1]
            la = (d - xb) * (d - xc) / ((xa - xb) * (xa - xc))
            lb = (d - xa) * (d - xc) / ((xb - xa) * (xb - xc))
            lc = (d - xa) * (d - xb) / ((xc - xa) * (xc - xb))
            vals.append(la * T[j - 1] + lb * T[j] + lc * T[j + 1])
        return np.array(vals)

    means = np.zeros((n_win, len(depths)))
    prev_p = 0.0
    for w in range(n_win):
        p = power[w]
        src[:] = 0.0
        src[stack.i0] = p
        acc = 0.5 * probe(T)
        for s in range(steps_per_win):
            if s == 0 and p != prev_p:
                for _ in range(2):  # Rannacher start after a switch
                    rhs = T + (DT / 2.0) * src / stack.cap
                    T = solve_banded((1, 1), ab_be, rhs)
            else:
                rhs = T + 0.5 * DT * stack.apply_k(T) / stack.cap + DT * src / stack.cap
                T = solve_banded((1, 1), ab_cn, rhs)
            acc += probe(T) if s < steps_per_win - 1 else 0.5 * probe(T)
        means[w] = acc / steps_per_win
        prev_p = p
    return means


def panel_fd(k, rho_c, sc, nx=801, dt=0.01):
    L, h = sc["L_mm"] * 1e-3, sc["h_W_per_m2K"]
    a = k / rho_c
    dx = L / (nx - 1)
    n = nx
    main = np.full(n, -2.0)
    up = np.ones(n - 1)
    lo = np.ones(n - 1)
    up[0] = 2.0
    lo[-1] = 2.0
    main[-1] = -2.0 - 2.0 * dx * h / k
    r = a / dx ** 2

    def bands(theta, step):
        ab = np.zeros((3, n))
        ab[0, 1:] = -theta * step * r * up
        ab[1] = 1.0 - theta * step * r * main
        ab[2, :-1] = -theta * step * r * lo
        return ab

    def q_at(tt):
        q = 0.0
        for st, qq in sc["flux_segments"]:
            if st <= tt + 1e-9:
                q = qq
        return q

    def apply_a(T):
        out = main * T
        out[:-1] += up * T[1:]
        out[1:] += lo * T[:-1]
        return out

    ab_cn, ab_be = bands(0.5, dt), bands(1.0, dt / 2.0)
    bvec = np.zeros(n)
    bvec[0] = 2.0 * a / (k * dx)
    T = np.zeros(n)
    t = 0.0
    nsteps = int(round(sc["t_s"] / dt))
    switch_steps = {int(round(st / dt)) for st, _ in sc["flux_segments"]}
    for i in range(nsteps):
        if i in switch_steps:
            for _ in range(2):
                T = solve_banded((1, 1), ab_be, T + (dt / 2.0) * bvec * q_at(t + dt / 2.0))
        else:
            q0, q1 = q_at(t), q_at(t + dt)
            T = solve_banded((1, 1), ab_cn, T + 0.5 * dt * r * apply_a(T) + dt * bvec * 0.5 * (q0 + q1))
        t += dt
    return float(np.interp(sc["x_mm"] * 1e-3, np.linspace(0.0, L, n), T))


def fit_stack(stack_opts=None):
    """Fit k, rho_c with the full-stack simulation; returns (k, rho_c, rms, predictions)."""
    stack_opts = stack_opts or {}
    with open(os.path.join(DATA, "apparatus.json")) as fh:
        app = json.load(fh)
    with open(os.path.join(DATA, "queries.json")) as fh:
        scenarios = json.load(fh)["scenarios"]
    with open(os.path.join(DATA, "sensors.csv"), newline="") as fh:
        img = {r["id"]: float(r["depth_mm"]) for r in csv.DictReader(fh)}
    sid = app["radiograph"]["focal_spot_to_detector_mm"]
    oid = app["radiograph"]["bead_plane_to_detector_mm"]
    depths = [img["TC%d" % j] * 1e-3 * (sid - oid) / sid for j in (1, 2, 3, 4)]
    area = app["heater"]["width_m"] * app["heater"]["length_m"]
    r_el = app["heater"]["element_resistance_ohm"]
    window = app["logger"]["interval_s"]
    runs = [read_run(n) for n in ("A", "B")]
    powers = [r_el * d["I_A"] ** 2 / area for d in runs]
    powers = [np.where(p < 1e-3 / area, 0.0, p) for p in powers]
    obs = [np.stack([d["TC%d_C" % j] for j in (1, 2, 3, 4)], axis=1) for d in runs]

    def resid(p):
        stack = Stack(p[0], p[1] * 1e6, app["base_block"]["k_W_per_mK"], app["base_block"]["rho_c_J_per_m3K"],
                      app["specimen_block"]["thickness_m"], **stack_opts)
        out = []
        for pw, ob, d in zip(powers, obs, runs):
            model = simulate_run(stack, pw, d["t_s"][-1], window, depths)
            out.append((float(np.mean(ob - model)) + model - ob).ravel())
        return np.concatenate(out)

    fit = least_squares(resid, [0.4, 2.0], diff_step=1e-6, xtol=1e-12, ftol=1e-12, gtol=1e-12)
    k_s, rc_s = float(fit.x[0]), float(fit.x[1] * 1e6)
    rms = float(np.sqrt(np.mean(fit.fun ** 2)))
    preds = {sc["id"]: sc["T_init_C"] + panel_fd(k_s, rc_s, sc) for sc in scenarios}
    return k_s, rc_s, rms, preds


def main(out_path):
    with open(os.path.join(DATA, "apparatus.json")) as fh:
        app = json.load(fh)
    with open(os.path.join(DATA, "queries.json")) as fh:
        scenarios = json.load(fh)["scenarios"]
    with open(os.path.join(DATA, "sensors.csv"), newline="") as fh:
        img = {r["id"]: float(r["depth_mm"]) for r in csv.DictReader(fh)}
    sid = app["radiograph"]["focal_spot_to_detector_mm"]
    oid = app["radiograph"]["bead_plane_to_detector_mm"]
    depths = [img["TC%d" % j] * 1e-3 * (sid - oid) / sid for j in (1, 2, 3, 4)]
    area = app["heater"]["width_m"] * app["heater"]["length_m"]
    r_el = app["heater"]["element_resistance_ohm"]
    window = app["logger"]["interval_s"]
    runs = [read_run(n) for n in ("A", "B")]
    powers = [r_el * d["I_A"] ** 2 / area for d in runs]          # W/m^2 per window
    powers = [np.where(p < 1e-3 / area, 0.0, p) for p in powers]
    obs = [np.stack([d["TC%d_C" % j] for j in (1, 2, 3, 4)], axis=1) for d in runs]

    def resid(p):
        k_s, rc_s = p[0], p[1] * 1e6
        stack = Stack(k_s, rc_s, app["base_block"]["k_W_per_mK"], app["base_block"]["rho_c_J_per_m3K"],
                      app["specimen_block"]["thickness_m"])
        out = []
        for pw, ob, d in zip(powers, obs, runs):
            model = simulate_run(stack, pw, d["t_s"][-1], window, depths)
            t0 = float(np.mean(ob - model))                        # profiled-out initial temperature
            out.append((t0 + model - ob).ravel())
        return np.concatenate(out)

    fit = least_squares(resid, [0.4, 2.0], diff_step=1e-6, xtol=1e-12, ftol=1e-12, gtol=1e-12)
    k_s, rc_s = float(fit.x[0]), float(fit.x[1] * 1e6)
    rms = float(np.sqrt(np.mean(fit.fun ** 2)))
    print("independent FD fit: k = %.5f, rho_c = %.5e, rms = %.4f K, nfev = %d" % (k_s, rc_s, rms, fit.nfev))
    preds = {sc["id"]: sc["T_init_C"] + panel_fd(k_s, rc_s, sc) for sc in scenarios}
    with open(out_path, "w") as fh:
        json.dump({"k": k_s, "rho_c": rc_s, "predictions": preds}, fh, indent=1)
    print("predictions:", json.dumps(preds))


if __name__ == "__main__":
    main(sys.argv[1])
