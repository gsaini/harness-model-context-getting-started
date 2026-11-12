"""Keep a long run inside the context window.

Two strategies, so lesson 4 can compare them:

- "truncate":  keep the task and the last few turns, drop the middle. Cheap, and it silently loses facts.
- "summarize": ask the model for a summary, then start over from task + summary and replay nothing else.

"summarize" is the shape Anthropic's docs call simple compaction. Replaying *some* old turns after an edit
(as "truncate" does) invalidates the reasoning blocks of current Claude models, which are tied to the exact
history that produced them; the Claude adapter asks the API to drop such blocks instead of failing.
"""

from __future__ import annotations

from agentlab.harness import Middleware, State
from agentlab.messages import request_tokens, text_of, user
from agentlab.models.scripted import SUMMARIZE_PROMPT, SUMMARY_MARKER


class Compaction(Middleware):
    def __init__(self, strategy: str = "summarize", *, trigger: float = 0.7, keep_turns: int = 2):
        if strategy not in ("truncate", "summarize"):
            raise ValueError(f"unknown compaction strategy {strategy!r}")
        self.name = f"compaction:{strategy}"
        self.strategy = strategy
        self.trigger = trigger  # compact when the next request would pass this share of the window
        self.keep_turns = keep_turns

    def before_model(self, state: State) -> None:
        before = request_tokens(state.system, state.messages, state.tools)
        if before <= state.model.context_window * self.trigger:
            return
        state.messages = self._truncate(state) if self.strategy == "truncate" else self._summarize(state)
        after = request_tokens(state.system, state.messages, state.tools)
        state.emit({"type": "compaction", "strategy": self.strategy, "before_tokens": before, "after_tokens": after})

    def _truncate(self, state: State) -> list[dict]:
        # A turn is an assistant message plus the tool results that answer it; keep whole turns only.
        tail = state.messages[1:][-2 * self.keep_turns :]
        while tail and tail[0]["role"] != "assistant":
            tail = tail[1:]
        return [state.messages[0], *tail]

    def _summarize(self, state: State) -> list[dict]:
        # Same system prompt and tools as every other call, so a provider-side prompt cache still hits.
        reply = state.model.complete(
            system=state.system, messages=[*state.messages, user(SUMMARIZE_PROMPT)], tools=state.tools
        )
        state.add_usage(reply.usage)  # compaction isn't free: it is a model call
        summary = "\n".join(b["text"] for b in reply.content if b.get("type") == "text").strip()
        spoken = [m for m in state.messages if m["role"] == "user" and text_of(m)]
        task = text_of(spoken[-1]).partition(SUMMARY_MARKER)[0].strip()
        return [user(f"{task}\n\n{SUMMARY_MARKER}\n{summary}\n\nContinue the task from here.")]
