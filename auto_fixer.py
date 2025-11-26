from utils.llm_client import LLMClient

class AutoFixer:
    def __init__(self):
        self.llm = LLMClient()

    def fix(self, code, error_json):
        return self.llm.query(
            "deepseek-coder-v2:16b",
            f"""
You are a code-fixing AI.

Here is the original code:
{code}

And here is the execution error (JSON):
{error_json}

Fix the code so it runs successfully.
Return ONLY the corrected code.
"""
        )
