"""The Claude adapter, checked without a network call: the request it builds and how it reads a response."""

from contextlib import contextmanager

from anthropic.types.beta import BetaMessage

from agentlab.models import get_model, is_live
from agentlab.models.claude import ClaudeModel

TOOLS = [{"name": "read_file", "description": "Read", "input_schema": {"type": "object", "properties": {}}}]
MESSAGES = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


class FakeClient:
    """Stands in for anthropic.Anthropic: records the request and returns a canned message."""

    def __init__(self, message):
        self.message, self.sent = message, None
        self.beta = self.messages = self

    @contextmanager
    def stream(self, **kwargs):
        self.sent = kwargs
        yield self

    def get_final_message(self):
        return self.message


def message(**overrides):
    body = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "content": [
            {"type": "thinking", "thinking": "plan", "signature": "sig=="},
            {"type": "text", "text": "Reading."},
            {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.txt"}},
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 20,
        },
    }
    return BetaMessage.model_validate({**body, **overrides})


def test_the_default_request():
    request = ClaudeModel(client=FakeClient(None)).request(system="sys", messages=MESSAGES, tools=TOOLS)
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "medium"}
    assert request["thinking"] == {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert request["fallbacks"] == "default"
    assert set(request["betas"]) == {"thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"}
    assert request["cache_control"] == {"type": "ephemeral"}
    assert request["tools"][0]["eager_input_streaming"] is True
    assert "temperature" not in request and "tool_choice" not in request


def test_haiku_gets_no_server_side_fallback():
    request = ClaudeModel("claude-haiku-5-5", client=FakeClient(None)).request(system="s", messages=MESSAGES, tools=[])
    assert "fallbacks" not in request and request["betas"] == ["thinking-binding-controls-2026-08-01"]


def test_a_response_becomes_plain_blocks_that_can_be_sent_back():
    client = FakeClient(message())
    model = ClaudeModel(client=client)
    response = model.complete(system="sys", messages=MESSAGES, tools=TOOLS)
    assert client.sent["messages"] == MESSAGES
    assert response.stop_reason == "tool_use"
    assert response.content == [
        {"type": "thinking", "thinking": "plan", "signature": "sig=="},  # must go back unchanged
        {"type": "text", "text": "Reading."},
        {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.txt"}},
    ]
    assert response.usage == {
        "input_tokens": 130,
        "output_tokens": 5,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 20,
    }
    # 10 fresh x $4 + 20 written x $5 + 100 read x $0.20 + 5 out x $20, per million tokens
    assert abs(model.cost(response.usage) - (10 * 4 + 20 * 5 + 100 * 0.2 + 5 * 20) / 1e6) < 1e-12


def test_refusals_and_dropped_reasoning_blocks_are_reported():
    refusal = message(
        stop_reason="refusal", content=[], stop_details={"type": "refusal", "category": "cyber", "explanation": "x"}
    )
    response = ClaudeModel(client=FakeClient(refusal)).complete(system="s", messages=MESSAGES, tools=[])
    assert response.stop_reason == "refusal" and response.meta["stop_details"]["category"] == "cyber"

    dropped = message(
        input_transformations=[
            {"type": "thinking_dropped", "path": "messages.1.content.0", "reason": "prefix_binding_mismatch"}
        ]
    )
    response = ClaudeModel(client=FakeClient(dropped)).complete(system="s", messages=MESSAGES, tools=[])
    assert response.meta["input_transformations"][0]["reason"] == "prefix_binding_mismatch"


def test_only_claude_models_cost_money():
    assert not is_live("scripted-careful") and is_live("claude") and is_live("claude-haiku-5-5")
    assert get_model("scripted-fast").name == "scripted-fast"
