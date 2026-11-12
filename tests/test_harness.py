from agentlab.harness import Agent, Middleware, Response
from agentlab.messages import text, tool_use
from agentlab.models import get_model
from agentlab.tools import ToolError, Workspace, file_tools


class Replay:
    """A model that plays back a fixed list of responses."""

    name, context_window, native_edit_tool = "replay", 100_000, "edit_file"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests = []

    def complete(self, *, system, messages, tools):
        self.requests.append({"system": system, "messages": [*messages], "tools": tools})
        content, stop = self.turns.pop(0)
        return Response(content, stop, {"input_tokens": 10, "output_tokens": 2})

    def cost(self, usage):
        return 0.0


def call(name, **arguments):
    return [tool_use("t1", name, arguments)], "tool_use"


def test_the_loop_runs_tools_and_stops_when_the_model_answers(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    model = Replay(call("read_file", path="a.txt"), ([text("It says hello.")], "end_turn"))
    result = Agent(model=model, tools=file_tools(Workspace(tmp_path))).run("What does a.txt say?")
    assert (result.status, result.answer, result.steps) == ("done", "It says hello.", 2)
    assert result.usage == {"input_tokens": 20, "output_tokens": 4}
    fed_back = model.requests[1]["messages"][-1]["content"][0]
    assert fed_back == {"type": "tool_result", "tool_use_id": "t1", "content": "hello"}


def test_tool_errors_go_back_to_the_model_instead_of_crashing(tmp_path):
    model = Replay(
        call("read_file", path="nope.txt"), call("no_such_tool"), call("read_file", wrong=1), ([text("ok")], "end_turn")
    )
    result = Agent(model=model, tools=file_tools(Workspace(tmp_path))).run("go")
    assert result.status == "done"
    errors = [
        m["content"][0] for m in result.messages if m["role"] == "user" and m["content"][0]["type"] == "tool_result"
    ]
    assert all(e["is_error"] for e in errors)
    assert (
        "no such file" in errors[0]["content"]
        and "unknown tool" in errors[1]["content"]
        and "unknown field" in errors[2]["content"]
    )


def test_the_harness_stops_a_model_that_never_finishes(tmp_path):
    model = Replay(*[call("list_files")] * 5)
    result = Agent(model=model, tools=file_tools(Workspace(tmp_path)), max_steps=3).run("go")
    assert (result.status, result.steps) == ("max_steps", 3)


def test_refusals_and_model_errors_end_the_run_with_a_status(tmp_path):
    refused = Agent(model=Replay(([text("I can't.")], "refusal"))).run("go")
    assert refused.status == "refusal"

    class Broken(Replay):
        def complete(self, **request):
            raise RuntimeError("503")

    assert Agent(model=Broken()).run("go").status == "error"


def test_hooks_fire_in_order_and_wrappers_nest(tmp_path):
    log = []

    class Spy(Middleware):
        def __init__(self, tag):
            self.tag = tag

        def before_agent(self, state):
            log.append(f"{self.tag}:before_agent")

        def before_model(self, state):
            log.append(f"{self.tag}:before_model")

        def wrap_model_call(self, request, call_next, state):
            log.append(f"{self.tag}:model>")
            response = call_next(request)
            log.append(f"{self.tag}:model<")
            return response

        def wrap_tool_call(self, c, call_next, state):
            log.append(f"{self.tag}:tool>")
            return call_next(c)

        def after_agent(self, result, state):
            log.append(f"{self.tag}:after_agent")

    model = Replay(call("list_files"), ([text("done")], "end_turn"))
    Agent(model=model, tools=file_tools(Workspace(tmp_path)), middleware=[Spy("a"), Spy("b")]).run("go")
    assert log[:9] == [
        "a:before_agent",
        "b:before_agent",
        "a:before_model",
        "b:before_model",
        "a:model>",
        "b:model>",
        "b:model<",
        "a:model<",
        "a:tool>",
    ]
    assert log[-2:] == ["a:after_agent", "b:after_agent"]


def test_middleware_can_block_a_tool_and_replace_a_response(tmp_path):
    class Block(Middleware):
        def wrap_tool_call(self, c, call_next, state):
            raise ToolError("not allowed")

        def after_model(self, response, state):
            if response.stop_reason == "end_turn":
                return Response([text("REDACTED")], "end_turn", response.usage)
            return None  # None keeps the response as it is

    model = Replay(call("list_files"), ([text("secret")], "end_turn"))
    result = Agent(model=model, tools=file_tools(Workspace(tmp_path)), middleware=[Block()]).run("go")
    assert result.answer == "REDACTED"
    assert result.messages[2]["content"][0]["content"] == "Error: not allowed"


def test_a_conversation_can_continue_from_history(tmp_path):
    model = Replay(([text("first")], "end_turn"), ([text("second")], "end_turn"))
    agent = Agent(model=model)
    first = agent.run("one")
    second = agent.run("two", history=first.messages)
    assert [m["role"] for m in second.messages] == ["user", "assistant", "user", "assistant"]
    assert model.requests[1]["system"] == model.requests[0]["system"]  # the prefix stays stable


def test_the_scripted_model_is_stateless_and_refuses_oversized_requests(tmp_path):
    model = get_model("scripted-careful")
    request = {
        "system": "s",
        "messages": [{"role": "user", "content": [text("In `c.json`, set `port` to 1.")]}],
        "tools": [],
    }
    assert model.complete(**request).content == model.complete(**request).content
    big = {**request, "system": "x" * 4 * model.context_window}
    try:
        model.complete(**big)
    except Exception as exc:
        assert type(exc).__name__ == "ContextOverflow"
    else:
        raise AssertionError("expected ContextOverflow")
