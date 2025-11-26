from AI.Agents.base_agent import BaseAgent

class PlannerAgent(BaseAgent):
    def plan(self, goal):
        response = self.think(
            f"Break down the goal into 3–6 steps.\nGoal: {goal}"
        )
        return response
