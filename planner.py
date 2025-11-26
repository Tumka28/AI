from utils.llm_client import LLMClient

class AutoPlanner:
    """
    Generates step-by-step plan from user goal.
    """

    def __init__(self):
        self.llm = LLMClient()

    def plan(self, goal):
        result = self.llm.query(
            "deepseek-v2:16b",
            f"""
Break the following programming goal into 3–6 steps.

Goal: {goal}

Return steps as a numbered list.
"""
        )
        steps = [s.strip() for s in result.split("\n") if s.strip()]
        return steps
