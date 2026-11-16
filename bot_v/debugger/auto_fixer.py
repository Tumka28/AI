from bot_v.llm.client import LLMClient

class AutoFixer:
    def __init__(self):
        self.llm = LLMClient()

    def fix(self, code, error_json):
        return self.llm.query(
            "coder",
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
