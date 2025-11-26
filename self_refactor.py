from utils.llm_client import LLMClient

class SelfRefactor:
    """
    The AI improves its own code.
    """

    def __init__(self):
        self.llm = LLMClient()

    def refactor_code(self, code, weaknesses):
        return self.llm.query(
            "deepseek-coder-v2:16b",
            f"""
Refactor this code based on the weaknesses:
{weaknesses}

Code:
{code}

Return ONLY the improved code.
"""
        )
