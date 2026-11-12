"""Verifier for the `two-edits` task.

Self-contained on purpose (standard library only): a task carries its own tests, so any runner can use it.
Harbor calls it through tests/test.sh; the local runner imports `verify` directly.
"""

import json
import sys
from pathlib import Path


def verify(root: Path) -> dict:
    checks = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    lines = (root / "server.js").read_text(encoding="utf-8").split("\n") if (root / "server.js").is_file() else []
    express = 'const express = require("express");'
    at = lines.index(express) if express in lines else -1
    check(
        "helmet is required on the line below express",
        at >= 0 and lines[at + 1 : at + 2] == ['const helmet = require("helmet");'],
    )
    check("PORT is 8080", "const PORT = 8080;" in lines and "const PORT = 3000;" not in lines)
    check("TIMEOUT_MS is untouched", "const TIMEOUT_MS = 3000;" in lines)
    check("nothing else changed", len(lines) == 10 and "const app = express();" in lines, f"{len(lines)} lines")

    return {"reward": 1.0 if all(c["passed"] for c in checks) else 0.0, "checks": checks}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["reward"] == 1.0 else 1)
