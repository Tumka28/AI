from pathlib import Path
from types import SimpleNamespace

import pytest

from bot_v.config import PROJECT_ROOT, load_settings
from bot_v.integrations.openjarvis_adapter import (
    OpenJarvisAdapter,
    OpenJarvisUnavailable,
    apply_llm_overrides,
    llm_overrides,
)

from fakes import FakeJarvis


def make(fake=None):
    fake = fake or FakeJarvis()
    return OpenJarvisAdapter(jarvis_factory=lambda: fake), fake


def test_plain_ask_has_no_agent():
    adapter, fake = make()
    result = adapter.ask("hello")
    assert result.content == "oj: hello"
    assert result.agent is None
    assert result.backend == "openjarvis"
    assert fake.calls[0]["agent"] is None
    assert fake.calls[0]["tools"] is None


def test_tools_without_agent_use_orchestrator():
    adapter, fake = make()
    result = adapter.ask("2+3?", tools=["calculator"])
    assert fake.calls[0]["agent"] == "orchestrator"
    assert fake.calls[0]["tools"] == ["calculator"]
    assert result.turns == 2
    assert result.tool_results[0]["tool_name"] == "calculator"
    assert result.to_dict()["engine"] == "llamacpp"


def test_explicit_agent_is_kept():
    adapter, fake = make()
    adapter.ask("research", agent="deep_research")
    assert fake.calls[0]["agent"] == "deep_research"


def test_client_is_created_once_and_closed():
    created = []

    def factory():
        created.append(FakeJarvis())
        return created[-1]

    adapter = OpenJarvisAdapter(jarvis_factory=factory)
    adapter.ask("a")
    adapter.ask("b")
    assert len(created) == 1
    assert adapter.status()["connected"] is True
    adapter.close()
    assert created[0].closed
    assert adapter.status()["connected"] is False


def test_memory_passthrough():
    adapter, fake = make()
    assert adapter.index_path("docs/")["path"] == "docs/"
    assert adapter.search_memory("q")[0]["content"] == "hit for q"


# ------------------------------------------------- one model setting for both
def fake_oj_config():
    return SimpleNamespace(
        engine=SimpleNamespace(default="llamacpp", llamacpp=SimpleNamespace(host="http://localhost:8080"),
                               ollama=SimpleNamespace(host="http://localhost:11434")),
        intelligence=SimpleNamespace(default_model=""),
    )


def test_llm_overrides_follow_bot_v_settings():
    s = load_settings({"BOTV_LLM_BACKEND": "openai", "BOTV_LLM_HOST": "http://gpu-box:9000/v1/",
                       "BOTV_MODEL_GENERAL": "qwen3"})
    assert llm_overrides(s) == {"engine": "llamacpp", "host": "http://gpu-box:9000", "model": "qwen3"}

    s = load_settings({"BOTV_LLM_BACKEND": "ollama", "BOTV_LLM_HOST": "http://nas:11434/"})
    assert llm_overrides(s) == {"engine": "ollama", "host": "http://nas:11434", "model": "deepseek-v2:16b"}


def test_apply_llm_overrides_switches_engine_host_and_model():
    cfg = fake_oj_config()
    apply_llm_overrides(cfg, {"engine": "ollama", "host": "http://nas:11434", "model": "qwen3:14b"})
    assert cfg.engine.default == "ollama"
    assert cfg.engine.ollama.host == "http://nas:11434"
    assert cfg.engine.llamacpp.host == "http://localhost:8080"  # untouched
    assert cfg.intelligence.default_model == "qwen3:14b"


def test_status_shows_shared_llm_and_sync_can_be_turned_off():
    s = load_settings({"BOTV_LLM_BACKEND": "openai", "BOTV_MODEL_GENERAL": "qwen3"})
    adapter = OpenJarvisAdapter(jarvis_factory=FakeJarvis, bot_settings=s)
    assert adapter.status()["llm"] == {"engine": "llamacpp", "host": "http://localhost:8080", "model": "qwen3"}

    off = load_settings({"BOTV_OPENJARVIS_SYNC_LLM": "0"})
    assert off.openjarvis_sync_llm is False
    assert OpenJarvisAdapter(jarvis_factory=FakeJarvis, bot_settings=off).status()["llm"] is None


def install_fake_openjarvis(monkeypatch, cfg):
    """Fake 'openjarvis' modules so _client() can run without the real package."""
    import sys
    import types

    captured = {}

    class FakeJarvisSDK:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self):
            pass

    root = types.ModuleType("openjarvis")
    root.Jarvis = FakeJarvisSDK
    core = types.ModuleType("openjarvis.core")
    config_mod = types.ModuleType("openjarvis.core.config")
    config_mod.load_config = lambda path=None: cfg
    monkeypatch.setitem(sys.modules, "openjarvis", root)
    monkeypatch.setitem(sys.modules, "openjarvis.core", core)
    monkeypatch.setitem(sys.modules, "openjarvis.core.config", config_mod)
    return captured


def test_client_always_names_the_engine(monkeypatch):
    cfg = fake_oj_config()
    captured = install_fake_openjarvis(monkeypatch, cfg)

    shared = OpenJarvisAdapter(bot_settings=load_settings(
        {"BOTV_LLM_BACKEND": "ollama", "BOTV_LLM_HOST": "http://nas:11434", "BOTV_MODEL_GENERAL": "qwen3"}))
    shared.is_installed = lambda: True
    shared._client()
    assert captured["engine_key"] == "ollama" and captured["model"] == "qwen3"
    assert captured["config"] is cfg and cfg.engine.ollama.host == "http://nas:11434"

    # Sync off: the engine still comes from config.toml, but it is named explicitly,
    # so OpenJarvis cannot silently fall back to another (possibly remote) engine.
    captured.clear()
    cfg.engine.default = "llamacpp"
    own = OpenJarvisAdapter(bot_settings=load_settings({"BOTV_OPENJARVIS_SYNC_LLM": "0"}))
    own.is_installed = lambda: True
    own._client()
    assert captured["engine_key"] == "llamacpp" and captured["model"] is None


def test_api_key_is_passed_through_the_environment(monkeypatch):
    captured = install_fake_openjarvis(monkeypatch, fake_oj_config())
    monkeypatch.delenv("LLAMACPP_API_KEY", raising=False)
    adapter = OpenJarvisAdapter(bot_settings=load_settings(
        {"BOTV_LLM_BACKEND": "openai", "BOTV_LLM_API_KEY": "k-123"}))
    adapter.is_installed = lambda: True
    adapter._client()
    import os
    assert os.environ["LLAMACPP_API_KEY"] == "k-123" and captured["engine_key"] == "llamacpp"


def test_real_openjarvis_config_is_overridden():
    pytest.importorskip("openjarvis")
    from openjarvis.core.config import load_config

    cfg = load_config(Path(PROJECT_ROOT / "config" / "openjarvis.toml"))
    assert cfg.engine.default == "llamacpp"
    apply_llm_overrides(cfg, {"engine": "ollama", "host": "http://nas:11434", "model": "qwen3:14b"})
    assert cfg.engine.default == "ollama"
    assert cfg.engine.ollama_host == "http://nas:11434"  # the attribute OpenJarvis's engine factory reads
    assert cfg.intelligence.default_model == "qwen3:14b"
    assert cfg.analytics.enabled is False  # the rest still comes from config.toml


def test_missing_openjarvis_raises_clear_error(monkeypatch):
    adapter = OpenJarvisAdapter()
    monkeypatch.setattr(adapter, "is_installed", lambda: False)
    try:
        adapter.ask("x")
    except OpenJarvisUnavailable as exc:
        assert "pip install" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected OpenJarvisUnavailable")
