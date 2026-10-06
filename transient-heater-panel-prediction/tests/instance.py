"""The task instance: hidden truth, apparatus, logged runs and scenarios.

Standard library only.  ``build()`` regenerates, byte for byte, every file
shipped in the agent image under /app/data, plus the visible-scenario truth,
the held-out scenarios (never shipped) and their truth.  The verifier runs it
in an isolated interpreter and checks the result against tests/lock.json, so
the graded truth is derived from the same code that produced the agent's data.
"""

import json
import math
import random

import thermal_model as tm

# --- hidden truth: the specimen material -----------------------------------
K_SPECIMEN = 0.5862          # W m^-1 K^-1
RHO_C_SPECIMEN = 1.6385e6    # J m^-3 K^-1

# --- apparatus (shipped in apparatus.json unless marked hidden) -------------
HEATER_R_ELEMENT = 5.800     # ohm, element only, temperature-independent
R_LEADS = 0.372              # ohm, supply leads + connectors (hidden; V/I - R_element)
HEATER_W = 0.080             # m
HEATER_L = 0.080             # m
LEAD_LENGTH = 1.5            # m
BLOCK_THICKNESS = 0.060      # m, both blocks
BASE_K = 1.140               # borosilicate glass
BASE_RHO_C = 1.728e6
INTERVAL = 2.0               # s, integrating logger
SID_MM = 1000.0              # X-ray focal spot to detector
OID_MM = 120.0               # bead plane to detector
DEPTHS_IMAGE_MM = (1.364, 2.955, 4.659, 6.477)   # as measured on the detector

SIGMA_T = 0.015              # K, thermocouple noise after integration
SIGMA_I = 0.0003             # A
SIGMA_V = 0.002              # V

RUNS = {
    "A": {"T0": 22.814, "t_end": 420.0,
          "program": [(0.0, 0.0), (30.0, 2.400), (180.0, 1.200), (300.0, 0.0)]},
    "B": {"T0": 23.162, "t_end": 420.0,
          "program": [(0.0, 0.0), (30.0, 3.000), (70.0, 0.0), (130.0, 3.000),
                      (170.0, 0.0), (230.0, 2.000), (330.0, 0.0)]},
}

# --- graded scenario family -------------------------------------------------
VISIBLE = [
    {"id": "P1", "L_mm": 10.0, "h_W_per_m2K": 25.0, "T_init_C": 22.0,
     "flux_segments": [[0.0, 3000.0]], "x_mm": 0.0, "t_s": 300.0},
    {"id": "P2", "L_mm": 6.0, "h_W_per_m2K": 60.0, "T_init_C": 25.0,
     "flux_segments": [[0.0, 5000.0], [120.0, 0.0]], "x_mm": 6.0, "t_s": 400.0},
    {"id": "P3", "L_mm": 15.0, "h_W_per_m2K": 10.0, "T_init_C": 20.0,
     "flux_segments": [[0.0, 2000.0], [200.0, 4000.0], [500.0, 800.0]], "x_mm": 4.0, "t_s": 650.0},
    {"id": "P4", "L_mm": 4.5, "h_W_per_m2K": 35.0, "T_init_C": 23.5,
     "flux_segments": [[0.0, 1500.0], [60.0, 5000.0]], "x_mm": 1.0, "t_s": 64.0},
    {"id": "P5", "L_mm": 18.0, "h_W_per_m2K": 8.0, "T_init_C": 19.0,
     "flux_segments": [[0.0, 3000.0], [400.0, 0.0]], "x_mm": 9.0, "t_s": 1500.0},
    {"id": "P6", "L_mm": 12.0, "h_W_per_m2K": 20.0, "T_init_C": 22.0,
     "flux_segments": [[0.0, 5000.0], [90.0, 0.0]], "x_mm": 0.0, "t_s": 95.0},
]
N_HELDOUT = 30
HELDOUT_SEED = "heldout-scenarios-v1"
REL_TOL = 0.005              # of the true rise above T_init
ABS_TOL = 0.010              # K


def magnification():
    return SID_MM / (SID_MM - OID_MM)


def true_depths_m():
    m = magnification()
    return [d / m * 1e-3 for d in DEPTHS_IMAGE_MM]


def effusivity(k, rho_c):
    return math.sqrt(k * rho_c)


def current_at(program, t_window_end):
    """Current during the window ending at t (programs change only at timestamps)."""
    cur = 0.0
    for start, amps in program:
        if start < t_window_end:
            cur = amps
    return cur


def power_steps(program):
    steps = []
    prev = 0.0
    for start, amps in program:
        p = amps * amps * HEATER_R_ELEMENT
        if p != prev:
            steps.append((start, p - prev))
            prev = p
    return steps


def run_csv(name, noise_tag=""):
    """Logger file for one run; noise_tag != "" draws an independent noise realisation
    (authoring Monte Carlo only; the shipped files use the default)."""
    run = RUNS[name]
    depths = true_depths_m()
    e_sum = effusivity(K_SPECIMEN, RHO_C_SPECIMEN) + effusivity(BASE_K, BASE_RHO_C)
    alpha = K_SPECIMEN / RHO_C_SPECIMEN
    area = HEATER_W * HEATER_L
    steps = power_steps(run["program"])
    rng_i = random.Random("run-%s-I%s" % (name, noise_tag))
    rng_v = random.Random("run-%s-V%s" % (name, noise_tag))
    rng_tc = [random.Random("run-%s-TC%d%s" % (name, j + 1, noise_tag)) for j in range(4)]
    lines = ["t_s,I_A,V_supply_V,TC1_C,TC2_C,TC3_C,TC4_C"]
    n = int(round(run["t_end"] / INTERVAL))
    for i in range(1, n + 1):
        t = i * INTERVAL
        amps = current_at(run["program"], t)
        i_log = amps + rng_i.gauss(0.0, SIGMA_I)
        v_log = amps * (HEATER_R_ELEMENT + R_LEADS) + rng_v.gauss(0.0, SIGMA_V)
        fields = ["%.1f" % t, "%.4f" % i_log, "%.3f" % v_log]
        for j, x in enumerate(depths):
            rise = tm.window_mean_rise(x, t, INTERVAL, steps, area, e_sum, alpha)
            fields.append("%.3f" % (run["T0"] + rise + rng_tc[j].gauss(0.0, SIGMA_T)))
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode("ascii")


def sensors_csv():
    lines = ["id,depth_mm"]
    for j, d in enumerate(DEPTHS_IMAGE_MM):
        lines.append("TC%d,%.3f" % (j + 1, d))
    return ("\n".join(lines) + "\n").encode("ascii")


def apparatus_json():
    doc = {
        "heater": {
            "element_resistance_ohm": HEATER_R_ELEMENT,
            "width_m": HEATER_W,
            "length_m": HEATER_L,
            "supply_lead_length_m": LEAD_LENGTH,
        },
        "specimen_block": {"thickness_m": BLOCK_THICKNESS},
        "base_block": {
            "material": "borosilicate glass",
            "thickness_m": BLOCK_THICKNESS,
            "k_W_per_mK": BASE_K,
            "rho_c_J_per_m3K": BASE_RHO_C,
        },
        "logger": {"interval_s": INTERVAL},
        "radiograph": {
            "focal_spot_to_detector_mm": SID_MM,
            "bead_plane_to_detector_mm": OID_MM,
        },
    }
    return (json.dumps(doc, indent=2) + "\n").encode("ascii")


def queries_json():
    return (json.dumps({"scenarios": VISIBLE}, indent=2) + "\n").encode("ascii")


def scenario_theta(k, rho_c, sc):
    segs = [(float(s), float(q)) for s, q in sc["flux_segments"]]
    return tm.panel_theta(k, rho_c, float(sc["h_W_per_m2K"]), float(sc["L_mm"]) * 1e-3,
                          segs, float(sc["x_mm"]) * 1e-3, float(sc["t_s"]))


def heldout_scenarios():
    """Held-out scenarios: same family as VISIBLE, drawn from a fixed seed."""
    rng = random.Random(HELDOUT_SEED)
    out = []
    while len(out) < N_HELDOUT:
        length = round(rng.uniform(4.0, 18.0), 1)
        h = round(rng.uniform(6.0, 70.0) * 2.0) / 2.0
        nseg = rng.choice((1, 2, 3))
        segs = [[0.0, float(round(rng.uniform(1000.0, 5000.0), -1))]]
        start = 0.0
        for _ in range(nseg - 1):
            start += float(round(rng.uniform(60.0, 400.0)))
            q = 0.0 if rng.random() < 0.35 else float(round(rng.uniform(400.0, 5000.0), -1))
            segs.append([start, q])
        r = rng.random()
        if r < 0.15:
            x = 0.0
        elif r < 0.30:
            x = length
        else:
            x = round(rng.uniform(0.0, length), 2)
        t = float(round(rng.uniform(8.0, min(segs[-1][0] + 600.0, 1500.0))))
        switches = [s for s, _ in segs]
        if min(abs(t - s) for s in switches) < 2.0:
            continue
        sc = {"id": "H%02d" % (len(out) + 1), "L_mm": length, "h_W_per_m2K": h,
              "T_init_C": round(rng.uniform(18.0, 30.0), 1), "flux_segments": segs,
              "x_mm": x, "t_s": t}
        rise = scenario_theta(K_SPECIMEN, RHO_C_SPECIMEN, sc)
        if rise < 1.0 or rise > 100.0:
            continue
        out.append(sc)
    return out


def shipped_files():
    return {
        "apparatus.json": apparatus_json(),
        "queries.json": queries_json(),
        "run_A.csv": run_csv("A"),
        "run_B.csv": run_csv("B"),
        "sensors.csv": sensors_csv(),
    }


def build():
    """Everything the verifier needs, regenerated from the constants above."""
    files = shipped_files()
    visible = []
    for sc in VISIBLE:
        visible.append((sc["id"], sc["T_init_C"] + scenario_theta(K_SPECIMEN, RHO_C_SPECIMEN, sc)))
    heldout = []
    for sc in heldout_scenarios():
        heldout.append((sc, sc["T_init_C"] + scenario_theta(K_SPECIMEN, RHO_C_SPECIMEN, sc)))
    return files, visible, heldout
