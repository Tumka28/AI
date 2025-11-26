from utils.llm_client import LLMClient

class BehaviorOptimizer:
    """
    AI improves its reasoning + planning style.
    """

    def __init__(self):
        self.llm = LLMClient()

    def optimize_rules(self, weaknesses):
        return self.llm.query(
            "deepseek-v2:16b",
            f"""
Given these weaknesses:
{weaknesses}

Suggest NEW thinking rules for the AI to improve.

Return rules as a JSON list of thinking improvements.
"""
        )
