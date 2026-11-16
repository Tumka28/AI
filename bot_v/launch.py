"""One click: model server + Bot V (+ OpenJarvis, MCP tools) + browser, with auto-update.

    python -m bot_v.launch                 # what start-botv.bat / start-botv.sh run
    python -m bot_v.launch --check         # show what would start; start nothing
    python -m bot_v.launch --no-browser

Settings live in config/launch.toml (created on the first run; it is not
committed). The launcher is a small supervisor:

1. updates the checkout from GitHub ([update] auto: main branch, fast-forward only),
2. starts the model server (llama-server or Ollama) unless it is already running,
   waits until it answers, and reads the model name from it,
3. starts Bot V's web server as a child process with matching BOTV_* settings
   (Bot V warms up OpenJarvis and the MCP tools in the background),
4. opens the browser,
5. restarts Bot V when it updated itself (F5 in the browser), reinstalling the
   packages if the requirements changed; the model server keeps running,
6. on exit, stops the model server only if it started it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bot_v import updater
from bot_v.config import PROJECT_ROOT

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "launch.toml"
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "launch.example.toml"
RESTART_CODE = 75  # Bot V exits with this after updating itself: "start me again"
ENGINES = ("llamacpp", "ollama")

# Health checks are local: never send them through a system/corporate proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class LaunchError(RuntimeError):
    pass


def say(message: str) -> None:
    print(message, flush=True)


# ------------------------------------------------------------------- config
def _q(value: Any) -> str:
    """A TOML string (JSON string escaping is valid TOML for basic strings)."""
    return json.dumps(str(value), ensure_ascii=False)


def render_config(engine: str = "llamacpp", host: str = "http://127.0.0.1:8080",
                  server: str = "llama-server", gguf: str = "", ollama_model: str = "qwen3:14b") -> str:
    return f"""# Bot V one-click start settings (start-botv.bat / start-botv.sh).
# This file is yours: it is not committed to git.

[model]
# "llamacpp" = llama-server with a GGUF file, "ollama" = Ollama
engine = {_q(engine)}
# Where the model server listens (llama-server: 8080, Ollama: 11434)
host = {_q(host)}
# Start the model server if it is not running yet
start = true
# How long a big model may take to load (seconds)
wait_seconds = 600

[llamacpp]
# llama-server(.exe): a full path, or just the name if it is on PATH
server = {_q(server)}
# Your model file, e.g. "C:/models/qwen3-14b-q4_k_m.gguf"
model = {_q(gguf)}
# Extra llama-server options, e.g. ["-c", "8192", "-ngl", "99"] (-ngl: layers on the GPU)
args = ["-c", "8192"]

[ollama]
model = {_q(ollama_model)}
# Download the model if Ollama does not have it yet
pull = true

[botv]
port = 5000
open_browser = true

[update]
# On every start and on F5 in the browser: take the newest version from GitHub
# (main branch, fast-forward only; local changes are never overwritten)
auto = true

[env]
# More Bot V settings (see README), for example:
# BOTV_HA_URL = "http://homeassistant.local:8123"
# BOTV_TEACHER = "claude"
"""


DEFAULTS: Dict[str, Dict[str, Any]] = tomllib.loads(render_config())


def find_gguf(limit: int = 10) -> List[Path]:
    """GGUF files in the usual places, to help on the first run."""
    places = [PROJECT_ROOT / "models", Path.home() / "models", Path.home() / "Downloads",
              Path("C:/models"), Path("D:/models")]
    found: List[Path] = []
    for place in places:
        try:
            if place.is_dir():
                found += sorted(place.glob("*.gguf")) + sorted(place.glob("*/*.gguf"))
        except OSError:
            continue
    unique = list(dict.fromkeys(p.resolve() for p in found))
    return unique[:limit]


def first_run(path: Path, ask: Callable[[str], str] = input, interactive: Optional[bool] = None) -> None:
    """Create config/launch.toml, asking a few questions when possible."""
    interactive = sys.stdin.isatty() if interactive is None else interactive
    path.parent.mkdir(parents=True, exist_ok=True)
    if not interactive:
        path.write_text(render_config(), encoding="utf-8")
        raise LaunchError(f"{path} үүсгэлээ. GGUF файлынхаа замыг [llamacpp] model-д бичээд дахин асаана уу.")

    say("Анхны тохиргоо: хэдэн асуултад хариулна уу (дараа нь config/launch.toml-д засаж болно).")
    choice = ask("Загварыг юугаар ажиллуулах вэ? 1 = llama-server (GGUF файл), 2 = Ollama [1]: ").strip()
    if choice == "2":
        model = ask("Ollama загварын нэр [qwen3:14b]: ").strip() or "qwen3:14b"
        text = render_config(engine="ollama", host="http://127.0.0.1:11434", ollama_model=model)
    else:
        found = find_gguf()
        for i, p in enumerate(found, 1):
            say(f"  {i}. {p}")
        hint = " (эсвэл дээрх дугаар)" if found else ""
        gguf = ask(f"GGUF файлын зам{hint}: ").strip().strip('"')
        if gguf.isdigit() and found and 1 <= int(gguf) <= len(found):
            gguf = str(found[int(gguf) - 1])
        server = ask("llama-server-ийн зам (PATH дээр байвал Enter): ").strip().strip('"') or "llama-server"
        text = render_config(engine="llamacpp", server=server, gguf=gguf)
    path.write_text(text, encoding="utf-8")
    say(f"[ok] {path} хадгаллаа")


def load_config(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        with open(path, "rb") as fh:
            user = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise LaunchError(f"{path}: TOML алдаа: {exc}") from exc
    cfg = {section: {**values, **(user.get(section) or {})} for section, values in DEFAULTS.items()}
    cfg["env"] = dict(user.get("env") or {})
    if cfg["model"]["engine"] not in ENGINES:
        raise LaunchError(f"[model] engine нь {ENGINES}-ийн нэг байх ёстой, {cfg['model']['engine']!r} биш")
    return cfg


# ------------------------------------------------------------------- http
def http_json(url: str, timeout: float = 2.0) -> Optional[Any]:
    try:
        with _OPENER.open(url, timeout=timeout) as res:
            if res.status != 200:
                return None
            return json.loads(res.read().decode("utf-8") or "null")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _log_tail(log_path: Optional[Path], lines: int = 15) -> str:
    if not log_path or not log_path.exists():
        return ""
    text = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return "\n".join(text)


def wait_until(url: str, timeout: float, *, proc: Optional[subprocess.Popen] = None,
               label: str = "server", log_path: Optional[Path] = None, every: float = 1.0) -> Any:
    """Poll url until it returns JSON. Raises LaunchError on timeout or if proc dies."""
    started = time.time()
    next_note = started + 15
    while True:
        data = http_json(url)
        if data is not None:
            return data
        if proc is not None and proc.poll() is not None:
            tail = _log_tail(log_path)
            raise LaunchError(f"{label} зогслоо (код {proc.returncode})." + (f"\n{tail}" if tail else ""))
        now = time.time()
        if now - started > timeout:
            raise LaunchError(f"{label} {int(timeout)} секундэд хариулсангүй: {url}")
        if now >= next_note:
            say(f"[..] {label} ачаалж байна... ({int(now - started)} сек)")
            next_note = now + 15
        time.sleep(every)


# ------------------------------------------------------------ model server
def _host_port(host: str) -> Tuple[str, int]:
    u = urlparse(host)
    return u.hostname or "127.0.0.1", u.port or 8080


def _command(value: Any) -> List[str]:
    """A command from config: "llama-server", a path, or a list like ["wsl", "llama-server"]."""
    parts = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    if not parts or not parts[0]:
        raise LaunchError("[llamacpp] server хоосон байна")
    exe = shutil.which(parts[0]) or (parts[0] if Path(parts[0]).expanduser().exists() else None)
    if exe is None:
        raise LaunchError(
            f"llama-server олдсонгүй: {parts[0]!r}. llama.cpp-г https://github.com/ggml-org/llama.cpp/releases-ээс "
            "татаад config/launch.toml-ийн [llamacpp] server-т llama-server.exe-ийн бүтэн замыг бичнэ үү."
        )
    return [exe, *parts[1:]]


def llama_command(cfg: Dict[str, Dict[str, Any]]) -> List[str]:
    llama = cfg["llamacpp"]
    model = Path(str(llama.get("model") or "")).expanduser()
    if not str(llama.get("model") or "") or not model.is_file():
        found = "\n".join(f"  {p}" for p in find_gguf())
        raise LaunchError(
            f"GGUF файл олдсонгүй: {llama.get('model')!r}. config/launch.toml-ийн [llamacpp] model-д бичнэ үү."
            + (f"\nОлдсон GGUF файлууд:\n{found}" if found else "")
        )
    host, port = _host_port(cfg["model"]["host"])
    return [*_command(llama.get("server") or "llama-server"), "-m", str(model),
            "--host", host, "--port", str(port), *[str(a) for a in llama.get("args") or []]]


def detect_model_id(host: str) -> Optional[str]:
    data = http_json(host.rstrip("/") + "/v1/models")
    if not isinstance(data, dict):
        return None
    for item in (data.get("data") or data.get("models") or []):
        if isinstance(item, dict) and (item.get("id") or item.get("name")):
            return str(item.get("id") or item.get("name"))
    return None


def _start_logged(cmd: List[str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=PROJECT_ROOT)
    except OSError as exc:
        raise LaunchError(f"эхлүүлж чадсангүй: {cmd[0]}: {exc}") from exc
    finally:
        log.close()


def ensure_model_server(cfg: Dict[str, Dict[str, Any]], logs: Path
                        ) -> Tuple[Optional[subprocess.Popen], str]:
    """Make sure the model server answers. Returns (process we started or None, model name)."""
    model_cfg = cfg["model"]
    engine, host = model_cfg["engine"], model_cfg["host"].rstrip("/")
    wait = float(model_cfg.get("wait_seconds", 600))
    proc = None

    if engine == "llamacpp":
        health = host + "/v1/models"
        if http_json(health) is None:
            if not model_cfg.get("start", True):
                raise LaunchError(f"llama-server {host} дээр ажиллахгүй байна ([model] start = false)")
            cmd = llama_command(cfg)
            log_path = logs / "llama-server.log"
            say(f"[..] llama-server асааж байна: {Path(cmd[cmd.index('-m') + 1]).name}")
            proc = _start_logged(cmd, log_path)
            wait_until(health, wait, proc=proc, label="llama-server", log_path=log_path)
        else:
            say(f"[ok] llama-server аль хэдийн ажиллаж байна ({host})")
        model = detect_model_id(host) or "local-model"
        say(f"[ok] Загвар: {model}")
        return proc, model

    # Ollama
    health = host + "/api/tags"
    if http_json(health) is None:
        ollama = shutil.which("ollama")
        if not model_cfg.get("start", True) or ollama is None:
            raise LaunchError(f"Ollama {host} дээр ажиллахгүй байна. Ollama-г асаана уу (https://ollama.com).")
        say("[..] Ollama асааж байна")
        log_path = logs / "ollama.log"
        proc = _start_logged([ollama, "serve"], log_path)
        wait_until(health, 60, proc=proc, label="Ollama", log_path=log_path)
    model = str(cfg["ollama"].get("model") or "qwen3:14b")
    tags = http_json(health) or {}
    names = {m.get("name") or m.get("model") for m in tags.get("models", []) if isinstance(m, dict)}
    if model not in names and f"{model}:latest" not in names:
        ollama = shutil.which("ollama")
        if not cfg["ollama"].get("pull", True) or ollama is None:
            raise LaunchError(f"Ollama-д {model!r} загвар алга. `ollama pull {model}` ажиллуулна уу.")
        say(f"[..] {model} загварыг татаж байна (анх удаа удаж магадгүй)")
        if subprocess.run([ollama, "pull", model]).returncode != 0:
            raise LaunchError(f"ollama pull {model} амжилтгүй боллоо")
    say(f"[ok] Ollama, загвар: {model}")
    return proc, model


def stop_process(proc: Optional[subprocess.Popen], label: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    say(f"[..] {label}-ийг унтрааж байна")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


# ------------------------------------------------------------------- Bot V
def botv_env(cfg: Dict[str, Dict[str, Any]], model: str, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Environment for Bot V: the model server the launcher manages, plus [env]."""
    import os

    env = dict(os.environ if base is None else base)
    for key, value in cfg["env"].items():
        env.setdefault(str(key), str(value))  # a variable already set in the shell wins
    engine = cfg["model"]["engine"]
    # The model connection must match the server the launcher manages.
    env["BOTV_LLM_BACKEND"] = "ollama" if engine == "ollama" else "openai"
    env["BOTV_LLM_HOST"] = cfg["model"]["host"].rstrip("/")
    env["BOTV_MODEL_GENERAL"] = model
    env["BOTV_SERVER_PORT"] = str(cfg["botv"]["port"])
    env["BOTV_SUPERVISED"] = "1"
    env["BOTV_AUTO_UPDATE"] = "1" if cfg["update"].get("auto", True) else "0"
    env["BOTV_WARMUP"] = "1"
    env.setdefault("PYTHONUTF8", "1")
    return env


def supervise(cmd: List[str], env: Dict[str, str], url: str, *, open_browser: bool = True,
              installer: Callable[[], bool] = updater.pip_install, repo: Path = PROJECT_ROOT,
              max_restarts: int = 20, start_timeout: float = 120) -> int:
    """Run Bot V; restart it when it exits with RESTART_CODE (after an update)."""
    opened = False
    restarts = 0
    while True:
        req_hash = updater.requirements_hash(repo)
        child = subprocess.Popen(cmd, env=env, cwd=repo)
        try:
            if not opened:
                try:
                    wait_until(url + "/status", start_timeout, proc=child, label="Bot V")
                    say(f"[ok] Bot V бэлэн: {url}")
                    if open_browser:
                        webbrowser.open(url)
                except LaunchError as exc:
                    say(f"[!!] {exc}")
                opened = True
            code = child.wait()
        except KeyboardInterrupt:
            stop_process(child, "Bot V")
            return 0
        if code != RESTART_CODE:
            return code
        restarts += 1
        if restarts > max_restarts:
            say("[!!] Bot V хэт олон удаа дахин асав, зогсоолоо")
            return code
        say("[..] Bot V шинэчлэгдлээ, дахин асааж байна")
        if updater.requirements_hash(repo) != req_hash:
            say("[..] Шинэ package-ууд суулгаж байна")
            if not installer():
                say("[!!] pip install амжилтгүй. Дээрх алдааг харна уу.")


def startup_update(cfg: Dict[str, Dict[str, Any]], installer: Callable[[], bool] = updater.pip_install) -> None:
    if not cfg["update"].get("auto", True) or not updater.is_checkout():
        return
    result = updater.apply()
    if result.get("updated"):
        say(f"[ok] GitHub-аас шинэчиллээ: {result['from']} -> {result['to']} ({result['commits']} commit)")
        if result.get("requirements_changed"):
            say("[..] Шинэ package-ууд суулгаж байна")
            installer()
    elif result.get("reason") and result.get("reason") != "up to date":
        say(f"[--] Шинэчлэл хийгдсэнгүй: {result['reason']}")


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # never crash on a console that cannot show Cyrillic
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="python -m bot_v.launch")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="show what would start, start nothing")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    started: Optional[subprocess.Popen] = None
    try:
        if not config_path.exists():
            first_run(config_path)
        cfg = load_config(config_path)
        port = int(cfg["botv"]["port"])
        url = f"http://127.0.0.1:{port}"

        if args.check:
            say(json.dumps({"config": str(config_path), "model": cfg["model"],
                            "llama_command": llama_command(cfg) if cfg["model"]["engine"] == "llamacpp" else None,
                            "update": updater.status(do_fetch=False)}, ensure_ascii=False, indent=2))
            return 0

        startup_update(cfg)

        running = http_json(url + "/status")
        if isinstance(running, dict) and "llm" in running:
            say(f"[ok] Bot V аль хэдийн ажиллаж байна: {url}")
            if cfg["botv"].get("open_browser", True) and not args.no_browser:
                webbrowser.open(url)
            return 0

        logs = PROJECT_ROOT / "data" / "logs"
        started, model = ensure_model_server(cfg, logs)
        env = botv_env(cfg, model)
        return supervise([sys.executable, "-m", "bot_v.server"], env, url,
                         open_browser=cfg["botv"].get("open_browser", True) and not args.no_browser)
    except LaunchError as exc:
        say(f"[!!] {exc}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop_process(started, "Загварын сервер")


if __name__ == "__main__":
    sys.exit(main())
