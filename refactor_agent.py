from utils.llm_client import LLMClient

class RefactorAgent:
    """
    Uses DeepSeek-Coder-v2 to refactor each file.
    """

    def __init__(self):
        self.llm = LLMClient()

    def refactor(self, path, content):
        instruction = f"""
You are a senior software engineer refactoring a file.

File path: {path}

Refactor rules:
- Improve naming
- Clean unused variables
- Remove dead code
- Improve readability
- Keep functionality identical
- Do NOT add comments about what you changed
- Return ONLY the refactored file content

Original file:
{content}
"""

        result = self.llm.query("deepseek-coder-v2:16b", instruction)
        return result
