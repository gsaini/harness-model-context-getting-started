"""Models behind one interface (`agentlab.harness.Model`): pick one by name.

scripted-careful   the default stand-in: reads before it edits
scripted-fast      a cheaper stand-in that guesses instead of reading
scripted-liner     a stand-in whose native edit tool is line patches
claude             Claude Opus 5.5 through the Anthropic SDK (needs credentials; costs money)
claude-<id>        any other Claude model id, e.g. claude-haiku-5-5
"""

from __future__ import annotations

from agentlab.harness import Model
from agentlab.models import scripted

SCRIPTED = {"scripted-careful": scripted.careful, "scripted-fast": scripted.fast, "scripted-liner": scripted.liner}


def is_live(name: str) -> bool:
    """True for models that call a paid API."""
    return name not in SCRIPTED


def get_model(name: str = "scripted-careful", **options: object) -> Model:
    if name in SCRIPTED:
        return SCRIPTED[name]()
    if name == "claude" or name.startswith("claude-"):
        from agentlab.models.claude import DEFAULT_MODEL, ClaudeModel  # imported late: needs the anthropic package

        return ClaudeModel(DEFAULT_MODEL if name == "claude" else name, **options)
    raise ValueError(f"unknown model {name!r}. Choose from: {', '.join(SCRIPTED)}, claude, claude-<model-id>")
