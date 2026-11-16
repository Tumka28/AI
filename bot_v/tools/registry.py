"""One tool layer for everything Bot V can do, all spoken in JSON.

Every tool, wherever it lives, looks the same to Bot V and to the model:

    {"name": ..., "description": ..., "input_schema": {JSON schema}}
    call:   {"tool": name, "args": {...}}  ->  {"status": ..., "result": ...}

Sources:
    native         Python functions in this process (fastest, microseconds)
    homeassistant  Home Assistant REST API (direct JSON over HTTP)
    mcp:<server>   tools of an MCP server (JSON-RPC over a kept-alive stdio pipe)

Every call is checked before it runs:
    read       runs
    write      needs approval (approver callback, or the pending-approval queue)
    dangerous  needs approval and is only offered when explicitly enabled
    blocked    never runs
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

RISKS = ("read", "write", "dangerous", "blocked")
ACTION_TTL_SECONDS = 15 * 60
MAX_PENDING = 50

# approver(task, tool_names) -> True to allow (same shape as PermissionGate's approver)
Approver = Callable[[str, List[str]], bool]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]
    source: str = "native"
    risk: str = "read"
    # Optional per-call risk (e.g. Home Assistant: locks are dangerous, lights are not).
    classify: Optional[Callable[[Dict[str, Any]], str]] = None
    # Extra words that make this tool relevant to a request (any language).
    keywords: Iterable[str] = ()
    # May Bot V pick this tool by itself in "auto" chat mode?
    auto: bool = False

    def risk_for(self, args: Dict[str, Any]) -> str:
        risk = self.classify(args) if self.classify else self.risk
        if risk not in RISKS:
            return "blocked"
        return risk

    def spec(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


# --------------------------------------------------------------- validation
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def validate_args(schema: Dict[str, Any], args: Any, path: str = "args") -> List[str]:
    """Check args against the common subset of JSON Schema. Returns error messages."""
    errors: List[str] = []
    expected = schema.get("type")
    if expected:
        types = expected if isinstance(expected, list) else [expected]
        ok = False
        for t in types:
            py = _JSON_TYPES.get(t)
            if py is None:
                ok = True
                break
            if isinstance(args, py) and not (t in ("integer", "number") and isinstance(args, bool)):
                ok = True
                break
        if not ok:
            return [f"{path}: expected {expected}, got {type(args).__name__}"]
    if "enum" in schema and args not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(args, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in args:
                errors.append(f"{path}.{key}: required")
        if schema.get("additionalProperties") is False:
            for key in args:
                if key not in props:
                    errors.append(f"{path}.{key}: not allowed")
        for key, value in args.items():
            if key in props and isinstance(props[key], dict):
                errors.extend(validate_args(props[key], value, f"{path}.{key}"))
    if isinstance(args, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(args):
            errors.extend(validate_args(schema["items"], item, f"{path}[{i}]"))
    return errors


def _words(text: str) -> set:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= 3}


def _keyword_hit(keyword: str, lowered: str) -> bool:
    # English keywords must match whole words ("fan" is not in "fantastic"); Mongolian
    # keywords are stems that take suffixes ("асаа" matches "асаагаад").
    if keyword.isascii():
        return re.search(r"\b" + re.escape(keyword) + r"\b", lowered) is not None
    return keyword in lowered


# ------------------------------------------------------------------ registry
class ToolRegistry:
    def __init__(self, approver: Optional[Approver] = None):
        self.approver = approver
        self._tools: Dict[str, Tool] = {}
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._stats: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- tools
    def register(self, tool: Tool, replace: bool = False) -> None:
        if not re.match(r"^[A-Za-z0-9_.\-]{1,128}$", tool.name):
            raise ValueError(f"invalid tool name {tool.name!r}")
        with self._lock:
            if tool.name in self._tools and not replace:
                raise ValueError(f"tool {tool.name!r} is already registered")
            self._tools[tool.name] = tool

    def unregister_source(self, source: str) -> None:
        with self._lock:
            for name in [n for n, t in self._tools.items() if t.source == source]:
                del self._tools[name]

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def describe(self) -> List[Dict[str, Any]]:
        out = []
        for t in self.list():
            stats = self._stats.get(t.name)
            out.append({
                **t.spec(), "source": t.source, "risk": t.risk if not t.classify else "per call",
                "auto": t.auto,
                "calls": int(stats["calls"]) if stats else 0,
                "avg_ms": round(stats["total_ms"] / stats["calls"], 2) if stats else None,
            })
        return out

    def relevant(self, query: str, *, auto_only: bool = False, limit: int = 8) -> List[Tool]:
        """Tools whose name, description or keywords match the request."""
        words = _words(query)
        lowered = query.lower()
        scored = []
        for tool in self.list():
            if auto_only and not tool.auto:
                continue
            if tool.name.lower() in lowered:
                scored.append((100, tool))
                continue
            keywords = {k.lower() for k in tool.keywords}
            keyword_hits = sum(1 for k in keywords if _keyword_hit(k, lowered))
            overlap = len(words & _words(tool.name.replace("_", " ") + " " + tool.description))
            score = keyword_hits * 3 + overlap
            if keyword_hits or overlap >= 2:
                scored.append((score, tool))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [tool for _, tool in scored[:limit]]

    # -------------------------------------------------------------- calls
    def call(self, name: str, args: Optional[Dict[str, Any]] = None, *,
             task: str = "", approved: bool = False) -> Dict[str, Any]:
        args = {} if args is None else args
        tool = self.get(name)
        if tool is None:
            return {"status": "error", "tool": name, "error": f"unknown tool {name!r}"}
        if not isinstance(args, dict):
            return {"status": "invalid_args", "tool": name, "errors": ["args must be a JSON object"]}
        errors = validate_args(tool.input_schema or {"type": "object"}, args)
        if errors:
            return {"status": "invalid_args", "tool": name, "errors": errors}

        risk = tool.risk_for(args)
        if risk == "blocked":
            return {"status": "denied", "tool": name, "risk": risk,
                    "error": "this action is blocked by Bot V's safety settings"}
        if risk in ("write", "dangerous") and not approved:
            if self.approver is not None:
                try:
                    ok = bool(self.approver(task or f"{name} {json.dumps(args, ensure_ascii=False)}", [name]))
                except Exception:
                    ok = False
                if not ok:
                    return {"status": "denied", "tool": name, "risk": risk, "error": "not approved"}
            else:
                action = self._queue(name, args, risk, task)
                return {"status": "needs_approval", "tool": name, "risk": risk, "action": action}

        started = time.perf_counter()
        try:
            result = tool.handler(args)
            status = "ok"
        except Exception as exc:
            result = None
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        self._record(name, elapsed_ms)
        out = {"status": status, "tool": name, "risk": risk, "elapsed_ms": elapsed_ms}
        if status == "ok":
            out["result"] = result
        else:
            out["error"] = error
        return out

    def _record(self, name: str, elapsed_ms: float) -> None:
        with self._lock:
            s = self._stats.setdefault(name, {"calls": 0, "total_ms": 0.0})
            s["calls"] += 1
            s["total_ms"] += elapsed_ms

    # ---------------------------------------------------------- approvals
    def _queue(self, name: str, args: Dict[str, Any], risk: str, task: str) -> Dict[str, Any]:
        self._expire()
        with self._lock:
            if len(self._pending) >= MAX_PENDING:
                oldest = min(self._pending.values(), key=lambda a: a["created"])
                del self._pending[oldest["id"]]
            action = {"id": uuid.uuid4().hex[:12], "tool": name, "args": args, "risk": risk,
                      "task": task, "created": time.time()}
            self._pending[action["id"]] = action
            return dict(action)

    def _expire(self) -> None:
        cutoff = time.time() - ACTION_TTL_SECONDS
        with self._lock:
            for key in [k for k, a in self._pending.items() if a["created"] < cutoff]:
                del self._pending[key]

    def pending(self) -> List[Dict[str, Any]]:
        self._expire()
        with self._lock:
            return sorted((dict(a) for a in self._pending.values()), key=lambda a: a["created"])

    def approve(self, action_id: str) -> Dict[str, Any]:
        """Run a pending action a person approved."""
        self._expire()
        with self._lock:
            action = self._pending.pop(action_id, None)
        if action is None:
            return {"status": "error", "error": "no such pending action (it may have expired)"}
        return {**self.call(action["tool"], action["args"], task=action["task"], approved=True),
                "action_id": action_id}

    def deny(self, action_id: str) -> Dict[str, Any]:
        with self._lock:
            action = self._pending.pop(action_id, None)
        if action is None:
            return {"status": "error", "error": "no such pending action"}
        return {"status": "denied", "tool": action["tool"], "action_id": action_id}
