"""Bot V's tool loop: the local model talks to tools in plain JSON.

Each turn the model replies with exactly one JSON object:

    {"tool": "<name>", "args": {...}}     call a tool
    {"answer": "<text for the user>"}     finish

This works with any model (no native function-calling needed). Only the
tools relevant to the request are shown, which keeps the prompt short: on a
local model, prompt length is what makes tool use feel slow.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from bot_v.llm.client import LLMError
from bot_v.llm.parsing import extract_json
from bot_v.tools.registry import Tool, ToolRegistry

MAX_STEPS = 5
MAX_RESULT_CHARS = 2500

PROMPT = """You are Bot V, a personal assistant that can use tools.
Reply with exactly ONE JSON object and nothing else:
  {{"tool": "<tool name>", "args": {{...}}}}  to use a tool
  {{"answer": "<your reply to the user>"}}   when you are done
Write the answer in the user's language. Use a tool only when it helps.
Actions that change something need the user's approval; Bot V will ask them.

Tools:
{tools}"""


def _compact_schema(schema: Dict[str, Any]) -> str:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts = []
    for name, spec in props.items():
        kind = spec.get("type", "any") if isinstance(spec, dict) else "any"
        parts.append(f"{name}{'' if name in required else '?'}: {kind}")
    return "{" + ", ".join(parts) + "}"


def tools_prompt(tools: List[Tool]) -> str:
    return PROMPT.format(tools="\n".join(
        f"- {t.name} {_compact_schema(t.input_schema)}: {t.description}" for t in tools
    ))


class ToolAgent:
    def __init__(self, llm: Any, registry: ToolRegistry, max_steps: int = MAX_STEPS):
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps

    def run(self, message: str, tools: List[Tool], context: str = "") -> Dict[str, Any]:
        allowed = {t.name for t in tools}
        system = tools_prompt(tools) + (f"\n\n{context}" if context else "")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
        steps: List[Dict[str, Any]] = []

        for _ in range(self.max_steps):
            try:
                reply = self.llm.chat("general", messages)
            except LLMError as exc:
                return {"status": "error", "reply": f"[LLM ERROR] {exc}", "steps": steps}

            try:
                decision = extract_json(reply)
            except (ValueError, LLMError):
                decision = None
            if not isinstance(decision, dict):
                return {"status": "ok", "reply": reply.strip(), "steps": steps}
            if "answer" in decision:
                return {"status": "ok", "reply": str(decision["answer"]), "steps": steps}

            name = decision.get("tool")
            args = decision.get("args") or {}
            messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
            if name not in allowed:
                messages.append({"role": "user", "content":
                                 f"Unknown tool {name!r}. Use one of: {sorted(allowed)}, or answer."})
                continue

            result = self.registry.call(name, args, task=message)
            steps.append({"tool": name, "args": args, "status": result["status"],
                          "elapsed_ms": result.get("elapsed_ms")})
            if result["status"] == "needs_approval":
                return {
                    "status": "needs_approval",
                    "reply": f"Bot V wants to run {name} with {json.dumps(args, ensure_ascii=False)}. Approve?",
                    "action": result["action"],
                    "steps": steps,
                }
            payload = json.dumps(result, ensure_ascii=False, default=str)
            if len(payload) > MAX_RESULT_CHARS:
                payload = payload[:MAX_RESULT_CHARS] + "...(truncated)"
            messages.append({"role": "user", "content": f"Tool result: {payload}"})

        return {"status": "ok", "reply": "I stopped after too many tool steps.", "steps": steps}
