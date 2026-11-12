"""agentlab: a small agent harness, a stand-in model, and the tooling around them (evals, traces, a flywheel)."""

from pathlib import Path

# The repository root (src/agentlab/__init__.py -> two levels up). Fixtures, tasks and lessons live there.
ROOT = Path(__file__).resolve().parents[2]
