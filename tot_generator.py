from llm_client import LLMClient

class ToTGenerator:
    """
    Tree-of-Thought reasoning:
    - generates multiple thought branches
    - each branch = different chain-of-thought direction
    """
    def __init__(self):
        self.llm = LLMClient()

    def generate_branches(self, prompt, n=4):
        branches = []
        for _ in range(n):
            thought = self.llm.query(
                "deepseek-v2:16b",
                f"""
User question: {prompt}

Generate a DIFFERENT line of reasoning (not the final answer).
Keep it concise.
"""
            )
            branches.append(thought.strip())
        return branches
