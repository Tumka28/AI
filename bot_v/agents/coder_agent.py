from bot_v.agents.base_agent import BaseAgent

class CoderAgent(BaseAgent):
    def write(self, instruction):
        return self.llm.query(
            "coder",
            f"Write code for: {instruction}"
        )

    def improve(self, code):
        return self.llm.query(
            "coder",
            f"Improve this code:\n{code}"
        )
