import json
from bot_v.llm.client import LLMClient
from bot_v.llm.parsing import extract_json

class ReActEngine:
    """
    ReAct Loop:
    Thought → Action → Observation → repeat
    """
    def __init__(self, tool_map, memory):
        self.llm = LLMClient()
        self.tool_map = tool_map
        self.memory = memory

    def run(self, prompt):
        thoughts = []
        loops = 0

        while loops < 6:
            loops += 1

            react_json = self.llm.query(
                "general",
                f"""
We are using ReAct loop.

User request: {prompt}

Previous steps:
{json.dumps(thoughts, indent=2)}

Return next step in JSON:
{{
  "thought": "reasoning...",
  "action": "tool_name OR finish",
  "args": {{ ... }},
  "answer": "final answer if finish"
}}
Only output JSON.
"""
            )

            try:
                parsed = extract_json(react_json)
            except Exception:
                # fallback → consider as final answer
                return react_json
            if not isinstance(parsed, dict) or "action" not in parsed:
                return react_json

            # if finished, return
            if parsed["action"] == "finish":
                return parsed.get("answer", "No answer provided.")

            tool = parsed["action"]
            args = parsed.get("args", {})

            # execute tool
            if tool in self.tool_map:
                try:
                    result = self.tool_map[tool](**(args if isinstance(args, dict) else {}))
                except Exception as exc:
                    result = f"tool error: {exc}"
                thoughts.append({"tool": tool, "result": result})
            else:
                thoughts.append({"thought": parsed})

        return "ReAct loop did not converge."
