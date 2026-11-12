"""Verifier for the `config-port` task.

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

    original = {"host": "0.0.0.0", "port": 3000, "timeout": 10, "debug": False}
    try:
        data = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        check("config.json is valid JSON", False, str(exc))
        data = None
    if data is not None:
        check("port is 8080", data.get("port") == 8080, f"got {data.get('port')!r}")
        rest = {k: v for k, v in data.items() if k != "port"}
        check(
            "every other setting is unchanged",
            rest == {k: v for k, v in original.items() if k != "port"},
            f"got {rest}",
        )

    return {"reward": 1.0 if all(c["passed"] for c in checks) else 0.0, "checks": checks}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["reward"] == 1.0 else 1)
