#!/bin/bash
# Reference solution: proves the task can be solved and that the verifier accepts a correct result.
# Harbor's oracle agent runs it in the container; the local `agentlab oracle` sets APP_DIR to a temp workspace.
set -euo pipefail
cd "${APP_DIR:-/app}"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("config/settings.json")
data = json.loads(p.read_text())
data["port"] = 9090
p.write_text(json.dumps(data, indent=2) + "\n")
PY
