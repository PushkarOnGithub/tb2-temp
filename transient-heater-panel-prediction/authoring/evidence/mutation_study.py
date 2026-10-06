"""Two-sided mutation study of the stated physical assumptions (authoring only).

Each mutation breaks one stated assumption *inside the solver* (the data are the
shipped logs, generated under the stated assumptions), refits k and rho_c with
the full-stack finite-volume model, and reports
  * evidence contradiction: fit RMS vs the 0.0155 K of the stated model, and
  * graded values moved: how many of the 36 graded temperatures leave tolerance.
The trap and logger rules are mutated in variants.py (silent by design: the
logs cannot contradict them; the apparatus statements pin them).

Run from the task root:  python3 authoring/evidence/mutation_study.py
"""

import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import answer_format  # noqa: E402
import check_submission  # noqa: E402
import independent_solver as fv  # noqa: E402

MUTATIONS = [
    ("stated assumptions", {}),
    ("heater areal heat capacity 400 J/(m^2 K) (stated: negligible)", {"heater_cap": 400.0}),
    ("specimen-side contact resistance 4e-4 m^2 K/W (stated: negligible)", {"r_contact": 4.0e-4}),
    ("outer faces isothermal (stated: insulated)", {"outer": "isothermal"}),
]


def main():
    truth = json.loads(subprocess.run([sys.executable, "-I", "-S", os.path.join(ROOT, "tests", "derive_truth.py")],
                                      capture_output=True, check=True, timeout=120).stdout)
    print("%-66s %9s %9s %10s %8s" % ("mutation", "fit_rms", "k", "rho_c", "graded!"))
    for name, opts in MUTATIONS:
        k, rc, rms, preds = fv.fit_stack(opts)
        ans = answer_format.validate({"k": k, "rho_c": rc, "predictions": preds}, truth["visible_ids"])
        fails = check_submission.grade(truth, ans)
        n_vis = sum(1 for f in fails if f.startswith("predictions."))
        n_hid = sum(int(f.split()[0]) for f in fails if "hidden" in f)
        print("%-66s %9.4f %9.5f %10.4e %5d/36" % (name, rms, k, rc, n_vis + n_hid))


if __name__ == "__main__":
    main()
