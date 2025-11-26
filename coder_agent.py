from AI.Agents.base_agent import BaseAgent

class CoderAgent(BaseAgent):
    def write(self, instruction):
        return self.llm.query(
            "deepseek-coder-v2:16b",
            f"Write code for: {instruction}"
        )

    def improve(self, code):
        return self.llm.query(
            "deepseek-coder-v2:16b",
            f"Improve this code:\n{code}"
        )
