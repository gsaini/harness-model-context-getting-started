"""Verifier for the `changelog-entry` task.

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

    text = (root / "CHANGELOG.md").read_text(encoding="utf-8") if (root / "CHANGELOG.md").is_file() else ""
    lines = text.split("\n")
    entry = "- **1.4.0** — Fixed the login redirect bug"
    at = lines.index("## Unreleased") if "## Unreleased" in lines else -1
    check(
        "the entry is the first line under ## Unreleased",
        at >= 0 and lines[at + 1 : at + 2] == [entry],
        f"expected {entry!r} there",
    )
    check("the entry appears exactly once", text.count("1.4.0") == 1)
    check(
        "earlier entries are still there",
        all(old in lines for old in ["- **1.3.1** — Fixed a crash on empty search", "- **1.3.0** — Added dark mode"]),
    )

    return {"reward": 1.0 if all(c["passed"] for c in checks) else 0.0, "checks": checks}


if __name__ == "__main__":
    result = verify(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["reward"] == 1.0 else 1)
