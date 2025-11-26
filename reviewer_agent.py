from AI.Agents.base_agent import BaseAgent

class ReviewerAgent(BaseAgent):
    def review(self, code):
        return self.think(
            f"Review this code and give high-level feedback:\n{code}"
        )
