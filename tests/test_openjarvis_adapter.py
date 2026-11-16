from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter, OpenJarvisUnavailable

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


def test_missing_openjarvis_raises_clear_error(monkeypatch):
    adapter = OpenJarvisAdapter()
    monkeypatch.setattr(adapter, "is_installed", lambda: False)
    try:
        adapter.ask("x")
    except OpenJarvisUnavailable as exc:
        assert "pip install" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected OpenJarvisUnavailable")
