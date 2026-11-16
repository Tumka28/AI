import pytest

from bot_v.core.brain import BotV
from bot_v.core.permissions import PermissionGate
from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter
from bot_v.memory.experience_log import ExperienceLog

from fakes import FailingLLM, FakeJarvis, FakeLLM


def make_bot(tmp_path, llm=None, jarvis=None, approver=None, installed=True):
    jarvis = jarvis or FakeJarvis()
    adapter = OpenJarvisAdapter(jarvis_factory=lambda: jarvis)
    if not installed:
        adapter.is_installed = lambda: False
    bot = BotV(
        llm=llm or FakeLLM(),
        openjarvis=adapter,
        gate=PermissionGate(approver=approver),
        log=ExperienceLog(tmp_path / "exp.jsonl"),
    )
    return bot, jarvis


# ----------------------------------------------------------- permission gate
def test_gate_allows_read_only_tools():
    d = PermissionGate().check("t", ["calculator", "web_search"])
    assert d.allowed and d.denied == []


def test_gate_denies_risky_and_unknown_tools_without_approver():
    d = PermissionGate().check("t", ["calculator", "shell_exec", "made_up_tool"])
    assert not d.allowed
    assert d.denied == ["shell_exec", "made_up_tool"]


def test_gate_asks_approver_only_about_risky_tools():
    seen = []
    gate = PermissionGate(approver=lambda task, tools: seen.append((task, tools)) or True)
    d = gate.check("do it", ["calculator", "file_write"])
    assert d.allowed and d.approved == ["file_write"]
    assert seen == [("do it", ["file_write"])]


def test_gate_treats_approver_crash_as_no():
    def boom(task, tools):
        raise RuntimeError("ui closed")

    d = PermissionGate(approver=boom).check("t", ["shell_exec"])
    assert not d.allowed and "approver failed" in d.reason


# ------------------------------------------------------------------- Bot V
def test_chat_uses_local_model_and_logs(tmp_path):
    bot, _ = make_bot(tmp_path)
    out = bot.handle("hi", backend="local")
    assert out == {"status": "ok", "backend": "local", "reply": "local reply"}
    assert bot.log.tail(1)[0]["kind"] == "chat"


def test_delegate_runs_on_openjarvis(tmp_path):
    bot, jarvis = make_bot(tmp_path)
    out = bot.delegate("2+3?", tools=["calculator"])
    assert out["status"] == "ok"
    assert out["reply"] == "oj: 2+3?"
    assert out["result"]["agent"] == "orchestrator"
    entry = bot.log.tail(1)[0]
    assert entry["backend"] == "openjarvis" and entry["status"] == "ok"


def test_delegate_blocks_risky_tool_before_openjarvis_sees_it(tmp_path):
    bot, jarvis = make_bot(tmp_path)
    out = bot.delegate("rm -rf", tools=["shell_exec"])
    assert out["status"] == "denied"
    assert out["denied"] == ["shell_exec"]
    assert jarvis.calls == []  # OpenJarvis was never called
    assert bot.log.tail(1)[0]["status"] == "denied"


def test_delegate_with_approval(tmp_path):
    bot, jarvis = make_bot(tmp_path, approver=lambda task, tools: True)
    out = bot.delegate("write file", tools=["file_write"])
    assert out["status"] == "ok"
    assert bot.log.tail(1)[0]["approved"] == ["file_write"]


def test_delegate_reports_openjarvis_errors(tmp_path):
    bot, _ = make_bot(tmp_path, jarvis=FakeJarvis(raise_exc=RuntimeError("no engine")))
    out = bot.delegate("x")
    assert out["status"] == "error" and "no engine" in out["reply"]


def test_auto_falls_back_to_openjarvis_when_local_model_fails(tmp_path):
    bot, jarvis = make_bot(tmp_path, llm=FailingLLM())
    out = bot.handle("hello")
    assert out["status"] == "ok"
    assert out["backend"] == "openjarvis"
    assert out["fallback_from"] == "local"
    assert len(jarvis.calls) == 1


def test_auto_without_openjarvis_returns_local_error(tmp_path):
    bot, jarvis = make_bot(tmp_path, llm=FailingLLM(), installed=False)
    out = bot.handle("hello")
    assert out["status"] == "error" and out["backend"] == "local"
    assert jarvis.calls == []


def test_unknown_backend_rejected(tmp_path):
    bot, _ = make_bot(tmp_path)
    with pytest.raises(ValueError):
        bot.handle("x", backend="cloud")
