from AI.MultiAgent2.base_agent import BaseAgent

class PlannerAgent(BaseAgent):
    def plan(self, goal):
        return self.think(f"Break into steps: {goal}")

class CoderAgent(BaseAgent):
    def code(self, spec):
        return self.llm.query(
            "deepseek-coder-v2:16b",
            f"Write code for:\n{spec}"
        )

class ReviewerAgent(BaseAgent):
    def review(self, code):
        return self.think(f"Review:\n{code}")

class CriticAgent(BaseAgent):
    def critique(self, text):
        return self.think(f"Critique this:\n{text}")

class SummarizerAgent(BaseAgent):
    def summarize(self, texts):
        joined = "\n---\n".join(texts)
        return self.think(f"Summarize:\n{joined}")
