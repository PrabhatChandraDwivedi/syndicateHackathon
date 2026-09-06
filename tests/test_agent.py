import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from typing import List

from pydantic import BaseModel

from app.harness.tools import ToolRegistry, ToolSpec
from app.agent.loop import (
    ReconciliationAgent,
    parse_action,
    build_system_prompt,
    MAX_STEPS_DEFAULT,
)


class FakeRouter:
    def __init__(self, responses: List[str]):
        self._responses = list(responses)

    def complete(self, prompt: str, max_tokens: int = 1000):
        if not self._responses:
            raise RuntimeError("no more responses")
        text = self._responses.pop(0)
        return {"provider": "fake", "model": "mock", "text": text, "attempts": 1}


class RaisingRouter:
    def complete(self, prompt: str, max_tokens: int = 1000):
        raise RuntimeError("boom")


def test_parse_action_clean_json():
    text = '{"thought": "hello", "tool": "add", "args": {"a": 1, "b": 2}, "done": false}'
    res = parse_action(text)
    assert res["thought"] == "hello"
    assert res["tool"] == "add"
    assert res["args"] == {"a": 1, "b": 2}
    assert res["done"] is False
    assert "parse_error" not in res


def test_parse_action_wrapped_json_prose():
    text = "Some prose before\n```json\n{\"thought\": \"call\", \"tool\": \"add\", \"args\": {\"a\": 1, \"b\": 2}, \"done\": false}\n```\nAfterwards"
    res = parse_action(text)
    assert res["tool"] == "add"
    assert res["args"] == {"a": 1, "b": 2}
    assert res["done"] is False


def test_parse_action_garbage():
    text = "not json at all"
    res = parse_action(text)
    assert "parse_error" in res


def test_build_system_prompt_contains_text():
    registry = ToolRegistry()
    class SimpleArgs(BaseModel):
        x: int
    def f(v: SimpleArgs):
        return {"ok": True}
    registry.register(ToolSpec(name="simple", description="a simple tool", args_model=SimpleArgs, fn=f, dangerous=False))

    prompt = build_system_prompt(registry, "do something")
    assert "You are a reconciliation agent" in prompt
    assert "Goal: do something" in prompt
    assert "simple" in prompt  # tool name should appear in the registry.describe() part


def test_agent_done_on_first_response():
    registry = ToolRegistry()

    class DoArgs(BaseModel):
        x: int

    def do_fn(v: DoArgs):
        return {"value": v.x}

    registry.register(ToolSpec(name="do", description="do something", args_model=DoArgs, fn=do_fn, dangerous=False))

    router = FakeRouter(['{"thought": "done", "done": true, "summary": "finished"}'])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("complete immediately")

    assert res["completed"] is True
    assert res["stopped_reason"] == "done"
    assert res["step_count"] == 1
    assert res["tool_calls"] == 0
    first_step = res["steps"][0]
    assert first_step["tool"] is None
    assert first_step["observation"] is None


def test_agent_calls_tool_and_finish():
    registry = ToolRegistry()

    class AddArgs(BaseModel):
        a: int
        b: int

    def add_fn(v: AddArgs):
        return {"sum": v.a + v.b}

    registry.register(ToolSpec(name="add", description="add numbers", args_model=AddArgs, fn=add_fn, dangerous=False))

    first = '{"thought": "call tool", "tool": "add", "args": {"a": 1, "b": 2}, "done": false}'
    second = '{"thought": "done", "done": true, "summary": "finished"}'
    router = FakeRouter([first, second])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("sum 1 and 2")

    assert res["completed"] is True
    assert res["stopped_reason"] == "done"
    assert res["step_count"] == 2
    assert res["tool_calls"] == 1
    first_step = res["steps"][0]
    assert first_step["tool"] == "add"
    assert first_step["args"] == {"a": 1, "b": 2}
    assert first_step["observation"] == {"sum": 3}


def test_failing_tool_call_does_not_end_run():
    registry = ToolRegistry()

    class AddArgs(BaseModel):
        a: int
        b: int

    def fail_fn(v: AddArgs):
        raise ValueError("boom")

    registry.register(ToolSpec(name="add", description="add numbers", args_model=AddArgs, fn=fail_fn, dangerous=False))

    first = '{"thought": "call tool", "tool": "add", "args": {"a": 0, "b": 0}, "done": false}'
    second = '{"thought": "done", "done": true, "summary": "finished"}'
    router = FakeRouter([first, second])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("try failing tool")

    assert res["completed"] is True
    assert res["stopped_reason"] == "done"
    assert res["step_count"] == 2
    assert res["tool_calls"] == 1
    first_step = res["steps"][0]
    assert first_step["tool"] == "add"
    assert first_step["error"] is not None or first_step["observation"] is None


def test_invalid_arguments_rejected_by_registry():
    registry = ToolRegistry()

    class AddArgs(BaseModel):
        a: int
        b: int

    def add_fn(v: AddArgs):
        return {"sum": v.a + v.b}

    registry.register(ToolSpec(name="add", description="add numbers", args_model=AddArgs, fn=add_fn, dangerous=False))

    # Missing required field 'b'
    first = '{"thought": "call tool", "tool": "add", "args": {"a": 1}, "done": false}'
    second = '{"thought": "done", "done": true, "summary": "finished"}'
    router = FakeRouter([first, second])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("invalid args")

    assert res["completed"] is True  # finishes due to the done signal from router
    first_step = res["steps"][0]
    assert first_step["tool"] == "add"
    assert first_step["error"] is not None or first_step["observation"] is None


def test_max_steps_stops():
    registry = ToolRegistry()

    class SimpleArgs(BaseModel):
        v: int

    def f(v: SimpleArgs):
        return {"ok": True}

    registry.register(ToolSpec(name="simple", description="desc", args_model=SimpleArgs, fn=f, dangerous=False))

    # No termination signal; just two responses to exhaust steps
    first = '{"thought": "call tool", "tool": "simple", "args": {"v": 1}, "done": false}'
    second = '{"thought": "continue", "done": false}'
    # We won't provide a "done" response, forcing max_steps termination
    router = FakeRouter([first, second])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=2)
    res = agent.run("hit max steps")

    assert res["completed"] is False
    assert res["stopped_reason"] == "max_steps"


def test_router_error_stops():
    registry = ToolRegistry()
    router = RaisingRouter()
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("boom test")
    assert res["completed"] is False
    assert res["stopped_reason"] == "router_error"


def test_router_none_returns_no_router():
    registry = ToolRegistry()
    agent = ReconciliationAgent(registry=registry, router=None, max_steps=5)
    res = agent.run("no router present")
    assert res["completed"] is False
    assert res["stopped_reason"] == "no_router"
    assert res["step_count"] == 0


def test_unknown_tool_in_prompt():
    class AddArgsLocal(BaseModel):
        a: int
        b: int

    def add_fn(v: AddArgsLocal):
        return {"sum": v.a + v.b}

    registry = ToolRegistry()
    registry.register(ToolSpec(name="add", description="add numbers", args_model=AddArgsLocal, fn=add_fn, dangerous=False))

    first = '{"thought": "call unknown", "tool": "not_a_tool", "args": {"a": 1, "b": 2}, "done": False}'
    second = '{"thought": "done", "done": true, "summary": "finished"}'
    router = FakeRouter([first, second])
    agent = ReconciliationAgent(registry=registry, router=router, max_steps=5)
    res = agent.run("unknown tool test")

    assert res["completed"] is True
    assert res["stopped_reason"] == "done"
    assert res["step_count"] == 2
    first_step = res["steps"][0]
    assert first_step["tool"] == "not_a_tool"
    assert first_step["observation"]["error"] == "unknown tool: not_a_tool"
