from bot_v.agents.base_agent import BaseAgent

class DebugAgent(BaseAgent):
    def debug(self, code):
        return self.think(
            f"Find potential errors in this code:\n{code}"
        )

    def fix(self, code):
        return self.llm.query(
            "coder",
            f"Fix any errors in this code:\n{code}"
        )
