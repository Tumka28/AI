from bot_v.llm.client import LLMClient

class PerformanceAnalyzer:
    """
    Analyzes AI's recent outputs and scores quality.
    """

    def __init__(self):
        self.llm = LLMClient()

    def score_output(self, output_text):
        score = self.llm.query(
            "general",
            f"""
Rate the quality of this AI output from 1-10:

{output_text}

Only return number.
"""
        )
        try:
            return int(score.strip())
        except ValueError:
            return None
