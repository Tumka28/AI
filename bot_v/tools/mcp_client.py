"""A small synchronous MCP client (stdio transport) that keeps servers alive.

Measured with the official MCP Python SDK server: starting a server and the
handshake take ~0.7 s (npx-based servers can take seconds), but each tool call
afterwards takes ~1-2 ms. So Bot V starts each server once, keeps the pipe
open, caches the tool list, and only shows the model the tools it needs.

Protocol: JSON-RPC 2.0, one JSON message per line on stdin/stdout, the
``initialize`` handshake (protocol revisions 2024-11-05 ... 2025-11-25).

Servers are configured in config/mcp.json, in the same format Claude Desktop
uses, plus two Bot V keys:

    {"mcpServers": {
        "files": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me/docs"],
            "env": {},
            "allow": ["read_file", "list_directory"],   # run without approval
            "disabled": false
        }
    }}

Every other tool of a server needs approval, like any write action.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot_v.tools.registry import Tool, ToolRegistry

CLIENT_INFO = {"name": "bot-v", "version": "0.3"}
REQUEST_VERSION = "2025-11-25"
HANDSHAKE_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
MAX_LINE = 10_000_000
_STDOUT_CLOSED = "_botv_stdout_closed"  # flag set on a Popen once its stdout hits EOF


class MCPError(RuntimeError):
    """An MCP server could not be started or did not answer correctly."""


class MCPServer:
    """One running MCP server process and its JSON-RPC session."""

    def __init__(self, name: str, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
                 timeout: float = 30.0, start_timeout: float = 60.0):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout = timeout
        self.start_timeout = start_timeout
        self.protocol_version: Optional[str] = None
        self.server_info: Dict[str, Any] = {}
        self.startup_ms: Optional[float] = None
        self._proc: Optional[subprocess.Popen] = None
        self._next_id = 0
        self._waiting: Dict[int, "queue.Queue[Dict[str, Any]]"] = {}
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._tools: Optional[List[Dict[str, Any]]] = None
        self._stderr_tail: List[str] = []

    # ----------------------------------------------------------- process
    @property
    def running(self) -> bool:
        proc = self._proc
        # A server whose stdout has closed can no longer answer, even if the
        # process has not finished exiting yet (on Windows that takes a moment).
        return proc is not None and proc.poll() is None and not getattr(proc, _STDOUT_CLOSED, False)

    def start(self) -> None:
        with self._state_lock:
            if self.running:
                return
            old = self._proc
            if old is not None and old.poll() is None:
                try:
                    old.kill()  # stdout closed but the process lingers: don't leave it behind
                except OSError:
                    pass
            # On Windows "npx", "uvx"... are .cmd files that subprocess cannot
            # find by name; shutil.which resolves them through PATHEXT.
            command = shutil.which(self.command) or self.command
            # MCP stdio is UTF-8. Python servers on Windows otherwise read and
            # write pipes as cp1252, which garbles non-English text. Values
            # already set in the environment or the server's config win.
            env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", **os.environ, **self.env}
            started = time.perf_counter()
            try:
                proc = subprocess.Popen(
                    [command, *self.args],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env=env, cwd=self.cwd,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
            except OSError as exc:
                raise MCPError(f"{self.name}: cannot start {self.command!r}: {exc}") from exc
            self._proc = proc
            threading.Thread(target=self._read_stdout, args=(proc,), daemon=True).start()
            threading.Thread(target=self._read_stderr, args=(proc,), daemon=True).start()
        try:
            result = self._request("initialize", {
                "protocolVersion": REQUEST_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            }, timeout=self.start_timeout)
        except MCPError:
            self.close()
            raise
        version = result.get("protocolVersion")
        if version not in HANDSHAKE_VERSIONS:
            self.close()
            raise MCPError(f"{self.name}: unsupported protocol version {version!r}")
        self.protocol_version = version
        self.server_info = result.get("serverInfo") or {}
        self._notify("notifications/initialized")
        self.startup_ms = round((time.perf_counter() - started) * 1000, 1)

    def close(self) -> None:
        with self._state_lock:
            proc, self._proc = self._proc, None
            self._tools = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        self._fail_all("server closed")

    def _fail_all(self, message: str) -> None:
        """Wake every request still waiting for an answer (each waiter is woken once)."""
        for req_id in list(self._waiting):
            waiter = self._waiting.pop(req_id, None)
            if waiter is None:
                continue
            try:
                waiter.put_nowait({"error": {"code": -32000, "message": message}})
            except queue.Full:
                pass

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line or len(line) > MAX_LINE:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # servers must not print non-JSON to stdout; ignore it
            if not isinstance(msg, dict):
                continue
            if "id" in msg and ("result" in msg or "error" in msg) and "method" not in msg:
                waiter = self._waiting.pop(msg["id"], None)
                if waiter is not None:
                    try:
                        waiter.put_nowait(msg)
                    except queue.Full:
                        pass
            elif "method" in msg and "id" in msg:
                try:
                    self._answer_server_request(msg)
                except MCPError:
                    pass
            # notifications from the server (logging, list_changed...) are ignored
        # The server closed stdout: it cannot answer any more. Mark it, then fail
        # its pending requests, unless a new process already replaced it (then
        # close() has failed the old ones).
        setattr(proc, _STDOUT_CLOSED, True)
        if self._proc is proc or self._proc is None:
            self._fail_all("server exited")
        try:
            proc.wait(timeout=5)  # reap the process once it finishes exiting
        except Exception:
            pass

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr_tail = (self._stderr_tail + [line.rstrip()])[-20:]

    def _send(self, msg: Dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise MCPError(f"{self.name}: server is not running")
        data = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            try:
                proc.stdin.write(data + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise MCPError(f"{self.name}: server pipe closed") from exc

    def _answer_server_request(self, msg: Dict[str, Any]) -> None:
        # Bot V offers no client capabilities (sampling, roots...), only ping.
        if msg.get("method") == "ping":
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        else:
            self._send({"jsonrpc": "2.0", "id": msg["id"],
                        "error": {"code": -32601, "message": "Method not found"}})

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None,
                 timeout: Optional[float] = None) -> Dict[str, Any]:
        with self._write_lock:
            self._next_id += 1
            req_id = self._next_id
        waiter: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        self._waiting[req_id] = waiter
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self._send(msg)
            reply = waiter.get(timeout=timeout or self.timeout)
        except queue.Empty as exc:
            try:
                self._notify("notifications/cancelled", {"requestId": req_id, "reason": "timeout"})
            except MCPError:
                pass
            raise MCPError(f"{self.name}: {method} timed out") from exc
        finally:
            self._waiting.pop(req_id, None)
        if "error" in reply:
            err = reply["error"] or {}
            detail = " | ".join(self._stderr_tail[-3:])
            raise MCPError(f"{self.name}: {method} failed: {err.get('message')}" + (f" ({detail})" if detail else ""))
        result = reply.get("result")
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------- tools
    def list_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        if self._tools is not None and not refresh:
            return self._tools
        if not self.running:
            self.start()
        tools: List[Dict[str, Any]] = []
        cursor = None
        for _ in range(50):  # pagination guard
            result = self._request("tools/list", {"cursor": cursor} if cursor else None)
            tools.extend(t for t in result.get("tools", []) if isinstance(t, dict) and t.get("name"))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self._tools = tools
        return tools

    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.running:
            self.start()
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict) and c.get("type") == "text"]
        out: Dict[str, Any] = {"text": "\n".join(texts)}
        if "structuredContent" in result:
            out["structured"] = result["structuredContent"]
        if result.get("isError"):
            raise MCPError(f"{self.name}/{tool}: {out['text'] or 'tool reported an error'}")
        return out

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "protocol_version": self.protocol_version,
            "server": self.server_info,
            "startup_ms": self.startup_ms,
            "tools": len(self._tools) if self._tools is not None else None,
        }


def tool_name(server: str, tool: str) -> str:
    return f"mcp__{server}__{tool}"


class MCPManager:
    """Starts the configured servers on first use and registers their tools."""

    def __init__(self, config_path: Optional[Path] = None, servers: Optional[Dict[str, MCPServer]] = None,
                 allow: Optional[Dict[str, List[str]]] = None):
        self.config_path = Path(config_path) if config_path else None
        self.servers: Dict[str, MCPServer] = dict(servers or {})
        self.allow: Dict[str, List[str]] = dict(allow or {})
        self.errors: Dict[str, str] = {}
        self._loaded = False
        self._lock = threading.Lock()
        if self.config_path and self.config_path.exists():
            self._read_config()

    def _read_config(self) -> None:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            self.errors["config"] = f"invalid JSON in {self.config_path}: {exc}"
            return
        for name, spec in (data.get("mcpServers") or {}).items():
            if not isinstance(spec, dict) or spec.get("disabled"):
                continue
            if not isinstance(spec.get("command"), str):
                self.errors[name] = "missing 'command' (only stdio servers are supported)"
                continue
            self.servers[name] = MCPServer(
                name, spec["command"], spec.get("args") or [], spec.get("env") or {}, spec.get("cwd"),
            )
            self.allow[name] = list(spec.get("allow") or [])

    def load(self, registry: ToolRegistry, refresh: bool = False) -> None:
        """Start servers (once) and register their tools as mcp__<server>__<tool>."""
        with self._lock:
            if self._loaded and not refresh:
                return
            for name, server in self.servers.items():
                registry.unregister_source(f"mcp:{name}")
                try:
                    tools = server.list_tools(refresh=refresh)
                except MCPError as exc:
                    self.errors[name] = str(exc)
                    continue
                self.errors.pop(name, None)
                for spec in tools:
                    self._register(registry, name, server, spec)
            self._loaded = True

    def _register(self, registry: ToolRegistry, server_name: str, server: MCPServer,
                  spec: Dict[str, Any]) -> None:
        raw_name = spec["name"]
        allowed = raw_name in self.allow.get(server_name, [])
        annotations = spec.get("annotations") or {}
        description = (spec.get("description") or "").strip()
        if annotations.get("destructiveHint"):
            description += " (server marks this tool as destructive)"

        def handler(args: Dict[str, Any], _srv=server, _tool=raw_name) -> Dict[str, Any]:
            return _srv.call_tool(_tool, args)

        schema = spec.get("inputSchema") if isinstance(spec.get("inputSchema"), dict) else {"type": "object"}
        try:
            registry.register(Tool(
                name=tool_name(server_name, raw_name),
                description=description[:1000] or f"{raw_name} (MCP server {server_name})",
                input_schema=schema,
                handler=handler,
                source=f"mcp:{server_name}",
                risk="read" if allowed else "write",
            ), replace=True)
        except ValueError as exc:
            self.errors[f"{server_name}/{raw_name}"] = str(exc)

    def status(self) -> Dict[str, Any]:
        return {
            "config": str(self.config_path) if self.config_path else None,
            "servers": {name: srv.status() for name, srv in self.servers.items()},
            "errors": dict(self.errors),
        }

    def close(self) -> None:
        for server in self.servers.values():
            server.close()
