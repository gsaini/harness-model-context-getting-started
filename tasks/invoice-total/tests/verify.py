"""Verifier for the `invoice-total` task.

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

    from decimal import Decimal, InvalidOperation

    raw = (root / "total.txt").read_text(encoding="utf-8").strip() if (root / "total.txt").is_file() else ""
    try:
        total = Decimal(raw)
    except InvalidOperation:
        total = None
    check("total.txt holds a number", total is not None, f"got {raw!r}")
    check("the total is 47249.94", total == Decimal("47249.94"), f"got {raw!r}")

    return {"reward": 1.0 if all(c["passed"] for c in checks) else 0.0, "checks": checks}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["reward"] == 1.0 else 1)
