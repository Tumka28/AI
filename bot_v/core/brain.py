"""Bot V — the master controller.

Bot V owns the decisions; backends do the work:

    user -> BotV -> (local LLM)            plain answers, Bot V's own agents
                 -> PermissionGate -> OpenJarvisAdapter -> OpenJarvis agents/tools

Everything Bot V does is written to the ExperienceLog.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

from bot_v.core.permissions import PermissionGate
from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter, OpenJarvisUnavailable
from bot_v.llm.client import LLMClient, is_error
from bot_v.memory.experience_log import ExperienceLog

SYSTEM_PROMPT = (
    "You are Bot V, a personal AI assistant. Answer clearly and concisely, "
    "in the same language the user writes in."
)

BACKENDS = ("auto", "local", "openjarvis")


class BotV:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        openjarvis: Optional[OpenJarvisAdapter] = None,
        gate: Optional[PermissionGate] = None,
        log: Optional[ExperienceLog] = None,
        on_event: Optional[Callable[[str], None]] = None,
    ):
        self.llm = llm or LLMClient()
        self.openjarvis = openjarvis or OpenJarvisAdapter()
        self.gate = gate or PermissionGate()
        self.log = log or ExperienceLog()
        self._on_event = on_event

    def _event(self, text: str) -> None:
        if self._on_event is not None:
            try:
                self._on_event(text)
            except Exception:
                pass

    # ------------------------------------------------------------ actions
    def chat(self, message: str) -> Dict[str, Any]:
        """Answer with Bot V's own local model."""
        self._event("local: thinking")
        reply = self.llm.query("general", message, system=SYSTEM_PROMPT)
        status = "error" if is_error(reply) else "ok"
        self.log.record("chat", backend="local", input=message, output=reply, status=status)
        return {"status": status, "backend": "local", "reply": reply}

    def delegate(
        self,
        task: str,
        *,
        agent: Optional[str] = None,
        tools: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Hand a task to OpenJarvis, after Bot V's permission check."""
        tools = list(tools or [])
        decision = self.gate.check(task, tools)
        if not decision.allowed:
            self._event(f"openjarvis: denied {decision.denied}")
            self.log.record(
                "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
                status="denied", denied=decision.denied, reason=decision.reason,
            )
            return {
                "status": "denied",
                "backend": "openjarvis",
                "reply": f"Bot V blocked tools {decision.denied}: {decision.reason}",
                "denied": decision.denied,
            }

        self._event(f"openjarvis: running (agent={agent}, tools={tools})")
        try:
            result = self.openjarvis.ask(task, agent=agent, tools=tools)
        except OpenJarvisUnavailable as exc:
            self.log.record("delegate", backend="openjarvis", input=task, status="unavailable")
            return {"status": "unavailable", "backend": "openjarvis", "reply": str(exc)}
        except Exception as exc:
            self.log.record(
                "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
                status="error", error=str(exc),
            )
            return {"status": "error", "backend": "openjarvis", "reply": f"OpenJarvis error: {exc}"}

        self.log.record(
            "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
            approved=decision.approved, output=result.content,
            tool_results=result.tool_results, model=result.model, status="ok",
        )
        self._event("openjarvis: done")
        return {
            "status": "ok",
            "backend": "openjarvis",
            "reply": result.content,
            "result": result.to_dict(),
        }

    def handle(self, message: str, backend: str = "auto") -> Dict[str, Any]:
        """Entry point for a user message.

        ``auto``: use the local model; if it fails and OpenJarvis is installed,
        let OpenJarvis answer instead.
        """
        if backend not in BACKENDS:
            raise ValueError(f"backend must be one of {BACKENDS}, got {backend!r}")
        if backend == "openjarvis":
            return self.delegate(message)

        local = self.chat(message)
        if backend == "local" or local["status"] == "ok":
            return local
        if not self.openjarvis.is_installed():
            return local

        self._event("local model failed, falling back to OpenJarvis")
        fallback = self.delegate(message)
        fallback["fallback_from"] = "local"
        fallback["local_error"] = local["reply"]
        return fallback

    # ------------------------------------------------------------- status
    def status(self) -> Dict[str, Any]:
        return {
            "llm": {
                "backend": self.llm.backend,
                "host": self.llm.host,
                "models": self.llm.models,
            },
            "openjarvis": self.openjarvis.status(),
            "safe_tools": sorted(self.gate.safe_tools),
            "approver": self.gate.approver is not None,
        }

    def close(self) -> None:
        self.openjarvis.close()
