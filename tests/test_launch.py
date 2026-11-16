import json
import os
import socket
import sys
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bot_v import launch
from bot_v.launch import (
    EXAMPLE_CONFIG, LaunchError, RESTART_CODE, botv_env, detect_model_id, ensure_model_server,
    first_run, llama_command, load_config, render_config, stop_process, supervise, wait_until,
)

FAKE_LLAMA = """
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
model = args[args.index("-m") + 1]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        data = json.dumps({"data": [{"id": "stub-model", "path": model}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def json_server():
    """Serve fixed JSON per path on a local port."""
    routes = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path not in routes:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(routes[self.path]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", routes
    srv.shutdown()


def write_config(path, **kw):
    path.write_text(render_config(**kw), encoding="utf-8")
    return load_config(path)


# ------------------------------------------------------------------- config
def test_example_config_matches_the_template():
    assert EXAMPLE_CONFIG.read_text(encoding="utf-8") == render_config()


def test_render_and_load_roundtrip_with_windows_path(tmp_path):
    cfg = write_config(tmp_path / "launch.toml", gguf=r"C:\models\qwen 14b.gguf", server=r"C:\llama\llama-server.exe")
    assert cfg["llamacpp"]["model"] == r"C:\models\qwen 14b.gguf"
    assert cfg["llamacpp"]["server"] == r"C:\llama\llama-server.exe"
    assert cfg["botv"]["port"] == 5000 and cfg["update"]["auto"] is True and cfg["env"] == {}


def test_load_config_fills_defaults_and_validates(tmp_path):
    path = tmp_path / "launch.toml"
    path.write_text('[model]\nengine = "ollama"\nhost = "http://127.0.0.1:11434"\n[env]\nBOTV_TEACHER = "claude"\n')
    cfg = load_config(path)
    assert cfg["ollama"]["model"] == "qwen3:14b" and cfg["env"] == {"BOTV_TEACHER": "claude"}

    path.write_text('[model]\nengine = "gpt"\n')
    with pytest.raises(LaunchError, match="engine"):
        load_config(path)
    path.write_text("[model\n")
    with pytest.raises(LaunchError, match="TOML"):
        load_config(path)


def test_first_run_non_interactive_writes_template(tmp_path):
    path = tmp_path / "config" / "launch.toml"
    with pytest.raises(LaunchError, match="GGUF"):
        first_run(path, interactive=False)
    assert tomllib.loads(path.read_text(encoding="utf-8"))["model"]["engine"] == "llamacpp"


def test_first_run_wizard(tmp_path, monkeypatch):
    gguf = tmp_path / "qwen.gguf"
    gguf.write_bytes(b"GGUF")
    monkeypatch.setattr(launch, "find_gguf", lambda limit=10: [gguf])

    answers = iter(["1", "1", ""])  # llama-server, first found file, llama-server on PATH
    path = tmp_path / "a.toml"
    first_run(path, ask=lambda q: next(answers), interactive=True)
    cfg = load_config(path)
    assert cfg["model"]["engine"] == "llamacpp" and cfg["llamacpp"]["model"] == str(gguf)

    monkeypatch.setattr(launch, "ollama_models", lambda host=launch.OLLAMA_HOST: [])
    answers = iter(["2", "llama3.2:3b"])
    path = tmp_path / "b.toml"
    first_run(path, ask=lambda q: next(answers), interactive=True)
    cfg = load_config(path)
    assert cfg["model"]["engine"] == "ollama" and cfg["model"]["host"].endswith(":11434")
    assert cfg["ollama"]["model"] == "llama3.2:3b"


def test_wizard_lists_installed_ollama_models_and_fixes_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launch, "ollama_models", lambda host=launch.OLLAMA_HOST: ["qwen3:14b", "llama3.2:3b"])
    answers = iter(["2", "2"])  # Ollama, second installed model
    path = tmp_path / "a.toml"
    first_run(path, ask=lambda q: next(answers), interactive=True)
    assert load_config(path)["ollama"]["model"] == "llama3.2:3b"
    assert "1. qwen3:14b" in capsys.readouterr().out

    # "qwen3.8 27b" (a space instead of ':') is understood; a name with other spaces is asked again.
    answers = iter(["2", "qwen3.8 27b"])
    path = tmp_path / "b.toml"
    first_run(path, ask=lambda q: next(answers), interactive=True)
    assert load_config(path)["ollama"]["model"] == "qwen3.8:27b"

    answers = iter(["2", "my model name", "qwen3:14b"])
    path = tmp_path / "c.toml"
    first_run(path, ask=lambda q: next(answers), interactive=True)
    assert load_config(path)["ollama"]["model"] == "qwen3:14b"
    assert "хоосон зайгүй" in capsys.readouterr().out


def test_ollama_name_helpers():
    assert launch.normalize_ollama_name("qwen3 14b") == "qwen3:14b"
    assert launch.normalize_ollama_name(" qwen3.8 27B ") == "qwen3.8:27b"
    assert launch.normalize_ollama_name("qwen3:14b") == "qwen3:14b"
    for good in ("qwen3:14b", "llama3.2", "hf.co/bartowski/Qwen3-GGUF:Q4_K_M"):
        assert launch.valid_ollama_name(good)
    for bad in ("qwen3.8 27b", "", ":14b", "qwen3:14b extra"):
        assert not launch.valid_ollama_name(bad)


# ---------------------------------------------------------- model server
def test_llama_command(tmp_path):
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"GGUF")
    cfg = write_config(tmp_path / "l.toml", gguf=str(gguf))
    cfg["llamacpp"]["server"] = [sys.executable, "fake.py"]
    cmd = llama_command(cfg)
    assert cmd[:2] == [sys.executable, "fake.py"]
    assert cmd[2:] == ["-m", str(gguf), "--host", "127.0.0.1", "--port", "8080", "-c", "8192"]

    cfg["llamacpp"]["server"] = "definitely-not-installed-llama"
    with pytest.raises(LaunchError, match="олдсонгүй"):
        llama_command(cfg)
    cfg["llamacpp"]["server"] = sys.executable
    cfg["llamacpp"]["model"] = str(tmp_path / "missing.gguf")
    with pytest.raises(LaunchError, match="GGUF"):
        llama_command(cfg)


def test_detect_model_id_and_wait(json_server):
    base, routes = json_server
    routes["/v1/models"] = {"data": [{"id": "qwen3-14b"}]}
    assert detect_model_id(base) == "qwen3-14b"
    routes["/v1/models"] = {"models": [{"name": "other"}]}
    assert detect_model_id(base) == "other"
    assert wait_until(base + "/v1/models", 2)["models"][0]["name"] == "other"
    with pytest.raises(LaunchError, match="хариулсангүй"):
        wait_until(base + "/nothing", 0.3, every=0.1)


def test_wait_until_reports_a_crashed_process(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("error: model file is corrupt\n")
    proc = __import__("subprocess").Popen([sys.executable, "-c", "raise SystemExit(2)"])
    proc.wait()
    with pytest.raises(LaunchError, match="corrupt"):
        wait_until(f"http://127.0.0.1:{free_port()}/v1/models", 5, proc=proc, log_path=log, every=0.1)


def test_launcher_starts_llama_server_and_reads_the_model(tmp_path):
    script = tmp_path / "fake_llama.py"
    script.write_text(FAKE_LLAMA)
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"GGUF")
    port = free_port()
    cfg = write_config(tmp_path / "l.toml", gguf=str(gguf), host=f"http://127.0.0.1:{port}")
    cfg["llamacpp"]["server"] = [sys.executable, str(script)]
    cfg["llamacpp"]["args"] = []

    proc, model = ensure_model_server(cfg, tmp_path / "logs")
    try:
        assert proc is not None and model == "stub-model"
        # Already running now: a second launch reuses it and starts nothing.
        again, model2 = ensure_model_server(cfg, tmp_path / "logs")
        assert again is None and model2 == "stub-model"
    finally:
        stop_process(proc, "test")
    assert proc.poll() is not None


def test_ollama_model_check(tmp_path, json_server, monkeypatch):
    base, routes = json_server
    routes["/api/tags"] = {"models": [{"name": "qwen3:14b"}]}
    cfg = write_config(tmp_path / "o.toml", engine="ollama", host=base, ollama_model="qwen3:14b")
    assert ensure_model_server(cfg, tmp_path) == (None, "qwen3:14b")

    cfg["ollama"]["model"] = "missing-model"
    cfg["ollama"]["pull"] = False
    with pytest.raises(LaunchError, match="ollama pull") as err:
        ensure_model_server(cfg, tmp_path)
    assert "qwen3:14b" in str(err.value)  # the message lists what is installed

    cfg["ollama"]["model"] = "qwen3.8 27b"  # what was typed on the first real run
    with pytest.raises(LaunchError, match="нэр буруу") as err:
        ensure_model_server(cfg, tmp_path)
    assert "config/launch.toml" in str(err.value)


# ------------------------------------------------------------------- Bot V
def test_botv_env(tmp_path):
    cfg = write_config(tmp_path / "e.toml", engine="ollama", host="http://127.0.0.1:11434/")
    cfg["env"] = {"BOTV_TEACHER": "claude", "BOTV_HA_URL": "http://ha.local:8123"}
    env = botv_env(cfg, "qwen3:14b", base={"BOTV_TEACHER": "ollama", "BOTV_LLM_HOST": "http://old:1"})
    assert env["BOTV_LLM_BACKEND"] == "ollama"
    assert env["BOTV_LLM_HOST"] == "http://127.0.0.1:11434"  # the launcher's server always wins
    assert env["BOTV_MODEL_GENERAL"] == "qwen3:14b"
    assert env["BOTV_TEACHER"] == "ollama"  # a variable set in the shell wins over [env]
    assert env["BOTV_HA_URL"] == "http://ha.local:8123"
    assert env["BOTV_SUPERVISED"] == "1" and env["BOTV_AUTO_UPDATE"] == "1"


def test_supervisor_restarts_after_update_and_reinstalls(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    marker = tmp_path / "updated"
    child = (
        "import pathlib, sys\n"
        f"m = pathlib.Path(r'{marker}')\n"
        "if not m.exists():\n"
        "    m.write_text('1')\n"
        f"    pathlib.Path(r'{tmp_path / 'requirements.txt'}').write_text('flask\\nnumpy\\n')\n"
        f"    sys.exit({RESTART_CODE})\n"
        "sys.exit(0)\n"
    )
    installs = []
    code = supervise([sys.executable, "-c", child], dict(os.environ), f"http://127.0.0.1:{free_port()}",
                     open_browser=False, installer=lambda: installs.append(1) or True,
                     repo=tmp_path, start_timeout=5)
    assert code == 0 and marker.exists() and installs == [1]


def test_supervisor_gives_up_after_too_many_restarts(tmp_path):
    started = time.time()
    code = supervise([sys.executable, "-c", f"raise SystemExit({RESTART_CODE})"], dict(os.environ),
                     f"http://127.0.0.1:{free_port()}", open_browser=False, installer=lambda: True,
                     repo=tmp_path, max_restarts=2, start_timeout=5)
    assert code == RESTART_CODE and time.time() - started < 30


def test_check_mode_prints_plan(tmp_path, capsys):
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"GGUF")
    path = tmp_path / "launch.toml"
    path.write_text(render_config(gguf=str(gguf), server=sys.executable), encoding="utf-8")
    assert launch.main(["--config", str(path), "--check"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["llama_command"][1:3] == ["-m", str(gguf)]
    assert plan["llama_command"][3:7] == ["--host", "127.0.0.1", "--port", "8080"]
    assert Path(plan["config"]) == path
