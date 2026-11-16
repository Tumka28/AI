"""Bot V -> OpenJarvis adapter.

Bot V is the master. OpenJarvis (https://github.com/open-jarvis/OpenJarvis,
Apache-2.0) is used as an execution backend: its agents, tools, inference
engines and memory. Bot V decides what to run and whether it is allowed (see
``bot_v.core.permissions``); this adapter only translates calls.

OpenJarvis is an optional dependency and is imported lazily, so Bot V still
works without it. Install with ``pip install -r requirements-openjarvis.txt``.

One model setting for both: unless BOTV_OPENJARVIS_SYNC_LLM=0, OpenJarvis is
pointed at the same model server and model as Bot V (BOTV_LLM_BACKEND,
BOTV_LLM_HOST, BOTV_LLM_API_KEY, BOTV_MODEL_GENERAL). The rest of OpenJarvis's
settings still come from config/openjarvis.toml.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bot_v.config import Settings, settings

# Bot V's LLM backend -> the OpenJarvis engine that speaks the same protocol.
# OpenJarvis's "llamacpp" engine is its generic OpenAI-compatible client
# (GET /v1/models, POST /v1/chat/completions), so it also fits LM Studio, vLLM...
ENGINE_FOR_BACKEND = {"ollama": "ollama", "openai": "llamacpp"}


def llm_overrides(s: Settings) -> Dict[str, str]:
    """The engine, host and model OpenJarvis should use, taken from Bot V's settings."""
    engine = ENGINE_FOR_BACKEND[s.llm_backend]
    host = s.llm_host.rstrip("/")
    if engine != "ollama" and host.endswith("/v1"):
        host = host[: -len("/v1")]  # OpenJarvis adds the /v1 prefix itself
    return {"engine": engine, "host": host, "model": s.models.get("general", "")}


def apply_llm_overrides(cfg: Any, overrides: Dict[str, str]) -> None:
    """Point an OpenJarvis JarvisConfig at Bot V's model server."""
    engine = overrides["engine"]
    cfg.engine.default = engine
    getattr(cfg.engine, engine).host = overrides["host"]
    if overrides.get("model"):
        cfg.intelligence.default_model = overrides["model"]


class OpenJarvisUnavailable(RuntimeError):
    """OpenJarvis is not installed."""


@dataclass
class DelegationResult:
    content: str
    agent: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    turns: Optional[int] = None
    model: Optional[str] = None
    engine: Optional[str] = None
    backend: str = "openjarvis"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OpenJarvisAdapter:
    """Thin wrapper around ``openjarvis.Jarvis``.

    ``jarvis_factory`` lets tests (or other callers) supply their own client
    object; it is called with no arguments and must return something with the
    ``Jarvis`` interface (``ask_full``, ``memory``, ``close``).
    """

    name = "openjarvis"

    def __init__(
        self,
        config_path: Optional[str] = None,
        engine_key: Optional[str] = None,
        model: Optional[str] = None,
        jarvis_factory: Optional[Callable[[], Any]] = None,
        sync_llm: Optional[bool] = None,
        bot_settings: Optional[Settings] = None,
    ):
        s = bot_settings or settings
        self.config_path = config_path or s.openjarvis_config
        self.engine_key = engine_key
        self.model = model
        self._factory = jarvis_factory
        self._jarvis: Any = None
        sync = s.openjarvis_sync_llm if sync_llm is None else sync_llm
        self.llm: Optional[Dict[str, str]] = llm_overrides(s) if sync else None
        self._api_key = s.llm_api_key

    # ----------------------------------------------------------- lifecycle
    def is_installed(self) -> bool:
        if self._factory is not None:
            return True
        return importlib.util.find_spec("openjarvis") is not None

    def _client(self) -> Any:
        if self._jarvis is not None:
            return self._jarvis
        if self._factory is not None:
            self._jarvis = self._factory()
            return self._jarvis
        if not self.is_installed():
            raise OpenJarvisUnavailable(
                "OpenJarvis is not installed. Run: pip install -r requirements-openjarvis.txt"
            )
        from openjarvis import Jarvis
        from openjarvis.core.config import load_config

        cfg = load_config(Path(self.config_path)) if self.config_path else load_config()
        model = self.model
        if self.llm is not None:
            apply_llm_overrides(cfg, self.llm)
            model = model or self.llm["model"] or None
            if self._api_key and self.llm["engine"] != "ollama":
                # OpenJarvis reads OpenAI-compatible API keys only from the environment.
                os.environ.setdefault(f"{self.llm['engine'].upper()}_API_KEY", self._api_key)
        # Always name the engine. Without it, when the configured engine is down
        # OpenJarvis falls back to any engine that answers, including remote
        # ones such as NVIDIA's hosted NIM API, so prompts could leave the
        # machine. With an explicit engine it reports an error instead.
        self._jarvis = Jarvis(
            config=cfg,
            engine_key=self.engine_key or cfg.engine.default,
            model=model,
        )
        return self._jarvis

    def close(self) -> None:
        if self._jarvis is not None:
            try:
                self._jarvis.close()
            finally:
                self._jarvis = None

    def __enter__(self) -> "OpenJarvisAdapter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------- actions
    def ask(
        self,
        task: str,
        *,
        agent: Optional[str] = None,
        tools: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> DelegationResult:
        """Run a task on OpenJarvis.

        With no agent and no tools this is a plain model call. When tools are
        given without an agent, OpenJarvis's ``orchestrator`` agent (automatic
        tool selection) is used.

        Permission checks are NOT done here: Bot V must check ``tools`` with
        its PermissionGate before calling this.
        """
        tools = list(tools or [])
        if tools and agent is None:
            agent = "orchestrator"
        raw = self._client().ask_full(
            task,
            agent=agent,
            tools=tools or None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return DelegationResult(
            content=raw.get("content", ""),
            agent=agent,
            tools=tools,
            tool_results=list(raw.get("tool_results", [])),
            turns=raw.get("turns"),
            model=raw.get("model"),
            engine=raw.get("engine"),
        )

    def list_agents(self) -> List[str]:
        if not self.is_installed() or self._factory is not None:
            return []
        import openjarvis.agents  # noqa: F401  (registers agents)
        from openjarvis.core.registry import AgentRegistry

        return sorted(AgentRegistry.keys())

    def list_tools(self) -> List[str]:
        if not self.is_installed() or self._factory is not None:
            return []
        import openjarvis.tools  # noqa: F401  (registers tools)
        from openjarvis.core.registry import ToolRegistry

        return sorted(ToolRegistry.keys())

    def warm_up(self) -> Dict[str, Any]:
        """Load OpenJarvis and check its engine answers, so the first task is fast."""
        models = self._client().list_models()
        return {
            "engine": self.llm["engine"] if self.llm else self.engine_key,
            "model": (self.llm or {}).get("model") or self.model,
            "models": list(models)[:5],
        }

    def index_path(self, path: str) -> Dict[str, Any]:
        """Index a file or folder into OpenJarvis memory."""
        return self._client().memory.index(path)

    def search_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self._client().memory.search(query, top_k=top_k)

    def status(self) -> Dict[str, Any]:
        installed = self.is_installed()
        version = None
        if installed and self._factory is None:
            from importlib.metadata import PackageNotFoundError, version as pkg_version

            try:
                version = pkg_version("openjarvis")
            except PackageNotFoundError:
                version = None
        return {
            "installed": installed,
            "version": version,
            "config_path": self.config_path,
            # engine/host/model shared with Bot V (None: taken from config.toml)
            "llm": dict(self.llm) if self.llm else None,
            "connected": self._jarvis is not None,
        }
