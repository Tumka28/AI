from utils.llm_client import LLMClient

class PerformanceAnalyzer:
    """
    Analyzes AI's recent outputs and scores quality.
    """

    def __init__(self):
        self.llm = LLMClient()

    def score_output(self, output_text):
        score = self.llm.query(
            "deepseek-v2:16b",
            f"""
Rate the quality of this AI output from 1-10:

{output_text}

Only return number.
"""
