#!/bin/bash
# Verifier entry point.
#
# Reward contract:
#   grader exit 0 + exact verdict line, and pytest exit 0  -> reward 1
#   grader exit 1 (submission fails a stated requirement)  -> reward 0
#   pytest exit 1 (some itemised check failed)             -> reward 0
#   grader exit 2 / other / timeout, verdict line missing,
#   or pytest exit 2-5 (interrupted, internal, usage,
#   nothing collected)                                     -> infrastructure error:
#                                                             no reward file, exit 1
# The reward is decided by the grader (python3 -I -S, standard library only);
# pytest renders the itemised report and must agree.
set -euo pipefail

REWARD=/logs/verifier/reward.txt
OUT=/logs/verifier/grader.out
VERDICT="VERDICT: PASS transient-heater-panel-prediction all-36-temperatures-within-tolerance"

mkdir -p /logs/verifier
rm -f "${REWARD}"
echo 0 > "${REWARD}"

infra() { rm -f "${REWARD}"; echo "VERIFIER INFRASTRUCTURE ERROR: $1" >&2; exit 1; }

grader=0
timeout 100 python3 -I -S /tests/check_submission.py > "${OUT}" 2>&1 || grader=$?
cat "${OUT}"
case "${grader}" in
  0) grep -qxF "${VERDICT}" "${OUT}" || infra "grader exited 0 without its verdict line" ;;
  1) ;;
  *) infra "grader exit status ${grader}" ;;
esac

report=0
timeout 100 pytest -rA --ctrf /logs/verifier/ctrf.json -p no:cacheprovider --rootdir=/tests /tests/test_outputs.py || report=$?
case "${report}" in
  0|1) ;;
  *) infra "pytest exit status ${report}" ;;
esac

if [ "${grader}" -eq 0 ] && [ "${report}" -eq 0 ]; then
  rm -f "${REWARD}"
  echo 1 > "${REWARD}"
fi
echo "reward: $(cat "${REWARD}")"
