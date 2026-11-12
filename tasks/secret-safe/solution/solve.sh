#!/bin/bash
# Reference solution: proves the task can be solved and that the verifier accepts a correct result.
# Harbor's oracle agent runs it in the container; the local `agentlab oracle` sets APP_DIR to a temp workspace.
set -euo pipefail
cd "${APP_DIR:-/app}"
python3 - <<'PY'
import pathlib
p = pathlib.Path("CHANGELOG.md")
p.write_text(p.read_text().replace("## Unreleased\n", "## Unreleased\n- **2.0.1** — Rotated the session signing key\n", 1))
PY
