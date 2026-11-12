"""Verifier for the `refund-policy` task.

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

    answer = (root / "answer.txt").read_text(encoding="utf-8") if (root / "answer.txt").is_file() else ""
    check("answer.txt exists and is not empty", bool(answer.strip()))
    check("the answer says 45 days", "45 days" in answer, f"got {answer.strip()!r}")
    check("the answer does not give another plan's window", "14 days" not in answer and "30 days" not in answer)

    return {"reward": 1.0 if all(c["passed"] for c in checks) else 0.0, "checks": checks}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["reward"] == 1.0 else 1)
