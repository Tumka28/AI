import json
import time

import pytest

from bot_v.core.tool_agent import ToolAgent, tools_prompt
from bot_v.llm.client import LLMError
from bot_v.tools import registry as registry_module
from bot_v.tools.native import register_native_tools, safe_eval
from bot_v.tools.registry import Tool, ToolRegistry, validate_args

from fakes import ScriptedLLM


def make_registry(approver=None):
    reg = ToolRegistry(approver=approver)
    register_native_tools(reg)
    calls = []

    def lamp(args):
        calls.append(args)
        return {"lamp": args["entity_id"], "on": True}

    reg.register(Tool(
        name="lamp_on", description="Turn on a lamp in the house.",
        input_schema={"type": "object", "properties": {"entity_id": {"type": "string"}},
                      "required": ["entity_id"], "additionalProperties": False},
        handler=lamp, source="test", risk="write", keywords=("гэрэл", "lamp"), auto=True,
    ))
    reg.register(Tool(
        name="door", description="Open the front door.", input_schema={"type": "object"},
        handler=lambda a: "opened", source="test", classify=lambda a: "blocked",
    ))
    return reg, calls


# --------------------------------------------------------------- registry
def test_read_tools_run_immediately():
    reg, _ = make_registry()
    out = reg.call("calculate", {"expression": "(12.5*4)/2"})
    assert out["status"] == "ok" and out["result"]["value"] == 25
    assert out["elapsed_ms"] >= 0


def test_write_tools_wait_for_approval():
    reg, calls = make_registry()
    out = reg.call("lamp_on", {"entity_id": "light.kitchen"}, task="turn on the kitchen light")
    assert out["status"] == "needs_approval" and calls == []
    action = out["action"]
    assert reg.pending()[0]["id"] == action["id"]

    done = reg.approve(action["id"])
    assert done["status"] == "ok" and done["result"]["on"] is True
    assert calls == [{"entity_id": "light.kitchen"}]
    assert reg.pending() == []
    assert reg.approve(action["id"])["status"] == "error"  # one approval runs once


def test_deny_and_expiry(monkeypatch):
    reg, calls = make_registry()
    a = reg.call("lamp_on", {"entity_id": "light.a"})["action"]
    assert reg.deny(a["id"])["status"] == "denied"
    b = reg.call("lamp_on", {"entity_id": "light.b"})["action"]
    real_time = time.time
    monkeypatch.setattr(registry_module.time, "time", lambda: real_time() + 3600)
    assert reg.pending() == []
    assert reg.approve(b["id"])["status"] == "error"
    assert calls == []


def test_approver_callback():
    seen = []
    reg, calls = make_registry(approver=lambda task, tools: seen.append(tools) or True)
    assert reg.call("lamp_on", {"entity_id": "light.x"})["status"] == "ok"
    assert seen == [["lamp_on"]] and len(calls) == 1

    reg_no, calls_no = make_registry(approver=lambda task, tools: False)
    assert reg_no.call("lamp_on", {"entity_id": "light.x"})["status"] == "denied"
    assert calls_no == []


def test_blocked_and_invalid_and_unknown():
    reg, _ = make_registry(approver=lambda task, tools: True)
    assert reg.call("door", {})["status"] == "denied"  # approval cannot unblock
    assert reg.call("lamp_on", {})["status"] == "invalid_args"
    assert reg.call("lamp_on", {"entity_id": "x", "extra": 1})["status"] == "invalid_args"
    assert reg.call("lamp_on", "not a dict")["status"] == "invalid_args"
    assert reg.call("nope", {})["status"] == "error"


def test_handler_errors_are_returned():
    reg, _ = make_registry()
    out = reg.call("calculate", {"expression": "1/0"})
    assert out["status"] == "error" and "ZeroDivisionError" in out["error"]


def test_relevance_and_keywords():
    reg, _ = make_registry()
    assert [t.name for t in reg.relevant("гэрлээ асаагаадах", auto_only=True)] == []  # stem "гэрэл" differs
    assert [t.name for t in reg.relevant("гэрэл асаа", auto_only=True)] == ["lamp_on"]
    assert [t.name for t in reg.relevant("turn on the lamp please", auto_only=True)] == ["lamp_on"]
    assert reg.relevant("that was a lampoon", auto_only=True) == []  # whole words for English
    assert reg.relevant("please calculate 2+2")[0].name == "calculate"


def test_describe_has_latency_stats():
    reg, _ = make_registry()
    reg.call("calculate", {"expression": "1+1"})
    info = {d["name"]: d for d in reg.describe()}
    assert info["calculate"]["calls"] == 1 and info["calculate"]["avg_ms"] is not None
    assert info["door"]["risk"] == "per call"


def test_duplicate_and_bad_names():
    reg, _ = make_registry()
    with pytest.raises(ValueError):
        reg.register(Tool("calculate", "dup", {}, lambda a: 1))
    with pytest.raises(ValueError):
        reg.register(Tool("bad name!", "x", {}, lambda a: 1))


def test_validate_args_subset():
    schema = {"type": "object", "required": ["n"], "properties": {
        "n": {"type": "integer"}, "mode": {"type": "string", "enum": ["a", "b"]},
        "tags": {"type": "array", "items": {"type": "string"}}}}
    assert validate_args(schema, {"n": 1, "mode": "a", "tags": ["x"]}) == []
    assert validate_args(schema, {"n": True}) != []  # bool is not an integer
    assert validate_args(schema, {"n": 1, "mode": "c"}) != []
    assert validate_args(schema, {"n": 1, "tags": [1]}) != []


# ------------------------------------------------------------ native tools
def test_safe_eval():
    assert safe_eval("2^10") == 1024
    assert safe_eval("sqrt(16) + pi") == pytest.approx(4 + 3.14159, rel=1e-4)
    for bad in ("__import__('os')", "open('x')", "9**999999", "(10**100)**100", "a+1", "x" * 300):
        with pytest.raises(ValueError):
            safe_eval(bad)


def test_now_tool():
    reg, _ = make_registry()
    result = reg.call("now", {})["result"]
    assert set(result) >= {"iso", "date", "time", "weekday"}


# --------------------------------------------------------------- tool loop
def test_tool_loop_calls_tool_then_answers():
    reg, _ = make_registry()
    llm = ScriptedLLM('{"tool": "calculate", "args": {"expression": "6*7"}}', '{"answer": "Хариу: 42"}')
    out = ToolAgent(llm, reg).run("6*7 хэд вэ?", [reg.get("calculate")])
    assert out == {"status": "ok", "reply": "Хариу: 42",
                   "steps": [{"tool": "calculate", "args": {"expression": "6*7"}, "status": "ok",
                              "elapsed_ms": out["steps"][0]["elapsed_ms"]}]}
    system = llm.chats[0][0]["content"]
    assert "calculate {expression: string}" in system and "lamp_on" not in system  # only given tools
    assert '"value": 42' in llm.chats[1][-1]["content"]


def test_tool_loop_stops_for_approval():
    reg, calls = make_registry()
    llm = ScriptedLLM('```json\n{"tool": "lamp_on", "args": {"entity_id": "light.kitchen"}}\n```')
    out = ToolAgent(llm, reg).run("гэрэл асаа", [reg.get("lamp_on")])
    assert out["status"] == "needs_approval" and out["action"]["tool"] == "lamp_on"
    assert calls == []


def test_tool_loop_handles_unknown_tools_and_plain_text():
    reg, _ = make_registry()
    llm = ScriptedLLM('{"tool": "door", "args": {}}', "Just a normal sentence.")
    out = ToolAgent(llm, reg).run("open the door", [reg.get("calculate")])
    assert out["reply"] == "Just a normal sentence." and out["steps"] == []
    assert "Unknown tool" in llm.chats[1][-1]["content"]


def test_tool_loop_step_limit_and_llm_error():
    reg, _ = make_registry()
    llm = ScriptedLLM(*['{"tool": "now", "args": {}}'] * 10)
    out = ToolAgent(llm, reg, max_steps=3).run("time?", [reg.get("now")])
    assert len(out["steps"]) == 3 and "too many" in out["reply"]

    class Broken:
        def chat(self, model, messages):
            raise LLMError("down")

    assert ToolAgent(Broken(), reg).run("x", [reg.get("now")])["status"] == "error"


def test_tools_prompt_is_compact():
    reg, _ = make_registry()
    prompt = tools_prompt(reg.list())
    assert len(prompt) < 2000
    assert json.loads('{"tool": "x"}')  # the format shown is valid JSON
    assert '{"tool": "<tool name>", "args": {...}}' in prompt
