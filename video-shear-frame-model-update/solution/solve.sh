#!/bin/bash
set -euo pipefail
mkdir -p /app/output
python3 /solution/solve.py
test -s /app/output/model.json
