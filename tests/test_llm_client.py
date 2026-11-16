import pytest
import requests

from bot_v.config import load_settings
from bot_v.llm.client import LLMClient, LLMError, is_error


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = str(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, data=None, status=200, exc=None):
        self.data = data
        self.status = status
        self.exc = exc
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.exc:
            raise self.exc
        return FakeResponse(self.data, self.status)


MODELS = {"general": "qwen-real", "coder": "coder-real", "embed": "embed-real"}


def client(backend, session, **kw):
    return LLMClient(
        host=kw.pop("host", "http://llm"), backend=backend, models=MODELS,
        api_key=kw.pop("api_key", ""), session=session, **kw,
    )


def test_ollama_chat_resolves_role_to_model():
    s = FakeSession({"message": {"content": "hi"}})
    assert client("ollama", s).query("general", "hello", system="sys") == "hi"
    call = s.calls[0]
    assert call["url"] == "http://llm/api/chat"
    assert call["json"]["model"] == "qwen-real"
    assert call["json"]["stream"] is False
    assert call["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_chat_and_v1_suffix_and_api_key():
    s = FakeSession({"choices": [{"message": {"content": "yo"}}]})
    c = client("openai", s, host="http://llm:8080/v1/", api_key="k")
    assert c.query("coder", "x") == "yo"
    assert s.calls[0]["url"] == "http://llm:8080/v1/chat/completions"
    assert s.calls[0]["json"]["model"] == "coder-real"
    assert s.calls[0]["headers"]["Authorization"] == "Bearer k"


def test_unknown_role_is_passed_through_as_model_name():
    s = FakeSession({"message": {"content": "ok"}})
    client("ollama", s).query("llama3:8b", "x")
    assert s.calls[0]["json"]["model"] == "llama3:8b"


def test_query_returns_error_string_instead_of_raising():
    s = FakeSession(exc=requests.ConnectionError("refused"))
    reply = client("ollama", s).query("general", "x")
    assert is_error(reply)


def test_http_error_raises_in_chat():
    s = FakeSession({"error": "boom"}, status=500)
    with pytest.raises(LLMError):
        client("openai", s).chat("general", [{"role": "user", "content": "x"}])


def test_embed_both_backends():
    s = FakeSession({"embeddings": [[1, 2, 3]]})
    assert client("ollama", s).embed("embed", "t") == [1.0, 2.0, 3.0]
    assert s.calls[0]["url"] == "http://llm/api/embed"
    assert s.calls[0]["json"]["model"] == "embed-real"

    s = FakeSession({"data": [{"embedding": [0.5]}]})
    assert client("openai", s).embed("embed", "t") == [0.5]
    assert s.calls[0]["url"] == "http://llm/v1/embeddings"


def test_embed_without_vector_raises():
    with pytest.raises(LLMError):
        client("ollama", FakeSession({"embeddings": []})).embed("embed", "t")


def test_query_image_formats(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")

    s = FakeSession({"message": {"content": "a cat"}})
    assert client("ollama", s).query_image("vision", "what?", str(img)) == "a cat"
    assert s.calls[0]["json"]["messages"][0]["images"]

    s = FakeSession({"choices": [{"message": {"content": "a dog"}}]})
    assert client("openai", s).query_image("vision", "what?", str(img)) == "a dog"
    parts = s.calls[0]["json"]["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_settings_from_env():
    s = load_settings({
        "BOTV_LLM_BACKEND": "openai",
        "BOTV_MODEL_GENERAL": "qwen",
        "BOTV_DATA_DIR": "/tmp/x",
        "BOTV_OPENJARVIS_CONFIG": "/tmp/oj.toml",
    })
    assert s.llm_backend == "openai"
    assert s.llm_host == "http://localhost:8080"
    assert s.models["general"] == "qwen"
    assert s.models["embed"] == "qwen"  # embed defaults to the general model
    assert s.openjarvis_config == "/tmp/oj.toml"

    with pytest.raises(ValueError):
        load_settings({"BOTV_LLM_BACKEND": "nope"})
