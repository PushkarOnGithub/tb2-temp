"""Itemised pytest report for /app/answer.json.

The reward is decided by check_submission.py (run first by test.sh); these tests
use the same reader (answer_format) and the same truth (derive_truth.py, run in
an isolated interpreter), so every check here mirrors one grading condition and
one sentence of the instruction.  Contract tests are collected first; accuracy
tests skip when the contract already failed (the reward is then 0 regardless).
"""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import answer_format  # noqa: E402
import check_submission  # noqa: E402

ANSWER = "/app/answer.json"


@pytest.fixture(scope="session")
def truth():
    """Graded truth, regenerated and lock-checked by derive_truth.py in a separate -I -S interpreter."""
    proc = subprocess.run([sys.executable, "-I", "-S", os.path.join(HERE, "derive_truth.py")],
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, "derive_truth.py failed: %s" % proc.stderr.decode(errors="replace")[-500:]
    return json.loads(proc.stdout.decode("ascii"))


@pytest.fixture(scope="session")
def answer(truth):
    """The validated submission, or a pytest.skip when the output contract is not met."""
    try:
        return answer_format.read_answer(ANSWER, truth["visible_ids"])
    except answer_format.ContractError as exc:
        pytest.skip("output contract not met: %s" % exc)


def test_answer_is_regular_bounded_file():
    """/app/answer.json exists and is a regular file (no symlink/FIFO/device) of at most 64 KiB."""
    answer_format.read_bytes(ANSWER)


def test_answer_is_strict_json_object():
    """The file is UTF-8 JSON (no NaN/Infinity, no duplicate keys) holding one object."""
    doc = answer_format.parse(answer_format.read_bytes(ANSWER))
    assert isinstance(doc, dict), "answer.json must contain a JSON object"


def test_top_level_keys_are_exact():
    """The object has exactly the keys k, rho_c and predictions."""
    doc = answer_format.parse(answer_format.read_bytes(ANSWER))
    assert isinstance(doc, dict) and set(doc) == set(answer_format.TOP_KEYS), \
        "top-level keys must be exactly %s" % (list(answer_format.TOP_KEYS),)


def test_k_and_rho_c_are_numbers_in_stated_ranges():
    """k is a JSON number in [0.01, 100] W/(m K) and rho_c a JSON number in [1e5, 1e8] J/(m^3 K)."""
    doc = answer_format.parse(answer_format.read_bytes(ANSWER))
    assert isinstance(doc, dict) and "k" in doc and "rho_c" in doc, "k and rho_c are required"
    k = answer_format.number(doc["k"], "k")
    rho_c = answer_format.number(doc["rho_c"], "rho_c")
    assert answer_format.K_RANGE[0] <= k <= answer_format.K_RANGE[1], "k outside the stated range"
    assert answer_format.RHO_C_RANGE[0] <= rho_c <= answer_format.RHO_C_RANGE[1], "rho_c outside the stated range"


def test_predictions_cover_exactly_the_scenario_ids(truth):
    """predictions has exactly the ids of /app/data/queries.json, each a finite JSON number."""
    answer_format.read_answer(ANSWER, truth["visible_ids"])


def test_visible_predictions_within_tolerance(truth, answer):
    """Each predicted temperature for the shipped scenarios is within 0.5 % of the true rise plus 0.01 K."""
    bad = []
    for sc in truth["visible_scenarios"]:
        sid = sc["id"]
        if not check_submission.within(answer["predictions"][sid], truth["visible"][sid], sc["T_init_C"],
                                       truth["rel_tol"], truth["abs_tol"]):
            bad.append(sid)
    assert not bad, "predictions outside tolerance: %s" % bad


def test_hidden_scenarios_within_tolerance_under_reported_model(truth, answer):
    """The 30 hidden scenarios, evaluated exactly with the reported k and rho_c, are all within tolerance."""
    bad = 0
    for item in truth["heldout"]:
        sc = item["scenario"]
        pred = check_submission.scenario_temperature(answer["k"], answer["rho_c"], sc)
        if not check_submission.within(pred, item["T_true"], sc["T_init_C"], truth["rel_tol"], truth["abs_tol"]):
            bad += 1
    assert bad == 0, "%d of %d hidden scenarios outside tolerance" % (bad, len(truth["heldout"]))
