import pytest

from bot_v.core.brain import BotV
from bot_v.core.permissions import PermissionGate
from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter
from bot_v.memory.experience_log import ExperienceLog
from bot_v.server import create_app

from fakes import FakeJarvis, FakeLLM


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("print('hi')\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("secret")
    (tmp_path / "outside.txt").write_text("outside")

    bot = BotV(
        llm=FakeLLM(),
        openjarvis=OpenJarvisAdapter(jarvis_factory=FakeJarvis),
        gate=PermissionGate(),
        log=ExperienceLog(tmp_path / "exp.jsonl"),
    )
    return create_app(bot=bot, root=root).test_client()


def test_status(client):
    data = client.get("/status").get_json()
    assert data["openjarvis"]["installed"] is True
    assert "calculator" in data["safe_tools"]


def test_chat(client):
    res = client.post("/chat", json={"message": "hi", "backend": "local"})
    assert res.status_code == 200
    assert res.get_json()["reply"] == "local reply"


def test_chat_validates_input(client):
    assert client.post("/chat", json={}).status_code == 400
    assert client.post("/chat", json={"message": "x", "backend": "nope"}).status_code == 400


def test_openjarvis_ask_ok_and_denied(client):
    ok = client.post("/openjarvis/ask", json={"task": "2+3", "tools": ["calculator"]})
    assert ok.status_code == 200 and ok.get_json()["reply"] == "oj: 2+3"

    denied = client.post("/openjarvis/ask", json={"task": "ls", "tools": ["shell_exec"]})
    assert denied.status_code == 403
    assert denied.get_json()["denied"] == ["shell_exec"]

    bad = client.post("/openjarvis/ask", json={"task": "x", "tools": "shell_exec"})
    assert bad.status_code == 400


def test_experience_endpoint(client):
    client.post("/chat", json={"message": "hi", "backend": "local"})
    assert client.get("/experience").get_json()[-1]["input"] == "hi"


def test_file_tree_and_open_file(client):
    files = client.get("/file_tree").get_json()["files"]
    assert files == ["pkg/mod.py"]  # .git is hidden

    res = client.post("/open_file", json={"path": "pkg/mod.py"})
    assert res.get_json()["content"] == "print('hi')\n"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", ".git/config", "pkg/../../outside.txt"])
def test_open_file_blocks_paths_outside_project(client, path):
    assert client.post("/open_file", json={"path": path}).status_code == 400


def test_ui_is_served(client):
    assert b"Bot V" in client.get("/").data
    assert client.get("/ui/app.js").status_code == 200
