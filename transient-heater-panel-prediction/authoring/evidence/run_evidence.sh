#!/bin/bash
# Rebuild both images from the current tree, then drive every calibration run.
# Usage (from anywhere):  bash authoring/evidence/run_evidence.sh
# Hosts behind a TLS-intercepting proxy must make the verifier image's pip
# layer trust that proxy themselves; the shipped Dockerfiles stay unchanged.
set -euo pipefail
TASK="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "${TASK}/authoring/generate.py" --check
docker build -q -t thpp-env "${TASK}/environment"
docker build -q -t thpp-verifier "${TASK}/tests"
AGENT_IMAGE=thpp-env VERIFIER_IMAGE=thpp-verifier python3 "${TASK}/authoring/evidence/run_evidence.py"
