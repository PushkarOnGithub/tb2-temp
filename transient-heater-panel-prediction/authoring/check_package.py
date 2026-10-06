"""Static package checks mirroring the review gates (authoring only).

Run from anywhere:  python3 authoring/check_package.py
Exits 0 when every check passes; prints one line per check.
"""

import ast
import json
import os
import re
import stat
import subprocess
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

BIDI_ZW = "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0x202E, 0x2066, 0x2067))
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CLOSING = ("You have 600 seconds to complete this task. Do not cheat by using online solutions "
           "or hints specific to this task.")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def main():
    # --- layout -----------------------------------------------------------
    required = ["task.toml", "instruction.md", "README.md", "environment/Dockerfile", "environment/.dockerignore",
                "solution/solve.sh", "solution/solve.py", "tests/Dockerfile", "tests/.dockerignore", "tests/test.sh",
                "tests/test_outputs.py", "tests/check_submission.py", "tests/derive_truth.py", "tests/instance.py",
                "tests/thermal_model.py", "tests/answer_format.py", "tests/lock.json", "authoring/README.md",
                "authoring/evidence/offline_oracle_run.log", "authoring/evidence/calibration_run.log",
                "authoring/evidence/run_records.json"]
    missing = [r for r in required if not os.path.exists(os.path.join(ROOT, r))]
    check("required files present", not missing, ", ".join(missing))
    env_entries = sorted(os.listdir(os.path.join(ROOT, "environment")))
    check("environment/ holds only Dockerfile, .dockerignore, data/", env_entries == [".dockerignore", "Dockerfile", "data"],
          str(env_entries))
    stray = [os.path.join(d, n) for d, ds, fs in os.walk(ROOT) for n in ds + fs
             if n in ("__pycache__", ".pytest_cache") or n.endswith(".pyc")]
    check("no caches in the package", not stray, ", ".join(stray[:5]))

    # --- task.toml ----------------------------------------------------------
    raw = read("task.toml")
    if tomllib:
        cfg = tomllib.loads(raw)
        check("schema_version 1.3", cfg.get("schema_version") == "1.3")
        check("artifacts == ['/app/answer.json'] at top level", cfg.get("artifacts") == ["/app/answer.json"])
        task = cfg.get("task", {})
        check("task.name is org/name", re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", task.get("name", "")) is not None
              and ".." not in task.get("name", ""), task.get("name"))
        check("task.description and keywords present", bool(task.get("description")) and bool(task.get("keywords")))
        md = cfg.get("metadata", {})
        hours = md.get("expert_time_estimate_hours", 0)
        check("expert_time_estimate_hours in (0, 1.5]", 0 < hours <= 1.5, str(hours))
        check("agent timeout 600", cfg.get("agent", {}).get("timeout_sec") == 600.0)
        ver = cfg.get("verifier", {})
        check("verifier separate, timeout < 28800", ver.get("environment_mode") == "separate"
              and 0 < ver.get("timeout_sec", 0) < 28800)
        check("verifier no-network, agent public", ver.get("environment", {}).get("network_mode") == "no-network"
              and cfg.get("environment", {}).get("network_mode") == "public")
    deprecated = [k for k in ("difficulty_explanation", "solution_explanation", "verification_explanation", "allow_internet")
                  if k in raw]
    check("no deprecated task.toml keys", not deprecated, ", ".join(deprecated))

    # --- instruction.md -------------------------------------------------------
    ins = read("instruction.md")
    lines = [l for l in ins.splitlines() if l.strip()]
    check("closing line exact and last", lines[-1] == CLOSING)
    check("no test internals or HTML in instruction", not re.search(r"pytest|/tests|<[a-zA-Z]", ins))
    paths = set(re.findall(r"`(/app/[^`]+)`", ins))
    shipped = {"/app/data/" + n for n in os.listdir(os.path.join(ROOT, "environment", "data"))}
    bad = sorted(p for p in paths if p not in shipped and p != "/app/answer.json" and p != "/app/data")
    check("every /app path named in instruction exists in the image or is the artifact", not bad, ", ".join(bad))
    check("instruction names the artifact path", "/app/answer.json" in ins)
    words = len(re.findall(r"\S+", ins))
    check("instruction length (words) <= 650", words <= 650, str(words))

    # --- Dockerfiles ----------------------------------------------------------
    for rel in ("environment/Dockerfile", "tests/Dockerfile"):
        df = read(rel)
        froms = re.findall(r"^FROM\s+(\S+)", df, re.M)
        check("%s: FROM pinned by tag and digest" % rel,
              froms and all(re.search(r":[\w.-]+@sha256:[0-9a-f]{64}$", f) for f in froms), " ".join(froms))
        check("%s: apt in one RUN with cleanup" % rel,
              all("rm -rf /var/lib/apt/lists/*" in l for l in df.splitlines() if "apt-get install" in l))
        pips = re.findall(r"pip install[^\n]*", df)
        unpinned = [tok for p in pips for tok in p.split()[2:] if not tok.startswith("-") and "==" not in tok]
        check("%s: pip packages pinned with ==" % rel, not unpinned, " ".join(unpinned))
        check("%s: no ARG, only benign ENV" % rel, "ARG " not in df and
              all(k in ("DEBIAN_FRONTEND", "PYTHONDONTWRITEBYTECODE", "PIP_NO_CACHE_DIR", "PIP_DISABLE_PIP_VERSION_CHECK")
                  for k in re.findall(r"(\w+)=", " ".join(re.findall(r"^ENV[^\n]*(?:\\\n[^\n]*)*", df, re.M)))))
    envdf = read("environment/Dockerfile")
    check("agent Dockerfile never mentions solution or tests", not re.search(r"solution|tests", envdf))
    check("agent Dockerfile has no wildcard COPY", not re.search(r"^COPY[^\n]*[*?]", envdf, re.M))
    check("verifier Dockerfile pins pytest and pytest-json-ctrf, mkdirs, COPY . /tests/",
          re.search(r"pytest==[\d.]+", read("tests/Dockerfile")) and re.search(r"pytest-json-ctrf==[\d.]+", read("tests/Dockerfile"))
          and "mkdir -p /app /logs/verifier" in read("tests/Dockerfile") and "COPY . /tests/" in read("tests/Dockerfile"))

    # --- solution -------------------------------------------------------------
    sh = read("solution/solve.sh")
    mode = os.stat(os.path.join(ROOT, "solution/solve.sh")).st_mode
    check("solve.sh executable with bash shebang", sh.startswith("#!/bin/bash") and mode & stat.S_IXUSR)
    check("solve.sh plain commands (no heredoc, no python -c)", "<<" not in sh and "python3 -c" not in sh)
    solve = read("solution/solve.py")
    check("solve.py reads only /app/data and never tests/", "/tests" not in solve and "tests/" not in solve)

    # --- tests ------------------------------------------------------------------
    tsh = read("tests/test.sh")
    mode = os.stat(os.path.join(ROOT, "tests/test.sh")).st_mode
    check("test.sh executable, set -euo pipefail, pytest -rA --ctrf",
          mode & stat.S_IXUSR and "set -euo pipefail" in tsh and re.search(r"pytest -rA --ctrf /logs/verifier/ctrf.json", tsh))
    check("test.sh writes 0 first and 1 only on grader+pytest success",
          'echo 0 > "${REWARD}"' in tsh and 'if [ "${grader}" -eq 0 ] && [ "${report}" -eq 0 ]' in tsh)
    verdict_sh = re.search(r'VERDICT="([^"]+)"', tsh).group(1)
    verdict_py = re.search(r'VERDICT = "([^"]+)"', read("tests/check_submission.py")).group(1)
    check("verdict line identical in grader and test.sh", verdict_sh == verdict_py)
    tree = ast.parse(read("tests/test_outputs.py"))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    tests = [f for f in funcs if f.name.startswith("test_")]
    check("pytest module has test_ functions, all with docstrings (fixtures too)",
          tests and all(ast.get_docstring(f) for f in funcs))
    for rel in ("tests/check_submission.py", "tests/derive_truth.py", "tests/instance.py", "tests/thermal_model.py",
                "tests/answer_format.py"):
        mods = {a.name.split(".")[0] for n in ast.walk(ast.parse(read(rel))) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(ast.parse(read(rel))) if isinstance(n, ast.ImportFrom) and n.module}
        third = sorted(m for m in mods if m not in sys.stdlib_module_names
                       and m not in ("instance", "thermal_model", "answer_format", "derive_truth"))
        check("%s is standard-library only" % rel, not third, ", ".join(third))

    # --- hygiene / security ---------------------------------------------------
    code_files = [os.path.join(d, f) for d, _, fs in os.walk(ROOT) for f in fs if f.endswith((".py", ".sh"))]
    evals, nonascii = [], []
    for p in code_files:
        txt = open(p, encoding="utf-8").read()
        if re.search(r"(?<![\w.])(eval|exec)\s*\(", txt):
            evals.append(os.path.relpath(p, ROOT))
        for i, line in enumerate(txt.splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(ord(c) > 127 for c in code) and not line.lstrip().startswith(("#", '"""', "'")):
                nonascii.append("%s:%d" % (os.path.relpath(p, ROOT), i))
    check("no eval/exec in code", not evals, ", ".join(evals))
    check("code is ASCII outside comments/docstrings", not nonascii, ", ".join(nonascii[:5]))
    hidden = [os.path.relpath(os.path.join(d, f), ROOT) for d, _, fs in os.walk(ROOT) for f in fs
              if any(c in open(os.path.join(d, f), "rb").read().decode("utf-8", "replace") for c in BIDI_ZW)]
    check("no zero-width or bidi control characters", not hidden, ", ".join(hidden))

    # --- data and lock in sync --------------------------------------------------
    gen = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "authoring", "generate.py"), "--check"],
                         capture_output=True, text=True, timeout=120)
    check("environment/data and tests/lock.json match the generator", gen.returncode == 0, gen.stdout[-300:])
    q = json.loads(read("environment/data/queries.json"))
    check("six visible scenarios, as stated", len(q["scenarios"]) == 6)

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print("%s  %-*s %s" % ("PASS" if ok else "FAIL", width, name, ("" if ok else detail)))
    n_fail = sum(1 for _, ok, _ in results if not ok)
    print("CHECK_PACKAGE %s (%d checks, %d failed)" % ("PASS" if not n_fail else "FAIL", len(results), n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
