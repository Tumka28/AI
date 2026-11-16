"""A tiny MCP server over stdio for tests (no SDK needed).

Usage: python fake_mcp_server.py [normal|badversion]
"""

import json
import os
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
state = {"pong": False}

# Emulate Windows: with no UTF-8 setting in the environment, Python reads and
# writes pipes in the locale code page (cp1252), which garbles non-ASCII text.
if (os.environ.get("FAKE_WINDOWS_DEFAULT") and not os.environ.get("PYTHONIOENCODING")
        and os.environ.get("PYTHONUTF8") != "1"):
    sys.stdin.reconfigure(encoding="cp1252", errors="surrogateescape")
    sys.stdout.reconfigure(encoding="cp1252", errors="surrogateescape")

TOOLS = [
    {"name": "echo", "description": "Echo the text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "fail", "description": "Always fails.", "inputSchema": {"type": "object"}},
    {"name": "slow", "description": "Sleeps two seconds.", "inputSchema": {"type": "object"}},
    {"name": "pong_received", "description": "Did the client answer our ping?", "inputSchema": {"type": "object"}},
    {"name": "wipe", "description": "Deletes things.", "inputSchema": {"type": "object"},
     "annotations": {"destructiveHint": True}},
    {"name": "crash", "description": "Exits the server.", "inputSchema": {"type": "object"}},
    {"name": "hang_up", "description": "Closes stdout but keeps running for a while.",
     "inputSchema": {"type": "object"}},
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def text_result(req_id, text, is_error=False):
    send({"jsonrpc": "2.0", "id": req_id,
          "result": {"content": [{"type": "text", "text": text}], "isError": is_error}})


print("this line is not JSON and must be ignored", flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    method, req_id = msg.get("method"), msg.get("id")
    if method is None:  # a response from the client (to our ping)
        if msg.get("id") == "srv-ping":
            state["pong"] = True
        continue
    if method == "initialize":
        version = "1999-01-01" if MODE == "badversion" else msg["params"]["protocolVersion"]
        send({"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1"}}})
    elif method == "notifications/initialized":
        send({"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info", "data": "hi"}})
        send({"jsonrpc": "2.0", "id": "srv-ping", "method": "ping"})
    elif method == "tools/list":
        cursor = (msg.get("params") or {}).get("cursor")
        if cursor is None:
            send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS[:3], "nextCursor": "page2"}})
        else:
            send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS[3:]}})
    elif method == "tools/call":
        name = msg["params"]["name"]
        args = msg["params"].get("arguments") or {}
        if name == "echo":
            send({"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": args.get("text", "")}],
                "structuredContent": {"echo": args.get("text", "")}}})
        elif name == "fail":
            text_result(req_id, "boom", is_error=True)
        elif name == "slow":
            time.sleep(2)
            text_result(req_id, "late")
        elif name == "pong_received":
            text_result(req_id, str(state["pong"]))
        elif name == "crash":
            sys.exit(3)
        elif name == "hang_up":
            # Like a server that is shutting down: the pipe is gone, the process is not (yet).
            # (sys.stdout.close() would keep fd 1 open, so close the descriptor itself.)
            sys.stdout.flush()
            os.close(sys.stdout.fileno())
            time.sleep(3)
            sys.exit(0)
        else:
            text_result(req_id, "ok")
    elif req_id is not None:
        send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}})
