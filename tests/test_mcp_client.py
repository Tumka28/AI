import json
import sys
from pathlib import Path

import pytest

from bot_v.tools.mcp_client import MCPError, MCPManager, MCPServer
from bot_v.tools.registry import ToolRegistry

FAKE = str(Path(__file__).with_name("fake_mcp_server.py"))


@pytest.fixture
def server():
    srv = MCPServer("fake", sys.executable, [FAKE], timeout=5)
    yield srv
    srv.close()


def test_handshake_list_and_call(server):
    tools = server.list_tools()
    assert [t["name"] for t in tools] == [
        "echo", "fail", "slow", "pong_received", "wipe", "crash", "hang_up"]  # 2 pages
    assert server.protocol_version == "2025-11-25"
    assert server.status()["running"] and server.status()["tools"] == 7

    assert server.call_tool("echo", {"text": "сайн уу"}) == {"text": "сайн уу", "structured": {"echo": "сайн уу"}}
    with pytest.raises(MCPError, match="boom"):
        server.call_tool("fail", {})
    # The server pinged us after the handshake; the client must have answered.
    assert server.call_tool("pong_received", {})["text"] == "True"


def test_tool_list_is_cached(server):
    first = server.list_tools()
    assert server.list_tools() is first


def test_timeout_and_recovery(server):
    server.timeout = 0.5
    with pytest.raises(MCPError, match="timed out"):
        server.call_tool("slow", {})
    server.timeout = 5
    assert server.call_tool("echo", {"text": "still alive"})["text"] == "still alive"


def test_crash_is_reported_and_server_restarts(server):
    server.list_tools()
    with pytest.raises(MCPError):
        server.call_tool("crash", {})
    assert not server.running
    assert server.call_tool("echo", {"text": "back"})["text"] == "back"  # restarted on demand


def test_server_that_hangs_up_counts_as_stopped_and_is_replaced(server):
    # On Windows the pipe closes a moment before the process is gone. Bot V must
    # treat the server as stopped right away and start a fresh one.
    server.list_tools()
    with pytest.raises(MCPError):
        server.call_tool("hang_up", {})
    lingering = server._proc
    assert not server.running
    assert server.call_tool("echo", {"text": "new process"})["text"] == "new process"
    assert server._proc is not lingering
    assert lingering.wait(timeout=5) is not None  # the old process was not left behind


def test_python_servers_get_utf8_stdio(monkeypatch):
    # FAKE_WINDOWS_DEFAULT makes the fake server behave like Python on Windows:
    # cp1252 pipes unless PYTHONIOENCODING / PYTHONUTF8 say otherwise.
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    srv = MCPServer("win", sys.executable, [FAKE], env={"FAKE_WINDOWS_DEFAULT": "1"}, timeout=5)
    try:
        assert srv.call_tool("echo", {"text": "Сайн уу, Монгол"})["text"] == "Сайн уу, Монгол"
    finally:
        srv.close()


def test_command_is_resolved_like_a_shell_would(monkeypatch):
    # Windows: "npx" is really "npx.cmd"; shutil.which finds it through PATHEXT.
    from bot_v.tools import mcp_client

    monkeypatch.setattr(mcp_client.shutil, "which",
                        lambda cmd: sys.executable if cmd == "fake-npx" else None)
    srv = MCPServer("cmd", "fake-npx", [FAKE], timeout=5)
    try:
        assert srv.call_tool("echo", {"text": "ok"})["text"] == "ok"
    finally:
        srv.close()


def test_bad_protocol_version_is_rejected():
    srv = MCPServer("old", sys.executable, [FAKE, "badversion"], timeout=5)
    with pytest.raises(MCPError, match="protocol version"):
        srv.start()
    assert not srv.running


def test_missing_command():
    with pytest.raises(MCPError, match="cannot start"):
        MCPServer("ghost", "/no/such/binary").start()


def test_manager_registers_tools_with_risk(tmp_path):
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {
        "fake": {"command": sys.executable, "args": [FAKE], "allow": ["echo"]},
        "off": {"command": "nothing", "disabled": True},
        "http": {"url": "https://example.com/mcp"},
    }}))
    manager = MCPManager(config)
    registry = ToolRegistry()
    try:
        manager.load(registry)
        tools = {t.name: t for t in registry.list()}
        assert tools["mcp__fake__echo"].risk == "read"
        assert tools["mcp__fake__wipe"].risk == "write"
        assert "destructive" in tools["mcp__fake__wipe"].description
        assert "off" not in manager.servers
        assert "stdio" in manager.errors["http"]

        assert registry.call("mcp__fake__echo", {"text": "hi"})["result"]["text"] == "hi"
        pending = registry.call("mcp__fake__wipe", {})
        assert pending["status"] == "needs_approval"
        assert registry.approve(pending["action"]["id"])["status"] == "ok"
        assert registry.call("mcp__fake__echo", {})["status"] == "invalid_args"  # text is required
    finally:
        manager.close()


def test_broken_config_is_reported(tmp_path):
    config = tmp_path / "mcp.json"
    config.write_text("{not json")
    assert "config" in MCPManager(config).errors


def test_interop_with_official_sdk_server(tmp_path):
    pytest.importorskip("mcp.server.mcpserver")
    script = tmp_path / "sdk_server.py"
    script.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "server = MCPServer('sdk')\n"
        "@server.tool()\n"
        "def add(a: int, b: int) -> int:\n"
        "    '''Add two integers.'''\n"
        "    return a + b\n"
        "server.run()\n"
    )
    srv = MCPServer("sdk", sys.executable, [str(script)], timeout=10, start_timeout=60)
    try:
        assert [t["name"] for t in srv.list_tools()] == ["add"]
        assert srv.call_tool("add", {"a": 2, "b": 40})["text"] == "42"
    finally:
        srv.close()
