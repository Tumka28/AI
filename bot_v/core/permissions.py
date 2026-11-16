"""Bot V permission gate.

Bot V decides which tools a backend (e.g. OpenJarvis) may use for a task.
Read-only tools are allowed. Anything that writes files, runs code, sends
messages, changes git history, or is simply unknown needs approval. With no
approver configured, those tools are denied (default-deny).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

# Tools that only read or think, or only write to OpenJarvis's own memory.
DEFAULT_SAFE_TOOLS = frozenset(
    {
        "think",
        "calculator",
        "llm",
        "web_search",
        "get_weather",
        "file_read",
        "pdf_extract",
        "retrieval",
        "scan_chunks",
        "memory_search",
        "memory_retrieve",
        "memory_store",
        "memory_index",
        "kg_query",
        "kg_neighbors",
        "kg_add_entity",
        "kg_add_relation",
        "knowledge_sql",
        "git_status",
        "git_diff",
        "git_log",
        "calendar_search",
        "calendar_upcoming",
        "channel_list",
        "channel_status",
    }
)

# Called as approver(task, risky_tools) -> True to allow.
Approver = Callable[[str, List[str]], bool]


@dataclass
class PermissionDecision:
    allowed: bool
    approved: List[str] = field(default_factory=list)
    denied: List[str] = field(default_factory=list)
    reason: str = ""


class PermissionGate:
    def __init__(
        self,
        safe_tools: Iterable[str] = DEFAULT_SAFE_TOOLS,
        approver: Optional[Approver] = None,
    ):
        self.safe_tools = frozenset(safe_tools)
        self.approver = approver

    def is_safe(self, tool: str) -> bool:
        return tool in self.safe_tools

    def check(self, task: str, tools: Iterable[str]) -> PermissionDecision:
        tools = list(dict.fromkeys(tools))  # dedupe, keep order
        risky = [t for t in tools if not self.is_safe(t)]
        if not risky:
            return PermissionDecision(allowed=True, reason="all tools are read-only")

        if self.approver is None:
            return PermissionDecision(
                allowed=False,
                denied=risky,
                reason="these tools need approval and no approver is configured",
            )

        try:
            ok = bool(self.approver(task, risky))
        except Exception as exc:  # an approver failure must never mean "yes"
            return PermissionDecision(
                allowed=False, denied=risky, reason=f"approver failed: {exc}"
            )
        if ok:
            return PermissionDecision(allowed=True, approved=risky, reason="approved")
        return PermissionDecision(allowed=False, denied=risky, reason="approver said no")
