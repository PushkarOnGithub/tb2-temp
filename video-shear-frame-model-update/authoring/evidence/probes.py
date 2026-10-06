"""Anti-cheat probes and the legitimate-format battery, run through the real test.sh.

Every probe places something at /app/output/model.json inside the verifier
image (built by run_evidence.sh as vsf-verifier:local), runs
``bash /tests/test.sh`` with the network disabled and records the exit
status, the reward file and the wall time.  Exploit probes must end with
reward 0 (or, for the lying ground-truth module, as an infrastructure error
with no reward file) and must leave no side effect; the format battery must
score 1 for every serialisation of a correct answer.

Author-side only: nothing in solution/ or tests/ imports or opens this file.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, "..", ".."))
IMAGE = os.environ.get("VERIFIER_IMG", "vsf-verifier:local")
DOCKER = os.environ.get("DOCKER", "sudo docker").split()


def oracle_model():
    with open(os.path.join(HERE, "run_records.json")) as fh:
        recs = json.load(fh)
    return next(r["artifact"] for r in recs if r["variant"] == "P1-oracle")


def run(setup, extra_mounts=(), shell_prefix=""):
    """setup(dirpath) prepares the artifact directory; returns a result dict."""
    work = tempfile.mkdtemp(prefix="vsf_probe_")
    out = os.path.join(work, "output"); logs = os.path.join(work, "logs")
    os.makedirs(out); os.makedirs(logs)
    os.chmod(out, 0o777); os.chmod(logs, 0o777)
    setup(out)
    cmd = DOCKER + ["run", "--rm", "--network", "none", "-v", "%s:/app/output" % out, "-v", "%s:/logs/verifier" % logs]
    for src, dst in extra_mounts:
        cmd += ["-v", "%s:%s:ro" % (src, dst)]
    cmd += [IMAGE, "bash", "-c", shell_prefix + "bash /tests/test.sh; rc=$?; "
            "if [ -e /tmp/vsf_pwned ]; then echo PWNED_FLAG_PRESENT; fi; exit $rc"]
    t0 = time.time()
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    wall = time.time() - t0
    text = p.stdout.decode(errors="replace")
    reward_path = os.path.join(logs, "reward.txt")
    reward = open(reward_path).read().strip() if os.path.exists(reward_path) else None
    grader_line = next((ln for ln in text.splitlines() if ln.startswith(("FAIL", "VSF-GRADER", "VERIFIER INFRA"))), "")
    shutil.rmtree(work, ignore_errors=True)
    return {"exit": p.returncode, "reward": reward, "wall_s": round(wall, 2),
            "pwned": "PWNED_FLAG_PRESENT" in text, "grader_line": grader_line}


def write(text, binary=False):
    def setup(d):
        mode = "wb" if binary else "w"
        with open(os.path.join(d, "model.json"), mode) as fh:
            fh.write(text)
    return setup


def main():
    good = oracle_model()
    k = good["k"]
    inj = "__import__('os').system('touch /tmp/vsf_pwned')"

    def symlink(target):
        def setup(d):
            os.symlink(target, os.path.join(d, "model.json"))
        return setup

    def fifo(d):
        os.mkfifo(os.path.join(d, "model.json"))

    def bomb(d):
        depth = 30000
        with open(os.path.join(d, "model.json"), "w") as fh:
            fh.write('{"k": ' + "[" * depth + "]" * depth + "}")

    forged_dir = tempfile.mkdtemp(prefix="vsf_forge_")
    forged = os.path.join(forged_dir, "instance.py")
    with open(os.path.join(PKG, "tests", "instance.py")) as fh:
        src = fh.read()
    # Lying ground-truth module: identical shipped files, forged answers.
    src = src.replace("def simulate_displacements():", "_REAL_K = list(K_TRUE)\n\n\ndef simulate_displacements():")
    src = src.replace("    omega, phi = modes(K_TRUE, m)", "    omega, phi = modes(_REAL_K, m)")
    src += "\nK_TRUE = [6983.0, 6984.0, 6665.0, 3848.0]\n"
    with open(forged, "w") as fh:
        fh.write(src)
    os.chmod(forged, 0o644)
    os.chmod(forged_dir, 0o755)

    blind = [6983.0, 6984.0, 6665.0, 3848.0]
    exploit = [
        ("X01 code-injection strings", write(json.dumps({"k": [inj] * 4}))),
        ("X02 dunder/attribute walk object", write(json.dumps({"k": {"__class__": {"__init__": "__globals__"}}}))),
        ("X03 open()-and-write-reward payload", write(json.dumps({"k": "open('/logs/verifier/reward.txt','w').write('1')"}))),
        ("X04 nested-list expression bomb (depth 30000)", bomb),
        ("X05 symlink to the verifier's truth deriver", symlink("/tests/derive_truth.py")),
        ("X06 symlink to /dev/zero", symlink("/dev/zero")),
        ("X07 FIFO at the artifact path", fifo),
        ("X08 oversized file (70 KiB of whitespace + valid model)", write(" " * 70000 + json.dumps(good))),
        ("X09 NaN and Infinity values", write('{"k": [NaN, Infinity, 5000, 5000]}')),
        ("X10 duplicate key: wrong k then right k", write('{"k": [1, 1, 1, 1], "k": %s}' % json.dumps(k))),
        ("X11 every-candidate submission (extra key with alternatives)", write(json.dumps(dict(good, k_alternatives=[blind, k])))),
        ("X12 k given as strings", write(json.dumps({"k": [str(x) for x in k]}))),
        ("X13 out-of-range values (1e308, 0, negative)", write(json.dumps({"k": [1e308, 0.0, -5000.0, 5100.0]}))),
        ("X14 visible objects only: frame fitted to the four apparent frequencies", write(json.dumps({"k": blind}))),
        ("X15 empty object", write("{}")),
        ("X16 eight stiffnesses (both candidate models concatenated)", write(json.dumps({"k": blind + k}))),
    ]
    infra = [
        ("I01 lying ground-truth module (same shipped bytes, forged answers)", write(json.dumps({"k": blind})),
         [(forged, "/tests/instance.py")]),
    ]
    legit = [
        ("L01 compact separators", json.dumps(good, separators=(",", ":"))),
        ("L02 indent 4 + trailing newline", json.dumps(good, indent=4) + "\n"),
        ("L03 integers", json.dumps({"k": [int(round(x)) for x in k]})),
        ("L04 exponent notation", '{"k": [%s]}' % ", ".join("%.15e" % x for x in k)),
        ("L05 upper-case exponent, no trailing newline", '{"k":[%s]}' % ",".join("%sE-3" % repr(x * 1000) for x in k)),
        ("L06 CRLF line endings", json.dumps(good, indent=2).replace("\n", "\r\n") + "\r\n"),
        ("L07 UTF-8 byte-order mark", ("\ufeff" + json.dumps(good)).encode("utf-8")),
        ("L08 unicode-escaped key name", json.dumps(good).replace('"k"', '"\\u006b"')),
        ("L09 tabs and padding whitespace", "\t \n" + json.dumps(good, indent="\t") + "\n\n  "),
        ("L10 fixed-point with trailing zeros", '{"k": [%s]}' % ", ".join("%.6f" % x for x in k)),
        ("L11 short rounding (3 significant digits)", json.dumps({"k": [float("%.3g" % x) for x in k]})),
        ("L12 explicit +0 exponent", '{"k": [%s]}' % ", ".join("%.10fe+0" % x for x in k)),
    ]

    lines, records = [], []
    for name, setup in exploit:
        r = run(setup)
        ok = r["reward"] == "0" and r["exit"] == 0 and not r["pwned"]
        records.append(dict(r, probe=name, kind="exploit", as_expected=ok))
        lines.append("%-74s exit=%d reward=%s pwned=%s %5.2fs %s | %s" % (name, r["exit"], r["reward"], r["pwned"], r["wall_s"], "OK" if ok else "BAD", r["grader_line"][:90]))
        print(lines[-1], flush=True)
    for name, setup, mounts in infra:
        r = run(setup, extra_mounts=mounts)
        ok = r["reward"] is None and r["exit"] != 0 and not r["pwned"]
        records.append(dict(r, probe=name, kind="verifier-corruption", as_expected=ok))
        lines.append("%-74s exit=%d reward=%s pwned=%s %5.2fs %s | infrastructure error expected" % (name, r["exit"], r["reward"], r["pwned"], r["wall_s"], "OK" if ok else "BAD"))
        print(lines[-1], flush=True)
    for name, text in legit:
        r = run(write(text, binary=isinstance(text, bytes)))
        ok = r["reward"] == "1" and r["exit"] == 0
        records.append(dict(r, probe=name, kind="legitimate-format", as_expected=ok))
        lines.append("%-74s exit=%d reward=%s %5.2fs %s" % (name, r["exit"], r["reward"], r["wall_s"], "OK" if ok else "BAD"))
        print(lines[-1], flush=True)
    with open(os.path.join(HERE, "probe_run.log"), "w") as fh:
        fh.write("Probes run through bash /tests/test.sh in the verifier image (--network none)\n\n")
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(HERE, "probe_records.json"), "w") as fh:
        json.dump(records, fh, indent=1)
    if not all(r["as_expected"] for r in records):
        raise SystemExit("some probes did not behave as expected")


if __name__ == "__main__":
    main()
