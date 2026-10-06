#!/bin/bash
# Author-side evidence runner (never used at build, solve or grade time).
#
# Builds the agent and verifier images, runs the oracle with the network
# removed, grades it in the separate verifier image, grades a no-op run, and
# re-runs the wrong-method harness and the probe battery.
#
# Local sandbox note: the authoring machine reaches registries through a
# TLS-intercepting proxy and cannot download blobs from public.ecr.aws, so the
# images are built from byte-identical copies of the two Dockerfiles whose FROM
# line names the same manifest digest on Docker Hub, with the proxy CA trusted
# for the pip step only.  The shipped Dockerfiles are not modified.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "${HERE}/../.." && pwd)"
WORK="${WORK:-$(mktemp -d)}"
CA="${CA:-/root/.ccr/ca-bundle.crt}"
DOCKER="${DOCKER:-sudo docker}"
AGENT_IMG=vsf-agent:local
VERIFIER_IMG=vsf-verifier:local

localize() {  # $1 = source context, $2 = destination context
  rm -rf "$2"; cp -r "$1" "$2"; cp "${CA}" "$2/zz-local-ca.crt"
  sed -i -e 's#^FROM public.ecr.aws/docker/library/ubuntu:24.04@#FROM ubuntu:24.04@#' \
         -e 's#^RUN pip install #COPY zz-local-ca.crt /tmp/ca.crt\nRUN PIP_CERT=/tmp/ca.crt pip install #' "$2/Dockerfile"
}

localize "${PKG}/environment" "${WORK}/env"
localize "${PKG}/tests" "${WORK}/tests"
${DOCKER} build -q --network host -t "${AGENT_IMG}" "${WORK}/env" >/dev/null
${DOCKER} build -q --network host -t "${VERIFIER_IMG}" "${WORK}/tests" >/dev/null
echo "images built: ${AGENT_IMG} ${VERIFIER_IMG}"

grade() {  # $1 = host dir holding model.json (may be empty), $2 = host dir for /logs/verifier
  mkdir -p "$2"; chmod 777 "$2"
  local rc=0
  ${DOCKER} run --rm --network none -v "$1:/app/output" -v "$2:/logs/verifier" "${VERIFIER_IMG}" \
    bash /tests/test.sh || rc=$?
  echo "test.sh exit status: ${rc}"
  echo "reward.txt: $(cat "$2/reward.txt" 2>/dev/null || echo '<absent>')"
}

# ---- offline oracle run --------------------------------------------------------
OUT="${WORK}/oracle_out"; mkdir -p "${OUT}"; chmod 777 "${OUT}"
{
  echo "== offline oracle run ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  ${DOCKER} run --rm --network none -v "${PKG}/solution:/solution:ro" -v "${OUT}:/app/output" \
    -v "${HERE}/net_probe.py:/probe/net_probe.py:ro" "${AGENT_IMG}" \
    bash -c 'python3 /probe/net_probe.py; start=$(date +%s.%N); bash /solution/solve.sh; rc=$?; end=$(date +%s.%N); echo "oracle exit status: ${rc}"; python3 -c "print(\"oracle wall time: %.2f s\" % (${end}-${start}))"; ls -l /app/output/model.json; cat /app/output/model.json'
  echo "== verifier (separate image, --network none)"
  grade "${OUT}" "${WORK}/oracle_logs"
} 2>&1 | tee "${HERE}/offline_oracle_run.log"

# ---- no-op run -------------------------------------------------------------------
NOP="${WORK}/nop_out"; mkdir -p "${NOP}"; chmod 777 "${NOP}"
{ echo "== no-op run (no artifact written)"; grade "${NOP}" "${WORK}/nop_logs"; } 2>&1 | tee "${HERE}/nop_run.log"

# ---- independent truth, identifiability, wrong-method harness, probes ------------
python3 "${HERE}/independent_truth.py" | tee "${HERE}/independent_truth.log"
python3 "${HERE}/identifiability.py" >/dev/null
python3 "${HERE}/variants.py"
python3 "${HERE}/independent_solver.py"
python3 "${HERE}/mutations.py"
python3 "${HERE}/seed_sweep.py" 10
python3 "${HERE}/probes.py"
