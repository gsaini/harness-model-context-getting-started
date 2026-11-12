#!/bin/bash
# Reference solution: proves the task can be solved and that the verifier accepts a correct result.
# Harbor's oracle agent runs it in the container; the local `agentlab oracle` sets APP_DIR to a temp workspace.
set -euo pipefail
cd "${APP_DIR:-/app}"
python3 - <<'PY'
import pathlib
p = pathlib.Path("server.js")
text = p.read_text()
express = 'const express = require("express");'
text = text.replace(express, express + '\nconst helmet = require("helmet");', 1)
p.write_text(text.replace("const PORT = 3000;", "const PORT = 8080;", 1))
PY
