from utils.llm_client import LLMClient

class AutoImprover:
    """
    Suggests improvements after code runs.
    """

    def __init__(self):
        self.llm = LLMClient()

    def improve(self, current_code, output):
        result = self.llm.query(
            "deepseek-v2:16b",
            f"""
We ran the following code:

{current_code}

Output:
{output}

Suggest improvements to structure, readability, or performance.
Then produce a cleaned-up version of the code.
Return ONLY the improved code.
"""
        )
        return result
