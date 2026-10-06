#!/bin/bash
# Reference solution: all logic is in /solution/solve.py.
set -euo pipefail
mkdir -p /app
python3 /solution/solve.py
test -s /app/answer.json
