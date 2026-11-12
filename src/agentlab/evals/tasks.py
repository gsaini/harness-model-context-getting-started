"""Eval tasks, laid out the way Harbor lays them out.

    tasks/<name>/
      instruction.md           what the agent is told
      task.toml                metadata and limits
      environment/Dockerfile   the sandbox image; it copies environment/workspace/ to /app
      solution/solve.sh        a reference solution, to prove the task is solvable
      tests/test.sh            the verifier Harbor runs; writes the reward to /logs/verifier/reward.txt
      tests/verify.py          the checks themselves (test.sh calls it; the local runner imports it)

The local runner skips Docker: its sandbox is a fresh temporary directory plus the tools' path jail.
"""

from __future__ import annotations

import importlib.util
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Task:
    id: str
    instruction: str
    verifier: Callable[[Path], dict]  # workspace -> {"reward": 0..1, "checks": [{name, passed, detail}]}
    directory: Path | None = None  # set for tasks loaded from disk
    files: dict[str, str] = field(default_factory=dict)  # set for tasks generated in memory
    meta: dict = field(default_factory=dict)

    def setup(self, sandbox: Path) -> Path:
        """Create the starting workspace inside `sandbox` and return its path."""
        workspace = sandbox / "workspace"
        if self.directory:
            shutil.copytree(self.directory / "environment" / "workspace", workspace)
        else:
            for relative, content in self.files.items():
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def verify(self, workspace: Path) -> dict:
        return self.verifier(workspace)


def _load_verifier(path: Path) -> Callable[[Path], dict]:
    spec = importlib.util.spec_from_file_location(f"verify_{path.parent.parent.name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


def load_task(directory: Path) -> Task:
    meta = tomllib.loads((directory / "task.toml").read_text(encoding="utf-8"))
    return Task(
        id=directory.name,
        instruction=(directory / "instruction.md").read_text(encoding="utf-8").strip(),
        verifier=_load_verifier(directory / "tests" / "verify.py"),
        directory=directory,
        meta=meta.get("metadata", {}),
    )


def load_tasks(directory: Path) -> list[Task]:
    return [load_task(d) for d in sorted(Path(directory).iterdir()) if (d / "task.toml").is_file()]
