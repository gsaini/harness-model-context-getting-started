#!/bin/bash
# Reference solution: proves the task can be solved and that the verifier accepts a correct result.
# Harbor's oracle agent runs it in the container; the local `agentlab oracle` sets APP_DIR to a temp workspace.
set -euo pipefail
cd "${APP_DIR:-/app}"
python3 - <<'PY'
import json, pathlib
from decimal import Decimal
total = sum(Decimal(str(json.loads(p.read_text())["amount"])) for p in sorted(pathlib.Path("invoices").glob("*.json")))
pathlib.Path("total.txt").write_text(f"{total:.2f}\n")
PY
