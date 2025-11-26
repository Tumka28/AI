import json
from llm_client import LLMClient

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
                "deepseek-v2:16b",
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
                parsed = json.loads(react_json)
            except:
                # fallback → consider as final answer
                return react_json

            # if finished, return
            if parsed["action"] == "finish":
                return parsed.get("answer", "No answer provided.")

            tool = parsed["action"]
            args = parsed.get("args", {})

            # execute tool
            if tool in self.tool_map:
                result = self.tool_map[tool](**args)
                thoughts.append({"tool": tool, "result": result})
            else:
                thoughts.append({"thought": parsed})

        return "ReAct loop did not converge."
