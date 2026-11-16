"""Bot V settings.

Every value can be overridden with an environment variable, so the same code
runs against Ollama, llama-server (llama.cpp), LM Studio, vLLM, etc.

    BOTV_LLM_BACKEND      "ollama" (default) or "openai" (any OpenAI-compatible server)
    BOTV_LLM_HOST         server URL (default: Ollama 11434, OpenAI-compatible 8080)
    BOTV_LLM_API_KEY      optional bearer token for the LLM server
    BOTV_LLM_TIMEOUT      request timeout in seconds (default 120)
    BOTV_MODEL_GENERAL    model used for reasoning / chat
    BOTV_MODEL_CODER      model used for writing and fixing code
    BOTV_MODEL_VISION     model used for images
    BOTV_MODEL_EMBED      model used for embeddings (memory, semantic search)
    BOTV_DATA_DIR         where Bot V keeps its own data (default: <repo>/data)
    BOTV_OPENJARVIS_CONFIG  OpenJarvis config.toml that Bot V hands to OpenJarvis

Teacher (a bigger model Bot V learns from; off unless BOTV_TEACHER is set):

    BOTV_TEACHER          "" (off), "claude", "openai" or "ollama"
    BOTV_TEACHER_MODEL    model name (claude default: claude-opus-5-5)
    BOTV_TEACHER_HOST     server URL for "openai" / "ollama" teachers
    BOTV_TEACHER_EFFORT   Claude effort: low|medium|high|xhigh|max (default high)
    BOTV_TEACHER_MODE     "fallback" (default): ask the teacher when the local model fails
                          "review": the teacher also grades every local answer
                          "manual": only when the teacher is asked directly

Tools:

    BOTV_MCP_CONFIG       MCP servers file (default: <repo>/config/mcp.json, if present)
    BOTV_HA_URL           Home Assistant URL, e.g. http://homeassistant.local:8123
    BOTV_HA_TOKEN         Home Assistant long-lived access token (keep it secret)
    BOTV_HA_ENTITIES      optional allowlist, e.g. "light.*,switch.kitchen,sensor.*"
    BOTV_HA_ALLOW_DANGEROUS  "1" to allow (with approval) locks, alarms, covers, scripts...
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_HOSTS = {
    "ollama": "http://localhost:11434",
    "openai": "http://localhost:8080",  # llama-server default port
}


@dataclass
class Settings:
    llm_backend: str = "ollama"
    llm_host: str = _DEFAULT_HOSTS["ollama"]
    llm_api_key: str = ""
    llm_timeout: float = 120.0
    # Code refers to models by *role* ("general", "coder", ...); this maps a
    # role to the real model name on the server.
    models: Dict[str, str] = field(default_factory=dict)
    data_dir: Path = PROJECT_ROOT / "data"
    openjarvis_config: Optional[str] = None
    teacher_provider: str = ""
    teacher_model: str = ""
    teacher_host: str = ""
    teacher_effort: str = "high"
    teacher_mode: str = "fallback"
    mcp_config: Optional[str] = None
    ha_url: str = ""
    ha_token: str = field(default="", repr=False)
    ha_entities: List[str] = field(default_factory=list)
    ha_allow_dangerous: bool = False


TEACHER_PROVIDERS = ("", "claude", "openai", "ollama")
TEACHER_MODES = ("fallback", "review", "manual")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def load_settings(env: Optional[Dict[str, str]] = None) -> Settings:
    env = dict(os.environ if env is None else env)

    backend = env.get("BOTV_LLM_BACKEND", "ollama").strip().lower()
    if backend not in _DEFAULT_HOSTS:
        raise ValueError(
            f"BOTV_LLM_BACKEND must be one of {sorted(_DEFAULT_HOSTS)}, got {backend!r}"
        )

    general = env.get("BOTV_MODEL_GENERAL", "deepseek-v2:16b")
    models = {
        "general": general,
        "coder": env.get("BOTV_MODEL_CODER", "deepseek-coder-v2:16b"),
        "vision": env.get("BOTV_MODEL_VISION", "llava:7b"),
        "embed": env.get("BOTV_MODEL_EMBED", general),
    }

    oj_config = env.get("BOTV_OPENJARVIS_CONFIG")
    if not oj_config:
        bundled = PROJECT_ROOT / "config" / "openjarvis.toml"
        oj_config = str(bundled) if bundled.exists() else None

    teacher = env.get("BOTV_TEACHER", "").strip().lower()
    if teacher not in TEACHER_PROVIDERS:
        raise ValueError(f"BOTV_TEACHER must be one of {TEACHER_PROVIDERS}, got {teacher!r}")
    teacher_mode = env.get("BOTV_TEACHER_MODE", "fallback").strip().lower()
    if teacher_mode not in TEACHER_MODES:
        raise ValueError(f"BOTV_TEACHER_MODE must be one of {TEACHER_MODES}, got {teacher_mode!r}")
    teacher_effort = env.get("BOTV_TEACHER_EFFORT", "high").strip().lower()
    if teacher_effort not in CLAUDE_EFFORTS:
        raise ValueError(f"BOTV_TEACHER_EFFORT must be one of {CLAUDE_EFFORTS}, got {teacher_effort!r}")
    teacher_model = env.get("BOTV_TEACHER_MODEL", "")
    if teacher == "claude" and not teacher_model:
        teacher_model = "claude-opus-5-5"
    teacher_host = env.get("BOTV_TEACHER_HOST", "")
    if teacher in ("openai", "ollama") and not teacher_host:
        teacher_host = _DEFAULT_HOSTS[teacher]

    mcp_config = env.get("BOTV_MCP_CONFIG")
    if not mcp_config:
        default_mcp = PROJECT_ROOT / "config" / "mcp.json"
        mcp_config = str(default_mcp) if default_mcp.exists() else None
    ha_entities = [p.strip() for p in env.get("BOTV_HA_ENTITIES", "").split(",") if p.strip()]

    return Settings(
        llm_backend=backend,
        llm_host=env.get("BOTV_LLM_HOST", _DEFAULT_HOSTS[backend]),
        llm_api_key=env.get("BOTV_LLM_API_KEY", ""),
        llm_timeout=float(env.get("BOTV_LLM_TIMEOUT", "120")),
        models=models,
        data_dir=Path(env.get("BOTV_DATA_DIR", PROJECT_ROOT / "data")),
        openjarvis_config=oj_config,
        teacher_provider=teacher,
        teacher_model=teacher_model,
        teacher_host=teacher_host,
        teacher_effort=teacher_effort,
        teacher_mode=teacher_mode,
        mcp_config=mcp_config,
        ha_url=env.get("BOTV_HA_URL", "").strip(),
        ha_token=env.get("BOTV_HA_TOKEN", "").strip(),
        ha_entities=ha_entities,
        ha_allow_dangerous=env.get("BOTV_HA_ALLOW_DANGEROUS", "").strip().lower() in ("1", "true", "yes"),
    )


settings = load_settings()


def data_path(*parts: str) -> Path:
    """Path inside Bot V's data directory. Parent folders are created."""
    path = settings.data_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
