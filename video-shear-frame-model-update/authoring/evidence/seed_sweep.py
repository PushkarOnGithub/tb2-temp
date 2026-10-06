"""Tolerance calibration over independent noise realisations of the same specimen.

The generator in tests/instance.py is re-run with different SEED strings (the
shipped instance uses the locked seed); for each realisation the correct
estimators and the nearest wrong ones are scored against the 164 held-out
frequencies of the shipped configuration set.  This is the evidence behind the
3 % band: correct estimators must stay well inside it on every realisation and
the nearest wrong ones well outside.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import importlib
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.normpath(os.path.join(HERE, "..", "..", "tests"))
sys.path.insert(0, TESTS)


def run(seed_tag):
    import instance
    importlib.reload(instance)
    instance.SEED = "vsf-sweep-" + seed_tag
    d = tempfile.mkdtemp(prefix="vsf_sweep_")
    for name, data in instance.render_files().items():
        with open(os.path.join(d, name), "wb") as fh:
            fh.write(data)
    os.environ["VSF_DATA"] = d
    import idlib
    importlib.reload(idlib)
    import variants
    importlib.reload(variants)
    out = {}
    for label, fn in (("oracle", lambda: variants.pipeline()),
                      ("shapes-only", lambda: variants.pipeline(kmethod="shapes")),
                      ("fdd", variants.fdd_pipeline),
                      ("shutter-ignored(shapes)", lambda: variants.pipeline(branch="oracle", shutter="ignore", kmethod="shapes")),
                      ("pixel-units(shapes)", lambda: variants.pipeline(units="pixels", kmethod="shapes")),
                      ("design-masses", lambda: variants.pipeline(masses="design")),
                      ("alias-blind", lambda: variants.pipeline(branch="principal", kmethod="freq", k0=[8000] * 4))):
        k, _ = fn()
        out[label] = 100 * variants.worst_error({"k": [float(x) for x in k]})[0]
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    rows = [run(str(i)) for i in range(n)]
    labels = list(rows[0])
    lines = ["max relative error of the 164 graded frequencies (%%) over %d noise realisations" % n,
             "%-26s %8s %8s %8s" % ("estimator", "min", "median", "max")]
    for lab in labels:
        v = np.array([r[lab] for r in rows])
        lines.append("%-26s %8.3f %8.3f %8.3f" % (lab, v.min(), np.median(v), v.max()))
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(HERE, "seed_sweep.log"), "w") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
