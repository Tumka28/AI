import json
from types import SimpleNamespace

import pytest

from bot_v.config import load_settings
from bot_v.teacher import load_teacher
from bot_v.teacher.base import TeacherError, review_from_dict
from bot_v.teacher.claude import ClaudeTeacher
from bot_v.teacher.llm_teacher import LLMTeacher


# ------------------------------------------------------------ fake Claude
def text_response(text, stop="end_turn", model="claude-opus-5-5", details=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        stop_details=details,
        model=model,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )


class FakeAnthropic:
    def __init__(self, *responses, exc=None):
        self.responses = list(responses)
        self.exc = exc
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.responses.pop(0)


def test_claude_answer_request_shape():
    client = FakeAnthropic(text_response("Ulaanbaatar"))
    answer = ClaudeTeacher(client=client).answer("Capital of Mongolia?")
    assert answer.text == "Ulaanbaatar"
    assert answer.model == "claude-opus-5-5" and answer.provider == "claude"
    assert answer.usage == {"input_tokens": 11, "output_tokens": 7}
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == 16000
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {"effort": "high"}
    assert call["messages"] == [{"role": "user", "content": "Capital of Mongolia?"}]
    assert "temperature" not in call


def test_claude_records_the_model_that_served_a_fallback():
    client = FakeAnthropic(text_response("ok", model="claude-opus-4-8"))
    assert ClaudeTeacher(client=client).answer("q").model == "claude-opus-4-8"


def test_claude_refusal_raises():
    details = SimpleNamespace(category="cyber")
    client = FakeAnthropic(text_response("", stop="refusal", details=details))
    with pytest.raises(TeacherError, match="cyber"):
        ClaudeTeacher(client=client).answer("q")


def test_claude_truncated_answer_is_flagged():
    client = FakeAnthropic(text_response("partial", stop="max_tokens"))
    assert ClaudeTeacher(client=client).answer("q").truncated is True


def test_claude_haiku_has_no_fallbacks():
    client = FakeAnthropic(text_response("ok"))
    ClaudeTeacher(client=client, model="claude-haiku-5-5").answer("q")
    assert "fallbacks" not in client.calls[0] and "betas" not in client.calls[0]


def test_claude_review_uses_json_schema():
    payload = {"score": 3, "verdict": "wrong", "problems": ["wrong city"], "improved_answer": "Ulaanbaatar"}
    client = FakeAnthropic(text_response(json.dumps(payload)))
    review = ClaudeTeacher(client=client, effort="max").review("Capital?", "Darkhan")
    assert (review.score, review.verdict, review.improved_answer) == (3, "wrong", "Ulaanbaatar")
    fmt = client.calls[0]["output_config"]
    assert fmt["effort"] == "max"
    assert fmt["format"]["type"] == "json_schema"
    assert fmt["format"]["schema"]["required"] == ["score", "verdict", "problems", "improved_answer"]
    assert "Darkhan" in client.calls[0]["messages"][0]["content"]


def test_claude_review_rejects_bad_json():
    client = FakeAnthropic(text_response("not json"))
    with pytest.raises(TeacherError):
        ClaudeTeacher(client=client).review("q", "a")


def test_claude_sdk_errors_become_teacher_errors():
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    cases = [
        (anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None),
         "credentials"),
        (anthropic.RateLimitError("slow", response=httpx.Response(429, request=request), body=None),
         "rate limit"),
        (anthropic.NotFoundError("nope", response=httpx.Response(404, request=request), body=None),
         "not found"),
        (anthropic.APIConnectionError(request=request), "cannot reach"),
        (TypeError("Could not resolve authentication method."), "no Claude credentials"),
    ]
    for exc, expected in cases:
        with pytest.raises(TeacherError, match=expected):
            ClaudeTeacher(client=FakeAnthropic(exc=exc)).answer("q")


# --------------------------------------------------------------- reviews
def test_review_from_dict_validates_and_clamps():
    r = review_from_dict({"score": 42, "verdict": "GOOD", "problems": "x", "improved_answer": "a"}, "p", "m")
    assert (r.score, r.verdict, r.problems) == (10, "good", ["x"])
    with pytest.raises(TeacherError):
        review_from_dict({"score": 5, "verdict": "meh", "improved_answer": "a"}, "p", "m")
    with pytest.raises(TeacherError):
        review_from_dict(["not", "a", "dict"], "p", "m")


# ----------------------------------------------------------- LLM teacher
class FakeChatClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, model, messages):
        self.calls.append((model, messages))
        return self.reply


def test_llm_teacher_answer_and_review():
    client = FakeChatClient("big model answer")
    teacher = LLMTeacher("ollama", "http://x", "qwen-72b", client=client)
    assert teacher.answer("q").text == "big model answer"
    assert client.calls[0][0] == "teacher"
    assert client.calls[0][1][0]["role"] == "system"

    client.reply = 'Here you go:\n```json\n{"score": 9, "verdict": "good", "problems": [], "improved_answer": "a"}\n```'
    review = teacher.review("q", "a")
    assert review.verdict == "good" and review.provider == "ollama"


def test_llm_teacher_needs_a_model():
    with pytest.raises(ValueError):
        LLMTeacher("openai", "http://x", "")


# ------------------------------------------------------------- settings
def test_load_teacher_from_settings():
    assert load_teacher(load_settings({})) is None

    claude = load_teacher(load_settings({"BOTV_TEACHER": "claude"}))
    assert isinstance(claude, ClaudeTeacher) and claude.model == "claude-opus-5-5"
    assert claude.effort == "high"

    big = load_teacher(load_settings({"BOTV_TEACHER": "ollama", "BOTV_TEACHER_MODEL": "qwen-72b"}))
    assert isinstance(big, LLMTeacher) and big.client.host == "http://localhost:11434"

    with pytest.raises(ValueError):
        load_settings({"BOTV_TEACHER": "gpt"})
    with pytest.raises(ValueError):
        load_settings({"BOTV_TEACHER_MODE": "always"})
    with pytest.raises(ValueError):
        load_settings({"BOTV_TEACHER_EFFORT": "extreme"})
