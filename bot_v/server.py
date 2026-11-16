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

from bot_v import updater
from bot_v.config import PROJECT_ROOT
from bot_v.core.brain import BACKENDS, BotV
from bot_v.skills.library import SkillError

RESTART_CODE = 75  # tells the launcher (bot_v.launch) to start Bot V again

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


def _restart_soon(delay: float = 1.0) -> None:
    """Exit with RESTART_CODE after the HTTP response has gone out."""
    timer = threading.Timer(delay, lambda: os._exit(RESTART_CODE))
    timer.daemon = True
    timer.start()


def create_app(bot: Optional[BotV] = None, root: Path = PROJECT_ROOT, *,
               supervised: Optional[bool] = None, auto_update: Optional[bool] = None,
               restart: Callable[[], None] = _restart_soon, repo: Path = PROJECT_ROOT) -> Flask:
    app = Flask(__name__, static_folder=None)
    hub = EventHub()
    bot = bot or BotV(on_event=hub.publish)
    root = Path(root).resolve()
    app.config["BOT"] = bot
    app.config["HUB"] = hub
    # Started by bot_v.launch? Only then can Bot V restart itself after an update.
    supervised = os.environ.get("BOTV_SUPERVISED") == "1" if supervised is None else supervised
    auto_update = os.environ.get("BOTV_AUTO_UPDATE") == "1" if auto_update is None else auto_update

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

    # -------------------------------------------------------------- update
    @app.get("/update/status")
    def update_status():
        info = updater.status(repo)  # git fetch at most every few seconds
        return jsonify({**info, "supervised": supervised, "auto": auto_update})

    @app.post("/update/apply")
    def update_apply():
        if not supervised:
            return jsonify({"updated": False, "reason": "Bot V can only restart itself when started "
                            "with start-botv (python -m bot_v.launch)"}), 409
        result = updater.apply(repo)
        if result.get("updated"):
            hub.publish(f"update: {result['from']} -> {result['to']}, restarting")
            bot.log.record("update", **{k: v for k, v in result.items() if k != "files"})
            restart()
            result["restarting"] = True
        return jsonify(result)

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

    # --------------------------------------------------------------- tools
    @app.get("/tools")
    def tools_list():
        bot.load_tools()
        return jsonify({"tools": bot.tools.describe(),
                        "mcp": bot.mcp.status() if bot.mcp else None})

    @app.post("/tools/call")
    def tools_call():
        data = _json_body()
        name = _require_str(data, "tool")
        args = data.get("args") or {}
        if not isinstance(args, dict):
            abort(400, description="'args' must be a JSON object")
        bot.load_tools()
        result = bot.tools.call(name, args, task=f"direct call: {name}")
        code = {"ok": 200, "needs_approval": 202, "denied": 403, "invalid_args": 400}.get(result["status"], 502)
        return jsonify(result), code

    @app.get("/actions")
    def actions_list():
        return jsonify({"pending": bot.tools.pending()})

    @app.post("/actions/approve")
    def actions_approve():
        result = bot.approve_action(_require_str(_json_body(), "id"))
        return jsonify(result), (200 if result["status"] == "ok" else 400)

    @app.post("/actions/deny")
    def actions_deny():
        result = bot.deny_action(_require_str(_json_body(), "id"))
        return jsonify(result), (200 if result["status"] == "denied" else 400)

    # ------------------------------------------------------- teacher/learning
    @app.get("/learning/stats")
    def learning_stats():
        return jsonify(bot.training.stats())

    @app.post("/learning/export")
    def learning_export():
        fmt = _json_body().get("format", "sft")
        if fmt not in ("sft", "dpo"):
            abort(400, description="'format' must be 'sft' or 'dpo'")
        out = bot.training.path.parent / f"train_{fmt}.jsonl"
        count = bot.training.export_sft(out) if fmt == "sft" else bot.training.export_dpo(out)
        return jsonify({"format": fmt, "count": count, "path": str(out)})

    # -------------------------------------------------------------- skills
    @app.errorhandler(SkillError)
    def _skill_error(err):
        return jsonify({"error": str(err)}), 400

    @app.get("/skills")
    def skills_list():
        return jsonify(bot.skills.list())

    @app.post("/skills/fetch")
    def skills_fetch():
        data = _json_body()
        source = _require_str(data, "source")
        subdir = data.get("subdir") or None
        ref = data.get("ref") or None
        return jsonify({"results": bot.skills.fetch(source, subdir=subdir, ref=ref)})

    @app.get("/skills/report/<name>")
    def skills_report(name: str):
        return jsonify(bot.skills.report(name))

    @app.post("/skills/approve")
    def skills_approve():
        data = _json_body()
        name = _require_str(data, "name")
        allow = data.get("allow_high_risk") is True
        return jsonify(bot.skills.approve(name, allow_high_risk=allow, approved_by="web-ui"))

    @app.post("/skills/reject")
    def skills_reject():
        name = _require_str(_json_body(), "name")
        bot.skills.reject(name)
        return jsonify({"name": name, "status": "rejected"})

    @app.post("/skills/remove")
    def skills_remove():
        name = _require_str(_json_body(), "name")
        bot.skills.remove(name)
        return jsonify({"name": name, "status": "removed"})

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


def warm_up(bot: BotV, say: Callable[[str], None] = print) -> None:
    """Load OpenJarvis and the MCP tools in the background so the first request is fast."""
    if bot.openjarvis.is_installed():
        try:
            info = bot.openjarvis.warm_up()
            say(f"[ok] OpenJarvis бэлэн: engine {info['engine']}, загвар {info['model']}")
        except Exception as exc:
            say(f"[!!] OpenJarvis: {exc}")
    else:
        say("[--] OpenJarvis суугаагүй (pip install -r requirements-openjarvis.txt)")
    try:
        bot.load_tools()
        sources: Dict[str, int] = {}
        for tool in bot.tools.list():
            sources[tool.source] = sources.get(tool.source, 0) + 1
        say(f"[ok] Tool-ууд: {sources}")
        if bot.mcp is not None and bot.mcp.errors:
            say(f"[!!] MCP: {bot.mcp.errors}")
    except Exception as exc:
        say(f"[!!] Tool-ууд: {exc}")


def main() -> None:
    host = os.environ.get("BOTV_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("BOTV_SERVER_PORT", "5000"))
    app = create_app()
    if os.environ.get("BOTV_WARMUP") == "1":
        threading.Thread(target=warm_up, args=(app.config["BOT"],), daemon=True).start()
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
