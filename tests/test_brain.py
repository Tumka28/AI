import pytest

from bot_v.core.brain import BotV
from bot_v.core.permissions import PermissionGate
from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter
from bot_v.memory.experience_log import ExperienceLog

from bot_v.learning.dataset import TrainingStore
from bot_v.skills.library import SkillLibrary
from bot_v.teacher.base import TeacherReview

from bot_v.tools.native import register_native_tools
from bot_v.tools.registry import Tool, ToolRegistry

from fakes import FailingLLM, FakeJarvis, FakeLLM, FakeTeacher, ScriptedLLM, write_skill


def home_tools():
    reg = ToolRegistry()
    register_native_tools(reg)
    switched = []
    reg.register(Tool(
        name="lamp_on", description="Turn on a lamp.",
        input_schema={"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]},
        handler=lambda a: switched.append(a["entity_id"]) or {"on": a["entity_id"]},
        source="homeassistant", risk="write", keywords=("гэрэл", "гэрл", "lamp"), auto=True,
    ))
    return reg, switched


def make_bot(tmp_path, llm=None, jarvis=None, approver=None, installed=True,
             teacher=None, mode="fallback", skills=None, tools=None):
    jarvis = jarvis or FakeJarvis()
    adapter = OpenJarvisAdapter(jarvis_factory=lambda: jarvis)
    if not installed:
        adapter.is_installed = lambda: False
    bot = BotV(
        llm=llm or FakeLLM(),
        openjarvis=adapter,
        gate=PermissionGate(approver=approver),
        log=ExperienceLog(tmp_path / "exp.jsonl"),
        teacher=teacher,
        teacher_mode=mode,
        training=TrainingStore(tmp_path / "train.jsonl"),
        skills=skills or SkillLibrary(root=tmp_path / "skills"),
        tools=tools,
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


# ----------------------------------------------------------------- teacher
def review(score, verdict, improved="better answer"):
    return TeacherReview(score, verdict, [] if verdict == "good" else ["issue"], improved, "fake", "fake-teacher")


def test_teacher_answers_when_local_fails_before_openjarvis(tmp_path):
    teacher = FakeTeacher()
    bot, jarvis = make_bot(tmp_path, llm=FailingLLM(), teacher=teacher)
    out = bot.handle("Нийслэл?")
    assert out["backend"] == "teacher" and out["reply"] == "teacher answer"
    assert out["fallback_from"] == "local" and out["learned"] is True
    assert jarvis.calls == []  # teacher handled it
    [example] = list(bot.training)
    assert (example["prompt"], example["answer"], example["source"]) == ("Нийслэл?", "teacher answer", "teacher_answer")


def test_openjarvis_is_next_when_teacher_fails(tmp_path):
    bot, jarvis = make_bot(tmp_path, llm=FailingLLM(), teacher=FakeTeacher(error="no key"))
    out = bot.handle("hello")
    assert out["backend"] == "openjarvis" and out["status"] == "ok"
    assert len(jarvis.calls) == 1
    assert bot.training.stats()["total"] == 0


def test_manual_mode_never_calls_teacher_automatically(tmp_path):
    teacher = FakeTeacher()
    bot, _ = make_bot(tmp_path, llm=FailingLLM(), teacher=teacher, mode="manual")
    assert bot.handle("hello")["backend"] == "openjarvis"
    assert teacher.answer_calls == []
    assert bot.handle("hello", backend="teacher")["backend"] == "teacher"


def test_ask_teacher_without_teacher(tmp_path):
    bot, _ = make_bot(tmp_path)
    out = bot.handle("q", backend="teacher")
    assert out["status"] == "unavailable" and "BOTV_TEACHER" in out["reply"]


def test_truncated_teacher_answer_is_not_learned(tmp_path):
    bot, _ = make_bot(tmp_path, teacher=FakeTeacher(truncated=True))
    out = bot.handle("q", backend="teacher")
    assert out["status"] == "ok" and out["learned"] is False
    assert bot.training.stats()["total"] == 0


def test_review_mode_keeps_good_local_answer(tmp_path):
    teacher = FakeTeacher(review=review(9, "good", improved="same"))
    bot, _ = make_bot(tmp_path, teacher=teacher, mode="review")
    out = bot.handle("hi")
    assert out["backend"] == "local" and out["reply"] == "local reply"
    assert out["review"]["score"] == 9
    assert teacher.review_calls == [("hi", "local reply")]
    assert list(bot.training)[0]["source"] == "local_verified"


def test_review_mode_replaces_weak_local_answer(tmp_path):
    teacher = FakeTeacher(review=review(3, "wrong", improved="correct answer"))
    bot, _ = make_bot(tmp_path, teacher=teacher, mode="review")
    out = bot.handle("2+2?")
    assert out["backend"] == "teacher" and out["reply"] == "correct answer"
    assert out["local_reply"] == "local reply"
    [example] = list(bot.training)
    assert example["source"] == "teacher_correction" and example["rejected"] == "local reply"


def test_review_failure_falls_back_to_local_answer(tmp_path):
    bot, _ = make_bot(tmp_path, teacher=FakeTeacher(error="rate limited"), mode="review")
    out = bot.handle("hi")
    assert out["reply"] == "local reply" and "rate limited" in out["review_error"]


# ------------------------------------------------------------------ skills
def installed_skills(tmp_path):
    src = tmp_path / "src"
    write_skill(src, "pdf-merge", "Merge several PDF files into one document.", body="Use pypdf to merge.")
    lib = SkillLibrary(root=tmp_path / "skills")
    lib.fetch(str(src))
    lib.approve("pdf-merge")
    return lib


def test_chat_uses_relevant_skill(tmp_path):
    llm = FakeLLM()
    bot, _ = make_bot(tmp_path, llm=llm, skills=installed_skills(tmp_path))
    out = bot.handle("merge these pdf files please", backend="local")
    assert out["skills"] == ["pdf-merge"]
    assert "Use pypdf to merge." in llm.calls[0]["system"]

    bot.handle("hello", backend="local")
    assert "pdf-merge" not in llm.calls[1]["system"]


def test_review_keeps_skill_names_when_teacher_corrects(tmp_path):
    teacher = FakeTeacher(review=review(2, "wrong", improved="fixed"))
    bot, _ = make_bot(tmp_path, teacher=teacher, mode="review", skills=installed_skills(tmp_path))
    out = bot.handle("merge these pdf files please")
    assert out["backend"] == "teacher" and out["skills"] == ["pdf-merge"]


def test_delegate_passes_skill_instructions_to_openjarvis(tmp_path):
    bot, jarvis = make_bot(tmp_path, skills=installed_skills(tmp_path))
    out = bot.delegate("merge these pdf files please")
    assert out["skills"] == ["pdf-merge"]
    sent = jarvis.calls[0]["query"]
    assert "Use pypdf to merge." in sent and "<task>\nmerge these pdf files please\n</task>" in sent
    assert bot.log.tail(1)[0]["input"] == "merge these pdf files please"


# ------------------------------------------------------------------- tools
def test_home_request_goes_to_tools_and_waits_for_approval(tmp_path):
    reg, switched = home_tools()
    llm = ScriptedLLM('{"tool": "lamp_on", "args": {"entity_id": "light.kitchen"}}')
    bot, jarvis = make_bot(tmp_path, llm=llm, tools=reg)
    out = bot.handle("гал тогооны гэрлийг асаа")  # auto mode
    assert out["backend"] == "tools" and out["status"] == "needs_approval"
    assert switched == [] and llm.calls == []  # no plain chat, nothing switched yet

    done = bot.approve_action(out["action"]["id"])
    assert done["status"] == "ok" and switched == ["light.kitchen"]
    kinds = [e["kind"] for e in bot.log.tail(5)]
    assert kinds[-2:] == ["tools", "action"]


def test_denied_action_does_nothing(tmp_path):
    reg, switched = home_tools()
    bot, _ = make_bot(tmp_path, llm=ScriptedLLM('{"tool": "lamp_on", "args": {"entity_id": "light.a"}}'), tools=reg)
    action = bot.handle("гэрэл асаа", backend="tools")["action"]
    assert bot.deny_action(action["id"])["status"] == "denied"
    assert bot.approve_action(action["id"])["status"] == "error"
    assert switched == []


def test_non_home_requests_stay_in_chat(tmp_path):
    reg, _ = home_tools()
    llm = ScriptedLLM()
    bot, _ = make_bot(tmp_path, llm=llm, tools=reg)
    assert bot.handle("Монголын нийслэл?")["backend"] == "local"
    assert llm.chats == []


def test_tools_backend_answers_with_native_tool(tmp_path):
    reg, _ = home_tools()
    llm = ScriptedLLM('{"tool": "calculate", "args": {"expression": "2+2*10"}}', '{"answer": "22"}')
    bot, _ = make_bot(tmp_path, llm=llm, tools=reg)
    out = bot.handle("please calculate 2+2*10", backend="tools")
    assert out["reply"] == "22" and out["steps"][0]["tool"] == "calculate"
    assert "calculate" in llm.chats[0][0]["content"]


def test_status_reports_teacher_skills_and_learning(tmp_path):
    bot, _ = make_bot(tmp_path, teacher=FakeTeacher(), mode="review", skills=installed_skills(tmp_path))
    status = bot.status()
    assert status["teacher"] == {"provider": "fake", "model": "fake-teacher", "mode": "review"}
    assert status["skills"]["installed"] == ["pdf-merge"]
    assert status["learning"]["total"] == 0
