"""Wrong-method harness and positive variants, graded by the real grader.

Each variant is a complete pipeline that ends in a well-formed model.json.
The artifact is written to /app/output/model.json and graded by running
``python3 -I -S tests/check_submission.py`` exactly as test.sh does.
Results go to calibration_run.log and run_records.json next to this file.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import json
import os
import subprocess
import sys

import numpy as np

import idlib

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, "..", ".."))
ARTIFACT = "/app/output/model.json"
TOL = 0.03


def pipeline(branch="realness", shutter="modal", masses="tested", units="per_target",
             mapping="file", kmethod="shapes+freq", k0=None, preprocess="ssi"):
    t, disp, delay, design, tested = idlib.load(mapping=mapping, units=units)
    mass = tested if masses == "tested" else design
    sel = idlib.identify(t, disp, delay, branch=branch, shutter=shutter, preprocess=preprocess)
    omega, zeta, phi = idlib.modal_arrays(sel, mass)
    if kmethod == "shapes":
        k = idlib.k_from_shapes(omega, phi, mass)
    elif kmethod == "shapes+freq":
        k, _ = idlib.k_from_frequencies(omega, mass, idlib.k_from_shapes(omega, phi, mass))
    elif kmethod == "freq":
        k, _ = idlib.k_from_frequencies(omega, mass, np.array(k0, float))
    else:
        raise ValueError(kmethod)
    return k, omega / (2 * np.pi)


def fdd_pipeline():
    t, disp, delay, design, tested = idlib.load()
    sel = []
    for fa, u in idlib.fdd_modes(t, disp):
        ratio, ft, phi = idlib.fdd_resolve(fa, u, delay, 1.0 / float(np.median(np.diff(t))))
        sel.append((2j * np.pi * ft, phi))
    sel.sort(key=lambda x: abs(x[0]))
    omega, _, phi = idlib.modal_arrays(sel, tested)
    k, _ = idlib.k_from_frequencies(omega, tested, idlib.k_from_shapes(omega, phi, tested))
    return k, omega / (2 * np.pi)


def fft_default():
    t, disp, delay, design, tested = idlib.load()
    omega, _ = idlib.fft_peaks(t, disp)
    k, _ = idlib.k_from_frequencies(omega, tested, np.full(4, 8000.0))
    return k, omega / (2 * np.pi)


VARIANTS = [
    ("P1-oracle", 1, "positive", "solution/solve.py: SSI-cov, shutter-corrected realness picks the branch, as-tested M, shapes then frequency refinement", None),
    ("P2-fdd", 1, "positive", "different identification: frequency-domain decomposition of the Welch CSD matrix; branch by shutter-corrected realness of the singular vector",
     fdd_pipeline),
    ("P3-shapes-only", 1, "positive", "same modes, k projected from M Phi W^2 Phi^T M without frequency refinement",
     lambda: pipeline(kmethod="shapes")),
    ("N1-alias-blind-freq-update", 0, "crux", "default: principal-branch poles, k updated to the four identified frequencies (matches them exactly)",
     lambda: pipeline(branch="principal", kmethod="freq", k0=[8000] * 4)),
    ("N2-alias-blind-shapes", 0, "crux", "principal-branch poles, shutter corrected with those poles, k from mode shapes",
     lambda: pipeline(branch="principal", kmethod="shapes")),
    ("N3-alias-blind-shapes+freq", 0, "crux", "principal-branch poles, k from shapes then frequency refinement",
     lambda: pipeline(branch="principal", kmethod="shapes+freq")),
    ("N4-wrong-fold", 0, "crux", "aliasing suspected but the highest mode assumed folded without reflection (fs + f_apparent)",
     lambda: pipeline(branch="fold", kmethod="shapes+freq")),
    ("N5-welch-peaks", 0, "crux", "Welch peak picking, frequency updating",
     fft_default),
    ("N13-fold-rule-positive-frequencies", 0, "crux", "fold rule applied, but each identified shape is referred to a common instant with a positive candidate frequency (no conjugate image): the most nearly real candidate for mode 4 is 85.47 Hz",
     lambda: pipeline(branch="naive-positive", kmethod="shapes+freq")),
    ("N6-design-masses", 0, "trap", "true branch, design floor masses (logger on floor 3 omitted)",
     lambda: pipeline(masses="design")),
    ("N7-shutter-ignored", 1, "time-cost", "true branch, rolling-shutter delays ignored in the shapes, k from mode shapes (category b: precision cost, still inside tolerance on this instance)",
     lambda: pipeline(branch="oracle", shutter="ignore", kmethod="shapes")),
    ("N8-shutter-spline", 0, "trap", "rolling shutter handled by spline-resampling each channel to the frame times, true branch",
     lambda: pipeline(branch="oracle", shutter="spline", kmethod="shapes")),
    ("N9-pixel-units", 0, "trap", "true branch, positions left in pixels or one common mm/px (per-target scales ignored), k from mode shapes",
     lambda: pipeline(units="pixels", kmethod="shapes")),
    ("N10-label-order", 0, "trap", "tracker labels T1..T4 taken as floors 1..4",
     lambda: pipeline(mapping="labels", kmethod="shapes+freq")),
    ("N11-freq-only-uniform-start", 0, "identifiability", "true branch, k least-squares-fitted to the four frequencies from a uniform 15 kN/m start: local minimum missing the frequencies by about 1-2 %",
     lambda: pipeline(kmethod="freq", k0=[15000] * 4)),
    ("N12-isospectral-twin", 0, "identifiability", "true branch, frequency-only updating that lands on the exact isospectral twin (all four tested-frame frequencies matched, shapes ignored)",
     lambda: pipeline(kmethod="freq", k0=[30000, 6000, 5000, 3000])),
]


def grade(model):
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    with open(ARTIFACT, "w") as fh:
        json.dump(model, fh)
    proc = subprocess.run([sys.executable, "-I", "-S", os.path.join(PKG, "tests", "check_submission.py")],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=200)
    out = proc.stdout.decode()
    reward = 1 if proc.returncode == 0 and "VSF-GRADER: PASS" in out else 0
    return proc.returncode, reward, out.strip().splitlines()[0] if out.strip() else proc.stderr.decode()


_TRUTH = None


def worst_error(model):
    global _TRUTH
    sys.path.insert(0, os.path.join(PKG, "tests"))
    import frame_model
    if _TRUTH is None:
        _TRUTH = json.loads(subprocess.run([sys.executable, "-I", "-S", os.path.join(PKG, "tests", "derive_truth.py")],
                                           stdout=subprocess.PIPE, check=True).stdout)
    if min(model["k"]) <= 0:
        return float("nan"), 164
    ef, nbad = 0.0, 0
    for row in _TRUTH["configs"]:
        f = frame_model.configuration_frequencies(model["k"], _TRUTH["as_tested_mass_kg"], row["added_mass_kg"],
                                                  row["stiffness_factor"])
        for i in range(4):
            e = abs(f[i] / row["f_hz"][i] - 1)
            ef = max(ef, e)
            nbad += e > TOL
    return ef, nbad


def main():
    records, log = [], []
    for name, expected, kind, desc, fn in VARIANTS:
        if fn is None:
            subprocess.run(["python3", os.path.join(PKG, "solution", "solve.py")], check=True, stdout=subprocess.DEVNULL)
            with open(ARTIFACT) as fh:
                model = json.load(fh)
            fid = None
        else:
            k, fhz = fn()
            model = {"k": [float(x) for x in k]}
            fid = [round(float(x), 4) for x in fhz]
        code, reward, line = grade(model)
        ef, nbad = worst_error(model)
        ok = reward == expected
        records.append({"variant": name, "kind": kind, "description": desc, "artifact": model,
                        "identified_f_hz": fid, "grader_exit": code, "reward": reward, "expected_reward": expected,
                        "max_rel_freq_error": ef, "graded_values_out_of_tolerance": nbad,
                        "grader_line": line, "as_expected": ok})
        log.append("%-30s %-15s reward=%d expected=%d %s  max|df/f|=%7.3f%%  out-of-tol=%3d/164  k=%s  f_id=%s"
                   % (name, kind, reward, expected, "OK " if ok else "BAD", 100 * ef, nbad,
                      [round(x) for x in model["k"]], fid))
        print(log[-1], flush=True)
    with open(os.path.join(HERE, "run_records.json"), "w") as fh:
        json.dump(records, fh, indent=1)
    with open(os.path.join(HERE, "calibration_run.log"), "w") as fh:
        fh.write("Wrong-method harness and positive variants (graded by tests/check_submission.py)\n")
        fh.write("tolerance: 3% relative on each of 41 configurations x 4 natural frequencies = 164 graded values\n\n")
        fh.write("\n".join(log) + "\n")
    if not all(r["as_expected"] for r in records):
        sys.exit("some variants did not score as expected")


if __name__ == "__main__":
    main()
