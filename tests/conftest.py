import pytest

from agentlab import ROOT
from agentlab.evals import load_tasks


@pytest.fixture(scope="session")
def tasks():
    return {task.id: task for task in load_tasks(ROOT / "tasks")}
