from utils.llm_client import LLMClient

class WeaknessDetector:
    """
    Detects patterns in AI outputs that show weaknesses.
    """

    def __init__(self):
        self.llm = LLMClient()

    def detect(self, output_text):
        result = self.llm.query(
            "deepseek-v2:16b",
            f"""
List weaknesses found in this AI output:

{output_text}

Return as a JSON list of weakness descriptions.
"""
        )
        import json
        try:
            return json.loads(result)
        except:
            return ["general improvement needed"]
