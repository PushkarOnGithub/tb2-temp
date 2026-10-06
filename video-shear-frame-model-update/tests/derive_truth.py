"""Regenerate the instance, lock it, and emit the graded answers as JSON.

Run as ``python3 -I -S /tests/derive_truth.py``.  Exit status 0 means the JSON
on stdout is trustworthy; any other status is a verifier infrastructure error.

Paths opened: none.  Everything is regenerated from the modules in /tests,
which is the verify-time overlay and cannot be written by the agent.
"""

import hashlib
import json
import math
import os
import sys

# -I implies -P, so this file's directory is not on sys.path; /tests is the
# read-only verifier overlay, so adding it cannot import agent-written code.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frame_model  # noqa: E402
import heldout  # noqa: E402
import instance  # noqa: E402

LOCKED_DIGEST = "901c6cdd3a577c4635e4f80a79ee8f9bc62c82c07995fa758cf54e985a081978"
MIN_RELATIVE_GAP = 0.07
EIG_AGREEMENT = 1e-9


def true_frequencies(added, factor):
    """True natural frequencies of one configuration, by two independent eigen-solvers."""
    m = instance.as_tested_mass()
    f = frame_model.configuration_frequencies(instance.K_TRUE, m, added, factor)
    kk = [instance.K_TRUE[j] * factor[j] for j in range(4)]
    mm = [m[j] + added[j] for j in range(4)]
    f2 = [math.sqrt(x) / (2.0 * math.pi) for x in frame_model.sturm_eigenvalues(kk, mm)]
    for a, b in zip(f, f2):
        if abs(a - b) > EIG_AGREEMENT * abs(a):
            raise AssertionError("eigen-solvers disagree: %r vs %r" % (a, b))
    return f


def admissible(added, factor):
    f = true_frequencies(added, factor)
    return all(f[i + 1] / f[i] - 1.0 >= MIN_RELATIVE_GAP for i in range(3))


def build():
    configs = [([0.0] * 4, [1.0] * 4)] + heldout.heldout_configurations(admissible)
    if len(configs) != heldout.N_HELDOUT + 1:
        raise AssertionError("held-out set has the wrong size")
    if any(c == configs[0] for c in configs[1:]):
        raise AssertionError("a held-out configuration duplicates the tested frame")
    if len(set(json.dumps(c) for c in configs)) != len(configs):
        raise AssertionError("duplicate configurations")
    rows = []
    for i, (added, factor) in enumerate(configs):
        if not admissible(added, factor):
            raise AssertionError("configuration %d has near-degenerate modes" % i)
        rows.append({"id": "C%02d" % i, "added_mass_kg": added, "stiffness_factor": factor,
                     "f_hz": true_frequencies(added, factor)})
    return rows


def compute_digest(files, rows):
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(("== %s\n" % name).encode("ascii"))
        h.update(files[name])
    h.update(b"\n--- graded answers ---\n")
    for r in rows:
        line = "%s %s %s %s\n" % (r["id"], json.dumps(r["added_mass_kg"]),
                                  json.dumps(r["stiffness_factor"]),
                                  " ".join(repr(x) for x in r["f_hz"]))
        h.update(line.encode("ascii"))
    return h.hexdigest()


def main():
    files = instance.render_files()
    rows = build()
    digest = compute_digest(files, rows)
    if digest != LOCKED_DIGEST:
        sys.stderr.write("instance/answer digest mismatch: %s\n" % digest)
        return 2
    json.dump({"as_tested_mass_kg": instance.as_tested_mass(), "configs": rows,
               "digest": digest}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # any failure here is infrastructure, never a model verdict
        sys.stderr.write("derive_truth failed: %r\n" % (exc,))
        sys.exit(2)
