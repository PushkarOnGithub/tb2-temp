#!/bin/bash
# Reward contract (reward file: /logs/verifier/reward.txt, strictly 0 or 1).
#   check_submission.py exit 0 + exact verdict line -> requirement met
#   check_submission.py exit 1                      -> submission fails a stated requirement (reward 0)
#   check_submission.py exit 2 / timeout / other    -> verifier infrastructure error:
#                                                      reward file removed, test.sh exits 1
#   pytest exit 0 or 1 -> itemised result; pytest exit 2-5 -> infrastructure error
# Reward 1 is written only when the grader AND pytest both succeed.
set -euo pipefail

REWARD=/logs/verifier/reward.txt
OUT=/logs/verifier/grader.log
VERDICT="VSF-GRADER: PASS all 164 natural frequencies within tolerance"

mkdir -p /logs/verifier
infra() { rm -f "${REWARD}"; echo "VERIFIER INFRASTRUCTURE ERROR: $1" >&2; exit 1; }

rm -f "${REWARD}"
echo 0 > "${REWARD}"

grader=0
timeout 200 python3 -I -S /tests/check_submission.py > "${OUT}" 2>&1 || grader=$?
cat "${OUT}"
case "${grader}" in
  0) grep -qxF "${VERDICT}" "${OUT}" || infra "grader exited 0 without its verdict line" ;;
  1) ;;
  *) infra "grader exit status ${grader}" ;;
esac

report=0
pytest -rA --ctrf /logs/verifier/ctrf.json -p no:cacheprovider --rootdir=/tests /tests/test_outputs.py || report=$?
case "${report}" in
  0|1) ;;
  *) infra "pytest exit status ${report}" ;;
esac

if [ "${grader}" -eq 0 ] && [ "${report}" -eq 0 ]; then
  rm -f "${REWARD}"
  echo 1 > "${REWARD}"
fi
echo "reward: $(cat "${REWARD}")"
