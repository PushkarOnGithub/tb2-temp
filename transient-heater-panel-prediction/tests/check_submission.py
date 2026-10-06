"""Authoritative grader.  Run as:  python3 -I -S /tests/check_submission.py

Exit status contract (mapped explicitly in test.sh):
  0  every grading condition holds; the last line printed is VERDICT below
  1  the submission violates a stated requirement (contract or accuracy)
  2  the verifier itself failed (truth derivation, lock mismatch, unexpected error)

Files opened: /app/answer.json (the only agent artifact, read through
answer_format with lstat + O_NOFOLLOW, so a symlink there cannot make this
process read anything else) and its own /tests modules.  Truth comes from
derive_truth.py, run in a separate isolated interpreter that regenerates the
instance and checks it against tests/lock.json.  The grade is decided by
comparing temperatures only; the submitted k and rho_c are used solely as the
model under which the held-out scenarios are evaluated.
"""

import json
import os
import subprocess
import sys

# -I implies -P: put this script's own directory (the read-only /tests overlay,
# never an agent-writable path) on sys.path to reach the sibling modules.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import answer_format  # noqa: E402
import thermal_model  # noqa: E402

ANSWER = "/app/answer.json"
VERDICT = "VERDICT: PASS transient-heater-panel-prediction all-36-temperatures-within-tolerance"


class InfraError(Exception):
    pass


def derive_truth():
    try:
        proc = subprocess.run([sys.executable, "-I", "-S", os.path.join(HERE, "derive_truth.py")],
                              capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise InfraError("derive_truth.py timed out")
    if proc.returncode != 0:
        raise InfraError("derive_truth.py exited %d: %s" % (proc.returncode, proc.stderr.decode(errors="replace")[-500:]))
    truth = json.loads(proc.stdout.decode("ascii"))
    if len(truth["heldout"]) < 1 or len(truth["visible_ids"]) < 1:
        raise InfraError("empty truth")
    return truth


def within(pred, true, t_init, rel_tol, abs_tol):
    return abs(pred - true) <= rel_tol * abs(true - t_init) + abs_tol


def scenario_temperature(k, rho_c, sc):
    segs = [(float(s), float(q)) for s, q in sc["flux_segments"]]
    return float(sc["T_init_C"]) + thermal_model.panel_theta(
        k, rho_c, float(sc["h_W_per_m2K"]), float(sc["L_mm"]) * 1e-3, segs,
        float(sc["x_mm"]) * 1e-3, float(sc["t_s"]))


def grade(truth, answer):
    """Return a list of failure strings (empty when every check passes)."""
    rel, abs_ = truth["rel_tol"], truth["abs_tol"]
    failures = []
    for sc in truth["visible_scenarios"]:
        sid = sc["id"]
        pred, true = answer["predictions"][sid], truth["visible"][sid]
        if not within(pred, true, sc["T_init_C"], rel, abs_):
            failures.append("predictions.%s = %.4f C is outside the tolerance band" % (sid, pred))
    n_bad = 0
    for item in truth["heldout"]:
        sc, true = item["scenario"], item["T_true"]
        pred = scenario_temperature(answer["k"], answer["rho_c"], sc)
        if not within(pred, true, sc["T_init_C"], rel, abs_):
            n_bad += 1
    if n_bad:
        failures.append("%d of %d hidden scenarios evaluated with the reported k and rho_c are outside the tolerance band"
                        % (n_bad, len(truth["heldout"])))
    return failures


def main():
    truth = derive_truth()
    try:
        answer = answer_format.read_answer(ANSWER, truth["visible_ids"])
    except answer_format.ContractError as exc:
        print("FAIL contract: %s" % exc)
        return 1
    failures = grade(truth, answer)
    if failures:
        for f in failures:
            print("FAIL accuracy: %s" % f)
        return 1
    print("visible %d/%d and hidden %d/%d temperatures within tolerance"
          % (len(truth["visible_ids"]), len(truth["visible_ids"]), len(truth["heldout"]), len(truth["heldout"])))
    print(VERDICT)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except InfraError as exc:
        print("VERIFIER INFRASTRUCTURE ERROR: %s" % exc)
        code = 2
    except Exception as exc:  # an unexpected grader crash is never a model failure
        print("VERIFIER INFRASTRUCTURE ERROR: unexpected %r" % (exc,))
        code = 2
    sys.exit(code)
