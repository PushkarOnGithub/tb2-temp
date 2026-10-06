"""Write environment/data and tests/lock.json from tests/instance.py (authoring only).

Run from the task root:  python3 authoring/generate.py [--check]
--check verifies, without writing, that environment/data is byte-identical to
the generator output and that tests/lock.json matches the regenerated truth.
"""

import json
import os
import sys

sys.dont_write_bytecode = True  # keep tests/ and solution/ free of __pycache__

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import derive_truth  # noqa: E402
import instance  # noqa: E402

DATA_DIR = os.path.join(ROOT, "environment", "data")
LOCK = os.path.join(ROOT, "tests", "lock.json")


def main(check):
    files, visible, heldout = instance.build()
    digest = derive_truth.canonical_digest(files, visible, heldout)
    problems = []
    for name, blob in sorted(files.items()):
        path = os.path.join(DATA_DIR, name)
        if check:
            with open(path, "rb") as fh:
                if fh.read() != blob:
                    problems.append("environment/data/%s differs from generator output" % name)
        else:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(blob)
    extra = sorted(set(os.listdir(DATA_DIR)) - set(files))
    if extra:
        problems.append("unexpected files in environment/data: %s" % extra)
    if check:
        with open(LOCK) as fh:
            if json.load(fh)["sha256"] != digest:
                problems.append("tests/lock.json does not match regenerated truth")
    else:
        with open(LOCK, "w") as fh:
            json.dump({"sha256": digest}, fh)
            fh.write("\n")
    print("digest", digest)
    for sid, temp in visible:
        print("visible %s T_true = %.6f C" % (sid, temp))
    print("held-out scenarios: %d" % len(heldout))
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv[1:]))
