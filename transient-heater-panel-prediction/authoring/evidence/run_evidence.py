"""Drive every calibration run through the real images (authoring only).

Assumes two locally built images (see run_evidence.sh):
  AGENT_IMAGE    built from environment/
  VERIFIER_IMAGE built from tests/
Writes, next to this file:
  offline_oracle_run.log   oracle with the network removed + verifier result
  calibration_run.log      positives, wrong-method variants, exploit probes,
                           legitimate-format battery, lying ground-truth probe
  run_records.json         one record per run: artifact, measured result, reward
"""

import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
AGENT = os.environ.get("AGENT_IMAGE", "thpp-env")
VERIFIER = os.environ.get("VERIFIER_IMAGE", "thpp-verifier")
VERDICT = "VERDICT: PASS transient-heater-panel-prediction all-36-temperatures-within-tolerance"

records = []
cal_lines = []


def sh(cmd, timeout=900):
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr, time.time() - t0


def verify(artifact_bytes=None, setup="", post=""):
    """Run tests/test.sh in a fresh no-network verifier container."""
    with tempfile.TemporaryDirectory() as art, tempfile.TemporaryDirectory() as logs:
        if artifact_bytes is not None:
            with open(os.path.join(art, "answer.json"), "wb") as fh:
                fh.write(artifact_bytes)
        script = ("set -u; "
                  + ("cp /art/answer.json /app/answer.json; " if artifact_bytes is not None else "")
                  + setup + " bash /tests/test.sh; rc=$?; " + post + " exit $rc")
        rc, out, wall = sh(["docker", "run", "--rm", "--network", "none", "-v", art + ":/art:ro",
                            "-v", logs + ":/logs/verifier", VERIFIER, "bash", "-c", script])
        reward_path = os.path.join(logs, "reward.txt")
        reward = open(reward_path).read().strip() if os.path.exists(reward_path) else "NO REWARD FILE"
    summary = [l for l in out.splitlines() if l.startswith(("FAIL", "VERDICT", "visible ", "VERIFIER", "SIDE-EFFECT", "=", "reward"))]
    return rc, reward, out, summary, wall


def record(kind, name, artifact, expect, reward, rc, summary, wall, note=""):
    ok = (reward == expect)
    records.append({"kind": kind, "name": name,
                    "artifact_sha256": hashlib.sha256(artifact).hexdigest() if artifact else None,
                    "artifact_preview": (artifact[:160].decode("utf-8", "replace") if artifact else None),
                    "test_sh_exit": rc, "reward": reward, "expected": expect, "as_expected": ok,
                    "verifier_lines": summary[-6:], "wall_s": round(wall, 2), "note": note})
    cal_lines.append("%-6s %-44s reward=%-14s expected=%-14s %s  %s" % (
        kind, name, reward, expect, "OK " if ok else "BAD", note))
    return ok


def offline_oracle():
    lines = []
    with tempfile.TemporaryDirectory() as out:
        probe = ("python3 - <<'PY'\n"
                 "import socket\n"
                 "try:\n"
                 "    socket.getaddrinfo('pypi.org', 443)\n"
                 "    print('NETWORK: reachable')\n"
                 "except OSError as e:\n"
                 "    print('NETWORK: unreachable -> %s' % type(e).__name__)\n"
                 "print('interfaces present: ' + ' '.join(l.split(':')[0].strip() + ':' for l in open('/proc/net/dev').read().splitlines()[2:]))\n"
                 "PY\n")
        cmd = ["docker", "run", "--rm", "--network", "none", "-v", os.path.join(ROOT, "solution") + ":/solution:ro",
               "-v", out + ":/out", AGENT, "bash", "-c",
               probe + "start=$(date +%s.%N); /solution/solve.sh; rc=$?; end=$(date +%s.%N); "
               "echo \"ORACLE exit=$rc wall_s=$(python3 -c \"print(round($end-$start,2))\")\"; "
               "ls -l /app/answer.json; cp /app/answer.json /out/answer.json; exit $rc"]
        rc, text, wall = sh(cmd)
        lines.append("$ docker run --network none <agent image> /solution/solve.sh   (network removed)")
        lines.extend(text.rstrip().splitlines())
        artifact = open(os.path.join(out, "answer.json"), "rb").read()
    lines.append("artifact /app/answer.json sha256=%s" % hashlib.sha256(artifact).hexdigest())
    lines.append(artifact.decode().rstrip())
    vrc, reward, vout, summary, vwall = verify(artifact)
    lines.append("$ docker run --network none <verifier image> bash /tests/test.sh")
    lines.extend(vout.rstrip().splitlines())
    lines.append("verifier exit=%d reward=%s wall_s=%.2f" % (vrc, reward, vwall))
    with open(os.path.join(HERE, "offline_oracle_run.log"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    record("P1", "oracle_offline", artifact, "1", reward, vrc, summary, vwall, "reference solution, network removed")
    return artifact


def main():
    oracle = offline_oracle()
    doc = json.loads(oracle)

    # no-op: nothing written
    rc, reward, out, summary, wall = verify(None)
    record("NOOP", "no_answer_file", b"", "0", reward, rc, summary, wall, "agent did nothing")

    # positives and wrong-method variants from variants.py (and the independent solver)
    with tempfile.TemporaryDirectory() as vd:
        subprocess.run([sys.executable, os.path.join(HERE, "variants.py"), vd], check=True, capture_output=True, timeout=900)
        p2 = os.path.join(vd, "P2_independent_fd")
        os.makedirs(p2)
        subprocess.run([sys.executable, os.path.join(HERE, "independent_solver.py"), os.path.join(p2, "answer.json")],
                       check=True, capture_output=True, timeout=900)
        for name in sorted(os.listdir(vd)):
            art = open(os.path.join(vd, name, "answer.json"), "rb").read()
            expect = "1" if name.startswith(("P", "B1")) else "0"
            rc, reward, out, summary, wall = verify(art)
            kind = "POS" if expect == "1" else "NEG"
            record(kind, name, art, expect, reward, rc, summary, wall)

    # legitimate-format battery: valid serialisations of the oracle answer
    k, rc_, preds = doc["k"], doc["rho_c"], doc["predictions"]
    rev = {kk: preds[kk] for kk in reversed(list(preds))}
    battery = {
        "compact": json.dumps(doc, separators=(",", ":")),
        "indent4_sorted": json.dumps(doc, indent=4, sort_keys=True),
        "predictions_first": json.dumps({"predictions": preds, "rho_c": rc_, "k": k}),
        "prediction_keys_reversed": json.dumps({"k": k, "rho_c": rc_, "predictions": rev}),
        "exponent_notation": '{"k": %.9e, "rho_c": %.9E, "predictions": {%s}}' % (
            k, rc_, ", ".join('"%s": %.9e' % (kk, v) for kk, v in preds.items())),
        "rho_c_integer": json.dumps({"k": k, "rho_c": int(round(rc_)), "predictions": preds}),
        "rounded_4_decimals": json.dumps({"k": round(k, 6), "rho_c": round(rc_), "predictions": {kk: round(v, 4) for kk, v in preds.items()}}),
        "crlf": json.dumps(doc, indent=2).replace("\n", "\r\n") + "\r\n",
        "no_trailing_newline": json.dumps(doc),
        "utf8_bom": "\ufeff" + json.dumps(doc),
        "unicode_escaped_keys": json.dumps(doc).replace('"k"', '"\\u006b"').replace('"rho_c"', '"rho\\u005fc"'),
        "whitespace_padding": "\n\n   " + json.dumps(doc, indent=1) + "   \n\t\n",
    }
    for name, text in battery.items():
        art = text.encode("utf-8")
        rc, reward, out, summary, wall = verify(art)
        record("FMT", name, art, "1", reward, rc, summary, wall, "valid serialisation of the oracle answer")

    # exploit probes: every one must score 0 with no side effect
    side = ("if [ -e /tmp/pwned ] || [ -e /logs/verifier/pwned ]; then echo SIDE-EFFECT: pwned=True; "
            "else echo SIDE-EFFECT: pwned=False; fi;")
    inj = "__import__('os').system('touch /tmp/pwned /logs/verifier/pwned')"
    probes = [
        ("symlink_to_lock", None, "ln -sf /tests/lock.json /app/answer.json;", "answer path is a symlink to verifier data"),
        ("symlink_to_passwd", None, "ln -sf /etc/passwd /app/answer.json;", "symlink to a system file"),
        ("fifo_answer", None, "mkfifo /app/answer.json;", "FIFO would block a naive open()"),
        ("directory_answer", None, "mkdir -p /app/answer.json;", "directory at the answer path"),
        ("dev_zero_symlink", None, "ln -sf /dev/zero /app/answer.json;", "endless device"),
        ("oversized", (" " * 70000 + json.dumps(doc)).encode(), "", "valid JSON padded past 64 KiB"),
        ("code_injection_strings", json.dumps({"k": inj, "rho_c": inj, "predictions": {kk: inj for kk in preds}}).encode(),
         "", "strings that would execute if eval'd"),
        ("nan_infinity", ('{"k": NaN, "rho_c": Infinity, "predictions": {%s}}' % ", ".join('"%s": -Infinity' % kk for kk in preds)).encode(),
         "", "non-finite constants"),
        ("overflow_exponent", ('{"k": 1e999, "rho_c": 1e999, "predictions": {%s}}' % ", ".join('"%s": 1e999' % kk for kk in preds)).encode(),
         "", "1e999 parses to inf"),
        ("duplicate_keys", ('{"k": 0.5, "k": %r, "rho_c": %r, "predictions": %s}' % (k, rc_, json.dumps(preds))).encode(),
         "", "duplicate key shadowing"),
        ("booleans", json.dumps({"k": True, "rho_c": True, "predictions": {kk: True for kk in preds}}).encode(), "", "bools are not numbers"),
        ("nesting_bomb", ("[" * 20000 + "]" * 20000).encode(), "", "deep nesting within the size limit"),
        ("extra_key", json.dumps(dict(doc, notes="x")).encode(), "", "fourth top-level key"),
        ("missing_prediction", json.dumps(dict(doc, predictions={kk: v for kk, v in list(preds.items())[:-1]})).encode(), "", "one id missing"),
        ("extra_predictions_flood", json.dumps(dict(doc, predictions=dict(preds, **{"H%02d" % i: 50.0 for i in range(1, 31)}))).encode(),
         "", "submitting answers for guessed hidden ids"),
        ("k_out_of_range", json.dumps(dict(doc, k=1.0e6)).encode(), "", "k outside the stated range"),
        ("agent_visible_objects_only", json.dumps({"k": 1.14, "rho_c": 1.728e6,
                                                   "predictions": {sc["id"]: sc["T_init_C"] for sc in json.load(open(os.path.join(ROOT, "environment", "data", "queries.json")))["scenarios"]}}).encode(),
         "", "answer assembled only from shipped reference objects"),
        ("correct_visible_wrong_model", json.dumps({"k": k * 1.1, "rho_c": rc_ * 1.1, "predictions": preds}).encode(),
         "", "visible predictions copied from a correct run, model perturbed 10%"),
    ]
    for name, art, setup, note in probes:
        rc, reward, out, summary, wall = verify(art, setup=setup, post=side)
        pw = "SIDE-EFFECT: pwned=False" in out
        note2 = note + ("; no side effect" if pw else "; SIDE EFFECT DETECTED")
        okp = record("PROBE", name, art or setup.encode(), "0", reward, rc, summary, wall, note2)
        if not pw:
            records[-1]["as_expected"] = False

    # lying ground-truth module: verifier data tampered so the truth matches a wrong answer
    wrong = json.dumps({"k": 0.6785, "rho_c": 1.898e6, "predictions": preds}).encode()
    tamper = ("sed -i 's/^K_SPECIMEN = 0.5862 /K_SPECIMEN = 0.6785 /; s/^RHO_C_SPECIMEN = 1.6385e6 /RHO_C_SPECIMEN = 1.898e6 /' /tests/instance.py; "
              "grep -n '^K_SPECIMEN\\|^RHO_C_SPECIMEN' /tests/instance.py;")
    rc, reward, out, summary, wall = verify(wrong, setup=tamper)
    infra = "VERIFIER INFRASTRUCTURE ERROR" in out and reward == "NO REWARD FILE"
    records.append({"kind": "LYING-TRUTH", "name": "tampered_instance_constants", "test_sh_exit": rc, "reward": reward,
                    "expected": "infrastructure error (no reward file)", "as_expected": infra,
                    "verifier_lines": summary[-6:], "wall_s": round(wall, 2),
                    "note": "lock over instance bytes + graded answers rejects the forged truth"})
    cal_lines.append("%-6s %-44s reward=%-14s expected=%-14s %s  %s" % (
        "LIE", "tampered_instance_constants", reward, "infra-error", "OK " if infra else "BAD",
        "truth module rewritten to agree with a trap-blind answer"))

    with open(os.path.join(HERE, "run_records.json"), "w") as fh:
        json.dump(records, fh, indent=1)
    n_bad = sum(1 for r in records if not r["as_expected"])
    cal_lines.append("TOTAL runs=%d unexpected=%d" % (len(records), n_bad))
    with open(os.path.join(HERE, "calibration_run.log"), "w") as fh:
        fh.write("\n".join(cal_lines) + "\n")
    print("\n".join(cal_lines))
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
