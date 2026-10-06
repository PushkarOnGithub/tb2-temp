"""Instance generator for the shear-frame video test, standard library only.

The files shipped in the agent image are exactly ``render_files()``; the
verifier regenerates them and checks a locked SHA-256 digest before any
graded value is emitted, so a modified generator has to reproduce the shipped
bytes (that is, be this generator).

Physics: a shaker on floor 1 applies a zero-order-hold Gaussian force
(2 ms steps).  The response is integrated exactly in complex modal
coordinates (classical Rayleigh damping) and sampled at each target's
rolling-shutter capture time.  Tracker noise is added in pixels.
"""

import cmath
import hashlib
import json
import math
import os
import struct
import sys

# -I implies -P; /tests is the read-only verify-time overlay, so adding this
# file's directory to sys.path cannot import agent-written code.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frame_model import modes, rayleigh_zeta  # noqa: E402

# ---- true specimen (verifier-private) ---------------------------------------
DESIGN_MASS_KG = [5.10, 5.25, 4.85, 7.50]           # floors 1..4
MOUNTED = [{"item": "wireless data logger", "floor": 3, "mass_kg": 1.10}]
K_TRUE = [4930.0, 18880.0, 5080.0, 5100.0]           # storeys 1..4, N/m
A0_TRUE = 0.147                                      # 1/s
A1_TRUE = 9.3e-5                                     # s

# ---- test and camera ----------------------------------------------------------
FRAME_RATE = 25.0
N_FRAMES = 15000                                     # 600 s
ROW_PERIOD_S = 1.86e-5
FLOOR_ROW = [884, 642, 401, 158]                     # image row of each floor's target
FLOOR_MM_PER_PX = [0.4415, 0.4296, 0.4188, 0.4092]
FLOOR_REST_PX = [1012.37, 986.52, 1003.91, 995.08]
TARGET_FLOOR = {"T1": 2, "T2": 4, "T3": 1, "T4": 3}  # tracker labels -> floor
SHAKER_FLOOR = 1
FORCE_STEP_S = 0.002
FORCE_STD_N = 2.0
BURN_IN_S = 90.0
NOISE_PX = 0.012
SEED = "vsf-instance-2026-10-ambient"


def as_tested_mass():
    m = list(DESIGN_MASS_KG)
    for item in MOUNTED:
        m[item["floor"] - 1] += item["mass_kg"]
    return m


class GaussStream:
    """Counter-based standard normals: SHA-256 blocks -> Box-Muller, reproducible everywhere."""

    def __init__(self, name):
        self.name = name
        self.block = 0
        self.buf = []

    def next(self):
        if not self.buf:
            h = hashlib.sha256(("%s|%s|%d" % (SEED, self.name, self.block)).encode("ascii")).digest()
            self.block += 1
            u = [(x + 0.5) / 18446744073709551616.0 for x in struct.unpack(">4Q", h)]
            for a, b in ((u[0], u[1]), (u[2], u[3])):
                r = math.sqrt(-2.0 * math.log(a))
                self.buf.append(r * math.cos(2.0 * math.pi * b))
                self.buf.append(r * math.sin(2.0 * math.pi * b))
            self.buf.reverse()
        return self.buf.pop()


def simulate_displacements():
    """Floor displacements (m) at every target capture time: list[floor][frame]."""
    m = as_tested_mass()
    omega, phi = modes(K_TRUE, m)
    n = len(m)
    s = []
    for w in omega:
        z = rayleigh_zeta(A0_TRUE, A1_TRUE, w)
        s.append(complex(-z * w, w * math.sqrt(1.0 - z * z)))
    c = [phi[SHAKER_FLOOR - 1][r] / (s[r] - s[r].conjugate()) for r in range(n)]
    h = FORCE_STEP_S
    e_full = [cmath.exp(x * h) for x in s]
    g_full = [(e_full[r] - 1.0) / s[r] * c[r] for r in range(n)]

    dt = 1.0 / FRAME_RATE
    order = sorted(range(n), key=lambda j: FLOOR_ROW[j])
    force = GaussStream("shaker")
    q = [0j] * n
    step = 0
    u = FORCE_STD_N * force.next()
    out = [[0.0] * N_FRAMES for _ in range(n)]
    for fr in range(N_FRAMES):
        for j in order:
            t = BURN_IN_S + fr * dt + FLOOR_ROW[j] * ROW_PERIOD_S
            while (step + 1) * h <= t:
                q = [e_full[r] * q[r] + g_full[r] * u for r in range(n)]
                step += 1
                u = FORCE_STD_N * force.next()
            rho = t - step * h
            x = 0.0
            for r in range(n):
                e = cmath.exp(s[r] * rho)
                qq = e * q[r] + (e - 1.0) / s[r] * c[r] * u
                x += phi[j][r] * 2.0 * qq.real
            out[j][fr] = x
    return out


def render_files():
    """Return {file name: bytes} for every file in /app/data."""
    disp = simulate_displacements()
    labels = sorted(TARGET_FLOOR)
    noise = {lab: GaussStream("tracker-" + lab) for lab in labels}
    lines = ["t_s," + ",".join(labels)]
    for fr in range(N_FRAMES):
        row = ["%.2f" % (fr / FRAME_RATE)]
        for lab in labels:
            j = TARGET_FLOOR[lab] - 1
            px = FLOOR_REST_PX[j] + 1000.0 * disp[j][fr] / FLOOR_MM_PER_PX[j]
            px += NOISE_PX * noise[lab].next()
            row.append("%.3f" % px)
        lines.append(",".join(row))
    tracks = ("\n".join(lines) + "\n").encode("ascii")

    targets = {}
    for lab in labels:
        j = TARGET_FLOOR[lab] - 1
        targets[lab] = {"floor": j + 1, "image_row": FLOOR_ROW[j], "mm_per_px": FLOOR_MM_PER_PX[j]}
    targets_b = (json.dumps(targets, indent=2) + "\n").encode("ascii")

    record = {
        "design_floor_mass_kg": {str(j + 1): DESIGN_MASS_KG[j] for j in range(4)},
        "mounted_during_test": MOUNTED,
        "excitation": {"floor": SHAKER_FLOOR, "signal": "broadband random force, not recorded"},
        "camera": {"row_period_s": ROW_PERIOD_S},
    }
    record_b = (json.dumps(record, indent=2) + "\n").encode("ascii")
    return {"tracks.csv": tracks, "targets.json": targets_b, "test_record.json": record_b}


if __name__ == "__main__":
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    for name, data in render_files().items():
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
