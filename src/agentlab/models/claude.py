"""Claude behind the same `Model` interface as the stand-in.

The harness works on plain dicts; this adapter is the only place that knows about the Anthropic SDK and the
quirks of particular Claude models. Swapping providers means writing one more file like this one.

Running it costs money and needs credentials (ANTHROPIC_API_KEY, or a profile from `ant auth login`).
"""

from __future__ import annotations

from typing import Any

import anthropic

from agentlab.harness import Response

DEFAULT_MODEL = "claude-opus-5-5"

# $ per million tokens: (input, output, cache read). Cache writes cost 1.25x input. For estimates only.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-2": (8.00, 40.00, 0.20),
}
# Models where a safety classifier's refusal can be re-run server-side on a recommended fallback model.
FALLBACKS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"}
# Models whose reasoning blocks are tied to the exact history that produced them ("preserved thinking").
BOUND_THINKING = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"}


class ClaudeModel:
    native_edit_tool = "edit_file"  # exact-string replacement is the edit shape Claude models are used to
    context_window = 1_000_000

    def __init__(
        self,
        name: str = DEFAULT_MODEL,
        *,
        effort: str = "medium",
        max_tokens: int = 64_000,
        client: anthropic.Anthropic | None = None,
    ):
        self.name = name
        self.effort = effort
        # Thinking counts toward max_tokens even when its text isn't returned, so leave room.
        # Streaming keeps a large value safe from HTTP timeouts.
        self.max_tokens = max_tokens
        self.client = client or anthropic.Anthropic(max_retries=4)  # retries 429 and 5xx with backoff

    def request(self, *, system: str, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        """Build the request. Separate from `complete` so tests can check it without a network call."""
        kwargs: dict[str, Any] = {
            "model": self.name,
            "max_tokens": self.max_tokens,
            "system": system,
            # Stream tool inputs as they are generated. The API then doesn't validate them,
            # which is why the harness does (Tool.validate) before running anything.
            "tools": [{**tool, "eager_input_streaming": True} for tool in tools],
            "messages": messages,
            # Cache the stable prefix (tools + system + history so far) on every turn.
            "cache_control": {"type": "ephemeral"},
            # Set explicitly: the default differs by model (medium on Opus 5.5, high on Sonnet 5.5).
            "output_config": {"effort": self.effort},
            # Thinking is always on for current models; ask for readable summaries so traces can show them.
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        betas = []
        if self.name in BOUND_THINKING:
            # Middleware in this lab may rewrite history (the "truncate" strategy does). A reasoning block
            # replayed after such an edit is invalid; drop it instead of failing the request, and report
            # the drop in `input_transformations` so the trace shows it.
            kwargs["thinking"]["block_binding"] = {"prefix_mismatch_behavior": "drop_block"}
            betas.append("thinking-binding-controls-2026-08-01")
        if self.name in FALLBACKS:
            betas.append("server-side-fallback-2026-07-01")
            kwargs["fallbacks"] = "default"
        if betas:
            kwargs["betas"] = betas
        return kwargs

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> Response:
        with self.client.beta.messages.stream(**self.request(system=system, messages=messages, tools=tools)) as stream:
            message = stream.get_final_message()
        usage = message.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        meta: dict[str, Any] = {}
        if message.stop_reason == "refusal":
            meta["stop_details"] = _plain(getattr(message, "stop_details", None))
        dropped = getattr(message, "input_transformations", None)
        if dropped:
            meta["input_transformations"] = [_plain(item) for item in dropped]
        return Response(
            # Every block goes back unchanged on the next request, reasoning blocks included.
            content=[_plain(block) for block in message.content],
            stop_reason=message.stop_reason or "end_turn",
            usage={
                # input_tokens here is the whole window, so traces compare across models.
                "input_tokens": usage.input_tokens + cache_read + cache_write,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            },
            model=message.model,
            meta=meta,
        )

    def cost(self, usage: dict[str, int]) -> float:
        price_in, price_out, price_read = PRICES.get(self.name, PRICES[DEFAULT_MODEL])
        read, write = usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0)
        fresh = usage.get("input_tokens", 0) - read - write
        return (
            fresh * price_in + write * price_in * 1.25 + read * price_read + usage.get("output_tokens", 0) * price_out
        ) / 1e6


def _plain(obj: Any) -> Any:
    """SDK objects -> the same JSON the API sent, so blocks can be stored, counted and sent back as-is."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_unset=True, by_alias=True)
    return obj
