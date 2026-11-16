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
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

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

    return Settings(
        llm_backend=backend,
        llm_host=env.get("BOTV_LLM_HOST", _DEFAULT_HOSTS[backend]),
        llm_api_key=env.get("BOTV_LLM_API_KEY", ""),
        llm_timeout=float(env.get("BOTV_LLM_TIMEOUT", "120")),
        models=models,
        data_dir=Path(env.get("BOTV_DATA_DIR", PROJECT_ROOT / "data")),
        openjarvis_config=oj_config,
    )


settings = load_settings()


def data_path(*parts: str) -> Path:
    """Path inside Bot V's data directory. Parent folders are created."""
    path = settings.data_dir.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
