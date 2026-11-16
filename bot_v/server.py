"""Bot V web server: serves the IDE in ui/ and the JSON API it calls.

Run:  python -m bot_v.server        (http://127.0.0.1:5000)

Binds to 127.0.0.1 by default because the API can read project files. Set
BOTV_SERVER_HOST / BOTV_SERVER_PORT to change that.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from bot_v.config import PROJECT_ROOT
from bot_v.core.brain import BACKENDS, BotV

UI_DIR = PROJECT_ROOT / "ui"
SKIP_DIRS = {".git", "__pycache__", "data", "node_modules", ".venv", "venv", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".toml"}
MAX_OPEN_BYTES = 1_000_000


class EventHub:
    """Fan-out of short status lines to every /stream listener."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: List[queue.Queue] = []

    def publish(self, text: str) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for q in listeners:
            try:
                q.put_nowait(text)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)


def _json_body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _require_str(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        abort(400, description=f"'{key}' (non-empty string) is required")
    return value


def create_app(bot: Optional[BotV] = None, root: Path = PROJECT_ROOT) -> Flask:
    app = Flask(__name__, static_folder=None)
    hub = EventHub()
    bot = bot or BotV(on_event=hub.publish)
    root = Path(root).resolve()
    app.config["BOT"] = bot
    app.config["HUB"] = hub

    @app.errorhandler(400)
    def _bad_request(err):
        return jsonify({"error": getattr(err, "description", "bad request")}), 400

    # ------------------------------------------------------------------ UI
    @app.get("/")
    def index():
        return send_from_directory(UI_DIR, "index.html")

    @app.get("/ui/<path:name>")
    def ui_file(name: str):
        return send_from_directory(UI_DIR, name)

    # --------------------------------------------------------------- Bot V
    @app.get("/status")
    def status():
        return jsonify(bot.status())

    @app.post("/chat")
    def chat():
        data = _json_body()
        message = _require_str(data, "message")
        backend = data.get("backend", "auto")
        if backend not in BACKENDS:
            abort(400, description=f"'backend' must be one of {list(BACKENDS)}")
        return jsonify(bot.handle(message, backend=backend))

    @app.get("/experience")
    def experience():
        n = min(int(request.args.get("n", 20)), 200)
        return jsonify(bot.log.tail(n))

    # ---------------------------------------------------------- OpenJarvis
    @app.post("/openjarvis/ask")
    def openjarvis_ask():
        data = _json_body()
        task = _require_str(data, "task")
        agent = data.get("agent") or None
        tools = data.get("tools") or []
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            abort(400, description="'tools' must be a list of tool names")
        result = bot.delegate(task, agent=agent, tools=tools)
        code = {"ok": 200, "denied": 403, "unavailable": 503}.get(result["status"], 502)
        return jsonify(result), code

    @app.get("/openjarvis/agents")
    def openjarvis_agents():
        return jsonify({"agents": bot.openjarvis.list_agents()})

    @app.get("/openjarvis/tools")
    def openjarvis_tools():
        tools = bot.openjarvis.list_tools()
        return jsonify(
            {"tools": [{"name": t, "needs_approval": not bot.gate.is_safe(t)} for t in tools]}
        )

    # --------------------------------------------------------------- files
    @app.get("/file_tree")
    def file_tree():
        files = []
        for folder, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(names):
                path = Path(folder) / name
                if path.suffix in TEXT_SUFFIXES:
                    files.append(path.relative_to(root).as_posix())
        return jsonify({"files": files})

    @app.post("/open_file")
    def open_file():
        rel = _require_str(_json_body(), "path")
        target = (root / rel).resolve()
        if not target.is_relative_to(root) or any(p in SKIP_DIRS for p in target.relative_to(root).parts):
            abort(400, description="path is outside the project")
        if not target.is_file():
            abort(400, description="not a file")
        if target.stat().st_size > MAX_OPEN_BYTES:
            abort(400, description="file too large")
        return jsonify({"path": rel, "content": target.read_text(encoding="utf-8", errors="replace")})

    # -------------------------------------------------- Bot V's own agents
    # These call the local model and can take a while.
    def run(fn: Callable[[], Any]):
        try:
            return jsonify(fn())
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/multi_agent_v2")
    def multi_agent_v2():
        goal = _require_str(_json_body(), "goal")
        from bot_v.agents.multi_agent.multi_agent_controller import MultiAgentController2

        return run(lambda: MultiAgentController2().run(goal))

    @app.post("/autogpt")
    def autogpt():
        goal = _require_str(_json_body(), "goal")
        from bot_v.autogpt.controller import AutoGPTController

        return run(lambda: AutoGPTController().run(goal))

    @app.post("/generate_project")
    def generate_project():
        desc = _require_str(_json_body(), "description")
        from bot_v.project.project_builder import ProjectBuilder

        out_dir = str(root / "data" / "generated_project")
        return run(lambda: ProjectBuilder().build_project(desc, output_dir=out_dir))

    @app.post("/semantic/build")
    def semantic_build():
        from bot_v.search.semantic_search_controller import SemanticSearchController

        return run(lambda: SemanticSearchController().build_index(str(root / "bot_v")))

    @app.post("/semantic/search")
    def semantic_search():
        query = _require_str(_json_body(), "query")
        from bot_v.search.semantic_search_controller import SemanticSearchController

        return run(lambda: SemanticSearchController().search(query))

    @app.post("/self_optimize")
    def self_optimize():
        code = _require_str(_json_body(), "code")
        from bot_v.self_optimize.self_optimizer import SelfOptimizer

        return run(lambda: SelfOptimizer().optimize(code))

    @app.post("/long_memory")
    def long_memory():
        data = _json_body()
        message = _require_str(data, "message")
        agent = data.get("agent") or "IDE-Agent"
        from bot_v.memory.long_memory_controller import LongMemoryController

        def go():
            ctrl = LongMemoryController()
            reply = ctrl.process(agent, message, lambda prompt: bot.llm.query("general", prompt))
            return {"agent": agent, "reply": reply}

        return run(go)

    # -------------------------------------------------------------- stream
    @app.get("/stream")
    def stream():
        q = hub.subscribe()

        def events():
            try:
                yield "data: [connected to Bot V]\n\n"
                while True:
                    try:
                        text = q.get(timeout=15)
                        for line in str(text).splitlines() or [""]:
                            yield f"data: {line}\n"
                        yield "\n"
                    except queue.Empty:
                        yield ": keep-alive\n\n"
            finally:
                hub.unsubscribe(q)

        return Response(events(), mimetype="text/event-stream")

    return app


def main() -> None:
    host = os.environ.get("BOTV_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("BOTV_SERVER_PORT", "5000"))
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
